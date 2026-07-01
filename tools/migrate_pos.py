#!/usr/bin/env python3
"""
One-time (idempotent) migration: normalize the free-text `pos` in every shipped
words.*.json to a canonical tag + `gender`, and bump each manifest version so
clients re-fetch.

Only the `pos` and `gender` fields are touched — translations, audio, examples,
readings and everything else are preserved byte-for-byte (protects hand-enriched
en/de content). Safe to re-run: already-canonical data produces no diff and the
version is only bumped when a file actually changes.

Usage:
    python tools/migrate_pos.py            # rewrite in place
    python tools/migrate_pos.py --check    # report only, exit 1 if changes needed
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

from pos_normalize import normalize

ROOT = Path(__file__).resolve().parent.parent


def migrate_words(path: Path):
    words = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for w in words:
        tag, gender = normalize(w.get("pos"))
        # Gender is additive and idempotent: once a run has lifted "noun-f" into
        # pos="noun" + gender="f", a later pass sees bare "noun" (gender=None) and
        # must NOT strip the field it already set. Only write gender when the raw
        # pos actually carries one.
        pos_changed = w.get("pos") != tag
        gender_changed = gender is not None and w.get("gender") != gender
        if pos_changed or gender_changed:
            changed += 1
        w["pos"] = tag
        if gender is not None:
            w["gender"] = gender
    return words, changed


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
                    help="report only; exit 1 if any file needs migration")
    args = ap.parse_args()

    total_changed = 0
    for wf in sorted(glob.glob(str(ROOT / "*" / "words.*.json"))):
        wpath = Path(wf)
        words, changed = migrate_words(wpath)
        if not changed:
            print(f"  {wpath.parent.name}/{wpath.name}: already canonical")
            continue
        total_changed += 1
        print(f"  {wpath.parent.name}/{wpath.name}: {changed} record(s) normalized")
        if args.check:
            continue
        wpath.write_text(
            json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
        bumped = bump_manifest(wpath.parent)
        if bumped:
            mpath, manifest = bumped
            mpath.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8")
            print(f"    -> {wpath.parent.name}/manifest.json version "
                  f"{manifest['version']}")

    if args.check and total_changed:
        raise SystemExit(f"{total_changed} file(s) need migration.")
    print(f"\nDone. {total_changed} file(s) "
          f"{'need migration' if args.check else 'were migrated'}.")


if __name__ == "__main__":
    main()
