"""Dry-run-first cleanup of old, unselected managed footage releases."""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import time

from import_source import ImportBusy
from source_catalog import DATA_ROOT, SOURCE_ROOT, load_release, load_source
from cameras import CAMERAS_BY_ID

MIN_RETENTION_DAYS = 30
MAX_METADATA_BYTES = 64 * 1024
RELEASE_ID = re.compile(r'[0-9a-f]{32}')


def _finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except (OverflowError, ValueError, TypeError):
        return False


def _lock(path, label):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.close()
        raise ImportBusy(f'Cannot prune while {label} is active') from error
    return handle


def _release_lock(handle):
    try:
        fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()


def _regular_directory(path, parent):
    try:
        path.lstat()
        return (not path.is_symlink() and path.is_dir()
                and path.resolve().is_relative_to(parent.resolve()))
    except OSError:
        return False


def _tree_bytes(path):
    total = 0
    for root, directories, files in os.walk(path, followlinks=False):
        directories[:] = [name for name in directories if not (Path(root) / name).is_symlink()]
        for name in files:
            item = Path(root) / name
            try:
                info = item.lstat()
                if item.is_symlink() or not item.is_file():
                    continue
                total += info.st_size
            except OSError:
                continue
    return total


def _read_json(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_METADATA_BYTES:
            return None
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def _old_staging(parent, prefix, cutoff, *, area, camera_id=None):
    candidates, skipped = [], []
    if not _regular_directory(parent, parent.parent):
        return candidates, skipped
    for path in parent.iterdir():
        if not path.name.startswith(prefix):
            continue
        if not _regular_directory(path, parent):
            skipped.append({'camera_id': camera_id, 'staging': path.name,
                            'reason': 'Staging path is not a regular contained directory'})
            continue
        try:
            info = path.stat()
            if info.st_mtime >= cutoff:
                continue
            if any(item.is_symlink() for item in path.rglob('*')):
                skipped.append({'camera_id': camera_id, 'staging': path.name,
                                'reason': 'Staging directory contains symlinked files'})
                continue
            candidates.append({'area': area, 'camera_id': camera_id, 'name': path.name,
                               'bytes': _tree_bytes(path), 'path': str(path)})
        except OSError:
            skipped.append({'camera_id': camera_id, 'staging': path.name,
                            'reason': 'Staging directory changed during inventory'})
    return candidates, skipped


def _selected_chain(camera, source_root):
    selected = load_source(camera, source_root, verify=True)
    protected = set()
    manifest = selected['manifest'] if selected else None
    if manifest:
        marker = manifest.get('source_selection')
        if isinstance(marker, dict):
            prior = marker.get('from_release')
            if isinstance(prior, str) and RELEASE_ID.fullmatch(prior):
                # A next-startup selection can roll back to a release that is not
                # the new pointer's parent; preserve the previous running release.
                load_release(camera, prior, source_root, verify=True)
                protected.add(prior)
    seen = set()
    while manifest:
        release = manifest.get('release')
        if not isinstance(release, str) or not RELEASE_ID.fullmatch(release) or release in seen:
            raise ValueError(f'{camera} has an invalid or cyclic selected release chain')
        seen.add(release)
        protected.add(release)
        previous = manifest.get('previous_release')
        if previous is None:
            break
        if not isinstance(previous, str) or not RELEASE_ID.fullmatch(previous):
            raise ValueError(f'{camera} has an invalid parent release reference')
        binding = load_release(camera, previous, source_root, verify=True)
        manifest = binding['manifest']
    return protected


def _receipt_inventory(data_root, cutoff):
    receipts, skipped = [], []
    jobs = data_root / 'uploads' / 'jobs'
    if not _regular_directory(jobs, data_root):
        return {'all': receipts, 'keep': set(), 'removable': [], 'skipped': skipped}, skipped
    for path in jobs.iterdir():
        if not re.fullmatch(r'[0-9a-f]{32}\.json', path.name):
            continue
        receipt = _read_json(path)
        if (not receipt or receipt.get('job_id') != path.stem
                or receipt.get('camera_id') not in CAMERAS_BY_ID
                or receipt.get('status') not in {'ready', 'failed', 'cancelled'}
                or not _finite_number(receipt.get('created_at'))):
            skipped.append({'job_id': path.stem, 'reason': 'Invalid terminal upload receipt retained'})
            continue
        try:
            receipts.append({'job_id': path.stem, 'camera_id': receipt['camera_id'],
                             'status': receipt['status'], 'created_at': receipt['created_at'],
                             'bytes': path.stat().st_size, 'path': str(path), 'release': receipt.get('release')})
        except OSError:
            skipped.append({'job_id': path.stem, 'reason': 'Upload receipt changed during inventory'})
    latest = {}
    for receipt in receipts:
        old = latest.get(receipt['camera_id'])
        if old is None or (receipt['created_at'], receipt['job_id']) > (old['created_at'], old['job_id']):
            latest[receipt['camera_id']] = receipt
    keep = {value['job_id'] for value in receipts
            if value['created_at'] >= cutoff or latest[value['camera_id']]['job_id'] == value['job_id']}
    removable = [value for value in receipts
                 if value['created_at'] < cutoff and value['job_id'] not in keep]
    return {'all': receipts, 'keep': keep, 'removable': removable, 'skipped': skipped}, skipped


def plan_prune(source_root=SOURCE_ROOT, data_root=DATA_ROOT, *, now=None, days=30):
    """Return eligible old release directories; fail closed on selected-chain errors."""
    if type(days) is not int or not MIN_RETENTION_DAYS <= days <= 365:
        raise ValueError(f'Retention must be an integer from {MIN_RETENTION_DAYS} to 365 days')
    root = Path(source_root).resolve()
    data = Path(data_root).resolve(strict=True)
    if root == data or data.is_relative_to(root):
        raise ValueError('Source root must be separate from and must not contain the application data root')
    if root.exists() and not root.is_dir():
        raise ValueError('Source root must be a directory')
    checked_at = time.time() if now is None else now
    if not _finite_number(checked_at):
        raise ValueError('Prune timestamp must be finite')
    cutoff = checked_at - days * 86400
    release_candidates, staging_candidates, skipped = [], [], []
    receipts, invalid_receipts = _receipt_inventory(data, cutoff)
    skipped.extend(invalid_receipts)
    upload_staging, upload_skipped = _old_staging(data / 'uploads', '.upload-', cutoff, area='upload')
    staging_candidates.extend(upload_staging)
    skipped.extend(upload_skipped)
    receipt_release_ids = set()
    for receipt in receipts['all']:
        if receipt['job_id'] not in receipts['keep'] or receipt['status'] != 'ready':
            continue
        value = receipt['release']
        release_id = value.get('release') if isinstance(value, dict) else None
        if isinstance(release_id, str) and RELEASE_ID.fullmatch(release_id):
            receipt_release_ids.add((receipt['camera_id'], release_id))
    for camera in sorted(CAMERAS_BY_ID):
        folder = root / camera
        if not _regular_directory(folder, root):
            continue
        import_staging, import_skipped = _old_staging(folder, '.import-', cutoff,
                                                      area='import', camera_id=camera)
        staging_candidates.extend(import_staging)
        skipped.extend(import_skipped)
        releases = folder / 'releases'
        if not _regular_directory(releases, root):
            continue
        try:
            protected = _selected_chain(camera, root)
            protected.update(release for receipt_camera, release in receipt_release_ids if receipt_camera == camera)
        except (OSError, ValueError) as error:
            skipped.append({'camera_id': camera, 'reason': f'Selected release chain is invalid: {error}'})
            continue
        for path in sorted(releases.iterdir()):
            if not RELEASE_ID.fullmatch(path.name) or path.name in protected:
                continue
            if not _regular_directory(path, releases):
                skipped.append({'camera_id': camera, 'release': path.name, 'reason': 'Not a regular contained directory'})
                continue
            try:
                binding = load_release(camera, path.name, root, verify=True)
                imported_at = binding['manifest'].get('imported_at')
                if (not _finite_number(imported_at)
                        or imported_at >= cutoff):
                    continue
                # Don't remove directories containing unexpected symlinked entries.
                if any(item.is_symlink() for item in path.rglob('*')):
                    skipped.append({'camera_id': camera, 'release': path.name, 'reason': 'Contains symlinked files'})
                    continue
                release_candidates.append({'camera_id': camera, 'release': path.name,
                                           'imported_at': imported_at, 'bytes': _tree_bytes(path),
                                           'path': str(path)})
            except (OSError, ValueError, KeyError, TypeError) as error:
                skipped.append({'camera_id': camera, 'release': path.name,
                                'reason': f'Invalid release retained: {error}'})
    receipt_candidates = [{'job_id': item['job_id'], 'camera_id': item['camera_id'],
                           'created_at': item['created_at'], 'bytes': item['bytes'], 'path': item['path']}
                          for item in receipts['removable']]
    candidates = release_candidates + receipt_candidates + staging_candidates
    return {'retention_days': days, 'cutoff_utc_epoch': cutoff,
            'candidate_count': len(candidates),
            'candidate_bytes': sum(item['bytes'] for item in candidates),
            'candidates': release_candidates, 'receipt_candidates': receipt_candidates,
            'staging_candidates': staging_candidates,
            'skipped': skipped}


def prune(source_root=SOURCE_ROOT, data_root=DATA_ROOT, *, now=None, days=30, apply=False):
    """Plan under exclusive processor/import/upload locks and optionally unlink candidates."""
    source = Path(source_root).resolve()
    data = Path(data_root).resolve(strict=True)
    handles = []
    try:
        handles.append(_lock(data / '.processing.lock', 'the processor'))
        handles.append(_lock(source / '.import.lock', 'an import or selection'))
        handles.append(_lock(source / '.upload.lock', 'an upload or preparation'))
        result = plan_prune(source, data, now=now, days=days)
        removed = []
        removed_receipts = []
        removed_staging = []
        if apply:
            for candidate in result['candidates']:
                path = Path(candidate['path'])
                parent = source / candidate['camera_id'] / 'releases'
                # Recheck identity/containment immediately before deletion.
                if (not RELEASE_ID.fullmatch(candidate['release'])
                        or path != parent / candidate['release']
                        or not _regular_directory(path, parent)):
                    raise RuntimeError('Release path changed during cleanup; stopping')
                shutil.rmtree(path)
                removed.append(candidate['release'])
            jobs = data / 'uploads' / 'jobs'
            for receipt in result['receipt_candidates']:
                path = Path(receipt['path'])
                if (path.parent != jobs or path.name != f"{receipt['job_id']}.json"
                        or path.is_symlink() or not path.is_file()
                        or not path.resolve().is_relative_to(data)):
                    raise RuntimeError('Upload receipt path changed during cleanup; stopping')
                path.unlink()
                removed_receipts.append(receipt['job_id'])
            for staging in result['staging_candidates']:
                path = Path(staging['path'])
                parent = (data / 'uploads' if staging['area'] == 'upload'
                          else source / staging['camera_id'])
                prefix = '.upload-' if staging['area'] == 'upload' else '.import-'
                if (path.parent != parent or not path.name.startswith(prefix)
                        or not _regular_directory(path, parent)):
                    raise RuntimeError('Staging path changed during cleanup; stopping')
                shutil.rmtree(path)
                removed_staging.append(path.name)
        result.update(applied=bool(apply), removed=removed, removed_receipts=removed_receipts,
                      removed_staging=removed_staging)
        return result
    finally:
        for handle in reversed(handles):
            _release_lock(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=SOURCE_ROOT)
    parser.add_argument('--data-root', type=Path, default=DATA_ROOT)
    parser.add_argument('--days', type=int, default=30, help='Minimum age to prune (30–365 days; default 30)')
    parser.add_argument('--apply', action='store_true', help='Delete eligible old, unselected releases')
    args = parser.parse_args(argv)
    try:
        result = prune(args.source_root, args.data_root, days=args.days, apply=args.apply)
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Source release cleanup failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    if not args.apply:
        print('Dry run only. Review the inventory; rerun with --apply to delete the listed releases.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
