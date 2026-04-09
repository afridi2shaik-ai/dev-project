"""
Universal router – decides which provider to use.
"""

from loguru import logger

from app.schemas.services.sllm import SLLMCONFIG
from .groq_small_talk import groq_generate_small_talk
# from .openai_small_talk import openai_generate_small_talk
# from .bedrock_small_talk import bedrock_generate_small_talk


async def small_talk_response(
    user_text: str,
    llm_config: SLLMCONFIG,
    system_prompt: str ,
) -> str | None:

    if not user_text or not user_text.strip():
        return None

    provider = llm_config.provider.lower()
    logger.debug(f"[SmallTalk] Selected provider: {provider}")

    # Route to appropriate provider file
    if provider == "groq":
        return await groq_generate_small_talk(user_text, llm_config, system_prompt)

    # elif provider == "openai":
    #     return await openai_generate_small_talk(user_text, llm_config, system_prompt)

    # elif provider == "bedrock":
    #     return await bedrock_generate_small_talk(user_text, llm_config, system_prompt)

    logger.error(f"[SmallTalk] Unsupported Provider: {provider}")
    return None
