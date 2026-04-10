# Ecommerce Example

This example includes three semantic views:

- `orders_semantic`: order-level sales and customer geography
- `customer_semantic`: customer, segment, and lifetime value analysis
- `product_sales_semantic`: item-level product and order context analysis

These questions are grounded in the existing schema so we can use them later for CLI, Python, dbt, or MCP query walkthroughs.

For evaluation design, see [eval/README.md](eval/README.md).

## View Inventory

### `orders_semantic`

Best for order performance, channel mix, payments, and customer location rollups.

Available dimensions and time dimensions include:

- `order_id`
- `order_status`
- `sales_channel`
- `payment_method`
- `order_date`
- `customer_id`
- `customer_name`
- `customer_city`
- `customer_state`
- `customer_country`
- `signup_date`

Available metrics include:

- `gross_sales`
- `total_discount`
- `total_tax`
- `total_shipping`
- `net_sales`
- `order_count`
- `average_order_value`

### `customer_semantic`

Best for customer counts, segments, signup cohorts, and lifetime value.

Available dimensions and time dimensions include:

- `customer_id`
- `customer_name`
- `email`
- `city`
- `state`
- `country`
- `segment_name`
- `segment_type`
- `order_status`
- `sales_channel`
- `signup_date`
- `order_date`

Available metrics include:

- `customer_count`
- `order_count`
- `lifetime_value`
- `average_order_value`

### `product_sales_semantic`

Best for product, brand, category, and item-level sales analysis.

Available dimensions and time dimensions include:

- `order_item_id`
- `product_id`
- `product_name`
- `category_id`
- `brand_name`
- `is_active`
- `order_status`
- `sales_channel`
- `payment_method`
- `launch_date`
- `order_date`

Available metrics include:

- `units_sold`
- `gross_item_sales`
- `item_discount`
- `net_item_sales`
- `line_count`
- `average_selling_price`

## Questions To Ask

### `orders_semantic`

- What are net sales, order count, and average order value by month?
- Which sales channels generate the most net sales?
- Which payment methods are most common, and do they differ in average order value?
- How much discount are we giving by channel and by month?
- Which customer states or countries contribute the most revenue?
- How much shipping revenue and tax are collected over time?
- How do cancelled versus completed orders compare on gross sales and net sales?

Example request sketch:

```text
orders_semantic
dimensions date_trunc('month', order_date) as order_month, sales_channel
metrics net_sales, order_count, average_order_value
```

Natural-language examples:

- "Show monthly net sales and order count by sales channel."
- "Which payment methods have the highest average order value?"
- "Rank customer states by net sales."

### `customer_semantic`

- How many customers do we have by segment?
- Which customer segments drive the most lifetime value?
- What is average order value by customer segment?
- How many customers signed up each month?
- How does lifetime value vary by signup cohort?
- Which cities or states have the highest-value customers?
- How many orders come from each segment and sales channel combination?

Example request sketch:

```text
customer_semantic
dimensions segment_name, segment_type
metrics customer_count, lifetime_value, average_order_value
```

Natural-language examples:

- "Which customer segments have the highest lifetime value?"
- "Show customer count by signup month."
- "Compare average order value across segment types."

### `product_sales_semantic`

- Which products generate the most net item sales?
- Which brands or categories sell the most units?
- What is average selling price by brand?
- How do product sales trend by month?
- Which payment methods are associated with the most product revenue?
- Which sales channels move the most units?
- Which inactive products still appear in recent sales?

Example request sketch:

```text
product_sales_semantic
dimensions brand_name, category_id
metrics units_sold, net_item_sales, average_selling_price
```

Natural-language examples:

- "Show monthly net item sales by brand."
- "Which products sold the most units?"
- "Compare average selling price by category."

## Whole-Schema Demo Flow

If we want to show how querying works across the example as a whole, a good progression is:

1. Start with `orders_semantic` for top-line business performance.
2. Move to `customer_semantic` to explain who is driving that performance.
3. Move to `product_sales_semantic` to explain what is being sold.

That gives us a clean narrative:

- "How is the business doing?"
- "Which customers or segments are driving it?"
- "Which products and brands explain the result?"

## Current Boundaries

The current example does not expose every possible cross-cut. In particular:

- There is no single semantic view that joins products directly to customer segments.
- There is no inventory, return, or marketing attribution model in this schema.
- `product_sales_semantic` exposes `category_id`, but not a separate category dimension table with names.

Those gaps are useful candidates for later example expansion if we want more advanced end-to-end demos.
