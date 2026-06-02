"""
Notion integration — creates / reads / updates database entries.
Uses the Notion API for database operations and page content.
"""

import logging
import mimetypes
import re
from pathlib import Path

import httpx
import markdownify
from notion_client import Client

log = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_blog_entry(
    token: str,
    database_id: str,
    title: str,
    slug: str,
    description: str,
    category: str,
    tags: list[str],
    focus_keyword: str,
    meta_title: str,
    meta_description: str,
    content: str,
    status: str = "Draft",
) -> dict:
    """
    Create a new entry in the Notion Blogs database.
    Sets all property columns and writes the blog body as page content.
    Returns {"page_id": ..., "url": ...}.
    """
    notion = Client(auth=token)
    db_id = _normalize_id(database_id)

    # Build properties
    properties = {
        "title": {"title": [{"text": {"content": title}}]},
        "slug": {"rich_text": [{"text": {"content": slug}}]},
        "status": {"status": {"name": status}},
        "description": {"rich_text": [{"text": {"content": description}}]},
        "category": {"rich_text": [{"text": {"content": category}}]},
        "tags": {"multi_select": [{"name": t.strip()} for t in tags if t.strip()]},
        "focus_keyword": {"rich_text": [{"text": {"content": focus_keyword}}]},
        "meta_title": {"rich_text": [{"text": {"content": meta_title}}]},
        "meta_description": {"rich_text": [{"text": {"content": meta_description}}]},
    }

    # Convert content (HTML or Markdown) to Notion blocks
    if _looks_like_html(content):
        md_content = markdownify.markdownify(
            content,
            heading_style="ATX",
            bullets="-",
            strip=["img", "script", "style"],
        )
    else:
        md_content = content

    md_content = _clean_markdown(md_content)
    blocks = _markdown_to_blocks(md_content)

    # Notion API limits children to 100 blocks per request.
    # Create page with the first batch, then append the rest.
    first_batch = blocks[:100]
    remaining = blocks[100:]

    page = notion.pages.create(
        parent={"database_id": db_id},
        properties=properties,
        children=first_batch,
    )

    page_id = page.get("id", "")
    page_url = page.get("url", "")

    # Append remaining blocks in chunks of 100
    for i in range(0, len(remaining), 100):
        chunk = remaining[i : i + 100]
        notion.blocks.children.append(block_id=page_id, children=chunk)

    log.info(f"Created Notion blog entry: {page_id} — {page_url} ({len(blocks)} blocks)")
    return {"page_id": page_id, "url": page_url}


def update_blog_status(token: str, page_id: str, status: str) -> None:
    """Update the status property of a Notion blog page."""
    notion = Client(auth=token)
    notion.pages.update(
        page_id=page_id,
        properties={
            "status": {"status": {"name": status}},
        },
    )
    log.info(f"Updated Notion page {page_id} status to '{status}'")


def update_blog_content(
    token: str,
    page_id: str,
    content: str,
    properties: dict | None = None,
) -> None:
    """
    Replace the body content of a Notion blog page.
    Optionally update properties too.
    """
    notion = Client(auth=token)
    norm_id = _normalize_id(page_id)

    # Erase the entire page body (and update properties) in a single request.
    # Notion's `erase_content: true` flag wipes all existing blocks at once —
    # no need to list + delete blocks individually.
    payload: dict = {"erase_content": True}
    if properties:
        payload["properties"] = properties

    resp = httpx.patch(
        f"{NOTION_API}/pages/{norm_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        json=payload,
    )
    resp.raise_for_status()
    log.info(f"Erased content of Notion page {page_id}")

    # Convert and append new content
    if _looks_like_html(content):
        md_content = markdownify.markdownify(
            content,
            heading_style="ATX",
            bullets="-",
            strip=["img", "script", "style"],
        )
    else:
        md_content = content

    md_content = _clean_markdown(md_content)
    blocks = _markdown_to_blocks(md_content)

    # Notion API limits children to 100 blocks per request
    for i in range(0, len(blocks), 100):
        chunk = blocks[i : i + 100]
        notion.blocks.children.append(block_id=page_id, children=chunk)

    log.info(f"Updated Notion page {page_id} content")


def list_blog_titles(token: str, database_id: str, limit: int = 200) -> list[str]:
    """
    Return the titles of existing entries in the Notion Blogs database.

    Works under the new Notion data-source API model (version 2025-09-03+):
    a database holds one or more data sources, and rows are queried per data
    source (`/v1/data_sources/{id}/query`). Falls back to the legacy
    `/v1/databases/{id}/query` for older single-source databases.

    Best-effort — raises nothing; returns whatever it could collect.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    db_norm = _normalize_id(database_id)
    titles: list[str] = []

    def _collect(query_url: str) -> None:
        cursor = None
        while len(titles) < limit:
            body: dict = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            r = httpx.post(query_url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
            for row in data.get("results", []):
                for val in row.get("properties", {}).values():
                    if val.get("type") == "title":
                        text = _extract_rich_text(val.get("title", []))
                        if text:
                            titles.append(text)
                        break
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

    # Resolve the database's data sources (new model). Single-source / legacy
    # databases return no `data_sources` array, so we fall back to the old path.
    data_source_ids: list[str] = []
    try:
        dbresp = httpx.get(f"{NOTION_API}/databases/{db_norm}", headers=headers)
        dbresp.raise_for_status()
        for ds in dbresp.json().get("data_sources", []) or []:
            if ds.get("id"):
                data_source_ids.append(ds["id"])
    except Exception as exc:
        log.warning(f"Could not retrieve Notion database {database_id}: {exc}")

    if data_source_ids:
        for ds_id in data_source_ids:
            try:
                _collect(f"{NOTION_API}/data_sources/{_normalize_id(ds_id)}/query")
            except Exception as exc:
                log.warning(f"Notion data-source query failed for {ds_id}: {exc}")
    else:
        try:
            _collect(f"{NOTION_API}/databases/{db_norm}/query")
        except Exception as exc:
            log.warning(f"Notion database query failed for {database_id}: {exc}")

    log.info(f"Fetched {len(titles)} existing Notion blog title(s) for dedup")
    return titles[:limit]


def read_page_content(token: str, page_id: str) -> str:
    """
    Read all text content from a Notion page.
    Returns plain text representation.
    """
    notion = Client(auth=token)
    blocks = _collect_all_blocks(notion, page_id)
    return _blocks_to_text(blocks)


def read_page_properties(token: str, page_id: str) -> dict:
    """Read all properties of a Notion page."""
    notion = Client(auth=token)
    page = notion.pages.retrieve(page_id=page_id)
    props = page.get("properties", {})

    result = {}
    for key, val in props.items():
        prop_type = val.get("type", "")
        if prop_type == "title":
            result[key] = _extract_rich_text(val.get("title", []))
        elif prop_type == "rich_text":
            result[key] = _extract_rich_text(val.get("rich_text", []))
        elif prop_type == "status":
            result[key] = (val.get("status") or {}).get("name", "")
        elif prop_type == "multi_select":
            result[key] = [opt["name"] for opt in val.get("multi_select", [])]
        elif prop_type == "select":
            result[key] = (val.get("select") or {}).get("name", "")
        else:
            result[key] = str(val)

    return result


def upload_image_to_page(token: str, page_id: str, file_path: str) -> dict:
    """
    Upload a local image to a Notion page (inserted at the top).

    Flow:
      1. POST /file_uploads          → get upload id
      2. POST /file_uploads/{id}/send → send the file (multipart)
      3. PATCH /blocks/{page_id}/children → add image block at position: start

    Args:
        token: Notion integration token.
        page_id: The Notion page to add the image to.
        file_path: Absolute path to the local image file.

    Returns:
        {"file_upload_id": ..., "page_id": ...}
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {file_path}")

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
    }

    # 1 — Create file upload object
    resp = httpx.post(
        f"{NOTION_API}/file_uploads",
        headers={**headers, "Content-Type": "application/json"},
    )
    resp.raise_for_status()
    file_upload_id = resp.json()["id"]
    log.info(f"Created file upload: {file_upload_id}")

    # 2 — Send file content
    with open(path, "rb") as f:
        resp = httpx.post(
            f"{NOTION_API}/file_uploads/{file_upload_id}/send",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_VERSION,
            },
            files={"file": (path.name, f)},
        )
    resp.raise_for_status()
    log.info(f"Uploaded file content for {file_upload_id}")

    # 3 — Add image block at the top of the page
    resp = httpx.patch(
        f"{NOTION_API}/blocks/{page_id}/children",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "children": [
                {
                    "type": "image",
                    "image": {
                        "caption": [],
                        "type": "file_upload",
                        "file_upload": {"id": file_upload_id},
                    },
                }
            ],
            "position": {"type": "start"},
        },
    )
    resp.raise_for_status()

    log.info(f"Uploaded image {path.name} to Notion page {page_id} (at top)")
    return {"file_upload_id": file_upload_id, "page_id": page_id}


def get_first_image_url(token: str, page_id: str) -> str | None:
    """
    Return the URL of the first image block on a Notion page (top to bottom),
    or None if the page has no image. Handles uploaded files (`file`),
    external images (`external`), and unresolved `file_upload` blocks.
    """
    notion = Client(auth=token)
    cursor = None
    while True:
        kwargs = {"block_id": _normalize_id(page_id)}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = notion.blocks.children.list(**kwargs)
        for block in response.get("results", []):
            if block.get("type") != "image":
                continue
            img = block.get("image", {})
            itype = img.get("type")
            url = (img.get(itype) or {}).get("url") if itype else None
            if url:
                return url
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    return None


def set_thumbnail_url(token: str, page_id: str, url: str) -> None:
    """
    Set the `thumbnail_url` property on a Notion blog page (a URL-type column).
    """
    notion = Client(auth=token)
    notion.pages.update(
        page_id=page_id,
        properties={"thumbnail_url": {"url": url}},
    )
    log.info(f"Set thumbnail_url on Notion page {page_id}")


def get_page_id_by_slug(token: str, database_id: str, slug: str) -> str | None:
    """
    Look up a Notion page ID by its slug property.

    Args:
        token: Notion integration token.
        database_id: The Notion database to query.
        slug: The slug value to search for.

    Returns:
        Page ID if found, None otherwise.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    resp = httpx.post(
        f"{NOTION_API}/databases/{_normalize_id(database_id)}/query",
        headers=headers,
        json={
            "filter": {
                "property": "slug",
                "title": {"equals": slug},
            }
        },
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])

    if results:
        page_id = results[0]["id"]
        log.info(f"Found page for slug '{slug}': {page_id}")
        return page_id

    log.warning(f"No page found for slug '{slug}'")
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_rich_text(rich_text_list: list) -> str:
    """Extract plain text from a Notion rich_text array."""
    return "".join(item.get("plain_text", "") for item in rich_text_list)


def _collect_all_blocks(notion: Client, block_id: str) -> list:
    """Recursively collect all blocks from a page."""
    all_blocks = []
    cursor = None
    while True:
        kwargs = {"block_id": block_id}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = notion.blocks.children.list(**kwargs)
        results = response.get("results", [])
        all_blocks.extend(results)
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    return all_blocks


def _blocks_to_text(blocks: list) -> str:
    """Convert Notion blocks to plain text."""
    lines = []
    for block in blocks:
        btype = block.get("type", "")
        data = block.get(btype, {})
        rich_text = data.get("rich_text", [])
        text = _extract_rich_text(rich_text)

        if btype.startswith("heading_"):
            level = btype[-1]
            lines.append(f"{'#' * int(level)} {text}")
        elif btype == "paragraph":
            lines.append(text)
        elif btype == "bulleted_list_item":
            lines.append(f"- {text}")
        elif btype == "numbered_list_item":
            lines.append(f"1. {text}")
        elif btype == "code":
            lang = data.get("language", "")
            lines.append(f"```{lang}\n{text}\n```")
        elif btype == "quote":
            lines.append(f"> {text}")
        elif btype == "divider":
            lines.append("---")
        elif text:
            lines.append(text)

    return "\n\n".join(lines)


def _looks_like_html(text: str) -> bool:
    """Check if text contains HTML tags."""
    return bool(re.search(r"<[a-zA-Z][^>]*>", text[:500]))


def _normalize_id(raw_id: str) -> str:
    """
    Accept IDs in various formats:
    - Full URL: https://www.notion.so/workspace/abc123def456...
    - UUID: abc123de-f456-...
    - Raw ID: abc123def456...
    """
    # Extract from URL
    if "notion.so" in raw_id:
        parts = raw_id.rstrip("/").split("/")[-1]
        # Remove query params
        parts = parts.split("?")[0]
        match = re.search(r"([a-f0-9]{32})$", parts.replace("-", ""))
        if match:
            raw_hex = match.group(1)
            return f"{raw_hex[:8]}-{raw_hex[8:12]}-{raw_hex[12:16]}-{raw_hex[16:20]}-{raw_hex[20:]}"

    # Strip dashes and reformat as UUID if needed
    clean = raw_id.replace("-", "")
    if len(clean) == 32 and all(c in "0123456789abcdef" for c in clean.lower()):
        return f"{clean[:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:]}"

    return raw_id


def _clean_markdown(md: str) -> str:
    """Clean up markdown artifacts from HTML conversion."""
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = "\n".join(line.rstrip() for line in md.splitlines())
    return md.strip()


def _markdown_to_blocks(md: str) -> list[dict]:
    """
    Convert markdown text to Notion block objects.
    Handles headings, paragraphs, bullet lists, numbered lists, and code blocks.
    """
    lines = md.split("\n")
    blocks = []
    i = 0
    in_code_block = False
    code_lines = []
    code_lang = ""

    while i < len(lines):
        line = lines[i]

        # Code block toggle
        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_lang = line.strip()[3:].strip()
                code_lines = []
            else:
                in_code_block = False
                code_text = "\n".join(code_lines)
                # Notion limits rich_text content to 2000 chars
                if len(code_text) > 2000:
                    code_text = code_text[:2000]
                blocks.append({
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": code_text}}],
                        "language": code_lang or "plain text",
                    },
                })
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            i += 1
            continue

        # Headings
        if stripped.startswith("# "):
            blocks.append(_heading_block(stripped[2:], 1))
        elif stripped.startswith("## "):
            blocks.append(_heading_block(stripped[3:], 2))
        elif stripped.startswith("### "):
            blocks.append(_heading_block(stripped[4:], 3))

        # Bulleted list
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append(_list_item_block(stripped[2:], "bulleted"))

        # Numbered list
        elif re.match(r"^\d+\.\s", stripped):
            text = re.sub(r"^\d+\.\s", "", stripped)
            blocks.append(_list_item_block(text, "numbered"))

        # Blockquote
        elif stripped.startswith("> "):
            blocks.append({
                "type": "quote",
                "quote": {
                    "rich_text": _parse_inline_formatting(stripped[2:]),
                },
            })

        # Horizontal rule
        elif stripped in ("---", "***", "___"):
            blocks.append({"type": "divider", "divider": {}})

        # Regular paragraph
        else:
            blocks.append({
                "type": "paragraph",
                "paragraph": {
                    "rich_text": _parse_inline_formatting(stripped),
                },
            })

        i += 1

    return blocks


def _heading_block(text: str, level: int) -> dict:
    key = f"heading_{level}"
    return {
        "type": key,
        key: {
            "rich_text": _parse_inline_formatting(text),
        },
    }


def _list_item_block(text: str, style: str) -> dict:
    key = f"{style}_list_item"
    return {
        "type": key,
        key: {
            "rich_text": _parse_inline_formatting(text),
        },
    }


def _parse_inline_formatting(text: str) -> list[dict]:
    """
    Parse inline markdown formatting (bold, italic, code, links)
    into Notion rich_text objects.
    """
    parts = []
    pattern = re.compile(
        r"(\*\*(.+?)\*\*)"        # bold
        r"|(\*(.+?)\*)"           # italic
        r"|(`(.+?)`)"             # inline code
        r"|(\[(.+?)\]\((.+?)\))"  # link
    )

    last_end = 0
    for match in pattern.finditer(text):
        if match.start() > last_end:
            plain = text[last_end:match.start()]
            if plain:
                parts.append(_text_obj(plain))

        if match.group(2):  # bold
            parts.append(_text_obj(match.group(2), bold=True))
        elif match.group(4):  # italic
            parts.append(_text_obj(match.group(4), italic=True))
        elif match.group(6):  # code
            parts.append(_text_obj(match.group(6), code=True))
        elif match.group(8):  # link
            parts.append(_text_obj(match.group(8), link=match.group(9)))

        last_end = match.end()

    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            parts.append(_text_obj(remaining))

    if not parts:
        parts.append(_text_obj(text))

    return parts


def _text_obj(
    content: str,
    bold: bool = False,
    italic: bool = False,
    code: bool = False,
    link: str | None = None,
) -> dict:
    """Build a Notion rich_text object."""
    # Notion limits each text content to 2000 chars
    if len(content) > 2000:
        content = content[:2000]

    obj: dict = {
        "type": "text",
        "text": {
            "content": content,
        },
    }
    if link:
        obj["text"]["link"] = {"url": link}

    annotations = {}
    if bold:
        annotations["bold"] = True
    if italic:
        annotations["italic"] = True
    if code:
        annotations["code"] = True
    if annotations:
        obj["annotations"] = annotations

    return obj
