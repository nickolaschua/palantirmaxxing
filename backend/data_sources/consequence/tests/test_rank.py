import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.data_sources.consequence import pipeline

HEADER = ['site_id', 'condition_id', 'role', 'C_low', 'C_central', 'C_high', 'secondary_central', 'veto_status',
          'veto_reasons_civilian', 'veto_reasons_capability']


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(zip(HEADER, r)))


class CrossSectorRank(unittest.TestCase):
    def test_sectors_join_one_ordering_with_vetoed_rows_last(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write(out / 'residential/residential_output.csv',
                  [('hdb:1', 'weekday_midday', 'hdb_block', 1, 2, 3, 40, 'unknown', '', ''),
                   ('hdb:1', 'weekday_night', 'hdb_block', 1, 9, 9, 40, 'unknown', '', '')])
            write(out / 'parks_civic/parks_civic_output.csv',
                  [('PARK-1', 'WD_DAY', 'park', 0, 0.5, 1, 10, 'unknown', '', '')])
            write(out / 'defence/military_output.csv',
                  [('military-9', 'weekday_midday', 'military_air_base', 0, 0.1, 1, 20, 'vetoed', '',
                    'priority_asset_capability_not_assessed')])
            with mock.patch.object(pipeline, 'OUTPUT', out):
                pipeline.run_rank('weekday_midday', out / 'ranking.csv')
            with (out / 'ranking.csv').open(encoding='utf-8') as f:
                rows = list(csv.DictReader(f))
        self.assertEqual([r['site_id'] for r in rows], ['PARK-1', 'hdb:1', 'military-9'])
        self.assertEqual([r['source'] for r in rows], ['parks_civic', 'residential', 'military'])
        self.assertEqual(rows[-1]['veto_reasons_capability'], 'priority_asset_capability_not_assessed')

    def test_all_conditions_rank_separately_in_one_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write(out / 'residential/residential_output.csv',
                  [('hdb:1', 'weekday_midday', 'hdb_block', 1, 2, 3, 40, 'unknown', '', ''),
                   ('hdb:1', 'weekday_night', 'hdb_block', 1, 9, 9, 40, 'unknown', '', '')])
            write(out / 'parks_civic/parks_civic_output.csv',
                  [('PARK-1', 'WD_DAY', 'park', 0, 0.5, 1, 10, 'unknown', '', ''),
                   ('PARK-1', 'WD_NIGHT', 'park', 0, 20, 30, 10, 'unknown', '', '')])
            with mock.patch.object(pipeline, 'OUTPUT', out):
                pipeline.run_rank('all', out / 'ranking.csv')
            with (out / 'ranking.csv').open(encoding='utf-8') as f:
                rows = [(r['condition_id'], r['rank'], r['site_id']) for r in csv.DictReader(f)]
        self.assertEqual(rows, [('weekday_midday', '1', 'PARK-1'), ('weekday_midday', '2', 'hdb:1'),
                                ('weekday_night', '1', 'hdb:1'), ('weekday_night', '2', 'PARK-1')])


if __name__ == '__main__':
    unittest.main()
