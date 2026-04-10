# Persisted Semantic Concepts

Status: Proposed
Addresses Issue: [validation_layer_design.md](./validation_layer_design.md)
Implemented By:

## Summary

Add a persisted semantic concept layer in the DuckDB registry so the validator can resolve user-facing concepts against canonical concept ids instead of raw field names. The concept layer should be built deterministically from registry metadata plus curated policy, stored in `semantic.*` tables, and reused across requests until a registry fingerprint changes.

This is intended to fix false unsupported outcomes caused by alias expansion across multiple views, such as treating `customer_state` and `state` as two separate required dimensions instead of one concept satisfied by different fields in different views.

It is also intended to fix false validation failures where the planner correctly links a question phrase to a semantic time field but the deterministic validator does not, such as mapping `signed up each month` to `signup_date`.

## Problem

The current validator infers required dimensions and metrics as raw field names. That creates two bad outcomes:

- synonym over-collection
  Example: `customer states` can expand to both `customer_state` and `state`, causing candidate view detection to fail even when `orders_semantic` already satisfies the question.
- repeated per-request work
  The validator currently rebuilds schema metadata from the registry on every request. That cost is acceptable now, but concept resolution should become a reusable registry artifact rather than runtime-only inference.

It also mishandles phrase-to-field time semantics when there is no direct raw field-name match in the question.

Example:

- question: `How many customers signed up each month?`
- correct planner output:
  - `chosen_view = customer_semantic`
  - `dimensions = ["date_trunc('month', signup_date) as signup_month"]`
  - `metrics = ["customer_count"]`
- current validator failure:
  - infers `required_time_dimension = order_date`
  - rejects the correct plan as missing the required time grain on `order_date`

That should instead resolve the phrase `signed up` to the canonical concept for `signup_date`.

It also cannot currently rescue planner null-plan failures when the question uses semantic phrases that imply a field plus filter rather than directly naming a registry field.

Example:

- question: `Which inactive products still appear in recent sales?`
- likely answerable view: `product_sales_semantic`
- likely semantic concepts:
  - product identity such as `product_name`
  - product status concept backed by `is_active`
  - sales activity concept backed by recent `order_date` and a sales metric such as `line_count` or `net_item_sales`
- current validator failure:
  - infers no concrete required dimensions or metrics
  - treats all views as candidate views because the required concept set is empty
  - cannot flag `false_unsupported_candidate_exists`

That should instead resolve semantic phrases such as `inactive products` and `recent sales` into canonical concepts and supported field/filter realizations.

The concept layer must remain deterministic. It should not use fuzzy matching or LLMs.

## Design

### Concept model

Represent a concept as a canonical semantic meaning with:

- `concept_id`
- `concept_kind`
  Values: `dimension` or `metric`
- approved phrases
- allowed field realizations by view
- optional preferred field per view

Examples:

- concept `customer_state`
  - phrases: `customer state`, `customer states`, `state`, `states`
  - allowed fields:
    - `orders_semantic.customer_state`
    - `customer_semantic.state`
- concept `signup_date`
  - phrases: `signed up`, `signup`, `signup date`, `signup month`
  - allowed fields:
    - `customer_semantic.signup_date`
    - `orders_semantic.signup_date`
- concept `inactive_product`
  - phrases: `inactive product`, `inactive products`
  - allowed fields:
    - `product_sales_semantic.is_active`
  - canonical predicate:
    - `is_active = false`
- concept `recent_sales_activity`
  - phrases: `recent sales`, `still appear in recent sales`
  - allowed fields:
    - `product_sales_semantic.order_date`
    - `product_sales_semantic.net_item_sales`
    - `product_sales_semantic.line_count`
- concept `net_sales`
  - phrases: `net sales`
  - allowed fields:
    - `orders_semantic.net_sales`

### Deterministic construction rules

Build concepts in three stages:

1. Registry field harvest
   Load all dimensions and metrics from all semantic views.
2. Normalization
   For each field, generate deterministic normalized tokens:
   - lowercase
   - snake_case to spaced phrase
   - singular/plural normalization for simple suffixes
   - allowlisted prefix stripping such as `customer_`, `order_`, `product_`
3. Curated concept merge
   Merge fields into one concept only when one of these is true:
   - exact canonical policy mapping exists
   - exact normalized-name equivalence is allowed by policy

Do not merge fields by fuzzy similarity score or edit distance.

### Persisted schema

Add registry-adjacent tables under `semantic`:

- `semantic.semantic_concept_sets`
  - `fingerprint text primary key`
  - `policy_version text not null`
  - `created_at timestamptz/text not null`
  - `status text not null`
- `semantic.semantic_concepts`
  - `fingerprint text not null`
  - `concept_id text not null`
  - `concept_kind text not null`
  - primary key `(fingerprint, concept_id, concept_kind)`
- `semantic.semantic_concept_fields`
  - `fingerprint text not null`
  - `concept_id text not null`
  - `concept_kind text not null`
  - `view_name text not null`
  - `field_name text not null`
  - `is_preferred boolean not null default false`
  - primary key `(fingerprint, concept_id, concept_kind, view_name, field_name)`
- `semantic.semantic_concept_phrases`
  - `fingerprint text not null`
  - `concept_id text not null`
  - `concept_kind text not null`
  - `phrase text not null`
  - primary key `(fingerprint, concept_id, concept_kind, phrase)`

The `fingerprint` partitions one complete built concept set from another, so rebuilds do not require destructive in-place edits.

### Fingerprint

Compute the concept-set fingerprint from:

- semantic view names
- semantic tables
- dimension definitions
- metric definitions
- joins
- concept-policy version

The fingerprint must change when:

- a view is added or removed
- a dimension or metric name changes
- a field is added or removed
- a curated alias/concept rule changes
- merge policy version changes

The fingerprint does not need to include runtime data rows.

### Build and load flow

Validator/runtime flow:

1. Compute current concept fingerprint from the registry and policy version.
2. Check `semantic.semantic_concept_sets` for that fingerprint.
3. If present, load concepts from the concept tables.
4. If absent, rebuild deterministically from registry metadata plus policy and persist a fresh concept set.
5. Use the loaded concept set for intent extraction and candidate view coverage.

This should be implemented as a library provider, for example:

- `compute_concept_fingerprint(conn, policy) -> str`
- `load_semantic_concepts(conn, fingerprint) -> SemanticConceptIndex | None`
- `build_semantic_concepts(conn, policy) -> SemanticConceptIndex`
- `ensure_semantic_concepts(conn, policy) -> SemanticConceptIndex`

### Validator integration

Refactor the validator to operate on canonical concepts instead of raw field strings for intent coverage checks.

The flow should become:

1. Infer required concept ids from the question using concept phrases.
2. Determine which views satisfy each required concept using `semantic_concept_fields`.
3. Compute candidate covering views by concept coverage, not by raw field-name equality.
4. Normalize the selected plan fields back to concept ids and verify that the chosen plan preserves each required concept.

The validator should still compile with raw field names after validation; only intent/coverage reasoning changes to concepts.

### Chosen field resolution

When a concept is satisfied by multiple fields across views:

- candidate-view selection should accept any allowed field in that view
- chosen-plan validation should accept any allowed field in the selected view
- optional preferred-field metadata should be used only for retry guidance or future deterministic repair, not for compiler behavior

Example:

- required concept: `customer_state`
- allowed fields:
  - `orders_semantic.customer_state`
  - `customer_semantic.state`
- plan chooses `orders_semantic` with `dimensions=["customer_state"]`
- validation passes because `customer_state` satisfies concept `customer_state`

Example:

- question: `How many customers signed up each month?`
- required concepts:
  - `signup_date`
  - `customer_count`
- planner chooses `customer_semantic` with:
  - `dimensions=["date_trunc('month', signup_date) as signup_month"]`
  - `metrics=["customer_count"]`
- validation passes because `signup_date` satisfies the canonical time concept instead of incorrectly defaulting to `order_date`

Example:

- question: `Which inactive products still appear in recent sales?`
- required concepts:
  - `inactive_product`
  - `recent_sales_activity`
- candidate covering view:
  - `product_sales_semantic`
- planner null plan should trigger retry because the concept layer can identify one valid single-view candidate even though the user did not directly name fields like `is_active`, `product_name`, or `order_date`

## Implementation Notes

Suggested modules:

- `packages/semduck/src/semduck/agent/validation/concepts.py`
  - concept dataclasses/models
  - concept fingerprint helpers
- `packages/semduck/src/semduck/agent/validation/concept_builder.py`
  - deterministic concept generation from registry metadata plus policy
- `packages/semduck/src/semduck/agent/validation/concept_store.py`
  - registry table initialization, load, persist, and ensure helpers
- `packages/semduck/src/semduck/agent/validation/policy.py`
  - replace flat alias maps with canonical concept definitions and policy version

Registry DDL should be added in the existing registry schema path so concept tables are initialized with the rest of `semantic.*`.

The implementation should avoid rebuilding concepts inside `validate_plan(...)` directly. `validate_plan(...)` should consume a loaded concept index supplied by a provider/helper.

## Test Plan

Add tests for:

- fingerprint stays stable when registry metadata is unchanged
- fingerprint changes when a dimension/metric name or concept-policy version changes
- `ensure_semantic_concepts(...)` builds once and loads persisted concepts on later calls
- `customer_state` concept covers `orders_semantic.customer_state` and `customer_semantic.state`
- validator accepts `Rank customer states by net sales.` when the planner chooses `orders_semantic` and `customer_state`
- validator still rejects when no view satisfies the required concept set
- persisted concepts survive across separate validation calls in the same database

Regression examples:

- `Rank customer states by net sales.` should not infer both `customer_state` and `state` as separate requirements
- `How many customers signed up each month?` should resolve `signed up` to `signup_date` and accept a monthly `signup_date` bucket
- `Which inactive products still appear in recent sales?` should identify `product_sales_semantic` as a candidate via semantic concepts even when the planner initially returns null
- `Which payment methods have the highest average order value?` should still resolve to a single valid view when one exists
- `Which marketing campaigns drive the most net sales?` should remain unsupported when no concept or field exists

## Assumptions And Defaults

- Concept construction is deterministic and does not use LLMs.
- Policy-defined concept merges are authoritative; automatic merges are limited to exact normalized-name rules explicitly allowed by policy.
- The concept cache is stored in DuckDB beside the registry, not only in process memory.
- The concept-set fingerprint includes policy version so policy changes invalidate persisted concepts automatically.
- This layer is for validation and intent coverage only; it does not change compiler request syntax or SQL generation.
