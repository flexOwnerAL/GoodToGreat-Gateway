"""Маппинг алиасов Onyx → реальные ID моделей FreeTheAI.

ID сформата: fta/<seller>/<model>, где seller — bbl, cat, dog, zai, fox, ...
Список живой: https://api.freetheai.org/v1/models
"""

ONYX_ALIASES = {
    # --- Anthropic (dog) ---
    "onyx:claude-5-sonnet":    "fta/dog/claude-5-sonnet",
    "onyx:claude-4.6-sonnet":  "fta/dog/claude-4-6-sonnet",
    "onyx:claude-4.5-sonnet":  "fta/dog/claude-4-5-sonnet",
    "onyx:claude-4.5-haiku":   "fta/dog/claude-4-5-haiku",
    "onyx:claude-fable-5.1":   "fta/dog/claude-fable-5.1",
    "onyx:claude-fable-5":     "fta/dog/claude-fable-5",

    # --- OpenAI (bbl) ---
    "onyx:gpt-5.4-mini":       "fta/bbl/gpt-5.4-mini",

    # --- Google Gemini (bbl) ---
    "onyx:gemini-3.5-flash":   "fta/bbl/gemini-3.5-flash",
    "onyx:gemini-3.1-flash-lite": "fta/bbl/gemini-3.1-flash-lite",
    "onyx:gemini-3-flash":     "fta/bbl/gemini-3-flash-preview",
    "onyx:gemini-2.5-flash-lite": "fta/bbl/gemini-2.5-flash-lite",

    # --- Grok (bbl) ---
    "onyx:grok-4-fast":        "fta/bbl/grok-4-1-fast-non-reasoning",

    # --- DeepSeek (cat) ---
    "onyx:deepseek-v4-flash":  "fta/cat/deepseek-ai/deepseek-v4-flash-0731",

    # --- MiniMax (cat) ---
    "onyx:minimax-m2.7":       "fta/cat/minimaxai/minimax-m2.7",

    # --- ZAI GLM ---
    "onyx:glm-5.3":            "fta/zai/glm-5.3",
}

def resolve(model: str) -> str:
    return ONYX_ALIASES.get(model, model)

def aliases() -> list[str]:
    return sorted(ONYX_ALIASES.keys())
