"""Audio Filter configuration schemas.

Provides configurable audio filter parameters for noise suppression,
echo cancellation, and other audio processing features.
"""

from pydantic import Field

from app.schemas.base_schema import BaseSchema


class KrispVivaFilterConfig(BaseSchema):
    """Krisp VIVA Noise Suppression Filter configuration.

    Controls Krisp AI's VIVA engine for real-time noise suppression.
    Reduces background noise in audio streams to improve speech recognition accuracy.

    Supports multiple sample rates (8kHz, 16kHz, 24kHz, 32kHz, 44.1kHz, 48kHz),
    making it compatible with all transport types including telephony (8kHz).

    Model path is obtained from KRISP_VIVA_MODEL_PATH environment variable.
    Set this environment variable to the path of your .kef model file.
    """

    enabled: bool = Field(True, description="Enable or disable Krisp VIVA noise suppression filter.")

    noise_suppression_level: int = Field(100, ge=0, le=100, description="Noise suppression level from 0 (no suppression) to 100 (maximum suppression).")

    def get_effective_model_path(self) -> str | None:
        """Get the model path from environment variable.

        Returns:
            The model path from KRISP_VIVA_MODEL_PATH env var, or None if not set
        """
        from app.core.config import settings

        return settings.KRISP_VIVA_MODEL_PATH

    def is_ready(self) -> bool:
        """Check if the filter is ready to be used.

        Returns:
            True if enabled and model path is available
        """
        return self.enabled and self.get_effective_model_path() is not None

