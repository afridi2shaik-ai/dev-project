"""
VAD Integration Usage Example

This example shows how to use the VAD (Voice Activity Detection) integration
in your voice AI application.
"""

from src.app.schemas.services.agent import AgentConfig
from src.app.schemas.services.vad import VADConfig
from src.app.services.vad import create_vad_analyzer, create_dynamic_vad_params


def example_basic_vad():
    """Example: Basic VAD configuration"""
    print("=== Basic VAD Configuration ===")
    
    # Create a VAD config with default settings
    vad_config = VADConfig()
    print(f"Default VAD Config: enabled={vad_config.enabled}, confidence={vad_config.confidence}")
    
    # Create VAD analyzer
    vad_analyzer = create_vad_analyzer(vad_config)
    print(f"VAD Analyzer created: {type(vad_analyzer).__name__}")


def example_preset_vad():
    """Example: Using VAD presets for different scenarios"""
    print("\n=== VAD Presets ===")
    
    # Conversation preset - balanced settings
    conversation_config = VADConfig(preset="conversation")
    effective_config = conversation_config.get_effective_config()
    print(f"Conversation preset: confidence={effective_config.confidence}, stop_secs={effective_config.stop_secs}")
    
    # IVR preset - patient settings for menu navigation
    ivr_config = VADConfig(preset="ivr")
    effective_config = ivr_config.get_effective_config()
    print(f"IVR preset: confidence={effective_config.confidence}, stop_secs={effective_config.stop_secs}")
    
    # Sensitive preset - more responsive
    sensitive_config = VADConfig(preset="sensitive")
    effective_config = sensitive_config.get_effective_config()
    print(f"Sensitive preset: confidence={effective_config.confidence}, stop_secs={effective_config.stop_secs}")


def example_custom_vad():
    """Example: Custom VAD configuration"""
    print("\n=== Custom VAD Configuration ===")
    
    # Custom VAD settings for noisy environment
    noisy_env_config = VADConfig(
        enabled=True,
        confidence=0.9,  # High confidence for noisy environments
        start_secs=0.3,  # Slightly slower to avoid false positives
        stop_secs=1.0,   # Longer silence required
        min_volume=0.8   # Higher volume threshold
    )
    
    vad_analyzer = create_vad_analyzer(noisy_env_config)
    print(f"Custom noisy environment VAD created: {type(vad_analyzer).__name__}")


def example_dynamic_vad():
    """Example: Dynamic VAD configuration for different scenarios"""
    print("\n=== Dynamic VAD Configuration ===")
    
    # Create optimized VAD for call center scenario
    call_center_config = create_dynamic_vad_params(
        scenario="call_center",
        responsiveness="fast",
        noise_level="normal"
    )
    print(f"Call center config: confidence={call_center_config.confidence}, stop_secs={call_center_config.stop_secs}")
    
    # Create optimized VAD for quiet room
    quiet_room_config = create_dynamic_vad_params(
        scenario="quiet_room",
        responsiveness="balanced",
        noise_level="quiet"
    )
    print(f"Quiet room config: confidence={quiet_room_config.confidence}, stop_secs={quiet_room_config.stop_secs}")


def example_agent_with_vad():
    """Example: Using VAD in AgentConfig"""
    print("\n=== Agent Configuration with VAD ===")
    
    # Create agent with custom VAD settings
    agent_config = AgentConfig(
        name="Call Center Agent",
        vad=VADConfig(preset="call_center")
    )
    
    print(f"Agent '{agent_config.name}' VAD preset: {agent_config.vad.preset}")
    
    # You can also override VAD settings entirely
    agent_config_custom = AgentConfig(
        name="Custom Agent",
        vad=VADConfig(
            enabled=True,
            confidence=0.8,
            start_secs=0.15,  # Very responsive
            stop_secs=0.6,    # Quick turn-taking
            min_volume=0.7
        )
    )
    
    print(f"Agent '{agent_config_custom.name}' custom VAD: confidence={agent_config_custom.vad.confidence}")


def example_disabled_vad():
    """Example: Disabling VAD completely"""
    print("\n=== Disabled VAD ===")
    
    # Disable VAD (not recommended for production)
    disabled_config = VADConfig(enabled=False)
    vad_analyzer = create_vad_analyzer(disabled_config)
    print(f"Disabled VAD returns: {vad_analyzer}")


if __name__ == "__main__":
    print("🎙️ VAD Integration Examples\n")
    
    example_basic_vad()
    example_preset_vad()
    example_custom_vad()
    example_dynamic_vad()
    example_agent_with_vad()
    example_disabled_vad()
    
    print("\n✅ All VAD examples completed successfully!")
    print("\n💡 Tips:")
    print("- Use 'conversation' preset for general voice AI")
    print("- Use 'ivr' preset for menu navigation")
    print("- Use 'sensitive' preset for quiet environments")
    print("- Use 'strict' preset for noisy environments")
    print("- Customize confidence/timing for specific use cases")
