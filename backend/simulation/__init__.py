"""Public interface for the isolated continuous-event simulation layer."""
from .engine import SimulationEngine
from .models import (MAX_CANDIDATES_PER_PAIR, MAX_INTERCEPTORS, MAX_THREATS,
                     EPISODE_SCHEMA_VERSIONS, SIMULATOR_VERSION, AbsoluteCandidate, Assignment,
                     AssignmentStatus, EpisodeSpec, EventKind, EventRecord,
                     InterceptorResource, ResolutionKind, ScheduledThreat,
                     ThreatStatus)
from .provider import (ConsequenceProvider, DeterministicToyProvider,
                       ObjectiveDirection, ProviderEvaluation, provider_identity)
from .baseline import BaselineRun, ImmediateInterceptionPolicy
from .recording import (ROLLOUT_SCHEMA_VERSION, JsonlRolloutRecorder,
                        RolloutRecord, observation_reference, replay_rollout)
from .scenarios import (SCENARIO_GENERATOR_VERSION, SeededScenarioGenerator,
                        generate_episode)
from .singapore_scenario import (SINGAPORE_EPISODE_SCHEMA_VERSION,
                                 SINGAPORE_SCENARIO_VERSION,
                                 MainIslandGeometry, SingaporeGenerationError,
                                 SingaporeScenarioConfig,
                                 SingaporeScenarioGenerator,
                                 canonical_episode_hash, episode_to_dict,
                                 load_main_island)
from .singapore_provider import (CONSEQUENCE_CATALOG_VERSION,
                                 SINGAPORE_PROVIDER_VERSION,
                                 CandidateAssessment, ConsequenceCatalog,
                                 SingaporeConsequenceProvider,
                                 build_consequence_catalog)
from .suites import (HELD_OUT_TEST_SEEDS, ORACLE_MAX_ACTION_SEQUENCES,
                     ORACLE_SEEDS, SMOKE_TRAINING_STEPS, STRESS_SEEDS,
                     SUITES, SUITE_MANIFEST_VERSION, VALIDATION_SEEDS,
                     SuiteDefinition, build_suite_manifest)
from .factories import (GENERATOR_CHOICES, PROVIDER_CHOICES,
                        runtime_factories)

__all__ = [
    'SIMULATOR_VERSION', 'EPISODE_SCHEMA_VERSIONS', 'MAX_THREATS', 'MAX_INTERCEPTORS',
    'MAX_CANDIDATES_PER_PAIR', 'ScheduledThreat', 'InterceptorResource',
    'EpisodeSpec', 'AbsoluteCandidate', 'Assignment', 'AssignmentStatus',
    'ThreatStatus', 'ResolutionKind', 'EventKind', 'EventRecord',
    'ConsequenceProvider', 'ProviderEvaluation', 'ObjectiveDirection',
    'DeterministicToyProvider', 'provider_identity', 'SimulationEngine',
    'SCENARIO_GENERATOR_VERSION', 'SeededScenarioGenerator', 'generate_episode',
    'SINGAPORE_SCENARIO_VERSION', 'SINGAPORE_EPISODE_SCHEMA_VERSION',
    'SingaporeScenarioConfig', 'SingaporeScenarioGenerator',
    'SingaporeGenerationError', 'MainIslandGeometry', 'load_main_island',
    'episode_to_dict', 'canonical_episode_hash',
    'SINGAPORE_PROVIDER_VERSION', 'CONSEQUENCE_CATALOG_VERSION',
    'CandidateAssessment', 'ConsequenceCatalog', 'SingaporeConsequenceProvider',
    'build_consequence_catalog',
    'BaselineRun', 'ImmediateInterceptionPolicy', 'ROLLOUT_SCHEMA_VERSION',
    'RolloutRecord', 'JsonlRolloutRecorder', 'observation_reference',
    'replay_rollout',
    'SMOKE_TRAINING_STEPS', 'VALIDATION_SEEDS', 'HELD_OUT_TEST_SEEDS',
    'STRESS_SEEDS', 'ORACLE_SEEDS', 'ORACLE_MAX_ACTION_SEQUENCES',
    'SuiteDefinition', 'SUITES',
    'SUITE_MANIFEST_VERSION', 'build_suite_manifest',
    'PROVIDER_CHOICES', 'GENERATOR_CHOICES', 'runtime_factories',
]
