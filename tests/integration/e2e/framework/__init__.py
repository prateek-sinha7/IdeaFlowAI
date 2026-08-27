"""Shared machinery for the integration suite.

Nothing here knows about a specific screen. Anything screen-specific belongs
beside the tests that use it, in `suites/<area>/`.
"""

from framework.shot import Shooter, slugify

__all__ = ["Shooter", "slugify"]
