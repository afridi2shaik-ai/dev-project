"""
Business Tools API Package

This package contains the REST API implementation for the new business tools system,
providing simplified endpoints for managing business tools.
"""

from .router import business_tools_router

__all__ = ["business_tools_router"]
