import asyncio
import os

import aiofiles
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from loguru import logger

from app.core import settings


def _upload_to_s3_sync(bucket: str, key: str, data: bytes, content_type: str):
    """
    Synchronous function to upload data to an S3 bucket.
    
    Uses auto-detection for AWS credentials:
    - If AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY are set → uses explicit credentials
    - Otherwise → boto3 auto-discovers from IAM role (IRSA/instance profile)
    """
    s3 = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        **settings.get_aws_client_kwargs(),
    )
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


async def save_artifact(path: str, data: bytes, content_type: str):
    """
    Saves an artifact to S3 or locally based on the SAVE_TO_LOCAL flag.
    """
    if settings.SAVE_TO_LOCAL:
        # Save locally
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            async with aiofiles.open(path, "wb") as file:
                await file.write(data)
            logger.info(f"Saved artifact locally to {path}")
        except Exception as e:
            logger.error(f"Error saving artifact locally: {e}")
    elif settings.S3_BUCKET_NAME:
        # Save to S3 in a separate thread to avoid blocking
        try:
            await asyncio.to_thread(_upload_to_s3_sync, settings.S3_BUCKET_NAME, path, data, content_type)
            logger.info(f"Successfully uploaded to s3://{settings.S3_BUCKET_NAME}/{path}")
        except Exception as e:
            logger.error(f"Error uploading to S3: {e}")
    else:
        logger.warning("Neither SAVE_TO_LOCAL is true nor S3 bucket is configured. Artifact not saved.")


def _create_presigned_url_sync(bucket: str, key: str, expiration: int = 600) -> str | None:
    """
    Synchronous function to generate a pre-signed URL for an S3 object.

    NOTE ON CORS FIX: By setting region_name correctly here, boto3 ensures 
    the URL is generated with the regional endpoint implicitly, which prevents the 
    browser-breaking 307 redirect error.
    
    Uses auto-detection for AWS credentials:
    - If AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY are set → uses explicit credentials
    - Otherwise → boto3 auto-discovers from IAM role (IRSA/instance profile)
    """
    s3 = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        config=Config(signature_version="s3v4"),
        **settings.get_aws_client_kwargs(),
    )
    try:
        url = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expiration)
        # CRITICAL CHECK: Look at the URL structure
        if 's3.amazonaws.com' in url and f'.s3.{settings.AWS_REGION}.amazonaws.com' not in url:
            logger.warning(f"The URL uses the generic endpoint. If you saw a 307 redirect above, ensure your AWS_REGION is set correctly in your backend code to force the regional URL generation.")
        return url
    except ClientError as e:
        logger.error(f"Error generating pre-signed URL for {key}: {e}")
        return None


async def create_presigned_url(key: str, expiration: int = 600) -> str | None:
    """
    Asynchronously generates a pre-signed URL for an S3 object.
    If local storage is used or S3 is not configured, this function will return None.
    """
    if not settings.S3_BUCKET_NAME or settings.SAVE_TO_LOCAL:
        if settings.SAVE_TO_LOCAL:
            logger.debug(f"Local storage is enabled. Cannot generate a pre-signed URL for {key}.")
        else:
            logger.warning("S3_BUCKET_NAME is not configured. Cannot generate pre-signed URL.")
        return None

    try:
        url = await asyncio.to_thread(_create_presigned_url_sync, settings.S3_BUCKET_NAME, key, expiration)
        return url
    except Exception as e:
        logger.error(f"Error in async pre-signed URL generation for {key}: {e}")
        return None
