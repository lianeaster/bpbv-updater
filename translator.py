"""Translate Ukrainian text to EN / DE / FR via Google Translate (free)."""

from __future__ import annotations

from deep_translator import GoogleTranslator

LANGUAGES = ("en", "de", "fr")


def translate(text: str, dest: str) -> str:
    """Translate Ukrainian *text* to *dest* language. Returns original on failure."""
    if not text.strip():
        return text
    try:
        return GoogleTranslator(source="uk", target=dest).translate(text)
    except Exception:
        return text
