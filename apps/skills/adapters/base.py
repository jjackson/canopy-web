from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    """Abstract base class for runtime adapters."""

    @abstractmethod
    def generate(self, skill_definition: dict) -> dict:
        """Generate a runtime-specific representation of a skill definition."""
        ...
