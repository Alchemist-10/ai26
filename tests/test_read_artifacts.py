"""Per-read evidence contracts use synthetic pixels, isolated storage and no ML downloads."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

os.environ['AI26_PROCESSING_ENABLED']='0'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import numpy as np
from fastapi.testclient import TestClient
import artifacts
import events
import main
import processing
from repository import Repository,canonical_json


class ReadArtifacts(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        self.repository=Repository(self.root/'fixture.sqlite3');self.addCleanup(self.repository.close)
        for module in (events,main,processing):
            p=patch.object(module,'store',self.repository);p.start();self.addCleanup(p.stop)
        p=patch.object(artifacts,'ROOT',self.root/'artifacts');p.start();self.addCleanup(p.stop)
        self.client=TestClient(main.app);self.now=time.time()

    def read(self,frame_id=1,**extra):
        return {'camera_id':'CAM-07','session_id':'synthetic-read-artifacts','frame_id':frame_id,
                'source_sha256':'a'*64,'source_time_seconds':frame_id/25,'frame_size':[40,30],
                'kind':'plate','track_id':1,'confidence':.9,'bbox':[2,3,20,15],
                'plate':'KL07AB1234','plate_norm':'KL07AB1234','plate_raw':'KL07AB1234',
                'identity_status':'supported','ts':self.now+frame_id/100,
                'source_mode':'synthetic fixture','time_basis':'replay_clock',**extra}

    def image(self,value=60): return np.full((30,40,3),value,np.uint8)

    def capture(self,reads,image=None):
        return artifacts.capture_read_images(self.image() if image is None else image,reads)

    def test_shared_frame_is_encoded_once_and_same_crop_reused_with_per_read_context(self):
        reads=[self.read(track_id=track) for track in (1,2,3)]
        with patch.object(artifacts,'save_image',wraps=artifacts.save_image) as save:
            metrics=self.capture(reads)
        self.assertEqual(save.call_count,2)
        self.assertEqual(metrics,{'image_attempts':2,'image_failures':0,'incomplete_reads':0,'storage_budget_failures':0})
        self.assertEqual(len({r['artifacts'][0]['sha256'] for r in reads}),1)
        self.assertTrue(all(r['image_quality']['version']=='sampled-crop-statistics-v1' for r in reads))
        for read in reads:
            self.assertEqual(read['artifact_capture']['status'],'complete')
            self.assertEqual(read['artifacts'][1]['crop_bbox'],read['bbox'])
            for ref in read['artifacts']:
                self.assertEqual(ref['frame_id'],read['frame_id'])
                self.assertEqual(ref['source_sha256'],read['source_sha256'])
                data=artifacts.artifact_bytes(ref['sha256'])
                self.assertEqual(hashlib.sha256(data).hexdigest(),ref['sha256'])

    def test_top_k_quality_candidates_rank_sharp_crop_without_dropping_reads(self):
        dull=self.image(127)
        sharp=self.image(127)
        for y in range(3,15):
            for x in range(2,20):
                sharp[y,x]=255 if (x+y)%2 else 0
        reads=[self.read(1,confidence=.95),self.read(2,confidence=.45)]
        for read,frame in zip(reads,(dull,sharp)):
            self.capture([read],frame)
        events.add_events(reads)
        stored=self.repository.observations(kind='plate',limit=10)
        report=artifacts.rank_read_image_candidates(stored,top_k=2)
        group=report['groups'][0]
        self.assertEqual(group['candidate_count'],2)
        sharp_digest=reads[1]['image_quality']['crop_sha256']
        self.assertEqual(group['top_k'][0]['crop_sha256'],sharp_digest)
        self.assertTrue(report['raw_reads_retained'])
        self.assertFalse(report['accuracy_claim'])
        with self.assertRaises(ValueError):artifacts.rank_read_image_candidates(stored,top_k=0)

    def test_lower_confidence_next_read_gets_its_own_frame_and_crop(self):
        first=self.read();second=self.read(2,confidence=.5,bbox=[5,6,25,20])
        self.capture([first],self.image(30));self.capture([second],self.image(120))
        for index in (0,1):
            self.assertNotEqual(first['artifacts'][index]['sha256'],second['artifacts'][index]['sha256'])
            self.assertEqual(second['artifacts'][index]['frame_id'],2)
        self.assertEqual(artifacts.summarize_read_images([first,second])['reads_with_complete_current_images'],2)

    def test_clipped_crop_and_fully_negative_box_never_wrap_numpy_indices(self):
        clipped=self.read(bbox=[-10,-5,15,12]);outside=self.read(track_id=2,bbox=[-30,0,-2,20])
        self.capture([clipped,outside])
        self.assertEqual(clipped['artifacts'][1]['crop_bbox'],[0,0,15,12])
        crop=artifacts.cv2.imdecode(np.frombuffer(artifacts.artifact_bytes(clipped['artifacts'][1]['sha256']),np.uint8),1)
        self.assertEqual(crop.shape[:2],(12,15))
        self.assertEqual(len(outside['artifacts']),1)
        self.assertEqual(outside['artifact_capture']['crop_status'],'outside_or_empty_box')
        summary=artifacts.summarize_read_images([clipped,outside])
        self.assertEqual(summary['reads_with_current_frame'],2)
        self.assertEqual(summary['reads_with_complete_current_images'],1)

    def test_empty_detection_frame_performs_no_image_io(self):
        with patch.object(artifacts,'save_image',side_effect=AssertionError('empty frame IO')):
            self.assertEqual(self.capture([]),{'image_attempts':0,'image_failures':0,'incomplete_reads':0,'storage_budget_failures':0})
        self.assertFalse(artifacts.ROOT.exists())

    def test_frame_write_failure_preserves_reads_and_reports_missing_coverage(self):
        read=self.read();save=artifacts.save_image
        def fail_frame(image,role):
            if role=='unannotated-frame-jpeg':raise OSError('fixture disk full')
            return save(image,role)
        with patch.object(artifacts,'save_image',side_effect=fail_frame):metrics=self.capture([read])
        self.assertEqual(metrics['image_failures'],1)
        self.assertEqual(read['artifact_capture']['frame_status'],'failed')
        self.assertEqual(read['artifacts'][0]['role'],'plate-crop')
        self.assertEqual(events.add_events([read]),1)
        report=events.evidence_report('KL07AB1234',self.now-1,self.now+1)
        self.assertEqual(report['artifact_coverage']['reads_with_capture_failures'],1)
        self.assertEqual(report['artifact_coverage']['reads_with_complete_current_images'],0)

    def test_crop_encoder_failure_does_not_reuse_previous_picture(self):
        read=self.read()
        with patch.object(artifacts,'save_image',side_effect=[artifacts.save_image(self.image(),'unannotated-frame-jpeg'),None]):
            metrics=self.capture([read])
        self.assertEqual(metrics['incomplete_reads'],1)
        self.assertEqual(read['artifact_capture']['crop_status'],'failed')
        self.assertEqual(len(read['artifacts']),1)

    def test_invalid_low_confidence_and_ambiguous_raw_reads_still_get_images(self):
        reads=[self.read(track_id=i,identity_status=status,plate=None,plate_norm=None,plate_raw='?')
               for i,status in enumerate(('invalid','low_confidence'),1)]
        reads.append(self.read(track_id=3,identity_status='tracking_ambiguous'))
        self.capture(reads)
        self.assertEqual(events.add_events(reads),3)
        self.assertEqual(artifacts.summarize_read_images(self.repository.observations())['reads_with_complete_current_images'],3)
        self.assertEqual(events.get_trajectory('KL07AB1234',self.now-1,self.now+1)['status'],'not_found')

    def test_summary_refuses_wrong_frame_source_crop_digest_and_legacy_claims(self):
        for key,value in [('frame_id',999),('source_sha256','b'*64),('size',True),('sha256','invalid')]:
            read=self.read();self.capture([read])
            for ref in read['artifacts']:ref[key]=value
            self.assertEqual(artifacts.summarize_read_images([read])['reads_with_complete_current_images'],0)
        read=self.read();self.capture([read]);read['artifacts'][1]['crop_bbox']=[0,0,1,1]
        self.assertEqual(artifacts.summarize_read_images([read])['reads_with_current_crop'],0)
        read=self.read();self.capture([read]);read.pop('artifact_capture')
        summary=artifacts.summarize_read_images([read])
        self.assertEqual(summary['legacy_or_manual_reads'],1)
        self.assertEqual(summary['reads_with_complete_current_images'],0)

    def test_encoder_and_atomic_write_failures_leave_no_temporary_downloads(self):
        with patch.object(artifacts.cv2,'imencode',return_value=(False,None)):
            with self.assertRaisesRegex(ValueError,'encoding failed'):artifacts.save_image(self.image(),'plate-crop')
        with patch.object(Path,'replace',side_effect=OSError('fixture disk full')):
            with self.assertRaises(OSError):artifacts.save_image(self.image(),'plate-crop')
        self.assertEqual(list(artifacts.ROOT.iterdir()),[])

    def test_corrupt_existing_image_refused_without_overwrite(self):
        ref=artifacts.save_image(self.image(),'plate-crop');path=artifacts.ROOT/(ref['sha256']+'.jpg')
        path.write_bytes(b'corrupt fixture')
        with self.assertRaisesRegex(ValueError,'verification failed'):artifacts.save_image(self.image(),'plate-crop')
        self.assertEqual(path.read_bytes(),b'corrupt fixture')

    def test_storage_budget_preserves_existing_images_and_allows_digest_reuse(self):
        ref=artifacts.save_image(self.image(),'plate-crop')
        with patch.dict(os.environ,{'AI26_ARTIFACT_MAX_BYTES':str(ref['size'])}):
            self.assertEqual(artifacts.save_image(self.image(),'plate-crop'),ref)
            with self.assertRaises(artifacts.ArtifactCapacityError):artifacts.save_image(self.image(120),'plate-crop')
            self.assertEqual(artifacts.storage_usage()['used_bytes'],ref['size'])
        self.assertEqual(len(list(artifacts.ROOT.iterdir())),1)
        self.assertIsNotNone(artifacts.artifact_bytes(ref['sha256']))

    def test_full_budget_keeps_raw_reads_with_explicit_capacity_reason(self):
        read=self.read()
        with patch.dict(os.environ,{'AI26_ARTIFACT_MAX_BYTES':'1'}):metrics=self.capture([read])
        self.assertEqual(metrics['storage_budget_failures'],2)
        self.assertEqual(read['artifacts'],[])
        self.assertEqual(read['artifact_capture']['frame_error'],'storage_budget_exceeded')
        self.assertEqual(read['artifact_capture']['crop_error'],'storage_budget_exceeded')
        self.assertEqual(events.add_events([read]),1)
        self.assertEqual(self.repository.observations()[0]['artifact_capture'],read['artifact_capture'])

    def test_retention_releases_budget_but_does_not_evict_protected_images(self):
        first=artifacts.save_image(self.image(),'plate-crop');second=artifacts.save_image(self.image(120),'plate-crop')
        for ref in (first,second):os.utime(artifacts.ROOT/(ref['sha256']+'.jpg'),(self.now-8*86400,)*2)
        with patch.dict(os.environ,{'AI26_ARTIFACT_MAX_BYTES':str(first['size']+second['size'])}):
            with self.assertRaises(artifacts.ArtifactCapacityError):artifacts.save_image(self.image(200),'plate-crop')
            artifacts.cleanup_artifacts(self.now-7*86400,{first['sha256']})
            self.assertEqual(artifacts.storage_usage()['used_bytes'],first['size'])
            third=artifacts.save_image(self.image(120),'plate-crop')
            self.assertIsNotNone(artifacts.artifact_bytes(first['sha256'],self.now+100))
            self.assertIsNotNone(artifacts.artifact_bytes(third['sha256']))

    def test_storage_usage_does_not_scan_the_directory_for_every_read_or_poll(self):
        original_glob=Path.glob
        with patch.object(artifacts,'_storage_root',None),patch.object(Path,'glob',autospec=True,side_effect=original_glob) as scan:
            self.capture([self.read()]);artifacts.storage_usage();artifacts.storage_usage()
            self.capture([self.read(2)],self.image(120))
            self.assertEqual(scan.call_count,1)

    def test_report_snapshot_zip_print_and_retention_use_all_current_reads(self):
        reads=[self.read(),self.read(2,confidence=.5)]
        for read,value in zip(reads,(30,120)):self.capture([read],self.image(value))
        events.add_events(reads)
        report=events.evidence_report('KL07AB1234',self.now-1,self.now+1)
        self.assertEqual(report['version'],3)
        self.assertEqual(report['artifact_coverage']['reads_with_complete_current_images'],2)
        self.assertTrue(report['image_review_candidates']['raw_reads_retained'])
        self.assertEqual(report['image_review_candidates']['groups'][0]['candidate_count'],2)
        route='/api/reports/'+report['report_id'];before=self.client.get(route).content
        with zipfile.ZipFile(io.BytesIO(self.client.get(route+'/package').content)) as package:
            self.assertEqual(json.loads(package.read('manifest.json')),report)
            for ref in report['artifacts']:
                self.assertEqual(hashlib.sha256(package.read('artifacts/'+ref['sha256']+'.jpg')).hexdigest(),ref['sha256'])
                path=artifacts.ROOT/(ref['sha256']+'.jpg');os.utime(path,(self.now-8*86400,)*2)
        self.assertIn('2 of 2 reads have a matching sampled frame and crop',self.client.get(route+'/print').text)
        self.assertIn('Top image review candidates',self.client.get(route+'/print').text)
        artifacts.cleanup_artifacts(self.now-7*86400,self.repository.protected_artifacts(self.now))
        self.assertEqual(self.client.get(route+'/package').status_code,200)
        third=self.read(3);self.capture([third],self.image(200));events.add_events([third])
        self.assertEqual(self.client.get(route).content,before)
        unsigned={k:v for k,v in report.items() if k!='package_hash'}
        self.assertEqual(hashlib.sha256(canonical_json(unsigned).encode()).hexdigest(),report['package_hash'])

    def test_old_report_snapshot_prints_explicit_missing_summary_and_stays_immutable(self):
        events.add_events([self.read()]);report=events.evidence_report('KL07AB1234',self.now-1,self.now+1)
        for version in (1,2):
            legacy={k:v for k,v in report.items() if k not in ('artifact_coverage','package_hash')}
            legacy.update(version=version,report_id=f'EVD-OLD-{version}')
            legacy['package_hash']=hashlib.sha256(canonical_json(legacy).encode()).hexdigest()
            self.repository.put_report(legacy)
            route='/api/reports/'+legacy['report_id']
            self.assertEqual(self.client.get(route).json(),legacy)
            self.assertIn('Image coverage is unavailable in this older report snapshot',self.client.get(route+'/print').text)

    def test_processor_later_frame_uses_current_images_and_exposes_storage_failure(self):
        path=self.root/'source.mp4';path.write_bytes(b'synthetic source identity')
        reads=iter([self.image(30),self.image(120),self.image(200)])
        capture=SimpleNamespace(isOpened=lambda:True,get=lambda key:25 if key==processing.cv2.CAP_PROP_FPS else 10000,
                                set=lambda *args:True,read=lambda:(True,next(reads)),release=lambda:None)
        camera={'id':'CAM-07','kind':'plate'}
        processor=processing.Processor(cameras=[camera],source=lambda _:path,
                annotator=lambda frame,*_:(frame,[self.read(confidence=.5)]));processor.started=self.now
        with patch.object(processing.cv2,'VideoCapture',return_value=capture):
            for offset in (1,2):
                with patch.object(processing.time,'time',return_value=self.now+offset):processor.step(camera)
            with patch.object(artifacts,'save_image',side_effect=OSError('fixture disk full')):
                with patch.object(processing.time,'time',return_value=self.now+3):processor.step(camera)
        stored=self.repository.observations(since=self.now,until=self.now+4)
        self.assertEqual(len(stored),3)
        self.assertNotEqual(stored[0]['artifacts'][0]['sha256'],stored[1]['artifacts'][0]['sha256'])
        self.assertEqual(stored[1]['artifacts'][0]['frame_id'],stored[1]['frame_id'])
        self.assertEqual(stored[2]['artifacts'],[])
        health=processor.health()[0]
        self.assertEqual(health['status'],'processing')
        self.assertEqual(health['artifact_capture']['image_failures'],2)
        self.assertEqual(health['artifact_capture']['incomplete_reads'],1)
        self.assertIn('artifact_capture_ms',health)


if __name__=='__main__':unittest.main()
