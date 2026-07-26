"""
Model-Agnostic LLM & Embedding Provider
========================================

Uses **LiteLLM** so you can switch between providers by changing one config value.

Supported LLM model strings (set via Streamlit secrets  →  LLM_MODEL):
  • "gemini/gemini-2.0-flash"                   (Google — default, free tier)
  • "nvidia_nim/minimaxai/minimax-m3"            (Nvidia NIM — MiniMax M3)
  • "gpt-4o"                                     (OpenAI)
  • Any other LiteLLM-compatible model string.

Embedding:
  Uses Google Generative AI SDK for multimodal embeddings (text + images).
  The embedding model is independent of the chat LLM — you can run Gemini
  embeddings while chatting with MiniMax.

Environment / secrets expected:
  GEMINI_API_KEY          — required for Gemini LLM & embeddings
  OPENAI_API_KEY          — required if using OpenAI models
  NVIDIA_NIM_API_KEY      — required if using Nvidia NIM models
  LLM_MODEL               — model string (default: gemini/gemini-2.0-flash)
  EMBEDDING_MODEL         — embedding model (default: models/text-embedding-004)
"""

from __future__ import annotations

import os
import base64
from typing import Any, Optional, List, Dict

import streamlit as st
import litellm

# ── Configuration ──

def _secret(key: str, default: str = "") -> str:
    """Read from Streamlit secrets first, then env vars."""
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, default)


def get_llm_model() -> str:
    return _secret("LLM_MODEL", "gemini/gemini-2.0-flash")


def get_embedding_model() -> str:
    return _secret("EMBEDDING_MODEL", "models/text-embedding-004")


def _set_api_keys() -> None:
    """Push secrets into env vars so LiteLLM / Google SDK can find them."""
    mappings = {
        "GEMINI_API_KEY": "GEMINI_API_KEY",
        "OPENAI_API_KEY": "OPENAI_API_KEY",
        "NVIDIA_NIM_API_KEY": "NVIDIA_NIM_API_KEY",
    }
    for secret_key, env_key in mappings.items():
        val = _secret(secret_key)
        if val:
            os.environ[env_key] = val
    # LiteLLM also checks GOOGLE_API_KEY for Gemini
    gemini_key = _secret("GEMINI_API_KEY")
    if gemini_key:
        os.environ["GOOGLE_API_KEY"] = gemini_key


# Initialize keys on import
_set_api_keys()


# ═══════════════════════════════════════════════════════════════════════
#  Chat / Completion
# ═══════════════════════════════════════════════════════════════════════

def chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 4096,
    stream: bool = False,
    model: Optional[str] = None,
) -> Any:
    """Send a chat-completion request via LiteLLM.

    Works identically regardless of the backing provider.

    Args:
        messages: OpenAI-format messages list.
        temperature: Sampling temperature.
        max_tokens: Max tokens in the response.
        stream: If True, returns a generator of delta chunks.
        model: Override the default model for this single call.

    Returns:
        LiteLLM ModelResponse (or a streaming generator).
    """
    _set_api_keys()
    mdl = model or get_llm_model()
    return litellm.completion(
        model=mdl,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream,
    )


def chat_stream(
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 4096,
    model: Optional[str] = None,
):
    """Convenience wrapper that always streams."""
    return chat(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        model=model,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Embeddings  (Google Generative AI — supports multimodal)
# ═══════════════════════════════════════════════════════════════════════

def _get_genai_client():
    """Lazy-import and configure the Google GenAI client."""
    import google.generativeai as genai

    api_key = _secret("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
    return genai


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a batch of text strings using the configured embedding model.

    Returns:
        List of embedding vectors (each a list of floats).
    """
    genai = _get_genai_client()
    model_name = get_embedding_model()

    result = genai.embed_content(
        model=model_name,
        content=texts,
        task_type="retrieval_document",
    )
    return result["embedding"]


def embed_query(text: str) -> List[float]:
    """Embed a single query string (uses retrieval_query task type)."""
    genai = _get_genai_client()
    model_name = get_embedding_model()

    result = genai.embed_content(
        model=model_name,
        content=text,
        task_type="retrieval_query",
    )
    return result["embedding"]


def embed_image(image_bytes: bytes) -> List[float]:
    """Embed an image using Gemini's multimodal embedding.

    Falls back to describing the image via vision LLM and embedding the text
    if the embedding model doesn't support direct image input.
    """
    try:
        genai = _get_genai_client()
        model_name = get_embedding_model()

        # Construct an image Part for the API
        import google.generativeai as genai_module

        image_part = {"mime_type": "image/png", "data": image_bytes}
        result = genai_module.embed_content(
            model=model_name,
            content=image_part,
            task_type="retrieval_document",
        )
        return result["embedding"]
    except Exception:
        # Fallback: describe the image with vision LLM, then embed the text
        description = describe_image(image_bytes)
        return embed_texts([description])[0]


def describe_image(image_bytes: bytes, prompt: str = "Describe this image in detail, including any text, data, charts, or tables visible.") -> str:
    """Use the vision LLM to generate a text description of an image."""
    _set_api_keys()
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                },
            ],
        }
    ]
    resp = litellm.completion(
        model=get_llm_model(),
        messages=messages,
        max_tokens=1024,
        temperature=0.2,
    )
    return resp.choices[0].message.content


# ═══════════════════════════════════════════════════════════════════════
#  Utility
# ═══════════════════════════════════════════════════════════════════════

def get_provider_info() -> Dict[str, str]:
    """Return a summary of the current LLM configuration."""
    mdl = get_llm_model()
    emb = get_embedding_model()
    provider = mdl.split("/")[0] if "/" in mdl else "openai"
    return {
        "llm_model": mdl,
        "embedding_model": emb,
        "provider": provider,
    }


def test_connection() -> bool:
    """Quick health-check: send a trivial prompt and see if we get a response."""
    try:
        resp = chat(
            [{"role": "user", "content": "Reply with OK"}],
            max_tokens=10,
            temperature=0,
        )
        return bool(resp.choices[0].message.content)
    except Exception:
        return False
