"""Supervised plate-crop quality trainer enforces provenance and session splits."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

MODULE_PATH=Path(__file__).parents[1]/"evaluation"/"train_plate_quality.py"
spec=importlib.util.spec_from_file_location("train_plate_quality",MODULE_PATH)
quality=importlib.util.module_from_spec(spec);spec.loader.exec_module(quality)


class PlateQualityTrainingTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.manifest_path=self.root/'manifest.json'
        self.document={"schema_version":1,"dataset_id":"synthetic-training-test",
            "label_definitions":{"readable":"most characters legible","marginal":"some characters uncertain",
                                 "unreadable":"no reliable characters"},"records":[]}
        for split in ('train','validation','test'):
            for camera_index in range(3):
                camera=f'{split}-camera-{camera_index}'
                session=f'{split}-session-{camera_index}'
                clip=self.root/f'{camera}.mp4';clip.write_bytes(f'fixture-{camera}'.encode())
                clip_hash=quality._hash_file(clip)
                for label_index,label in enumerate(quality.CLASSES):
                    rng=np.random.default_rng(camera_index*10+label_index)
                    image=np.zeros((96,256,3),dtype=np.uint8)
                    if label=='readable':
                        image[:]=(35,190,235)
                        cv2.putText(image,'KL07AB1234',(8,65),cv2.FONT_HERSHEY_SIMPLEX,1.2,(5,5,5),3,cv2.LINE_AA)
                    elif label=='marginal':
                        image[:]=(80,145,190)
                        cv2.putText(image,'KL07AB1234',(8,65),cv2.FONT_HERSHEY_SIMPLEX,1.0,(25,25,25),2,cv2.LINE_AA)
                        image=cv2.GaussianBlur(image,(0,0),2.4)
                    else:
                        image[:]=(8,12,14)
                        image=cv2.GaussianBlur(image,(0,0),8)
                    image=np.clip(image.astype(np.int16)+rng.integers(-4,5,image.shape),0,255).astype(np.uint8)
                    crop=self.root/f'{camera}-{label}.png';self.assertTrue(cv2.imwrite(str(crop),image))
                    self.document['records'].append({"record_id":f'{camera}-{label}',"camera_id":camera,
                        "session_id":session,"source_clip_path":clip.name,"source_clip_sha256":clip_hash,
                        "crop_path":crop.name,"sha256":quality._hash_file(crop),"label":label,"split":split})
        self.write_manifest()
        self.base_document=json.loads(json.dumps(self.document))

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.document))

    def test_trains_and_evaluates_once_on_camera_session_and_clip_heldout_data(self):
        model=quality.train_evaluate(self.manifest_path)
        self.assertEqual(model['status'],'trained_from_labeled_crops')
        self.assertEqual(model['split_dimensions'],['camera_id','session_id','source_clip_sha256'])
        self.assertEqual(model['split_counts'],{'train':9,'validation':9,'test':9})
        self.assertEqual(model['test']['samples'],9)
        self.assertEqual(sum(map(sum,model['test']['confusion_matrix_rows_true_cols_pred'])),9)
        self.assertEqual(len(model['weights']),3)
        self.assertTrue(all(len(row)==len(quality.FEATURES) for row in model['weights']))
        self.assertFalse(model['probabilities_calibrated'])
        self.assertFalse(model['live_routing_enabled'])

    def test_rejects_camera_session_or_source_clip_leakage_and_changed_crop(self):
        self.document['records'][-1]['camera_id']=self.document['records'][0]['camera_id']
        self.write_manifest()
        with self.assertRaisesRegex(quality.QualityDatasetError,'split leakage'):
            quality.load_dataset(self.manifest_path)
        self.document=json.loads(json.dumps(self.base_document));self.write_manifest()
        crop=self.root/self.document['records'][0]['crop_path'];crop.write_bytes(b'changed')
        with self.assertRaisesRegex(quality.QualityDatasetError,'crop SHA-256'):
            quality.load_dataset(self.manifest_path)

    def test_cli_report_is_no_clobber_and_carries_manifest_provenance(self):
        output=self.root/'quality-model.json'
        written=quality.run(self.manifest_path,output)
        result=json.loads(written.read_text())
        self.assertEqual(result['manifest_sha256'],quality._hash_file(self.manifest_path))
        with self.assertRaises(FileExistsError): quality.run(self.manifest_path,output)


if __name__=='__main__': unittest.main()
