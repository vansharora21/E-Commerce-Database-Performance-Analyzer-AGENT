import pytest
from unittest.mock import AsyncMock, MagicMock
from agent.orchestrator import AgentOrchestrator
from models import ExecutionResult, QueryPlanResult, QueryPlan, IntentResult, IntentType, TimePeriod, InsightResult

@pytest.mark.asyncio
async def test_replan_on_empty_result():
    # 1. Mock DB connection
    mock_db = MagicMock()

    # 2. Instantiate orchestrator
    orchestrator = AgentOrchestrator(db=mock_db)

    # 3. Mock intent detector to return a simple analytics intent
    mock_intent = IntentResult(
        intent=IntentType.REVENUE,
        time_period=TimePeriod.THIS_WEEK,
        confidence=0.9,
        rephrased_question="How much revenue did we generate this week?",
        is_compound=False,
        sub_intents=[]
    )
    orchestrator._intent_detector.detect = AsyncMock(return_value=mock_intent)

    # 4. Mock query planner to return a query plan on first call,
    # and a modified query plan on second call.
    mock_plan = QueryPlan(
        collection="orders",
        operation="aggregate",
        filters=[],
        time_period=TimePeriod.THIS_WEEK
    )
    mock_plan_res_1 = QueryPlanResult(
        primary=mock_plan,
        safety_passed=True,
        replan_reason=None
    )
    mock_plan_res_2 = QueryPlanResult(
        primary=mock_plan.model_copy(update={"limit": 50}),  # Slightly modified
        safety_passed=True,
        replan_reason="loosened date filter"
    )
    orchestrator._query_planner.plan = AsyncMock(side_effect=[mock_plan_res_1, mock_plan_res_2])

    # 5. Mock query executor:
    # First execution returns 0 rows, second returns 1 row.
    mock_exec_res_1 = ExecutionResult(
        primary_data=[],
        row_count=0,
        execution_time_ms=5.0
    )
    mock_exec_res_2 = ExecutionResult(
        primary_data=[{"totalAmount": 100}],
        row_count=1,
        execution_time_ms=10.0
    )
    orchestrator._query_executor.execute = AsyncMock(side_effect=[mock_exec_res_1, mock_exec_res_2])

    # 6. Mock insight generator
    mock_insight = InsightResult(
        headline="Revenue generated",
        summary="We generated 100 INR",
        key_metrics=[]
    )
    orchestrator._insight_gen.generate = AsyncMock(return_value=mock_insight)

    # 7. Run orchestrator
    response = await orchestrator.ask("How much revenue did we generate this week?")

    # 8. Verify asserts
    assert orchestrator._query_planner.plan.call_count == 2
    assert orchestrator._query_executor.execute.call_count == 2
    assert any("Re-plan attempt 1: loosened date filter" in step for step in response.pipeline_steps)
