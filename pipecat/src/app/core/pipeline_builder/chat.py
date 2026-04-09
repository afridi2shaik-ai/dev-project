from fastapi import WebSocket
from loguru import logger
from pipecat.pipeline.pipeline import Pipeline

from app.agents import BaseAgent
from app.services.chat_completions.chat_frame import WebSocketTextOutbound
from app.utils.transcript_utils import TranscriptAccumulator


def build_text_pipeline(
    agent: BaseAgent,
    websocket: WebSocket,
    session_id: str,
) -> Pipeline:
    llm = agent._llm
    context_agg = agent._context_aggregator

    if llm is None or context_agg is None:
        raise RuntimeError("LLM or context_aggregator not initialized. Call agent.get_services() first.")

    # One shared accumulator for the whole session
    accumulator = TranscriptAccumulator()

    # The outbound processor handles sending + storing assistant messages
    ws_out = WebSocketTextOutbound(websocket=websocket, accumulator=accumulator)

    processors = [
        context_agg.user(),       # Processes user messages, updates context
        llm,                      # Generates response
        ws_out,                   # Sends full text + stores in accumulator
        context_agg.assistant(),  # Saves assistant response back to context (for next turns)
    ]

    pipeline = Pipeline(processors)

    # Attach accumulator to pipeline for external access (e.g., observers, artifact manager)
    pipeline.transcript_accumulator = accumulator

    logger.debug(f"Built text pipeline with WebSocketTextOutbound for session {session_id}")

    return pipeline

