# Benchmark analysis

Sources: `dev_v2_comparison.jsonl` · 864 scored runs · 108 tickets · answer key `b51a88a20e01` · split `dev`

Intervals are 95% cluster-bootstrap CIs: tickets are resampled, so repeated runs of one ticket count as one ticket.

## 1. Leaderboard

| variant                    | condition         |   tickets | all labels [95% CI]   | urgency [95% CI]   | critical caught   |   false critical |   under-triage |   escalation recall |   first-pass valid |
|:---------------------------|:------------------|----------:|:----------------------|:-------------------|:------------------|-----------------:|---------------:|--------------------:|-------------------:|
| v3_fewshot@1.0.0           | llama3.1:8b T=0.0 |       108 | 0.53 [0.44, 0.62]     | 0.79 [0.71, 0.86]  | 7.0/20            |             0.02 |           0.14 |                0.74 |               0.97 |
| v5_critical_example@1.0.1  | llama3.1:8b T=0.0 |       108 | 0.58 [0.49, 0.68]     | 0.84 [0.77, 0.91]  | 18.0/20           |             0.05 |           0.03 |                0.91 |               0.97 |
| v6_critical_triggers@2.1.0 | llama3.1:8b T=0.0 |       108 | 0.63 [0.54, 0.72]     | 0.84 [0.77, 0.91]  | 18.0/20           |             0.08 |           0.06 |                0.83 |               0.97 |
| v6_critical_triggers@2.2.0 | llama3.1:8b T=0.0 |       108 | 0.65 [0.56, 0.74]     | 0.86 [0.79, 0.93]  | 18.0/20           |             0.07 |           0.06 |                0.83 |               0.95 |
| v3_fewshot@1.0.0           | qwen2.5:7b T=0.0  |       108 | 0.55 [0.45, 0.64]     | 0.71 [0.63, 0.80]  | 4.0/20            |             0.02 |           0.19 |                0.86 |               1    |
| v5_critical_example@1.0.1  | qwen2.5:7b T=0.0  |       108 | 0.54 [0.44, 0.63]     | 0.75 [0.67, 0.82]  | 5.0/20            |             0.02 |           0.17 |                0.49 |               1    |
| v6_critical_triggers@2.1.0 | qwen2.5:7b T=0.0  |       108 | 0.57 [0.48, 0.67]     | 0.78 [0.69, 0.85]  | 18.0/20           |             0.08 |           0.05 |                0.74 |               0.99 |
| v6_critical_triggers@2.2.0 | qwen2.5:7b T=0.0  |       108 | 0.56 [0.47, 0.66]     | 0.77 [0.69, 0.84]  | 18.0/20           |             0.08 |           0.07 |                0.74 |               0.99 |

## 2. Paired comparisons

Same tickets, two variants. *broke / fixed* = tickets only the baseline / only the candidate got right (the only tickets McNemar uses). Holm corrects for running 6 tests at once; the verdict uses the Holm p-value at 0.05. *detectable* = the smallest true difference these tickets would catch 80% of the time: a smaller observed gap with no verdict means 'not measurable here', not 'none'.

| condition         | baseline → candidate                                    | measured on                                   |   tickets |   baseline |   candidate | difference [95% CI]   | broke / fixed   |   McNemar p |   Holm p | detectable (80% power)   | verdict                  |
|:------------------|:--------------------------------------------------------|:----------------------------------------------|----------:|-----------:|------------:|:----------------------|:----------------|------------:|---------:|:-------------------------|:-------------------------|
| llama3.1:8b T=0.0 | v6_critical_triggers@2.1.0 → v6_critical_triggers@2.2.0 | all labels, all tickets                       |       108 |       0.63 |        0.65 | +0.02 [-0.02, +0.06]  | 1 / 3           |       0.625 |        1 | ±0.05                    | no detectable difference |
| llama3.1:8b T=0.0 | v6_critical_triggers@2.1.0 → v6_critical_triggers@2.2.0 | urgency, all tickets                          |       108 |       0.84 |        0.86 | +0.02 [+0.00, +0.05]  | 0 / 2           |       0.5   |        1 | ±0.04                    | no detectable difference |
| llama3.1:8b T=0.0 | v6_critical_triggers@2.1.0 → v6_critical_triggers@2.2.0 | urgency, critical tickets (= critical recall) |        20 |       0.9  |        0.9  | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |
| qwen2.5:7b T=0.0  | v6_critical_triggers@2.1.0 → v6_critical_triggers@2.2.0 | all labels, all tickets                       |       108 |       0.57 |        0.56 | -0.01 [-0.06, +0.03]  | 3 / 2           |       1     |        1 | ±0.06                    | no detectable difference |
| qwen2.5:7b T=0.0  | v6_critical_triggers@2.1.0 → v6_critical_triggers@2.2.0 | urgency, all tickets                          |       108 |       0.78 |        0.77 | -0.01 [-0.06, +0.03]  | 3 / 2           |       1     |        1 | ±0.06                    | no detectable difference |
| qwen2.5:7b T=0.0  | v6_critical_triggers@2.1.0 → v6_critical_triggers@2.2.0 | urgency, critical tickets (= critical recall) |        20 |       0.9  |        0.9  | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |

## 3. Calibration of confidence_score

confidence_score claims P(category AND urgency correct). ECE 0 = perfectly calibrated; positive overconfidence = the model is surer than it is right.

| variant                    | condition         |   answers |   mean confidence |   actual accuracy |   overconfidence |   ECE |   Brier |
|:---------------------------|:------------------|----------:|------------------:|------------------:|-----------------:|------:|--------:|
| v3_fewshot@1.0.0           | llama3.1:8b T=0.0 |       108 |              0.86 |              0.61 |             0.25 |  0.27 |   0.311 |
| v5_critical_example@1.0.1  | llama3.1:8b T=0.0 |       108 |              0.86 |              0.67 |             0.2  |  0.22 |   0.267 |
| v6_critical_triggers@2.1.0 | llama3.1:8b T=0.0 |       108 |              0.84 |              0.67 |             0.18 |  0.24 |   0.266 |
| v6_critical_triggers@2.2.0 | llama3.1:8b T=0.0 |       108 |              0.85 |              0.69 |             0.16 |  0.21 |   0.249 |
| v3_fewshot@1.0.0           | qwen2.5:7b T=0.0  |       108 |              0.89 |              0.56 |             0.33 |  0.33 |   0.358 |
| v5_critical_example@1.0.1  | qwen2.5:7b T=0.0  |       108 |              0.89 |              0.61 |             0.28 |  0.28 |   0.321 |
| v6_critical_triggers@2.1.0 | qwen2.5:7b T=0.0  |       107 |              0.89 |              0.64 |             0.25 |  0.25 |   0.291 |
| v6_critical_triggers@2.2.0 | qwen2.5:7b T=0.0  |       108 |              0.89 |              0.63 |             0.26 |  0.26 |   0.306 |
