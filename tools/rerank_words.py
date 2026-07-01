#!/usr/bin/env python3
"""
Re-rank every shipped words.*.json by real corpus frequency (freq_rank) and
assign stable, rank-independent keys.

Reorders words, reassigns rank/key/level/pack, and freezes the generator's
original order into `srcRank`. Every other field — target, pos, gender,
translations, audio, examples, reading — is preserved. Each changed manifest
gets a version bump so clients re-fetch. Idempotent: a second run is a no-op.

Languages with no wordfreq corpus (th, sw) are left in their current order
(keys still assigned). Junk (zero-frequency words in well-covered languages)
is not removed — it sinks to the tail; the report prints how much.

Usage:
    python tools/rerank_words.py            # rewrite in place
    python tools/rerank_words.py --check    # report only, exit 1 if changes needed
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

from freq_rank import rank_words, tier
from wordfreq import zipf_frequency

ROOT = Path(__file__).resolve().parent.parent


def _code_of(words_path: Path) -> str:
    # words.<code>.json
    return words_path.name.split(".")[1]


def process(words_path: Path):
    code = _code_of(words_path)
    words = json.loads(words_path.read_text(encoding="utf-8"))
    before = [w["target"] for w in words]

    ranked = rank_words([dict(w) for w in words], code)  # copy: keep `words`

    after = [w["target"] for w in ranked]
    moved = sum(1 for a, b in zip(before, after) if a != b)
    # Changed if ANYTHING we manage differs — order, keys (hash migration),
    # rank/level/pack, or the new srcRank anchor. Order-stable languages like a
    # pre-sorted English still need the key + srcRank migration.
    changed = json.dumps(words, ensure_ascii=False, sort_keys=True) != \
        json.dumps(ranked, ensure_ascii=False, sort_keys=True)
    t = tier(code)
    junk = (sum(1 for w in ranked if zipf_frequency(w["target"], code) == 0)
            if t != "none" else 0)
    return code, ranked, changed, moved, t, junk, before[:8], after[:8]


def bump_manifest(lang_dir: Path):
    mpath = lang_dir / "manifest.json"
    if not mpath.exists():
        return None
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["version"] = int(manifest.get("version", 0)) + 1
    return mpath, manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report only; exit 1 if any file needs re-ranking")
    args = ap.parse_args()

    total_changed = 0
    for wf in sorted(glob.glob(str(ROOT / "*" / "words.*.json"))):
        wpath = Path(wf)
        code, ranked, changed, moved, t, junk, top_before, top_after = \
            process(wpath)
        name = wpath.parent.name

        if not changed:
            print(f"  {name} ({code}, {t}): already ranked")
            continue
        total_changed += 1
        print(f"  {name} ({code}, tier={t}): {moved} moved, "
              f"junk(zipf=0)={junk}")
        if moved:
            print(f"      top before: {top_before}")
            print(f"      top after : {top_after}")
        if args.check:
            continue

        wpath.write_text(
            json.dumps(ranked, ensure_ascii=False, indent=2), encoding="utf-8")
        bumped = bump_manifest(wpath.parent)
        if bumped:
            mpath, manifest = bumped
            mpath.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8")
            print(f"      -> {name}/manifest.json version {manifest['version']}")

    if args.check and total_changed:
        raise SystemExit(f"{total_changed} file(s) need re-ranking.")
    print(f"\nDone. {total_changed} file(s) "
          f"{'need re-ranking' if args.check else 'were re-ranked'}.")


if __name__ == "__main__":
    main()
