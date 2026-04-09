from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.dependencies import get_db
from app.schemas.api_schema import PresignedUrlRequest, PresignedUrlResponse
from app.utils.s3_utils import create_presigned_url

artifact_router = APIRouter()


@artifact_router.post("/presigned-url", response_model=PresignedUrlResponse)
async def get_presigned_url(request: PresignedUrlRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Generate a pre-signed URL for a given S3 artifact path."""
    if not request.s3_path:
        raise HTTPException(status_code=400, detail="s3_path is required.")

    url = await create_presigned_url(request.s3_path)
    if not url:
        raise HTTPException(status_code=404, detail="Could not generate pre-signed URL. The file may not exist or S3 may not be configured.")

    return PresignedUrlResponse(url=url)
