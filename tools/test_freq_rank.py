#!/usr/bin/env python3
"""Tests for freq_rank. Run: python tools/test_freq_rank.py"""
from freq_rank import (
    _score, can_rank, level_for_rank, pack_for_rank, rank_words, stable_key, tier,
)


def _w(target, rank, **extra):
    d = {"target": target, "rank": rank, "pos": "noun",
         "translations": {"en": [target]}}
    d.update(extra)
    return d


def test_tier():
    assert tier("es") == "large"
    assert tier("en") == "large"
    assert tier("vi") == "small"
    assert tier("id") == "small"
    assert tier("th") == "none"       # no wordfreq corpus
    assert can_rank("es") and not can_rank("th")


def test_stable_key():
    k = stable_key("es", "casa")
    assert k.startswith("es_") and len(k) == 3 + 12
    assert k == stable_key("es", "casa")          # deterministic
    assert stable_key("es", "casa") != stable_key("es", "perro")
    assert stable_key("es", "casa") != stable_key("fr", "casa")  # code-scoped


def test_level_and_pack():
    assert level_for_rank(1) == "beginner"
    assert level_for_rank(1000) == "beginner"
    assert level_for_rank(1001) == "intermediate"
    assert level_for_rank(3001) == "advanced"
    assert pack_for_rank(1) == {"id": 1, "label": "1-10"}
    assert pack_for_rank(127) == {"id": 13, "label": "121-130"}


def test_large_sorts_by_zipf_junk_to_tail():
    # Deliberately scrambled input order.
    words = [_w("xyzzy", 1), _w("casa", 2), _w("el", 3), _w("perro", 4)]
    out = rank_words(words, "es")
    targets = [w["target"] for w in out]
    assert targets[0] == "el"          # most frequent
    assert targets[-1] == "xyzzy"      # zero-freq junk sinks last
    assert out[0]["rank"] == 1 and out[-1]["rank"] == 4
    assert out[0]["key"] == stable_key("es", "el")
    # ranks contiguous, level/pack recomputed
    assert [w["rank"] for w in out] == [1, 2, 3, 4]
    assert all(w["pack"] == pack_for_rank(w["rank"]) for w in out)


def test_fields_preserved():
    words = [_w("casa", 1, gender="f", audio="a", examples=[1],
                translations={"en": ["house"]})]
    out = rank_words(words, "es")
    w = out[0]
    assert w["gender"] == "f" and w["audio"] == "a" and w["examples"] == [1]
    assert w["translations"] == {"en": ["house"]}
    assert w["pos"] == "noun"


def test_keys_unique_and_assigned_for_uncovered():
    # 'th' has no corpus: order preserved, but keys still assigned + unique.
    words = [_w("ก", 1), _w("ข", 2), _w("ค", 3)]
    out = rank_words(words, "th")
    assert [w["target"] for w in out] == ["ก", "ข", "ค"]   # order untouched
    assert len({w["key"] for w in out}) == 3
    assert all(w["key"].startswith("th_") for w in out)


def test_small_blend_keeps_common_zero_freq_word_high():
    # Small-tier: a zero-freq word at the top of the original list must stay
    # above a covered mid-frequency word buried deep in the original order.
    zero_top = _score(0.0, orig_rank=1, n=100, large=False)
    covered_deep = _score(4.0, orig_rank=90, n=100, large=False)
    assert zero_top > covered_deep
    # And a covered common word still beats a zero-freq word when both are deep.
    covered_deep2 = _score(6.0, orig_rank=80, n=100, large=False)
    zero_deep = _score(0.0, orig_rank=81, n=100, large=False)
    assert covered_deep2 > zero_deep


def test_multiword_target_scored():
    from wordfreq import zipf_frequency
    # Vietnamese multi-syllable word with a space is scored by wordfreq (not 0).
    assert zipf_frequency("đồng hồ", "vi") > 0
    # rank_words handles it without crashing; at equal original standing the
    # scored word outranks a nonsense token.
    out = rank_words([_w("đồng hồ", 1), _w("xxqzq", 2)], "vi")
    assert out[0]["target"] == "đồng hồ"


def test_idempotent_small_tier():
    import copy
    # Small-tier blend must converge: re-ranking already-ranked words is a no-op,
    # thanks to the frozen srcRank anchor.
    words = [_w(t, i + 1) for i, t in enumerate(
        ["đồng hồ", "nước", "xxqzq", "máy", "karst"])]
    r1 = rank_words(copy.deepcopy(words), "vi")
    r2 = rank_words(copy.deepcopy(r1), "vi")
    assert [w["target"] for w in r1] == [w["target"] for w in r2]
    assert all("srcRank" in w for w in r1)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok {t.__name__}")
    print(f"OK — {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
