"""Backward-compatible pipeline name for the transport configuration."""

from .transport import Transport


class Pipeline(Transport):
    """Compatibility wrapper retained for older imports."""

    def calculate_pressure_drop(self, m_dot=None, length=None, diameter=None):
        """Forward to the still-unapproved horizontal pressure-drop API."""
        return self.calculate_pipeline_pressure_drop()
