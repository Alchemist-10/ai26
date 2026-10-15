"""Recorded imports resolved once at startup; never scan/hash videos in API polls."""
import hashlib
import json
import os
import re
from pathlib import Path
from source_clock import validate_recording_clock

DATA_ROOT = Path(os.environ.get('AI26_DATA_ROOT', Path(__file__).parent / 'data'))
SOURCE_ROOT = Path(os.environ.get('AI26_SOURCE_ROOT', DATA_ROOT / 'sources'))
MAX_MANIFEST_BYTES = 64 * 1024


def file_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_source(camera_id, root=SOURCE_ROOT, *, verify=False):
    """An invalid explicit binding is an error, never silently replaced by a demo clip."""
    if not re.fullmatch(r'CAM-[0-9]{2}', camera_id): raise ValueError('Invalid camera ID')
    root = Path(root).resolve()
    pointer = root / camera_id / 'active.json'
    if not pointer.exists() and not pointer.is_symlink(): return None
    return load_manifest(camera_id, root, pointer, verify=verify)


def load_release(camera_id, release, root=SOURCE_ROOT, *, verify=False):
    if not re.fullmatch(r'CAM-[0-9]{2}', camera_id) or not re.fullmatch(r'[0-9a-f]{32}', release):
        raise ValueError('Invalid release identity')
    root = Path(root).resolve()
    binding = load_manifest(camera_id, root, root / camera_id / 'releases' / release / 'manifest.json', verify=verify)
    if binding['manifest']['release'] != release: raise ValueError('Release identity mismatch')
    return binding


def load_manifest(camera_id, root, pointer, *, verify=False):
    try:
        if not pointer.resolve().is_relative_to(root): raise ValueError('Manifest escapes managed root')
        with pointer.open('rb') as stream:
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES: raise ValueError('Source manifest is too large')
        manifest = json.loads(raw)
        release = manifest['release']
        if type(manifest['version']) is not int or manifest['version'] != 1 or manifest['camera_id'] != camera_id or not re.fullmatch(r'[0-9a-f]{32}', release):
            raise ValueError('Invalid source binding identity/version')
        if 'recording_clock' in manifest:
            validate_recording_clock(manifest['recording_clock'])
        base = (root / camera_id / 'releases' / release).resolve()
        if not base.is_relative_to(root): raise ValueError('Source release escapes managed root')
        for role, name in [('original', 'original.media'), ('playback', 'playback.mp4')]:
            info = manifest[role]; path = (base / name).resolve()
            if not path.is_relative_to(base) or info['file'] != name or not re.fullmatch(r'[0-9a-f]{64}', info['sha256']):
                raise ValueError('Invalid managed file reference')
            if not path.is_file() or type(info['bytes']) is not int or info['bytes'] < 1 or path.stat().st_size != info['bytes']:
                raise ValueError('Managed source is missing or its size changed')
            if verify and file_digest(path) != info['sha256']:
                raise ValueError('Managed source digest mismatch')
        return {'original':base/'original.media', 'playback':base/'playback.mp4', 'manifest':manifest}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f'Invalid managed source for {camera_id}: {error}') from error


def load_catalog(camera_ids, root=SOURCE_ROOT):
    return {camera:binding for camera in camera_ids if (binding := load_source(camera, root, verify=True)) is not None}
