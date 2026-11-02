# Benchmark analysis

Sources: `dev_temperature_sweep.jsonl` · 2160 scored runs · 36 tickets · answer key `fa52bab0aed3` · split `dev`

Intervals are 95% cluster-bootstrap CIs: tickets are resampled, so repeated runs of one ticket count as one ticket.

## 1. Leaderboard

| variant               | condition         |   tickets | all labels [95% CI]   | urgency [95% CI]   | critical caught   |   false critical |   under-triage |   escalation recall |   first-pass valid |
|:----------------------|:------------------|----------:|:----------------------|:-------------------|:------------------|-----------------:|---------------:|--------------------:|-------------------:|
| v1_baseline@1.0.0     | llama3.1:8b T=0.0 |        36 | 0.39 [0.25, 0.56]     | 0.78 [0.64, 0.92]  | 2.0/5             |             0.1  |           0.14 |                0.82 |               0.97 |
| v2_policy_first@1.0.0 | llama3.1:8b T=0.0 |        36 | 0.44 [0.28, 0.61]     | 0.72 [0.58, 0.86]  | 2.0/5             |             0.1  |           0.11 |                0.82 |               0.97 |
| v3_fewshot@1.0.0      | llama3.1:8b T=0.0 |        36 | 0.58 [0.42, 0.75]     | 0.78 [0.64, 0.89]  | 1.0/5             |             0.03 |           0.14 |                0.82 |               0.97 |
| v1_baseline@1.0.0     | llama3.1:8b T=0.3 |        36 | 0.39 [0.26, 0.53]     | 0.73 [0.59, 0.86]  | 1.0/5             |             0.1  |           0.15 |                0.85 |               0.96 |
| v2_policy_first@1.0.0 | llama3.1:8b T=0.3 |        36 | 0.44 [0.29, 0.59]     | 0.70 [0.56, 0.83]  | 1.7/5             |             0.1  |           0.12 |                0.82 |               0.97 |
| v3_fewshot@1.0.0      | llama3.1:8b T=0.3 |        36 | 0.56 [0.41, 0.70]     | 0.73 [0.58, 0.86]  | 1.0/5             |             0.05 |           0.14 |                0.82 |               0.97 |
| v1_baseline@1.0.0     | llama3.1:8b T=0.7 |        36 | 0.45 [0.31, 0.60]     | 0.76 [0.63, 0.87]  | 1.7/5             |             0.05 |           0.15 |                0.88 |               0.95 |
| v2_policy_first@1.0.0 | llama3.1:8b T=0.7 |        36 | 0.39 [0.25, 0.54]     | 0.68 [0.54, 0.81]  | 1.3/5             |             0.09 |           0.16 |                0.79 |               0.96 |
| v3_fewshot@1.0.0      | llama3.1:8b T=0.7 |        36 | 0.55 [0.41, 0.69]     | 0.80 [0.68, 0.90]  | 2.0/5             |             0.03 |           0.11 |                0.79 |               0.99 |
| v1_baseline@1.0.0     | llama3.1:8b T=1.0 |        36 | 0.48 [0.35, 0.62]     | 0.81 [0.69, 0.91]  | 2.0/5             |             0.03 |           0.12 |                0.73 |               0.98 |
| v2_policy_first@1.0.0 | llama3.1:8b T=1.0 |        36 | 0.35 [0.22, 0.49]     | 0.68 [0.55, 0.80]  | 1.7/5             |             0.13 |           0.15 |                0.85 |               0.98 |
| v3_fewshot@1.0.0      | llama3.1:8b T=1.0 |        36 | 0.50 [0.37, 0.63]     | 0.71 [0.58, 0.82]  | 1.3/5             |             0.04 |           0.16 |                0.76 |               1    |
| v1_baseline@1.0.0     | qwen2.5:7b T=0.0  |        36 | 0.50 [0.33, 0.67]     | 0.64 [0.47, 0.78]  | 0.0/5             |             0    |           0.33 |                0.73 |               1    |
| v2_policy_first@1.0.0 | qwen2.5:7b T=0.0  |        36 | 0.44 [0.28, 0.61]     | 0.64 [0.47, 0.78]  | 0.0/5             |             0    |           0.31 |                0.73 |               1    |
| v3_fewshot@1.0.0      | qwen2.5:7b T=0.0  |        36 | 0.50 [0.33, 0.67]     | 0.67 [0.50, 0.81]  | 0.0/5             |             0.03 |           0.19 |                0.91 |               1    |
| v1_baseline@1.0.0     | qwen2.5:7b T=0.3  |        36 | 0.52 [0.36, 0.68]     | 0.66 [0.50, 0.81]  | 0.0/5             |             0    |           0.31 |                0.76 |               1    |
| v2_policy_first@1.0.0 | qwen2.5:7b T=0.3  |        36 | 0.45 [0.30, 0.61]     | 0.65 [0.50, 0.79]  | 0.0/5             |             0    |           0.31 |                0.76 |               1    |
| v3_fewshot@1.0.0      | qwen2.5:7b T=0.3  |        36 | 0.53 [0.36, 0.69]     | 0.69 [0.53, 0.82]  | 0.0/5             |             0.03 |           0.17 |                0.91 |               1    |
| v1_baseline@1.0.0     | qwen2.5:7b T=0.7  |        36 | 0.54 [0.39, 0.69]     | 0.68 [0.54, 0.81]  | 0.0/5             |             0.01 |           0.29 |                0.79 |               1    |
| v2_policy_first@1.0.0 | qwen2.5:7b T=0.7  |        36 | 0.46 [0.31, 0.61]     | 0.65 [0.51, 0.79]  | 0.0/5             |             0.01 |           0.28 |                0.76 |               1    |
| v3_fewshot@1.0.0      | qwen2.5:7b T=0.7  |        36 | 0.53 [0.37, 0.69]     | 0.68 [0.53, 0.81]  | 0.0/5             |             0.04 |           0.17 |                0.88 |               1    |
| v1_baseline@1.0.0     | qwen2.5:7b T=1.0  |        36 | 0.47 [0.31, 0.63]     | 0.61 [0.46, 0.76]  | 0.0/5             |             0    |           0.33 |                0.79 |               1    |
| v2_policy_first@1.0.0 | qwen2.5:7b T=1.0  |        36 | 0.50 [0.36, 0.64]     | 0.69 [0.56, 0.81]  | 0.0/5             |             0.02 |           0.25 |                0.76 |               1    |
| v3_fewshot@1.0.0      | qwen2.5:7b T=1.0  |        36 | 0.56 [0.41, 0.70]     | 0.70 [0.56, 0.83]  | 0.0/5             |             0.04 |           0.17 |                0.88 |               1    |

## 2. Paired comparisons

Same tickets, two variants. *broke / fixed* = tickets only the baseline / only the candidate got right (the only tickets McNemar uses). Holm corrects for running 48 tests at once; the verdict uses the Holm p-value at 0.05. *detectable* = the smallest true difference these tickets would catch 80% of the time: a smaller observed gap with no verdict means 'not measurable here', not 'none'.

| condition         | baseline → candidate                      | measured on                                   |   tickets |   baseline |   candidate | difference [95% CI]   | broke / fixed   |   McNemar p |   Holm p | detectable (80% power)   | verdict                  |
|:------------------|:------------------------------------------|:----------------------------------------------|----------:|-----------:|------------:|:----------------------|:----------------|------------:|---------:|:-------------------------|:-------------------------|
| llama3.1:8b T=0.0 | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | all labels, all tickets                       |        36 |       0.39 |        0.44 | +0.06 [-0.06, +0.17]  | 1 / 3           |       0.625 |        1 | ±0.16                    | no detectable difference |
| llama3.1:8b T=0.0 | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, all tickets                          |        36 |       0.78 |        0.72 | -0.06 [-0.17, +0.06]  | 3 / 1           |       0.625 |        1 | ±0.16                    | no detectable difference |
| llama3.1:8b T=0.0 | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, critical tickets (= critical recall) |         5 |       0.4  |        0.4  | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |
| llama3.1:8b T=0.3 | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | all labels, all tickets                       |        36 |       0.39 |        0.44 | +0.05 [-0.06, +0.15]  | 2 / 3           |       1     |        1 | ±0.17                    | no detectable difference |
| llama3.1:8b T=0.3 | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, all tickets                          |        36 |       0.73 |        0.7  | -0.03 [-0.11, +0.05]  | 2 / 1           |       1     |        1 | ±0.13                    | no detectable difference |
| llama3.1:8b T=0.3 | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, critical tickets (= critical recall) |         5 |       0.2  |        0.33 | +0.13 [+0.00, +0.27]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |
| llama3.1:8b T=0.7 | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | all labels, all tickets                       |        36 |       0.45 |        0.39 | -0.06 [-0.20, +0.06]  | 7 / 3           |       0.344 |        1 | ±0.25                    | no detectable difference |
| llama3.1:8b T=0.7 | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, all tickets                          |        36 |       0.76 |        0.68 | -0.08 [-0.19, +0.01]  | 4 / 1           |       0.375 |        1 | ±0.17                    | no detectable difference |
| llama3.1:8b T=0.7 | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, critical tickets (= critical recall) |         5 |       0.33 |        0.27 | -0.07 [-0.40, +0.20]  | 1 / 0           |       1     |        1 | ±0.56                    | no detectable difference |
| llama3.1:8b T=1.0 | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | all labels, all tickets                       |        36 |       0.48 |        0.35 | -0.13 [-0.23, -0.03]  | 5 / 0           |       0.062 |        1 | ±0.17                    | no detectable difference |
| llama3.1:8b T=1.0 | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, all tickets                          |        36 |       0.81 |        0.68 | -0.13 [-0.22, -0.04]  | 5 / 1           |       0.219 |        1 | ±0.19                    | no detectable difference |
| llama3.1:8b T=1.0 | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, critical tickets (= critical recall) |         5 |       0.4  |        0.33 | -0.07 [-0.27, +0.13]  | 1 / 0           |       1     |        1 | ±0.56                    | no detectable difference |
| qwen2.5:7b T=0.0  | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | all labels, all tickets                       |        36 |       0.5  |        0.44 | -0.06 [-0.17, +0.06]  | 3 / 1           |       0.625 |        1 | ±0.16                    | no detectable difference |
| qwen2.5:7b T=0.0  | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, all tickets                          |        36 |       0.64 |        0.64 | +0.00 [-0.08, +0.08]  | 1 / 1           |       1     |        1 | ±0.11                    | no detectable difference |
| qwen2.5:7b T=0.0  | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, critical tickets (= critical recall) |         5 |       0    |        0    | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |
| qwen2.5:7b T=0.3  | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | all labels, all tickets                       |        36 |       0.52 |        0.45 | -0.06 [-0.17, +0.02]  | 4 / 0           |       0.125 |        1 | ±0.16                    | no detectable difference |
| qwen2.5:7b T=0.3  | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, all tickets                          |        36 |       0.66 |        0.65 | -0.01 [-0.07, +0.05]  | 2 / 0           |       0.5   |        1 | ±0.11                    | no detectable difference |
| qwen2.5:7b T=0.3  | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, critical tickets (= critical recall) |         5 |       0    |        0    | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |
| qwen2.5:7b T=0.7  | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | all labels, all tickets                       |        36 |       0.54 |        0.46 | -0.07 [-0.17, +0.01]  | 3 / 1           |       0.625 |        1 | ±0.16                    | no detectable difference |
| qwen2.5:7b T=0.7  | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, all tickets                          |        36 |       0.68 |        0.65 | -0.03 [-0.08, +0.02]  | 1 / 0           |       1     |        1 | ±0.08                    | no detectable difference |
| qwen2.5:7b T=0.7  | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, critical tickets (= critical recall) |         5 |       0    |        0    | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |
| qwen2.5:7b T=1.0  | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | all labels, all tickets                       |        36 |       0.47 |        0.5  | +0.03 [-0.07, +0.13]  | 3 / 3           |       1     |        1 | ±0.19                    | no detectable difference |
| qwen2.5:7b T=1.0  | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, all tickets                          |        36 |       0.61 |        0.69 | +0.07 [+0.01, +0.15]  | 1 / 3           |       0.625 |        1 | ±0.16                    | no detectable difference |
| qwen2.5:7b T=1.0  | v1_baseline@1.0.0 → v2_policy_first@1.0.0 | urgency, critical tickets (= critical recall) |         5 |       0    |        0    | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |
| llama3.1:8b T=0.0 | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | all labels, all tickets                       |        36 |       0.39 |        0.58 | +0.19 [+0.03, +0.36]  | 2 / 9           |       0.065 |        1 | ±0.26                    | no detectable difference |
| llama3.1:8b T=0.0 | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, all tickets                          |        36 |       0.78 |        0.78 | +0.00 [-0.11, +0.11]  | 2 / 2           |       1     |        1 | ±0.16                    | no detectable difference |
| llama3.1:8b T=0.0 | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, critical tickets (= critical recall) |         5 |       0.4  |        0.2  | -0.20 [-0.60, +0.00]  | 1 / 0           |       1     |        1 | ±0.56                    | no detectable difference |
| llama3.1:8b T=0.3 | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | all labels, all tickets                       |        36 |       0.39 |        0.56 | +0.17 [+0.04, +0.30]  | 3 / 8           |       0.227 |        1 | ±0.26                    | no detectable difference |
| llama3.1:8b T=0.3 | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, all tickets                          |        36 |       0.73 |        0.73 | +0.00 [-0.07, +0.07]  | 2 / 2           |       1     |        1 | ±0.16                    | no detectable difference |
| llama3.1:8b T=0.3 | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, critical tickets (= critical recall) |         5 |       0.2  |        0.2  | +0.00 [-0.40, +0.40]  | 1 / 1           |       1     |        1 | ±0.79                    | no detectable difference |
| llama3.1:8b T=0.7 | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | all labels, all tickets                       |        36 |       0.45 |        0.55 | +0.09 [-0.03, +0.22]  | 3 / 4           |       1     |        1 | ±0.21                    | no detectable difference |
| llama3.1:8b T=0.7 | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, all tickets                          |        36 |       0.76 |        0.8  | +0.04 [-0.06, +0.14]  | 3 / 3           |       1     |        1 | ±0.19                    | no detectable difference |
| llama3.1:8b T=0.7 | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, critical tickets (= critical recall) |         5 |       0.33 |        0.4  | +0.07 [-0.40, +0.60]  | 1 / 1           |       1     |        1 | ±0.79                    | no detectable difference |
| llama3.1:8b T=1.0 | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | all labels, all tickets                       |        36 |       0.48 |        0.5  | +0.02 [-0.10, +0.13]  | 4 / 6           |       0.754 |        1 | ±0.25                    | no detectable difference |
| llama3.1:8b T=1.0 | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, all tickets                          |        36 |       0.81 |        0.71 | -0.09 [-0.19, -0.00]  | 5 / 2           |       0.453 |        1 | ±0.21                    | no detectable difference |
| llama3.1:8b T=1.0 | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, critical tickets (= critical recall) |         5 |       0.4  |        0.27 | -0.13 [-0.60, +0.33]  | 2 / 1           |       1     |        1 | ±0.97                    | no detectable difference |
| qwen2.5:7b T=0.0  | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | all labels, all tickets                       |        36 |       0.5  |        0.5  | +0.00 [-0.17, +0.17]  | 5 / 5           |       1     |        1 | ±0.25                    | no detectable difference |
| qwen2.5:7b T=0.0  | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, all tickets                          |        36 |       0.64 |        0.67 | +0.03 [-0.14, +0.19]  | 4 / 5           |       1     |        1 | ±0.23                    | no detectable difference |
| qwen2.5:7b T=0.0  | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, critical tickets (= critical recall) |         5 |       0    |        0    | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |
| qwen2.5:7b T=0.3  | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | all labels, all tickets                       |        36 |       0.52 |        0.53 | +0.01 [-0.16, +0.19]  | 5 / 5           |       1     |        1 | ±0.25                    | no detectable difference |
| qwen2.5:7b T=0.3  | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, all tickets                          |        36 |       0.66 |        0.69 | +0.03 [-0.13, +0.19]  | 4 / 5           |       1     |        1 | ±0.23                    | no detectable difference |
| qwen2.5:7b T=0.3  | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, critical tickets (= critical recall) |         5 |       0    |        0    | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |
| qwen2.5:7b T=0.7  | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | all labels, all tickets                       |        36 |       0.54 |        0.53 | -0.01 [-0.15, +0.12]  | 4 / 5           |       1     |        1 | ±0.23                    | no detectable difference |
| qwen2.5:7b T=0.7  | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, all tickets                          |        36 |       0.68 |        0.68 | +0.00 [-0.13, +0.13]  | 5 / 5           |       1     |        1 | ±0.25                    | no detectable difference |
| qwen2.5:7b T=0.7  | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, critical tickets (= critical recall) |         5 |       0    |        0    | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |
| qwen2.5:7b T=1.0  | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | all labels, all tickets                       |        36 |       0.47 |        0.56 | +0.08 [-0.06, +0.23]  | 3 / 7           |       0.344 |        1 | ±0.25                    | no detectable difference |
| qwen2.5:7b T=1.0  | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, all tickets                          |        36 |       0.61 |        0.7  | +0.09 [-0.05, +0.24]  | 3 / 7           |       0.344 |        1 | ±0.25                    | no detectable difference |
| qwen2.5:7b T=1.0  | v1_baseline@1.0.0 → v3_fewshot@1.0.0      | urgency, critical tickets (= critical recall) |         5 |       0    |        0    | +0.00 [+0.00, +0.00]  | 0 / 0           |       1     |        1 | n/a                      | no detectable difference |

## 3. Calibration of confidence_score

confidence_score claims P(category AND urgency correct). ECE 0 = perfectly calibrated; positive overconfidence = the model is surer than it is right.

| variant               | condition         |   answers |   mean confidence |   actual accuracy |   overconfidence |   ECE |   Brier |
|:----------------------|:------------------|----------:|------------------:|------------------:|-----------------:|------:|--------:|
| v1_baseline@1.0.0     | llama3.1:8b T=0.0 |        36 |              0.84 |              0.53 |             0.31 |  0.31 |   0.324 |
| v2_policy_first@1.0.0 | llama3.1:8b T=0.0 |        36 |              0.85 |              0.58 |             0.26 |  0.26 |   0.306 |
| v3_fewshot@1.0.0      | llama3.1:8b T=0.0 |        36 |              0.84 |              0.67 |             0.18 |  0.26 |   0.266 |
| v1_baseline@1.0.0     | llama3.1:8b T=0.3 |       108 |              0.85 |              0.51 |             0.34 |  0.34 |   0.348 |
| v2_policy_first@1.0.0 | llama3.1:8b T=0.3 |       108 |              0.84 |              0.57 |             0.27 |  0.27 |   0.309 |
| v3_fewshot@1.0.0      | llama3.1:8b T=0.3 |       108 |              0.85 |              0.63 |             0.22 |  0.25 |   0.289 |
| v1_baseline@1.0.0     | llama3.1:8b T=0.7 |       108 |              0.82 |              0.51 |             0.31 |  0.33 |   0.36  |
| v2_policy_first@1.0.0 | llama3.1:8b T=0.7 |       108 |              0.82 |              0.51 |             0.31 |  0.31 |   0.343 |
| v3_fewshot@1.0.0      | llama3.1:8b T=0.7 |       108 |              0.84 |              0.63 |             0.21 |  0.23 |   0.282 |
| v1_baseline@1.0.0     | llama3.1:8b T=1.0 |       108 |              0.82 |              0.59 |             0.23 |  0.23 |   0.277 |
| v2_policy_first@1.0.0 | llama3.1:8b T=1.0 |       108 |              0.84 |              0.46 |             0.37 |  0.37 |   0.389 |
| v3_fewshot@1.0.0      | llama3.1:8b T=1.0 |       108 |              0.84 |              0.57 |             0.27 |  0.28 |   0.306 |
| v1_baseline@1.0.0     | qwen2.5:7b T=0.0  |        36 |              0.87 |              0.5  |             0.37 |  0.37 |   0.382 |
| v2_policy_first@1.0.0 | qwen2.5:7b T=0.0  |        36 |              0.88 |              0.47 |             0.41 |  0.41 |   0.405 |
| v3_fewshot@1.0.0      | qwen2.5:7b T=0.0  |        36 |              0.87 |              0.5  |             0.37 |  0.41 |   0.413 |
| v1_baseline@1.0.0     | qwen2.5:7b T=0.3  |       108 |              0.88 |              0.52 |             0.36 |  0.36 |   0.372 |
| v2_policy_first@1.0.0 | qwen2.5:7b T=0.3  |       108 |              0.87 |              0.48 |             0.39 |  0.39 |   0.387 |
| v3_fewshot@1.0.0      | qwen2.5:7b T=0.3  |       108 |              0.87 |              0.53 |             0.35 |  0.36 |   0.386 |
| v1_baseline@1.0.0     | qwen2.5:7b T=0.7  |       108 |              0.87 |              0.54 |             0.33 |  0.35 |   0.364 |
| v2_policy_first@1.0.0 | qwen2.5:7b T=0.7  |       108 |              0.87 |              0.49 |             0.38 |  0.38 |   0.377 |
| v3_fewshot@1.0.0      | qwen2.5:7b T=0.7  |       108 |              0.86 |              0.53 |             0.33 |  0.37 |   0.387 |
| v1_baseline@1.0.0     | qwen2.5:7b T=1.0  |       108 |              0.86 |              0.47 |             0.39 |  0.39 |   0.401 |
| v2_policy_first@1.0.0 | qwen2.5:7b T=1.0  |       108 |              0.87 |              0.52 |             0.36 |  0.36 |   0.378 |
| v3_fewshot@1.0.0      | qwen2.5:7b T=1.0  |       108 |              0.84 |              0.56 |             0.29 |  0.31 |   0.332 |

## 4. Seed consistency (temperature > 0)

| variant               | condition         |   seeds per ticket |   same answer across seeds |
|:----------------------|:------------------|-------------------:|---------------------------:|
| v1_baseline@1.0.0     | llama3.1:8b T=0.3 |                  3 |                       0.9  |
| v1_baseline@1.0.0     | llama3.1:8b T=0.7 |                  3 |                       0.87 |
| v1_baseline@1.0.0     | llama3.1:8b T=1.0 |                  3 |                       0.79 |
| v1_baseline@1.0.0     | qwen2.5:7b T=0.3  |                  3 |                       0.97 |
| v1_baseline@1.0.0     | qwen2.5:7b T=0.7  |                  3 |                       0.89 |
| v1_baseline@1.0.0     | qwen2.5:7b T=1.0  |                  3 |                       0.9  |
| v2_policy_first@1.0.0 | llama3.1:8b T=0.3 |                  3 |                       0.93 |
| v2_policy_first@1.0.0 | llama3.1:8b T=0.7 |                  3 |                       0.81 |
| v2_policy_first@1.0.0 | llama3.1:8b T=1.0 |                  3 |                       0.75 |
| v2_policy_first@1.0.0 | qwen2.5:7b T=0.3  |                  3 |                       0.95 |
| v2_policy_first@1.0.0 | qwen2.5:7b T=0.7  |                  3 |                       0.92 |
| v2_policy_first@1.0.0 | qwen2.5:7b T=1.0  |                  3 |                       0.83 |
| v3_fewshot@1.0.0      | llama3.1:8b T=0.3 |                  3 |                       0.93 |
| v3_fewshot@1.0.0      | llama3.1:8b T=0.7 |                  3 |                       0.88 |
| v3_fewshot@1.0.0      | llama3.1:8b T=1.0 |                  3 |                       0.78 |
| v3_fewshot@1.0.0      | qwen2.5:7b T=0.3  |                  3 |                       0.99 |
| v3_fewshot@1.0.0      | qwen2.5:7b T=0.7  |                  3 |                       0.93 |
| v3_fewshot@1.0.0      | qwen2.5:7b T=1.0  |                  3 |                       0.91 |
