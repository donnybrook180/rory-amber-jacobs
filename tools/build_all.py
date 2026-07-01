#!/usr/bin/env python3
"""
Build every configured language from tools/languages.json, writing normalized JSON +
manifests directly into the CDN repo (rory-amber-jacobs/) and refreshing its index.json.

The CDN repo is served as-is by GitHub Pages from its root:

    rory-amber-jacobs/
    ├── index.json            # lists every published app/language
    ├── english/
    │   ├── manifest.json
    │   └── words.en.json
    └── <lang>/ ...

Usage:
    python tools/build_all.py            # build all languages + refresh index.json
    python tools/build_all.py --strict   # fail on any validation warning
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "tools" / "languages.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--index-only", action="store_true",
                    help="skip Excel re-import; rebuild index.json from the "
                         "manifests already committed on disk (deploy path)")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cdn_root = ROOT / cfg["cdnRoot"]
    cdn_root.mkdir(parents=True, exist_ok=True)

    index = {"apps": []}
    for lang in [] if args.index_only else cfg["languages"]:
        out = ROOT / lang["out"]
        source = ROOT / lang["source"]
        # A language can be registered before its master spreadsheet is dropped in
        # (e.g. german scaffolded ahead of content). Skip — don't fail the build —
        # and leave it out of index.json until the master exists.
        if not source.exists():
            print(f"\n=== skipping {lang['targetLang']}: source not found "
                  f"({lang['source']}) ===")
            continue
        cmd = [
            sys.executable, str(ROOT / "tools" / "import_content.py"),
            "--source", str(source),
            "--target-lang", lang["targetLang"],
            "--out", str(out),
            "--min-app-version", lang.get("minAppVersion", "1.0.0"),
        ]
        if args.strict:
            cmd.append("--strict")
        print(f"\n=== building {lang['targetLang']} ===")
        subprocess.run(cmd, check=True)

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        rel = out.relative_to(cdn_root).as_posix()  # e.g. "english"
        index["apps"].append({
            "targetLang": lang["targetLang"],
            "path": rel,
            "manifest": f"{rel}/manifest.json",
            "version": manifest["version"],
            "wordCount": manifest["wordCount"],
            "audioCount": manifest.get("audioCount", 0),
            "exampleCount": manifest.get("exampleCount", 0),
            "nativeLangs": manifest["nativeLangs"],
        })

    # Languages generated outside the Excel pipeline (tools/gen_lang_content.py)
    # write their <lang>/manifest.json straight into the CDN root but never touch
    # languages.json. Pick them up by discovery so they get published too.
    configured = {app["path"] for app in index["apps"]}
    for manifest_path in sorted(cdn_root.glob("*/manifest.json")):
        rel = manifest_path.parent.relative_to(cdn_root).as_posix()
        if rel in configured:
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        index["apps"].append({
            "targetLang": manifest["targetLang"],
            "path": rel,
            "manifest": f"{rel}/manifest.json",
            "version": manifest["version"],
            "wordCount": manifest["wordCount"],
            "audioCount": manifest.get("audioCount", 0),
            "exampleCount": manifest.get("exampleCount", 0),
            "nativeLangs": manifest["nativeLangs"],
        })
        print(f"=== discovered {manifest['targetLang']} ({rel}) ===")

    index_path = cdn_root / "index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {index_path} ({len(index['apps'])} app(s)).")


if __name__ == "__main__":
    main()
# publish trigger: es top-1000 senses
