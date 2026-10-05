"""
Deterministic mock AI provider.

Used when no real provider is available (dev, tests, or when all real
providers fail). Rather than returning a canned string, this provider
inspects the system prompt for the JSON context block the chat service
always includes, and produces a relevant, data-grounded reply.

Never calls the network. Never invents data. If the context block is
missing, it falls back to a generic capability message.
"""
import json
import logging

from .base import AIProvider

logger = logging.getLogger('apps.ai')


class MockAIProvider(AIProvider):
    """Offline provider — reads context, answers from it."""

    def __init__(self, config=None):
        super().__init__(config or {})
        self.model = 'mock'

    # ─────────────────────────────────────────────────────────────
    # Chat
    # ─────────────────────────────────────────────────────────────
    def chat_completion(self, messages, max_tokens=1000) -> str:
        user_msg = self._last_user_message(messages)
        context = self._extract_context(messages)
        return self._respond(user_msg, context)

    # ─────────────────────────────────────────────────────────────
    # Analysis interface (deterministic stubs — never invent data)
    # ─────────────────────────────────────────────────────────────
    def detect_payday(self, transactions):
        return {
            'detected_salary': False,
            'salary_amount': None,
            'salary_frequency': None,
            'employer': None,
            'historical_paydays': [],
            'confidence': 0.0,
            'predicted_next_payday': None,
            'explanation': 'Mock provider — no live AI available.',
        }

    def detect_debt_obligations(self, transactions):
        return {
            'creditors': [],
            'total_monthly_obligations': 0,
            'explanation': 'Mock provider — no live AI available.',
        }

    def analyze_transactions(self, transactions):
        return {
            'salary_detection': {},
            'recurring_expenses': [],
            'unusual_transactions': [],
            'monthly_income_estimate': 0.0,
            'monthly_expense_estimate': 0.0,
            'explanation': 'Mock provider — no live AI available.',
        }

    # ─────────────────────────────────────────────────────────────
    # Response synthesis
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _last_user_message(messages):
        for m in reversed(messages or []):
            if (m or {}).get('role') == 'user':
                return ((m.get('content') or '')).strip()
        return ''

    @staticmethod
    def _extract_context(messages):
        """
        Scan system messages for the largest JSON object.
        The chat service always includes a context block via the
        'Context data (only source of truth)' system message.
        """
        best = None
        best_len = 0
        for m in messages or []:
            if (m or {}).get('role') != 'system':
                continue
            content = m.get('content') or ''
            start = content.find('{')
            end = content.rfind('}')
            if start == -1 or end <= start:
                continue
            candidate = content[start:end + 1]
            if len(candidate) <= best_len:
                continue
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                best = parsed
                best_len = len(candidate)
        return best or {}

    # ── The actual reply ─────────────────────────────────────────
    def _respond(self, user_msg, context) -> str:
        text = (user_msg or '').lower().strip()
        role = context.get('role', 'client')

        if not text or text in ('hi', 'hello', 'hey', 'yo', 'howzit', 'hie'):
            return self._greeting(role, context)

        if any(k in text for k in ('performance', 'portfolio', 'overview', 'summary', 'how are we doing', 'how is the business')):
            return self._portfolio(role, context)

        if any(k in text for k in ('outstanding', 'balance', 'owe', 'owed', 'how much')):
            return self._balance(role, context)

        if 'overdue' in text:
            return self._overdue(role, context)

        if any(k in text for k in ('recommend', 'suggest', 'advice', 'advise', 'should i')):
            return self._recommendations(role, context)

        if 'application' in text:
            return self._applications(role, context)

        if 'loan' in text:
            return self._loans(role, context)

        if 'ai' in text or 'model' in text or 'which' in text:
            return (
                "I'm running in **offline mode**. The live AI providers "
                "(Grok, GLM) are currently unavailable. Enable a working "
                "provider in `.env` for full responses."
            )

        return self._fallback(role, context)

    # ── Individual intents ───────────────────────────────────────
    def _greeting(self, role, ctx):
        if role == 'staff':
            p = ctx.get('portfolio') or {}
            return (
                "Hello. I'm in **offline mode** — the AI providers are "
                "unavailable right now, so I can only report what's already "
                "in this session.\n\n"
                "**Portfolio snapshot**\n"
                f"- Active loans: {p.get('active_loans', 0)}\n"
                f"- Overdue: {p.get('overdue_loans', 0)}\n"
                f"- Defaulted: {p.get('defaulted_loans', 0)}\n"
                f"- Total outstanding: R {p.get('total_outstanding', '0.00')}"
            )
        loans = ctx.get('loans') or []
        return (
            "Hello. I'm in **offline mode** — the AI providers are "
            "unavailable right now, so I can only answer from data "
            f"already on your account. You have {len(loans)} loan(s) on file."
        )

    def _portfolio(self, role, ctx):
        if role != 'staff':
            return "Portfolio reporting is only available to staff accounts."
        p = ctx.get('portfolio') or {}
        lines = [
            "**Portfolio snapshot** _(offline mode)_",
            f"- Total loans: {p.get('total_loans', p.get('active_loans', 0))}",
            f"- Active: {p.get('active_loans', 0)}",
            f"- Overdue: {p.get('overdue_loans', 0)}",
            f"- Defaulted: {p.get('defaulted_loans', 0)}",
            f"- Total outstanding: R {p.get('total_outstanding', '0.00')}",
        ]
        return "\n".join(lines) + (
            "\n\n_Live narrative analysis needs Grok or GLM. "
            "See `.env` → `GROK_ENABLED` / `GLM_ENABLED`._"
        )

    def _balance(self, role, ctx):
        if role == 'staff':
            return self._portfolio(role, ctx)
        loans = ctx.get('loans') or []
        if not loans:
            return "No active loans on your account right now."
        lines = ["**Your outstanding balances**"]
        for l in loans[:5]:
            lines.append(
                f"- {l.get('product', 'Loan')}: R {l.get('outstanding', '0.00')} "
                f"({l.get('status', '?')})"
            )
        return "\n".join(lines)

    def _overdue(self, role, ctx):
        if role == 'staff':
            p = ctx.get('portfolio') or {}
            n = p.get('overdue_loans', 0)
            if n == 0:
                return "No overdue loans in the portfolio right now."
            return f"There are **{n}** overdue loan(s) in the portfolio."
        return "You have no overdue loans."

    def _applications(self, role, ctx):
        apps = ctx.get('applications') or []
        if not apps:
            return "No applications in the current dataset."
        return f"There are **{len(apps)}** application(s) in the current dataset."

    def _loans(self, role, ctx):
        loans = ctx.get('loans') or []
        if not loans:
            return "No loans in the current data."
        lines = ["**Loans on file**"]
        for l in loans[:10]:
            lines.append(
                f"- {l.get('product', 'Loan')}: R {l.get('outstanding', '0.00')} "
                f"({l.get('status', '?')})"
            )
        return "\n".join(lines)

    def _recommendations(self, role, ctx):
        if role != 'staff':
            return (
                "Recommendations are only available to staff accounts. "
                "I can help you check your balance or your next repayment."
            )
        p = ctx.get('portfolio') or {}
        active = p.get('active_loans', 0)
        overdue = p.get('overdue_loans', 0)
        outstanding = p.get('total_outstanding', '0.00')

        lines = ["**Snapshot-based recommendations** _(offline mode)_"]
        if overdue > 0:
            lines.append(
                f"- **Priority:** {overdue} loan(s) overdue. "
                "Start collections outreach before month-end."
            )
        if active == 0:
            lines.append("- No active loans. Focus on converting the approved backlog.")
        else:
            lines.append(
                f"- {active} active loan(s) with R {outstanding} outstanding. "
                "Monitor the collection window and retry queue."
            )
        lines.append(
            "\n_For live, contextual recommendations, configure a working "
            "AI provider in `.env`._"
        )
        return "\n".join(lines)

    def _fallback(self, role, ctx):
        if role == 'staff':
            return (
                "I'm in **offline mode** and can only summarise the data "
                "already on this page.\n\n"
                "Try: *portfolio*, *overdue loans*, *outstanding balance*, "
                "*recommendations*."
            )
        return (
            "I'm in **offline mode** and can only answer from data already "
            "on your account.\n\nTry: *my balance*, *my loans*, *my next payment*."
        )