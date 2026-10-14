"""Validation shared by HTTP and ingestion; no model loading required."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator, model_validator
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

class WatchlistCondition(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    active_from: StrictFloat | None = None
    active_until: StrictFloat | None = None
    minimum_sightings: StrictInt = Field(default=1, ge=1, le=1000)
    history_window_seconds: StrictFloat = Field(default=0, ge=0, le=7*86400)

    @model_validator(mode='after')
    def valid_window(self):
        if self.active_from is not None and self.active_until is not None and self.active_from >= self.active_until:
            raise ValueError('Watchlist active_from must be before active_until')
        if self.minimum_sightings > 1 and self.history_window_seconds <= 0:
            raise ValueError('A positive history window is required for multiple sightings')
        return self

class ZonePermit(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)
    permit_id: StrictStr = Field(min_length=1, max_length=64)
    plate: StrictStr = Field(min_length=1, max_length=16)
    camera_ids: list[StrictStr] = Field(min_length=1, max_length=9)
    valid_from: StrictFloat
    valid_until: StrictFloat
    reason: StrictStr = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def valid_period(self):
        if self.valid_from >= self.valid_until:
            raise ValueError('Permit valid_from must be before valid_until')
        if len(set(self.camera_ids)) != len(self.camera_ids):
            raise ValueError('Permit camera IDs must be unique')
        return self

class RuleConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    watchlist: dict[str, str] = Field(default_factory=dict)
    watchlist_conditions: dict[str, WatchlistCondition] = Field(default_factory=dict)
    restricted_cameras: list[str] = Field(default_factory=list)
    zone_permits: list[ZonePermit] = Field(default_factory=list, max_length=1000)
    dwell_zones: list[ZoneRule] = Field(default_factory=list)

    @field_validator('watchlist')
    @classmethod
    def watchlist_reasons_nonblank(cls, value):
        if any(not isinstance(reason,str) or not reason.strip() for reason in value.values()):
            raise ValueError('Every watchlist entry needs a nonblank reason')
        return value

class CameraConfigurationUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)
    expected_revision: int = Field(ge=1, strict=True)
    location: StrictStr = Field(min_length=1, max_length=200)
    location_confirmed: bool = Field(strict=True)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    reviewer: StrictStr = Field(min_length=1, max_length=100)
    reason: StrictStr = Field(min_length=1, max_length=1000)

class CameraPairConstraintUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)
    from_camera_id: StrictStr = Field(pattern=r'^CAM-[0-9]{2}$')
    to_camera_id: StrictStr = Field(pattern=r'^CAM-[0-9]{2}$')
    min_travel_seconds: StrictFloat = Field(ge=0, le=86400)
    max_travel_seconds: StrictFloat = Field(gt=0, le=86400)
    enabled: StrictBool
    reviewer: StrictStr = Field(min_length=1, max_length=100)
    reason: StrictStr = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def ordered_window(self):
        if self.min_travel_seconds >= self.max_travel_seconds:
            raise ValueError('Minimum travel time must be less than maximum travel time')
        return self

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
    mfa_code: StrictStr | None = Field(default=None, min_length=1, max_length=32)

class AuthMfaCodeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: StrictStr = Field(min_length=1, max_length=32)

class AuthMfaDisableRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: StrictStr = Field(min_length=1, max_length=256)
    code: StrictStr = Field(min_length=1, max_length=32)

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
