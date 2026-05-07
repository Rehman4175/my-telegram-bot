#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v20.0  COMPLETE FIX                ║
║  FIX 1: ConversationHandler order aur registration sahi ki      ║
║  FIX 2: Diary password — hamesha maangega (view + write)        ║
║  FIX 3: Auto-backup — asyncio.create_task properly              ║
║  FIX 4: Reminder midnight reset — range check se fix            ║
║  FIX 5: per_user only (per_chat hata diya) — state match fix    ║
║  FIX 6: Diary save — ConversationHandler se bahar nahi          ║
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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON",
                    os.environ.get("Google_CREDS_JSON", ""))
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "")

DIARY_PASSWORD = "Rk1996"

# ── ConversationHandler states ──────────────────────────────────────
# Diary ke liye do alag flows:
#   DIARY_AWAIT_MODE  → /diary ke baad mode decide (view/write)
#   DIARY_AWAIT_PASS  → password check karo (view ke liye)
#   DIARY_AWAIT_TEXT  → diary text input (write ke liye, password ke baad)
DIARY_AWAIT_MODE = 0
DIARY_AWAIT_PASS = 1
DIARY_AWAIT_TEXT = 2

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

def call_gemini(prompt, max_tokens=400):
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
            "maxOutputTokens": min(max_tokens, 600)
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
        """Raat 12 baje fired_today reset karo"""
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

    def clear(self):
        count = len(self.store.data["history"])
        self.store.data["history"] = []
        self.store.save()
        return count


# ═══════════════════════════════════════════════════════════════════
# INIT STORES
# ═══════════════════════════════════════════════════════════════════
memory   = MemoryStore()
tasks    = TaskStore()
diary    = DiaryStore()
habits   = HabitStore()
expenses = ExpenseStore()
goals    = GoalStore()
reminders = ReminderStore()
water    = WaterStore()
bills    = BillStore()
calendar = CalendarStore()
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
            "Reminders":              ["ID","Time","Text","Repeat","Status","Created Date","Chat ID","Last Fired","Remarks"],
            "Tasks":                  ["ID","Title","Priority","Status","Created Date","Completed Date","Due Date","Tags"],
            "Expenses":               ["Date","Amount (Rs)","Description","Category","Time"],
            "Habits":                 ["ID","Habit Name","Emoji","Streak","Best Streak","Created Date","Target (per day)"],
            "Water Intake":           ["Date","Total ML","Goal ML","Percentage","Glasses (250ml)","Hourly Logs"],
            "Memory / Important Notes":["Date","Category","Content","Tags","Priority"],
            "Daily_Logs":             ["Date","Tasks Done","Tasks Pending","Expenses (Rs)","Reminders Active","Habits Done","Water ML","Mood","Notes"],
            "Goals":                  ["ID","Title","Progress %","Status","Deadline","Created Date","Milestones"],
            "Bills & Subscriptions":  ["ID","Name","Amount (₹)","Due Date","Auto-pay","Paid Status","Payment Method","Notes"],
            "Calendar Events":        ["Date","Time","Event Title","Location","Reminder Set","Participants","Notes"],
            "Diary":                  ["Date","Time","Content","Mood"],
            "Miscellaneous":          ["Timestamp","Date","Role","User","Message"],
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
            ("Tasks",       self.save_tasks),
            ("Reminders",   self.save_reminders),
            ("Expenses",    self.save_expenses),
            ("Habits",      self.save_habits),
            ("Memory",      self.save_memory),
            ("Goals",       self.save_goals),
            ("Bills",       self.save_bills),
            ("Calendar",    self.save_calendar),
            ("Water",       self.save_water),
            ("Daily_Log",   self.save_daily_log),
            ("Diary",       self.save_diary),
            ("Chat_History",self.save_chat_history),
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

# ═══════════════════════════════════════════════════════════════════
# FIX 3: AUTO-BACKUP — asyncio.ensure_future properly use karo
# asyncio.get_event_loop().create_task() deprecated hai 3.10+ mein
# asyncio.ensure_future() bhi safe nahi bahar coroutine context ke
# Sahi tarika: asyncio.create_task() inside async function
# ═══════════════════════════════════════════════════════════════════
async def auto_backup_to_sheets():
    """Sheets mein async backup — non-blocking"""
    if not google_sheets.sheet:
        return
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, google_sheets.full_sync)
        log.info(f"📤 Auto-backup: {result}")
    except Exception as e:
        log.error(f"Auto-backup error: {e}")


def fire_and_forget_backup():
    """
    Non-async jagah se backup schedule karne ke liye.
    asyncio.create_task safe hai sirf running loop mein.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(auto_backup_to_sheets())
    except RuntimeError:
        pass  # No running loop — skip


# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════
def build_system_prompt():
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    ag = goals.active()
    exp_t = expenses.today_total()
    exp_m = expenses.month_total()
    bl    = expenses.budget_left()
    wt    = water.today_total()
    wg    = water.goal()

    tasks_s = "\n".join(
        f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}"
        for t in tp[:5]
    ) or "  Koi nahi"
    h_done = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    h_pend = ", ".join(f"{h['name']}" for h in hp) or "Sab ho gaye!"
    goals_s = "\n".join(
        f"  🎯 {g['title']} ({g['progress']}%)" for g in ag[:4]
    ) or "  Koi nahi"
    budget_s = f"Budget baaki: ₹{bl:.0f}" if bl is not None else ""

    return (
        f"Tu mera Personal AI Assistant hai — naam 'Dost'. Hamesha Hindi/Hinglish mein baat kar.\n"
        f"⚠️ REAL TIME: {now_ist().strftime('%A, %d %b %Y — %I:%M %p')} IST\n"
        f"📋 AAJ KE TASKS ({len(tp)}):\n{tasks_s}\n"
        f"💪 HABITS: Done: {h_done} | Baaki: {h_pend}\n"
        f"💰 KHARCHA: Aaj ₹{exp_t} | Mahina ₹{exp_m} {budget_s}\n"
        f"🎯 GOALS ({len(ag)}):\n{goals_s}\n"
        f"💧 PAANI: {wt}ml/{wg}ml\n"
        f"RULES: Dost ki tarah baat kar, Hindi/Hinglish mein SHORT jawab (2-4 lines)."
    )


# ═══════════════════════════════════════════════════════════════════
# AI CHAT
# ═══════════════════════════════════════════════════════════════════
async def ai_chat(user_msg, chat_id=None, user_name=""):
    prompt = build_system_prompt() + "\n\nUser: " + user_msg + "\n\nShort Hindi reply:"
    reply = call_gemini(prompt)
    if not reply:
        msg = user_msg.lower()
        n = now_ist()
        if any(w in msg for w in ["time", "baje"]):
            reply = f"⏰ Abhi *{n.strftime('%I:%M %p')}* baj rahe hain (IST)"
        elif any(w in msg for w in ["hello", "hi", "assalam"]):
            reply = "🕌 *Assalamualaikum!* Batao kaisi help chahiye?"
        else:
            reply = "🙏 `/help` try karo!"
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
        f"Main aapka AI dost hoon! Jo marzi likho, main jawab dunga.\n\n"
        f"📋 `/task` `/done` `/habit` `/remind` `/kharcha` `/diary` `/help`",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *COMMANDS*\n\n"
        "`/task` `/done` `/deltask` — Tasks\n"
        "`/habit` `/hdone` `/delhabit` — Habits\n"
        "`/remind` `/reminders` `/delremind` — Reminders\n"
        "`/kharcha` `/budget` — Expenses\n"
        "`/diary` — Diary dekho/likho (password: hamesha maangega)\n"
        "  `/diary` → aaj ki diary\n"
        "  `/diary week` → hafte ki diary\n"
        "  `/diary all` → poori diary\n"
        "  `/diary write` → naya entry likho\n"
        "`/save Aaj ka din...` → seedha diary save\n"
        "`/remember` `/recall` — Memory\n"
        "`/goal` `/gprogress` — Goals\n"
        "`/bill` `/bills` `/billpaid` `/delbill` — Bills\n"
        "`/cal` `/calendar` `/delcal` — Calendar\n"
        "`/water` `/waterstatus` `/watergoal` — Water\n"
        "`/news` — News\n"
        "`/briefing` `/weekly` `/report` `/yesterday` — Reports\n"
        "`/alltasks` `/completed` — Views\n"
        "`/backup` `/dbstatus` `/clear` — Utils",
        parse_mode="Markdown"
    )


async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
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
        f"✅ {e} *{t['title']}*\n🆔 `#{t['id']}`",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            await update.message.reply_text(
                "📋 *Pending:*\n" +
                "\n".join(f"`/done {t['id']}` → {t['title']}" for t in pending[:15]),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("🎉 No pending!")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        await update.message.reply_text(
            f"🎉 *Done!* {t['title']} ✅" if t else "❌ Not found!",
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
    await update.message.reply_text("🗑 Deleted!")
    await auto_backup_to_sheets()


# ═══════════════════════════════════════════════════════════════════
# DIARY — COMPLETE REWRITE v20
#
# ARCHITECTURE:
#   /diary (koi bhi args) → ConversationHandler entry_point
#   State DIARY_AWAIT_MODE → mode select karo (view/write)
#   State DIARY_AWAIT_PASS → password check
#   State DIARY_AWAIT_TEXT → text likhne ka wait (write mode)
#
# KEY FIXES:
#   1. ConversationHandler PEHLE register hoga (main() mein)
#   2. per_user=True, per_chat=False — state sirf user ke hisaab se
#   3. cmd_diary sirf mode set karta hai, password baad mein
#   4. /save command ConversationHandler ke bahar hai (direct save)
#   5. asyncio.create_task() sahi se use kiya
# ═══════════════════════════════════════════════════════════════════

async def cmd_diary_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /diary entry point — ConversationHandler trigger karta hai.
    Mode decide karo aur uske hisaab se state set karo.
    """
    args = ctx.args or []

    if not args:
        # Koi argument nahi — mode choose karne ko kaho
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📖 Diary Dekho (Aaj)", callback_data="diary_view_today"),
                InlineKeyboardButton("📅 Is Hafte", callback_data="diary_view_week"),
            ],
            [
                InlineKeyboardButton("📚 Poori Diary", callback_data="diary_view_all"),
                InlineKeyboardButton("✏️ Naya Likhna", callback_data="diary_write"),
            ]
        ])
        await update.message.reply_text(
            "📖 *Diary — Kya Karna Chahte Ho?*\n\n"
            "_Neeche se choose karo ya seedha type karo:_\n"
            "`/diary week` — hafte ki diary\n"
            "`/diary all` — poori diary\n"
            "`/diary write` — naya likhna",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return DIARY_AWAIT_MODE

    first = args[0].lower()

    if first == "write":
        # Write mode — pehle password maango
        ctx.user_data["diary_mode"] = "write"
        await update.message.reply_text(
            "🔐 *Password Daalo Diary Likhne Ke Liye:*\n\n"
            "_/cancel se bahar jao_",
            parse_mode="Markdown"
        )
        return DIARY_AWAIT_PASS

    elif first == "week":
        ctx.user_data["diary_mode"] = "view_week"
    elif first == "all":
        ctx.user_data["diary_mode"] = "view_all"
    elif first in ["today", "view"]:
        ctx.user_data["diary_mode"] = "view_today"
    elif first == "date" and len(args) >= 2:
        ctx.user_data["diary_mode"] = f"view_date_{args[1]}"
    else:
        # Text diya — direct write mode, password pehle
        ctx.user_data["diary_mode"] = "write"
        ctx.user_data["diary_pending_text"] = " ".join(args)
        await update.message.reply_text(
            "🔐 *Password Confirm Karo Diary Save Karne Ke Liye:*\n\n"
            "_/cancel se bahar jao_",
            parse_mode="Markdown"
        )
        return DIARY_AWAIT_PASS

    # View mode — password maango
    await update.message.reply_text(
        "🔐 *Diary Password Enter Karo:*\n\n"
        "_/cancel se bahar jao_",
        parse_mode="Markdown"
    )
    return DIARY_AWAIT_PASS


async def diary_mode_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    DIARY_AWAIT_MODE state — user ne text message bheja
    (inline keyboard callback alag handler mein handle hoga)
    """
    text = update.message.text.strip().lower() if update.message else ""

    if "week" in text:
        ctx.user_data["diary_mode"] = "view_week"
    elif "all" in text or "poori" in text or "sab" in text:
        ctx.user_data["diary_mode"] = "view_all"
    elif "likh" in text or "write" in text or "naya" in text:
        ctx.user_data["diary_mode"] = "write"
    else:
        ctx.user_data["diary_mode"] = "view_today"

    await update.message.reply_text(
        "🔐 *Diary Password Enter Karo:*\n\n"
        "_/cancel se bahar jao_",
        parse_mode="Markdown"
    )
    return DIARY_AWAIT_PASS


async def diary_password_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    DIARY_AWAIT_PASS state — password verify karo
    """
    if not update.message:
        return ConversationHandler.END

    entered = update.message.text.strip()

    if entered != DIARY_PASSWORD:
        # Wrong password — delete karo message, error do, end karo
        try:
            await update.message.delete()
        except Exception:
            pass
        await update.effective_chat.send_message(
            "❌ *Galat Password!*\n\n"
            "_Dobara try karne ke liye /diary likhao._",
            parse_mode="Markdown"
        )
        ctx.user_data.pop("diary_mode", None)
        ctx.user_data.pop("diary_pending_text", None)
        return ConversationHandler.END

    # Password sahi — message delete karo (security)
    try:
        await update.message.delete()
    except Exception:
        pass

    mode = ctx.user_data.get("diary_mode", "view_today")

    # ── WRITE MODE ──────────────────────────────────────────────────
    if mode == "write":
        pending = ctx.user_data.get("diary_pending_text", "")
        if pending:
            # Text pehle se tha — seedha save karo
            await _do_save_diary(update, ctx, pending)
            return ConversationHandler.END
        else:
            # Text abhi maango
            await update.effective_chat.send_message(
                "✏️ *Aaj Ka Diary Entry Likho:*\n\n"
                "_Apne dil ki baat likho..._\n"
                "_/cancel se bahar jao_",
                parse_mode="Markdown"
            )
            return DIARY_AWAIT_TEXT

    # ── VIEW MODE ───────────────────────────────────────────────────
    await _show_diary(update, ctx, mode)
    return ConversationHandler.END


async def diary_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    DIARY_AWAIT_TEXT state — user ne diary text diya
    """
    if not update.message:
        return ConversationHandler.END
    text = update.message.text.strip()
    await _do_save_diary(update, ctx, text)
    return ConversationHandler.END


async def _do_save_diary(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    """
    Diary entry save karo, user ka message delete karo,
    confirmation 3 sec baad delete karo.
    """
    # Save
    diary.add(text, mood="📝")

    # User ka original message delete karo (privacy)
    try:
        if update.message:
            await update.message.delete()
    except Exception:
        pass

    # Confirmation
    try:
        conf_msg = await update.effective_chat.send_message(
            f"📖 *Diary Saved!* ✅\n"
            f"🕐 {now_str()}\n\n"
            f"_{text[:120]}{'...' if len(text) > 120 else ''}_",
            parse_mode="Markdown"
        )
        # Backup schedule
        asyncio.create_task(auto_backup_to_sheets())

        # 3 sec baad delete
        await asyncio.sleep(3)
        try:
            await conf_msg.delete()
        except Exception:
            pass
    except Exception as e:
        log.error(f"_do_save_diary confirmation error: {e}")

    # Cleanup
    ctx.user_data.pop("diary_mode", None)
    ctx.user_data.pop("diary_pending_text", None)


async def _show_diary(update: Update, ctx: ContextTypes.DEFAULT_TYPE, mode: str):
    """Diary entries dikhao based on mode"""

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

    elif mode.startswith("view_date_"):
        d_arg = mode[len("view_date_"):]
        entries = diary.get(d_arg)
        all_entries = {d_arg: entries} if entries else {}
        title = f"📖 *Diary — {d_arg}*"

    else:
        all_entries = {}
        title = "📖 *Diary*"

    if not all_entries or not any(all_entries.values()):
        await update.effective_chat.send_message(
            f"{title}\n\n_Koi entry nahi mili._\n\n"
            "_Likhne ke liye:_ `/diary write`",
            parse_mode="Markdown"
        )
        return

    chunks, current = [], f"{title}\n{'━'*25}\n\n"
    for dk in sorted(all_entries.keys(), reverse=True):
        if not all_entries[dk]:
            continue
        block = f"📅 *{dk}*\n"
        for e in all_entries[dk]:
            mood  = e.get("mood", "📝")
            time_ = e.get("time", "")
            text  = e.get("text", "")
            block += f"{mood} `{time_}` — {text}\n"
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
    """/cancel — diary session khatam"""
    ctx.user_data.pop("diary_mode", None)
    ctx.user_data.pop("diary_pending_text", None)
    try:
        if update.message:
            await update.message.reply_text(
                "⏱ Diary session cancel.\n_Dobara karo: /diary_"
            )
    except Exception:
        pass
    return ConversationHandler.END


# ─── /save shortcut — ConversationHandler ke BAHAR ─────────────────
async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /save Aaj ka din acha tha...
    Password NAHI maanga jaata — ye quick save shortcut hai.
    Agar privacy chahiye toh /diary write use karo.
    """
    if not ctx.args:
        await update.message.reply_text(
            "📖 *Quick Diary Save*\n\n"
            "`/save Aaj ka din acha tha...`\n\n"
            "_Password wale save ke liye: /diary write_",
            parse_mode="Markdown"
        )
        return
    text = " ".join(ctx.args)
    await _do_save_diary(update, ctx, text)


# ─── Inline keyboard callback for diary mode select ─────────────────
async def diary_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /diary se aayi inline keyboard ka callback.
    ConversationHandler ke bahar hai isliye seedha handle karta hai.
    """
    query = update.callback_query
    await query.answer()
    d = query.data

    mode_map = {
        "diary_view_today": "view_today",
        "diary_view_week":  "view_week",
        "diary_view_all":   "view_all",
        "diary_write":      "write",
    }

    if d not in mode_map:
        return

    ctx.user_data["diary_mode"] = mode_map[d]

    try:
        await query.message.delete()
    except Exception:
        pass

    await update.effective_chat.send_message(
        "🔐 *Diary Password Enter Karo:*\n\n"
        "_/cancel se bahar jao_",
        parse_mode="Markdown"
    )
    # NOTE: Inline callback ConversationHandler state set nahi kar sakta directly.
    # Isliye hum ek naya flow start karte hain — user ka next message
    # diary_password_flow_handler pakad lega.
    ctx.user_data["diary_awaiting_pass_from_callback"] = True


async def diary_pass_from_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Inline keyboard se aaye password input ko handle karta hai.
    Ye MessageHandler hai, ConversationHandler ke bahar.
    """
    if not ctx.user_data.get("diary_awaiting_pass_from_callback"):
        return  # Ye message hamare liye nahi

    if not update.message:
        return

    entered = update.message.text.strip()
    ctx.user_data.pop("diary_awaiting_pass_from_callback", None)

    try:
        await update.message.delete()
    except Exception:
        pass

    if entered != DIARY_PASSWORD:
        await update.effective_chat.send_message(
            "❌ *Galat Password!*\n\n"
            "_Dobara try: /diary_",
            parse_mode="Markdown"
        )
        ctx.user_data.pop("diary_mode", None)
        return

    mode = ctx.user_data.get("diary_mode", "view_today")

    if mode == "write":
        await update.effective_chat.send_message(
            "✏️ *Aaj Ka Diary Entry Likho:*\n\n"
            "_Apne dil ki baat likho..._\n"
            "_/cancel ke baad /diary se dobara shuru karo_",
            parse_mode="Markdown"
        )
        ctx.user_data["diary_awaiting_text_from_callback"] = True
    else:
        await _show_diary(update, ctx, mode)
        ctx.user_data.pop("diary_mode", None)


async def diary_text_from_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inline flow se aaya diary text"""
    if not ctx.user_data.get("diary_awaiting_text_from_callback"):
        return
    if not update.message:
        return

    ctx.user_data.pop("diary_awaiting_text_from_callback", None)
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    await _do_save_diary(update, ctx, text)
    ctx.user_data.pop("diary_mode", None)


# ═══════════════════════════════════════════════════════════════════
# REMAINING COMMANDS
# ═══════════════════════════════════════════════════════════════════

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("💪 `/habit Naam`", parse_mode="Markdown")
        return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(
        f"💪 {h['emoji']} *{h['name']}*\n`/hdone {h['id']}`",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            await update.message.reply_text(
                "💪 *Pending:*\n" +
                "\n".join(f"`/hdone {h['id']}` → {h['name']}" for h in pending),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("🎊 Sab done!")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        await update.message.reply_text(
            f"💪 *Done!* 🔥 {streak}d!" if ok else "✅ Already done!",
            parse_mode="Markdown"
        )
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ Invalid!")


async def cmd_delhabit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("`/delhabit <id>`")
        return
    habits.delete(int(ctx.args[0]))
    await update.message.reply_text("🗑 Deleted!")
    await auto_backup_to_sheets()


async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text("💰 `/kharcha amount desc`")
        return
    try:
        amount = float(ctx.args[0])
        desc   = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        await update.message.reply_text(
            f"💰 ₹{amount:.0f} — {desc}\n📊 Aaj: ₹{expenses.today_total():.0f}",
            parse_mode="Markdown"
        )
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ `/kharcha 100 Chai`")


async def cmd_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            f"💳 Budget: ₹{expenses.store.data.get('budget','Not set')}\n"
            f"`/budget 5000`",
            parse_mode="Markdown"
        )
        return
    expenses.set_budget(float(ctx.args[0]))
    await update.message.reply_text(f"💳 Budget: ₹{ctx.args[0]}")
    await auto_backup_to_sheets()


async def cmd_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        active = goals.active()
        if active:
            await update.message.reply_text(
                "🎯 *ACTIVE GOALS*\n\n" +
                "\n".join(f"#{g['id']} {g['title']} — {g['progress']}%" for g in active),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("🎯 `/goal Description`")
        return
    g = goals.add(" ".join(ctx.args))
    await update.message.reply_text(
        f"🎯 Goal set! #{g['id']} {g['title']}",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_gprogress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text("📊 `/gprogress <id> <pct>`")
        return
    try:
        g = goals.update_progress(int(ctx.args[0]), int(ctx.args[1]))
        await update.message.reply_text(
            f"📊 *{g['title']}* — {g['progress']}%" if g else "❌ Not found!",
            parse_mode="Markdown"
        )
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ Invalid!")


async def cmd_remember(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🧠 `/remember text`")
        return
    memory.add_fact(" ".join(ctx.args))
    await update.message.reply_text("🧠 Yaad kar liya! ✅")
    await auto_backup_to_sheets()


async def cmd_recall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("🧠 Kuch yaad nahi.")
        return
    await update.message.reply_text(
        "🧠 *MEMORY*\n\n" +
        "\n".join(f"📌 {f['f']}" for f in facts[-15:]),
        parse_mode="Markdown"
    )


async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n = now_ist()
    tp = tasks.today_pending()
    hd, _ = habits.today_status()
    txt = (
        f"🌅 *BRIEFING*\n"
        f"⏰ {n.strftime('%I:%M %p')} | 📅 {n.strftime('%d %b')}\n\n"
        f"📋 Pending: {len(tp)}\n"
        f"💪 Done: {len(hd)}\n"
        f"💰 Aaj: ₹{expenses.today_total():.0f}\n"
        f"💧 Water: {water.today_total()}ml/{water.goal()}ml"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")
    await auto_backup_to_sheets()


async def cmd_weekly(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n = now_ist()
    ws_date = n.date() - timedelta(days=n.weekday())
    tw = tasks.get_weekly_summary()
    await update.message.reply_text(
        f"📊 *WEEKLY*\n"
        f"📅 {ws_date.strftime('%d %b')} - {n.strftime('%d %b %Y')}\n\n"
        f"📋 Done: {sum(v['done'] for v in tw.values())}\n"
        f"💰 Month: ₹{expenses.month_total():.0f}",
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
        await update.message.reply_text("❌ Invalid date!")
        return
    exp_t = sum(e["amount"] for e in expenses.get_by_date(target))
    hl    = habits.get_logs_by_date(target)
    hd    = [h for h in habits.all() if h["id"] in hl]
    wt    = sum(w["ml"] for w in water.get_by_date(target))
    await update.message.reply_text(
        f"📋 *REPORT {target}*\n\n"
        f"📋 Done: {len(tasks.done_on(target))}\n"
        f"💰 ₹{exp_t:.0f}\n"
        f"📖 {len(diary.get(target))} entries\n"
        f"💪 {len(hd)} habits\n"
        f"💧 {wt}ml",
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
            await update.message.reply_text(
                "📰 *INDIA NEWS*\n\n" +
                "\n".join(
                    f"• *{item.findtext('title','')}*"
                    for item in items if item.findtext('title','')
                ),
                parse_mode="Markdown"
            )
    except Exception:
        await update.message.reply_text("📰 News unavailable.")


async def cmd_alltasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    p = tasks.pending()
    if not p:
        await update.message.reply_text("📋 No pending tasks!")
        return
    await update.message.reply_text(
        f"📋 *ALL PENDING*\n⏳ {len(p)} tasks\n\n" +
        "\n".join(f"   #{t['id']} {t['title']}" for t in p[:10]),
        parse_mode="Markdown"
    )


async def cmd_completed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    c = tasks.completed_tasks()
    if not c:
        await update.message.reply_text("✅ None yet!")
        return
    await update.message.reply_text(
        f"✅ *COMPLETED ({len(c)})*\n\n" +
        "\n".join(f"  ✓ #{t['id']} {t['title']}" for t in c[-15:]),
        parse_mode="Markdown"
    )


async def cmd_yesterday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    yd    = yesterday_str()
    exp_t = sum(e["amount"] for e in expenses.get_by_date(yd))
    hl    = habits.get_logs_by_date(yd)
    hd    = [h for h in habits.all() if h["id"] in hl]
    await update.message.reply_text(
        f"📅 *YESTERDAY ({yd})*\n\n"
        f"✅ Tasks: {len(tasks.done_on(yd))}\n"
        f"💪 Habits: {len(hd)}/{len(habits.all())}\n"
        f"💰 ₹{exp_t:.0f}",
        parse_mode="Markdown"
    )


async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = now_ist()
    if not ctx.args:
        await update.message.reply_text(
            "⏰ `/remind 2m Test` | `/remind 30m Chai` | `/remind 15:30 Doctor`",
            parse_mode="Markdown"
        )
        return
    time_arg = ctx.args[0].lower()
    rest = list(ctx.args[1:])
    repeat = "once"
    if rest and rest[-1].lower() in ["daily", "weekly"]:
        repeat = rest[-1].lower()
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
            await update.message.reply_text("❌ Invalid time format!")
            return
    else:
        await update.message.reply_text("❌ Format: `/remind 30m Chai` ya `/remind 15:30 Meeting`")
        return

    r = reminders.add(update.effective_chat.id, text, remind_at, repeat)
    await update.message.reply_text(
        f"✅ *Reminder Set!* ⏰ {remind_at} — {text}\n"
        f"🆔 `#{r['id']}` | Repeat: {repeat}",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_reminders_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    active = reminders.all_active()
    if not active:
        await update.message.reply_text("⏰ Koi active reminder nahi!")
        return
    await update.message.reply_text(
        f"⏰ *ACTIVE REMINDERS ({len(active)})*\n\n" +
        "\n".join(
            f"*#{r['id']}* `{r['time']}` — {r['text']} ({r.get('repeat','once')})"
            for r in active
        ),
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
    await update.message.reply_text(
        f"💧 *Water Status*\n{total}ml / {goal}ml ({pct}%)",
        parse_mode="Markdown"
    )


async def cmd_water_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args and ctx.args[0].isdigit():
        water.set_goal(int(ctx.args[0]))
    await update.message.reply_text(f"✅ Water Goal: {water.goal()}ml")


async def cmd_bill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 3:
        await update.message.reply_text("💳 `/bill Name Amount DueDay`")
        return
    try:
        b = bills.add(ctx.args[0], float(ctx.args[1]), int(ctx.args[2]))
        await update.message.reply_text(
            f"✅ Bill added: {b['name']} ₹{b['amount']:.0f} — Due {b['due_day']}th",
            parse_mode="Markdown"
        )
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ Format: `/bill Netflix 299 5`")


async def cmd_bills_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    all_b = bills.all_active()
    if not all_b:
        await update.message.reply_text("💳 Koi bill nahi!")
        return
    await update.message.reply_text(
        "💳 *BILLS*\n\n" +
        "\n".join(
            f"{'✅' if bills.is_paid_this_month(b['id']) else '⏳'} "
            f"*{b['name']}* — ₹{b['amount']:.0f} (Due {b['due_day']}th)"
            for b in all_b
        ),
        parse_mode="Markdown"
    )


async def cmd_bill_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("`/billpaid <id>`")
        return
    try:
        ok = bills.mark_paid(int(ctx.args[0]))
        await update.message.reply_text("✅ Paid!" if ok else "⚠️ Already marked paid!")
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
        await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`")
        return
    args_str  = " ".join(ctx.args)
    date_str  = None
    title     = args_str

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
        await update.message.reply_text("❌ Format: `/cal 2025-07-15 Meeting`")
        return

    event_time = ""
    t_match = _re.search(r'(\d{1,2}:\d{2})', title)
    if t_match:
        event_time = t_match.group(1)
        title = title.replace(event_time, "").strip()

    try:
        date.fromisoformat(date_str)
        calendar.add(title, date_str, event_time)
        await update.message.reply_text(
            f"📅 Event added: {title} — {date_str}" +
            (f" ⏰{event_time}" if event_time else ""),
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
    await update.message.reply_text(
        "📅 *UPCOMING EVENTS*\n\n" +
        "\n".join(
            f"{'🔴' if e['date']==today_str() else '📆'} {e['date']} — {e['title']}"
            for e in upcoming[:10]
        ),
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
        await update.message.reply_text("🧠 Memory empty!")
        return
    await update.message.reply_text(
        "🧠 *MEMORY*\n\n" +
        "\n".join(f"📌 {f['f']}" for f in facts[-15:]),
        parse_mode="Markdown"
    )


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
        f"Expenses: {e}\nChat history: {ch}"
    )


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    count = chat_hist.clear()
    await update.message.reply_text(f"🧹 {count} chat messages cleared!")


# ═══════════════════════════════════════════════════════════════════
# MESSAGE HANDLER — AI CHAT + CHAT LOG
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_msg  = update.message.text.strip()
    user_name = update.effective_user.first_name or "User"

    if user_msg.startswith("/"):
        return

    # Diary inline flow intercept
    if ctx.user_data.get("diary_awaiting_pass_from_callback"):
        await diary_pass_from_callback(update, ctx)
        return

    if ctx.user_data.get("diary_awaiting_text_from_callback"):
        await diary_text_from_callback(update, ctx)
        return

    # Normal AI chat
    await ctx.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )
    reply = await ai_chat(user_msg, update.effective_chat.id, user_name)

    # Pehle save, phir backup
    chat_hist.add("user", user_msg, user_name)
    chat_hist.add("assistant", reply, "Bot")

    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(reply)

    await auto_backup_to_sheets()


# ═══════════════════════════════════════════════════════════════════
# BACKGROUND JOBS
# ═══════════════════════════════════════════════════════════════════

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Har minute chalta hai.
    FIX: Midnight reset ke liye exact string match hataya —
         ab 00:00 ya 00:01 dono pe reset hoga (range check).
    """
    now = now_ist()
    now_hm = now.strftime("%H:%M")

    # FIX 4: Midnight reset — range check, exact match nahi
    if now.hour == 0 and now.minute <= 2:
        reminders.reset_daily()
        log.info("🌙 Midnight: reminders reset")
        return

    # Due reminders fire karo
    due = reminders.due_now()
    if due:
        log.info(f"⏰ Firing {len(due)} reminder(s) at {now_hm}")

    for r in due:
        try:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Done", callback_data=f"remind_done_{r['id']}"),
                InlineKeyboardButton("⏰ Snooze 10m", callback_data=f"remind_snooze_{r['id']}")
            ]])
            await context.bot.send_message(
                chat_id=int(r["chat_id"]),
                text=(
                    f"🚨🔔 *ALARM!*\n{'═'*20}\n"
                    f"⏰ *{r['time']}*\n"
                    f"📢 *{r['text']}*\n"
                    f"{'🔁 Daily' if r.get('repeat')=='daily' else ''}"
                ),
                parse_mode="Markdown",
                reply_markup=kb
            )
            reminders.mark_fired(r["id"])
            log.info(f"  ✅ Fired reminder #{r['id']}: {r['text']}")
            await asyncio.sleep(0.5)
        except Exception as e:
            log.error(f"  ❌ Reminder fire error #{r['id']}: {e}")


async def bill_due_job(context: ContextTypes.DEFAULT_TYPE):
    """Subah 9 baje bill due alerts"""
    if now_ist().strftime("%H:%M") != "09:00":
        return
    due = bills.due_soon(3)
    if not due:
        return
    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    for cid in chat_ids:
        try:
            await context.bot.send_message(
                chat_id=int(cid),
                text=(
                    "💳 *BILL DUE SOON!*\n\n" +
                    "\n".join(
                        f"⚠️ *{b['name']}* — ₹{b['amount']:.0f} (Due {b.get('due_date','')})"
                        for b in due
                    )
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            log.warning(f"Bill due alert error: {e}")


async def water_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """Har 3 ghante paani reminder (8am-10pm)"""
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
                    f"`/water` — 250ml log karo"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            log.warning(f"Water reminder error: {e}")


async def scheduled_backup_job(context: ContextTypes.DEFAULT_TYPE):
    """Har ghante scheduled backup"""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, google_sheets.full_sync)
    log.info(f"🕒 Scheduled backup: {result}")


# ═══════════════════════════════════════════════════════════════════
# CALLBACK HANDLER (reminder buttons + diary inline)
# ═══════════════════════════════════════════════════════════════════
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    d = query.data
    message = query.message
    if not message:
        return

    # ── Reminder callbacks ─────────────────────────────────────────
    if d.startswith("remind_done_"):
        rid = int(d.split("_")[2])
        reminders.mark_fired(rid)
        try:
            await message.edit_text("✅ Done! Reminder cleared.")
        except Exception:
            pass
        await asyncio.sleep(2)
        try:
            await message.delete()
        except Exception:
            pass
        await auto_backup_to_sheets()

    elif d.startswith("remind_snooze_"):
        rid = int(d.split("_")[2])
        snooze_time = (now_ist() + timedelta(minutes=10)).strftime("%H:%M")
        r_list = [r for r in reminders.get_all() if r["id"] == rid]
        if r_list:
            reminders.add(
                int(r_list[0]["chat_id"]),
                r_list[0]["text"],
                snooze_time,
                "once"
            )
            reminders.mark_fired(rid)
        try:
            await message.edit_text(f"😴 Snoozed to {snooze_time}")
        except Exception:
            pass
        await asyncio.sleep(2)
        try:
            await message.delete()
        except Exception:
            pass
        await auto_backup_to_sheets()

    # ── Diary inline callbacks ─────────────────────────────────────
    elif d.startswith("diary_"):
        await diary_callback(update, ctx)


# ═══════════════════════════════════════════════════════════════════
# MAIN — Handler registration order BAHUT important hai
# ═══════════════════════════════════════════════════════════════════
def main():
    log.info("=" * 60)
    log.info("🤖 Personal AI Bot v20.0 — COMPLETE FIX")
    log.info("  ✅ FIX 1: ConversationHandler order sahi")
    log.info("  ✅ FIX 2: Diary password hamesha maangega")
    log.info("  ✅ FIX 3: asyncio.create_task() properly")
    log.info("  ✅ FIX 4: Reminder midnight reset range-based")
    log.info("  ✅ FIX 5: per_user only (per_chat hata diya)")
    log.info("  ✅ FIX 6: Backup reliable hai")
    log.info(f"⏰ IST: {now_ist().strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"📊 Sheets: {'✅ Connected' if google_sheets.sheet else '❌ Not connected'}")
    log.info("=" * 60)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # ════════════════════════════════════════════════════════════════
    # STEP 1: ConversationHandler SABSE PEHLE register karo
    #         (iske baad aane wale CommandHandler("diary") se override na ho)
    # ════════════════════════════════════════════════════════════════
    diary_conv = ConversationHandler(
        entry_points=[
            CommandHandler("diary", cmd_diary_entry)
        ],
        states={
            DIARY_AWAIT_MODE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    diary_mode_select
                )
            ],
            DIARY_AWAIT_PASS: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    diary_password_check
                )
            ],
            DIARY_AWAIT_TEXT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    diary_text_input
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", diary_cancel)
        ],
        # FIX 5: per_user=True, per_chat=False
        # per_chat=True + per_user=True dono saath hone se
        # state (chat_id, user_id) tuple se match hoti hai
        # jo private chats mein theek hai lekin kabhi kabhi
        # unexpected behavior deta hai — sirf per_user rakho
        per_user=True,
        per_chat=False,
        conversation_timeout=120,
        allow_reentry=True,
    )

    # ════════════════════════════════════════════════════════════════
    # STEP 2: Diary ConversationHandler PEHLE add karo
    # ════════════════════════════════════════════════════════════════
    app.add_handler(diary_conv)

    # ════════════════════════════════════════════════════════════════
    # STEP 3: Baaki sab commands
    # ════════════════════════════════════════════════════════════════
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

    # ════════════════════════════════════════════════════════════════
    # STEP 4: CallbackQueryHandler
    # ════════════════════════════════════════════════════════════════
    app.add_handler(CallbackQueryHandler(callback_handler))

    # ════════════════════════════════════════════════════════════════
    # STEP 5: General message handler SABSE AAKHIR mein
    # ════════════════════════════════════════════════════════════════
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # ════════════════════════════════════════════════════════════════
    # STEP 6: Background jobs
    # ════════════════════════════════════════════════════════════════
    if app.job_queue:
        # Reminder check: har minute
        app.job_queue.run_repeating(
            reminder_job, interval=60, first=10,
            name="reminder_check"
        )
        # Bill due: har ghante check
        app.job_queue.run_repeating(
            bill_due_job, interval=3600, first=300,
            name="bill_due_check"
        )
        # Water reminder: har ghante check (andar filter hai)
        app.job_queue.run_repeating(
            water_reminder_job, interval=3600, first=600,
            name="water_reminder"
        )
        # Sheets backup: har ghante
        app.job_queue.run_repeating(
            scheduled_backup_job, interval=3600, first=120,
            name="scheduled_backup"
        )
        log.info("⏰ All background jobs registered!")
    else:
        log.warning("⚠️ job_queue not available — background jobs nahi chalenge!")

    log.info("✅ Bot ready! Polling shuru...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()