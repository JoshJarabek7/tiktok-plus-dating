import re
from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict, EmailStr, Field, field_validator


class User(BaseModel):
    """User model representing a user in the system.

    This model contains all the basic information about a user including their
    profile details and engagement metrics.

    Attributes:
        user_id: Unique identifier for the user
        auth_id: Authentication provider's unique identifier
        username: Unique username for the user
        email: Verified email address
        display_name: User's display name
        profile_picture_s3_key: S3 key for profile picture if exists
        is_private: Whether the account is private
        created_at: When the account was created
        bio: User's biography if set
        follower_count: Number of followers
        following_count: Number of users being followed
        likes_count: Number of likes received
        post_count: Number of videos posted
        latitude: Latitude of the user's location
        longitude: Longitude of the user's location
        location_updated_at: Timestamp of when the location was last updated
        interests: List of interests of the user
    """

    model_config = ConfigDict(frozen=True)

    # Basic Info
    user_id: UUID4
    auth_id: str
    username: str
    email: EmailStr
    display_name: str
    profile_picture_s3_key: str | None
    is_private: bool
    created_at: datetime
    # Profile Info
    bio: str | None
    follower_count: int = 0
    following_count: int = 0
    likes_count: int = 0
    post_count: int = 0
    # Location Info
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    location_updated_at: datetime | None = None
    # Interests
    interests: list[str] = Field(default_factory=list)

    @field_validator("username")
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]{3,20}$", v):
            raise ValueError("Username must be 3-20 alphanumeric characters")
        return v
