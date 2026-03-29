# VeraBench Results

## Summary

| Model | check@1 | verify@1 | fix@1 | run_correct | Problems |
|-------|---------|----------|-------|-------------|----------|
| claude-sonnet-4-20250514 | 96% | 96% | 50% | 78% | 50 |

## By Tier

| Model | Metric | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|-------|--------|--------|--------|--------|--------|--------|
| claude-sonnet-4-20250514 | check@1 | 100% | 100% | 100% | 90% | 90% |
| claude-sonnet-4-20250514 | verify@1 | 100% | 100% | 100% | 90% | 89% |
| claude-sonnet-4-20250514 | fix@1 | 0% | 0% | 0% | 100% | 0% |
| claude-sonnet-4-20250514 | run_correct | 100% | 0% | 0% | 62% | 60% |

## Per-Problem Detail

### claude-sonnet-4-20250514

| Problem | check@1 | verify | fix | run | tokens | time |
|---------|---------|--------|-----|-----|--------|------|
| VB-T1-001 | PASS | PASS | - | PASS | 110 | 2.91s |
| VB-T1-002 | PASS | PASS | - | PASS | 140 | 2.68s |
| VB-T1-003 | PASS | PASS | - | PASS | 117 | 3.0s |
| VB-T1-004 | PASS | PASS | - | PASS | 126 | 2.77s |
| VB-T1-005 | PASS | PASS | - | PASS | 126 | 3.29s |
| VB-T1-006 | PASS | PASS | - | PASS | 62 | 2.03s |
| VB-T1-007 | PASS | PASS | - | PASS | 76 | 2.65s |
| VB-T1-008 | PASS | PASS | - | PASS | 97 | 2.98s |
| VB-T1-009 | PASS | PASS | - | PASS | 195 | 3.16s |
| VB-T1-010 | PASS | PASS | - | PASS | 83 | 2.55s |
| VB-T2-001 | PASS | PASS | - | - | 86 | 3.02s |
| VB-T2-002 | PASS | PASS | - | - | 82 | 3.17s |
| VB-T2-003 | PASS | PASS | - | - | 80 | 2.19s |
| VB-T2-004 | PASS | PASS | - | - | 71 | 1.75s |
| VB-T2-005 | PASS | PASS | - | - | 59 | 1.72s |
| VB-T2-006 | PASS | PASS | - | - | 63 | 1.85s |
| VB-T2-007 | PASS | PASS | - | - | 81 | 2.45s |
| VB-T2-008 | PASS | PASS | - | - | 108 | 2.56s |
| VB-T2-009 | PASS | PASS | - | - | 51 | 1.77s |
| VB-T2-010 | PASS | PASS | - | - | 134 | 3.35s |
| VB-T3-001 | PASS | PASS | - | - | 121 | 2.84s |
| VB-T3-002 | PASS | PASS | - | - | 134 | 2.43s |
| VB-T3-003 | PASS | PASS | - | - | 151 | 2.85s |
| VB-T3-004 | PASS | PASS | - | - | 116 | 2.22s |
| VB-T3-005 | PASS | PASS | - | - | 115 | 2.6s |
| VB-T3-006 | PASS | PASS | - | - | 96 | 2.24s |
| VB-T3-007 | PASS | PASS | - | - | 135 | 2.54s |
| VB-T3-008 | PASS | PASS | - | - | 135 | 3.62s |
| VB-T3-009 | PASS | PASS | - | - | 127 | 2.6s |
| VB-T3-010 | PASS | PASS | - | - | 158 | 2.78s |
| VB-T4-001 | PASS | PASS | - | PASS | 134 | 2.59s |
| VB-T4-002 | PASS | PASS | - | FAIL | 115 | 2.73s |
| VB-T4-003 | PASS | PASS | - | PASS | 186 | 2.92s |
| VB-T4-004 | PASS | PASS | - | FAIL | 113 | 2.26s |
| VB-T4-005 | PASS | PASS | - | PASS | 111 | 2.16s |
| VB-T4-006 | PASS | PASS | - | - | 182 | 3.29s |
| VB-T4-007 | PASS | PASS | - | PASS | 103 | 78.01s |
| VB-T4-008 | PASS | PASS | - | PASS | 113 | 2.88s |
| VB-T4-009 | FAIL | - | PASS | - | 159 | 4.58s |
| VB-T4-010 | PASS | FAIL | - | FAIL | 126 | 2.63s |
| VB-T5-001 | PASS | PASS | - | PASS | 223 | 5.4s |
| VB-T5-002 | PASS | PASS | - | - | 159 | 3.88s |
| VB-T5-003 | PASS | PASS | - | FAIL | 196 | 4.94s |
| VB-T5-004 | FAIL | - | FAIL | - | 293 | 5.76s |
| VB-T5-005 | PASS | PASS | - | - | 220 | 4.32s |
| VB-T5-006 | PASS | PASS | - | PASS | 253 | 5.58s |
| VB-T5-007 | PASS | PASS | - | FAIL | 195 | 3.73s |
| VB-T5-008 | PASS | FAIL | - | - | 273 | 7.56s |
| VB-T5-009 | PASS | PASS | - | PASS | 382 | 6.85s |
| VB-T5-010 | PASS | PASS | - | - | 201 | 3.76s |
