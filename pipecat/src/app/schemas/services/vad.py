"""Voice Activity Detection (VAD) configuration schemas.

Provides configurable VAD parameters for different use cases like
standard conversation, IVR navigation, and turn detection.
"""

from pydantic import Field, field_validator

from ..base_schema import BaseSchema


class VADConfig(BaseSchema):
    """Voice Activity Detection configuration.

    Controls how the system detects when a user starts and stops speaking.
    Critical for natural conversation flow and preventing empty transcriptions.
    """

    enabled: bool = Field(True, description="Enable or disable Voice Activity Detection.")

    confidence: float = Field(
        0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold for voice detection. Higher values = more strict detection, fewer false positives.",
    )

    start_secs: float = Field(
        0.2,
        ge=0.0,
        le=2.0,
        description="Time in seconds user must speak before VAD confirms speech has started. Lower values = more responsive.",
    )

    stop_secs: float = Field(
        0.8,
        ge=0.0,
        le=5.0,
        description="Time in seconds of silence required before confirming speech has stopped. Critical for turn-taking behavior.",
    )

    min_volume: float = Field(
        0.6,
        ge=0.0,
        le=1.0,
        description="Minimum audio volume threshold for speech detection. Works alongside confidence for detection accuracy.",
    )

    # Preset configurations for common use cases
    preset: str | None = Field(None, description="Use a preset configuration: 'conversation', 'turn_detection', 'ivr', 'sensitive', 'strict'")

    # Advanced settings
    auto_adjust_for_turn_detection: bool = Field(True, description="Automatically set stop_secs=0.2 when Smart Turn Detection is enabled.")

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, v):
        """Validate preset values."""
        if v is not None:
            valid_presets = ["conversation", "turn_detection", "ivr", "sensitive", "strict"]
            if v not in valid_presets:
                raise ValueError(f"Invalid preset '{v}'. Must be one of: {valid_presets}")
        return v

    def get_effective_config(self) -> "VADConfig":
        """Get the effective configuration after applying presets.

        Returns:
            A new VADConfig with preset values applied if specified
        """
        if not self.preset:
            return self

        # Define preset configurations
        presets = {
            "conversation": {
                "confidence": 0.7,
                "start_secs": 0.2,
                "stop_secs": 0.8,
                "min_volume": 0.6,
            },
            "turn_detection": {
                "confidence": 0.7,
                "start_secs": 0.2,
                "stop_secs": 0.2,  # Required for Smart Turn Detection
                "min_volume": 0.6,
            },
            "ivr": {
                "confidence": 0.8,
                "start_secs": 0.3,
                "stop_secs": 2.0,  # Wait for complete menu announcements
                "min_volume": 0.7,
            },
            "sensitive": {
                "confidence": 0.5,
                "start_secs": 0.1,
                "stop_secs": 0.5,
                "min_volume": 0.4,
            },
            "strict": {
                "confidence": 0.75,
                "start_secs": 0.3,
                "stop_secs": 0.9,
                "min_volume": 0.65,
            },
        }

        preset_config = presets[self.preset]

        # Create new config with preset values, keeping explicitly set values
        return VADConfig(
            enabled=self.enabled,
            confidence=preset_config["confidence"],
            start_secs=preset_config["start_secs"],
            stop_secs=preset_config["stop_secs"],
            min_volume=preset_config["min_volume"],
            preset=None,  # Clear preset after applying
            auto_adjust_for_turn_detection=self.auto_adjust_for_turn_detection,
        )
