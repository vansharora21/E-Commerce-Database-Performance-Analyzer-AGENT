"""
models/schemas.py
─────────────────
Pydantic models for the agent's structured data contracts.
These are NOT ORM models — they define the JSON shapes that
the agent produces and the API accepts/returns.
"""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Any, Literal, Optional
from datetime import datetime
from enum import Enum


# ── Intent Types ─────────────────────────────────────────────────────────────

class IntentType(str, Enum):
    REVENUE          = "revenue"
    ORDER_STATUS     = "order_status"
    PRODUCT_PERF     = "product_performance"
    CUSTOMER_INSIGHT = "customer_insight"
    INVENTORY        = "inventory"
    TREND            = "trend_comparison"
    TOP_N            = "top_n_ranking"
    PAYMENT          = "payment_analytics"
    CONVERSATIONAL   = "conversational"
    UNKNOWN          = "unknown"


class TimePeriod(str, Enum):
    TODAY      = "today"
    YESTERDAY  = "yesterday"
    THIS_WEEK  = "this_week"
    LAST_WEEK  = "last_week"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    THIS_YEAR  = "this_year"
    CUSTOM     = "custom"
    ALL_TIME   = "all_time"


# ── Query Plan (the structured JSON the agent outputs before execution) ───────

class QueryFilter(BaseModel):
    field: str = "createdAt"
    operator: str = "eq"    # validated below
    value: Any = None
    value2: Optional[Any] = None

    @field_validator("operator", mode="before")
    @classmethod
    def coerce_operator(cls, v):
        allowed = {"eq","ne","gt","gte","lt","lte","in","nin","regex","between"}
        return v if v in allowed else "eq"

    @field_validator("field", mode="before")
    @classmethod
    def coerce_field(cls, v):
        return str(v) if v is not None else "createdAt"


class QueryPlan(BaseModel):
    """
    Null-tolerant query plan. The LLM may return None for optional fields;
    field_validators coerce them to safe defaults so we never crash on
    Pydantic literal_error.
    """
    collection: str = "orders"          # validated below
    operation: str = "aggregate"        # validated below
    filters: list[QueryFilter] = Field(default_factory=list)
    group_by: Optional[str] = None
    metric: Optional[str] = None        # validated below
    metric_field: Optional[str] = None
    sort_field: Optional[str] = None
    sort_order: Optional[str] = "desc"  # validated below → always "asc"|"desc"
    limit: Optional[int] = 10           # validated below → clamped 1-100
    date_field: Optional[str] = None
    time_period: Optional[TimePeriod] = None
    compare_previous: Optional[bool] = False

    # ── Validators (run before type-checking) ────────────────────────────────

    @field_validator("sort_order", mode="before")
    @classmethod
    def coerce_sort_order(cls, v):
        if v is None or v not in ("asc", "desc"):
            return "desc"
        return v

    @field_validator("limit", mode="before")
    @classmethod
    def coerce_limit(cls, v):
        try:
            v = int(v)
        except (TypeError, ValueError):
            return 10
        return max(1, min(100, v))

    @field_validator("collection", mode="before")
    @classmethod
    def coerce_collection(cls, v):
        allowed = {"users", "orders", "products", "payments"}
        return v if v in allowed else "orders"

    @field_validator("operation", mode="before")
    @classmethod
    def coerce_operation(cls, v):
        allowed = {"aggregate", "count", "find_one", "distinct"}
        return v if v in allowed else "aggregate"

    @field_validator("metric", mode="before")
    @classmethod
    def coerce_metric(cls, v):
        if v is None:
            return None
        allowed = {"sum", "avg", "count", "min", "max"}
        return v if v in allowed else None

    @field_validator("compare_previous", mode="before")
    @classmethod
    def coerce_bool(cls, v):
        if v is None:
            return False
        return bool(v)

    @field_validator("filters", mode="before")
    @classmethod
    def coerce_filters(cls, v):
        if not v or not isinstance(v, list):
            return []
        return v


# ── Agent Pipeline Stages ────────────────────────────────────────────────────

class IntentResult(BaseModel):
    intent: IntentType
    time_period: TimePeriod
    entities: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    rephrased_question: str


class QueryPlanResult(BaseModel):
    primary: QueryPlan
    comparison: Optional[QueryPlan] = None     # for trend / WoW / MoM
    safety_passed: bool = True
    safety_notes: list[str] = Field(default_factory=list)
    index_suggestions: list[str] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    primary_data: list[dict[str, Any]] | dict[str, Any]
    comparison_data: Optional[list[dict[str, Any]] | dict[str, Any]] = None
    row_count: int = 0
    execution_time_ms: float = 0.0
    query_complexity: Literal["simple", "moderate", "complex"] = "simple"


class InsightResult(BaseModel):
    headline: str
    summary: str
    key_metrics: list[dict[str, Any]]
    trend: Optional[dict[str, Any]] = None
    recommendations: list[str] = Field(default_factory=list)
    data_quality_notes: list[str] = Field(default_factory=list)
    chart_hint: Optional[Literal["bar", "line", "pie", "table", "number"]] = None


# ── Full Agent Response ───────────────────────────────────────────────────────

class AgentResponse(BaseModel):
    question: str
    intent: IntentType
    time_period: TimePeriod
    insight: InsightResult
    raw_results_preview: list[dict[str, Any]] = Field(default_factory=list)
    execution_time_ms: float
    pipeline_steps: list[str] = Field(default_factory=list)
    index_suggestions: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    # Conversation fields
    is_conversational: bool = False
    plain_response: Optional[str] = None   # set when is_conversational=True


# ── API Request/Response Schemas ─────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=500,
        examples=["How much revenue did we generate this week?"]
    )
    session_id: str = Field(
        default="default",
        max_length=64,
        description="Browser session ID for conversation memory"
    )


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: str = "AGENT_ERROR"
