"""Compatibility shim for legacy PageIndex imports.

PageIndex still imports ``PyPDF2`` directly, while this project has moved to
``pypdf``. Re-export the pypdf API under the old module name so direct
``import pageindex`` entrypoints keep working without the deprecated package.
"""
from pypdf import *  # noqa: F401,F403
