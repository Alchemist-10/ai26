"""Durable observation services; rolling views expire on every read, not only ingestion."""
import hashlib
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from bisect import bisect_left, bisect_right
from math import asin, cos, radians, sin, sqrt
from collections import Counter
from statistics import mean, median
from zoneinfo import ZoneInfo
import re

from cameras import CAMERAS_BY_ID
from plate_format import normalize_plate
from repository import Repository, canonical_json
from report_signing import sign_report
from schemas import Observation

MAX_EVENTS = 5000
WINDOW_SECONDS = 300
MAX_TRAVEL_SPEED_KMH = 160
RETENTION_SECONDS = 7 * 86400
REPORT_RETENTION_SECONDS = 86400
LINK_ALGORITHM_VERSION = 'exact-plate-pair-constraints-v3'
store = Repository(Path(os.environ.get('AI26_DATA_ROOT', Path(__file__).parent / 'data')) / 'ai26.sqlite3')
DEFAULT_RULES = {'watchlist': {'KL07AB1234': 'Local example watchlist entry; human review required'},
                 'watchlist_conditions': {}, 'restricted_cameras': ['CAM-09'],
                 'zone_permits': [], 'dwell_zones': []}


def add_events(detections):
    with store.lock:
        return _add_events(detections)


def _add_events(detections):
    validated = []
    catalog = {c['id']:c for c in store.camera_catalog()}
    for raw in detections:
        event = Observation.model_validate(raw).model_dump(exclude_none=True)
        if event['camera_id'] not in CAMERAS_BY_ID: raise ValueError('Unknown camera in observation')
        event['camera_configuration'] = catalog[event['camera_id']]
        if event['kind'] == 'plate':
            normalized = normalize_plate(event.get('plate_norm') or event.get('plate', ''))
            if not normalized['format_valid']:
                if event.get('identity_status') not in ('invalid','low_confidence'): raise ValueError('Invalid canonical plate')
                event['plate'] = event['plate_norm'] = None
            else:
                event['plate'] = event['plate_norm'] = str(normalized['plate_norm'])
        validated.append(event)
    return store.ingest(validated)


def get_events(camera_id=None, plate=None, since=None, until=None, kind=None, limit=None):
    normalized = str(normalize_plate(plate)['plate_norm']) if plate else None
    return store.observations(camera_id, normalized, time.time()-WINDOW_SECONDS if since is None else since,
                              time.time() if until is None else until, kind, limit or MAX_EVENTS)


def _distance_km(first, second):
    a, b = first, second
    lat1, lat2 = radians(a['lat']), radians(b['lat'])
    h = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin(radians(b['lon']-a['lon'])/2)**2
    return 6371 * 2 * asin(min(1, sqrt(h)))


def build_trajectory(observations):
    ordered = sorted(observations, key=lambda e: (e['ts'], e.get('event_id','')))
    catalog = {c['id']:c for c in store.camera_catalog()}
    hops = []
    for event in ordered:
        camera = event.get('camera_configuration') or catalog.get(event['camera_id'], {})
        hops.append({**event, 'location': camera.get('location', 'Unknown'),
                     'location_confirmed': camera.get('location_confirmed', False),
                     'lat': camera.get('lat'), 'lon': camera.get('lon'),
                     'camera_configuration':camera,
                     'metadata_basis':'observation_snapshot' if event.get('camera_configuration') else 'current_catalog_legacy',
                     'repairs': event.get('repairs', [])})
    accepted, rejected, candidates = [], [], []
    for first, second in zip(hops, hops[1:]):
        if first['camera_id'] == second['camera_id']: continue
        elapsed = second['ts'] - first['ts']
        distance = _distance_km(first, second)
        speed = distance * 3600 / elapsed if elapsed > 0 else None
        pair_constraint=store.camera_pair_constraint(first['camera_id'],second['camera_id'])
        constraint_matches=bool(pair_constraint and
            pair_constraint['from_revision']==first['camera_configuration']['revision'] and
            pair_constraint['to_revision']==second['camera_configuration']['revision'])
        pair_snapshot={**pair_constraint,'matches_observation_revisions':constraint_matches} if pair_constraint else None
        link = {'from_camera_id': first['camera_id'], 'to_camera_id': second['camera_id'],
                'from_ts': first['ts'], 'to_ts': second['ts'], 'distance_km': round(distance, 3),
                'elapsed_seconds': round(elapsed, 3), 'implied_speed_kmh': round(speed, 1) if speed is not None else None,
                'from_passage_id': first.get('passage_id'), 'to_passage_id': second.get('passage_id'), 'method': 'exact_plate',
                'supporting_event_ids':[first.get('event_id'),second.get('event_id')],
                'algorithm_version':LINK_ALGORITHM_VERSION,
                'camera_configurations':[first['camera_configuration'],second['camera_configuration']],
                'camera_pair_constraint':pair_snapshot,
                'metadata_basis':[first['metadata_basis'],second['metadata_basis']],
                'time_bases':[first.get('time_basis','unspecified'),second.get('time_basis','unspecified')],
                'identity_verified':False}
        # Replay position and reader-arrival times are not synchronized capture clocks.
        uncalibrated = not first['location_confirmed'] or not second['location_confirmed'] or any(
            e.get('time_basis') in ('replay_clock', 'capture_arrival_clock') for e in (first, second))
        if elapsed <= 0:
            rejected.append({**link, 'reason': 'nonpositive elapsed time; transition cannot be established'})
        elif uncalibrated:
            candidates.append({**link, 'implied_speed_kmh': None, 'reason': 'Location or synchronized capture-time calibration unavailable'})
        elif speed > MAX_TRAVEL_SPEED_KMH:
            rejected.append({**link, 'reason': f'impossible travel: {speed:.1f} km/h implied; limit {MAX_TRAVEL_SPEED_KMH} km/h'})
        elif not constraint_matches:
            candidates.append({**link,'implied_speed_kmh':None,
                               'reason':'Camera-pair travel window is missing or belongs to different location revisions'})
        elif not pair_constraint['enabled']:
            rejected.append({**link,'reason':'Camera pair is marked as a disconnected route'})
        elif not pair_constraint['min_travel_seconds'] <= elapsed <= pair_constraint['max_travel_seconds']:
            rejected.append({**link,'reason':'Observed travel time falls outside the configured camera-pair window'})
        else:
            accepted.append({**link, 'reason': 'Exact plate and baseline travel gate; identity remains unverified'})
    status = 'not_found' if not hops else 'observed'
    if accepted or candidates: status = 'candidate'
    if rejected: status = 'review_required'
    return {'mode': 'live', 'source_mode': ordered[0].get('source_mode', 'manual') if ordered else None,
            'status': status, 'plate': ordered[0].get('plate_norm', '') if ordered else '',
            'observations': hops, 'accepted_links': accepted, 'rejected_links': rejected, 'candidate_links': candidates}


def get_trajectory(plate, since=None, until=None):
    normalized = str(normalize_plate(plate)['plate_norm'])
    start = time.time()-WINDOW_SECONDS if since is None else since
    end = time.time() if until is None else until
    with store.lock:
        result = build_trajectory(store.supported_passage_reads(normalized, start, end))
        result = store.put_journey_links(normalized,result)
    result['plate'] = normalized
    result['interval'] = {'since': start, 'until': time.time() if until is None else until}
    return result


def evidence_report(plate, since=None, until=None, case_id=None):
    # Prevent maintenance from removing a source between selecting it and leasing it.
    with store.lock:
        return _evidence_report(plate, since, until, case_id)


def _evidence_report(plate, since=None, until=None, case_id=None):
    trajectory = get_trajectory(plate, since, until)
    if not trajectory['observations']: raise ValueError('No supported plate observations for this interval')
    now = time.time()
    passages = [h['passage_id'] for h in trajectory['observations']]
    raw_reads, raw_total = store.reads_for_passages(passages, trajectory['interval']['since'], trajectory['interval']['until'])
    if raw_total > 5000: raise ValueError('Report exceeds 5000 raw reads; choose a shorter interval')
    artifacts = {}
    for hop in raw_reads:
        for artifact in hop.get('artifacts', []): artifacts[artifact['sha256']] = artifact
    from artifacts import artifact_bytes, summarize_read_images, rank_read_image_candidates
    for artifact in artifacts.values():
        if artifact_bytes(artifact['sha256'], now + REPORT_RETENTION_SECONDS) is None:
            raise ValueError('A source artifact is missing; choose an available evidence interval')
    report = {'report_id': f'EVD-{uuid.uuid4().hex[:12].upper()}', 'version': 5,
              'generated_at': now, 'expires_at': now + REPORT_RETENTION_SECONDS,
              'case_id': case_id,
              'retention': 'Report expires after 24 hours; referenced artifacts protected until report expiry; other source artifacts retained for 7 days',
              'trajectory': trajectory, 'raw_reads': raw_reads, 'raw_read_count':raw_total, 'artifacts': list(artifacts.values()),
              'model_provenance': summarize_read_models(raw_reads),
              'artifact_coverage': summarize_read_images(raw_reads),
              'image_review_candidates':rank_read_image_candidates(raw_reads,top_k=3),
              'signature': None,
              'limitations': ['Candidate links do not verify vehicle identity.', 'Frame/crop JPEGs are decoded image derivatives; source clip digests identify their recording.', 'package_hash is an unkeyed integrity digest. When signature is present, Ed25519 authenticates the canonical JSON payload; trust the public-key fingerprint through an independent channel.',
                              'Model-file digests identify loaded bytes, not accuracy or authenticity. Older/manual reads can lack exact model provenance; weights are not included in the evidence ZIP.',
                              'Top image candidates use a fixed unvalidated heuristic; they are review suggestions, not measured best shots or OCR accuracy.',
                              'Image coverage counts current sampled-read JPEG derivatives only. Older/manual reads, failed writes or empty/outside boxes can lack matching images; this is not a full video-frame archive.']}
    report['signature'] = sign_report(report)
    report['package_hash'] = hashlib.sha256(canonical_json(report).encode()).hexdigest()
    store.put_report(report)
    return report


def summarize_read_models(reads):
    sets={}; missing=0; exact=0
    required={'plate_detector_weights','ocr_weights','ocr_configuration'}
    for read in reads:
        metadata=read.get('model_metadata')
        if not isinstance(metadata,dict) or not metadata:
            missing+=1; continue
        digest=hashlib.sha256(canonical_json(metadata).encode()).hexdigest()
        if digest not in sets: sets[digest]={'model_set_id':digest,'read_count':0,'metadata':metadata}
        sets[digest]['read_count']+=1
        files=metadata.get('model_files',[])
        valid={f.get('role') for f in files if isinstance(f,dict) and isinstance(f.get('role'),str) and
               isinstance(f.get('sha256'),str) and re.fullmatch(r'[a-f0-9]{64}',f['sha256']) and
               isinstance(f.get('size'),int) and not isinstance(f['size'],bool) and f['size']>0} if isinstance(files,list) else set()
        if metadata.get('weight_provenance_status')=='hashed_loaded_files' and required<=valid: exact+=1
    return {'total_reads':len(reads),'reads_missing_model_metadata':missing,
            'reads_with_exact_alpr_files':exact,'reads_without_exact_alpr_files':len(reads)-exact,
            'model_sets':[sets[key] for key in sorted(sets)]}


def _alert(rule, subject, event, severity, summary, detail, support=None):
    identity = [rule, subject, event.get('session_id', 'manual'), event['camera_id']]
    alert = {'alert_id': hashlib.sha256(canonical_json(identity).encode()).hexdigest()[:24], 'rule_version': 1,
             'type': rule, 'severity': severity, 'summary': summary, 'detail': detail, 'ts': event['ts'],
             'supporting_event_ids': support or [event.get('event_id')], 'source_mode': event.get('source_mode', 'manual')}
    store.put_alert(alert)


def derive_alerts(since=None, until=None):
    start = time.time()-WINDOW_SECONDS if since is None else since
    snapshot = get_events(since=start, until=until)
    rules = store.setting('rules', DEFAULT_RULES)
    supported = {p['passage_id'] for p in store.passages(start,until) if p['kind']=='plate' and not p.get('identity_conflict')}
    conditions=rules.get('watchlist_conditions',{})
    max_history=max((float(condition.get('history_window_seconds',0)) for condition in conditions.values()),default=0)
    history_snapshot=get_events(since=start-max_history,until=until) if max_history else snapshot
    history_supported={p['passage_id'] for p in store.passages(start-max_history,until)
                       if p['kind']=='plate' and not p.get('identity_conflict')} if max_history else supported
    plate_history={}
    for event in history_snapshot:
        if event['kind']=='plate' and event.get('identity_status','supported')=='supported' and event.get('passage_id') in history_supported:
            plate_history.setdefault(event.get('plate_norm'),[]).append(event['ts'])
    for timestamps in plate_history.values(): timestamps.sort()
    permits=rules.get('zone_permits',[])
    for event in snapshot:
        if event.get('passage_id') not in supported: continue
        if event['kind'] != 'plate' or event.get('identity_status', 'supported') != 'supported': continue
        plate = event.get('plate_norm')
        if plate in rules['watchlist']:
            condition=conditions.get(plate,{})
            active_from=condition.get('active_from')
            active_until=condition.get('active_until')
            is_active=(active_from is None or event['ts']>=active_from) and (active_until is None or event['ts']<active_until)
            minimum=max(1,int(condition.get('minimum_sightings',1)))
            lookback=max(0,float(condition.get('history_window_seconds',0)))
            sightings=plate_history.get(plate,[])
            history_count=bisect_right(sightings,event['ts'])-bisect_left(sightings,event['ts']-lookback)
            if is_active and history_count>=minimum:
                detail=f"{rules['watchlist'][plate]} · {history_count} supported sighting(s) in the prior {lookback:g}s; local review only"
                _alert('watchlist match', plate, event, 'critical', f'{plate} matched a local watchlist entry', detail)
        if event['camera_id'] in rules['restricted_cameras']:
            active_permit=next((permit for permit in permits if permit['plate']==plate and
                event['camera_id'] in permit['camera_ids'] and permit['valid_from']<=event['ts']<permit['valid_until']),None)
            if active_permit:
                detail=f"Local permit {active_permit['permit_id']} applies: {active_permit['reason']}. No external permit verification was performed."
                _alert('permitted zone visit', [plate,active_permit['permit_id']], event, 'info',
                       f'{plate} observed at {event["camera_id"]} with a local permit on file', detail)
            else:
                _alert('zone sighting', plate, event, 'warning', f'{plate} observed at {event["camera_id"]}', 'No matching local permit record; this is not a legal violation determination')
    for plate in {e.get('plate_norm') for e in snapshot if e['kind']=='plate' and e.get('plate_norm')}:
        route = get_trajectory(plate, start, until)
        for link in route['rejected_links']:
            event = {'camera_id': link['to_camera_id'], 'ts': link['to_ts']}
            _alert('route review', [plate, link['from_ts'], link['to_ts']], event, 'warning', f'{plate}: camera transition requires review', link['reason'])
    # Dwell means one tracked subject remains in an explicitly configured zone for elapsed time.
    for rule in rules.get('dwell_zones', []):
        by_track = {}
        for e in snapshot:
            if e['kind']!='vehicle' or e['camera_id']!=rule['camera_id'] or e.get('track_id') is None: continue
            by_track.setdefault((e.get('session_id'), e['track_id']), []).append(e)
        for identity, reads in by_track.items():
            sequence=[]
            for e in reads:
                width, height = e.get('frame_size', [0,0])
                if not width or not height: continue
                x1,y1,x2,y2=e['bbox']; x=(x1+x2)/2/width; y=(y1+y2)/2/height
                left,top,right,bottom=rule['zone']
                if not(left<=x<=right and top<=y<=bottom): sequence=[]; continue
                if sequence and e['ts']-sequence[-1]['ts']>rule['max_gap_seconds']: sequence=[]
                sequence.append(e)
                if len(sequence)>=3 and e['ts']-sequence[0]['ts']>=rule['dwell_seconds']:
                    _alert('zone dwell', list(identity)+[sequence[0]['ts']], e, 'warning', f'Track {e["track_id"]} remained in the configured zone',
                           f'{e["ts"]-sequence[0]["ts"]:.1f}s observed dwell at {e["camera_id"]}; identity is camera-local', [r.get('event_id') for r in sequence])
                    break
    return [a for a in store.alerts(start) if until is None or a['ts']<=until]


def stats(since=None, until=None):
    now = time.time()
    start = now-WINDOW_SECONDS if since is None else since
    end = now if until is None else until
    # Aggregate across all rows, not the paginated raw-read API limit.
    return {**store.statistics(start,end,now), 'interval':{'since':start,'until':end},
            'metric':'camera-local tracked passages, not globally unique vehicles', 'coverage':'sampled recorded inputs'}


def flows(since=None, until=None):
    start = time.time()-WINDOW_SECONDS if since is None else since
    passages=store.passages(start,until)
    plates={p.get('plate_norm') for p in passages if p['kind']=='plate' and p.get('identity_status','supported')=='supported' and not p.get('identity_conflict')}
    counts=Counter()
    for plate in plates:
        for link in get_trajectory(plate,start,until)['accepted_links']:
            counts[(link['from_camera_id'],link['to_camera_id'])]+=1
    return [{'from':a,'to':b,'count':n} for (a,b),n in counts.items()]


def traffic_baselines(days=28, now=None, timezone_name=None):
    """Compare the latest completed live source-hour with covered weekday/hour history."""
    if type(days) is not int or not 7 <= days <= 90:
        raise ValueError('days must be an integer from 7 to 90')
    now=time.time() if now is None else now
    timezone_name=timezone_name or os.environ.get('AI26_TIMEZONE','Asia/Kolkata')
    zone=ZoneInfo(timezone_name)
    start=int((now-days*86400)//900)*900
    end=int(now)+1
    rows=store.camera_hourly_traffic(start,end)
    # Aggregate repeated local hours (for example a DST fall-back) per local day.
    per_camera={camera['id']:{} for camera in store.camera_catalog()}
    for row in rows:
        hour_start=datetime.fromtimestamp(row['bucket_start_utc'],timezone.utc).astimezone(zone)
        key=(hour_start.date(),hour_start.weekday(),hour_start.hour)
        bucket=per_camera.setdefault(row['camera'],{}).setdefault(key,{
            'date':key[0], 'weekday':key[1], 'hour':key[2], 'processed_samples':0,
            'processed_quarter_hours':0,
            'vehicle_passages':0, 'latest_bucket_start_utc':row['bucket_start_utc'],
            'local_hour_start':hour_start.replace(minute=0,second=0,microsecond=0)})
        bucket['processed_samples']+=row['processed_samples']
        bucket['processed_quarter_hours']+=row['processed_samples']>0
        bucket['vehicle_passages']+=row['vehicle_passages']
        if row['bucket_start_utc']>bucket['latest_bucket_start_utc']:
            bucket['latest_bucket_start_utc']=row['bucket_start_utc']
            bucket['local_hour_start']=hour_start.replace(minute=0,second=0,microsecond=0)
    current_local_hour=datetime.fromtimestamp(now,timezone.utc).astimezone(zone).replace(minute=0,second=0,microsecond=0)
    start_date=datetime.fromtimestamp(start,timezone.utc).astimezone(zone).date()
    result=[]
    for camera_id in sorted(per_camera):
        camera_entries=list(per_camera[camera_id].values())
        completed=[entry for entry in camera_entries if
                 (entry['date']<current_local_hour.date() or
                  (entry['date']==current_local_hour.date() and entry['hour']<current_local_hour.hour))]
        covered=[entry for entry in completed if entry['processed_samples']>=4
                 and entry['processed_quarter_hours']>=2]
        if not covered:
            result.append({'camera_id':camera_id,
                           'status':'insufficient_coverage' if completed else 'no_live_history',
                           'latest_complete_hour_local':None,
                           'latest_passages':None,'latest_processed_samples':None,'baseline_median':None,
                           'latest_covered_quarter_hours':None,'baseline_mean':None,
                           'baseline_comparable_hours':0,'change_vs_median_percent':None,
                           'age_seconds':None})
            continue
        latest=max(covered,key=lambda row:row['latest_bucket_start_utc'])
        history=[entry for entry in covered if entry['date']<latest['date']
                 and entry['weekday']==latest['weekday'] and entry['hour']==latest['hour']
                 and entry['date']>=start_date]
        # Keep the requested rolling interval by timestamp as well as local date.
        history=[entry for entry in history if entry['latest_bucket_start_utc']>=start]
        baseline_values=[entry['vehicle_passages'] for entry in history]
        baseline_median=float(median(baseline_values)) if len(baseline_values)>=2 else None
        baseline_mean=float(mean(baseline_values)) if len(baseline_values)>=2 else None
        delta=(100*(latest['vehicle_passages']-baseline_median)/baseline_median
               if baseline_median not in (None,0) else None)
        age=max(0,now-(latest['local_hour_start'].timestamp()+3600))
        status='stale' if age>36*3600 else 'baseline_ready' if len(baseline_values)>=2 else 'insufficient_history'
        local_stamp=latest['local_hour_start']
        result.append({'camera_id':camera_id,'status':status,
                       'latest_complete_hour_local':local_stamp.isoformat(),
                       'latest_passages':latest['vehicle_passages'],
                       'latest_processed_samples':latest['processed_samples'],
                       'latest_covered_quarter_hours':latest['processed_quarter_hours'],
                       'baseline_median':baseline_median,'baseline_mean':baseline_mean,
                       'baseline_comparable_hours':len(baseline_values),
                       'change_vs_median_percent':round(delta,2) if delta is not None else None,
                       'age_seconds':round(age,1)})
    return {'window_days':days,'timezone':timezone_name,
            'scope':'Live-source camera-local tracked vehicle passages; one sample per local passage',
            'time_basis':'capture_arrival_clock','retention_days':90,
            'speed_kmh':None,'speed_status':'Unavailable until route distance and capture clocks are independently calibrated',
            'cameras':result}
