"""Krisp VIVA Filter service factory.

Creates properly configured Krisp VIVA noise suppression filters for audio processing.
"""

from typing import TYPE_CHECKING

from loguru import logger

from app.schemas.services.audio_filter import KrispVivaFilterConfig

if TYPE_CHECKING:
    from pipecat.audio.filters.krisp_viva_filter import KrispVivaFilter

try:
    from pipecat.audio.filters.krisp_viva_filter import KrispVivaFilter
except ImportError as e:
    logger.error(f"KrispVivaFilter import failed: {e}")
    logger.error("To use Krisp VIVA noise suppression, ensure krisp-audio package is installed")
    KrispVivaFilter = None  # type: ignore[assignment,misc]


def create_krisp_viva_filter(krisp_config: KrispVivaFilterConfig) -> "KrispVivaFilter | None":
    """Create a Krisp VIVA noise suppression filter from configuration.

    Args:
        krisp_config: Krisp VIVA filter configuration settings

    Returns:
        Configured KrispVivaFilter instance, or None if disabled/unavailable
    """
    if not krisp_config.enabled:
        logger.info("Krisp VIVA noise suppression is disabled in configuration")
        return None

    if KrispVivaFilter is None:
        logger.warning("KrispVivaFilter not available - ensure krisp-audio package is installed")
        return None

    # Get model path from environment variable only
    model_path = krisp_config.get_effective_model_path()
    if not model_path:
        logger.info("Krisp VIVA noise suppression disabled: KRISP_VIVA_MODEL_PATH environment variable not set")
        logger.debug("To enable Krisp VIVA noise suppression, set the KRISP_VIVA_MODEL_PATH environment variable")
        logger.debug("Example: KRISP_VIVA_MODEL_PATH=Krisp\\krisp-viva-models-9.9\\krisp-viva-pro-v1.kef")
        return None

    # Validate noise suppression level (already validated by Pydantic, but double-check)
    if not (0 <= krisp_config.noise_suppression_level <= 100):
        logger.error(f"Invalid noise_suppression_level: {krisp_config.noise_suppression_level} (must be 0-100)")
        return None

    try:
        # Create the Krisp VIVA filter
        # model_path is guaranteed to be non-None here (we return early if None)
        # SDK constructor will validate the model file exists and has .kef extension
        krisp_filter = KrispVivaFilter(
            model_path=model_path, noise_suppression_level=krisp_config.noise_suppression_level
        )

        logger.info(
            f"✅ Created Krisp VIVA noise suppression filter | enabled={krisp_config.enabled}, "
            f"noise_suppression_level={krisp_config.noise_suppression_level}, "
            f"filter_type={type(krisp_filter).__name__}"
        )
        logger.debug(f"Krisp VIVA filter will process audio at sample rates: {', '.join(map(str, get_krisp_viva_sample_rates()))} Hz")

        return krisp_filter

    except Exception as e:
        logger.error(f"Failed to create KrispVivaFilter: {e}")
        logger.error("Please check your model path and ensure krisp-audio package is properly installed")
        return None


def get_krisp_viva_sample_rates() -> list[int]:
    """Get the supported sample rates for Krisp VIVA noise suppression.

    Returns:
        List of supported sample rates in Hz
    """
    return [8000, 16000, 24000, 32000, 44100, 48000]


def is_krisp_viva_compatible(sample_rate: int) -> bool:
    """Check if a sample rate is compatible with Krisp VIVA filter.

    Args:
        sample_rate: Sample rate to check in Hz

    Returns:
        True if compatible, False otherwise (always True for Krisp VIVA - supports all rates)
    """
    return sample_rate in get_krisp_viva_sample_rates()

