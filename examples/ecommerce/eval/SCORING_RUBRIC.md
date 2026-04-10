# Ecommerce Evaluation Scoring Rubric

This rubric scores how well a result answers a question against the ecommerce semantic views.

It is designed for:

- direct semantic requests
- `ask` workflow outputs
- MCP-assisted analytics answers
- human or model-written summaries of query results

The goal is to evaluate answer quality, not just whether a query executed.

## What We Score

Each evaluated answer should be judged on five dimensions:

1. Question coverage
2. Semantic correctness
3. Analytical quality
4. Communication quality
5. Operational efficiency

Scores are weighted so a result that is fluent but semantically wrong still scores poorly.

## Scorecard

Use a 0 to 5 score for each dimension, then apply the weights below.

| Dimension | Weight | What it measures |
| --- | ---: | --- |
| Question coverage | 30% | Whether the answer actually addresses the user's question |
| Semantic correctness | 30% | Whether the chosen view, dimensions, metrics, and filters are correct |
| Analytical quality | 20% | Whether the result is useful, well-structured, and appropriately interpreted |
| Communication quality | 10% | Whether the answer is clear, concise, and easy to trust |
| Operational efficiency | 10% | Whether the path to the answer was reasonably direct and scoped |

Weighted score formula:

```text
final_score =
  20 * (
    0.30 * coverage +
    0.30 * correctness +
    0.20 * analytical_quality +
    0.10 * communication +
    0.10 * efficiency
  )
```

This yields a final score from 0 to 100.

## Hard Failure Conditions

These should cap the result at a failing score even if other dimensions are strong.

- Wrong semantic view for the question when the correct view is available
- Wrong metric semantics, such as using `gross_sales` when the question asks for net sales
- Missing the main grouping, time grain, or filter explicitly requested by the user
- Fabricating schema elements not present in the ecommerce example
- Contradicting the result table in the written summary
- Claiming unsupported cross-view analysis as if the schema directly supports it

Recommended cap:

- Any major hard failure: final score cannot exceed `49`
- Multiple major hard failures: final score cannot exceed `29`

## Dimension Rubrics

### 1. Question Coverage

How fully does the result answer the actual business question?

| Score | Standard |
| --- | --- |
| 5 | Fully answers the question, including the requested metric, grouping, time grain, and comparison |
| 4 | Answers the main question correctly with only minor omissions |
| 3 | Partially answers the question but misses one important requested element |
| 2 | Addresses the topic but not the actual question asked |
| 1 | Barely relevant to the question |
| 0 | Does not answer the question |

Checks:

- Did it answer the main business intent?
- Did it include the requested breakdown, comparison, or ranking?
- Did it use the requested time window or grain?

### 2. Semantic Correctness

Did the answer use the schema correctly?

| Score | Standard |
| --- | --- |
| 5 | Correct view, dimensions, metrics, joins, and filters throughout |
| 4 | Mostly correct with only minor semantic imprecision that does not change the answer materially |
| 3 | One notable semantic mistake, but the result is still directionally useful |
| 2 | Multiple semantic mistakes that weaken trust in the result |
| 1 | Major semantic misunderstanding |
| 0 | Semantically invalid or fabricated |

Checks:

- Was the best semantic view chosen?
- Were the dimensions and metrics compatible with the question?
- Were derived expressions logically consistent with the metric definitions?
- Were limitations stated when the schema could not support the request directly?

### 3. Analytical Quality

Does the result help someone understand the business outcome?

| Score | Standard |
| --- | --- |
| 5 | Well-shaped result with the right grain, useful ordering, and meaningful interpretation |
| 4 | Solid result structure with minor missed opportunities |
| 3 | Correct but mechanically presented; limited interpretation or prioritization |
| 2 | Weak structure or shallow interpretation |
| 1 | Poorly organized and hard to use |
| 0 | No meaningful analytical value |

Checks:

- Was the result grouped at a useful grain?
- Was the output ordered or filtered to highlight the important signal?
- Did the interpretation identify the main pattern, outlier, or comparison?
- Did it avoid overclaiming causality from descriptive data?

### 4. Communication Quality

Is the answer easy to read and easy to trust?

| Score | Standard |
| --- | --- |
| 5 | Clear, concise, precise, and grounded in the result |
| 4 | Clear overall with small wording or structure issues |
| 3 | Understandable but verbose, vague, or uneven |
| 2 | Hard to follow or missing important framing |
| 1 | Confusing or misleading presentation |
| 0 | Unusable explanation |

Checks:

- Does the answer state what was measured?
- Does it distinguish observed results from interpretation?
- Is the wording specific rather than generic?
- Does it mention the semantic view when useful for traceability?

### 5. Operational Efficiency

Did the workflow get to the answer with reasonable discipline?

| Score | Standard |
| --- | --- |
| 5 | Direct path to the answer with no unnecessary detours |
| 4 | Efficient overall with minor extra work |
| 3 | Acceptable but somewhat repetitive or over-broad |
| 2 | Noticeably inefficient or noisy |
| 1 | Very inefficient or dependent on avoidable retries |
| 0 | Failed to complete efficiently enough to be useful |

Checks:

- Was the question mapped to an appropriate view quickly?
- Were unnecessary extra queries or irrelevant schema explorations avoided?
- Was the result scoped tightly enough for the question?

## Recommended Rating Bands

| Final Score | Rating | Interpretation |
| --- | --- | --- |
| 90-100 | Excellent | Trusted answer; strong candidate as a reference example |
| 75-89 | Good | Useful and mostly correct; minor issues only |
| 60-74 | Adequate | Partially successful but should be improved before showcasing |
| 40-59 | Weak | Important quality issues; not ready as a reference answer |
| 0-39 | Failing | Incorrect, unsupported, or not meaningfully useful |

## Question-Type Adjustments

Not every ecommerce question needs the same judging emphasis.

### Descriptive Rollups

Examples:

- "What are net sales by month?"
- "Which brands sold the most units?"

Emphasize:

- correct metric choice
- correct grouping grain
- sorting and readability

### Ranking Questions

Examples:

- "Which customer segments drive the most lifetime value?"
- "Rank customer states by net sales."

Emphasize:

- correct ordering
- top-N clarity if a limit is used
- whether ties or near-ties are described responsibly

### Comparative Questions

Examples:

- "How do cancelled versus completed orders compare on net sales?"
- "Which payment methods have the highest average order value?"

Emphasize:

- like-for-like comparison
- denominator awareness
- avoiding misleading comparisons from sparse groups

### Exploratory Questions

Examples:

- "What stands out in product sales by brand over time?"
- "Which inactive products still appear in sales?"

Emphasize:

- useful filtering
- interpretation quality
- explicit acknowledgment of uncertainty or follow-up questions

## Evaluation Template

Use this template when scoring a result.

```text
Question:

Expected semantic view:

Observed result:

Scores:
- Question coverage (0-5):
- Semantic correctness (0-5):
- Analytical quality (0-5):
- Communication quality (0-5):
- Operational efficiency (0-5):

Hard failures:

Weighted final score (0-100):

Rationale:

Suggested improvement:
```

## Reference Expectations For This Example

For this ecommerce dataset, a high-quality answer usually:

- explicitly chooses one of `orders_semantic`, `customer_semantic`, or `product_sales_semantic`
- uses metrics already defined in that view instead of recreating them inconsistently
- uses a business-relevant grain such as month, segment, state, brand, or product
- avoids pretending the example supports product-to-segment analysis in one step
- summarizes the top signal instead of only dumping rows
