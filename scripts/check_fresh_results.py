#!/usr/bin/env python3
"""Cross-language publication checks over freshly exported files only."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.api.validation import InvalidResult, validate_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory
    accepted, rejected = [], []
    planning = json.loads((directory / 'planning-1.json').read_text())
    simulation = json.loads((directory / 'simulation-7-1.json').read_text())
    assert planning == json.loads((directory / 'planning-2.json').read_text()), 'Planning exports differ'
    assert simulation == json.loads((directory / 'simulation-7-2.json').read_text()), 'Seed 7 exports differ'
    for path in sorted(directory.glob('*.json')):
        payload = json.loads(path.read_text())
        kind = 'planning' if path.name.startswith('planning') else 'simulation'
        before = deepcopy(payload)
        assert validate_result(kind, payload) is payload
        assert payload == before
        accepted.append({'kind': kind, 'payload': payload, 'name': path.name})
    for kind, source in (('planning', planning), ('simulation', simulation)):
        def reject(name, mutate):
            payload = deepcopy(source)
            mutate(payload)
            try:
                validate_result(kind, payload)
            except InvalidResult:
                rejected.append({'kind': kind, 'name': name, 'payload': payload})
            else:
                raise AssertionError(f'Python accepted {kind}/{name}')
        reject('wrong-schema', lambda p: p.update(schemaVersion='wrong/1'))
        reject('wrong-kind', lambda p: p.update(schemaVersion=('simulation' if kind == 'planning' else 'planning') + '-result/1'))
        if kind == 'planning':
            reject('invalid-coordinates', lambda p: p['candidates'][0]['position'].update(lat=91))
            reject('broken-reference', lambda p: p['representativeCandidateIds'].append('unknown'))
            reject('radius-mismatch', lambda p: next(c for c in p['candidates'] if 'footprint' in c)['footprint'].update(radiusM=101))
            reject('one-sample', lambda p: p['threat'].update(samples=p['threat']['samples'][:1]))
            reject('unordered-samples', lambda p: p['threat']['samples'].reverse())
        else:
            reject('invalid-coordinates', lambda p: p['trajectories'][0]['samples'][0]['position'].update(lon=181))
            reject('broken-reference', lambda p: p['selectedFootprints'][0].update(opportunityId='unknown'))
            reject('radius-mismatch', lambda p: p['selectedFootprints'][0].update(radiusM=101))
        # Nonfinite values cannot be encoded in strict JSON. Each language creates
        # these mutations independently after decoding the same actual payload.
        nonfinite = deepcopy(source)
        nonfinite['unexpectedNumber'] = float('nan')
        try:
            validate_result(kind, nonfinite)
        except InvalidResult:
            pass
        else:
            raise AssertionError('Python accepted NaN')
    # Contract-supported partial evidence and numerical zero remain distinct.
    evidence = deepcopy(planning)
    candidate = next(c for c in evidence['candidates'] if 'exposure' in c)
    candidate['exposure'].update(status='partial_coverage', peoplePotentiallyExposed=None,
                                 knownAreaExposure=0, coveredAreaFraction=0)
    validate_result('planning', evidence)
    accepted.append({'kind': 'planning', 'name': 'missing-and-zero-evidence', 'payload': evidence})
    corpus = directory / 'cross-language-corpus.json'
    corpus.write_text(json.dumps({'accepted': accepted, 'rejected': rejected}, allow_nan=False))
    subprocess.run(['node', '--experimental-strip-types', 'tests/fresh-results.mjs', str(corpus)],
                   cwd=ROOT / 'frontend', check=True, timeout=45)
    print(json.dumps({'freshExports': len(accepted) - 1, 'invalidCasesPerLanguage': len(rejected) + 2,
                      'deterministicPlanning': True, 'deterministicSeed7': True,
                      'seeds': [7, 17, 10020], 'evidencePreserved': True}))


if __name__ == '__main__':
    main()
