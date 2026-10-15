"""Validation and projection for operator-claimed recording-clock metadata."""
from datetime import datetime, timezone
import math


MAX_CLOCK_UNCERTAINTY_SECONDS = 86400


def _finite(value):
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def normalize_recording_clock(start_utc, uncertainty_seconds=None):
    """Return a bounded UTC clock claim, or None when no claim was supplied."""
    if start_utc is None:
        if uncertainty_seconds is not None:
            raise ValueError('Clock uncertainty requires a recording start time')
        return None
    if not isinstance(start_utc, str) or not 1 <= len(start_utc) <= 64:
        raise ValueError('Recording start time must include a timezone and be at most 64 characters')
    try:
        parsed = datetime.fromisoformat(start_utc[:-1] + '+00:00' if start_utc.endswith(('Z', 'z')) else start_utc)
    except ValueError as error:
        raise ValueError('Recording start time must be an ISO-8601 timestamp with a timezone') from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Recording start time must include a timezone')
    if uncertainty_seconds is not None:
        if isinstance(uncertainty_seconds, bool) or not isinstance(uncertainty_seconds, (int, float)):
            raise ValueError('Clock uncertainty must be a number from 0 to 86400 seconds')
        if not _finite(uncertainty_seconds) or not 0 <= uncertainty_seconds <= MAX_CLOCK_UNCERTAINTY_SECONDS:
            raise ValueError('Clock uncertainty must be a number from 0 to 86400 seconds')
    try:
        normalized = parsed.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
        epoch = parsed.timestamp()
    except (OverflowError, OSError, ValueError) as error:
        raise ValueError('Recording start time is outside the supported UTC range') from error
    return {'start_utc': normalized, 'start_epoch': epoch,
            'uncertainty_seconds': uncertainty_seconds,
            'provenance': 'operator_claimed', 'status': 'unverified'}


def validate_recording_clock(value):
    """Validate the serialized manifest form and reject forged runtime fields."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
            'start_utc', 'start_epoch', 'uncertainty_seconds', 'provenance', 'status'}:
        raise ValueError('Invalid recording-clock claim')
    normalized = normalize_recording_clock(value['start_utc'], value['uncertainty_seconds'])
    if (value['provenance'] != 'operator_claimed' or value['status'] != 'unverified'
            or type(value['start_epoch']) not in (int, float)
            or not _finite(value['start_epoch'])
            or abs(value['start_epoch'] - normalized['start_epoch']) > 0.000001):
        raise ValueError('Invalid recording-clock claim')
    return normalized


def source_time_from_decoder(reported_milliseconds, frame_index, fps, duration_seconds):
    """Prefer a useful decoder timestamp; otherwise preserve the explicit FPS estimate."""
    estimate = frame_index / fps if (type(frame_index) is int and frame_index >= 0 and
                                      type(fps) in (int, float) and _finite(fps) and fps > 0) else None
    if (type(reported_milliseconds) in (int, float) and _finite(reported_milliseconds) and
            reported_milliseconds > 0 and type(duration_seconds) in (int, float) and
            _finite(duration_seconds) and duration_seconds > 0 and
            reported_milliseconds <= duration_seconds * 1000):
        return reported_milliseconds / 1000, 'decoder_reported_position_msec'
    if estimate is not None:
        return estimate, 'frame_index_divided_by_reported_fps'
    return None, 'source_time_unavailable'


def source_capture_clock_fields(clock, source_time_seconds, source_time_basis='frame_index_divided_by_reported_fps'):
    """Project a claimed absolute source time without promoting it to event time."""
    if clock is None or type(source_time_seconds) not in (int, float) or not _finite(source_time_seconds):
        return {}
    if not 0 <= source_time_seconds <= 86400:
        return {}
    epoch = clock['start_epoch'] + source_time_seconds
    try:
        timestamp = datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    except (OverflowError, OSError, ValueError):
        return {}
    return {'claimed_source_capture_time_utc': timestamp,
            'source_offset_basis': source_time_basis,
            'recording_clock_status': 'operator_claimed_unverified',
            'recording_clock_uncertainty_seconds': clock['uncertainty_seconds']}
