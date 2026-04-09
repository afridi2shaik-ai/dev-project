from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.dependencies import get_db
from app.managers.customer_profile_manager import CustomerProfileManager
from app.schemas.core.customer_profile import (
    CustomerProfileCreateRequest,
    CustomerProfileIdParams,
    CustomerProfileIdentifierParams,
    CustomerProfileLinkPathParams,
    CustomerProfileListParams,
    CustomerProfileResponse,
    CustomerProfileSearchParams,
    CustomerProfileUpdateRequest,
    LinkIdentityRequest,
)

router = APIRouter()


# -------------------------------------------------------------------------
# Dependency mappers for path params (schema-driven)
# -------------------------------------------------------------------------


def get_identifier_params(
    identifier: Annotated[str, Path(description="Email, phone number, or profile ID")],
) -> CustomerProfileIdentifierParams:
    return CustomerProfileIdentifierParams(identifier=identifier)


def get_profile_id_params(
    profile_id: Annotated[str, Path(description="Customer profile ID")],
) -> CustomerProfileIdParams:
    return CustomerProfileIdParams(profile_id=profile_id)


def get_link_path_params(
    profile_id: Annotated[str, Path(description="Customer profile ID")],
    identity_type: Annotated[str, Path(description="Identity type: 'email' or 'phone'")],
    value: Annotated[str, Path(description="Identity value to unlink")],
) -> CustomerProfileLinkPathParams:
    return CustomerProfileLinkPathParams(profile_id=profile_id, identity_type=identity_type, value=value)


def get_list_params(
    skip: int = 0,
    limit: int = 20,
    sort_by: str = "last_interaction_at",
    sort_order: int = -1,
) -> CustomerProfileListParams:
    return CustomerProfileListParams(skip=skip, limit=limit, sort_by=sort_by, sort_order=sort_order)


def get_search_params(q: str, limit: int = 10) -> CustomerProfileSearchParams:
    return CustomerProfileSearchParams(q=q, limit=limit)


async def get_profile_manager(db: Annotated[AsyncIOMotorDatabase, Depends(get_db)]) -> CustomerProfileManager:
    return CustomerProfileManager(db)


# -------------------------------------------------------------------------
# Profile CRUD
# -------------------------------------------------------------------------


@router.get(
    "/{identifier}",
    response_model=CustomerProfileResponse,
    summary="Get Customer Profile",
    description="Retrieve a customer profile by email, phone number, or profile ID.",
)
async def get_profile(
    params: CustomerProfileIdentifierParams = Depends(get_identifier_params),
    manager: Annotated[CustomerProfileManager, Depends(get_profile_manager)] = None,
) -> CustomerProfileResponse:
    profile = await manager.get_by_profile_id(params.identifier)
    if not profile:
        profile = await manager.get_by_identifier(params.identifier)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer profile not found for identifier: {params.identifier}",
        )

    return CustomerProfileResponse.from_profile(profile)


@router.post(
    "",
    response_model=CustomerProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Customer Profile",
    description="Create a new customer profile with a primary identifier (email or phone).",
)
async def create_profile(
    request: CustomerProfileCreateRequest = Body(...),
    manager: Annotated[CustomerProfileManager, Depends(get_profile_manager)] = None,
) -> CustomerProfileResponse:
    try:
        profile = await manager.create_profile(request)
        return CustomerProfileResponse.from_profile(profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.patch(
    "/{profile_id}",
    response_model=CustomerProfileResponse,
    summary="Update Customer Profile",
    description="Update an existing customer profile's details and preferences.",
)
async def update_profile(
    path: CustomerProfileIdParams = Depends(get_profile_id_params),
    request: CustomerProfileUpdateRequest = Body(...),
    manager: Annotated[CustomerProfileManager, Depends(get_profile_manager)] = None,
) -> CustomerProfileResponse:
    profile = await manager.update_profile(path.profile_id, request)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer profile not found: {path.profile_id}",
        )
    return CustomerProfileResponse.from_profile(profile)


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Customer Profile",
    description="Delete a customer profile by ID.",
)
async def delete_profile(
    path: CustomerProfileIdParams = Depends(get_profile_id_params),
    manager: Annotated[CustomerProfileManager, Depends(get_profile_manager)] = None,
) -> None:
    deleted = await manager.delete_profile(path.profile_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer profile not found: {path.profile_id}",
        )


# -------------------------------------------------------------------------
# Identity Linking
# -------------------------------------------------------------------------


@router.post(
    "/{profile_id}/link",
    response_model=CustomerProfileResponse,
    summary="Link Identity",
    description="Link an additional email or phone identity to a customer profile.",
)
async def link_identity(
    path: CustomerProfileIdParams = Depends(get_profile_id_params),
    request: LinkIdentityRequest = Body(...),
    manager: Annotated[CustomerProfileManager, Depends(get_profile_manager)] = None,
) -> CustomerProfileResponse:
    try:
        profile = await manager.link_identity(
            profile_id=path.profile_id,
            identity_type=request.identity_type,
            value=request.value,
        )
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer profile not found: {path.profile_id}",
            )
        return CustomerProfileResponse.from_profile(profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.delete(
    "/{profile_id}/link/{identity_type}/{value}",
    response_model=CustomerProfileResponse,
    summary="Unlink Identity",
    description="Remove a linked identity from a customer profile.",
)
async def unlink_identity(
    path: CustomerProfileLinkPathParams = Depends(get_link_path_params),
    manager: Annotated[CustomerProfileManager, Depends(get_profile_manager)] = None,
) -> CustomerProfileResponse:
    if path.identity_type not in ("email", "phone"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="identity_type must be 'email' or 'phone'",
        )

    profile = await manager.unlink_identity(
        profile_id=path.profile_id,
        identity_type=path.identity_type,
        value=path.value,
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer profile not found: {path.profile_id}",
        )
    return CustomerProfileResponse.from_profile(profile)


# -------------------------------------------------------------------------
# List and Search
# -------------------------------------------------------------------------


@router.get(
    "",
    response_model=dict,
    summary="List Customer Profiles",
    description="List customer profiles with pagination.",
)
async def list_profiles(
    query: CustomerProfileListParams = Depends(get_list_params),
    manager: Annotated[CustomerProfileManager, Depends(get_profile_manager)] = None,
) -> dict:
    profiles, total = await manager.list_profiles(
        skip=query.skip,
        limit=query.limit,
        sort_by=query.sort_by,
        sort_order=query.sort_order,
    )

    return {
        "items": [CustomerProfileResponse.from_profile(p) for p in profiles],
        "total": total,
        "skip": query.skip,
        "limit": query.limit,
    }


@router.get(
    "/search/query",
    response_model=list[CustomerProfileResponse],
    summary="Search Customer Profiles",
    description="Search profiles by name, email, or phone.",
)
async def search_profiles(
    query: CustomerProfileSearchParams = Depends(get_search_params),
    manager: Annotated[CustomerProfileManager, Depends(get_profile_manager)] = None,
) -> list[CustomerProfileResponse]:
    profiles = await manager.search_profiles(query=query.q, limit=query.limit)
    return [CustomerProfileResponse.from_profile(p) for p in profiles]

