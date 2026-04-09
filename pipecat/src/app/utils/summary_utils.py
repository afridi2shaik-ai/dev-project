import json
from typing import Any

import openai
from loguru import logger

from app.core import settings
from app.schemas import AgentConfig


async def generate_summary(messages: list[dict[str, str]], agent_config: AgentConfig) -> dict[str, Any] | None:
    """Generates a summary from a transcript and returns it as a dictionary."""
    if not agent_config.summarization_enabled:
        logger.info("Summarization is disabled, skipping.")
        return None

    if not messages:
        logger.info("No messages to summarize.")
        return None

    try:
        if agent_config.summarization.provider == "openai":
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

            # Ensure the word "JSON" is explicitly mentioned for OpenAI's json_object mode
            full_prompt = f"{agent_config.summarization.prompt_template}\n\n{json.dumps(messages, indent=2)}"

            # Add explicit JSON instruction if not already present
            if "json" not in full_prompt.lower():
                logger.warning("Prompt template doesn't contain 'JSON' - adding explicit instruction")
                full_prompt += "\n\nPlease respond with valid JSON format."

            logger.debug(f"Summarization prompt contains 'json': {'json' in full_prompt.lower()}")

            messages_for_api = [
                {
                    "role": "system",
                    "content": full_prompt,
                }
            ]

            response = await client.chat.completions.create(
                model=agent_config.summarization.model,
                messages=messages_for_api,
                temperature=0.7,
                response_format={"type": "json_object"},
            )

            summary_content = response.choices[0].message.content

            summary_data = {}
            try:
                summary_data = json.loads(summary_content)
            except json.JSONDecodeError:
                logger.warning("Failed to parse summary as JSON, wrapping in an object.")
                summary_data = {"summary": summary_content}

            summary_data["model"] = response.model
            summary_data["usage"] = response.usage.model_dump()

            return summary_data
        else:
            logger.warning(f"Summarization provider '{agent_config.summarization.provider}' not yet implemented.")
            return None

    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return {"error": f"Failed to generate summary: {e}"}
