"""Plugin base class for all Integration Hub service panels."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ServicePlugin(ABC):
    """Describes one service tab in the tester GUI.

    Subclasses override `run()` with the service-specific logic.
    The GUI is entirely generic — it knows nothing about HL7, FHIR or MLLP.
    """

    tab_label: str
    """Short name shown on the notebook tab."""

    description: str
    """One-line description shown at the top of the tab."""

    input_label: str
    """Label above the input text pane."""

    output_label: str
    """Label above the output text pane."""

    button_label: str
    """Action button text, e.g. 'Transform', 'Validate + ACK', 'Preview MLLP'."""

    samples: dict[str, str] = field(default_factory=dict)
    """Named sample inputs loaded by the toolbar buttons."""

    @abstractmethod
    def run(self, input_text: str) -> tuple[str, str]:
        """Execute the service logic against *input_text*.

        Returns:
            (output_text, status_summary) — both are display strings.
        Raises:
            ValueError: expected failure (bad input, routing error, validation error).
            Exception:  unexpected failure — shown as an error in the UI.
        """
