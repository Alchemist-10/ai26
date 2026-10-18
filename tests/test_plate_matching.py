import unittest

from plate_matching import compare_plates, evaluate_labeled_pairs


class PlateMatchingTests(unittest.TestCase):
    def test_same_observed_characters_ignores_only_spacing_and_never_links_identity(self):
        result = compare_plates("KL 07 AB 1234", "KL07AB1234")
        self.assertEqual(result["status"], "same_observed_characters")
        self.assertEqual(result["similarity_score"], 1.0)
        self.assertTrue(result["raw_characters_equal"])
        self.assertTrue(result["normalization_equivalent"])
        self.assertFalse(result["identity_linked"])
        self.assertFalse(result["score_is_probability"])

    def test_ocr_repair_equivalence_is_not_reported_as_same_observed_characters(self):
        result=compare_plates("OL08AF5030","DL08AF5030")
        self.assertEqual(result["status"],"same_after_ocr_repair")
        self.assertFalse(result["raw_characters_equal"])
        self.assertTrue(result["normalization_equivalent"])
        self.assertTrue(result["requires_human_review"])
        self.assertTrue(result["left_repairs"])
        self.assertFalse(result["identity_linked"])

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
        with self.assertRaisesRegex(ValueError, "64 characters"):
            compare_plates("X" * 65, "KL07AB1234")

    def test_labeled_pair_sweep_reports_false_candidates_and_denominators(self):
        records = [
            {"pair_id": "p1", "left_read_id": "r1", "right_read_id": "r2", "left_vehicle_id": "v1", "right_vehicle_id": "v1", "left_session_id": "s1", "right_session_id": "s2", "left_plate": "KL07AB1234", "right_plate": "KL07AB1234", "same_vehicle": True},
            {"pair_id": "p2", "left_read_id": "r3", "right_read_id": "r4", "left_vehicle_id": "v2", "right_vehicle_id": "v2", "left_session_id": "s3", "right_session_id": "s4", "left_plate": "KL07AB1234", "right_plate": "KL07AC1234", "same_vehicle": True},
            {"pair_id": "p3", "left_read_id": "r5", "right_read_id": "r6", "left_vehicle_id": "v3", "right_vehicle_id": "v4", "left_session_id": "s5", "right_session_id": "s6", "left_plate": "KL07AB1234", "right_plate": "KL07AC1234", "same_vehicle": False},
            {"pair_id": "p4", "left_read_id": "r7", "right_read_id": "r8", "left_vehicle_id": "v5", "right_vehicle_id": "v6", "left_session_id": "s7", "right_session_id": "s8", "left_plate": "KL07AB1234", "right_plate": "TN22ZZ0007", "same_vehicle": False},
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
        self.assertTrue(result["pair_read_ids_unique"])
        self.assertTrue(result["pair_vehicle_and_session_ids_disjoint"])
        self.assertIn("camera/location grouping", result["independence_note"])
        false_rate_interval = permissive["false_positive_candidate_rate_on_negative_pairs_wilson_interval"]
        self.assertLessEqual(false_rate_interval["lower"], .5)
        self.assertGreaterEqual(false_rate_interval["upper"], .5)
        strict_false_fraction = strict["false_candidate_fraction_among_candidates_wilson_interval"]
        self.assertEqual(strict_false_fraction["lower"], 0)
        self.assertGreater(strict_false_fraction["upper"], 0)

    def test_zero_false_candidates_still_reports_upper_uncertainty_bound(self):
        records = [
            {"pair_id": "p1", "left_read_id": "r1", "right_read_id": "r2", "left_vehicle_id": "v1", "right_vehicle_id": "v1", "left_session_id": "s1", "right_session_id": "s2", "left_plate": "KL07AB1234", "right_plate": "KL07AB1234", "same_vehicle": True},
            {"pair_id": "p2", "left_read_id": "r3", "right_read_id": "r4", "left_vehicle_id": "v2", "right_vehicle_id": "v3", "left_session_id": "s3", "right_session_id": "s4", "left_plate": "KL07AB1234", "right_plate": "TN22ZZ0007", "same_vehicle": False},
        ]
        result = evaluate_labeled_pairs(records, [.99])
        metrics = result["threshold_results"][0]
        interval = metrics["false_positive_candidate_rate_on_negative_pairs_wilson_interval"]
        self.assertEqual(metrics["false_candidate_count"], 0)
        self.assertEqual(interval["lower"], 0)
        self.assertGreater(interval["upper"], 0)

    def test_confidence_level_must_be_open_unit_interval(self):
        pair = {"pair_id": "p1", "left_read_id": "r1", "right_read_id": "r2", "left_vehicle_id": "v1", "right_vehicle_id": "v1", "left_session_id": "s1", "right_session_id": "s2", "left_plate": "KL07AB1234", "right_plate": "KL07AB1234", "same_vehicle": True}
        records = [pair, {**pair, "pair_id": "p2", "left_read_id": "r3", "right_read_id": "r4", "left_vehicle_id": "v2", "right_vehicle_id": "v3", "left_session_id": "s3", "right_session_id": "s4", "right_plate": "TN22ZZ0007", "same_vehicle": False}]
        for invalid in (0, 1, True, float("nan")):
            with self.subTest(confidence_level=invalid), self.assertRaises(ValueError):
                evaluate_labeled_pairs(records, [.9], confidence_level=invalid)

    def test_evaluation_requires_positive_and_negative_labels(self):
        with self.assertRaises(ValueError):
            evaluate_labeled_pairs([{"pair_id": "p1", "left_read_id": "r1", "right_read_id": "r2", "left_vehicle_id": "v1", "right_vehicle_id": "v1", "left_session_id": "s1", "right_session_id": "s2", "left_plate": "KL07AB1234", "right_plate": "KL07AB1234",
                                     "same_vehicle": True}], [.9])

    def test_pair_evaluation_rejects_reused_reads_and_invalid_threshold_sweep(self):
        base = {"pair_id": "p1", "left_read_id": "r1", "right_read_id": "r2",
                "left_vehicle_id": "v1", "right_vehicle_id": "v1", "left_session_id": "s1", "right_session_id": "s2",
                "left_plate": "KL07AB1234", "right_plate": "KL07AB1234", "same_vehicle": True}
        negative = {**base, "pair_id": "p2", "left_read_id": "r2", "right_read_id": "r3",
                    "left_vehicle_id": "v2", "right_vehicle_id": "v3", "left_session_id": "s3", "right_session_id": "s4",
                    "right_plate": "TN22ZZ0007", "same_vehicle": False}
        with self.assertRaisesRegex(ValueError, "reuses a read ID"):
            evaluate_labeled_pairs([base, negative], [.9])
        negative["left_read_id"] = "r4"
        with self.assertRaisesRegex(ValueError, "thresholds must be unique"):
            evaluate_labeled_pairs([base, negative], [.9, .9])
        with self.assertRaisesRegex(ValueError, "at least one threshold"):
            evaluate_labeled_pairs([base, negative], [])

    def test_pair_evaluation_requires_read_provenance_ids(self):
        pair = {"left_plate": "KL07AB1234", "right_plate": "KL07AB1234", "same_vehicle": True}
        with self.assertRaisesRegex(ValueError, "pair_id"):
            evaluate_labeled_pairs([pair], [.9])

    def test_pair_evaluation_enforces_vehicle_session_disjointness_and_label_consistency(self):
        first = {"pair_id": "p1", "left_read_id": "r1", "right_read_id": "r2",
                 "left_vehicle_id": "v1", "right_vehicle_id": "v1", "left_session_id": "s1",
                 "right_session_id": "s2", "left_plate": "KL07AB1234", "right_plate": "KL07AB1234",
                 "same_vehicle": True}
        second = {"pair_id": "p2", "left_read_id": "r3", "right_read_id": "r4",
                  "left_vehicle_id": "v1", "right_vehicle_id": "v2", "left_session_id": "s3",
                  "right_session_id": "s4", "left_plate": "KL07AB1234", "right_plate": "TN22ZZ0007",
                  "same_vehicle": False}
        with self.assertRaisesRegex(ValueError, "reuses a vehicle"):
            evaluate_labeled_pairs([first, second], [.9])
        second["left_vehicle_id"] = "v3"
        second["left_session_id"] = "s1"
        with self.assertRaisesRegex(ValueError, "reuses a session"):
            evaluate_labeled_pairs([first, second], [.9])
        second["left_session_id"] = "s3"
        second["same_vehicle"] = True
        with self.assertRaisesRegex(ValueError, "label disagrees"):
            evaluate_labeled_pairs([first, second], [.9])


if __name__ == "__main__":
    unittest.main()
