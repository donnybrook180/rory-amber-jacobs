#!/usr/bin/env python3
"""
Split example sentences out of words.<code>.json into per-pack shards so the
words file stays small enough for the GitHub Pages deploy.

Layout:
    <code>/words.<code>.json          senses, NO examples (stays ~7M)
    examples/<code>/<packId>.json     { "<wordKey>": [exampleOrNull, ...] }
                                      list aligned to the word's senses

The manifest gains examplePacks (sorted pack ids that have a shard) + exampleCount
so the app knows which packs to lazy-fetch. Idempotent.

Usage: python tools/shard_examples.py <code>
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: shard_examples.py <code>")
    code = sys.argv[1]
    matches = list(ROOT.glob(f"*/words.{code}.json"))
    if not matches:
        sys.exit(f"no words.{code}.json")
    wpath = matches[0]
    words = json.loads(wpath.read_text(encoding="utf-8"))

    # Collect examples per pack, aligned to sense order, and strip them out.
    by_pack = defaultdict(dict)  # packId -> {key: [ex|null, ...]}
    total = 0
    for w in words:
        senses = w.get("senses")
        if not senses:
            continue
        aligned = []
        any_ex = False
        for s in senses:
            exs = s.get("examples")
            if exs:
                aligned.append(exs[0])   # one example per sense
                any_ex = True
                total += 1
                s.pop("examples", None)  # strip from words file
            else:
                aligned.append(None)
        if any_ex:
            by_pack[w["pack"]["id"]][w["key"]] = aligned

    ex_root = ROOT / "examples" / code
    ex_root.mkdir(parents=True, exist_ok=True)

    for pid, shard in by_pack.items():
        (ex_root / f"{pid}.json").write_text(
            json.dumps(shard, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")

    wpath.write_text(
        json.dumps(words, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")

    mpath = wpath.parent / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["exampleShards"] = True
    manifest["examplePacks"] = sorted(by_pack)
    manifest["exampleCount"] = total
    manifest["version"] = int(manifest.get("version", 0)) + 1
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                     encoding="utf-8")

    biggest = max((len((ex_root / f"{p}.json").read_bytes())
                   for p in by_pack), default=0)
    print(f"{code}: {total} examples -> {len(by_pack)} pack shards under "
          f"{ex_root.relative_to(ROOT)} (largest {biggest//1024}KB)")
    print(f"words.{code}.json stripped; manifest v{manifest['version']}")


if __name__ == "__main__":
    main()
