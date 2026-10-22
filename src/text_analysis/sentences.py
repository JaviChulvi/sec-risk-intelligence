"""Sentence segmentation backed by NLTK's Punkt model.

The Punkt model is downloaded once per machine (into NLTK's data directory,
``~/nltk_data`` by default) and loaded lazily on first use. It is *not* stored
in the repository: teammates get it automatically the first time they run code
that needs it, as long as ``nltk`` is installed (see the ``data-extraction``
optional dependency group in ``pyproject.toml``).

If NLTK or the Punkt model cannot be obtained (e.g. no network on first run),
segmentation degrades gracefully to a regex heuristic instead of raising, so
callers such as :attr:`ExtractedFilingSection.sentence_count` never break.
"""

from __future__ import annotations

import re
import threading

# Newer NLTK (>= 3.9) ships the Punkt tables as ``punkt_tab``; older releases
# use ``punkt``. We probe for both so the code works across versions.
_PUNKT_RESOURCES = ("tokenizers/punkt_tab", "tokenizers/punkt")
_PUNKT_PACKAGES = ("punkt_tab", "punkt")


class SentenceTokenizer:
    """Split text into sentences, preferring NLTK's Punkt over a regex fallback.

    A single instance caches whether Punkt is available so the (potentially
    slow) lookup/download happens at most once per process. It is safe to share
    one instance across threads.
    """

    # Sentence terminators (``.!?``) and newlines, collapsing runs so that
    # ``...``, ``.\n`` or blank lines do not yield empty sentences.
    _FALLBACK_SPLIT = re.compile(r"[.!?\n]+")

    def __init__(self) -> None:
        self._punkt_ready: bool | None = None  # None -> not yet attempted
        self._lock = threading.Lock()

    def split(self, text: str) -> list[str]:
        """Return the non-empty, stripped sentences found in ``text``."""
        if not text or not text.strip():
            return []
        if self._punkt_available():
            from nltk.tokenize import sent_tokenize

            sentences = sent_tokenize(text)
        else:
            sentences = self._FALLBACK_SPLIT.split(text)
        return [sentence.strip() for sentence in sentences if sentence.strip()]

    def count(self, text: str) -> int:
        """Return the number of sentences in ``text``."""
        return len(self.split(text))

    def _punkt_available(self) -> bool:
        if self._punkt_ready is not None:
            return self._punkt_ready
        with self._lock:
            if self._punkt_ready is None:
                self._punkt_ready = self._load_punkt()
        return self._punkt_ready

    def _load_punkt(self) -> bool:
        try:
            import nltk
        except ImportError:
            return False
        if self._resource_present(nltk):
            return True
        for package in _PUNKT_PACKAGES:
            try:
                if nltk.download(package, quiet=True):
                    return True
            except Exception:
                # Network errors, permission issues, etc. -> use the fallback.
                continue
        return self._resource_present(nltk)

    @staticmethod
    def _resource_present(nltk_module) -> bool:
        for resource in _PUNKT_RESOURCES:
            try:
                nltk_module.data.find(resource)
                return True
            except LookupError:
                continue
        return False


# Shared default instance so the Punkt setup is amortized across all callers.
_DEFAULT_TOKENIZER = SentenceTokenizer()


def split_sentences(text: str) -> list[str]:
    """Split ``text`` into sentences using the shared tokenizer."""
    return _DEFAULT_TOKENIZER.split(text)


def count_sentences(text: str) -> int:
    """Count the sentences in ``text`` using the shared tokenizer."""
    return _DEFAULT_TOKENIZER.count(text)
