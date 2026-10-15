"""Bounded, read-only Linux runtime sample; no labels or accuracy claims."""
import argparse
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics
import time
import urllib.parse
import urllib.request

MAX_RESPONSE_BYTES=1024*1024


def api_origin(value):
    parsed=urllib.parse.urlsplit(value)
    if (parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1')
            or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment):
        raise argparse.ArgumentTypeError('Use a local HTTP API origin without credentials, path or query')
    try: parsed.port
    except ValueError as error: raise argparse.ArgumentTypeError('Invalid API port') from error
    return value.rstrip('/')


def distribution(values):
    ordered=sorted(values)
    return {'samples':len(ordered),'median':round(statistics.median(ordered),3),
            'p95':round(ordered[math.ceil(len(ordered)*.95)-1],3),'max':round(ordered[-1],3)} if ordered else None


def read_health(origin, timeout=5):
    with urllib.request.urlopen(origin+'/api/health',timeout=timeout) as response:
        body=response.read(MAX_RESPONSE_BYTES+1)
    if len(body)>MAX_RESPONSE_BYTES: raise ValueError('Health response exceeded byte bound')
    result=json.loads(body)
    cameras=result.get('cameras') if isinstance(result,dict) else None
    if not isinstance(cameras,list) or len(cameras)>100: raise ValueError('Invalid camera health')
    seen=set()
    for camera in cameras:
        if not isinstance(camera,dict) or not isinstance(camera.get('camera_id'),str) or not re.fullmatch(r'CAM-\d{2}',camera['camera_id']):
            raise ValueError('Invalid camera health identity')
        if camera['camera_id'] in seen or type(camera.get('frames')) is not int or camera['frames']<0: raise ValueError('Invalid camera frame counters')
        age=camera.get('frame_age_seconds')
        if age is not None and (type(age) not in (int,float) or not math.isfinite(age)):
            raise ValueError('Invalid camera frame age')
        seen.add(camera['camera_id'])
    return result


def process_stats(pid, proc_root=Path('/proc')):
    # Read Linux procfs only. The birth tick prevents associating a reused PID.
    values=(Path(proc_root)/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
    return {'identity':int(values[19]),'cpu_seconds':(int(values[11])+int(values[12]))/os.sysconf('SC_CLK_TCK'),
            'rss_mib':int(values[21])*os.sysconf('SC_PAGE_SIZE')/1024**2}


def counter_deltas(before, after):
    old={c['camera_id']:c for c in before['cameras']};new={c['camera_id']:c for c in after['cameras']}
    fields=('frames','attempts','failed_attempts','budget_overruns','missing_source_checks','retry_backoff_checks')
    deltas={};invalid=[]
    for camera in sorted(set(old)|set(new)):
        start=old.get(camera);end=new.get(camera)
        # Session IDs change at replay loops; monotone counters detect restarts.
        if (start is None or end is None or not start.get('processor_run_id') or start.get('processor_run_id')!=end.get('processor_run_id')
                or any(type(start.get(k)) is not int or type(end.get(k)) is not int or end[k]<start[k] for k in fields)):
            invalid.append(camera);continue
        deltas[camera]={key:end[key]-start[key] for key in fields}
    return {'per_camera':deltas,'unverified_cameras':invalid,'total_completed_frames':sum(c['frames'] for c in deltas.values())}


def assess_profile_quality(samples, interval, health_failures, counter_window_valid):
    """Flag interruptions or wall-clock jumps that make aggregate FPS misleading."""
    anomalies=[]
    previous=None
    max_sample_gap=0.0
    for sample in samples:
        elapsed=sample.get('elapsed_seconds')
        if not isinstance(elapsed,(int,float)) or not math.isfinite(elapsed):
            anomalies.append({'kind':'invalid_sample_elapsed'})
            previous=sample
            continue
        if previous is not None:
            previous_elapsed=previous.get('elapsed_seconds')
            gap=elapsed-previous_elapsed if isinstance(previous_elapsed,(int,float)) else None
            if gap is not None and math.isfinite(gap):
                max_sample_gap=max(max_sample_gap,gap)
                if gap<=0:
                    anomalies.append({'kind':'non_monotonic_sample_elapsed','from_elapsed_seconds':previous_elapsed,
                                      'to_elapsed_seconds':elapsed,'gap_seconds':round(gap,3)})
                elif gap>max(interval*2.5,interval+1.0):
                    anomalies.append({'kind':'long_sample_gap','from_elapsed_seconds':previous_elapsed,
                                      'to_elapsed_seconds':elapsed,'gap_seconds':round(gap,3),
                                      'expected_interval_seconds':interval})
                before_ages=previous.get('frame_ages_seconds',{})
                current_ages=sample.get('frame_ages_seconds',{})
                if isinstance(before_ages,dict) and isinstance(current_ages,dict):
                    for camera_id in sorted(set(before_ages)&set(current_ages)):
                        before_age=before_ages[camera_id];current_age=current_ages[camera_id]
                        if (isinstance(before_age,(int,float)) and math.isfinite(before_age)
                                and isinstance(current_age,(int,float)) and math.isfinite(current_age)):
                            age_delta=current_age-before_age
                            discrepancy=age_delta-gap
                            if abs(discrepancy)>max(10.0,interval*5):
                                anomalies.append({'kind':'frame_age_clock_discontinuity','camera_id':camera_id,
                                                  'from_elapsed_seconds':previous_elapsed,
                                                  'to_elapsed_seconds':elapsed,'sample_gap_seconds':round(gap,3),
                                                  'frame_age_delta_seconds':round(age_delta,3),
                                                  'clock_discrepancy_seconds':round(discrepancy,3)})
        previous=sample
    if health_failures:
        anomalies.append({'kind':'health_read_failures','count':health_failures})
    if not counter_window_valid:
        anomalies.append({'kind':'counter_window_unverified'})
    return {'steady_state_rate_valid':not anomalies,
            'steady_state_rate_invalid_reasons':anomalies,
            'max_sample_gap_seconds':round(max_sample_gap,3) if len(samples)>1 else None}


def profile(origin, duration, interval, pid=None):
    started=time.monotonic();first=read_health(origin);first_at=time.monotonic();last=first;last_at=first_at
    first_process=process_stats(pid) if pid is not None else None
    previous_process=first_process;previous_process_at=first_at;process_status='sampled' if first_process else 'not_requested'
    samples=[];failures=0;next_sample=first_at+interval
    while next_sample-started<=duration:
        time.sleep(max(0,next_sample-time.monotonic()))
        began=time.monotonic()
        try:
            health=read_health(origin);last=health;last_at=time.monotonic()
            sample={'elapsed_seconds':round(last_at-started,3),'health_latency_ms':round((last_at-began)*1000,3),
                    'frames':{c['camera_id']:c['frames'] for c in health['cameras']},
                    'statuses':{c['camera_id']:c.get('status') for c in health['cameras']},
                    'frame_ages_seconds':{c['camera_id']:c.get('frame_age_seconds') for c in health['cameras']}}
        except (OSError,ValueError):
            failures+=1;sample={'elapsed_seconds':round(time.monotonic()-started,3),'health_failed':True}
        if previous_process is not None:
            try:
                current=process_stats(pid);now=time.monotonic()
                if current['identity']!=first_process['identity'] or current['cpu_seconds']<previous_process['cpu_seconds']:
                    raise ValueError('Process identity/counters changed')
                sample.update(cpu_percent=round(100*(current['cpu_seconds']-previous_process['cpu_seconds'])/max(now-previous_process_at,.001),3),
                              rss_mib=round(current['rss_mib'],3))
                previous_process=current;previous_process_at=now
            except (OSError,ValueError,IndexError):
                process_status='lost_or_replaced';previous_process=None
        samples.append(sample)
        # Skip late sampler slots rather than enqueueing catch-up requests.
        next_sample+=interval
        while next_sample<=time.monotonic(): next_sample+=interval
    elapsed=last_at-first_at;deltas=counter_deltas(first,last)
    profile_quality=assess_profile_quality(samples,interval,failures,not deltas['unverified_cameras'])
    measured_fps=round(deltas['total_completed_frames']/elapsed,4) if elapsed>0 and not deltas['unverified_cameras'] else None
    return {'version':1,'scope':'Read-only local API/process observation under current desktop load; not a controlled accuracy or browser playback benchmark',
            'conditions':{'api':origin,'requested_seconds':duration,'interval_seconds':interval,'successful_counter_window_seconds':round(elapsed,3),
                          'python':platform.python_version(),'platform':platform.platform(),'logical_cpus':os.cpu_count(),'pid':pid,
                          'process_status':process_status,'process_birth_ticks':first_process['identity'] if first_process else None},
            'sampling':{**deltas,'total_completed_fps':measured_fps,
                        'steady_state_total_completed_fps':measured_fps if profile_quality['steady_state_rate_valid'] else None,
                        'counter_window_valid':not deltas['unverified_cameras'],'health_failures':failures,
                        'profile_quality':profile_quality},
            'health_latency_ms':distribution([s['health_latency_ms'] for s in samples if 'health_latency_ms' in s]),
            'cpu_percent':distribution([s['cpu_percent'] for s in samples if 'cpu_percent' in s]),
            'rss_mib':distribution([s['rss_mib'] for s in samples if 'rss_mib' in s]),
            'first_health':first,'last_health':last,'samples':samples,
            'limitations':['Timing windows contain at most 64 successful attempts per camera; failures have separate counters and last-attempt timing.',
                           'First-success timing is per camera and can include source/model initialization; it is not a controlled cold-start benchmark.',
                           'Budget overruns mean a processing attempt exceeded its scheduled interval; they are not source frames or browser playback drops.',
                           'Sparse replay sampling intentionally skips source frames. VFR/capture drops, INP/LCP/CLS and real plate accuracy are unmeasured.',
                           'CPU percent uses process CPU seconds and can exceed 100%; memory is RSS, not peak resident usage. API restart can invalidate counters.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api',type=api_origin,default='http://127.0.0.1:8001')
    parser.add_argument('--duration',type=float,default=60)
    parser.add_argument('--interval',type=float,default=1)
    parser.add_argument('--pid',type=int,help='Optional Linux API process PID for CPU/RSS; never signals it')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not math.isfinite(args.duration) or not 5<=args.duration<=600: parser.error('duration must be 5–600 seconds')
    if not math.isfinite(args.interval) or not .25<=args.interval<=5 or args.interval>=args.duration: parser.error('interval must be .25–5 seconds and below duration')
    if args.pid is not None and (args.pid<1 or platform.system()!='Linux'): parser.error('pid requires a positive Linux process ID')
    try:result=profile(args.api,args.duration,args.interval,args.pid)
    except (OSError,ValueError,IndexError) as error:parser.exit(1,f'Profile could not start: {error}\n')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(f"{len(result['samples'])} samples; completed FPS={result['sampling']['total_completed_fps']}; output={args.output}")


if __name__=='__main__':main()
