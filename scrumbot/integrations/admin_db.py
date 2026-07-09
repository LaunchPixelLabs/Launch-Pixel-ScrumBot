import os
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
from scrumbot.config import get_settings
DATABASE_URL = get_settings().database_url

def get_conn():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except Exception as e:
        print(f"❌ [Database Error] Failed to connect to database: {e}")
        raise e

def _parse_id(ticket_id: str) -> int:
    try:
        return int(ticket_id.split('-')[1]) if '-' in ticket_id else int(ticket_id)
    except (ValueError, TypeError, IndexError):
        return 0

# --- DevOps ---

def get_last_ticket_id():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(id) FROM devops_tasks;")
            row = cur.fetchone()
            return row[0] if row[0] else 0
    except Exception:
        return 0
    finally:
        conn.close()

def create_ticket(ticket_id, title, description, assignee_id, assignee_name, priority, priority_days, start_date, end_date, story_points, acceptance_criteria, thread_id, channel_id):
    # Map to devops_tasks. We store extra info in 'tags' or 'links' for now.
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # We must ignore manual ticket_id because devops_tasks id is auto_increment,
            # but we can insert if we want, or just let DB handle it.
            cur.execute(
                """
                INSERT INTO devops_tasks (
                    title, description, status, "storyPoints", "createdAt", "updatedAt", tags, links
                ) VALUES (%s, %s, 'Pending', %s, NOW(), NOW(), %s, %s) RETURNING id;
                """,
                (
                    title, 
                    f"{description}\n\nAcceptance Criteria: {acceptance_criteria}\nAssignee: {assignee_name}", 
                    story_points,
                    psycopg2.extras.Json([priority]),
                    psycopg2.extras.Json([{"discord_channel_id": channel_id, "discord_thread_id": thread_id}])
                )
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error creating devops task: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def create_devops_task(title, description, status="Pending", story_points=1):
    """Insert a task into ``devops_tasks`` and return its new integer id.

    Used by the LangGraph agent's ``create_ticket`` tool (the Nemotron core
    brain); the ``!ticket create`` Discord flow uses :func:`create_ticket`
    instead, which also wires up channels and Kanban cards.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO devops_tasks (
                    title, description, status, "storyPoints", "createdAt", "updatedAt"
                ) VALUES (%s, %s, %s, %s, NOW(), NOW()) RETURNING id;
                """,
                (title, description, status, story_points),
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
    except Exception as e:
        print(f"❌ Error creating devops task: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def get_active_tickets():
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM devops_tasks WHERE status != 'Completed' AND status != 'Closed' ORDER BY id ASC;")
            tasks = cur.fetchall()
            # Map to legacy dict format for Discord Cog
            results = []
            for t in tasks:
                results.append({
                    "id": f"LP-{t['id']}",
                    "title": t['title'],
                    "description": t['description'],
                    "status": t['status'],
                    "story_points": t['storyPoints'],
                    "priority": t['tags'][0] if t.get('tags') else "Medium",
                    "priority_days": 0,
                    "assignee_name": "Unknown",
                    "channel_id": t['links'][0].get('discord_channel_id') if t.get('links') else None,
                    "thread_id": t['links'][0].get('discord_thread_id') if t.get('links') else None,
                    "end_date": None,
                    "updated_at": t.get('updatedAt'),
                })
            return results
    except Exception as e:
        print(f"⚠️ Error fetching devops tasks: {e}")
        return []
    finally:
        conn.close()

def get_ticket(ticket_id):
    conn = get_conn()
    try:
        tid = _parse_id(ticket_id)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM devops_tasks WHERE id = %s;", (tid,))
            t = cur.fetchone()
            if not t: return None
            return {
                "id": f"LP-{t['id']}",
                "title": t['title'],
                "description": t['description'],
                "status": t['status'],
                "story_points": t['storyPoints'],
                "priority": t['tags'][0] if t.get('tags') else "Medium",
                "priority_days": 0,
                "assignee_name": "Unknown",
                "channel_id": t['links'][0].get('discord_channel_id') if t.get('links') else None,
                "thread_id": t['links'][0].get('discord_thread_id') if t.get('links') else None,
                "start_date": None,
                "end_date": None,
                "acceptance_criteria": ""
            }
    except Exception as e:
        print(f"⚠️ Error fetching ticket {ticket_id}: {e}")
        return None
    finally:
        conn.close()

def update_ticket_status(ticket_id, status):
    conn = get_conn()
    try:
        tid = _parse_id(ticket_id)
        with conn.cursor() as cur:
            cur.execute("UPDATE devops_tasks SET status = %s, \"updatedAt\" = NOW() WHERE id = %s;", (status, tid))
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error updating ticket status: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def update_ticket_assignee(ticket_id, assignee_id, assignee_name):
    # Appends assignee to description for now until we add an Employee mapping
    conn = get_conn()
    try:
        tid = _parse_id(ticket_id)
        with conn.cursor() as cur:
            cur.execute("UPDATE devops_tasks SET description = description || %s, \"updatedAt\" = NOW() WHERE id = %s;", (f"\nRe-assigned to: {assignee_name}", tid))
            conn.commit()
            return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()

def get_ticket_attachments(ticket_id):
    return []

def get_ticket_comments(ticket_id):
    return []

# --- Finance ---

def log_expense(amount, service_vertical, category, description, payment_mode="other", added_by=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO finance_expenses (
                    date, amount, service_vertical, category, description, payment_mode, added_by, "createdAt", "updatedAt"
                ) VALUES (CURRENT_DATE, %s, %s, %s, %s, %s, %s, NOW(), NOW()) RETURNING id;
                """,
                (amount, service_vertical, category, description, payment_mode, added_by)
            )
            exp_id = cur.fetchone()[0]
            conn.commit()
            return exp_id
    except Exception as e:
        print(f"❌ Error logging expense: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

# --- Company Knowledge (Dynamic Memory) ---

def init_company_knowledge_table():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS company_knowledge (
                    id SERIAL PRIMARY KEY,
                    topic VARCHAR(255) UNIQUE NOT NULL,
                    content TEXT NOT NULL,
                    "updatedAt" TIMESTAMP DEFAULT NOW()
                );
                """
            )
            conn.commit()
    except Exception as e:
        print(f"❌ Error creating company_knowledge table: {e}")
    finally:
        conn.close()

# Ensure the table is created at startup
init_company_knowledge_table()

def get_company_knowledge() -> str:
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT topic, content, \"updatedAt\" FROM company_knowledge ORDER BY \"updatedAt\" DESC;")
            rows = cur.fetchall()
            if not rows:
                return "No company knowledge found yet."
            
            context = "LaunchPixel Company Knowledge & SOPs:\n\n"
            for row in rows:
                context += f"### {row['topic']} (Last updated: {row['updatedAt']})\n"
                context += f"{row['content']}\n\n"
            return context
    except Exception as e:
        print(f"⚠️ Error fetching company knowledge: {e}")
        return "Error fetching company knowledge."
    finally:
        conn.close()

def upsert_company_knowledge(topic: str, content: str) -> bool:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_knowledge (topic, content, "updatedAt")
                VALUES (%s, %s, NOW())
                ON CONFLICT (topic) DO UPDATE SET
                    content = EXCLUDED.content,
                    "updatedAt" = EXCLUDED."updatedAt";
                """,
                (topic, content)
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error upserting company knowledge: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


# --- Leads (growth pipeline) -------------------------------------------------

def init_leads_table():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255),
                    contact VARCHAR(255),
                    source VARCHAR(120),
                    summary TEXT,
                    status VARCHAR(40) DEFAULT 'new',
                    score INT DEFAULT 0,
                    "createdAt" TIMESTAMP DEFAULT NOW(),
                    "updatedAt" TIMESTAMP DEFAULT NOW()
                );
                """
            )
            conn.commit()
    except Exception as e:
        print(f"❌ Error creating leads table: {e}")
    finally:
        conn.close()


def save_lead(name, contact, source, summary, score=0, status="new"):
    """Insert a lead, de-duplicating on (contact, summary). Returns the id or None.

    Idempotent enough for the autonomous loop: if a lead with the same contact and
    summary already exists we return its id instead of creating a duplicate.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM leads WHERE contact = %s AND summary = %s LIMIT 1;",
                (contact, summary),
            )
            existing = cur.fetchone()
            if existing:
                return existing[0]
            cur.execute(
                """
                INSERT INTO leads (name, contact, source, summary, status, score, "createdAt", "updatedAt")
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW()) RETURNING id;
                """,
                (name, contact, source, summary, status, score),
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
    except Exception as e:
        print(f"❌ Error saving lead: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def get_leads(status=None, limit=25):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if status:
                cur.execute(
                    'SELECT * FROM leads WHERE status = %s ORDER BY score DESC, "createdAt" DESC LIMIT %s;',
                    (status, limit),
                )
            else:
                cur.execute(
                    'SELECT * FROM leads ORDER BY score DESC, "createdAt" DESC LIMIT %s;',
                    (limit,),
                )
            return cur.fetchall()
    except Exception as e:
        print(f"⚠️ Error fetching leads: {e}")
        return []
    finally:
        conn.close()


def update_lead_status(lead_id, status):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE leads SET status = %s, "updatedAt" = NOW() WHERE id = %s;',
                (status, _parse_id(str(lead_id))),
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error updating lead status: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


# --- Business knowledge seed (starter scaffold) ------------------------------

# A neutral scaffold so the Business Brain has structure on day one. These are
# frameworks with explicit TODO markers, NOT invented facts — the founder refines
# them via `learn_business_rule`. Seeding is idempotent and never overwrites a
# topic the founder has already authored.
_SEED_KNOWLEDGE = {
    "Company Overview": (
        "LaunchPixel (launchpixel.in) is an elite product & development agency. "
        "TODO(founder): confirm services, team size, positioning, and the "
        "flagship offerings we lead with."
    ),
    "Ideal Customer Profile": (
        "Used to qualify leads. TODO(founder): define target company size, "
        "industries, budget range, and the buying signals that make a lead 'hot' "
        "vs 'cold'. Until set, qualify on: clear budget, defined scope, decision "
        "maker engaged, timeline within a quarter."
    ),
    "Lead Qualification SOP": (
        "1. Capture name, contact, source, and what they want. 2. Score 0-100 on "
        "fit (ICP), intent (how ready to buy), and budget. 3. Log with save_lead. "
        "4. Draft a concise, value-first reply. 5. Escalate leads scoring 70+ to "
        "the founder. TODO(founder): adjust scoring thresholds."
    ),
    "Escalation Rules": (
        "Escalate to the founder (Vivek) when: a ticket is overdue by more than 2 "
        "days, a client is unhappy, a lead scores 70+, or any spend/commitment is "
        "material. TODO(founder): set the exact spend threshold."
    ),
    "KPIs": (
        "TODO(founder): define the numbers we run on — e.g. new qualified leads / "
        "week, proposal win rate, active projects on time, monthly revenue and "
        "burn. The Scrum Master reports against these."
    ),
}


def seed_default_business_knowledge() -> int:
    """Insert the starter knowledge scaffold for any topic that doesn't exist yet.

    Returns the number of topics newly seeded. Existing (founder-authored) topics
    are left untouched.
    """
    seeded = 0
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for topic, content in _SEED_KNOWLEDGE.items():
                cur.execute(
                    """
                    INSERT INTO company_knowledge (topic, content, "updatedAt")
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (topic) DO NOTHING;
                    """,
                    (topic, content),
                )
                if cur.rowcount:
                    seeded += 1
            conn.commit()
    except Exception as e:
        print(f"⚠️ Error seeding business knowledge: {e}")
        conn.rollback()
    finally:
        conn.close()
    return seeded


# Ensure the leads table exists at startup (mirrors the knowledge table above).
init_leads_table()


# --- Founder alerts (escalation queue) ---------------------------------------
# The agent and the schedulers write alerts here when something is genuinely
# critical. A drainer in main.py pulls undelivered rows and delivers them to the
# founder (@mention + DM for high/critical). Decoupling write from delivery keeps
# the agent — which has no Discord access — able to escalate, matching the
# existing architecture.

def init_founder_alerts_table():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS founder_alerts (
                    id SERIAL PRIMARY KEY,
                    severity VARCHAR(16) DEFAULT 'medium',
                    topic VARCHAR(255) NOT NULL,
                    summary TEXT NOT NULL,
                    delivered BOOLEAN DEFAULT FALSE,
                    "createdAt" TIMESTAMP DEFAULT NOW()
                );
                """
            )
            conn.commit()
    except Exception as e:
        print(f"❌ Error creating founder_alerts table: {e}")
    finally:
        conn.close()


def create_founder_alert(severity: str, topic: str, summary: str):
    """Queue an escalation for the founder. Returns the alert id or None.

    Severity is one of low|medium|high|critical. ``topic`` is a short label
    (e.g. 'Overdue ticket LP-7'); ``summary`` is the human-readable detail.
    """
    severity = (severity or "medium").lower()
    if severity not in ("low", "medium", "high", "critical"):
        severity = "medium"
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO founder_alerts (severity, topic, summary, delivered, "createdAt")
                VALUES (%s, %s, %s, FALSE, NOW()) RETURNING id;
                """,
                (severity, topic, summary),
            )
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else None
    except Exception as e:
        print(f"❌ Error creating founder alert: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def get_undelivered_alerts(limit: int = 20):
    """Return undelivered alerts, oldest first."""
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, severity, topic, summary, "createdAt"
                FROM founder_alerts
                WHERE delivered = FALSE
                ORDER BY "createdAt" ASC, severity ASC
                LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()
    except Exception as e:
        print(f"⚠️ Error fetching undelivered alerts: {e}")
        return []
    finally:
        conn.close()


def mark_alert_delivered(alert_id: int) -> bool:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE founder_alerts SET delivered = TRUE WHERE id = %s;',
                (alert_id,),
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error marking alert delivered: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


# --- Report ledger (autonomous-loop de-dup memory) ---------------------------
# Stops the 24/7 loop spamming the same finding every cycle: before posting, the
# loop asks "did I already report this signature recently?".

def init_report_ledger_table():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS report_ledger (
                    id SERIAL PRIMARY KEY,
                    focus VARCHAR(64) NOT NULL,
                    signature VARCHAR(255) NOT NULL,
                    summary TEXT,
                    "createdAt" TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS report_ledger_focus_sig_idx
                    ON report_ledger (focus, signature);
                """
            )
            conn.commit()
    except Exception as e:
        print(f"❌ Error creating report_ledger table: {e}")
    finally:
        conn.close()


def was_reported_recently(focus: str, signature: str, hours: int = 12) -> bool:
    """True if this (focus, signature) was recorded within the last ``hours``."""
    hours = max(1, int(hours or 12))
    if not signature or not signature.strip():
        return False  # empty signature never matches; don't suppress real reports
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM report_ledger
                WHERE focus = %s AND signature = %s
                  AND "createdAt" >= NOW() - (%s || ' hours')::INTERVAL
                LIMIT 1;
                """,
                (focus, signature, str(int(hours))),
            )
            return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        conn.close()


def record_report(focus: str, signature: str, summary: str = "") -> None:
    if not signature or not signature.strip():
        return  # nothing meaningful to record; avoid collision
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO report_ledger (focus, signature, summary, "createdAt")
                VALUES (%s, %s, %s, NOW());
                """,
                (focus, signature, summary[:2000]),
            )
            conn.commit()
    except Exception as e:
        print(f"⚠️ Error recording report: {e}")
        conn.rollback()
    finally:
        conn.close()


# --- Decision log (Dual-Brain council memory) --------------------------------

def init_decisions_table():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id SERIAL PRIMARY KEY,
                    question TEXT NOT NULL,
                    lead_answer TEXT,
                    second_answer TEXT,
                    verdict TEXT,
                    "createdAt" TIMESTAMP DEFAULT NOW()
                );
                """
            )
            conn.commit()
    except Exception as e:
        print(f"❌ Error creating decisions table: {e}")
    finally:
        conn.close()


def record_decision(question: str, lead_answer: str, second_answer: str, verdict: str):
    """Persist a dual-brain deliberation. Returns the id or None."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO decisions (question, lead_answer, second_answer, verdict, "createdAt")
                VALUES (%s, %s, %s, %s, NOW()) RETURNING id;
                """,
                (question, lead_answer, second_answer, verdict),
            )
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else None
    except Exception as e:
        print(f"❌ Error recording decision: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def get_decisions(limit: int = 10):
    """Return the most recent decisions, newest first."""
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, question, lead_answer, second_answer, verdict, "createdAt"
                FROM decisions ORDER BY "createdAt" DESC LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()
    except Exception as e:
        print(f"⚠️ Error fetching decisions: {e}")
        return []
    finally:
        conn.close()


def get_decision(decision_id: int):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, question, lead_answer, second_answer, verdict, "createdAt"
                FROM decisions WHERE id = %s;
                """,
                (decision_id,),
            )
            return cur.fetchone()
    except Exception as e:
        print(f"⚠️ Error fetching decision {decision_id}: {e}")
        return None
    finally:
        conn.close()


# --- Finance queries + business-state aggregations ---------------------------

def get_expenses(days: int = 30, category: Optional[str] = None, limit: int = 100):
    """Return recent expenses, newest first, optionally filtered by category."""
    days = max(1, int(days or 30))
    limit = max(1, min(int(limit or 100), 500))  # cap at 500 to prevent runaway queries
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if category:
                cur.execute(
                    """
                    SELECT id, date, amount, service_vertical, category, description,
                           payment_mode, added_by, "createdAt"
                    FROM finance_expenses
                    WHERE category = %s
                      AND "createdAt" >= NOW() - (%s || ' days')::INTERVAL
                    ORDER BY "createdAt" DESC LIMIT %s;
                    """,
                    (category, str(int(days)), limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, date, amount, service_vertical, category, description,
                           payment_mode, added_by, "createdAt"
                    FROM finance_expenses
                    WHERE "createdAt" >= NOW() - (%s || ' days')::INTERVAL
                    ORDER BY "createdAt" DESC LIMIT %s;
                    """,
                    (str(int(days)), limit),
                )
            return cur.fetchall()
    except Exception as e:
        print(f"⚠️ Error fetching expenses: {e}")
        return []
    finally:
        conn.close()


def get_expense_summary(days: int = 30) -> dict:
    """Aggregate spend over the last ``days`` days: total + per-vertical + per-category."""
    days = max(1, int(days or 30))
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total,
                       COUNT(*) AS count
                FROM finance_expenses
                WHERE "createdAt" >= NOW() - (%s || ' days')::INTERVAL;
                """,
                (str(int(days)),),
            )
            totals = cur.fetchone() or {}
            cur.execute(
                """
                SELECT service_vertical, COALESCE(SUM(amount), 0) AS total
                FROM finance_expenses
                WHERE "createdAt" >= NOW() - (%s || ' days')::INTERVAL
                GROUP BY service_vertical ORDER BY total DESC;
                """,
                (str(int(days)),),
            )
            by_vertical = cur.fetchall()
            cur.execute(
                """
                SELECT category, COALESCE(SUM(amount), 0) AS total
                FROM finance_expenses
                WHERE "createdAt" >= NOW() - (%s || ' days')::INTERVAL
                GROUP BY category ORDER BY total DESC;
                """,
                (str(int(days)),),
            )
            by_category = cur.fetchall()
        return {
            "days": days,
            "total": float(totals.get("total") or 0),
            "count": int(totals.get("count") or 0),
            "by_vertical": [
                {"vertical": r["service_vertical"], "total": float(r["total"])}
                for r in by_vertical
            ],
            "by_category": [
                {"category": r["category"], "total": float(r["total"])}
                for r in by_category
            ],
        }
    except Exception as e:
        print(f"⚠️ Error computing expense summary: {e}")
        return {"days": days, "total": 0.0, "count": 0, "by_vertical": [], "by_category": []}
    finally:
        conn.close()


def count_active_tickets() -> int:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM devops_tasks WHERE status NOT IN ('Completed', 'Closed', 'Resolved');"
            )
            row = cur.fetchone()
            return int(row[0]) if row and row[0] else 0
    except Exception:
        return 0
    finally:
        conn.close()


def count_overdue_tickets() -> int:
    """Active tickets not updated in >48h (mirrors the scheduler's staleness rule)."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM devops_tasks
                WHERE status NOT IN ('Completed', 'Closed', 'Resolved')
                  AND ("updatedAt" IS NULL
                       OR "updatedAt" < NOW() - INTERVAL '48 hours');
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row and row[0] else 0
    except Exception:
        return 0
    finally:
        conn.close()


def leads_by_status() -> list:
    """Count leads grouped by pipeline status (new/contacted/qualified/won/lost)."""
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT status, COUNT(*) AS count, COALESCE(MAX(score), 0) AS top_score
                FROM leads GROUP BY status ORDER BY count DESC;
                """
            )
            return cur.fetchall()
    except Exception as e:
        print(f"⚠️ Error grouping leads by status: {e}")
        return []
    finally:
        conn.close()


def top_leads(limit: int = 3) -> list:
    """Highest-scoring open leads (not won/lost), for the business snapshot."""
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, contact, source, summary, score, status, "createdAt"
                FROM leads
                WHERE status NOT IN ('won', 'lost')
                ORDER BY score DESC, "createdAt" DESC LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()
    except Exception as e:
        print(f"⚠️ Error fetching top leads: {e}")
        return []
    finally:
        conn.close()


# Ensure the new tables exist at startup (mirrors the leads/knowledge inits).
init_founder_alerts_table()
init_report_ledger_table()
init_decisions_table()
