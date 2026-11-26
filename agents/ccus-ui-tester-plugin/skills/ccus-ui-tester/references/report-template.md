# UI test report – CCUS cluster app

Save as `<PROJECT>\test-reports\ui\report_<YYYYMMDD_HHMM>.md`.

## 1. Session

| Item | Value |
|---|---|
| Date / time | |
| Tester (human) | |
| Agent / model | |
| Mode | A (agent drives) / B (human drives) / mixed |
| App URL / commit or folder date | `http://localhost:8501` / |
| Python / Streamlit / browser | (from `preflight.json`) |
| Language tested | HR / EN |
| Stories run | S01 … |

## 2. Summary

* Result: **PASS / PASS WITH ISSUES / FAIL**
* New defects: n (S1: n, S2: n, S3: n, S4: n)
* Known issues reproduced: K.., K..
* Known issues not reproduced (fixed?): K..
* Blocked steps: …

## 3. Results by story

| Story | Step | Expected | Observed | Verdict | Issue | Evidence |
|---|---|---|---|---|---|---|
| S01 | 3 | NPV `-919,875,061` (oracle) | `-919,875,061` | PASS | – | snapshot |
| | | | | | | |

Verdicts: PASS, FAIL, BLOCKED, SKIPPED, HUMAN-OK (judgment confirmed by the human).

## 4. Defects

One block per defect (new ones first):

```
ID:          NEW-01 (or K..)
Severity:    S1 / S2 / S3 / S4
Title:       <one line, what is wrong>
Story/step:  S0x / n
Steps:       1. … 2. … 3. …
Expected:    …
Observed:    … (quote UI text exactly)
Evidence:    test-reports/ui/playwright/<file>.png, oracle_<x>.json
Layer:       UI / engine / input data / documentation
Human note:  …
```

## 5. Oracle and headless results

Paste the summary lines of `oracle.py` and `apptest_<time>.md`.

## 6. Human feedback

Free text from the tester: clarity of labels, units, layout, what was confusing, what is
missing for a techno-economic cluster study.

## Severity scale

| Severity | Meaning | Examples |
|---|---|---|
| S1 | Wrong numbers or silent data loss | wrong NPV, scenario edits dropped |
| S2 | Crash or blocked workflow | traceback, cannot reload a saved scenario |
| S3 | Misleading or confusing display | wrong status banner, wrong label, hidden warnings |
| S4 | Cosmetic | typo, mojibake, alignment |
