from contextlib import contextmanager
from copy import deepcopy
import http.client
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest

from backend.api.jobs import (
    InvalidSubmission, JobManager, RunFailure, validate_submission)
from backend.api.server import make_server
from backend.api.store import ResultNotFound, ResultStore
from backend.api.validation import InvalidResult, validate_result
from backend.simulation import load_scenario_manifest, manifest_public_metadata


ROOT = Path(__file__).resolve().parents[2]
DEMO_POLICIES = (
    'naive-launch-on-detection/1',
    'optimal-fixed-rank-assignment/1',
    'structured-behavior-cloning/1',
)


def completed(manager, identity, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = manager.get(identity)
        if record['status'] in ('succeeded', 'failed'):
            return record
        time.sleep(.02)
    raise AssertionError('timed out waiting for scenario run')


@contextmanager
def running_server(store, manager):
    server = make_server(store, jobs=manager)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown(); thread.join(timeout=5); server.server_close()


class ScenarioRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_scenario_manifest()
        cls.entry = cls.manifest.entries[0]

    def export(self, directory, policy='naive-launch-on-detection/1'):
        output = Path(directory) / (policy.split('/')[0] + '.json')
        subprocess.run([
            sys.executable, str(ROOT / 'scripts/export_simulation_result.py'),
            '--scenario-ref', self.entry['scenario_ref'], '--policy', policy,
            '--output', str(output)], cwd=ROOT, check=True, timeout=120,
            capture_output=True, text=True)
        return json.loads(output.read_text())

    def test_manifest_submission_contract_rejects_mixed_or_unchecked_input(self):
        for policy in DEMO_POLICIES:
            with self.subTest(policy=policy):
                accepted = validate_submission({
                    'kind': 'simulation',
                    'scenarioRef': self.entry['scenario_ref'],
                    'policy': policy,
                }, self.manifest)
                self.assertEqual(accepted, {
                    'kind': 'simulation',
                    'scenarioRef': self.entry['scenario_ref'],
                    'policy': policy,
                })
        invalid = (
            {'kind': 'simulation', 'scenarioRef': self.entry['scenario_ref']},
            {'kind': 'simulation', 'policy': 'naive-launch-on-detection/1'},
            {'kind': 'simulation', 'scenarioRef': self.entry['scenario_ref'],
             'policy': 'naive-launch-on-detection/1', 'seed': 1},
            {'kind': 'simulation', 'scenarioRef': self.entry['scenario_ref'],
             'policy': 'unknown/1'},
            {'kind': 'simulation', 'scenarioRef': 'sg2:validation:999999',
             'policy': 'naive-launch-on-detection/1'},
            {'kind': 'simulation', 'scenarioRef': '../../suites.json',
             'policy': 'naive-launch-on-detection/1'},
            {'kind': 'simulation', 'scenarioRef': self.entry['scenario_ref'],
             'policy': 'naive-launch-on-detection/1', 'extra': True},
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(InvalidSubmission):
                validate_submission(value, self.manifest)
        self.assertEqual(validate_submission({'kind': 'simulation'}),
                         {'kind': 'simulation', 'seed': 7})

    def test_every_request_maps_to_a_fixed_internal_argument_list(self):
        manager = object.__new__(JobManager)
        captured = []
        with TemporaryDirectory() as directory:
            def execute(args, _log):
                captured.append(args)
                output = Path(args[args.index('--output') + 1])
                output.write_text((ROOT / 'data/results/demo-simulation-result.json').read_text())
            manager._execute = execute
            JobManager._export(manager, {
                'kind': 'simulation', 'scenarioRef': self.entry['scenario_ref'],
                'policy': 'optimal-fixed-rank-assignment/1'}, Path(directory),
                Path(directory) / 'log')
        self.assertEqual(captured[0], [
            sys.executable, str(ROOT / 'scripts/export_simulation_result.py'),
            '--scenario-ref', self.entry['scenario_ref'], '--policy',
            'optimal-fixed-rank-assignment/1', '--output',
            str(Path(directory) / 'result.json')])

    def test_same_reference_and_policy_are_payload_deterministic(self):
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            a = self.export(first)
            b = self.export(second)
        self.assertEqual(a, b)
        self.assertEqual(a['schemaVersion'], 'simulation-result/2')
        validate_result('simulation', a)
        self.assertEqual(a['provenance']['scenarioRef'],
                         self.entry['scenario_ref'])

    def test_structured_imitation_export_is_fixed_and_provenance_bound(self):
        with TemporaryDirectory() as directory:
            payload = self.export(
                directory, 'structured-behavior-cloning/1')
        validate_result('simulation', payload)
        self.assertEqual(
            payload['policy']['identity'],
            'structured-behavior-cloning/1')
        self.assertEqual(
            payload['policy']['deploymentStatus'],
            'experimental-unpromoted')
        self.assertRegex(
            payload['policy']['artifactIdentity'], r'^sha256:[0-9a-f]{64}$')
        self.assertEqual(
            payload['provenance']['policyArtifactIdentity'],
            payload['policy']['artifactIdentity'])

    def test_all_three_demo_policies_execute_validate_publish_and_reload(self):
        """Exercise the same worker/publication path used by the live API."""
        with TemporaryDirectory() as directory:
            store = ResultStore(Path(directory) / 'store')
            manager = JobManager(store)
            try:
                for policy in DEMO_POLICIES:
                    with self.subTest(policy=policy):
                        submitted = manager.submit({
                            'kind': 'simulation',
                            'scenarioRef': self.entry['scenario_ref'],
                            'policy': policy,
                        })
                        final = completed(manager, submitted['runId'])
                        self.assertEqual(final['status'], 'succeeded', final)
                        self.assertEqual(final['policy'], policy)
                        envelope = store.get('simulation', final['resultId'])
                        payload = envelope['result']
                        validate_result('simulation', payload)
                        self.assertEqual(payload['policy']['identity'], policy)
                        self.assertEqual(
                            payload['provenance']['policyIdentity'], policy)
                        if policy == 'structured-behavior-cloning/1':
                            self.assertEqual(
                                payload['policy']['deploymentStatus'],
                                'experimental-unpromoted')
                            self.assertEqual(
                                payload['provenance']['policyArtifactIdentity'],
                                payload['policy']['artifactIdentity'])
            finally:
                manager.close()
                store.close()

    def test_v2_validation_rejects_counts_duplicates_outcomes_exactness_and_provenance(self):
        with TemporaryDirectory() as directory:
            payload = self.export(directory)
        mutations = []
        value = deepcopy(payload); value['outcomes'].pop(); mutations.append(value)
        value = deepcopy(payload); value['trajectories'][1]['threatId'] = value['trajectories'][0]['threatId']; mutations.append(value)
        value = deepcopy(payload); value['outcomes'][0]['outcome'] = 'escaped'; mutations.append(value)
        value = deepcopy(payload); value['policyComparison']['active']['ordinalCost'] = float('nan'); mutations.append(value)
        value = deepcopy(payload); value['policyComparison']['exactReference']['exact'] = False; mutations.append(value)
        value = deepcopy(payload); value['provenance']['seed'] += 1; mutations.append(value)
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(InvalidResult):
                validate_result('simulation', value)
        legacy = json.loads((
            ROOT / 'data/results/demo-simulation-result.json').read_text())
        self.assertIs(validate_result('simulation', legacy), legacy)

    def test_manifest_get_and_job_record_survive_restart(self):
        with TemporaryDirectory() as directory:
            store = ResultStore(Path(directory) / 'store')
            manager = JobManager(store)
            try:
                with running_server(store, manager) as port:
                    connection = http.client.HTTPConnection(
                        '127.0.0.1', port, timeout=10)
                    connection.request('GET', '/api/v1/scenario-manifest')
                    response = connection.getresponse()
                    body = json.loads(response.read())
                    connection.close()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(body, manifest_public_metadata(self.manifest))
                submitted = manager.submit({
                    'kind': 'simulation',
                    'scenarioRef': self.entry['scenario_ref'],
                    'policy': 'naive-launch-on-detection/1'})
                final = completed(manager, submitted['runId'])
                self.assertEqual(final['status'], 'succeeded', final)
                self.assertEqual(final['scenarioRef'], self.entry['scenario_ref'])
                self.assertEqual(final['policy'], 'naive-launch-on-detection/1')
            finally:
                manager.close()
            manager = JobManager(store)
            try:
                self.assertEqual(manager.get(submitted['runId']), final)
            finally:
                manager.close(); store.close()

    def test_exit_42_and_identity_failure_publish_nothing(self):
        with TemporaryDirectory() as directory:
            store = ResultStore(Path(directory) / 'store')
            manager = JobManager(store, executor=lambda *_: (_ for _ in ()).throw(
                RunFailure('SCENARIO_IDENTITY_MISMATCH', 'injected mismatch')))
            try:
                run = manager.submit({
                    'kind': 'simulation',
                    'scenarioRef': self.entry['scenario_ref'],
                    'policy': 'naive-launch-on-detection/1'})
                final = completed(manager, run['runId'])
                self.assertEqual(final['error']['code'],
                                 'SCENARIO_IDENTITY_MISMATCH')
                with self.assertRaises(ResultNotFound):
                    store.get('simulation')
                with self.assertRaises(RunFailure) as failure:
                    manager._execute([
                        sys.executable, '-c', 'raise SystemExit(42)'],
                        Path(directory) / 'exit.log')
                self.assertEqual(failure.exception.code,
                                 'SCENARIO_IDENTITY_MISMATCH')
            finally:
                manager.close(); store.close()


if __name__ == '__main__':
    unittest.main()
