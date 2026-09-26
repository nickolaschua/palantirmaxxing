"""Seeded synthetic episode generation for simulator plumbing validation."""
import math
import random
from typing import Optional

from backend.domain import InterceptorState, ThreatState

from .models import (MAX_INTERCEPTORS, MAX_THREATS, EpisodeSpec,
                     InterceptorResource, ScheduledThreat)


SCENARIO_GENERATOR_VERSION = 'seeded-synthetic-scenarios/1'


class SeededScenarioGenerator:
    """Produces deterministic continuous, simultaneous and scarce episodes.

    Values are intentionally synthetic. They validate scheduling and learning
    plumbing and are not representative operational performance parameters.
    """

    version = SCENARIO_GENERATOR_VERSION

    def __init__(self, candidate_count: int = 20,
                 max_threats: int = MAX_THREATS,
                 max_interceptors: int = MAX_INTERCEPTORS):
        if type(candidate_count) is not int or not 1 <= candidate_count <= 20:
            raise ValueError('candidate_count must be between 1 and 20')
        if type(max_threats) is not int or not 1 <= max_threats <= MAX_THREATS:
            raise ValueError('max_threats must be between 1 and 8')
        if type(max_interceptors) is not int or not 1 <= max_interceptors <= MAX_INTERCEPTORS:
            raise ValueError('max_interceptors must be between 1 and 8')
        self.candidate_count = candidate_count
        self.max_threats = max_threats
        self.max_interceptors = max_interceptors

    def generate(self, seed: int, threat_count: Optional[int] = None,
                 interceptor_count: Optional[int] = None,
                 full_capacity: bool = False) -> EpisodeSpec:
        if type(seed) is not int:
            raise ValueError('seed must be an integer')
        rng = random.Random(seed)
        if full_capacity:
            threat_count = self.max_threats
            interceptor_count = self.max_interceptors
        if threat_count is None:
            threat_count = rng.randint(2, self.max_threats)
        if interceptor_count is None:
            # Deliberately includes scarce episodes as well as balanced ones.
            interceptor_count = rng.randint(1, min(self.max_interceptors, threat_count + 1))
        if type(threat_count) is not int or not 1 <= threat_count <= self.max_threats:
            raise ValueError('threat_count is outside generator capacity')
        if (type(interceptor_count) is not int
                or not 1 <= interceptor_count <= self.max_interceptors):
            raise ValueError('interceptor_count is outside generator capacity')

        interceptors = []
        for index in range(interceptor_count):
            angle = (math.tau * index / max(1, interceptor_count)) + rng.uniform(-0.08, 0.08)
            radius = rng.uniform(0.0, 90.0)
            interceptors.append(InterceptorResource(
                state=InterceptorState(
                    interceptor_id='interceptor-%02d' % (index + 1),
                    position_x_m=math.cos(angle) * radius,
                    position_y_m=math.sin(angle) * radius,
                    heading_rad=angle,
                    speed_mps=rng.uniform(95.0, 145.0),
                    max_turn_rate_rad_s=math.radians(rng.uniform(12.0, 22.0)),
                ),
                metadata={'synthetic': True},
            ))

        threats = []
        detection_time = 0.0
        previous_detection = 0.0
        for index in range(threat_count):
            if index == 0:
                detection_time = 0.0
            elif rng.random() < 0.30:
                # A stable exact timestamp creates simultaneous detections.
                detection_time = previous_detection
            else:
                detection_time = previous_detection + rng.uniform(0.75, 7.0)
            previous_detection = detection_time
            approach_angle = rng.uniform(0.0, math.tau)
            distance = rng.uniform(420.0, 1050.0)
            speed = rng.uniform(6.0, 20.0)
            threats.append(ScheduledThreat(
                detection_time_s=round(detection_time, 6),
                state=ThreatState(
                    threat_id='threat-%02d' % (index + 1),
                    position_x_m=math.cos(approach_angle) * distance,
                    position_y_m=math.sin(approach_angle) * distance,
                    velocity_x_mps=-math.cos(approach_angle) * speed,
                    velocity_y_mps=-math.sin(approach_angle) * speed,
                    maximum_time_to_go_s=rng.uniform(22.0, 48.0),
                ),
                metadata={
                    'priority': round(rng.uniform(0.5, 2.0), 6),
                    'preferred_candidate_fraction': round(rng.uniform(0.15, 0.9), 6),
                    'synthetic': True,
                },
            ))
        return EpisodeSpec(
            episode_id='synthetic-%010d' % seed,
            seed=seed,
            threats=tuple(threats),
            interceptors=tuple(interceptors),
            candidate_count=self.candidate_count,
            metadata={
                'generator': self.version,
                'label': 'plumbing validation only',
            },
        )


def generate_episode(seed: int, **kwargs) -> EpisodeSpec:
    """Convenience interface using the default fixed-capacity generator."""
    return SeededScenarioGenerator().generate(seed, **kwargs)
