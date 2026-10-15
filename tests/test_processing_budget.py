"""Scheduler fairness, bounded telemetry and read-only profiling contracts."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
os.environ['AI26_PROCESSING_ENABLED']='0'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import numpy as np
import processing
spec=importlib.util.spec_from_file_location('runtime_profile',Path(__file__).resolve().parents[1]/'evaluation/profile_runtime.py')
profiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(profiler)


class Clock:
    def __init__(self):self.now=0
    def monotonic(self):return self.now
    def sleep(self,value):self.now+=value


class Budget(unittest.TestCase):
    def processor(self,ids):return processing.Processor(cameras=[{'id':f'CAM-{i:02d}','kind':'vehicle'} for i in ids],rate=2)
    def loop(self,p,work,waits):
        clock=Clock();seen=[];stopped=False
        def step(camera):
            seen.append(camera['id']);attempt,delay=work[camera['id']];clock.sleep(delay);return attempt
        def wait(delay):
            nonlocal stopped
            waits.append(delay);clock.sleep(delay)
            if len(seen)>=len(p.cameras):stopped=True
        p.stop_event=SimpleNamespace(is_set=lambda:stopped,wait=wait)
        with patch.object(processing.time,'monotonic',side_effect=clock.monotonic),patch.object(p,'step',side_effect=step):p.run()
        return seen,clock.now
    def test_missing_cameras_do_not_spend_slots_and_available_order_is_fair(self):
        p=self.processor([1,7,2,8,3,9]);waits=[]
        work={c['id']:(c['id'] in ('CAM-01','CAM-02','CAM-03'),.1 if c['id'] in ('CAM-01','CAM-02','CAM-03') else 0) for c in p.cameras}
        # Stop after the one sweep even when its final camera is missing.
        clock=Clock();seen=[]
        def step(camera):seen.append(camera['id']);attempt,delay=work[camera['id']];clock.sleep(delay);return attempt
        def wait(delay):waits.append(delay);clock.sleep(delay)
        p.stop_event=SimpleNamespace(is_set=lambda:len(seen)>=len(p.cameras),wait=wait)
        with patch.object(processing.time,'monotonic',side_effect=clock.monotonic),patch.object(p,'step',side_effect=step):p.run()
        self.assertEqual(seen,[c['id'] for c in p.cameras]);self.assertEqual(len(waits),3);self.assertAlmostEqual(clock.now,1.5)
    def test_all_missing_or_backoff_sweep_sleeps_and_stop_is_bounded(self):
        p=self.processor([7,8,9]);waits=[]
        seen,elapsed=self.loop(p,{c['id']:(False,0) for c in p.cameras},waits)
        self.assertEqual(len(seen),3);self.assertEqual(waits,[1]);self.assertEqual(elapsed,1)
    def test_over_budget_work_does_not_enqueue_catch_up_and_failures_spend_a_slot(self):
        p=self.processor([1,2]);waits=[]
        seen,elapsed=self.loop(p,{'CAM-01':(True,.8),'CAM-02':(True,.1)},waits)
        self.assertEqual(len(seen),2);self.assertEqual(waits[0],0);self.assertAlmostEqual(waits[1],.4);self.assertAlmostEqual(elapsed,1.3)
    def test_real_missing_and_retry_checks_do_not_count_as_attempts(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'clip';p=self.processor([1]);p.source=lambda _:path
            p.decode_next['CAM-01']=9
            self.assertFalse(p.step(p.cameras[0]));self.assertNotIn('CAM-01',p.decode_next)
            path.write_bytes(b'fixture');p.retry_at['CAM-01']=processing.time.time()+20
            self.assertFalse(p.step(p.cameras[0]));h=p.health()[0]
            self.assertEqual(h['missing_source_checks'],1);self.assertEqual(h['retry_backoff_checks'],1);self.assertEqual(h['attempts'],0);self.assertIsNone(h['timing']['total'])
    def test_success_and_failure_timings_are_separate_and_no_health_accumulation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'clip';path.write_bytes(b'fixture');p=self.processor([1]);p.source=lambda _:path
            clock=Clock()
            def annotate(frame,*args):clock.sleep(.6);return frame,[]
            p.annotator=annotate
            cap=SimpleNamespace(isOpened=lambda:True,get=lambda k:25 if k==processing.cv2.CAP_PROP_FPS else 1000,set=lambda *args:True,
                                read=lambda:(True,np.zeros((20,20,3),dtype=np.uint8)),release=Mock())
            with patch.object(processing.cv2,'VideoCapture',return_value=cap),patch.object(processing,'store',Mock()),patch.object(processing,'add_events',return_value=0),patch.object(processing.time,'monotonic',side_effect=clock.monotonic):
                self.assertTrue(p.step(p.cameras[0]));p.annotator=Mock(side_effect=OSError('Synthetic failure'))
                with self.assertLogs(processing.log,level='ERROR'):self.assertTrue(p.step(p.cameras[0]))
            for _ in range(4):h=p.health()[0]
            self.assertEqual(h['frames'],1);self.assertEqual(h['attempts'],2);self.assertEqual(h['failed_attempts'],1);self.assertEqual(h['budget_overruns'],1)
            self.assertEqual(h['timing']['successful_samples'],1);self.assertEqual(h['timing']['first_success']['phases_ms']['inference'],600)
            self.assertFalse(h['last_attempt']['succeeded']);self.assertEqual(set(h['timing']['phases']),{'source','decode','inference','artifacts','persistence','jpeg'})
    def test_timing_window_is_bounded_and_first_sample_remains(self):
        p=self.processor([1]);phases={k:0 for k in ('source','decode','inference','artifacts','persistence','jpeg')}
        for i in range(80):
            with patch.object(processing.time,'monotonic',return_value=i/1000):p.record_attempt('CAM-01',0,phases,True)
        h=p.health()[0];self.assertEqual(h['attempts'],80);self.assertEqual(h['timing']['successful_samples'],64)
        self.assertEqual(h['timing']['first_success']['total_ms'],0);self.assertEqual(h['timing']['total'],{'p50_ms':47,'p95_ms':76,'max_ms':79})
    def test_fps_uses_monotonic_elapsed_not_adjusted_wall_clock(self):
        p=self.processor([1]);p.state['CAM-01']['frames']=10;p.started_monotonic=100
        with patch.object(processing.time,'monotonic',return_value=105),patch.object(processing.time,'time',return_value=p.started-100):
            self.assertEqual(p.health()[0]['processed_fps'],2)


class RuntimeProfile(unittest.TestCase):
    def health(self,frames=0,run='same'):
        return {'cameras':[{'camera_id':'CAM-01','processor_run_id':run,'frames':frames,'attempts':frames,'failed_attempts':0,'budget_overruns':0,
                            'missing_source_checks':0,'retry_backoff_checks':0,'status':'processing','frame_age_seconds':1}]}
    def test_origin_and_health_validation_reject_unsafe_or_unbounded_input(self):
        for origin in ('https://127.0.0.1:8001','http://example.com','http://user:secret@localhost','http://localhost/path','http://localhost/?key=x','http://localhost:bad'):
            with self.assertRaises(argparse.ArgumentTypeError):profiler.api_origin(origin)
        self.assertEqual(profiler.api_origin('http://127.0.0.1:8001/'),'http://127.0.0.1:8001')
        class Response:
            def __init__(self,content):self.content=content
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,bound):return self.content[:bound]
        invalid_age=self.health()['cameras'][0].copy();invalid_age['frame_age_seconds']=float('nan')
        for body in (b'x'*(profiler.MAX_RESPONSE_BYTES+1),json.dumps({'cameras':[self.health()['cameras'][0]]*2}).encode(),json.dumps({'cameras':[{'camera_id':'CAM-01','frames':False}]}).encode(),json.dumps({'cameras':[invalid_age]}).encode()):
            with patch.object(profiler.urllib.request,'urlopen',return_value=Response(body)):
                with self.assertRaises(ValueError):profiler.read_health('http://localhost:8001')
    def test_restart_or_missing_counter_marks_window_unverified(self):
        first=self.health(100);last=self.health(200,'new')
        self.assertEqual(profiler.counter_deltas(first,last)['unverified_cameras'],['CAM-01'])
        last=self.health(99);self.assertEqual(profiler.counter_deltas(first,last)['total_completed_frames'],0)
        last=self.health(101);del last['cameras'][0]['attempts'];self.assertEqual(profiler.counter_deltas(first,last)['unverified_cameras'],['CAM-01'])
    def test_sampler_recovers_from_health_outage_and_marks_pid_reuse(self):
        clock=Clock();reads=[self.health(1),self.health(2),OSError('Synthetic outage'),self.health(3),self.health(4),self.health(5)]
        process=[{'identity':10,'cpu_seconds':1,'rss_mib':100},{'identity':10,'cpu_seconds':1.5,'rss_mib':101},{'identity':11,'cpu_seconds':2,'rss_mib':102}]
        with patch.object(profiler,'read_health',side_effect=reads),patch.object(profiler,'process_stats',side_effect=process),patch.object(profiler.time,'monotonic',side_effect=clock.monotonic),patch.object(profiler.time,'sleep',side_effect=clock.sleep):
            result=profiler.profile('http://localhost:8001',5,1,12)
        self.assertEqual(result['sampling']['health_failures'],1);self.assertEqual(result['sampling']['total_completed_frames'],4)
        self.assertEqual(result['conditions']['process_status'],'lost_or_replaced');self.assertEqual(result['cpu_percent']['samples'],1);self.assertEqual(len(result['samples']),5)
        self.assertFalse(result['sampling']['profile_quality']['steady_state_rate_valid'])
    def test_procfs_parses_parenthesized_process_name_and_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'12';path.mkdir();values=['0']*22;values[11]='100';values[12]='50';values[19]='999';values[21]='256'
            (path/'stat').write_text('12 (odd ) process) '+' '.join(values))
            result=profiler.process_stats(12,Path(folder));self.assertEqual(result['identity'],999);self.assertGreater(result['rss_mib'],0)
    def test_late_sampler_skips_slots_and_never_catches_up(self):
        clock=Clock();calls=[]
        def health(*args):calls.append(clock.now);clock.sleep(2 if calls else 0);return self.health(len(calls))
        with patch.object(profiler,'read_health',side_effect=health),patch.object(profiler.time,'monotonic',side_effect=clock.monotonic),patch.object(profiler.time,'sleep',side_effect=clock.sleep):
            result=profiler.profile('http://localhost:8001',8,1)
        self.assertEqual(calls,[0,3,6]);self.assertEqual(len(result['samples']),2)
        self.assertFalse(result['sampling']['profile_quality']['steady_state_rate_valid'])
        self.assertEqual(result['sampling']['steady_state_total_completed_fps'],None)

    def test_profile_quality_rejects_wall_clock_jumps_and_accepts_continuous_samples(self):
        continuous=[
            {'elapsed_seconds':1.0,'frame_ages_seconds':{'CAM-01':1.0}},
            {'elapsed_seconds':3.0,'frame_ages_seconds':{'CAM-01':0.5}},
            {'elapsed_seconds':5.0,'frame_ages_seconds':{'CAM-01':2.5}},
        ]
        quality=profiler.assess_profile_quality(continuous,2,0,True)
        self.assertTrue(quality['steady_state_rate_valid'])
        self.assertEqual(quality['max_sample_gap_seconds'],2.0)

        interrupted=[
            {'elapsed_seconds':184.0,'frame_ages_seconds':{'CAM-01':1.4}},
            {'elapsed_seconds':206.0,'frame_ages_seconds':{'CAM-01':2668.8}},
        ]
        quality=profiler.assess_profile_quality(interrupted,2,0,True)
        self.assertFalse(quality['steady_state_rate_valid'])
        self.assertEqual({item['kind'] for item in quality['steady_state_rate_invalid_reasons']},
                         {'long_sample_gap','frame_age_clock_discontinuity'})
        self.assertEqual(quality['max_sample_gap_seconds'],22.0)
        backwards=profiler.assess_profile_quality([
            {'elapsed_seconds':2.0,'frame_ages_seconds':{}},
            {'elapsed_seconds':1.0,'frame_ages_seconds':{}},
        ],2,0,True)
        self.assertFalse(backwards['steady_state_rate_valid'])
        self.assertEqual(backwards['steady_state_rate_invalid_reasons'][0]['kind'],'non_monotonic_sample_elapsed')

if __name__=='__main__':unittest.main()
