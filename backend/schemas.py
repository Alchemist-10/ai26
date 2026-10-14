"""Validation shared by HTTP and ingestion; no model loading required."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator, model_validator
import math

class Observation(BaseModel):
    model_config = ConfigDict(extra='allow', allow_inf_nan=False)
    camera_id: StrictStr
    kind: Literal['vehicle', 'plate']
    confidence: float = Field(ge=0, le=1)
    bbox: tuple[int, int, int, int]
    ts: float
    session_id: str | None = None
    track_id: int | None = None

    @field_validator('bbox')
    @classmethod
    def check_box(cls, v):
        if v[2] < v[0] or v[3] < v[1]: raise ValueError('Invalid bounding box')
        return v

class QueryRequest(BaseModel):
    question: StrictStr = Field(min_length=1, max_length=500)
    @field_validator('question')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('Enter a question')
        return value.strip()

class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    state: Literal['acknowledged', 'dismissed', 'reviewed', 'open', 'escalated']
    reviewer: StrictStr = Field(min_length=1, max_length=100)
    note: StrictStr = Field(default='', max_length=1000)
    escalation_target: StrictStr | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode='after')
    def escalation_requires_target(self):
        if self.state == 'escalated' and not self.escalation_target:
            raise ValueError('An escalation target is required')
        if self.state != 'escalated' and self.escalation_target is not None:
            raise ValueError('An escalation target is only valid for escalated state')
        return self

class ZoneRule(BaseModel):
    camera_id: str
    # normalized image coordinates: left, top, right, bottom
    zone: tuple[float, float, float, float]
    dwell_seconds: float = Field(default=30, ge=10, le=3600)
    max_gap_seconds: float = Field(default=5, ge=1, le=60)
    @field_validator('zone')
    @classmethod
    def valid_zone(cls, v):
        if any(not math.isfinite(x) or x<0 or x>1 for x in v) or v[0]>=v[2] or v[1]>=v[3]:
            raise ValueError('Zone must be a normalized positive rectangle')
        return v

class RuleConfig(BaseModel):
    watchlist: dict[str, str] = Field(default_factory=dict)
    restricted_cameras: list[str] = Field(default_factory=list)
    dwell_zones: list[ZoneRule] = Field(default_factory=list)

class CameraConfigurationUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)
    expected_revision: int = Field(ge=1, strict=True)
    location: StrictStr = Field(min_length=1, max_length=200)
    location_confirmed: bool = Field(strict=True)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    reviewer: StrictStr = Field(min_length=1, max_length=100)
    reason: StrictStr = Field(min_length=1, max_length=1000)

class SourceSelectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    release: StrictStr = Field(pattern=r'^[0-9a-f]{32}$')
    expected_token: StrictStr = Field(pattern=r'^(default|[0-9a-f]{64})$')
    intent: Literal['select', 'rollback']
    reviewer: StrictStr = Field(min_length=1, max_length=100)
    reason: StrictStr = Field(min_length=1, max_length=1000)

class AuthLoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: StrictStr = Field(min_length=3, max_length=32)
    password: StrictStr = Field(min_length=1, max_length=256)

class AuthUserCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: StrictStr = Field(min_length=3, max_length=32)
    password: StrictStr = Field(min_length=14, max_length=256)
    role: Literal['admin', 'operator', 'analyst', 'viewer']
    case_ids: list[StrictStr] = Field(default_factory=list, max_length=100)

class AuthUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['admin', 'operator', 'analyst', 'viewer'] | None = None
    disabled: StrictBool | None = None
    case_ids: list[StrictStr] | None = Field(default=None, max_length=100)

    @model_validator(mode='after')
    def at_least_one_change(self):
        if self.role is None and self.disabled is None and self.case_ids is None:
            raise ValueError('Set role, disabled, or case_ids')
        return self

class AuthPasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: StrictStr = Field(min_length=14, max_length=256)
