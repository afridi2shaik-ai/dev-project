"""
Groq-specific small talk API implementation.
"""

import time
import aiohttp
from loguru import logger
from app.core import settings
from app.schemas.services.sllm import GroqSLLMConfig


async def groq_generate_small_talk(
    user_text: str,
    groq_config: GroqSLLMConfig,
    system_prompt: str ,
) -> str | None:

    if not settings.GROQ_API_KEY:
        logger.warning("[Groq Small Talk] Missing GROQ_API_KEY")
        return None

    
    final_prompt = system_prompt 

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": groq_config.model,
        "messages": [
            {"role": "system", "content": final_prompt},
            {"role": "user", "content": user_text.strip()},
        ],
        "temperature": groq_config.temperature ,
        "max_tokens": groq_config.max_completion_tokens,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=3.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:

                if response.status != 200:
                    logger.error(f"[Groq Small Talk] Error {response.status}")
                    return None

                data = await response.json()
                text = data["choices"][0]["message"]["content"]
                return text.strip() if text else None

    except Exception as e:
        logger.error(f"[Groq Small Talk] Exception: {e}")
        return None
