"""Evaluate explicit labeled JSONL records. Synthetic fixtures never establish model accuracy."""
import argparse
import hashlib
import json
import importlib.util
import re
import math
from pathlib import Path
try:
    from .dataset_manifest import ManifestError, validate_manifest
except ImportError:
    try:
        from dataset_manifest import ManifestError, validate_manifest
    except ImportError:
        spec = importlib.util.spec_from_file_location(
            "dataset_manifest", Path(__file__).with_name("dataset_manifest.py"))
        if spec is None or spec.loader is None:
            raise
        dataset_manifest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dataset_manifest)
        ManifestError, validate_manifest = dataset_manifest.ManifestError, dataset_manifest.validate_manifest


def iou(a,b):
    area=lambda box:max(0,box[2]-box[0])*max(0,box[3]-box[1])
    intersection=area([max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3])])
    union=area(a)+area(b)-intersection
    return intersection/union if union else 0


def _validated_boxes(boxes, field, sample):
    if not isinstance(boxes, list):
        raise ValueError(f'{field} must be a list in sample {sample!r}')
    for index, box in enumerate(boxes):
        if not isinstance(box, dict) or not isinstance(box.get('label'), str) or not box['label'].strip():
            raise ValueError(f'{field}[{index}] needs a non-empty label in sample {sample!r}')
        coords = box.get('bbox')
        if (not isinstance(coords, (list, tuple)) or len(coords) != 4
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in coords)
                or coords[2] < coords[0] or coords[3] < coords[1]):
            raise ValueError(f'{field}[{index}] needs finite, ordered bbox coordinates in sample {sample!r}')
    return boxes


def _box_matches(predictions, ground, threshold=.5):
    """Return a maximum-cardinality one-to-one match set at the IoU threshold."""
    edges = {}
    for pi, prediction in enumerate(predictions):
        candidates = []
        for gi, expected in enumerate(ground):
            if prediction['label'] != expected['label']:
                continue
            score = iou(prediction['bbox'], expected['bbox'])
            if score >= threshold:
                candidates.append((score, gi))
        edges[pi] = [gi for _, gi in sorted(candidates, key=lambda edge: (-edge[0], edge[1]))]

    ground_to_prediction = {}

    def assign(pi, visited):
        for gi in edges[pi]:
            if gi in visited:
                continue
            visited.add(gi)
            if gi not in ground_to_prediction or assign(ground_to_prediction[gi], visited):
                ground_to_prediction[gi] = pi
                return True
        return False

    for pi in range(len(predictions)):
        assign(pi, set())
    return {pi: gi for gi, pi in ground_to_prediction.items()}


def evaluate(records):
    records=list(records)
    if not records:
        raise ValueError('at least one evaluation sample is required')
    if any(not isinstance(record,dict) for record in records):
        raise ValueError('each evaluation sample must be a JSON object')
    seen=set();plate_total=plate_correct=plate_false=plate_unread=0
    tp=fp=fn=detector_samples=0;switches=fragments=0;identities={};track_state={}
    tracking_samples=sequence_samples=ordered_tracking_samples=0;frame_order={}
    tracking_scopes={(r.get('camera'),r.get('session')) for r in records
                     if isinstance(r.get('expected_boxes'),list)
                     and any(isinstance(g,dict) and 'identity' in g for g in r['expected_boxes'])}
    link_tp=link_fp=link_fn=0;rule_tp=rule_fp=rule_fn=0
    passages_expected=passages_predicted=0
    for r in records:
        sample=r['sample_id']
        if not isinstance(sample,str) or not sample.strip():
            raise ValueError('sample_id must be non-empty text')
        if sample in seen: raise ValueError(f'Duplicate sample ID: {sample}')
        seen.add(sample)
        if 'expected_plate' in r:
            plate_total+=1
            prediction=r.get('predicted_plate');expected=r['expected_plate']
            plate_correct+=prediction==expected
            plate_unread+=prediction is None
            plate_false+=prediction is not None and prediction!=expected
        has_expected_boxes='expected_boxes' in r
        has_predicted_boxes='predicted_boxes' in r
        if has_expected_boxes != has_predicted_boxes:
            raise ValueError(f'sample {sample!r} must provide both expected_boxes and predicted_boxes')
        if has_expected_boxes:
            ground=_validated_boxes(r['expected_boxes'],'expected_boxes',sample)
            prediction=_validated_boxes(r['predicted_boxes'],'predicted_boxes',sample)
            detector_samples+=1
        else:
            ground=[];prediction=[]
        labeled=[g for g in ground if 'identity' in g]
        scope=(r.get('camera'),r.get('session'))
        if labeled:
            if any(not isinstance(value,str) or not value.strip() for value in scope):
                raise ValueError('Tracking labels require camera and recording session')
            if len({g['identity'] for g in labeled}) != len(labeled):
                raise ValueError('A ground-truth identity must occur once per frame')
            tracking_samples+=1
        sequence_samples+=scope in tracking_scopes
        if 'frame_index' in r:
            frame=r['frame_index']
            if type(frame) is not int or frame<0: raise ValueError('frame_index must be a nonnegative integer')
            if scope in frame_order and frame<=frame_order[scope]:
                raise ValueError('Frames must be strictly ordered within camera/session')
            frame_order[scope]=frame
            ordered_tracking_samples+=scope in tracking_scopes

        matches=_box_matches(prediction,ground) if has_expected_boxes else {}
        used_p=set(matches);used_g=set(matches.values());matched_boxes={gi:prediction[pi] for pi,gi in matches.items()}
        tp+=len(matches)
        visible={(scope[0],scope[1],g['identity']) for g in labeled}
        # Ground-truth absence ends a visible span; an unlabeled interval is not a
        # measured tracking miss. A fragment needs visible tracked -> missed -> tracked.
        for key,state in track_state.items():
            if key[:2]==scope and key not in visible:
                state['interrupted']=False;state['span_seen']=False
        for gi,g in enumerate(ground):
            if 'identity' not in g: continue
            key=(scope[0],scope[1],g['identity'])
            state=track_state.setdefault(key,{'span_seen':False,'interrupted':False,'visible_frames':0,'tracked_frames':0})
            state['visible_frames']+=1
            p=matched_boxes.get(gi)
            if p is None or p.get('track_id') is None:
                if state['span_seen']: state['interrupted']=True
                continue
            state['tracked_frames']+=1
            if state['span_seen'] and state['interrupted']: fragments+=1
            if key in identities and identities[key]!=p['track_id']: switches+=1
            identities[key]=p['track_id']
            state['span_seen']=True;state['interrupted']=False
        fp+=len(prediction)-len(used_p);fn+=len(ground)-len(used_g)
        for prefix in ('link','rule'):
            expected=r.get('expected_'+prefix);predicted=r.get('predicted_'+prefix)
            if expected is None:continue
            if not isinstance(expected,bool) or not isinstance(predicted,bool):raise ValueError(f'{prefix} requires Boolean labels/predictions')
            if prefix=='link':
                link_tp+=expected and predicted;link_fp+=not expected and predicted;link_fn+=expected and not predicted
            else:
                rule_tp+=expected and predicted;rule_fp+=not expected and predicted;rule_fn+=expected and not predicted
        passages_expected+=r.get('expected_passages',0);passages_predicted+=r.get('predicted_passages',0)
    rate=lambda a,b:round(a/b,4) if b else None
    return {'sample_count':len(records),'synthetic':any(r.get('synthetic',False) for r in records),
            'detector':{'evaluated_sample_count':detector_samples,'tp':tp,'fp':fp,'fn':fn,
                        'precision':rate(tp,tp+fp),'recall':rate(tp,tp+fn),'iou_threshold':.5},
            'plates':{'labeled_samples':plate_total,'exact_matches':plate_correct,'exact_match_rate':rate(plate_correct,plate_total),'false_reads':plate_false,'abstentions':plate_unread},
            'tracking':{'matched_ground_truth_identities':len(identities),'labeled_ground_truth_identities':len(track_state),
                        'id_switches':switches,'fragmentations':fragments,
                        'visible_identity_frames':sum(s['visible_frames'] for s in track_state.values()),
                        'matched_identity_frames':sum(s['tracked_frames'] for s in track_state.values()),
                        'labeled_frame_samples':tracking_samples,'sequence_frame_samples':sequence_samples,
                        'ordered_frame_samples':ordered_tracking_samples,'unverified_frame_samples':sequence_samples-ordered_tracking_samples,
                        'chronology_verified':bool(sequence_samples) and sequence_samples==ordered_tracking_samples},
            'links':{'tp':link_tp,'fp':link_fp,'fn':link_fn,'precision':rate(link_tp,link_tp+link_fp),'recall':rate(link_tp,link_tp+link_fn)},
            'rules':{'tp':rule_tp,'fp':rule_fp,'fn':rule_fn,'precision':rate(rule_tp,rule_tp+rule_fp),'recall':rate(rule_tp,rule_tp+rule_fn)},
            'passages':{'expected':passages_expected,'predicted':passages_predicted,'signed_error':passages_predicted-passages_expected},
            'limitations':['Inputs must be labeled held-out predictions in source-time order; frame_index verifies order when supplied. Fragmentation counts interruptions while ground truth stays visible. This runner does not supply labels or prove split independence. Synthetic records are correctness fixtures only.']}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,help='validated dataset manifest; required for non-synthetic records')
    parser.add_argument('--model-sha256',help='exact detector/OCR bundle SHA-256; required for non-synthetic records')
    args=parser.parse_args();records=[json.loads(line) for line in args.records.read_text().splitlines() if line.strip()]
    real_records=[record for record in records if not record.get('synthetic',False)]
    if real_records and len(real_records)!=len(records):
        parser.error('synthetic and real records cannot be mixed in one evaluation report')
    if real_records and args.manifest is None:
        parser.error('non-synthetic evaluation requires --manifest so test split and source clip can be checked')
    if real_records and (not isinstance(args.model_sha256,str) or not re.fullmatch(r'[0-9a-f]{64}',args.model_sha256)):
        parser.error('non-synthetic evaluation requires --model-sha256 with a lowercase SHA-256 digest')
    if not real_records and args.model_sha256 is not None:
        parser.error('--model-sha256 is only valid for non-synthetic records')
    if real_records:
        for record in real_records:
            if record.get('model_sha256') != args.model_sha256:
                parser.error(f"record {record.get('sample_id')!r} model_sha256 does not match --model-sha256")
    if args.manifest is not None:
        try:
            manifest_report=validate_manifest(args.manifest)
        except ManifestError as error:
            parser.error(f'invalid dataset manifest: {error}')
        if manifest_report['status'] != 'ready':
            parser.error('dataset manifest is incomplete; use labeled clips in all three disjoint splits')
        manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
        clips={clip['clip_id']:clip for clip in manifest['clips']}
        for index,record in enumerate(real_records):
            clip_id=record.get('clip_id')
            if not isinstance(clip_id,str) or clip_id not in clips:
                parser.error(f'record {record.get("sample_id", index)!r} must reference a manifest clip_id')
            clip=clips[clip_id]
            if clip['split'] != 'test':
                parser.error(f'record {record.get("sample_id", index)!r} uses a non-test clip')
            if record.get('camera') != clip['camera_id'] or record.get('session') != clip['session_id']:
                parser.error(f'record {record.get("sample_id", index)!r} camera/session do not match its clip')
    result=evaluate(records)
    result['provenance']={
        'schema_version':1,
        'model_sha256':args.model_sha256,
        'manifest_sha256':hashlib.sha256(args.manifest.read_bytes()).hexdigest() if real_records else None,
        'records_sha256':hashlib.sha256(args.records.read_bytes()).hexdigest(),
        'sample_ids_sha256':hashlib.sha256('\n'.join(sorted(record['sample_id'] for record in records)).encode()).hexdigest(),
        'test_split_only':bool(real_records),
        'record_count':len(records),
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{len(records)} records evaluated; synthetic={result["synthetic"]}; output={args.output}')
