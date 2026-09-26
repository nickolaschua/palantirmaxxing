#!/usr/bin/env python3
"""Write a deterministic legacy seed result or frozen-scenario replay."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.presentation import (simulation_result_to_dict,
                                  simulation_result_v2_to_dict)
from backend.simulation import (FeasibleImmediateMatchingPolicy,
                                NaiveLaunchOnDetectionPolicy,
                                OptimalFixedRankAssignmentPolicy,
                                ScenarioIdentityMismatch,
                                SingaporeConsequenceProvider,
                                SingaporeScenarioConfig,
                                SingaporeScenarioGenerator,
                                SingaporeScenarioV2Generator, SimulationEngine,
                                load_scenario_distribution,
                                load_scenario_manifest, resolve_scenario_ref)


POLICIES = {
    NaiveLaunchOnDetectionPolicy.identity: NaiveLaunchOnDetectionPolicy,
    FeasibleImmediateMatchingPolicy.identity: FeasibleImmediateMatchingPolicy,
    OptimalFixedRankAssignmentPolicy.identity:
        OptimalFixedRankAssignmentPolicy,
    'structured-behavior-cloning/1': None,
}

STRUCTURED_IMITATION_IDENTITY = 'structured-behavior-cloning/1'
STRUCTURED_IMITATION_ARTIFACT = (
    ROOT / 'data/results/rl/experiments/structured-imitation-512-seed7'
    / 'pipeline/bc-artifact')


def _provider(seed_provider, config):
    return SingaporeConsequenceProvider(
        catalog=seed_provider.catalog, scenario_config=config)


def _run_structured_imitation(episode, seed_provider, config):
    """Replay the fixed local BC artifact through the same masked environment."""
    from backend.learning import CentralizedInterceptionEnv, load_imitation_policy

    def provider_factory():
        return _provider(seed_provider, config)

    policy = load_imitation_policy(
        STRUCTURED_IMITATION_ARTIFACT, provider_factory=provider_factory)
    environment = CentralizedInterceptionEnv(
        provider_factory(), episode_spec=episode,
        policy_version=policy.model_version)
    try:
        observation, _ = environment.reset()
        while True:
            action, _ = policy.predict(
                observation, deterministic=True,
                action_masks=environment.action_masks())
            observation, _, terminated, truncated, _ = environment.step(
                int(action))
            if terminated or truncated:
                break
        if truncated or environment.engine is None:
            raise RuntimeError(
                'structured imitation replay truncated without a result')
        return environment.engine, policy.artifact_identity
    finally:
        environment.close()
        policy.close()


def _legacy(seed: int, policy_name: str):
    config = SingaporeScenarioConfig()
    seed_provider = SingaporeConsequenceProvider(scenario_config=config)
    generator = SingaporeScenarioGenerator(
        config=config, consequence_provider=seed_provider)
    episode = generator.generate(seed)

    baseline_engine = SimulationEngine(
        episode, _provider(seed_provider, config))
    baseline = FeasibleImmediateMatchingPolicy().run(baseline_engine)

    selected_engine = SimulationEngine(
        episode, _provider(seed_provider, config))
    policy = (FeasibleImmediateMatchingPolicy() if policy_name == 'baseline'
              else OptimalFixedRankAssignmentPolicy())
    selected = policy.run(selected_engine)
    return simulation_result_to_dict(
        selected_engine, policy_identity=policy.identity,
        baseline_raw_score=baseline.raw_score, assignment_plan=selected.plan)


def _frozen(scenario_ref: str, policy_identity: str):
    manifest = load_scenario_manifest()
    entry = manifest.entries_by_ref.get(scenario_ref)
    if entry is None:
        # Keep the resolver as the single canonical parser/error source.
        resolve_scenario_ref(scenario_ref, manifest=manifest)
        raise AssertionError('unknown scenario reference unexpectedly resolved')
    try:
        distribution = load_scenario_distribution(
            expected_checksum=entry['distribution_checksum'])
    except ValueError as exc:
        raise ScenarioIdentityMismatch(
            'scenario reference distribution identity mismatch') from exc
    config = SingaporeScenarioConfig()
    seed_provider = SingaporeConsequenceProvider(scenario_config=config)
    generator = SingaporeScenarioV2Generator(
        distribution=distribution, config=config,
        consequence_provider=seed_provider)
    episode = resolve_scenario_ref(
        scenario_ref, manifest=manifest, generator=generator)

    naive_engine = SimulationEngine(
        episode, _provider(seed_provider, config))
    NaiveLaunchOnDetectionPolicy().run(naive_engine)
    exact_engine = SimulationEngine(
        episode, _provider(seed_provider, config))
    exact_run = OptimalFixedRankAssignmentPolicy().run(exact_engine)
    artifact_identity = None
    if policy_identity == STRUCTURED_IMITATION_IDENTITY:
        active_engine, artifact_identity = _run_structured_imitation(
            episode, seed_provider, config)
    else:
        active_engine = SimulationEngine(
            episode, _provider(seed_provider, config))
        POLICIES[policy_identity]().run(active_engine)
    return simulation_result_v2_to_dict(
        active_engine, scenario_entry=entry,
        policy_identity=policy_identity, naive_engine=naive_engine,
        exact_engine=exact_engine, exact_plan=exact_run.plan,
        policy_artifact_identity=artifact_identity,
        policy_deployment_status=(
            'experimental-unpromoted' if artifact_identity else None))


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--seed', type=int)
    source.add_argument('--scenario-ref')
    parser.add_argument('--output', type=Path,
                        default=Path('data/results/demo-simulation-result.json'))
    parser.add_argument('--policy', choices=(
        'baseline', 'optimal', *POLICIES), default='baseline')
    args = parser.parse_args()
    if args.scenario_ref is None:
        if args.policy not in ('baseline', 'optimal'):
            parser.error('legacy seed runs accept policy baseline or optimal')
        payload = _legacy(7 if args.seed is None else args.seed, args.policy)
    else:
        if args.policy not in POLICIES:
            parser.error('frozen scenario runs require a versioned policy identity')
        try:
            payload = _frozen(args.scenario_ref, args.policy)
        except ScenarioIdentityMismatch as exc:
            print(str(exc), file=sys.stderr)
            return 42
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(
        payload, indent=2, sort_keys=True, ensure_ascii=False,
        allow_nan=False) + '\n', encoding='utf-8')
    print(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
