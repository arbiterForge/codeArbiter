#!/usr/bin/env python3
"""Compatibility import for the canonical, shipped lifecycle validators."""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "core", "pysrc"))
import _adrlifecycle

# Preserve the existing module API, including private parser helpers used by CI.
sys.modules[__name__] = _adrlifecycle
