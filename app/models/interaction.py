from datetime import datetime
from enum import Enum

from pydantic import UUID4, BaseModel, ConfigDict, Field


class InteractionType(str, Enum):
    """Types of interactions that can be recorded.

    Attributes:
        LIKE: Like on a post/comment
        COMMENT: Comment on a post
        SHARE: Share a post
        FOLLOW: Follow a user
        BLOCK: Block a user
        REPORT: Report content/user
        SWIPE_LEFT: Pass/reject in dating
        SWIPE_RIGHT: Like in dating
        SUPER_LIKE: Super like in dating
        MATCH: Match between users
        MESSAGE: Direct message
    """

    LIKE = "LIKE"
    COMMENT = "COMMENT"
    SHARE = "SHARE"
    FOLLOW = "FOLLOW"
    BLOCK = "BLOCK"
    REPORT = "REPORT"
    SWIPE_LEFT = "SWIPE_LEFT"  # Dating pass/reject
    SWIPE_RIGHT = "SWIPE_RIGHT"  # Dating like
    SUPER_LIKE = "SUPER_LIKE"  # Dating super like
    MATCH = "MATCH"
    MESSAGE = "MESSAGE"


class InteractionStrength(float, Enum):
    """Weights for different types of interactions.

    These weights are used in calculating user similarity
    and content recommendations.
    """

    # Video view weights
    VIEW_START = 0.1
    VIEW_25 = 0.2
    VIEW_50 = 0.4
    VIEW_75 = 0.6
    VIEW_COMPLETE = 1.0
    VIEW_LOOP = 1.2
    SHARE = 2.0
    LIKE = 1.5
    SAVE = 1.8

    # Engagement weights
    LONG_VIEW = 1.3
    ENGAGED_VIEW = 1.4
    UNREGRETTED_VIEW = 0.8

    # Creator weights
    PROFILE_VIEW = 0.5
    FOLLOW = 2.5

    # Comment weights
    COMMENT = 1.6
    COMMENT_LIKE = 0.7
    COMMENT_REPLY = 1.4

    # Dating weights
    SWIPE_RIGHT = 2.0  # Like
    SWIPE_LEFT = -1.0  # Pass
    SUPER_LIKE = 3.0


class VideoInteractionMetrics(BaseModel):
    """Metrics for a user's interaction with a video.

    This model tracks detailed engagement metrics for a single
    video viewing session.

    Attributes:
        video_id: ID of the video
        user_id: ID of the user watching
        view_duration_ms: How long they watched
        video_duration_ms: Total video length
        completion_rate: Percentage watched
        loop_count: Number of times rewatched
        avg_view_duration_ms: Average view duration across loops
        engagement_signals: List of engagement types
        unregretted: Whether they watched meaningfully
        created_at: When the interaction occurred
    """

    model_config = ConfigDict(frozen=True)

    video_id: UUID4
    user_id: UUID4
    view_duration_ms: int = Field(ge=0)
    video_duration_ms: int = Field(ge=0)
    completion_rate: float = Field(ge=0, le=1)
    loop_count: int = Field(ge=0)
    avg_view_duration_ms: int = Field(ge=0)
    engagement_signals: list[InteractionType] = []
    unregretted: bool = False
    created_at: datetime


class CreatorInteractionMetrics(BaseModel):
    """Metrics for a user's interaction with a creator.

    This model tracks how users engage with content creators,
    used for both recommendations and dating matches.

    Attributes:
        creator_id: ID of the creator
        user_id: ID of the viewing user
        profile_view_count: Number of profile views
        total_view_duration_ms: Total time watching their content
        completion_rate_avg: Average completion rate of their videos
        like_rate: Percentage of videos liked
        comment_rate: Percentage of videos commented on
        share_rate: Percentage of videos shared
        save_rate: Percentage of videos saved
        dating_signals: List of dating-related interactions
        created_at: When first interaction occurred
        updated_at: When last interaction occurred
    """

    model_config = ConfigDict(frozen=True)

    creator_id: UUID4
    user_id: UUID4
    profile_view_count: int = Field(ge=0)
    total_view_duration_ms: int = Field(ge=0)
    completion_rate_avg: float = Field(ge=0, le=1)
    like_rate: float = Field(ge=0, le=1)
    comment_rate: float = Field(ge=0, le=1)
    share_rate: float = Field(ge=0, le=1)
    save_rate: float = Field(ge=0, le=1)
    dating_signals: list[InteractionType] = []
    created_at: datetime
    updated_at: datetime


class UserSimilarityScore(BaseModel):
    """Model representing a similarity score between two users.

    This model contains information about how similar two users are
    based on their interactions and content preferences.
    """

    model_config = ConfigDict(frozen=True)

    user_id: UUID4 = Field(description="ID of the first user")
    target_id: UUID4 = Field(description="ID of the second user")
    content_similarity: float = Field(
        description="How similar their content preferences are (0-1)"
    )
    interaction_similarity: float = Field(
        description="How similar their interaction patterns are (0-1)"
    )
    social_similarity: float = Field(
        description="How similar their social graphs are (0-1)"
    )
    total_score: float = Field(description="Overall similarity score (0-1)")
