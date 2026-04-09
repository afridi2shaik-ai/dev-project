import uuid

# A base namespace for all our provider-specific namespaces.
# Using NAMESPACE_DNS as a well-known starting point.
BASE_NAMESPACE = uuid.NAMESPACE_DNS


def generate_session_id(provider: str, provider_session_id: str) -> str:
    """
    Generates a deterministic, unique session ID using UUIDv5.

    This creates a consistent ID based on the transport provider and their
    session identifier.

    Args:
        provider: The name of the transport provider (e.g., "plivo", "webrtc").
        provider_session_id: The unique session ID from the provider.

    Returns:
        A string representation of the generated UUID.
    """
    # Create a deterministic namespace for the provider
    provider_namespace = uuid.uuid5(BASE_NAMESPACE, provider)
    # Generate the final session ID within the provider's namespace
    session_id = uuid.uuid5(provider_namespace, provider_session_id)
    return str(session_id)
