"""Shared validation patterns for API schemas."""

import re

NATIONAL_ID_RE = re.compile(r"^[0-9]{10}$")
YEAR_RE = re.compile(r"^[0-9]{4}$")
PHONE_RE = re.compile(r"^[0-9]+$")
