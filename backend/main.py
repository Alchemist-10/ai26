import asyncio
import hashlib
import html
import io
import json
import math
import os
import time
import zipfile
from contextlib import asynccontextmanager
from typing import Annotated
import hmac
import re
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from cameras import CAMERAS_BY_ID, camera_playback_source, camera_source
from events import derive_alerts, evidence_report, flows, get_events, get_trajectory, stats, store, traffic_baselines
from nlquery import answer as nl_answer
from processing import processor, inference_branches, validate_branch_configuration
from model_rollout import CONFIGURATION as vehicle_model_rollout, status as vehicle_model_rollout_status
from metrics import render_metrics
from schemas import QueryRequest, ReviewRequest, RuleConfig, CameraConfigurationUpdate, SourceSelectionRequest
from stream import mjpeg_generator, snapshot_frame
from plate_format import normalize_plate
from repository import canonical_json
from report_signing import EvidenceSigningError
from artifacts import artifact_bytes
from maintenance import Maintenance
from source_status import source_status
from onvif_discovery import discover_onvif
from onvif_profiles import inspect_onvif_profiles, OnvifInspectionError
from source_uploads import uploads, parse_metadata, UploadBusy
from starlette.requests import ClientDisconnect
from source_selection import select_for_restart, SelectionConflict
from import_source import ImportBusy
from auth import AuthService, AuthenticationError, auth_enabled, cookie_secure, SESSION_COOKIE, CSRF_HEADER
from auth import CASE_PATTERN, PURPOSES
from schemas import AuthLoginRequest, AuthUserCreateRequest, AuthUserUpdateRequest, AuthPasswordResetRequest, AuthPasswordChangeRequest, AuthPasswordRecoveryRequest, AuthMfaCodeRequest, AuthMfaDisableRequest, AuthMfaResetRequest, AuthCaseCameraScopeUpdate, CameraPairConstraintUpdate, OnvifDiscoveryRequest, OnvifProfileRequest
from privacy import enabled as privacy_enabled, redact_analytics_payload, status as privacy_status, validate_configuration
from auth_key_lock import api_lifetime_lock, verify_active_mfa_key, verify_active_privacy_key


@asynccontextmanager
async def lifespan(app):
    with api_lifetime_lock(store.path):
        verify_active_mfa_key(store.path)
        verify_active_privacy_key(store.path)
        validate_configuration()
        validate_branch_configuration()
        janitor = Maintenance(store)
        AuthService(store).ensure_bootstrap_admin()
        janitor.start()
        try:
            if os.environ.get('AI26_PROCESSING_ENABLED','1')=='1': processor.start()
            yield
        finally:
            await asyncio.to_thread(uploads.close)
            await asyncio.to_thread(processor.stop)
            await asyncio.to_thread(janitor.stop)

frontend_port=os.environ.get('AI26_FRONTEND_PORT','5174')
app=FastAPI(title='Sakshi observation API',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[f'http://localhost:{frontend_port}',f'http://127.0.0.1:{frontend_port}'],allow_methods=['*'],allow_headers=['*'])

SENSITIVE_PREFIXES=('/api/cameras','/api/camera-pair-constraints','/api/source-preparations/','/api/journey-links','/api/traffic/','/api/stream/','/api/video/',
                    '/api/snapshot/','/api/preview/','/api/events','/api/stats','/api/flows','/api/alerts',
                    '/api/rules','/api/nlquery','/api/trajectory/','/api/evidence/','/api/reports/','/api/artifacts/')


def required_role(method, path):
    if path == '/api/health': return 'admin'
    if path == '/api/metrics': return 'admin'
    if path in {'/api/auth/status','/api/auth/login','/api/auth/password-recovery'}: return None
    if path == '/api/auth/me/password': return 'authenticated'
    if path == '/api/auth/me' or path == '/api/auth/logout': return 'authenticated'
    if path == '/api/auth/mfa' or path.startswith('/api/auth/mfa/'): return 'authenticated'
    if path.startswith('/api/auth/users'): return 'admin'
    if path == '/api/cameras' and method == 'GET': return 'viewer'
    if path.startswith('/api/cameras/'):
        if '/source' in path: return 'operator'
        if path.endswith('/configuration'):
            return 'analyst' if method == 'GET' else 'operator'
    if path == '/api/camera-pair-constraints': return 'operator'
    if path.startswith('/api/source-preparations/'): return 'operator'
    if path == '/api/audit/integrity': return 'admin'
    if path.startswith('/api/traffic/') and method == 'GET': return 'analyst'
    if path.startswith('/api/alerts/') and path.endswith('/review'): return 'operator'
    if path == '/api/rules' and method == 'PUT': return 'admin'
    if path.startswith('/api/evidence/') and method == 'POST': return 'analyst'
    if path == '/api/nlquery' and method == 'POST': return 'analyst'
    if path.startswith(('/api/events','/api/stats','/api/flows','/api/alerts','/api/rules','/api/nlquery',
                        '/api/trajectory/','/api/journey-links','/api/reports/','/api/artifacts/','/api/stream/',
                        '/api/video/','/api/snapshot/','/api/preview/')) and method == 'GET': return 'analyst'
    return 'admin'


def valid_metrics_bearer(request):
    """Allow a dedicated, read-only scraper secret only on the metrics route."""
    if request.url.path != '/api/metrics':
        return False
    secret_file=os.environ.get('AI26_METRICS_TOKEN_FILE','').strip()
    authorization=request.headers.get('authorization','')
    scheme,separator,token=authorization.partition(' ')
    if not secret_file or not separator or scheme.lower()!='bearer':
        return False
    try:
        expected=Path(secret_file).read_text(encoding='utf-8').strip()
    except OSError:
        return False
    if len(expected)<32 or not token:
        return False
    return hmac.compare_digest(token,expected)


@app.middleware('http')
async def authentication_and_case_scope(request, call_next):
    if not request.url.path.startswith('/api/') or request.method == 'OPTIONS' or not auth_enabled():
        return await call_next(request)
    path=request.url.path
    if path in {'/api/auth/status','/api/auth/login','/api/auth/password-recovery','/api/privacy/status'}:
        return await call_next(request)
    if valid_metrics_bearer(request):
        return await call_next(request)
    service=AuthService(store)
    session=service.session(request.cookies.get(SESSION_COOKIE))
    if not session:
        return JSONResponse(status_code=401,content={'error':{'code':401,'message':'Sign in to access Sakshi'}})
    role=required_role(request.method,path)
    allowed={'authenticated':{'admin','operator','analyst','viewer'},
             'admin':{'admin'},'operator':{'admin','operator'},
             'analyst':{'admin','operator','analyst'},'viewer':{'admin','operator','analyst','viewer'}}
    if role not in allowed or session['role'] not in allowed[role]:
        return JSONResponse(status_code=403,content={'error':{'code':403,'message':'Your role cannot perform this action'}})
    if request.method in {'POST','PUT','PATCH','DELETE'}:
        csrf=request.headers.get(CSRF_HEADER,'')
        if not csrf or not hmac.compare_digest(csrf,session['csrf_token']):
            return JSONResponse(status_code=403,content={'error':{'code':403,'message':'Refresh the session before changing data'}})
    request.state.actor=session
    if any(path.startswith(prefix) for prefix in SENSITIVE_PREFIXES):
        case_id=request.headers.get('x-ai26-case-id') or request.query_params.get('case_id','')
        purpose=request.headers.get('x-ai26-purpose') or request.query_params.get('purpose','')
        if not CASE_PATTERN.fullmatch(case_id):
            return JSONResponse(status_code=422,content={'error':{'code':422,'message':'A valid case ID is required for sensitive access'}})
        if purpose not in PURPOSES:
            return JSONResponse(status_code=422,content={'error':{'code':422,'message':'Choose a recognized purpose for sensitive access'}})
        if not service.can_access_case(session['username'], case_id, session['role']):
            return JSONResponse(status_code=403,content={'error':{'code':403,'message':'Your account is not assigned to this case'}})
        request.state.case_id=case_id
        request.state.purpose=purpose
        camera_ids=None if session['role']=='admin' else store.case_camera_ids(case_id)
        request.state.camera_ids=camera_ids
        if camera_ids is not None:
            camera_route=next((prefix for prefix in ('/api/cameras/','/api/stream/','/api/video/','/api/snapshot/','/api/preview/')
                               if path.startswith(prefix)),None)
            if camera_route:
                camera_id=path[len(camera_route):].split('/',1)[0]
                if camera_id != 'onvif' and camera_id not in camera_ids:
                    return JSONResponse(status_code=403,content={'error':{'code':403,'message':'This case is not assigned to the requested camera'}})
        service.audit_sensitive_access(session,case_id,purpose,request.method,path)
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_error(request,exc):
    return JSONResponse(status_code=exc.status_code,content={'error':{'code':exc.status_code,'message':str(exc.detail)}})

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    return JSONResponse(status_code=422,content={'error':{'code':422,'message':'; '.join(f'{".".join(map(str,e["loc"]))}: {e["msg"]}' for e in exc.errors())}})

TimeFilter=Annotated[float|None,Query(ge=0,allow_inf_nan=False)]


@app.get('/api/auth/status')
def auth_status():
    return {'enabled':auth_enabled()}


@app.get('/api/privacy/status')
def get_privacy_status():
    return privacy_status()


@app.post('/api/auth/login')
def auth_login(body:AuthLoginRequest,request:Request,response:Response):
    if not auth_enabled(): raise HTTPException(404,'Authentication is disabled')
    # The bundled reverse proxy overwrites X-Real-IP; when calling the API directly,
    # fall back to the ASGI peer address.
    address=request.headers.get('x-real-ip') or (request.client.host if request.client else 'unknown')
    try: result,reason=AuthService(store).login(body.username,body.password,address,mfa_code=body.mfa_code)
    except AuthenticationError: result,reason=None,'invalid'
    except RuntimeError as exc: raise HTTPException(503,'MFA cannot be verified; contact an administrator') from exc
    if reason=='limited': raise HTTPException(429,'Too many sign-in attempts; try again in 15 minutes')
    if reason=='mfa_required': raise HTTPException(401,'MFA_CODE_REQUIRED')
    if reason=='mfa_invalid': raise HTTPException(401,'Authenticator or recovery code is invalid')
    if not result: raise HTTPException(401,'Username or password is incorrect')
    response.set_cookie(SESSION_COOKIE,result['token'],max_age=int(result['expires_at']-time.time()),
                        httponly=True,secure=cookie_secure(),samesite='strict',path='/api')
    return {'user':result['user'],'case_ids':AuthService(store).case_ids(result['user']['username']),
            'csrf_token':result['csrf_token'],'expires_at':result['expires_at']}


@app.post('/api/auth/password-recovery')
def auth_password_recovery(body:AuthPasswordRecoveryRequest, request:Request):
    if not auth_enabled(): raise HTTPException(404,'Authentication is disabled')
    address=request.headers.get('x-real-ip') or (request.client.host if request.client else 'unknown')
    try:
        result=AuthService(store).recover_password(body.username,body.new_password,body.code,address)
    except RuntimeError as exc:
        raise HTTPException(503,'Password recovery is unavailable; contact an administrator') from exc
    if result=='limited': raise HTTPException(429,'Too many recovery attempts; try again in 15 minutes')
    # Identical response for unknown, disabled, non-MFA and successful accounts.
    return {'recovery_requested':True}


@app.get('/api/auth/me')
def auth_me(request:Request):
    actor=request.state.actor
    return {'user':{'username':actor['username'],'role':actor['role']},
            'case_ids':AuthService(store).case_ids(actor['username']),
            'csrf_token':actor['csrf_token'],'expires_at':actor['expires_at']}


@app.post('/api/auth/me/password')
def auth_change_password(body:AuthPasswordChangeRequest,request:Request):
    try:
        AuthService(store).change_password(request.state.actor['username'],body.current_password,body.new_password)
    except AuthenticationError as exc:
        raise HTTPException(422,str(exc)) from exc
    return {'password_changed':True,'sessions_revoked':True}


@app.post('/api/auth/logout')
def auth_logout(request:Request,response:Response):
    AuthService(store).logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE,path='/api',secure=cookie_secure(),httponly=True,samesite='strict')
    return {'signed_out':True}


@app.get('/api/auth/users')
def auth_users():
    return AuthService(store).users()


@app.post('/api/auth/users',status_code=201)
def auth_create_user(body:AuthUserCreateRequest):
    try: return AuthService(store).create_user(body.username,body.password,body.role,case_ids=body.case_ids)
    except AuthenticationError as exc: raise HTTPException(422,str(exc)) from exc
    except sqlite3.IntegrityError as exc: raise HTTPException(409,'Username already exists') from exc


@app.patch('/api/auth/users/{username}')
def auth_update_user(username:str,body:AuthUserUpdateRequest):
    try: result=AuthService(store).update_user(username,body.role,body.disabled,case_ids=body.case_ids)
    except AuthenticationError as exc: raise HTTPException(409,str(exc)) from exc
    if not result: raise HTTPException(404,'Unknown user')
    return result


@app.post('/api/auth/users/{username}/password')
def auth_reset_password(username:str,body:AuthPasswordResetRequest):
    try: changed=AuthService(store).reset_password(username,body.password,body.reason)
    except AuthenticationError as exc: raise HTTPException(422,str(exc)) from exc
    if not changed: raise HTTPException(404,'Unknown user')
    return {'password_reset':True,'sessions_revoked':True}


@app.get('/api/auth/mfa')
def auth_mfa_status(request:Request):
    if not auth_enabled(): raise HTTPException(404,'Authentication is disabled')
    service=AuthService(store)
    return {**service.mfa_status(request.state.actor['username']),'supported':service.key_configured()}


@app.post('/api/auth/mfa/setup')
def auth_mfa_setup(request:Request):
    if not auth_enabled(): raise HTTPException(404,'Authentication is disabled')
    try: return AuthService(store).begin_mfa(request.state.actor['username'])
    except AuthenticationError as exc: raise HTTPException(409,str(exc)) from exc
    except RuntimeError as exc: raise HTTPException(503,str(exc)) from exc


@app.post('/api/auth/mfa/enable')
def auth_mfa_enable(request:Request,body:AuthMfaCodeRequest):
    if not auth_enabled(): raise HTTPException(404,'Authentication is disabled')
    try:
        codes=AuthService(store).confirm_mfa(request.state.actor['username'],body.code,request.state.actor['token_hash'])
    except AuthenticationError as exc: raise HTTPException(422,str(exc)) from exc
    except RuntimeError as exc: raise HTTPException(503,str(exc)) from exc
    return {'enabled':True,'recovery_codes':codes}


@app.post('/api/auth/mfa/disable')
def auth_mfa_disable(request:Request,body:AuthMfaDisableRequest):
    if not auth_enabled(): raise HTTPException(404,'Authentication is disabled')
    try:
        AuthService(store).disable_mfa(request.state.actor['username'],body.password,body.code,request.state.actor['token_hash'])
    except AuthenticationError as exc: raise HTTPException(422,str(exc)) from exc
    except RuntimeError as exc: raise HTTPException(503,str(exc)) from exc
    return {'enabled':False,'sessions_revoked':True}


@app.post('/api/auth/users/{username}/mfa/reset')
def auth_reset_mfa(username:str,body:AuthMfaResetRequest,request:Request):
    if not auth_enabled(): raise HTTPException(404,'Authentication is disabled')
    if request.state.actor['role'] != 'admin': raise HTTPException(403,'Administrator access is required')
    try: changed=AuthService(store).reset_mfa(username,body.reason)
    except AuthenticationError as exc: raise HTTPException(422,str(exc)) from exc
    if not changed: raise HTTPException(404,'Unknown user')
    return {'mfa_reset':True,'sessions_revoked':True}


def check_camera(camera_id):
    if camera_id not in CAMERAS_BY_ID: raise HTTPException(404,'Unknown camera')


def check_plate(plate):
    normalized=normalize_plate(plate)
    if not normalized['format_valid']: raise HTTPException(422,'Enter a valid Indian registration plate')
    return str(normalized['plate_norm'])


def interval(since,until):
    if since is not None and until is not None and since>until: raise HTTPException(422,'since must not be after until')


@app.get('/api/cameras')
def list_cameras(request:Request):
    processing_enabled=os.environ.get('AI26_PROCESSING_ENABLED','1')=='1'
    health={s['camera_id']:{**s,'processing_enabled':processing_enabled,
                            'inference_branches':inference_branches()} for s in processor.health()}
    camera_ids=getattr(request.state,'camera_ids',None)
    return [{**c,'source_mode':'live' if processor.source_is_live(c['id']) else 'recorded',
             'source_available':processor.source_available(c['id']),
             'health':health[c['id']]} for c in store.camera_catalog()
            if camera_ids is None or c['id'] in camera_ids]

@app.get('/api/auth/case-camera-scopes')
def list_case_camera_scopes():
    cameras=[{'id':camera['id'],'name':camera.get('name',camera['id'])} for camera in store.camera_catalog()]
    return {'cameras':cameras,'scopes':store.case_camera_scopes()}

@app.put('/api/auth/case-camera-scopes')
def update_case_camera_scope(body:AuthCaseCameraScopeUpdate,request:Request):
    known={camera['id'] for camera in store.camera_catalog()}
    if any(camera_id not in known for camera_id in body.camera_ids):
        raise HTTPException(422,'Camera scope contains an unknown camera ID')
    actor=getattr(request.state,'actor',None)
    result=store.update_case_camera_scope(body.case_id,body.camera_ids,actor['username'],time.time())
    return result

@app.post('/api/cameras/onvif/discover')
def onvif_discovery(body:OnvifDiscoveryRequest):
    try:
        return discover_onvif(body.timeout_seconds)
    except OSError as exc:
        raise HTTPException(503,'Local ONVIF discovery is unavailable on this host') from exc

@app.post('/api/cameras/onvif/profiles')
def onvif_profiles(body:OnvifProfileRequest):
    try:
        return inspect_onvif_profiles(body.source_address, body.service_address, body.username,
                                      body.password, body.timeout_seconds)
    except OnvifInspectionError as exc:
        raise HTTPException(422, str(exc)) from exc

@app.get('/api/cameras/{camera_id}/configuration')
def camera_configuration(camera_id:str, revision:Annotated[int|None,Query(ge=1)]=None):
    check_camera(camera_id)
    config=store.camera_configuration(camera_id,revision)
    if config is None: raise HTTPException(404,'Camera configuration revision unavailable')
    return config

@app.get('/api/cameras/{camera_id}/source')
def camera_source_status(camera_id:str):
    check_camera(camera_id)
    return {**source_status(camera_id),
            'configured_source_mode':'live' if processor.source_is_live(camera_id) else 'recorded',
            'source_available':processor.source_available(camera_id)}

@app.post('/api/cameras/{camera_id}/source/prepare',status_code=202)
async def prepare_camera_source(camera_id:str,request:Request):
    check_camera(camera_id)
    if request.headers.get('content-type','').split(';')[0]!='application/octet-stream': raise HTTPException(415,'Send a raw video file')
    try:
        metadata=parse_metadata(request.headers.get('x-ai26-upload'))
        if request.headers.get('content-length') and int(request.headers['content-length'])!=metadata['bytes']: raise ValueError('Upload size header does not match the file')
        actor=getattr(request.state,'actor',None)
        job,path=await uploads.reserve_async(camera_id,metadata,authenticated_uploader=actor['username'] if actor else None)
    except UploadBusy as error: raise HTTPException(409,str(error)) from error
    except (ValueError,OSError) as error: raise HTTPException(422,str(error)) from error
    try: return await uploads.receive(request,job,path)
    except ClientDisconnect as error: raise HTTPException(400,'Upload interrupted') from error
    except TimeoutError as error: raise HTTPException(408,'Upload timed out') from error
    except (ValueError,OSError) as error: raise HTTPException(422,str(error)) from error

def get_source_preparation_for_request(job_id:str,request:Request):
    try: result=uploads.get(job_id)
    except KeyError as error: raise HTTPException(404,'Preparation unavailable') from error
    actor=getattr(request.state,'actor',None)
    camera_ids=getattr(request.state,'camera_ids',None)
    if actor and actor['role']!='admin' and (camera_ids is None or result.get('camera_id') not in camera_ids):
        # Opaque job IDs do not grant access to preparations from another case.
        raise HTTPException(404,'Preparation unavailable')
    return result

@app.get('/api/source-preparations/{job_id}')
def source_preparation(job_id:str,request:Request):
    return get_source_preparation_for_request(job_id,request)

@app.post('/api/cameras/{camera_id}/source/selection')
def select_camera_source(camera_id:str,body:SourceSelectionRequest,request:Request):
    check_camera(camera_id)
    actor=getattr(request.state,'actor',None)
    selection=body.model_dump()
    if actor:
        # The authenticated account is server supplied; a client cannot claim
        # another account through the reviewer field.
        selection['reviewer']=actor['username']
    try: result=select_for_restart(camera_id,selection,authenticated_user=actor['username'] if actor else None)
    except (SelectionConflict,ImportBusy) as error: raise HTTPException(409,str(error)) from error
    except (ValueError,OSError) as error:
        raise HTTPException(422,'Imported files or selection records could not be verified or written. Running footage is unchanged; check host files before retrying.') from error
    return {**result,'source':source_status(camera_id)}

@app.post('/api/source-preparations/{job_id}/cancel')
def cancel_source_preparation(job_id:str,request:Request):
    get_source_preparation_for_request(job_id,request)
    try: return uploads.cancel(job_id)
    except KeyError as error: raise HTTPException(404,'Preparation unavailable') from error

@app.put('/api/cameras/{camera_id}/configuration')
def update_camera_configuration(camera_id:str, body:CameraConfigurationUpdate):
    check_camera(camera_id)
    try: return store.update_camera(camera_id,body.model_dump(),time.time())
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc

@app.get('/api/camera-pair-constraints')
def list_camera_pair_constraints(request:Request):
    camera_ids=getattr(request.state,'camera_ids',None)
    rows=store.camera_pair_constraints()
    return rows if camera_ids is None else [row for row in rows if row['from_camera'] in camera_ids and row['to_camera'] in camera_ids]

@app.put('/api/camera-pair-constraints')
def update_camera_pair_constraint(body:CameraPairConstraintUpdate,request:Request):
    camera_ids=getattr(request.state,'camera_ids',None)
    if camera_ids is not None and (body.from_camera_id not in camera_ids or body.to_camera_id not in camera_ids):
        raise HTTPException(403,'Both cameras must be assigned to this case')
    try: return store.put_camera_pair_constraint(body.model_dump(),time.time())
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc

@app.get('/api/journey-links')
def journey_links(request:Request,plate:str|None=None,since:TimeFilter=None,until:TimeFilter=None,
                  limit:Annotated[int,Query(ge=1,le=5000)]=5000):
    interval(since,until)
    if plate: plate=check_plate(plate)
    return redact_analytics_payload(store.journey_links(plate,0 if since is None else since,until,limit,
                                                          camera_ids=getattr(request.state,'camera_ids',None)))

@app.get('/api/audit/integrity')
def audit_integrity():
    return store.verify_audit_chain()

@app.get('/healthz')
def healthz():
    """Minimal liveness response for local/container health checks."""
    return {'status':'ok'}

@app.get('/api/health')
def health():
    cameras=processor.health()
    for camera in cameras:
        camera['source_available']=processor.source_available(camera['camera_id'])
    return {'processing_enabled':os.environ.get('AI26_PROCESSING_ENABLED','1')=='1','cameras':cameras,
            'inference_branches':inference_branches(),
            'vehicle_model_rollout':vehicle_model_rollout_status(vehicle_model_rollout),
            'database_schema':store.schema_version,'scope':'single API process; run uvicorn with one worker'}

@app.get('/api/metrics')
def prometheus_metrics():
    cameras=processor.health()
    for camera in cameras:
        camera['source_available']=processor.source_available(camera['camera_id'])
    body=render_metrics(cameras,os.environ.get('AI26_PROCESSING_ENABLED','1')=='1',inference_branches())
    return Response(body,media_type='text/plain; version=0.0.4; charset=utf-8')

@app.get('/api/stream/{camera_id}')
async def stream(request:Request,camera_id:str,start:float|None=None,anchor:float|None=None):
    check_camera(camera_id)
    if not processor.source_is_live(camera_id) and not camera_source(camera_id).is_file(): raise HTTPException(404,'Camera source is unavailable')
    return StreamingResponse(mjpeg_generator(camera_id,request=request),media_type='multipart/x-mixed-replace; boundary=frame')

@app.get('/api/video/{camera_id}')
def video(camera_id:str):
    if privacy_enabled(): raise HTTPException(403,'Raw recorded playback is disabled while privacy mode is enabled')
    check_camera(camera_id)
    if processor.source_is_live(camera_id): raise HTTPException(404,'Recorded playback is unavailable for a live source')
    path=camera_playback_source(camera_id)
    if not path.is_file(): raise HTTPException(404,'Camera source is unavailable')
    return FileResponse(path,media_type='video/mp4')

@app.get('/api/snapshot/{camera_id}')
def snapshot(camera_id:str):
    check_camera(camera_id)
    if not processor.source_available(camera_id): raise HTTPException(404,'Camera source is unavailable')
    jpeg=snapshot_frame(camera_id)
    if not jpeg: raise HTTPException(503,'No current processed frame; check camera health')
    return Response(content=jpeg,media_type='image/jpeg')

@app.get('/api/preview/{camera_id}')
def preview(camera_id:str,request:Request):
    check_camera(camera_id)
    if not processor.source_available(camera_id): raise HTTPException(404,'Camera source is unavailable')
    latest=processor.preview(camera_id)
    if not latest: raise HTTPException(503,'Preview is not ready; check camera health')
    etag='"'+hashlib.sha256(latest[1]).hexdigest()+'"'
    headers={'ETag':etag,'Cache-Control':'private, no-cache','X-Frame-Time':str(latest[0])}
    if request.headers.get('if-none-match')==etag: return Response(status_code=304,headers=headers)
    return Response(content=latest[1],media_type='image/jpeg',headers=headers)

@app.get('/api/events')
def events(request:Request,camera:str|None=None,plate:str|None=None,since:TimeFilter=None,until:TimeFilter=None,limit:Annotated[int,Query(ge=1,le=5000)]=5000):
    interval(since,until)
    if camera: check_camera(camera)
    if plate: plate=check_plate(plate)
    camera_ids=getattr(request.state,'camera_ids',None)
    if camera_ids is not None and camera is not None and camera not in camera_ids:
        raise HTTPException(403,'This case is not assigned to the requested camera')
    return redact_analytics_payload(get_events(camera,plate,since,until,limit=limit,camera_ids=camera_ids))

@app.get('/api/stats')
def get_stats(request:Request,since:TimeFilter=None,until:TimeFilter=None):
    interval(since,until); return stats(since,until,camera_ids=getattr(request.state,'camera_ids',None))

@app.get('/api/flows')
def get_flows(request:Request,since:TimeFilter=None,until:TimeFilter=None):
    interval(since,until); return flows(since,until,camera_ids=getattr(request.state,'camera_ids',None))

@app.get('/api/traffic/baselines')
def get_traffic_baselines(request:Request,days:Annotated[int,Query(ge=7,le=90)]=28):
    try: return traffic_baselines(days,camera_ids=getattr(request.state,'camera_ids',None))
    except (ValueError,KeyError) as exc: raise HTTPException(422,'Traffic baseline configuration or timezone is invalid') from exc

@app.get('/api/alerts')
def alerts(request:Request,since:TimeFilter=None,until:TimeFilter=None,include_escalated:bool=False):
    interval(since,until)
    camera_ids=getattr(request.state,'camera_ids',None)
    recent=derive_alerts(since,until,camera_ids=camera_ids)
    actor=getattr(request.state,'actor',None)
    scope_case_id=request.state.case_id if actor and actor['role']!='admin' else None
    if scope_case_id is not None:
        recent=[alert for alert in recent if alert.get('state')!='escalated' or alert.get('case_id')==scope_case_id]
    if not include_escalated: return redact_analytics_payload(recent)
    known={a['alert_id'] for a in recent}
    scoped_escalations=store.escalated_alerts(scope_case_id=scope_case_id)
    if camera_ids is not None: scoped_escalations=[a for a in scoped_escalations if a.get('camera_id') in camera_ids]
    return redact_analytics_payload(recent+[a for a in scoped_escalations if a['alert_id'] not in known])

@app.get('/api/alerts/escalations')
def escalations(request:Request,limit:Annotated[int,Query(ge=1,le=100)]=50,
                before_ts:Annotated[float|None,Query()]=None,
                before_id:Annotated[str|None,Query(min_length=1,max_length=200)]=None):
    if (before_ts is None) != (before_id is None) or (before_ts is not None and not math.isfinite(before_ts)):
        raise HTTPException(422,'Both finite before_ts and before_id are required for an escalation cursor')
    actor=getattr(request.state,'actor',None)
    scope_case_id=(request.state.case_id if actor and actor['role']!='admin' else None)
    camera_ids=getattr(request.state,'camera_ids',None)
    page=store.escalated_alerts_page(limit,(before_ts,before_id) if before_ts is not None else None,scope_case_id,camera_ids)
    return redact_analytics_payload(page)

@app.post('/api/alerts/{alert_id}/review')
def review(alert_id:str,body:ReviewRequest,request:Request):
    actor=getattr(request.state,'actor',None)
    if actor:
        reviewer=actor['username']
        if actor['role']!='admin':
            alert=store.alert(alert_id)
            camera_ids=getattr(request.state,'camera_ids',None)
            # Legacy alerts without a camera cannot be safely assigned to a case.
            if alert is None or camera_ids is None or alert.get('camera_id') not in camera_ids:
                raise HTTPException(404,'Unknown alert')
    elif body.reviewer and body.reviewer.strip():
        reviewer=body.reviewer.strip()
    else:
        raise HTTPException(422,'Reviewer name is required in local mode')
    data={**body.model_dump(),'reviewer':reviewer,'reviewer_authenticated':bool(actor),'ts':time.time()}
    if actor:
        data['case_id']=request.state.case_id
    if not store.review_alert(alert_id,data,
                              expected_case_id=request.state.case_id if actor else None,
                              administrator=bool(actor and actor['role']=='admin')):
        raise HTTPException(404,'Unknown alert')
    return {'alert_id':alert_id,**data}

@app.get('/api/rules')
def get_rules(request:Request):
    from events import DEFAULT_RULES
    configured=store.setting('rules',DEFAULT_RULES)
    result={**DEFAULT_RULES,**configured,
            'watchlist_conditions':configured.get('watchlist_conditions',{}),
            'zone_permits':configured.get('zone_permits',[])}
    camera_ids=getattr(request.state,'camera_ids',None)
    if camera_ids is not None:
        # The current rule store is global; keep camera-bound controls scoped and
        # do not expose unrelated plate identities or permits to case members.
        result['watchlist']={}
        result['watchlist_conditions']={}
        result['restricted_cameras']=[camera for camera in result['restricted_cameras'] if camera in camera_ids]
        result['dwell_zones']=[zone for zone in result['dwell_zones'] if zone['camera_id'] in camera_ids]
        result['zone_permits']=[{**permit,'camera_ids':[camera for camera in permit['camera_ids'] if camera in camera_ids]}
                                for permit in result['zone_permits'] if any(camera in camera_ids for camera in permit['camera_ids'])]
    return result

@app.put('/api/rules')
def update_rules(body:RuleConfig):
    config=body.model_dump()
    normalized_watchlist={}
    for plate,reason in config['watchlist'].items():
        normalized=check_plate(plate)
        if normalized in normalized_watchlist: raise HTTPException(422,'Watchlist plates must be unique after normalization')
        normalized_watchlist[normalized]=reason.strip()
    config['watchlist']=normalized_watchlist
    normalized_conditions={}
    for plate,condition in config['watchlist_conditions'].items():
        normalized=check_plate(plate)
        if normalized in normalized_conditions: raise HTTPException(422,'Watchlist condition plates must be unique after normalization')
        if normalized not in normalized_watchlist: raise HTTPException(422,'Watchlist conditions must refer to a configured watchlist plate')
        normalized_conditions[normalized]=condition
    config['watchlist_conditions']=normalized_conditions
    for camera in config['restricted_cameras']+[z['camera_id'] for z in config['dwell_zones']]: check_camera(camera)
    if len(set(config['restricted_cameras']))!=len(config['restricted_cameras']):
        raise HTTPException(422,'Restricted cameras must be unique')
    permit_ids=set()
    for permit in config['zone_permits']:
        permit['plate']=check_plate(permit['plate'])
        if permit['permit_id'] in permit_ids: raise HTTPException(422,'Permit IDs must be unique')
        permit_ids.add(permit['permit_id'])
        for camera in permit['camera_ids']: check_camera(camera)
    store.update_rules(config,time.time()); return config

@app.post('/api/nlquery')
def nlquery(body:QueryRequest,request:Request): return redact_analytics_payload(nl_answer(body.question,camera_ids=getattr(request.state,'camera_ids',None)))

@app.get('/api/trajectory/{plate}')
def trajectory(plate:str,request:Request,since:TimeFilter=None,until:TimeFilter=None):
    interval(since,until); return redact_analytics_payload(get_trajectory(check_plate(plate),since,until,camera_ids=getattr(request.state,'camera_ids',None)))

@app.post('/api/evidence/{plate}')
def evidence(plate:str,request:Request,since:TimeFilter=None,until:TimeFilter=None):
    interval(since,until); plate=check_plate(plate)
    actor=getattr(request.state,'actor',None)
    case_id=request.state.case_id if actor else None
    try: return evidence_report(plate,since,until,case_id=case_id,camera_ids=getattr(request.state,'camera_ids',None))
    except EvidenceSigningError as exc: raise HTTPException(503,'Evidence signing is configured but the signing key is unavailable or invalid') from exc
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc


def report_payload(report_id,scope_case_id=None):
    report=store.report(report_id,time.time(),scope_case_id=scope_case_id)
    if not report: raise HTTPException(404,'Report unavailable or expired')
    unsigned={k:v for k,v in report.items() if k!='package_hash'}
    if hashlib.sha256(canonical_json(unsigned).encode()).hexdigest()!=report['package_hash']:
        raise HTTPException(409,'Report hash verification failed')
    return report

@app.get('/api/reports/{report_id}')
def report_json(report_id:str,request:Request):
    actor=getattr(request.state,'actor',None)
    scope_case_id=request.state.case_id if actor and actor['role']!='admin' else None
    report=report_payload(report_id,scope_case_id)
    return Response(canonical_json(report),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="{report["report_id"]}.json"'})

@app.get('/api/reports/{report_id}/package')
def report_package(report_id:str,request:Request):
    actor=getattr(request.state,'actor',None)
    scope_case_id=request.state.case_id if actor and actor['role']!='admin' else None
    report=report_payload(report_id,scope_case_id); out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as package:
        package.writestr('manifest.json',canonical_json(report))
        if sum(a['size'] for a in report['artifacts']) > 64*1024*1024:
            raise HTTPException(413,'Artifact package exceeds 64 MiB; choose a shorter interval')
        for artifact in report['artifacts']:
            try: data=artifact_bytes(artifact['sha256'], report['expires_at'])
            except ValueError as exc: raise HTTPException(409,str(exc)) from exc
            if data is None: raise HTTPException(410,'A report artifact has expired or is missing')
            package.writestr(f'artifacts/{artifact["sha256"]}.jpg',data)
    return Response(out.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{report["report_id"]}.zip"'})

@app.get('/api/artifacts/{digest}')
def artifact(digest:str,request:Request):
    actor=getattr(request.state,'actor',None)
    scope_case_id=request.state.case_id if actor and actor['role']!='admin' else None
    protected_until=store.artifact_expiry(digest, time.time(), scope_case_id=scope_case_id)
    if scope_case_id is not None and protected_until is None: raise HTTPException(404,'Artifact unavailable or expired')
    try: data=artifact_bytes(digest, protected_until)
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    if data is None: raise HTTPException(404,'Artifact unavailable or expired')
    return Response(data,media_type='image/jpeg')

@app.get('/api/reports/{report_id}/print',response_class=HTMLResponse)
def report_print(report_id:str,request:Request):
    actor=getattr(request.state,'actor',None)
    scope_case_id=request.state.case_id if actor and actor['role']!='admin' else None
    report=report_payload(report_id,scope_case_id)
    esc=lambda value:html.escape(str(value))
    rows=''.join(f'<tr><td>{esc(h["camera_id"])}</td><td>{esc(h["ts"])}</td><td>{esc(h.get("plate_raw",""))}</td><td>{esc(h.get("plate_norm",""))}</td><td>{esc(h.get("source_mode","manual"))} / {esc(h.get("time_basis","provided"))}</td></tr>' for h in report['trajectory']['observations'])
    raw_rows=''.join(f'<tr><td>{esc(h["event_id"])}</td><td>{esc(h["ts"])}</td><td>{esc(h.get("plate_raw",""))}</td><td>{esc(h.get("plate_norm",""))}</td><td>{esc(h.get("identity_status","supported"))}</td></tr>' for h in report.get('raw_reads',[]))
    coverage=report.get('artifact_coverage')
    coverage_text=(f'Image coverage: {coverage["reads_with_complete_current_images"]} of {coverage["total_reads"]} reads have a matching sampled frame and crop. '
                   f'Reads without complete matching images: {coverage["reads_without_complete_current_images"]}. Older/manual reads: {coverage["legacy_or_manual_reads"]}. '
                   'This covers sampled reads, not every video frame.' if coverage else 'Image coverage is unavailable in this older report snapshot.')
    raw_section=f'<h2>Supporting raw reads ({esc(report.get("raw_read_count",0))})</h2><p>{esc(coverage_text)}</p><p class="table-scroll-hint">Scroll horizontally to view every column.</p><div class="report-table" role="region" aria-label="Supporting raw reads table" tabindex="0"><table><tr><th>Read ID</th><th>Observation time</th><th>Raw OCR</th><th>Canonical plate</th><th>Identity status</th></tr>{raw_rows}</table></div>'
    image_candidates=report.get('image_review_candidates')
    image_candidate_section=(f'<h2>Top image review candidates</h2><p>Fixed heuristic ranking for review only; all raw reads and images remain included. It does not identify a verified best shot or OCR accuracy.</p><pre>{esc(json.dumps(image_candidates,sort_keys=True,indent=2))}</pre>' if image_candidates else '')
    provenance_section=f'<h2>Model provenance</h2><pre>{esc(json.dumps(report.get("model_provenance",{"status":"unavailable in this older report snapshot"}),sort_keys=True,indent=2))}</pre>'
    signature=report.get('signature')
    signature_section=(f'<h2>Digital signature</h2><p>Ed25519 signature over canonical JSON. Verify the downloaded JSON with a trusted public key distributed independently.</p><pre>{esc(json.dumps(signature,sort_keys=True,indent=2))}</pre>' if signature else '<h2>Digital signature</h2><p>This report was not digitally signed.</p>')
    pictures=''.join(f'<figure><img src="/api/artifacts/{esc(a["sha256"])}" alt="{esc(a["role"])}"><figcaption>{esc(a["role"])} · frame {esc(a.get("frame_id",""))} · {esc(a["sha256"])}</figcaption></figure>' for a in report['artifacts'])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(report_id)}</title><style>body{{font:16px system-ui;max-width:900px;margin:32px auto;padding:16px;line-height:1.5}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #777;padding:8px;text-align:left;overflow-wrap:anywhere}}pre,figcaption{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}.report-table{{overflow-x:auto}}.table-scroll-hint{{display:none}}img{{max-width:100%;max-height:400px}}@media screen and (max-width:600px){{.report-table table{{min-width:640px}}.table-scroll-hint{{display:block;font-size:14px}}}}@media print{{button{{display:none}}figure,tr{{break-inside:avoid}}}}</style><button onclick="window.print()">Print / Save PDF</button><h1>Sakshi observation report</h1><p>{esc(report_id)} · plate {esc(report['trajectory']['plate'])} · {esc(report['trajectory']['status'])}</p><p>Snapshot created {esc(report['generated_at'])}; expires {esc(report['expires_at'])} (UTC epoch seconds).</p><p>{esc(' '.join(report['limitations']))}</p><h2>Observations</h2><p class="table-scroll-hint">Scroll horizontally to view every column.</p><div class="report-table" role="region" aria-label="Observations table" tabindex="0"><table><tr><th>Camera</th><th>Observation time (UTC epoch)</th><th>Raw OCR</th><th>Canonical plate</th><th>Input / clock basis</th></tr>{rows}</table></div>{raw_section}{image_candidate_section}<h2>Accepted, rejected and unresolved links</h2><pre>{esc(canonical_json({k:report['trajectory'][k] for k in ['accepted_links','rejected_links','candidate_links']}))}</pre>{provenance_section}{signature_section}<h2>Manifest SHA-256</h2><pre>{esc(report['package_hash'])}</pre>{pictures}</html>'''
