#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v21.0  NATURAL LANGUAGE MODE       ║
║  NO BUTTONS — Sab kuch chat se hoga                             ║
║  - Natural language se task, habit, reminder, diary sab kaam   ║
║  - Google Sheets sync intact                                    ║
║  - Reminders/Alarms background mein chalte rahenge             ║
║  - Commands bhi kaam karenge                                    ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, json, logging, time, asyncio, random
import urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta, timezone
import datetime as dt_module
from xml.etree import ElementTree as ET
import re as _re

ssl._create_default_https_context = ssl._create_unverified_context

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    HAS_GSHEETS = True
except ImportError:
    HAS_GSHEETS = False

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
    ConversationHandler
)

# ═══════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON",
                    os.environ.get("Google_CREDS_JSON", ""))
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")

DIARY_PASSWORD = "Rk1996"

# ConversationHandler states (diary)
DIARY_AWAIT_PASS = 0
DIARY_AWAIT_TEXT = 1

if not TELEGRAM_TOKEN:
    log.error("❌ TELEGRAM_TOKEN not set!")
    exit(1)

# ═══════════════════════════════════════════════════════════════════
# IST TIMEZONE
# ═══════════════════════════════════════════════════════════════════
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(timezone.utc).astimezone(IST)

def today_str():
    return now_ist().strftime("%Y-%m-%d")

def now_str():
    return now_ist().strftime("%H:%M")

def yesterday_str():
    return (now_ist() - timedelta(days=1)).strftime("%Y-%m-%d")

# ═══════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════
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
        except Exception as e:
            log.warning(f"DB save error [{collection}]: {e}")

db = Database()

class Store:
    def __init__(self, name, default=None):
        self.name = name
        self.data = db.load(name, default if default is not None else {})

    def save(self):
        db.save(self.name, self.data)

# ═══════════════════════════════════════════════════════════════════
# GEMINI API
# ═══════════════════════════════════════════════════════════════════
GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
_last_gemini_call = 0

def call_gemini(prompt, max_tokens=500):
    global _last_gemini_call
    if not GEMINI_API_KEY:
        return None
    now_t = time.time()
    elapsed = now_t - _last_gemini_call
    if elapsed < 3:
        time.sleep(3 - elapsed + random.uniform(0.5, 1.5))
    _last_gemini_call = time.time()

    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.75,
            "maxOutputTokens": min(max_tokens, 700)
        }
    }).encode("utf-8")

    for model in GEMINI_MODELS:
        try:
            url = GEMINI_URL.format(model=model, key=GEMINI_API_KEY)
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=35) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            log.warning(f"Gemini [{model}] error: {e}")
            continue
    return None

# ═══════════════════════════════════════════════════════════════════
# DATA STORES
# ═══════════════════════════════════════════════════════════════════

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

    def _save(self):
        self.store.save()

    def add(self, title, priority="medium"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        t = {
            "id": self.store.data["counter"], "title": title,
            "priority": priority, "done": False,
            "created": today_str(), "due": today_str(),
            "tags": "", "done_date": ""
        }
        self.store.data["list"].append(t)
        self._save()
        return t

    def complete(self, tid):
        for t in self.store.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True
                t["done_date"] = today_str()
                self._save()
                return t
        return None

    def complete_by_title(self, keyword):
        """Title mein keyword se task complete karo"""
        keyword = keyword.lower()
        for t in self.store.data["list"]:
            if not t["done"] and keyword in t["title"].lower():
                t["done"] = True
                t["done_date"] = today_str()
                self._save()
                return t
        return None

    def delete(self, tid):
        self.store.data["list"] = [
            t for t in self.store.data["list"] if t["id"] != tid
        ]
        self._save()

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

    def get_weekly_summary(self):
        result = {}
        n = now_ist()
        for i in range(7):
            d = (n.date() - timedelta(days=i)).isoformat()
            done = self.done_on(d)
            result[d] = {"done": len(done), "pending": 0}
        return result


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

    def log_by_name(self, keyword):
        """Name se habit log karo"""
        keyword = keyword.lower()
        for h in self.store.data.get("list", []):
            if keyword in h["name"].lower():
                return self.log(h["id"]) + (h,)
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
        self.store.data["list"] = [
            h for h in self.store.data["list"] if h["id"] != hid
        ]
        self.store.save()

    def get_logs_by_date(self, target_date):
        return self.store.data.get("logs", {}).get(target_date, [])


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
            "fired_today": False, "last_fired": "", "remarks": ""
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
                if r["repeat"] == "once":
                    r["active"] = False
                self.store.save()
                break

    def reset_daily(self):
        for r in self.store.data["list"]:
            r["fired_today"] = False
        self.store.save()
        log.info("🔄 Reminders reset for new day")

    def due_now(self):
        now_hm = now_ist().strftime("%H:%M")
        return [
            r for r in self.store.data.get("list", [])
            if r.get("active") and not r.get("fired_today")
            and r["time"] == now_hm
        ]

    def snooze(self, rid, minutes=10):
        snooze_time = (now_ist() + timedelta(minutes=minutes)).strftime("%H:%M")
        for r in self.store.data["list"]:
            if r["id"] == rid:
                new_r = self.add(int(r["chat_id"]), r["text"], snooze_time, "once")
                self.mark_fired(rid)
                return new_r, snooze_time
        return None, snooze_time


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

    def get_by_date(self, target_date):
        return self.store.data.get("logs", {}).get(target_date, [])

    def week_summary(self):
        result = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            result[d] = sum(
                e["ml"] for e in self.store.data.get("logs", {}).get(d, [])
            )
        return result


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

    def delete(self, bid):
        self.store.data["list"] = [
            b for b in self.store.data["list"] if b["id"] != bid
        ]
        self.store.save()

    def due_soon(self, days_ahead=3):
        today_d = now_ist().date()
        result = []
        for b in self.store.data.get("list", []):
            if not b.get("active") or self.is_paid_this_month(b["id"]):
                continue
            try:
                due_date = date(today_d.year, today_d.month, min(b["due_day"], 28))
            except Exception:
                continue
            if today_d <= due_date <= today_d + timedelta(days=days_ahead):
                result.append({**b, "due_date": due_date.isoformat()})
        return result


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

    def today_events(self):
        return [
            e for e in self.store.data.get("events", [])
            if e["date"] == today_str()
        ]


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

    def get_recent(self, n=10):
        return self.store.data.get("history", [])[-n:]

    def clear(self):
        count = len(self.store.data["history"])
        self.store.data["history"] = []
        self.store.save()
        return count


# ═══════════════════════════════════════════════════════════════════
# INIT STORES
# ═══════════════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════════════
# GOOGLE SHEETS BACKUP
# ═══════════════════════════════════════════════════════════════════
class GoogleSheetsBackup:
    def __init__(self):
        self.sheet = None
        if not HAS_GSHEETS or not GOOGLE_CREDS_JSON:
            log.warning("⚠️ Google Sheets: HAS_GSHEETS=%s, CREDS_SET=%s",
                        HAS_GSHEETS, bool(GOOGLE_CREDS_JSON))
            return
        try:
            creds_dict = json.loads(GOOGLE_CREDS_JSON)
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            self.sheet = client.open_by_key("1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")
            log.info("✅ Google Sheets connected!")
            self.ensure_worksheets()
        except Exception as e:
            log.error(f"❌ Sheets connect error: {e}")

    def ensure_worksheets(self):
        if not self.sheet:
            return
        sheet_configs = {
            "Reminders":               ["ID","Time","Text","Repeat","Status","Created Date","Chat ID","Last Fired","Remarks"],
            "Tasks":                   ["ID","Title","Priority","Status","Created Date","Completed Date","Due Date","Tags"],
            "Expenses":                ["Date","Amount (Rs)","Description","Category","Time"],
            "Habits":                  ["ID","Habit Name","Emoji","Streak","Best Streak","Created Date","Target (per day)"],
            "Water Intake":            ["Date","Total ML","Goal ML","Percentage","Glasses (250ml)","Hourly Logs"],
            "Memory / Important Notes":["Date","Category","Content","Tags","Priority"],
            "Daily_Logs":              ["Date","Tasks Done","Tasks Pending","Expenses (Rs)","Reminders Active","Habits Done","Water ML","Mood","Notes"],
            "Goals":                   ["ID","Title","Progress %","Status","Deadline","Created Date","Milestones"],
            "Bills & Subscriptions":   ["ID","Name","Amount (₹)","Due Date","Auto-pay","Paid Status","Payment Method","Notes"],
            "Calendar Events":         ["Date","Time","Event Title","Location","Reminder Set","Participants","Notes"],
            "Diary":                   ["Date","Time","Content","Mood"],
            "Miscellaneous":           ["Timestamp","Date","Role","User","Message"],
        }
        existing_ws = {ws.title: ws for ws in self.sheet.worksheets()}
        for name, headers in sheet_configs.items():
            if name not in existing_ws:
                try:
                    ws = self.sheet.add_worksheet(title=name, rows=1000, cols=len(headers))
                    ws.update('A1', [headers])
                    log.info(f"📊 Created worksheet: {name}")
                except Exception as e:
                    log.warning(f"Could not create worksheet {name}: {e}")

    def _upsert_by_id(self, ws, rows, id_col=0):
        try:
            existing = ws.get_all_values()
            key_to_row = {}
            for i, row in enumerate(existing[1:], start=2):
                if row and len(row) > id_col and row[id_col]:
                    key_to_row[str(row[id_col]).strip()] = i
            updates, appends = [], []
            for row in rows:
                key = str(row[id_col]).strip() if row else ""
                if key and key in key_to_row:
                    updates.append((key_to_row[key], row))
                else:
                    appends.append(row)
            if updates:
                batch = []
                for row_num, data in updates:
                    col_end = chr(ord("A") + len(data) - 1)
                    batch.append({
                        "range": f"A{row_num}:{col_end}{row_num}",
                        "values": [data]
                    })
                ws.batch_update(batch)
            for row in appends:
                ws.append_row(row, value_input_option="USER_ENTERED")
        except Exception as e:
            log.warning(f"_upsert_by_id error: {e}")

    def _append_unique(self, ws, rows, key_cols):
        try:
            existing = ws.get_all_values()
            existing_keys = set()
            for row in existing[1:]:
                key = "|".join(str(row[c]) if len(row) > c else "" for c in key_cols)
                existing_keys.add(key)
            new_rows = []
            for row in rows:
                key = "|".join(str(row[c]) if len(row) > c else "" for c in key_cols)
                if key not in existing_keys:
                    new_rows.append(row)
                    existing_keys.add(key)
            for row in new_rows:
                ws.append_row(row, value_input_option="USER_ENTERED")
        except Exception as e:
            log.warning(f"_append_unique error: {e}")

    def save_tasks(self):
        try:
            ws = self.sheet.worksheet("Tasks")
            rows = [
                [str(t.get("id","")), t.get("title",""), t.get("priority","medium"),
                 "Done" if t.get("done") else "Pending",
                 t.get("created",""), t.get("done_date",""),
                 t.get("due",""), t.get("tags","")]
                for t in tasks.all_tasks()
            ]
            if rows:
                self._upsert_by_id(ws, rows, 0)
            return True
        except Exception as e:
            log.warning(f"save_tasks: {e}")
            return False

    def save_reminders(self):
        try:
            ws = self.sheet.worksheet("Reminders")
            rows = [
                [str(r.get("id","")), r.get("time",""), r.get("text",""),
                 r.get("repeat","once"),
                 "Active" if r.get("active") else "Inactive",
                 r.get("date",""), str(r.get("chat_id","")),
                 r.get("last_fired",""), r.get("remarks","")]
                for r in reminders.get_all()
            ]
            if rows:
                self._upsert_by_id(ws, rows, 0)
            return True
        except Exception as e:
            log.warning(f"save_reminders: {e}")
            return False

    def save_expenses(self):
        try:
            ws = self.sheet.worksheet("Expenses")
            rows = [
                [e.get("date",""), e.get("amount",0),
                 e.get("desc",""), e.get("category","general"), e.get("time","")]
                for e in expenses.store.data.get("list", [])
            ]
            if rows:
                self._append_unique(ws, rows, [0, 1, 2])
            return True
        except Exception as e:
            log.warning(f"save_expenses: {e}")
            return False

    def save_habits(self):
        try:
            ws = self.sheet.worksheet("Habits")
            rows = [
                [str(h.get("id","")), h.get("name",""), h.get("emoji","✅"),
                 h.get("streak",0), h.get("best_streak",0),
                 h.get("created",""), h.get("target","")]
                for h in habits.all()
            ]
            if rows:
                self._upsert_by_id(ws, rows, 0)
            return True
        except Exception as e:
            log.warning(f"save_habits: {e}")
            return False

    def save_memory(self):
        try:
            ws = self.sheet.worksheet("Memory / Important Notes")
            rows = [
                [f.get("d",""), "Fact", f.get("f",""), "", "Medium"]
                for f in memory.get_all_facts()
            ]
            if rows:
                self._append_unique(ws, rows, [0, 2])
            return True
        except Exception as e:
            log.warning(f"save_memory: {e}")
            return False

    def save_goals(self):
        try:
            ws = self.sheet.worksheet("Goals")
            rows = [
                [str(g.get("id","")), g.get("title",""), g.get("progress",0),
                 "Done" if g.get("done") else "Active",
                 g.get("deadline",""), g.get("created",""), g.get("milestones","")]
                for g in goals.active() + goals.completed()
            ]
            if rows:
                self._upsert_by_id(ws, rows, 0)
            return True
        except Exception as e:
            log.warning(f"save_goals: {e}")
            return False

    def save_bills(self):
        try:
            ws = self.sheet.worksheet("Bills & Subscriptions")
            rows = [
                [str(b.get("id","")), b.get("name",""), b.get("amount",0),
                 str(b.get("due_day","")),
                 b.get("auto_pay","No"),
                 "Paid" if bills.is_paid_this_month(b["id"]) else "Pending",
                 b.get("payment_method",""), b.get("notes","")]
                for b in bills.all_active()
            ]
            if rows:
                self._upsert_by_id(ws, rows, 0)
            return True
        except Exception as e:
            log.warning(f"save_bills: {e}")
            return False

    def save_calendar(self):
        try:
            ws = self.sheet.worksheet("Calendar Events")
            rows = [
                [e.get("date",""), e.get("time",""), e.get("title",""),
                 e.get("location",""), e.get("reminder_set","Yes"),
                 e.get("participants",""), e.get("notes","")]
                for e in calendar.store.data.get("events", [])
            ]
            if rows:
                self._append_unique(ws, rows, [0, 2])
            return True
        except Exception as e:
            log.warning(f"save_calendar: {e}")
            return False

    def save_water(self):
        try:
            ws = self.sheet.worksheet("Water Intake")
            goal_ml = water.goal()
            week = water.week_summary()
            rows = []
            for d, total_ml in sorted(week.items()):
                pct = int(total_ml / goal_ml * 100) if goal_ml else 0
                rows.append([d, total_ml, goal_ml, f"{pct}%", total_ml // 250, ""])
            if rows:
                self._upsert_by_id(ws, rows, 0)
            return True
        except Exception as e:
            log.warning(f"save_water: {e}")
            return False

    def save_daily_log(self):
        try:
            ws = self.sheet.worksheet("Daily_Logs")
            today = today_str()
            row = [
                today, len(tasks.done_on(today)), len(tasks.today_pending()),
                expenses.today_total(), len(reminders.all_active()),
                len(habits.today_status()[0]), water.today_total(), "", ""
            ]
            all_vals = ws.get_all_values()
            for i, r in enumerate(all_vals):
                if r and r[0] == today:
                    ws.update(f'A{i+1}:I{i+1}', [row])
                    return True
            ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            log.warning(f"save_daily_log: {e}")
            return False

    def save_diary(self):
        try:
            ws = self.sheet.worksheet("Diary")
            existing = ws.get_all_values()
            existing_keys = set()
            for row in existing[1:]:
                if row and row[0]:
                    key = f"{row[0]}|{row[1] if len(row)>1 else ''}|{row[2][:50] if len(row)>2 else ''}"
                    existing_keys.add(key)
            new_rows = []
            for edate in sorted(diary.get_all_entries().keys()):
                for entry in diary.get_all_entries()[edate]:
                    key = f"{edate}|{entry.get('time','')}|{entry.get('text','')[:50]}"
                    if key not in existing_keys:
                        new_rows.append([
                            edate, entry.get("time",""),
                            entry.get("text",""), entry.get("mood","📝")
                        ])
                        existing_keys.add(key)
            for row in new_rows:
                ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            log.warning(f"save_diary: {e}")
            return False

    def save_chat_history(self):
        try:
            ws = self.sheet.worksheet("Miscellaneous")
            existing = ws.get_all_values()
            existing_keys = set()
            for row in existing[1:]:
                if row and len(row) >= 5 and row[0]:
                    key = f"{row[0]}|{row[2]}|{row[4][:80] if len(row) > 4 else ''}"
                    existing_keys.add(key)
            all_history = chat_hist.get_all()
            new_rows = []
            for h in all_history:
                ts   = h.get("timestamp", "")
                role = h.get("role", "")
                msg  = h.get("message", "")
                key  = f"{ts}|{role}|{msg[:80]}"
                if key not in existing_keys:
                    new_rows.append([
                        ts, h.get("date",""), role, h.get("user",""), msg
                    ])
                    existing_keys.add(key)
            if new_rows:
                for row in new_rows:
                    ws.append_row(row, value_input_option="USER_ENTERED")
                log.info(f"💬 Miscellaneous: {len(new_rows)} rows saved")
            return True
        except Exception as e:
            log.error(f"save_chat_history error: {e}")
            return False

    def full_sync(self):
        if not self.sheet:
            return "❌ Sheets not connected!"
        ops = [
            ("Tasks",        self.save_tasks),
            ("Reminders",    self.save_reminders),
            ("Expenses",     self.save_expenses),
            ("Habits",       self.save_habits),
            ("Memory",       self.save_memory),
            ("Goals",        self.save_goals),
            ("Bills",        self.save_bills),
            ("Calendar",     self.save_calendar),
            ("Water",        self.save_water),
            ("Daily_Log",    self.save_daily_log),
            ("Diary",        self.save_diary),
            ("Chat_History", self.save_chat_history),
        ]
        success = 0
        for name, fn in ops:
            try:
                if fn():
                    success += 1
                    log.info(f"  ✅ {name}")
                else:
                    log.warning(f"  ⚠️ {name} returned False")
            except Exception as e:
                log.error(f"  ❌ Sync [{name}]: {e}")
        return f"✅ {success}/{len(ops)} synced"


google_sheets = GoogleSheetsBackup()


async def auto_backup_to_sheets():
    if not google_sheets.sheet:
        return
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, google_sheets.full_sync)
        log.info(f"📤 Auto-backup: {result}")
    except Exception as e:
        log.error(f"Auto-backup error: {e}")


# ═══════════════════════════════════════════════════════════════════
# NATURAL LANGUAGE PROCESSOR — ye sab kaam karega bina buttons ke
# ═══════════════════════════════════════════════════════════════════

def extract_time_from_text(text):
    """Text se time extract karo — '5 baje', '3:30', '30 min mein' etc."""
    text = text.lower()

    # X minutes/hours mein
    m = _re.search(r'(\d+)\s*(min|minute|minut)', text)
    if m:
        mins = int(m.group(1))
        return (now_ist() + timedelta(minutes=mins)).strftime("%H:%M"), f"{mins}min"

    m = _re.search(r'(\d+)\s*(ghante|hour|hr)', text)
    if m:
        hrs = int(m.group(1))
        return (now_ist() + timedelta(hours=hrs)).strftime("%H:%M"), f"{hrs}hr"

    # HH:MM format
    m = _re.search(r'\b(\d{1,2}):(\d{2})\b', text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}", f"{h:02d}:{mi:02d}"

    # X baje / at X
    m = _re.search(r'(\d{1,2})\s*(baje|bajay|pm|am|:00)', text)
    if m:
        h = int(m.group(1))
        suffix = m.group(2)
        if "pm" in suffix and h != 12:
            h += 12
        if "am" in suffix and h == 12:
            h = 0
        return f"{h:02d}:00", f"{h:02d}:00"

    return None, None


def extract_amount_from_text(text):
    """Text se amount extract karo"""
    m = _re.search(r'(?:rs\.?|₹|rupees?|rupe)\s*(\d+(?:\.\d+)?)', text.lower())
    if m:
        return float(m.group(1))
    m = _re.search(r'(\d+(?:\.\d+)?)\s*(?:rs\.?|₹|rupees?|rupe)', text.lower())
    if m:
        return float(m.group(1))
    m = _re.search(r'\b(\d+(?:\.\d+)?)\b', text)
    if m:
        return float(m.group(1))
    return None


def detect_intent(text):
    """
    User ke message ka intent detect karo.
    Returns: (intent, data_dict)
    """
    t = text.lower().strip()

    # ── REMINDER ────────────────────────────────────────────────────
    remind_keywords = ["remind", "reminder", "alarm", "alert", "yaad", "yaad kara",
                       "remind kar", "bata", "bata dena", "bhool", "reminder set",
                       "set reminder", "mujhe yaad", "wake", "uthana"]
    if any(k in t for k in remind_keywords):
        time_val, time_label = extract_time_from_text(t)
        # Remove time-related words to get the reminder text
        reminder_text = _re.sub(
            r'\d+\s*(min|minute|ghante|hour|hr|baje|bajay|pm|am)\w*', '', t, flags=_re.I
        )
        reminder_text = _re.sub(
            r'\b(remind|reminder|alarm|yaad|kara|dena|mujhe|set|kar|please|plz|ko)\b',
            '', reminder_text
        ).strip()
        reminder_text = _re.sub(r'\s+', ' ', reminder_text).strip()
        if not reminder_text or len(reminder_text) < 3:
            reminder_text = text.strip()
        repeat = "daily" if any(w in t for w in ["daily", "roz", "har din", "everyday"]) else "once"
        return "reminder", {"time": time_val, "text": reminder_text or text, "repeat": repeat}

    # ── TASK ADD ────────────────────────────────────────────────────
    task_add_keywords = ["task", "kaam", "todo", "to-do", "add task", "naya kaam",
                         "karna hai", "karna hai mujhe", "list mein", "yaad rakh",
                         "note kar", "pending", "complete karna"]
    if any(k in t for k in task_add_keywords):
        priority = "high" if any(w in t for w in ["urgent", "jaldi", "important", "zaruri", "high"]) \
                   else "low" if any(w in t for w in ["low", "baad mein", "later"]) else "medium"
        title = _re.sub(
            r'\b(task|kaam|todo|add|naya|mujhe|karna|hai|please|plz|urgent|jaldi|important|zaruri)\b',
            '', t
        ).strip()
        title = _re.sub(r'\s+', ' ', title).strip()
        return "task_add", {"title": title or text.strip(), "priority": priority}

    # ── TASK DONE ────────────────────────────────────────────────────
    task_done_keywords = ["task done", "kaam ho gaya", "ho gaya", "complete", "kar liya",
                          "finish", "khatam", "done", "completed", "mark done"]
    if any(k in t for k in task_done_keywords):
        m = _re.search(r'#?(\d+)', t)
        if m:
            return "task_done", {"id": int(m.group(1))}
        # Try keyword match
        title_hint = _re.sub(
            r'\b(task|done|ho|gaya|complete|kar|liya|finish|khatam|mark)\b', '', t
        ).strip()
        return "task_done", {"id": None, "keyword": title_hint}

    # ── HABIT LOG ────────────────────────────────────────────────────
    habit_done_keywords = ["habit done", "habit kar li", "habit complete", "exercise kiya",
                           "meditation kiya", "padhai ki", "gym gaya", "running ki",
                           "hdone", "habit ho gaya"]
    if any(k in t for k in habit_done_keywords):
        m = _re.search(r'#?(\d+)', t)
        if m:
            return "habit_done", {"id": int(m.group(1))}
        keyword = _re.sub(
            r'\b(habit|done|complete|kiya|ki|gaya|ho|kar|li)\b', '', t
        ).strip()
        return "habit_done", {"keyword": keyword}

    # ── EXPENSE ────────────────────────────────────────────────────
    expense_keywords = ["kharcha", "kharch", "spent", "spend", "khaya", "piya", "kharida",
                        "buy", "bought", "paid", "payment", "expense", "rupees", "rs",
                        "₹", "paisa", "paise"]
    if any(k in t for k in expense_keywords):
        amount = extract_amount_from_text(t)
        desc = _re.sub(
            r'(?:rs\.?|₹|rupees?|rupe|\d+(?:\.\d+)?|\b(kharcha|kharch|spent|spend|kharida|buy|bought|paid|payment|expense|paisa|paise|ka|ke|ki|mein|pr|par)\b)',
            '', t, flags=_re.I
        ).strip()
        desc = _re.sub(r'\s+', ' ', desc).strip()
        return "expense", {"amount": amount, "desc": desc or "Expense"}

    # ── WATER ────────────────────────────────────────────────────────
    water_keywords = ["paani piya", "water piya", "paani pi", "water pi", "water log",
                      "paani log", "glass paani", "bottle paani"]
    if any(k in t for k in water_keywords):
        m = _re.search(r'(\d+)\s*(ml|liter|litre|glass|bottle)', t)
        ml = 250
        if m:
            val = int(m.group(1))
            unit = m.group(2)
            if "liter" in unit or "litre" in unit:
                ml = val * 1000
            elif "glass" in unit:
                ml = val * 250
            elif "bottle" in unit:
                ml = val * 500
            else:
                ml = val
        return "water", {"ml": ml}

    # ── DIARY READ ────────────────────────────────────────────────────
    diary_read_keywords = ["diary dekho", "diary dikhao", "diary padho", "diary kya hai",
                           "aaj ki diary", "kal ki diary", "diary view", "diary open"]
    if any(k in t for k in diary_read_keywords):
        if "week" in t or "hafte" in t:
            return "diary_read", {"mode": "week"}
        elif "all" in t or "poori" in t or "sab" in t:
            return "diary_read", {"mode": "all"}
        return "diary_read", {"mode": "today"}

    # ── STATUS / BRIEFING ────────────────────────────────────────────
    status_keywords = ["kya chal", "aaj kya", "status", "briefing", "update", "summary",
                       "aaj ka", "batao", "kya karna hai", "pending kya", "schedule"]
    if any(k in t for k in status_keywords):
        return "briefing", {}

    # No specific intent — normal chat
    return "chat", {}


# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════
def build_system_prompt():
    tp    = tasks.today_pending()
    hd, hp = habits.today_status()
    ag    = goals.active()
    exp_t = expenses.today_total()
    exp_m = expenses.month_total()
    bl    = expenses.budget_left()
    wt    = water.today_total()
    wg    = water.goal()
    active_reminders = reminders.all_active()

    tasks_s = "\n".join(
        f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} #{t['id']} {t['title']}"
        for t in tp[:5]
    ) or "  Koi nahi"
    h_done = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    h_pend = ", ".join(f"#{h['id']} {h['name']}" for h in hp) or "Sab ho gaye!"
    goals_s = "\n".join(
        f"  🎯 #{g['id']} {g['title']} ({g['progress']}%)" for g in ag[:4]
    ) or "  Koi nahi"
    reminders_s = "\n".join(
        f"  ⏰ #{r['id']} {r['time']} — {r['text']}" for r in active_reminders[:5]
    ) or "  Koi nahi"
    budget_s = f"| Budget baaki: ₹{bl:.0f}" if bl is not None else ""

    return (
        f"Tu mera Personal AI Assistant hai — naam 'Dost'. Hamesha Hindi/Hinglish mein baat kar.\n"
        f"Tera kaam sirf jawab dena nahi — KAAM KARNA hai. User jo bolega woh actually hona chahiye.\n"
        f"⚠️ REAL TIME: {now_ist().strftime('%A, %d %b %Y — %I:%M %p')} IST\n\n"
        f"📋 AAJ KE TASKS ({len(tp)}):\n{tasks_s}\n\n"
        f"💪 HABITS: Done: {h_done} | Baaki: {h_pend}\n\n"
        f"💰 KHARCHA: Aaj ₹{exp_t} | Mahina ₹{exp_m} {budget_s}\n\n"
        f"🎯 GOALS ({len(ag)}):\n{goals_s}\n\n"
        f"⏰ REMINDERS ({len(active_reminders)}):\n{reminders_s}\n\n"
        f"💧 PAANI: {wt}ml/{wg}ml\n\n"
        f"RULES:\n"
        f"- Dost ki tarah baat kar, Hindi/Hinglish mein SHORT jawab (2-4 lines)\n"
        f"- Kaam ho gaya toh confirm karo clearly\n"
        f"- Agar kuch add/save/set hua toh batao ID bhi\n"
        f"- Commands yaad dilao agar needed: /task /remind /kharcha /diary /habit\n"
        f"- Koi button use mat karo — sab chat se hoga"
    )


# ═══════════════════════════════════════════════════════════════════
# AI CHAT — Context-aware with intent detection
# ═══════════════════════════════════════════════════════════════════
async def ai_chat(user_msg, chat_id=None, user_name=""):
    # Recent context add karo prompt mein
    recent = chat_hist.get_recent(6)
    context_str = ""
    if recent:
        context_lines = []
        for h in recent[-6:]:
            role_label = "User" if h["role"] == "user" else "Dost"
            context_lines.append(f"{role_label}: {h['message'][:100]}")
        context_str = "\n\nHALI BAAT:\n" + "\n".join(context_lines)

    prompt = build_system_prompt() + context_str + f"\n\nUser: {user_msg}\n\nShort Hindi reply:"
    reply = call_gemini(prompt)
    if not reply:
        n = now_ist()
        msg = user_msg.lower()
        if any(w in msg for w in ["time", "baje", "kitne"]):
            reply = f"⏰ Abhi *{n.strftime('%I:%M %p')}* baj rahe hain (IST)"
        elif any(w in msg for w in ["hello", "hi", "assalam", "salam"]):
            reply = f"🕌 *Assalamualaikum!* Batao kaisi help chahiye?"
        else:
            reply = "🙏 Kuch samajh nahi aaya. `/help` try karo!"
    return reply


# ═══════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Dost"
    n = now_ist()
    await update.message.reply_text(
        f"🕌 *Assalamualaikum {name}!*\n\n"
        f"⏰ {n.strftime('%I:%M %p')} IST\n"
        f"📅 {n.strftime('%d %b %Y')}\n\n"
        f"Main aapka AI Dost hoon! Seedha baat karo — kaam ho jaayega.\n\n"
        f"Kuch bhi likho jaise:\n"
        f"• 'Kal meeting hai 3 baje remind karna'\n"
        f"• 'Exercise kharcha 500 rupees'\n"
        f"• 'Gym ka kaam add kar'\n\n"
        f"Ya commands use karo:\n"
        f"📋 /task /done /habit /remind /kharcha /diary /help",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *COMMANDS*\n\n"
        "🗣 *Natural Chat se karo:*\n"
        "  'Kal 9 baje doctor reminder'\n"
        "  'Chai pe 50 rupees kharcha'\n"
        "  '30 min mein meeting yaad dilana'\n"
        "  'Exercise habit ho gayi aaj'\n\n"
        "⚡ *Commands:*\n"
        "`/task Kaam [high/low]` — Task add\n"
        "`/done <id>` — Task complete\n"
        "`/deltask <id>` — Task delete\n"
        "`/habit Naam` — Habit add\n"
        "`/hdone <id>` — Habit log\n"
        "`/remind 30m Chai` ya `/remind 15:30 Meeting`\n"
        "`/kharcha 100 Chai` — Expense\n"
        "`/budget 5000` — Budget set\n"
        "`/diary` — Diary (password required)\n"
        "`/save Aaj ka din...` — Quick diary save\n"
        "`/water 250` — Paani log\n"
        "`/goal Title` — Goal add\n"
        "`/remember Note` — Memory\n"
        "`/briefing` — Aaj ka summary\n"
        "`/backup` — Google Sheets sync\n"
        "`/help` — Ye menu",
        parse_mode="Markdown"
    )


async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(
                f"{'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} "
                f"#{t['id']} {t['title']}"
                for t in pending[:15]
            )
            await update.message.reply_text(
                f"📋 *Pending Tasks ({len(pending)}):*\n\n{lines}\n\n"
                f"_Complete karne ke liye: /done <id>_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("📋 `/task Kaam [high/low]`", parse_mode="Markdown")
        return
    args = " ".join(ctx.args)
    priority = "medium"
    if args.endswith(" high"):
        priority = "high"; args = args[:-5].strip()
    elif args.endswith(" low"):
        priority = "low";  args = args[:-4].strip()
    t = tasks.add(args, priority)
    e = "🔴" if priority == "high" else "🟡" if priority == "medium" else "🟢"
    await update.message.reply_text(
        f"✅ Task added!\n{e} *{t['title']}*\n🆔 `#{t['id']}`",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} — {t['title']}" for t in pending[:15])
            await update.message.reply_text(
                f"📋 *Pending ({len(pending)}):*\n\n{lines}\n\n"
                f"_Likhao: /done <id>_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("🎉 Koi pending task nahi!")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        await update.message.reply_text(
            f"🎉 *Done!* ✅\n{t['title']}" if t else "❌ Not found!",
            parse_mode="Markdown"
        )
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")


async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("`/deltask <id>`")
        return
    tasks.delete(int(ctx.args[0]))
    await update.message.reply_text("🗑 Task deleted!")
    await auto_backup_to_sheets()


# ═══════════════════════════════════════════════════════════════════
# DIARY — ConversationHandler (password required, no buttons)
# ═══════════════════════════════════════════════════════════════════

async def cmd_diary_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or []

    if not args:
        await update.message.reply_text(
            "📖 *Diary*\n\n"
            "Kya karna hai?\n"
            "• `/diary` — Aaj ki diary\n"
            "• `/diary week` — Hafte ki\n"
            "• `/diary all` — Poori\n"
            "• `/diary write` — Naya likhna\n\n"
            "_Password hamesha maanga jaayega_",
            parse_mode="Markdown"
        )
        ctx.user_data["diary_mode"] = "view_today"
        await update.message.reply_text(
            "🔐 *Password daalo:*\n_/cancel se bahar jao_",
            parse_mode="Markdown"
        )
        return DIARY_AWAIT_PASS

    first = args[0].lower()
    if first == "write":
        ctx.user_data["diary_mode"] = "write"
    elif first == "week":
        ctx.user_data["diary_mode"] = "view_week"
    elif first == "all":
        ctx.user_data["diary_mode"] = "view_all"
    else:
        ctx.user_data["diary_mode"] = "write"
        ctx.user_data["diary_pending_text"] = " ".join(args)

    await update.message.reply_text(
        "🔐 *Password daalo:*\n_/cancel se bahar jao_",
        parse_mode="Markdown"
    )
    return DIARY_AWAIT_PASS


async def diary_password_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END

    entered = update.message.text.strip()

    try:
        await update.message.delete()
    except Exception:
        pass

    if entered != DIARY_PASSWORD:
        await update.effective_chat.send_message(
            "❌ *Galat Password!*\n_Dobara: /diary_",
            parse_mode="Markdown"
        )
        ctx.user_data.pop("diary_mode", None)
        ctx.user_data.pop("diary_pending_text", None)
        return ConversationHandler.END

    mode = ctx.user_data.get("diary_mode", "view_today")

    if mode == "write":
        pending = ctx.user_data.get("diary_pending_text", "")
        if pending:
            await _do_save_diary(update, ctx, pending)
            return ConversationHandler.END
        else:
            await update.effective_chat.send_message(
                "✏️ *Diary mein likho:*\n\n_Dil ki baat..._\n_/cancel se bahar_",
                parse_mode="Markdown"
            )
            return DIARY_AWAIT_TEXT
    else:
        await _show_diary(update, ctx, mode)
        return ConversationHandler.END


async def diary_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END
    text = update.message.text.strip()
    await _do_save_diary(update, ctx, text)
    return ConversationHandler.END


async def _do_save_diary(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    diary.add(text, mood="📝")
    try:
        if update.message:
            await update.message.delete()
    except Exception:
        pass
    try:
        conf_msg = await update.effective_chat.send_message(
            f"📖 *Diary Saved!* ✅\n"
            f"🕐 {now_str()}\n\n"
            f"_{text[:120]}{'...' if len(text) > 120 else ''}_",
            parse_mode="Markdown"
        )
        asyncio.create_task(auto_backup_to_sheets())
        await asyncio.sleep(4)
        try:
            await conf_msg.delete()
        except Exception:
            pass
    except Exception as e:
        log.error(f"_do_save_diary error: {e}")
    ctx.user_data.pop("diary_mode", None)
    ctx.user_data.pop("diary_pending_text", None)


async def _show_diary(update: Update, ctx: ContextTypes.DEFAULT_TYPE, mode: str):
    if mode == "view_today":
        entries = diary.get(today_str())
        all_entries = {today_str(): entries} if entries else {}
        title = f"📖 *Aaj Ki Diary — {today_str()}*"
    elif mode == "view_week":
        n = now_ist()
        all_entries = {}
        for i in range(7):
            d = (n - timedelta(days=i)).strftime("%Y-%m-%d")
            e = diary.get(d)
            if e:
                all_entries[d] = e
        title = "📖 *Is Hafte Ki Diary*"
    elif mode == "view_all":
        all_entries = diary.get_all_entries()
        title = f"📖 *Puri Diary ({len(all_entries)} din)*"
    else:
        all_entries = {}
        title = "📖 *Diary*"

    if not all_entries or not any(all_entries.values()):
        await update.effective_chat.send_message(
            f"{title}\n\n_Koi entry nahi mili._\n\n_Likhne ke liye:_ `/diary write`",
            parse_mode="Markdown"
        )
        return

    chunks, current = [], f"{title}\n{'━'*25}\n\n"
    for dk in sorted(all_entries.keys(), reverse=True):
        if not all_entries[dk]:
            continue
        block = f"📅 *{dk}*\n"
        for e in all_entries[dk]:
            block += f"📝 `{e.get('time','')}` — {e.get('text','')}\n"
        block += "\n"
        if len(current) + len(block) > 3800:
            chunks.append(current)
            current = block
        else:
            current += block
    if current.strip():
        chunks.append(current)

    for chunk in chunks:
        try:
            await update.effective_chat.send_message(chunk, parse_mode="Markdown")
        except Exception:
            await update.effective_chat.send_message(chunk)


async def diary_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("diary_mode", None)
    ctx.user_data.pop("diary_pending_text", None)
    if update.message:
        await update.message.reply_text("⏱ Diary cancel. _Dobara: /diary_")
    return ConversationHandler.END


async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Quick diary save — no password"""
    if not ctx.args:
        await update.message.reply_text(
            "📖 `/save Aaj ka din acha tha...`\n\n"
            "_Password ke saath save: /diary write_",
            parse_mode="Markdown"
        )
        return
    text = " ".join(ctx.args)
    await _do_save_diary(update, ctx, text)


# ═══════════════════════════════════════════════════════════════════
# REMAINING COMMANDS
# ═══════════════════════════════════════════════════════════════════

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        all_h = habits.all()
        hd, hp = habits.today_status()
        if all_h:
            lines = "\n".join(
                f"{'✅' if h in hd else '⬜'} #{h['id']} {h['emoji']} {h['name']} 🔥{h['streak']}"
                for h in all_h
            )
            await update.message.reply_text(
                f"💪 *Habits ({len(all_h)}):*\n\n{lines}\n\n"
                f"_Done karne ke liye: /hdone <id>_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("💪 `/habit Naam` — Habit add karo", parse_mode="Markdown")
        return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(
        f"💪 Habit added!\n{h['emoji']} *{h['name']}*\n🆔 `#{h['id']}`\n\n_Done karne ke liye: /hdone {h['id']}_",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            lines = "\n".join(f"⬜ #{h['id']} {h['name']}" for h in pending)
            await update.message.reply_text(
                f"💪 *Pending Habits:*\n\n{lines}\n\n_Likhao: /hdone <id>_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("🎊 Aaj ki saari habits complete!")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        await update.message.reply_text(
            f"💪 *Habit Done!* 🔥 {streak} din streak!" if ok else "✅ Already done!",
            parse_mode="Markdown"
        )
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")


async def cmd_delhabit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("`/delhabit <id>`")
        return
    habits.delete(int(ctx.args[0]))
    await update.message.reply_text("🗑 Habit deleted!")
    await auto_backup_to_sheets()


async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 2:
        today_list = expenses.get_by_date(today_str())
        if today_list:
            lines = "\n".join(f"₹{e['amount']:.0f} — {e['desc']}" for e in today_list[-10:])
            await update.message.reply_text(
                f"💰 *Aaj Ka Kharcha:*\n\n{lines}\n\n"
                f"*Total: ₹{expenses.today_total():.0f}*\n\n"
                f"_Add karne ke liye: /kharcha 100 Chai_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("💰 `/kharcha amount description`")
        return
    try:
        amount = float(ctx.args[0])
        desc   = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        bl = expenses.budget_left()
        budget_line = f"\n💳 Budget baaki: ₹{bl:.0f}" if bl is not None else ""
        await update.message.reply_text(
            f"💰 ₹{amount:.0f} — {desc}\n📊 Aaj total: ₹{expenses.today_total():.0f}{budget_line}",
            parse_mode="Markdown"
        )
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ `/kharcha 100 Chai`")


async def cmd_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        b = expenses.store.data.get("budget", 0)
        bl = expenses.budget_left()
        await update.message.reply_text(
            f"💳 *Budget:* ₹{b}\n"
            f"💰 Is mahine: ₹{expenses.month_total():.0f}\n"
            f"✅ Baaki: ₹{bl:.0f}" if bl is not None else f"💳 Budget: ₹{b}\n`/budget 5000`",
            parse_mode="Markdown"
        )
        return
    expenses.set_budget(float(ctx.args[0]))
    await update.message.reply_text(f"💳 Budget set: ₹{ctx.args[0]}")
    await auto_backup_to_sheets()


async def cmd_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        active = goals.active()
        if active:
            lines = "\n".join(f"#{g['id']} {g['title']} — {g['progress']}%" for g in active)
            await update.message.reply_text(
                f"🎯 *Active Goals ({len(active)}):*\n\n{lines}\n\n"
                f"_Progress update: /gprogress <id> <percent>_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("🎯 `/goal Description`")
        return
    g = goals.add(" ".join(ctx.args))
    await update.message.reply_text(
        f"🎯 Goal set!\n#{g['id']} {g['title']}",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_gprogress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text("📊 `/gprogress <id> <percent>`")
        return
    try:
        g = goals.update_progress(int(ctx.args[0]), int(ctx.args[1]))
        await update.message.reply_text(
            f"📊 *{g['title']}* — {g['progress']}%\n"
            f"{'🎉 Completed!' if g['done'] else '💪 Keep going!'}" if g else "❌ Not found!",
            parse_mode="Markdown"
        )
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ Invalid!")


async def cmd_remember(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🧠 `/remember Note`")
        return
    memory.add_fact(" ".join(ctx.args))
    await update.message.reply_text("🧠 Yaad kar liya! ✅")
    await auto_backup_to_sheets()


async def cmd_recall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("🧠 Kuch yaad nahi.")
        return
    lines = "\n".join(f"📌 {f['f']}" for f in facts[-15:])
    await update.message.reply_text(f"🧠 *Memory:*\n\n{lines}", parse_mode="Markdown")


async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n = now_ist()
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    today_ev = calendar.today_events()
    active_rem = reminders.all_active()

    ev_line = f"\n📅 Events: {', '.join(e['title'] for e in today_ev[:3])}" if today_ev else ""
    rem_line = f"\n⏰ Reminders: {len(active_rem)} active" if active_rem else ""

    await update.message.reply_text(
        f"🌅 *BRIEFING — {n.strftime('%d %b %Y')}*\n"
        f"⏰ {n.strftime('%I:%M %p')} IST\n\n"
        f"📋 Tasks pending: {len(tp)}\n"
        f"💪 Habits done: {len(hd)}/{len(hd)+len(hp)}\n"
        f"💰 Aaj kharcha: ₹{expenses.today_total():.0f}\n"
        f"💧 Water: {water.today_total()}ml/{water.goal()}ml"
        f"{ev_line}{rem_line}",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_weekly(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n = now_ist()
    tw = tasks.get_weekly_summary()
    await update.message.reply_text(
        f"📊 *WEEKLY SUMMARY*\n\n"
        f"📋 Tasks done: {sum(v['done'] for v in tw.values())}\n"
        f"💰 Month kharcha: ₹{expenses.month_total():.0f}\n"
        f"💧 Aaj paani: {water.today_total()}ml",
        parse_mode="Markdown"
    )


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📋 `/report YYYY-MM-DD`")
        return
    target = ctx.args[0]
    try:
        datetime.strptime(target, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("❌ Invalid date! Format: YYYY-MM-DD")
        return
    exp_t = sum(e["amount"] for e in expenses.get_by_date(target))
    hl    = habits.get_logs_by_date(target)
    hd    = [h for h in habits.all() if h["id"] in hl]
    wt    = sum(w["ml"] for w in water.get_by_date(target))
    await update.message.reply_text(
        f"📋 *REPORT {target}*\n\n"
        f"✅ Tasks done: {len(tasks.done_on(target))}\n"
        f"💰 Kharcha: ₹{exp_t:.0f}\n"
        f"📖 Diary: {len(diary.get(target))} entries\n"
        f"💪 Habits: {len(hd)}/{len(habits.all())}\n"
        f"💧 Water: {wt}ml",
        parse_mode="Markdown"
    )


async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        req = urllib.request.Request(
            "https://feeds.bbci.co.uk/hindi/rss.xml",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            items = ET.parse(resp).getroot().find("channel").findall("item")[:5]
            lines = "\n\n".join(
                f"• *{item.findtext('title','')}*"
                for item in items if item.findtext('title','')
            )
            await update.message.reply_text(
                f"📰 *INDIA NEWS*\n\n{lines}",
                parse_mode="Markdown"
            )
    except Exception:
        await update.message.reply_text("📰 News unavailable.")


async def cmd_alltasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    p = tasks.pending()
    if not p:
        await update.message.reply_text("📋 Koi pending task nahi! 🎉")
        return
    lines = "\n".join(
        f"{'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} "
        f"#{t['id']} {t['title']}"
        for t in p[:20]
    )
    await update.message.reply_text(
        f"📋 *All Pending Tasks ({len(p)}):*\n\n{lines}",
        parse_mode="Markdown"
    )


async def cmd_completed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    c = tasks.completed_tasks()
    if not c:
        await update.message.reply_text("✅ Abhi tak koi task complete nahi!")
        return
    lines = "\n".join(f"✓ #{t['id']} {t['title']}" for t in c[-15:])
    await update.message.reply_text(
        f"✅ *Completed ({len(c)}):*\n\n{lines}",
        parse_mode="Markdown"
    )


async def cmd_yesterday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    yd    = yesterday_str()
    exp_t = sum(e["amount"] for e in expenses.get_by_date(yd))
    hl    = habits.get_logs_by_date(yd)
    hd    = [h for h in habits.all() if h["id"] in hl]
    await update.message.reply_text(
        f"📅 *Kal ({yd}):*\n\n"
        f"✅ Tasks done: {len(tasks.done_on(yd))}\n"
        f"💪 Habits: {len(hd)}/{len(habits.all())}\n"
        f"💰 Kharcha: ₹{exp_t:.0f}",
        parse_mode="Markdown"
    )


async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = now_ist()
    if not ctx.args:
        active = reminders.all_active()
        if active:
            lines = "\n".join(
                f"⏰ #{r['id']} `{r['time']}` — {r['text']} ({r.get('repeat','once')})"
                for r in active
            )
            await update.message.reply_text(
                f"⏰ *Active Reminders ({len(active)}):*\n\n{lines}\n\n"
                f"_Add: /remind 30m Chai | /remind 15:30 Meeting_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "⏰ `/remind 2m Test` | `/remind 30m Chai` | `/remind 15:30 Doctor`",
                parse_mode="Markdown"
            )
        return

    time_arg = ctx.args[0].lower()
    rest = list(ctx.args[1:])
    repeat = "once"
    if rest and rest[-1].lower() in ["daily", "weekly", "roz"]:
        repeat = "daily" if rest[-1].lower() in ["daily", "roz"] else "weekly"
        rest = rest[:-1]
    text = " ".join(rest) if rest else "⏰ Reminder!"

    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        remind_at = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif time_arg.endswith("h") and time_arg[:-1].isdigit():
        remind_at = (now + timedelta(hours=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        parts = time_arg.split(":")
        if len(parts) == 2 and parts[0].isdigit() and 0 <= int(parts[0]) <= 23:
            remind_at = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        else:
            await update.message.reply_text("❌ Invalid time!")
            return
    else:
        await update.message.reply_text("❌ `/remind 30m Chai` ya `/remind 15:30 Meeting`")
        return

    r = reminders.add(update.effective_chat.id, text, remind_at, repeat)
    await update.message.reply_text(
        f"✅ *Reminder Set!*\n"
        f"⏰ {remind_at} — {text}\n"
        f"🆔 `#{r['id']}` | {repeat}",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_reminders_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    active = reminders.all_active()
    if not active:
        await update.message.reply_text("⏰ Koi active reminder nahi!")
        return
    lines = "\n".join(
        f"*#{r['id']}* `{r['time']}` — {r['text']} ({r.get('repeat','once')})"
        for r in active
    )
    await update.message.reply_text(
        f"⏰ *Active Reminders ({len(active)}):*\n\n{lines}\n\n"
        f"_Delete: /delremind <id>_",
        parse_mode="Markdown"
    )


async def cmd_delremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("`/delremind <id>`")
        return
    reminders.delete(int(ctx.args[0]))
    await update.message.reply_text("🗑 Reminder deleted!")
    await auto_backup_to_sheets()


async def cmd_water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ml = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 250
    water.add(ml)
    total = water.today_total()
    goal  = water.goal()
    pct   = int(total / goal * 100) if goal else 0
    bar   = "💧" * min(10, pct // 10) + "⬜" * (10 - min(10, pct // 10))
    await update.message.reply_text(
        f"💧 +{ml}ml logged!\n{bar}\n{total}ml / {goal}ml ({pct}%)",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_water_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    total = water.today_total()
    goal  = water.goal()
    pct   = int(total / goal * 100) if goal else 0
    bar   = "💧" * min(10, pct // 10) + "⬜" * (10 - min(10, pct // 10))
    await update.message.reply_text(
        f"💧 *Water Status*\n{bar}\n{total}ml / {goal}ml ({pct}%)",
        parse_mode="Markdown"
    )


async def cmd_water_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args and ctx.args[0].isdigit():
        water.set_goal(int(ctx.args[0]))
        await update.message.reply_text(f"✅ Water goal set: {ctx.args[0]}ml")
    else:
        await update.message.reply_text(f"💧 Current goal: {water.goal()}ml\n`/watergoal 2500`")


async def cmd_bill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 3:
        await update.message.reply_text("💳 `/bill Name Amount DueDay`\nExample: `/bill Netflix 299 5`")
        return
    try:
        b = bills.add(ctx.args[0], float(ctx.args[1]), int(ctx.args[2]))
        await update.message.reply_text(
            f"✅ Bill added!\n💳 {b['name']} — ₹{b['amount']:.0f}\n📅 Due: {b['due_day']}th every month",
            parse_mode="Markdown"
        )
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ `/bill Netflix 299 5`")


async def cmd_bills_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    all_b = bills.all_active()
    if not all_b:
        await update.message.reply_text("💳 Koi bill nahi!\n`/bill Name Amount DueDay`")
        return
    lines = "\n".join(
        f"{'✅' if bills.is_paid_this_month(b['id']) else '⏳'} "
        f"#{b['id']} *{b['name']}* — ₹{b['amount']:.0f} (Due {b['due_day']}th)"
        for b in all_b
    )
    await update.message.reply_text(
        f"💳 *Bills ({len(all_b)}):*\n\n{lines}\n\n"
        f"_Paid mark: /billpaid <id>_",
        parse_mode="Markdown"
    )


async def cmd_bill_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("`/billpaid <id>`")
        return
    try:
        ok = bills.mark_paid(int(ctx.args[0]))
        await update.message.reply_text("✅ Bill paid!" if ok else "⚠️ Already marked paid!")
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")


async def cmd_del_bill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("`/delbill <id>`")
        return
    bills.delete(int(ctx.args[0]))
    await update.message.reply_text("🗑 Bill deleted!")
    await auto_backup_to_sheets()


async def cmd_cal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        upcoming = calendar.upcoming(30)
        if upcoming:
            lines = "\n".join(
                f"{'🔴' if e['date']==today_str() else '📆'} {e['date']} — {e['title']}"
                for e in upcoming[:10]
            )
            await update.message.reply_text(
                f"📅 *Upcoming Events:*\n\n{lines}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`")
        return

    args_str = " ".join(ctx.args)
    date_str = None
    title    = args_str

    m = _re.match(r'^(\d{4}-\d{2}-\d{2})\s+(.*)', args_str)
    if m:
        date_str, title = m.group(1), m.group(2)
    if not date_str:
        if args_str.lower().startswith("aaj "):
            date_str = today_str(); title = args_str[4:]
        elif args_str.lower().startswith("kal "):
            date_str = (now_ist().date() + timedelta(days=1)).isoformat()
            title = args_str[4:]
    if not date_str:
        await update.message.reply_text("❌ `/cal 2025-07-15 Meeting`")
        return

    event_time = ""
    t_match = _re.search(r'(\d{1,2}:\d{2})', title)
    if t_match:
        event_time = t_match.group(1)
        title = title.replace(event_time, "").strip()

    try:
        date.fromisoformat(date_str)
        e = calendar.add(title, date_str, event_time)
        await update.message.reply_text(
            f"📅 Event added!\n#{e['id']} {title} — {date_str}"
            + (f" ⏰{event_time}" if event_time else ""),
            parse_mode="Markdown"
        )
        await auto_backup_to_sheets()
    except ValueError:
        await update.message.reply_text("❌ Invalid date format!")


async def cmd_cal_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    upcoming = calendar.upcoming(30)
    if not upcoming:
        await update.message.reply_text("📅 Koi upcoming event nahi!")
        return
    lines = "\n".join(
        f"{'🔴' if e['date']==today_str() else '📆'} {e['date']} — {e['title']}"
        for e in upcoming[:10]
    )
    await update.message.reply_text(
        f"📅 *Upcoming Events:*\n\n{lines}",
        parse_mode="Markdown"
    )


async def cmd_del_cal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("`/delcal <id>`")
        return
    calendar.delete(int(ctx.args[0]))
    await update.message.reply_text("🗑 Event deleted!")
    await auto_backup_to_sheets()


async def cmd_memory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("🧠 Memory empty!\n`/remember Note`")
        return
    lines = "\n".join(f"📌 {f['f']}" for f in facts[-15:])
    await update.message.reply_text(f"🧠 *Memory:*\n\n{lines}", parse_mode="Markdown")


async def cmd_backup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📤 Backup shuru ho raha hai...")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, google_sheets.full_sync)
    await update.message.reply_text(result)


async def cmd_dbstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    r  = len(reminders.get_all())
    t  = len(tasks.all_tasks())
    d  = sum(len(v) for v in diary.get_all_entries().values())
    e  = len(expenses.store.data.get("list", []))
    ch = len(chat_hist.get_all())
    await update.message.reply_text(
        f"📊 *DB STATUS*\n\n"
        f"Sheets: {'🟢 Connected' if google_sheets.sheet else '🔴 Disconnected'}\n\n"
        f"Reminders: {r}\nTasks: {t}\nDiary entries: {d}\n"
        f"Expenses: {e}\nChat history: {ch}",
        parse_mode="Markdown"
    )


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    count = chat_hist.clear()
    await update.message.reply_text(f"🧹 {count} chat messages cleared!")


# ═══════════════════════════════════════════════════════════════════
# MAIN MESSAGE HANDLER — Natural Language Processing
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_msg  = update.message.text.strip()
    user_name = update.effective_user.first_name or "User"
    chat_id   = update.effective_chat.id

    if user_msg.startswith("/"):
        return

    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Intent detect karo
    intent, data = detect_intent(user_msg)

    # ── REMINDER ────────────────────────────────────────────────────
    if intent == "reminder":
        time_val  = data.get("time")
        rem_text  = data.get("text", user_msg)
        repeat    = data.get("repeat", "once")

        if not time_val:
            # Time nahi mili — AI se poochho
            reply = await ai_chat(user_msg, chat_id, user_name)
            reply += "\n\n_Time format: '30 min mein', '3 baje', '15:30'_"
        else:
            r = reminders.add(chat_id, rem_text, time_val, repeat)
            reply = (
                f"✅ *Reminder Set!*\n"
                f"⏰ {time_val} — {rem_text}\n"
                f"🆔 #{r['id']} | {repeat}"
            )
            await auto_backup_to_sheets()

    # ── TASK ADD ────────────────────────────────────────────────────
    elif intent == "task_add":
        title    = data.get("title", user_msg)
        priority = data.get("priority", "medium")
        if len(title) < 2:
            title = user_msg
        t = tasks.add(title, priority)
        e = "🔴" if priority == "high" else "🟡" if priority == "medium" else "🟢"
        reply = f"✅ Task added!\n{e} *{t['title']}*\n🆔 #{t['id']}"
        await auto_backup_to_sheets()

    # ── TASK DONE ────────────────────────────────────────────────────
    elif intent == "task_done":
        tid = data.get("id")
        if tid:
            t = tasks.complete(tid)
        else:
            kw = data.get("keyword", "")
            t  = tasks.complete_by_title(kw) if kw else None

        if t:
            reply = f"🎉 *Done!* ✅\n{t['title']}"
            await auto_backup_to_sheets()
        else:
            pending = tasks.pending()
            if pending:
                lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:8])
                reply = f"📋 *Kaun sa task done hua?*\n\n{lines}\n\n_/done <id> likhao_"
            else:
                reply = "Koi pending task nahi!"

    # ── HABIT DONE ────────────────────────────────────────────────────
    elif intent == "habit_done":
        hid = data.get("id")
        if hid:
            ok, streak = habits.log(hid)
            h_obj = next((h for h in habits.all() if h["id"] == hid), None)
            h_name = h_obj["name"] if h_obj else f"#{hid}"
        else:
            kw = data.get("keyword", "")
            result = habits.log_by_name(kw)
            ok, streak, h_obj = result if len(result) == 3 else (result[0], result[1], None)
            h_name = h_obj["name"] if h_obj else kw

        if ok:
            reply = f"💪 *{h_name} done!* 🔥 {streak} din streak!"
            await auto_backup_to_sheets()
        else:
            _, pending = habits.today_status()
            if pending:
                lines = "\n".join(f"#{h['id']} {h['name']}" for h in pending[:5])
                reply = f"⬜ *Pending habits:*\n\n{lines}\n\n_/hdone <id> likhao_"
            else:
                reply = "🎊 Sab habits ho gayi aaj!"

    # ── EXPENSE ────────────────────────────────────────────────────
    elif intent == "expense":
        amount = data.get("amount")
        desc   = data.get("desc", "Expense")
        if amount:
            expenses.add(amount, desc)
            bl = expenses.budget_left()
            budget_line = f"\n💳 Budget baaki: ₹{bl:.0f}" if bl is not None else ""
            reply = (
                f"💰 ₹{amount:.0f} — {desc}\n"
                f"📊 Aaj total: ₹{expenses.today_total():.0f}{budget_line}"
            )
            await auto_backup_to_sheets()
        else:
            reply = "💰 Amount clear nahi hua.\n_Example: '50 rupees chai pe kharcha'_"

    # ── WATER ────────────────────────────────────────────────────────
    elif intent == "water":
        ml    = data.get("ml", 250)
        water.add(ml)
        total = water.today_total()
        goal  = water.goal()
        pct   = int(total / goal * 100) if goal else 0
        bar   = "💧" * min(10, pct // 10) + "⬜" * (10 - min(10, pct // 10))
        reply = f"💧 +{ml}ml!\n{bar}\n{total}ml / {goal}ml ({pct}%)"
        await auto_backup_to_sheets()

    # ── DIARY READ ────────────────────────────────────────────────────
    elif intent == "diary_read":
        mode = data.get("mode", "today")
        # Diary ke liye password check
        ctx.user_data["diary_mode"] = f"view_{mode}"
        await update.message.reply_text(
            "🔐 *Diary password daalo:*",
            parse_mode="Markdown"
        )
        ctx.user_data["diary_awaiting_pass_inline"] = True
        chat_hist.add("user", user_msg, user_name)
        return

    # ── BRIEFING ────────────────────────────────────────────────────
    elif intent == "briefing":
        n = now_ist()
        tp = tasks.today_pending()
        hd, hp = habits.today_status()
        reply = (
            f"🌅 *Aaj Ka Status*\n"
            f"⏰ {n.strftime('%I:%M %p')}\n\n"
            f"📋 Tasks pending: {len(tp)}\n"
            f"💪 Habits done: {len(hd)}/{len(hd)+len(hp)}\n"
            f"💰 Aaj kharcha: ₹{expenses.today_total():.0f}\n"
            f"💧 Water: {water.today_total()}ml/{water.goal()}ml\n"
            f"⏰ Reminders: {len(reminders.all_active())} active"
        )

    # ── NORMAL AI CHAT ────────────────────────────────────────────────
    else:
        reply = await ai_chat(user_msg, chat_id, user_name)

    # Save history
    chat_hist.add("user", user_msg, user_name)
    chat_hist.add("assistant", reply, "Bot")

    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(reply)

    await auto_backup_to_sheets()


# Inline diary password (outside ConversationHandler)
async def handle_inline_diary_pass(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Natural language se diary read ke liye password handler"""
    if not ctx.user_data.get("diary_awaiting_pass_inline"):
        return False

    if not update.message:
        return False

    entered = update.message.text.strip()
    ctx.user_data.pop("diary_awaiting_pass_inline", None)

    try:
        await update.message.delete()
    except Exception:
        pass

    if entered != DIARY_PASSWORD:
        await update.effective_chat.send_message(
            "❌ *Galat Password!*\n_Dobara: /diary_",
            parse_mode="Markdown"
        )
        ctx.user_data.pop("diary_mode", None)
        return True

    mode = ctx.user_data.pop("diary_mode", "view_today")
    await _show_diary(update, ctx, mode)
    return True


# ═══════════════════════════════════════════════════════════════════
# BACKGROUND JOBS
# ═══════════════════════════════════════════════════════════════════

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now = now_ist()

    # Midnight reset
    if now.hour == 0 and now.minute <= 2:
        reminders.reset_daily()
        log.info("🌙 Midnight: reminders reset")
        return

    due = reminders.due_now()
    if due:
        log.info(f"⏰ Firing {len(due)} reminder(s) at {now.strftime('%H:%M')}")

    for r in due:
        try:
            await context.bot.send_message(
                chat_id=int(r["chat_id"]),
                text=(
                    f"🚨🔔 *ALARM!*\n{'═'*20}\n"
                    f"⏰ *{r['time']}*\n"
                    f"📢 *{r['text']}*\n\n"
                    f"{'🔁 Daily reminder' if r.get('repeat')=='daily' else ''}\n"
                    f"_Snooze karne ke liye: /remind 10m {r['text']}_\n"
                    f"_Delete: /delremind {r['id']}_"
                ),
                parse_mode="Markdown"
            )
            reminders.mark_fired(r["id"])
            log.info(f"  ✅ Fired #{r['id']}: {r['text']}")
            await asyncio.sleep(0.5)
        except Exception as e:
            log.error(f"  ❌ Reminder fire error #{r['id']}: {e}")


async def bill_due_job(context: ContextTypes.DEFAULT_TYPE):
    if now_ist().strftime("%H:%M") != "09:00":
        return
    due = bills.due_soon(3)
    if not due:
        return
    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    for cid in chat_ids:
        try:
            lines = "\n".join(
                f"⚠️ *{b['name']}* — ₹{b['amount']:.0f} (Due {b.get('due_date','')})"
                for b in due
            )
            await context.bot.send_message(
                chat_id=int(cid),
                text=f"💳 *BILL DUE SOON!*\n\n{lines}\n\n_/bills — Full list_",
                parse_mode="Markdown"
            )
        except Exception as e:
            log.warning(f"Bill due alert: {e}")


async def water_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now = now_ist()
    if not (8 <= now.hour <= 22):
        return
    if now.hour % 3 != 0:
        return
    if water.today_total() >= water.goal():
        return
    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    for cid in chat_ids:
        try:
            await context.bot.send_message(
                chat_id=int(cid),
                text=(
                    f"💧 *Paani Peena Yaad Hai?*\n"
                    f"Abhi tak: {water.today_total()}ml / {water.goal()}ml\n"
                    f"_'/water' ya '250ml paani piya' likho_"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            log.warning(f"Water reminder: {e}")


async def scheduled_backup_job(context: ContextTypes.DEFAULT_TYPE):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, google_sheets.full_sync)
    log.info(f"🕒 Scheduled backup: {result}")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    log.info("=" * 60)
    log.info("🤖 Personal AI Bot v21.0 — Natural Language Mode")
    log.info("  ✅ No buttons — Sab chat se hoga")
    log.info("  ✅ Natural language intent detection")
    log.info("  ✅ Reminders/Alarms background mein")
    log.info("  ✅ Google Sheets auto-sync")
    log.info("  ✅ Diary password flow intact")
    log.info(f"⏰ IST: {now_ist().strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"📊 Sheets: {'✅ Connected' if google_sheets.sheet else '❌ Not connected'}")
    log.info("=" * 60)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # ── Step 1: Diary ConversationHandler PEHLE ──────────────────────
    diary_conv = ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary_entry)],
        states={
            DIARY_AWAIT_PASS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)
            ],
            DIARY_AWAIT_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, diary_text_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", diary_cancel)],
        per_user=True,
        per_chat=False,
        conversation_timeout=120,
        allow_reentry=True,
    )
    app.add_handler(diary_conv)

    # ── Step 2: Commands ──────────────────────────────────────────────
    cmds = [
        ("start",       cmd_start),
        ("help",        cmd_help),
        ("task",        cmd_task),
        ("done",        cmd_done),
        ("deltask",     cmd_deltask),
        ("habit",       cmd_habit),
        ("hdone",       cmd_hdone),
        ("delhabit",    cmd_delhabit),
        ("kharcha",     cmd_kharcha),
        ("budget",      cmd_budget),
        ("goal",        cmd_goal),
        ("gprogress",   cmd_gprogress),
        ("remember",    cmd_remember),
        ("recall",      cmd_recall),
        ("briefing",    cmd_briefing),
        ("weekly",      cmd_weekly),
        ("report",      cmd_report),
        ("news",        cmd_news),
        ("alltasks",    cmd_alltasks),
        ("completed",   cmd_completed),
        ("yesterday",   cmd_yesterday),
        ("remind",      cmd_remind),
        ("reminders",   cmd_reminders_list),
        ("delremind",   cmd_delremind),
        ("water",       cmd_water),
        ("waterstatus", cmd_water_status),
        ("watergoal",   cmd_water_goal),
        ("bill",        cmd_bill),
        ("bills",       cmd_bills_list),
        ("billpaid",    cmd_bill_paid),
        ("delbill",     cmd_del_bill),
        ("cal",         cmd_cal),
        ("calendar",    cmd_cal_list),
        ("delcal",      cmd_del_cal),
        ("memory",      cmd_memory),
        ("backup",      cmd_backup),
        ("dbstatus",    cmd_dbstatus),
        ("clear",       cmd_clear),
        ("save",        cmd_save),
    ]
    for cmd, handler in cmds:
        app.add_handler(CommandHandler(cmd, handler))

    # ── Step 3: General message handler (natural language) ────────────
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # ── Step 4: Background jobs ───────────────────────────────────────
    if app.job_queue:
        app.job_queue.run_repeating(
            reminder_job, interval=60, first=10, name="reminder_check"
        )
        app.job_queue.run_repeating(
            bill_due_job, interval=3600, first=300, name="bill_due_check"
        )
        app.job_queue.run_repeating(
            water_reminder_job, interval=3600, first=600, name="water_reminder"
        )
        app.job_queue.run_repeating(
            scheduled_backup_job, interval=3600, first=120, name="scheduled_backup"
        )
        log.info("⏰ All background jobs registered!")
    else:
        log.warning("⚠️ job_queue not available!")

    log.info("✅ Bot ready! Polling shuru...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
