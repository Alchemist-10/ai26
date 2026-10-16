"""Regression/contract tests use isolated storage and deterministic fixtures, never live data."""
import asyncio
from contextlib import nullcontext
import sqlite3
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

os.environ['AI26_PROCESSING_ENABLED']='0'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import numpy as np
from fastapi.testclient import TestClient
import events
import main
import processing
import artifacts
import stream
import nlquery
from source_clock import normalize_recording_clock, source_capture_clock_fields
from repository import Repository, canonical_json
from fusion import PlateConsensus
from maintenance import Maintenance
from report_signing import generate_key_pair, verify_report

class Reliability(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'test.sqlite3'
        self.repo=Repository(self.path)
        for module in (events,main,processing):
            p=patch.object(module,'store',self.repo);p.start();self.addCleanup(p.stop)
        p=patch.object(artifacts,'ROOT',Path(self.folder.name)/'artifacts');p.start();self.addCleanup(p.stop)
        self.addCleanup(lambda:self.repo.close())
        self.client=TestClient(main.app)
        self.now=time.time()

    def plate(self,camera='CAM-07',ts=None,plate='KL07AB1234',**extra):
        return {'camera_id':camera,'kind':'plate','plate':plate,'plate_norm':plate,'plate_raw':plate,
                'confidence':.9,'bbox':[0,0,20,20],'ts':self.now if ts is None else ts,**extra}

    def vehicle(self,ts=None,track=1,**extra):
        return {'camera_id':'CAM-01','kind':'vehicle','label':'car','track_id':track,'session_id':'test-session',
                'confidence':.9,'bbox':[10,10,30,30],'frame_size':[100,100],'ts':self.now if ts is None else ts,**extra}

    def test_idle_expiry_preserves_durable_history(self):
        events.add_events([self.plate()])
        with patch.object(events.time,'time',return_value=self.now+301):
            self.assertEqual(events.get_events(),[])
            self.assertEqual(events.stats()['total_events'],0)
        self.assertEqual(len(events.get_events(since=0)),1)

    def test_out_of_order_window_filter(self):
        events.add_events([self.plate(),self.plate('CAM-08',self.now-400)])
        self.assertEqual(len(events.get_events()),1)

    def test_retry_idempotency_and_restart(self):
        event=self.vehicle(frame_id=42)
        self.assertEqual(events.add_events([event]),1)
        self.assertEqual(events.add_events([event]),0)
        reopened=Repository(self.path)
        try:self.assertEqual(len(reopened.observations()),1)
        finally:reopened.close()

    def test_one_vehicle_six_frames_is_one_passage(self):
        events.add_events([self.vehicle(self.now-i*.1,frame_id=i) for i in range(6)])
        self.assertEqual(events.stats()['total_events'],6)
        self.assertEqual(events.stats()['vehicle_passages'],1)
        self.assertEqual(events.derive_alerts(),[])

    def test_plate_votes_isolated_and_conflicts_abstain(self):
        fusion=PlateConsensus()
        for _ in range(3): result=fusion.read('CAM-07',1,'KL07AB1234')
        self.assertEqual(result['fused_plate'],'KL07AB1234')
        b=fusion.read('CAM-07',2,'TN22ZZ0007')
        self.assertEqual(b['identity_status'],'tentative');self.assertIsNone(b['fused_plate'])
        conflict=fusion.read('CAM-07',1,'TN22ZZ0007')
        self.assertEqual(conflict['identity_status'],'conflicting');self.assertIsNone(conflict['fused_plate'])
        fusion.reset('CAM-07');self.assertEqual(len(fusion.history),0)

    def test_conflicting_track_not_used_for_trajectory(self):
        events.add_events([self.plate(track_id=1,session_id='a',identity_status='supported'),
                           self.plate(ts=self.now+1,track_id=1,session_id='a',plate='TN22ZZ0007',identity_status='conflicting')])
        self.assertEqual(events.get_trajectory('KL07AB1234',0)['status'],'not_found')

    def test_equal_timestamps_http_and_evidence(self):
        events.add_events([self.plate(),self.plate('CAM-08')])
        response=self.client.get('/api/trajectory/KL07AB1234')
        self.assertEqual(response.status_code,200)
        self.assertIsNone(response.json()['rejected_links'][0]['implied_speed_kmh'])
        report=self.client.post('/api/evidence/KL07AB1234')
        self.assertEqual(report.status_code,200)

    def test_mixed_route_requires_review(self):
        for camera in ('CAM-07','CAM-08','CAM-09'):
            config=self.repo.camera_configuration(camera)
            self.repo.update_camera(camera,{**config,'expected_revision':config['revision'],'location_confirmed':True,
                'reviewer':'fixture','reason':'configure deterministic route fixture'},self.now)
        self.repo.put_camera_pair_constraint({'from_camera_id':'CAM-07','to_camera_id':'CAM-08',
            'min_travel_seconds':0,'max_travel_seconds':3600,'enabled':True,'reviewer':'fixture','reason':'reachable'},self.now)
        self.repo.put_camera_pair_constraint({'from_camera_id':'CAM-08','to_camera_id':'CAM-09',
            'min_travel_seconds':0,'max_travel_seconds':3600,'enabled':False,'reviewer':'fixture','reason':'disconnected'},self.now)
        result=events.build_trajectory([self.plate(ts=self.now-121),self.plate('CAM-08',self.now-1),self.plate('CAM-09')])
        self.assertEqual(len(result['accepted_links']),1)
        self.assertEqual(len(result['rejected_links']),1)
        self.assertEqual(result['status'],'review_required')

    def test_replay_time_not_physical_travel_claim(self):
        result=events.build_trajectory([self.plate(ts=self.now-120,time_basis='replay_clock'),self.plate('CAM-08',time_basis='replay_clock')])
        self.assertEqual(result['accepted_links'],[])
        self.assertEqual(len(result['candidate_links']),1)
        self.assertIsNone(result['candidate_links'][0]['implied_speed_kmh'])

    def test_live_arrival_clock_is_not_physical_cross_camera_travel_time(self):
        for camera in ('CAM-07','CAM-08'):
            config=self.repo.camera_configuration(camera)
            self.repo.update_camera(camera,{**config,'expected_revision':config['revision'],'location_confirmed':True,
                'reviewer':'fixture','reason':'configure deterministic live-clock fixture'},self.now)
        self.repo.put_camera_pair_constraint({'from_camera_id':'CAM-07','to_camera_id':'CAM-08',
            'min_travel_seconds':0,'max_travel_seconds':3600,'enabled':True,'reviewer':'fixture','reason':'fixture window'},self.now)
        result=events.build_trajectory([
            self.plate(ts=self.now-120,source_mode='live',time_basis='capture_arrival_clock'),
            self.plate('CAM-08',self.now,source_mode='live',time_basis='capture_arrival_clock'),
        ])
        self.assertEqual(result['accepted_links'],[])
        self.assertEqual(result['rejected_links'],[])
        self.assertEqual(len(result['candidate_links']),1)
        link=result['candidate_links'][0]
        self.assertIsNone(link['implied_speed_kmh'])
        self.assertEqual(link['time_bases'],['capture_arrival_clock','capture_arrival_clock'])
        self.assertIn('synchronized capture-time calibration unavailable',link['reason'])

    def test_unconfigured_pair_stays_candidate_and_constraint_window_is_enforced(self):
        first=self.plate(ts=self.now-120)
        second=self.plate('CAM-08',self.now)
        missing=events.build_trajectory([first,second])
        self.assertEqual(missing['accepted_links'],[])
        self.assertIn('window is missing',missing['candidate_links'][0]['reason'])
        for camera in ('CAM-07','CAM-08'):
            config=self.repo.camera_configuration(camera)
            self.repo.update_camera(camera,{**config,'expected_revision':config['revision'],'location_confirmed':True,
                'reviewer':'fixture','reason':'configure deterministic route fixture'},self.now)
        self.repo.put_camera_pair_constraint({'from_camera_id':'CAM-07','to_camera_id':'CAM-08',
            'min_travel_seconds':180,'max_travel_seconds':300,'enabled':True,'reviewer':'fixture','reason':'bounded test window'},self.now)
        outside=events.build_trajectory([first,second])
        self.assertEqual(outside['accepted_links'],[])
        self.assertIn('outside the configured',outside['rejected_links'][0]['reason'])
        self.repo.put_camera_pair_constraint({'from_camera_id':'CAM-07','to_camera_id':'CAM-08',
            'min_travel_seconds':0,'max_travel_seconds':300,'enabled':True,'reviewer':'fixture','reason':'revision check'},self.now)
        config=self.repo.camera_configuration('CAM-07')
        self.repo.update_camera('CAM-07',{**config,'expected_revision':config['revision'],'location':'Updated test location',
            'reviewer':'fixture','reason':'ensure old route windows go stale'},self.now)
        stale=events.build_trajectory([first,second])
        self.assertEqual(stale['accepted_links'],[])
        self.assertIn('different location revisions',stale['candidate_links'][0]['reason'])

    def test_unknown_camera_and_missing_source(self):
        for route in ['video','stream','snapshot']:
            self.assertEqual(self.client.get(f'/api/{route}/NO-CAMERA').status_code,404)
            self.assertEqual(self.client.get(f'/api/{route}/CAM-07').status_code,404)
        catalog=self.client.get('/api/cameras').json()
        self.assertEqual(sum(c['source_available'] for c in catalog),6)

    def test_health_reports_recorded_sources_while_processing_is_paused(self):
        health=self.client.get('/api/health').json()
        self.assertFalse(health['processing_enabled'])
        availability={camera['camera_id']:camera['source_available'] for camera in health['cameras']}
        self.assertEqual(sum(availability.values()),6)
        self.assertEqual([camera for camera,available in availability.items() if not available],
                         ['CAM-07','CAM-08','CAM-09'])

    def test_question_validation(self):
        for body in [{},{'question':None},{'question':123},{'question':True},{'question':' '},{'question':'x'*501}]:
            self.assertEqual(self.client.post('/api/nlquery',json=body).status_code,422)
        self.assertEqual(self.client.post('/api/nlquery',json={'question':'busiest camera'}).status_code,200)

    def test_invalid_plate_and_time_filters(self):
        self.assertEqual(self.client.get('/api/trajectory/garbage').status_code,422)
        for query in ['since=nan','since=inf','since=5&until=2','limit=0']:
            self.assertEqual(self.client.get('/api/events?'+query).status_code,422)

    def test_empty_evidence_rejected(self):
        self.assertEqual(self.client.post('/api/evidence/DL07ZZ9999').status_code,409)

    def test_failed_raw_reads_retained_without_becoming_identity(self):
        events.add_events([self.plate(plate='',plate_norm='',plate_raw='?L 07 ??',identity_status='invalid',track_id=1,session_id='ocr',frame_id=1)])
        raw=self.repo.observations()[0]
        self.assertEqual(raw['plate_raw'],'?L 07 ??');self.assertIsNone(raw['plate_norm'])
        self.assertEqual(events.get_trajectory('KL07AB1234',0)['status'],'not_found')
        self.assertEqual(events.derive_alerts(),[])

    def test_report_includes_tentative_and_failed_reads_of_supported_track(self):
        shared={'track_id':1,'session_id':'ocr'}
        events.add_events([self.plate(ts=self.now-2,frame_id=1,identity_status='tentative',**shared),
                           self.plate(ts=self.now-1,frame_id=2,identity_status='supported',**shared),
                           self.plate(frame_id=3,plate='TN22ZZ0007',identity_status='low_confidence',confidence=.2,**shared)])
        report=events.evidence_report('KL07AB1234',self.now-10,self.now+1)
        self.assertEqual(len(report['trajectory']['observations']),1)
        self.assertEqual(report['raw_read_count'],3)
        printed=self.client.get('/api/reports/'+report['report_id']+'/print').text
        self.assertIn('Supporting raw reads (3)',printed)
        self.assertIn('low_confidence',printed);self.assertIn('TN22ZZ0007',printed)

    def test_report_refuses_to_silently_truncate_reads(self):
        events.add_events([self.plate()])
        with patch.object(self.repo,'reads_for_passages',return_value=([],5001)):
            self.assertEqual(self.client.post('/api/evidence/KL07AB1234').status_code,409)

    def test_passage_count_requires_an_observation_inside_interval(self):
        events.add_events([self.vehicle(self.now-10,frame_id=1),self.vehicle(self.now,frame_id=2)])
        self.assertEqual(events.stats(since=self.now-8,until=self.now-2)['vehicle_passages'],0)

    def test_oversized_artifact_package_is_rejected(self):
        fake={**artifacts.save_image(np.zeros((30,30,3),dtype=np.uint8),'plate-crop'),'size':65*1024*1024}
        events.add_events([self.plate(artifacts=[fake])]);report=events.evidence_report('KL07AB1234')
        self.assertEqual(self.client.get('/api/reports/'+report['report_id']+'/package').status_code,413)

    def test_evidence_snapshot_hash_download_and_print(self):
        events.add_events([self.plate()])
        report=self.client.post('/api/evidence/KL07AB1234').json()
        digest=report['package_hash']
        unsigned={k:v for k,v in report.items() if k!='package_hash'}
        self.assertEqual(digest,hashlib.sha256(canonical_json(unsigned).encode()).hexdigest())
        events.add_events([self.plate('CAM-08',self.now+1)])
        loaded=self.client.get('/api/reports/'+report['report_id'])
        self.assertEqual(loaded.json(),report)
        printed=self.client.get('/api/reports/'+report['report_id']+'/print').text
        self.assertIn(digest,printed);self.assertNotIn('Blue city bus',printed)
        package=self.client.get('/api/reports/'+report['report_id']+'/package')
        with zipfile.ZipFile(io.BytesIO(package.content)) as z:self.assertEqual(json.loads(z.read('manifest.json')),report)

    def test_signed_evidence_report_survives_exports_and_verifies_offline(self):
        events.add_events([self.plate()])
        private=Path(self.folder.name)/'report-signing-private.pem'
        public=Path(self.folder.name)/'report-signing-public.pem'
        generate_key_pair(private,public)
        with patch.dict(os.environ,{'AI26_EVIDENCE_SIGNING_PRIVATE_KEY_FILE':str(private)}):
            response=self.client.post('/api/evidence/KL07AB1234')
            self.assertEqual(response.status_code,200)
            report=response.json()
            self.assertEqual(report['version'],5)
            self.assertEqual(verify_report(report,public)['status'],'valid')
            downloaded=self.client.get('/api/reports/'+report['report_id']).json()
            self.assertEqual(downloaded['signature'],report['signature'])
            with zipfile.ZipFile(io.BytesIO(self.client.get('/api/reports/'+report['report_id']+'/package').content)) as package:
                self.assertEqual(json.loads(package.read('manifest.json'))['signature'],report['signature'])
            printed=self.client.get('/api/reports/'+report['report_id']+'/print').text
            self.assertIn(report['signature']['key_fingerprint_sha256'],printed)
            reads=self.repo.db.execute("SELECT action,subject FROM audit WHERE action='report_read'").fetchall()
            self.assertEqual(len(reads),3)
            self.assertEqual({row['subject'] for row in reads},{report['report_id']})
            self.assertEqual(self.repo.verify_audit_chain()['status'],'valid')

    def test_prometheus_metrics_export_bounded_processor_health_without_event_data(self):
        camera={'camera_id':'CAM-01','status':'error"\ncheck','frames':7,'attempts':4,'failed_attempts':2,
                'budget_overruns':1,'missing_source_checks':3,'retry_backoff_checks':4,'source_available':False,
                'processed_fps':.5,'frame_age_seconds':None,'queue_depth':0,'sampling_budget_fps':2,
                'timing':{'total':{'p50_ms':10,'p95_ms':30,'max_ms':40},
                          'phases':{'decode':{'p50_ms':2,'p95_ms':5,'max_ms':7}}}}
        with patch.object(main.processor,'health',return_value=[camera]), \
             patch.object(main,'camera_source',return_value=Path('/missing/CAM-01.mp4')):
            response=self.client.get('/api/metrics')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.headers['content-type'].startswith('text/plain; version=0.0.4'))
        body=response.text
        self.assertIn('ai26_camera_frames_total{camera_id="CAM-01"} 7',body)
        self.assertIn('ai26_camera_failed_attempts_total{camera_id="CAM-01"} 2',body)
        self.assertIn('ai26_camera_status{camera_id="CAM-01",status="error\\\"\\ncheck"} 1',body)
        self.assertIn('ai26_camera_sample_duration_ms{camera_id="CAM-01",quantile="0.95"} 30',body)
        self.assertIn('ai26_camera_phase_duration_ms{camera_id="CAM-01",phase="decode",quantile="0.5"} 2',body)
        self.assertNotIn('frame_age_seconds{camera_id="CAM-01"}',body)
        self.assertNotIn('ABC1234',body)

    def test_configured_but_invalid_signing_key_fails_report_creation(self):
        events.add_events([self.plate()])
        with patch.dict(os.environ,{'AI26_EVIDENCE_SIGNING_PRIVATE_KEY_FILE':str(Path(self.folder.name)/'missing.pem')}):
            response=self.client.post('/api/evidence/KL07AB1234')
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['error']['message'],'Evidence signing is configured but the signing key is unavailable or invalid')

    def test_expired_report_inaccessible(self):
        events.add_events([self.plate()]);report=events.evidence_report('KL07AB1234')
        with patch.object(main.time,'time',return_value=report['expires_at']+1):
            self.assertEqual(self.client.get('/api/reports/'+report['report_id']).status_code,404)

    def test_report_lease_survives_source_age_and_expires(self):
        ref=artifacts.save_image(np.zeros((30,30,3),dtype=np.uint8),'plate-crop')
        path=artifacts.ROOT/(ref['sha256']+'.jpg')
        os.utime(path,(self.now-8*86400,self.now-8*86400))
        events.add_events([self.plate(artifacts=[ref])])
        report=events.evidence_report('KL07AB1234')
        Maintenance(self.repo).run_once()
        self.assertTrue(path.is_file())
        self.assertEqual(self.client.get(ref['url']).status_code,200)
        self.assertEqual(self.client.get('/api/reports/'+report['report_id']+'/package').status_code,200)
        Maintenance(self.repo).run_once(report['expires_at']+1)
        self.assertFalse(path.exists())
        self.assertEqual(self.repo.protected_artifacts(report['expires_at']+1),set())
        self.assertIsNone(self.repo.report(report['report_id'],report['expires_at']+1))

    def test_observation_retention_period_is_operator_configurable(self):
        fake_repository=Mock()
        fake_repository.lock=nullcontext()
        fake_repository.protected_artifacts.return_value=set()
        with patch.dict(os.environ,{'AI26_OBSERVATION_RETENTION_DAYS':'30',
                                    'AI26_TRAFFIC_RETENTION_DAYS':'60'}), \
             patch('maintenance.cleanup_artifacts') as cleanup_artifacts:
            janitor=Maintenance(fake_repository)
            janitor.run_once(now=self.now)
        self.assertEqual(janitor.retention_days,30)
        self.assertEqual(janitor.traffic_retention_days,60)
        fake_repository.cleanup.assert_called_once_with(self.now-30*86400,self.now,60)
        cleanup_artifacts.assert_called_once_with(self.now-30*86400,set())
        for invalid in ('', '6', '366', 'seven'):
            with self.subTest(invalid=invalid), patch.dict(os.environ,{'AI26_OBSERVATION_RETENTION_DAYS':invalid}):
                with self.assertRaisesRegex(ValueError,'7 to 365'):
                    Maintenance(self.repo)
        for name,invalid,expected in (
            ('AI26_TRAFFIC_RETENTION_DAYS','6','7 to 365'),
            ('AI26_TRAFFIC_RETENTION_DAYS','366','7 to 365'),
            ('AI26_REPORT_RETENTION_HOURS','0','1 to 720'),
            ('AI26_REPORT_RETENTION_HOURS','721','1 to 720'),
        ):
            with self.subTest(name=name,invalid=invalid), patch.dict(os.environ,{name:invalid}):
                with self.assertRaisesRegex(ValueError,expected):
                    Maintenance(self.repo)

    def test_report_retention_hours_are_operator_configurable(self):
        events.add_events([self.plate()])
        with patch.dict(os.environ,{'AI26_REPORT_RETENTION_HOURS':'48'}):
            report=events.evidence_report('KL07AB1234')
        self.assertAlmostEqual(report['expires_at']-report['generated_at'],48*3600,delta=0.01)
        self.assertIn('expires after 48 hours',report['retention'])

    def test_unprotected_artifacts_follow_configured_observation_retention(self):
        ref=artifacts.save_image(np.zeros((30,30,3),dtype=np.uint8),'plate-crop')
        path=artifacts.ROOT/(ref['sha256']+'.jpg')
        os.utime(path,(self.now-8*86400,self.now-8*86400))
        with patch.dict(os.environ,{'AI26_OBSERVATION_RETENTION_DAYS':'30'}):
            self.assertIsNotNone(artifacts.artifact_bytes(ref['sha256']))

    def test_schema_one_migration_backfills_report_leases(self):
        path=Path(self.folder.name)/'legacy.sqlite3'
        db=sqlite3.connect(path)
        db.execute('CREATE TABLE reports(id TEXT PRIMARY KEY,expires REAL,data TEXT)')
        report={'report_id':'legacy','expires_at':self.now+100,'artifacts':[{'sha256':'a'*64}]}
        db.execute('INSERT INTO reports VALUES(?,?,?)',('legacy',report['expires_at'],canonical_json(report)))
        db.execute('PRAGMA user_version=1');db.commit();db.close()
        migrated=Repository(path)
        try:
            self.assertEqual(migrated.schema_version,14)
            self.assertEqual(migrated.protected_artifacts(self.now),{'a'*64})
            self.assertEqual(migrated.db.execute('PRAGMA user_version').fetchone()[0],14)
        finally: migrated.close()

    def test_retention_lifespan_runs_without_inference(self):
        with patch.object(main,'Maintenance') as janitor, patch.object(main.processor,'start') as start, patch.object(main.processor,'stop'):
            with TestClient(main.app): pass
            start.assert_not_called()
            janitor.return_value.start.assert_called_once()
            janitor.return_value.stop.assert_called_once()

    def test_preview_cache_validation_and_stale_abstention(self):
        p=processing.Processor(cameras=[{'id':'CAM-01','kind':'vehicle'}])
        p.state['CAM-01']['status']='processing'
        p.latest['CAM-01']=(self.now,b'full frame')
        p.thumbnails['CAM-01']=(self.now,b'preview')
        with patch.object(main,'processor',p):
            response=self.client.get('/api/preview/CAM-01')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.content,b'preview')
            self.assertEqual(self.client.get('/api/preview/CAM-01',headers={'If-None-Match':response.headers['etag']}).status_code,304)
            p.state['CAM-01']['status']='error'
            self.assertEqual(self.client.get('/api/preview/CAM-01').status_code,503)
            self.assertEqual(self.client.get('/api/preview/CAM-09').status_code,404)
        self.assertEqual(self.repo.observations(),[])

    def test_artifact_corruption_detected(self):
        ref=artifacts.save_image(np.zeros((30,30,3),dtype=np.uint8),'plate-crop')
        self.assertEqual(hashlib.sha256(artifacts.artifact_bytes(ref['sha256'])).hexdigest(),ref['sha256'])
        (artifacts.ROOT/(ref['sha256']+'.jpg')).write_bytes(b'changed')
        self.assertEqual(self.client.get(ref['url']).status_code,409)

    def test_report_tampering_rejected(self):
        events.add_events([self.plate()]);report=events.evidence_report('KL07AB1234')
        report['trajectory']['plate']='TN22ZZ0007'
        with self.repo.db:self.repo.db.execute('UPDATE reports SET data=? WHERE id=?',(canonical_json(report),report['report_id']))
        self.assertEqual(self.client.get('/api/reports/'+report['report_id']).status_code,409)

    def test_specific_plate_query_filters_other_plates(self):
        events.add_events([self.plate(),self.plate('CAM-08',plate='TN22ZZ0007')])
        answer=nlquery.answer('Where was plate KL07AB1234?')['text']
        self.assertIn('KL07AB1234',answer);self.assertNotIn('TN22ZZ0007',answer)

    def test_today_queries_history_not_five_minute_window(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        start=datetime.now(ZoneInfo('Asia/Kolkata')).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        if self.now-start<400:self.skipTest('Too close to midnight for this fixture')
        events.add_events([self.plate(ts=start+1)])
        self.assertNotIn('KL07AB1234',nlquery.answer('plates at CAM-07')['text'])
        self.assertIn('KL07AB1234',nlquery.answer('plates at CAM-07 today')['text'])

    def test_unsupported_query_clear_and_no_fake_sql(self):
        result=nlquery.answer('How congested is the city?')
        self.assertEqual(result['status'],'unsupported');self.assertNotIn('sql',result)

    def test_dwell_requires_elapsed_zone_presence(self):
        self.repo.set_setting('rules',{'watchlist':{},'restricted_cameras':[], 'dwell_zones':[{'camera_id':'CAM-01','zone':[0,0,.5,.5],'dwell_seconds':10,'max_gap_seconds':5}]})
        events.add_events([self.vehicle(self.now-10+i*5,frame_id=i) for i in range(3)])
        alerts=events.derive_alerts();self.assertEqual([a['type'] for a in alerts],['zone dwell'])
        self.assertEqual(len(alerts[0]['supporting_event_ids']),3)

    def test_dwell_breaks_on_zone_exit_and_capture_gap(self):
        self.repo.set_setting('rules',{'watchlist':{},'restricted_cameras':[], 'dwell_zones':[{'camera_id':'CAM-01','zone':[0,0,.5,.5],'dwell_seconds':10,'max_gap_seconds':5}]})
        events.add_events([self.vehicle(self.now-15,frame_id=1),self.vehicle(self.now-10,frame_id=2,bbox=[70,70,90,90]),self.vehicle(self.now,frame_id=3)])
        self.assertEqual(events.derive_alerts(),[])

    def test_watchlist_history_and_effective_window_conditions(self):
        plate='KL07AB1234'
        self.repo.set_setting('rules',{'watchlist':{plate:'Repeat sighting review'},
            'watchlist_conditions':{plate:{'active_from':self.now-5,'active_until':self.now+10,
                'minimum_sightings':2,'history_window_seconds':30}},
            'restricted_cameras':[],'zone_permits':[],'dwell_zones':[]})
        events.add_events([self.plate(ts=self.now-10,session_id='history',frame_id=1)])
        self.assertFalse(any(a['type']=='watchlist match' for a in events.derive_alerts()))
        events.add_events([self.plate(ts=self.now,session_id='history',frame_id=2)])
        match=next(a for a in events.derive_alerts() if a['type']=='watchlist match')
        self.assertIn('2 supported sighting(s)',match['detail'])
        expired_plate='TN22ZZ0007'
        self.repo.set_setting('rules',{'watchlist':{expired_plate:'Expired entry'},
            'watchlist_conditions':{expired_plate:{'active_from':self.now-20,'active_until':self.now-1,
                'minimum_sightings':1,'history_window_seconds':30}},
            'restricted_cameras':[],'zone_permits':[],'dwell_zones':[]})
        events.add_events([self.plate(ts=self.now,plate=expired_plate,session_id='expired',frame_id=1)])
        self.assertFalse(any(a['type']=='watchlist match' and expired_plate in a['summary'] for a in events.derive_alerts()))

    def test_local_zone_permit_records_suppress_warning_without_claiming_verification(self):
        plate='KL07AB1234'
        event=self.plate('CAM-07',self.now,session_id='permit',frame_id=1)
        base={'watchlist':{},'watchlist_conditions':{},'restricted_cameras':['CAM-07'],'dwell_zones':[]}
        self.repo.set_setting('rules',{**base,'zone_permits':[{'permit_id':'LOCAL-1','plate':plate,
            'camera_ids':['CAM-07'],'valid_from':self.now-1,'valid_until':self.now+1,'reason':'scheduled service'}]})
        events.add_events([event])
        permitted=events.derive_alerts()
        self.assertIn('permitted zone visit',[alert['type'] for alert in permitted])
        permit_alert=next(alert for alert in permitted if alert['type']=='permitted zone visit')
        self.assertIn('No external permit verification',permit_alert['detail'])
        self.repo.set_setting('rules',{**base,'zone_permits':[]})
        warnings=events.derive_alerts()
        self.assertIn('zone sighting',[alert['type'] for alert in warnings])

    def test_review_state_survives_rule_recalculation_and_reopen(self):
        events.add_events([self.plate()]);alert=events.derive_alerts()[0]
        response=self.client.post(f'/api/alerts/{alert["alert_id"]}/review',json={'state':'acknowledged','reviewer':'Course reviewer','note':'Inspect crop'})
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json()['reviewer_authenticated'])
        self.assertEqual(self.repo.verify_audit_chain()['status'],'valid')
        same=next(a for a in events.derive_alerts() if a['alert_id']==alert['alert_id'])
        self.assertEqual(same['state'],'acknowledged')
        reopened=Repository(self.path)
        try:self.assertEqual(reopened.alerts()[0]['review'][0]['reviewer'],'Course reviewer')
        finally:reopened.close()

    def test_escalation_requires_target_and_stays_queued_until_decided(self):
        events.add_events([self.plate()]);alert=events.derive_alerts()[0]
        url=f'/api/alerts/{alert["alert_id"]}/review'
        missing=self.client.post(url,json={'state':'escalated','reviewer':'Operator'})
        self.assertEqual(missing.status_code,422)
        escalated=self.client.post(url,json={'state':'escalated','reviewer':'Operator',
                                               'escalation_target':'Traffic desk','note':'Please verify crop'})
        self.assertEqual(escalated.status_code,200)
        self.assertEqual(escalated.json()['escalation_target'],'Traffic desk')
        # A caller looking only after the alert timestamp still sees the active handoff.
        queued=self.client.get('/api/alerts',params={'since':self.now+1,'include_escalated':'true'})
        self.assertEqual([item['alert_id'] for item in queued.json()],[alert['alert_id']])
        reopened=Repository(self.path)
        try:
            item=reopened.escalated_alerts()[0]
            self.assertEqual(item['review'][-1]['escalation_target'],'Traffic desk')
        finally:reopened.close()
        reassigned=self.client.post(url,json={'state':'escalated','reviewer':'Operator',
                                                'escalation_target':'Duty supervisor','note':'Reassigned'})
        self.assertEqual(reassigned.status_code,200)
        self.assertEqual(self.client.get('/api/alerts',params={'include_escalated':'true'}).json()[0]['review'][-1]['escalation_target'],'Duty supervisor')
        resolved=self.client.post(url,json={'state':'acknowledged','reviewer':'Duty supervisor','note':'Reviewed'})
        self.assertEqual(resolved.status_code,200)
        self.assertEqual(self.repo.escalated_alerts(),[])

    def test_escalation_queue_cursor_pages_retain_all_active_handoffs(self):
        with self.repo.lock, self.repo.db:
            for index in range(205):
                alert_id=f'queue-{index:03d}'
                alert={'alert_id':alert_id,'ts':1000.0,'severity':'warning','type':'test',
                       'summary':alert_id,'detail':'synthetic pagination fixture'}
                self.repo.db.execute(
                    "INSERT INTO alerts(id,ts,data,state,review) VALUES(?,?,?,?,?)",
                    (alert_id,1000.0,canonical_json(alert),'escalated',canonical_json([{
                        'reviewer':'Fixture','state':'escalated','escalation_target':'Queue','note':'','ts':1000.0
                    }])),
                )
        first=self.client.get('/api/alerts/escalations',params={'limit':100})
        self.assertEqual(first.status_code,200)
        result=first.json(); ids=[item['alert_id'] for item in result['items']]
        self.assertEqual(len(ids),100)
        while result['next_cursor']:
            result=self.client.get('/api/alerts/escalations',params={
                'limit':100,'before_ts':result['next_cursor']['ts'],'before_id':result['next_cursor']['id'],
            }).json()
            ids.extend(item['alert_id'] for item in result['items'])
        self.assertEqual(len(ids),205)
        self.assertEqual(len(set(ids)),205)
        self.assertEqual(ids[0],'queue-204')
        self.assertEqual(ids[-1],'queue-000')
        invalid=self.client.get('/api/alerts/escalations',params={'before_id':'queue-100'})
        self.assertEqual(invalid.status_code,422)

    def test_rule_configuration_validated_and_persisted(self):
        valid={'watchlist':{'kl 07 ab 1234':'Review this local plate'},'restricted_cameras':['CAM-07'],'dwell_zones':[],
            'watchlist_conditions':{'kl 07 ab 1234':{'minimum_sightings':2,'history_window_seconds':120}},
            'zone_permits':[{'permit_id':'LOCAL-2','plate':'kl 07 ab 1234','camera_ids':['CAM-07'],
                'valid_from':self.now-10,'valid_until':self.now+10,'reason':'scheduled maintenance'}]}
        response=self.client.put('/api/rules',json=valid)
        self.assertEqual(response.status_code,200)
        self.assertIn('KL07AB1234',self.client.get('/api/rules').json()['watchlist'])
        normalized=self.client.get('/api/rules').json()
        self.assertIn('KL07AB1234',normalized['watchlist_conditions'])
        self.assertEqual(normalized['zone_permits'][0]['plate'],'KL07AB1234')
        audit=self.repo.db.execute("SELECT action FROM audit ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.assertEqual(audit,'rules_updated')
        self.assertEqual(self.repo.verify_audit_chain()['status'],'valid')
        valid['dwell_zones']=[{'camera_id':'CAM-01','zone':[1,0,0,1]}]
        self.assertEqual(self.client.put('/api/rules',json=valid).status_code,422)
        bad_condition={**valid,'dwell_zones':[],'watchlist_conditions':{'TN22ZZ0007':{'minimum_sightings':1}}}
        self.assertEqual(self.client.put('/api/rules',json=bad_condition).status_code,422)
        bad_permit={**valid,'dwell_zones':[],'zone_permits':[{'permit_id':'LOCAL-3','plate':'KL07AB1234',
            'camera_ids':['CAM-99'],'valid_from':self.now-1,'valid_until':self.now+1,'reason':'bad camera'}]}
        self.assertEqual(self.client.put('/api/rules',json=bad_permit).status_code,404)

    def test_consumers_do_not_ingest_or_run_models(self):
        p=processing.Processor(cameras=[{'id':'CAM-01','kind':'vehicle'}])
        p.state['CAM-01']['status']='processing';p.latest['CAM-01']=(self.now,b'jpeg')
        with patch.object(stream,'processor',p):
            async def consume():
                a=stream.mjpeg_generator('CAM-01');b=stream.mjpeg_generator('CAM-01')
                self.assertIn(b'jpeg',await anext(a));self.assertIn(b'jpeg',await anext(b))
                await a.aclose();await b.aclose()
            asyncio.run(consume())
            self.assertEqual(stream.snapshot_frame('CAM-01'),b'jpeg')
        self.assertEqual(self.repo.observations(),[])

    def test_idle_stream_cancels_without_blocking_event_loop(self):
        p=processing.Processor(cameras=[])
        with patch.object(stream,'processor',p):
            async def cancel_idle():
                feed=stream.mjpeg_generator('CAM-01')
                pending=asyncio.create_task(anext(feed))
                await asyncio.sleep(.01)
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError): await pending
                await feed.aclose()
            asyncio.run(asyncio.wait_for(cancel_idle(),.5))

    def test_report_creation_rejects_missing_source_artifact(self):
        events.add_events([self.plate(artifacts=[{'sha256':'a'*64,'role':'plate-crop','size':30}])])
        response=self.client.post('/api/evidence/KL07AB1234')
        self.assertEqual(response.status_code,409)
        self.assertIn('missing',response.json()['error']['message'])
        self.assertEqual(self.repo.db.execute('SELECT count(*) FROM reports').fetchone()[0],0)

    def test_missing_processor_source_bounded(self):
        p=processing.Processor(cameras=[{'id':'CAM-01','kind':'vehicle'}],source=lambda _:Path(self.folder.name)/'missing.mp4')
        p.step(p.cameras[0]);self.assertEqual(p.health()[0]['status'],'unavailable')
        self.assertEqual(p.health()[0]['frames'],0)

    def test_processor_owns_one_frame_and_records_provenance(self):
        path=Path(self.folder.name)/'source.mp4';path.write_bytes(b'test clip identity')
        capture=SimpleNamespace(isOpened=lambda:True,get=lambda key:25 if key==processing.cv2.CAP_PROP_FPS else 1000 if key==processing.cv2.CAP_PROP_FRAME_COUNT else 2375 if key==processing.cv2.CAP_PROP_POS_MSEC else 0,
                                set=lambda *args:True,read=lambda:(True,np.zeros((100,100,3),dtype=np.uint8)),release=lambda:None)
        p=processing.Processor(cameras=[{'id':'CAM-01','kind':'vehicle'}],source=lambda _:path,
                               annotator=lambda frame,kind,camera:(frame,[self.vehicle()]))
        clock=normalize_recording_clock('2026-10-14T06:30:00Z',2.0)
        with patch.object(processing.cameras,'MANAGED_SOURCES',{'CAM-01':{'manifest':{'recording_clock':clock}}}), \
             patch.object(processing.cv2,'VideoCapture',return_value=capture):p.step(p.cameras[0])
        self.assertEqual(p.health()[0]['status'],'processing')
        read=self.repo.observations()[0]
        self.assertEqual(read['time_basis'],'replay_clock');self.assertIn('source_sha256',read)
        self.assertEqual(read['recording_clock_status'],'operator_claimed_unverified')
        self.assertEqual(read['source_offset_basis'],'decoder_reported_position_msec')
        self.assertEqual(read['source_time_basis'],'decoder_reported_position_msec')
        self.assertEqual(read['source_time_seconds'],2.375)
        self.assertEqual(read['claimed_source_capture_time_utc'],
                         source_capture_clock_fields(clock,read['source_time_seconds'])['claimed_source_capture_time_utc'])
        self.assertTrue(any(ref.get('claimed_source_capture_time_utc')==read['claimed_source_capture_time_utc']
                            and ref.get('source_offset_basis')==read['source_offset_basis']
                            and ref.get('source_time_basis')==read['source_time_basis']
                            for ref in read['artifacts']))
        self.assertEqual(len(read['artifacts']),2)
        self.assertTrue(p.jpeg('CAM-01')[1].startswith(b'\xff\xd8'))
        preview=processing.cv2.imdecode(np.frombuffer(p.preview('CAM-01')[1],np.uint8),processing.cv2.IMREAD_COLOR)
        self.assertEqual(preview.shape[1],320)

    def test_aggregates_do_not_truncate_at_raw_api_limit(self):
        events.add_events([self.vehicle(self.now-i*.1,frame_id=i) for i in range(6)])
        with patch.object(events,'MAX_EVENTS',2):
            self.assertEqual(len(events.get_events()),2)
            self.assertEqual(events.stats()['total_events'],6)
            self.assertIn('1 camera-local car passages',nlquery.answer('count cars at CAM-01')['text'])

    def test_unknown_camera_and_color_queries_not_silently_broadened(self):
        events.add_events([self.plate(),self.vehicle()])
        self.assertEqual(nlquery.answer('plates at CAM-99')['status'],'invalid')
        self.assertEqual(nlquery.answer('red cars at CAM-01')['status'],'unsupported')
        self.assertEqual(nlquery.answer('plates KL07AB1234 and TN22ZZ0007')['status'],'unsupported')

    def test_no_duplicate_inference_owner_for_same_data_directory(self):
        first=processing.Processor(cameras=[]);second=processing.Processor(cameras=[])
        first.start();self.addCleanup(first.stop);self.addCleanup(second.stop)
        with self.assertRaises(RuntimeError):second.start()
        first.stop();second.start();second.stop()

    def test_bad_capture_has_retry_backoff(self):
        path=Path(self.folder.name)/'corrupt.mp4';path.write_bytes(b'corrupt')
        capture=SimpleNamespace(isOpened=lambda:False,release=lambda:None)
        p=processing.Processor(cameras=[{'id':'CAM-01','kind':'vehicle'}],source=lambda _:path)
        with patch.object(processing.cv2,'VideoCapture',return_value=capture) as factory:
            with self.assertLogs(processing.log,level='ERROR'):p.step(p.cameras[0])
            p.step(p.cameras[0]);self.assertEqual(factory.call_count,1)
        self.assertEqual(p.health()[0]['status'],'error')

    def test_loop_boundary_resets_identity_and_creates_new_passage(self):
        path=Path(self.folder.name)/'source.mp4';path.write_bytes(b'clip')
        capture=SimpleNamespace(isOpened=lambda:True,get=lambda key:25 if key==processing.cv2.CAP_PROP_FPS else 1000,
                                set=lambda *args:True,read=lambda:(True,np.zeros((100,100,3),dtype=np.uint8)),release=lambda:None)
        p=processing.Processor(cameras=[{'id':'CAM-01','kind':'vehicle'}],source=lambda _:path,annotator=lambda frame,*_:(frame,[self.vehicle()]))
        p.started=self.now;reset=Mock()
        with patch.object(processing.cv2,'VideoCapture',return_value=capture),patch.dict(sys.modules,{'inference':SimpleNamespace(reset_camera=reset)}):
            with patch.object(processing.time,'time',return_value=self.now+1):p.step(p.cameras[0])
            with patch.object(processing.time,'time',return_value=self.now+41):p.step(p.cameras[0])
        reset.assert_called_once_with('CAM-01')
        self.assertEqual(len(self.repo.passages()),2)

    def test_inference_exception_backoff_and_reconnect_create_new_session(self):
        path=Path(self.folder.name)/'source.mp4';path.write_bytes(b'clip')
        capture=SimpleNamespace(isOpened=lambda:True,get=lambda key:25 if key==processing.cv2.CAP_PROP_FPS else 10000,
                                set=lambda *args:True,read=lambda:(True,np.zeros((100,100,3),dtype=np.uint8)),release=lambda:None)
        calls=Mock(side_effect=[(np.zeros((100,100,3),dtype=np.uint8),[self.vehicle()]),OSError('Model download unavailable'),(np.zeros((100,100,3),dtype=np.uint8),[self.vehicle()])])
        p=processing.Processor(cameras=[{'id':'CAM-01','kind':'vehicle'}],source=lambda _:path,annotator=calls);p.started=self.now;reset=Mock()
        with patch.object(processing.cv2,'VideoCapture',return_value=capture),patch.dict(sys.modules,{'inference':SimpleNamespace(reset_camera=reset)}):
            with patch.object(processing.time,'time',return_value=self.now+1):p.step(p.cameras[0])
            old_session=p.health()[0]['session_id']
            with patch.object(processing.time,'time',return_value=self.now+2),self.assertLogs(processing.log,level='ERROR'):p.step(p.cameras[0])
            self.assertIsNone(p.jpeg('CAM-01'))
            with patch.object(processing.time,'time',return_value=self.now+3):p.step(p.cameras[0])
            self.assertEqual(calls.call_count,2)
            with patch.object(processing.time,'time',return_value=self.now+13):p.step(p.cameras[0])
        self.assertNotEqual(old_session,p.health()[0]['session_id']);reset.assert_called_once()
        self.assertEqual(len(self.repo.passages()),2)

    def test_eof_decode_failure_is_bounded_and_discards_stale_frame(self):
        path=Path(self.folder.name)/'source.mp4';path.write_bytes(b'clip')
        capture=SimpleNamespace(isOpened=lambda:True,get=lambda key:25 if key==processing.cv2.CAP_PROP_FPS else 1000,
                                set=lambda *args:True,read=lambda:(False,None),release=lambda:None)
        p=processing.Processor(cameras=[{'id':'CAM-01','kind':'vehicle'}],source=lambda _:path)
        with patch.object(processing.cv2,'VideoCapture',return_value=capture) as factory:
            with self.assertLogs(processing.log,level='ERROR'):p.step(p.cameras[0])
            p.step(p.cameras[0]);self.assertEqual(factory.call_count,1)
        self.assertEqual(p.health()[0]['status'],'error');self.assertIsNone(p.jpeg('CAM-01'))

    def test_artifact_package_contains_verified_image_bytes(self):
        ref=artifacts.save_image(np.zeros((20,20,3),dtype=np.uint8),'plate-crop')
        events.add_events([self.plate(artifacts=[ref])]);report=events.evidence_report('KL07AB1234')
        response=self.client.get('/api/reports/'+report['report_id']+'/package')
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            data=z.read('artifacts/'+ref['sha256']+'.jpg')
            self.assertEqual(hashlib.sha256(data).hexdigest(),ref['sha256'])
        (artifacts.ROOT/(ref['sha256']+'.jpg')).unlink()
        self.assertEqual(self.client.get('/api/reports/'+report['report_id']+'/package').status_code,410)

    def test_evaluation_fixture_detects_errors_and_marks_synthetic(self):
        import importlib.util
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('ai26_evaluation',root/'evaluation/evaluate.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        records=[json.loads(line) for line in (root/'evaluation/example.jsonl').read_text().splitlines()]
        result=module.evaluate(records)
        self.assertTrue(result['synthetic']);self.assertEqual(result['tracking']['id_switches'],1)
        self.assertEqual(result['detector']['fp'],1);self.assertEqual(result['links']['fp'],1)
        self.assertEqual(result['passages']['signed_error'],1)
        with self.assertRaises(ValueError):module.evaluate([records[0],records[0]])

if __name__=='__main__':unittest.main()
