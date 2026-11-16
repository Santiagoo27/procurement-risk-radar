# Election-cycle features: design

Approved 2026-11-16.

## Why

The 2026-11-16 monthly retrain produced a worse time-extension model (PR-AUC −0.041). The
cause is contracts signed in 2023-H1, which entered training for the first time. Their
time-extension rate was unusually high, mostly in territorial service contracts. Contracts whose **planned end
fell in the four months before the October 2023 regional elections** were extended 20.4% of
the time, against 11.8% for the rest. Ley 996 de 2005 (Ley de Garantías) restricts
contracting in that window, so entities extend running contracts instead of signing new
ones. The model has no way to see this, so it learns "these buyers extend a lot" and
over-predicts in 2024. 2026 is an election year too, so this matters for current scores.

A quick experiment showed that adding calendar features recovers the extension model
(PR-AUC 0.318 → 0.339 on 2024-H2 test rows, against 0.342 when 2023-H1 is dropped).

## Goals

- Election-calendar features known at signing time, computed in the shared feature SQL so
  training, the API and the website get identical values. No new API fields.
- Each model carries its own feature list, so a bundle can hold a model trained with the old
  features next to one trained with the new ones. The monthly retrain then compares them
  on the same rows and the per-target gate decides. No manual migration.

## Non-goals

- No per-target feature lists at training time: both targets train with the same features;
  the per-target gate protects a target the new features do not help.
- No claim in public text that elections *cause* amendments. The site and docs describe the
  pattern and the legal restriction, nothing more.

## Design

1. `ELECTION_DAYS` constant: Congress, President (first round) and regional elections,
   2018 to 2027. A test fails when the last date is less than 12 months after today, so the
   calendar gets extended (2030) in time.
2. Features (validated with the real training before being kept, 3 seeds, both targets):
   `signed_in_restriction`, `planned_end_in_restriction` (planned start + planned duration
   within 122 days before an election day), `days_end_to_next_election`. Restriction window:
   4 months, as in Ley 996.
3. `RiskModel` prepares frames with its own `feature_names` and `categories` instead of the
   global list. Old pickled models already store their list, so they keep working.
4. `load_bundle` accepts a bundle when every model's features can be computed by this code
   (a subset of the current feature list), instead of requiring an exact match.
5. Monitoring marks the new features as expected drift (they follow the calendar). The model
   card and SHAP labels describe them.

## Builder's calls

- Exact SQL form of the calendar (VALUES table joined with ASOF or a correlated min).
- Whether `days_to_next_election` (from signing) is kept: only if validation shows it helps.
