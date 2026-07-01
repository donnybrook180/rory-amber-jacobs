#!/usr/bin/env python3
"""Exhaustive tests for pos_normalize — every distinct pos value shipped in the
content plus edge cases. Run: python tools/test_pos_normalize.py"""
from pos_normalize import TAGS, normalize

# (raw pos, expected tag, expected gender). Covers every distinct value found in
# rory-amber-jacobs/*/words.*.json as of the migration.
CASES = [
    ("adj",         "adjective",    None),
    ("adj masc.",   "adjective",    "m"),
    ("adj, m",      "adjective",    "m"),
    ("adj.",        "adjective",    None),
    ("adjective",   "adjective",    None),
    ("adv",         "adverb",       None),
    ("adverb",      "adverb",       None),
    ("art",         "article",      None),
    ("article",     "article",      None),
    ("aux",         "verb",         None),
    ("classifier",  "other",        None),
    ("conj",        "conjunction",  None),
    ("conjunction", "conjunction",  None),
    ("connector",   "conjunction",  None),
    ("danh từ",     "noun",         None),
    ("determiner",  "article",      None),
    ("interjection","interjection", None),
    ("n",           "noun",         None),
    ("n.f.",        "noun",         "f"),
    ("n.m.",        "noun",         "m"),
    ("nf",          "noun",         "f"),
    ("nm",          "noun",         "m"),
    ("noun",        "noun",         None),
    ("noun f",      "noun",         "f"),
    ("noun f.",     "noun",         "f"),
    ("noun fem.",   "noun",         "f"),
    ("noun m",      "noun",         "m"),
    ("noun m.",     "noun",         "m"),
    ("noun m/f",    "noun",         None),   # ambiguous -> no gender
    ("noun masc.",  "noun",         "m"),
    ("noun, f",     "noun",         "f"),
    ("noun, m",     "noun",         "m"),
    ("noun-f",      "noun",         "f"),
    ("noun-m",      "noun",         "m"),
    ("noun.f",      "noun",         "f"),
    ("noun.m",      "noun",         "m"),
    ("noun_f",      "noun",         "f"),
    ("noun_m",      "noun",         "m"),
    ("num",         "numeral",      None),
    ("numeral",     "numeral",      None),
    ("other",       "other",        None),
    ("particle",    "other",        None),
    ("prep",        "preposition",  None),
    ("preposition", "preposition",  None),
    ("pron",        "pronoun",      None),
    ("pronoun",     "pronoun",      None),
    ("v",           "verb",         None),
    ("verb",        "verb",         None),
]

# Edge cases beyond the shipped set.
EDGE = [
    ("",            "other",        None),
    ("   ",         "other",        None),
    (None,          "other",        None),
    ("NOUN-M",      "noun",         "m"),    # case-insensitive
    ("  verb  ",    "verb",         None),   # trimming
    ("gibberish",   "other",        None),   # unknown -> other
    ("Substantiv",  "other",        None),   # untranslated leakage not aliased
]


def main():
    failures = []
    for raw, tag, gender in CASES + EDGE:
        got = normalize(raw)
        if got != (tag, gender):
            failures.append(f"  normalize({raw!r}) = {got}, expected {(tag, gender)}")
        if got[0] not in TAGS:
            failures.append(f"  normalize({raw!r}) tag {got[0]!r} not in TAGS")

    if failures:
        print(f"FAIL ({len(failures)}):")
        print("\n".join(failures))
        raise SystemExit(1)
    print(f"OK — {len(CASES) + len(EDGE)} cases passed.")


if __name__ == "__main__":
    main()
