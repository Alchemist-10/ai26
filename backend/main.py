import asyncio
import hashlib
import html
import io
import json
import os
import time
import zipfile
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from cameras import CAMERAS_BY_ID, camera_playback_source, camera_source
from events import derive_alerts, evidence_report, flows, get_events, get_trajectory, stats, store
from nlquery import answer as nl_answer
from processing import processor
from schemas import QueryRequest, ReviewRequest, RuleConfig, CameraConfigurationUpdate, SourceSelectionRequest
from stream import mjpeg_generator, snapshot_frame
from plate_format import normalize_plate
from repository import canonical_json
from artifacts import artifact_bytes
from maintenance import Maintenance
from source_status import source_status
from source_uploads import uploads, parse_metadata, UploadBusy
from starlette.requests import ClientDisconnect
from source_selection import select_for_restart, SelectionConflict
from import_source import ImportBusy


@asynccontextmanager
async def lifespan(app):
    janitor = Maintenance(store)
    janitor.start()
    try:
        if os.environ.get('AI26_PROCESSING_ENABLED','1')=='1': processor.start()
        yield
    finally:
        await asyncio.to_thread(uploads.close)
        await asyncio.to_thread(processor.stop)
        await asyncio.to_thread(janitor.stop)

frontend_port=os.environ.get('AI26_FRONTEND_PORT','5174')
app=FastAPI(title='AI26 observation API',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[f'http://localhost:{frontend_port}',f'http://127.0.0.1:{frontend_port}'],allow_methods=['*'],allow_headers=['*'])


@app.exception_handler(HTTPException)
async def http_error(request,exc):
    return JSONResponse(status_code=exc.status_code,content={'error':{'code':exc.status_code,'message':str(exc.detail)}})

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    return JSONResponse(status_code=422,content={'error':{'code':422,'message':'; '.join(f'{".".join(map(str,e["loc"]))}: {e["msg"]}' for e in exc.errors())}})

TimeFilter=Annotated[float|None,Query(ge=0,allow_inf_nan=False)]


def check_camera(camera_id):
    if camera_id not in CAMERAS_BY_ID: raise HTTPException(404,'Unknown camera')


def check_plate(plate):
    normalized=normalize_plate(plate)
    if not normalized['format_valid']: raise HTTPException(422,'Enter a valid Indian registration plate')
    return str(normalized['plate_norm'])


def interval(since,until):
    if since is not None and until is not None and since>until: raise HTTPException(422,'since must not be after until')


@app.get('/api/cameras')
def list_cameras():
    health={s['camera_id']:s for s in processor.health()}
    return [{**c,'source_available':camera_source(c['id']).is_file(),
             'health':health[c['id']]} for c in store.camera_catalog()]

@app.get('/api/cameras/{camera_id}/configuration')
def camera_configuration(camera_id:str, revision:Annotated[int|None,Query(ge=1)]=None):
    check_camera(camera_id)
    config=store.camera_configuration(camera_id,revision)
    if config is None: raise HTTPException(404,'Camera configuration revision unavailable')
    return config

@app.get('/api/cameras/{camera_id}/source')
def camera_source_status(camera_id:str):
    check_camera(camera_id)
    return source_status(camera_id)

@app.post('/api/cameras/{camera_id}/source/prepare',status_code=202)
async def prepare_camera_source(camera_id:str,request:Request):
    check_camera(camera_id)
    if request.headers.get('content-type','').split(';')[0]!='application/octet-stream': raise HTTPException(415,'Send a raw video file')
    try:
        metadata=parse_metadata(request.headers.get('x-ai26-upload'))
        if request.headers.get('content-length') and int(request.headers['content-length'])!=metadata['bytes']: raise ValueError('Upload size header does not match the file')
        job,path=await uploads.reserve_async(camera_id,metadata)
    except UploadBusy as error: raise HTTPException(409,str(error)) from error
    except (ValueError,OSError) as error: raise HTTPException(422,str(error)) from error
    try: return await uploads.receive(request,job,path)
    except ClientDisconnect as error: raise HTTPException(400,'Upload interrupted') from error
    except TimeoutError as error: raise HTTPException(408,'Upload timed out') from error
    except (ValueError,OSError) as error: raise HTTPException(422,str(error)) from error

@app.get('/api/source-preparations/{job_id}')
def source_preparation(job_id:str):
    try: return uploads.get(job_id)
    except KeyError as error: raise HTTPException(404,'Preparation unavailable') from error

@app.post('/api/cameras/{camera_id}/source/selection')
def select_camera_source(camera_id:str,body:SourceSelectionRequest):
    check_camera(camera_id)
    try: result=select_for_restart(camera_id,body.model_dump())
    except (SelectionConflict,ImportBusy) as error: raise HTTPException(409,str(error)) from error
    except (ValueError,OSError) as error:
        raise HTTPException(422,'Imported files or selection records could not be verified or written. Running footage is unchanged; check host files before retrying.') from error
    return {**result,'source':source_status(camera_id)}

@app.post('/api/source-preparations/{job_id}/cancel')
def cancel_source_preparation(job_id:str):
    try: return uploads.cancel(job_id)
    except KeyError as error: raise HTTPException(404,'Preparation unavailable') from error

@app.put('/api/cameras/{camera_id}/configuration')
def update_camera_configuration(camera_id:str, body:CameraConfigurationUpdate):
    check_camera(camera_id)
    try: return store.update_camera(camera_id,body.model_dump(),time.time())
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc

@app.get('/api/journey-links')
def journey_links(plate:str|None=None,since:TimeFilter=None,until:TimeFilter=None,
                  limit:Annotated[int,Query(ge=1,le=5000)]=5000):
    interval(since,until)
    if plate: plate=check_plate(plate)
    return store.journey_links(plate,0 if since is None else since,until,limit)

@app.get('/api/health')
def health():
    return {'processing_enabled':os.environ.get('AI26_PROCESSING_ENABLED','1')=='1','cameras':processor.health(),
            'database_schema':store.schema_version,'scope':'single API process; run uvicorn with one worker'}

@app.get('/api/stream/{camera_id}')
def stream(camera_id:str,start:float|None=None,anchor:float|None=None):
    check_camera(camera_id)
    if not camera_source(camera_id).is_file(): raise HTTPException(404,'Camera source is unavailable')
    return StreamingResponse(mjpeg_generator(camera_id),media_type='multipart/x-mixed-replace; boundary=frame')

@app.get('/api/video/{camera_id}')
def video(camera_id:str):
    check_camera(camera_id); path=camera_playback_source(camera_id)
    if not path.is_file(): raise HTTPException(404,'Camera source is unavailable')
    return FileResponse(path,media_type='video/mp4')

@app.get('/api/snapshot/{camera_id}')
def snapshot(camera_id:str):
    check_camera(camera_id)
    if not camera_source(camera_id).is_file(): raise HTTPException(404,'Camera source is unavailable')
    jpeg=snapshot_frame(camera_id)
    if not jpeg: raise HTTPException(503,'No current processed frame; check camera health')
    return Response(content=jpeg,media_type='image/jpeg')

@app.get('/api/preview/{camera_id}')
def preview(camera_id:str,request:Request):
    check_camera(camera_id)
    if not camera_source(camera_id).is_file(): raise HTTPException(404,'Camera source is unavailable')
    latest=processor.preview(camera_id)
    if not latest: raise HTTPException(503,'Preview is not ready; check camera health')
    etag='"'+hashlib.sha256(latest[1]).hexdigest()+'"'
    headers={'ETag':etag,'Cache-Control':'private, no-cache','X-Frame-Time':str(latest[0])}
    if request.headers.get('if-none-match')==etag: return Response(status_code=304,headers=headers)
    return Response(content=latest[1],media_type='image/jpeg',headers=headers)

@app.get('/api/events')
def events(camera:str|None=None,plate:str|None=None,since:TimeFilter=None,until:TimeFilter=None,limit:Annotated[int,Query(ge=1,le=5000)]=5000):
    interval(since,until)
    if camera: check_camera(camera)
    if plate: plate=check_plate(plate)
    return get_events(camera,plate,since,until,limit=limit)

@app.get('/api/stats')
def get_stats(since:TimeFilter=None,until:TimeFilter=None):
    interval(since,until); return stats(since,until)

@app.get('/api/flows')
def get_flows(since:TimeFilter=None,until:TimeFilter=None):
    interval(since,until); return flows(since,until)

@app.get('/api/alerts')
def alerts(since:TimeFilter=None,until:TimeFilter=None):
    interval(since,until); return derive_alerts(since,until)

@app.post('/api/alerts/{alert_id}/review')
def review(alert_id:str,body:ReviewRequest):
    if not body.reviewer.strip(): raise HTTPException(422,'Reviewer name is required')
    data={**body.model_dump(),'reviewer':body.reviewer.strip(),'ts':time.time()}
    if not store.review_alert(alert_id,data): raise HTTPException(404,'Unknown alert')
    return {'alert_id':alert_id,**data}

@app.get('/api/rules')
def get_rules():
    from events import DEFAULT_RULES
    return store.setting('rules',DEFAULT_RULES)

@app.put('/api/rules')
def update_rules(body:RuleConfig):
    for camera in body.restricted_cameras+[z.camera_id for z in body.dwell_zones]: check_camera(camera)
    config=body.model_dump(); config['watchlist']={check_plate(k):v for k,v in config['watchlist'].items()}
    store.set_setting('rules',config); return config

@app.post('/api/nlquery')
def nlquery(body:QueryRequest): return nl_answer(body.question)

@app.get('/api/trajectory/{plate}')
def trajectory(plate:str,since:TimeFilter=None,until:TimeFilter=None):
    interval(since,until); return get_trajectory(check_plate(plate),since,until)

@app.post('/api/evidence/{plate}')
def evidence(plate:str,since:TimeFilter=None,until:TimeFilter=None):
    interval(since,until); plate=check_plate(plate)
    try: return evidence_report(plate,since,until)
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc


def report_payload(report_id):
    report=store.report(report_id,time.time())
    if not report: raise HTTPException(404,'Report unavailable or expired')
    unsigned={k:v for k,v in report.items() if k!='package_hash'}
    if hashlib.sha256(canonical_json(unsigned).encode()).hexdigest()!=report['package_hash']:
        raise HTTPException(409,'Report hash verification failed')
    return report

@app.get('/api/reports/{report_id}')
def report_json(report_id:str):
    report=report_payload(report_id)
    return Response(canonical_json(report),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="{report["report_id"]}.json"'})

@app.get('/api/reports/{report_id}/package')
def report_package(report_id:str):
    report=report_payload(report_id); out=io.BytesIO()
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
def artifact(digest:str):
    try: data=artifact_bytes(digest, store.artifact_expiry(digest, time.time()))
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    if data is None: raise HTTPException(404,'Artifact unavailable or expired')
    return Response(data,media_type='image/jpeg')

@app.get('/api/reports/{report_id}/print',response_class=HTMLResponse)
def report_print(report_id:str):
    report=report_payload(report_id)
    esc=lambda value:html.escape(str(value))
    rows=''.join(f'<tr><td>{esc(h["camera_id"])}</td><td>{esc(h["ts"])}</td><td>{esc(h.get("plate_raw",""))}</td><td>{esc(h.get("plate_norm",""))}</td><td>{esc(h.get("source_mode","manual"))} / {esc(h.get("time_basis","provided"))}</td></tr>' for h in report['trajectory']['observations'])
    raw_rows=''.join(f'<tr><td>{esc(h["event_id"])}</td><td>{esc(h["ts"])}</td><td>{esc(h.get("plate_raw",""))}</td><td>{esc(h.get("plate_norm",""))}</td><td>{esc(h.get("identity_status","supported"))}</td></tr>' for h in report.get('raw_reads',[]))
    coverage=report.get('artifact_coverage')
    coverage_text=(f'Image coverage: {coverage["reads_with_complete_current_images"]} of {coverage["total_reads"]} reads have a matching sampled frame and crop. '
                   f'Reads without complete matching images: {coverage["reads_without_complete_current_images"]}. Older/manual reads: {coverage["legacy_or_manual_reads"]}. '
                   'This covers sampled reads, not every video frame.' if coverage else 'Image coverage is unavailable in this older report snapshot.')
    raw_section=f'<h2>Supporting raw reads ({esc(report.get("raw_read_count",0))})</h2><p>{esc(coverage_text)}</p><p class="table-scroll-hint">Scroll horizontally to view every column.</p><div class="report-table" role="region" aria-label="Supporting raw reads table" tabindex="0"><table><tr><th>Read ID</th><th>Observation time</th><th>Raw OCR</th><th>Canonical plate</th><th>Identity status</th></tr>{raw_rows}</table></div>'
    provenance_section=f'<h2>Model provenance</h2><pre>{esc(json.dumps(report.get("model_provenance",{"status":"unavailable in this older report snapshot"}),sort_keys=True,indent=2))}</pre>'
    pictures=''.join(f'<figure><img src="/api/artifacts/{esc(a["sha256"])}" alt="{esc(a["role"])}"><figcaption>{esc(a["role"])} · frame {esc(a.get("frame_id",""))} · {esc(a["sha256"])}</figcaption></figure>' for a in report['artifacts'])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(report_id)}</title><style>body{{font:16px system-ui;max-width:900px;margin:32px auto;padding:16px;line-height:1.5}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #777;padding:8px;text-align:left;overflow-wrap:anywhere}}pre,figcaption{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}.report-table{{overflow-x:auto}}.table-scroll-hint{{display:none}}img{{max-width:100%;max-height:400px}}@media screen and (max-width:600px){{.report-table table{{min-width:640px}}.table-scroll-hint{{display:block;font-size:14px}}}}@media print{{button{{display:none}}figure,tr{{break-inside:avoid}}}}</style><button onclick="window.print()">Print / Save PDF</button><h1>AI26 observation report</h1><p>{esc(report_id)} · plate {esc(report['trajectory']['plate'])} · {esc(report['trajectory']['status'])}</p><p>Snapshot created {esc(report['generated_at'])}; expires {esc(report['expires_at'])} (UTC epoch seconds).</p><p>{esc(' '.join(report['limitations']))}</p><h2>Observations</h2><p class="table-scroll-hint">Scroll horizontally to view every column.</p><div class="report-table" role="region" aria-label="Observations table" tabindex="0"><table><tr><th>Camera</th><th>Observation time (UTC epoch)</th><th>Raw OCR</th><th>Canonical plate</th><th>Input / clock basis</th></tr>{rows}</table></div>{raw_section}<h2>Accepted, rejected and unresolved links</h2><pre>{esc(canonical_json({k:report['trajectory'][k] for k in ['accepted_links','rejected_links','candidate_links']}))}</pre>{provenance_section}<h2>Manifest SHA-256</h2><pre>{esc(report['package_hash'])}</pre>{pictures}</html>'''
