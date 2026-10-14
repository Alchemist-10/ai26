"""Hourly live-source passage history excludes replay and requires coverage."""
from datetime import datetime
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

os.environ['AI26_PROCESSING_ENABLED']='0'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import events
from repository import Repository


class TrafficBaselineTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.repo=Repository(Path(self.folder.name)/'traffic.sqlite3');self.addCleanup(self.repo.close)
        self.store_patch=patch.object(events,'store',self.repo);self.store_patch.start();self.addCleanup(self.store_patch.stop)
        self.zone=ZoneInfo('Asia/Kolkata')
        self.now=datetime(2026,10,14,15,30,tzinfo=self.zone).timestamp()

    def sample_hour(self, day, passages, processed=6, camera='CAM-01'):
        local=datetime.fromisoformat(day).replace(tzinfo=self.zone,hour=14,minute=0,second=0,microsecond=0)
        for index in range(passages):
            ts=local.timestamp()+index*60
            events.add_events([{'camera_id':camera,'kind':'vehicle','confidence':.8,
                'bbox':[0,0,20,20],'ts':ts,'session_id':f'{day}-session-{index}',
                'track_id':index+1,'frame_id':index+1,'source_mode':'live',
                'time_basis':'capture_arrival_clock'}])
        for index in range(processed):
            self.repo.record_traffic_sample(camera,local.timestamp()+index*300)

    def test_live_history_uses_local_hour_and_compares_matching_weekday(self):
        self.sample_hour('2026-09-30',3)
        self.sample_hour('2026-10-07',7)
        self.sample_hour('2026-10-14',5)
        report=events.traffic_baselines(days=28,now=self.now,timezone_name='Asia/Kolkata')
        camera=next(item for item in report['cameras'] if item['camera_id']=='CAM-01')
        self.assertEqual(camera['status'],'baseline_ready')
        self.assertEqual(camera['latest_passages'],5)
        self.assertEqual(camera['baseline_median'],5)
        self.assertEqual(camera['baseline_comparable_hours'],2)
        self.assertEqual(camera['latest_complete_hour_local'],'2026-10-14T14:00:00+05:30')
        self.assertIsNone(report['speed_kmh'])

    def test_replay_and_recorded_observations_do_not_enter_history(self):
        events.add_events([{'camera_id':'CAM-01','kind':'vehicle','confidence':.8,
            'bbox':[0,0,20,20],'ts':self.now-86400,'session_id':'replay-session',
            'track_id':1,'frame_id':1,'source_mode':'recorded','time_basis':'replay_clock'}])
        self.assertEqual(self.repo.camera_hourly_traffic(self.now-7*86400,self.now),[])
        report=events.traffic_baselines(days=28,now=self.now,timezone_name='Asia/Kolkata')
        camera=next(item for item in report['cameras'] if item['camera_id']=='CAM-01')
        self.assertEqual(camera['status'],'no_live_history')
        self.assertIsNone(camera['latest_passages'])

    def test_partial_single_quarter_hour_is_not_reported_as_zero_traffic(self):
        self.sample_hour('2026-10-14',0,processed=3)
        report=events.traffic_baselines(days=28,now=self.now,timezone_name='Asia/Kolkata')
        camera=next(item for item in report['cameras'] if item['camera_id']=='CAM-01')
        self.assertEqual(camera['status'],'insufficient_coverage')
        self.assertIsNone(camera['latest_passages'])

    def test_deduplicates_passages_and_retains_only_bounded_aggregate_history(self):
        self.sample_hour('2026-10-14',1,processed=2)
        ts=datetime(2026,10,14,14,10,tzinfo=self.zone).timestamp()
        event={'camera_id':'CAM-01','kind':'vehicle','confidence':.8,'bbox':[0,0,20,20],
               'ts':ts+60,'session_id':'2026-10-14-session-0','track_id':1,'frame_id':2,
               'source_mode':'live','time_basis':'capture_arrival_clock'}
        events.add_events([event])
        before=self.repo.db.execute('SELECT sum(vehicle_passages),sum(processed_samples) FROM camera_traffic_buckets').fetchone()
        self.assertEqual(tuple(before),(1,2))
        old=datetime(2026,1,1,tzinfo=self.zone).timestamp()
        self.repo.record_traffic_sample('CAM-01',old)
        self.repo.cleanup(self.now-7*86400,self.now)
        self.assertEqual(self.repo.db.execute('SELECT count(*) FROM camera_traffic_buckets WHERE bucket_start_utc<?',(self.now-90*86400,)).fetchone()[0],0)
        self.assertEqual(self.repo.schema_version,12)

    def test_rejects_bad_day_window_and_timezone(self):
        with self.assertRaises(ValueError): events.traffic_baselines(days=6,now=self.now)
        with self.assertRaises(Exception): events.traffic_baselines(days=28,now=self.now,timezone_name='No/Such_Zone')


if __name__=='__main__': unittest.main()
