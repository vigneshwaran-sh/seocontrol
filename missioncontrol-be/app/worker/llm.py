"""
LLM execution layer — calls OpenAI, Gemini, or Claude based on agent config.
All functions are synchronous (for Celery workers).

Two calling modes:
 1. execute_with_llm()        — simple system + user prompt (one-shot)
 2. execute_with_llm_cached() — full messages array (multi-turn, OpenAI cached)

Logging is done here at the point of the actual API call so the logged
request exactly matches what was sent (raw kwargs / params) and the logged
response is the raw text returned by the provider.
"""

import logging
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB logging — writes the raw request + response at the moment of the call
# ---------------------------------------------------------------------------

def _write_log(
    task_id: str,
    agent_id: str,
    space_id: str,
    provider: str,
    model: str,
    request: dict,
    response: str,
    duration_ms: int,
    requested_at: datetime,
) -> None:
    try:
        from app.worker.db import get_sync_db
        db = get_sync_db()
        db.llm_logs.insert_one({
            "task_id": task_id,
            "agent_id": agent_id,
            "space_id": space_id,
            "provider": provider,
            "model": model,
            "request": request,
            "response": response,
            "duration_ms": duration_ms,
            "requested_at": requested_at,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as exc:
        log.warning(f"Failed to persist LLM log: {exc}")


# ---------------------------------------------------------------------------
# One-shot interface (used by researcher, topic validator)
# ---------------------------------------------------------------------------

def execute_with_llm(
    provider: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    *,
    task_id: str = "",
    agent_id: str = "",
    space_id: str = "",
) -> str:
    """
    Send a prompt to the configured LLM and return the generated text.
    Raises on failure so the caller can handle retries / error comments.
    """
    if provider == "openai":
        return _call_openai(
            api_key, model, system_prompt, user_prompt,
            task_id=task_id, agent_id=agent_id, space_id=space_id,
        )
    elif provider == "gemini":
        return _call_gemini(
            api_key, model, system_prompt, user_prompt,
            task_id=task_id, agent_id=agent_id, space_id=space_id,
        )
    elif provider == "claude":
        return _call_claude(
            api_key, model, system_prompt, user_prompt,
            task_id=task_id, agent_id=agent_id, space_id=space_id,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")


# ---------------------------------------------------------------------------
# Cached / multi-turn interface (used by writer & validator revision loop)
# ---------------------------------------------------------------------------

def execute_with_llm_cached(
    provider: str,
    model: str,
    api_key: str,
    messages: list[dict],
    *,
    task_id: str = "",
    agent_id: str = "",
    space_id: str = "",
) -> tuple[str, list[dict]]:
    """
    Send a full conversation (messages array) to the LLM.

    For OpenAI  — sends the entire array so the API can cache the prefix.
    For others  — extracts system + last user message and calls normally.

    Returns (response_text, updated_messages) where updated_messages has the
    new assistant turn appended.
    """
    if provider == "openai":
        response_text = _call_openai_messages(
            api_key, model, messages,
            task_id=task_id, agent_id=agent_id, space_id=space_id,
        )
    elif provider == "gemini":
        system_prompt, user_prompt = _extract_system_and_last_user(messages)
        response_text = _call_gemini(
            api_key, model, system_prompt, user_prompt,
            task_id=task_id, agent_id=agent_id, space_id=space_id,
        )
    elif provider == "claude":
        system_prompt, user_prompt = _extract_system_and_last_user(messages)
        response_text = _call_claude(
            api_key, model, system_prompt, user_prompt,
            task_id=task_id, agent_id=agent_id, space_id=space_id,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")

    updated_messages = messages + [{"role": "assistant", "content": response_text}]
    return response_text, updated_messages


def _extract_system_and_last_user(messages: list[dict]) -> tuple[str, str]:
    """Extract system prompt and the last user message from a messages array."""
    system_prompt = ""
    user_prompt = ""
    for msg in messages:
        if msg["role"] == "system":
            system_prompt = msg["content"]
        elif msg["role"] == "user":
            user_prompt = msg["content"]  # keeps overwriting → last one wins
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# OpenAI — one-shot
# ---------------------------------------------------------------------------

def _call_openai(
    api_key: str, model: str, system_prompt: str, user_prompt: str,
    *, task_id: str = "", agent_id: str = "", space_id: str = "",
) -> str:
    return _call_openai_messages(
        api_key, model,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        task_id=task_id, agent_id=agent_id, space_id=space_id,
    )


# ---------------------------------------------------------------------------
# OpenAI — messages array (enables prompt caching on prefix)
# ---------------------------------------------------------------------------

def _call_openai_messages(
    api_key: str, model: str, messages: list[dict],
    *, task_id: str = "", agent_id: str = "", space_id: str = "",
) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    kwargs: dict = {
        "model": model,
        "messages": messages,
    }

    requested_at = datetime.now(timezone.utc)
    t0 = time.time()

    try:
        kwargs["max_completion_tokens"] = 16384
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        if "max_completion_tokens" in str(exc):
            kwargs.pop("max_completion_tokens")
            kwargs["max_tokens"] = 4096
            response = client.chat.completions.create(**kwargs)
        else:
            raise

    duration_ms = int((time.time() - t0) * 1000)
    content = response.choices[0].message.content or ""

    # Log cache stats if available
    usage = response.usage
    if usage and hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
        details = usage.prompt_tokens_details
        cached = getattr(details, "cached_tokens", 0)
        total = usage.prompt_tokens
        if cached:
            log.info(
                f"OpenAI cache hit: {cached}/{total} prompt tokens cached "
                f"({100 * cached // total}%)"
            )

    # Reasoning models may exhaust the token budget on reasoning and
    # return empty content. Detect and raise so the caller can retry.
    if not content.strip() and response.choices[0].finish_reason == "length":
        raise ValueError(
            f"Model '{model}' exhausted token limit on reasoning with no output. "
            f"Usage: {response.usage}"
        )

    _write_log(
        task_id=task_id,
        agent_id=agent_id,
        space_id=space_id,
        provider="openai",
        model=model,
        request=kwargs,
        response=content,
        duration_ms=duration_ms,
        requested_at=requested_at,
    )

    return content


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

def _call_gemini(
    api_key: str, model: str, system_prompt: str, user_prompt: str,
    *, task_id: str = "", agent_id: str = "", space_id: str = "",
) -> str:
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    gen_model = genai.GenerativeModel(
        model_name=model,
        system_instruction=system_prompt,
    )

    requested_at = datetime.now(timezone.utc)
    t0 = time.time()
    response = gen_model.generate_content(user_prompt)
    duration_ms = int((time.time() - t0) * 1000)

    content = response.text or ""

    _write_log(
        task_id=task_id,
        agent_id=agent_id,
        space_id=space_id,
        provider="gemini",
        model=model,
        request={
            "model": model,
            "system_instruction": system_prompt,
            "prompt": user_prompt,
        },
        response=content,
        duration_ms=duration_ms,
        requested_at=requested_at,
    )

    return content


# ---------------------------------------------------------------------------
# Claude (Anthropic)
# ---------------------------------------------------------------------------

def _call_claude(
    api_key: str, model: str, system_prompt: str, user_prompt: str,
    *, task_id: str = "", agent_id: str = "", space_id: str = "",
) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)

    kwargs = {
        "model": model,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    requested_at = datetime.now(timezone.utc)
    t0 = time.time()
    message = client.messages.create(**kwargs)
    duration_ms = int((time.time() - t0) * 1000)

    content = "".join(block.text for block in message.content if hasattr(block, "text"))

    _write_log(
        task_id=task_id,
        agent_id=agent_id,
        space_id=space_id,
        provider="claude",
        model=model,
        request=kwargs,
        response=content,
        duration_ms=duration_ms,
        requested_at=requested_at,
    )

    return content
