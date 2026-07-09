#!/usr/bin/env python3
"""Tests for gen_audio with a MOCKED TTS client — no network, no billing.

Asserts: filename == <key>.mp3, audio field set, idempotent skip of existing
clips, --limit cap, and manifest audioCount/version patching.
Run: python tools/test_gen_audio.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from gen_audio import generate, lang_code_of, patch_manifest


class FakeTts:
    """Stand-in for Google TTS: records calls, returns deterministic bytes."""

    def __init__(self):
        self.calls = []

    def __call__(self, text, voice, lang_code):
        self.calls.append((text, voice, lang_code))
        return f"MP3::{text}".encode("utf-8")


def words_fixture():
    return [
        {"key": "en_aaa", "target": "the", "audio": None},
        {"key": "en_bbb", "target": "water", "audio": None},
        {"key": "en_ccc", "target": "  ", "audio": None},   # blank -> skipped
    ]


def check(cond, msg, failures):
    if not cond:
        failures.append(msg)


def main():
    failures = []

    # lang_code derivation
    check(lang_code_of("en-US-Neural2-C") == "en-US",
          "lang_code_of en-US wrong", failures)
    check(lang_code_of("cmn-CN-Wavenet-A") == "cmn-CN",
          "lang_code_of cmn-CN wrong", failures)

    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "audio"

        # --- first run: synthesizes the two real words, skips the blank ---
        words = words_fixture()
        fake = FakeTts()
        made = generate(words, audio, "en-US-Neural2-C", "en-US", fake)
        check(made == 2, f"expected 2 synthesized, got {made}", failures)
        check(len(fake.calls) == 2, "blank target should not be synthesized", failures)
        check(words[0]["audio"] == "en_aaa.mp3", "audio filename not <key>.mp3", failures)
        check(words[1]["audio"] == "en_bbb.mp3", "audio filename not <key>.mp3", failures)
        check(words[2]["audio"] is None, "blank word should stay audio=None", failures)
        check((audio / "en_aaa.mp3").read_bytes() == b"MP3::the",
              "mp3 bytes not written", failures)

        # --- idempotent re-run: nothing new synthesized, field still set ---
        words2 = words_fixture()
        fake2 = FakeTts()
        made2 = generate(words2, audio, "en-US-Neural2-C", "en-US", fake2)
        check(made2 == 0, f"re-run should synthesize 0, got {made2}", failures)
        check(len(fake2.calls) == 0, "re-run must not call TTS", failures)
        check(words2[0]["audio"] == "en_aaa.mp3",
              "re-run must still set audio field from disk", failures)

        # --- limit caps new synthesis ---
        import shutil
        fresh = Path(td) / "audio2"
        words3 = words_fixture()
        made3 = generate(words3, fresh, "en-US-Neural2-C", "en-US", FakeTts(), limit=1)
        check(made3 == 1, f"limit=1 should synthesize 1, got {made3}", failures)
        shutil.rmtree(fresh, ignore_errors=True)

        # --- manifest patch ---
        mpath = Path(td) / "manifest.json"
        mpath.write_text(json.dumps({"version": 14, "audioCount": 0}), encoding="utf-8")
        v = patch_manifest(mpath, words)
        check(v == 15, f"version should bump to 15, got {v}", failures)
        m = json.loads(mpath.read_text(encoding="utf-8"))
        check(m["audioCount"] == 2, f"audioCount should be 2, got {m['audioCount']}",
              failures)

    if failures:
        print(f"FAIL ({len(failures)}):")
        print("\n".join(f"  {f}" for f in failures))
        raise SystemExit(1)
    print("OK — gen_audio tests passed.")


if __name__ == "__main__":
    main()
