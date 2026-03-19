"""
Shared test utilities available to all test files via pytest conftest.
"""
from app.core.security import create_access_token


def auth_headers(user_id: int) -> dict:
    """Return Authorization header dict for a given user_id (no DB needed)."""
    token = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}
