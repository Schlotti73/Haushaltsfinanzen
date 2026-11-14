"""Gemeinsamer Import-Hash-Dienst (vorher in import_excel.py inline)."""

from __future__ import annotations

import hashlib


def make_hash(*parts) -> str:
    """SHA-256 über beliebige Felder, gibt erste 16 Hex-Zeichen zurück."""
    raw = "|".join(str(p) if p is not None else "" for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
