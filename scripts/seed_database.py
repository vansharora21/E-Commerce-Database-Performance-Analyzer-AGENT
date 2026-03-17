"""
scripts/seed_database.py
─────────────────────────
Populates the MongoDB fashion_ecommerce database with realistic
fake data so the agent has something to query from day one.

Generates:
  - 200 users
  - 150 products across 5 categories
  - 1 200 orders spanning the last 6 months
  - 1 200 payments linked to orders

Run: python scripts/seed_database.py
"""
import asyncio
import random
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow importing from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from faker import Faker
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import track

load_dotenv()
fake = Faker("en_IN")
console = Console()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/fashion_ecommerce")
DB_NAME     = os.getenv("DB_NAME", "fashion_ecommerce")

# ── Config ────────────────────────────────────────────────────────────────────
N_USERS    = 200
N_PRODUCTS = 150
N_ORDERS   = 1200

CATEGORIES   = ["tops", "dresses", "shoes", "accessories", "bottoms"]
BRANDS       = ["Zara", "H&M", "Mango", "FabIndia", "W", "Biba", "Vero Moda", "AND", "Avaasa", "Aurelia"]
CITIES       = ["Mumbai", "Delhi", "Bangalore", "Chennai", "Hyderabad", "Pune", "Kolkata", "Jaipur", "Ahmedabad", "Surat"]
TIERS        = ["bronze", "silver", "gold", "platinum"]
ORDER_STATUS = ["pending", "confirmed", "shipped", "delivered", "cancelled", "returned"]
PAY_STATUS   = ["pending", "paid", "failed", "refunded"]
PAY_METHODS  = ["card", "cod", "upi", "wallet", "bnpl"]

STATUS_WEIGHTS  = [0.05, 0.10, 0.15, 0.55, 0.08, 0.07]
PAY_METH_WEIGHTS = [0.20, 0.25, 0.35, 0.10, 0.10]


def rand_date(start_days_ago: int = 180) -> datetime:
    base = datetime.now(timezone.utc) - timedelta(days=start_days_ago)
    offset = random.randint(0, start_days_ago * 86400)
    return base + timedelta(seconds=offset)


# ── Generators ────────────────────────────────────────────────────────────────

def make_products() -> list[dict]:
    products = []
    for _ in range(N_PRODUCTS):
        cat = random.choice(CATEGORIES)
        price = round(random.uniform(299, 4999), 2)
        sold  = random.randint(0, 800)
        products.append({
            "name":      f"{random.choice(BRANDS)} {cat.title()} {fake.color_name()}",
            "category":  cat,
            "brand":     random.choice(BRANDS),
            "price":     price,
            "stock":     random.randint(0, 200),
            "soldCount": sold,
            "rating":    round(random.uniform(2.5, 5.0), 1),
            "isActive":  random.random() > 0.05,
            "createdAt": rand_date(365),
        })
    return products


def make_users() -> list[dict]:
    users = []
    for _ in range(N_USERS):
        orders = random.randint(0, 40)
        spent  = round(random.uniform(0, 60000), 2)
        tier   = (
            "platinum" if spent > 40000 else
            "gold"     if spent > 20000 else
            "silver"   if spent > 8000  else
            "bronze"
        )
        users.append({
            "city":        random.choice(CITIES),
            "totalOrders": orders,
            "totalSpent":  spent,
            "tier":        tier,
            "isActive":    random.random() > 0.08,
            "createdAt":   rand_date(365),
        })
    return users


def make_orders(user_ids, product_pool) -> tuple[list[dict], list[dict]]:
    orders   = []
    payments = []

    for _ in range(N_ORDERS):
        user_id = random.choice(user_ids)
        n_items = random.randint(1, 4)
        items   = []
        total   = 0.0

        for _ in range(n_items):
            p = random.choice(product_pool)
            qty   = random.randint(1, 3)
            price = p["price"]
            items.append({
                "productId": p["_id"],
                "name":      p["name"],
                "quantity":  qty,
                "price":     price,
                "category":  p["category"],
            })
            total += qty * price

        total = round(total, 2)
        status = random.choices(ORDER_STATUS, weights=STATUS_WEIGHTS)[0]
        pay_status = "paid" if status in ("confirmed", "shipped", "delivered") else \
                     "refunded" if status == "returned" else \
                     random.choices(PAY_STATUS, weights=[0.1, 0.6, 0.2, 0.1])[0]
        created = rand_date(180)

        order = {
            "userId":       user_id,
            "items":        items,
            "totalAmount":  total,
            "status":       status,
            "paymentStatus": pay_status,
            "shippingCity": random.choice(CITIES),
            "createdAt":    created,
            "updatedAt":    created + timedelta(hours=random.randint(1, 72)),
        }
        orders.append(order)

        method = random.choices(PAY_METHODS, weights=PAY_METH_WEIGHTS)[0]
        payments.append({
            "amount":    total,
            "method":    method,
            "status":    "success" if pay_status == "paid" else
                         "refunded" if pay_status == "refunded" else
                         "failed"   if pay_status == "failed" else "pending",
            "createdAt": created + timedelta(minutes=random.randint(1, 60)),
        })

    return orders, payments


# ── Main ──────────────────────────────────────────────────────────────────────

async def seed():
    console.rule("[bold magenta]🌱 Seeding Fashion E-Commerce Database")
    client = AsyncIOMotorClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=30000,
        connectTimeoutMS=30000,
        socketTimeoutMS=30000,
    )
    db     = client[DB_NAME]

    # Drop existing data
    for col in ["users", "products", "orders", "payments"]:
        await db[col].drop()
    console.print("[yellow]Dropped existing collections[/yellow]")

    # Products
    console.print("\n[cyan]Inserting products…[/cyan]")
    products = make_products()
    res = await db.products.insert_many(products)
    product_ids = res.inserted_ids
    # Re-fetch with _ids for order items
    product_pool = []
    async for p in db.products.find({}, {"_id": 1, "name": 1, "price": 1, "category": 1}):
        product_pool.append(p)
    console.print(f"  ✅ {len(product_ids)} products inserted")

    # Users
    console.print("[cyan]Inserting users…[/cyan]")
    users = make_users()
    res   = await db.users.insert_many(users)
    user_ids = res.inserted_ids
    console.print(f"  ✅ {len(user_ids)} users inserted")

    # Orders + Payments
    console.print("[cyan]Generating orders & payments…[/cyan]")
    orders, payments = make_orders(user_ids, product_pool)
    order_res = await db.orders.insert_many(orders)
    order_ids = order_res.inserted_ids
    # Link payment → order
    for i, pay in enumerate(payments):
        pay["orderId"] = order_ids[i]
    await db.payments.insert_many(payments)
    console.print(f"  ✅ {len(orders)} orders inserted")
    console.print(f"  ✅ {len(payments)} payments inserted")

    # Create indexes for agent performance
    console.print("\n[cyan]Creating indexes…[/cyan]")
    await db.orders.create_index([("createdAt", -1)])
    await db.orders.create_index([("status", 1)])
    await db.orders.create_index([("userId", 1)])
    await db.orders.create_index([("paymentStatus", 1)])
    await db.products.create_index([("category", 1)])
    await db.products.create_index([("soldCount", -1)])
    await db.products.create_index([("isActive", 1)])
    await db.users.create_index([("tier", 1)])
    await db.users.create_index([("createdAt", -1)])
    await db.payments.create_index([("createdAt", -1)])
    await db.payments.create_index([("method", 1)])
    console.print("  ✅ Indexes created")

    client.close()
    console.rule("[bold green]✅ Seeding complete!")
    console.print(f"\n[bold]Database:[/bold] {DB_NAME}")
    console.print(f"[bold]URI:[/bold]      {MONGODB_URI}")
    console.print("\nYou can now start the server: [bold cyan]python main.py[/bold cyan]\n")


if __name__ == "__main__":
    asyncio.run(seed())
