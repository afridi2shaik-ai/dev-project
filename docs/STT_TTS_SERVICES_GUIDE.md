# STT/TTS Services Guide

## Overview

Speech-to-Text (STT) and Text-to-Speech (TTS) services are critical components that determine voice quality, latency, and cost. This guide covers all supported providers, configuration, selection criteria, and provider comparison.

## Table of Contents

1. [STT Services](#stt-services)
2. [TTS Services](#tts-services)
3. [Provider Comparison](#provider-comparison)
4. [Configuration](#configuration)
5. [Best Practices](#best-practices)

---

## STT Services

### Location

**Directory:** `src/app/services/stt/`

**Files:**
- `deepgram_stt_service.py` - Deepgram (recommended)
- `openai_stt_service.py` - OpenAI Whisper
- `google_stt_service.py` - Google Cloud Speech-to-Text
- `elevenlabs_stt_service.py` - ElevenLabs
- `cartesia_stt_service.py` - Cartesia

### Deepgram (Recommended)

**Status:** ✅ Production-ready

**Features:**
- Lowest latency (streaming)
- Highest accuracy
- Fast transcription
- Good language support
- Cost-effective

**Configuration:**
```python
class STTConfig:
    provider: str = "deepgram"
    language: str = "en"
    model: str = "nova-2"  # Latest model
```

**Environment:**
```bash
DEEPGRAM_API_KEY=your_key
```

**Usage:**
```python
from pipecat.services.deepgram import DeepgramSTTService

stt = DeepgramSTTService(api_key=settings.DEEPGRAM_API_KEY)
```

**When to use:** Default choice for most applications

### OpenAI Whisper STT

**Status:** ✅ Supported

**Features:**
- Integrates with OpenAI LLM
- Good accuracy
- Supports many languages
- Higher latency than Deepgram

**Configuration:**
```python
class STTConfig:
    provider: str = "openai"
    model: str = "whisper-1"
```

**When to use:** OpenAI ecosystem, OpenAI LLM partnership

### Google Cloud STT

**Status:** ✅ Supported

**Features:**
- Very high accuracy
- Many language options
- Real-time streaming
- Higher cost

**When to use:** Best-in-class accuracy needed

### ElevenLabs STT

**Status:** ✅ Supported

**When to use:** ElevenLabs TTS partnership, specialized features

### Cartesia STT

**Status:** ✅ Supported

**When to use:** Cartesia ecosystem, specific latency requirements

---

## TTS Services

### Location

**Directory:** `src/app/services/tts/`

**Files:**
- `elevenlabs_tts_service.py` - ElevenLabs (most natural)
- `openai_tts_service.py` - OpenAI TTS
- `sarvam_tts_service.py` - Sarvam (Indian languages)
- `cartesia_tts_service.py` - Cartesia (low latency)

### ElevenLabs (Recommended)

**Status:** ✅ Production-ready

**Features:**
- Most natural sounding voices
- 32 realistic voices
- Voice cloning support
- Lowest latency in class
- Premium quality

**Configuration:**
```python
class TTSConfig:
    provider: str = "elevenlabs"
    voice: str = "21m00Tcm4TlvDq8ikWAM"  # Specific voice ID
    model: str = "eleven_monolingual_v1"
    stability: float = 0.5
    similarity_boost: float = 0.75
```

**Environment:**
```bash
ELEVENLABS_API_KEY=your_key
```

**Voice Options:**
```
21m00Tcm4TlvDq8ikWAM - Bella (female, warm)
29vD33N1CtxCmqQRPOHJ - Arnold (male, deep)
TZ06ctNYISas3XVtexW8 - Sam (male, professional)
... and 29 more
```

**When to use:** Premium quality required, customer-facing applications

### OpenAI TTS

**Status:** ✅ Supported

**Features:**
- Integrates with OpenAI LLM
- Quick setup
- Good quality
- Three voice options

**Voices:**
```
alloy (neutral, versatile)
echo (calm, soothing)
fable (warm, engaging)
```

**Configuration:**
```python
class TTSConfig:
    provider: str = "openai"
    voice: str = "fable"
    model: str = "tts-1"  # or "tts-1-hd"
```

**When to use:** OpenAI ecosystem preference

### Sarvam TTS

**Status:** ✅ Supported

**Features:**
- Excellent for Indian languages
- Hindi, Bengali, Tamil, Telugu
- Natural sounding
- Cost-effective

**When to use:** Indian language support needed

### Cartesia TTS

**Status:** ✅ Supported

**Features:**
- Ultra-low latency
- Real-time streaming
- High quality

**When to use:** Ultra-low latency requirement

---

## Provider Comparison

### STT Providers

| Provider | Latency | Accuracy | Cost | Languages | Notes |
|----------|---------|----------|------|-----------|-------|
| **Deepgram** | 100ms ⭐⭐⭐ | 95% ⭐⭐ | $ ⭐⭐⭐ | 40+ | Best overall |
| OpenAI | 500ms ⭐⭐ | 98% ⭐⭐⭐ | $$$ | 100+ | High accuracy |
| Google | 300ms ⭐⭐ | 99% ⭐⭐⭐⭐ | $$ | 120+ | Highest accuracy |
| ElevenLabs | 400ms ⭐⭐ | 92% ⭐ | $$ | 20+ | Lower accuracy |
| Cartesia | 50ms ⭐⭐⭐⭐ | 94% ⭐⭐ | $$$ | 10+ | Ultra-fast |

### TTS Providers

| Provider | Latency | Quality | Cost | Voices | Notes |
|----------|---------|---------|------|--------|-------|
| **ElevenLabs** | 300ms ⭐⭐⭐ | 98% ⭐⭐⭐⭐ | $$ | 32 | Most natural |
| OpenAI | 200ms ⭐⭐⭐⭐ | 85% ⭐⭐ | $ | 3 | Fast & cheap |
| Sarvam | 400ms ⭐⭐ | 90% ⭐⭐ | $ | Regional | Indian langs |
| Cartesia | 100ms ⭐⭐⭐⭐ | 92% ⭐⭐ | $$$ | 10+ | Ultra-fast |

---

## Configuration

### STT Configuration Schema

**File:** `src/app/schemas/services/agent.py`

```python
class STTConfig:
    provider: STTProvider  # "deepgram", "openai", "google", etc.
    language: str = "en"  # BCP 47 language code
    model: str | None = None  # Provider-specific model
    encoding: str = "linear16"  # Audio encoding
```

### TTS Configuration Schema

```python
class TTSConfig:
    provider: TTSProvider  # "elevenlabs", "openai", etc.
    voice: str  # Voice ID or name
    model: str | None = None  # Provider-specific model
    language: str | None = None  # Override language
```

### Complete Agent Configuration

```python
from app.schemas.services.agent import AgentConfig, STTConfig, TTSConfig

agent_config = AgentConfig(
    # STT Configuration
    stt=STTConfig(
        provider="deepgram",
        language="en",
        model="nova-2",
    ),
    
    # TTS Configuration
    tts=TTSConfig(
        provider="elevenlabs",
        voice="21m00Tcm4TlvDq8ikWAM",  # Bella
        model="eleven_monolingual_v1",
    ),
    
    # LLM Configuration
    llm=LLMConfig(
        provider="openai",
        model="gpt-4o",
        temperature=0.7,
    ),
)
```

### Environment Variables

**STT:**
```bash
DEEPGRAM_API_KEY=your_deepgram_key
OPENAI_API_KEY=your_openai_key
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
ELEVENLABS_API_KEY=your_elevenlabs_key
CARTESIA_API_KEY=your_cartesia_key
```

**TTS:**
```bash
ELEVENLABS_API_KEY=your_elevenlabs_key
OPENAI_API_KEY=your_openai_key
SARVAM_API_KEY=your_sarvam_key
CARTESIA_API_KEY=your_cartesia_key
```

---

## Best Practices

### 1. Provider Selection

**For Standard Applications:**
```python
stt=STTConfig(provider="deepgram"),     # Best balance
tts=TTSConfig(provider="elevenlabs"),   # Most natural
```

**For High Accuracy:**
```python
stt=STTConfig(provider="google"),        # Best accuracy
tts=TTSConfig(provider="elevenlabs"),    # Best quality
```

**For Ultra-Low Latency:**
```python
stt=STTConfig(provider="deepgram"),      # Streaming
tts=TTSConfig(provider="cartesia"),      # 100ms latency
```

**For Cost Optimization:**
```python
stt=STTConfig(provider="deepgram"),      # Cheap & fast
tts=TTSConfig(provider="openai"),        # Cheapest
```

**For Ecosystem Consistency:**
```python
stt=STTConfig(provider="openai"),        # Whisper
tts=TTSConfig(provider="openai"),        # TTS
llm=LLMConfig(provider="openai"),        # GPT-4o
```

### 2. Language Handling

**Set language in config:**
```python
stt=STTConfig(
    provider="deepgram",
    language="es",  # Spanish
)

tts=TTSConfig(
    provider="elevenlabs",
    language="es",
)
```

**Auto-detect with MultiTTSRouter:**
```python
# See CUSTOM_PROCESSORS_GUIDE.md for details
tts_services = {
    "en": openai_tts_en,
    "es": sarvam_tts_es,
    "hi": sarvam_tts_hi,
}
```

### 3. Voice Selection

**ElevenLabs Voice IDs:**
```
21m00Tcm4TlvDq8ikWAM - Bella (warm female)
29vD33N1CtxCmqQRPOHJ - Arnold (deep male)
TZ06ctNYISas3XVtexW8 - Sam (professional male)
EL7ej0gVUwAJR2mZ5h5B - Luna (dynamic female)
... see ElevenLabs dashboard for all options
```

**Select based on character:**
```python
# Friendly, warm
voice_id = "21m00Tcm4TlvDq8ikWAM"  # Bella

# Professional, corporate
voice_id = "TZ06ctNYISas3XVtexW8"  # Sam

# Energetic, engaging
voice_id = "EL7ej0gVUwAJR2mZ5h5B"  # Luna
```

### 4. Quality vs. Cost Tradeoffs

**Premium Quality (Higher Cost):**
```python
stt=STTConfig(provider="google"),        # 99% accuracy
tts=TTSConfig(provider="elevenlabs"),    # Most natural
```
**Cost:** ~$0.05 per minute

**Balanced (Recommended):**
```python
stt=STTConfig(provider="deepgram"),      # 95% accuracy, fast
tts=TTSConfig(provider="elevenlabs"),    # Natural
```
**Cost:** ~$0.01 per minute

**Cost-Optimized:**
```python
stt=STTConfig(provider="deepgram"),
tts=TTSConfig(provider="openai"),        # Cheapest
```
**Cost:** ~$0.005 per minute

### 5. Error Handling

**Fallback providers:**
```python
try:
    stt = DeepgramSTTService(...)
except Exception as e:
    logger.warning(f"Deepgram failed: {e}, using OpenAI")
    stt = OpenAISTTService(...)

try:
    tts = ElevenLabsTTSService(...)
except Exception as e:
    logger.warning(f"ElevenLabs failed: {e}, using OpenAI")
    tts = OpenAITTSService(...)
```

### 6. Monitoring

**Track usage metrics:**
```python
logger.info(f"STT: {stt_config.provider}, "
           f"language: {stt_config.language}")
logger.info(f"TTS: {tts_config.provider}, "
           f"voice: {tts_config.voice}")

# Log in every session creation for audit trail
```

---

## Summary

**STT Selection:**
- **Default:** Deepgram (best latency/accuracy balance)
- **Best accuracy:** Google Cloud
- **Ultra-fast:** Cartesia
- **OpenAI ecosystem:** OpenAI Whisper

**TTS Selection:**
- **Default:** ElevenLabs (most natural)
- **Cheap:** OpenAI
- **Indian languages:** Sarvam
- **Ultra-fast:** Cartesia

**Configure once in AgentConfig, referenced throughout pipeline.**

