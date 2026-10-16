"""Inactive preparation, streamed request ownership and offline selection contracts."""
import asyncio
import base64
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import import_source as importer
from select_source import select_release
from source_catalog import load_release,load_source
from source_uploads import SourceUploads,UploadBusy,parse_metadata,MAX_UPLOAD_BYTES
import source_uploads
from starlette.requests import ClientDisconnect

VIDEO={'codec':'h264','pixel_format':'yuv420p','fps':10,'duration_seconds':1.,'width':320,'height':240,'frame_count':10}
META={'filename':'clip.mp4','bytes':4,'reviewer':'Local tester','reason':'Synthetic input','replace':False}
class Preparation(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.base=Path(temp.name);self.data=self.base/'data';self.root=self.base/'sources'
        self.input=self.base/'input.mp4';self.input.write_bytes(b'input')
        self.addCleanup(patch.stopall)
        patch.object(importer,'probe',return_value=VIDEO).start()
        patch.object(importer,'ffmpeg_version',return_value='Mock').start()
        patch.object(importer,'transcode',side_effect=lambda src,dst,*args:dst.write_bytes(b'preview')).start()
        patch.object(importer,'camera_source',return_value=self.base/'missing').start()
        self.manager=SourceUploads(self.data,self.root);self.addCleanup(self.manager.close)
    def prepare(self,**kw):
        return importer.import_source('CAM-07',self.input,'Tester','Synthetic',prepare=True,source_root=self.root,data_root=self.data,max_bytes=1024,**kw)
    def select(self,release,expected='default'):
        return select_release('CAM-07',release,expected,root=self.root,data_root=self.data)
    def test_prepare_during_processing_keeps_binding_and_database_untouched(self):
        self.data.mkdir();db=self.data/'ai26.sqlite3';db.write_bytes(b'Existing database')
        with (self.data/'.processing.lock').open('a+') as owner:
            fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=self.prepare()
            self.assertIsNone(load_source('CAM-07',self.root))
            self.assertTrue(result['activation_required'])
            self.assertEqual(load_release('CAM-07',result['release'],self.root,verify=True)['original'].read_bytes(),b'input')
            with self.assertRaisesRegex(ValueError,'Stop the processor'):self.select(result['release'])
        self.assertEqual(db.read_bytes(),b'Existing database')
        self.select(result['release'])
        self.assertEqual(load_source('CAM-07',self.root)['manifest']['release'],result['release'])
    def test_selection_compare_and_swap_and_idempotence(self):
        first=self.prepare();second=self.prepare()
        self.select(first['release'])
        with self.assertRaisesRegex(ValueError,'changed since preparation'):self.select(second['release'])
        third=self.prepare(replace=True)
        with self.assertRaises(ValueError):self.select(third['release'])
        self.select(third['release'],first['release'])
        self.assertTrue(self.select(third['release'])['already_selected'])
        self.assertEqual(load_release('CAM-07',third['release'],self.root)['manifest']['previous_release'],first['release'])
    def test_selection_rechecks_same_size_corruption(self):
        result=self.prepare();binding=load_release('CAM-07',result['release'],self.root)
        binding['original'].write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'digest mismatch'):self.select(result['release'])
        self.assertIsNone(load_source('CAM-07',self.root))
    def test_retained_manifest_identity_and_containment(self):
        result=self.prepare();folder=self.root/'CAM-07/releases'/result['release'];manifest=folder/'manifest.json'
        value=json.loads(manifest.read_text());value['release']='a'*32;manifest.write_text(json.dumps(value))
        with self.assertRaises(ValueError):load_release('CAM-07',result['release'],self.root)
        manifest.unlink();outside=self.base/'outside.json';outside.write_text(json.dumps(result));manifest.symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'escapes'):load_release('CAM-07',result['release'],self.root)
        with self.assertRaises(ValueError):load_release('CAM-07','../outside',self.root)
    def test_metadata_unicode_strict_types_and_limits(self):
        value={**META,'reviewer':'测试者'}
        encode=lambda val:base64.b64encode(json.dumps(val).encode()).decode()
        self.assertEqual(parse_metadata(encode(value))['reviewer'],'测试者')
        clock={**META,'recording_start_utc':'2026-10-14T12:00:00+05:30','clock_uncertainty_seconds':1.5}
        self.assertEqual(parse_metadata(encode(clock))['recording_start_utc'],clock['recording_start_utc'])
        for value in ({**META,'bytes':True},{**META,'bytes':MAX_UPLOAD_BYTES+1},{**META,'reviewer':' '},{**META,'replace':'false'},{**META,'extra':'field'}):
            with self.assertRaises(ValueError):parse_metadata(encode(value))
        for value in ({**META,'recording_start_utc':'2026-10-14T12:00:00'},
                      {**META,'clock_uncertainty_seconds':2},
                      {**META,'recording_start_utc':'2026-10-14T12:00:00Z','clock_uncertainty_seconds':True}):
            with self.assertRaises(ValueError):parse_metadata(encode(value))
        for value in ('invalid','x'*8193,None):
            with self.assertRaises(ValueError):parse_metadata(value)
    def test_single_upload_and_cross_manager_lock(self):
        job,_=self.manager.reserve('CAM-07',META)
        with self.assertRaises(UploadBusy):self.manager.reserve('CAM-08',META)
        other=SourceUploads(self.base/'other-data',self.root);self.addCleanup(other.close)
        with self.assertRaises(UploadBusy):other.reserve('CAM-08',META)
        self.manager._finish(job,'failed')
        job,_=other.reserve('CAM-08',META);other._finish(job,'cancelled')
    def test_streamed_size_mismatch_and_disconnect_release_ownership(self):
        class Request:
            async def stream(self):
                yield b'abc'
        for kind in ('short','long','disconnect','timeout'):
            job,path=self.manager.reserve('CAM-07',META)
            class Request:
                async def stream(request):
                    if kind=='timeout':raise TimeoutError()
                    if kind=='disconnect':raise ClientDisconnect()
                    yield b'abc' if kind=='short' else b'abcde'
            with self.assertRaises((ValueError,ClientDisconnect,TimeoutError)):
                asyncio.run(self.manager.receive(Request(),job,path))
            self.assertIsNone(self.manager.active);self.assertIsNone(self.manager.owner);self.assertFalse(path.exists())
            self.assertEqual(self.manager.get(job)['status'],'failed')
    def test_cancel_before_conversion_and_shutdown(self):
        job,path=self.manager.reserve('CAM-07',META);self.manager.cancel(job)
        class Request:
            async def stream(self):yield b'abcd'
        with patch.object(self.manager,'_prepare') as prepare:
            with self.assertRaises(ValueError):asyncio.run(self.manager.receive(Request(),job,path))
            prepare.assert_not_called()
        job,path=self.manager.reserve('CAM-07',META);self.manager.close()
        self.assertEqual(self.manager.get(job)['status'],'cancelled');self.assertFalse(path.parent.exists())
        with self.assertRaises(UploadBusy):self.manager.reserve('CAM-07',META)
    def test_failed_receipt_write_always_cleans_and_unlocks(self):
        job,path=self.manager.reserve('CAM-07',META)
        with patch.object(source_uploads,'atomic_json',side_effect=OSError('Disk failed')):
            with self.assertLogs('source_uploads',level='ERROR'):self.manager._finish(job,'failed')
        self.assertIsNone(self.manager.owner);self.assertFalse(path.parent.exists())
        next_job,_=self.manager.reserve('CAM-07',META);self.manager._finish(next_job,'cancelled')
    def test_shutdown_escalates_worker_that_ignores_cancellation(self):
        job,_=self.manager.reserve('CAM-07',META)
        process=unittest.mock.Mock(pid=123456789);process.poll.return_value=None
        process.wait.side_effect=[subprocess.TimeoutExpired('worker',10),0]
        thread=unittest.mock.Mock();thread.is_alive.side_effect=[True,False]
        self.manager.process=process;self.manager.thread=thread
        with patch.object(source_uploads.os,'killpg') as kill:
            self.manager.close()
        self.assertEqual([call.args[1] for call in kill.call_args_list], [source_uploads.signal.SIGTERM,source_uploads.signal.SIGTERM,source_uploads.signal.SIGKILL])
        self.assertEqual(thread.join.call_count,2)
        self.assertEqual(self.manager.get(job)['status'],'cancelled');self.assertIsNone(self.manager.owner)
        self.manager.thread=None;self.manager.process=None
    def test_receipt_survives_restart_projects_metadata_and_checks_release_presence(self):
        release=self.prepare();job,_=self.manager.reserve('CAM-07',META)
        self.manager._finish(job,'ready',release={'release':release['release'],'host_path':'private'})
        restored=SourceUploads(self.data,self.root);self.addCleanup(restored.close)
        value=restored.get(job);self.assertEqual(value['status'],'ready');self.assertNotIn('host_path',value['release'])
        (self.root/'CAM-07/releases'/release['release']/'playback.mp4').unlink()
        self.assertEqual(restored.get(job)['status'],'failed')
        with self.assertRaises(KeyError):restored.get('../outside')
    def test_worker_is_separate_bounded_process_and_never_selects(self):
        start='2026-10-14T06:30:00.000000Z'
        result=self.prepare(recording_start_utc=start,clock_uncertainty_seconds=1.5)
        metadata={**META,'recording_start_utc':start,'clock_uncertainty_seconds':1.5}
        job,path=self.manager.reserve('CAM-07',metadata);path.write_bytes(b'abcd')
        process=unittest.mock.Mock(returncode=0)
        process.communicate.return_value=(json.dumps({'release':result['release']}),'')
        process.poll.return_value=0
        with patch.object(source_uploads.subprocess,'Popen',return_value=process) as launch:
            self.manager._prepare(job,path)
        args,kwargs=launch.call_args
        self.assertIn('--prepare',args[0]);self.assertIn(str(MAX_UPLOAD_BYTES),args[0])
        self.assertIn('--recording-start-utc',args[0]);self.assertIn(start,args[0])
        self.assertIn('--clock-uncertainty-seconds',args[0]);self.assertIn('1.5',args[0])
        self.assertTrue(kwargs['start_new_session']);self.assertEqual(kwargs['env']['AI26_PROCESSING_ENABLED'],'0')
        process.communicate.assert_called_once_with(timeout=650)
        self.assertEqual(self.manager.get(job)['status'],'ready');self.assertIsNone(load_source('CAM-07',self.root))
        self.assertFalse(path.exists())
    def test_worker_binds_only_trusted_session_uploader_to_manifest(self):
        result=self.prepare();job,path=self.manager.reserve('CAM-07',META,authenticated_uploader='signed-in-operator');path.write_bytes(b'abcd')
        process=unittest.mock.Mock(returncode=0)
        process.communicate.return_value=(json.dumps({'release':result['release']}),'')
        process.poll.return_value=0
        with patch.object(source_uploads.subprocess,'Popen',return_value=process) as launch:
            self.manager._prepare(job,path)
        manifest=load_release('CAM-07',result['release'],self.root,verify=True)['manifest']
        self.assertTrue(manifest['uploader_authenticated'])
        self.assertEqual(manifest['authenticated_uploader'],'signed-in-operator')
        self.assertNotIn('signed-in-operator',launch.call_args.args[0])
        release=self.manager.get(job)['release']
        self.assertTrue(release['uploader_authenticated'])
        self.assertEqual(release['authenticated_uploader'],'signed-in-operator')
        self.assertEqual(release['reviewer'],'Tester')
        restored=SourceUploads(self.data,self.root);self.addCleanup(restored.close)
        persisted=restored.get(job)['release']
        self.assertTrue(persisted['uploader_authenticated'])
        self.assertEqual(persisted['authenticated_uploader'],'signed-in-operator')
    def test_worker_failure_and_timeout_release_ownership(self):
        for timeout in (False,True):
            job,path=self.manager.reserve('CAM-07',META)
            process=unittest.mock.Mock(returncode=1);process.poll.return_value=None;process.pid=123456789
            process.communicate.side_effect=subprocess.TimeoutExpired('import',650) if timeout else None
            process.communicate.return_value=('','Bad video')
            with patch.object(source_uploads.subprocess,'Popen',return_value=process),patch.object(source_uploads.os,'killpg'):
                with self.assertLogs('source_uploads'):self.manager._prepare(job,path)
            self.assertEqual(self.manager.get(job)['status'],'failed');self.assertIsNone(self.manager.owner)
    def test_cancel_waits_for_disk_write_before_file_cleanup(self):
        started=threading.Event();finished=threading.Event();allow=threading.Event()
        def write():started.set();allow.wait(2);finished.set()
        async def scenario():
            task=asyncio.create_task(SourceUploads._write(write))
            await asyncio.to_thread(started.wait,1);task.cancel();allow.set()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertTrue(finished.is_set())
        asyncio.run(scenario())
    def test_cancelled_reservation_is_cleaned_after_thread_finishes(self):
        original=self.manager.reserve;started=threading.Event();allow=threading.Event()
        def reserve(*args):started.set();allow.wait(2);return original(*args)
        async def scenario():
            with patch.object(self.manager,'reserve',side_effect=reserve):
                task=asyncio.create_task(self.manager.reserve_async('CAM-07',META))
                await asyncio.to_thread(started.wait,1);task.cancel();allow.set()
                with self.assertRaises(asyncio.CancelledError):await task
            self.assertIsNone(self.manager.active);self.assertIsNone(self.manager.owner)
        asyncio.run(scenario())
    def test_memory_receipts_are_bounded_and_remain_on_disk(self):
        first=None
        for i in range(17):
            job,_=self.manager.reserve('CAM-07',META);first=first or job;self.manager._finish(job,'cancelled')
        self.assertEqual(len(self.manager.jobs),16);self.assertNotIn(first,self.manager.jobs)
        self.assertEqual(self.manager.get(first)['status'],'cancelled')
    def test_api_rejects_bad_requests_and_exposes_receipt_without_activation(self):
        import main
        from fastapi.testclient import TestClient
        client=TestClient(main.app)
        header=base64.b64encode(json.dumps(META).encode()).decode()
        headers={'content-type':'application/octet-stream','x-ai26-upload':header}
        with patch.object(main,'uploads',self.manager),patch.object(self.manager,'_prepare'):
            self.assertEqual(client.post('/api/cameras/CAM-99/source/prepare',content=b'abcd',headers=headers).status_code,404)
            self.assertEqual(client.post('/api/cameras/CAM-07/source/prepare',content=b'abcd').status_code,415)
            self.assertEqual(client.post('/api/cameras/CAM-07/source/prepare',content=b'abc',headers=headers).status_code,422)
            response=client.post('/api/cameras/CAM-07/source/prepare',content=b'abcd',headers=headers)
            self.assertEqual(response.status_code,202);job=response.json()['job_id']
            self.assertEqual(client.get('/api/source-preparations/'+job).json()['status'],'preparing')
            self.assertEqual(client.post('/api/cameras/CAM-08/source/prepare',content=b'abcd',headers=headers).status_code,409)
            self.assertEqual(client.get('/api/source-preparations/not-a-job').status_code,404)
            self.assertIsNone(load_source('CAM-07',self.root));self.manager._finish(job,'cancelled')
    def test_authenticated_api_upload_uses_session_account_not_header_claim(self):
        import main
        from fastapi.testclient import TestClient
        session={'username':'verified-uploader','role':'operator','csrf_token':'csrf'}
        auth_service=unittest.mock.MagicMock();auth_service.session.return_value=session;auth_service.can_access_case.return_value=True
        header=base64.b64encode(json.dumps(META).encode()).decode()
        with patch.object(main,'auth_enabled',return_value=True),patch.object(main,'AuthService',return_value=auth_service),patch.object(main.store,'case_camera_ids',return_value=['CAM-07']),patch.object(main,'uploads',self.manager),patch.object(self.manager,'_prepare'):
            response=TestClient(main.app).post('/api/cameras/CAM-07/source/prepare',content=b'abcd',
                headers={'content-type':'application/octet-stream','x-ai26-upload':header,main.CSRF_HEADER:'csrf','X-AI26-Case-ID':'CASE-1','X-AI26-Purpose':'system_test'},
                cookies={main.SESSION_COOKIE:'session'})
        self.assertEqual(response.status_code,202,response.text)
        self.assertEqual(self.manager.active['metadata']['_authenticated_uploader'],'verified-uploader')
        self.assertEqual(self.manager.active['metadata']['reviewer'],'Local tester')
        auth_service.audit_sensitive_access.assert_called_once()
        self.manager._finish(response.json()['job_id'],'cancelled')

if __name__=='__main__':unittest.main()
