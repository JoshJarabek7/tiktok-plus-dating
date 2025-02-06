from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.db import DatabaseManager
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.responses import HealthCheckResponseSchema


@asynccontextmanager
async def lifespan(app: FastAPI):
    this_db = DatabaseManager()
    this_db.driver
    app.state.driver = this_db.driver
    yield
    this_db.close()


app = FastAPI(lifespan=lifespan)


@app.get("/api/health", response_model=HealthCheckResponseSchema)
async def health_check() -> HealthCheckResponseSchema:
    return HealthCheckResponseSchema(success=True)


@app.get("/api/me", response_model=User)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get the current user's profile.

    This is a protected endpoint that requires authentication.
    The user is automatically fetched from the JWT token.

    Args:
        current_user: Injected by the auth dependency

    Returns:
        The current user's profile
    """
    return current_user
