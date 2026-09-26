"""Deterministic policy/baseline evaluation and acceptance metrics."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import random
import statistics
import time
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from backend.simulation import (DeterministicToyProvider, EpisodeSpec,
                                ImmediateInterceptionPolicy, ObjectiveDirection,
                                SeededScenarioGenerator, SimulationEngine,
                                canonical_episode_hash)

from backend.simulation.suites import (ORACLE_CANDIDATES_PER_PAIR,
                                      ORACLE_MAX_ACTION_SEQUENCES,
                                      ORACLE_MAX_INTERCEPTORS, ORACLE_MAX_THREATS)

from .environment import CentralizedInterceptionEnv
from .oracle import bounded_oracle


@dataclass(frozen=True)
class OracleEvidence:
    raw_score: Optional[float]
    exact: bool
    enumerated_action_sequences: int
    max_action_sequences: int
    actions: Tuple[Tuple[object, ...], ...]
    normalized_regret: Optional[float]
    regret_ineligibility_reason: Optional[str]


@dataclass(frozen=True)
class EpisodeEvaluation:
    seed: int
    episode_id: str
    canonical_episode_hash: str
    policy_raw_score: float
    baseline_raw_score: float
    policy_reward: float
    policy_actions: int
    policy_inference_p95_ms: float
    decision_path_p95_ms: float
    model_version: str
    baseline_version: str
    provider_identity: str
    provider_version: str
    score_direction: str
    simulator_version: str
    scenario_generator_version: str
    policy_inference_samples_ms: Tuple[float, ...]
    decision_path_samples_ms: Tuple[float, ...]
    oracle: Optional[OracleEvidence] = None


@dataclass(frozen=True)
class ComparisonSummary:
    episode_count: int
    win_rate: float
    policy_mean_raw_score: float
    baseline_mean_raw_score: float
    favorable_mean_difference: float
    favorable_mean_difference_ci95: Tuple[float, float]
    relative_mean_improvement: float
    inference_p95_ms: float
    decision_path_p95_ms: float
    oracle_episode_count: int
    oracle_exact_episode_count: int
    oracle_eligible_regret_count: int
    median_normalized_regret: Optional[float]
    oracle_enumerated_action_sequences: int


def _rollout_model(model: Any, env: CentralizedInterceptionEnv,
                   seed: int) -> Tuple[float, float, int, Tuple[float, ...], Tuple[float, ...], Mapping[str, Any]]:
    observation, info = env.reset(seed=seed)
    total_reward = 0.0
    inference_timings: List[float] = []
    decision_timings: List[float] = []
    actions = 0
    while True:
        started = time.perf_counter()
        mask = env.action_masks().astype(bool)
        inference_started = time.perf_counter()
        prediction = model.predict(
            observation, deterministic=True, action_masks=mask)
        inference_timings.append((time.perf_counter() - inference_started) * 1000.0)
        action = prediction[0] if isinstance(prediction, tuple) else prediction
        if isinstance(action, np.ndarray):
            action = int(action.reshape(-1)[0])
        observation, reward, terminated, truncated, info = env.step(int(action))
        # Includes candidate generation, observation encoding, action masking and
        # deterministic inference for the complete decision path.
        decision_timings.append((time.perf_counter() - started) * 1000.0)
        total_reward += float(reward)
        actions += 1
        if terminated or truncated:
            if truncated:
                raise RuntimeError('policy episode truncated: ' + str(info['termination_reason']))
            break
    return (float(info['raw_score']), total_reward, actions,
            tuple(inference_timings), tuple(decision_timings), info)


def evaluate_model(model: Any, seeds: Sequence[int],
                   generator: Optional[SeededScenarioGenerator] = None,
                   provider_factory: Callable[[], Any] = DeterministicToyProvider,
                   report_path: Optional[Path] = None,
                   full_capacity: bool = False,
                   include_oracle: bool = False,
                   oracle_max_action_sequences: int = ORACLE_MAX_ACTION_SEQUENCES) -> Tuple[EpisodeEvaluation, ...]:
    if generator is None:
        generator = (SeededScenarioGenerator(
            max_threats=ORACLE_MAX_THREATS,
            max_interceptors=ORACLE_MAX_INTERCEPTORS,
            candidate_count=ORACLE_CANDIDATES_PER_PAIR)
            if include_oracle else SeededScenarioGenerator())
    rows = []
    for seed in seeds:
        spec: EpisodeSpec = generator.generate(int(seed), full_capacity=full_capacity)
        env = CentralizedInterceptionEnv(provider_factory(), episode_spec=spec)
        try:
            policy_raw, reward, actions, inference_samples, decision_samples, info = _rollout_model(
                model, env, int(seed))
        finally:
            env.close()
        baseline_engine = SimulationEngine(spec, provider_factory())
        baseline = ImmediateInterceptionPolicy().run(baseline_engine)
        if baseline.truncated or baseline.raw_score is None:
            raise RuntimeError('baseline episode did not terminate normally')
        oracle_evidence = None
        if include_oracle:
            oracle = bounded_oracle(
                SimulationEngine(spec, provider_factory()),
                max_action_sequences=oracle_max_action_sequences)
            regret = None
            reason = None
            direction = ObjectiveDirection(info['score_direction'])
            if not oracle.exact:
                reason = 'oracle_inexact'
            elif oracle.raw_score is None:
                reason = 'oracle_score_unavailable'
            elif ((direction == ObjectiveDirection.MINIMIZE
                   and oracle.raw_score >= baseline.raw_score)
                  or (direction == ObjectiveDirection.MAXIMIZE
                      and oracle.raw_score <= baseline.raw_score)):
                reason = 'oracle_not_strictly_better_than_baseline'
            else:
                regret = normalized_regret(
                    policy_raw, float(baseline.raw_score), oracle.raw_score, direction)
            oracle_evidence = OracleEvidence(
                raw_score=oracle.raw_score, exact=oracle.exact,
                enumerated_action_sequences=oracle.enumerated_action_sequences,
                max_action_sequences=oracle_max_action_sequences,
                actions=oracle.actions, normalized_regret=regret,
                regret_ineligibility_reason=reason)
        rows.append(EpisodeEvaluation(
            seed=int(seed),
            episode_id=spec.episode_id,
            canonical_episode_hash=canonical_episode_hash(spec),
            policy_raw_score=policy_raw,
            baseline_raw_score=float(baseline.raw_score),
            policy_reward=reward,
            policy_actions=actions,
            policy_inference_p95_ms=float(np.percentile(inference_samples, 95)),
            decision_path_p95_ms=float(np.percentile(decision_samples, 95)),
            policy_inference_samples_ms=inference_samples,
            decision_path_samples_ms=decision_samples,
            oracle=oracle_evidence,
            model_version=getattr(model, 'model_version', model.__class__.__name__),
            baseline_version=ImmediateInterceptionPolicy.identity,
            provider_identity=info['provider']['identity'],
            provider_version=info['provider']['version'],
            score_direction=info['score_direction'],
            simulator_version=info['simulator_version'],
            scenario_generator_version=generator.version,
        ))
    result = tuple(rows)
    if report_path is not None:
        summary = summarize_comparison(result)
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        is_toy = all(
            row.provider_identity == DeterministicToyProvider.identity
            for row in result)
        path.write_text(json.dumps({
            'schema_version': 'rl-evaluation/2',
            'artifact_label': ('toy provider: plumbing validation only' if is_toy
                               else 'Singapore demo-v2 assumption-grade evaluation'),
            'summary': asdict(summary),
            'acceptance_gates': acceptance_evidence(summary, summary.median_normalized_regret),
            'episodes': [asdict(item) for item in result],
        }, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    return result


def _favorable_difference(row: EpisodeEvaluation) -> float:
    if row.score_direction == ObjectiveDirection.MINIMIZE.value:
        return row.baseline_raw_score - row.policy_raw_score
    if row.score_direction == ObjectiveDirection.MAXIMIZE.value:
        return row.policy_raw_score - row.baseline_raw_score
    raise ValueError('unknown score direction')


def bootstrap_mean_ci(values: Sequence[float], confidence: float = 0.95,
                      resamples: int = 5000, seed: int = 8675309) -> Tuple[float, float]:
    if not values:
        raise ValueError('bootstrap input cannot be empty')
    if type(resamples) is not int or resamples <= 0:
        raise ValueError('resamples must be a positive integer')
    if not 0 < confidence < 1:
        raise ValueError('confidence must be between zero and one')
    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        means.append(statistics.fmean(
            values[rng.randrange(len(values))] for _ in values))
    means.sort()
    tail = (1.0 - confidence) / 2.0
    low = means[max(0, int(tail * resamples))]
    high = means[min(resamples - 1, int((1.0 - tail) * resamples) - 1)]
    return float(low), float(high)


def summarize_comparison(rows: Sequence[EpisodeEvaluation]) -> ComparisonSummary:
    if not rows:
        raise ValueError('at least one evaluation row is required')
    directions = {row.score_direction for row in rows}
    if len(directions) != 1:
        raise ValueError('objective direction changed across evaluation episodes')
    differences = [_favorable_difference(row) for row in rows]
    policy_mean = statistics.fmean(row.policy_raw_score for row in rows)
    baseline_mean = statistics.fmean(row.baseline_raw_score for row in rows)
    denominator = abs(baseline_mean)
    relative = statistics.fmean(differences) / denominator if denominator else 0.0
    oracles = [row.oracle for row in rows if row.oracle is not None]
    regrets = [item.normalized_regret for item in oracles
               if item.exact and item.regret_ineligibility_reason is None
               and item.normalized_regret is not None]
    return ComparisonSummary(
        episode_count=len(rows),
        win_rate=sum(value > 0 for value in differences) / len(differences),
        policy_mean_raw_score=policy_mean,
        baseline_mean_raw_score=baseline_mean,
        favorable_mean_difference=statistics.fmean(differences),
        favorable_mean_difference_ci95=bootstrap_mean_ci(differences),
        relative_mean_improvement=relative,
        inference_p95_ms=float(np.percentile(
            [sample for row in rows for sample in row.policy_inference_samples_ms], 95)),
        decision_path_p95_ms=float(np.percentile(
            [sample for row in rows for sample in row.decision_path_samples_ms], 95)),
        oracle_episode_count=len(oracles),
        oracle_exact_episode_count=sum(item.exact for item in oracles),
        oracle_eligible_regret_count=len(regrets),
        median_normalized_regret=statistics.median(regrets) if regrets else None,
        oracle_enumerated_action_sequences=sum(item.enumerated_action_sequences for item in oracles),
    )


def normalized_regret(policy_score: float, baseline_score: float,
                      oracle_score: float,
                      direction: ObjectiveDirection) -> float:
    values = (policy_score, baseline_score, oracle_score)
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError('regret scores must be finite')
    if not isinstance(direction, ObjectiveDirection):
        direction = ObjectiveDirection(direction)
    if direction == ObjectiveDirection.MINIMIZE:
        denominator = baseline_score - oracle_score
        numerator = policy_score - oracle_score
    else:
        denominator = oracle_score - baseline_score
        numerator = oracle_score - policy_score
    if denominator <= 0:
        raise ValueError('oracle must be strictly better than baseline for normalized regret')
    return numerator / denominator


def acceptance_evidence(summary: ComparisonSummary,
                        median_oracle_regret: Optional[float] = None) -> Mapping[str, bool]:
    return {
        'win_rate_at_least_60_percent': summary.win_rate >= 0.60,
        'mean_improvement_at_least_5_percent': summary.relative_mean_improvement >= 0.05,
        'bootstrap_ci_excludes_zero': summary.favorable_mean_difference_ci95[0] > 0,
        'median_normalized_regret_at_most_10_percent': (
            summary.oracle_eligible_regret_count > 0
            and median_oracle_regret is not None
            and math.isfinite(median_oracle_regret)
            and median_oracle_regret <= 0.10),
        'decision_path_p95_below_100_ms': summary.decision_path_p95_ms < 100.0,
    }
