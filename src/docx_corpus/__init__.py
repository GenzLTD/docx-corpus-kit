"""docx-corpus-kit: white-label toolkit for docx collections.

Capabilities:
  - convert  : docx -> markdown (markitdown, with a fast plain-text fallback)
  - pair     : 1:1 docx<->md correspondence + drift detection (sync)
  - index    : SQLite FTS5 full-text index, Chinese-substring friendly, incremental
  - inventory: scan + sha256 dedup + name-version clusters + optional md pairing

No project-specific assumptions are baked in; classification is folder-based by
default and fully overridable with a rules file (see examples/classify_rules.json).
"""
__version__ = "0.1.0"
