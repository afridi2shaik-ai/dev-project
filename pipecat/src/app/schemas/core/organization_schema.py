"""Organization schema for global database organizations collection."""

from pydantic import Field

from app.schemas.base_schema import BaseSchema


class Organization(BaseSchema):
    """Organization model representing a tenant organization in the global database.
    
    This schema only includes the 4 essential fields that are fetched from the database
    for security and performance reasons.
    """

    id: str = Field(..., alias="_id", description="Unique tenant identifier (primary key)")
    tenant_id: str = Field(..., description="Tenant identifier (same as _id)")
    organization_name: str = Field(..., description="Name of the organization")
    auth0_organization_id: str = Field(..., description="Auth0 organization ID used for authentication")


class OrganizationResponse(BaseSchema):
    """Response model for organization details."""

    id: str = Field(..., alias="_id", description="Unique tenant identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    organization_name: str = Field(..., description="Name of the organization")
    auth0_organization_id: str = Field(..., description="Auth0 organization ID")
