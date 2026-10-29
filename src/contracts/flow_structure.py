"""Source-declared conditional edges, independent of execution policy."""

from pydantic import BaseModel, ConfigDict, Field


class ConditionalExit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_id: str = Field(min_length=1, strict=True)
    target_id: str = Field(min_length=1, strict=True)
    when_true: bool = Field(strict=True)
