"""Offline recorded-source onboarding. No ML, SQL writes or live source switching."""
import argparse
from contextlib import contextmanager, nullcontext
import fcntl
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from fractions import Fraction

from cameras import CAMERAS_BY_ID, camera_source
from source_catalog import DATA_ROOT, SOURCE_ROOT, file_digest, load_source
from source_clock import normalize_recording_clock

DEFAULT_MAX_BYTES = 1024**3


def ffmpeg_version():
    result=subprocess.run(['ffmpeg','-version'],capture_output=True,text=True,timeout=10,check=True)
    return result.stdout.splitlines()[0]


def probe(path, count_frames=False, timeout=30):
    command=['ffprobe','-v','error','-select_streams','v:0']
    if count_frames: command.append('-count_frames')
    command.extend(['-show_streams','-show_format','-of','json',str(path)])
    result = subprocess.run(command,
                            capture_output=True, text=True, timeout=timeout, check=True)
    payload = json.loads(result.stdout)
    streams = payload.get('streams', [])
    if not streams: raise ValueError('Input has no video stream')
    video = streams[0]
    try:
        rate = float(Fraction(video['avg_frame_rate']))
        duration = float(video.get('duration') or payload['format']['duration'])
        width, height = int(video['width']), int(video['height'])
    except (KeyError, ValueError, ZeroDivisionError) as error:
        raise ValueError('Video duration/frame rate/dimensions are unavailable') from error
    if not math.isfinite(rate) or not 0 < rate <= 240 or not math.isfinite(duration) or not 0 < duration <= 86400 or not 2 <= width <= 16384 or not 2 <= height <= 16384:
        raise ValueError('Unsupported video duration/frame rate/dimensions')
    frame_value=video.get('nb_read_frames') if count_frames else video.get('nb_frames')
    return {'codec':video.get('codec_name'), 'pixel_format':video.get('pix_fmt'), 'width':width, 'height':height,
            'fps':rate, 'duration_seconds':duration, 'frame_count':int(frame_value) if str(frame_value or '').isdigit() else None}


def transcode(source, destination, timeout, max_bytes):
    # One decode/encode/filter thread; conversion runs outside the serving process.
    subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-threads','1','-i',str(source),
                    '-map','0:v:0','-an','-sn','-dn','-c:v','libx264','-threads','1','-filter_threads','1',
                    '-vf','scale=trunc(min(1280\\,iw)/2)*2:-2','-pix_fmt','yuv420p','-preset','fast','-crf','23',
                    '-fps_mode','passthrough','-movflags','+faststart','-fs',str(max_bytes),'-y',str(destination)],
                   capture_output=True, text=True, timeout=timeout, check=True)


class ImportBusy(ValueError): pass


@contextmanager
def exclusive(path, message):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as owner:
        try: fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error: raise ImportBusy(message) from error
        try: yield
        finally: fcntl.flock(owner, fcntl.LOCK_UN)


def atomic_json(path, value):
    handle, name = tempfile.mkstemp(prefix='.manifest-', dir=path.parent)
    try:
        with os.fdopen(handle,'w') as stream:
            json.dump(value,stream,sort_keys=True,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
        sync_directory(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def sync_directory(path):
    descriptor=os.open(path,os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def inspect_source(source, max_bytes):
    if type(max_bytes) is not int or max_bytes < 1: raise ValueError('Maximum file size must be positive')
    path = Path(source).resolve(strict=True)
    if not path.is_file() or not 0 < path.stat().st_size <= max_bytes: raise ValueError('Input must be a nonempty regular file within the size limit')
    return path, probe(path)


def import_source(camera, source, reviewer=None, reason=None, *, replace=False, check=False, prepare=False,
                  source_root=SOURCE_ROOT, data_root=DATA_ROOT, max_bytes=DEFAULT_MAX_BYTES, timeout=600,
                  recording_start_utc=None, clock_uncertainty_seconds=None):
    if camera not in CAMERAS_BY_ID: raise ValueError('Unknown camera; choose an existing catalog ID')
    if not check and (not isinstance(reviewer,str) or not 1 <= len(reviewer.strip()) <= 100 or not isinstance(reason,str) or not 1 <= len(reason.strip()) <= 1000):
        raise ValueError('Enter a reviewer name (1–100) and reason (1–1000), excluding surrounding spaces')
    if not math.isfinite(timeout) or not 0 < timeout <= 3600: raise ValueError('Conversion timeout must be between 0 and 3600 seconds')
    recording_clock = normalize_recording_clock(recording_start_utc, clock_uncertainty_seconds)
    source, metadata = inspect_source(source, max_bytes)
    if check:
        return {'check_only':True,'camera_id':camera,'bytes':source.stat().st_size,'sha256':file_digest(source),
                'video':metadata,'scope':'Probe/fingerprint only; full decode and playback conversion have not run'}
    root, data = Path(source_root).resolve(), Path(data_root).resolve()
    with (nullcontext() if prepare else exclusive(data/'.processing.lock','Stop the processor before importing into this data directory')), \
         exclusive(root/'.import.lock','Another source import is in progress'):
        existing = load_source(camera,root)
        if not replace and (existing or camera_source(camera).is_file()):
            raise ValueError('Camera already has a source; use --replace to explicitly select a new release')
        folder = root/camera; releases = folder/'releases'
        if not folder.resolve().is_relative_to(root) or not releases.resolve().is_relative_to(root):
            raise ValueError('Managed directories escape the source root')
        releases.mkdir(parents=True,exist_ok=True)
        if source.is_relative_to(root): raise ValueError('Import an external input, not a managed source release')
        if shutil.disk_usage(root).free < max_bytes*2 + 16*1024**2:
            raise ValueError('Insufficient free space for the configured two-file import allowance')
        staging = Path(tempfile.mkdtemp(prefix='.import-',dir=folder));published=None
        try:
            original = staging/'original.media';playback = staging/'playback.mp4'
            # Copy with a hard bound; a growing or replaced input cannot exceed the allowance.
            before=source.stat();copied=0
            with source.open('rb') as incoming, original.open('xb') as outgoing:
                while chunk := incoming.read(1024**2):
                    copied+=len(chunk)
                    if copied>max_bytes: raise ValueError('Input grew beyond the size limit while copying')
                    outgoing.write(chunk)
                outgoing.flush();os.fsync(outgoing.fileno())
            after=source.stat()
            if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or copied!=before.st_size:
                raise ValueError('Input changed during copying; retry with a stable file')
            # Validate the staged bytes actually used for conversion, not just the input path.
            # Container nb_frames can be stale. Compare frames actually decoded
            # from both files so valid inputs are not rejected for bad headers.
            original_video=probe(original,count_frames=True,timeout=timeout)
            tool_version=ffmpeg_version()
            print('Preparing and validating browser playback; existing selection is unchanged…' if prepare else 'Preparing and validating browser playback; inference remains stopped…',file=sys.stderr,flush=True)
            transcode(original,playback,timeout,max_bytes)
            if not playback.is_file() or not 0 < playback.stat().st_size < max_bytes: raise ValueError('Playback conversion hit its size limit or produced no video')
            playback_video=probe(playback,count_frames=True,timeout=timeout)
            if playback_video['codec']!='h264' or playback_video['pixel_format']!='yuv420p': raise ValueError('Playback is not browser-compatible H.264/yuv420p')
            if abs(playback_video['duration_seconds']-original_video['duration_seconds'])>max(.25,2/original_video['fps']):
                raise ValueError('Playback duration differs from the source; conversion may be truncated')
            if original_video['frame_count'] is not None and playback_video['frame_count']!=original_video['frame_count']:
                raise ValueError('Playback frame count differs from the source')
            release=uuid.uuid4().hex
            manifest={'version':1,'camera_id':camera,'release':release,'imported_at':time.time(),
                      'prepared_without_activation':prepare,
                      'reviewer':reviewer.strip(),'reason':reason.strip(),'time_basis':'replay_clock',
                      'scope':'Local operator import; content, location and original clocks unverified',
                      'conversion':{'recipe':'h264-preview-v1','ffmpeg_version':tool_version,
                                    'importer_sha256':file_digest(Path(__file__)), 'threads':1,'crf':23,'preset':'fast'},
                      'original':{'file':original.name,'bytes':original.stat().st_size,'sha256':file_digest(original),'video':original_video},
                      'playback':{'file':playback.name,'bytes':playback.stat().st_size,'sha256':file_digest(playback),'video':playback_video,
                                  'derivative':'Silent H.264/yuv420p, max 1280px width; original bytes unchanged'},
                      'previous_release':existing['manifest']['release'] if existing else None}
            if recording_clock is not None: manifest['recording_clock'] = recording_clock
            atomic_json(staging/'manifest.json',manifest)
            with playback.open('rb') as stream: os.fsync(stream.fileno())
            published=releases/release;staging.rename(published)
            sync_directory(releases)
            if not prepare: atomic_json(folder/'active.json',manifest)
            # Prior releases are deliberately retained; no implicit deletion/retention policy.
            return {**manifest,'restart_required':True,'activation_required':prepare}
        except BaseException:
            # An interrupted return after pointer publication must not delete the
            # now-active release. Failed publication before replace leaves old data.
            if published is not None:
                try: active=json.loads((folder/'active.json').read_text()).get('release')
                except (OSError,ValueError): active=None
                if active!=published.name: shutil.rmtree(published,ignore_errors=True)
            raise
        finally: shutil.rmtree(staging,ignore_errors=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('camera',choices=sorted(CAMERAS_BY_ID));parser.add_argument('file',type=Path)
    parser.add_argument('--reviewer');parser.add_argument('--reason')
    parser.add_argument('--replace',action='store_true');parser.add_argument('--check',action='store_true')
    parser.add_argument('--prepare',action='store_true',help='Prepare a retained release without changing active.json; processing may continue')
    parser.add_argument('--recording-start-utc',help='Operator-claimed original recording start, ISO-8601 with timezone')
    parser.add_argument('--clock-uncertainty-seconds',type=float,help='Operator estimate of recording-clock uncertainty (0–86400 seconds)')
    parser.add_argument('--max-bytes',type=int,default=DEFAULT_MAX_BYTES);parser.add_argument('--timeout',type=float,default=600)
    args=parser.parse_args(argv)
    try:
        result=import_source(args.camera,args.file,args.reviewer,args.reason,replace=args.replace,check=args.check,prepare=args.prepare,max_bytes=args.max_bytes,timeout=args.timeout,
                             recording_start_utc=args.recording_start_utc,clock_uncertainty_seconds=args.clock_uncertainty_seconds)
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        detail=error.stderr[-1500:] if isinstance(error,subprocess.CalledProcessError) and error.stderr else str(error)
        print(f'Import failed: {detail}',file=sys.stderr);return 1
    print(json.dumps(result,indent=2,allow_nan=False));return 0


if __name__=='__main__':
    def interrupted(signum, frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    sys.exit(main())
