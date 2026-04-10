# Ecommerce Evaluation Set

This file turns the ecommerce example into a judged eval set.

It pairs each question with:

- an expected semantic view
- the expected analytical grain
- the expected metrics
- common failure modes
- notes on what a high-scoring answer should look like

Use this alongside [SCORING_RUBRIC.md](SCORING_RUBRIC.md).

## How To Use This Set

For each case:

1. Ask the question using `ask`, MCP, or a direct semantic request workflow.
2. Capture the semantic request, result table, and any written explanation.
3. Score the output with the rubric.
4. Record whether the system chose the expected view and grain.

## Eval Cases

### EC-01 Monthly Topline Sales

- Question: "What are net sales, order count, and average order value by month?"
- Expected semantic view: `orders_semantic`
- Question type: descriptive rollup
- Expected grain: month
- Expected dimensions: `date_trunc('month', order_date) as order_month`
- Expected metrics: `net_sales`, `order_count`, `average_order_value`
- Good answer characteristics:
  - groups by month
  - uses net rather than gross sales
  - presents all three topline metrics together
  - highlights any trend or seasonality in the summary
- Common failure modes:
  - using `gross_sales` instead of `net_sales`
  - grouping by day instead of month
  - omitting `average_order_value`
  - choosing `customer_semantic` without need

### EC-02 Channel Revenue Mix

- Question: "Which sales channels generate the most net sales?"
- Expected semantic view: `orders_semantic`
- Question type: ranking
- Expected grain: sales channel
- Expected dimensions: `sales_channel`
- Expected metrics: `net_sales`, optionally `order_count`
- Good answer characteristics:
  - ranks channels by `net_sales` descending
  - optionally includes share of total or order count for context
  - summary names the top and bottom channels
- Common failure modes:
  - sorting alphabetically instead of by metric
  - using order count as the primary answer to a revenue question
  - mixing in unnecessary time grain

### EC-03 Payment Method Comparison

- Question: "Which payment methods have the highest average order value?"
- Expected semantic view: `orders_semantic`
- Question type: comparative ranking
- Expected grain: payment method
- Expected dimensions: `payment_method`
- Expected metrics: `average_order_value`, optionally `order_count`, `net_sales`
- Good answer characteristics:
  - ranks by `average_order_value`
  - includes `order_count` so tiny groups are not over-interpreted
  - summary avoids overclaiming if counts are close or sparse
- Common failure modes:
  - ranking by `net_sales` instead of `average_order_value`
  - omitting denominator context
  - comparing raw totals when the question asks for averages

### EC-04 Discount Trend By Channel

- Question: "How much discount are we giving by channel and by month?"
- Expected semantic view: `orders_semantic`
- Question type: descriptive comparison
- Expected grain: month by sales channel
- Expected dimensions: `date_trunc('month', order_date) as order_month`, `sales_channel`
- Expected metrics: `total_discount`
- Good answer characteristics:
  - uses a two-dimensional breakdown
  - keeps month as the primary time grain
  - summary points out where discounting is concentrated
- Common failure modes:
  - leaving out channel or month
  - substituting `gross_sales` or `net_sales`
  - flattening to a single total that hides the comparison

### EC-05 Geographic Revenue Ranking

- Question: "Rank customer states by net sales."
- Expected semantic view: `orders_semantic`
- Question type: ranking
- Expected grain: customer state
- Expected dimensions: `customer_state`
- Expected metrics: `net_sales`, optionally `order_count`, `average_order_value`
- Good answer characteristics:
  - ranks states descending by `net_sales`
  - handles null or missing geography explicitly if present
  - summary identifies top states and any long-tail shape
- Common failure modes:
  - grouping by `customer_country` instead of `customer_state`
  - ranking by order count
  - returning unordered rows

### EC-06 Shipping And Tax Over Time

- Question: "How much shipping revenue and tax are collected over time?"
- Expected semantic view: `orders_semantic`
- Question type: descriptive rollup
- Expected grain: month
- Expected dimensions: `date_trunc('month', order_date) as order_month`
- Expected metrics: `total_shipping`, `total_tax`
- Good answer characteristics:
  - returns both measures together at a consistent time grain
  - summary compares their trajectories rather than only listing values
- Common failure modes:
  - answering only one metric
  - using net sales as a proxy
  - grouping by a non-time dimension

### EC-07 Order Status Comparison

- Question: "How do cancelled versus completed orders compare on gross sales and net sales?"
- Expected semantic view: `orders_semantic`
- Question type: comparison
- Expected grain: order status
- Expected dimensions: `order_status`
- Expected metrics: `gross_sales`, `net_sales`, optionally `order_count`
- Good answer characteristics:
  - compares the requested statuses directly
  - shows both gross and net measures
  - notes if other statuses exist and whether they were excluded
- Common failure modes:
  - using only one sales metric
  - failing to constrain or explain included statuses
  - comparing statuses without order counts for context

### EC-08 Customers By Segment

- Question: "How many customers do we have by segment?"
- Expected semantic view: `customer_semantic`
- Question type: descriptive ranking
- Expected grain: segment
- Expected dimensions: `segment_name`, optionally `segment_type`
- Expected metrics: `customer_count`
- Good answer characteristics:
  - uses customer-centric counting
  - includes segment labels clearly
  - summary identifies the largest segments
- Common failure modes:
  - using `order_count` instead of `customer_count`
  - choosing `orders_semantic`, which does not expose segment detail in this example
  - failing to distinguish `segment_name` from `segment_type`

### EC-09 Segment Lifetime Value

- Question: "Which customer segments drive the most lifetime value?"
- Expected semantic view: `customer_semantic`
- Question type: ranking
- Expected grain: segment
- Expected dimensions: `segment_name`, optionally `segment_type`
- Expected metrics: `lifetime_value`, optionally `customer_count`, `average_order_value`
- Good answer characteristics:
  - ranks segments by `lifetime_value`
  - optionally includes customer count to separate scale from value density
  - summary distinguishes total segment contribution from per-order efficiency
- Common failure modes:
  - using `average_order_value` as the only ranking metric
  - choosing `orders_semantic`
  - over-interpreting without customer-count context

### EC-10 Signup Cohort Growth

- Question: "How many customers signed up each month?"
- Expected semantic view: `customer_semantic`
- Question type: descriptive rollup
- Expected grain: signup month
- Expected dimensions: `date_trunc('month', signup_date) as signup_month`
- Expected metrics: `customer_count`
- Good answer characteristics:
  - uses signup date rather than order date
  - groups at monthly cohort grain
  - summary describes growth or contraction over time
- Common failure modes:
  - using `order_date`
  - counting orders instead of customers
  - returning customer-level detail instead of a cohort rollup

### EC-11 Lifetime Value By Signup Cohort

- Question: "How does lifetime value vary by signup cohort?"
- Expected semantic view: `customer_semantic`
- Question type: cohort comparison
- Expected grain: signup month
- Expected dimensions: `date_trunc('month', signup_date) as signup_month`
- Expected metrics: `lifetime_value`, optionally `customer_count`, `average_order_value`
- Good answer characteristics:
  - frames cohorts on signup date
  - compares cohort total value, ideally with customer counts for context
  - summary avoids causal claims not supported by the data
- Common failure modes:
  - cohorting on `order_date`
  - omitting the cohort dimension entirely
  - presenting only customer count

### EC-12 Segment And Channel Mix

- Question: "How many orders come from each segment and sales channel combination?"
- Expected semantic view: `customer_semantic`
- Question type: matrix breakdown
- Expected grain: segment by sales channel
- Expected dimensions: `segment_name`, `sales_channel`
- Expected metrics: `order_count`
- Good answer characteristics:
  - uses both requested dimensions together
  - returns a clear matrix or sorted long table
  - summary identifies the strongest combinations
- Common failure modes:
  - omitting one dimension
  - using `customer_count`
  - choosing a product-oriented view

### EC-13 Product Revenue Leaders

- Question: "Which products generate the most net item sales?"
- Expected semantic view: `product_sales_semantic`
- Question type: ranking
- Expected grain: product
- Expected dimensions: `product_name`, optionally `product_id`
- Expected metrics: `net_item_sales`, optionally `units_sold`, `average_selling_price`
- Good answer characteristics:
  - ranks products by `net_item_sales`
  - includes units or price as supporting context
  - summary identifies top products clearly
- Common failure modes:
  - ranking by `units_sold` when the question asks for sales
  - grouping only at brand or category level
  - using order-level revenue metrics from another view

### EC-14 Brand And Category Volume

- Question: "Which brands or categories sell the most units?"
- Expected semantic view: `product_sales_semantic`
- Question type: ranking
- Expected grain: brand or category
- Expected dimensions: `brand_name` or `category_id`
- Expected metrics: `units_sold`
- Good answer characteristics:
  - uses the requested grouping level
  - ranks by `units_sold`
  - does not imply human-readable category names beyond `category_id`
- Common failure modes:
  - using `net_item_sales` as the primary answer
  - inventing category names not present in the schema
  - mixing brand and product grain in one unsound result

### EC-15 Average Selling Price By Brand

- Question: "What is average selling price by brand?"
- Expected semantic view: `product_sales_semantic`
- Question type: comparative rollup
- Expected grain: brand
- Expected dimensions: `brand_name`
- Expected metrics: `average_selling_price`, optionally `units_sold`
- Good answer characteristics:
  - uses the predefined average selling price metric
  - includes units sold for context where helpful
  - summary flags small-sample risk if needed
- Common failure modes:
  - manually dividing the wrong fields
  - ranking by total sales instead of average selling price
  - omitting brand grain

### EC-16 Product Sales Trend

- Question: "How do product sales trend by month?"
- Expected semantic view: `product_sales_semantic`
- Question type: descriptive trend
- Expected grain: month
- Expected dimensions: `date_trunc('month', order_date) as order_month`
- Expected metrics: `net_item_sales`, optionally `units_sold`
- Good answer characteristics:
  - uses order date at monthly grain
  - tracks item-level sales over time
  - summary notes major trend changes or peaks
- Common failure modes:
  - using `launch_date` as the main trend axis
  - using order-level net sales instead of item-level net item sales
  - omitting the time dimension

### EC-17 Revenue By Payment Method At Item Level

- Question: "Which payment methods are associated with the most product revenue?"
- Expected semantic view: `product_sales_semantic`
- Question type: ranking
- Expected grain: payment method
- Expected dimensions: `payment_method`
- Expected metrics: `net_item_sales`, optionally `units_sold`
- Good answer characteristics:
  - uses item-level revenue metric with order-context dimension
  - ranks payment methods by sales
  - summary distinguishes revenue from volume if both are shown
- Common failure modes:
  - switching to `orders_semantic` unnecessarily
  - using gross instead of net item sales without explanation
  - ranking by count of line items only

### EC-18 Inactive Products With Sales

- Question: "Which inactive products still appear in recent sales?"
- Expected semantic view: `product_sales_semantic`
- Question type: exploratory exception finding
- Expected grain: product
- Expected dimensions: `product_name`, `is_active`, optionally `date_trunc('month', order_date) as order_month`
- Expected metrics: `net_item_sales` or `units_sold`, optionally `line_count`
- Expected filters: `is_active = false`
- Good answer characteristics:
  - filters to inactive products
  - uses a recent time window if the workflow supports one and states it clearly
  - highlights unusual exceptions rather than dumping all rows without framing
- Common failure modes:
  - forgetting the inactive filter
  - not defining what "recent" means
  - using an active/inactive dimension without any sales metric

### EC-19 Quarterly Sales Rollup

- Question: "What are net sales by quarter?"
- Expected semantic view: `orders_semantic`
- Question type: descriptive rollup
- Expected grain: quarter
- Expected dimensions: `date_trunc('quarter', order_date) as order_quarter`
- Expected metrics: `net_sales`
- Good answer characteristics:
  - uses quarter grain rather than month or raw date
  - keeps the answer at order-level net sales
  - summarizes the quarterly trend clearly
- Common failure modes:
  - defaulting to month despite the explicit quarter request
  - grouping by raw `order_date`
  - substituting `gross_sales` for `net_sales`

## Unsupported Or Trick Cases

These are useful negative tests and should score poorly if the system answers them confidently without caveat.

### EC-X1 Product Sales By Customer Segment

- Question: "Which customer segments buy the most from each product category?"
- Expected outcome: unsupported directly by the current semantic views
- Why: no single view exposes product sales and customer segments together
- High-scoring behavior:
  - states the limitation clearly
  - suggests that this would require a new semantic view or a broader join path
- Failure mode:
  - fabricating a direct answer as if the schema already supports it

### EC-X2 Marketing Attribution

- Question: "Which marketing campaigns drive the most net sales?"
- Expected outcome: unsupported
- Why: the ecommerce example has no marketing campaign dimension or attribution model
- High-scoring behavior:
  - says the question cannot be answered from the current schema
  - optionally points to the missing model needed
- Failure mode:
  - inventing campaign fields or making unsupported claims
