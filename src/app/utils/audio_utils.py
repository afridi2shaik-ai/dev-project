import io
import os
import wave

import aiofiles
import aiofiles.os
from loguru import logger

from app.core import settings
from app.schemas.log_schema import Artifact, ArtifactType

from .s3_utils import save_artifact


async def save_file_artifact(tenant_id: str, transport_type: str, session_id: str, data: bytes, content_type: str, filename: str) -> Artifact | None:
    """Saves a generic file artifact (e.g., text, csv) and returns an Artifact object."""
    path = f"vagent/{tenant_id}/{transport_type}/{session_id}/{filename}"
    try:
        if settings.SAVE_TO_LOCAL:
            # Emulate S3-like structure locally
            local_dir = os.path.join("vagent_local_artifacts", os.path.dirname(path))
            await aiofiles.os.makedirs(local_dir, exist_ok=True)
            async with aiofiles.open(os.path.join(local_dir, filename), "wb") as f:
                await f.write(data)
        else:
            await save_artifact(path, data, content_type)

        return Artifact(artifact_type=_get_artifact_type_from_filename(filename), s3_location=path)
    except Exception as e:
        logger.error(f"Error saving file artifact to {path}: {e}", exc_info=True)
        return None


async def save_audio_artifact(tenant_id: str, transport_type: str, session_id: str, audio: bytes, sample_rate: int, num_channels: int) -> Artifact | None:
    """Saves raw audio data as a WAV file and returns an Artifact object."""
    filename = "audio.wav"
    path = f"vagent/{tenant_id}/{transport_type}/{session_id}/{filename}"
    try:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(num_channels)
            wf.setsampwidth(2)  # 16-bit audio
            wf.setframerate(sample_rate)
            wf.writeframes(audio)
        buffer.seek(0)
        wav_data = buffer.read()

        if settings.SAVE_TO_LOCAL:
            # Emulate S3-like structure locally
            local_dir = os.path.join("vagent_local_artifacts", os.path.dirname(path))
            await aiofiles.os.makedirs(local_dir, exist_ok=True)
            async with aiofiles.open(os.path.join(local_dir, filename), "wb") as f:
                await f.write(wav_data)
        else:
            await save_artifact(path, wav_data, "audio/wav")

        return Artifact(artifact_type=ArtifactType.AUDIO, s3_location=path)
    except Exception as e:
        logger.error(f"Error saving audio artifact to {path}: {e}", exc_info=True)
        return None


def _get_artifact_type_from_filename(filename: str) -> ArtifactType:
    if filename == "metrics.csv":
        return ArtifactType.METRICS_CSV
    elif filename == "session_log.log":
        return ArtifactType.SESSION_LOG
    return ArtifactType.SESSION_METADATA  # A reasonable default
