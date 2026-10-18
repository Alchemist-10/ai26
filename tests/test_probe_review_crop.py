from __future__ import annotations

import numpy as np
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.probe_review_crop_ocr import VARIANT_NAMES, _canonical, _summarize_variant_predictions, _variants


class ProbeReviewCropTests(unittest.TestCase):
    def test_preprocessing_probe_variants_have_stable_sanitized_names(self):
        image = np.zeros((24, 48, 3), dtype=np.uint8)

        variants = _variants(image)

        self.assertEqual(len(variants),len(VARIANT_NAMES))
        self.assertEqual(len(VARIANT_NAMES),17)
        self.assertEqual(len(set(VARIANT_NAMES)),len(VARIANT_NAMES))
        self.assertEqual(VARIANT_NAMES[5],"grayscale_contrast_alpha_1_5_beta_minus_25")
        self.assertTrue(all(variant.ndim == 3 and variant.shape[2] == 3 for variant in variants))


    def test_probe_canonicalization_compares_characters_without_storing_text(self):
        self.assertEqual(_canonical(" KL-07 BR 9607 "),"KL07BR9607")


    def test_probe_counts_wrong_format_valid_outputs_without_retaining_ocr_text(self):
        class OCRResult:
            def __init__(self, text, confidence):
                self.text = text
                self.confidence = confidence

        class OCR:
            def __init__(self):
                self.results = iter([
                    OCRResult("KL07AB1234", 0.2),
                    OCRResult("KL07AB1234", [0.8, 0.9]),
                    OCRResult("KL07AC1234", 0.95),
                    OCRResult("unreadable", 0.99),
                ])

            def predict(self, _candidate):
                return next(self.results)

        class Model:
            ocr = OCR()

        report = _summarize_variant_predictions(Model(), [object(), object(), object(), object()], "KL07AB1234")

        self.assertEqual(report["exact_match_variant_indices"],[0,1])
        self.assertEqual(report["variants_passing_format_and_confidence_gates"],2)
        self.assertEqual(report["exact_gate_passing_variant_indices"],[1])
        self.assertEqual(report["inexact_gate_passing_variant_indices"],[2])
        self.assertFalse(report["ocr_text_recorded"])
        self.assertNotIn("KL07AB1234",str(report))
