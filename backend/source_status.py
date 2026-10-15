"""Read-only source inspection. No video hashes, decoders, SQL or live activation."""
import json
import math
import re
import time
from pathlib import Path

import cameras
from source_catalog import SOURCE_ROOT, MAX_MANIFEST_BYTES, load_source
from source_selection import selection_token, same_release_manifest
from source_clock import validate_recording_clock

HISTORY_LIMIT = 10


def text(value, limit=1000):
    return value[:limit] if isinstance(value, str) else None


def number(value):
    try:
        return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def release_summary(manifest):
    """Project local metadata rather than exposing arbitrary manifest fields/paths."""
    result = {key: text(manifest.get(key)) for key in ('release', 'reviewer', 'reason', 'time_basis', 'previous_release')}
    result['imported_at'] = number(manifest.get('imported_at'))
    clock = validate_recording_clock(manifest.get('recording_clock'))
    result['recording_clock'] = ({'start_utc': clock['start_utc'],
                                  'uncertainty_seconds': clock['uncertainty_seconds'],
                                  'provenance': clock['provenance'],
                                  'status': clock['status']} if clock else None)
    for role in ('original', 'playback'):
        info = manifest.get(role, {})
        video = info.get('video', {}) if isinstance(info, dict) else {}
        if not isinstance(video, dict): video = {}
        result[role] = {
            'bytes': number(info.get('bytes')) if isinstance(info, dict) else None,
            'sha256': text(info.get('sha256'), 64) if isinstance(info, dict) else None,
            'video': {key: number(video.get(key)) for key in ('width', 'height', 'fps', 'duration_seconds', 'frame_count')},
        }
    return result


def file_summary(path, expected_bytes=None):
    path = Path(path)
    try:
        size = path.stat().st_size if path.is_file() else None
    except OSError:
        size = None
    return {'filename': path.name, 'available': size is not None, 'bytes': size,
            'size_matches_import': None if expected_bytes is None else size == expected_bytes}


def recent_releases(camera_id, selected, root):
    """Follow at most ten parent manifests; do not scan the source directory."""
    releases, seen, error = [], set(), None
    manifest = selected['manifest'] if selected else None
    base = (Path(root).resolve() / camera_id / 'releases').resolve()
    if not base.is_relative_to(Path(root).resolve()):
        return {'releases': [], 'more': False, 'error': 'Import history directory is outside the managed source root.'}
    while manifest and len(releases) < HISTORY_LIMIT:
        release = manifest.get('release')
        if not isinstance(release, str) or not re.fullmatch(r'[0-9a-f]{32}', release) or release in seen:
            error = 'Import history contains an invalid or repeated release.'; break
        seen.add(release); releases.append(release_summary(manifest))
        previous = manifest.get('previous_release')
        if previous is None: manifest = None; break
        if not isinstance(previous, str) or not re.fullmatch(r'[0-9a-f]{32}', previous):
            error = 'An earlier import reference is invalid.'; manifest = None; break
        if len(releases) == HISTORY_LIMIT: break
        path = (base / previous / 'manifest.json').resolve()
        try:
            if not path.is_relative_to(base): raise ValueError('Outside source root')
            with path.open('rb') as stream:
                raw = stream.read(MAX_MANIFEST_BYTES + 1)
            if len(raw) > MAX_MANIFEST_BYTES: raise ValueError('Manifest too large')
            manifest = json.loads(raw)
            if not isinstance(manifest, dict) or manifest.get('camera_id') != camera_id or manifest.get('release') != previous or type(manifest.get('version')) is not int or manifest['version'] != 1:
                raise ValueError('Wrong release identity')
        except (OSError, ValueError, TypeError):
            error = 'An earlier import manifest is unavailable or invalid.'; manifest = None
    return {'releases': releases, 'more': bool(manifest and manifest.get('previous_release')) and not error,
            'error': error}


def source_status(camera_id, root=SOURCE_ROOT):
    if camera_id not in cameras.CAMERAS_BY_ID: raise ValueError('Unknown camera')
    binding = cameras.MANAGED_SOURCES.get(camera_id)
    inference = cameras.camera_source(camera_id)
    playback = cameras.camera_playback_source(camera_id)
    configured = Path(cameras.CAMERAS_BY_ID[camera_id]['path'])
    kind = 'managed' if binding else 'configured_original' if inference == configured and inference.is_file() else 'bundled_proxy' if inference.is_file() else 'missing'
    active_manifest = binding['manifest'] if binding else None
    active = {'kind': kind, 'release': release_summary(active_manifest) if active_manifest else None,
              'inference': file_summary(inference, active_manifest['original']['bytes'] if binding else None),
              'playback': file_summary(playback, active_manifest['playback']['bytes'] if binding else None)}
    try:
        pointer = Path(root) / camera_id / 'active.json'
        if pointer.exists() and pointer.stat().st_size > MAX_MANIFEST_BYTES: raise ValueError('Manifest too large')
        selected = load_source(camera_id, root, verify=False)
        active_id = active_manifest['release'] if binding else None
        selected_id = selected['manifest']['release'] if selected else None
        # Same release with edited manifest fields is also a pending change.
        status = 'current' if active_id == selected_id and (not binding or same_release_manifest(active_manifest,selected['manifest'])) else 'restart_required'
        marker=selected['manifest'].get('source_selection') if selected else None
        if not isinstance(marker,dict): marker=None
        claim={key:text(marker.get(key)) for key in ('id','intent','reviewer','reason','from_release','to_release')} if marker else None
        if claim: claim['selected_at']=number(marker.get('selected_at'))
        selection = {'status': status, 'release': release_summary(selected['manifest']) if selected else None,
                     'error': None,'token':selection_token(selected),'last_action':claim}
        history = recent_releases(camera_id, selected, root)
    except (OSError, ValueError):
        selection = {'status': 'invalid', 'release': None,'token':None,'last_action':None,
                     'error': 'The selected import is missing or invalid. Restore a retained manifest while the app is stopped before restarting.'}
        history = {'releases': [], 'more': False, 'error': 'History could not be loaded from the selected import.'}
    return {'camera_id': camera_id, 'checked_at': time.time(), 'time_basis': 'replay_clock',
            'active': active, 'selection': selection, 'history': history,
            'verification': 'File presence and size checked now. Imported hashes were verified at API startup; pending selections and history have not been rehashed.'}
