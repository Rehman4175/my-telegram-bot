#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SECURE DATA MANAGER — FIXED VERSION
Changes:
  - Daily_Logs tab REMOVED — chat history now goes to "Miscellaneous" tab
  - Habits → Google Sheet "Habits" tab properly synced
  - Goals  → Google Sheet "Goals" tab properly synced
  - Diary  → read operations (show/view) do NOT write to sheet
  - TAB_MAP updated accordingly
"""

import os
import json
import logging
import subprocess
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

GITHUB_TOKEN      = os.environ.get("GB_TOKEN", "")
PRIVATE_REPO_URL  = os.environ.get("PRIVATE_REPO_URL", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "")
SHEET_KEY         = os.environ.get("SHEET_KEY", "1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")

DATA_DIR = "bot_private_data"

IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(timezone.utc).astimezone(IST)

def today_str():
    return now_ist().strftime("%Y-%m-%d")

def now_str():
    return now_ist().strftime("%H:%M")

def yesterday_str():
    return (now_ist() - timedelta(days=1)).strftime("%Y-%m-%d")

HAS_GSHEETS = False
try:
    import gspread
    HAS_GSHEETS = True
    log.info("gspread found")
except ImportError:
    log.error("gspread not installed!")


class GoogleSheetsBackup:
    # EXACT tab names as they appear in your Google Sheet
    TAB_MAP = {
        "Reminders": "Reminders",
        "Tasks":     "Tasks",
        "Memory":    "Memory / Important Notes",
        "Goals":     "Goals",
        "Calendar":  "Calendar Events",
        "Bills":     "Bills & Subscriptions",
        "Expenses":  "Expenses",
        "Habits":    "Habits",
        "Water":     "Water Intake",
        "Misc":      "Miscellaneous",      # ← Daily_Logs + chat history yahan
        "Diary":     "Diary",
    }

    HEADERS = {
        "Reminders": ["ID", "Time", "Text", "Repeat", "Status", "Created Date", "Chat ID", "Last Fired", "Acknowledged", "Remarks"],
        "Tasks":     ["ID", "Title", "Priority", "Status", "Created", "Done Date"],
        "Memory":    ["Date", "Time", "Fact"],
        "Goals":     ["ID", "Title", "Progress", "Status", "Deadline", "Created"],
        "Calendar":  ["ID", "Title", "Date", "Time", "Location", "Notes", "Type", "Created"],
        "Bills":     ["ID", "Name", "Amount", "Due Day", "Status", "Auto Pay", "Payment Method", "Notes", "Created"],
        "Expenses":  ["Date", "Time", "Amount", "Description", "Category"],
        "Habits":    ["Date", "Time", "Habit Name", "Streak"],
        "Water":     ["Date", "Time", "ML Added", "Day Total"],
        "Misc":      ["Timestamp", "Date", "Role", "User", "Message"],  # ← Miscellaneous headers
        "Diary":     ["Date", "Time", "Text", "Mood"],
    }

    def __init__(self):
        self._client   = None
        self._book     = None
        self._ws_cache = {}
        self._connect()

    def _connect(self):
        if not HAS_GSHEETS:
            return
        if not GOOGLE_CREDS_JSON:
            log.error("GOOGLE_CREDS_JSON empty")
            return
        try:
            creds_dict = json.loads(GOOGLE_CREDS_JSON)
        except json.JSONDecodeError as e:
            log.error(f"GOOGLE_CREDS_JSON invalid: {e}")
            return

        authorized = False
        try:
            from google.oauth2.service_account import Credentials
            creds = Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/drive"]
            )
            self._client = gspread.authorize(creds)
            authorized = True
        except Exception as e1:
            log.warning(f"google-auth failed: {e1}")

        if not authorized:
            try:
                from oauth2client.service_account import ServiceAccountCredentials
                creds = ServiceAccountCredentials.from_json_keyfile_dict(
                    creds_dict,
                    ["https://spreadsheets.google.com/feeds",
                     "https://www.googleapis.com/auth/drive"]
                )
                self._client = gspread.authorize(creds)
                authorized = True
            except Exception as e2:
                log.error(f"All auth failed: {e2}")
                return

        try:
            self._book = self._client.open_by_key(SHEET_KEY)
            for ws in self._book.worksheets():
                self._ws_cache[ws.title] = ws
            log.info(f"Sheet tabs: {list(self._ws_cache.keys())}")
        except Exception as e:
            log.error(f"Cannot open sheet: {e}")

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
                log.info(f"Created tab: '{tab_name}'")
                return ws
            except Exception as e:
                log.error(f"Cannot create tab '{tab_name}': {e}")
                return None
        except Exception as e:
            log.error(f"Error tab '{tab_name}': {e}")
            return None

    def _append(self, key, row):
        if not self._book:
            return False
        ws = self._ws(key)
        if not ws:
            return False
        try:
            ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
            log.info(f"[{self.TAB_MAP.get(key, key)}] row appended")
            return True
        except gspread.exceptions.APIError as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                log.warning("Rate limit, retry 65s...")
                time.sleep(65)
                try:
                    ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
                    return True
                except Exception as e2:
                    log.error(f"Retry failed [{key}]: {e2}")
            else:
                log.error(f"API error [{key}]: {e}")
            return False
        except Exception as e:
            log.error(f"Append error [{key}]: {e}")
            return False

    def delete_row_by_value(self, key, col_index, match_value):
        if not self._book:
            return False
        ws = self._ws(key)
        if not ws:
            return False
        try:
            all_values = ws.get_all_values()
            for i, row in enumerate(all_values):
                if i == 0:
                    continue
                if len(row) >= col_index and str(row[col_index - 1]).strip() == str(match_value).strip():
                    ws.delete_rows(i + 1)
                    log.info(f"Deleted row [{key}] col{col_index}='{match_value}'")
                    return True
            return False
        except Exception as e:
            log.error(f"delete_row [{key}]: {e}")
            return False

    def update_row_by_value(self, key, col_index, match_value, new_row):
        if not self._book:
            return False
        ws = self._ws(key)
        if not ws:
            return False
        try:
            all_values = ws.get_all_values()
            for i, row in enumerate(all_values):
                if i == 0:
                    continue
                if len(row) >= col_index and str(row[col_index - 1]).strip() == str(match_value).strip():
                    row_num = i + 1
                    for j, val in enumerate(new_row):
                        ws.update_cell(row_num, j + 1, str(val))
                    log.info(f"Updated row [{key}] col{col_index}='{match_value}'")
                    return True
            return False
        except Exception as e:
            log.error(f"update_row [{key}]: {e}")
            return False

    # ── Public sync methods ───────────────────────────────────────

    def reminder(self, r, action="created"):
        row = [
            r.get("id", ""),
            r.get("time", ""),
            r.get("text", ""),
            r.get("repeat", "once"),
            "Active" if r.get("active") else "Inactive",
            r.get("date", today_str()),
            r.get("chat_id", ""),
            r.get("last_fired", ""),
            str(r.get("acknowledged", False)),
            r.get("remarks", ""),
        ]
        if action == "created":
            return self._append("Reminders", row)
        else:
            ok = self.update_row_by_value("Reminders", 1, str(r.get("id", "")), row)
            return ok if ok else self._append("Reminders", row)

    def task(self, t):
        return self._append("Tasks", [
            t.get("id", ""), t.get("title", ""), t.get("priority", "medium"),
            "Done" if t.get("done") else "Pending",
            t.get("created", ""), t.get("done_date", "")
        ])

    def task_update(self, t):
        row = [t.get("id", ""), t.get("title", ""), t.get("priority", "medium"),
               "Done" if t.get("done") else "Pending", t.get("created", ""), t.get("done_date", "")]
        ok = self.update_row_by_value("Tasks", 1, str(t.get("id", "")), row)
        return ok if ok else self._append("Tasks", row)

    def memory(self, text):
        return self._append("Memory", [today_str(), now_str(), text])

    def goal(self, g):
        """Goals tab mein sync — FIXED"""
        return self._append("Goals", [
            g.get("id", ""),
            g.get("title", ""),
            g.get("progress", 0),
            "Done" if g.get("done") else "Active",
            g.get("deadline", ""),
            g.get("created", "")
        ])

    def goal_update(self, g):
        """Goal progress update karo sheet mein"""
        row = [
            g.get("id", ""),
            g.get("title", ""),
            g.get("progress", 0),
            "Done" if g.get("done") else "Active",
            g.get("deadline", ""),
            g.get("created", "")
        ]
        ok = self.update_row_by_value("Goals", 1, str(g.get("id", "")), row)
        return ok if ok else self._append("Goals", row)

    def calendar_event(self, e):
        return self._append("Calendar", [
            e.get("id", ""), e.get("title", ""), e.get("date", ""),
            e.get("time", ""), e.get("location", ""), e.get("notes", ""),
            e.get("type", "event"), e.get("created", "")
        ])

    def bill(self, b, action="created"):
        row = [
            b.get("id", ""), b.get("name", ""), b.get("amount", ""),
            b.get("due_day", ""),
            "Active" if b.get("active") else "Inactive",
            b.get("auto_pay", "No"), b.get("payment_method", ""),
            b.get("notes", ""), b.get("created", "")
        ]
        if action == "created":
            return self._append("Bills", row)
        else:
            ok = self.update_row_by_value("Bills", 1, str(b.get("id", "")), row)
            return ok if ok else self._append("Bills", row)

    def expense(self, amount, desc, category="general"):
        return self._append("Expenses", [today_str(), now_str(), amount, desc, category])

    def habit(self, name, streak):
        """Habits tab mein sync — FIXED: tab naam aur columns correct hain"""
        return self._append("Habits", [today_str(), now_str(), name, streak])

    def water(self, ml_added, day_total):
        return self._append("Water", [today_str(), now_str(), ml_added, day_total])

    def log_event(self, role, user, message):
        """Chat history → Miscellaneous tab (Daily_Logs nahi)"""
        return self._append("Misc", [now_ist().isoformat(), today_str(), role, user, message])

    def diary_write(self, text, mood="📝"):
        """
        ONLY call this when WRITING a diary entry.
        Reading/showing diary → is function ko call mat karo.
        """
        return self._append("Diary", [today_str(), now_str(), text, mood])

    # NOTE: diary() alias hata diya — ab sirf diary_write() hai
    # Bot code mein sheets_backup.diary() ki jagah sheets_backup.diary_write() use karo

    def test_connection(self):
        ok = self.log_event("system", "Bot", f"Started {now_ist().strftime('%H:%M IST')}")
        log.info("Sheets test PASSED" if ok else "Sheets test FAILED")
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
            log.warning("GitHub creds not set — local only")
            return
        self.is_connected = True
        self._setup_repo()

    def _configure_git(self):
        try:
            subprocess.run(["git", "config", "--global", "user.email", "botdata@bot.local"], capture_output=True)
            subprocess.run(["git", "config", "--global", "user.name", "BotDataManager"], capture_output=True)
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
                r = subprocess.run(["git", "clone", auth_url, self.data_dir], capture_output=True, text=True)
                if r.returncode != 0:
                    subprocess.run(["git", "-C", self.data_dir, "init"], capture_output=True)
            else:
                subprocess.run(["git", "-C", self.data_dir, "pull", auth_url, "main", "--rebase"],
                               capture_output=True, text=True)
        except Exception as e:
            log.warning(f"Git setup: {e}")

    def _push_changes(self, commit_msg="Auto-save"):
        if not self.is_connected or not self._is_git_repo():
            return
        auth_url = self._get_auth_url()
        if not auth_url:
            return
        try:
            subprocess.run(["git", "-C", self.data_dir, "add", "."], check=True, capture_output=True)
            r = subprocess.run(["git", "-C", self.data_dir, "commit", "-m", commit_msg],
                               capture_output=True, text=True)
            if "nothing to commit" in (r.stdout + r.stderr):
                return
            subprocess.run(["git", "-C", self.data_dir, "push", auth_url, "main"],
                           capture_output=True, text=True)
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
            log.error(f"Corrupt {filename}! Resetting.")
            self.save_file(filename, default)
            return default
        except Exception as e:
            log.error(f"Load failed ({filename}): {e}")
            return default


# ================================================================
# GLOBAL OBJECTS
# ================================================================
repo_manager  = PrivateRepoManager()
sheets_backup = GoogleSheetsBackup()


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

    def add(self, text):
        """add() method — bot_fixed.py se call hota hai"""
        return self.add_fact(text)

    def add_fact(self, text):
        facts = self.store.data.get("facts", [])
        facts.append({"f": text, "d": today_str()})
        self.store.data["facts"] = facts[-200:]
        self.store.save()
        try:
            sheets_backup.memory(text)
        except Exception:
            pass

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
            sheets_backup.task(t)
        except Exception:
            pass
        return t

    def complete(self, tid):
        for t in self.store.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"]      = True
                t["done_date"] = today_str()
                self.store.save()
                try:
                    sheets_backup.task_update(t)
                except Exception:
                    pass
                return t
        return None

    def delete(self, tid):
        self.store.data["list"] = [t for t in self.store.data["list"] if t["id"] != tid]
        self.store.save()
        try:
            sheets_backup.delete_row_by_value("Tasks", 1, str(tid))
        except Exception:
            pass

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
# IMPORTANT: add() → sheet mein likhta hai
#            get() / get_all_entries() → sirf read, sheet mein kuch nahi
# ================================================================
class DiaryStore:
    def __init__(self):
        self.store = PrivateStore("diary", {"entries": {}})

    def add(self, text, mood="📝"):
        """WRITE diary entry — local + sheet dono mein save"""
        td = today_str()
        self.store.data.setdefault("entries", {}).setdefault(td, [])
        self.store.data["entries"][td].append({"text": text, "mood": mood, "time": now_str()})
        self.store.save()
        try:
            sheets_backup.diary_write(text, mood)   # ← diary_write() use karo, diary() nahi
        except Exception:
            pass

    def get(self, d):
        """READ only — NO sheet write"""
        return self.store.data.get("entries", {}).get(d, [])

    def get_all_entries(self):
        """READ only — NO sheet write"""
        return self.store.data.get("entries", {})


# ================================================================
# HABIT STORE  — FIXED: log() mein sheets_backup.habit() properly call hota hai
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
        logs = self.store.data.get("logs", {})
        logs.setdefault(td, [])
        if hid in logs[td]:
            return False, 0

        logs[td].append(hid)
        streak   = 1
        hab_name = f"#{hid}"

        for h in self.store.data.get("list", []):
            if h["id"] == hid:
                h["streak"]      = h.get("streak", 0) + 1 if hid in logs.get(yd, []) else 1
                h["best_streak"] = max(h.get("best_streak", 0), h["streak"])
                streak           = h["streak"]
                hab_name         = h["name"]

        self.store.data["logs"] = logs
        self.store.save()

        # ── FIXED: yahan sheets_backup.habit() call guaranteed hota hai ──
        try:
            sheets_backup.habit(hab_name, streak)
            log.info(f"Habit synced to sheet: {hab_name} streak={streak}")
        except Exception as e:
            log.error(f"Habit sheet sync failed: {e}")

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
            sheets_backup.expense(amount, desc, category)
        except Exception:
            pass

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
# GOAL STORE  — FIXED: add() aur update_progress() dono sheet mein sync hote hain
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
        # ── FIXED: goal sheet sync guaranteed ──
        try:
            sheets_backup.goal(g)
            log.info(f"Goal synced to sheet: {g['title']}")
        except Exception as e:
            log.error(f"Goal sheet sync failed: {e}")
        return g

    def update_progress(self, gid, pct):
        for g in self.store.data["list"]:
            if g["id"] == gid:
                g["progress"] = min(100, max(0, pct))
                if g["progress"] == 100:
                    g["done"] = True
                self.store.save()
                try:
                    sheets_backup.goal_update(g)
                except Exception as e:
                    log.error(f"Goal update sheet sync failed: {e}")
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
        rid = self.store.data["counter"]
        r = {
            "id":           rid,
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
            sheets_backup.reminder(r, action="created")
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
        try:
            sheets_backup.delete_row_by_value("Reminders", 1, str(rid))
        except Exception:
            pass

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
                try:
                    sheets_backup.reminder(r, action="update")
                except Exception:
                    pass
                return True
        return False

    def acknowledge_all_by_text(self, text):
        count = 0
        text_clean = text.strip().lower().lstrip("🔁 ")
        for r in self.store.data["list"]:
            if not r.get("active"):
                continue
            r_text = r.get("text", "").strip().lower().lstrip("🔁 ")
            if r_text == text_clean or text_clean in r_text or r_text in text_clean:
                r["active"]       = False
                r["acknowledged"] = True
                r["remarks"]      = "Bulk dismissed"
                r["last_fired"]   = now_ist().isoformat()
                count += 1
        if count:
            self.store.save()
        return count

    def reset_daily(self):
        changed = False
        for r in self.store.data["list"]:
            if r.get("repeat") in ("daily", "weekly") and r.get("active"):
                r["fired_today"] = False
                r["fire_count"]  = 0
                changed = True
        if changed:
            self.store.save()
        log.info("Daily reminders reset")

    def due_now(self):
        now_hm = now_ist().strftime("%H:%M")
        return [r for r in self.store.data.get("list", [])
                if r.get("active") and not r.get("acknowledged") and r["time"] == now_hm]


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
            sheets_backup.water(ml, total)
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

    def add(self, name, amount, due_day, auto_pay="No", payment_method="", notes=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        b = {
            "id":             self.store.data["counter"],
            "name":           name,
            "amount":         amount,
            "due_day":        due_day,
            "active":         True,
            "paid_months":    [],
            "created":        today_str(),
            "auto_pay":       auto_pay,
            "payment_method": payment_method,
            "notes":          notes
        }
        self.store.data["list"].append(b)
        self.store.save()
        try:
            sheets_backup.bill(b, action="created")
        except Exception:
            pass
        return b

    def all_active(self):
        return [b for b in self.store.data.get("list", []) if b.get("active")]

    def get_by_id(self, bid):
        for b in self.store.data.get("list", []):
            if b["id"] == bid:
                return b
        return None

    def mark_paid(self, bid):
        ym = today_str()[:7]
        for b in self.store.data["list"]:
            if b["id"] == bid and ym not in b.get("paid_months", []):
                b["paid_months"].append(ym)
                self.store.save()
                try:
                    sheets_backup.bill(b, action="update")
                except Exception:
                    pass
                return True
        return False

    def delete(self, bid):
        self.store.data["list"] = [b for b in self.store.data["list"] if b["id"] != bid]
        self.store.save()
        try:
            sheets_backup.delete_row_by_value("Bills", 1, str(bid))
        except Exception:
            pass

    def is_paid_this_month(self, bid):
        ym = today_str()[:7]
        for b in self.store.data["list"]:
            if b["id"] == bid:
                return ym in b.get("paid_months", [])
        return False

    def due_soon(self, days=3):
        today_day = now_ist().day
        result = []
        for b in self.all_active():
            try:
                due = int(b.get("due_day", 0))
                if 0 < due - today_day <= days:
                    result.append(b)
            except Exception:
                pass
        return result


# ================================================================
# CALENDAR STORE
# ================================================================
class CalendarStore:
    def __init__(self):
        self.store = PrivateStore("calendar", {"events": [], "counter": 0})

    def add(self, title, event_date, event_time="", location="", notes="", event_type="event"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        e = {
            "id":                self.store.data["counter"],
            "title":             title,
            "date":              event_date,
            "time":              event_time,
            "location":          location,
            "notes":             notes,
            "type":              event_type,
            "created":           today_str(),
            "remind_day_before": True,
        }
        self.store.data["events"].append(e)
        self.store.save()
        try:
            sheets_backup.calendar_event(e)
        except Exception:
            pass
        return e

    def delete(self, eid):
        self.store.data["events"] = [e for e in self.store.data["events"] if e["id"] != eid]
        self.store.save()
        try:
            sheets_backup.delete_row_by_value("Calendar", 1, str(eid))
        except Exception:
            pass

    def upcoming(self, days=30):
        today_d = now_ist().date()
        cutoff  = today_d + timedelta(days=days)
        return sorted(
            [e for e in self.store.data.get("events", [])
             if today_d <= date.fromisoformat(e["date"]) <= cutoff],
            key=lambda x: x["date"]
        )

    def today_events(self):
        return [e for e in self.store.data.get("events", []) if e["date"] == today_str()]

    def tomorrow_events(self):
        tomorrow = (now_ist().date() + timedelta(days=1)).strftime("%Y-%m-%d")
        return [e for e in self.store.data.get("events", []) if e["date"] == tomorrow]

    def events_needing_reminder(self):
        return self.tomorrow_events()

    def all_events(self):
        return sorted(self.store.data.get("events", []), key=lambda x: x["date"])

    def get_by_id(self, eid):
        for e in self.store.data.get("events", []):
            if e["id"] == eid:
                return e
        return None


# ================================================================
# CHAT HISTORY STORE  →  Miscellaneous tab (Daily_Logs NAHI)
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
        try:
            # ← Miscellaneous tab mein jata hai ab
            sheets_backup.log_event(role, user_name, content)
        except Exception:
            pass

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

try:
    ok = sheets_backup.test_connection()
    log.info("Sheets PASSED" if ok else "Sheets FAILED — GitHub only")
except Exception as e:
    log.error(f"Sheets startup: {e}")

log.info("=" * 60)
log.info("SECURE DATA MANAGER READY")
log.info(f"  GitHub : {'Connected' if repo_manager.is_connected else 'Local only'}")
log.info(f"  Sheets : {'Connected' if sheets_backup.connected   else 'NOT connected'}")
log.info("=" * 60)
