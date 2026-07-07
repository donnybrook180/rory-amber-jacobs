#!/usr/bin/env python3
"""
Merge example-sentence agent output straight into the per-pack example shards
(`examples/<code>/<packId>.json`), P2.

Examples live in shards (not inline in the words file) to keep that file under
the GitHub Pages deploy ceiling, so this enricher writes shards directly — the
big words file is never touched or re-deployed. A shard maps a word key to a
list of `example|null` aligned to that word's senses (entry i -> senses[i]).

Incremental and safe: only words the run produced examples for are touched, and
within a word a sense keeps any example it already had if the run didn't cover
it. Recomputes the manifest exampleCount / examplePacks from the shards on disk
and bumps the version.

Usage:
    python tools/enrich_examples.py <code> <run_dir> [<run_dir> ...] [--check]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "tools"))
from gen_lang_content import _collect_examples, _norm  # noqa: E402

NATIVE_POOL = ['ar', 'de', 'en', 'es', 'fr', 'hi', 'id', 'it', 'ja', 'ko',
               'nl', 'pt', 'ru', 'sw', 'th', 'ur', 'vi', 'zh']


def native_langs(code):
    return [l for l in NATIVE_POOL if l != code]


def _load_shard(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


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

    # Space-delimited script? (unspaced: zh/ja/th use a character floor.)
    spaced = code not in {'zh', 'ja', 'th'}
    ex_by = _collect_examples(args.run_dirs, langs, spaced=spaced)
    print(f"parsed examples for {len(ex_by)} distinct keys")

    ex_root = ROOT / "examples" / code
    ex_root.mkdir(parents=True, exist_ok=True)

    shards = {}          # packId -> {key: [ex|null, ...]}
    touched_packs = set()
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
        pid = w["pack"]["id"]
        if pid not in shards:
            shards[pid] = _load_shard(ex_root / f"{pid}.json")
        shard = shards[pid]
        aligned = list(shard.get(w["key"]) or [])
        if len(aligned) < len(senses):
            aligned += [None] * (len(senses) - len(aligned))
        touched = False
        # Align by order: sense i's example list -> aligned[i]; keep existing
        # where this run didn't cover the sense. `examples[i]` is now a *list* of
        # examples (multiple per sense).
        for i in range(len(senses)):
            if i < len(examples) and examples[i]:
                aligned[i] = examples[i]
                senses_filled += 1
                touched = True
        if touched:
            shard[w["key"]] = aligned
            touched_packs.add(pid)
            words_touched += 1

    print(f"words touched: {words_touched}; senses given an example: "
          f"{senses_filled}; packs touched: {len(touched_packs)}")
    if args.check:
        for pid in sorted(touched_packs):
            for k, al in shards[pid].items():
                entry = next((e for e in al if e), None)
                if entry:
                    ex = entry[0] if isinstance(entry, list) else entry
                    print(f"  e.g. pack {pid} {k}: {ex['text']}")
                    return
        return

    for pid in touched_packs:
        (ex_root / f"{pid}.json").write_text(
            json.dumps(shards[pid], ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")

    # Recompute totals from every shard on disk (this run + prior). An entry is a
    # list of examples (current) or a single example object (legacy).
    def _count(entry):
        if isinstance(entry, list):
            return len(entry)
        return 1 if entry else 0

    all_packs = sorted(int(p.stem) for p in ex_root.glob("*.json"))
    total = 0
    for p in all_packs:
        shard = _load_shard(ex_root / f"{p}.json")
        total += sum(_count(e) for al in shard.values() for e in al)

    mpath = wpath.parent / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["exampleShards"] = True
    manifest["examplePacks"] = all_packs
    manifest["exampleCount"] = total
    manifest["version"] = int(manifest.get("version", 0)) + 1
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(f"wrote {len(touched_packs)} shard(s) under {ex_root.relative_to(ROOT)}; "
          f"{mpath.name} -> version {manifest['version']}, "
          f"exampleCount {total}, examplePacks {len(all_packs)}")


if __name__ == "__main__":
    main()
