from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.dependencies import PaginationParams, get_current_user, get_db
from app.schemas import AgentConfig
from app.schemas.assistant_api_schema import AssistantValidationResponse
from app.schemas.pagination_schema import PaginatedResponse
from app.schemas.request_params import AssistantParams

assistant_router = APIRouter()


@assistant_router.post("/validate", response_model=AssistantValidationResponse)
async def validate_assistant(config: AgentConfig):
    """Validate an assistant configuration payload against the AgentConfig schema.
    
    This endpoint validates whether a given assistant configuration is valid
    according to the AgentConfig schema. FastAPI automatically validates the
    request body using the AgentConfig schema. If validation succeeds, we
    return the validated configuration. If validation fails, FastAPI returns
    a 422 error with detailed validation messages.
    
    The request body should be the assistant configuration JSON directly.
    """
    # If we reach here, the config is already validated by FastAPI
    # Convert validated config back to dict for response
    validated_dict = config.model_dump(exclude_none=True, mode="json")
    
    return AssistantValidationResponse(
        valid=True,
        errors=[],
        validated_config=validated_dict,
    )


@assistant_router.post("", response_model=str)
async def create_assistant(config: AgentConfig, current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    raise HTTPException(status_code=410, detail="Local assistant CRUD is deprecated. Use external Assistant API.")


@assistant_router.get("", response_model=PaginatedResponse[str])
async def list_assistants(db: AsyncIOMotorDatabase = Depends(get_db), pagination: PaginationParams = Depends()):
    raise HTTPException(status_code=410, detail="Local assistant CRUD is deprecated. Use external Assistant API.")


@assistant_router.get("/{assistant_id}", response_model=AgentConfig)
async def get_assistant(params: AssistantParams = Depends(), db: AsyncIOMotorDatabase = Depends(get_db)):
    raise HTTPException(status_code=410, detail="Local assistant CRUD is deprecated. Use external Assistant API.")


@assistant_router.put("/{assistant_id}", status_code=204)
async def update_assistant(config: AgentConfig, params: AssistantParams = Depends(), current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    raise HTTPException(status_code=410, detail="Local assistant CRUD is deprecated. Use external Assistant API.")


@assistant_router.delete("/{assistant_id}", status_code=204)
async def delete_assistant(params: AssistantParams = Depends(), db: AsyncIOMotorDatabase = Depends(get_db)):
    raise HTTPException(status_code=410, detail="Local assistant CRUD is deprecated. Use external Assistant API.")
