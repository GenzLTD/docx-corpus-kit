"""Core operations for docx collections: scan, inventory, pair (1:1), index.

White-label by design: the only default assumption is that a file's *category*
is its top-level folder; everything can be overridden with a ``rules`` list of
(pattern, category) pairs (see examples/classify_rules.json).
"""
import os
import re
import csv
import json
import sqlite3
import fnmatch
import hashlib
from collections import defaultdict
from datetime import datetime

from . import extract


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mtime_str(path):
    return datetime.fromtimestamp(os.stat(path).st_mtime).strftime("%Y-%m-%d %H:%M")


_VER = re.compile(r"^(?P<base>.+?)(?:\s*\((\d+)\))?$")


def base_name(fname):
    """Strip extension and a trailing ' (n)' copy-number suffix."""
    stem = os.path.splitext(fname)[0]
    m = _VER.match(stem)
    return (m.group("base").strip() if m else stem.strip())


def classify(rel_path, rules=None):
    """Category for a file.

    rules: optional list of [pattern, category]; first match wins. Matching is
    tried against the relative path and against the bare filename.
    Default: the top-level folder name, or 'root' when at the top level.
    """
    if rules:
        name = os.path.basename(rel_path)
        for pattern, cat in rules:
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(name, pattern):
                return cat
    parts = re.split(r"[/\\]", rel_path)
    return parts[0] if len(parts) > 1 else "root"


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #
def scan_docx(root):
    rows = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if not fn.lower().endswith(".docx"):
                continue
            full = os.path.join(dp, fn)
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, root)
            rows.append(
                {
                    "rel": rel,
                    "bucket": classify(rel),
                    "size": st.st_size,
                    "mtime": mtime_str(full),
                    "base": base_name(fn),
                    "path": full,
                    "sha": sha256_file(full),
                    "pair": "",
                }
            )
    return rows


# --------------------------------------------------------------------------- #
# inventory: dedup + version clusters + optional md pairing
# --------------------------------------------------------------------------- #
def inventory(root, pair_dir=None, rules=None, csv_path=None, json_path=None):
    rows = scan_docx(root)
    for r in rows:
        r["bucket"] = classify(r["rel"], rules)

    by_sha = defaultdict(list)
    for r in rows:
        by_sha[r["sha"]].append(r)
    for r in rows:
        r["dup"] = len(by_sha[r["sha"]])
        r["sha12"] = r["sha"][:12]

    # Pair every docx with a same-base .md found anywhere under pair_dir.
    if pair_dir:
        md = {}
        for dp, _, fns in os.walk(pair_dir):
            for fn in fns:
                if fn.lower().endswith(".md"):
                    md[os.path.splitext(fn)[0]] = os.path.join(dp, fn)
        for r in rows:
            r["pair"] = md.get(r["base"], "")

    rows.sort(key=lambda x: (x["bucket"], x["base"], x["rel"]))

    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["rel_path", "bucket", "size", "mtime", "sha12", "dup", "base", "pair"])
            for r in rows:
                w.writerow([r["rel"], r["bucket"], r["size"], r["mtime"],
                            r["sha12"], r["dup"], r["base"], r["pair"]])

    bucket_counts = defaultdict(int)
    for r in rows:
        bucket_counts[r["bucket"]] += 1
    dup_clusters = [
        {"sha12": s[:12], "count": len(g), "files": sorted(x["rel"] for x in g)}
        for s, g in by_sha.items() if len(g) > 1
    ]
    dup_clusters.sort(key=lambda c: -c["count"])
    base_groups = defaultdict(list)
    for r in rows:
        base_groups[r["base"]].append(r["rel"])
    version_clusters = {b: v for b, v in base_groups.items() if len(v) > 1}
    version_clusters = dict(sorted(version_clusters.items(), key=lambda kv: -len(kv[1])))

    summary = {
        "root": os.path.abspath(root),
        "total_docx": len(rows),
        "bucket_counts": dict(bucket_counts),
        "exact_dup_clusters": len(dup_clusters),
        "exact_dup_extra": sum(c["count"] - 1 for c in dup_clusters),
        "version_clusters": len(version_clusters),
    }
    if pair_dir:
        paired = [r for r in rows if r["pair"]]
        summary["pairs"] = "%d/%d" % (len(paired), len(rows))
        summary["missing_md"] = [r["rel"] for r in rows if not r["pair"]]

    if json_path:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(
                {"summary": summary, "dup_clusters": dup_clusters,
                 "version_clusters": version_clusters},
                f, ensure_ascii=False, indent=2,
            )
    return summary


# --------------------------------------------------------------------------- #
# sync: 1:1 docx <-> md correspondence + drift detection
# --------------------------------------------------------------------------- #
def sync(src_dir, md_dir, make=False, force=False, rules=None):
    src = os.path.abspath(src_dir)
    md_dir = os.path.abspath(md_dir)
    os.makedirs(md_dir, exist_ok=True)
    targets = []
    for dp, _, fns in os.walk(src):
        for fn in fns:
            if not fn.lower().endswith(".docx"):
                continue
            full = os.path.join(dp, fn)
            base = base_name(fn)
            out = os.path.join(md_dir, base + ".md")
            if not os.path.exists(out):
                status = "MISSING"
            elif os.stat(full).st_mtime > os.stat(out).st_mtime:
                status = "STALE"   # docx newer than md -> drift
            else:
                status = "OK"
            targets.append({"src": full, "base": base, "out": out, "status": status})
    targets.sort(key=lambda r: r["base"])

    do_make = make or force
    for r in targets:
        if do_make and (r["status"] in ("MISSING", "STALE") or force):
            text = extract.docx_text_best(r["src"])
            with open(r["out"], "w", encoding="utf-8") as f:
                f.write(text + "\n")
            r["flag"] = " -> generated/refreshed"
    return targets


# --------------------------------------------------------------------------- #
# index: SQLite FTS5 full-text, Chinese-substring friendly, incremental
# --------------------------------------------------------------------------- #
def _search(cur, q):
    hits = []
    # FTS5 trigram: efficient substring search for queries >= 3 characters.
    if len(q) >= 3:
        try:
            hits = cur.execute(
                "SELECT d.rel, d.title, f.rank FROM docs_fts f "
                "JOIN docs d ON d.id=f.rowid WHERE docs_fts MATCH ? "
                "ORDER BY f.rank LIMIT 50", (q,)
            ).fetchall()
        except Exception:  # pragma: no cover - defensive
            hits = []
    # LIKE fallback: guarantees correct substring search at any length
    # (including 2-character Chinese terms that trigram cannot index).
    like = cur.execute(
        "SELECT rel, title FROM docs WHERE content LIKE ? OR title LIKE ? LIMIT 50",
        ("%" + q + "%", "%" + q + "%"),
    ).fetchall()
    seen, merged = set(), []
    for r in hits + like:
        if r[0] not in seen:
            seen.add(r[0])
            merged.append(r)
    return merged[:50]


def index(root, db_path=None, query=None, rebuild=False, rules=None):
    root = os.path.abspath(root)
    dbp = db_path or os.path.join(root, "docx_index.db")
    conn = sqlite3.connect(dbp)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS docs(
            id INTEGER PRIMARY KEY, path TEXT UNIQUE,
            rel TEXT, bucket TEXT, sha TEXT, mtime TEXT, title TEXT, content TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
            title, content, path, content_rowid=id, tokenize='trigram');
        """
    )
    if rebuild:
        cur.execute("DELETE FROM docs;")
        cur.execute("INSERT INTO docs_fts(docs_fts) VALUES('rebuild');")

    seen, n_new, n_upd = set(), 0, 0
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if not fn.lower().endswith(".docx"):
                continue
            full = os.path.join(dp, fn)
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, root)
            sha = sha256_file(full)
            mts = mtime_str(full)
            seen.add(rel)
            row = cur.execute("SELECT id, sha, mtime FROM docs WHERE rel=?", (rel,)).fetchone()
            if row and row[1] == sha and row[2] == mts:
                continue  # unchanged -> skip (incremental)
            content = extract.docx_text_plain(full)
            title = base_name(fn)
            cat = classify(rel, rules)
            if row:
                cur.execute(
                    "UPDATE docs SET path=?, bucket=?, sha=?, mtime=?, title=?, content=? WHERE id=?",
                    (full, cat, sha, mts, title, content, row[0]),
                )
                n_upd += 1
            else:
                cur.execute(
                    "INSERT INTO docs(path, rel, bucket, sha, mtime, title, content) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (full, rel, cat, sha, mts, title, content),
                )
                n_new += 1
    n_del = 0
    for (rel,) in cur.execute("SELECT rel FROM docs").fetchall():
        if rel not in seen:
            cur.execute("DELETE FROM docs WHERE rel=?", (rel,))
            n_del += 1
    cur.execute("INSERT INTO docs_fts(docs_fts) VALUES('rebuild');")
    conn.commit()
    total = cur.execute("SELECT COUNT(*) FROM docs").fetchone()[0]

    result = {"db": dbp, "new": n_new, "updated": n_upd, "deleted": n_del, "total": total}
    if query:
        result["query"] = query
        result["hits"] = _search(cur, query)
    conn.close()
    return result
