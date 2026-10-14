"""Small Prometheus text exposition over the bounded processor health snapshot."""
import math


def _escape_label(value):
    return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace('"', '\\"')


def _number(value):
    if isinstance(value, bool):
        return '1' if value else '0'
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return str(value)


def render_metrics(cameras, processing_enabled, branches):
    """Render low-cardinality service/camera metrics; never expose observations or identities."""
    lines=[]

    def family(name, help_text, metric_type, samples):
        lines.extend((f'# HELP {name} {help_text}', f'# TYPE {name} {metric_type}'))
        for labels, value in samples:
            number=_number(value)
            if number is None:
                continue
            label_text='{' + ','.join(f'{key}="{_escape_label(item)}"' for key,item in sorted(labels.items())) + '}' if labels else ''
            lines.append(f'{name}{label_text} {number}')

    family('ai26_processing_enabled', 'Whether camera inference processing is enabled.', 'gauge',
           [( {}, processing_enabled )])
    family('ai26_inference_branch_enabled', 'Whether an inference branch is enabled at API startup.', 'gauge',
           [({'branch':'vehicle_person'}, branches.get('vehicle_detection_enabled')),
            ({'branch':'plate_recognition'}, branches.get('plate_recognition_enabled'))])

    counters=(('frames_total','frames','Frames successfully processed.'),
              ('attempts_total','attempts','Source processing attempts.'),
              ('failed_attempts_total','failed_attempts','Failed source processing attempts.'),
              ('budget_overruns_total','budget_overruns','Attempts exceeding the scheduled processing interval.'),
              ('missing_source_checks_total','missing_source_checks','Checks where the configured source file was missing.'),
              ('retry_backoff_checks_total','retry_backoff_checks','Checks skipped while a source retry deadline was active.'))
    for suffix,key,help_text in counters:
        family('ai26_camera_'+suffix,help_text,'counter',
               [({'camera_id':camera.get('camera_id','unknown')},camera.get(key)) for camera in cameras])

    for name,help_text,key in (
        ('ai26_camera_source_available','Whether the configured recorded file exists or a live source has a fresh frame.','source_available'),
        ('ai26_camera_processed_fps','Recent successful camera frame processing rate.','processed_fps'),
        ('ai26_camera_frame_age_seconds','Age of the latest processed frame; absent until a frame has been processed.','frame_age_seconds'),
        ('ai26_camera_queue_depth','Current processor queue depth. The single-owner processor has no growing queue.','queue_depth'),
        ('ai26_camera_sampling_budget_fps','Scheduled total processor sampling budget per camera.','sampling_budget_fps')):
        family(name,help_text,'gauge',
               [({'camera_id':camera.get('camera_id','unknown')},camera.get(key)) for camera in cameras])

    statuses=[]
    for camera in cameras:
        statuses.append(({'camera_id':camera.get('camera_id','unknown'),
                          'status':camera.get('status','unknown')},1))
    family('ai26_camera_status','One-hot camera processor status.', 'gauge', statuses)

    totals=[];phases=[]
    for camera in cameras:
        camera_id=camera.get('camera_id','unknown')
        timing=camera.get('timing') or {}
        for quantile,key in (('0.5','p50_ms'),('0.95','p95_ms'),('1.0','max_ms')):
            summary=timing.get('total') or {}
            if key in summary:
                totals.append(({'camera_id':camera_id,'quantile':quantile},summary[key]))
        for phase,summary in (timing.get('phases') or {}).items():
            if not isinstance(summary,dict):
                continue
            for quantile,key in (('0.5','p50_ms'),('0.95','p95_ms'),('1.0','max_ms')):
                if key in summary:
                    phases.append(({'camera_id':camera_id,'phase':phase,'quantile':quantile},summary[key]))
    family('ai26_camera_sample_duration_ms',
           'Recent successful sample duration quantiles in milliseconds; at most 64 samples per camera.',
           'summary',totals)
    family('ai26_camera_phase_duration_ms',
           'Recent successful phase duration quantiles in milliseconds; at most 64 samples per camera.',
           'summary',phases)
    return '\n'.join(lines)+'\n'
