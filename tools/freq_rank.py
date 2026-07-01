#!/usr/bin/env python3
"""
Frequency re-ranking + stable word keys.

The generator produces ~5000 plausible words but can't truly rank them by
corpus frequency (it estimates in coarse alphabetical/thematic batches). This
re-orders a language's words by real frequency from the `wordfreq` corpus and
assigns each a stable, rank-independent key.

Two coverage tiers (wordfreq wordlist size):
  large  reliable corpora — order strictly by Zipf frequency; a zero score
         means the word is genuinely absent (junk) and sinks to the tail.
  small  thin corpora (id, vi, ko, hi, ur, tr) — many real words score zero
         from corpus gaps, so a pure Zipf sort would wrongly bury them.
         Blend: score = 0.7*original_position + 0.3*normalized_zipf, so covered
         common words rise while uncovered words keep the generator's ordering
         instead of being dumped at the bottom.
Uncovered languages (no wordfreq list, e.g. th, sw) are left untouched.

Keys: `<code>_<sha1(target)[:12]>` — stable across re-ranks forever, so progress
and favorites survive future frequency updates. Length auto-extends on the rare
collision.
"""
from __future__ import annotations

import hashlib

from wordfreq import available_languages, zipf_frequency

_AVAILABLE = set(available_languages())

# Corpora large enough to trust a strict frequency sort.
LARGE = {"en", "es", "fr", "de", "pt", "it", "ru", "zh", "ja", "ar", "nl"}
# Thin corpora: blend corpus signal with the generator's original order.
SMALL = {"id", "vi", "ko", "hi", "ur", "tr"}

_ZIPF_MAX = 8.0  # practical ceiling of the Zipf scale
_BLEND_ORIG = 0.7  # weight on original position for small-tier langs
_BLEND_ZIPF = 0.3


def tier(code: str) -> str:
    """'large' | 'small' | 'none' (no wordfreq corpus for this language)."""
    if code not in _AVAILABLE:
        return "none"
    return "large" if code in LARGE else "small"


def can_rank(code: str) -> bool:
    return tier(code) != "none"


def stable_key(code: str, target: str, length: int = 12) -> str:
    """Deterministic, rank-independent key for [target]."""
    digest = hashlib.sha1(target.encode("utf-8")).hexdigest()
    return f"{code}_{digest[:length]}"


def level_for_rank(rank: int) -> str:
    if rank <= 1000:
        return "beginner"
    if rank <= 3000:
        return "intermediate"
    return "advanced"


def pack_for_rank(rank: int) -> dict:
    pid = (rank - 1) // 10 + 1
    return {"id": pid, "label": f"{(pid - 1) * 10 + 1}-{pid * 10}"}


def _score(zipf: float, orig_rank: int, n: int, large: bool) -> float:
    if large:
        return zipf
    norm_zipf = min(zipf, _ZIPF_MAX) / _ZIPF_MAX
    # Original position normalized to [0,1]; rank 1 -> 1.0 (most common).
    norm_orig = 1.0 - (orig_rank - 1) / max(1, n - 1)
    return _BLEND_ORIG * norm_orig + _BLEND_ZIPF * norm_zipf


def _assign_keys(words: list[dict], code: str) -> None:
    """Set a unique stable key on each word in place, extending the hash length
    only if 12 hex chars collide within this list."""
    for length in range(12, 41, 4):
        keys = [stable_key(code, w["target"], length) for w in words]
        if len(set(keys)) == len(keys):
            for w, k in zip(words, keys):
                w["key"] = k
            return
    raise ValueError(f"{code}: unresolvable key collision")


def rank_words(words: list[dict], code: str) -> list[dict]:
    """Return [words] re-ordered by frequency with rank/key/level/pack updated.

    Every other field (target, pos, gender, translations, audio, examples,
    reading) is preserved untouched. If the language has no wordfreq corpus the
    list is returned unchanged (only keys are (re)assigned). The input dicts are
    mutated and also returned in their new order.
    """
    t = tier(code)
    n = len(words)

    # Freeze the generator's original ordering once, so re-ranking is
    # idempotent — the small-tier blend and the tiebreaker read this stable
    # anchor, never the mutable `rank` we overwrite below.
    for i, w in enumerate(words):
        if "srcRank" not in w:
            w["srcRank"] = w.get("rank") or (i + 1)

    if t != "none":
        large = t == "large"
        keyed = []
        for w in words:
            orig = w["srcRank"]
            z = zipf_frequency(w["target"], code)
            keyed.append((-_score(z, orig, n, large), orig, w))
        keyed.sort(key=lambda t: (t[0], t[1]))
        words = [w for _, _, w in keyed]

    for i, w in enumerate(words, 1):
        w["rank"] = i
        w["level"] = level_for_rank(i)
        w["pack"] = pack_for_rank(i)

    _assign_keys(words, code)
    return words
