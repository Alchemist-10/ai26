"""Bounded offline burst reconstruction preserves source provenance and labels derivatives."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

MODULE_PATH = Path(__file__).parents[1] / "evaluation" / "burst_super_resolution.py"
spec = importlib.util.spec_from_file_location("burst_super_resolution", MODULE_PATH)
burst_sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(burst_sr)


class BurstSuperResolutionTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(281)
        self.reference=cv2.GaussianBlur(rng.integers(0,256,(96,112,3),dtype=np.uint8),(0,0),1.2)
        self.frames=[self.reference]
        for dx,dy in ((0.45,0),(0,0.45),(0.55,0.55)):
            self.frames.append(cv2.warpAffine(self.reference,np.float32([[1,0,dx],[0,1,dy]]),
                                              (112,96),borderMode=cv2.BORDER_REFLECT_101))

    def test_reconstruction_is_2x_derivative_with_explicit_non_evidence_status(self):
        result,details=burst_sr.reconstruct_burst(self.frames)
        self.assertEqual(result.shape,(192,224,3))
        self.assertEqual(result.dtype,np.uint8)
        self.assertEqual(details['status'],'reconstructed')
        self.assertFalse(details['raw_evidence'])
        self.assertFalse(details['confidence_is_calibrated'])
        self.assertFalse(details['identity_inferred'])
        self.assertEqual(details['input_frame_count'],4)
        self.assertGreater(details['subpixel_phase_spread'],0.15)

    def test_rejects_flat_bursts_without_registration_or_subpixel_support(self):
        flat=np.full((64,64,3),128,dtype=np.uint8)
        with self.assertRaises(ValueError): burst_sr.reconstruct_burst([flat,flat.copy()])
        with self.assertRaises(ValueError): burst_sr.reconstruct_burst([self.reference])
        with self.assertRaises(ValueError): burst_sr.reconstruct_burst([self.reference,self.reference[:,:-1]])

    def test_run_hashes_inputs_and_never_overwrites_them_or_existing_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);paths=[]
            for index,frame in enumerate(self.frames):
                path=root/f'frame-{index}.png';self.assertTrue(cv2.imwrite(str(path),frame));paths.append(path)
            hashes=[burst_sr._sha256(path) for path in paths]
            output=root/'reconstructed.png';manifest=burst_sr.run(paths,output)
            import json
            details=json.loads(manifest.read_text())
            self.assertEqual(details['status'],'reconstructed')
            self.assertEqual([item['sha256'] for item in details['inputs']],hashes)
            self.assertTrue(output.is_file())
            with self.assertRaises(FileExistsError): burst_sr.run(paths,output)
            self.assertEqual([burst_sr._sha256(path) for path in paths],hashes)


if __name__ == "__main__": unittest.main()
