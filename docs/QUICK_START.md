# Quick Start Guide

> ⚡ **Get started in 5 minutes** • Essential setup and first agent

## Prerequisites

- Python 3.9+
- MongoDB instance
- API credentials (OpenAI, Sarvam, etc.)
- Pipecat-Service repository

---

## Step 1: Installation

```bash
# Clone repository
git clone <repo-url>
cd Pipecat-Service

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your credentials
```

---

## Step 2: Configuration

### Environment Variables

```bash
# .env file
MONGODB_URI=mongodb://localhost:27017/pipecat
OPENAI_API_KEY=sk-...
SARVAM_API_KEY=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
```

### Start MongoDB

```bash
# Local MongoDB
mongod

# Or use Docker
docker run -d -p 27017:27017 mongo:latest
```

---

## Step 3: Create Your First Agent

### Using Python SDK

```python
from app.schemas.services.agent import AgentConfig, OpenAILLMConfig
from app.schemas.services.stt import OpenAISTTConfig
from app.schemas.services.tts import SarvamTTSConfig

# Create minimal agent config
config = AgentConfig(
    name="My First Agent",
    pipeline_mode="traditional",
    llm=OpenAILLMConfig(
        provider="openai",
        model="gpt-4o"
    ),
    stt=OpenAISTTConfig(
        provider="openai",
        model="whisper-1"
    ),
    tts=SarvamTTSConfig(
        provider="sarvam",
        voice="male_1"
    )
)

# Save agent
# POST /assistants with this config
```

### Using API

```bash
curl -X POST http://localhost:8000/api/v1/assistants \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My First Agent",
    "config": {
      "llm": {"provider": "openai", "model": "gpt-4o"},
      "stt": {"provider": "openai", "model": "whisper-1"},
      "tts": {"provider": "sarvam", "voice": "male_1"}
    }
  }'

# Response: {"assistant_id": "asst-123"}
```

---

## Step 4: Create a Session

```bash
# Create session with your assistant
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "asst-123"
  }'

# Response: {"session_id": "sess-456"}
```

---

## Step 5: Connect WebRTC (Browser)

### HTML Setup

```html
<!DOCTYPE html>
<html>
<head>
    <title>Voice Agent</title>
</head>
<body>
    <div id="status">Connecting...</div>
    <button id="hangup">Hang Up</button>
    
    <script>
        const sessionId = "sess-456";
        const token = "YOUR_TOKEN";
        
        // Create peer connection
        const pc = new RTCPeerConnection();
        
        // Add audio tracks
        navigator.mediaDevices.getUserMedia({audio: true})
            .then(stream => {
                stream.getTracks().forEach(track => pc.addTrack(track, stream));
            });
        
        // Create offer
        pc.createOffer()
            .then(offer => pc.setLocalDescription(offer))
            .then(() => {
                // Send to API
                return fetch('http://localhost:8000/api/v1/offer', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        session_id: sessionId,
                        pc_id: "pc-" + Math.random().toString(36),
                        sdp: pc.localDescription.sdp,
                        type: 'offer'
                    })
                });
            })
            .then(res => res.json())
            .then(data => {
                // Set remote description
                pc.setRemoteDescription(
                    new RTCSessionDescription({
                        type: 'answer',
                        sdp: data.sdp
                    })
                );
                document.getElementById('status').textContent = 'Connected';
            });
        
        document.getElementById('hangup').onclick = () => {
            pc.close();
            fetch(`http://localhost:8000/api/v1/sessions/${sessionId}/end`, {
                method: 'POST',
                headers: {'Authorization': `Bearer ${token}`}
            });
        };
    </script>
</body>
</html>
```

---

## Step 6: Monitor and Debug

### Check Session Status

```bash
curl -X GET http://localhost:8000/api/v1/sessions/sess-456 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Get Session Logs

```bash
curl -X GET "http://localhost:8000/api/v1/logs/sess-456/artifacts" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### View Transcript

```bash
# From logs response, find artifact_type: "transcript"
curl -X GET "http://localhost:8000/api/v1/artifacts" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Next Steps

### Add Business Tools

```python
# Create a business tool
tool_config = {
    "name": "send_email",
    "description": "Send an email",
    "parameters": [...],
    "api_config": {...}
}

# POST /api/v1/business-tools
```

See [BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md)

### Enable Call Summaries

```python
# Update agent config with summarization
config.summarization_enabled = True
config.summarization = {
    "provider": "openai",
    "model": "gpt-4o"
}
```

See [CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md)

### Add Customer Profiles

```python
# Create customer profile
profile = {
    "primary_identifier": "john@example.com",
    "identifier_type": "email",
    "name": "John Doe"
}

# POST /api/v1/customer-profiles
```

See [CUSTOMER_PROFILES.md](CUSTOMER_PROFILES.md)

---

## Troubleshooting

### Agent Not Responding

1. Check agent config is saved
2. Verify API keys are correct
3. Check MongoDB connection
4. Review logs: `GET /logs/{session_id}/artifacts`

### WebRTC Connection Failed

1. Check CORS headers
2. Verify SSL certificate (if HTTPS)
3. Check firewall/NAT settings
4. Review browser console for errors

### Poor Audio Quality

1. Check STT/TTS models
2. Verify audio input levels
3. Check network bandwidth
4. Review VAD settings

---

## Common Configuration Examples

### Customer Service Bot

```python
AgentConfig(
    name="Support Agent",
    llm=OpenAILLMConfig(model="gpt-4o"),
    customer_profile_config={
        "use_in_prompt": True,
        "update_after_call": True
    },
    summarization_enabled=True
)
```

### Sales Agent

```python
AgentConfig(
    name="Sales Bot",
    llm=OpenAILLMConfig(model="gpt-4o"),
    tools=ToolsConfig(
        business_tools=[
            {"tool_id": "schedule_demo", "enabled": True},
            {"tool_id": "send_proposal", "enabled": True}
        ]
    ),
    summarization_enabled=True
)
```

### 24/7 Support Agent

```python
AgentConfig(
    name="Always-On Support",
    llm=OpenAILLMConfig(model="gpt-3.5-turbo"),  # Cheaper model
    idle_timeout={
        "enabled": True,
        "timeout_seconds": 30
    }
)
```

---

## Useful Resources

| Resource | Link |
|----------|------|
| Full Architecture | [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) |
| API Reference | [API_GUIDE.md](API_GUIDE.md) |
| Configuration Options | [DEPLOYMENT_CONFIGURATION.md](DEPLOYMENT_CONFIGURATION.md) |
| Business Tools | [BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md) |
| Database Schema | [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md) |
| Troubleshooting | [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md) |

---

## Getting Help

- 📖 Check [README.md](README.md) for documentation index
- 🐛 See [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md) for logging & monitoring
- 📚 Review examples in guides/ folder
- 💬 Check existing issues/discussions

---

**Next**: Explore [DEPLOYMENT_CONFIGURATION.md](DEPLOYMENT_CONFIGURATION.md) for advanced configuration →

Or return to [README.md](README.md) for full navigation.

