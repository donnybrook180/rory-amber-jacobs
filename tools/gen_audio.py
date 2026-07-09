#!/usr/bin/env python3
"""
Synthesize one pronunciation mp3 per target word via Google Cloud Text-to-Speech
and wire it into the CDN content, so the app plays a natural voice offline.

Runs AFTER import_content.py / shard_examples.py, same as a post-import step:

    <lang>/words.<code>.json   word.audio set to "<key>.mp3"
    <lang>/audio/<key>.mp3     the synthesized clip
    <lang>/manifest.json       audioCount patched, version bumped

Batch, not runtime: the app ships no API key and streams/caches the mp3s. Cost is
one-time (~$0.50/language on Neural2). Idempotent + cheap to re-run: any word whose
mp3 already exists on disk is skipped, so re-runs never re-bill.

Auth: set GOOGLE_TTS_API_KEY to a Google Cloud API key with the Text-to-Speech API
enabled. The key lives in the build environment only — never committed, never bundled.

Voice: --voice wins; otherwise the matching tools/languages.json entry's "voice".
The BCP-47 languageCode is the first two segments of the voice name
(en-US-Neural2-C -> en-US).

Usage:
    GOOGLE_TTS_API_KEY=... python tools/gen_audio.py en
    GOOGLE_TTS_API_KEY=... python tools/gen_audio.py en --voice en-US-Neural2-C --limit 50
    python tools/gen_audio.py en --dry-run          # list work, no network/billing
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "tools" / "languages.json"
ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"


def lang_code_of(voice: str) -> str:
    """BCP-47 languageCode from a voice name: en-US-Neural2-C -> en-US."""
    parts = voice.split("-")
    if len(parts) < 2:
        raise ValueError(f"can't derive languageCode from voice {voice!r}")
    return f"{parts[0]}-{parts[1]}"


def voice_for(code: str) -> str | None:
    """The `voice` configured for target-language `code` in languages.json."""
    if not CONFIG.exists():
        return None
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    for lang in cfg.get("languages", []):
        if lang.get("targetLang") == code:
            return lang.get("voice")
    return None


def synthesize_google(text: str, voice: str, lang_code: str, api_key: str) -> bytes:
    """POST one word to Google Cloud TTS, return raw mp3 bytes. Raises on HTTP error."""
    body = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": lang_code, "name": voice},
        "audioConfig": {"audioEncoding": "MP3"},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{ENDPOINT}?key={api_key}", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    audio_b64 = payload.get("audioContent")
    if not audio_b64:
        raise RuntimeError(f"no audioContent in response for {text!r}")
    return base64.b64decode(audio_b64)


def generate(words: list[dict], audio_dir: Path, voice: str, lang_code: str,
             synth_fn, *, limit: int | None = None, force: bool = False) -> int:
    """Synthesize missing mp3s and set each word's `audio` field in place.

    `synth_fn(text, voice, lang_code) -> bytes` is injected so tests can run with a
    fake client (no network, no billing). Returns the number of clips synthesized.
    Words already carrying an mp3 on disk are skipped unless `force`.
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    made = 0
    for w in words:
        text = (w.get("target") or "").strip()
        if not text:
            continue
        fname = f"{w['key']}.mp3"
        path = audio_dir / fname
        if not force and path.exists() and path.stat().st_size > 0:
            w["audio"] = fname          # ensure the field reflects the on-disk clip
            continue
        if limit is not None and made >= limit:
            continue
        data = synth_fn(text, voice, lang_code)
        path.write_bytes(data)
        w["audio"] = fname
        made += 1
    return made


def patch_manifest(mpath: Path, words: list[dict]) -> int:
    """Update audioCount from the words on disk and bump the version. Returns version."""
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["audioCount"] = sum(1 for w in words if w.get("audio"))
    manifest["version"] = int(manifest.get("version", 0)) + 1
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return manifest["version"]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("code", help="target-language code, e.g. en")
    ap.add_argument("--voice", help="Google TTS voice name (overrides languages.json)")
    ap.add_argument("--limit", type=int,
                    help="synthesize at most N new clips (smoke test / cost cap)")
    ap.add_argument("--force", action="store_true",
                    help="re-synthesize even if the mp3 already exists (re-bills)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report how many clips are missing; no network, no writes")
    args = ap.parse_args()

    matches = list(ROOT.glob(f"*/words.{args.code}.json"))
    if not matches:
        sys.exit(f"no words.{args.code}.json")
    wpath = matches[0]
    words = json.loads(wpath.read_text(encoding="utf-8"))

    voice = args.voice or voice_for(args.code)
    if not voice:
        sys.exit(f"no voice for {args.code}: pass --voice or add \"voice\" to "
                 f"the {args.code} entry in tools/languages.json")
    lang_code = lang_code_of(voice)
    audio_dir = wpath.parent / "audio"

    if args.dry_run:
        missing = sum(
            1 for w in words
            if (w.get("target") or "").strip()
            and not (audio_dir / f"{w['key']}.mp3").exists())
        print(f"{args.code}: {missing} word(s) missing audio "
              f"(voice {voice}, langCode {lang_code}).")
        return

    api_key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not api_key:
        sys.exit("set GOOGLE_TTS_API_KEY (Google Cloud API key with the "
                 "Text-to-Speech API enabled)")

    def synth(text, v, lc):
        try:
            return synthesize_google(text, v, lc, api_key)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            sys.exit(f"TTS HTTP {e.code} for {text!r}: {detail}")

    made = generate(words, audio_dir, voice, lang_code, synth,
                    limit=args.limit, force=args.force)

    wpath.write_text(
        json.dumps(words, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    version = patch_manifest(wpath.parent / "manifest.json", words)

    covered = sum(1 for w in words if w.get("audio"))
    print(f"{args.code}: synthesized {made} new clip(s) with {voice}; "
          f"{covered}/{len(words)} words now have audio. manifest v{version}.")


if __name__ == "__main__":
    main()
