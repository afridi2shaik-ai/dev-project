from fastapi import APIRouter

from app.api.ingest import router as ingest_router
from app.api.circuitry_advisor_tool import router as circuitry_advisor_tool_router

api_router = APIRouter()
api_router.include_router(ingest_router, prefix="/core", tags=["core"])
api_router.include_router(circuitry_advisor_tool_router, prefix="/circuitry", tags=["circuitry"])
