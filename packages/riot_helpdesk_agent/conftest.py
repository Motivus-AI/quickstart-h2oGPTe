"""Pytest-only: keep unit tests offline so they never call partners.h2o.ai."""

import os

os.environ["H2OGPTE_OFFLINE"] = "1"
