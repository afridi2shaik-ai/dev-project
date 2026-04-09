from typing import Any

from loguru import logger

from app.utils.metrics_utils import MetricsAccumulator

# ==================================================================================================
# Pricing constants (placeholders, replace with your actuals)
# ==================================================================================================
# Per 1M tokens
GPT4O_PROMPT_COST_PER_1M_TOKENS = 5.00
GPT4O_COMPLETION_COST_PER_1M_TOKENS = 15.00
# Per 1k characters
ELEVENLABS_COST_PER_1K_CHARS = 0.30
# Per minute
DEEPGRAM_NOVA2_COST_PER_MINUTE = 0.0059

# TODO: Add pricing for other services (Google, Sarvam, etc.)


def calculate_cost(accumulator: MetricsAccumulator) -> dict[str, Any]:
    """
    Calculates the estimated cost of a session based on accumulated metrics.

    Note: This uses placeholder pricing. Update the constants with your actual rates.
    """
    total_cost = 0.0
    cost_breakdown = {}

    try:
        # LLM Costs (assuming GPT-4o for now)
        prompt_tokens = accumulator._totals.get("llm_prompt_tokens", 0)
        completion_tokens = accumulator._totals.get("llm_completion_tokens", 0)

        if prompt_tokens > 0:
            prompt_cost = (prompt_tokens / 1_000_000) * GPT4O_PROMPT_COST_PER_1M_TOKENS
            cost_breakdown["llm_prompt_cost"] = prompt_cost
            total_cost += prompt_cost

        if completion_tokens > 0:
            completion_cost = (completion_tokens / 1_000_000) * GPT4O_COMPLETION_COST_PER_1M_TOKENS
            cost_breakdown["llm_completion_cost"] = completion_cost
            total_cost += completion_cost

        # TTS Costs (assuming ElevenLabs for now)
        tts_chars = accumulator._totals.get("tts_characters", 0)
        if tts_chars > 0:
            tts_cost = (tts_chars / 1000) * ELEVENLABS_COST_PER_1K_CHARS
            cost_breakdown["tts_cost"] = tts_cost
            total_cost += tts_cost

        # TODO: Add STT cost calculation (requires audio duration, which is not in metrics yet)

    except Exception as e:
        logger.error(f"Error calculating session cost: {e}")
        return {"error": str(e)}

    return {"total_cost": total_cost, "currency": "USD", "breakdown": cost_breakdown, "notes": "Costs are estimates based on placeholder pricing."}
