"""Helpers for declaring platform-specific pieces while building Qt UIs."""
from collections.abc import Callable
from PySide6.QtWidgets import QFormLayout, QLayout, QWidget
from platform_profile import Feature, PlatformProfile

class PlatformUi:
    """Add UI elements only when their required capability is available."""

    def __init__(self, profile: PlatformProfile):
        self.profile = profile

    def supported(self, feature: Feature | None) -> bool:
        return feature is None or self.profile.supports(feature)

    def add_row(self, form: QFormLayout, *items, requires: Feature | None = None) -> bool:
        """Add a form row when supported and report whether it was added."""
        if not self.supported(requires):
            return False

        form.addRow(*items)
        return True

    def add_widget(self, layout: QLayout, widget: QWidget, *args, requires: Feature | None = None) -> bool:
        """Adds an already created widget when supported."""
        if not self.supported(requires):
            return False

        layout.addWidget(widget, *args)
        return True

    def build_widget(self,layout: QLayout, factory: Callable[[], QWidget], *args, requires: Feature | None = None) -> QWidget | None:
        """Construct and add a widget only when its capability is supported."""
        if not self.supported(requires):
            return None

        widget = factory()
        layout.addWidget(widget, *args)
        return widget
