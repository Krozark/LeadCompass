from __future__ import annotations

import unittest

from leadcompass.config import BusinessProfile, ScoringCriterion
from leadcompass.tasks.scoring import ScoreResult, _classify, _extract_json, _percentage, generate_score


class FakeBackend:
    name = "Fake"

    def __init__(self, response: str):
        self._response = response

    def generate(self, system: str, user: str) -> str:
        return self._response


class ScoringHelpersTests(unittest.TestCase):
    def test_percentage(self):
        self.assertEqual(_percentage(5, 10), 50.0)
        self.assertEqual(_percentage(0, 0), 0.0)

    def test_classify_thresholds(self):
        self.assertEqual(_classify(70), "chaud")
        self.assertEqual(_classify(69.9), "tiede")
        self.assertEqual(_classify(40), "tiede")
        self.assertEqual(_classify(39.9), "froid")

    def test_extract_json_from_surrounding_text(self):
        self.assertEqual(_extract_json('blah blah {"a": 1} blah'), {"a": 1})

    def test_extract_json_raises_without_json(self):
        with self.assertRaises(ValueError):
            _extract_json("no json here")


class GenerateScoreTests(unittest.TestCase):
    def setUp(self):
        self.profile = BusinessProfile(
            scoring_criteria=[ScoringCriterion("A", "desc a", 1), ScoringCriterion("B", "desc b", 2)]
        )

    def test_positional_matching_and_weighting(self):
        backend = FakeBackend(
            '{"criteria_scores": [{"name": "A", "score": 5, "justification": "x"}, '
            '{"name": "B", "score": 3, "justification": "y"}]}'
        )
        result = generate_score("context", self.profile, backend)
        self.assertEqual(result.total, 5 * 1 + 3 * 2)
        self.assertEqual(result.max_total, 5 * 1 + 5 * 2)
        self.assertEqual(result.classification, "chaud")

    def test_criterion_count_mismatch_raises(self):
        backend = FakeBackend('{"criteria_scores": [{"name": "A", "score": 5, "justification": "x"}]}')
        with self.assertRaises(ValueError):
            generate_score("context", self.profile, backend)

    def test_weighting_is_positional_not_name_based(self):
        # Even if the model paraphrases a name, the weight comes from the
        # criterion at that position, not from a (fragile) name lookup.
        backend = FakeBackend(
            '{"criteria_scores": [{"name": "A (paraphrased)", "score": 5, "justification": "x"}, '
            '{"name": "B (paraphrased)", "score": 3, "justification": "y"}]}'
        )
        result = generate_score("context", self.profile, backend)
        self.assertEqual(result.total, 5 * 1 + 3 * 2)


class ScoreResultTests(unittest.TestCase):
    def test_percentage_property_matches_helper(self):
        result = ScoreResult(total=15, max_total=20, classification="chaud", details=[])
        self.assertEqual(result.percentage, _percentage(15, 20))


if __name__ == "__main__":
    unittest.main()
