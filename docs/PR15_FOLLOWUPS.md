# PR #15 Review — Deferred Follow-Ups

Recorded 2026-08-09 from an eight-round independent review of PR #15
(branch `fix/trend-chart-consolidation`, base `e3237b6`). Everything the review
confirmed and fixed landed in that branch with a mutation-proven regression
test. This file holds only what was deliberately **not** fixed there.

Delete an entry once its fix and regression test are on `main`; delete this file
when empty.

## D1 — Wearable timestamps are format-ambiguous (deferred by ruling)

`validation.validate_wearable` requires a `timestamp` to be present but not to
parse, and `condition_charts._coerce_point` falls back to `pandas.to_datetime`'s
heuristics. A wearable export written in day-first order therefore charts on the
wrong date: `04/03/2026` and `05/03/2026` plot as 3 April and 3 May rather than
4 and 5 March. Partial dates similarly acquire an invented day.

Nothing warns, and the record itself is stored exactly as given — only the chart
and any "latest reading" derived from it are wrong.

**Ruling, 2026-08-09:** deferred. Day-first exports are not expected in the near
term, and any fix necessarily stops charting timestamps that chart today, so it
is a product decision rather than a bug fix.

**When to revisit:** the first non-US-format data source, or any report of a
wearable point appearing on the wrong date.

**Shape of the fix:** constrain `validate_wearable` to an explicit supported
format list at the input boundary, rather than widening the chart-time parser —
`_coerce_point` cannot recover an intent the stored string no longer carries.
Whatever is chosen has to say what happens to timestamps already stored under
the looser rule.

## D2 — `import_wearables_csv` keeps the older parsing behavior

`imports_exports.import_labs_csv` now reads with `dtype=str,
keep_default_na=False` and resolves absence per column through `_csv_cell`,
because pandas' type inference silently rewrote values before validation saw
them — it reads `0.000000000000000001` as `0.0`, and blanks `NA`/`NULL`.

`import_wearables_csv` still uses a bare `pd.read_csv(file_obj)` followed by
`float(data["value"])`, so a wearable reading is exposed to the same rewriting.

**Not a one-line change.** Copying `dtype=str, keep_default_na=False` alone
turns a tolerant import into a rejecting one: `NA` in a coded or numeric column
would reach validation literally. `_csv_cell` is reusable, but its
`_LITERAL_CSV_FIELDS` set is lab-specific — wearables have no free-text result
column, so the wearable equivalent is probably empty.

Needs regression tests mirroring the lab ones: precision preserved, NA tokens
still absent, and a value the old path fabricated now reported in `skipped`.

## D3 — `validate_wearable` does not validate `unit`

PR #15 fixed the *display* consequence — `build_trend_chart` splits a line by
unit, so a weight logged in lb and then kg no longer draws one continuous fall —
but the input boundary still accepts any unit string, or none.

Deferred as out of scope for that PR. Related to D1: both are gaps in the same
validator.

## Ruled not defects (do not re-open without new evidence)

Recorded so a later review does not spend another round on them.

- **`build_severity_chart` y-domain of `[0, 10]` for a 1–10 scale.** Raised
  twice. No data is altered or hidden and the axis is titled "Severity (1-10)";
  padding the floor renders a severity-1 point fully instead of clipping it on
  the axis line.
- **Float rounding at the 16th significant digit** (`9007199254740993`,
  `1.0000000000000001`). "5.6" is equally inexact, so "exactly representable" is
  not a meetable bar, and `result_value` retains the written text verbatim.
- **Values whose magnitude a float cannot carry** — several-hundred-digit
  integers, decimals below float range. A guard for these was written during the
  review and then removed: no assay, portal export, or person produces such a
  value, and the code and its tests were cost without a clinical trigger. The
  overflow check inside `parse_plain_decimal` predates the review and stays.
- **A CSV `flag` column holding `0` or `False`.** Every unrecognized flag token,
  including a real portal's `H`/`L`, has always been reported in `skipped`;
  these are not special, and the row is reported rather than silently altered.
