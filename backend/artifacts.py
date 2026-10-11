"""Content-addressed raw-frame/crop artifacts with verification and age-based cleanup."""
import hashlib
import os
import re
import time
import tempfile
import threading
from pathlib import Path
import cv2

ROOT = Path(os.environ.get('AI26_DATA_ROOT', Path(__file__).parent / 'data')) / 'artifacts'
CAPTURE_POLICY = 'per-read-jpeg-v1'
_storage_lock = threading.RLock()
_storage_root = None
_storage_bytes = 0


class ArtifactCapacityError(OSError):
    pass


def _size(path):
    try: return path.stat().st_size
    except FileNotFoundError: return 0


def storage_usage():
    """Index once; maintenance reconciles external changes without scanning on every read."""
    global _storage_root,_storage_bytes
    with _storage_lock:
        if _storage_root!=ROOT:
            _storage_root=ROOT
            _storage_bytes=sum(_size(path) for path in ROOT.glob('*.jpg'))
        limit=int(os.environ.get('AI26_ARTIFACT_MAX_BYTES',str(2*1024**3)))
        if limit<1: raise ValueError('AI26_ARTIFACT_MAX_BYTES must be positive')
        return {'used_bytes':_storage_bytes,'limit_bytes':limit}


def save_image(frame, role):
    global _storage_bytes
    ok, data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok: raise ValueError('Artifact JPEG encoding failed')
    raw = data.tobytes()
    digest = hashlib.sha256(raw).hexdigest()
    with _storage_lock:
        usage=storage_usage()
        ROOT.mkdir(parents=True, exist_ok=True)
        path = ROOT / (digest + '.jpg')
        try:
            stored = path.read_bytes()
        except FileNotFoundError:
            stored = None
        if stored is not None:
            if stored != raw: raise ValueError('Stored artifact hash verification failed')
            os.utime(path, None)
        else:
            if usage['used_bytes']+len(raw)>usage['limit_bytes']:
                raise ArtifactCapacityError('Artifact storage budget exceeded; adjust capacity or wait for retention cleanup')
            # Unique temporary files also keep an interrupted/failed write out of downloads.
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=ROOT,delete=False) as output:
                    temporary=Path(output.name);output.write(raw)
                temporary.replace(path)
                _storage_bytes+=len(raw)
            finally:
                if temporary is not None: temporary.unlink(missing_ok=True)
    return {'sha256': digest, 'role': role, 'media_type': 'image/jpeg', 'size': len(raw), 'url': f'/api/artifacts/{digest}'}


def capture_read_images(frame, detections):
    """Attach this sampled frame to every read, encoding the shared frame just once.

    Image failures never borrow a prior track's picture or discard the raw read.
    The caller exposes the returned failure counts in processor health.
    """
    metrics={'image_attempts':0,'image_failures':0,'incomplete_reads':0,'storage_budget_failures':0}
    if not detections: return metrics
    height,width=frame.shape[:2]
    def save(image,role):
        metrics['image_attempts']+=1
        try:
            ref=save_image(image,role)
            if ref is None: raise ValueError('Artifact encoder returned no image')
            return ref,None
        except ArtifactCapacityError:
            metrics['image_failures']+=1;metrics['storage_budget_failures']+=1
            return None,'storage_budget_exceeded'
        except (OSError,ValueError,cv2.error):
            metrics['image_failures']+=1
            return None,'write_or_encode_failed'
    shared,frame_error=save(frame,'unannotated-frame-jpeg')
    crops={}
    for read in detections:
        context={key:read[key] for key in ('camera_id','session_id','frame_id','source_sha256','source_time_seconds')}
        refs=[{**shared,**context,'frame_size':[width,height]}] if shared else []
        x1,y1,x2,y2=read['bbox']
        box=[max(0,min(width,x1)),max(0,min(height,y1)),max(0,min(width,x2)),max(0,min(height,y2))]
        crop_status='outside_or_empty_box'
        crop_error=None
        if box[2]>box[0] and box[3]>box[1]:
            role='plate-crop' if read['kind']=='plate' else 'vehicle-crop'
            key=(role,*box)
            if key not in crops: crops[key]=save(frame[box[1]:box[3],box[0]:box[2]],role)
            crop,crop_error=crops[key]
            crop_status='stored' if crop else 'failed'
            if crop: refs.append({**crop,**context,'crop_bbox':box,'frame_size':[width,height]})
        complete=shared is not None and crop_status=='stored'
        read['artifacts']=refs
        read['artifact_capture']={'policy':CAPTURE_POLICY,'status':'complete' if complete else 'incomplete',
                                  'frame_status':'stored' if shared else 'failed','crop_status':crop_status,
                                  'crop_bbox':box,'jpeg_quality':92}
        if frame_error: read['artifact_capture']['frame_error']=frame_error
        if crop_error: read['artifact_capture']['crop_error']=crop_error
        if not complete: metrics['incomplete_reads']+=1
    return metrics


def summarize_read_images(reads):
    """Count exact read-context references, without upgrading historical best-shot data."""
    summary={'policy':CAPTURE_POLICY,'total_reads':len(reads),'reads_with_current_frame':0,
             'reads_with_current_crop':0,'reads_with_complete_current_images':0,
             'reads_without_complete_current_images':0,'legacy_or_manual_reads':0,
             'reads_with_capture_failures':0}
    for read in reads:
        capture=read.get('artifact_capture')
        if not isinstance(capture,dict) or capture.get('policy')!=CAPTURE_POLICY:
            summary['legacy_or_manual_reads']+=1
            continue
        if capture.get('frame_status')=='failed' or capture.get('crop_status')=='failed':
            summary['reads_with_capture_failures']+=1
        def matches(ref,role):
            return (isinstance(ref,dict) and ref.get('role')==role and
                    isinstance(ref.get('sha256'),str) and re.fullmatch(r'[a-f0-9]{64}',ref['sha256']) and
                    type(ref.get('size')) is int and ref['size']>0 and
                    all(read.get(key) is not None and ref.get(key)==read[key] for key in
                        ('camera_id','session_id','frame_id','source_sha256','source_time_seconds','frame_size')))
        refs=read.get('artifacts',[])
        if not isinstance(refs,list): refs=[]
        frame=any(matches(ref,'unannotated-frame-jpeg') for ref in refs)
        dimensions=read.get('frame_size');bbox=read.get('bbox');expected=None
        if (isinstance(dimensions,(list,tuple)) and len(dimensions)==2 and
            all(type(x) is int and x>0 for x in dimensions) and isinstance(bbox,(list,tuple)) and
            len(bbox)==4 and all(type(x) is int for x in bbox)):
            w,h=dimensions
            expected=[max(0,min(w,bbox[0])),max(0,min(h,bbox[1])),max(0,min(w,bbox[2])),max(0,min(h,bbox[3]))]
        role='plate-crop' if read.get('kind')=='plate' else 'vehicle-crop'
        crop=bool(expected and expected[2]>expected[0] and expected[3]>expected[1] and
                  any(matches(ref,role) and ref.get('crop_bbox')==expected for ref in refs))
        summary['reads_with_current_frame']+=bool(frame)
        summary['reads_with_current_crop']+=crop
        summary['reads_with_complete_current_images']+=bool(frame and crop)
    summary['reads_without_complete_current_images']=len(reads)-summary['reads_with_complete_current_images']
    return summary


def artifact_bytes(digest, protected_until=None):
    if not re.fullmatch(r'[a-f0-9]{64}', digest): return None
    path = ROOT / (digest + '.jpg')
    try:
        if not path.is_file(): return None
        now = time.time()
        if now-path.stat().st_mtime >= 7*86400 and (protected_until or 0) <= now: return None
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    if hashlib.sha256(data).hexdigest() != digest: raise ValueError('Artifact hash verification failed')
    return data


def cleanup_artifacts(cutoff, protected=frozenset()):
    global _storage_root,_storage_bytes
    with _storage_lock:
        retained=0
        for path in ROOT.glob('*.jpg'):
            try:
                if path.stem not in protected and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                else: retained+=path.stat().st_size
            except FileNotFoundError: pass
        _storage_root=ROOT;_storage_bytes=retained
