"""
llm_adapter.py
--------------
Unified LLM calling interface supporting OpenAI, Google Gemini, and Anthropic Claude.
Dispatches to the correct provider based on the ``provider`` parameter.

Usage:
    from src.llm_adapter import call_llm

    json_str, total, inp, out = call_llm(
        provider="openai",
        model_name="gpt-4o",
        api_key="sk-...",
        endpoint="https://api.openai.com/v1",
        system_prompt="You are ...",
        user_content="Extract data from ...",
        page_images=["base64string1", "base64string2"]
    )
"""

import re
import json
import base64
import logging

logger = logging.getLogger(__name__)


def call_llm(
    provider: str,
    model_name: str,
    api_key: str,
    endpoint: str,
    system_prompt: str,
    user_content: str,
    page_images: list = None,
    image_detail: str = "high",
) -> tuple:
    """
    Unified LLM call that dispatches to the appropriate provider.

    Args:
        provider:       LLM provider name (e.g. "OpenAI", "Gemini", "Claude").
        model_name:     Model identifier (e.g. "gpt-4o", "gemini-2.0-flash", "claude-sonnet-4-20250514").
        api_key:        API key for the provider.
        endpoint:       Base URL / endpoint for the provider API (can be None for defaults).
        system_prompt:  System instructions for the model.
        user_content:   User message content (combined prompt + document text).
        page_images:    Optional list of base64-encoded PNG images for multimodal context.
        image_detail:   Detail level for vision models ("high" or "low", default: "high").

    Returns:
        Tuple of (json_string, total_tokens, input_tokens, output_tokens).

    Raises:
        ValueError: If the provider is not supported.
    """
    provider_lower = (provider or "openai").strip().lower()

    if provider_lower == "openai":
        return _call_openai(model_name, api_key, endpoint, system_prompt, user_content, page_images, image_detail=image_detail)
    elif provider_lower in ("gemini", "google"):
        return _call_gemini(model_name, api_key, endpoint, system_prompt, user_content, page_images)
    elif provider_lower in ("claude", "anthropic"):
        return _call_claude(model_name, api_key, endpoint, system_prompt, user_content, page_images)
    else:
        raise ValueError(f"Unsupported LLM provider: '{provider}'. Supported: OpenAI, Gemini, Claude.")


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) that some models wrap around JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?\s*```$", "", text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════
#  OpenAI  (uses the `openai` SDK)
# ═══════════════════════════════════════════════════════════════════════

def _call_openai(model_name, api_key, endpoint, system_prompt, user_content, page_images, image_detail="high"):
    from openai import OpenAI

    client_kwargs = {"api_key": api_key}
    if endpoint:
        client_kwargs["base_url"] = endpoint
    client = OpenAI(**client_kwargs)

    # Build user message — multi-part if images provided
    if page_images:
        user_parts = [{"type": "text", "text": user_content}]
        for img_b64 in page_images:
            user_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": image_detail}
            })
        user_message_content = user_parts
    else:
        user_message_content = user_content

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message_content}
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )

    content = response.choices[0].message.content
    usage = response.usage
    total_tokens = usage.total_tokens if usage else 0
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0

    logger.info(f"[LLM:OpenAI] Model={model_name}, Tokens: total={total_tokens}, in={input_tokens}, out={output_tokens}")
    return _strip_code_fences(content), total_tokens, input_tokens, output_tokens


# ═══════════════════════════════════════════════════════════════════════
#  Google Gemini  (uses the `google-genai` SDK)
# ═══════════════════════════════════════════════════════════════════════

def _call_gemini(model_name, api_key, endpoint, system_prompt, user_content, page_images):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
    )

    # Build content parts
    if page_images:
        contents = [types.Part.from_text(text=user_content)]
        for img_b64 in page_images:
            img_bytes = base64.b64decode(img_b64)
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
    else:
        contents = user_content

    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=config,
    )

    content = response.text
    metadata = response.usage_metadata
    input_tokens = metadata.prompt_token_count if metadata else 0
    output_tokens = metadata.candidates_token_count if metadata else 0
    total_tokens = (metadata.total_token_count if metadata else 0) or (input_tokens + output_tokens)

    logger.info(f"[LLM:Gemini] Model={model_name}, Tokens: total={total_tokens}, in={input_tokens}, out={output_tokens}")
    return _strip_code_fences(content), total_tokens, input_tokens, output_tokens


# ═══════════════════════════════════════════════════════════════════════
#  Anthropic Claude  (uses the `anthropic` SDK)
# ═══════════════════════════════════════════════════════════════════════

def _call_claude(model_name, api_key, endpoint, system_prompt, user_content, page_images):
    import anthropic

    client_kwargs = {"api_key": api_key}
    if endpoint:
        client_kwargs["base_url"] = endpoint
    client = anthropic.Anthropic(**client_kwargs)

    # Build user message content
    if page_images:
        user_parts = []
        for img_b64 in page_images:
            user_parts.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": img_b64,
                }
            })
        user_parts.append({"type": "text", "text": user_content})
        user_message_content = user_parts
    else:
        user_message_content = user_content

    response = client.messages.create(
        model=model_name,
        max_tokens=None,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_message_content},
            {"role": "assistant", "content": "{"}  # Prefill to enforce JSON output
        ]
    )

    # Reattach the prefilled opening brace
    raw_content = "{" + response.content[0].text

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    total_tokens = input_tokens + output_tokens

    logger.info(f"[LLM:Claude] Model={model_name}, Tokens: total={total_tokens}, in={input_tokens}, out={output_tokens}")
    return _strip_code_fences(raw_content), total_tokens, input_tokens, output_tokens
