"""RAG Tool (Knowledge Center).

When the LLM calls this tool, it calls the external RAG API with the user's question,
gets the reply, and speaks that reply to the user. API call is delegated to RagClient.
"""

from typing import Any

from loguru import logger
from pipecat.frames.frames import TTSSpeakFrame

try:  # pragma: no cover - optional import for type hints
    from pipecat.services.llm_service import FunctionCallParams  # type: ignore
except Exception:  # pragma: no cover
    FunctionCallParams = Any  # type: ignore

from app.services.rag_client import RagClient


async def rag_query(
    params: "FunctionCallParams",
    query: str,
    engaging_words: str = "Let me look that up for you",
    document_ids: list[str] | None = None,
) -> None:
    """Search the knowledge base and get the answer. Use this when the user asks
    a question that should be answered from the knowledge base. Send the user's
    question as query. Optionally provide a short phrase to say while looking up
    (e.g. "Let me look that up for you."). If your system prompt specifies which
    document_ids to use for which topic, pass that list; otherwise omit it
    to search the whole knowledge base.

    Args:
        params: Tool context from the system.
        query: The user's question to look up.
        engaging_words: Optional short phrase to say while fetching the answer.
        document_ids: Optional list of document IDs. When specified in system prompt
            for the topic, pass them to scope the search. If you cannot decide, omit it.
    """
    query = (query or "").strip()
    if not query:
        await params.result_callback({
            "status": "error",
            "error": "empty_query",
            "message": "Search query cannot be empty.",
        })
        return

    session = getattr(params, "aiohttp_session", None)
    if not session:
        logger.error("No HTTP session available for RAG tool")
        await params.result_callback({
            "status": "error",
            "error": "no_session",
            "message": "Unable to look up the answer right now.",
        })
        return

    from app.tools.session_context_tool import get_session_context

    context = get_session_context()
    if not context:
        logger.error("No session context available for RAG tool")
        await params.result_callback({
            "status": "error",
            "error": "no_session",
            "message": "Unable to look up the answer right now.",
        })
        return

    tenant_id = getattr(context.user, "tenant_id", None)
    if not tenant_id:
        logger.error("No tenant ID available for RAG tool")
        await params.result_callback({
            "status": "error",
            "error": "no_tenant",
            "message": "Unable to look up the answer right now.",
        })
        return

    # Use only document_ids from tool call (system prompt); do not use metadata
    document_ids = [x.strip() for x in (document_ids or []) if (x or "").strip()] or None
    access_token = None
    id_token = None
    try:
        from app.services.token_provider import TokenProvider
        access_token, id_token = await TokenProvider.get_tokens_for_tenant(tenant_id)
        logger.debug("✅ Retrieved tokens for RAG API")
    except Exception as token_error:
        logger.warning(f"⚠️ Could not retrieve tokens for RAG API: {token_error}. Proceeding without tokens.")

    # Always say something before the (possibly slow) API call so the user isn't left in silence
    engaging_words = (engaging_words or "").strip() or "Let me look that up for you."
    await params.llm.push_frame(TTSSpeakFrame(engaging_words))

    try:
        rag_client = RagClient()
        response = await rag_client.query(
            session,
            query=query,
            document_ids=document_ids,
            access_token=access_token,
            id_token=id_token,
        )
    except ValueError as e:
        logger.error(f"RAG client config error: {e}")
        await params.result_callback({
            "status": "error",
            "error": "config_error",
            "message": "Knowledge base is not configured.",
        })
        return
    except Exception as e:
        logger.error(f"RAG API call failed: {type(e).__name__}: {e}", exc_info=True)
        await params.result_callback({
            "status": "error",
            "error": "api_failed",
            "message": "Could not reach the knowledge base. Please try again.",
        })
        return

    if response.status_code != 200:
        await params.result_callback({
            "status": "error",
            "error": "api_error",
            "message": "Could not get an answer. Please try again.",
        })
        return

    reply_text = (response.get_reply_text() or "").strip()
    if not reply_text:
        await params.result_callback({
            "status": "error",
            "error": "empty_reply",
            "message": "No answer was returned.",
        })
        return

   #await params.llm.push_frame(TTSSpeakFrame(reply_text))
    await params.result_callback({
        "status": "success",
        "reply": reply_text,
    })
