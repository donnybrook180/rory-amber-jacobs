# German master spreadsheet — column layout spec

Authoring spec for `Top_5000_Duitse_Woorden_Meertalig_Master.xlsx`. Drop the finished file
in this folder (`rory-amber-jacobs/resources/`) and `tools/build_all.py` emits
`german/words.de.json` + `german/manifest.json` and adds the index entry — no code change.

The importer (`tools/import_content.py`) is **position-based**, not name-based, for the first
three columns; native-language columns are matched by the ISO code in their header. Match this
layout exactly.

## Workbook = up to three sheets

| Sheet | Purpose | Imported? |
|-------|---------|-----------|
| `Overzicht (Info)` | free-text metadata / notes | **No** — skipped (any sheet whose name contains `overzicht` or `info`) |
| `Top 5000 Master` | the 5000 word rows | **Yes** — this is the data sheet |
| `Examples` | example sentences per word (Increment 8c) | **Yes, optional** — omit it and words simply ship with no examples |

The data sheet **must** be named `Top 5000 Master` (the importer's `DATA_SHEET`). If renamed,
the importer falls back to the first non-info sheet, so keep the name to be safe.

## Row 1 = header. Rows 2…5001 = words (one per rank).

### Fixed columns (by position — header text is free, but order is fixed)

| Col (0-based) | A=0 | Content | Notes |
|---|---|---------|-------|
| 0 | A | **Rank** | integer 1…5000, unique. Drives `key = de_<rank:04d>` (e.g. `de_0042`), `level` band, and 10-word Learner `pack`. Non-numeric rank → row skipped with warning. |
| 1 | B | **German Word** | the word being taught. Empty → row skipped. |
| 2 | C | **Part of Speech** | authored in **Dutch** (same as the English master), normalized to a neutral enum — see table below. |

### Native-language columns (col D=3 onward)

One column per native language the app can translate **into**. Header **must end with the ISO
code in parentheses** — that's how the code is extracted:

```
Nederlands (NL) | English (EN) | Español (ES) | 中文 (ZH) | Français (FR) | …
```

- Header `Español (ES)` → native code `es`. Match is the trailing `(XX)`; the label before it
  is cosmetic.
- A column with an **empty header is ignored**, so don't leave gaps between native columns.
- The set of native codes present becomes `manifest.nativeLangs` (and feeds the in-app "I
  speak…" picker). Reuse the **same 17** as the English master for parity:
  `NL, EN, ES, ZH, HI, UR, AR, PT, JA, KO, FR, IT, VI, TH, ID, RU, SW`
  (English replaces the English master's German column — the target language is never its own
  translation column).
- **Cells may hold several comma-separated options** — `der, die, das` / `ser, estar`. The
  importer splits on commas into a list; the quiz accepts any listed answer, the flashcard
  shows the first as primary. So put the **primary translation first**.
- Empty translation cell → kept as `[]` with a per-row warning (build still succeeds unless
  `--strict`).

## Part-of-Speech values (Dutch → neutral enum)

Use exactly these Dutch strings in column C (case-insensitive). Anything else maps to `other`
with a warning.

| Dutch (column C) | → enum |
|------------------|--------|
| `werkwoord` | `verb` |
| `zelfstandig naamwoord` | `noun` |
| `bijvoeglijk naamwoord` | `adjective` |
| `voorzetsel` | `preposition` |
| `lidwoord/bepaling` | `article` |
| `voegwoord` | `conjunction` |
| `voornaamwoord` | `pronoun` |

> Adding a new POS string means adding it to `POS_MAP` in `tools/import_content.py`. Until then
> it imports as `other`. German articles vary by gender/case — keep them under `article`
> (`lidwoord/bepaling`).

## Derived fields (do NOT add columns for these — the importer computes them)

| Field | Rule |
|-------|------|
| `key` | `de_<rank:04d>` |
| `level` | rank 1–1000 `beginner`, 1001–3000 `intermediate`, 3001–5000 `advanced` |
| `pack` | 10 words per pack by rank → `{ id, label: "1-10" }` |
| `audio` | `null` until a matching `german/audio/<key>.mp3` ships (then auto-set) |

## Example rows (sheet `Top 5000 Master`)

```
Rank | German Word | Part of Speech        | Nederlands (NL) | English (EN) | Español (ES) | Français (FR) | …
1    | der/die/das | lidwoord/bepaling     | de, het         | the          | el, la       | le, la        | …
2    | sein        | werkwoord             | zijn            | be           | ser, estar   | être          | …
3    | Haus        | zelfstandig naamwoord | huis            | house        | casa         | maison        | …
```

→ produces:

```jsonc
{ "key": "de_0003", "rank": 3, "target": "Haus", "pos": "noun",
  "level": "beginner", "pack": { "id": 1, "label": "1-10" },
  "translations": { "nl": ["huis"], "en": ["house"], "es": ["casa"], "fr": ["maison"], … },
  "audio": null }
```

## `Examples` sheet (optional — Increment 8c)

Give students a sentence per word **plus its translation in their native language**. One row
per sentence, foreign-keyed by `Rank`. A word can have several sentences (repeat the Rank).

### Columns

| Col (0-based) | Content | Notes |
|---|---------|-------|
| 0 | **Rank** | must match a Rank in `Top 5000 Master`. Orphan ranks are warned + skipped. |
| 1 | **Example (target)** | the sentence in German. Empty → row skipped. |
| 2…N | **native-language columns** | same `(XX)` ISO-code headers as the word sheet, e.g. `Nederlands (NL)`, `English (EN)`. **One sentence per cell** (no comma-splitting — unlike word translations). |

- Translations are **sparse-friendly**: leave a cell blank and that language just falls back
  to showing the target sentence only. A target-only row (no native columns filled) is valid.
- Put the columns in any order after Rank/Example; matching is by the trailing `(XX)` code.
- Order of rows for the same Rank = order the sentences appear in the app.

### Example rows (sheet `Examples`)

```
Rank | Example (target)     | Nederlands (NL)     | English (EN)            | Español (ES)
3    | Das Haus ist groß.   | Het huis is groot.  | The house is big.       | La casa es grande.
3    | Wir kaufen ein Haus. | We kopen een huis.  | We are buying a house.  |
2    | Ich will hier sein.  | Ik wil hier zijn.   | I want to be here.      | Quiero estar aquí.
```

→ attaches to the word records:

```jsonc
// word de_0003 ("Haus")
"examples": [
  { "text": "Das Haus ist groß.", "audio": null,
    "translations": { "nl": "Het huis is groot.", "en": "The house is big.", "es": "La casa es grande." } },
  { "text": "Wir kaufen ein Haus.", "audio": null,
    "translations": { "nl": "We kopen een huis.", "en": "We are buying a house." } }
]
```

Words with no rows in this sheet get `"examples": []` and show no examples section — fully
backward-compatible.

## Validate before publishing

```bash
# from the content repo root, dry-run a single language to one temp dir:
python tools/import_content.py \
  --source resources/Top_5000_Duitse_Woorden_Meertalig_Master.xlsx \
  --target-lang de --out /tmp/german --strict
```

`--strict` exits non-zero on any warning (missing translation, duplicate rank, unknown POS),
so you catch authoring gaps before they reach the CDN. Then `python tools/build_all.py`
publishes all languages + refreshes `index.json`.
