"""Command-line interface for docx-corpus-kit."""
import argparse
import json
import os
import sys

from . import core


def _load_rules(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)  # list of [pattern, category]


def _inventory(a):
    csv_path = a.csv or os.path.join(a.root, "docx_inventory.csv")
    json_path = a.json or os.path.join(a.root, "docx_inventory.json")
    s = core.inventory(a.root, pair_dir=a.pair_dir, rules=_load_rules(a.rules),
                       csv_path=csv_path, json_path=json_path)
    print("inventory -> %s" % csv_path)
    print("summary   -> %s" % json_path)
    print(json.dumps(s, ensure_ascii=False, indent=2))
    return 0


def _sync(a):
    targets = core.sync(a.src_dir, a.md_dir, make=a.make, force=a.force,
                        rules=_load_rules(a.rules))
    print("=== docx<->md 1:1 status (%d) ===" % len(targets))
    for r in targets:
        print("  [%-7s] %s%s" % (r["status"], r["base"], r.get("flag", "")))
    miss = sum(1 for r in targets if r["status"] == "MISSING")
    stale = sum(1 for r in targets if r["status"] == "STALE")
    ok = len(targets) - miss - stale
    print("\npairing: %d | MISSING %d | STALE(drift) %d | OK %d"
          % (len(targets), miss, stale, ok))
    if a.make:
        print("wrote md -> %s" % os.path.abspath(a.md_dir))
    else:
        print("(no files written; add --make to generate/refresh md)")
    return 0


def _convert(a):
    from . import extract
    text = extract.docx_text_best(a.one)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("convert -> %s (%d chars)" % (a.out, len(text)))
    else:
        print(text[:4000])
    return 0


def _index(a):
    r = core.index(a.root, db_path=a.db, query=a.query, rebuild=a.rebuild,
                   rules=_load_rules(a.rules))
    print("index -> %(db)s | new %(new)d updated %(updated)d deleted %(deleted)d total %(total)d"
          % r)
    if a.query:
        print('\n=== query "%s" : %d hits ===' % (a.query, len(r.get("hits", []))))
        for rel, title in r.get("hits", []):
            print("  - %s" % rel)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="docx collection toolkit: convert / 1:1 pair / full-text index (Chinese-friendly)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("inventory", help="scan + dedup + version clusters + md pairing")
    p.add_argument("root")
    p.add_argument("--csv")
    p.add_argument("--json")
    p.add_argument("--pair-dir", help="directory of .md to pair against docx")
    p.add_argument("--rules", help="JSON file: list of [pattern, category]")
    p.set_defaults(func=_inventory)

    p = sub.add_parser("sync", help="docx->md 1:1 correspondence + drift detection")
    p.add_argument("src_dir")
    p.add_argument("md_dir")
    p.add_argument("--make", action="store_true", help="generate/refresh missing or drifted md")
    p.add_argument("--force", action="store_true", help="force-refresh all md")
    p.add_argument("--rules")
    p.set_defaults(func=_sync)

    p = sub.add_parser("convert", help="convert a single .docx -> markdown")
    p.add_argument("one")
    p.add_argument("--out")
    p.set_defaults(func=_convert)

    p = sub.add_parser("index", help="build / query a full-text index")
    p.add_argument("root")
    p.add_argument("--db")
    p.add_argument("--query")
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--rules")
    p.set_defaults(func=_index)

    args = ap.parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
