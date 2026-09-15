#!/usr/bin/env python3
"""Calculate people potentially exposed from prepared population and episode JSON files."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.exposure import CalculationSettings, PECValidationError, prepare_population, calculate_episode
from backend.exposure.calculator import invalid_result
from backend.exposure.validation import error


def load_json(path):
    def constant(value):
        raise ValueError('Nonfinite JSON constants are forbidden')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON object key: ' + key)
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=constant, object_pairs_hook=pairs)


def write_json(path, result):
    content = (json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--population', type=Path, required=True)
    parser.add_argument('--episode', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--circle-edges', type=int, choices=(128, 256), default=128)
    args = parser.parse_args()
    if any(args.output.resolve() == path.resolve() or
           (args.output.exists() and path.exists() and os.path.samefile(args.output, path))
           for path in (args.population, args.episode)):
        parser.error('Output must not overwrite either input')
    episode = None
    try:
        try:
            documents = []
            for kind, path in [('population', args.population), ('episode', args.episode)]:
                try:
                    documents.append(load_json(path))
                except (ValueError, UnicodeError) as exc:
                    raise PECValidationError([error('invalid_json', kind, '$', str(exc))]) from exc
            population, episode = documents
            result = calculate_episode(prepare_population(population), episode, CalculationSettings(args.circle_edges))
        except PECValidationError as exc:
            result = invalid_result(exc.errors, episode)
        write_json(args.output, result)
    except OSError as exc:
        print(f'PEC file error: {exc}', file=sys.stderr)
        return 1
    print(f"{result['status']}: {args.output}")
    return 2 if result['status'] == 'invalid_input' else 0


if __name__ == '__main__':
    raise SystemExit(main())
