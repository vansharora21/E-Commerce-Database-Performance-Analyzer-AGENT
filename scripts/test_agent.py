"""
scripts/test_agent.py
──────────────────────
Smoke-tests & demo runner for the agent pipeline.

Run BEFORE the server to verify the full pipeline works:
  python scripts/test_agent.py

Tests:
  1. Revenue query
  2. Order status breakdown
  3. Top products
  4. Customer insight
  5. WoW comparison
  6. Ambiguous question (low confidence)
"""
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(Path(__file__).parent.parent)  # ensure .env is found

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from config import connect_db, get_db
from agent import AgentOrchestrator

console = Console()

TEST_QUESTIONS = [
    "How much revenue did we generate this week?",
    "What is the breakdown of orders by status this month?",
    "Which are the top 5 best-selling products?",
    "How many new customers joined this month?",
    "Compare this week's revenue vs last week",
    "xyz blah blah nonsense question",       # should return low-confidence fallback
]


async def run_tests():
    console.rule("[bold magenta]🤖 Agentic AI — Pipeline Test Run")

    await connect_db()
    db    = get_db()
    agent = AgentOrchestrator(db)

    for i, question in enumerate(TEST_QUESTIONS, 1):
        console.print(f"\n[bold cyan]Test {i}/{len(TEST_QUESTIONS)}[/bold cyan]")
        console.print(Panel(f"[italic]{question}[/italic]", title="Question", border_style="blue"))

        try:
            result = await agent.ask(question)

            # Pipeline steps
            for step in result.pipeline_steps:
                console.print(f"  [dim]{step}[/dim]")

            # Main insight
            console.print(Panel(
                f"[bold]{result.insight.headline}[/bold]\n\n"
                f"{result.insight.summary}",
                title=f"💡 Insight [{result.intent.value}]",
                border_style="green",
            ))

            # Key metrics table
            if result.insight.key_metrics:
                tbl = Table(box=box.SIMPLE, show_header=True)
                tbl.add_column("Metric",  style="cyan")
                tbl.add_column("Value",   style="bold yellow")
                tbl.add_column("Unit",    style="dim")
                tbl.add_column("Change%", style="green")
                for m in result.insight.key_metrics:
                    tbl.add_row(
                        str(m.get("label", "")),
                        str(m.get("value", "")),
                        str(m.get("unit", "")),
                        str(m.get("change_pct") or "—"),
                    )
                console.print(tbl)

            # Trend
            if result.insight.trend:
                t = result.insight.trend
                direction = {"up": "📈", "down": "📉", "flat": "➡️"}.get(t.get("direction",""), "")
                console.print(f"  {direction} [bold]{t.get('period_label','')}[/bold]: {t.get('narrative','')}")

            # Recommendations
            for rec in result.insight.recommendations:
                console.print(f"  [yellow]→ {rec}[/yellow]")

            # Index suggestions
            if result.index_suggestions:
                console.print(f"  [dim]Index hint: {', '.join(result.index_suggestions)}[/dim]")

        except Exception as e:
            console.print(f"  [bold red]ERROR: {e}[/bold red]")

    console.rule("[bold green]✅ Test run complete")


if __name__ == "__main__":
    asyncio.run(run_tests())
