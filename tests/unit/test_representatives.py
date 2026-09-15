import unittest

from backend.trade_space import analyze_pareto, extract_representative_categories
from test_pareto import candidate


class RepresentativeTests(unittest.TestCase):
    def extract(self, rows):
        pareto = analyze_pareto(rows)
        return pareto, extract_representative_categories(
            rows, pareto.pareto_candidate_ids)

    def test_each_descriptive_category_is_selected(self):
        rows = (candidate('early', 1, .9, 300),
                candidate('success', 2, .95, 500),
                candidate('exposure', 3, .8, 100))
        pareto, (assignments, representatives) = self.extract(rows)
        self.assertEqual(pareto.pareto_candidate_ids,
                         ('early', 'success', 'exposure'))
        self.assertEqual(assignments.earliest_viable, 'early')
        self.assertEqual(assignments.highest_success, 'success')
        self.assertEqual(assignments.lowest_exposure, 'exposure')
        self.assertEqual(representatives, ('early', 'success', 'exposure'))

    def test_one_candidate_can_own_multiple_categories_without_duplicates(self):
        rows = (candidate('A', 1, .95, 500), candidate('B', 2, .9, 100))
        _, (assignments, representatives) = self.extract(rows)
        self.assertEqual(assignments.earliest_viable, 'A')
        self.assertEqual(assignments.highest_success, 'A')
        self.assertEqual(assignments.lowest_exposure, 'B')
        self.assertEqual(representatives, ('A', 'B'))

    def test_empty_eligible_set_is_clean(self):
        assignments, representatives = extract_representative_categories((), ())
        self.assertIsNone(assignments.earliest_viable)
        self.assertIsNone(assignments.highest_success)
        self.assertIsNone(assignments.lowest_exposure)
        self.assertEqual(representatives, ())

    def test_one_candidate_pareto_set(self):
        row = candidate('only', 1, .9, 100)
        _, (assignments, representatives) = self.extract((row,))
        self.assertEqual((assignments.earliest_viable, assignments.highest_success,
                          assignments.lowest_exposure), ('only', 'only', 'only'))
        self.assertEqual(representatives, ('only',))

    def test_all_candidates_can_be_pareto_efficient(self):
        rows = (candidate('A', 1, .95, 500), candidate('B', 2, .9, 300),
                candidate('C', 3, .85, 100))
        pareto, (_, representatives) = self.extract(rows)
        self.assertEqual(pareto.pareto_candidate_ids, ('A', 'B', 'C'))
        self.assertEqual(representatives, ('A', 'C'))

    def test_only_one_pareto_candidate(self):
        rows = (candidate('A', 1, .95, 100), candidate('B', 2, .9, 200),
                candidate('C', 3, .8, 300))
        pareto, (_, representatives) = self.extract(rows)
        self.assertEqual(pareto.pareto_candidate_ids, ('A',))
        self.assertEqual(representatives, ('A',))

    def test_tolerance_ties_keep_canonical_candidate(self):
        rows = (candidate('A', 1, .9, 100),
                candidate('B', 2, .9 + .5e-12, 100 - .5e-9))
        pareto, (assignments, representatives) = self.extract(rows)
        self.assertEqual(pareto.pareto_candidate_ids, ('A', 'B'))
        self.assertEqual(assignments.highest_success, 'A')
        self.assertEqual(assignments.lowest_exposure, 'A')
        self.assertEqual(representatives, ('A',))


if __name__ == '__main__':
    unittest.main()
