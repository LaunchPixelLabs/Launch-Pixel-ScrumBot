import os
from typing import Optional, List, Dict
from langchain_core.tools import tool
import scrumbot.integrations.admin_db as db

@tool
def create_ticket(title: str, description: str, priority: str, story_points: int) -> str:
    """Creates a new Kanban ticket on the LaunchPixel board."""
    # We call db.create_devops_task directly to use the real Admin tables
    task_id = db.create_devops_task(title, description, status="Pending", story_points=story_points)
    if task_id:
        return f"Created ticket LP-{task_id}: {title}"
    return "Failed to create ticket in Neon DB."

@tool
def update_ticket_status(ticket_id: str, status: str) -> str:
    """Updates the status of a Kanban ticket (e.g. Pending, In Progress, Blocked, Completed)."""
    success = db.update_ticket_status(ticket_id, status)
    if success:
        return f"Updated {ticket_id} to {status}"
    return f"Failed to update {ticket_id}."

@tool
def get_active_tickets() -> str:
    """Retrieves all active tickets on the Kanban board."""
    tickets = db.get_active_tickets()
    if not tickets:
        return "No active tickets found."
    lines = [f"{t['id']} [{t['status']}]: {t['title']} (Assignee: {t['assignee_name']})" for t in tickets]
    return "\n".join(lines)

@tool
def log_expense(amount: float, service_vertical: str, category: str, description: str, payment_mode: str = "other") -> str:
    """Logs a financial expense to the Neon database. service_vertical must be one of: 'tech', 'ca_referral', 'influencer', 'general'."""
    exp_id = db.log_expense(amount, service_vertical, category, description, payment_mode)
    if exp_id:
        return f"Successfully logged expense ID {exp_id} for {amount} ({category})."
    return "Failed to log expense."


@tool
def save_lead(name: str, contact: str, source: str, summary: str, score: int = 0) -> str:
    """Save a business lead to the LaunchPixel growth pipeline.

    ``name`` who they are, ``contact`` an email/handle/phone, ``source`` where the
    lead came from (e.g. 'gmail', 'web', 'referral'), ``summary`` what they want,
    ``score`` a 0-100 fit/intent score. De-duplicates on contact + summary.
    """
    lead_id = db.save_lead(name, contact, source, summary, score=score)
    if lead_id:
        return f"Saved lead #{lead_id}: {name} (score {score}) from {source}."
    return "Failed to save lead."


@tool
def list_leads(status: str = "") -> str:
    """List leads in the growth pipeline, optionally filtered by status (new, contacted, qualified, won, lost)."""
    leads = db.get_leads(status=status or None)
    if not leads:
        return "No leads found."
    lines = [
        f"#{l['id']} [{l['status']}] score {l.get('score', 0)}: {l['name']} ({l.get('contact','?')}) — {l.get('summary','')[:120]}"
        for l in leads
    ]
    return "\n".join(lines)


@tool
def update_lead_status(lead_id: str, status: str) -> str:
    """Update a lead's pipeline status (new, contacted, qualified, won, lost)."""
    if db.update_lead_status(lead_id, status):
        return f"Updated lead {lead_id} to {status}."
    return f"Failed to update lead {lead_id}."


# --- Founder escalation ------------------------------------------------------

@tool
def escalate_to_founder(topic: str, summary: str, severity: str = "medium") -> str:
    """Escalate a critical item to the founder (Vivek).

    Use this when something genuinely needs the founder's attention: an overdue
    ticket, a hot lead (score 70+), an unhappy client, or any material spend or
    commitment. ``topic`` is a short label (e.g. 'Overdue ticket LP-7'), ``summary``
    is the detail and recommended action, ``severity`` is one of low|medium|high|critical.
    The alert is queued and delivered by a background loop (high/critical also DM).
    """
    aid = db.create_founder_alert(severity, topic, summary)
    if aid:
        return f"Escalation #{aid} queued for the founder ({severity}): {topic}"
    return "Failed to queue escalation for the founder."


# --- Finance visibility ------------------------------------------------------

@tool
def get_expense_summary(days: int = 30) -> str:
    """Summarise spend over the last N days: total, count, and breakdown by service vertical and category."""
    s = db.get_expense_summary(days=days)
    lines = [
        f"Spend over last {s['days']} days: {s['total']:.2f} across {s['count']} expenses."
    ]
    if s.get("by_vertical"):
        lines.append("By vertical: " + ", ".join(
            f"{v['vertical']} {v['total']:.2f}" for v in s["by_vertical"]
        ))
    if s.get("by_category"):
        lines.append("By category: " + ", ".join(
            f"{c['category']} {c['total']:.2f}" for c in s["by_category"]
        ))
    return "\n".join(lines)


@tool
def list_expenses(limit: int = 10) -> str:
    """List recent expenses (newest first) so the agent can spot unusual spending."""
    rows = db.get_expenses(days=30, limit=limit)
    if not rows:
        return "No recent expenses logged."
    return "\n".join(
        f"#{r.get('id','?')} {r.get('date','?')} {r.get('amount',0)} "
        f"({r.get('service_vertical','?')}/{r.get('category','?')}): {r.get('description','') or ''}"
        for r in rows
    )


# --- Decision recall ---------------------------------------------------------

@tool
def list_decisions(limit: int = 5) -> str:
    """Recall the most recent high-stakes decisions made by the Dual-Brain council.

    Use this before re-deciding something the team has already ruled on, to stay
    consistent and avoid contradicting a prior call.
    """
    rows = db.get_decisions(limit=limit)
    if not rows:
        return "No recorded decisions yet."
    return "\n".join(
        f"#{r.get('id','?')} [{r.get('createdAt','?')}]: "
        f"{(r.get('question') or '')[:100]} -> "
        f"{(r.get('verdict') or '(no verdict)')[:120]}"
        for r in rows
    )


# --- Business snapshot (the "knows the business" centerpiece) ----------------

@tool
def company_snapshot() -> str:
    """Pull a live snapshot of the whole business: tickets, leads, spend, alerts, recent decisions.

    Call this at the start of any status, briefing, or autonomous report so you
    answer from real state instead of guessing. Returns a compact, structured
    summary covering board health, the lead pipeline, recent finances, pending
    founder escalations, and the last few council decisions.
    """
    try:
        active = db.count_active_tickets()
        overdue = db.count_overdue_tickets()
        lead_groups = db.leads_by_status()
        top = db.top_leads(limit=3)
        spend = db.get_expense_summary(days=7)
        pending_alerts = db.get_undelivered_alerts(limit=5)
        recent_decisions = db.get_decisions(limit=3)
    except Exception as exc:  # noqa: BLE001 - snapshot must never crash a report
        return f"Could not build business snapshot right now: {exc}"

    lines = ["== LaunchPixel Business Snapshot =="]
    lines.append(f"Board: {active} active tickets, {overdue} overdue (>48h no update).")

    if lead_groups:
        lead_line = ", ".join(
            f"{g.get('status','?')}={g.get('count',0)}" for g in lead_groups
        )
        lines.append(f"Leads: {lead_line}.")
    else:
        lines.append("Leads: none in the pipeline.")
    if top:
        lines.append(
            "Top open leads: "
            + "; ".join(
                f"#{l.get('id','?')} {l.get('name','?') or 'Unknown'} (score {l.get('score',0)})"
                for l in top
            )
        )

    lines.append(
        f"Spend (7d): {spend.get('total', 0):.2f} across {spend.get('count', 0)} expenses."
    )

    if pending_alerts:
        first = pending_alerts[0]
        lines.append(
            f"Pending founder escalations: {len(pending_alerts)} "
            f"(highest: {first.get('severity','?')} — {first.get('topic','?')})"
        )

    if recent_decisions:
        lines.append("Recent decisions:")
        for d in recent_decisions:
            v = (d.get("verdict") or "")[:80]
            lines.append(f"  - #{d.get('id','?')}: {(d.get('question') or '')[:80]} -> {v}")
    else:
        lines.append("Recent decisions: none yet.")

    return "\n".join(lines)


def get_neon_tools() -> list:
    return [
        create_ticket,
        update_ticket_status,
        get_active_tickets,
        log_expense,
        save_lead,
        list_leads,
        update_lead_status,
        escalate_to_founder,
        get_expense_summary,
        list_expenses,
        list_decisions,
        company_snapshot,
    ]
