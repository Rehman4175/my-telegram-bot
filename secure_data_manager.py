#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SECURE DATA MANAGER - Private GitHub Repo + Google Sheets Backup
FIXED v2:
  - DiaryStore.add() — proper Sheets sync with visible error logging
  - All stores log EXACTLY what syncs to Sheets and what fails
  - Sheets tab names matched carefully to your existing sheet
  - Data safe in private GitHub repo
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
# CONFIGURATION
# ================================================================
GITHUB_TOKEN      = os.environ.get("GB_TOKEN", "")
PRIVATE_REPO_URL  = os.environ.get("PRIVATE_REPO_URL", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "")
SHEET_KEY         = os.environ.get("SHEET_KEY", "1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")

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
HAS_GSHEETS = False
try:
    import gspread
    HAS_GSHEETS = True
    log.info("✅ gspread library found")
except ImportError:
    log.error("❌ gspread not installed! Run: pip install gspread google-auth")


class GoogleSheetsBackup:
    """
    Writes to BotBackup sheet tabs.
    TAB_MAP keys = internal names
    TAB_MAP values = EXACT tab names in your Google Sheet
    ⚠️  If your sheet tab is named differently, update TAB_MAP below.
    """

    # ─── IMPORTANT: Update these to match your EXACT sheet tab names ───
    TAB_MAP = {
        "Diary":     "Diary",
        "Expenses":  "Expenses",
        "Habits":    "Habits",
        "Water":     "Water Intake",
        "Reminders": "Reminders",
        "Tasks":     "Tasks",
        "Logs":      "Daily_Logs",
    }

    HEADERS = {
        "Diary":     ["Date", "Time", "Text", "Mood"],
        "Expenses":  ["Date", "Time", "Amount", "Description", "Category"],
        "Habits":    ["Date", "Time", "Habit Name", "Streak"],
        "Water":     ["Date", "Time", "ML Added", "Day Total"],
        "Reminders": ["Date", "Set For", "Text", "Action"],
        "Tasks":     ["ID", "Title", "Priority", "Status", "Created", "Done Date"],
        "Logs":      ["Date", "Time", "Type", "Details"],
    }

    def __init__(self):
        self._client   = None
        self._book     = None
        self._ws_cache = {}
        self._connect()

    def _connect(self):
        if not HAS_GSHEETS:
            log.error("❌ gspread not installed — Sheets will not work")
            return
        if not GOOGLE_CREDS_JSON:
            log.error("❌ GOOGLE_CREDS_JSON is empty. Set it as environment variable!")
            return

        try:
            creds_dict = json.loads(GOOGLE_CREDS_JSON)
            log.info(f"✅ GOOGLE_CREDS_JSON parsed — client_email: {creds_dict.get('client_email','?')}")
        except json.JSONDecodeError as e:
            log.error(f"❌ GOOGLE_CREDS_JSON is not valid JSON: {e}")
            return

        authorized = False

        # Try google-auth (preferred)
        try:
            from google.oauth2.service_account import Credentials
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds        = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            self._client = gspread.authorize(creds)
            authorized   = True
            log.info("✅ Auth: google-auth SUCCESS")
        except Exception as e1:
            log.warning(f"google-auth failed ({e1}), trying oauth2client...")

        # Fallback to oauth2client
        if not authorized:
            try:
                from oauth2client.service_account import ServiceAccountCredentials
                scope        = ["https://spreadsheets.google.com/feeds",
                                "https://www.googleapis.com/auth/drive"]
                creds        = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                self._client = gspread.authorize(creds)
                authorized   = True
                log.info("✅ Auth: oauth2client SUCCESS")
            except Exception as e2:
                log.error(f"❌ All auth methods failed: {e2}")
                return

        # Open spreadsheet
        try:
            self._book = self._client.open_by_key(SHEET_KEY)
            log.info(f"✅ Sheet opened: '{self._book.title}'")
            for ws in self._book.worksheets():
                self._ws_cache[ws.title] = ws
            log.info(f"📋 Sheet tabs found: {list(self._ws_cache.keys())}")

            # Warn if expected tabs are missing
            for key, tab_name in self.TAB_MAP.items():
                if tab_name not in self._ws_cache:
                    log.warning(f"⚠️  Tab '{tab_name}' NOT FOUND in sheet — will be auto-created on first write")

        except gspread.exceptions.SpreadsheetNotFound:
            log.error(f"❌ Sheet not found (key={SHEET_KEY}). Check SHEET_KEY env var.")
        except gspread.exceptions.APIError as e:
            if "403" in str(e):
                log.error("❌ Permission denied (403). Share sheet with service account email as Editor!")
            else:
                log.error(f"❌ Sheets API error: {e}")
        except Exception as e:
            log.error(f"❌ Cannot open sheet: {e}")

    @property
    def connected(self):
        return self._book is not None

    def _ws(self, key):
        if not self._book:
            return None
        tab_name = self.TAB_MAP.get(key, key)
        if tab_name in self._ws_cache:
            return self._ws_cache[tab_name]
        try:
            ws = self._book.worksheet(tab_name)
            self._ws_cache[tab_name] = ws
            return ws
        except gspread.exceptions.WorksheetNotFound:
            try:
                headers = self.HEADERS.get(key, ["Date", "Details"])
                ws = self._book.add_worksheet(title=tab_name, rows=2000, cols=len(headers))
                ws.append_row(headers, value_input_option="USER_ENTERED")
                self._ws_cache[tab_name] = ws
                log.info(f"📋 Created new tab: '{tab_name}'")
                return ws
            except Exception as e:
                log.error(f"❌ Cannot create tab '{tab_name}': {e}")
                return None
        except Exception as e:
            log.error(f"❌ Error getting tab '{tab_name}': {e}")
            return None

    def _append(self, key, row):
        if not self._book:
            log.warning(f"⚠️  Sheets NOT connected — skipping sync for [{key}]")
            return False
        ws = self._ws(key)
        if not ws:
            log.error(f"❌ Sheets tab [{key}] not accessible — data NOT synced to Sheets")
            return False
        try:
            ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
            log.info(f"📤 Sheets ✅ [{self.TAB_MAP.get(key,key)}] row added: {row[:3]}")
            return True
        except gspread.exceptions.APIError as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                log.warning("⏳ Sheets rate limit hit, retrying in 65s...")
                time.sleep(65)
                try:
                    ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
                    log.info(f"📤 Sheets ✅ [{key}] row added after retry")
                    return True
                except Exception as e2:
                    log.error(f"❌ Sheets [{key}] retry also failed: {e2}")
            else:
                log.error(f"❌ Sheets [{key}] API error: {e}")
            return False
        except Exception as e:
            log.error(f"❌ Sheets [{key}] unexpected error: {e}")
            return False

    # ── Public sync methods ───────────────────────────────────────
    def diary(self, text, mood="📝"):
        log.info(f"📤 Syncing diary to Sheets: '{text[:50]}'")
        ok = self._append("Diary", [today_str(), now_str(), text, mood])
        if not ok:
            log.error("❌ DIARY DID NOT SYNC TO SHEETS — check connection above")
        return ok

    def expense(self, amount, desc, category="general"):
        log.info(f"📤 Syncing expense to Sheets: ₹{amount} {desc}")
        return self._append("Expenses", [today_str(), now_str(), amount, desc, category])

    def habit(self, name, streak):
        log.info(f"📤 Syncing habit to Sheets: {name} streak={streak}")
        return self._append("Habits", [today_str(), now_str(), name, streak])

    def water(self, ml_added, day_total):
        return self._append("Water", [today_str(), now_str(), ml_added, day_total])

    def reminder(self, text, set_for, action="created"):
        return self._append("Reminders", [today_str(), set_for, text, action])

    def task(self, t):
        return self._append("Tasks", [
            t.get("id",""), t.get("title",""), t.get("priority",""),
            "done" if t.get("done") else "pending",
            t.get("created",""), t.get("done_date","")
        ])

    def log_event(self, type_, details):
        return self._append("Logs", [today_str(), now_str(), type_, details])

    def test_connection(self):
        """Write a test entry to Daily_Logs. Returns True if successful."""
        log.info("🧪 Testing Sheets connection...")
        ok = self.log_event("CONNECTION_TEST", f"Bot started at {now_ist().strftime('%H:%M:%S IST')}")
        if ok:
            log.info("✅ Sheets test PASSED")
        else:
            log.error("❌ Sheets test FAILED")
        return ok


# ================================================================
# GITHUB PRIVATE REPO MANAGER
# ================================================================
class PrivateRepoManager:
    def __init__(self):
        self.data_dir     = DATA_DIR
        self.repo_url     = PRIVATE_REPO_URL
        self.token        = GITHUB_TOKEN
        self.is_connected = False

        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        self._configure_git()

        if not self.repo_url or not self.token:
            log.warning("⚠️ GitHub credentials not set — saving locally only")
            return

        self.is_connected = True
        self._setup_repo()

    def _configure_git(self):
        try:
            subprocess.run(["git", "config", "--global", "user.email", "botdata@bot.local"],
                           capture_output=True)
            subprocess.run(["git", "config", "--global", "user.name",  "BotDataManager"],
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
                r = subprocess.run(["git", "clone", auth_url, self.data_dir],
                                   capture_output=True, text=True)
                if r.returncode == 0:
                    log.info("✅ Private data repo cloned")
                else:
                    log.warning(f"Clone failed: {r.stderr.strip()}")
                    subprocess.run(["git", "-C", self.data_dir, "init"], capture_output=True)
            else:
                r = subprocess.run(
                    ["git", "-C", self.data_dir, "pull", auth_url, "main", "--rebase"],
                    capture_output=True, text=True
                )
                if r.returncode == 0:
                    log.info("✅ Private repo pulled latest")
                else:
                    log.warning(f"Pull warning: {r.stderr.strip()}")
        except Exception as e:
            log.warning(f"Git setup: {e}")

    def _push_changes(self, commit_msg="Auto-save"):
        if not self.is_connected or not self._is_git_repo():
            return
        auth_url = self._get_auth_url()
        if not auth_url:
            return
        try:
            subprocess.run(["git", "-C", self.data_dir, "add", "."],
                           check=True, capture_output=True)
            r = subprocess.run(
                ["git", "-C", self.data_dir, "commit", "-m", commit_msg],
                capture_output=True, text=True
            )
            if "nothing to commit" in (r.stdout + r.stderr):
                return
            p = subprocess.run(
                ["git", "-C", self.data_dir, "push", auth_url, "main"],
                capture_output=True, text=True
            )
            if p.returncode == 0:
                log.info(f"📤 GitHub ✅ committed & pushed: {commit_msg}")
            else:
                log.warning(f"Push failed: {p.stderr.strip()}")
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
            log.info(f"📄 Creating {filename} with defaults")
            self.save_file(filename, default)
            return default
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            log.error(f"❌ Corrupt {filename}! Resetting to defaults.")
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
# STORE BASE
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
            "id": self.store.data["counter"], "title": title,
            "priority": priority, "done": False,
            "created": today_str(), "due": today_str(),
            "tags": "", "done_date": ""
        }
        self.store.data["list"].append(t)
        self.store.save()
        try:
            ok = sheets_backup.task(t)
            log.info(f"📤 Task '{title}' → Sheets: {'✅' if ok else '❌'}")
        except Exception as e:
            log.error(f"Task sheets sync error: {e}")
        return t

    def complete(self, tid):
        for t in self.store.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True
                t["done_date"] = today_str()
                self.store.save()
                try:
                    ok = sheets_backup.task(t)
                    log.info(f"📤 Task #{tid} complete → Sheets: {'✅' if ok else '❌'}")
                except Exception as e:
                    log.error(f"Task complete sheets error: {e}")
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
# DIARY STORE — FIXED
# ================================================================
class DiaryStore:
    def __init__(self):
        self.store = PrivateStore("diary", {"entries": {}})

    def add(self, text, mood="📝"):
        td = today_str()
        ts = now_str()

        # Save to local JSON + GitHub
        self.store.data.setdefault("entries", {}).setdefault(td, [])
        self.store.data["entries"][td].append({"text": text, "mood": mood, "time": ts})
        self.store.save()
        log.info(f"📖 Diary saved locally: '{text[:60]}'")

        # Sync to Google Sheets — with explicit success/failure log
        try:
            ok = sheets_backup.diary(text, mood)
            if ok:
                log.info(f"✅ Diary synced to Sheets successfully")
            else:
                log.error(f"❌ Diary FAILED to sync to Sheets — is Sheets connected?")
        except Exception as e:
            log.error(f"❌ Diary sheets sync EXCEPTION: {e}")

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
            "id": self.store.data["counter"], "name": name,
            "emoji": emoji, "streak": 0, "best_streak": 0,
            "created": today_str(), "target": ""
        }
        self.store.data["list"].append(h)
        self.store.save()
        return h

    def log(self, hid):
        td, yd = today_str(), yesterday_str()
        logs   = self.store.data.get("logs", {})
        logs.setdefault(td, [])
        if hid in logs[td]:
            return False, 0
        logs[td].append(hid)
        streak = 1
        for h in self.store.data.get("list", []):
            if h["id"] == hid:
                h["streak"]      = h.get("streak", 0) + 1 if hid in logs.get(yd, []) else 1
                h["best_streak"] = max(h.get("best_streak", 0), h["streak"])
                streak           = h["streak"]
        self.store.data["logs"] = logs
        self.store.save()
        try:
            name = next((h["name"] for h in self.store.data["list"] if h["id"] == hid), f"#{hid}")
            ok = sheets_backup.habit(name, streak)
            log.info(f"📤 Habit '{name}' → Sheets: {'✅' if ok else '❌'}")
        except Exception as e:
            log.error(f"Habit sheets sync error: {e}")
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
        self.store.data["list"].append({
            "amount": amount, "desc": desc,
            "category": category, "date": today_str(), "time": now_str()
        })
        self.store.save()
        try:
            ok = sheets_backup.expense(amount, desc, category)
            log.info(f"📤 Expense ₹{amount} '{desc}' → Sheets: {'✅' if ok else '❌'}")
        except Exception as e:
            log.error(f"Expense sheets sync error: {e}")

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

    def get_by_date(self, d):
        return [e for e in self.store.data.get("list", []) if e.get("date") == d]


# ================================================================
# GOAL STORE
# ================================================================
class GoalStore:
    def __init__(self):
        self.store = PrivateStore("goals", {"list": [], "counter": 0})

    def add(self, title, deadline=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        g = {
            "id": self.store.data["counter"], "title": title,
            "progress": 0, "done": False, "deadline": deadline,
            "created": today_str(), "milestones": ""
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
            "fire_count":   0
        }
        self.store.data["list"].append(r)
        self.store.save()
        try:
            sheets_backup.reminder(text, remind_at, "created")
        except Exception:
            pass
        return r

    def all_active(self):
        return [r for r in self.store.data.get("list", []) if r.get("active")]

    def get_all(self):
        return self.store.data.get("list", [])

    def get_by_id(self, rid):
        for r in self.store.data.get("list", []):
            if r["id"] == rid:
                return r
        return None

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
        for r in self.store.data["list"]:
            if r["id"] == rid and r.get("active"):
                r["active"]       = False
                r["acknowledged"] = True
                r["remarks"]      = remark
                r["last_fired"]   = now_ist().isoformat()
                self.store.save()
                log.info(f"✅ Reminder #{rid} acknowledged: {remark}")
                try:
                    sheets_backup.reminder(r["text"], r["time"], "acknowledged")
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
        log.info("🔄 Daily reminders reset at midnight")

    def due_now(self):
        """Reminders that have NOT been fired yet and their time matches right now."""
        now_hm = now_ist().strftime("%H:%M")
        return [
            r for r in self.store.data.get("list", [])
            if (r.get("active")
                and not r.get("acknowledged", False)
                and not r.get("fired_today", False)
                and r["time"] == now_hm)
        ]

    def ringing(self):
        """
        Reminders that were fired (fired_today=True) but NOT yet acknowledged.
        These need to re-ring every minute.
        """
        return [
            r for r in self.store.data.get("list", [])
            if (r.get("active")
                and not r.get("acknowledged", False)
                and r.get("fired_today", False))
        ]


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
        try:
            ok = sheets_backup.water(ml, total)
            log.info(f"📤 Water {ml}ml → Sheets: {'✅' if ok else '❌'}")
        except Exception as e:
            log.error(f"Water sheets sync error: {e}")
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
            "id": self.store.data["counter"], "name": name,
            "amount": amount, "due_day": due_day, "active": True,
            "paid_months": [], "created": today_str(),
            "auto_pay": "No", "payment_method": "", "notes": ""
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
            "id": self.store.data["counter"], "title": title,
            "date": event_date, "time": event_time, "location": location,
            "reminder_set": "Yes", "participants": "",
            "notes": notes, "created": today_str()
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
            "timestamp": now_ist().isoformat(), "date": today_str(),
            "role": role, "message": content, "user": user_name
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
# STARTUP TEST — writes one row to Daily_Logs on every restart
# ================================================================
try:
    ok = sheets_backup.test_connection()
    if ok:
        log.info("✅ Sheets startup test PASSED — all data will sync!")
    else:
        log.error("❌ Sheets startup test FAILED — data will save to GitHub only, NOT Sheets")
        log.error("   Fix: Share sheet with service account email as Editor")
        log.error(f"   Sheet Key: {SHEET_KEY}")
except Exception as e:
    log.error(f"Sheets startup test exception: {e}")

# ================================================================
# STATUS SUMMARY
# ================================================================
log.info("=" * 60)
log.info("🔐 SECURE DATA MANAGER READY")
log.info(f"   📁 Data dir : {DATA_DIR}/")
log.info(f"   🔐 GitHub   : {'✅ Connected' if repo_manager.is_connected  else '⚠️  Local only'}")
log.info(f"   📊 Sheets   : {'✅ Connected' if sheets_backup.connected    else '❌ NOT connected'}")
log.info("=" * 60)
