"""Shipped conversion backends.

Importing this package registers every backend into the process-wide registry.
Keep imports here cheap-ish and side-effect-only.
"""

from convtui.backends import markitdown_backend  # noqa: F401

__all__ = ["markitdown_backend"]
