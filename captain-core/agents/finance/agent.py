"""
Finance Agent — reads CSV bank/card exports or a local ledger file and
produces a spending snapshot, budget status, and anomaly flags.
No cloud connection required; works entirely from local CSV files.
"""
import logging
import time
from pathlib import Path
from agents.base import AgentBase, AgentTask, AgentResult, Tool, Artifact, Permission

log = logging.getLogger(__name__)

DEFAULT_LEDGER_DIR = Path.home() / "Documents" / "Captain" / "Finance"


class Agent(AgentBase):
    id = "finance"
    name = "Finance Agent"
    description = "Analyzes spending from local CSV exports and flags anomalies"
    capabilities = ["spending_summary", "budget_check", "anomaly_detection", "monthly_report"]
    required_permissions = [Permission.FILESYSTEM_READ]

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="spending_summary",
                description="Summarize recent spending from CSV files",
                parameters={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "default": 30,
                                 "description": "How many days back to analyze"},
                    },
                    "required": [],
                },
                handler=self._spending_summary,
            ),
            Tool(
                name="find_anomalies",
                description="Flag unusual transactions (large amounts, new merchants)",
                parameters={
                    "type": "object",
                    "properties": {
                        "threshold_usd": {"type": "number", "default": 200.0},
                    },
                    "required": [],
                },
                handler=self._find_anomalies,
            ),
            Tool(
                name="list_csv_files",
                description="List available CSV transaction files",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=self._list_csv_files,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()
        from briefing.store import add_item
        from api.websocket import event_bus

        tools = await self.get_tools()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a finance agent. Analyze spending data from CSV files. "
                    "Provide a concise summary: total spent, top categories, any anomalies. "
                    "Be factual and specific with numbers."
                ),
            },
            {"role": "user", "content": task.user_message},
        ]

        response, tool_calls, tokens = await self._llm_tool_loop(messages, tools, task)

        if response:
            await add_item(
                category="finance",
                title="Financial snapshot",
                summary=response[:400],
                source_agent=self.id,
                priority=5,
            )
            await event_bus.publish("notification", {
                "category": "finance",
                "title": "Finance update",
                "summary": response[:200],
                "priority": 5,
            })

        return AgentResult(
            task_id=task.id,
            success=True,
            response=response or "No financial data found. Add CSV exports to ~/Documents/Captain/Finance/",
            tool_calls=tool_calls,
            tokens_used=tokens,
            latency_ms=int((time.time() - t_start) * 1000),
        )

    async def _load_transactions(self, days: int = 30) -> list[dict]:
        """Load and parse all CSV files in the ledger directory."""
        import csv
        from datetime import datetime, timedelta

        DEFAULT_LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        cutoff = datetime.now() - timedelta(days=days)
        transactions = []

        for csv_path in DEFAULT_LEDGER_DIR.glob("*.csv"):
            try:
                with open(csv_path, newline="", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Try common column name variants
                        date_str = row.get("Date") or row.get("date") or row.get("Transaction Date") or ""
                        amount_str = row.get("Amount") or row.get("amount") or row.get("Debit") or "0"
                        description = row.get("Description") or row.get("description") or row.get("Merchant") or ""

                        try:
                            # Try multiple date formats
                            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y"):
                                try:
                                    date = datetime.strptime(date_str.strip(), fmt)
                                    break
                                except ValueError:
                                    continue
                            else:
                                continue

                            if date < cutoff:
                                continue

                            amount = float(amount_str.replace("$", "").replace(",", "").strip() or "0")
                            transactions.append({
                                "date": date,
                                "amount": abs(amount),
                                "description": description.strip(),
                                "source_file": csv_path.name,
                            })
                        except Exception:
                            continue
            except Exception as e:
                log.debug(f"Could not parse {csv_path}: {e}")

        return sorted(transactions, key=lambda x: x["date"], reverse=True)

    async def _spending_summary(self, days: int = 30) -> str:
        txns = await self._load_transactions(days)
        if not txns:
            return (
                f"No transactions found for the last {days} days. "
                f"Add CSV bank exports to {DEFAULT_LEDGER_DIR}"
            )

        total = sum(t["amount"] for t in txns)
        by_merchant: dict[str, float] = {}
        for t in txns:
            key = t["description"][:40]
            by_merchant[key] = by_merchant.get(key, 0) + t["amount"]

        top = sorted(by_merchant.items(), key=lambda x: x[1], reverse=True)[:5]
        top_str = "\n".join(f"  ${amt:.2f} — {name}" for name, amt in top)

        return (
            f"**Last {days} days — {len(txns)} transactions**\n"
            f"Total spent: ${total:.2f}\n\n"
            f"Top merchants:\n{top_str}"
        )

    async def _find_anomalies(self, threshold_usd: float = 200.0) -> str:
        txns = await self._load_transactions(30)
        if not txns:
            return "No transaction data available."

        large = [t for t in txns if t["amount"] >= threshold_usd]
        if not large:
            return f"No transactions above ${threshold_usd:.0f} in the last 30 days."

        lines = [
            f"${t['amount']:.2f} — {t['description'][:50]} ({t['date'].strftime('%b %d')})"
            for t in large[:10]
        ]
        return f"**Transactions ≥ ${threshold_usd:.0f}:**\n" + "\n".join(lines)

    async def _list_csv_files(self) -> str:
        DEFAULT_LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        files = list(DEFAULT_LEDGER_DIR.glob("*.csv"))
        if not files:
            return (
                f"No CSV files found in {DEFAULT_LEDGER_DIR}\n"
                "Export transactions from your bank and save them here."
            )
        return "\n".join(f.name for f in files)

    async def health_check(self):
        from agents.base import HealthStatus
        DEFAULT_LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        return HealthStatus.HEALTHY
