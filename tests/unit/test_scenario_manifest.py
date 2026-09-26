from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.simulation import (
    DEFAULT_SCENARIO_MANIFEST_PATH, ScenarioIdentityMismatch,
    SingaporeConsequenceProvider, SingaporeScenarioV2Generator,
    build_frozen_scenario_manifest, load_scenario_manifest,
    resolve_scenario_ref, validate_scenario_ref,
    verify_all_scenario_references)


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / 'data/results/rl/scenario-audit-v2.json'


class ScenarioManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_scenario_manifest()

    def generator(self):
        provider = SingaporeConsequenceProvider()
        return SingaporeScenarioV2Generator(
            config=provider.scenario_config, consequence_provider=provider)

    def test_checked_manifest_is_v5_flat_unique_and_canonical(self):
        document = self.manifest.document
        self.assertEqual(document['schema_version'],
                         'rl-scenario-suites/5')
        self.assertEqual(len(document['entries']), 544)
        self.assertEqual(len(self.manifest.entries_by_ref), 544)
        hashes = [row['canonical_episode_hash'] for row in document['entries']]
        self.assertEqual(len(hashes), len(set(hashes)))
        checked = DEFAULT_SCENARIO_MANIFEST_PATH.read_bytes()
        regenerated = (json.dumps(
            document, indent=2, sort_keys=True, ensure_ascii=False,
            allow_nan=False) + '\n').encode()
        self.assertEqual(regenerated, checked)

    def test_all_544_references_regenerate_and_hash_match(self):
        checked = verify_all_scenario_references(
            self.manifest, self.generator())
        self.assertEqual(len(checked), 544)
        self.assertEqual(checked, tuple(
            (entry['scenario_ref'], entry['canonical_episode_hash'])
            for entry in self.manifest.entries))

    def test_malformed_unknown_traversal_overlong_and_confusable_refs_fail(self):
        invalid = (
            'sg2:validation:999999', '../suites.json',
            'sg2:validation:000000/../../x',
            'sg2:validation:' + '0' * 100,
            'ѕg2:validation:000000', 'sg2：validation：000000',
            'sg2:VALIDATION:000000', 'sg2:validation:１７',
        )
        for value in invalid:
            with self.subTest(value=value):
                if re.fullmatch(r'sg2:validation:[0-9]{6}', value):
                    with self.assertRaises(KeyError):
                        resolve_scenario_ref(value, self.manifest)
                else:
                    with self.assertRaises(ValueError):
                        validate_scenario_ref(value)

    def test_seed_profile_checksum_provider_and_hash_tampering_is_rejected(self):
        source = deepcopy(self.manifest.document)
        mutations = []
        seed = deepcopy(source); seed['entries'][0]['seed'] += 1; mutations.append(seed)
        profile = deepcopy(source); profile['entries'][0]['profile'] = 'warmup'; mutations.append(profile)
        checksum = deepcopy(source); fake = 'sha256:' + '1' * 64
        checksum['distribution_checksum'] = fake
        for row in checksum['entries']: row['distribution_checksum'] = fake
        mutations.append(checksum)
        provider = deepcopy(source); provider['provider_identity'] = 'other-provider'
        for row in provider['entries']: row['provider_identity'] = 'other-provider'
        mutations.append(provider)
        training = deepcopy(source)
        training['training_seed_partition']['scenario_seed_offset'] -= 1
        mutations.append(training)
        oracle = deepcopy(source)
        oracle['bounded_oracle']['candidates_per_pair'] += 1
        mutations.append(oracle)
        boolean_index = deepcopy(source)
        boolean_index['entries'][0]['index'] = False
        mutations.append(boolean_index)
        with TemporaryDirectory() as directory:
            for index, value in enumerate(mutations):
                path = Path(directory) / ('manifest-%d.json' % index)
                path.write_text(json.dumps(value))
                with self.subTest(index=index), self.assertRaises(ValueError):
                    manifest = load_scenario_manifest(path)
                    resolve_scenario_ref(value['entries'][0]['scenario_ref'],
                                         manifest)
            value = deepcopy(source)
            value['entries'][0]['canonical_episode_hash'] = (
                'sha256:' + 'f' * 64)
            path = Path(directory) / 'hash.json'
            path.write_text(json.dumps(value))
            manifest = load_scenario_manifest(path)
            with self.assertRaises(ScenarioIdentityMismatch):
                resolve_scenario_ref(
                    value['entries'][0]['scenario_ref'], manifest,
                    self.generator())

    def test_manifest_builder_refuses_duplicate_episode_hashes(self):
        audit = json.loads(AUDIT.read_text())
        generator = self.generator()
        spec = generator.generate(10000, 'balanced')
        with patch.object(generator, 'generate', return_value=spec):
            with self.assertRaisesRegex(ValueError, 'duplicate canonical'):
                build_frozen_scenario_manifest(generator, audit)

    def test_check_mode_does_not_rewrite_manifest(self):
        before = DEFAULT_SCENARIO_MANIFEST_PATH.read_bytes()
        subprocess.run([
            str(ROOT / '.venv-rl/bin/python'),
            str(ROOT / 'scripts/build_scenario_manifest.py'), '--check'],
            cwd=ROOT, check=True, timeout=600)
        self.assertEqual(DEFAULT_SCENARIO_MANIFEST_PATH.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
