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

def get_neon_tools() -> list:
    return [create_ticket, update_ticket_status, get_active_tickets, log_expense]
