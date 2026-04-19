"""
Python-only Streamlit interface for the e-commerce analytics agent.

This app reuses the existing agent pipeline directly:
Intent -> Plan -> Execute -> Insight
"""
from __future__ import annotations

import asyncio
import html
import os
import random
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st
from pymongo.errors import ConfigurationError
try:
    from streamlit_echarts import st_echarts
    ECHARTS_AVAILABLE = True
except Exception:
    ECHARTS_AVAILABLE = False

from agent import AgentOrchestrator
from config import connect_db, get_db, get_settings


st.set_page_config(
    page_title="InsightAI Streamlit",
    page_icon="SA",
    layout="wide",
)

SAMPLE_QUESTIONS = [
    "How much revenue did we generate this week?",
    "What is the order status breakdown this month?",
    "Which are the top 5 best-selling products?",
    "How many new customers joined this month?",
    "Compare this week's revenue vs last week",
    "Which categories generated the most revenue this month?",
]


class AsyncLoopRunner:
    """Runs all coroutines on one persistent event loop in a background thread."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def _run_forever(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro: Any):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()


@st.cache_resource
def get_runtime_and_orchestrator() -> tuple[AsyncLoopRunner, AgentOrchestrator]:
    """Initialize shared async runtime, DB, and orchestrator once per server process."""
    runner = AsyncLoopRunner()
    runner.run(connect_db())
    return runner, AgentOrchestrator(get_db())


def init_state() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = ""
    if "login_error" not in st.session_state:
        st.session_state.login_error = ""
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"st_{uuid4().hex[:12]}"
    if "history" not in st.session_state:
        st.session_state.history = []
    if "ui_show_pipeline" not in st.session_state:
        st.session_state.ui_show_pipeline = True
    if "ui_show_raw" not in st.session_state:
        st.session_state.ui_show_raw = False
    if "backend_error" not in st.session_state:
        st.session_state.backend_error = ""
    if "profile_name" not in st.session_state:
        st.session_state.profile_name = "Vansh Arora"
    if "profile_role" not in st.session_state:
        st.session_state.profile_role = "Founder / Data Lead"
    if "profile_email" not in st.session_state:
        st.session_state.profile_email = "vansh@insightai.local"
    if "profile_region" not in st.session_state:
        st.session_state.profile_region = "India"
    if "profile_company" not in st.session_state:
        st.session_state.profile_company = "InsightAI Commerce"
    if "admin_view" not in st.session_state:
        st.session_state.admin_view = "Overview"
    if "assistant_input" not in st.session_state:
        st.session_state.assistant_input = ""


def inject_styles() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

            html, body {
                background:
                    radial-gradient(circle at 5% -5%, rgba(14, 116, 144, 0.14), transparent 32%),
                    radial-gradient(circle at 95% 0%, rgba(194, 65, 12, 0.10), transparent 32%),
                    linear-gradient(180deg, #f8fafc 0%, #eef2f6 100%) !important;
            }

            .stApp,
            [data-testid="stAppViewContainer"],
            [data-testid="stAppViewContainer"] > .main,
            [data-testid="stAppViewContainer"] > .main > div,
            [data-testid="stAppViewContainer"] > .main .block-container {
                background:
                    radial-gradient(circle at 5% -5%, rgba(14, 116, 144, 0.14), transparent 32%),
                    radial-gradient(circle at 95% 0%, rgba(194, 65, 12, 0.10), transparent 32%),
                    linear-gradient(180deg, #f8fafc 0%, #eef2f6 100%) !important;
            }

            [data-testid="stAppViewContainer"] * {
                font-family: 'Sora', sans-serif;
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #0f172a 0%, #0b1324 100%);
                border-right: 1px solid rgba(148, 163, 184, 0.2);
            }

            [data-testid="stSidebar"] * {
                color: #e2e8f0;
            }

            .hero {
                border: 1px solid #d9e2ec;
                background: linear-gradient(126deg, #ffffff 0%, #f7fafc 55%, #ecfeff 100%);
                border-radius: 20px;
                padding: 24px 28px;
                box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08);
                margin-bottom: 16px;
                animation: rise 0.45s ease-out;
            }

            .login-wrap {
                max-width: 480px;
                margin: 4rem auto 0;
                border: 1px solid #dbe4ea;
                background: linear-gradient(160deg, #ffffff 0%, #f8fafc 100%);
                border-radius: 18px;
                padding: 22px;
                box-shadow: 0 14px 30px rgba(15, 23, 42, 0.08);
            }

            .login-title {
                margin: 0;
                color: #0f172a;
                font-size: 1.35rem;
                font-weight: 700;
            }

            .login-sub {
                margin-top: 6px;
                margin-bottom: 14px;
                color: #475569;
                font-size: 0.9rem;
            }

            .topbar {
                border: 1px solid #d9e2ec;
                background: #ffffff;
                border-radius: 16px;
                padding: 14px 16px;
                margin-bottom: 12px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
            }

            .topbar-right {
                display: flex;
                align-items: center;
                gap: 10px;
            }

            .profile-circle {
                width: 36px;
                height: 36px;
                border-radius: 999px;
                background: linear-gradient(135deg, #0284c7, #0ea5e9);
                color: #e0f2fe;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-weight: 700;
                font-size: 0.85rem;
            }

            .admin-badge {
                border: 1px solid #bfdbfe;
                background: #eff6ff;
                color: #1d4ed8;
                border-radius: 999px;
                padding: 5px 9px;
                font-size: 0.73rem;
                font-family: 'IBM Plex Mono', monospace;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .topbar-title {
                color: #0f172a;
                font-size: 0.95rem;
            }

            .topbar-sub {
                color: #64748b;
                font-size: 0.82rem;
                margin-top: 2px;
            }

            .profile-chip {
                border: 1px solid #bfdbfe;
                background: #eff6ff;
                color: #1e3a8a;
                border-radius: 999px;
                padding: 6px 10px;
                font-size: 0.76rem;
                font-family: 'IBM Plex Mono', monospace;
                white-space: nowrap;
            }

            .hero h2 {
                margin: 0;
                color: #0f172a;
                font-size: 1.7rem;
                letter-spacing: -0.01em;
            }

            .hero p {
                margin: 10px 0 12px;
                color: #334155;
                line-height: 1.6;
            }

            .hero-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(120px, 1fr));
                gap: 10px;
            }

            .hero-stat {
                border: 1px solid #dbeafe;
                background: #ffffff;
                border-radius: 12px;
                padding: 10px 12px;
            }

            .hero-stat-label {
                color: #64748b;
                font-size: 0.74rem;
                margin-bottom: 4px;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .hero-stat-value {
                color: #0f172a;
                font-weight: 700;
                font-size: 1.15rem;
            }

            .pill {
                display: inline-block;
                margin-top: 4px;
                background: #ecfeff;
                color: #155e75;
                border: 1px solid #bae6fd;
                border-radius: 999px;
                padding: 5px 11px;
                font-size: 0.8rem;
                font-family: 'IBM Plex Mono', monospace;
            }

            .section-title {
                color: #0f172a;
                font-weight: 700;
                margin: 6px 0 10px;
                font-size: 1.05rem;
            }

            .insight-card {
                border: 1px solid #dbe4ea;
                background: #ffffff;
                border-radius: 16px;
                padding: 16px 18px;
                margin: 4px 0 12px;
                box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
            }

            .insight-title {
                margin: 0;
                color: #0f172a;
                font-size: 1.16rem;
                letter-spacing: -0.01em;
            }

            .insight-summary {
                margin: 8px 0 0;
                color: #334155;
                line-height: 1.62;
            }

            .intent-chip {
                display: inline-block;
                font-size: 0.72rem;
                font-weight: 600;
                margin-bottom: 8px;
                padding: 4px 10px;
                border-radius: 999px;
                background: #ecfeff;
                color: #0f766e;
                border: 1px solid #99f6e4;
                text-transform: uppercase;
                letter-spacing: 0.03em;
            }

            .trend-note {
                margin-top: 10px;
                background: #fff7ed;
                border: 1px solid #fdba74;
                border-radius: 10px;
                padding: 9px 11px;
                color: #7c2d12;
                font-size: 0.93rem;
            }

            .reco-title {
                margin-top: 12px;
                color: #0f172a;
                font-weight: 600;
            }

            .status-ok {
                border: 1px solid #86efac;
                background: #f0fdf4;
                color: #166534;
                border-radius: 10px;
                padding: 8px 10px;
                margin-bottom: 10px;
                font-size: 0.88rem;
            }

            .status-bad {
                border: 1px solid #fecaca;
                background: #fff1f2;
                color: #9f1239;
                border-radius: 10px;
                padding: 8px 10px;
                margin-bottom: 10px;
                font-size: 0.88rem;
            }

            .profile-card {
                border: 1px solid rgba(148, 163, 184, 0.35);
                background: linear-gradient(160deg, #111b34 0%, #0f172a 100%);
                border-radius: 14px;
                padding: 12px;
                margin-bottom: 10px;
            }

            .avatar {
                width: 38px;
                height: 38px;
                border-radius: 999px;
                background: linear-gradient(145deg, #22d3ee, #38bdf8);
                color: #082f49;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-weight: 700;
                margin-right: 8px;
            }

            .profile-head {
                display: flex;
                align-items: center;
            }

            .profile-name {
                color: #f8fafc;
                font-weight: 700;
                font-size: 0.95rem;
                line-height: 1.15;
            }

            .profile-role {
                color: #93c5fd;
                font-size: 0.77rem;
                margin-top: 2px;
            }

            .profile-meta {
                margin-top: 10px;
                color: #cbd5e1;
                font-size: 0.75rem;
                line-height: 1.45;
            }

            .mono {
                font-family: 'IBM Plex Mono', monospace;
                color: #475569;
                font-size: 0.8rem;
            }

            .sample-caption {
                color: #475569;
                margin-bottom: 10px;
            }

            /* Strong overrides for login readability and premium look */
            [data-testid="stAppViewContainer"] {
                background:
                    radial-gradient(circle at 10% 0%, rgba(30, 64, 175, 0.25), transparent 35%),
                    radial-gradient(circle at 90% 0%, rgba(8, 145, 178, 0.18), transparent 30%),
                    linear-gradient(180deg, #020617 0%, #0b1220 100%) !important;
            }

            [data-testid="stAppViewContainer"] > .main .block-container {
                background: transparent !important;
            }

            .login-wrap {
                border: 1px solid rgba(148, 163, 184, 0.35) !important;
                background: linear-gradient(165deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.92) 100%) !important;
                border-radius: 18px;
                box-shadow: 0 16px 40px rgba(2, 6, 23, 0.5) !important;
                backdrop-filter: blur(8px);
            }

            .login-title {
                color: #f8fafc !important;
            }

            .login-sub {
                color: #cbd5e1 !important;
            }

            [data-testid="stTextInput"] label,
            [data-testid="stTextInput"] p,
            [data-testid="stTextInput"] span,
            [data-testid="stCaptionContainer"] p {
                color: #e2e8f0 !important;
            }

            div[data-baseweb="input"] > div {
                background: #0f172a !important;
                border: 1px solid #334155 !important;
                border-radius: 10px !important;
            }

            div[data-baseweb="input"] input {
                color: #f8fafc !important;
            }

            [data-testid="stForm"] button,
            [data-testid="stButton"] button {
                background: linear-gradient(90deg, #0ea5e9 0%, #2563eb 100%) !important;
                color: #eff6ff !important;
                border: none !important;
                border-radius: 10px !important;
                font-weight: 700 !important;
            }

            [data-testid="stForm"] button:hover,
            [data-testid="stButton"] button:hover {
                filter: brightness(1.05);
                transform: translateY(-1px);
            }

            .panel {
                border: 1px solid #dbe4ea;
                background: #ffffff;
                border-radius: 14px;
                padding: 14px;
                margin-bottom: 12px;
                box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
            }

            .echart-shell {
                border: 1px solid #dbe4ea;
                background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
                border-radius: 14px;
                padding: 10px 12px;
                margin-bottom: 12px;
                box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
            }

            .assistant-panel {
                border: 1px solid #cbd5e1;
                background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
                border-radius: 14px;
                padding: 12px;
                box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
                position: sticky;
                top: 80px;
            }

            .panel-title {
                font-size: 0.98rem;
                color: #0f172a;
                font-weight: 700;
                margin-bottom: 8px;
            }

            @media (max-width: 900px) {
                .hero-grid {
                    grid-template-columns: 1fr;
                }
            }

            @keyframes rise {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def format_metric_value(value: Any) -> str:
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            return f"{value:,.2f}"
        return f"{value:,}"
    return str(value)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def render_auto_chart(item: dict[str, Any], insight: dict[str, Any]) -> None:
    """Render a best-effort chart from raw preview rows or key metrics."""
    rows = item.get("raw_results_preview") or []

    if rows and isinstance(rows, list) and isinstance(rows[0], dict):
        sample = rows[0]
        numeric_keys = [k for k, v in sample.items() if _is_number(v)]
        category_keys = [k for k, v in sample.items() if isinstance(v, str)]

        if numeric_keys:
            y_key = "value" if "value" in numeric_keys else numeric_keys[0]
            x_key = category_keys[0] if category_keys else None

            chart_data: list[dict[str, Any]] = []
            for row in rows[:20]:
                if not isinstance(row, dict) or y_key not in row:
                    continue
                if x_key:
                    chart_data.append({"x": str(row.get(x_key, "n/a")), "y": row.get(y_key, 0)})
                else:
                    chart_data.append({"x": f"row_{len(chart_data)+1}", "y": row.get(y_key, 0)})

            if chart_data:
                st.markdown("**Chart**")
                chart_hint = insight.get("chart_hint")
                if chart_hint == "line":
                    st.line_chart(chart_data, x="x", y="y")
                else:
                    st.bar_chart(chart_data, x="x", y="y")
                return

    metrics = insight.get("key_metrics") or []
    if metrics:
        chart_data = []
        for m in metrics[:8]:
            value = m.get("value")
            if _is_number(value):
                chart_data.append({"x": str(m.get("label", "Metric")), "y": value})
        if chart_data:
            st.markdown("**Chart**")
            st.bar_chart(chart_data, x="x", y="y")


def render_echart(title: str, option: dict[str, Any], height: int = 320) -> None:
    st.markdown(f"<div class='echart-shell'><div class='panel-title'>{title}</div>", unsafe_allow_html=True)
    if ECHARTS_AVAILABLE:
        st_echarts(options=option, height=f"{height}px")
    else:
        st.info("Install streamlit-echarts for advanced chart rendering. Falling back to basic charts.")
    st.markdown("</div>", unsafe_allow_html=True)


async def _fetch_snapshot_async() -> dict[str, Any]:
    """Fetch dashboard snapshot from MongoDB for overview/explorer sections."""
    db = get_db()
    now = datetime.now(timezone.utc)
    since_30 = now - timedelta(days=30)

    users = await db.users.count_documents({})
    products = await db.products.count_documents({})
    orders = await db.orders.count_documents({})
    payments = await db.payments.count_documents({})

    total_rev_doc = await db.orders.aggregate([
        {"$group": {"_id": None, "revenue": {"$sum": "$totalAmount"}}}
    ]).to_list(length=1)
    total_revenue = total_rev_doc[0]["revenue"] if total_rev_doc else 0

    rev_30_doc = await db.orders.aggregate([
        {"$match": {"createdAt": {"$gte": since_30}}},
        {"$group": {"_id": None, "revenue": {"$sum": "$totalAmount"}}}
    ]).to_list(length=1)
    revenue_30 = rev_30_doc[0]["revenue"] if rev_30_doc else 0

    status_data = await db.orders.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]).to_list(length=20)

    revenue_30d = await db.orders.aggregate([
        {"$match": {"createdAt": {"$gte": since_30}}},
        {
            "$group": {
                "_id": {
                    "$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"}
                },
                "revenue": {"$sum": "$totalAmount"},
                "orders": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]).to_list(length=40)

    top_categories = await db.orders.aggregate([
        {"$unwind": "$items"},
        {
            "$group": {
                "_id": "$items.category",
                "units": {"$sum": "$items.quantity"},
                "revenue": {"$sum": {"$multiply": ["$items.quantity", "$items.price"]}},
            }
        },
        {"$sort": {"revenue": -1}},
    ]).to_list(length=20)

    recent_orders = await db.orders.find(
        {},
        {
            "totalAmount": 1,
            "status": 1,
            "paymentStatus": 1,
            "shippingCity": 1,
            "createdAt": 1,
        },
    ).sort("createdAt", -1).limit(40).to_list(length=40)

    payment_status = await db.payments.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}, "amount": {"$sum": "$amount"}}},
        {"$sort": {"count": -1}},
    ]).to_list(length=20)

    return {
        "counts": {
            "users": users,
            "products": products,
            "orders": orders,
            "payments": payments,
        },
        "finance": {
            "total_revenue": total_revenue,
            "revenue_30": revenue_30,
            "estimated_margin": 0.22,
        },
        "status_data": status_data,
        "payment_status": payment_status,
        "revenue_30d": revenue_30d,
        "top_categories": top_categories,
        "recent_orders": recent_orders,
    }


def get_dashboard_snapshot(backend: tuple[AsyncLoopRunner, AgentOrchestrator] | None) -> dict[str, Any]:
    if backend is None:
        return {}
    runner, _ = backend
    try:
        return runner.run(_fetch_snapshot_async())
    except Exception as exc:
        st.session_state.backend_error = f"Snapshot load failed: {exc}"
        return {}


def render_overview_tab(snapshot: dict[str, Any], backend_ok: bool) -> None:
    counts = snapshot.get("counts", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Users", f"{counts.get('users', 0):,}")
    c2.metric("Products", f"{counts.get('products', 0):,}")
    c3.metric("Orders", f"{counts.get('orders', 0):,}")
    c4.metric("Payments", f"{counts.get('payments', 0):,}")

    left, right = st.columns([1.3, 1])
    with left:
        rev = snapshot.get("revenue_30d", [])
        if rev:
            df = pd.DataFrame(
                [{"date": row.get("_id"), "revenue": row.get("revenue", 0), "orders": row.get("orders", 0)} for row in rev]
            )
            if ECHARTS_AVAILABLE:
                render_echart(
                    "Revenue Trend (Last 30 Days)",
                    {
                        "tooltip": {"trigger": "axis"},
                        "grid": {"left": "4%", "right": "3%", "top": "10%", "bottom": "8%", "containLabel": True},
                        "xAxis": {"type": "category", "data": df["date"].tolist(), "axisLabel": {"color": "#64748b"}},
                        "yAxis": {"type": "value", "axisLabel": {"color": "#64748b"}},
                        "series": [{"data": df["revenue"].tolist(), "type": "line", "smooth": True, "areaStyle": {}, "lineStyle": {"width": 3, "color": "#0284c7"}, "itemStyle": {"color": "#0284c7"}}],
                    },
                    height=340,
                )
            else:
                st.markdown("<div class='panel'><div class='panel-title'>Revenue Trend (Last 30 Days)</div>", unsafe_allow_html=True)
                st.line_chart(df, x="date", y="revenue")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("No trend data available yet.")

    with right:
        status = snapshot.get("status_data", [])
        if status:
            df = pd.DataFrame([{"status": r.get("_id", "unknown"), "count": r.get("count", 0)} for r in status])
            if ECHARTS_AVAILABLE:
                render_echart(
                    "Order Status Mix",
                    {
                        "tooltip": {"trigger": "item"},
                        "legend": {"bottom": 0},
                        "series": [{"name": "Orders", "type": "pie", "radius": ["42%", "70%"], "data": [{"value": int(row["count"]), "name": str(row["status"])} for _, row in df.iterrows()]}],
                    },
                    height=340,
                )
            else:
                st.markdown("<div class='panel'><div class='panel-title'>Order Status Mix</div>", unsafe_allow_html=True)
                st.bar_chart(df, x="status", y="count")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("No status data yet.")

    cats = snapshot.get("top_categories", [])
    if cats:
        df = pd.DataFrame(
            [{"category": r.get("_id", "unknown"), "revenue": round(r.get("revenue", 0), 2), "units": r.get("units", 0)} for r in cats]
        )
        if ECHARTS_AVAILABLE:
            render_echart(
                "Top Categories by Revenue",
                {
                    "tooltip": {"trigger": "axis"},
                    "grid": {"left": "4%", "right": "3%", "top": "12%", "bottom": "10%", "containLabel": True},
                    "xAxis": {"type": "category", "data": df["category"].tolist(), "axisLabel": {"rotate": 15, "color": "#64748b"}},
                    "yAxis": {"type": "value", "axisLabel": {"color": "#64748b"}},
                    "series": [{"data": df["revenue"].tolist(), "type": "bar", "itemStyle": {"borderRadius": [6, 6, 0, 0], "color": "#0ea5e9"}}],
                },
                height=320,
            )
        else:
            st.markdown("<div class='panel'><div class='panel-title'>Top Categories by Revenue</div>", unsafe_allow_html=True)
            st.bar_chart(df, x="category", y="revenue")
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No category data yet.")

    if not backend_ok:
        st.warning("Backend is offline, so overview data may be stale or empty.")


def render_revenue_tab(snapshot: dict[str, Any]) -> None:
    finance = snapshot.get("finance", {})
    total_revenue = float(finance.get("total_revenue", 0))
    revenue_30 = float(finance.get("revenue_30", 0))

    c1, c2 = st.columns(2)
    c1.metric("Total Revenue", f"INR {total_revenue:,.0f}")
    c2.metric("Last 30 Days", f"INR {revenue_30:,.0f}")

    rev = snapshot.get("revenue_30d", [])
    if rev:
        df = pd.DataFrame([{"date": row.get("_id"), "revenue": row.get("revenue", 0)} for row in rev])
        if ECHARTS_AVAILABLE:
            render_echart(
                "Daily Revenue Trend",
                {
                    "tooltip": {"trigger": "axis"},
                    "xAxis": {"type": "category", "data": df["date"].tolist()},
                    "yAxis": {"type": "value"},
                    "series": [{"data": df["revenue"].tolist(), "type": "line", "smooth": True, "symbol": "none", "lineStyle": {"width": 3, "color": "#22c55e"}, "areaStyle": {"opacity": 0.15, "color": "#22c55e"}}],
                },
                height=340,
            )
        else:
            st.markdown("<div class='panel'><div class='panel-title'>Daily Revenue Trend</div>", unsafe_allow_html=True)
            st.area_chart(df, x="date", y="revenue")
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No revenue trend data available.")


def render_profit_loss_tab(snapshot: dict[str, Any]) -> None:
    finance = snapshot.get("finance", {})
    total_revenue = float(finance.get("total_revenue", 0))
    margin = float(finance.get("estimated_margin", 0.22))
    est_profit = total_revenue * margin
    est_cost = total_revenue - est_profit

    c1, c2, c3 = st.columns(3)
    c1.metric("Revenue", f"INR {total_revenue:,.0f}")
    c2.metric("Est. Cost", f"INR {est_cost:,.0f}")
    c3.metric("Est. Profit", f"INR {est_profit:,.0f}")

    st.caption("Profit/Loss here is an estimate using a configurable margin assumption for MVP presentation.")
    if ECHARTS_AVAILABLE:
        render_echart(
            "P&L Breakdown (Estimated)",
            {
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "category", "data": ["Revenue", "Cost", "Profit"]},
                "yAxis": {"type": "value"},
                "series": [{"type": "bar", "data": [total_revenue, est_cost, est_profit], "itemStyle": {"color": "#3b82f6", "borderRadius": [8, 8, 0, 0]}}],
            },
            height=320,
        )
    else:
        st.markdown("<div class='panel'><div class='panel-title'>P&L Breakdown (Estimated)</div>", unsafe_allow_html=True)
        st.bar_chart(pd.DataFrame([
            {"component": "Revenue", "value": total_revenue},
            {"component": "Cost", "value": est_cost},
            {"component": "Profit", "value": est_profit},
        ]), x="component", y="value")
        st.markdown("</div>", unsafe_allow_html=True)


def render_orders_tab(snapshot: dict[str, Any]) -> None:
    status = snapshot.get("status_data", [])
    if status:
        df = pd.DataFrame([{"status": r.get("_id", "unknown"), "count": r.get("count", 0)} for r in status])
        if ECHARTS_AVAILABLE:
            render_echart(
                "Order Status",
                {
                    "tooltip": {"trigger": "axis"},
                    "xAxis": {"type": "category", "data": df["status"].tolist()},
                    "yAxis": {"type": "value"},
                    "series": [{"type": "bar", "data": df["count"].tolist(), "itemStyle": {"color": "#0891b2", "borderRadius": [8, 8, 0, 0]}}],
                },
                height=320,
            )
        else:
            st.markdown("<div class='panel'><div class='panel-title'>Order Status</div>", unsafe_allow_html=True)
            st.bar_chart(df, x="status", y="count")
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No order status data available.")


def render_customers_tab(snapshot: dict[str, Any]) -> None:
    count = snapshot.get("counts", {}).get("users", 0)
    st.metric("Total Customers", f"{count:,}")
    st.markdown("<div class='panel'><div class='panel-title'>Recent Orders (Customer Activity Proxy)</div>", unsafe_allow_html=True)
    rows = snapshot.get("recent_orders", [])
    if rows:
        df = pd.DataFrame([{"createdAt": str(r.get("createdAt", "")), "city": r.get("shippingCity", ""), "status": r.get("status", ""), "totalAmount": r.get("totalAmount", 0)} for r in rows])
        st.dataframe(df, use_container_width=True, height=320)
    else:
        st.info("No customer activity data available.")
    st.markdown("</div>", unsafe_allow_html=True)


def render_right_assistant_panel() -> None:
    st.markdown("<div class='assistant-panel'>", unsafe_allow_html=True)
    st.markdown("#### AI Assistant")
    st.caption("Ask analytics questions and get narrative insights.")

    if st.session_state.history:
        for item in st.session_state.history[-4:]:
            headline = "Conversation" if item.get("is_conversational") else str(item.get("insight", {}).get("headline", "Insight"))
            st.markdown(f"- {headline}")
    else:
        st.caption("No insights yet. Run your first query.")

    with st.form("assistant_side_form", clear_on_submit=True):
        prompt = st.text_area("Analytics Chat", key="assistant_input", height=90, placeholder="Example: What is the revenue trend this month?")
        submitted = st.form_submit_button("Ask Assistant", use_container_width=True)
        if submitted and prompt.strip():
            with st.spinner("Analyzing..."):
                ok = try_ask(prompt.strip())
            if ok:
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


def render_explorer_tab(snapshot: dict[str, Any]) -> None:
    st.markdown("<div class='panel'><div class='panel-title'>Recent Orders Explorer</div>", unsafe_allow_html=True)
    rows = snapshot.get("recent_orders", [])
    if rows:
        cleaned = []
        for r in rows:
            cleaned.append(
                {
                    "createdAt": str(r.get("createdAt", "")),
                    "status": r.get("status", ""),
                    "paymentStatus": r.get("paymentStatus", ""),
                    "shippingCity": r.get("shippingCity", ""),
                    "totalAmount": r.get("totalAmount", 0),
                }
            )
        df = pd.DataFrame(cleaned)
        st.dataframe(df, use_container_width=True, height=360)
    else:
        st.info("No recent orders to display.")
    st.markdown("</div>", unsafe_allow_html=True)


def render_overview() -> None:
    total = len(st.session_state.history)
    analytics = sum(1 for x in st.session_state.history if not x.get("is_conversational"))
    avg_ms = 0.0
    if total:
        avg_ms = sum(float(x.get("execution_time_ms", 0)) for x in st.session_state.history) / total

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Queries", total)
    c2.metric("Analytics Runs", analytics)
    c3.metric("Avg Latency", f"{avg_ms:.0f} ms")


def render_hero(backend_ok: bool) -> None:
    total = len(st.session_state.history)
    analytics = sum(1 for x in st.session_state.history if not x.get("is_conversational"))
    last_intent = "none"
    if st.session_state.history:
        last_intent = str(st.session_state.history[-1].get("intent", "unknown"))

    status = "Connected" if backend_ok else "Offline"
    company = html.escape(st.session_state.profile_company)
    user = html.escape(st.session_state.profile_name)
    st.markdown(
        f"""
        <div class="hero">
            <h2>InsightAI Executive Dashboard</h2>
            <p>Welcome, {user}. Here is your command center for revenue, orders, products, customer cohorts, and payment performance at {company}.</p>
            <span class="pill">Engine status: {status}</span>
            <div class="hero-grid">
                <div class="hero-stat">
                    <div class="hero-stat-label">Total Activity</div>
                    <div class="hero-stat-value">{total}</div>
                </div>
                <div class="hero-stat">
                    <div class="hero-stat-label">Analytics Sessions</div>
                    <div class="hero-stat-value">{analytics}</div>
                </div>
                <div class="hero-stat">
                    <div class="hero-stat-label">Last Intent</div>
                    <div class="hero-stat-value">{html.escape(last_intent.replace('_', ' ').title())}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_topbar() -> None:
    name = html.escape(st.session_state.profile_name)
    role = html.escape(st.session_state.profile_role)
    region = html.escape(st.session_state.profile_region)
    initials = "".join([part[0] for part in st.session_state.profile_name.split() if part][:2]).upper() or "U"
    st.markdown(
        f"""
        <div class="topbar">
            <div>
                <div class="topbar-title">Portfolio-grade AI Analytics Workspace</div>
                <div class="topbar-sub">Personalized for {name} · {role}</div>
            </div>
            <div class="topbar-right">
                <div class="admin-badge">Admin</div>
                <div class="profile-chip">Region: {region}</div>
                <div class="profile-circle">{initials}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def check_credentials(username: str, password: str) -> bool:
    settings = get_settings()
    expected_user = os.getenv("STREAMLIT_USERNAME", "admin")
    expected_pass = os.getenv("STREAMLIT_PASSWORD", settings.admin_api_key)
    return secrets.compare_digest(username.strip(), expected_user) and secrets.compare_digest(password, expected_pass)


def render_login() -> None:
    st.markdown(
        """
        <div class="login-wrap">
            <h2 class="login-title">InsightAI Secure Access</h2>
            <div class="login-sub">Sign in to access the executive analytics dashboard.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Username", placeholder="admin")
        password = st.text_input("Password", type="password")

        if st.session_state.login_error:
            st.error(st.session_state.login_error)

        if st.button("Sign In", use_container_width=True):
            if check_credentials(username, password):
                st.session_state.authenticated = True
                st.session_state.auth_user = username.strip()
                st.session_state.login_error = ""
                st.rerun()
            else:
                st.session_state.login_error = "Invalid username or password."
                st.rerun()

        st.caption("Default username is 'admin'. Password defaults to ADMIN_API_KEY unless STREAMLIT_PASSWORD is set.")


def render_sidebar_profile() -> None:
    initials = "".join([part[0] for part in st.session_state.profile_name.split() if part][:2]).upper() or "U"
    name = html.escape(st.session_state.profile_name)
    role = html.escape(st.session_state.profile_role)
    email = html.escape(st.session_state.profile_email)
    company = html.escape(st.session_state.profile_company)

    st.markdown(
        f"""
        <div class="profile-card">
            <div class="profile-head">
                <div class="avatar">{initials}</div>
                <div>
                    <div class="profile-name">{name}</div>
                    <div class="profile-role">{role}</div>
                </div>
            </div>
            <div class="profile-meta">{email}<br/>{company}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Edit Profile"):
        st.session_state.profile_name = st.text_input("Name", value=st.session_state.profile_name)
        st.session_state.profile_role = st.text_input("Role", value=st.session_state.profile_role)
        st.session_state.profile_email = st.text_input("Email", value=st.session_state.profile_email)
        st.session_state.profile_company = st.text_input("Company", value=st.session_state.profile_company)
        st.session_state.profile_region = st.selectbox(
            "Region",
            ["India", "UAE", "Europe", "US", "APAC", "Other"],
            index=["India", "UAE", "Europe", "US", "APAC", "Other"].index(st.session_state.profile_region)
            if st.session_state.profile_region in ["India", "UAE", "Europe", "US", "APAC", "Other"] else 0,
        )


def render_empty_state(runner: AsyncLoopRunner, orchestrator: AgentOrchestrator) -> None:
    st.markdown(
        """
        <div class="hero">
            <h2>InsightAI Sales Intelligence</h2>
            <p>
                Ask natural-language business questions and get structured insights from your live MongoDB data.
            </p>
            <span class="pill">Read-only analytics engine</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### Start with a sample")
    left, right = st.columns(2)
    for idx, question in enumerate(SAMPLE_QUESTIONS):
        target_col = left if idx % 2 == 0 else right
        with target_col:
            if st.button(question, key=f"main_sample_{idx}", use_container_width=True):
                ask_question(runner, orchestrator, question)
                st.rerun()


def render_history() -> None:
    for item in st.session_state.history:
        with st.chat_message("user"):
            st.write(item["question"])

        with st.chat_message("assistant"):
            if item.get("is_conversational"):
                st.write(item.get("plain_response", ""))
                continue

            insight = item["insight"]
            intent = str(item.get("intent", "unknown")).replace("_", " ")
            period = str(item.get("time_period", "all_time")).replace("_", " ")
            headline = html.escape(str(insight.get("headline", "Insight")))
            summary = html.escape(str(insight.get("summary", "")))

            st.markdown(
                f"""
                <div class="insight-card">
                    <div class="intent-chip">{html.escape(intent)} | {html.escape(period)}</div>
                    <h3 class="insight-title">{headline}</h3>
                    <p class="insight-summary">{summary}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            metrics = insight.get("key_metrics") or []
            if metrics:
                st.markdown("**Key Metrics**")
                cols = st.columns(min(4, len(metrics)))
                for idx, m in enumerate(metrics[:4]):
                    value = format_metric_value(m.get("value", "-"))
                    unit = m.get("unit", "")
                    label = m.get("label", "Metric")
                    delta = m.get("change_pct")
                    delta_str = None if delta is None else f"{float(delta):.1f}%"
                    cols[idx].metric(label=label, value=f"{value} {unit}".strip(), delta=delta_str)

                    render_auto_chart(item, insight)

            trend = insight.get("trend")
            if trend and trend.get("narrative"):
                narrative = trend.get("narrative", "")
                period_label = trend.get("period_label", "")
                change = trend.get("change_pct")
                change_note = ""
                if change is not None:
                    change_note = f" | Change: {float(change):.1f}%"
                st.markdown(
                    f"<div class='trend-note'><strong>Trend</strong>: {html.escape(str(period_label))} | {html.escape(str(narrative))}{html.escape(change_note)}</div>",
                    unsafe_allow_html=True,
                )

            recommendations = insight.get("recommendations") or []
            if recommendations:
                st.markdown("<div class='reco-title'>Recommendations</div>", unsafe_allow_html=True)
                for rec in recommendations:
                    st.write(f"- {rec}")

            if st.session_state.ui_show_pipeline:
                with st.expander("Pipeline Details"):
                    for step in item.get("pipeline_steps", []):
                        st.markdown(f"<div class='mono'>{step}</div>", unsafe_allow_html=True)

            if st.session_state.ui_show_raw and item.get("raw_results_preview"):
                with st.expander("Raw Results Preview"):
                    st.json(item["raw_results_preview"])


def ask_question(runner: AsyncLoopRunner, orchestrator: AgentOrchestrator, question: str) -> None:
    response = runner.run(orchestrator.ask(question, session_id=st.session_state.session_id))
    payload = response.model_dump(mode="json")
    st.session_state.history.append(payload)


def get_backend() -> tuple[AsyncLoopRunner, AgentOrchestrator] | None:
    """Try to return backend runtime; store a user-friendly error and keep UI alive."""
    try:
        st.session_state.backend_error = ""
        return get_runtime_and_orchestrator()
    except ConfigurationError as exc:
        msg = str(exc)
        if "DNS query name does not exist" in msg:
            st.session_state.backend_error = (
                "MongoDB SRV DNS not found. Re-copy MONGODB_URI from Atlas and restart app."
            )
        else:
            st.session_state.backend_error = f"MongoDB connection failed: {msg}"
        return None
    except Exception as exc:
        st.session_state.backend_error = f"Backend initialization failed: {exc}"
        return None


def try_ask(question: str) -> bool:
    backend = get_backend()
    if backend is None:
        return False
    runner, orchestrator = backend
    ask_question(runner, orchestrator, question)
    return True


def main() -> None:
    inject_styles()
    init_state()

    if not st.session_state.authenticated:
        render_login()
        return

    backend = get_backend()
    backend_ok = backend is not None
    snapshot = get_dashboard_snapshot(backend)

    render_topbar()
    render_hero(backend_ok)
    render_overview()

    with st.sidebar:
        st.markdown("### Admin Navigation")
        st.caption("Core controls for finance operations.")

        st.session_state.admin_view = st.radio(
            "Go to",
            ["Overview", "Revenue", "Profit & Loss", "Orders", "Customers"],
            index=["Overview", "Revenue", "Profit & Loss", "Orders", "Customers"].index(st.session_state.admin_view)
            if st.session_state.admin_view in ["Overview", "Revenue", "Profit & Loss", "Orders", "Customers"] else 0,
        )

        if backend_ok:
            st.markdown("<div class='status-ok'>Backend connected and ready.</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='status-bad'>Backend not available.</div>", unsafe_allow_html=True)
            if st.session_state.backend_error:
                st.caption(st.session_state.backend_error)
            if st.button("Retry Connection", use_container_width=True):
                st.cache_resource.clear()
                st.rerun()

        st.markdown("---")
        st.subheader("Session")
        st.caption(f"Signed in as: {st.session_state.auth_user}")
        if st.button("Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.auth_user = ""
            st.rerun()

        st.code(st.session_state.session_id)

        if st.button("Clear Chat History", use_container_width=True):
            st.session_state.history = []
            st.rerun()

        if st.button("Run Random Sample", use_container_width=True):
            with st.spinner("Running sample query..."):
                ok = try_ask(random.choice(SAMPLE_QUESTIONS))
            if ok:
                st.rerun()

        st.markdown("---")
        st.subheader("AI Quick Prompts")
        for idx, q in enumerate(SAMPLE_QUESTIONS):
            if st.button(q, key=f"side_sample_{idx}", use_container_width=True):
                with st.spinner("Running query..."):
                    ok = try_ask(q)
                if ok:
                    st.rerun()

    main_col, assistant_col = st.columns([3, 1.2], gap="large")

    with main_col:
        if st.session_state.admin_view == "Overview":
            render_overview_tab(snapshot, backend_ok)
        elif st.session_state.admin_view == "Revenue":
            render_revenue_tab(snapshot)
        elif st.session_state.admin_view == "Profit & Loss":
            render_profit_loss_tab(snapshot)
        elif st.session_state.admin_view == "Orders":
            render_orders_tab(snapshot)
        elif st.session_state.admin_view == "Customers":
            render_customers_tab(snapshot)

        st.markdown("<div class='section-title'>Recent AI Insights</div>", unsafe_allow_html=True)
        if st.session_state.history:
            render_history()
        else:
            st.info("No AI insights yet. Use the assistant panel to ask your first business question.")

    with assistant_col:
        render_right_assistant_panel()


if __name__ == "__main__":
    main()
