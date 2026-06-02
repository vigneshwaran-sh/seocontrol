"""
Blog thumbnail generator — renders an SVG template with a dynamic title
and saves it to the assets/ folder.
"""

import logging
import re
import textwrap
from pathlib import Path

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = _PROJECT_ROOT / "assets"


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:80].strip("-")


def _wrap_title(title: str, max_chars_per_line: int = 30) -> list[str]:
    """Word-wrap the title into lines for the SVG text area."""
    lines = textwrap.wrap(title, width=max_chars_per_line)
    return lines[:5]


def _escape_xml(text: str) -> str:
    """Escape special XML characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _build_svg(title: str) -> str:
    """Build an SVG string from the blog thumbnail template."""
    lines = _wrap_title(title)
    line_count = len(lines)

    line_height = 72
    total_text_height = line_count * line_height
    start_y = 260 - (total_text_height / 2) + line_height / 2 + 120

    tspan_elements = []
    for idx, line in enumerate(lines):
        escaped = _escape_xml(line)
        tspan_elements.append(
            f'    <tspan x="600" dy="{line_height if idx > 0 else 0}">{escaped}</tspan>'
        )

    tspans = "\n".join(tspan_elements)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800" width="1200" height="800">
  <defs>
    <linearGradient id="borderGradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#010729;stop-opacity:1" />
      <stop offset="50%" style="stop-color:#2f5cff;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#000000;stop-opacity:1" />
    </linearGradient>
    <linearGradient id="textGradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#010729" />
      <stop offset="50%" style="stop-color:#2f5cff" />
      <stop offset="100%" style="stop-color:#000000" />
    </linearGradient>
  </defs>

  <rect width="1200" height="800" fill="#FFF"/>
  <rect x="0" y="0" width="1200" height="800" fill="url(#borderGradient)"/>
  <rect x="45" y="45" width="1110" height="710" fill="#FFF" rx="15"/>

  <text
    x="600"
    y="{start_y}"
    text-anchor="middle"
    font-family="Montserrat, Arial, Helvetica, sans-serif"
    font-size="56"
    font-weight="800"
    fill="url(#textGradient)"
    letter-spacing="-0.5">
{tspans}
  </text>

  <line x1="110" y1="575" x2="1090" y2="575" stroke="#dbe2ec" stroke-width="3"/>

  <text
    x="600"
    y="620"
    text-anchor="middle"
    font-family="Montserrat, Arial, Helvetica, sans-serif"
    font-size="22"
    font-weight="800"
    letter-spacing="3"
    fill="#2f5cff">REVIEWHANDY.COM</text>
</svg>"""

    return svg


def generate_thumbnail(title: str, filename: str | None = None) -> str:
    """
    Generate a blog thumbnail SVG from a title.

    Args:
        title: The blog post title to render on the thumbnail.
        filename: Optional custom filename (without extension).
                  Defaults to a slugified version of the title.

    Returns:
        Absolute path to the generated SVG file.
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    if not filename:
        filename = _slugify(title)
    if not filename:
        filename = "thumbnail"

    svg_path = ASSETS_DIR / f"{filename}.svg"
    svg_string = _build_svg(title)
    svg_path.write_text(svg_string, encoding="utf-8")

    log.info(f"Generated thumbnail: {svg_path}")
    return str(svg_path)


def delete_thumbnail(filename: str) -> bool:
    """
    Delete a thumbnail file from the assets folder.

    Args:
        filename: The filename (with or without .svg extension).

    Returns:
        True if the file was deleted, False if it didn't exist.
    """
    if not filename.endswith(".svg"):
        filename = f"{filename}.svg"

    file_path = ASSETS_DIR / filename
    if file_path.exists():
        file_path.unlink()
        log.info(f"Deleted thumbnail: {file_path}")
        return True

    log.warning(f"Thumbnail not found: {file_path}")
    return False
