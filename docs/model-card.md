# Model card: amendment risk at signing time

> Scores are statistical estimates for analysis, not allegations of wrongdoing. They estimate the chance that a contract will be amended, nothing more.

## Intended use

Estimate, at the moment a Colombian public contract is signed, the probability that it
will later receive a value addition (primary target) or a time extension (secondary
target), to help analysts, journalists and oversight bodies prioritise review. Not for
decisions about individual people or suppliers.

## Data

- Source: SECOP II open data (datos.gov.co), contracts signed 2019-01-01 to 2026-11-13; 4,510,521 closed contracts.
- Closed contract: planned end date (planned start + planned duration, falling back to the current end date) at least 180 days before 2026-11-14. Only closed contracts are labelled. The current end date is not used because extensions move it, which would drop extended contracts from recent periods.
- `has_value_addition` (10.5% positive): an explicit 'Adicion en el valor' amendment, or a generic amendment whose text describes a value addition (see [data audit](data-audit.md)).
- `has_time_extension` (13.6% positive): added days > 0 or an 'Extension' amendment.
- Temporal split by signing date: train before 2023-11-16 (2,521,447), validation 2023-11-16 to 2024-05-16 (463,849), test 2024-05-16 to 2025-11-16 (1,388,450).

## Features

Only information known at signing time.

- Categorical: `buyer_department`, `buyer_order`, `buyer_sector`, `buyer_branch`, `buyer_centralized`, `procurement_method`, `contract_type`, `category_segment`, `funding_source`.
- Numeric: `log_award_value`, `log_tender_budget`, `award_to_budget_ratio`, `planned_duration_days`, `days_publication_to_signing`, `days_signing_to_start`, `n_bidders`, `single_bidder`, `n_responses`, `n_invited`, `n_lots`, `signing_month`, `signed_in_december`, `supplier_is_natural_person`, `supplier_is_sme`, `supplier_is_group`, `advance_payment_enabled`, `extendable_clause`, `buyer_prior_n`, `buyer_prior_value_addition_rate`, `buyer_prior_extension_rate`, `supplier_prior_n`, `supplier_prior_value_addition_rate`, `supplier_prior_extension_rate`, `signed_in_restriction`, `planned_end_in_restriction`, `days_end_to_next_election`.
- Buyer and supplier history use only labels observable before the signing date (end date + 180 days), smoothed toward the training-period rate.
- Election calendar: whether the signing day and the planned end fall in the four months before an ordinary election, when Ley 996 de 2005 restricts contracting, and the days from the planned end to the next election. They describe a pattern (contracts ending in that window are extended more often), not a cause.
- Excluded: current contract value (already includes additions), current end date and stated duration (moved by extensions), added days, contract status (stale), payments, identifiers and supplier names.

## Evaluation (test split)

Ranking metrics (PR-AUC, ROC-AUC, precision and recall in the top 5%) use raw LightGBM scores; Brier score and log loss use the calibrated probabilities. Ties at the top-5% cutoff are broken at random with a fixed seed.

### `has_value_addition`

| Model | PR-AUC | ROC-AUC | Brier | Log loss | Precision @ top 5% | Recall @ top 5% |
|---|---:|---:|---:|---:|---:|---:|
| Base rate | 0.083 | 0.500 | 0.0773 | 0.2929 | 0.085 | 0.051 |
| Buyer history rate | 0.190 | 0.698 | 0.0745 | 0.2733 | 0.289 | 0.174 |
| Logistic regression | 0.222 | 0.726 | 0.0711 | 0.2598 | 0.308 | 0.186 |
| LightGBM (calibrated) | 0.261 | 0.765 | 0.0689 | 0.2508 | 0.372 | 0.224 |

![Precision-recall](figures/has_value_addition-pr-curves.png)
![Calibration](figures/has_value_addition-calibration.png)
![Top features](figures/has_value_addition-importance.png)

### `has_time_extension`

| Model | PR-AUC | ROC-AUC | Brier | Log loss | Precision @ top 5% | Recall @ top 5% |
|---|---:|---:|---:|---:|---:|---:|
| Base rate | 0.161 | 0.500 | 0.1375 | 0.4524 | 0.163 | 0.051 |
| Buyer history rate | 0.323 | 0.680 | 0.1291 | 0.4487 | 0.512 | 0.159 |
| Logistic regression | 0.332 | 0.682 | 0.1288 | 0.4258 | 0.502 | 0.156 |
| LightGBM (calibrated) | 0.366 | 0.741 | 0.1222 | 0.4045 | 0.486 | 0.151 |

![Precision-recall](figures/has_time_extension-pr-curves.png)
![Calibration](figures/has_time_extension-calibration.png)
![Top features](figures/has_time_extension-importance.png)

## Model

LightGBM gradient boosting, early-stopped on the validation split by average precision,
with isotonic calibration fitted on the validation split only. Explanations are SHAP
contributions computed by LightGBM. Runs and the registered model are tracked in MLflow.

## Limitations

- Label noise: value additions recovered from text come from a keyword matcher with 84% precision on a manual check of 50 cases; some additions with unusual wording are missed.
- The size of each addition is not published by SECOP; the model predicts whether an addition happens, not how large it is.
- `estado_contrato` is not kept up to date, so closure is inferred from planned end dates. Contracts signed in the most recent months are only included once their planned end has passed, so the test period over-represents shorter contracts.
- Colombia only; data lag of about two days behind the SECOP portal.
- A high score reflects patterns of similar past contracts, not evidence about this one.

## Ethical considerations

- Natural-person suppliers are replaced by a salted hash before storage; their names and ID numbers never enter the dataset, figures or reports.
- Public views aggregate by entity, region and contract type; there are no supplier rankings.
- Outputs are framed as amendment risk signals and always shown with the disclaimer above.
