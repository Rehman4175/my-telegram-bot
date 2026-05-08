#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SECURE DATA MANAGER - Private GitHub Repo + Google Sheets Backup
"""

import os
import json
import logging
import subprocess
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
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
PRIVATE_REPO_URL = os.environ.get("PRIVATE_REPO_URL", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "")

DATA_DIR = "bot_private_data"

# ================================================================
# GOOGLE SHEETS SETUP
# ================================================================
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    HAS_GSHEETS = True
except ImportError:
    HAS_GSHEETS = False

class GoogleSheetsBackup:
    def __init__(self):
        self.sheet = None
        if not HAS_GSHEETS or not GOOGLE_CREDS_JSON:
            log.warning("⚠️ Google Sheets not available")
            return
        try:
            creds_dict = json.loads(GOOGLE_CREDS_JSON)
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            sheet_key = "1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc"
            self.sheet = client.open_by_key(sheet_key)
            log.info("✅ Google Sheets connected")
        except Exception as e:
            log.error(f"❌ Sheets error: {e}")

    def backup_diary(self, diary_entries):
        """Backup diary entries to Google Sheets"""
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Diary")
            # Clear existing data (optional)
            # ws.clear()
            rows = []
            for date_str, entries in diary_entries.items():
                for entry in entries:
                    rows.append([
                        date_str,
                        entry.get("time", ""),
                        entry.get("text", ""),
                        entry.get("mood", "📝")
                    ])
            if rows:
                # Append new rows
                for row in rows:
                    try:
                        ws.append_row(row, value_input_option="USER_ENTERED")
                    except:
                        pass
            log.info(f"📤 Backed up {len(rows)} diary entries to Google Sheets")
            return True
        except Exception as e:
            log.error(f"Diary backup error: {e}")
            return False

# ================================================================
# GITHUB PRIVATE REPO MANAGER
# ================================================================
class PrivateRepoManager:
    def __init__(self):
        self.data_dir = DATA_DIR
        self.repo_url = PRIVATE_REPO_URL
        self.token = GITHUB_TOKEN
        self.is_connected = False
        
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        
        if not self.repo_url or not self.token:
            log.warning("⚠️ GitHub credentials not set - local only")
            return
        
        self.is_connected = True
        self._setup_repo()
    
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
                subprocess.run(["git", "clone", auth_url, self.data_dir], check=True, capture_output=True)
                log.info("✅ Cloned private repository")
            else:
                subprocess.run(["git", "-C", self.data_dir, "pull", auth_url, "main"], check=True, capture_output=True)
                log.info("✅ Pulled latest changes")
        except Exception as e:
            log.warning(f"Git setup: {e}")
    
    def _push_changes(self, commit_message="Auto-save"):
        if not self.is_connected or not self._is_git_repo():
            return
        auth_url = self._get_auth_url()
        if not auth_url:
            return
        try:
            subprocess.run(["git", "-C", self.data_dir, "add", "."], check=True, capture_output=True)
            subprocess.run(["git", "-C", self.data_dir, "commit", "-m", commit_message], capture_output=True)
            subprocess.run(["git", "-C", self.data_dir, "push", auth_url, "main"], check=True, capture_output=True)
            log.info("📤 Pushed to GitHub")
        except Exception as e:
            log.warning(f"Push failed: {e}")
    
    def save_file(self, filename, data):
        filepath = Path(self.data_dir) / filename
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._push_changes(f"Update {filename}")
            return True
        except Exception as e:
            log.error(f"Save failed: {e}")
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
        except Exception as e:
            log.error(f"Load failed: {e}")
            return default

# ================================================================
# INITIALIZE
# ================================================================
repo_manager = PrivateRepoManager()
sheets_backup = GoogleSheetsBackup()

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
# STORE CLASS
# ================================================================
class PrivateStore:
    def __init__(self, name, default=None):
        self.name = name
        self.default = default if default is not None else {}
        self.data = repo_manager.load_file(name, self.default)
    
    def save(self):
        repo_manager.save_file(self.name, self.data)

# ================================================================
# DIARY STORE (with Google Sheets backup)
# ================================================================
class DiaryStore:
    def __init__(self):
        self.store = PrivateStore("diary", {"entries": {}})
    
    def add(self, text, mood="📝"):
        td = today_str()
        self.store.data.setdefault("entries", {}).setdefault(td, [])
        self.store.data["entries"][td].append({
            "text": text, "mood": mood, "time": now_str()
        })
        self.store.save()
        log.info(f"📖 Diary saved: {text[:50]}...")
        
        # Backup to Google Sheets
        try:
            sheets_backup.backup_diary(self.store.data.get("entries", {}))
        except Exception as e:
            log.warning(f"Sheets backup failed: {e}")
    
    def get(self, d):
        return self.store.data.get("entries", {}).get(d, [])
    
    def get_all_entries(self):
        return self.store.data.get("entries", {})

# ================================================================
# TASK STORE
# ================================================================
class TaskStore:
    def __init__(self):
        self.store = PrivateStore("tasks", {"list": [], "counter": 0})
    
    def add(self, title, priority="medium"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        t = {
            "id": self.store.data["counter"],
            "title": title,
            "priority": priority,
            "done": False,
            "created": today_str(),
            "due": today_str(),
            "tags": "",
            "done_date": ""
        }
        self.store.data["list"].append(t)
        self.store.save()
        return t
    
    def complete(self, tid):
        for t in self.store.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True
                t["done_date"] = today_str()
                self.store.save()
                return t
        return None
    
    def pending(self):
        return [t for t in self.store.data.get("list", []) if not t["done"]]
    
    def all_tasks(self):
        return self.store.data.get("list", [])

# ================================================================
# OTHER STORES (Habit, Expense, Reminder, etc.)
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

class HabitStore:
    def __init__(self):
        self.store = PrivateStore("habits", {"list": [], "logs": {}, "counter": 0})
    
    def add(self, name, emoji="✅"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        h = {
            "id": self.store.data["counter"],
            "name": name,
            "emoji": emoji,
            "streak": 0,
            "best_streak": 0,
            "created": today_str(),
            "target": ""
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
        for h in self.store.data.get("list", []):
            if h["id"] == hid:
                yd_logs = logs.get(yd, [])
                h["streak"] = h.get("streak", 0) + 1 if hid in yd_logs else 1
                h["best_streak"] = max(h.get("best_streak", 0), h.get("streak", 0))
        self.store.data["logs"] = logs
        self.store.save()
        streak = next((h.get("streak", 1) for h in self.store.data["list"] if h["id"] == hid), 1)
        return True, streak
    
    def today_status(self):
        done_ids = self.store.data.get("logs", {}).get(today_str(), [])
        all_h = self.all()
        return ([h for h in all_h if h["id"] in done_ids], [h for h in all_h if h["id"] not in done_ids])
    
    def all(self):
        return self.store.data.get("list", [])

class ExpenseStore:
    def __init__(self):
        self.store = PrivateStore("expenses", {"list": [], "budget": 0})
    
    def add(self, amount, desc, category="general"):
        self.store.data["list"].append({
            "amount": amount, "desc": desc,
            "category": category, "date": today_str(), "time": now_str()
        })
        self.store.save()
    
    def today_total(self):
        return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date") == today_str())

class ReminderStore:
    def __init__(self):
        self.store = PrivateStore("reminders", {"list": [], "counter": 0})
    
    def add(self, chat_id, text, remind_at, repeat="once"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        r = {
            "id": self.store.data["counter"],
            "chat_id": str(chat_id),
            "text": text,
            "time": remind_at,
            "repeat": repeat,
            "date": today_str(),
            "active": True,
            "fired_today": False,
            "remarks": "",
            "acknowledged": False
        }
        self.store.data["list"].append(r)
        self.store.save()
        return r
    
    def all_active(self):
        return [r for r in self.store.data.get("list", []) if r.get("active")]
    
    def get_all(self):
        return self.store.data.get("list", [])
    
    def delete(self, rid):
        self.store.data["list"] = [r for r in self.store.data["list"] if r["id"] != rid]
        self.store.save()
    
    def due_now(self):
        now_hm = now_ist().strftime("%H:%M")
        return [r for r in self.store.data.get("list", []) if r.get("active") and not r.get("fired_today") and r["time"] == now_hm]
    
    def mark_fired(self, rid):
        for r in self.store.data["list"]:
            if r["id"] == rid:
                r["fired_today"] = True
                self.store.save()
                break

class WaterStore:
    def __init__(self):
        self.store = PrivateStore("water", {"logs": {}, "goal_ml": 2000})
    
    def add(self, ml=250):
        td = today_str()
        self.store.data.setdefault("logs", {}).setdefault(td, [])
        self.store.data["logs"][td].append({"ml": ml, "time": now_str()})
        self.store.save()
    
    def today_total(self):
        return sum(e["ml"] for e in self.store.data.get("logs", {}).get(today_str(), []))

class GoalStore:
    def __init__(self):
        self.store = PrivateStore("goals", {"list": [], "counter": 0})
    
    def add(self, title, deadline=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        g = {
            "id": self.store.data["counter"],
            "title": title,
            "progress": 0,
            "done": False,
            "deadline": deadline,
            "created": today_str(),
            "milestones": ""
        }
        self.store.data["list"].append(g)
        self.store.save()
        return g

class BillStore:
    def __init__(self):
        self.store = PrivateStore("bills", {"list": [], "counter": 0})
    
    def add(self, name, amount, due_day):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        b = {
            "id": self.store.data["counter"],
            "name": name,
            "amount": amount,
            "due_day": due_day,
            "active": True,
            "paid_months": [],
            "created": today_str()
        }
        self.store.data["list"].append(b)
        self.store.save()
        return b

class CalendarStore:
    def __init__(self):
        self.store = PrivateStore("calendar", {"events": [], "counter": 0})
    
    def add(self, title, event_date, event_time="", location="", notes=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        e = {
            "id": self.store.data["counter"],
            "title": title,
            "date": event_date,
            "time": event_time,
            "location": location,
            "notes": notes,
            "created": today_str()
        }
        self.store.data["events"].append(e)
        self.store.save()
        return e

class ChatHistoryStore:
    def __init__(self):
        self.store = PrivateStore("chat_history", {"history": []})
    
    def add(self, role, content, user_name=""):
        self.store.data["history"].append({
            "timestamp": now_ist().isoformat(),
            "date": today_str(),
            "role": role,
            "message": content,
            "user": user_name
        })
        self.store.data["history"] = self.store.data["history"][-500:]
        self.store.save()

# ================================================================
# INITIALIZE ALL STORES
# ================================================================
memory = MemoryStore()
tasks = TaskStore()
diary = DiaryStore()
habits = HabitStore()
expenses = ExpenseStore()
goals = GoalStore()
reminders = ReminderStore()
water = WaterStore()
bills = BillStore()
calendar = CalendarStore()
chat_hist = ChatHistoryStore()

log.info("=" * 60)
log.info("🔐 SECURE DATA MANAGER INITIALIZED")
log.info(f"   Data stored in: '{DATA_DIR}/'")
log.info(f"   GitHub: {'✅ Connected' if repo_manager.is_connected else '⚠️ Local only'}")
log.info(f"   Sheets: {'✅ Connected' if sheets_backup.sheet else '⚠️ Not connected'}")
log.info("=" * 60)
