#!/usr/bin/env python3
"""
Merge sense-translation agent output into an existing words.<code>.json.

Unlike the full assemble (which rebuilds the list from the pool), this ENRICHES
in place: only words the run produced senses for are updated (senses + a refreshed
flat translations view); every other word is left exactly as-is. Safe for partial
or incremental runs — a failed chunk never wipes existing translations.

Existing per-language translations are preserved for any language a new sense
doesn't cover, so coverage never regresses.

Usage:
    python tools/enrich_senses.py <code> <run_dir> [<run_dir> ...] [--check]
    e.g. python tools/enrich_senses.py es /path/to/workflow/transcripts
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Reuse the tested parsers from the generator (main repo tools).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "tools"))
from gen_lang_content import (  # noqa: E402
    NATIVE_POOL, _collect_senses, _merge_glosses, _norm, native_langs,
)

# NATIVE_POOL / native_langs come from gen_lang_content — the same list the
# emit side prompts with. This file used to keep its own copy, which silently
# fell behind at 18 languages: the generated senses carried all 22 glosses but
# the flat `translations` view rebuilt here dropped tr/pl/el/bn/uk, leaving the
# manifest unable to offer them.
assert len(NATIVE_POOL) >= 18, NATIVE_POOL


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("run_dirs", nargs="+")
    ap.add_argument("--check", action="store_true",
                    help="report only, don't write")
    args = ap.parse_args()
    code = args.code
    langs = native_langs(code)

    # locate the words file
    matches = list(ROOT.glob(f"*/words.{code}.json"))
    if not matches:
        sys.exit(f"no words.{code}.json found")
    wpath = matches[0]
    words = json.loads(wpath.read_text(encoding="utf-8"))

    senses_by, reading_by = _collect_senses(args.run_dirs, langs)
    print(f"parsed senses for {len(senses_by)} distinct keys "
          f"from {len(args.run_dirs)} run dir(s)")

    enriched = 0
    for w in words:
        key = w["target"].strip().lower()
        senses = senses_by.get(key) or senses_by.get(_norm(w["target"]))
        if not senses:
            continue
        merged = _merge_glosses(senses, langs)
        # Never regress coverage: keep existing translations for langs the new
        # senses don't cover.
        translations = dict(w.get("translations") or {})
        translations.update(merged)
        w["senses"] = senses
        w["translations"] = translations
        enriched += 1

    print(f"enriched {enriched}/{len(words)} words with senses")
    if args.check:
        # show a couple of samples
        for w in words:
            if w.get("senses") and len(w["senses"]) > 1:
                print(f"  e.g. {w['target']}: "
                      f"{[s['gloss'].get('en') for s in w['senses']]}")
                break
        return

    # Compact: sense data triples file size; indent-2 pushed es past the Pages
    # deploy ceiling. Manifests/index stay pretty (tiny, diff-friendly).
    wpath.write_text(
        json.dumps(words, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    mpath = wpath.parent / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["version"] = int(manifest.get("version", 0)) + 1
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(f"wrote {wpath.name}; {mpath.name} -> version {manifest['version']}")


if __name__ == "__main__":
    main()
