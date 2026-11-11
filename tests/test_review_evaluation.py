import unittest

from services.review_evaluation import (
    evaluate_review_dataset,
    load_review_dataset,
)


class ReviewEvaluationTests(unittest.TestCase):
    def test_fixed_dataset_passes_stability_adoption_and_uplift_gates(self):
        summary = evaluate_review_dataset(load_review_dataset())

        self.assertTrue(summary.passed)
        self.assertEqual(summary.case_count, 2)
        self.assertEqual(summary.stable_case_count, 2)
        self.assertEqual(summary.max_score_drift, 1)
        self.assertEqual(summary.stability_pass_rate, 1.0)
        self.assertEqual(summary.decision_count, 3)
        self.assertEqual(summary.adopted_decision_count, 2)
        self.assertEqual(summary.suggestion_adoption_rate, 0.667)
        self.assertEqual(summary.revision_score_samples, 2)
        self.assertEqual(summary.revision_score_improvement_rate, 1.0)

    def test_score_drift_tolerance_is_a_regression_gate(self):
        summary = evaluate_review_dataset(
            load_review_dataset(),
            score_drift_tolerance=0,
        )

        self.assertFalse(summary.passed)
        self.assertEqual(summary.stability_pass_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
