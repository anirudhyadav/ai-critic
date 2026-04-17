# aicritic benchmark harness

Measures the pipeline's **precision** and **recall** against known-flawed
fixture repos. This is how you answer "is the tool any good?" with a number
instead of an anecdote.

## What it does

1. Loads `ground_truth.json` — the list of issues each fixture *should*
   produce.
2. Runs the full aicritic pipeline (analyst → checker → critic) on each
   fixture, using the tool profile declared for that case.
3. Matches each expected finding against the critic's output by
   **file basename + keyword presence** in the description.
4. Reports precision, recall, per-case timing, and which expected issues
   were missed.

## Run it

```bash
# All cases
python benchmarks/run.py

# One case
python benchmarks/run.py --case sql_injection

# Faster (skip Gemini cross-check)
python benchmarks/run.py --skip-checker

# Persist results as JSON (for trend tracking in CI)
python benchmarks/run.py --output benchmarks/latest.json
```

## Output shape

```
aicritic benchmark — 3 case(s)
================================================
→ sql_injection [security_review]
  precision=1.00  recall=1.00  matched=2/2  extra=0  (14.2s)

→ hardcoded_secret [secrets_scan]
  precision=0.75  recall=1.00  matched=3/3  extra=1  (12.1s)

→ missing_timeout [error_handling]
  precision=1.00  recall=0.50  matched=1/2  extra=0  (11.5s)
    MISS: fetcher.py: timeout/requests.post

================================================
AVERAGE  precision=0.92  recall=0.83  across 3 case(s)
```

## Adding a new case

1. Create `benchmarks/cases/<name>/…` with the flawed source.
2. Add an entry to `benchmarks/ground_truth.json`:
   ```json
   "<name>": {
     "tool": "<built-in tool name>",
     "min_risk": "medium",
     "expected": [
       { "file": "app.py", "keywords": ["keyword1", "keyword2"], "risk": "high" }
     ]
   }
   ```
3. Re-run `python benchmarks/run.py --case <name>`.

## Matching rules

A finding counts as a **true positive** when:

- the finding's `file` basename matches the expected `file` (case-insensitive)
- AND at least one of the expected `keywords` appears in the finding's
  `description` (case-insensitive substring match)

This is intentionally lenient — we care that the *right class of issue in the
right file* was reported, not that the phrasing matches exactly. Risk-level
mismatches are *not* penalised in the score today; they're visible in the
raw per-finding output if you want to inspect.

## Limitations

- Keyword matching can over-credit a finding that mentions the right word
  for the wrong reason. Counter this by using more specific keywords.
- Fixture set is small (3 cases). Adding more raises the ceiling.
- Every run costs LLM calls — `--skip-checker` cuts that roughly in half.
