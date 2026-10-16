import unittest

from plate_matching import compare_plates, evaluate_labeled_pairs


class PlateMatchingTests(unittest.TestCase):
    def test_exact_text_uses_existing_canonical_repairs_but_never_links_identity(self):
        result = compare_plates("KL 07 AB 1234", "KL07AB1234")
        self.assertEqual(result["status"], "exact_text")
        self.assertEqual(result["similarity_score"], 1.0)
        self.assertFalse(result["identity_linked"])
        self.assertFalse(result["score_is_probability"])

    def test_single_edit_is_a_review_only_candidate_and_confidence_is_not_probability(self):
        result = compare_plates("KL07AB1234", "KL07AC1234", left_ocr_confidence=.8,
                                right_ocr_confidence=.9, candidate_threshold=.75)
        self.assertEqual(result["status"], "review_candidate")
        self.assertEqual(result["edit_distance"], 1)
        self.assertAlmostEqual(result["similarity_score"], .9)
        self.assertAlmostEqual(result["review_score"], .9 * (.8 * .9) ** .5)
        self.assertTrue(result["requires_human_review"])
        self.assertFalse(result["identity_linked"])
        self.assertFalse(result["score_is_probability"])

    def test_invalid_input_and_incomplete_confidence_are_rejected(self):
        self.assertEqual(compare_plates("bad", "KL07AB1234")["status"], "not_comparable")
        with self.assertRaises(ValueError):
            compare_plates("KL07AB1234", "KL07AB1234", left_ocr_confidence=.8)
        with self.assertRaises(ValueError):
            compare_plates("KL07AB1234", "KL07AB1234", candidate_threshold=1.1)

    def test_labeled_pair_sweep_reports_false_candidates_and_denominators(self):
        records = [
            {"left_plate": "KL07AB1234", "right_plate": "KL07AB1234", "same_vehicle": True},
            {"left_plate": "KL07AB1234", "right_plate": "KL07AC1234", "same_vehicle": True},
            {"left_plate": "KL07AB1234", "right_plate": "KL07AC1234", "same_vehicle": False},
            {"left_plate": "KL07AB1234", "right_plate": "TN22ZZ0007", "same_vehicle": False},
        ]
        result = evaluate_labeled_pairs(records, [.95, .9])
        strict, permissive = result["threshold_results"]
        self.assertEqual((strict["positive_pair_count"], strict["negative_pair_count"]), (2, 2))
        self.assertEqual(strict["false_candidate_count"], 0)
        self.assertEqual(strict["recall_on_positive_pairs"], .5)
        self.assertEqual(permissive["false_candidate_count"], 1)
        self.assertEqual(permissive["false_positive_candidate_rate_on_negative_pairs"], .5)
        self.assertAlmostEqual(permissive["false_candidate_fraction_among_candidates"], 1 / 3)
        self.assertFalse(result["identity_linking_enabled"])
        self.assertEqual(result["uncertainty"]["method"], "two-sided_wilson_score_interval")
        false_rate_interval = permissive["false_positive_candidate_rate_on_negative_pairs_wilson_interval"]
        self.assertLessEqual(false_rate_interval["lower"], .5)
        self.assertGreaterEqual(false_rate_interval["upper"], .5)
        strict_false_fraction = strict["false_candidate_fraction_among_candidates_wilson_interval"]
        self.assertEqual(strict_false_fraction["lower"], 0)
        self.assertGreater(strict_false_fraction["upper"], 0)

    def test_zero_false_candidates_still_reports_upper_uncertainty_bound(self):
        records = [
            {"left_plate": "KL07AB1234", "right_plate": "KL07AB1234", "same_vehicle": True},
            {"left_plate": "KL07AB1234", "right_plate": "TN22ZZ0007", "same_vehicle": False},
        ]
        result = evaluate_labeled_pairs(records, [.99])
        metrics = result["threshold_results"][0]
        interval = metrics["false_positive_candidate_rate_on_negative_pairs_wilson_interval"]
        self.assertEqual(metrics["false_candidate_count"], 0)
        self.assertEqual(interval["lower"], 0)
        self.assertGreater(interval["upper"], 0)

    def test_confidence_level_must_be_open_unit_interval(self):
        pair = {"left_plate": "KL07AB1234", "right_plate": "KL07AB1234", "same_vehicle": True}
        records = [pair, {**pair, "right_plate": "TN22ZZ0007", "same_vehicle": False}]
        for invalid in (0, 1, True, float("nan")):
            with self.subTest(confidence_level=invalid), self.assertRaises(ValueError):
                evaluate_labeled_pairs(records, [.9], confidence_level=invalid)

    def test_evaluation_requires_positive_and_negative_labels(self):
        with self.assertRaises(ValueError):
            evaluate_labeled_pairs([{"left_plate": "KL07AB1234", "right_plate": "KL07AB1234",
                                     "same_vehicle": True}], [.9])


if __name__ == "__main__":
    unittest.main()
