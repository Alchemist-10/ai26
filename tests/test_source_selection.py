"""Browser selection changes next-startup files, never the running decoder binding."""
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import cameras
import import_source
import main
import source_selection as selector
from source_catalog import load_source
from source_status import source_status
from fastapi.testclient import TestClient

class SourceSelection(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.base=Path(temp.name);self.root=self.base/'sources';self.data=self.base/'data';self.data.mkdir()
        self.addCleanup(patch.stopall)
        patch.dict(cameras.MANAGED_SOURCES,{},clear=True).start()
        patch.dict(cameras.CAMERAS_BY_ID,{'CAM-07':{'path':str(self.base/'missing')}}).start()
        patch.object(cameras,'PLAYBACK_ROOT',self.base/'proxies').start()
        patch.object(main,'select_for_restart',side_effect=lambda cam,body:selector.select_for_restart(cam,body,root=self.root)).start()
        patch.object(main,'source_status',side_effect=lambda cam:source_status(cam,self.root)).start()
        self.client=TestClient(main.app)
    def release(self,index,previous=None,select=False):
        release=f'{index:032x}';folder=self.root/'CAM-07/releases'/release;folder.mkdir(parents=True)
        manifest={'version':1,'camera_id':'CAM-07','release':release,'previous_release':previous,'reviewer':'Synthetic import','reason':'Synthetic fixture','time_basis':'replay_clock'}
        for role,name in [('original','original.media'),('playback','playback.mp4')]:
            content=f'{role} {index}'.encode();(folder/name).write_bytes(content)
            manifest[role]={'file':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
        (folder/'manifest.json').write_text(json.dumps(manifest))
        if select:(self.root/'CAM-07/active.json').write_text(json.dumps(manifest))
        return manifest
    def body(self,target,intent='select',token=None):
        return {'release':target['release'],'expected_token':token or selector.selection_token(load_source('CAM-07',self.root)),
                'intent':intent,'reviewer':'Local operator','reason':'Synthetic selection check'}
    def select(self,target,intent='select',token=None):
        return selector.select_for_restart('CAM-07',self.body(target,intent,token),root=self.root)
    def test_selection_while_processing_retains_cached_original_playback_and_no_sql(self):
        first=self.release(1,select=True);binding=load_source('CAM-07',self.root,verify=True);cameras.MANAGED_SOURCES['CAM-07']=binding
        second=self.release(2,first['release'])
        store=MagicMock()
        with (self.data/'.processing.lock').open('a+') as owner,patch.object(main,'store',store):
            fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
            response=self.client.post('/api/cameras/CAM-07/source/selection',json=self.body(second))
        self.assertEqual(response.status_code,200);result=response.json()['source']
        self.assertEqual(result['selection']['status'],'restart_required');self.assertEqual(result['active']['release']['release'],first['release'])
        self.assertEqual(cameras.camera_source('CAM-07'),binding['original'])
        self.assertEqual(self.client.get('/api/video/CAM-07').content,b'playback 1');self.assertEqual(store.mock_calls,[])
        self.assertEqual((binding['original'].parent/'manifest.json').read_text(),json.dumps(first))
        claim=result['selection']['last_action'];receipt=self.root/'CAM-07/selection_history'/f"{claim['id']}.json"
        self.assertEqual(json.loads(receipt.read_text())['reviewer'],'Local operator')
        self.assertNotIn(str(self.base),json.dumps(result))
    def test_restart_then_rollback_requires_restart_and_keeps_both_old_roles(self):
        first=self.release(1,select=True);second=self.release(2,first['release']);self.select(second)
        cameras.MANAGED_SOURCES['CAM-07']=load_source('CAM-07',self.root,verify=True)
        self.select(first,'rollback');result=source_status('CAM-07',self.root)
        self.assertEqual(result['selection']['status'],'restart_required');self.assertEqual(result['active']['release']['release'],second['release'])
        self.assertEqual(self.client.get('/api/video/CAM-07').content,b'playback 2')
        cameras.MANAGED_SOURCES['CAM-07']=load_source('CAM-07',self.root,verify=True)
        self.assertEqual(source_status('CAM-07',self.root)['selection']['status'],'current')
        self.assertEqual(self.client.get('/api/video/CAM-07').content,b'playback 1')
    def test_revert_pending_selection_to_running_release_clears_restart_notice(self):
        first=self.release(1,select=True);cameras.MANAGED_SOURCES['CAM-07']=load_source('CAM-07',self.root)
        second=self.release(2,first['release']);self.select(second);self.select(first,'rollback')
        self.assertEqual(source_status('CAM-07',self.root)['selection']['status'],'current')
    def test_token_protects_against_stale_requests_and_return_to_same_release(self):
        first=self.release(1,select=True);token=self.body(first)['expected_token'];second=self.release(2,first['release'])
        self.select(second);self.select(first,'rollback')
        with self.assertRaises(selector.SelectionConflict):self.select(second,token=token)
        self.assertNotEqual(token,self.body(first)['expected_token'])
    def test_token_ignores_json_formatting_but_tracks_manifest_edits(self):
        first=self.release(1,select=True);old=self.body(first)['expected_token'];pointer=self.root/'CAM-07/active.json'
        pointer.write_text(json.dumps(first,indent=4,sort_keys=True));self.assertEqual(old,self.body(first)['expected_token'])
        pointer.write_text(json.dumps({**first,'reason':'Edited'}));self.assertNotEqual(old,self.body(first)['expected_token'])
    def test_wrong_preparation_base_and_unlinked_rollback_reject(self):
        first=self.release(1,select=True);second=self.release(2)
        with self.assertRaises(selector.SelectionConflict):self.select(second)
        with self.assertRaisesRegex(ValueError,'displayed parent'):self.select(second,'rollback')
        self.assertEqual(load_source('CAM-07',self.root)['manifest']['release'],first['release'])
    def test_rollback_bounds_and_invalid_parent_reference(self):
        previous=None
        for index in range(1,12):previous=self.release(index,previous,select=True)['release']
        with self.assertRaises(ValueError):self.select({'release':f'{1:032x}'},'rollback')
        pointer=self.root/'CAM-07/active.json';value=json.loads(pointer.read_text())
        for invalid in ('../outside',{},[],False,12):
            value['previous_release']=invalid;pointer.write_text(json.dumps(value))
            with self.assertRaises(ValueError):self.select({'release':f'{10:032x}'},'rollback')
        self.assertEqual(len(list((self.root/'CAM-07').glob('selection_history/*.json'))),0)
    def test_both_file_hashes_rechecked_and_pointer_preserved(self):
        first=self.release(1,select=True);second=self.release(2,first['release']);pointer=self.root/'CAM-07/active.json';old=pointer.read_bytes()
        for role,name in [('original','original.media'),('playback','playback.mp4')]:
            path=self.root/'CAM-07/releases'/second['release']/name;original=path.read_bytes();path.write_bytes(b'x'*len(original))
            with self.assertRaisesRegex(ValueError,'digest mismatch'):self.select(second)
            self.assertEqual(pointer.read_bytes(),old);path.write_bytes(original)
    def test_publication_failure_preserves_prior_pointer_and_removes_proposal(self):
        first=self.release(1,select=True);second=self.release(2,first['release']);pointer=self.root/'CAM-07/active.json';old=pointer.read_bytes();real=selector.atomic_json
        def fail(path,value):
            if path.name=='active.json':raise OSError('Synthetic publication failure')
            real(path,value)
        with patch.object(selector,'atomic_json',side_effect=fail):
            with self.assertRaises(OSError):self.select(second)
        self.assertEqual(pointer.read_bytes(),old);self.assertFalse(list((self.root/'CAM-07/selection_history').glob('*.json')))
    def test_interrupted_return_after_publication_keeps_committed_record(self):
        first=self.release(1,select=True);second=self.release(2,first['release']);real=selector.atomic_json
        def interrupt(path,value):
            real(path,value)
            if path.name=='active.json':raise KeyboardInterrupt()
        with patch.object(selector,'atomic_json',side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):self.select(second)
        marker=load_source('CAM-07',self.root)['manifest']['source_selection']
        self.assertTrue((self.root/'CAM-07/selection_history'/f"{marker['id']}.json").exists())
    def test_successive_committed_records_link_and_idempotent_selection_does_not_append(self):
        first=self.release(1,select=True);second=self.release(2,first['release']);self.select(second)
        one=load_source('CAM-07',self.root)['manifest']['source_selection'];self.select(first,'rollback')
        two=load_source('CAM-07',self.root)['manifest']['source_selection'];self.assertEqual(two['previous_selection'],one['id'])
        self.assertTrue(self.select(first,'rollback')['already_selected'])
        self.assertEqual(len(list((self.root/'CAM-07/selection_history').glob('*.json'))),2)
    def test_selection_record_symlink_escape_rejects_without_pointer_changes(self):
        first=self.release(1,select=True);second=self.release(2,first['release']);outside=self.base/'outside';outside.mkdir()
        (self.root/'CAM-07/selection_history').symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'escape'):self.select(second)
        self.assertEqual(list(outside.iterdir()),[]);self.assertEqual(load_source('CAM-07',self.root)['manifest']['release'],first['release'])
    def test_api_validation_conflict_ownership_and_missing_files_are_explicit(self):
        first=self.release(1,select=True);second=self.release(2,first['release']);body=self.body(second)
        for change in ({'reviewer':' '},{'reason':False},{'intent':'activate'},{'release':'../bad'},{'expected_token':'bad'},{'extra':'field'}):
            self.assertEqual(self.client.post('/api/cameras/CAM-07/source/selection',json={**body,**change}).status_code,422)
        self.assertEqual(self.client.post('/api/cameras/CAM-99/source/selection',json=body).status_code,404)
        with (self.root/'.import.lock').open('a+') as owner:
            fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.client.post('/api/cameras/CAM-07/source/selection',json=body).status_code,409)
        self.select(second)
        self.assertEqual(self.client.post('/api/cameras/CAM-07/source/selection',json=body).status_code,409)
        (self.root/'CAM-07/releases'/first['release']/'playback.mp4').unlink()
        response=self.client.post('/api/cameras/CAM-07/source/selection',json=self.body(first,'rollback'))
        self.assertEqual(response.status_code,422);self.assertNotIn(str(self.base),response.text)

if __name__=='__main__':unittest.main()
