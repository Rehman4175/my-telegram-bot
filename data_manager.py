#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     DATA MANAGER — DO NOT CHANGE THIS FILE                     ║
║     Yeh file aapka data handle karegi. Kabhi change mat karna. ║
║     Isme Google Sheets backup, Database, aur Stores hain.      ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, json, logging, time, asyncio
from datetime import datetime, date, timedelta, timezone

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
# DATABASE (JSON FILES) - YAHI AAPKA MAIN DATA HAI
# ================================================================
class Database:
    def __init__(self):
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)

    def load(self, collection, default=None):
        if default is None:
            default = {}
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            log.warning(f"DB load error [{collection}]: {e}")
        return default

    def save(self, collection, data):
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log.info(f"💾 Data saved to {collection}.json")
        except Exception as e:
            log.warning(f"DB save error [{collection}]: {e}")

db = Database()

class Store:
    def __init__(self, name, default=None):
        self.name = name
        self.data = db.load(name, default if default is not None else {})

    def save(self):
        db.save(self.name, self.data)


# ================================================================
# DATA STORES (YAHI AAPKE SAARE DATA HAIN)
# ================================================================

class MemoryStore:
    def __init__(self):
        self.store = Store("memory", {"facts": []})

    def add_fact(self, text):
        facts = self.store.data.get("facts", [])
        facts.append({"f": text, "d": today_str()})
        self.store.data["facts"] = facts[-200:]
        self.store.save()

    def get_all_facts(self):
        return self.store.data.get("facts", [])


class TaskStore:
    def __init__(self):
        self.store = Store("tasks", {"list": [], "counter": 0})

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
        self.store.data["list"] = [
            t for t in self.store.data["list"] if t["id"] != tid
        ]
        self.store.save()

    def pending(self):
        return [t for t in self.store.data.get("list", []) if not t["done"]]

    def done_on(self, d):
        return [
            t for t in self.store.data.get("list", [])
            if t["done"] and t.get("done_date") == d
        ]

    def today_pending(self):
        return [t for t in self.pending() if t.get("due", "") <= today_str()]

    def all_tasks(self):
        return self.store.data.get("list", [])

    def completed_tasks(self):
        return [t for t in self.all_tasks() if t["done"]]


class DiaryStore:
    def __init__(self):
        self.store = Store("diary", {"entries": {}})

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


class HabitStore:
    def __init__(self):
        self.store = Store("habits", {"list": [], "logs": {}, "counter": 0})

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
        for h in self.store.data.get("list", []):
            if h["id"] == hid:
                yd_logs = logs.get(yd, [])
                h["streak"] = h.get("streak", 0) + 1 if hid in yd_logs else 1
                h["best_streak"] = max(h.get("best_streak", 0), h.get("streak", 0))
        self.store.data["logs"] = logs
        self.store.save()
        streak = next(
            (h.get("streak", 1) for h in self.store.data["list"] if h["id"] == hid), 1
        )
        return True, streak

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
        self.store.data["list"] = [
            h for h in self.store.data["list"] if h["id"] != hid
        ]
        self.store.save()


class ExpenseStore:
    def __init__(self):
        self.store = Store("expenses", {"list": [], "budget": 0})

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
        return sum(
            e["amount"] for e in self.store.data.get("list", [])
            if e.get("date") == today_str()
        )

    def month_total(self):
        m = today_str()[:7]
        return sum(
            e["amount"] for e in self.store.data.get("list", [])
            if e.get("date", "")[:7] == m
        )

    def budget_left(self):
        b = self.store.data.get("budget", 0)
        return b - self.month_total() if b else None

    def get_by_date(self, target_date):
        return [
            e for e in self.store.data.get("list", [])
            if e.get("date") == target_date
        ]


class GoalStore:
    def __init__(self):
        self.store = Store("goals", {"list": [], "counter": 0})

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


class ReminderStore:
    def __init__(self):
        self.store = Store("reminders", {"list": [], "counter": 0})

    def add(self, chat_id, text, remind_at, repeat="once"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        r = {
            "id": self.store.data["counter"],
            "chat_id": str(chat_id), "text": text,
            "time": remind_at, "repeat": repeat,
            "date": today_str(), "active": True,
            "fired_today": False, "last_fired": "", "remarks": "",
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
        self.store.data["list"] = [
            r for r in self.store.data["list"] if r["id"] != rid
        ]
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


class WaterStore:
    def __init__(self):
        self.store = Store("water", {"logs": {}, "goal_ml": 2000})

    def add(self, ml=250):
        td = today_str()
        self.store.data.setdefault("logs", {}).setdefault(td, [])
        self.store.data["logs"][td].append({"ml": ml, "time": now_str()})
        self.store.save()

    def today_total(self):
        return sum(
            e["ml"] for e in self.store.data.get("logs", {}).get(today_str(), [])
        )

    def goal(self):
        return self.store.data.get("goal_ml", 2000)

    def set_goal(self, ml):
        self.store.data["goal_ml"] = ml
        self.store.save()


class BillStore:
    def __init__(self):
        self.store = Store("bills", {"list": [], "counter": 0})

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


class CalendarStore:
    def __init__(self):
        self.store = Store("calendar", {"events": [], "counter": 0})

    def add(self, title, event_date, event_time="", location="", notes=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        e = {
            "id": self.store.data["counter"], "title": title,
            "date": event_date, "time": event_time,
            "location": location, "reminder_set": "Yes",
            "participants": "", "notes": notes, "created": today_str()
        }
        self.store.data["events"].append(e)
        self.store.save()
        return e

    def delete(self, eid):
        self.store.data["events"] = [
            e for e in self.store.data["events"] if e["id"] != eid
        ]
        self.store.save()

    def upcoming(self, days=7):
        today_d = now_ist().date()
        cutoff = today_d + timedelta(days=days)
        return sorted(
            [e for e in self.store.data.get("events", [])
             if today_d <= date.fromisoformat(e["date"]) <= cutoff],
            key=lambda x: x["date"]
        )


class ChatHistoryStore:
    def __init__(self):
        self.store = Store("chat_history", {"history": []})

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

    def clear(self):
        count = len(self.store.data["history"])
        self.store.data["history"] = []
        self.store.save()
        return count


# ================================================================
# GOOGLE SHEETS BACKUP - FIXED AND STABLE
# ================================================================
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    HAS_GSHEETS = True
except ImportError:
    HAS_GSHEETS = False

class GoogleSheetsBackup:
    def __init__(self, creds_json):
        self.sheet = None
        if not HAS_GSHEETS or not creds_json:
            log.warning("⚠️ Google Sheets not available")
            return
        try:
            creds_dict = json.loads(creds_json)
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            sheet_key = "1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc"
            self.sheet = client.open_by_key(sheet_key)
            log.info("✅ Google Sheets connected for backup")
        except Exception as e:
            log.error(f"❌ Sheets connect error: {e}")

    def backup_all_data(self, stores):
        """Backup all data to Google Sheets without deleting existing data"""
        if not self.sheet:
            return "❌ Sheets not connected"
        
        results = {}
        for name, data in stores.items():
            try:
                ws = self.sheet.worksheet(name)
                # Append new data, don't clear existing
                for row in data:
                    ws.append_row(row, value_input_option="USER_ENTERED")
                results[name] = f"✅ {len(data)} rows"
            except Exception as e:
                results[name] = f"❌ {str(e)[:50]}"
        
        return results


# ================================================================
# INITIALIZE ALL STORES — YE HI AAPKA DATA HAI
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

# Data backup reference
ALL_STORES = {
    "Tasks": lambda: [[str(t.get("id","")), t.get("title",""), t.get("priority",""),
                      "Done" if t.get("done") else "Pending", t.get("created",""), 
                      t.get("done_date","")] for t in tasks.all_tasks()],
    "Diary": lambda: [[d, e.get("time",""), e.get("text",""), e.get("mood","📝")]
                      for d, entries in diary.get_all_entries().items() 
                      for e in entries],
    "Expenses": lambda: [[e.get("date",""), e.get("amount",0), e.get("desc",""), 
                          e.get("category",""), e.get("time","")] 
                         for e in expenses.store.data.get("list", [])],
    "Habits": lambda: [[h.get("id"), h.get("name",""), h.get("emoji","✅"),
                        h.get("streak",0), h.get("best_streak",0), h.get("created","")]
                       for h in habits.all()],
    "Reminders": lambda: [[r.get("id"), r.get("time",""), r.get("text",""), 
                           r.get("repeat","once"), "Active" if r.get("active") else "Inactive",
                           r.get("date",""), r.get("remarks","")]
                          for r in reminders.get_all()],
    "Goals": lambda: [[g.get("id"), g.get("title",""), g.get("progress",0),
                       "Done" if g.get("done") else "Active", g.get("deadline",""), 
                       g.get("created","")] for g in goals.active() + goals.completed()],
    "Bills": lambda: [[b.get("id"), b.get("name",""), b.get("amount",0), 
                       b.get("due_day"), "Paid" if bills.is_paid_this_month(b["id"]) else "Pending"]
                      for b in bills.all_active()],
    "Calendar": lambda: [[e.get("date",""), e.get("time",""), e.get("title",""), 
                          e.get("location","")] for e in calendar.store.data.get("events", [])],
    "Water": lambda: [[d, sum(l.get("ml",0) for l in logs), water.goal()]
                      for d, logs in water.store.data.get("logs", {}).items()],
    "Memory": lambda: [[f.get("d",""), f.get("f","")] for f in memory.get_all_facts()],
}

log.info("=" * 50)
log.info("✅ DATA MANAGER INITIALIZED")
log.info("   All data stored in 'data/' folder")
log.info("   JSON files are your primary data source")
log.info("=" * 50)
