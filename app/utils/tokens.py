"""Rough token-count estimation.

None of GTG's providers (DeepBridge's web client, GPTBridge's plain-text
endpoint, or Ollama without a tokenizer loaded) return exact token usage, so
this is a ~4-chars-per-token heuristic for populating the OpenAI-compatible
`usage` field. Treat it as an estimate, not a billing-accurate count.
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def usage_block(prompt_text: str, completion_text: str) -> dict[str, int]:
    prompt_tokens = estimate_tokens(prompt_text)
    completion_tokens = estimate_tokens(completion_text)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
