"""Deterministic association and labeled-metric checks; no model-accuracy claims."""
import importlib.util
import itertools
import random
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from tracking import CentroidTracker, _assignment
from fusion import PlateConsensus

spec=importlib.util.spec_from_file_location('tracker_evaluation',ROOT/'evaluation/evaluate.py')
evaluation=importlib.util.module_from_spec(spec);spec.loader.exec_module(evaluation)


def detection(x,label='car',width=4,height=4):
    return {'label':label,'bbox':[x,0,x+width,height]}


class Association(unittest.TestCase):
    def test_assignment_matches_exhaustive_small_matrices(self):
        rng=random.Random(26)
        for rows in range(1,5):
            columns=rows+2
            for _ in range(12):
                costs=[[rng.randrange(30)/10 for _ in range(columns)] for _ in range(rows)]
                selected=_assignment(costs)
                best=min(sum(costs[i][j] for i,j in enumerate(p)) for p in itertools.permutations(range(columns),rows))
                self.assertAlmostEqual(sum(costs[i][j] for i,j in enumerate(selected)),best)
                self.assertEqual(len(set(selected)),rows)

    def test_global_assignment_avoids_greedy_track_theft(self):
        t=CentroidTracker(max_distance=10)
        first=t.update([detection(0),detection(10)],timestamp=0)
        second=t.update([detection(4),detection(-5)],timestamp=1)
        self.assertEqual([d['track_id'] for d in second],[first[1]['track_id'],first[0]['track_id']])

    def test_motion_keeps_crossing_subjects_separate(self):
        t=CentroidTracker(max_distance=20)
        first=t.update([detection(0),detection(50)],timestamp=0)
        t.update([detection(10),detection(40)],timestamp=1)
        crossed=t.update([detection(20),detection(30)],timestamp=3)
        self.assertEqual([d['track_id'] for d in crossed],[first[1]['track_id'],first[0]['track_id']])

    def test_brief_occlusion_recovers_predicted_motion(self):
        t=CentroidTracker(max_distance=20,max_age_seconds=12)
        initial=t.update([detection(0)],timestamp=0)[0]
        t.update([detection(10)],timestamp=1)
        t.update([],timestamp=2)
        recovered=t.update([detection(30)],timestamp=3)[0]
        self.assertEqual(recovered['track_id'],initial['track_id'])
        self.assertEqual(recovered['track_history'],[(2,2),(12,2),(32,2)])

    def test_elapsed_expiry_prevents_stale_identity_reuse(self):
        t=CentroidTracker(max_distance=20,max_age_seconds=5)
        initial=t.update([detection(0)],timestamp=0)[0]
        later=t.update([detection(0)],timestamp=6)[0]
        self.assertNotEqual(initial['track_id'],later['track_id'])
        self.assertNotIn(initial['track_id'],t.active_ids)

    def test_ambiguous_tracks_retire_and_consensus_abstains(self):
        t=CentroidTracker(max_distance=20)
        old=t.update([detection(0),detection(10)],timestamp=0)
        ambiguous=t.update([detection(5)],timestamp=1)[0]
        self.assertEqual(ambiguous['association_status'],'ambiguous')
        self.assertTrue({d['track_id'] for d in old}.isdisjoint(t.active_ids))
        fusion=PlateConsensus()
        for _ in range(3): fusion.read('CAM-07',ambiguous['track_id'],'KL07AB1234')
        result=fusion.read('CAM-07',ambiguous['track_id'],'KL07AB1234',association_status='ambiguous')
        self.assertEqual(result['identity_status'],'tracking_ambiguous')
        self.assertIsNone(result['fused_plate']);self.assertNotIn(('CAM-07',ambiguous['track_id']),fusion.history)

    def test_character_vote_is_review_only_and_does_not_resolve_conflict(self):
        fusion=PlateConsensus()
        for plate in ('TN22ZZ0007','TN22ZZ0007','TN22ZZ0001','TN22ZZ0007'):
            result=fusion.read('CAM-07',9,plate,confidence=.8)
        self.assertEqual(result['identity_status'],'conflicting')
        self.assertIsNone(result['fused_plate'])
        self.assertEqual(result['character_consensus_candidate'],'TN22ZZ0007')
        diagnostics=result['character_consensus_diagnostics']
        self.assertEqual(diagnostics['reason'],None)
        self.assertEqual(diagnostics['confidence_semantics'],'heuristic_weight_share_not_calibrated_probability')
        self.assertEqual(diagnostics['positions'][-1]['winner_weight_share'],0.75)

    def test_character_vote_abstains_on_tie_and_length_mismatch(self):
        tied=PlateConsensus()
        for plate in ('TN22ZZ0007','TN22ZZ0001','TN22ZZ0002'):
            result=tied.read('CAM-07',1,plate)
        self.assertIsNone(result['character_consensus_candidate'])
        self.assertEqual(result['character_consensus_diagnostics']['reason'],'weak_character_vote')
        lengths=PlateConsensus()
        for plate in ('TN22ZZ0007','TN22ZZ0007','TN22ZZ000'):
            result=lengths.read('CAM-07',1,plate)
        self.assertIsNone(result['character_consensus_candidate'])
        self.assertEqual(result['character_consensus_diagnostics']['reason'],'plate_length_mismatch')

    def test_shape_change_and_class_change_do_not_reuse_track(self):
        t=CentroidTracker()
        old=t.update([detection(0,width=10,height=10)],timestamp=0)[0]
        resized=t.update([detection(0,width=100,height=100)],timestamp=1)[0]
        changed=t.update([detection(0,label='bus',width=100,height=100)],timestamp=2)[0]
        self.assertNotEqual(old['track_id'],resized['track_id'])
        self.assertNotEqual(resized['track_id'],changed['track_id'])

    def test_ordered_finite_clocks_and_same_timestamp(self):
        t=CentroidTracker()
        first=t.update([detection(0)],timestamp=1)[0]
        self.assertEqual(t.update([detection(0)],timestamp=1)[0]['track_id'],first['track_id'])
        for invalid in (0,float('inf'),float('nan')):
            with self.assertRaises(ValueError): t.update([],timestamp=invalid)

    def test_empty_frame_expires_by_missed_bound(self):
        t=CentroidTracker(max_missing=1)
        old=t.update([detection(0)],timestamp=0)[0]
        t.update([],timestamp=1);t.update([],timestamp=2)
        self.assertNotIn(old['track_id'],t.active_ids)


class TrackingMetrics(unittest.TestCase):
    def record(self,index,predicted=1,visible=True,session='a'):
        return {'sample_id':f'{session}-{index}','camera':'CAM-01','session':session,'frame_index':index,'synthetic':True,
                'expected_boxes':[{**detection(0),'identity':'subject'}] if visible else [],
                'predicted_boxes':[{**detection(0),'track_id':predicted}] if predicted is not None else []}

    def test_visible_tracking_loss_and_reacquisition_is_fragment(self):
        r=evaluation.evaluate([self.record(0),self.record(1,None),self.record(2,2)])['tracking']
        self.assertEqual(r['fragmentations'],1);self.assertEqual(r['id_switches'],1)
        self.assertEqual(r['visible_identity_frames'],3);self.assertEqual(r['matched_identity_frames'],2)
        self.assertTrue(r['chronology_verified'])

    def test_unmatched_prefix_or_gt_absence_is_not_fragmentation(self):
        r=evaluation.evaluate([self.record(0,None),self.record(1),self.record(2,None,False),self.record(3,None),self.record(4)])['tracking']
        self.assertEqual(r['fragmentations'],0);self.assertEqual(r['id_switches'],0)

    def test_camera_session_scope_and_frame_order_validation(self):
        r=evaluation.evaluate([self.record(0,1),self.record(0,2,session='b')])['tracking']
        self.assertEqual(r['id_switches'],0)
        with self.assertRaises(ValueError): evaluation.evaluate([self.record(2),self.record(1)])
        missing=self.record(0);missing.pop('session')
        with self.assertRaises(ValueError): evaluation.evaluate([missing])

    def test_missing_order_is_explicitly_unverified(self):
        record=self.record(0);record.pop('frame_index')
        self.assertFalse(evaluation.evaluate([record])['tracking']['chronology_verified'])

class InferenceContract(unittest.TestCase):
    def test_ambiguous_plate_keeps_raw_read_without_reusing_supported_identity(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import numpy as np
        # Exercise real tracking/fusion/normalization/render integration with stub model
        # outputs. No model downloads or inference are needed for this contract.
        fake_torch=SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:False),
                                   set_num_threads=lambda _:None,get_num_threads=lambda:2,__version__='fixture')
        modules={'torch':fake_torch,'fast_alpr':SimpleNamespace(ALPR=lambda **_:None),
                 'ultralytics':SimpleNamespace(YOLO=lambda _:SimpleNamespace())}
        name='inference_tracking_contract'
        spec=importlib.util.spec_from_file_location(name,ROOT/'backend/inference.py')
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,modules): spec.loader.exec_module(module)
        def result(x,plate):
            return SimpleNamespace(detection=SimpleNamespace(bounding_box=SimpleNamespace(x1=x,y1=0,x2=x+4,y2=4)),
                                   ocr=SimpleNamespace(text=plate,confidence=.9))
        plate_outputs=[result(0,'KL07AB1234'),result(10,'TN22ZZ0007')]
        module._alpr=SimpleNamespace(predict=lambda _:plate_outputs)
        for _ in range(3):
            _,reads=module.annotate_plate_frame(np.zeros((100,100,3),dtype=np.uint8),'CAM-07')
        self.assertEqual({r['identity_status'] for r in reads},{'supported'})
        old_ids={r['track_id'] for r in reads}
        plate_outputs[:]=[result(5,'KL07AB1234')]
        _,reads=module.annotate_plate_frame(np.zeros((100,100,3),dtype=np.uint8),'CAM-07')
        self.assertEqual(reads[0]['identity_status'],'tracking_ambiguous')
        self.assertEqual(reads[0]['plate_raw'],'KL07AB1234')
        self.assertNotIn(reads[0]['track_id'],old_ids)
        self.assertTrue(old_ids.isdisjoint(module._plate_trackers['CAM-07'].active_ids))
        self.assertFalse(module._consensus.history)
        import events
        from repository import Repository
        repository=Repository(':memory:')
        try:
            with patch.object(events,'store',repository):
                events.add_events(reads)
                self.assertEqual(len(repository.observations()),1)
                self.assertEqual(events.get_trajectory('KL07AB1234',since=0)['status'],'not_found')
        finally: repository.close()


if __name__=='__main__': unittest.main()
