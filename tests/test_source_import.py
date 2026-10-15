"""Offline source publication/recovery contracts; mocked video tools, isolated files."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import cameras
import import_source as importer
from source_catalog import load_source, load_catalog
from source_status import release_summary

REAL_PROBE=importer.probe
VIDEO={'codec':'h264','pixel_format':'yuv420p','fps':10,'duration_seconds':1.,'width':320,'height':240,'frame_count':10}


class SourceImport(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.base=Path(self.folder.name);self.root=self.base/'sources';self.data=self.base/'data'
        self.input=self.base/'input.mp4';self.input.write_bytes(b'original-video-bytes')
        self.addCleanup(patch.stopall)
        self.probe=patch.object(importer,'probe',return_value=dict(VIDEO)).start()
        patch.object(importer,'ffmpeg_version',return_value='Mock FFmpeg for isolated contracts').start()
        self.transcode=patch.object(importer,'transcode',side_effect=lambda source,dest,*args:dest.write_bytes(b'browser-playback')).start()
        patch.object(importer,'camera_source',return_value=self.base/'missing.mp4').start()

    def run_import(self,**extra):
        return importer.import_source('CAM-07',self.input,'Local tester','Synthetic isolated input',source_root=self.root,data_root=self.data,max_bytes=1024,**extra)

    def test_copy_hashes_roles_and_no_models_or_sql(self):
        result=self.run_import();loaded=load_source('CAM-07',self.root,verify=True)
        self.assertEqual(loaded['original'].read_bytes(),self.input.read_bytes())
        self.assertEqual(result['original']['sha256'],hashlib.sha256(self.input.read_bytes()).hexdigest())
        self.assertNotEqual(loaded['original'],loaded['playback'])
        self.assertEqual(result['time_basis'],'replay_clock');self.assertTrue(result['restart_required'])
        self.assertFalse((self.data/'ai26.sqlite3').exists());self.assertEqual(self.input.read_bytes(),b'original-video-bytes')

    def test_optional_recording_clock_is_retained_as_an_unverified_claim(self):
        result=self.run_import(recording_start_utc='2026-10-14T12:00:00+05:30',clock_uncertainty_seconds=2.5)
        self.assertEqual(result['recording_clock'],{
            'start_utc':'2026-10-14T06:30:00.000000Z',
            'start_epoch':1791959400.0,
            'uncertainty_seconds':2.5,
            'provenance':'operator_claimed',
            'status':'unverified',
        })
        loaded=load_source('CAM-07',self.root,verify=True)
        self.assertEqual(loaded['manifest']['recording_clock'],result['recording_clock'])
        self.assertEqual(release_summary(loaded['manifest'])['recording_clock'],{
            'start_utc':'2026-10-14T06:30:00.000000Z',
            'uncertainty_seconds':2.5,
            'provenance':'operator_claimed',
            'status':'unverified',
        })

    def test_invalid_recording_clock_publishes_nothing(self):
        for start,uncertainty in (('2026-10-14T12:00:00',None),(None,1),('not-a-date',None),
                                  ('2026-10-14T12:00:00Z',float('inf'))):
            with self.subTest(start=start,uncertainty=uncertainty),self.assertRaises(ValueError):
                self.run_import(recording_start_utc=start,clock_uncertainty_seconds=uncertainty)
        self.assertFalse((self.root/'CAM-07'/'active.json').exists())

    def test_check_has_no_directory_or_conversion_side_effect(self):
        result=self.run_import(check=True)
        self.assertTrue(result['check_only']);self.assertFalse(self.root.exists());self.assertFalse(self.data.exists())
        self.assertTrue(importer.import_source('CAM-07',self.input,check=True,source_root=self.root,data_root=self.data)['check_only'])
        self.transcode.assert_not_called()

    def test_replace_is_explicit_and_keeps_prior_release(self):
        first=self.run_import()
        with self.assertRaisesRegex(ValueError,'--replace'):self.run_import()
        self.input.write_bytes(b'new-immutable-original')
        second=self.run_import(replace=True)
        self.assertEqual(second['previous_release'],first['release'])
        self.assertEqual((self.root/'CAM-07/releases'/first['release']/'original.media').read_bytes(),b'original-video-bytes')
        self.assertEqual(load_source('CAM-07',self.root)['manifest']['release'],second['release'])

    def test_existing_default_source_requires_explicit_replace(self):
        with patch.object(importer,'camera_source',return_value=self.input):
            with self.assertRaisesRegex(ValueError,'--replace'):self.run_import()
        self.assertFalse((self.root/'CAM-07/active.json').exists())

    def test_active_processor_and_importer_ownership_reject(self):
        self.data.mkdir()
        with (self.data/'.processing.lock').open('a+') as owner:
            fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'Stop the processor'):self.run_import()
        self.root.mkdir(exist_ok=True)
        with (self.root/'.import.lock').open('a+') as owner:
            fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'Another source import'):self.run_import()
        self.transcode.assert_not_called()

    def test_conversion_failure_preserves_pointer_and_removes_staging(self):
        first=self.run_import();old=(self.root/'CAM-07/active.json').read_bytes()
        self.transcode.side_effect=subprocess.TimeoutExpired('ffmpeg',1)
        with self.assertRaises(subprocess.TimeoutExpired):self.run_import(replace=True)
        self.assertEqual((self.root/'CAM-07/active.json').read_bytes(),old)
        self.assertEqual(len(list((self.root/'CAM-07/releases').iterdir())),1)
        self.assertFalse(list((self.root/'CAM-07').glob('.import-*')))
        self.assertEqual(load_source('CAM-07',self.root)['manifest']['release'],first['release'])

    def test_failed_pointer_publication_removes_only_new_release(self):
        self.run_import();old=(self.root/'CAM-07/active.json').read_bytes();real=importer.atomic_json
        def fail(path,value):
            if path.name=='active.json':raise OSError('Simulated publication failure')
            return real(path,value)
        with patch.object(importer,'atomic_json',side_effect=fail):
            with self.assertRaises(OSError):self.run_import(replace=True)
        self.assertEqual((self.root/'CAM-07/active.json').read_bytes(),old)
        self.assertEqual(len(list((self.root/'CAM-07/releases').iterdir())),1)

    def test_interruption_after_publication_keeps_active_release(self):
        real=importer.atomic_json
        def interrupted(path,value):
            real(path,value)
            if path.name=='active.json':raise KeyboardInterrupt()
        with patch.object(importer,'atomic_json',side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):self.run_import()
        self.assertIsNotNone(load_source('CAM-07',self.root,verify=True))

    def test_invalid_input_and_limits_publish_nothing(self):
        for kwargs in ({'max_bytes':0},{'max_bytes':2},{'timeout':float('nan')},{'timeout':0}):
            options=dict(source_root=self.root,data_root=self.data);options.update(kwargs)
            with self.assertRaises(ValueError):importer.import_source('CAM-07',self.input,'tester','reason',**options)
        for camera,reviewer,reason in [('CAM-99','tester','reason'),('CAM-07',' ','reason'),('CAM-07','tester',' ')]:
            with self.assertRaises(ValueError):importer.import_source(camera,self.input,reviewer,reason,source_root=self.root,data_root=self.data)
        self.assertFalse((self.root/'CAM-07/active.json').exists())

    def test_changed_input_during_copy_is_rejected(self):
        real_open=Path.open
        @contextmanager
        def changing_stream():
            with real_open(self.input,'rb') as incoming:
                class Reader:
                    def read(reader, size):
                        chunk=incoming.read(size)
                        if not chunk:
                            with real_open(self.input,'ab') as outgoing:outgoing.write(b'changed')
                        return chunk
                yield Reader()
        def open_file(path, mode='r', *args, **kwargs):
            return changing_stream() if path==self.input and mode=='rb' else real_open(path,mode,*args,**kwargs)
        with patch.object(Path,'open',open_file):
            with self.assertRaisesRegex(ValueError,'changed during copying'):self.run_import()
        self.transcode.assert_not_called();self.assertFalse((self.root/'CAM-07/active.json').exists())

    def test_proxy_codec_duration_count_and_size_failures_not_published(self):
        for change in ({'codec':'hevc'},{'pixel_format':'yuv444p'},{'duration_seconds':.1},{'frame_count':9}):
            self.probe.side_effect=lambda path:dict(VIDEO,**change) if path.name=='playback.mp4' else dict(VIDEO)
            with self.assertRaises(ValueError):self.run_import()
        self.probe.side_effect=None
        self.transcode.side_effect=lambda source,dest,*args:dest.write_bytes(b'x'*1024)
        with self.assertRaisesRegex(ValueError,'size limit'):self.run_import()
        self.assertFalse((self.root/'CAM-07/active.json').exists())

    def test_corrupt_missing_and_traversal_binding_never_fall_back(self):
        self.run_import();pointer=self.root/'CAM-07/active.json';manifest=json.loads(pointer.read_text())
        for change in ({'release':'../outside'},{'camera_id':'CAM-08'},{'version':2},{'version':True},{'original':{'file':'../../outside','bytes':1,'sha256':'a'*64}}):
            pointer.write_text(json.dumps({**manifest,**change}))
            with self.assertRaises(ValueError):load_source('CAM-07',self.root)
        pointer.write_text(json.dumps(manifest));binding=load_source('CAM-07',self.root)
        binding['original'].write_bytes(b'x'*manifest['original']['bytes'])
        with self.assertRaisesRegex(ValueError,'digest mismatch'):load_catalog(['CAM-07'],self.root)
        binding['original'].unlink()
        with self.assertRaises(ValueError):load_source('CAM-07',self.root)

    def test_managed_priority_and_process_cache_stay_consistent(self):
        self.run_import();bindings=load_catalog(['CAM-07'],self.root)
        with patch.object(cameras,'MANAGED_SOURCES',bindings):
            original=cameras.camera_source('CAM-07');playback=cameras.camera_playback_source('CAM-07')
            self.input.write_bytes(b'other-input');self.run_import(replace=True)
            self.assertEqual(cameras.camera_source('CAM-07'),original)
            self.assertEqual(cameras.camera_playback_source('CAM-07'),playback)
            self.assertNotEqual(load_catalog(['CAM-07'],self.root)['CAM-07']['original'],original)
            with patch('source_catalog.file_digest',side_effect=AssertionError('No hashing on source lookup')), patch.object(Path,'read_text',side_effect=AssertionError('No manifest reads on source lookup')):
                self.assertEqual(cameras.camera_source('CAM-07'),original)
                self.assertEqual(cameras.camera_playback_source('CAM-07'),playback)

    def test_source_root_symlink_escape_rejected(self):
        self.root.mkdir();outside=self.base/'outside';outside.mkdir();(self.root/'CAM-07').symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'escape'):self.run_import()
        self.assertFalse(list(outside.iterdir()))

    def test_probe_rejects_missing_and_invalid_video_metadata(self):
        for payload in ({'streams':[]},{'streams':[{'avg_frame_rate':'0/0','width':320,'height':240,'duration':'1'}]},
                        {'streams':[{'avg_frame_rate':'10/1','width':320,'height':240,'duration':'NaN'}]}):
            with patch.object(subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(payload),'')):
                with self.assertRaises(ValueError):REAL_PROBE(self.input)


if __name__=='__main__':unittest.main()
