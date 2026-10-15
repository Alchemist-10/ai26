"""Schema migrations, immutable metadata and queried journey decisions, with isolated data."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ['AI26_PROCESSING_ENABLED']='0'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi.testclient import TestClient
import events
import main
import nlquery
from repository import Repository, canonical_json


class Persistence(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'test.sqlite3'
        self.repo=Repository(self.path); self.addCleanup(lambda:self.repo.close())
        for module in (events,main):
            p=patch.object(module,'store',self.repo); p.start(); self.addCleanup(p.stop)
        self.client=TestClient(main.app)
        self.now=time.time()

    def edit(self,camera='CAM-07',**extra):
        current=self.repo.camera_configuration(camera)
        body={k:current[k] for k in ('location','location_confirmed','lat','lon')}
        body.update(expected_revision=current['revision'],reviewer='Local tester',reason='Fixture metadata update',**extra)
        return self.client.put(f'/api/cameras/{camera}/configuration',json=body)

    def ingest_pair(self,**extra):
        for camera,ts in [('CAM-07',self.now-120),('CAM-08',self.now)]:
            events.add_events([{'camera_id':camera,'kind':'plate','plate':'KL07AB1234','plate_norm':'KL07AB1234',
                'confidence':.9,'bbox':[0,0,20,20],'ts':ts,'session_id':'fixture','track_id':1,'frame_id':1,**extra}])

    def route(self):
        return events.get_trajectory('KL07AB1234',self.now-200,self.now+1)

    def test_seed_restart_preserves_current_and_history(self):
        self.assertEqual(len(self.repo.camera_catalog()),9)
        self.assertFalse(any('path' in c for c in self.repo.camera_catalog()))
        result=self.edit(location='Renamed fixture site').json()
        self.assertEqual(result['revision'],2)
        self.assertEqual(result['calibration_status'],'unverified')
        self.repo.close(); self.repo=Repository(self.path)
        self.assertEqual(self.repo.camera_configuration('CAM-07'),result)
        self.assertEqual(self.repo.camera_configuration('CAM-07',1)['revision'],1)
        self.assertEqual(len(self.repo.camera_catalog()),9)
        audit=self.repo.db.execute("SELECT data FROM audit WHERE action='camera_configuration'").fetchone()
        self.assertEqual(json.loads(audit[0])['reviewer'],'Local tester')

    def test_concurrent_stale_edit_rejected_without_revision_or_audit(self):
        other=Repository(self.path)
        self.addCleanup(other.close)
        before=other.camera_configuration('CAM-07')
        self.assertEqual(self.edit().status_code,200)
        with self.assertRaisesRegex(ValueError,'reload'):
            other.update_camera('CAM-07',{**before,'expected_revision':1,'reviewer':'second','reason':'stale'},self.now)
        self.assertEqual(other.camera_configuration('CAM-07')['revision'],2)
        self.assertEqual(other.db.execute('SELECT count(*) FROM audit').fetchone()[0],1)
        self.assertFalse(other.db.in_transaction)

    def test_configuration_validation_and_unknown_ids(self):
        for change in ({'lat':91},{'lon':181},{'location':' '},{'reviewer':' '},{'reason':' '},
                       {'path':'/tmp/source.mp4'},{'kind':'vehicle'},{'id':'CAM-10'},
                       {'location_confirmed':'true'},{'expected_revision':True}):
            current=self.repo.camera_configuration('CAM-07')
            body={k:current[k] for k in ('location','location_confirmed','lat','lon')}
            body.update(expected_revision=1,reviewer='tester',reason='test');body.update(change)
            self.assertEqual(self.client.put('/api/cameras/CAM-07/configuration',json=body).status_code,422,change)
        self.assertEqual(self.client.get('/api/cameras/CAM-99/configuration').status_code,404)
        self.assertEqual(self.client.get('/api/cameras/CAM-07/configuration?revision=999').status_code,404)
        self.assertEqual(self.repo.camera_configuration('CAM-07')['revision'],1)

    def test_camera_pair_constraint_requires_confirmed_locations_and_is_audited(self):
        body={'from_camera_id':'CAM-07','to_camera_id':'CAM-08','min_travel_seconds':20,
              'max_travel_seconds':900,'enabled':True,'reviewer':'Local tester','reason':'Validated test corridor'}
        self.edit('CAM-07',location_confirmed=False)
        self.assertEqual(self.client.put('/api/camera-pair-constraints',json=body).status_code,409)
        self.edit('CAM-07',location_confirmed=True)
        self.edit('CAM-08',location_confirmed=True)
        saved=self.client.put('/api/camera-pair-constraints',json=body)
        self.assertEqual(saved.status_code,200)
        self.assertEqual(saved.json()['max_travel_seconds'],900)
        self.assertEqual(self.client.get('/api/camera-pair-constraints').json(),[saved.json()])
        audit=self.repo.db.execute("SELECT action,subject FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(tuple(audit),('camera_pair_constraint','CAM-07>CAM-08'))
        invalid=self.client.put('/api/camera-pair-constraints',json={**body,'min_travel_seconds':900})
        self.assertEqual(invalid.status_code,422)
        self.assertEqual(self.client.put('/api/camera-pair-constraints',json={**body,'min_travel_seconds':True}).status_code,422)
        self.edit('CAM-07',location='New coordinates revision')
        self.assertFalse(self.client.get('/api/camera-pair-constraints').json()[0]['current_locations_valid'])

    def test_catalog_and_named_queries_use_persisted_metadata(self):
        self.edit(location='Fixture East')
        catalog=self.client.get('/api/cameras').json()
        self.assertEqual(next(c for c in catalog if c['id']=='CAM-07')['location'],'Fixture East')
        self.ingest_pair()
        self.assertIn('CAM-07',nlquery.answer('plates at Fixture East')['text'])
        self.edit('CAM-08',location='Fixture East')
        self.assertEqual(nlquery.answer('plates at Fixture East')['status'],'invalid')
        self.assertEqual(nlquery.answer('plates at CAM-07 Fixture East')['status'],'supported')

    def test_observation_snapshot_and_link_do_not_change_on_edit_or_retry(self):
        self.ingest_pair(time_basis='replay_clock')
        self.repo.put_camera_pair_constraint({'from_camera_id':'CAM-07','to_camera_id':'CAM-08',
            'min_travel_seconds':0,'max_travel_seconds':3600,'enabled':True,'reviewer':'fixture','reason':'snapshot test'},self.now)
        original=self.route()
        link=original['candidate_links'][0]
        self.assertEqual(link['camera_pair_constraint']['max_travel_seconds'],3600)
        self.assertIsNone(link['implied_speed_kmh'])
        self.assertFalse(link['identity_verified'])
        self.assertEqual(link['metadata_basis'],['observation_snapshot']*2)
        self.assertEqual(len(link['supporting_event_ids']),2)
        self.edit(location='Changed name',lat=0,lon=0)
        self.ingest_pair(time_basis='replay_clock') # retry same frame; original metadata remains immutable
        self.assertEqual(self.route(),original)
        self.assertEqual(self.repo.db.execute('SELECT count(*) FROM journey_links').fetchone()[0],1)
        self.repo.close();self.repo=Repository(self.path)
        self.assertEqual(self.repo.journey_links()[0],link)
        self.assertEqual(self.repo.observations()[0]['camera_configuration']['revision'],1)

    def test_new_observations_use_new_revision_and_decision_version(self):
        self.ingest_pair(time_basis='replay_clock'); old=self.route()['candidate_links'][0]
        self.edit(location='Changed name')
        events.add_events([{'camera_id':'CAM-07','kind':'plate','plate':'KL07AB1234','confidence':.9,
                           'bbox':[0,0,20,20],'ts':self.now+10,'session_id':'new','track_id':1,
                           'frame_id':2,'time_basis':'replay_clock'}])
        route=events.get_trajectory('KL07AB1234',self.now-200,self.now+20)
        self.assertEqual(route['observations'][-1]['camera_configuration']['revision'],2)
        self.assertEqual(route['candidate_links'][0],old)
        with patch.object(events,'LINK_ALGORITHM_VERSION','fixture-next-version'):
            updated=self.route()['candidate_links'][0]
        self.assertNotEqual(updated['link_id'],old['link_id'])
        self.assertEqual(updated['algorithm_version'],'fixture-next-version')
        self.assertEqual(len(self.repo.journey_links(until=self.now+20)),3)

    def test_report_manifest_remains_identical_after_edit(self):
        self.ingest_pair(time_basis='replay_clock')
        report=events.evidence_report('KL07AB1234',self.now-200,self.now+1)
        before=self.client.get('/api/reports/'+report['report_id']).content
        self.edit(location='New name')
        self.assertEqual(self.client.get('/api/reports/'+report['report_id']).content,before)
        self.assertIn('link_id',report['trajectory']['candidate_links'][0])

    def test_legacy_metadata_fallback_is_explicit_and_versions_are_retained(self):
        # Emulate rows imported by schema 2, which could not preserve metadata snapshots.
        for camera,ts in [('CAM-07',self.now-120),('CAM-08',self.now)]:
            self.repo.ingest([{'camera_id':camera,'kind':'plate','plate_norm':'KL07AB1234','confidence':.9,
                               'bbox':[0,0,20,20],'ts':ts,'time_basis':'replay_clock'}])
        old=self.route()['candidate_links'][0]
        self.assertEqual(old['metadata_basis'],['current_catalog_legacy']*2)
        self.edit(location='Legacy fallback changed')
        new=self.route()['candidate_links'][0]
        self.assertNotEqual(old['link_id'],new['link_id'])
        self.assertEqual(len(self.repo.journey_links()),2)

    def test_link_api_filters_and_expiry_preserve_report_snapshot(self):
        self.ingest_pair(time_basis='replay_clock'); self.route()
        report=events.evidence_report('KL07AB1234',self.now-200,self.now+1)
        self.assertEqual(len(self.client.get('/api/journey-links?plate=kl07ab1234&limit=1').json()),1)
        self.assertEqual(self.client.get('/api/journey-links?plate=TN22ZZ0007').json(),[])
        self.assertEqual(self.client.get('/api/journey-links?since='+str(self.now+1)).json(),[])
        for query in ('limit=0','limit=5001','plate=garbage','since=10&until=1','since=nan'):
            self.assertEqual(self.client.get('/api/journey-links?'+query).status_code,422)
        self.repo.cleanup(self.now+1,self.now+2)
        self.assertEqual(self.repo.journey_links(),[])
        self.assertEqual(self.repo.report(report['report_id'],self.now+3),report)

    def test_schema_two_migration_preserves_data_and_is_idempotent(self):
        self.edit(location='Hashed legacy audit entry')
        self.ingest_pair(); report=events.evidence_report('KL07AB1234',self.now-200,self.now+1)
        self.repo.close()
        db=sqlite3.connect(self.path)
        db.executescript('DROP TABLE camera_catalog; DROP TABLE journey_links; DROP INDEX alert_escalation_scope_ts; ALTER TABLE alerts DROP COLUMN scope_case_id; ALTER TABLE audit DROP COLUMN record_hash; ALTER TABLE audit DROP COLUMN previous_hash; ALTER TABLE user_mfa DROP COLUMN last_used_counter; PRAGMA user_version=2;');db.close()
        self.repo=Repository(self.path)
        self.assertEqual(self.repo.schema_version,13)
        self.assertEqual(self.repo.db.execute('PRAGMA user_version').fetchone()[0],13)
        self.assertEqual(self.repo.verify_audit_chain()['status'],'valid')
        self.assertEqual(len(self.repo.observations()),2)
        self.assertEqual(self.repo.report(report['report_id'],self.now+1),report)
        self.assertEqual(self.repo.verify_audit_chain()['status'],'valid')
        self.repo.close();self.repo=Repository(self.path)
        self.assertEqual(len(self.repo.camera_catalog()),9)
        self.assertEqual(len(self.repo.observations()),2)

    def test_future_schema_refused(self):
        path=Path(self.folder.name)/'future.sqlite3';db=sqlite3.connect(path)
        db.execute('PRAGMA user_version=14');db.close()
        with self.assertRaisesRegex(RuntimeError,'newer'):
            Repository(path)

    def test_schema_eleven_migration_adds_totp_replay_counter_preserving_mfa(self):
        self.repo.db.execute("INSERT INTO user_mfa(username,secret_ciphertext,enabled,recovery_hashes,updated_at,expires_at) VALUES(?,?,?,?,?,?)",
                             ("fixture",b"encrypted",1,'["one-use-hash"]',self.now,0))
        self.repo.db.commit()
        self.repo.close()
        db=sqlite3.connect(self.path)
        db.executescript("DROP INDEX alert_escalation_scope_ts; ALTER TABLE alerts DROP COLUMN scope_case_id; ALTER TABLE user_mfa DROP COLUMN last_used_counter; PRAGMA user_version=11;")
        db.close()
        self.repo=Repository(self.path)
        self.assertEqual(self.repo.schema_version,13)
        migrated=self.repo.db.execute("SELECT secret_ciphertext,enabled,recovery_hashes,last_used_counter FROM user_mfa WHERE username='fixture'").fetchone()
        self.assertEqual(bytes(migrated["secret_ciphertext"]),b"encrypted")
        self.assertEqual(migrated["enabled"],1)
        self.assertEqual(migrated["recovery_hashes"],'["one-use-hash"]')
        self.assertEqual(migrated["last_used_counter"],-1)

    def test_schema_twelve_migration_preserves_legacy_active_escalations(self):
        self.repo.put_alert({'alert_id':'legacy-case-queue','ts':self.now,'type':'watchlist match','summary':'legacy'})
        self.repo.review_alert('legacy-case-queue',{
            'state':'escalated','reviewer':'Operator','reviewer_authenticated':False,
            'escalation_target':'Duty desk','note':'Existing local queue','ts':self.now,
        })
        self.repo.close()
        db=sqlite3.connect(self.path)
        db.executescript('DROP INDEX alert_escalation_scope_ts; ALTER TABLE alerts DROP COLUMN scope_case_id; PRAGMA user_version=12;')
        db.close()
        migrated=Repository(self.path)
        try:
            row=migrated.db.execute("SELECT state,review,scope_case_id FROM alerts WHERE id='legacy-case-queue'").fetchone()
            self.assertEqual(migrated.schema_version,13)
            self.assertEqual(migrated.db.execute('PRAGMA user_version').fetchone()[0],13)
            self.assertEqual(row['state'],'escalated')
            self.assertIsNone(row['scope_case_id'])
            self.assertEqual(json.loads(row['review'])[-1]['escalation_target'],'Duty desk')
        finally:
            migrated.close()

    def test_audit_hash_chain_detects_changed_records_and_api_exposes_head(self):
        self.edit(location='Initial audit entry')
        self.edit(location='Second audit entry')
        valid=self.client.get('/api/audit/integrity').json()
        self.assertEqual(valid['status'],'valid')
        self.assertEqual(valid['records'],2)
        self.assertRegex(valid['head_hash'],r'^[a-f0-9]{64}$')
        self.repo.db.execute("UPDATE audit SET data='{}' WHERE id=1")
        invalid=self.repo.verify_audit_chain()
        self.assertEqual(invalid['status'],'invalid')
        self.assertEqual(invalid['first_invalid_id'],1)

    def test_each_decision_category_is_saved_with_its_support(self):
        for camera in ('CAM-07','CAM-08'):
            config=self.repo.camera_configuration(camera)
            self.repo.update_camera(camera,{**config,'expected_revision':config['revision'],'location_confirmed':True,
                'reviewer':'fixture','reason':'configure deterministic pair fixture'},self.now)
        self.repo.put_camera_pair_constraint({'from_camera_id':'CAM-07','to_camera_id':'CAM-08',
            'min_travel_seconds':120,'max_travel_seconds':3600,'enabled':True,'reviewer':'fixture','reason':'bounded fixture window'},self.now)
        for name,gap,time_basis,key,status in [('baseline',120,'manual','accepted_links','accepted'),
                    ('impossible',1,'manual','rejected_links','rejected'),
                    ('replay',120,'replay_clock','candidate_links','candidate')]:
            plate={'baseline':'KL07AB1234','impossible':'TN22ZZ0007','replay':'KA01AA1234'}[name]
            for camera,ts in [('CAM-07',self.now-gap),('CAM-08',self.now)]:
                events.add_events([{'camera_id':camera,'kind':'plate','plate':plate,'confidence':.9,
                                   'bbox':[0,0,20,20],'ts':ts,'session_id':name,'track_id':1,
                                   'time_basis':time_basis}])
            route=events.get_trajectory(plate,0,self.now+1)
            saved=self.repo.journey_links(plate,until=self.now+1)
            self.assertEqual(saved,route[key])
            self.assertEqual(saved[0]['decision_status'],status)
            self.assertFalse(saved[0]['identity_verified'])
            reads={e['event_id'] for e in self.repo.observations(plate=plate)}
            self.assertEqual(set(saved[0]['supporting_event_ids']),reads)
        self.assertEqual(len(self.repo.journey_links(until=self.now+1)),3)

    def test_nonfinite_configuration_rejected(self):
        for literal in ('NaN','Infinity','-Infinity'):
            body=canonical_json({'expected_revision':1,'location':'Fixture','location_confirmed':False,
                                 'lat':0,'lon':0,'reviewer':'tester','reason':'fixture'})
            body=body.replace('"lat":0',f'"lat":{literal}')
            response=self.client.put('/api/cameras/CAM-07/configuration',content=body,
                                     headers={'Content-Type':'application/json'})
            self.assertEqual(response.status_code,422)
        self.assertEqual(self.repo.camera_configuration('CAM-07')['revision'],1)


if __name__=='__main__': unittest.main()
