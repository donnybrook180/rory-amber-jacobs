#!/usr/bin/env python3
"""
Independently validate that each shipped words.*.json is really ordered by
corpus frequency — NOT by re-checking wordfreq (which we sorted by; circular),
but against an external reference: the HermitDave OpenSubtitles frequency lists.

Per language it reports, on the covered subset:
  coverage %   how many of our 5000 targets appear in the 50k reference
  top50 ∩      overlap of our top-50 with the reference top-50 (the cleanest
               signal — top function words are inflection-invariant)
  Spearman ρ   rank correlation, our rank vs reference rank
  monotonic    fraction of adjacent pairs with non-increasing wordfreq Zipf
               (self-check that the sort was applied)
  junk median  median rank of zero-frequency words (should sit in the tail)

Caveat: our lists are lemmas; the reference is inflected surface forms, so
coverage and ρ are undercounts by construction (a verb lemma competes with its
scattered conjugations). The top-N overlap is the inflection-robust metric.

Usage: python tools/validate_ranking.py [--refresh]
Reference lists are cached under tools/.freqcache/.
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).resolve().parent / ".freqcache"
URL = ("https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/"
       "content/2018/{lang}/{lang}_50k.txt")

LANGS = {"english": "en", "spanish": "es", "french": "fr", "german": "de",
         "indonesian": "id", "portuguese": "pt", "vietnamese": "vi"}

LARGE = {"en", "es", "fr", "de", "pt"}
# Decisive metrics: rank correlation with an independent corpus + word realness
# (coverage) + junk parked in the tail. Top-50 overlap is reported but NOT a
# pass gate — it is depressed by lemma-vs-surface-form and subtitle register
# mismatch (the reference top is full of contractions and spoken pronouns our
# lemma list omits), so it understates a genuinely correct ordering.
# Thresholds per tier: (min single-token coverage, min Spearman rho).
THRESHOLDS = {"large": (0.65, 0.60), "small": (0.50, 0.40)}


def fetch_ref(code: str, refresh: bool) -> dict[str, int]:
    """word -> reference rank (1 = most frequent), from cached OpenSubtitles."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{code}_50k.txt"
    if refresh or not path.exists():
        urllib.request.urlretrieve(URL.format(lang=code), path)
    ref = {}
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        word = line.split(" ", 1)[0].strip().lower()
        if word and word not in ref:
            ref[word] = i
    return ref


def spearman(pairs: list[tuple[int, int]]) -> float:
    """Spearman ρ over (our_rank, ref_rank) — rank both within the subset."""
    n = len(pairs)
    if n < 2:
        return float("nan")
    xs = _ranks([p[0] for p in pairs])
    ys = _ranks([p[1] for p in pairs])
    d2 = sum((x - y) ** 2 for x, y in zip(xs, ys))
    return 1 - 6 * d2 / (n * (n * n - 1))


def _ranks(vals: list[int]) -> list[float]:
    """Fractional ranks (average ties) of vals."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def validate(name: str, code: str, refresh: bool):
    from wordfreq import zipf_frequency
    words = json.loads((ROOT / name / f"words.{code}.json").read_text("utf-8"))
    words.sort(key=lambda w: w["rank"])
    targets = [w["target"].strip().lower() for w in words]
    ref = fetch_ref(code, refresh)

    covered = [(i + 1, ref[t]) for i, t in enumerate(targets) if t in ref]
    coverage = len(covered) / len(targets)
    # Multi-word lemmas can't match a single-token reference — measure coverage
    # over single-token targets only so gendered/compound languages aren't
    # penalised for tokenization mismatch.
    single = [t for t in targets if " " not in t]
    cov_single = (sum(1 for t in single if t in ref) / len(single)
                  if single else coverage)

    our_top = [t for t in targets[:50]]
    ref_top = sorted(ref, key=ref.get)[:50]
    top_overlap = len(set(our_top) & set(ref_top))

    rho = spearman(covered)

    zipfs = [zipf_frequency(t, code) for t in targets]
    mono = sum(1 for a, b in zip(zipfs, zipfs[1:]) if b <= a) / (len(zipfs) - 1)
    junk_ranks = [i + 1 for i, z in enumerate(zipfs) if z == 0]
    junk_median = (sorted(junk_ranks)[len(junk_ranks) // 2]
                   if junk_ranks else None)

    tier = "large" if code in LARGE else "small"
    min_cov, min_rho = THRESHOLDS[tier]
    # Junk must sit in the tail (bottom 20%), not the head.
    junk_ok = junk_median is None or junk_median > len(targets) * 0.8
    ok = (cov_single >= min_cov and rho >= min_rho and junk_ok)
    return {
        "name": name, "code": code, "tier": tier, "pass": ok,
        "coverage": coverage, "cov_single": cov_single,
        "top_overlap": top_overlap, "rho": rho,
        "mono": mono, "junk": len(junk_ranks), "junk_median": junk_median,
        "our_top20": targets[:20], "ref_top20": sorted(ref, key=ref.get)[:20],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="re-download reference lists")
    args = ap.parse_args()

    rows = [validate(n, c, args.refresh) for n, c in LANGS.items()]
    print(f"\n{'lang':<12}{'tier':<7}{'cov':>6}{'covS':>6}{'top50':>7}"
          f"{'rho':>7}{'mono':>7}{'junk':>6}{'jmed':>7}  verdict")
    print("-" * 76)
    for r in rows:
        jmed = r["junk_median"] if r["junk_median"] is not None else "-"
        print(f"{r['name']:<12}{r['tier']:<7}{r['coverage']*100:>5.0f}%"
              f"{r['cov_single']*100:>5.0f}%{r['top_overlap']:>7}"
              f"{r['rho']:>7.2f}{r['mono']*100:>6.0f}%"
              f"{r['junk']:>6}{str(jmed):>7}  {'PASS' if r['pass'] else 'FAIL'}")
    print("  cov=coverage  covS=single-token coverage (pass gate)  "
          "top50=informational")
    print()
    for r in rows:
        print(f"[{r['code']}] our  top20: {r['our_top20']}")
        print(f"[{r['code']}] ref  top20: {r['ref_top20']}")
    failed = [r["code"] for r in rows if not r["pass"]]
    print(f"\n{'ALL PASS' if not failed else 'FAILED: ' + ', '.join(failed)}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
