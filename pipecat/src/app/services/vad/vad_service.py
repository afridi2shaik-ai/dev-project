"""VAD (Voice Activity Detection) service factory.

Creates properly configured VAD analyzers for different use cases.
"""

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams

from app.schemas.services.vad import VADConfig


def create_vad_analyzer(vad_config: VADConfig, enable_turn_detection: bool = False) -> SileroVADAnalyzer | None:
    """Create a VAD analyzer from configuration.

    Args:
        vad_config: VAD configuration settings
        enable_turn_detection: Whether Smart Turn Detection is enabled (affects stop_secs)

    Returns:
        Configured SileroVADAnalyzer instance or None if disabled
    """
    if not vad_config.enabled:
        logger.info("VAD is disabled in configuration")
        return None

    # Get effective configuration (applying presets if specified)
    effective_config = vad_config.get_effective_config()

    # Adjust for turn detection if enabled and auto-adjust is on
    stop_secs = effective_config.stop_secs
    if enable_turn_detection and vad_config.auto_adjust_for_turn_detection:
        stop_secs = 0.2  # Required for Smart Turn Detection to work properly
        logger.info("Auto-adjusted stop_secs=0.2 for Smart Turn Detection compatibility")

    # Create VAD parameters
    vad_params = VADParams(
        confidence=effective_config.confidence,
        start_secs=effective_config.start_secs,
        stop_secs=stop_secs,
        min_volume=effective_config.min_volume,
    )

    # Create and configure the VAD analyzer
    vad_analyzer = SileroVADAnalyzer(params=vad_params)

    # Note: Silero VAD technical constraints (from SDK):
    # - ONLY supports 8kHz and 16kHz sample rates (hardcoded)
    # - Requires 16-bit signed integer PCM audio format
    # - Uses fixed frame sizes: 512 frames (16kHz) or 256 frames (8kHz) = 32ms chunks
    # - Model state resets every 5 seconds automatically
    # - Volume calculation uses EBU R128 broadcast standard (-20 to 80 LUFS)
    # - Exponential smoothing with 0.2 factor for noise reduction

    logger.info(
        f"Created VAD analyzer with preset='{vad_config.preset}' | "
        f"confidence={effective_config.confidence}, "
        f"start_secs={effective_config.start_secs}, "
        f"stop_secs={stop_secs}, "  # Use actual stop_secs (may be adjusted)
        f"min_volume={effective_config.min_volume}"
        f"{' (turn_detection_mode)' if enable_turn_detection else ''}"
    )

    return vad_analyzer


def create_dynamic_vad_params(scenario: str, responsiveness: str = "balanced", noise_level: str = "normal") -> VADConfig:
    """Create VAD configuration for common scenarios with fine-tuning options.

    Args:
        scenario: "conversation", "ivr", "call_center", "quiet_room", "public_space"
        responsiveness: "fast", "balanced", "patient"
        noise_level: "quiet", "normal", "noisy"

    Returns:
        VADConfig with optimized settings
    """
    # Base configurations for scenarios
    base_configs = {
        "conversation": {"confidence": 0.7, "start_secs": 0.2, "stop_secs": 0.8, "min_volume": 0.6},
        "ivr": {"confidence": 0.8, "start_secs": 0.3, "stop_secs": 2.0, "min_volume": 0.7},
        "call_center": {"confidence": 0.8, "start_secs": 0.2, "stop_secs": 0.6, "min_volume": 0.7},
        "quiet_room": {"confidence": 0.5, "start_secs": 0.1, "stop_secs": 0.7, "min_volume": 0.4},
        "public_space": {"confidence": 0.9, "start_secs": 0.4, "stop_secs": 1.0, "min_volume": 0.8},
    }

    if scenario not in base_configs:
        raise ValueError(f"Unknown scenario '{scenario}'. Available: {list(base_configs.keys())}")

    config = base_configs[scenario].copy()

    # Adjust for responsiveness
    if responsiveness == "fast":
        config["start_secs"] *= 0.7  # 30% faster detection
        config["stop_secs"] *= 0.8  # 20% quicker turn-taking
    elif responsiveness == "patient":
        config["start_secs"] *= 1.3  # 30% slower detection
        config["stop_secs"] *= 1.4  # 40% more patient waiting
    # "balanced" keeps original values

    # Adjust for noise level
    if noise_level == "quiet":
        config["confidence"] *= 0.8  # More sensitive
        config["min_volume"] *= 0.7  # Lower volume threshold
    elif noise_level == "noisy":
        config["confidence"] = min(1.0, config["confidence"] * 1.2)  # Less sensitive
        config["min_volume"] = min(1.0, config["min_volume"] * 1.3)  # Higher volume threshold
    # "normal" keeps original values

    logger.info(f"Created dynamic VAD config: scenario={scenario}, responsiveness={responsiveness}, noise_level={noise_level}")

    return VADConfig(enabled=True, confidence=config["confidence"], start_secs=config["start_secs"], stop_secs=config["stop_secs"], min_volume=config["min_volume"])
