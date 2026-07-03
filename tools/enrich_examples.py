#!/usr/bin/env python3
"""
Merge example-sentence agent output into an existing words.<code>.json (P2).

Each word's generated examples are aligned by order to its senses: examples[i]
attaches to senses[i].examples. Incremental and safe — only words the run
produced examples for are touched; a sense keeps any example it already had if
the run didn't cover it. Bumps the manifest exampleCount + version.

Usage:
    python tools/enrich_examples.py <code> <run_dir> [<run_dir> ...] [--check]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "tools"))
from gen_lang_content import _collect_examples, _norm  # noqa: E402

NATIVE_POOL = ['ar', 'de', 'en', 'es', 'fr', 'hi', 'id', 'it', 'ja', 'ko',
               'nl', 'pt', 'ru', 'sw', 'th', 'ur', 'vi', 'zh']


def native_langs(code):
    return [l for l in NATIVE_POOL if l != code]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("run_dirs", nargs="+")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    code = args.code
    langs = native_langs(code)

    matches = list(ROOT.glob(f"*/words.{code}.json"))
    if not matches:
        sys.exit(f"no words.{code}.json found")
    wpath = matches[0]
    words = json.loads(wpath.read_text(encoding="utf-8"))

    ex_by = _collect_examples(args.run_dirs, langs)
    print(f"parsed examples for {len(ex_by)} distinct keys")

    words_touched = 0
    senses_filled = 0
    for w in words:
        senses = w.get("senses")
        if not senses:
            continue
        key = w["target"].strip().lower()
        examples = ex_by.get(key) or ex_by.get(_norm(w["target"]))
        if not examples:
            continue
        touched = False
        # Align by order: example i -> sense i.
        for i, sense in enumerate(senses):
            if i < len(examples):
                sense["examples"] = [examples[i]]
                senses_filled += 1
                touched = True
        if touched:
            words_touched += 1

    total_examples = sum(len(s.get("examples", []))
                         for w in words for s in w.get("senses", []))
    print(f"words touched: {words_touched}; senses given an example: "
          f"{senses_filled}; total examples now: {total_examples}")
    if args.check:
        for w in words:
            for s in w.get("senses", []):
                if s.get("examples"):
                    print(f"  e.g. {w['target']}: {s['examples'][0]['text']}")
                    return
        return

    wpath.write_text(
        json.dumps(words, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    mpath = wpath.parent / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["exampleCount"] = total_examples
    manifest["version"] = int(manifest.get("version", 0)) + 1
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(f"wrote {wpath.name}; {mpath.name} -> version {manifest['version']}, "
          f"exampleCount {total_examples}")


if __name__ == "__main__":
    main()
