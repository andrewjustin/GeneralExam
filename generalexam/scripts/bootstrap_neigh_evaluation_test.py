"""Unit tests for bootstrap_neigh_evaluation.py."""

import unittest
import numpy
from generalexam.ge_utils import neigh_evaluation
from generalexam.scripts import bootstrap_neigh_evaluation as bootstrap_eval

TOLERANCE = 1e-6

# The following constants are used to test `_decompose_contingency_tables` and
# `_bootstrap_contingency_tables`.
PREDICTION_ORIENTED_CT_MATRIX = numpy.array([
    [numpy.nan, numpy.nan, numpy.nan],
    [1, 4, 2],
    [5, 5, 10]
])

ACTUAL_ORIENTED_CT_MATRIX = numpy.array([
    [numpy.nan, 2, 5],
    [numpy.nan, 5, 0],
    [numpy.nan, 10, 15]
])

PREDICTED_FRONT_ENUMS = numpy.concatenate((
    numpy.full(7, 1, dtype=int), numpy.full(20, 2, dtype=int)
))
PREDICTED_TO_ACTUAL_FRONT_ENUMS = numpy.concatenate((
    numpy.full(1, 0, dtype=int), numpy.full(4, 1, dtype=int),
    numpy.full(2, 2, dtype=int),
    numpy.full(5, 0, dtype=int), numpy.full(5, 1, dtype=int),
    numpy.full(10, 2, dtype=int)
))

ACTUAL_FRONT_ENUMS = numpy.concatenate((
    numpy.full(2, 1, dtype=int), numpy.full(5, 2, dtype=int),
    numpy.full(5, 1, dtype=int),
    numpy.full(10, 1, dtype=int), numpy.full(15, 2, dtype=int)
))
ACTUAL_TO_PREDICTED_FRONT_ENUMS = numpy.concatenate((
    numpy.full(7, 0, dtype=int), numpy.full(5, 1, dtype=int),
    numpy.full(25, 2, dtype=int)
))

MATCH_DICT = {
    bootstrap_eval.PREDICTED_LABELS_KEY: PREDICTED_FRONT_ENUMS,
    bootstrap_eval.PREDICTED_TO_ACTUAL_FRONTS_KEY:
        PREDICTED_TO_ACTUAL_FRONT_ENUMS,
    bootstrap_eval.ACTUAL_LABELS_KEY: ACTUAL_FRONT_ENUMS,
    bootstrap_eval.ACTUAL_TO_PREDICTED_FRONTS_KEY:
        ACTUAL_TO_PREDICTED_FRONT_ENUMS
}

# The following constants are used to test `_bootstrap_contingency_tables`.
BINARY_CT_AS_DICT = {
    neigh_evaluation.NUM_PREDICTION_ORIENTED_TP_KEY: 14,
    neigh_evaluation.NUM_FALSE_POSITIVES_KEY: 13,
    neigh_evaluation.NUM_ACTUAL_ORIENTED_TP_KEY: 20,
    neigh_evaluation.NUM_FALSE_NEGATIVES_KEY: 17
}


class BootstrapNeighEvaluationTests(unittest.TestCase):
    """Each method is a unit test for bootstrap_neigh_evaluation.py."""

    def test_decompose_contingency_tables(self):
        """Ensures correct output from _decompose_contingency_tables."""

        this_match_dict = bootstrap_eval._decompose_contingency_tables(
            prediction_oriented_ct_matrix=PREDICTION_ORIENTED_CT_MATRIX,
            actual_oriented_ct_matrix=ACTUAL_ORIENTED_CT_MATRIX)

        actual_keys = list(this_match_dict.keys())
        expected_keys = list(MATCH_DICT.keys())
        self.assertTrue(set(actual_keys) == set(expected_keys))

        for this_key in actual_keys:
            self.assertTrue(numpy.array_equal(
                this_match_dict[this_key], MATCH_DICT[this_key]
            ))

    def test_bootstrap_contingency_tables(self):
        """Ensures correct output from _bootstrap_contingency_tables."""

        (
            this_binary_ct_as_dict,
            this_prediction_oriented_matrix,
            this_actual_oriented_matrix
        ) = bootstrap_eval._bootstrap_contingency_tables(
            match_dict=MATCH_DICT, test_mode=True
        )

        self.assertTrue(this_binary_ct_as_dict == BINARY_CT_AS_DICT)
        self.assertTrue(numpy.allclose(
            this_prediction_oriented_matrix, PREDICTION_ORIENTED_CT_MATRIX,
            atol=TOLERANCE, equal_nan=True
        ))
        self.assertTrue(numpy.allclose(
            this_actual_oriented_matrix, ACTUAL_ORIENTED_CT_MATRIX,
            atol=TOLERANCE, equal_nan=True
        ))


if __name__ == '__main__':
    unittest.main()