from loguru import logger
from app.schemas.services.agent import SmartTurnConfig


def create_turn_analyzer(smart_turn_config: SmartTurnConfig):
    """Create a Smart Turn analyzer from configuration."""
    if not smart_turn_config.enabled:
        return None

    try:
        from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
        from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3

        params = SmartTurnParams(
            stop_secs=smart_turn_config.stop_secs,
            pre_speech_ms=smart_turn_config.pre_speech_ms,
            max_duration_secs=smart_turn_config.max_duration_secs,
        )
        analyzer = LocalSmartTurnAnalyzerV3(
            cpu_count=smart_turn_config.cpu_count,
            params=params,
        )
        logger.info(
            "Smart Turn enabled (stop_secs={:.2f}, pre_speech_ms={:.0f}, max_duration_secs={:.2f}, cpu={})",
            smart_turn_config.stop_secs,
            smart_turn_config.pre_speech_ms,
            smart_turn_config.max_duration_secs,
            smart_turn_config.cpu_count,
        )
        return analyzer
    except Exception as exc:
        logger.warning(f"Smart Turn disabled (failed to initialize): {exc}")
        return None
