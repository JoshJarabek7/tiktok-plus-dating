from datetime import date, datetime
from enum import Enum
from typing import Annotated

from pydantic import (
    UUID4,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationInfo,
    field_validator,
)

from app.models.interaction import InteractionType


class Gender(str, Enum):
    """Gender options for dating profiles."""

    MALE = "male"
    FEMALE = "female"
    NON_BINARY = "non_binary"
    OTHER = "other"


class Sexuality(str, Enum):
    """Sexuality options for dating preferences."""

    STRAIGHT = "straight"
    GAY = "gay"
    LESBIAN = "lesbian"
    BISEXUAL = "bisexual"
    PANSEXUAL = "pansexual"
    ASEXUAL = "asexual"
    OTHER = "other"


class DatingProfile(BaseModel):
    """Dating profile information and preferences.

    This model contains all the information shown on a user's dating profile,
    including their bio, photos, and basic information.

    Attributes:
        user_id: Unique identifier of the user
        bio: Short biography or description
        birth_date: User's birth date for age calculation
        gender: User's gender identity
        sexuality: User's sexual orientation
        photos: List of photo URLs (max 5)
        max_distance_miles: Maximum distance for potential matches
        min_age_preference: Minimum age for potential matches
        max_age_preference: Maximum age for potential matches
        gender_preference: List of genders they're interested in
        is_visible: Whether profile is visible in dating pool
        created_at: When the profile was created
        updated_at: When the profile was last updated
    """

    model_config = ConfigDict(frozen=True)

    user_id: UUID4
    bio: Annotated[str, Field(max_length=500)]
    birth_date: date
    gender: Gender
    sexuality: Sexuality
    photos: Annotated[list[HttpUrl], Field(max_length=5)]
    max_distance_miles: Annotated[float, Field(ge=1, le=100)] = 50
    min_age_preference: Annotated[int, Field(ge=18, le=100)] = 18
    max_age_preference: Annotated[int, Field(ge=18, le=100)] = 100
    gender_preference: list[Gender]
    is_visible: bool = True
    created_at: datetime
    updated_at: datetime

    @field_validator("birth_date")
    @classmethod
    def validate_age(cls, v: date) -> date:
        """Validate that the user is at least 18 years old."""
        age = (date.today() - v).days / 365.25
        if age < 18:
            raise ValueError("Must be at least 18 years old")
        if age > 100:
            raise ValueError("Invalid birth date")
        return v

    @field_validator("max_age_preference")
    @classmethod
    def validate_age_range(cls, v: int, info: ValidationInfo) -> int:
        """Validate that max age is greater than min age."""
        if v < info.data.get("min_age_preference", 18):
            raise ValueError("Maximum age must be greater than minimum age")
        return v

    @field_validator("gender_preference")
    @classmethod
    def validate_gender_preference(cls, v: list[Gender]) -> list[Gender]:
        if not v:
            raise ValueError("Must specify at least one gender preference")
        return v


class DatingMatch(BaseModel):
    """Represents a potential or confirmed match between users.

    Tracks the status of dating interactions between two users,
    including likes, super likes, and mutual matches.

    Attributes:
        match_id: Unique identifier for the match
        user_id_a: First user's ID
        user_id_b: Second user's ID
        user_a_action: Action taken by first user (like/pass/super)
        user_b_action: Action taken by second user (like/pass/super)
        distance_miles: Distance between users when matched
        compatibility_score: Calculated compatibility from interaction service
        is_mutual: Whether both users have liked each other
        created_at: When the match was created
        updated_at: When the match was last updated
    """

    model_config = ConfigDict(frozen=True)

    match_id: UUID4
    user_id_a: UUID4
    user_id_b: UUID4
    user_a_action: InteractionType | None = None
    user_b_action: InteractionType | None = None
    distance_miles: float
    compatibility_score: Annotated[float, Field(ge=0, le=1)]
    is_mutual: bool = False
    created_at: datetime
    updated_at: datetime


class DatingFilter(BaseModel):
    """Filter criteria for dating matches.

    Used to filter potential matches based on user preferences
    and search criteria.

    Attributes:
        max_distance_miles: Maximum distance to potential matches
        min_age: Minimum age of potential matches
        max_age: Maximum age of potential matches
        gender_preference: List of acceptable genders
        exclude_seen: Whether to exclude previously seen profiles
        exclude_matched: Whether to exclude existing matches
        min_compatibility: Minimum compatibility score required
        limit: Maximum number of matches to return
        offset: Number of matches to skip
    """

    model_config = ConfigDict(frozen=True)

    max_distance_miles: Annotated[float, Field(ge=1, le=100)] = 50
    min_age: Annotated[int, Field(ge=18, le=100)] = 18
    max_age: Annotated[int, Field(ge=18, le=100)] = 100
    gender_preference: list[Gender] | None = None
    exclude_seen: bool = True
    exclude_matched: bool = True
    min_compatibility: Annotated[float, Field(ge=0, le=1)] = 0.0
    limit: Annotated[int, Field(ge=1, le=100)] = 50
    offset: Annotated[int, Field(ge=0)] = 0

    @field_validator("max_age")
    @classmethod
    def validate_age_range(cls, v: int, info: ValidationInfo) -> int:
        """Validate that max age is greater than min age."""
        if v < info.data.get("min_age", 18):
            raise ValueError("Maximum age must be greater than minimum age")
        return v
