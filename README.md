# docx-corpus-kit

> White-label toolkit for taming large `.docx` collections: **convert** docx → markdown, keep a **1:1 docx↔md correspondence**, and build a **Chinese-friendly full-text index** for batch retrieval.

Nothing business-specific is baked in. Classification is folder-based by default and fully overridable with a rules file. Point it at any local folder or an external drive.

## Install

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -e ".[test]"      # or: pip install docx-corpus-kit
```

## Commands

All commands take a path argument — there are **no hardcoded paths**.

### 1. `inventory` — scan, dedup, version clusters, md pairing

```bash
docx-corpus inventory /path/to/docs --pair-dir /path/to/docs/md --csv inv.csv --json inv.json
```

- sha256 fingerprint per file → **exact-duplicate clusters**
- groups same-base files ignoring `(n)` copy suffixes → **version clusters**
- pairs each docx with a same-base `.md` found under `--pair-dir`

### 2. `index` — full-text search (Chinese-substring aware)

```bash
docx-corpus index /path/to/docs --db corpus.db
docx-corpus index /path/to/docs --db corpus.db --query 意象
```

- SQLite FTS5 **trigram** (≥3 chars) + **LIKE** fallback (any length, incl. 2-char Chinese)
- **incremental**: only re-extract files whose sha256/mtime changed

### 3. `sync` — 1:1 docx↔md with drift detection

```bash
docx-corpus sync /path/to/src /path/to/md --check   # preview, writes nothing
docx-corpus sync /path/to/src /path/to/md --make    # generate / refresh md
```

- `MISSING` md is created, `STALE` (docx newer than md) is refreshed, `OK` is left alone

### 4. `convert` — single file

```bash
docx-corpus convert file.docx --out file.md
```

## Why it is robust for large sets

- **Chinese search** — FTS5's default tokenizer does not split CJK, so we combine trigram (≥3 chars) with a `LIKE` fallback. Verified: `意象`, `风筝`, `诗话`, `古代诗歌意象` all resolve correctly.
- **Large-file guard** — `markitdown` can hang on very large docx; files > 800 KB go straight to the fast `python-docx` plain-text extractor.
- **Timeout guard** — `markitdown` runs in a thread with a 60 s cap; on timeout we fall back to plain text instead of blocking the batch.

## Customizing categories (white-label)

By default a file's category is its top-level folder. Override with a rules JSON
(list of `[pattern, category]`); first match wins:

```bash
docx-corpus inventory /path/to/docs --rules examples/classify_rules.json
```

Patterns use `fnmatch` (matched against the relative path and the filename).
See `examples/classify_rules.json`.

## License

MIT — see `LICENSE`.
