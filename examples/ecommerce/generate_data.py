#!/usr/bin/env python3

"""
Generate fake ecommerce demo data and write it to a DuckDB database.

Usage:
    python generate_ecommerce_duckdb.py
    python generate_ecommerce_duckdb.py --db ecommerce_demo.duckdb
    python generate_ecommerce_duckdb.py --customers 500 --products 120 --orders 4000
    python generate_ecommerce_duckdb.py --export-csv

Dependencies:
    pip install duckdb faker
"""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

import duckdb
from faker import Faker


fake = Faker()


def money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def daterange(start: date, end: date) -> date:
    delta_days = (end - start).days
    return start + timedelta(days=random.randint(0, delta_days))


def weighted_choice(options: list[tuple[str, float]]) -> str:
    values = [v for v, _ in options]
    weights = [w for _, w in options]
    return random.choices(values, weights=weights, k=1)[0]


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            normalized = {}
            for key, value in row.items():
                if isinstance(value, Decimal):
                    normalized[key] = f"{value:.2f}"
                elif isinstance(value, date):
                    normalized[key] = value.isoformat()
                elif isinstance(value, bool):
                    normalized[key] = value
                else:
                    normalized[key] = value
            writer.writerow(normalized)


@dataclass
class Segment:
    segment_id: str
    segment_name: str
    segment_type: str


@dataclass
class Category:
    category_id: str
    category_name: str
    parent_category_id: str | None


@dataclass
class Product:
    product_id: str
    product_name: str
    category_id: str
    brand_name: str
    unit_price: Decimal
    is_active: bool
    launch_date: date


@dataclass
class Customer:
    customer_id: str
    customer_name: str
    email: str
    signup_date: date
    segment_id: str
    city: str
    state: str
    country: str


def generate_segments() -> list[Segment]:
    return [
        Segment("SEG001", "New", "Lifecycle"),
        Segment("SEG002", "Returning", "Lifecycle"),
        Segment("SEG003", "VIP", "Value"),
        Segment("SEG004", "Wholesale", "Business"),
    ]


def generate_categories() -> list[Category]:
    return [
        Category("CAT001", "Apparel", None),
        Category("CAT002", "Footwear", None),
        Category("CAT003", "Accessories", None),
        Category("CAT004", "Electronics", None),
        Category("CAT005", "Outerwear", "CAT001"),
        Category("CAT006", "Athletic Shoes", "CAT002"),
        Category("CAT007", "Bags", "CAT003"),
        Category("CAT008", "Audio", "CAT004"),
    ]


def category_brand_pool() -> dict[str, list[str]]:
    return {
        "Apparel": ["Northline", "Blue Harbor", "Common Thread", "Peak State"],
        "Footwear": ["Stridewell", "Trailmark", "Summit Sole", "Urban Step"],
        "Accessories": ["Oak & Iron", "Fieldcraft", "Carrywell", "Everlane Co"],
        "Electronics": ["NovaTech", "SignalWorks", "BrightWave", "Circuit & Co"],
        "Outerwear": ["Northline", "Peak State", "Drift Supply", "Ridge & Pine"],
        "Athletic Shoes": ["Stridewell", "Summit Sole", "Run Harbor", "Motion Lab"],
        "Bags": ["Carrywell", "Oak & Iron", "Fieldcraft", "Transit Co"],
        "Audio": ["NovaTech", "BrightWave", "SignalWorks", "Echo Ridge"],
    }


def product_name_for(category_name: str) -> str:
    words = {
        "Apparel": ["Tee", "Henley", "Polo", "Jogger", "Crewneck"],
        "Footwear": ["Sneaker", "Boot", "Runner", "Slip-On", "Trainer"],
        "Accessories": ["Cap", "Belt", "Wallet", "Scarf", "Watch Band"],
        "Electronics": ["Speaker", "Charger", "Headphones", "Mouse", "Keyboard"],
        "Outerwear": ["Jacket", "Puffer", "Shell", "Vest", "Parka"],
        "Athletic Shoes": ["Road Runner", "Court Shoe", "Trainer", "Trail Shoe"],
        "Bags": ["Backpack", "Duffel", "Tote", "Sling", "Briefcase"],
        "Audio": ["Earbuds", "Portable Speaker", "Soundbar", "Headset"],
    }
    adjectives = [
        "Classic",
        "Essential",
        "Pro",
        "Everyday",
        "Trail",
        "Summit",
        "Urban",
        "Lite",
        "Premium",
        "Core",
    ]
    return f"{random.choice(adjectives)} {random.choice(words[category_name])}"


def price_range_for(category_name: str) -> tuple[int, int]:
    ranges = {
        "Apparel": (18, 90),
        "Footwear": (45, 160),
        "Accessories": (12, 80),
        "Electronics": (20, 220),
        "Outerwear": (60, 240),
        "Athletic Shoes": (70, 180),
        "Bags": (35, 170),
        "Audio": (30, 250),
    }
    return ranges[category_name]


def generate_products(categories: list[Category], count: int) -> list[Product]:
    brands = category_brand_pool()
    products: list[Product] = []

    for i in range(1, count + 1):
        cat = random.choice(categories)
        low, high = price_range_for(cat.category_name)
        base_price = money(random.uniform(low, high))
        products.append(
            Product(
                product_id=f"PROD{i:05d}",
                product_name=product_name_for(cat.category_name),
                category_id=cat.category_id,
                brand_name=random.choice(brands[cat.category_name]),
                unit_price=base_price,
                is_active=random.random() > 0.08,
                launch_date=daterange(date(2022, 1, 1), date(2025, 12, 31)),
            )
        )
    return products


def generate_customers(segments: list[Segment], count: int) -> list[Customer]:
    segment_weights = [
        ("SEG001", 0.24),
        ("SEG002", 0.52),
        ("SEG003", 0.18),
        ("SEG004", 0.06),
    ]
    customers: list[Customer] = []
    for i in range(1, count + 1):
        first = fake.first_name()
        last = fake.last_name()
        signup = daterange(date(2022, 1, 1), date(2026, 3, 15))
        customers.append(
            Customer(
                customer_id=f"CUST{i:05d}",
                customer_name=f"{first} {last}",
                email=f"{first.lower()}.{last.lower()}{random.randint(1,999):03d}@example.com",
                signup_date=signup,
                segment_id=weighted_choice(segment_weights),
                city=fake.city(),
                state=fake.state_abbr(),
                country="US",
            )
        )
    return customers


def order_status_for() -> str:
    return weighted_choice(
        [
            ("completed", 0.84),
            ("returned", 0.06),
            ("cancelled", 0.05),
            ("pending", 0.05),
        ]
    )


def sales_channel_for() -> str:
    return weighted_choice(
        [
            ("online", 0.62),
            ("mobile_app", 0.23),
            ("marketplace", 0.10),
            ("store", 0.05),
        ]
    )


def payment_method_for() -> str:
    return weighted_choice(
        [
            ("credit_card", 0.54),
            ("paypal", 0.18),
            ("apple_pay", 0.14),
            ("gift_card", 0.06),
            ("bank_transfer", 0.08),
        ]
    )


def customer_order_bias(customers: list[Customer]) -> list[float]:
    weights = []
    for c in customers:
        if c.segment_id == "SEG003":
            weights.append(3.2)
        elif c.segment_id == "SEG002":
            weights.append(2.0)
        elif c.segment_id == "SEG004":
            weights.append(1.6)
        else:
            weights.append(1.0)
    return weights


def generate_orders_and_items(
    customers: list[Customer],
    products: list[Product],
    order_count: int,
) -> tuple[list[dict], list[dict]]:
    orders: list[dict] = []
    order_items: list[dict] = []

    customer_weights = customer_order_bias(customers)

    product_weights = []
    for p in products:
        active_boost = 1.0 if p.is_active else 0.2
        price_penalty = 1.0
        if p.unit_price > Decimal("150"):
            price_penalty = 0.75
        elif p.unit_price < Decimal("30"):
            price_penalty = 1.15
        product_weights.append(active_boost * price_penalty)

    for order_num in range(1, order_count + 1):
        customer = random.choices(customers, weights=customer_weights, k=1)[0]
        status = order_status_for()
        order_date = daterange(max(customer.signup_date, date(2023, 1, 1)), date(2026, 3, 31))
        sales_channel = sales_channel_for()
        payment_method = payment_method_for()

        if customer.segment_id == "SEG004":
            line_count = random.randint(3, 8)
        elif customer.segment_id == "SEG003":
            line_count = random.randint(2, 6)
        else:
            line_count = random.randint(1, 5)

        chosen_products = random.choices(products, weights=product_weights, k=line_count)

        subtotal = Decimal("0.00")
        order_discount = Decimal("0.00")
        item_rows: list[dict] = []

        for item_idx, product in enumerate(chosen_products, start=1):
            quantity = random.randint(1, 6) if customer.segment_id == "SEG004" else random.randint(1, 3)
            unit_price = money(product.unit_price * Decimal(str(random.uniform(0.92, 1.05))))
            gross_item_amount = money(unit_price * quantity)

            if status == "cancelled":
                discount_rate = Decimal("0.00")
            elif customer.segment_id == "SEG003":
                discount_rate = Decimal(str(random.choice([0, 0.05, 0.10, 0.15])))
            elif sales_channel == "marketplace":
                discount_rate = Decimal(str(random.choice([0, 0.03, 0.05])))
            else:
                discount_rate = Decimal(str(random.choice([0, 0.00, 0.05, 0.10])))

            discount_item_amount = money(gross_item_amount * discount_rate)
            net_item_amount = gross_item_amount - discount_item_amount

            subtotal += gross_item_amount
            order_discount += discount_item_amount

            item_rows.append(
                {
                    "order_item_id": f"ITEM{order_num:06d}_{item_idx:02d}",
                    "order_id": f"ORD{order_num:06d}",
                    "product_id": product.product_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "gross_item_amount": gross_item_amount,
                    "discount_item_amount": discount_item_amount,
                    "net_item_amount": net_item_amount,
                }
            )

        if status == "cancelled":
            tax_amount = Decimal("0.00")
            shipping_amount = Decimal("0.00")
            total_amount = Decimal("0.00")
            subtotal_amount = Decimal("0.00")
            discount_amount = Decimal("0.00")
            for row in item_rows:
                row["gross_item_amount"] = Decimal("0.00")
                row["discount_item_amount"] = Decimal("0.00")
                row["net_item_amount"] = Decimal("0.00")
        else:
            subtotal_amount = money(subtotal)
            discount_amount = money(order_discount)
            taxable_base = subtotal_amount - discount_amount
            tax_rate = Decimal(str(random.uniform(0.05, 0.095)))
            tax_amount = money(taxable_base * tax_rate)

            if taxable_base >= Decimal("100"):
                shipping_amount = Decimal("0.00")
            else:
                shipping_amount = money(random.uniform(4.99, 12.99))

            total_amount = taxable_base + tax_amount + shipping_amount

        orders.append(
            {
                "order_id": f"ORD{order_num:06d}",
                "customer_id": customer.customer_id,
                "order_date": order_date,
                "order_status": status,
                "sales_channel": sales_channel,
                "payment_method": payment_method,
                "subtotal_amount": subtotal_amount,
                "discount_amount": discount_amount,
                "tax_amount": tax_amount,
                "shipping_amount": shipping_amount,
                "total_amount": money(total_amount),
            }
        )
        order_items.extend(item_rows)

    return orders, order_items


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("drop table if exists order_items")
    con.execute("drop table if exists orders")
    con.execute("drop table if exists products")
    con.execute("drop table if exists categories")
    con.execute("drop table if exists customers")
    con.execute("drop table if exists customer_segments")

    con.execute(
        """
        create table customer_segments (
            segment_id varchar primary key,
            segment_name varchar not null,
            segment_type varchar
        )
        """
    )

    con.execute(
        """
        create table customers (
            customer_id varchar primary key,
            customer_name varchar not null,
            email varchar,
            signup_date date,
            segment_id varchar,
            city varchar,
            state varchar,
            country varchar
        )
        """
    )

    con.execute(
        """
        create table categories (
            category_id varchar primary key,
            category_name varchar not null,
            parent_category_id varchar
        )
        """
    )

    con.execute(
        """
        create table products (
            product_id varchar primary key,
            product_name varchar not null,
            category_id varchar,
            brand_name varchar,
            unit_price decimal(12,2) not null,
            is_active boolean,
            launch_date date
        )
        """
    )

    con.execute(
        """
        create table orders (
            order_id varchar primary key,
            customer_id varchar not null,
            order_date date not null,
            order_status varchar not null,
            sales_channel varchar,
            payment_method varchar,
            subtotal_amount decimal(12,2) not null,
            discount_amount decimal(12,2) not null default 0,
            tax_amount decimal(12,2) not null default 0,
            shipping_amount decimal(12,2) not null default 0,
            total_amount decimal(12,2) not null
        )
        """
    )

    con.execute(
        """
        create table order_items (
            order_item_id varchar primary key,
            order_id varchar not null,
            product_id varchar not null,
            quantity integer not null,
            unit_price decimal(12,2) not null,
            gross_item_amount decimal(12,2) not null,
            discount_item_amount decimal(12,2) not null default 0,
            net_item_amount decimal(12,2) not null
        )
        """
    )


def insert_data(
    con: duckdb.DuckDBPyConnection,
    segments: list[Segment],
    categories: list[Category],
    products: list[Product],
    customers: list[Customer],
    orders: list[dict],
    order_items: list[dict],
) -> None:
    con.executemany(
        "insert into customer_segments values (?, ?, ?)",
        [(s.segment_id, s.segment_name, s.segment_type) for s in segments],
    )

    con.executemany(
        "insert into categories values (?, ?, ?)",
        [(c.category_id, c.category_name, c.parent_category_id) for c in categories],
    )

    con.executemany(
        "insert into products values (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                p.product_id,
                p.product_name,
                p.category_id,
                p.brand_name,
                p.unit_price,
                p.is_active,
                p.launch_date,
            )
            for p in products
        ],
    )

    con.executemany(
        "insert into customers values (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                c.customer_id,
                c.customer_name,
                c.email,
                c.signup_date,
                c.segment_id,
                c.city,
                c.state,
                c.country,
            )
            for c in customers
        ],
    )

    con.executemany(
        "insert into orders values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                o["order_id"],
                o["customer_id"],
                o["order_date"],
                o["order_status"],
                o["sales_channel"],
                o["payment_method"],
                o["subtotal_amount"],
                o["discount_amount"],
                o["tax_amount"],
                o["shipping_amount"],
                o["total_amount"],
            )
            for o in orders
        ],
    )

    con.executemany(
        "insert into order_items values (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                oi["order_item_id"],
                oi["order_id"],
                oi["product_id"],
                oi["quantity"],
                oi["unit_price"],
                oi["gross_item_amount"],
                oi["discount_item_amount"],
                oi["net_item_amount"],
            )
            for oi in order_items
        ],
    )


def export_csvs(
    output_dir: Path,
    segments: list[Segment],
    categories: list[Category],
    products: list[Product],
    customers: list[Customer],
    orders: list[dict],
    order_items: list[dict],
) -> None:
    write_csv(
        output_dir / "customer_segments.csv",
        ["segment_id", "segment_name", "segment_type"],
        (
            {
                "segment_id": s.segment_id,
                "segment_name": s.segment_name,
                "segment_type": s.segment_type,
            }
            for s in segments
        ),
    )

    write_csv(
        output_dir / "categories.csv",
        ["category_id", "category_name", "parent_category_id"],
        (
            {
                "category_id": c.category_id,
                "category_name": c.category_name,
                "parent_category_id": c.parent_category_id or "",
            }
            for c in categories
        ),
    )

    write_csv(
        output_dir / "products.csv",
        [
            "product_id",
            "product_name",
            "category_id",
            "brand_name",
            "unit_price",
            "is_active",
            "launch_date",
        ],
        (
            {
                "product_id": p.product_id,
                "product_name": p.product_name,
                "category_id": p.category_id,
                "brand_name": p.brand_name,
                "unit_price": p.unit_price,
                "is_active": p.is_active,
                "launch_date": p.launch_date,
            }
            for p in products
        ),
    )

    write_csv(
        output_dir / "customers.csv",
        [
            "customer_id",
            "customer_name",
            "email",
            "signup_date",
            "segment_id",
            "city",
            "state",
            "country",
        ],
        (
            {
                "customer_id": c.customer_id,
                "customer_name": c.customer_name,
                "email": c.email,
                "signup_date": c.signup_date,
                "segment_id": c.segment_id,
                "city": c.city,
                "state": c.state,
                "country": c.country,
            }
            for c in customers
        ),
    )

    write_csv(
        output_dir / "orders.csv",
        [
            "order_id",
            "customer_id",
            "order_date",
            "order_status",
            "sales_channel",
            "payment_method",
            "subtotal_amount",
            "discount_amount",
            "tax_amount",
            "shipping_amount",
            "total_amount",
        ],
        orders,
    )

    write_csv(
        output_dir / "order_items.csv",
        [
            "order_item_id",
            "order_id",
            "product_id",
            "quantity",
            "unit_price",
            "gross_item_amount",
            "discount_item_amount",
            "net_item_amount",
        ],
        order_items,
    )


def print_summary(con: duckdb.DuckDBPyConnection) -> None:
    print("\nTable counts:")
    for table in [
        "customer_segments",
        "customers",
        "categories",
        "products",
        "orders",
        "order_items",
    ]:
        count = con.execute(f"select count(*) from {table}").fetchone()[0]
        print(f"  {table}: {count}")

    print("\nSample query:")
    rows = con.execute(
        """
        select
            c.customer_name,
            sum(oi.net_item_amount) as total_revenue
        from order_items oi
        join orders o on oi.order_id = o.order_id
        join customers c on o.customer_id = c.customer_id
        where o.order_status = 'completed'
        group by 1
        order by 2 desc
        limit 10
        """
    ).fetchall()

    for row in rows[:5]:
        print(f"  {row[0]} -> {row[1]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate fake ecommerce demo data in DuckDB.")
    parser.add_argument("--db", default="ecommerce_demo.duckdb", help="DuckDB database file path.")
    parser.add_argument("--customers", type=int, default=500, help="Number of customers.")
    parser.add_argument("--products", type=int, default=120, help="Number of products.")
    parser.add_argument("--orders", type=int, default=4000, help="Number of orders.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--export-csv", action="store_true", help="Also export tables as CSV files.")
    parser.add_argument("--csv-dir", default="demo_data", help="CSV export directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    random.seed(args.seed)
    Faker.seed(args.seed)

    segments = generate_segments()
    categories = generate_categories()
    products = generate_products(categories, args.products)
    customers = generate_customers(segments, args.customers)
    orders, order_items = generate_orders_and_items(customers, products, args.orders)

    db_path = Path(args.db)
    con = duckdb.connect(str(db_path))

    try:
        create_schema(con)
        insert_data(con, segments, categories, products, customers, orders, order_items)
        print(f"Created DuckDB database: {db_path.resolve()}")

        if args.export_csv:
            export_csvs(
                Path(args.csv_dir),
                segments,
                categories,
                products,
                customers,
                orders,
                order_items,
            )
            print(f"Exported CSVs to: {Path(args.csv_dir).resolve()}")

        print_summary(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()