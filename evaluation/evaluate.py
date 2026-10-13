"""Evaluate explicit labeled JSONL records. Synthetic fixtures never establish model accuracy."""
import argparse
import json
from pathlib import Path
from dataset_manifest import ManifestError, validate_manifest


def iou(a,b):
    area=lambda box:max(0,box[2]-box[0])*max(0,box[3]-box[1])
    intersection=area([max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3])])
    union=area(a)+area(b)-intersection
    return intersection/union if union else 0


def evaluate(records):
    seen=set();plate_total=plate_correct=plate_false=plate_unread=0
    tp=fp=fn=0;switches=fragments=0;identities={};track_state={}
    tracking_samples=sequence_samples=ordered_tracking_samples=0;frame_order={}
    tracking_scopes={(r.get('camera'),r.get('session')) for r in records if any('identity' in g for g in r.get('expected_boxes',[]))}
    link_tp=link_fp=link_fn=0;rule_tp=rule_fp=rule_fn=0
    passages_expected=passages_predicted=0
    for r in records:
        sample=r['sample_id']
        if sample in seen: raise ValueError(f'Duplicate sample ID: {sample}')
        seen.add(sample)
        if 'expected_plate' in r:
            plate_total+=1
            prediction=r.get('predicted_plate');expected=r['expected_plate']
            plate_correct+=prediction==expected
            plate_unread+=prediction is None
            plate_false+=prediction is not None and prediction!=expected
        ground=r.get('expected_boxes',[]);prediction=r.get('predicted_boxes',[])
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

        matches=[]
        for pi,p in enumerate(prediction):
            for gi,g in enumerate(ground):
                if p['label']==g['label']: matches.append((iou(p['bbox'],g['bbox']),pi,gi))
        used_p=set();used_g=set();matched_boxes={}
        for score,pi,gi in sorted(matches,reverse=True):
            if score<.5 or pi in used_p or gi in used_g: continue
            used_p.add(pi);used_g.add(gi);tp+=1
            matched_boxes[gi]=prediction[pi]
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
            'detector':{'tp':tp,'fp':fp,'fn':fn,'precision':rate(tp,tp+fp),'recall':rate(tp,tp+fn),'iou_threshold':.5},
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
    args=parser.parse_args();records=[json.loads(line) for line in args.records.read_text().splitlines() if line.strip()]
    real_records=[record for record in records if not record.get('synthetic',False)]
    if real_records and args.manifest is None:
        parser.error('non-synthetic evaluation requires --manifest so test split and source clip can be checked')
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
    result=evaluate(records);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{len(records)} records evaluated; synthetic={result["synthetic"]}; output={args.output}')
