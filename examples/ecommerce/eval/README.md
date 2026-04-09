# Ecommerce Eval

This folder contains the evaluation framework for the ecommerce example.

Files:

- `SCORING_RUBRIC.md`: weighted scoring rubric for judging answer quality
- `EVAL_SET.md`: human-readable evaluation cases and expectations
- `eval_set.yaml`: machine-readable evaluation set for automation
- `run_ask_eval.py`: run the eval questions through `semduck ask` and write observed results to YAML
- `score_ask_eval.py`: score an ask-results YAML against the rubric and write scored YAML output

Use these files together:

1. Pick a case from `EVAL_SET.md` or `eval_set.yaml`.
2. Run the question through `ask`, MCP, or a direct semantic request.
3. Score the result with `SCORING_RUBRIC.md`.
4. Record the chosen semantic view, the produced result, and any failure modes.

Current scope:

- supported semantic views: `orders_semantic`, `customer_semantic`, `product_sales_semantic`
- includes supported questions and negative tests
- focuses on answer quality, not only query execution success

## Running The Ask Eval

Example:

```bash
uv run --group dev python examples/ecommerce/eval/run_ask_eval.py \
  --config packages/semduck/examples/ask_ollama_config.yaml \
  --output examples/ecommerce/eval/results/ask_results.yaml
```

The runner appends a UTC timestamp when it writes the file, so this command produces a file like `ask_results_20260409T021530Z.yaml`.

Useful flags:

- `--case EC-01`: run a single case
- `--skip-unsupported`: skip negative-test cases
- `--enforce-expected-view`: force `ask_question(...)` to use the expected semantic view
- `--llm-log-dir examples/ecommerce/eval/logs`: persist ask traces

The script copies `examples/ecommerce/ecommerce_demo.duckdb` to a temporary working database, initializes the registry there, loads all ecommerce semantic YAMLs, runs the selected eval questions, and writes a YAML results file that can be compared directly with `eval_set.yaml`.

## Scoring Ask Results

Example:

```bash
uv run --group dev python examples/ecommerce/eval/score_ask_eval.py \
  --ask-results examples/ecommerce/eval/results/ask_results_202604081939.yaml \
  --output examples/ecommerce/eval/results/ask_scores.yaml
```

The scorer also appends a UTC timestamp at write time, for example `ask_scores_20260409T021612Z.yaml`.

The scorer is deterministic. It reads `eval_set.yaml` and an ask-results file, applies baseline rubric checks such as:

- expected view match
- required dimensions and metrics present
- requested month grain present
- unsupported question refusal vs substitution
- ranking output sorted vs unsorted
- summary/table mismatch signals

It writes a scored YAML file with per-dimension scores, hard-failure flags, final weighted scores, ratings, rationale, and improvement actions. This is intended as the baseline artifact to compare before and after model, prompt, or planner changes.

### Gemma4 Judge Mode

You can also add a second-stage LLM judge using the same Gemma4 Ollama config used by the ask examples:

```bash
uv run --group dev python examples/ecommerce/eval/score_ask_eval.py \
  --ask-results examples/ecommerce/eval/results/ask_results_202604081939.yaml \
  --output examples/ecommerce/eval/results/ask_scores_judged.yaml \
  --judge \
  --config packages/semduck/examples/ask_ollama_config.yaml
```

In judge mode:

- deterministic checks remain authoritative for semantic correctness, efficiency, and hard failures
- Gemma4 scores `question_coverage`, `analytical_quality`, and `communication_quality`
- the output includes both `heuristic_scores` and `judge_scores` alongside the final combined score

This keeps objective structural failures deterministic while still capturing softer rubric dimensions with an LLM judge.
