"""
Thin entrypoint + compatibility exports.

Refactor note:
- New composition root lives in app.py
- Legacy implementation is preserved in legacy_main.py for compatibility
"""

from app import ImpactRPA, main
from core.config_manager import ConfigManager
from core.template_manager import TemplateManager
from core.settings_service import SettingsService
from infra.browser_manager import BrowserManager
from domain.date_picker import DatePicker, DatePickerResult
from domain.proposal_sender import ProposalSender, SendProposalsResult
from ui.menu_ui import MenuUI

__all__ = [
    "main",
    "ImpactRPA",
    "ConfigManager",
    "TemplateManager",
    "SettingsService",
    "BrowserManager",
    "DatePicker",
    "DatePickerResult",
    "ProposalSender",
    "SendProposalsResult",
    "MenuUI",
]


if __name__ == "__main__":
    main()

