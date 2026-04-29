# Batch 1 Anchor Retrieval Acceptance Report

## Scope

- Added `reference/exercises_ch15_30_anchor_retrieval.jsonl`.
- Added 90 Ch15-Ch30 anchor exercises.
- Did not add new procedure labels.
- Did not modify the generated eval banks.
- Updated JSONL ingestion so `reference/*_anchor_retrieval.jsonl` is indexed alongside `exercises_ch15.jsonl` through `exercises_ch30.jsonl`.
- Added an anchor-only procedure-label override so anchors use the existing procedure label embedded in `solution_text` instead of broad ontology cues.

## Anchor Counts

| Anchor class | Count |
|---|---:|
| known-sigma one-sample mean CI/test | 10 |
| unknown-sigma one-sample t CI/test | 10 |
| chi-square variance / standard deviation CI/test | 10 |
| two-sample known-sigma mean | 10 |
| pooled two-sample t interval/test | 10 |
| Welch two-sample t interval/test | 10 |
| paired difference interval/test | 10 |
| Fisher / NHST interpretation | 10 |
| Neyman-Pearson critical region / type I-II / power | 10 |
| Total | 90 |

## Index Build

Command:

```powershell
$env:HF_HOME='D:\4010Cheating Code\ve401_solver\.cache\huggingface'; $env:HF_HUB_DISABLE_SYMLINKS_WARNING='1'; python -m retriever.build_exercise_index --input reference --output data/exercise_index --backend dense
```

Result:

- `item_count`: 602
- Baseline no-anchor comparison index: 512 items
- Backend: `chroma_sentence_transformers`
- Model: `sentence-transformers/all-MiniLM-L6-v2`

## Eval Results

Consistent before/after comparison used dense retrieval with `pool_size=180` and `top_k=10` for top10 measurement.

| Suite | Before top1 | Before top5 | Before top10 | After top1 | After top5 | After top10 | Delta top1 | Delta top5 | Delta top10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| revised 300 | 160/300 | 210/300 | 218/300 | 171/300 | 214/300 | 232/300 | +11 | +4 | +14 |
| hard 100 | 83/100 | 90/100 | 94/100 | 82/100 | 90/100 | 94/100 | -1 | 0 | 0 |
| existing 115 | 105/115 | 111/115 | 112/115 | 106/115 | 111/115 | 112/115 | +1 | 0 | 0 |

Exact requested top-k 5 command results after Batch 1:

| Suite | top1 | top3 | top5 |
|---|---:|---:|---:|
| `eval/ve401_final_ch15_30_retrieval_eval_cases_300.jsonl` | 171/300 | 206/300 | 214/300 |
| `eval/ve401_final_hard_retrieval_eval_cases_100.jsonl` | 82/100 | 88/100 | 90/100 |
| `eval/retrieval_eval_cases.jsonl` | 106/115 | 110/115 | 111/115 |

## Remaining Miss Labels

Top expected labels among after top1 misses:

| Suite | Top remaining expected labels |
|---|---|
| revised 300 | `nhst_decision` 67, `chi_square_independence` 12, `variance_ratio_f_test` 9, `p_value_interpretation` 8, `chi_square_gof` 8, `pooled_t_test` 7, `welch_t_test` 7, `model_matrix_least_squares` 7 |
| hard 100 | `nhst_decision` 5, `one_sample_z_mean` 3, `wilcoxon_rank_sum` 3, `mean_interval` 2, `critical_region_power` 2, `sign_test` 2, `fisher_significance_test` 2, `welch_t_test` 2 |
| existing 115 | `slope_t_test` 2, `regression_prediction_interval` 2, `wilcoxon_signed_rank` 1, `one_proportion_z` 1, `fisher_correlation_z` 1, `model_selection_indicator_press` 1, `variance_ratio_f_test` 1 |

Top labels still absent from after top10:

| Suite | Top labels absent from top10 |
|---|---|
| revised 300 | `nhst_decision` 33, `variance_ratio_f_test` 8, `model_matrix_least_squares` 6, `pooled_t_test` 5, `chi_square_variance` 4, `one_proportion_z` 4, `welch_t_test` 4 |
| hard 100 | `nhst_decision` 2, plus one each for `one_sample_z_mean`, `mean_interval`, `wilcoxon_rank_sum`, `regression_prediction_interval`, `slope_t_test`, `overall_or_partial_f_test`, `model_matrix_least_squares` |
| existing 115 | `fisher_correlation_z` 1, `variance_ratio_f_test` 1, `slope_t_test` 1 |

## Diagnosis

- Revised 300 improved on top1, top5, and top10, so Batch 1 anchors are being ingested and improving coverage.
- Hard 100 did not meet the target `top1 >= 86, top5 >= 91`; after Batch 1 it is `top1=82, top5=90`.
- Existing 115 meets the requested floor of at least 105 top1 with `106/115`.
- The hard-suite regression is primarily a rerank / dense-neighbor competition issue, not an anchor-ingestion failure: several misses retrieve the new anchor family but rank a nearby sibling label above the expected one, for example `two_sample_z_mean` above expected `one_sample_z_mean` in known-sigma hard cases.
- `nhst_decision` remains the largest miss class. Many retrieved hits expose `fisher_significance_test` or `p_value_interpretation`, so this is mostly a procedure-vs-concept/rerank distinction rather than missing Ch15-Ch30 coverage.
- `variance_ratio_f_test`, `model_matrix_least_squares`, and regression labels absent from top10 are coverage and feature-extractor issues outside Batch 1's requested anchor focus.
- Some one-sample mean vs variance misses still show `chi_square_variance` competing with `one_sample_t_mean`; this points to feature extraction and rerank separation of target parameter wording, not lack of anchor file ingestion.

## Acceptance Status

- Anchor count and schema: pass.
- Anchor file isolated from eval banks: pass.
- Builder ingestion of `*_anchor_retrieval.jsonl`: pass.
- Revised 300 improvement: pass.
- Existing 115 top1 floor: pass.
- Hard 100 target: fail, because top1 is 82 and top5 is 90.

## Follow-Up Recommendation

Batch 2 should include regression anchors only after fixing rerank/feature separation for Batch 1-adjacent labels. The immediate next high-value work is not adding more procedures; it is:

1. Improve rerank separation for `nhst_decision` vs `fisher_significance_test` vs `p_value_interpretation`.
2. Add targeted anchors or feature cues for `variance_ratio_f_test`.
3. Add Batch 2 regression anchors for Ch25-Ch30 only after the above, focusing on `model_matrix_least_squares`, `overall_or_partial_f_test`, `slope_t_test`, and `regression_prediction_interval`.

## Targeted Repair Pass

This pass executed the three-step plan with rollback protection:

1. Added small feature-extractor cues for variance-ratio, GOF/independence, regression prediction, matrix least squares, and regression F-test wording.
2. Tested stronger rerank penalties and Batch 2 anchors.
3. Rolled back the unsafe parts because they degraded hard-suite retrieval.

Rolled-back items:

- `reference/exercises_ch15_30_batch2_anchor_retrieval.jsonl` with 80 anchors was tested and removed. It improved revised 300 but polluted hard 100.
- Broad diagnostic/assumption overrides were reverted because they made regression diagnostics outrank slope/matrix labels.
- New hard rerank penalties were reverted because the measured drop was caused by feature/index changes, not scoring.
- Over-broad cue phrases `independent of` and `estimate .*sigma squared` / `estimate .*error variance` were removed after they caused false positives.

Final retained changes:

- Safer additional cues in `retriever/extract_features.py`.
- Expanded anchor procedure-family mapping for existing labels only.
- No new procedure labels.
- No generated eval bank changes.
- No Batch 2 anchor file retained.

### Final Index

Command:

```powershell
$env:HF_HOME='D:\4010Cheating Code\ve401_solver\.cache\huggingface'; $env:HF_HUB_DISABLE_SYMLINKS_WARNING='1'; python -m retriever.build_exercise_index --input reference --output data/exercise_index --backend dense
```

Result:

- `item_count`: 602
- Backend: `chroma_sentence_transformers`
- Batch 1 anchors retained: 90
- Batch 2 anchors retained: 0

### Targeted Repair Eval Results

Before is the pre-pass state after Batch 1 and earlier targeted fixes. After is the final retained state after rollback.

| Suite | Before top1 | Before top5 | Before top10 | After top1 | After top5 | After top10 | Delta top1 | Delta top5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| revised 300 | 180/300 | 226/300 | 237/300 | 181/300 | 227/300 | 238/300 | +1 | +1 |
| hard 100 | 82/100 | 90/100 | not saved | 82/100 | 90/100 | 93/100 | 0 | 0 |
| existing 115 | 106/115 | 111/115 | 112/115 | 106/115 | 111/115 | 112/115 | 0 | 0 |

Exact requested top-k 5 command results after rollback:

| Suite | top1 | top3 | top5 |
|---|---:|---:|---:|
| `eval/ve401_final_ch15_30_retrieval_eval_cases_300.jsonl` | 181/300 | 215/300 | 227/300 |
| `eval/ve401_final_hard_retrieval_eval_cases_100.jsonl` | 82/100 | 88/100 | 90/100 |
| `eval/retrieval_eval_cases.jsonl` | 106/115 | 110/115 | 111/115 |

### Remaining Miss Labels After Repair

Top revised 300 top1 miss labels:

| Label | Count |
|---|---:|
| `nhst_decision` | 63 |
| `chi_square_independence` | 12 |
| `p_value_interpretation` | 9 |
| `variance_ratio_f_test` | 8 |
| `chi_square_gof` | 8 |
| `welch_t_test` | 7 |
| `model_matrix_least_squares` | 7 |
| `pooled_t_test` | 6 |
| `paired_t` | 6 |
| `fisher_significance_test` | 6 |

Top revised 300 labels still absent from top10:

| Label | Count |
|---|---:|
| `nhst_decision` | 29 |
| `variance_ratio_f_test` | 7 |
| `model_matrix_least_squares` | 6 |
| `pooled_t_test` | 5 |
| `chi_square_variance` | 4 |
| `paired_t` | 4 |
| `welch_t_test` | 4 |
| `overall_or_partial_f_test` | 4 |

### Diagnosis After Repair

- Revised 300 is still dominated by `nhst_decision` misses. Many cases retrieve Fisher/p-value/concrete-test neighbors, so this is mainly a rerank/procedure-vs-concept distinction.
- `variance_ratio_f_test` and `model_matrix_least_squares` remain absent from top10 often enough to indicate anchor coverage plus feature extraction gaps.
- Batch 2 anchors helped revised 300 but hurt hard 100, which confirms that blindly adding dense anchors can over-insure one suite and pollute harder contrastive cases.
- The safe next step is not a large anchor dump. It should be a smaller, contrastive anchor batch with paired positive/negative wording, especially for NHST-vs-Fisher-vs-NP and regression matrix-vs-F-test-vs-prediction.

## Contrastive Anchor Phases

Baseline for this phase sequence:

| Suite | top1 | top5 | top10 |
|---|---:|---:|---:|
| revised 300 | 181/300 | 227/300 | 238/300 |
| hard 100 | 82/100 | 90/100 | 93/100 |
| existing 115 | 106/115 | 111/115 | 112/115 |

### Phase 1: NHST / Fisher / p-value

Added `reference/exercises_ch16_18_contrastive_anchor_retrieval.jsonl`.

Anchor counts:

| Label focus | Count |
|---|---:|
| `nhst_decision` | 8 |
| `fisher_significance_test` | 6 |
| `p_value_interpretation` concept with Fisher procedure | 5 |
| `critical_region_power` | 5 |
| Total | 24 |

Result:

| Suite | top1 | top3 | top5 | top10 |
|---|---:|---:|---:|---:|
| revised 300 | 183/300 | 217/300 | 228/300 | 239/300 |
| hard 100 | 82/100 | 89/100 | 91/100 | 93/100 |
| existing 115 | 106/115 | 110/115 | 111/115 | 112/115 |

Decision: keep.

Reason:

- revised 300 improved top1 and top5.
- hard 100 top5 improved by 1.
- existing 115 was unchanged.

### Phase 2: variance_ratio_f_test

Tested `reference/exercises_ch20_variance_ratio_contrastive_anchor_retrieval.jsonl`.

Two variants were tested:

| Variant | Count | revised 300 | hard 100 | existing 115 | Decision |
|---|---:|---|---|---|---|
| positive + negative contrastive anchors | 14 | 184/300 top1, 227/300 top5 | 82/100 top1, 91/100 top5 | 106/115 top1, 111/115 top5 | rollback |
| positive-only anchors | 8 | 184/300 top1, 227/300 top5 | 82/100 top1, 91/100 top5 | 106/115 top1, 111/115 top5 | rollback |

Decision: rollback.

Reason:

- Compared with Phase 1, revised top5 fell from 228 to 227.
- This triggers the per-batch rollback rule even though hard 100 did not degrade.

### Phase 3: model_matrix_least_squares

Tested `reference/exercises_ch29_model_matrix_contrastive_anchor_retrieval.jsonl`.

Anchor count:

| Label focus | Count |
|---|---:|
| `model_matrix_least_squares` | 12 |

Result before rollback:

| Suite | top1 | top3 | top5 | top10 |
|---|---:|---:|---:|---:|
| revised 300 | 182/300 | 217/300 | 228/300 | 240/300 |
| hard 100 | 82/100 | 89/100 | 91/100 | not retained |
| existing 115 | 106/115 | 110/115 | 111/115 | not retained |

Matrix-specific result:

| Metric | Before Phase 3 | After Phase 3 |
|---|---:|---:|
| `model_matrix_least_squares` top1 misses | 7 | 7 |
| `model_matrix_least_squares` top10 absent | 6 | 5 |

Decision: rollback.

Reason:

- Matrix top10 absence improved only from 6 to 5, not near the target `<= 2`.
- revised top1 dropped from Phase 1's 183 to 182.
- Phase 4 was not run because Phase 3 did not stabilize.

### Final Phase State

Retained:

- `reference/exercises_ch16_18_contrastive_anchor_retrieval.jsonl`

Rolled back:

- `reference/exercises_ch20_variance_ratio_contrastive_anchor_retrieval.jsonl`
- `reference/exercises_ch29_model_matrix_contrastive_anchor_retrieval.jsonl`

Final index:

- `item_count`: 626
- Batch 1 anchors: 90
- Phase 1 contrastive anchors: 24
- Total retained anchors: 114

Final eval:

| Suite | top1 | top3 | top5 | top10 |
|---|---:|---:|---:|---:|
| revised 300 | 183/300 | 217/300 | 228/300 | 239/300 |
| hard 100 | 82/100 | 89/100 | 91/100 | 93/100 |
| existing 115 | 106/115 | 110/115 | 111/115 | 112/115 |

Final remaining revised 300 top1 miss labels:

| Label | Count |
|---|---:|
| `nhst_decision` | 63 |
| `chi_square_independence` | 12 |
| `variance_ratio_f_test` | 8 |
| `chi_square_gof` | 8 |
| `p_value_interpretation` | 7 |
| `welch_t_test` | 7 |
| `model_matrix_least_squares` | 7 |
| `pooled_t_test` | 6 |
| `paired_t` | 6 |
| `r_squared_interpretation` | 5 |

Final revised 300 labels absent from top10:

| Label | Count |
|---|---:|
| `nhst_decision` | 29 |
| `variance_ratio_f_test` | 7 |
| `model_matrix_least_squares` | 6 |
| `pooled_t_test` | 5 |
| `chi_square_variance` | 4 |
| `paired_t` | 4 |
| `welch_t_test` | 4 |
| `overall_or_partial_f_test` | 4 |

### Updated Recommendation

- Keep Phase 1.
- Do not retry variance-ratio or matrix anchors as dense-only additions. The failed Phase 2/3 tests show dense anchors alone move the wrong neighbors as much as the target label.
- Next attempt should be extractor-level diagnostics, not anchor dump:
  - Add explicit query-side feature for "two independent variances" only when two-sample variance wording is present.
  - Add matrix-specific cues that do not also match generic regression output.
  - For `nhst_decision`, add a lightweight rerank boost for exact decision wording instead of more anchors, because top10 absent remains high but hard 100 already benefits from Phase 1.
