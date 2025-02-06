from pydantic import BaseModel


class HealthCheckResponseSchema(BaseModel):
    success: bool
