# Ecommerce Ask Eval Gaps

Status: Proposed
Related Spec: [../specs/ecommerce-ask-hardening.md](../specs/ecommerce-ask-hardening.md)
Implemented By:

## Summary

The ecommerce ask evaluation shows that the current ask stack can usually produce executable semantic requests, but it still misses several important question semantics:

- month-level time grain
- ranking and ordered outputs
- unsupported-question refusal
- multi-hop join planning
- semantic-grain disambiguation across overlapping views
- faithful summary formatting

These are not all the same class of problem. Some are planner prompt failures, some are request-language/compiler limitations, and some are join-resolution constraints in the semantic planner.

Potential follow-on enhancement:

- add a post-plan question-to-plan validator that deterministically checks whether the generated plan preserved all clearly requested concepts from the question before execution

## Evidence From The Eval

Captured artifacts:

- [examples/ecommerce/eval/results/ask_results_202604081939.yaml](../../examples/ecommerce/eval/results/ask_results_202604081939.yaml)
- [examples/ecommerce/eval/results/ask_scores_202604081939.yaml](../../examples/ecommerce/eval/results/ask_scores_202604081939.yaml)

Notable failures:

- `EC-01`, `EC-04`, `EC-06`, `EC-10`, `EC-11`, `EC-16`: month-grain questions were planned with raw dates instead of `date_trunc('month', ...)`
- `EC-02`, `EC-03`, `EC-05`, `EC-08`, `EC-13`, `EC-17`: ranking-style questions compiled without `ORDER BY`
- `EC-09`: segment lifetime value failed with `No direct join found between orders and customer_segments`
- `EC-12`: the planner dropped `segment_name` and answered a different question on `orders_semantic`
- `EC-17`: the planner chose the wrong semantic grain, using `orders_semantic` and `net_sales` instead of `product_sales_semantic` and `net_item_sales`
- `EC-X2`: an unsupported marketing-attribution question was answered with `sales_channel` revenue instead of being refused

## Current Technical Constraints

Relevant implementation points:

- [ask.py](../../packages/semduck/src/semduck/agent/ask.py): planner prompt only returns `chosen_view`, `dimensions`, `metrics`, and `where_clause`
- [request_parser.py](../../packages/semduck/src/semduck/parser/request_parser.py): request language rejects `ORDER BY`, `LIMIT`, and `HAVING`
- [qualifier.py](../../packages/semduck/src/semduck/compiler/qualifier.py): `date_trunc` is already allowed in derived expressions
- [joins.py](../../packages/semduck/src/semduck/planner/joins.py): join resolution only looks for direct joins from the anchor table

This means:

- month truncation is already representable in the request language, but the planner is not selecting it
- ranking cannot be represented cleanly in the request language today
- multi-hop joins are not supported by the current join resolver
- overlapping-view failures are really semantic-grain disambiguation failures, not just ecommerce naming problems
- even when a syntactically valid plan compiles, semduck does not yet have a deterministic guardrail that rejects partial plans which silently drop requested dimensions or metrics

## Current Workaround

- Use `--enforce-expected-view` in the eval runner when testing a specific semantic view
- Manually inspect compiled requests with `--sql`
- Score failures deterministically with the eval scorer so regressions can be measured before model changes

## Why This Matters

Without these changes, ask can appear successful because SQL executes, while still answering the wrong question shape. That is a bad failure mode for analytics workflows because it produces plausible but semantically incorrect output.

## Deferred Enhancement: Post-Plan Validation

Add a schema-aware validation pass between ask planning and execution that compares:

- requested concepts inferred from the user question
- dimensions, metrics, grain, and ordering present in the generated plan

Desired behavior:

- deterministically reject plans that drop clearly requested concepts like `segment` in `segment by sales channel`
- force a planner retry with explicit missing-concept feedback when the plan is partial
- prefer an unsupported response over executing a nearby but incomplete answer
- detect false-unsupported planner outcomes when a described single semantic view already contains the needed fields
  Example:
  `Which payment methods have the highest average order value?` should be recoverable from `orders_semantic` because `payment_method` and `average_order_value` were both present in the described view, even though the planner drifted and returned an unsupported-style failure

Scope notes:

- this should be conservative and deterministic for explicit concepts first
- it does not need to solve arbitrary natural-language understanding
- it is intended as a guardrail on top of prompt improvements, not a replacement for them
