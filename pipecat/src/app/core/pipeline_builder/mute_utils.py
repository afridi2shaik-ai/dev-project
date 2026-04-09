from pipecat.processors.filters.stt_mute_filter import STTMuteConfig, STTMuteFilter, STTMuteStrategy

from app.schemas.services.agent import SpeakFirstMessageConfig


def add_first_speech_mute_if_needed(processors: list, agent_config, stt_enabled: bool = True) -> None:
    """Append an STT mute filter for speak-first flows.

    Keeps STT muted from the start until the assistant finishes its first speech,
    preventing user interruptions from being transcribed. Also mutes during
    function calls. No-op when STT is absent or not in speak-first mode.
    """
    if not stt_enabled:
        return

    if not isinstance(agent_config.first_message, SpeakFirstMessageConfig):
        return

    stt_mute_filter = STTMuteFilter(
        config=STTMuteConfig(
            strategies={
                STTMuteStrategy.MUTE_UNTIL_FIRST_BOT_COMPLETE,
                STTMuteStrategy.FUNCTION_CALL,
            }
        )
    )
    processors.append(stt_mute_filter)

