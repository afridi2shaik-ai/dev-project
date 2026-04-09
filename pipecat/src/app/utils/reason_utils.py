import json
from typing import Any

from .s3_utils import save_artifact


async def save_hangup_reason(transport_type: str, session_id: str, data: dict[str, Any]):
    """Saves disconnection reason data to S3 or locally based on configuration."""
    path = f"{transport_type}/{session_id}/hangup.json"
    json_data = json.dumps(data, indent=2, ensure_ascii=False, default=str).encode("utf-8")
    await save_artifact(path, json_data, "application/json")
