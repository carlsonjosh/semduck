# Ecommerce Ask Hardening

Status: Proposed
Addresses Issue: [../issues/ecommerce-ask-eval-gaps.md](../issues/ecommerce-ask-eval-gaps.md)
Implemented By:

## Summary

Harden the ask workflow against the ecommerce eval set by splitting the required work into three layers:

1. planner improvements for view choice, time grain, and unsupported-question handling
2. request-language and compiler additions for ranking semantics
3. join-resolution improvements for multi-hop semantic queries

The goal is not just to make more cases execute. The goal is to preserve the requested business semantics in the compiled request.

## Key Changes

### 1. Planner: Preserve Time Grain Explicitly

Problem:

- month-grain questions are currently planned with raw dates even though the request language already supports derived dimensions

Required change:

- update the ask planner guidance in [ask.py](../../packages/semduck/src/semduck/agent/ask.py) so questions containing month-level intent map to derived dimensions such as `date_trunc('month', order_date) as order_month`
- include explicit examples for:
  - monthly topline metrics
  - signup cohort month
  - month plus another grouping dimension
- treat time-grain words like `day`, `week`, `month`, `quarter`, and `year` as planning signals rather than optional phrasing

Why this is planner-first:

- [request_parser.py](../../packages/semduck/src/semduck/parser/request_parser.py) already supports derived dimensions with aliases
- [qualifier.py](../../packages/semduck/src/semduck/compiler/qualifier.py) already treats `date_trunc` as a valid SQL keyword/function

Expected result:

- the ask planner should emit derived time dimensions instead of raw dates whenever the question specifies a grain

### 2. Planner: Refuse Unsupported Questions

Problem:

- unsupported questions are currently answered with nearby but incorrect dimensions or metrics

Required change:

- change the ask planner contract so it can explicitly signal `unsupported` rather than always forcing a semantic request
- planner behavior should be:
  - if no view can answer the requested business concept, return `chosen_view = null`
  - do not substitute a semantically adjacent concept like `sales_channel` for `marketing_campaign`
- add negative examples to the planner prompt for:
  - missing subject-area dimensions
  - unsupported cross-view questions

Implementation note:

- the ask runner should translate `chosen_view = null` into a clean user-facing unsupported-schema response rather than a runtime failure

Expected result:

- `EC-X1` and `EC-X2` refuse unsupported questions cleanly and predictably

### 3. Planner: Strengthen Semantic-Grain Disambiguation

Problem:

- questions that could map to multiple views are falling back to the wrong semantic grain

Required change:

- update the planner guidance so view selection is based on semantic grain and subject, not on example-specific names
- the planner should explicitly reason about:
  - what entity or event the question is about
  - what metric grain is implied by the metric names and requested breakdowns
  - whether multiple candidate views expose similar dimensions but different aggregation meaning
- prefer the view whose native metric grain matches the user question, even if another view can produce a superficially similar answer
- add contrastive examples that are generic in shape, with ecommerce-specific examples only as one benchmark set:
  - event-level revenue by payment method vs item-level revenue by payment method
  - customer-segment by channel vs order-channel only
  - entity count vs event count when both are available in different views

Expected result:

- `EC-12` retains `segment_name`
- `EC-17` chooses `product_sales_semantic` and `net_item_sales`

### 4. Request Language And Compiler: Add Ordering Semantics

Problem:

- ranking questions cannot be faithfully represented because the request language rejects `ORDER BY` and `LIMIT`

Required change:

- extend the parsed request and plan model to carry ordering metadata separately from `dimensions`, `metrics`, and `where`
- allow the planner to request:
  - `order_by <expr> [asc|desc]`
  - optional `limit <n>`
  as dedicated planning fields rather than embedding them inside the semantic request text
- extend [types.py](../../packages/semduck/src/semduck/types.py) and the compiled plan types to carry ordering metadata
- extend [sql_compiler.py](../../packages/semduck/src/semduck/compiler/sql_compiler.py) to emit `ORDER BY` and `LIMIT` only in the outermost SQL stage, after semantic aggregation and derived-field projection

Important constraint:

- `ORDER BY` and `LIMIT` must not be serialized back into the semantic request text itself
- they should live as structured plan metadata and be appended only to the final outer SQL query in the correct position

Defaults:

- preserve current behavior when `order_by` and `limit` are omitted
- only allow ordering expressions that reference selected dimensions or metrics
- do not allow arbitrary post-aggregate SQL beyond the explicit request-language clauses

Expected result:

- ranking-style questions compile to ordered output instead of unordered group-bys

### 5. Join Resolver: Support Multi-Hop Join Paths

Problem:

- the current join resolver in [joins.py](../../packages/semduck/src/semduck/planner/joins.py) only supports direct joins between the anchor table and each required table

Required change:

- replace direct-anchor-only join lookup with graph-based path resolution across the semantic view join list
- choose the minimal join path that connects all required tables
- preserve deterministic ordering of joins once the path is chosen

Fanout protection rule:

- do not allow an automatically chosen multi-hop path unless it is grain-preserving relative to the anchor table
- use the registered table primary-key metadata already stored by the registry writer to validate whether each hop preserves anchor-table grain
- in v1, treat a join path as safe only when every added table is joined through a key-preserving path that behaves like many-to-one from the anchor-table perspective
- if the planner/compiler cannot prove the path is grain-preserving, fail with an explicit semantic-resolution error instead of executing a potentially fanout-inflated query

Practical consequence:

- dimension enrichment joins are allowed when they do not multiply anchor rows
- paths that would duplicate anchor rows across downstream tables stay invalid until semduck has richer join-cardinality metadata

Implementation note:

- this is intentionally conservative
- the first goal is to prevent silent metric corruption, not to maximize the number of join paths that compile

Expected result:

- questions that need `customers -> customer_segments` and `customers -> orders` can compile within `customer_semantic`
- `EC-09` stops failing on the segment lifetime-value case
- unsafe multi-hop paths fail loudly instead of introducing fanout-driven metric inflation

### 6. Summary Layer: Make Output Faithful To The Returned Table

Problem:

- summaries can introduce malformed headings or partial framing that does not match the result rows

Required change:

- tighten the summary prompt so it must either:
  - produce one concise sentence grounded in the rows, or
  - produce a markdown table using exactly the provided columns
- add regression tests around mismatched labels and invented headings

Expected result:

- cases like `EC-17` stop producing malformed summary headers

## Implementation Notes

Suggested order:

1. planner prompt hardening for unsupported questions and time grain
2. join resolver upgrade for multi-hop paths
3. structured `order_by` and `limit` plan fields plus outer-query SQL emission
4. summary prompt tightening
5. rerun the ecommerce eval and compare scores

Recommended acceptance baseline:

- all supported ecommerce eval cases compile and execute
- unsupported cases refuse cleanly
- all month-grain cases use truncated month dimensions
- all ranking cases emit ordered output
- no wrong-view failures remain in the baseline scorer

## Test Plan

- parser tests for `order_by` and `limit`
- compiler tests that ordered aggregate requests emit correct outer SQL and never inject ordering into inner aggregation stages
- join-planner tests for multi-hop paths across three tables
- join-planner tests that unsafe fanout paths are rejected when grain preservation cannot be proven
- ask tests for:
  - month-grain planning
  - unsupported-question refusal
  - semantic-grain disambiguation across overlapping views
  - faithful summary formatting
- rerun:
  - [run_ask_eval.py](../../examples/ecommerce/eval/run_ask_eval.py)
  - [score_ask_eval.py](../../examples/ecommerce/eval/score_ask_eval.py)

## Assumptions And Defaults

- time-grain preservation is treated as planner behavior first, not a new semantic-view authoring feature
- ranking semantics require planner metadata and compiler changes, not just summary-layer sorting
- unsupported-question refusal is preferred over semantic substitution
- multi-hop join expansion must be conservative and grain-safe by default
- the ecommerce eval set remains the initial acceptance harness for this work
