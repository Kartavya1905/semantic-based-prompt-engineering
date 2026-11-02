# Benchmark analysis

Sources: `critical_fix.jsonl`, `critical_triggers.jsonl` · 432 scored runs · 36 tickets · answer key `fa52bab0aed3` · split `dev`

Intervals are 95% cluster-bootstrap CIs: tickets are resampled, so repeated runs of one ticket count as one ticket.

## 1. Leaderboard

| variant                    | condition         |   tickets | all labels [95% CI]   | urgency [95% CI]   | critical caught   |   false critical |   under-triage |   escalation recall |   first-pass valid |
|:---------------------------|:------------------|----------:|:----------------------|:-------------------|:------------------|-----------------:|---------------:|--------------------:|-------------------:|
| v3_fewshot@1.0.0           | llama3.1:8b T=0.0 |        36 | 0.61 [0.44, 0.75]     | 0.81 [0.67, 0.92]  | 2.0/5             |             0.03 |           0.11 |                0.82 |               0.97 |
| v4_explicit_critical@1.0.0 | llama3.1:8b T=0.0 |        36 | 0.56 [0.39, 0.72]     | 0.78 [0.64, 0.92]  | 5.0/5             |             0.16 |           0.03 |                0.91 |               0.94 |
| v5_critical_example@1.0.0  | llama3.1:8b T=0.0 |        36 | 0.53 [0.36, 0.69]     | 0.78 [0.64, 0.92]  | 5.0/5             |             0.06 |           0.03 |                0.91 |               0.94 |
| v5_critical_example@1.0.1  | llama3.1:8b T=0.0 |        36 | 0.50 [0.33, 0.67]     | 0.75 [0.61, 0.89]  | 4.0/5             |             0.06 |           0.06 |                0.91 |               0.94 |
| v6_critical_triggers@2.0.0 | llama3.1:8b T=0.0 |        36 | 0.64 [0.47, 0.81]     | 0.86 [0.75, 0.97]  | 5.0/5             |             0.06 |           0.03 |                0.82 |               0.97 |
| v6_critical_triggers@2.1.0 | llama3.1:8b T=0.0 |        36 | 0.67 [0.50, 0.81]     | 0.92 [0.83, 1.00]  | 5.0/5             |             0.03 |           0.03 |                0.82 |               0.97 |
| v3_fewshot@1.0.0           | qwen2.5:7b T=0.0  |        36 | 0.53 [0.36, 0.69]     | 0.69 [0.53, 0.83]  | 0.0/5             |             0.03 |           0.17 |                0.91 |               1    |
| v4_explicit_critical@1.0.0 | qwen2.5:7b T=0.0  |        36 | 0.56 [0.39, 0.72]     | 0.72 [0.58, 0.86]  | 0.0/5             |             0.03 |           0.19 |                0.82 |               1    |
| v5_critical_example@1.0.0  | qwen2.5:7b T=0.0  |        36 | 0.58 [0.42, 0.75]     | 0.75 [0.61, 0.89]  | 0.0/5             |             0.03 |           0.17 |                0.73 |               1    |
| v5_critical_example@1.0.1  | qwen2.5:7b T=0.0  |        36 | 0.53 [0.36, 0.69]     | 0.72 [0.58, 0.86]  | 0.0/5             |             0.03 |           0.17 |                0.73 |               1    |
| v6_critical_triggers@2.0.0 | qwen2.5:7b T=0.0  |        36 | 0.56 [0.39, 0.72]     | 0.75 [0.61, 0.89]  | 5.0/5             |             0.06 |           0.06 |                0.82 |               0.97 |
| v6_critical_triggers@2.1.0 | qwen2.5:7b T=0.0  |        36 | 0.56 [0.39, 0.72]     | 0.78 [0.64, 0.92]  | 5.0/5             |             0.03 |           0.03 |                0.73 |               0.97 |

## 2. Paired comparisons

Same tickets, two variants. *broke / fixed* = tickets only the baseline / only the candidate got right (the only tickets McNemar uses). Holm corrects for running 18 tests at once; the verdict uses the Holm p-value at 0.05. *detectable* = the smallest true difference these tickets would catch 80% of the time: a smaller observed gap with no verdict means 'not measurable here', not 'none'.

| condition         | baseline → candidate                                    | measured on                                   |   tickets |   baseline |   candidate | difference [95% CI]   | broke / fixed   |   McNemar p |   Holm p | detectable (80% power)   | verdict                  |
|:------------------|:--------------------------------------------------------|:----------------------------------------------|----------:|-----------:|------------:|:----------------------|:----------------|------------:|---------:|:-------------------------|:-------------------------|
| llama3.1:8b T=0.0 | v3_fewshot@1.0.0 → v6_critical_triggers@2.1.0           | all labels, all tickets                       |        36 |       0.61 |        0.67 | +0.06 [-0.11, +0.22]  | 4 / 6           |       0.754 |        1 | ±0.25                    | no detectable difference |
| llama3.1:8b T=0.0 | v3_fewshot@1.0.0 → v6_critical_triggers@2.1.0           | urgency, all tickets                          |        36 |       0.81 |        0.92 | +0.11 [-0.03, +0.25]  | 2 / 6           |       0.289 |        1 | ±0.22                    | no detectable difference |
| llama3.1:8b T=0.0 | v3_fewshot@1.0.0 → v6_critical_triggers@2.1.0           | urgency, critical tickets (= critical recall) |         5 |       0.4  |        1    | +0.60 [+0.20, +1.00]  | 0 / 3           |       0.25  |        1 | ±0.97                    | no detectable difference |
| qwen2.5:7b T=0.0  | v3_fewshot@1.0.0 → v6_critical_triggers@2.1.0           | all labels, all tickets                       |        36 |       0.53 |        0.56 | +0.03 [-0.14, +0.19]  | 4 / 5           |       1     |        1 | ±0.23                    | no detectable difference |
| qwen2.5:7b T=0.0  | v3_fewshot@1.0.0 → v6_critical_triggers@2.1.0           | urgency, all tickets                          |        36 |       0.69 |        0.78 | +0.08 [-0.08, +0.25]  | 4 / 7           |       0.549 |        1 | ±0.26                    | no detectable difference |
| qwen2.5:7b T=0.0  | v3_fewshot@1.0.0 → v6_critical_triggers@2.1.0           | urgency, critical tickets (= critical recall) |         5 |       0    |        1    | +1.00 [+1.00, +1.00]  | 0 / 5           |       0.062 |        1 | ±1.00                    | no detectable difference |
| llama3.1:8b T=0.0 | v5_critical_example@1.0.1 → v6_critical_triggers@2.1.0  | all labels, all tickets                       |        36 |       0.5  |        0.67 | +0.17 [+0.03, +0.31]  | 1 / 7           |       0.07  |        1 | ±0.22                    | no detectable difference |
| llama3.1:8b T=0.0 | v5_critical_example@1.0.1 → v6_critical_triggers@2.1.0  | urgency, all tickets                          |        36 |       0.75 |        0.92 | +0.17 [+0.03, +0.31]  | 1 / 7           |       0.07  |        1 | ±0.22                    | no detectable difference |
| llama3.1:8b T=0.0 | v5_critical_example@1.0.1 → v6_critical_triggers@2.1.0  | urgency, critical tickets (= critical recall) |         5 |       0.8  |        1    | +0.20 [+0.00, +0.60]  | 0 / 1           |       1     |        1 | ±0.56                    | no detectable difference |
| qwen2.5:7b T=0.0  | v5_critical_example@1.0.1 → v6_critical_triggers@2.1.0  | all labels, all tickets                       |        36 |       0.53 |        0.56 | +0.03 [-0.14, +0.19]  | 4 / 5           |       1     |        1 | ±0.23                    | no detectable difference |
| qwen2.5:7b T=0.0  | v5_critical_example@1.0.1 → v6_critical_triggers@2.1.0  | urgency, all tickets                          |        36 |       0.72 |        0.78 | +0.06 [-0.11, +0.22]  | 4 / 6           |       0.754 |        1 | ±0.25                    | no detectable difference |
| qwen2.5:7b T=0.0  | v5_critical_example@1.0.1 → v6_critical_triggers@2.1.0  | urgency, critical tickets (= critical recall) |         5 |       0    |        1    | +1.00 [+1.00, +1.00]  | 0 / 5           |       0.062 |        1 | ±1.00                    | no detectable difference |
| llama3.1:8b T=0.0 | v6_critical_triggers@2.0.0 → v6_critical_triggers@2.1.0 | all labels, all tickets                       |        36 |       0.64 |        0.67 | +0.03 [-0.06, +0.11]  | 1 / 2           |       1     |        1 | ±0.13                    | no detectable difference |
| llama3.1:8b T=0.0 | v6_critical_triggers@2.0.0 → v6_critical_triggers@2.1.0 | urgency, all tickets                          |        36 |       0.86 |        0.92 | +0.06 [-0.06, +0.17]  | 1 / 3           |       0.625 |        1 | ±0.16                    | no detectable difference |
| llama3.1:8b T=0.0 | v6_critical_triggers@2.0.0 → v6_critical_triggers@2.1.0 | urgency, critical tickets (= critical recall) |         5 |       1    |        1    | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |
| qwen2.5:7b T=0.0  | v6_critical_triggers@2.0.0 → v6_critical_triggers@2.1.0 | all labels, all tickets                       |        36 |       0.56 |        0.56 | +0.00 [-0.11, +0.11]  | 2 / 2           |       1     |        1 | ±0.16                    | no detectable difference |
| qwen2.5:7b T=0.0  | v6_critical_triggers@2.0.0 → v6_critical_triggers@2.1.0 | urgency, all tickets                          |        36 |       0.75 |        0.78 | +0.03 [-0.06, +0.11]  | 1 / 2           |       1     |        1 | ±0.13                    | no detectable difference |
| qwen2.5:7b T=0.0  | v6_critical_triggers@2.0.0 → v6_critical_triggers@2.1.0 | urgency, critical tickets (= critical recall) |         5 |       1    |        1    | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |

## 3. Calibration of confidence_score

confidence_score claims P(category AND urgency correct). ECE 0 = perfectly calibrated; positive overconfidence = the model is surer than it is right.

| variant                    | condition         |   answers |   mean confidence |   actual accuracy |   overconfidence |   ECE |   Brier |
|:---------------------------|:------------------|----------:|------------------:|------------------:|-----------------:|------:|--------:|
| v3_fewshot@1.0.0           | llama3.1:8b T=0.0 |        36 |              0.84 |              0.69 |             0.15 |  0.23 |   0.244 |
| v4_explicit_critical@1.0.0 | llama3.1:8b T=0.0 |        36 |              0.85 |              0.64 |             0.21 |  0.26 |   0.274 |
| v5_critical_example@1.0.0  | llama3.1:8b T=0.0 |        36 |              0.85 |              0.61 |             0.24 |  0.25 |   0.271 |
| v5_critical_example@1.0.1  | llama3.1:8b T=0.0 |        36 |              0.85 |              0.58 |             0.26 |  0.31 |   0.297 |
| v6_critical_triggers@2.0.0 | llama3.1:8b T=0.0 |        36 |              0.82 |              0.69 |             0.12 |  0.18 |   0.219 |
| v6_critical_triggers@2.1.0 | llama3.1:8b T=0.0 |        36 |              0.83 |              0.72 |             0.11 |  0.18 |   0.206 |
| v3_fewshot@1.0.0           | qwen2.5:7b T=0.0  |        36 |              0.87 |              0.53 |             0.34 |  0.38 |   0.391 |
| v4_explicit_critical@1.0.0 | qwen2.5:7b T=0.0  |        36 |              0.89 |              0.56 |             0.33 |  0.33 |   0.366 |
| v5_critical_example@1.0.0  | qwen2.5:7b T=0.0  |        36 |              0.87 |              0.61 |             0.26 |  0.28 |   0.317 |
| v5_critical_example@1.0.1  | qwen2.5:7b T=0.0  |        36 |              0.88 |              0.56 |             0.33 |  0.33 |   0.354 |
| v6_critical_triggers@2.0.0 | qwen2.5:7b T=0.0  |        35 |              0.87 |              0.6  |             0.27 |  0.27 |   0.297 |
| v6_critical_triggers@2.1.0 | qwen2.5:7b T=0.0  |        35 |              0.88 |              0.63 |             0.25 |  0.25 |   0.288 |
