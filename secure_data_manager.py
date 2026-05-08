#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SECURE DATA MANAGER - Your personal data is stored in a PRIVATE GitHub repo.
All data automatically syncs to your private repository.
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
# Example PRIVATE_REPO_URL: "https://github.com/Rehman4175/my-bot-data.git"

DATA_DIR = "bot_private_data"  # Local folder for private data

# ================================================================
# GITHUB PRIVATE REPO MANAGER
# ================================================================
class PrivateRepoManager:
    """Handles all GitHub private repo operations - clone, pull, push"""
    
    def __init__(self):
        self.data_dir = DATA_DIR
        self.repo_url = PRIVATE_REPO_URL
        self.token = GITHUB_TOKEN
        self.is_connected = False
        
        # Create directory if not exists
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        
        # Check if we have valid credentials
        if not self.repo_url or not self.token:
            log.warning("⚠️ GITHUB_TOKEN or PRIVATE_REPO_URL not set!")
            log.warning("   Data will be stored LOCALLY only (not synced to GitHub)")
            log.warning("   Set these environment variables to enable cloud backup")
            return
        
        self.is_connected = True
        self._setup_repo()
    
    def _get_auth_url(self):
        """Get repo URL with authentication token"""
        if not self.repo_url:
            return None
        # Insert token into URL: https://TOKEN@github.com/username/repo.git
        return self.repo_url.replace("https://", f"https://{self.token}@")
    
    def _is_git_repo(self):
        """Check if directory is a git repository"""
        return (Path(self.data_dir) / ".git").exists()
    
    def _setup_repo(self):
        """Clone or pull the private repository"""
        auth_url = self._get_auth_url()
        if not auth_url:
            return
        
        try:
            if not self._is_git_repo():
                # Clone the repository
                log.info(f"📥 Cloning private repository into {self.data_dir}...")
                subprocess.run(
                    ["git", "clone", auth_url, self.data_dir],
                    check=True, capture_output=True, text=True
                )
                log.info("✅ Successfully cloned private repository")
            else:
                # Pull latest changes
                self._pull_changes()
        except subprocess.CalledProcessError as e:
            log.error(f"❌ Git operation failed: {e.stderr}")
            self.is_connected = False
    
    def _pull_changes(self):
        """Pull latest changes from GitHub"""
        if not self._is_git_repo():
            return
        
        auth_url = self._get_auth_url()
        if not auth_url:
            return
        
        try:
            log.info("📥 Pulling latest changes from GitHub...")
            subprocess.run(
                ["git", "-C", self.data_dir, "pull", auth_url, "main"],
                check=True, capture_output=True, text=True
            )
            log.info("✅ Successfully pulled latest changes")
        except subprocess.CalledProcessError as e:
            # It's okay if there's nothing to pull
            if "couldn't find remote ref" not in e.stderr:
                log.warning(f"Pull warning: {e.stderr}")
    
    def _push_changes(self, commit_message="Auto-save data"):
        """Push local changes to GitHub"""
        if not self._is_git_repo():
            return
        
        auth_url = self._get_auth_url()
        if not auth_url:
            return
        
        try:
            # Add all changes
            subprocess.run(
                ["git", "-C", self.data_dir, "add", "."],
                check=True, capture_output=True, text=True
            )
            
            # Commit changes
            commit_result = subprocess.run(
                ["git", "-C", self.data_dir, "commit", "-m", commit_message],
                capture_output=True, text=True
            )
            
            if "nothing to commit" in commit_result.stdout:
                log.info("📝 No changes to commit")
                return
            
            # Push changes
            log.info("📤 Pushing changes to GitHub...")
            subprocess.run(
                ["git", "-C", self.data_dir, "push", auth_url, "main"],
                check=True, capture_output=True, text=True
            )
            log.info("✅ Successfully pushed to GitHub")
        except subprocess.CalledProcessError as e:
            log.error(f"❌ Push failed: {e.stderr}")
    
    def save_file(self, filename, data):
        """Save data to file and sync to GitHub"""
        if not filename.endswith('.json'):
            filename = f"{filename}.json"
        
        filepath = Path(self.data_dir) / filename
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log.info(f"💾 Saved: {filename}")
            
            # Sync to GitHub if connected
            if self.is_connected:
                self._push_changes(f"Update {filename}")
            return True
        except Exception as e:
            log.error(f"❌ Failed to save {filename}: {e}")
            return False
    
    def load_file(self, filename, default=None):
        """Load data from file"""
        if default is None:
            default = {}
        
        if not filename.endswith('.json'):
            filename = f"{filename}.json"
        
        filepath = Path(self.data_dir) / filename
        if not filepath.exists():
            log.info(f"📄 {filename} not found, creating new file")
            self.save_file(filename, default)
            return default
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"❌ Failed to load {filename}: {e}")
            return default

# ================================================================
# INITIALIZE PRIVATE REPO MANAGER
# ================================================================
repo_manager = PrivateRepoManager()

# ================================================================
# TIMEZONE (IST)
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
# CUSTOM STORE CLASS
# ================================================================
class PrivateStore:
    def __init__(self, name, default=None):
        self.name = name
        self.default = default if default is not None else {}
        self.data = repo_manager.load_file(name, self.default)
    
    def save(self):
        repo_manager.save_file(self.name, self.data)

# ================================================================
# MEMORY STORE (Important Notes)
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
    
    def delete(self, tid):
        self.store.data["list"] = [t for t in self.store.data["list"] if t["id"] != tid]
        self.store.save()
    
    def pending(self):
        return [t for t in self.store.data.get("list", []) if not t["done"]]
    
    def done_on(self, d):
        return [t for t in self.store.data.get("list", []) if t["done"] and t.get("done_date") == d]
    
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
        self.store.data.setdefault("entries", {}).setdefault(td, [])
        self.store.data["entries"][td].append({
            "text": text, "mood": mood, "time": now_str()
        })
        self.store.save()
    
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
    
    def log_by_name(self, keyword):
        keyword = keyword.lower()
        for h in self.store.data.get("list", []):
            if keyword in h["name"].lower():
                ok, streak = self.log(h["id"])
                return ok, streak, h
        return False, 0, None
    
    def today_status(self):
        done_ids = self.store.data.get("logs", {}).get(today_str(), [])
        all_h = self.all()
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
    
    def set_budget(self, amount):
        self.store.data["budget"] = amount
        self.store.save()
    
    def today_total(self):
        return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date") == today_str())
    
    def month_total(self):
        m = today_str()[:7]
        return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date", "")[:7] == m)
    
    def budget_left(self):
        b = self.store.data.get("budget", 0)
        return b - self.month_total() if b else None
    
    def get_by_date(self, target_date):
        return [e for e in self.store.data.get("list", []) if e.get("date") == target_date]

# ================================================================
# GOAL STORE
# ================================================================
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
            "id": self.store.data["counter"],
            "chat_id": str(chat_id),
            "text": text,
            "time": remind_at,
            "repeat": repeat,
            "date": today_str(),
            "active": True,
            "fired_today": False,
            "last_fired": "",
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
    
    def mark_fired(self, rid):
        for r in self.store.data["list"]:
            if r["id"] == rid:
                r["fired_today"] = True
                r["last_fired"] = now_ist().isoformat()
                self.store.save()
                break
    
    def acknowledge(self, rid, remark="OK pressed"):
        for r in self.store.data["list"]:
            if r["id"] == rid and r.get("active"):
                r["active"] = False
                r["acknowledged"] = True
                r["remarks"] = remark
                self.store.save()
                return True
        return False
    
    def reset_daily(self):
        for r in self.store.data["list"]:
            r["fired_today"] = False
        self.store.save()
    
    def due_now(self):
        now_hm = now_ist().strftime("%H:%M")
        return [
            r for r in self.store.data.get("list", [])
            if r.get("active") and not r.get("fired_today") and r["time"] == now_hm
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
            "id": self.store.data["counter"],
            "name": name,
            "amount": amount,
            "due_day": due_day,
            "active": True,
            "paid_months": [],
            "created": today_str(),
            "auto_pay": "No",
            "payment_method": "",
            "notes": ""
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
            "id": self.store.data["counter"],
            "title": title,
            "date": event_date,
            "time": event_time,
            "location": location,
            "reminder_set": "Yes",
            "participants": "",
            "notes": notes,
            "created": today_str()
        }
        self.store.data["events"].append(e)
        self.store.save()
        return e
    
    def delete(self, eid):
        self.store.data["events"] = [e for e in self.store.data["events"] if e["id"] != eid]
        self.store.save()
    
    def upcoming(self, days=7):
        today_d = now_ist().date()
        cutoff = today_d + timedelta(days=days)
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
            "date": today_str(),
            "role": role,
            "message": content,
            "user": user_name
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

# ================================================================
# STATUS MESSAGE
# ================================================================
log.info("=" * 60)
log.info("🔐 SECURE DATA MANAGER INITIALIZED")
log.info(f"   Data stored in: '{DATA_DIR}/'")
log.info(f"   Private repo: {PRIVATE_REPO_URL if PRIVATE_REPO_URL else 'Not set'}")
log.info(f"   GitHub connection: {'✅ Connected' if repo_manager.is_connected else '⚠️ Local only'}")
log.info("   All data automatically syncs to your private GitHub repo")
log.info("=" * 60)
