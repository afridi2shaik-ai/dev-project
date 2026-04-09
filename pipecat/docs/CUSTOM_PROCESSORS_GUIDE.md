# Custom Processors Guide

## Overview

Pipecat-Service includes several custom frame processors that enhance the standard pipeline with specialized functionality. This guide explains each processor's purpose, architecture, configuration, and how to extend them.

## Table of Contents

1. [Processor Architecture](#processor-architecture)
2. [TranscriptionFilter](#transcriptionfilter)
3. [FillerWordsProcessor](#fillerwordsprocessor)
4. [IdleHandler](#idlehandler)
5. [MultiTTSRouter](#multittsrouter)
6. [AudioLoggingProcessor](#audiologgingprocessor)
7. [Custom Processor Development](#custom-processor-development)

---

## Processor Architecture

### Base Processor Pattern

All custom processors extend `FrameProcessor` from Pipecat:

```python
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import Frame

class CustomProcessor(FrameProcessor):
    def __init__(self, config=None):
        super().__init__()
        self._config = config
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """
        Process a frame flowing through the pipeline.
        
        Args:
            frame: The frame being processed
            direction: FrameDirection.UPSTREAM or DOWNSTREAM
        """
        # 1. Call parent to handle frame queueing and observers
        await super().process_frame(frame, direction)
        
        # 2. Implement custom processing
        # - Analyze frame
        # - Modify frame (create new one)
        # - Skip frame
        # - Generate new frames
        
        # 3. Pass frame downstream (or skip if filtering)
        await self.push_frame(frame, direction)
```

### Key Responsibilities

| Step | Purpose |
|------|---------|
| `super().process_frame()` | Initialize processor, notify observers |
| Custom logic | Analyze, filter, or modify frames |
| `self.push_frame()` | Pass frame to next processor |

### Frame Direction

- **DOWNSTREAM (→):** User input flowing toward output
- **UPSTREAM (←):** Responses flowing back to user

### Frame Queue Management

```python
# DO: Always call parent first
await super().process_frame(frame, direction)

# DON'T: Skip parent initialization
# This breaks the processor's internal queue
```

---

## TranscriptionFilter

**File:** `src/app/processors/transcription_filter.py`

**Purpose:** Remove empty, whitespace-only, or meaningless transcriptions before they reach the LLM.

### Problem Statement

STT services (especially OpenAI) sometimes return:
- Empty transcriptions: `""`
- Whitespace: `"   "`
- Filler sounds: `"uh"`, `"um"`, `"ah"`
- Single letters: `"a"`

These cause:
- Redundant LLM processing
- Potential crashes with some TTS services
- Polluted conversation history

### Solution

The TranscriptionFilter intercepts `TranscriptionFrame` and validates before passing downstream.

### Implementation

```python
class TranscriptionFilter(FrameProcessor):
    def __init__(
        self,
        min_length: int = 3,
        filter_patterns: list | None = None
    ):
        """
        Args:
            min_length: Minimum valid transcription length (default: 3)
            filter_patterns: Additional regex patterns to filter
        """
        super().__init__()
        self._min_length = min_length
        
        # Default patterns
        self._filter_patterns = filter_patterns or [
            r"^[.,!?\s]*$",           # Punctuation + whitespace
            r"^(uh|um|ah|er|hmm)\s*$",# Filler sounds
            r"^[a-zA-Z]\s*$",         # Single letters
            r"^\s*$",                 # Whitespace only
        ]
        
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self._filter_patterns
        ]
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        
        if isinstance(frame, TranscriptionFrame):
            if not self._is_valid_transcription(frame.text):
                logger.debug(f"Filtered: '{frame.text}'")
                return  # Don't pass downstream
        
        await self.push_frame(frame, direction)
    
    def _is_valid_transcription(self, text: str) -> bool:
        """Check if transcription meets validity criteria."""
        # Length check
        if len(text.strip()) < self._min_length:
            return False
        
        # Pattern matching
        for pattern in self._compiled_patterns:
            if pattern.match(text):
                return False
        
        return True
```

### Configuration

**In Pipeline Builder:**
```python
transcription_filter = TranscriptionFilter(
    min_length=3,
    filter_patterns=[
        r"^[.,!?\s]*$",
        r"^(uh|um|ah|er|hmm)\s*$",
    ]
)
processors.append(transcription_filter)
```

### Usage Example

```python
# Without filter:
User speech: "hmm"  → Transcribed: "hmm" → Sent to LLM → Waste of tokens
              "..."  → Transcribed: "..."  → Empty LLM response

# With filter:
User speech: "hmm"  → Filtered out → Skipped
              "..."  → Filtered out → Skipped
              "What time is it?"  → Passed → Sent to LLM ✓
```

---

## FillerWordsProcessor

**File:** `src/app/processors/filler_words_processor.py`

**Purpose:** Keep users engaged by generating conversational fillers during long processing delays.

### Problem

Users expect responsiveness. Long delays (>2 seconds) before bot response feel broken.

### Solution

Generate small talk phrases like:
- "Let me check that for you..."
- "One moment please..."
- "I'm looking into that..."

### Configuration

**Schema:**
```python
class FillerWordsConfig:
    enabled: bool = False                    # Enable filler words
    silence_threshold_ms: int = 2000         # Delay before filler (ms)
    groq_enabled: bool = False               # Use Groq for generation
    groq_model: str = "mixtral-8x7b-32768"   # Groq model
    static_phrases: list[str] = []           # Custom phrases
```

### Implementation

```python
class FillerWordsProcessor(FrameProcessor):
    def __init__(self, config: FillerWordsConfig):
        super().__init__()
        self._config = config
        self._timer_task = None
        self._last_user_text: str | None = None
        self._transcript_timestamp: float | None = None
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        
        # Track when user speaks
        if isinstance(frame, TranscriptionFrame):
            self._last_user_text = frame.text
            self._transcript_timestamp = time.time()
            
            # Start silence timer
            self._start_silence_timer()
        
        # Detect when LLM starts responding (cancel timer)
        if isinstance(frame, LLMFullResponseStartFrame):
            self._cancel_silence_timer()
        
        await self.push_frame(frame, direction)
    
    def _start_silence_timer(self):
        """Start timer to generate filler if silence continues."""
        self._cancel_silence_timer()
        
        delay = self._config.silence_threshold_ms / 1000
        self._timer_task = asyncio.create_task(
            self._generate_filler_after_delay(delay)
        )
    
    async def _generate_filler_after_delay(self, delay: float):
        """Generate filler after specified delay."""
        await asyncio.sleep(delay)
        
        if self._config.groq_enabled:
            filler = await self._get_groq_filler()
        else:
            filler = self._get_static_filler()
        
        if filler:
            # Create and push filler frame
            frame = TTSSpeakFrame(text=filler)
            await self.push_frame(frame, FrameDirection.DOWNSTREAM)
```

### Usage Example

**Config:**
```python
agent_config.filler_words = FillerWordsConfig(
    enabled=True,
    silence_threshold_ms=2000,  # After 2 seconds
    groq_enabled=True,
    groq_model="mixtral-8x7b-32768",
)
```

**Result:**
```
Timeline:
0ms:    User: "What's the weather in San Francisco?"
        | Processor starts silence timer
2000ms: | No LLM response yet → Generate filler
2100ms: | Bot speaks: "Let me check that for you..."
        | Timer cancelled
4000ms: | LLM responds with weather data
        | User hears: "Let me check that for you... 
                      The weather in San Francisco is..."
```

### Static Phrases

If Groq not enabled, use static phrases:

```python
FillerWordsConfig(
    enabled=True,
    groq_enabled=False,
    static_phrases=[
        "Let me check that for you...",
        "One moment please...",
        "I'm looking into that...",
        "Just a second...",
    ]
)
```

---

## IdleHandler

**File:** `src/app/processors/idle_handler.py`

**Purpose:** Detect user inactivity and trigger timeout behavior (hangup, idle messages).

### Configuration

**Schema:**
```python
class IdleTimeoutConfig:
    idle_timeout_seconds: int = 60      # Timeout in seconds
    idle_messages: list[str] = []       # Messages to speak when idle
    should_hangup: bool = False         # Auto-hangup on timeout
```

### Implementation

```python
async def handle_user_idle(
    processor,
    agent,
    idle_config: IdleTimeoutConfig,
):
    """Async handler for user idle timeout."""
    
    while True:
        # Calculate time since last user interaction
        time_since_last_input = time.time() - processor._last_user_input_time
        
        if time_since_last_input > idle_config.idle_timeout_seconds:
            # Timeout triggered
            logger.info(f"User idle for {time_since_last_input}s - triggering timeout")
            
            # Speak idle message
            if idle_config.idle_messages:
                message = random.choice(idle_config.idle_messages)
                await processor._speak_to_user(message)
            
            # Hangup if configured
            if idle_config.should_hangup:
                await agent.hangup()
            
            break
        
        await asyncio.sleep(1)  # Check every second
```

### Usage Example

**Config:**
```python
agent_config.idle_timeout = IdleTimeoutConfig(
    idle_timeout_seconds=60,
    idle_messages=[
        "Are you still there?",
        "I'm still here if you need help.",
    ],
    should_hangup=True,
)
```

**Timeline:**
```
0s:   User speaks
1s:   No activity
...
60s:  TIMEOUT TRIGGERED
      Bot speaks: "Are you still there?"
65s:  Still no response → Hangup called
```

---

## MultiTTSRouter

**File:** `src/app/processors/multi_tts_router.py`

**Purpose:** Route TTS requests to the best service based on detected language.

### Problem

- User speaks in English → Use fast TTS
- User switches to Spanish → Need Spanish-capable TTS
- User switches back to English → Back to first TTS

Requires intelligent routing without interrupting responses.

### Architecture

```
LLM Response (English) → Route to English TTS
                            ↓
                        ElevenLabs (English)
                            ↓
                        Audio Output

LLM Response (Spanish) → Route to Spanish TTS
                            ↓
                        Sarvam (Hindi/Multi)
                            ↓
                        Audio Output
```

### Configuration

**Schema:**
```python
tts_services: dict[str, AIService] = {
    "en": elevenlabs_service,
    "es": sarvam_service,
    "hi": sarvam_service,
}
```

### Implementation

```python
class MultiTTSRouter(FrameProcessor):
    def __init__(
        self,
        tts_services: dict[str, AIService],
        default_language: str = "en",
        confidence_threshold: float = 0.7,
        language_detection_service=None,
    ):
        super().__init__()
        self.tts_services = tts_services
        self.default_language = default_language
        self.confidence_threshold = confidence_threshold
        
        # Auto-detect language changes
        self.language_service = (
            language_detection_service or
            get_language_detection_service(default_language)
        )
        self.language_service.subscribe_to_language_changes(
            self._on_language_change
        )
    
    def _on_language_change(self, new_language: str):
        """Handle detected language change."""
        if new_language in self.tts_services:
            logger.info(f"Language changed: {self.default_language} → {new_language}")
            self.current_service = self.tts_services[new_language]
        else:
            logger.warning(f"No TTS service for {new_language}, using default")
            self.current_service = self.tts_services[self.default_language]
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # Control frames (StartFrame, EndFrame) must go to parent first
        if isinstance(frame, (StartFrame, EndFrame, CancelFrame)):
            await super().process_frame(frame, direction)
            # Forward to all TTS services
            for service in self.tts_services.values():
                await service.process_frame(frame, direction)
            return
        
        # Route TTS frames to appropriate service
        if isinstance(frame, TTSSpeakFrame):
            if self.current_service:
                await self.current_service.process_frame(frame, direction)
            else:
                await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)
```

### Usage Example

**Config:**
```python
tts_services = {
    "en": openai_tts,
    "es": sarvam_tts,
    "fr": elevenlabs_tts,
    "hi": sarvam_tts,
}

router = MultiTTSRouter(
    tts_services=tts_services,
    default_language="en",
    confidence_threshold=0.8,
)

# Add to pipeline
processors.append(router)
```

---

## AudioLoggingProcessor

**File:** `src/app/processors/audio_logging_processor.py`

**Purpose:** Log audio-related frames for debugging audio capture and playback issues.

### What It Logs

```python
# StartFrame with audio configuration
🎬 StartFrame: sample_rate=16000, audio_in_enabled=true, audio_out_enabled=true

# Input audio from user
🎤 InputAudioRawFrame: sample_rate=16000, audio_size=3200 bytes

# Output audio to user
🔊 OutputAudioRawFrame: sample_rate=16000, audio_size=2048 bytes
```

### Implementation

```python
class AudioLoggingProcessor(FrameProcessor):
    def __init__(self, session_id: str):
        super().__init__()
        self._session_id = session_id
        self._start_frame_received = False
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        
        # Log StartFrame to capture audio config
        if isinstance(frame, StartFrame):
            self._start_frame_received = True
            sample_rate = (
                getattr(frame, 'audio_out_sample_rate', None) or
                getattr(frame, 'audio_in_sample_rate', None)
            )
            logger.info(
                f"🎬 StartFrame session={self._session_id}: "
                f"sample_rate={sample_rate}"
            )
        
        # Log audio input
        if isinstance(frame, InputAudioRawFrame):
            logger.debug(
                f"🎤 InputAudio: session={self._session_id}, "
                f"sample_rate={frame.sample_rate}, "
                f"size={len(frame.audio)} bytes"
            )
        
        # Log audio output
        elif isinstance(frame, OutputAudioRawFrame):
            logger.debug(
                f"🔊 OutputAudio: session={self._session_id}, "
                f"sample_rate={frame.sample_rate}, "
                f"size={len(frame.audio)} bytes"
            )
        
        await self.push_frame(frame, direction)
```

### Usage Example

**Adding to Pipeline:**
```python
audio_logger = AudioLoggingProcessor(session_id=session_id)
processors.insert(0, audio_logger)  # Add first
```

**Debug Output:**
```
🎬 StartFrame received for session abc123: sample_rate=16000, audio_in_enabled=true
🎤 InputAudioRawFrame: sample_rate=16000, audio_size=3200
🎤 InputAudioRawFrame: sample_rate=16000, audio_size=3200
🔊 OutputAudioRawFrame: sample_rate=16000, audio_size=2048
```

---

## Custom Processor Development

### Template

**Create a new processor:**

```python
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import Frame
from loguru import logger

class MyCustomProcessor(FrameProcessor):
    def __init__(self, config=None):
        super().__init__()
        self._config = config
    
    async def setup(self, setup):
        """Optional: setup any resources."""
        await super().setup(setup)
        logger.info("MyCustomProcessor initialized")
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process each frame."""
        # 1. Always call parent first
        await super().process_frame(frame, direction)
        
        # 2. Implement custom logic
        if isinstance(frame, MyFrameType):
            # Analyze, transform, filter frame
            logger.debug(f"Processing {type(frame).__name__}")
        
        # 3. Pass downstream (or skip to filter)
        await self.push_frame(frame, direction)
```

### Integration Points

**Add to Pipeline:**
```python
from app.core.pipeline_builder.traditional import build_traditional_pipeline

# Custom processor setup
my_processor = MyCustomProcessor(config=my_config)

# Add to processor list before building
processors.append(my_processor)

# Build pipeline
pipeline, audio_buffer = build_traditional_pipeline(...)
```

### Testing Custom Processors

```python
async def test_my_processor():
    processor = MyCustomProcessor()
    
    # Create mock frame
    frame = MyFrameType(data="test")
    
    # Process it
    await processor.process_frame(frame, FrameDirection.DOWNSTREAM)
    
    # Verify output
    assert processor.last_output == expected_output
```

---

## Summary

The custom processor system provides:

- **TranscriptionFilter** - Remove invalid transcriptions
- **FillerWordsProcessor** - Keep users engaged during delays
- **IdleHandler** - Detect inactivity and hangup
- **MultiTTSRouter** - Route to best TTS by language
- **AudioLoggingProcessor** - Debug audio issues

All extend the Pipecat `FrameProcessor` base class and integrate seamlessly into the pipeline architecture. Use them for specialized processing needs and create custom processors by following the template and integration patterns.

