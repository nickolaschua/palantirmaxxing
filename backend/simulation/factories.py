"""Named provider/generator factories shared by training and CLI entrypoints."""
from __future__ import annotations

from typing import Any, Callable, Tuple

from .provider import DeterministicToyProvider
from .scenarios import SeededScenarioGenerator
from .singapore_provider import (SingaporeConsequenceProvider,
                                 build_consequence_catalog)
from .singapore_scenario import (SingaporeGenerationError, SingaporeScenarioConfig,
                                 SingaporeScenarioGenerator)
from .scenario_distribution import SingaporeScenarioV2Generator


PROVIDER_CHOICES = ('toy', 'singapore-demo-v2')
GENERATOR_CHOICES = ('synthetic', 'singapore-v1', 'singapore-v2')


class TrainingSingaporeV2Generator(SingaporeScenarioV2Generator):
    """Picklable deterministic training-mixture adapter with retry lanes."""

    def generate(self, seed: int, profile: str = None, **_ignored: Any):
        if profile is not None:
            return super().generate(seed, profile)
        profiles = ('warmup', 'balanced', 'full-standard', 'burst-contention',
                    'low-slack', 'consequence-contrast')
        profile = profiles[seed % len(profiles)]
        for retry in range(16):
            candidate_seed = seed + retry * 1_000_000_000
            try:
                return super().generate(candidate_seed, profile)
            except SingaporeGenerationError:
                if retry == 15:
                    raise


def runtime_factories(
        provider_name: str = 'toy', generator_name: str = 'synthetic'
        ) -> Tuple[Callable[[], Any], Callable[[], Any]]:
    if provider_name not in PROVIDER_CHOICES:
        raise ValueError('unknown provider selection: ' + str(provider_name))
    if generator_name not in GENERATOR_CHOICES:
        raise ValueError('unknown generator selection: ' + str(generator_name))
    if generator_name in ('singapore-v1', 'singapore-v2') \
            and provider_name != 'singapore-demo-v2':
        raise ValueError('Singapore generator and provider must share one scenario config')
    config = SingaporeScenarioConfig()
    if provider_name == 'toy':
        provider_factory = DeterministicToyProvider
        catalog = None
    else:
        catalog = build_consequence_catalog()
        provider_factory = lambda: SingaporeConsequenceProvider(
            catalog=catalog, scenario_config=config)
    if generator_name == 'synthetic':
        generator_factory = SeededScenarioGenerator
    elif generator_name == 'singapore-v1':
        # Generation itself must use consequence eligibility even if the caller
        # deliberately selects the toy training objective.
        singapore_catalog = catalog or build_consequence_catalog()
        generator_factory = lambda: SingaporeScenarioGenerator(
            config=config,
            consequence_provider=SingaporeConsequenceProvider(
                catalog=singapore_catalog, scenario_config=config))
    else:
        singapore_catalog = catalog or build_consequence_catalog()
        # Training samples the declared core mixture deterministically while the
        # public v2 generator itself keeps the strict generate(seed, profile) API.
        generator_factory = lambda: TrainingSingaporeV2Generator(
            config=config,
            consequence_provider=SingaporeConsequenceProvider(
                catalog=singapore_catalog, scenario_config=config))
    return provider_factory, generator_factory
