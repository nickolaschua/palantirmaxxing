import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from shapely import from_wkt
from backend.data_sources.acquisition import acquire, verify_cache
from backend.data_sources.pipeline import prepare

FIXTURES=Path(__file__).resolve().parents[1]/'fixtures'


class PipelineTests(unittest.TestCase):
    def test_offline_pipeline_reproducibility_and_projected_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for d in ['raw','processed','public']: (root/d).mkdir()
            # Small official excerpts use the same formats; only completeness counts differ.
            with patch('backend.data_sources.acquisition.EXPECTED_POPULATION_ROWS',6), patch('backend.data_sources.acquisition.EXPECTED_BOUNDARIES',4):
                acquire(root/'raw',population_file=FIXTURES/'population-sample.json',boundary_file=FIXTURES/'boundary-sample.geojson')
                report=prepare(root/'raw',root/'processed',root/'public/population.geojson')
                before={p.name:p.read_bytes() for p in (root/'processed').iterdir()}
                prepare(root/'raw',root/'processed',root/'public/population.geojson')
                self.assertEqual(before,{p.name:p.read_bytes() for p in (root/'processed').iterdir()})
                self.assertEqual((root/'public/population.geojson').read_bytes(),before['population-display.geojson'])
                projected=json.loads(before['population-projected.json'])
                display=json.loads(before['population-display.geojson'])
                original=json.loads((FIXTURES/'boundary-sample.geojson').read_text())
                geometries={f['properties']['SUBZONE_C']:f['geometry'] for f in original['features']}
                self.assertEqual(report['counts']['matched'],4)
                self.assertEqual(projected['crs'],'EPSG:3414')
                self.assertEqual(projected['units'],'metre')
                for zone in projected['zones']:
                    geometry=from_wkt(zone['geometry_wkt'])
                    self.assertTrue(geometry.is_valid)
                    self.assertAlmostEqual(geometry.area,zone['zone_area_m2'],places=5)
                    self.assertAlmostEqual(zone['population']/geometry.area,zone['population_density_people_per_m2'])
                for feature in display['features']:
                    self.assertEqual(feature['geometry'],geometries[feature['id']])
                # Cached acquisition never hits the network.
                with patch('backend.data_sources.acquisition.get',side_effect=AssertionError('network access')):
                    acquire(root/'raw')
                # A failed refresh must not replace the valid cache.
                snapshot={p.name:p.read_bytes() for p in (root/'raw').iterdir()}
                with patch('backend.data_sources.acquisition.get',side_effect=ValueError('download failed')):
                    with self.assertRaises(ValueError): acquire(root/'raw',refresh=True)
                self.assertEqual(snapshot,{p.name:p.read_bytes() for p in (root/'raw').iterdir()})
                # Even a syntactically successful but capped response cannot replace cache.
                incomplete=json.loads((FIXTURES/'population-sample.json').read_text())
                incomplete['result']['records']=incomplete['result']['records'][:-1]
                responses=[json.dumps(incomplete).encode(), b'{"code":0,"data":{"url":"https://example.invalid/blob"}}', (FIXTURES/'boundary-sample.geojson').read_bytes()]
                with patch('backend.data_sources.acquisition.get',side_effect=responses):
                    with self.assertRaises(ValueError): acquire(root/'raw',refresh=True)
                self.assertEqual(snapshot,{p.name:p.read_bytes() for p in (root/'raw').iterdir()})
                verify_cache(root/'raw')
                (root/'raw/population-api.json').write_text('{}')
                with self.assertRaises(ValueError): verify_cache(root/'raw')


if __name__=='__main__': unittest.main()
