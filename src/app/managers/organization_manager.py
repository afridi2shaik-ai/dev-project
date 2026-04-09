"""Manager for organization operations in the global database."""

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.core.organization_schema import Organization


class OrganizationManager:
    """Manager for organization-related database operations in the global database.
    
    This manager handles queries to the organizations collection which stores
    tenant organization details including Auth0 organization IDs.
    """

    def __init__(self, global_db: AsyncIOMotorDatabase):
        """Initialize the OrganizationManager.
        
        Args:
            global_db: The global MongoDB database connection containing the organizations collection.
        """
        self.db = global_db
        self.collection = global_db["organizations"]

    async def get_organization_by_tenant_id(self, tenant_id: str) -> Organization | None:
        """Retrieve organization details by tenant ID.
        
        Only fetches essential fields: _id, tenant_id, organization_name, auth0_organization_id
        
        Args:
            tenant_id: The unique tenant identifier (stored as _id in database).
            
        Returns:
            Organization object if found, None otherwise.
            
        Example:
            ```python
            org = await manager.get_organization_by_tenant_id("47f7d897311f5b3c91e46cba51332b00")
            if org:
                print(org.auth0_organization_id)  # "org_PGgFZXDl1LAZFred"
            ```
        """
        try:
            query = {"_id": tenant_id}
            
            # Define projection to only fetch essential fields
            projection = {
                "_id": 1,
                "tenant_id": 1,
                "organization_name": 1,
                "auth0_organization_id": 1
            }
            
            org_data = await self.collection.find_one(query, projection)
            
            if org_data:
                # logger.debug(f"Found organization for tenant_id: {tenant_id} with data: {org_data}")
                return Organization(**org_data)
            
            logger.warning(f"Organization not found for tenant_id: {tenant_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching organization for tenant_id {tenant_id}: {e}")
            return None

    async def get_auth0_org_id_by_tenant(self, tenant_id: str) -> str | None:
        """Get Auth0 organization ID for a tenant.
        
        Convenience method that extracts just the Auth0 organization ID
        from the organization document.
        
        Args:
            tenant_id: The unique tenant identifier.
            
        Returns:
            Auth0 organization ID (e.g., "org_PGgFZXDl1LAZFred") if found, None otherwise.
            
        Example:
            ```python
            org_id = await manager.get_auth0_org_id_by_tenant("47f7d897...")
            # Returns: "org_PGgFZXDl1LAZFred"
            ```
        """
        organization = await self.get_organization_by_tenant_id(tenant_id)
        
        if organization:
            logger.debug(f"Retrieved Auth0 org_id for tenant {tenant_id}: {organization.auth0_organization_id}")
            return organization.auth0_organization_id
        
        return None

    async def organization_exists(self, tenant_id: str) -> bool:
        """Check if an organization exists for the given tenant ID.
        
        Uses projection to only fetch the _id field for maximum efficiency.
        
        Args:
            tenant_id: The unique tenant identifier.
            
        Returns:
            True if organization exists, False otherwise.
        """
        try:
            # Use projection to only fetch _id field for maximum efficiency
            projection = {"_id": 1}
            org_data = await self.collection.find_one({"_id": tenant_id}, projection)
            return org_data is not None
        except Exception as e:
            logger.error(f"Error checking organization existence for tenant_id {tenant_id}: {e}")
            return False
