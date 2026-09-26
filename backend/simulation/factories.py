"""Named provider/generator factories shared by training and CLI entrypoints."""
from __future__ import annotations

from typing import Any, Callable, Tuple

from .provider import DeterministicToyProvider
from .scenarios import SeededScenarioGenerator
from .singapore_provider import (SingaporeConsequenceProvider,
                                 build_consequence_catalog)
from .singapore_scenario import SingaporeScenarioConfig, SingaporeScenarioGenerator


PROVIDER_CHOICES = ('toy', 'singapore-demo-v2')
GENERATOR_CHOICES = ('synthetic', 'singapore-v1')


def runtime_factories(
        provider_name: str = 'toy', generator_name: str = 'synthetic'
        ) -> Tuple[Callable[[], Any], Callable[[], Any]]:
    if provider_name not in PROVIDER_CHOICES:
        raise ValueError('unknown provider selection: ' + str(provider_name))
    if generator_name not in GENERATOR_CHOICES:
        raise ValueError('unknown generator selection: ' + str(generator_name))
    if generator_name == 'singapore-v1' and provider_name != 'singapore-demo-v2':
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
    else:
        # Generation itself must use consequence eligibility even if the caller
        # deliberately selects the toy training objective.
        singapore_catalog = catalog or build_consequence_catalog()
        generator_factory = lambda: SingaporeScenarioGenerator(
            config=config,
            consequence_provider=SingaporeConsequenceProvider(
                catalog=singapore_catalog, scenario_config=config))
    return provider_factory, generator_factory
