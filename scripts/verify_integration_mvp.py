#!/usr/bin/env python3
"""Independent MVP acceptance runner. Incomplete gates fail closed."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from importlib import metadata
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.integration_preflight import INPUTS


# These paths contain reproducible or exploratory artifacts produced by long-running
# training jobs. They are not source inputs to the integration MVP, and another
# training run must not invalidate an otherwise unchanged source snapshot.
VOLATILE_OUTPUT_PREFIXES = (
    'data/results/rl/experiments/',
    'data/scenarios/rl/pools/',
    'nickolas/',
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def fingerprint():
    files = set(git('ls-files', '-z').decode().split('\0'))
    files.update(git('ls-files', '--others', '--exclude-standard', '-z').decode().split('\0'))
    hashes = {name: digest((ROOT / name).read_bytes()) for name in sorted(files)
              if name and not name.startswith(('graphify-out/', '.codex/', 'outputs/'))
              and not name.startswith(VOLATILE_OUTPUT_PREFIXES)
              and (ROOT / name).is_file()}
    versions = {}
    for command in ('node', 'npm'):
        try:
            versions[command] = subprocess.check_output([command, '--version'], text=True, timeout=10).strip()
        except (OSError, subprocess.SubprocessError) as exc:
            versions[command] = f'unavailable: {exc}'
    versions['pythonPackages'] = {d.metadata['Name']: d.version for d in metadata.distributions() if d.metadata['Name']}
    return {'gitHead': git('rev-parse', 'HEAD').decode().strip(),
            'trackedDiffSha256': digest(git('diff', 'HEAD', '--binary')),
            'sourceFilesSha256': digest(json.dumps(hashes, sort_keys=True).encode()),
            'sourceHashes': hashes,
            'inputHashes': {name: digest((ROOT / name).read_bytes())
                            for name in INPUTS if (ROOT / name).is_file()},
            'lockfileSha256': digest((ROOT / 'frontend/package-lock.json').read_bytes()),
            'python': sys.version, 'platform': platform.platform(), 'runtimeVersions': versions}


class Harness:
    def __init__(self, evidence):
        self.evidence = evidence
        self.records = []
        self.current = None

    def assert_that(self, condition, message):
        self.current['assertions'].append({'description': message, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(message)

    def check_junit(self, path, minimum):
        suites = ET.parse(path).getroot().findall('testsuite')
        self.assert_that(sum(int(s.attrib['tests']) for s in suites) >= minimum
                         and all(int(s.attrib.get(field, 0)) == 0 for s in suites for field in ('skipped', 'errors', 'failures')),
                         f'{path.name}: at least {minimum} tests, no failures/errors/skips')

    def run(self, args, *, cwd=ROOT, timeout=300, expected=0, env=None):
        index = len(self.current['commands'])
        log = self.evidence / f"{self.current['id']}-{index:02d}.log"
        record = {'argv': [str(x) for x in args], 'cwd': str(cwd), 'log': str(log)}
        self.current['commands'].append(record)
        self.current['evidencePaths'].append(str(log))
        started = time.monotonic()
        with log.open('w') as stream:
            process = subprocess.Popen(args, cwd=cwd, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except BaseException:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=25)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise
            finally:
                record.update(exitCode=process.returncode, elapsedSeconds=time.monotonic() - started)
        self.assert_that(code == expected, f'Command {index} exit {code}; expected {expected}')
        return log.read_text()

    def b01(self):
        lock = (ROOT / 'frontend/package-lock.json').read_bytes()
        self.run([sys.executable, '-m', 'pip', 'install', '-r', 'scripts/requirements-integration.txt'])
        self.run(['npm', 'ci'], cwd=ROOT / 'frontend')
        self.assert_that(lock == (ROOT / 'frontend/package-lock.json').read_bytes(),
                         'Dependency installation preserves package-lock.json')
        self.run([sys.executable, 'scripts/integration_preflight.py'])
        with tempfile.TemporaryDirectory(prefix='mvp-prerequisite-') as missing:
            output = self.run([sys.executable, 'scripts/integration_preflight.py', '--input-root', missing], expected=1)
            self.assert_that(f'{missing}/data/processed/population-projected.json' in output
                             and 'Recovery:' in output and 'population_data.py' in output,
                             'Missing input reports exact path and recovery command')
            env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=missing)
            output = self.run(['node', '--experimental-strip-types', 'tests/preflight.mjs'],
                              cwd=ROOT / 'frontend', env=env, expected=1)
            self.assert_that('Missing Chromium:' in output and 'playwright install chromium' in output,
                             'Missing Chromium fails explicitly without skipping')
        junit = self.evidence / 'backend.xml'
        self.run([sys.executable, '-m', 'pytest', '-q', '--junitxml', str(junit)], timeout=1200)
        suites = ET.parse(junit).getroot().findall('testsuite')
        self.assert_that(sum(int(s.attrib['tests']) for s in suites) >= 318,
                         'Backend suite contains at least the 318 established tests')
        self.assert_that(all(int(s.attrib.get('skipped', 0)) == 0 for s in suites),
                         'No backend tests skipped')
        self.current['evidencePaths'].append(str(junit))
        output = self.run(['npm', 'test'], cwd=ROOT / 'frontend')
        unit_count = re.search(r'pass\s+(\d+)', output)
        self.assert_that(unit_count is not None and int(unit_count.group(1)) >= 32
                         and 'skipped 0' in output,
                         'All frontend model tests pass without skips (at least 32)')
        output = self.run(['npm', 'run', 'test:ui'], cwd=ROOT / 'frontend')
        ui_count = re.search(r'Tests\s+(\d+) passed', output)
        self.assert_that(ui_count is not None and int(ui_count.group(1)) >= 25 and 'skipped' not in output,
                         'All original UI tests and refresh tests pass without skips (at least 25)')
        self.run(['npm', 'run', 'build'], cwd=ROOT / 'frontend')

    def b02(self):
        curated = {
            str(path): digest(path.read_bytes())
            for path in (ROOT / 'data/results').rglob('*.json')
            if not path.relative_to(ROOT).as_posix().startswith(
                'data/results/rl/experiments/')}
        with tempfile.TemporaryDirectory(prefix='mvp-fresh-') as temporary:
            directory = Path(temporary)
            for repeat in (1, 2):
                self.run([sys.executable, 'scripts/export_static_mvp_planning_result.py',
                          '--scenario', 'data/scenarios/demo-singapore.json',
                          '--output', str(directory / f'planning-{repeat}.json')])
            for seed, repeat in ((7, 1), (7, 2), (17, 1), (10020, 1)):
                self.run([sys.executable, 'scripts/export_simulation_result.py', '--seed', str(seed),
                          '--output', str(directory / f'simulation-{seed}-{repeat}.json')])
            self.run([sys.executable, 'scripts/check_fresh_results.py', str(directory)])
            manifest = self.evidence / 'fresh-exports.json'
            manifest.write_text(json.dumps({p.name: digest(p.read_bytes()) for p in directory.glob('*.json')}, indent=2))
            self.current['evidencePaths'].append(str(manifest))
        self.assert_that(all(Path(path).is_file() and digest(Path(path).read_bytes()) == sha
                             for path, sha in curated.items()), 'Curated result artifacts unchanged')
        self.run(['npm', 'test'], cwd=ROOT / 'frontend')
        self.run(['npm', 'run', 'test:ui'], cwd=ROOT / 'frontend')
        self.run(['npm', 'run', 'build'], cwd=ROOT / 'frontend')

    def b03(self):
        self.run([sys.executable, '-m', 'pytest', '-q', 'tests/integration/test_result_store.py',
                  '--junitxml', str(self.evidence / 'store.xml')])
        self.current['evidencePaths'].append(str(self.evidence / 'store.xml'))
        self.check_junit(self.evidence / 'store.xml', 4)

    def b04(self):
        self.run([sys.executable, '-m', 'pytest', '-q', 'tests/integration/test_result_http.py',
                  '--junitxml', str(self.evidence / 'http.xml')])
        self.current['evidencePaths'].append(str(self.evidence / 'http.xml'))
        self.check_junit(self.evidence / 'http.xml', 3)

    def browser_gate(self, gate):
        with tempfile.TemporaryDirectory(prefix='mvp-browser-') as temporary:
            directory = Path(temporary)
            self.run([sys.executable, 'scripts/export_static_mvp_planning_result.py',
                      '--scenario', 'data/scenarios/demo-singapore.json', '--output', str(directory / 'planning.json')])
            self.run([sys.executable, 'scripts/export_simulation_result.py', '--seed', '7',
                      '--output', str(directory / 'simulation.json')])
            if gate == 'B08':
                self.write_warmup_result(directory / 'warmup.json')
            output = self.evidence / gate
            try:
                self.run(['node', 'tests/browser-integration.mjs', gate, str(output), str(directory), sys.executable],
                          cwd=ROOT / 'frontend', timeout=600 if gate == 'B08' else 240)
            finally:
                self.current['evidencePaths'].extend(str(p) for p in output.rglob('*') if p.is_file())

    @staticmethod
    def write_warmup_result(path):
        """Build a real two-threat v2 payload for browser geometry acceptance."""
        from backend.presentation import simulation_result_v2_to_dict
        from backend.simulation import (
            NaiveLaunchOnDetectionPolicy, OptimalFixedRankAssignmentPolicy,
            SingaporeConsequenceProvider, SingaporeScenarioConfig,
            SingaporeScenarioV2Generator, SimulationEngine,
            canonical_episode_hash, load_scenario_distribution)

        config = SingaporeScenarioConfig()
        seed_provider = SingaporeConsequenceProvider(scenario_config=config)
        distribution = load_scenario_distribution()
        generator = SingaporeScenarioV2Generator(
            distribution=distribution, config=config,
            consequence_provider=seed_provider)
        episode = next((candidate for seed in range(90_000, 90_200)
                        for candidate in (generator.generate(seed, 'warmup'),)
                        if len(candidate.threats) == 2), None)
        if episode is None:
            raise AssertionError('could not construct a two-threat warmup fixture')

        def engine():
            provider = SingaporeConsequenceProvider(
                catalog=seed_provider.catalog, scenario_config=config)
            return SimulationEngine(episode, provider)

        naive_engine = engine()
        NaiveLaunchOnDetectionPolicy().run(naive_engine)
        exact_engine = engine()
        exact_run = OptimalFixedRankAssignmentPolicy().run(exact_engine)
        active_engine = engine()
        NaiveLaunchOnDetectionPolicy().run(active_engine)
        entry = {
            'scenario_ref': 'sg2:validation:999999',
            'split': 'validation', 'index': 999999,
            'seed': episode.seed, 'profile': 'warmup',
            'generator_version': generator.version,
            'distribution_version': distribution.version,
            'distribution_checksum': distribution.checksum,
            'provider_identity': 'singapore-demo-v2',
            'canonical_episode_hash': canonical_episode_hash(episode),
            'expected_feasible': True,
        }
        payload = simulation_result_v2_to_dict(
            active_engine, scenario_entry=entry,
            policy_identity=NaiveLaunchOnDetectionPolicy.identity,
            naive_engine=naive_engine, exact_engine=exact_engine,
            exact_plan=exact_run.plan)
        path.write_text(json.dumps(
            payload, indent=2, sort_keys=True, ensure_ascii=False,
            allow_nan=False) + '\n')

    def b05(self):
        self.browser_gate('B05')

    def b06(self):
        self.run(['npm', 'run', 'test:ui'], cwd=ROOT / 'frontend')
        self.browser_gate('B06')

    def b07(self):
        self.run([sys.executable, '-m', 'pytest', '-q', 'tests/integration/test_run_jobs.py',
                  '--junitxml', str(self.evidence / 'jobs.xml')])
        self.current['evidencePaths'].append(str(self.evidence / 'jobs.xml'))
        self.check_junit(self.evidence / 'jobs.xml', 6)

    def b08(self):
        self.browser_gate('B08')

    def b09(self):
        self.browser_gate('B09')

    def b10(self):
        self.run([sys.executable, '-m', 'pytest', '-q', '--junitxml', str(self.evidence / 'final-backend.xml')], timeout=1200)
        suites = ET.parse(self.evidence / 'final-backend.xml').getroot().findall('testsuite')
        self.assert_that(sum(int(s.attrib['tests']) for s in suites) >= 333
                         and all(int(s.attrib.get('skipped', 0)) == 0 for s in suites),
                         'Final backend regression, including real launcher tests, passes without skips')
        self.current['evidencePaths'].append(str(self.evidence / 'final-backend.xml'))
        self.run(['npm', 'test'], cwd=ROOT / 'frontend')
        self.run(['npm', 'run', 'test:ui'], cwd=ROOT / 'frontend')
        self.run(['npm', 'run', 'build'], cwd=ROOT / 'frontend')
        self.run(['git', 'diff', '--check'])
        self.run(['git', 'diff', '--exit-code', 'HEAD', '--', 'data/results'])
        self.run(['graphify', 'update', '.'], timeout=180)
        self.assert_that((ROOT / 'graphify-out/graph.json').is_file(), 'Graphify output is present after refresh')

    def gate(self, name):
        self.current = {'id': name, 'status': 'running', 'assertions': [], 'commands': [], 'evidencePaths': []}
        self.records.append(self.current)
        started = time.monotonic()
        try:
            implementation = getattr(self, name.lower(), None)
            if implementation is None:
                raise NotImplementedError(f'{name} acceptance gate is not implemented')
            implementation()
            self.current['status'] = 'passed'
        except Exception as exc:
            self.current.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        finally:
            self.current['elapsedSeconds'] = time.monotonic() - started
        print(f"{name}: {self.current['status']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--all', action='store_true')
    selection.add_argument('--gate', choices=[f'B{i:02d}' for i in range(1, 11)])
    args = parser.parse_args()
    evidence = ROOT / 'outputs/integration-mvp/evidence' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    evidence.mkdir(parents=True)
    harness = Harness(evidence)
    report = {'startedAt': datetime.now(timezone.utc).isoformat(), 'state': fingerprint(), 'gates': harness.records}
    print(f'Evidence: {evidence}', flush=True)
    for name in ([f'B{i:02d}' for i in range(1, 11)] if args.all else [args.gate]):
        harness.gate(name)
        (evidence / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    final_state = fingerprint()
    report['finishedAt'] = datetime.now(timezone.utc).isoformat()
    report['testedStateUnchanged'] = all(report['state'][key] == final_state[key]
        for key in ('gitHead', 'trackedDiffSha256', 'sourceFilesSha256', 'inputHashes', 'lockfileSha256'))
    if not report['testedStateUnchanged']:
        report['stateError'] = 'Source or inputs changed during verification; results cannot prove this state.'
    report['status'] = 'passed' if report['testedStateUnchanged'] and all(row['status'] == 'passed' for row in harness.records) else 'failed'
    (evidence / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    if args.all:
        latest = evidence.parent / 'latest-full'
        temporary = evidence.parent / '.latest-full.tmp'
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(evidence.name, target_is_directory=True)
        os.replace(temporary, latest)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
