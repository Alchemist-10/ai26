"""One streamed upload/preparation per source root; activation is always offline."""
import asyncio
import base64
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError, field_validator
from starlette.requests import ClientDisconnect

from cameras import CAMERAS_BY_ID
from import_source import atomic_json
from source_catalog import DATA_ROOT, SOURCE_ROOT, MAX_MANIFEST_BYTES, load_release
from source_status import release_summary, text, number

MAX_UPLOAD_BYTES = 128 * 1024**2
UPLOAD_TIMEOUT = 120
TERMINAL = {'ready', 'failed', 'cancelled'}
log = logging.getLogger(__name__)


class UploadMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filename: StrictStr = Field(min_length=1, max_length=200)
    bytes: StrictInt = Field(ge=1, le=MAX_UPLOAD_BYTES)
    reviewer: StrictStr = Field(min_length=1, max_length=100)
    reason: StrictStr = Field(min_length=1, max_length=1000)
    replace: StrictBool = False

    @field_validator('filename', 'reviewer', 'reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('Enter a nonblank value')
        return value.strip()


def parse_metadata(header):
    if not header or len(header) > 8192: raise ValueError('Upload metadata is missing or too large')
    try: return UploadMetadata.model_validate_json(base64.b64decode(header,validate=True).decode('utf-8')).model_dump()
    except (ValidationError, ValueError) as error: raise ValueError('Enter a filename, size within 128 MiB, reviewer, reason and explicit replacement choice') from error


class UploadBusy(ValueError): pass


class SourceUploads:
    def __init__(self, data_root=DATA_ROOT, source_root=SOURCE_ROOT):
        self.data = Path(data_root).resolve(); self.root = Path(source_root).resolve()
        self.lock = threading.RLock(); self.jobs = {}; self.active = None; self.closed = False
        self.owner = None; self.process = None; self.thread = None

    def reserve(self, camera, metadata):
        if camera not in CAMERAS_BY_ID: raise ValueError('Unknown camera')
        metadata = UploadMetadata.model_validate(metadata).model_dump()
        with self.lock:
            if self.closed: raise UploadBusy('Source preparation is shutting down')
            if self.active: raise UploadBusy('Another clip is uploading or being prepared; finish or cancel it first')
            folder = self.data/'uploads'
            if folder.resolve().is_relative_to(self.root) or not folder.resolve().is_relative_to(self.data):
                raise ValueError('Upload storage must stay within data storage and outside the source root')
            folder.mkdir(parents=True, exist_ok=True); self.root.mkdir(parents=True, exist_ok=True)
            owner=(self.root/'.upload.lock').open('a+')
            try: fcntl.flock(owner,fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                owner.close(); raise UploadBusy('Another API process owns source preparation') from error
            self.owner = owner
            try:
                if shutil.disk_usage(folder).free < MAX_UPLOAD_BYTES*3 + 16*1024**2:
                    raise ValueError('Insufficient free disk space for upload, preserved original and playback')
                stage=Path(tempfile.mkdtemp(prefix='.upload-',dir=folder)); job=uuid.uuid4().hex
                result={'job_id':job,'camera_id':camera,'filename':Path(metadata['filename']).name,
                        'status':'uploading','created_at':time.time(),'error':None,'release':None}
                self.jobs[job]=result;self.active={'id':job,'stage':stage,'metadata':metadata,'cancel':False}
                return job, stage/'input.media'
            except BaseException:
                self._unlock(); raise

    def _unlock(self):
        if self.owner:
            fcntl.flock(self.owner,fcntl.LOCK_UN);self.owner.close();self.owner=None

    def _finish(self, job, status, error=None, release=None):
        with self.lock:
            self.jobs[job].update(status=status,error=error,release=release)
            receipts=self.data/'uploads'/'jobs'
            try:
                receipts.mkdir(parents=True,exist_ok=True)
                atomic_json(receipts/f'{job}.json',self.jobs[job])
            except OSError: log.exception('Could not retain upload receipt %s',job)
            finally:
                if self.active and self.active['id']==job:
                    shutil.rmtree(self.active['stage'],ignore_errors=True);self.active=None;self._unlock()
            while len(self.jobs)>16: self.jobs.pop(next(iter(self.jobs)))

    async def reserve_async(self, camera, metadata):
        task=asyncio.create_task(asyncio.to_thread(self.reserve,camera,metadata))
        try: return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                job,_=await task
                self._finish(job,'cancelled')
            except (OSError,ValueError): pass
            raise

    @staticmethod
    async def _write(function, *args):
        # A cancelled request must wait for its disk operation before closing
        # the file and removing its private staging directory.
        task=asyncio.create_task(asyncio.to_thread(function,*args))
        try: return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def receive(self, request, job, path):
        try:
            count=0
            expected=self.active['metadata']['bytes']
            with path.open('xb') as stream:
                async with asyncio.timeout(UPLOAD_TIMEOUT):
                    async for chunk in request.stream():
                        count+=len(chunk)
                        with self.lock:
                            if not self.active or self.active['cancel']: raise ValueError('Upload cancelled')
                        if count>MAX_UPLOAD_BYTES or count>expected:
                            raise ValueError('Upload exceeds its declared size or the 128 MiB limit')
                        await self._write(stream.write,chunk)
                if count != expected: raise ValueError('Upload size does not match the selected file')
                await self._write(stream.flush); await self._write(os.fsync,stream.fileno())
            with self.lock:
                if self.closed or not self.active or self.active['cancel']: raise ValueError('Upload cancelled or preparation is shutting down')
                self.jobs[job]['status']='preparing'
                self.thread=threading.Thread(target=self._prepare,args=(job,path),name='ai26-source-preparation',daemon=True)
                self.thread.start()
            return self.get(job)
        except BaseException as error:
            message = 'Upload interrupted; choose the file and retry' if isinstance(error,(ClientDisconnect,asyncio.CancelledError)) else 'Upload timed out; choose the file and retry' if isinstance(error,TimeoutError) else str(error)
            self._finish(job,'failed',message)
            raise

    def _prepare(self, job, path):
        process=None
        try:
            with self.lock:
                meta=self.active['metadata']
                args=[sys.executable,str(Path(__file__).parent/'import_source.py'),self.jobs[job]['camera_id'],str(path),
                      '--prepare','--reviewer',meta['reviewer'],'--reason',meta['reason'],'--max-bytes',str(MAX_UPLOAD_BYTES),'--timeout','600']
                if meta['replace']: args.append('--replace')
                env=dict(os.environ,AI26_DATA_ROOT=str(self.data),AI26_SOURCE_ROOT=str(self.root),AI26_PROCESSING_ENABLED='0')
                self.process=subprocess.Popen(args,cwd=Path(__file__).parent,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
                process=self.process
                if self.active['cancel']: self._signal(process,signal.SIGTERM)
            output,errors=process.communicate(timeout=650)
            if process.returncode:
                log.warning('Preparation %s failed: %s',job,errors[-1500:])
                with self.lock: cancelled=self.active['cancel']
                self._finish(job,'cancelled' if cancelled else 'failed',None if cancelled else 'Video preparation failed. Use a readable clip and check FFmpeg/libx264 on the API host; existing footage is unchanged.')
            else:
                result=json.loads(output)
                binding=load_release(self.jobs[job]['camera_id'],result['release'],self.root,verify=True)
                self._finish(job,'ready',release=release_summary(binding['manifest']))
        except BaseException:
            log.exception('Preparation worker failed for %s',job)
            if process and process.poll() is None:
                self._stop(process)
            self._finish(job,'failed','Preparation could not finish; existing footage is unchanged. Check host logs before retrying.')
        finally:
            with self.lock:
                if self.process is process: self.process=None

    def get(self, job):
        if not re.fullmatch(r'[0-9a-f]{32}',job): raise KeyError('Unknown preparation')
        with self.lock:
            value=self.jobs.get(job)
            if value is None:
                path=self.data/'uploads/jobs'/f'{job}.json'
                if not path.resolve().is_relative_to(self.data): raise KeyError('Unknown preparation')
                try:
                    with path.open('rb') as stream: raw=stream.read(MAX_MANIFEST_BYTES+1)
                    if len(raw)>MAX_MANIFEST_BYTES: raise ValueError('Oversized receipt')
                    value=json.loads(raw)
                    if value['job_id']!=job or value['camera_id'] not in CAMERAS_BY_ID or value['status'] not in TERMINAL: raise ValueError('Invalid receipt')
                except (OSError,ValueError,KeyError,TypeError) as error: raise KeyError('Unknown preparation') from error
            # Never expose arbitrary receipt fields or host paths.
            result={key:value.get(key) for key in ('job_id','camera_id','status')}
            result.update(filename=Path(text(value.get('filename'),200) or 'Recorded video').name,
                          created_at=number(value.get('created_at')),error=text(value.get('error'),1000),release=None)
            if value.get('status')=='ready':
                try:
                    release=value['release']['release']
                    binding=load_release(value['camera_id'],release,self.root)
                    result['release']=release_summary(binding['manifest'])
                except (KeyError,TypeError,ValueError):
                    result.update(status='failed',error='Prepared release is missing or invalid. Check host files before retrying.')
            return result

    @staticmethod
    def _signal(process, sig):
        try: os.killpg(process.pid,sig)
        except ProcessLookupError: pass

    @classmethod
    def _stop(cls, process):
        cls._signal(process,signal.SIGTERM)
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls._signal(process,signal.SIGKILL)
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: log.error('Preparation process did not stop: %s',process.pid)

    def cancel(self, job):
        with self.lock:
            if not self.active or self.active['id']!=job: return self.get(job)
            self.active['cancel']=True
            if self.process and self.process.poll() is None: self._signal(self.process,signal.SIGTERM)
            return self.get(job)

    def close(self):
        with self.lock:
            self.closed=True
            if self.active: self.cancel(self.active['id'])
            thread=self.thread
        if thread: thread.join(timeout=15)
        if thread and thread.is_alive():
            with self.lock: process=self.process
            if process: self._stop(process)
            thread.join(timeout=5)
        with self.lock:
            if self.active and (not thread or not thread.is_alive()): self._finish(self.active['id'],'cancelled')


uploads=SourceUploads()
