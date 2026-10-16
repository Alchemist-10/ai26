"""Supported, deterministic query intents against persisted observations. No simulated SQL."""
import os
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from cameras import CAMERAS_BY_ID
from events import derive_alerts, stats


def _find_camera(text):
    import events
    catalog = events.store.camera_catalog()
    for cam in catalog:
        if re.search(r'\b'+re.escape(cam['id'])+r'\b',text,re.I): return cam
    matches = [c for c in catalog if c['location_confirmed'] and c['location'].lower() in text.lower()]
    if len(matches)>1: raise ValueError('Location matches multiple cameras; use one camera ID')
    return matches[0] if matches else None


def _interval(text):
    tz=ZoneInfo(os.environ.get('AI26_TIMEZONE','Asia/Kolkata'))
    now=datetime.now(tz)
    if len(re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text))>1: raise ValueError('Multiple dates require structured interval search')
    date=re.search(r'\b(\d{4}-\d{2}-\d{2})\b',text)
    start=now.replace(hour=0,minute=0,second=0,microsecond=0)
    explicit=bool(date or 'today' in text or 'yesterday' in text)
    if date:
        start=datetime.strptime(date[1],'%Y-%m-%d').replace(tzinfo=tz)
    elif 'yesterday' in text:
        start-=timedelta(days=1)
    end=start+timedelta(days=1)
    if len(re.findall(r'\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b',text))>1: raise ValueError('Use one clock time')
    clock=re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b',text)
    if clock:
        hour=int(clock[1]); minute=int(clock[2] or 0)
        if not 1<=hour<=12 or not 0<=minute<=59: raise ValueError('Invalid am/pm time')
        start=start.replace(hour=hour%12+(12 if clock[3]=='pm' else 0),minute=minute)
        if 'before' in text: end=start; start=start.replace(hour=0,minute=0)
        elif 'after' not in text and 'since' not in text: end=start+timedelta(hours=1)
        explicit=True
    if not explicit: return time.time()-300,time.time()
    return start.timestamp(),end.timestamp()


def answer(question,camera_ids=None):
    import events
    q=question.lower()
    if 'congest' in q or re.search(r'\b(red|blue|white|black|silver|color|colour)\b',q):
        return {"status":"unsupported","text":"Color and calibrated congestion queries are not supported. Ask for plate reads or camera-local vehicle class counts."}
    try: since,until=_interval(q)
    except ValueError: return {'text':'Use a valid YYYY-MM-DD date and a time such as 8:30 am.', 'status':'invalid'}
    camera_names=re.findall(r'\bCAM-\d+\b',question,re.I)
    if any(c.upper() not in CAMERAS_BY_ID for c in camera_names): return {'status':'invalid','text':'Unknown camera ID. Use a configured ID from the Camera Wall.'}
    if len(set(c.upper() for c in camera_names))>1: return {'status':'unsupported','text':'Please query one camera at a time.'}
    if camera_ids is not None and camera_names and camera_names[0].upper() not in camera_ids:
        return {'status':'invalid','text':'That camera is not assigned to the selected case.'}
    try: cam=_find_camera(q)
    except ValueError as exc: return {'status':'invalid','text':str(exc)}
    if camera_ids is not None and cam and cam['id'] not in camera_ids:
        return {'status':'invalid','text':'That camera is not assigned to the selected case.'}
    # Whole-word matching prevents an arbitrary label from swallowing a requested plate.
    plate_pattern=r'\b([A-Z]{2}\s*\d{2}\s*[A-Z]{1,3}\s*\d{4}|\d{2}\s*BH\s*\d{4}\s*[A-Z]{1,2})\b'
    if len(re.findall(plate_pattern,question,re.I))>1: return {'status':'unsupported','text':'Please query one plate at a time.'}
    match=re.search(r'\b([A-Z]{2}\s*\d{2}\s*[A-Z]{1,3}\s*\d{4}|\d{2}\s*BH\s*\d{4}\s*[A-Z]{1,2})\b',question,re.I)
    plate=match[0] if match else None
    class_match=re.search(r'\b(car|bus|truck|motorcycle)s?\b',q)
    if class_match and plate: return {'status':'unsupported','text':'Vehicle class-to-plate association is not validated. Search this plate separately.'}
    interval={'since':since,'until':until,'timezone':os.environ.get('AI26_TIMEZONE','Asia/Kolkata')}
    if 'busiest' in q or 'busy' in q:
        s=stats(since,until,camera_ids=camera_ids); camera=s['busiest_camera']
        return {'status':'supported','interval':interval,'text':f'{camera} has the most camera-local tracked vehicle passages: {s["per_camera_passages"][camera]}.' if camera else 'No tracked vehicle passages in that interval.'}
    if any(word in q for word in ['violation','restricted','alert','anomal']):
        alerts=derive_alerts(since,until,camera_ids=camera_ids)
        return {'status':'supported','interval':interval,'text':'; '.join(f'{a["type"]}: {a["summary"]}' for a in alerts[:10]) if alerts else 'No configured rule alerts in that interval.'}
    if cam or plate or 'plate' in q or class_match:
        if class_match:
            count=events.store.query_vehicle_count(cam['id'] if cam else None,class_match[1],since,until,camera_ids=camera_ids)
            text=f'{count} camera-local {class_match[1]} passages in the requested interval.'
        else:
            from plate_format import normalize_plate
            normalized=str(normalize_plate(plate)['plate_norm']) if plate else None
            rows=events.store.query_plates(cam['id'] if cam else None,normalized,since,until,camera_ids=camera_ids)
            plates=sorted({r[0] for r in rows}); cameras=sorted({r[1] for r in rows})
            text=f'{len(plates)} supported plate(s): {", ".join(plates)}. Cameras: {", ".join(cameras)}.' if plates else 'No supported plate reads matching that plate/camera/time filter.'
        return {'status':'supported','interval':interval,'text':text}
    return {'status':'unsupported','text':'Supported queries: busiest camera, configured alerts, plates at a camera, a specific plate, or vehicle class counts. Add today, yesterday, YYYY-MM-DD, or after 8:30 am. Color, free-form congestion and unrestricted questions are not supported.'}
