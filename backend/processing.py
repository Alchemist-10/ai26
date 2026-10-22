"""One bounded round-robin inference owner per API process; viewers are consumers."""
import hashlib
import logging
import math
import os
import threading
import time
import uuid
from collections import deque
from pathlib import Path

import cv2
import cameras
from cameras import CAMERAS, camera_source
from events import add_events, derive_alerts, store
from artifacts import capture_read_images, storage_usage
from live_capture import LiveCapture, load_live_sources
from source_clock import source_capture_clock_fields, source_time_from_decoder

log = logging.getLogger(__name__)

def _branch_switch(name):
    value=os.environ.get(name,'1')
    if value not in ('0','1'):
        raise RuntimeError(f'{name} must be 0 or 1')
    return value=='1'

VEHICLE_DETECTION_ENABLED=_branch_switch('AI26_VEHICLE_DETECTION_ENABLED')
PLATE_RECOGNITION_ENABLED=_branch_switch('AI26_PLATE_RECOGNITION_ENABLED')

# Paired CAM-07–09 diagnostics matched decoded pixels. Forward grabs stayed
# faster through 220-frame gaps on CAM-07/09, while CAM-08 seeks won at 200/220.
# Bind the larger bound to the exact source bytes so a later replacement falls
# back to the conservative global limit until it is measured too.
SOURCE_FORWARD_DECODE_LIMITS = {
    ('CAM-07', '661be1e99aa302d161dfc9ccd1e83cfe7fe0811e40f6305ec97aa480b7a3b689'): 221,
    ('CAM-09', 'e30b35701c0962bd22b96acdf8096f1d440f5c21f10978d8e8bb858a4783f341'): 221,
}


def forward_decode_limit_for(camera_id, source_sha256, default_limit, override=False):
    """Use source-specific measured bounds only when no global override is set."""
    if override:
        return default_limit
    return SOURCE_FORWARD_DECODE_LIMITS.get((camera_id, source_sha256), default_limit)

def inference_branches():
    return {'vehicle_detection_enabled':VEHICLE_DETECTION_ENABLED,
            'plate_recognition_enabled':PLATE_RECOGNITION_ENABLED}

def model_version_for_detection(detection):
    metadata=detection.get('model_metadata')
    model_id=metadata.get('model_id') if isinstance(metadata,dict) else None
    if isinstance(model_id,str) and model_id:
        return model_id
    return 'yolov8n.pt' if detection.get('kind')=='vehicle' else 'fast-alpr:global-plates-mobile-vit-v2'

def recorded_video_geometry(camera_id, capture):
    """Prefer importer-verified decoded counts over stale container frame counts."""
    fps=capture.get(cv2.CAP_PROP_FPS)
    frames=capture.get(cv2.CAP_PROP_FRAME_COUNT)
    video=(cameras.MANAGED_SOURCES.get(camera_id,{}).get('manifest',{})
           .get('original',{}).get('video',{}))
    try:
        manifest_fps=float(video['fps'])
        manifest_frames=int(video['frame_count'])
        if (math.isfinite(manifest_fps) and manifest_fps>0 and manifest_frames>0
                and not isinstance(video['frame_count'],bool)):
            return manifest_fps,manifest_frames
    except (KeyError,TypeError,ValueError):
        pass
    return fps,frames

def validate_branch_configuration():
    from privacy import enabled as privacy_enabled
    if privacy_enabled() and not VEHICLE_DETECTION_ENABLED:
        raise RuntimeError('Privacy mode requires the vehicle/person detection branch for sampled person pixelation')


def annotate(frame, kind, camera_id):
    if kind == 'vehicle':
        if not VEHICLE_DETECTION_ENABLED: return frame, []
        from inference import annotate_vehicle_frame
        return annotate_vehicle_frame(frame, camera_id)
    if not VEHICLE_DETECTION_ENABLED and not PLATE_RECOGNITION_ENABLED: return frame, []
    raw = frame.copy()
    if VEHICLE_DETECTION_ENABLED:
        from inference import annotate_vehicle_frame, take_person_boxes
        frame, vehicles = annotate_vehicle_frame(frame, camera_id)
        people = take_person_boxes(camera_id)
    else:
        vehicles, people = [], []
    # OCR sees the raw frame, not vehicle annotation strokes.
    if PLATE_RECOGNITION_ENABLED:
        from inference import annotate_plate_frame
        plate_frame, plates = annotate_plate_frame(raw, camera_id)
    else:
        plate_frame, plates = frame, []
    if people:
        from privacy import enabled, pixelate_person_boxes
        if enabled(): pixelate_person_boxes(plate_frame, people)
    # Plate cameras prioritize plate overlays; observations retain both model outputs.
    return plate_frame, plates + vehicles


class Processor:
    def __init__(self, cameras=None, source=None, annotator=None, rate=None):
        self.cameras = cameras if cameras is not None else CAMERAS
        self.source = source or camera_source
        self.live_sources = load_live_sources(camera_ids=[c['id'] for c in self.cameras])
        self.live_captures = {}
        self.annotator = annotator or annotate
        self.rate = max(.1, min(10, rate or float(os.environ.get('AI26_TOTAL_INFERENCE_FPS', '2'))))
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.run_id = uuid.uuid4().hex
        self.started = time.time()
        self.started_monotonic = time.monotonic()
        self.captures = {}
        self.state = {c['id']: {'camera_id':c['id'], 'status':'idle', 'frames':0, 'last_frame_at':None,
                      'last_event_at':None, 'error':None, 'source_available':False, 'queue_depth':0,
                      'source_mode':'live' if c['id'] in self.live_sources else 'recorded',
                      'time_basis':'capture_arrival_clock' if c['id'] in self.live_sources else 'replay_clock',
                      'attempts':0,'failed_attempts':0,'budget_overruns':0,
                      'missing_source_checks':0,'retry_backoff_checks':0} for c in self.cameras}
        self.timing_windows = {c['id']:deque(maxlen=64) for c in self.cameras}
        self.first_timings = {}
        self.latest = {}
        self.thumbnails = {}
        self.epochs = {}
        self.retry_at = {}
        self.source_hashes = {}
        self.source_forward_decode_limits = {}
        self.capture_generation = {}
        self.live_reader_generation = {}
        self.last_traffic_sample_identity = {}
        self.decode_next = {}
        override = os.environ.get('AI26_FORWARD_DECODE_MAX_FRAMES')
        self.forward_decode_override = override is not None
        self.forward_decode_limit = max(0,min(128,int(override if override is not None else '128')))
        self.decode_threads = max(1,min(4,int(os.environ.get('AI26_RECORDED_DECODE_THREADS','2'))))
        self.owner_file = None

    def start(self):
        if self.thread and self.thread.is_alive(): return
        # Current deployment target is Linux. The advisory lock prevents a second API
        # process from writing duplicate observations into the same local data store.
        import fcntl
        lock_path = Path(store.path).parent / '.processing.lock'
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        owner = lock_path.open('a+')
        try: fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            owner.close()
            raise RuntimeError('Another processor owns this Sakshi data directory; use one API worker')
        self.owner_file = owner
        self.live_captures = {camera_id:LiveCapture(camera_id,url)
                              for camera_id,url in self.live_sources.items()}
        for live_capture in self.live_captures.values(): live_capture.start()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, name='ai26-inference-owner', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=30)
        for live_capture in self.live_captures.values(): live_capture.stop()
        if self.thread and self.thread.is_alive():
            log.error('Inference has not exited; do not start another owner in this process')
        else:
            with self.lock:
                for s in self.state.values(): s['status']='stopped'

    def health(self):
        now=time.time()
        elapsed=time.monotonic()-self.started_monotonic
        with self.lock:
            return [{**s, 'frame_age_seconds':round(now-s['last_frame_at'],2) if s['last_frame_at'] else None,
                     'processed_fps':round(s['frames']/max(elapsed,1),3),
                     'inference_owner':'single-process round-robin', 'sampling_budget_fps':self.rate,
                     'processor_run_id':self.run_id,
                     'forward_decode_max_frames':self.source_forward_decode_limits.get(
                         s['camera_id'],self.forward_decode_limit),
                     'recorded_decode_threads':self.decode_threads,
                     'timing':self.timing_summary(s['camera_id']),
                     'artifact_storage':storage_usage()}
                    for s in self.state.values()]

    def source_is_live(self, camera_id):
        return camera_id in self.live_sources

    def source_available(self, camera_id):
        if camera_id in self.live_captures:
            return self.live_captures[camera_id].latest()[0] is not None
        return Path(self.source(camera_id)).is_file()

    def timing_summary(self, camera):
        # At most 64 successful samples per camera; health never accumulates data.
        records=self.timing_windows[camera]
        def summary(values):
            ordered=sorted(values)
            return {'p50_ms':round(ordered[math.ceil(len(ordered)*.5)-1],3),
                    'p95_ms':round(ordered[math.ceil(len(ordered)*.95)-1],3),
                    'max_ms':round(ordered[-1],3)} if ordered else None
        return {'window_capacity':64,'successful_samples':len(records),
                'first_success':self.first_timings.get(camera),
                'total':summary([r['total_ms'] for r in records]),
                'phases':{phase:summary([r['phases_ms'][phase] for r in records])
                          for phase in ('source','decode','inference','artifacts','persistence','jpeg')},
                'scope':'Recent successful sampled attempts; first success is per camera, not an independently cold model run.'}

    def record_attempt(self, camera, began, phases, success):
        elapsed=(time.monotonic()-began)*1000
        record={'total_ms':round(elapsed,3),'phases_ms':{key:round(value,3) for key,value in phases.items()}}
        with self.lock:
            state=self.state[camera]
            state['attempts']+=1
            state['failed_attempts']+=not success
            state['budget_overruns']+=elapsed>1000/self.rate
            state['last_attempt']={**record,'succeeded':success}
            if success:
                self.first_timings.setdefault(camera,record)
                self.timing_windows[camera].append(record)

    def decode_frame(self, camera, cap, target):
        """Use bounded grabs only from a previously verified decoder position."""
        previous=self.decode_next.pop(camera,None)
        position=cap.get(cv2.CAP_PROP_POS_FRAMES)
        gap=target-previous if previous is not None else None
        limit=self.source_forward_decode_limits.get(camera,self.forward_decode_limit)
        forward=(limit>0 and gap is not None and 0<=gap<limit
                 and math.isfinite(position) and abs(position-previous)<.01)
        self._set(camera,decode_mode='forward' if forward else 'seek',decode_grabbed_frames=gap+1 if forward else 1,decode_position_verified=None)
        if forward:
            for _ in range(gap+1):
                if not cap.grab(): raise RuntimeError('Forward source frame could not be grabbed')
            ok,frame=cap.retrieve()
        else:
            if not cap.set(cv2.CAP_PROP_POS_FRAMES,target): raise RuntimeError('Source frame could not be sought')
            ok,frame=cap.read()
        if not ok or frame is None: raise RuntimeError('Source frame could not be decoded')
        position=cap.get(cv2.CAP_PROP_POS_FRAMES)
        verified=math.isfinite(position) and abs(position-(target+1))<.01
        if forward and not verified: raise RuntimeError('Forward decoded position could not be verified')
        if verified: self.decode_next[camera]=target+1
        self._set(camera,decode_position_verified=verified)
        return frame

    def jpeg(self, camera):
        with self.lock:
            value=self.latest.get(camera)
            # Failed or stopped producers must not serve a stale frame as current.
            if self.state.get(camera,{}).get('status') not in ('processing','loading'): return None
            if value and time.time()-value[0] > max(15, len(self.cameras)/self.rate*3): return None
            return value

    def preview(self, camera):
        with self.lock:
            return self.thumbnails.get(camera) if self.jpeg(camera) else None

    def _set(self, camera, **values):
        with self.lock: self.state[camera].update(values)

    def step(self, camera):
        camera_id=camera['id']; now=time.time()
        began_attempt=time.monotonic()
        if camera_id in self.live_captures:
            return self._step_live(camera, began_attempt)
        path=Path(self.source(camera_id))
        if not path.is_file():
            with self.lock:
                self.state[camera_id]['missing_source_checks']+=1
            self._set(camera_id,status='unavailable',source_available=False,error='Source file missing')
            self.latest.pop(camera_id,None)
            cap=self.captures.pop(camera_id,None)
            self.decode_next.pop(camera_id,None)
            if cap: cap.release()
            return False
        self._set(camera_id,source_available=True)
        if self.retry_at.get(camera_id,0)>now:
            with self.lock: self.state[camera_id]['retry_backoff_checks']+=1
            return False
        phases={};phase='source';phase_began=began_attempt;success=False
        def mark(next_phase):
            nonlocal phase,phase_began
            ended=time.monotonic();phases[phase]=(ended-phase_began)*1000
            phase=next_phase;phase_began=ended
        try:
            reopened = False
            if camera_id not in self.captures:
                self.decode_next.pop(camera_id,None)
                cap=cv2.VideoCapture(str(path),cv2.CAP_FFMPEG,
                                     [cv2.CAP_PROP_N_THREADS,self.decode_threads])
                if not cap.isOpened(): cap.release(); raise RuntimeError('Source could not be opened')
                self.captures[camera_id]=cap
                with path.open('rb') as source_file:
                    self.source_hashes[camera_id]=hashlib.file_digest(source_file,'sha256').hexdigest()
                self.source_forward_decode_limits[camera_id]=forward_decode_limit_for(
                    camera_id,self.source_hashes[camera_id],self.forward_decode_limit,
                    override=self.forward_decode_override)
                generation = self.capture_generation.get(camera_id, 0) + 1
                self.capture_generation[camera_id] = generation
                reopened = generation > 1
            cap=self.captures[camera_id]
            fps,frames=recorded_video_geometry(camera_id,cap)
            if not math.isfinite(fps) or fps<=0 or not math.isfinite(frames) or frames<=0: raise RuntimeError('Invalid source duration/frame rate')
            duration=frames/fps
            offset=(now-self.started)+int(camera_id.rsplit('-',1)[-1])*4.5
            epoch=int(offset//duration)
            position=offset % duration
            frame_id=min(int(position*fps),int(frames)-1)
            session=f'{self.run_id}:{camera_id}:{epoch}:capture-{self.capture_generation[camera_id]}'
            if self.epochs.get(camera_id)!=epoch or reopened:
                # Reset all local identities/fusion when replay crosses its source boundary.
                if camera_id in self.epochs or reopened:
                    from inference import reset_camera
                    reset_camera(camera_id)
                self.epochs[camera_id]=epoch
                store.start_session({'id':session,'camera_id':camera_id,'started_at':now,
                                     'source_sha256':self.source_hashes[camera_id], 'source_mode':'recorded',
                                     'time_basis':'replay_clock','loop_epoch':epoch,'run_id':self.run_id})
            mark('decode')
            raw=self.decode_frame(camera_id,cap,frame_id)
            source_time_seconds,source_time_basis=source_time_from_decoder(
                cap.get(cv2.CAP_PROP_POS_MSEC),frame_id,fps,duration)
            self._set(camera_id,status='loading',error=None)
            mark('inference')
            began=time.monotonic()
            frame,detections=self.annotator(raw.copy(),camera['kind'],camera_id)
            mark('artifacts')
            processing_time=time.time()
            height,width=raw.shape[:2]
            for detection in detections:
                detection.update(session_id=session,frame_id=frame_id,ts=now,source_time_seconds=source_time_seconds,
                                 source_time_basis=source_time_basis,
                                 processed_at=processing_time,source_mode='recorded',time_basis='replay_clock',
                                 source_sha256=self.source_hashes[camera_id],frame_size=[width,height],
                                 model_version=model_version_for_detection(detection))
                manifest=cameras.MANAGED_SOURCES.get(camera_id,{}).get('manifest',{})
                detection.update(source_capture_clock_fields(manifest.get('recording_clock'),source_time_seconds,source_time_basis))
            capture_began=time.monotonic()
            artifact_metrics=capture_read_images(raw,detections)
            artifact_ms=round((time.monotonic()-capture_began)*1000,1)
            mark('persistence')
            inserted=add_events(detections)
            if inserted: derive_alerts()
            mark('jpeg')
            ok,buf=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,80])
            if not ok: raise RuntimeError('Annotated image could not be encoded')
            preview=cv2.resize(frame,(320,max(1,round(height*320/width))),interpolation=cv2.INTER_AREA)
            preview_ok,preview_buf=cv2.imencode('.jpg',preview,[cv2.IMWRITE_JPEG_QUALITY,65])
            if not preview_ok: raise RuntimeError('Preview could not be encoded')
            with self.lock:
                self.latest[camera_id]=(processing_time,buf.tobytes())
                self.thumbnails[camera_id]=(processing_time,preview_buf.tobytes())
                s=self.state[camera_id]
                s.update(status='processing',error=None,last_frame_at=processing_time,
                         last_event_at=processing_time if detections else s['last_event_at'],
                         frames=s['frames']+1,latency_ms=round((time.monotonic()-began)*1000,1),
                         artifact_capture_ms=artifact_ms,artifact_capture=artifact_metrics,
                         session_id=session,frame_id=frame_id,source_time_seconds=source_time_seconds,
                         source_time_basis=source_time_basis)
            success=True
        except Exception as exc:
            log.exception('Camera %s processing failed',camera_id)
            self._set(camera_id,status='error',error=str(exc)[:200])
            self.retry_at[camera_id]=time.time()+10
            cap=self.captures.pop(camera_id,None)
            self.decode_next.pop(camera_id,None)
            if cap: cap.release()
        finally:
            phases[phase]=(time.monotonic()-phase_began)*1000
            self.record_attempt(camera_id,began_attempt,phases,success)
        return True

    def _step_live(self, camera, began_attempt):
        """Process a fresh frame from the bounded RTSP reader using arrival time."""
        camera_id = camera['id']; reader = self.live_captures[camera_id]
        sample, capture_status = reader.latest()
        if sample is None:
            self._set(camera_id, status='unavailable' if capture_status != 'connected' else 'stale',
                      source_available=False, source_mode='live', time_basis='capture_arrival_clock',
                      error='Live stream is connecting, unavailable, or stale')
            self.latest.pop(camera_id, None); self.thumbnails.pop(camera_id, None)
            return False
        captured_at, sequence, reader_generation, raw = sample
        self._set(camera_id, source_available=True, source_mode='live',
                  time_basis='capture_arrival_clock', status='loading', error=None,
                  capture_sequence=sequence, last_capture_at=captured_at)
        phases={}; phase='source'; phase_began=began_attempt; success=False
        def mark(next_phase):
            nonlocal phase,phase_began
            ended=time.monotonic(); phases[phase]=(ended-phase_began)*1000
            phase=next_phase; phase_began=ended
        try:
            frame_id = sequence
            session_generation=self.capture_generation.get(camera_id,0)
            new_connection=self.live_reader_generation.get(camera_id)!=reader_generation
            if new_connection:
                if camera_id in self.epochs:
                    from inference import reset_camera
                    reset_camera(camera_id)
                self.epochs[camera_id] = 'live'
                session_generation += 1
                self.capture_generation[camera_id] = session_generation
                self.live_reader_generation[camera_id]=reader_generation
                self.decode_next.pop(camera_id,None)
                session=f'{self.run_id}:{camera_id}:live:{session_generation}'
                store.start_session({'id':session,'camera_id':camera_id,'started_at':captured_at,
                                     'source_sha256':None,'source_mode':'live',
                                     'time_basis':'capture_arrival_clock','run_id':self.run_id})
            else:
                session=f'{self.run_id}:{camera_id}:live:{session_generation}'
            mark('inference')
            frame,detections=self.annotator(raw.copy(),camera['kind'],camera_id)
            mark('artifacts')
            processing_time=time.time(); height,width=raw.shape[:2]
            for detection in detections:
                detection.update(session_id=session,frame_id=frame_id,ts=captured_at,
                                 source_time_seconds=None,processed_at=processing_time,
                                 source_mode='live',time_basis='capture_arrival_clock',
                                 source_sha256=None,frame_size=[width,height],
                                 model_version=model_version_for_detection(detection))
            capture_began=time.monotonic(); artifact_metrics=capture_read_images(raw,detections)
            artifact_ms=round((time.monotonic()-capture_began)*1000,1)
            mark('persistence'); inserted=add_events(detections)
            if inserted: derive_alerts()
            mark('jpeg')
            ok,buf=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,80])
            if not ok: raise RuntimeError('Annotated image could not be encoded')
            preview=cv2.resize(frame,(320,max(1,round(height*320/width))),interpolation=cv2.INTER_AREA)
            preview_ok,preview_buf=cv2.imencode('.jpg',preview,[cv2.IMWRITE_JPEG_QUALITY,65])
            if not preview_ok: raise RuntimeError('Preview could not be encoded')
            sample_identity=(reader_generation,sequence)
            if self.last_traffic_sample_identity.get(camera_id)!=sample_identity:
                store.record_traffic_sample(camera_id,captured_at)
                self.last_traffic_sample_identity[camera_id]=sample_identity
            with self.lock:
                self.latest[camera_id]=(processing_time,buf.tobytes())
                self.thumbnails[camera_id]=(processing_time,preview_buf.tobytes())
                state=self.state[camera_id]
                state.update(status='processing',error=None,last_frame_at=processing_time,
                             last_event_at=processing_time if detections else state['last_event_at'],
                             frames=state['frames']+1,latency_ms=round((time.monotonic()-began_attempt)*1000,1),
                             artifact_capture_ms=artifact_ms,artifact_capture=artifact_metrics,
                             session_id=session,frame_id=frame_id,source_time_seconds=None,
                             capture_sequence=sequence)
            success=True
        except Exception as exc:
            log.exception('Live camera %s processing failed',camera_id)
            self._set(camera_id,status='error',error=str(exc)[:200])
        finally:
            phases[phase]=(time.monotonic()-phase_began)*1000
            self.record_attempt(camera_id,began_attempt,phases,success)
        return True

    def run(self):
        try:
            while not self.stop_event.is_set():
                if not self.cameras:
                    self.stop_event.wait(1)
                    continue
                attempted=False
                for camera in self.cameras:
                    if self.stop_event.is_set(): break
                    began=time.monotonic()
                    if self.step(camera):
                        attempted=True
                        self.stop_event.wait(max(0,1/self.rate-(time.monotonic()-began)))
                # Missing/backoff sources do not consume inference slots. An all-
                # unavailable sweep still sleeps, so discovery never busy-spins.
                if not attempted: self.stop_event.wait(1)
        finally:
            for cap in self.captures.values(): cap.release()
            self.captures.clear()
            self.decode_next.clear()
            if self.owner_file:
                self.owner_file.close()
                self.owner_file = None


processor=Processor()
