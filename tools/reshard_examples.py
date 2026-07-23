#!/usr/bin/env python3
"""
Re-distribute existing example shards onto the CURRENT pack layout.

A regeneration re-ranks the word list (freq_rank), which changes every word's
pack id. Example shards are keyed `examples/<code>/<packId>.json -> {wordKey: [...]}`,
so after a re-rank a surviving word's examples still sit in its OLD pack's shard
and the app (which fetches by current pack) can't find them. This reads all old
shards by the stable word key, rebuilds the shards under each word's current pack,
drops examples for words no longer in the list, and refreshes the manifest.

It moves data only — it never generates. Words with no prior example (e.g. the
freshly added ones) are simply absent and picked up by the examples workflow.

Usage: python tools/reshard_examples.py <code>
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: reshard_examples.py <code>")
    code = sys.argv[1]
    matches = list(ROOT.glob(f"*/words.{code}.json"))
    if not matches:
        sys.exit(f"no words.{code}.json")
    wpath = matches[0]
    words = json.loads(wpath.read_text(encoding="utf-8"))
    ex_root = ROOT / "examples" / code

    # 1. Gather every existing example, keyed by the stable word key.
    old_by_key = {}
    for shard in sorted(ex_root.glob("*.json")):
        for key, aligned in json.loads(shard.read_text(encoding="utf-8")).items():
            old_by_key[key] = aligned

    # 2. Rebuild shards under each surviving word's CURRENT pack. A word absent
    #    from `words` (removed by the regen) is dropped by never being visited.
    by_pack = defaultdict(dict)
    total = 0
    carried = 0
    for w in words:
        aligned = old_by_key.get(w["key"])
        if not aligned:
            continue
        # Trim/pad the alignment to the word's current sense count so a word whose
        # senses were regenerated to a different count stays consistent.
        n = len(w.get("senses", []) or [])
        if n:
            aligned = (aligned + [None] * n)[:n]
        if any(aligned):
            by_pack[w["pack"]["id"]][w["key"]] = aligned
            carried += 1
            total += sum(1 for e in aligned if e)

    # 3. Overwrite the shard dir with the new layout.
    if ex_root.exists():
        for stale in ex_root.glob("*.json"):
            stale.unlink()
    ex_root.mkdir(parents=True, exist_ok=True)
    for pid, shard in by_pack.items():
        (ex_root / f"{pid}.json").write_text(
            json.dumps(shard, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")

    # 4. Refresh the manifest's example bookkeeping and bump the version.
    mpath = wpath.parent / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["exampleShards"] = True
    manifest["examplePacks"] = sorted(by_pack)
    manifest["exampleCount"] = total
    manifest["version"] = int(manifest.get("version", 0)) + 1
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                     encoding="utf-8")

    print(f"{code}: re-sharded {total} examples for {carried} words -> "
          f"{len(by_pack)} packs; manifest v{manifest['version']}")
    dropped = len(old_by_key) - carried
    if dropped:
        print(f"  dropped {dropped} word(s) no longer in the list")


if __name__ == "__main__":
    main()
