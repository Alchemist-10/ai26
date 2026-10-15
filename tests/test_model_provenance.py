"""Exact-file provenance contracts use small files and stub model sessions, with no downloads."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

os.environ['AI26_PROCESSING_ENABLED']='0'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import model_provenance as provenance


class ModelFiles(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        self.source=self.root/'source.onnx';self.source.write_bytes(b'fixture model bytes')

    def snapshot(self): return provenance.snapshot_model_file(self.source,self.root/'models','ocr_weights')

    def test_digest_matches_copied_bytes_and_hides_absolute_paths(self):
        path,record=self.snapshot()
        self.assertEqual(record['sha256'],hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(record['size'],len(self.source.read_bytes()))
        self.assertEqual(path.read_bytes(),self.source.read_bytes())
        self.assertEqual(path.stem,record['sha256'])
        self.assertNotIn(str(self.root),json.dumps(record))
        self.assertEqual(len(list((self.root/'models').iterdir())),1)

    def test_same_bytes_reuse_snapshot_and_changed_cache_gets_new_digest(self):
        first,record=self.snapshot();self.assertEqual(self.snapshot(),(first,record))
        self.source.write_bytes(b'different model bytes')
        second,new=self.snapshot()
        self.assertNotEqual(record['sha256'],new['sha256'])
        self.assertEqual(first.read_bytes(),b'fixture model bytes')
        self.assertEqual(second.read_bytes(),b'different model bytes')

    def test_corrupt_snapshot_refused_without_overwrite(self):
        path,record=self.snapshot();path.write_bytes(b'x'*record['size'])
        with self.assertRaisesRegex(ValueError,'digest verification'):
            self.snapshot()
        self.assertEqual(path.read_bytes(),b'x'*record['size'])
        self.assertEqual(len(list((self.root/'models').iterdir())),1)

    def test_empty_missing_and_initialization_mutation_fail_explicitly(self):
        self.source.write_bytes(b'')
        with self.assertRaisesRegex(ValueError,'empty'): self.snapshot()
        self.assertEqual(list((self.root/'models').iterdir()),[])
        self.source.unlink()
        with self.assertRaises(FileNotFoundError): self.snapshot()
        self.source.write_bytes(b'original')
        path,record=self.snapshot();path.write_bytes(b'changed!')
        with self.assertRaisesRegex(ValueError,'changed'):
            provenance.verify_model_files([(path,record)])

    def test_pipeline_components_are_exact_and_change_with_source(self):
        names=('inference.py','model_provenance.py','model_rollout.py','tracking.py','fusion.py','plate_format.py','processing.py','artifacts.py','cameras.py','source_catalog.py')
        for name in names: (self.root/name).write_text(name)
        first=provenance.pipeline_components(self.root)
        self.assertEqual(set(first),set(names))
        (self.root/'fusion.py').write_text('changed consensus')
        second=provenance.pipeline_components(self.root)
        self.assertNotEqual(first['fusion.py'],second['fusion.py'])
        self.assertEqual(first['tracking.py'],second['tracking.py'])

    def loader_fixtures(self):
        weights=self.root/'ocr.onnx';weights.write_bytes(b'OCR fixture')
        config=self.root/'config.yaml';config.write_bytes(b'fixture_config: true')
        session=SimpleNamespace(get_providers=lambda:['CPUExecutionProvider'])
        detector=SimpleNamespace(model=session,predict=lambda _:[])
        ocr=SimpleNamespace(ocr_model=SimpleNamespace(model=session),predict=lambda _:None)
        create=Mock(return_value=detector);create_ocr=Mock(return_value=ocr)
        combine=Mock(return_value=SimpleNamespace(predict=lambda _:[]))
        detector_download=Mock(return_value=self.source)
        ocr_download=Mock(return_value=(weights,config))
        modules={'onnxruntime':SimpleNamespace(SessionOptions=SimpleNamespace,get_available_providers=lambda:['CPUExecutionProvider']),
                 'fast_alpr':SimpleNamespace(ALPR=combine),'fast_alpr.default_ocr':SimpleNamespace(DefaultOCR=create_ocr),
                 'open_image_models':SimpleNamespace(create_detector=create),
                 'open_image_models.detection.core.hub':SimpleNamespace(
                    DETECTION_MODELS={provenance.DETECTOR_MODEL:SimpleNamespace(backend='yolo_v9',class_labels=('License Plate',))},
                    download_model=detector_download),
                 'fast_plate_ocr.inference.hub':SimpleNamespace(download_model=ocr_download)}
        return modules,create,create_ocr,combine,detector_download,ocr_download

    def test_loader_binds_explicit_snapshots_to_both_sessions_and_thread_budget(self):
        modules,create,create_ocr,combine,download,ocr_download=self.loader_fixtures()
        with patch.dict(sys.modules,modules),patch.object(provenance,'version',return_value='fixture'):
            model,metadata=provenance.load_plate_model(self.root/'models',cpu_threads=2)
        self.assertEqual(metadata['weight_provenance_status'],'hashed_loaded_files')
        self.assertEqual({r['role'] for r in metadata['model_files']},
                         {'plate_detector_weights','ocr_weights','ocr_configuration'})
        paths=[create.call_args.args[0],create_ocr.call_args.kwargs['model_path'],create_ocr.call_args.kwargs['config_path']]
        for path,record in zip(paths,metadata['model_files']):
            self.assertEqual(provenance.file_sha256(path),record['sha256'])
        self.assertIsNone(create_ocr.call_args.kwargs['hub_ocr_model'])
        self.assertEqual(create.call_args.kwargs['providers'],['CPUExecutionProvider'])
        options=create.call_args.kwargs['sess_options']
        self.assertEqual(options.intra_op_num_threads,2);self.assertEqual(options.inter_op_num_threads,1)
        self.assertEqual(download.call_count,1);self.assertEqual(ocr_download.call_count,1)
        self.assertEqual(metadata['ocr_execution_providers'],['CPUExecutionProvider'])
        self.assertEqual(model.predict(None),[])

    def test_loader_failure_does_not_return_partial_provenance(self):
        modules,create,create_ocr,combine,_,_=self.loader_fixtures()
        create.side_effect=RuntimeError('fixture session initialization failure')
        with patch.dict(sys.modules,modules),self.assertRaisesRegex(RuntimeError,'initialization failure'):
            provenance.load_plate_model(self.root/'models')
        self.assertEqual(create_ocr.call_count,0);self.assertEqual(combine.call_count,0)


class InferenceProvenance(unittest.TestCase):
    def module(self):
        fake_torch=SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:False),
                                  set_num_threads=lambda _:None,get_num_threads=lambda:2,__version__='fixture')
        modules={'torch':fake_torch,'ultralytics':SimpleNamespace(YOLO=lambda _:SimpleNamespace())}
        spec=importlib.util.spec_from_file_location('inference_provenance_contract',ROOT/'backend/inference.py')
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,modules): spec.loader.exec_module(module)
        return module

    def test_vehicle_model_is_created_lazily_and_hashed_on_first_use(self):
        module=self.module()
        with tempfile.TemporaryDirectory() as folder:
            checkpoint=Path(folder)/'fixture.pt';checkpoint.write_bytes(b'pinned vehicle checkpoint')
            digest=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
            model=SimpleNamespace(
                task='detect',
                names={0:'person',2:'car',3:'motorcycle',5:'bus',7:'truck'},
                predict=Mock(return_value=[SimpleNamespace(boxes=SimpleNamespace(cls=[]))]),
            )
            loader=Mock(return_value=model)
            configuration={'stable':{'path':checkpoint,'expected_sha256':digest},'canary':None}
            record={'sha256':digest,'size':checkpoint.stat().st_size,'filename':checkpoint.name}
            with patch.object(module,'_vehicle_rollout',configuration), \
                 patch.object(module,'snapshot_model_file',return_value=(checkpoint,record)), \
                 patch.object(module,'verify_model_files'),patch.object(module,'YOLO',loader):
                self.assertEqual(module._vehicle_models,{})
                self.assertIs(module._vehicle_model(),model)
                self.assertIs(module._vehicle_model(),model)
            self.assertEqual(loader.call_count,1)
            self.assertEqual(module._model_metadata['checkpoint_sha256'],digest)
            self.assertEqual(module._model_metadata['model_profile'],'stable')
            self.assertEqual(module._model_metadata['model_id'],f'ultralytics-yolo:stable:{digest}')
            self.assertEqual(module._model_metadata['compatibility']['preflight_status'],'passed')
            self.assertEqual(configuration['stable']['compatibility']['required_class_ids'],[2,3,5,7])

    def test_lazy_failure_retries_and_success_initializes_once(self):
        module=self.module();model=SimpleNamespace(predict=lambda _:[])
        metadata={'weight_provenance_status':'hashed_loaded_files'}
        loader=Mock(side_effect=[RuntimeError('download failed'),(model,metadata)])
        with patch.object(module,'load_plate_model',loader):
            with self.assertRaisesRegex(RuntimeError,'download failed'):module._plate_model()
            self.assertIsNone(module._alpr);self.assertIsNone(module._alpr_metadata)
            self.assertIs(module._plate_model(),model);self.assertIs(module._plate_model(),model)
        self.assertEqual(loader.call_count,2)
        self.assertEqual(module._alpr_metadata,metadata)

    def test_all_raw_read_branches_keep_the_same_initialized_provenance(self):
        import numpy as np
        module=self.module()
        def result(x,text,confidence):
            return SimpleNamespace(detection=SimpleNamespace(bounding_box=SimpleNamespace(x1=x,y1=0,x2=x+4,y2=4)),
                                   ocr=SimpleNamespace(text=text,confidence=confidence))
        outputs=[result(0,'KL07AB1234',.9),result(20,'bad plate',.9),result(40,'TN22ZZ0007',.1)]
        model=SimpleNamespace(predict=lambda _:outputs)
        metadata={'weight_provenance_status':'hashed_loaded_files','model_files':[{'role':'ocr_weights','sha256':'a'*64}]}
        loader=Mock(return_value=(model,metadata))
        with patch.object(module,'load_plate_model',loader):
            for _ in range(3):
                _,reads=module.annotate_plate_frame(np.zeros((100,100,3),np.uint8),'CAM-07')
        self.assertEqual(loader.call_count,1)
        self.assertEqual({r['identity_status'] for r in reads},{'supported','invalid','low_confidence'})
        for read in reads:
            self.assertEqual(read['model_metadata']['model_files'],metadata['model_files'])
            self.assertEqual(set(read['model_metadata']['pipeline_components_sha256']),
                             {'inference.py','model_provenance.py','model_rollout.py','tracking.py','fusion.py','plate_format.py','processing.py','artifacts.py','cameras.py','source_catalog.py'})

    def test_vehicle_digest_mismatch_fails_before_model_load(self):
        module=self.module()
        with tempfile.TemporaryDirectory() as folder:
            checkpoint=Path(folder)/'candidate.pt';checkpoint.write_bytes(b'candidate bytes')
            digest=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
            config={'stable':{'path':checkpoint,'expected_sha256':'0'*64},'canary':None}
            record={'sha256':digest,'size':checkpoint.stat().st_size,'filename':checkpoint.name}
            loader=Mock()
            with patch.object(module,'_vehicle_rollout',config), \
                 patch.object(module,'snapshot_model_file',return_value=(checkpoint,record)), \
                 patch.object(module,'YOLO',loader), self.assertRaisesRegex(RuntimeError,'does not match'):
                module._vehicle_model()
            loader.assert_not_called()
            self.assertEqual(module._vehicle_models,{})

    def test_vehicle_checkpoint_compatibility_failure_is_not_cached_or_activated(self):
        module=self.module()
        with tempfile.TemporaryDirectory() as folder:
            checkpoint=Path(folder)/'candidate.pt';checkpoint.write_bytes(b'pinned but incompatible checkpoint')
            digest=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
            config={'stable':{'path':checkpoint,'expected_sha256':digest},'canary':None}
            record={'sha256':digest,'size':checkpoint.stat().st_size,'filename':checkpoint.name}
            incompatible=SimpleNamespace(task='detect',names={0:'person',2:'car',3:'motorcycle',5:'bus',7:'airplane'},predict=Mock())
            loader=Mock(return_value=incompatible)
            with patch.object(module,'_vehicle_rollout',config), \
                 patch.object(module,'snapshot_model_file',return_value=(checkpoint,record)), \
                 patch.object(module,'verify_model_files'),patch.object(module,'YOLO',loader), \
                 self.assertRaisesRegex(RuntimeError,'class 7 must be named'):
                module._vehicle_model()
            self.assertEqual(module._vehicle_models,{})
            self.assertFalse(config['stable'].get('loaded',False))
            self.assertNotIn('loaded_sha256',config['stable'])
            self.assertEqual(config['stable']['compatibility']['preflight_status'],'failed')
            with patch.object(module,'_vehicle_rollout',config), \
                 patch.object(module,'YOLO',loader), \
                 self.assertRaisesRegex(RuntimeError,'failed detection compatibility'):
                module._vehicle_model()
            loader.assert_called_once()

    def test_initialized_frames_do_not_repeat_hash_or_package_metadata_io(self):
        import numpy as np
        module=self.module();module._alpr=SimpleNamespace(predict=lambda _:[])
        module._alpr_metadata={'weight_provenance_status':'hashed_loaded_files'}
        with patch.object(module,'version',side_effect=AssertionError('per-frame package IO')), \
             patch.object(provenance,'file_sha256',side_effect=AssertionError('per-frame file hashing')):
            for _ in range(3):
                _,reads=module.annotate_plate_frame(np.zeros((100,100,3),np.uint8),'CAM-07')
                self.assertEqual(reads,[])


class ReportProvenance(unittest.TestCase):
    def metadata(self):
        return {'weight_provenance_status':'hashed_loaded_files','ocr_model':'fixture <model>',
                'model_files':[{'role':role,'sha256':letter*64,'size':10} for role,letter in
                               [('plate_detector_weights','a'),('ocr_weights','b'),('ocr_configuration','c')]]}

    def test_summary_deduplicates_sets_and_exposes_legacy_missing_coverage(self):
        import events
        metadata=self.metadata()
        summary=events.summarize_read_models([{'model_metadata':metadata},{'model_metadata':metadata},
                       {'model_metadata':{'fast_alpr_version':'legacy'}},{}])
        self.assertEqual(summary['total_reads'],4)
        self.assertEqual(summary['reads_with_exact_alpr_files'],2)
        self.assertEqual(summary['reads_without_exact_alpr_files'],2)
        self.assertEqual(summary['reads_missing_model_metadata'],1)
        self.assertEqual(sorted(s['read_count'] for s in summary['model_sets']),[1,2])

    def test_incomplete_or_malformed_digest_is_never_counted_as_exact(self):
        import events
        malformed=[]
        for key,bad in [('sha256','not a digest'),('role',[]),('role',{}),('size',True),('size',0)]:
            metadata=self.metadata();metadata['model_files'][0][key]=bad;malformed.append(metadata)
        for value in (None,[],{'model_files':'not a list'},*malformed):
            summary=events.summarize_read_models([{'model_metadata':value}])
            self.assertEqual(summary['reads_with_exact_alpr_files'],0)
            self.assertEqual(summary['reads_without_exact_alpr_files'],1)

    def test_exports_use_the_same_immutable_provenance_and_escape_print(self):
        import events,main,time,io,zipfile
        from repository import Repository,canonical_json
        from fastapi.testclient import TestClient
        repository=Repository(':memory:');self.addCleanup(repository.close)
        now=time.time();metadata=self.metadata()
        with patch.object(events,'store',repository),patch.object(main,'store',repository):
            for index in range(2):
                events.add_events([{'camera_id':'CAM-07','kind':'plate','plate':'KL07AB1234','confidence':.9,
                                   'bbox':[0,0,20,20],'ts':now-2+index,'session_id':'fixture','track_id':1,
                                   'frame_id':index,'model_metadata':metadata,'source_mode':'synthetic fixture'}])
            report=events.evidence_report('KL07AB1234',now-10,now+1)
            self.assertEqual(report['version'],5)
            self.assertEqual(report['model_provenance']['reads_with_exact_alpr_files'],2)
            client=TestClient(main.app);route='/api/reports/'+report['report_id']
            before=client.get(route).content
            with zipfile.ZipFile(io.BytesIO(client.get(route+'/package').content)) as package:
                self.assertEqual(json.loads(package.read('manifest.json')),report)
            printed=client.get(route+'/print').text
            self.assertIn('Model provenance',printed)
            self.assertIn('b'*64,printed)
            self.assertIn('&lt;model&gt;',printed)
            self.assertNotIn('fixture <model>',printed)
            metadata['model_files'][1]['sha256']='d'*64
            events.add_events([{'camera_id':'CAM-08','kind':'plate','plate':'KL07AB1234','confidence':.9,
                               'bbox':[0,0,20,20],'ts':now,'model_metadata':metadata}])
            self.assertEqual(client.get(route).content,before)
            self.assertEqual(client.get(route+'/print').text,printed)
            unsigned={k:v for k,v in report.items() if k!='package_hash'}
            self.assertEqual(hashlib.sha256(canonical_json(unsigned).encode()).hexdigest(),report['package_hash'])

    def test_version_one_snapshot_remains_downloadable_without_backfilled_claims(self):
        import events,main,time
        from repository import Repository,canonical_json
        from fastapi.testclient import TestClient
        repository=Repository(':memory:');self.addCleanup(repository.close)
        now=time.time()
        with patch.object(events,'store',repository),patch.object(main,'store',repository):
            events.add_events([{'camera_id':'CAM-07','kind':'plate','plate':'KL07AB1234','confidence':.9,
                               'bbox':[0,0,20,20],'ts':now}])
            original=events.evidence_report('KL07AB1234',now-1,now+1)
            legacy={k:v for k,v in original.items() if k not in ('model_provenance','artifact_coverage','package_hash')}
            legacy.update(version=1,report_id='EVD-LEGACY-FIXTURE')
            legacy['package_hash']=hashlib.sha256(canonical_json(legacy).encode()).hexdigest()
            repository.put_report(legacy)
            client=TestClient(main.app);route='/api/reports/'+legacy['report_id']
            self.assertEqual(client.get(route).json(),legacy)
            printed=client.get(route+'/print').text
            self.assertIn('unavailable in this older report snapshot',printed)
            self.assertEqual(repository.report(legacy['report_id'],now),legacy)


if __name__=='__main__': unittest.main()
