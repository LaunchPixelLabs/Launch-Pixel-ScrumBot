import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

def get_conn():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except Exception as e:
        print(f"❌ [Database Error] Failed to connect to database: {e}")
        raise e

def _parse_id(ticket_id: str) -> int:
    try:
        return int(ticket_id.split('-')[1]) if '-' in ticket_id else int(ticket_id)
    except:
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
                    "end_date": None
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
