"""Common inference contract for PPO and structured imitation policies."""
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Policy(Protocol):
    """Observation-only policy contract used by evaluation and deployment."""

    model_version: str

    def predict(self, observation: Any, deterministic: bool = True,
                action_masks: Any = None) -> Any:
        ...

    def close(self) -> None:
        ...
