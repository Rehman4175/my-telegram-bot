#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SECURE DATA MANAGER - Private GitHub Repo + Google Sheets Backup
FIXED VERSION: Proper Sheets sync + reliable saves
"""

import os
import json
import logging
import subprocess
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

# ================================================================
# LOGGING
# ================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ================================================================
# CONFIGURATION - Environment Variables
# ================================================================
GITHUB_TOKEN       = os.environ.get("GITHUB_TOKEN", "")
PRIVATE_REPO_URL   = os.environ.get("PRIVATE_REPO_URL", "")
GOOGLE_CREDS_JSON  = os.environ.get("GOOGLE_CREDS_JSON", "")
SHEET_KEY          = os.environ.get("SHEET_KEY", "1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")

DATA_DIR = "bot_private_data"

# ================================================================
# TIMEZONE
# ================================================================
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(timezone.utc).astimezone(IST)

def today_str():
    return now_ist().strftime("%Y-%m-%d")

def now_str():
    return now_ist().strftime("%H:%M")

def yesterday_str():
    return (now_ist() - timedelta(days=1)).strftime("%Y-%m-%d")

# ================================================================
# GOOGLE SHEETS SETUP
# ================================================================
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    HAS_GSHEETS = True
except ImportError:
    HAS_GSHEETS = False
    log.warning("⚠️ gspread not installed — pip install gspread oauth2client")

class GoogleSheetsBackup:
    def __init__(self):
        self.client = None
        self.sheet  = None
        self._connect()

    def _connect(self):
        if not HAS_GSHEETS:
            log.warning("⚠️ Google Sheets libs missing")
            return
        if not GOOGLE_CREDS_JSON:
            log.warning("⚠️ GOOGLE_CREDS_JSON env var not set")
            return
        try:
            creds_dict = json.loads(GOOGLE_CREDS_JSON)
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            from oauth2client.service_account import ServiceAccountCredentials
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            self.client = gspread.authorize(creds)
            self.sheet  = self.client.open_by_key(SHEET_KEY)
            log.info("✅ Google Sheets connected")
        except Exception as e:
            log.error(f"❌ Sheets connection error: {e}")

    def _get_or_create_ws(self, name, headers):
        """Return worksheet by name, creating it with headers if absent."""
        if not self.sheet:
            return None
        try:
            ws = self.sheet.worksheet(name)
            return ws
        except gspread.exceptions.WorksheetNotFound:
            try:
                ws = self.sheet.add_worksheet(title=name, rows=1000, cols=len(headers))
                ws.append_row(headers, value_input_option="USER_ENTERED")
                log.info(f"📋 Created worksheet: {name}")
                return ws
            except Exception as e:
                log.error(f"❌ Create worksheet '{name}' error: {e}")
                return None
        except Exception as e:
            log.error(f"❌ Get worksheet '{name}' error: {e}")
            return None

    # ── DIARY ──────────────────────────────────────────────────────
    def backup_diary_entry(self, date_str, time_str, text, mood="📝"):
        ws = self._get_or_create_ws("Diary", ["Date", "Time", "Text", "Mood"])
        if not ws:
            return False
        try:
            ws.append_row([date_str, time_str, text, mood], value_input_option="USER_ENTERED")
            log.info(f"📤 Diary entry synced to Sheets")
            return True
        except Exception as e:
            log.error(f"Diary Sheets error: {e}")
            return False

    # ── EXPENSE ────────────────────────────────────────────────────
    def backup_expense(self, date_str, time_str, amount, desc, category="general"):
        ws = self._get_or_create_ws("Expenses", ["Date", "Time", "Amount", "Description", "Category"])
        if not ws:
            return False
        try:
            ws.append_row([date_str, time_str, amount, desc, category], value_input_option="USER_ENTERED")
            log.info(f"📤 Expense synced to Sheets: ₹{amount} {desc}")
            return True
        except Exception as e:
            log.error(f"Expense Sheets error: {e}")
            return False

    # ── TASK ───────────────────────────────────────────────────────
    def backup_task(self, task):
        ws = self._get_or_create_ws("Tasks", ["ID", "Title", "Priority", "Done", "Created", "Done Date"])
        if not ws:
            return False
        try:
            ws.append_row([
                task.get("id"), task.get("title"), task.get("priority"),
                str(task.get("done")), task.get("created"), task.get("done_date", "")
            ], value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            log.error(f"Task Sheets error: {e}")
            return False

    # ── HABIT LOG ──────────────────────────────────────────────────
    def backup_habit_log(self, habit_name, streak):
        ws = self._get_or_create_ws("HabitLogs", ["Date", "Time", "Habit", "Streak"])
        if not ws:
            return False
        try:
            ws.append_row([today_str(), now_str(), habit_name, streak], value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            log.error(f"Habit Sheets error: {e}")
            return False

    # ── WATER ──────────────────────────────────────────────────────
    def backup_water(self, ml, total):
        ws = self._get_or_create_ws("Water", ["Date", "Time", "ML Added", "Day Total"])
        if not ws:
            return False
        try:
            ws.append_row([today_str(), now_str(), ml, total], value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            log.error(f"Water Sheets error: {e}")
            return False

    # ── REMINDER ───────────────────────────────────────────────────
    def backup_reminder(self, text, time_str, action="created"):
        ws = self._get_or_create_ws("Reminders", ["Date", "Time", "Reminder", "Action"])
        if not ws:
            return False
        try:
            ws.append_row([today_str(), time_str, text, action], value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            log.error(f"Reminder Sheets error: {e}")
            return False

    @property
    def connected(self):
        return self.sheet is not None


# ================================================================
# GITHUB PRIVATE REPO MANAGER
# ================================================================
class PrivateRepoManager:
    def __init__(self):
        self.data_dir    = DATA_DIR
        self.repo_url    = PRIVATE_REPO_URL
        self.token       = GITHUB_TOKEN
        self.is_connected = False

        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        self._configure_git()

        if not self.repo_url or not self.token:
            log.warning("⚠️ GitHub credentials not set — local only")
            return

        self.is_connected = True
        self._setup_repo()

    def _configure_git(self):
        try:
            subprocess.run(["git", "config", "--global", "user.email", "bot@bot.com"],
                           capture_output=True)
            subprocess.run(["git", "config", "--global", "user.name",  "BotData"],
                           capture_output=True)
        except Exception:
            pass

    def _get_auth_url(self):
        if not self.repo_url:
            return None
        return self.repo_url.replace("https://", f"https://{self.token}@")

    def _is_git_repo(self):
        return (Path(self.data_dir) / ".git").exists()

    def _setup_repo(self):
        auth_url = self._get_auth_url()
        if not auth_url:
            return
        try:
            if not self._is_git_repo():
                result = subprocess.run(
                    ["git", "clone", auth_url, self.data_dir],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    log.info("✅ Cloned private repository")
                else:
                    log.warning(f"Clone failed: {result.stderr}")
                    subprocess.run(["git", "-C", self.data_dir, "init"], capture_output=True)
            else:
                result = subprocess.run(
                    ["git", "-C", self.data_dir, "pull", auth_url, "main"],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    log.info("✅ Pulled latest from private repo")
                else:
                    log.warning(f"Pull warning: {result.stderr}")
        except Exception as e:
            log.warning(f"Git setup error: {e}")

    def _push_changes(self, commit_message="Auto-save"):
        if not self.is_connected or not self._is_git_repo():
            return
        auth_url = self._get_auth_url()
        if not auth_url:
            return
        try:
            subprocess.run(["git", "-C", self.data_dir, "add", "."],
                           check=True, capture_output=True)
            result = subprocess.run(
                ["git", "-C", self.data_dir, "commit", "-m", commit_message],
                capture_output=True, text=True
            )
            if "nothing to commit" in result.stdout + result.stderr:
                return  # no changes, skip push
            subprocess.run(
                ["git", "-C", self.data_dir, "push", auth_url, "main"],
                check=True, capture_output=True
            )
            log.info(f"📤 Pushed to GitHub: {commit_message}")
        except subprocess.CalledProcessError as e:
            log.warning(f"Push failed: {e.stderr if hasattr(e, 'stderr') else e}")
        except Exception as e:
            log.warning(f"Push error: {e}")

    def save_file(self, filename, data):
        filepath = Path(self.data_dir) / filename
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._push_changes(f"Update {filename}")
            return True
        except Exception as e:
            log.error(f"Save failed ({filename}): {e}")
            return False

    def load_file(self, filename, default=None):
        if default is None:
            default = {}
        filepath = Path(self.data_dir) / filename
        if not filepath.exists():
            self.save_file(filename, default)
            return default
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            log.error(f"Corrupt JSON in {filename}, resetting")
            self.save_file(filename, default)
            return default
        except Exception as e:
            log.error(f"Load failed ({filename}): {e}")
            return default


# ================================================================
# INITIALIZE GLOBAL OBJECTS
# ================================================================
repo_manager  = PrivateRepoManager()
sheets_backup = GoogleSheetsBackup()


# ================================================================
# STORE BASE CLASS
# ================================================================
class PrivateStore:
    def __init__(self, name, default=None):
        self.name    = name
        self.default = default if default is not None else {}
        self.data    = repo_manager.load_file(name, self.default)

    def save(self):
        repo_manager.save_file(self.name, self.data)


# ================================================================
# MEMORY STORE
# ================================================================
class MemoryStore:
    def __init__(self):
        self.store = PrivateStore("memory", {"facts": []})

    def add_fact(self, text):
        facts = self.store.data.get("facts", [])
        facts.append({"f": text, "d": today_str()})
        self.store.data["facts"] = facts[-200:]
        self.store.save()

    def get_all_facts(self):
        return self.store.data.get("facts", [])


# ================================================================
# TASK STORE
# ================================================================
class TaskStore:
    def __init__(self):
        self.store = PrivateStore("tasks", {"list": [], "counter": 0})

    def add(self, title, priority="medium"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        t = {
            "id":        self.store.data["counter"],
            "title":     title,
            "priority":  priority,
            "done":      False,
            "created":   today_str(),
            "due":       today_str(),
            "tags":      "",
            "done_date": ""
        }
        self.store.data["list"].append(t)
        self.store.save()
        # Sheets backup
        try:
            sheets_backup.backup_task(t)
        except Exception as e:
            log.warning(f"Task sheets backup failed: {e}")
        return t

    def complete(self, tid):
        for t in self.store.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"]      = True
                t["done_date"] = today_str()
                self.store.save()
                try:
                    sheets_backup.backup_task(t)
                except Exception:
                    pass
                return t
        return None

    def delete(self, tid):
        self.store.data["list"] = [t for t in self.store.data["list"] if t["id"] != tid]
        self.store.save()

    def pending(self):
        return [t for t in self.store.data.get("list", []) if not t["done"]]

    def done_on(self, d):
        return [t for t in self.store.data.get("list", [])
                if t["done"] and t.get("done_date") == d]

    def today_pending(self):
        return [t for t in self.pending() if t.get("due", "") <= today_str()]

    def all_tasks(self):
        return self.store.data.get("list", [])

    def completed_tasks(self):
        return [t for t in self.all_tasks() if t["done"]]


# ================================================================
# DIARY STORE
# ================================================================
class DiaryStore:
    def __init__(self):
        self.store = PrivateStore("diary", {"entries": {}})

    def add(self, text, mood="📝"):
        td = today_str()
        ts = now_str()
        self.store.data.setdefault("entries", {}).setdefault(td, [])
        entry = {"text": text, "mood": mood, "time": ts}
        self.store.data["entries"][td].append(entry)
        self.store.save()
        log.info(f"📖 Diary saved locally: {text[:50]}")
        # Sheets backup — immediately for this entry
        try:
            ok = sheets_backup.backup_diary_entry(td, ts, text, mood)
            if ok:
                log.info("📤 Diary entry synced to Google Sheets ✅")
        except Exception as e:
            log.warning(f"Diary Sheets backup failed: {e}")

    def get(self, d):
        return self.store.data.get("entries", {}).get(d, [])

    def get_all_entries(self):
        return self.store.data.get("entries", {})


# ================================================================
# HABIT STORE
# ================================================================
class HabitStore:
    def __init__(self):
        self.store = PrivateStore("habits", {"list": [], "logs": {}, "counter": 0})

    def add(self, name, emoji="✅"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        h = {
            "id":          self.store.data["counter"],
            "name":        name,
            "emoji":       emoji,
            "streak":      0,
            "best_streak": 0,
            "created":     today_str(),
            "target":      ""
        }
        self.store.data["list"].append(h)
        self.store.save()
        return h

    def log(self, hid):
        td, yd = today_str(), yesterday_str()
        logs = self.store.data.get("logs", {})
        logs.setdefault(td, [])
        if hid in logs[td]:
            return False, 0
        logs[td].append(hid)
        streak = 1
        for h in self.store.data.get("list", []):
            if h["id"] == hid:
                yd_logs  = logs.get(yd, [])
                h["streak"] = h.get("streak", 0) + 1 if hid in yd_logs else 1
                h["best_streak"] = max(h.get("best_streak", 0), h["streak"])
                streak = h["streak"]
        self.store.data["logs"] = logs
        self.store.save()
        # Sheets backup
        try:
            name = next((h["name"] for h in self.store.data["list"] if h["id"] == hid), f"#{hid}")
            sheets_backup.backup_habit_log(name, streak)
        except Exception:
            pass
        return True, streak

    def log_by_name(self, keyword):
        keyword = keyword.lower()
        for h in self.store.data.get("list", []):
            if keyword in h["name"].lower():
                ok, streak = self.log(h["id"])
                return ok, streak, h
        return False, 0, None

    def today_status(self):
        done_ids = self.store.data.get("logs", {}).get(today_str(), [])
        all_h    = self.all()
        return (
            [h for h in all_h if h["id"] in done_ids],
            [h for h in all_h if h["id"] not in done_ids]
        )

    def all(self):
        return self.store.data.get("list", [])

    def delete(self, hid):
        self.store.data["list"] = [h for h in self.store.data["list"] if h["id"] != hid]
        self.store.save()


# ================================================================
# EXPENSE STORE
# ================================================================
class ExpenseStore:
    def __init__(self):
        self.store = PrivateStore("expenses", {"list": [], "budget": 0})

    def add(self, amount, desc, category="general"):
        td = today_str()
        ts = now_str()
        self.store.data["list"].append({
            "amount": amount, "desc": desc,
            "category": category, "date": td, "time": ts
        })
        self.store.save()
        # Sheets backup
        try:
            sheets_backup.backup_expense(td, ts, amount, desc, category)
        except Exception as e:
            log.warning(f"Expense Sheets backup failed: {e}")

    def set_budget(self, amount):
        self.store.data["budget"] = amount
        self.store.save()

    def today_total(self):
        return sum(e["amount"] for e in self.store.data.get("list", [])
                   if e.get("date") == today_str())

    def month_total(self):
        m = today_str()[:7]
        return sum(e["amount"] for e in self.store.data.get("list", [])
                   if e.get("date", "")[:7] == m)

    def budget_left(self):
        b = self.store.data.get("budget", 0)
        return b - self.month_total() if b else None

    def get_by_date(self, target_date):
        return [e for e in self.store.data.get("list", [])
                if e.get("date") == target_date]


# ================================================================
# GOAL STORE
# ================================================================
class GoalStore:
    def __init__(self):
        self.store = PrivateStore("goals", {"list": [], "counter": 0})

    def add(self, title, deadline=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        g = {
            "id":         self.store.data["counter"],
            "title":      title,
            "progress":   0,
            "done":       False,
            "deadline":   deadline,
            "created":    today_str(),
            "milestones": ""
        }
        self.store.data["list"].append(g)
        self.store.save()
        return g

    def update_progress(self, gid, pct):
        for g in self.store.data["list"]:
            if g["id"] == gid:
                g["progress"] = min(100, max(0, pct))
                if g["progress"] == 100:
                    g["done"] = True
                self.store.save()
                return g
        return None

    def active(self):
        return [g for g in self.store.data.get("list", []) if not g["done"]]

    def completed(self):
        return [g for g in self.store.data.get("list", []) if g["done"]]


# ================================================================
# REMINDER STORE
# ================================================================
class ReminderStore:
    def __init__(self):
        self.store = PrivateStore("reminders", {"list": [], "counter": 0})

    def add(self, chat_id, text, remind_at, repeat="once"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        r = {
            "id":           self.store.data["counter"],
            "chat_id":      str(chat_id),
            "text":         text,
            "time":         remind_at,
            "repeat":       repeat,
            "date":         today_str(),
            "active":       True,
            "fired_today":  False,
            "last_fired":   "",
            "remarks":      "",
            "acknowledged": False,
            "fire_count":   0          # NEW: how many times fired
        }
        self.store.data["list"].append(r)
        self.store.save()
        # Sheets backup
        try:
            sheets_backup.backup_reminder(text, remind_at, "created")
        except Exception:
            pass
        return r

    def all_active(self):
        return [r for r in self.store.data.get("list", []) if r.get("active")]

    def get_all(self):
        return self.store.data.get("list", [])

    def delete(self, rid):
        self.store.data["list"] = [r for r in self.store.data["list"] if r["id"] != rid]
        self.store.save()

    def mark_fired(self, rid):
        for r in self.store.data["list"]:
            if r["id"] == rid:
                r["fired_today"] = True
                r["fire_count"]  = r.get("fire_count", 0) + 1
                r["last_fired"]  = now_ist().isoformat()
                self.store.save()
                break

    def acknowledge(self, rid, remark="OK pressed"):
        """Stops the alarm completely."""
        for r in self.store.data["list"]:
            if r["id"] == rid and r.get("active"):
                r["active"]       = False
                r["acknowledged"] = True
                r["remarks"]      = remark
                r["last_fired"]   = now_ist().isoformat()
                self.store.save()
                log.info(f"✅ Reminder #{rid} acknowledged and stopped")
                try:
                    sheets_backup.backup_reminder(r["text"], r["time"], "acknowledged")
                except Exception:
                    pass
                return True
        return False

    def reset_daily(self):
        changed = False
        for r in self.store.data["list"]:
            if r.get("repeat") in ("daily", "weekly") and r.get("active"):
                r["fired_today"] = False
                r["fire_count"]  = 0
                changed = True
        if changed:
            self.store.save()
        log.info("🔄 Reminders reset for new day")

    def due_now(self):
        now_hm = now_ist().strftime("%H:%M")
        return [
            r for r in self.store.data.get("list", [])
            if (
                r.get("active")
                and not r.get("acknowledged", False)
                and not r.get("fired_today", False)
                and r["time"] == now_hm
            )
        ]

    def get_by_id(self, rid):
        for r in self.store.data.get("list", []):
            if r["id"] == rid:
                return r
        return None


# ================================================================
# WATER STORE
# ================================================================
class WaterStore:
    def __init__(self):
        self.store = PrivateStore("water", {"logs": {}, "goal_ml": 2000})

    def add(self, ml=250):
        td = today_str()
        self.store.data.setdefault("logs", {}).setdefault(td, [])
        self.store.data["logs"][td].append({"ml": ml, "time": now_str()})
        self.store.save()
        total = self.today_total()
        # Sheets backup
        try:
            sheets_backup.backup_water(ml, total)
        except Exception:
            pass
        return total

    def today_total(self):
        return sum(e["ml"] for e in self.store.data.get("logs", {}).get(today_str(), []))

    def goal(self):
        return self.store.data.get("goal_ml", 2000)

    def set_goal(self, ml):
        self.store.data["goal_ml"] = ml
        self.store.save()


# ================================================================
# BILL STORE
# ================================================================
class BillStore:
    def __init__(self):
        self.store = PrivateStore("bills", {"list": [], "counter": 0})

    def add(self, name, amount, due_day):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        b = {
            "id":              self.store.data["counter"],
            "name":            name,
            "amount":          amount,
            "due_day":         due_day,
            "active":          True,
            "paid_months":     [],
            "created":         today_str(),
            "auto_pay":        "No",
            "payment_method":  "",
            "notes":           ""
        }
        self.store.data["list"].append(b)
        self.store.save()
        return b

    def all_active(self):
        return [b for b in self.store.data.get("list", []) if b.get("active")]

    def mark_paid(self, bid):
        ym = today_str()[:7]
        for b in self.store.data["list"]:
            if b["id"] == bid and ym not in b.get("paid_months", []):
                b["paid_months"].append(ym)
                self.store.save()
                return True
        return False

    def is_paid_this_month(self, bid):
        ym = today_str()[:7]
        for b in self.store.data["list"]:
            if b["id"] == bid:
                return ym in b.get("paid_months", [])
        return False


# ================================================================
# CALENDAR STORE
# ================================================================
class CalendarStore:
    def __init__(self):
        self.store = PrivateStore("calendar", {"events": [], "counter": 0})

    def add(self, title, event_date, event_time="", location="", notes=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        e = {
            "id":           self.store.data["counter"],
            "title":        title,
            "date":         event_date,
            "time":         event_time,
            "location":     location,
            "reminder_set": "Yes",
            "participants": "",
            "notes":        notes,
            "created":      today_str()
        }
        self.store.data["events"].append(e)
        self.store.save()
        return e

    def delete(self, eid):
        self.store.data["events"] = [e for e in self.store.data["events"] if e["id"] != eid]
        self.store.save()

    def upcoming(self, days=7):
        today_d = now_ist().date()
        cutoff  = today_d + timedelta(days=days)
        return sorted(
            [e for e in self.store.data.get("events", [])
             if today_d <= date.fromisoformat(e["date"]) <= cutoff],
            key=lambda x: x["date"]
        )

    def today_events(self):
        return [e for e in self.store.data.get("events", []) if e["date"] == today_str()]


# ================================================================
# CHAT HISTORY STORE
# ================================================================
class ChatHistoryStore:
    def __init__(self):
        self.store = PrivateStore("chat_history", {"history": []})

    def add(self, role, content, user_name=""):
        self.store.data["history"].append({
            "timestamp": now_ist().isoformat(),
            "date":      today_str(),
            "role":      role,
            "message":   content,
            "user":      user_name
        })
        self.store.data["history"] = self.store.data["history"][-500:]
        self.store.save()

    def get_all(self):
        return self.store.data.get("history", [])

    def get_recent(self, n=10):
        return self.store.data.get("history", [])[-n:]

    def clear(self):
        count = len(self.store.data["history"])
        self.store.data["history"] = []
        self.store.save()
        return count


# ================================================================
# INITIALIZE ALL STORES
# ================================================================
memory    = MemoryStore()
tasks     = TaskStore()
diary     = DiaryStore()
habits    = HabitStore()
expenses  = ExpenseStore()
goals     = GoalStore()
reminders = ReminderStore()
water     = WaterStore()
bills     = BillStore()
calendar  = CalendarStore()
chat_hist = ChatHistoryStore()

# ================================================================
# STATUS
# ================================================================
log.info("=" * 60)
log.info("🔐 SECURE DATA MANAGER INITIALIZED")
log.info(f"   Data stored in: '{DATA_DIR}/'")
log.info(f"   GitHub : {'✅ Connected' if repo_manager.is_connected  else '⚠️ Local only'}")
log.info(f"   Sheets : {'✅ Connected' if sheets_backup.connected     else '⚠️ Not connected'}")
log.info("=" * 60)
