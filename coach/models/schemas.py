"""Pydantic models for triathlon coach.

Specchio del DB. Validazione lato Python prima di scrivere su Supabase.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================================
# Enums
# ============================================================================
class Sport(str, Enum):
    SWIM = "swim"
    BIKE = "bike"
    RUN = "run"
    BRICK = "brick"
    STRENGTH = "strength"
    OTHER = "other"


class Source(str, Enum):
    GARMIN = "garmin"
    STRAVA = "strava"
    MANUAL = "manual"


class Phase(str, Enum):
    BASE = "base"
    BUILD = "build"
    SPECIFIC = "specific"
    PEAK = "peak"
    TAPER = "taper"
    RECOVERY = "recovery"


class SubjectiveKind(str, Enum):
    POST_SESSION = "post_session"
    MORNING = "morning"
    EVENING_DEBRIEF = "evening_debrief"
    ILLNESS = "illness"
    INJURY = "injury"
    FREE_NOTE = "free_note"


class ReadinessLabel(str, Enum):
    READY = "ready"
    CAUTION = "caution"
    REST = "rest"


# ============================================================================
# Models
# ============================================================================
class BaseDBModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Activity(BaseDBModel):
    external_id: str
    source: Source
    sport: Sport
    started_at: datetime
    duration_s: int = Field(gt=0)
    distance_m: Optional[float] = None
    elevation_gain_m: Optional[float] = None

    avg_hr: Optional[int] = Field(None, ge=0, le=250)
    max_hr: Optional[int] = Field(None, ge=0, le=250)
    hr_zones_s: Optional[dict[str, int]] = None

    avg_power_w: Optional[float] = None
    np_w: Optional[float] = None
    avg_pace_s_per_km: Optional[float] = None
    avg_pace_s_per_100m: Optional[float] = None

    tss: Optional[float] = None
    if_value: Optional[float] = None
    rpe: Optional[int] = Field(None, ge=1, le=10)

    # Garmin completeness Step 5.1
    splits: Optional[list[dict[str, Any]]] = None
    weather: Optional[dict[str, Any]] = None

    raw_payload: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


class DailyWellness(BaseDBModel):
    date: date

    hrv_rmssd: Optional[float] = None
    hrv_status: Optional[str] = None

    sleep_score: Optional[int] = Field(None, ge=0, le=100)
    sleep_total_s: Optional[int] = None
    sleep_deep_s: Optional[int] = None
    sleep_rem_s: Optional[int] = None
    sleep_efficiency: Optional[float] = None

    body_battery_min: Optional[int] = None
    body_battery_max: Optional[int] = None
    stress_avg: Optional[int] = None

    resting_hr: Optional[int] = None

    training_status: Optional[str] = None
    training_load_acute: Optional[float] = None
    training_load_chronic: Optional[float] = None
    vo2max_run: Optional[float] = None
    vo2max_bike: Optional[float] = None

    # Garmin completeness Step 5.1
    training_readiness_score: Optional[int] = None
    avg_sleep_stress: Optional[float] = None

    raw_payload: Optional[dict[str, Any]] = None


class SubjectiveLog(BaseDBModel):
    logged_at: datetime
    activity_id: Optional[UUID] = None
    kind: SubjectiveKind

    rpe: Optional[int] = Field(None, ge=1, le=10)
    sleep_quality: Optional[int] = Field(None, ge=1, le=10)
    motivation: Optional[int] = Field(None, ge=1, le=10)
    soreness: Optional[int] = Field(None, ge=0, le=10)

    illness_flag: bool = False
    illness_details: Optional[str] = None
    injury_flag: bool = False
    injury_details: Optional[str] = None
    injury_location: Optional[str] = None

    raw_text: Optional[str] = None
    parsed_data: Optional[dict[str, Any]] = None


class PhysiologyZones(BaseDBModel):
    discipline: Sport
    valid_from: date
    valid_to: Optional[date] = None

    ftp_w: Optional[float] = None
    threshold_pace_s_per_km: Optional[float] = None
    css_pace_s_per_100m: Optional[float] = None
    lthr: Optional[int] = None
    hr_max: Optional[int] = None

    test_activity_id: Optional[UUID] = None
    method: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("discipline")
    @classmethod
    def discipline_must_be_main(cls, v: Sport) -> Sport:
        if v not in (Sport.SWIM, Sport.BIKE, Sport.RUN):
            raise ValueError("zones only for swim/bike/run")
        return v


class DailyMetrics(BaseDBModel):
    date: date
    ctl: Optional[float] = None
    atl: Optional[float] = None
    tsb: Optional[float] = None
    daily_tss: Optional[float] = None
    # PMC Garmin (training load proprietario)
    garmin_acute_load: Optional[float] = None
    garmin_chronic_load: Optional[float] = None
    garmin_load_balance: Optional[float] = None
    garmin_training_readiness: Optional[int] = None
    garmin_training_status: Optional[str] = None
    ctl_swim: Optional[float] = None
    ctl_bike: Optional[float] = None
    ctl_run: Optional[float] = None

    hrv_z_score: Optional[float] = None
    hrv_baseline_28d: Optional[float] = None
    hrv_baseline_28d_sd: Optional[float] = None

    readiness_score: Optional[int] = Field(None, ge=0, le=100)
    readiness_label: Optional[ReadinessLabel] = None
    readiness_factors: Optional[dict[str, int]] = None

    flags: list[str] = Field(default_factory=list)


class Mesocycle(BaseDBModel):
    name: str
    phase: Phase
    start_date: date
    end_date: date
    target_race_id: Optional[UUID] = None
    weekly_pattern: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


class PlannedSession(BaseDBModel):
    mesocycle_id: Optional[UUID] = None
    planned_date: date
    sport: Sport
    session_type: Optional[str] = None
    duration_s: Optional[int] = None
    target_tss: Optional[float] = None
    target_zones: Optional[dict[str, float]] = None
    description: Optional[str] = None
    structured: Optional[dict[str, Any]] = None
    status: str = "planned"
    completed_activity_id: Optional[UUID] = None


class Race(BaseDBModel):
    name: str
    race_date: date
    race_tz: str = "Europe/Rome"
    distance: Optional[str] = None
    location: Optional[str] = None
    priority: Optional[str] = None
    target_time_s: Optional[int] = None
    target_position: Optional[str] = None
    actual_time_s: Optional[int] = None
    actual_position: Optional[str] = None
    notes: Optional[str] = None


class Health(BaseModel):
    component: str
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    failure_count: int = 0
    last_error: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
