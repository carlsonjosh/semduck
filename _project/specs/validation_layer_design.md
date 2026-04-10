Here’s a practical design spec for a validation layer that sits between your LLM planner and semduck execution.

Validation Layer Design Spec

1. Purpose

The validation layer exists to stop three bad outcomes:
	1.	Silent wrong answers
	•	wrong metric
	•	wrong semantic view
	•	unsupported question answered with a nearby substitute
	2.	Structurally invalid plans
	•	malformed fields
	•	unsupported clauses
	•	aliasing or SQL leakage
	•	invalid dimensions/metrics for the chosen view
	3.	Misleading analytical outputs
	•	duplicate rows per requested grain
	•	ranking questions without sort
	•	trend questions answered as top-N ranking
	•	unsupported questions passed through as if valid

The goal is not to make the LLM smarter. The goal is to make the system safe and predictable.

⸻

2. Scope

The validation layer covers four stages:
	1.	Plan validation
	•	Validate the structured semantic request returned by the planner.
	2.	Execution preflight
	•	Validate the compiled query shape before execution if possible.
	3.	Result validation
	•	Validate the returned dataset against the requested grain and intent.
	4.	Unsupported handling
	•	Convert unsafe or invalid plans into a clean unsupported outcome instead of executing them.

It should be deterministic and rule-based.

⸻

3. Non-goals

This layer should not:
	•	infer business meaning from vague language beyond a controlled mapping table
	•	rewrite arbitrary user intent into a better question
	•	perform fuzzy semantic matching without explicit policy
	•	depend on another LLM for core correctness checks

An optional judge LLM can be used later for soft scoring, but never for core pass/fail validation.

⸻

4. System placement

Recommended pipeline:
	1.	User question
	2.	Intent extraction / planner LLM
	3.	Validation layer: plan validation
	4.	Optional plan repair / retry
	5.	Semantic request compilation
	6.	Validation layer: execution preflight
	7.	Query execution
	8.	Validation layer: result validation
	9.	Response rendering

The validator should be callable as a pure Python library and return structured errors.

⸻

5. Inputs and outputs

5.1 Inputs

The validation layer should receive:
	•	question: str
	•	plan: SemanticPlan
	•	available_views: list[ViewSummary]
	•	described_views: dict[str, ViewDescription]
	•	compiled_query: Optional[CompiledQuery]
	•	result: Optional[QueryResult]
	•	expected_intent: Optional[IntentSpec]

5.2 Core plan schema

class SemanticPlan(BaseModel):
    chosen_view: str | None
    dimensions: list[str]
    metrics: list[str]
    where_clause: str | None
    order_by: list[str]
    limit: int | None

5.3 Validation output

class ValidationIssue(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str
    field: str | None = None
    details: dict = {}

class ValidationResult(BaseModel):
    is_valid: bool
    issues: list[ValidationIssue]
    normalized_plan: SemanticPlan | None = None
    action: Literal[
        "accept",
        "reject_as_unsupported",
        "reject_for_retry",
        "reject_execution",
        "accept_with_warnings",
    ]


⸻

6. Validation stages

6.1 Stage A: plan shape validation

This stage checks basic structure only.

Rules:
	•	chosen_view must be null or a known view name
	•	dimensions, metrics, order_by must be lists
	•	where_clause must be string or null
	•	limit must be positive integer or null
	•	all required top-level fields must exist
	•	no extra top-level fields allowed

Reject if:
	•	malformed JSON/object
	•	missing required fields
	•	unknown chosen_view
	•	invalid primitive types

Example failures:
	•	missing order_by
	•	metrics: "net_sales" instead of ["net_sales"]
	•	chosen_view: "orders" when only orders_semantic exists

⸻

6.2 Stage B: semantic membership validation

This checks whether the selected fields actually exist in the chosen view.

Rules:
	•	every requested metric must exist in the chosen view
	•	every requested dimension must exist in the chosen view, allowing approved time transforms
	•	if chosen_view is null, dimensions and metrics must be empty
	•	if chosen_view is not null, at least one metric or dimension must be present

Supported dimension transform policy:
	•	allow date_trunc('month', signup_date) as signup_month
	•	allow only whitelisted transform patterns
	•	transformed base field must exist in chosen view

Reject if:
	•	requested metric missing from chosen view
	•	dimension missing from chosen view
	•	view does not exist
	•	null plan contains fields
	•	non-null plan contains no usable fields

This is where you stop:
	•	wrong-view answers
	•	field hallucinations
	•	unsupported cross-view joins

⸻

6.3 Stage C: semantic exactness validation

This is the most important layer.

The validator should distinguish:
	•	exact match
	•	allowed canonical mapping
	•	forbidden substitution

Example policy table:

CANONICAL_MEASURE_MAP = {
    "product revenue": ["net_item_sales"],
    "item revenue": ["net_item_sales"],
    "net item sales": ["net_item_sales"],
    "gross item sales": ["gross_item_sales"],
    "net sales": ["net_sales"],
    "shipping revenue": ["total_shipping"],
    "tax": ["total_tax"],
}

Rules:
	•	if the question explicitly names a metric family, only exact or explicitly approved canonical mappings are allowed
	•	mappings must be curated, not fuzzy
	•	if no approved mapping exists, reject as unsupported
	•	never allow substitution across grain level without policy
	•	net_item_sales ≠ net_sales
	•	line_count ≠ net_item_sales
	•	gross_sales ≠ net_sales

This catches:
	•	EC-17 class failures
	•	EC-18 class failures
	•	campaign → sales_channel substitution failures

Recommendation:
make this policy file-driven so you can expand it over time.

⸻

6.4 Stage D: intent compliance validation

This checks whether the plan shape matches the question type.

You should define a lightweight intent model.

class IntentSpec(BaseModel):
    question_type: Literal[
        "trend",
        "ranking",
        "comparison",
        "breakdown",
        "cohort",
        "rollup",
        "unsupported",
    ]
    required_dimensions: list[str]
    required_metrics: list[str]
    required_time_grain: str | None = None
    requires_sort: bool = False
    sort_metric: str | None = None
    chronological: bool = False

Rules by intent:

Trend
	•	requires time dimension
	•	requires approved time grain
	•	result should usually be chronological, not top-N by metric
	•	ranking sort on metric should be flagged unless explicitly requested

Ranking
	•	requires order_by
	•	sort should reference selected metric descending unless explicitly otherwise
	•	limit optional

Cohort
	•	requires grouped time bucket derived from cohort field
	•	for signup/acquisition cohort, default month unless explicit grain

Breakdown / matrix
	•	all requested grouping dimensions must be present

Rollup
	•	should have one row per requested grain

This catches:
	•	trend rendered as top months by sales
	•	ranking missing sort
	•	cohort rejected despite available signup_date

⸻

6.5 Stage E: unsupported question validation

This stage decides whether the question should fail cleanly.

Rules:
	•	if required dimension or metric is absent from every single described view, reject as unsupported
	•	do not allow nearest-neighbor substitution
	•	if no single view contains the full required field set, reject as unsupported unless cross-view joins are explicitly supported
	•	unsupported should return a clean structured reason

Output example:

{
  "action": "reject_as_unsupported",
  "issues": [
    {
      "code": "missing_dimension",
      "message": "No described semantic view contains marketing_campaign."
    }
  ]
}

This catches:
	•	campaign attribution
	•	product category + customer segment cross-view mixes

⸻

6.6 Stage F: compiled query preflight validation

If semduck produces SQL or an intermediate logical plan, validate it before execution.

Rules:
	•	selected expressions must align with validated dimensions and metrics
	•	no unexpected extra grouping columns
	•	GROUP BY must match requested grain
	•	no unsupported clauses
	•	ORDER BY must match allowed intent behavior
	•	limit must match validated plan
	•	alias names should be normalized

This is where you catch:
	•	extra columns causing duplicated month rows
	•	bad GROUP BY
	•	rogue ranking clauses

If you can only inspect SQL text, build targeted checks:
	•	count group-by expressions
	•	confirm date_trunc alias appears exactly once
	•	confirm no hidden dimensions appear in select/group

⸻

6.7 Stage G: result validation

This is the layer your evals are screaming for.

After execution, validate the actual result frame.

Rules:
	•	required columns must exist
	•	one row per requested grain for rollups/trends/cohorts
	•	duplicate grain combinations should fail or warn
	•	chronological questions should be sorted chronologically
	•	ranking questions should be sorted by requested metric
	•	row count truncation should be surfaced

Examples:

Duplicate grain check

For a trend by order_month:
	•	if order_month appears multiple times, fail result validation

Matrix check

For segment x channel:
	•	duplicate (segment_name, sales_channel) pairs should fail

Ranking check

For payment_method by net_sales:
	•	ensure descending metric order unless explicitly requested otherwise

Chronology check

For trends:
	•	ensure months ascending unless the user asked for top months

This is the single best fix for your repeated month-row problem.

⸻

7. Repair policy

Not every invalid plan needs a full retry.

Use three levels:

7.1 Safe normalization

Apply automatically:
	•	fill missing where_clause = null
	•	fill missing order_by = []
	•	fill missing limit = null
	•	trim whitespace
	•	normalize exact view names if alias map explicitly allows it

7.2 Deterministic repair

Apply only if safe:
	•	infer missing chronological sort for trend from time dimension
	•	infer required ranking sort if question says rank/top/most and metric is unambiguous
	•	normalize approved time bucket expressions

7.3 Retry required

Use when:
	•	wrong metric
	•	wrong view
	•	unsupported field
	•	malformed transform
	•	null plan when valid single-view solution appears to exist

Retry prompt should contain only deterministic feedback:
	•	“The selected view does not contain net_item_sales.”
	•	“A valid single view exists: product_sales_semantic.”
	•	“Trend questions must return one row per month.”

⸻

8. Error taxonomy

Use stable machine-readable codes.

Recommended codes:

Plan shape
	•	invalid_plan_shape
	•	missing_required_field
	•	unknown_view
	•	invalid_field_type

Semantic membership
	•	missing_metric
	•	missing_dimension
	•	field_not_in_view
	•	null_plan_with_fields
	•	nonnull_plan_empty

Exactness
	•	forbidden_metric_substitution
	•	forbidden_dimension_substitution
	•	unsupported_proxy_mapping

Intent
	•	missing_time_grain
	•	missing_order_by_for_ranking
	•	trend_sorted_as_ranking
	•	cohort_bucket_missing
	•	incomplete_breakdown

Query/result
	•	unexpected_group_by
	•	duplicate_grain_rows
	•	ranking_not_sorted
	•	chronology_not_sorted
	•	partial_output_unlabeled

Unsupported
	•	unsupported_question
	•	no_single_view_covers_request

⸻

9. Policy configuration

Keep rules configurable, not buried in code.

Suggested config sections:

metric_aliases:
  product revenue:
    allowed_metrics: [net_item_sales]
  net sales:
    allowed_metrics: [net_sales]
  shipping revenue:
    allowed_metrics: [total_shipping]

time_defaults:
  trend: month
  cohort: month

intent_keywords:
  ranking: [top, most, highest, rank, lowest]
  trend: [trend, over time, by month, by quarter, by year]
  cohort: [cohort, signup cohort, acquisition cohort]

unsupported_substitutions:
  - from: marketing_campaign
    to: sales_channel
  - from: net_item_sales
    to: net_sales
  - from: product revenue
    to: gross_sales

allowed_dimension_transforms:
  - pattern: "date_trunc\\('(day|week|month|quarter|year)',\\s*[a-zA-Z_][a-zA-Z0-9_]*\\)\\s+as\\s+[a-zA-Z_][a-zA-Z0-9_]*"


⸻

10. Integration design

Recommended modules:

intent_parser.py
	•	derive lightweight intent signals from question
	•	no LLM required

schema_index.py
	•	flatten described views into:
	•	all dimensions
	•	all metrics
	•	base field lookup
	•	transformable time dimensions

plan_validator.py
	•	stages A through E

query_validator.py
	•	stage F

result_validator.py
	•	stage G

policy.py
	•	alias maps
	•	transform rules
	•	unsupported mappings
	•	intent keywords

retry_builder.py
	•	builds deterministic retry messages

⸻

11. Example validation flows

Example 1: good plan

Question:
“Which sales channels generate the most net sales?”

Plan:

{
  "chosen_view": "orders_semantic",
  "dimensions": ["sales_channel"],
  "metrics": ["net_sales"],
  "where_clause": null,
  "order_by": ["net_sales desc"],
  "limit": null
}

Validation:
	•	shape valid
	•	fields in view
	•	exact metric match
	•	ranking intent satisfied

Action:
	•	accept

⸻

Example 2: wrong substitution

Question:
“Which payment methods are associated with the most product revenue?”

Plan:

{
  "chosen_view": "orders_semantic",
  "dimensions": ["payment_method"],
  "metrics": ["net_sales"],
  "where_clause": null,
  "order_by": ["net_sales desc"],
  "limit": null
}

Validation:
	•	payment_method exists
	•	but “product revenue” maps only to net_item_sales
	•	net_sales is forbidden substitution
	•	product_sales_semantic contains valid fields

Action:
	•	reject for retry or repair target:
	•	chosen_view = product_sales_semantic
	•	metric = net_item_sales

⸻

Example 3: correct unsupported

Question:
“Which marketing campaigns drive the most net sales?”

Plan:

{
  "chosen_view": "orders_semantic",
  "dimensions": ["sales_channel"],
  "metrics": ["net_sales"],
  "where_clause": null,
  "order_by": ["net_sales desc"],
  "limit": null
}

Validation:
	•	“marketing campaigns” dimension not present in any view
	•	substitution to sales_channel forbidden

Action:
	•	reject_as_unsupported

⸻

Example 4: duplicate month rows after execution

Question:
“How much shipping revenue and tax are collected over time?”

Validated plan:

{
  "chosen_view": "orders_semantic",
  "dimensions": ["date_trunc('month', order_date) as order_month"],
  "metrics": ["total_shipping", "total_tax"],
  "where_clause": null,
  "order_by": [],
  "limit": null
}

Result contains repeated order_month values.

Validation:
	•	duplicate grain rows
	•	fails rollup/trend result validation

Action:
	•	reject execution result
	•	mark as compiler/query bug, not planner success

⸻

12. Logging and observability

Every validation run should log:
	•	question
	•	raw plan
	•	normalized plan
	•	detected intent
	•	schema coverage candidates
	•	validation issues
	•	chosen action
	•	retry count
	•	final execution status

Track issue counts over eval runs:
	•	forbidden_metric_substitution
	•	duplicate_grain_rows
	•	unsupported_question
	•	false_unsupported_if_candidate_exists

That last one is especially useful:
	•	if validator sees exactly one valid single-view candidate but planner returned null, count it

⸻

13. Evaluation hooks

Add validator-based metrics to your eval suite:
	•	exact metric preservation rate
	•	unsupported refusal correctness
	•	duplicate grain failure rate
	•	ranking compliance rate
	•	trend chronology rate
	•	false unsupported rate
	•	wrong-view rate

This will give you sharper signals than just final-answer judging.

⸻

14. Rollout plan

Phase 1: must-have
	•	plan shape validation
	•	field-in-view validation
	•	strict metric substitution block
	•	unsupported question block
	•	ranking/order_by validation

Phase 2: high-value
	•	result duplicate-grain validation
	•	trend chronology validation
	•	cohort rule validation
	•	deterministic retry messages

Phase 3: polish
	•	better unsupported explanations
	•	repair rules
	•	richer intent parser
	•	summary-quality checks

⸻

15. Recommended defaults

If you want one clear operating mode:
	•	Prefer rejection over substitution
	•	Prefer retry over execution when a plan is structurally wrong
	•	Prefer unsupported over nearest-neighbor answer
	•	Fail result validation on duplicate grain rows
	•	Require explicit truncation labeling when output is partial

That will reduce apparent “success rate” a bit, but it will dramatically improve trust.

⸻

16. Acceptance criteria

The validation layer is successful if it reduces:
	•	wrong metric substitutions
	•	wrong view selections
	•	fabricated answers for unsupported questions
	•	repeated rows for a requested rollup grain

Specifically, on your current eval set it should catch:
	•	EC-17 style wrong view / wrong metric
	•	EC-18 style metric substitution
	•	EC-X2 unsupported substitution
	•	repeated monthly/quarterly row failures across EC-01, EC-06, EC-16, EC-19

⸻

17. Final recommendation

Build this as a deterministic library first, not a prompt trick.

Your current evals show the real problem clearly:
	•	the models are often close enough to be useful
	•	but they are not reliable enough to be trusted without enforcement

The validation layer should be treated as part of the product, not a patch.

If you want, I can turn this into a Python module outline with Pydantic classes and validator function skeletons.