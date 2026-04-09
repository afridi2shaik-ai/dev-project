import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import CORS_ORIGINS
from app.core.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="event-management",
    version="0.1.0",
    docs_url="/eventmanager/docs",
    openapi_url="/eventmanager/openapi.json",
    redoc_url=None,
)

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS enabled for origins: %s", CORS_ORIGINS)
else:
    logger.info("CORS disabled: CORS_ORIGINS is empty")

app.include_router(api_router, prefix="/eventmanager/api")


def run() -> None:
    logger.info("Starting event-management on http://0.0.0.0:8000")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
