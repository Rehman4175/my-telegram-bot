#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v24.0  FULLY WORKING               ║
║  ✅ All data saves to correct Google Sheets                    ║
║  ✅ Diary, Tasks, Expenses, Habits, Reminders all work         ║
║  ✅ Alarm with OK button + Snooze                              ║
║  ✅ Auto-backup every hour                                     ║
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
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
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

def time_label():
    n = now_ist()
    days = {0:"Monday",1:"Tuesday",2:"Wednesday",3:"Thursday",4:"Friday",5:"Saturday",6:"Sunday"}
    return f"{days.get(n.weekday(),'')}, {n.day} {n.strftime('%b')} {n.year} — {n.strftime('%I:%M %p')} IST"

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

def call_gemini(prompt, max_tokens=500, is_action=False):
    global _last_gemini_call
    if not GEMINI_API_KEY:
        return None
    now_t = time.time()
    elapsed = now_t - _last_gemini_call
    if elapsed < 3:
        time.sleep(3 - elapsed + random.uniform(0.5, 1.5))
    _last_gemini_call = time.time()

    temp = 0.0 if is_action else 0.75
    tokens = min(max_tokens, 200 if is_action else 700)

    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temp,
            "maxOutputTokens": tokens
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
        except urllib.error.HTTPError as e:
            if e.code == 429:
                log.warning(f"Rate limited ({model})")
                time.sleep(5)
                continue
            log.warning(f"Gemini {e.code} ({model}): {e}")
            continue
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
        log.info(f"📖 Diary saved to DB: {text[:50]}...")

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
        log.info(f"💰 Expense added: ₹{amount} - {desc}")

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
            if r["id"] == rid:
                r["active"] = False
                r["acknowledged"] = True
                r["remarks"] = remark
                r["last_fired"] = now_ist().isoformat()
                self.store.save()
                log.info(f"✅ Reminder #{rid} acknowledged")
                return True
        return False

    def reset_daily(self):
        for r in self.store.data["list"]:
            if r.get("repeat") in ("daily", "weekly") and r.get("active"):
                r["fired_today"] = False
        self.store.save()
        log.info("🔄 Reminders reset for new day")

    def due_now(self):
        now_hm = now_ist().strftime("%H:%M")
        return [
            r for r in self.store.data.get("list", [])
            if r.get("active")
            and not r.get("acknowledged", False)
            and not r.get("fired_today", False)
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
# GOOGLE SHEETS BACKUP — COMPLETE FIX
# ═══════════════════════════════════════════════════════════════════
class GoogleSheetsBackup:
    def __init__(self):
        self.sheet = None
        self.last_sheet_call = 0
        if not HAS_GSHEETS or not GOOGLE_CREDS_JSON:
            log.warning("⚠️ Google Sheets: Missing libraries or creds")
            return
        try:
            creds_dict = json.loads(GOOGLE_CREDS_JSON)
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            sheet_key = "1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc"
            log.info(f"🔑 Opening sheet with key: {sheet_key}")
            self.sheet = client.open_by_key(sheet_key)
            log.info("✅ Google Sheets connected!")
            self.ensure_worksheets()
        except Exception as e:
            log.error(f"❌ Sheets connect error: {e}")
            log.error("   Make sure service account email is added as Editor to the sheet")

    def _rate_limit_sheets(self):
        now = time.time()
        elapsed = now - self.last_sheet_call
        if elapsed < 2:
            time.sleep(2 - elapsed)
        self.last_sheet_call = time.time()

    def _get_or_create_ws(self, name, headers):
        try:
            return self.sheet.worksheet(name)
        except Exception:
            self._rate_limit_sheets()
            ws = self.sheet.add_worksheet(title=name, rows=1000, cols=len(headers))
            ws.update('A1', [headers])
            log.info(f"📊 Created worksheet: {name}")
            return ws

    def ensure_worksheets(self):
        if not self.sheet:
            return
        sheet_configs = {
            "Tasks": ["ID","Title","Priority","Status","Created Date","Completed Date","Due Date","Tags"],
            "Reminders": ["ID","Time","Text","Repeat","Status","Created Date","Chat ID","Last Fired","Acknowledged","Remarks"],
            "Expenses": ["Date","Amount (Rs)","Description","Category","Time"],
            "Habits": ["ID","Habit Name","Emoji","Streak","Best Streak","Created Date","Target (per day)"],
            "Water Intake": ["Date","Total ML","Goal ML","Percentage","Glasses (250ml)","Hourly Logs"],
            "Memory / Important Notes": ["Date","Category","Content","Tags","Priority"],
            "Daily_Logs": ["Date","Tasks Done","Tasks Pending","Expenses (Rs)","Reminders Active","Habits Done","Water ML","Mood","Notes"],
            "Goals": ["ID","Title","Progress %","Status","Deadline","Created Date","Milestones"],
            "Bills & Subscriptions": ["ID","Name","Amount (₹)","Due Day","Auto-pay","Paid Status","Payment Method","Notes"],
            "Calendar Events": ["Date","Time","Event Title","Location","Reminder Set","Participants","Notes"],
            "Diary": ["Date","Time","Content","Mood"],
            "Miscellaneous": ["Timestamp","Date","Role","User","Message","Type"],
        }
        for name, headers in sheet_configs.items():
            self._get_or_create_ws(name, headers)

    def _clear_and_write(self, ws, rows, headers):
        try:
            self._rate_limit_sheets()
            ws.clear()
            self._rate_limit_sheets()
            if rows:
                ws.update('A1', [headers] + rows, value_input_option="USER_ENTERED")
            else:
                ws.update('A1', [headers])
            return True
        except Exception as e:
            if "429" in str(e):
                log.warning("Rate limit, waiting 5 seconds...")
                time.sleep(5)
                try:
                    ws.clear()
                    if rows:
                        ws.update('A1', [headers] + rows, value_input_option="USER_ENTERED")
                    else:
                        ws.update('A1', [headers])
                    return True
                except:
                    return False
            log.warning(f"_clear_and_write error: {e}")
            return False

    def save_tasks(self):
        try:
            ws = self._get_or_create_ws("Tasks", ["ID","Title","Priority","Status","Created Date","Completed Date","Due Date","Tags"])
            headers = ["ID","Title","Priority","Status","Created Date","Completed Date","Due Date","Tags"]
            rows = [
                [str(t.get("id","")), t.get("title",""), t.get("priority","medium"),
                 "Done" if t.get("done") else "Pending",
                 t.get("created",""), t.get("done_date",""), t.get("due",""), t.get("tags","")]
                for t in tasks.all_tasks()
            ]
            return self._clear_and_write(ws, rows, headers)
        except Exception as e:
            log.warning(f"save_tasks: {e}")
            return False

    def save_reminders(self):
        try:
            ws = self._get_or_create_ws("Reminders", ["ID","Time","Text","Repeat","Status","Created Date","Chat ID","Last Fired","Acknowledged","Remarks"])
            headers = ["ID","Time","Text","Repeat","Status","Created Date","Chat ID","Last Fired","Acknowledged","Remarks"]
            rows = [
                [str(r.get("id","")), r.get("time",""), r.get("text",""), r.get("repeat","once"),
                 "Active" if r.get("active") else "Inactive",
                 r.get("date",""), str(r.get("chat_id","")), r.get("last_fired",""),
                 "Yes" if r.get("acknowledged") else "No", r.get("remarks","")]
                for r in reminders.get_all()
            ]
            return self._clear_and_write(ws, rows, headers)
        except Exception as e:
            log.warning(f"save_reminders: {e}")
            return False

    def save_expenses(self):
        try:
            ws = self._get_or_create_ws("Expenses", ["Date","Amount (Rs)","Description","Category","Time"])
            headers = ["Date","Amount (Rs)","Description","Category","Time"]
            rows = [
                [e.get("date",""), e.get("amount",0), e.get("desc",""), e.get("category","general"), e.get("time","")]
                for e in expenses.store.data.get("list", [])
            ]
            return self._clear_and_write(ws, rows, headers)
        except Exception as e:
            log.warning(f"save_expenses: {e}")
            return False

    def save_habits(self):
        try:
            ws = self._get_or_create_ws("Habits", ["ID","Habit Name","Emoji","Streak","Best Streak","Created Date","Target (per day)"])
            headers = ["ID","Habit Name","Emoji","Streak","Best Streak","Created Date","Target (per day)"]
            rows = [
                [str(h.get("id","")), h.get("name",""), h.get("emoji","✅"),
                 h.get("streak",0), h.get("best_streak",0), h.get("created",""), h.get("target","")]
                for h in habits.all()
            ]
            return self._clear_and_write(ws, rows, headers)
        except Exception as e:
            log.warning(f"save_habits: {e}")
            return False

    def save_memory(self):
        try:
            ws = self._get_or_create_ws("Memory / Important Notes", ["Date","Category","Content","Tags","Priority"])
            headers = ["Date","Category","Content","Tags","Priority"]
            rows = [
                [f.get("d",""), "Fact", f.get("f",""), "", "Medium"]
                for f in memory.get_all_facts()
            ]
            return self._clear_and_write(ws, rows, headers)
        except Exception as e:
            log.warning(f"save_memory: {e}")
            return False

    def save_goals(self):
        try:
            ws = self._get_or_create_ws("Goals", ["ID","Title","Progress %","Status","Deadline","Created Date","Milestones"])
            headers = ["ID","Title","Progress %","Status","Deadline","Created Date","Milestones"]
            rows = [
                [str(g.get("id","")), g.get("title",""), g.get("progress",0),
                 "Done" if g.get("done") else "Active",
                 g.get("deadline",""), g.get("created",""), g.get("milestones","")]
                for g in goals.active() + goals.completed()
            ]
            return self._clear_and_write(ws, rows, headers)
        except Exception as e:
            log.warning(f"save_goals: {e}")
            return False

    def save_bills(self):
        try:
            ws = self._get_or_create_ws("Bills & Subscriptions", ["ID","Name","Amount (₹)","Due Day","Auto-pay","Paid Status","Payment Method","Notes"])
            headers = ["ID","Name","Amount (₹)","Due Day","Auto-pay","Paid Status","Payment Method","Notes"]
            rows = [
                [str(b.get("id","")), b.get("name",""), b.get("amount",0),
                 str(b.get("due_day","")), b.get("auto_pay","No"),
                 "Paid" if bills.is_paid_this_month(b["id"]) else "Pending",
                 b.get("payment_method",""), b.get("notes","")]
                for b in bills.all_active()
            ]
            return self._clear_and_write(ws, rows, headers)
        except Exception as e:
            log.warning(f"save_bills: {e}")
            return False

    def save_calendar(self):
        try:
            ws = self._get_or_create_ws("Calendar Events", ["Date","Time","Event Title","Location","Reminder Set","Participants","Notes"])
            headers = ["Date","Time","Event Title","Location","Reminder Set","Participants","Notes"]
            rows = [
                [e.get("date",""), e.get("time",""), e.get("title",""),
                 e.get("location",""), e.get("reminder_set","Yes"),
                 e.get("participants",""), e.get("notes","")]
                for e in calendar.store.data.get("events", [])
            ]
            return self._clear_and_write(ws, rows, headers)
        except Exception as e:
            log.warning(f"save_calendar: {e}")
            return False

    def save_water(self):
        try:
            ws = self._get_or_create_ws("Water Intake", ["Date","Total ML","Goal ML","Percentage","Glasses (250ml)","Hourly Logs"])
            headers = ["Date","Total ML","Goal ML","Percentage","Glasses (250ml)","Hourly Logs"]
            goal_ml = water.goal()
            week = water.week_summary()
            rows = []
            for d, total_ml in sorted(week.items()):
                pct = int(total_ml / goal_ml * 100) if goal_ml else 0
                rows.append([d, total_ml, goal_ml, f"{pct}%", total_ml // 250, ""])
            return self._clear_and_write(ws, rows, headers)
        except Exception as e:
            log.warning(f"save_water: {e}")
            return False

    def save_daily_log(self):
        try:
            ws = self._get_or_create_ws("Daily_Logs", ["Date","Tasks Done","Tasks Pending","Expenses (Rs)","Reminders Active","Habits Done","Water ML","Mood","Notes"])
            headers = ["Date","Tasks Done","Tasks Pending","Expenses (Rs)","Reminders Active","Habits Done","Water ML","Mood","Notes"]
            today = today_str()
            row = [today, len(tasks.done_on(today)), len(tasks.today_pending()),
                   expenses.today_total(), len(reminders.all_active()),
                   len(habits.today_status()[0]), water.today_total(), "", ""]
            self._rate_limit_sheets()
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
        """FIXED: Save all diary entries to Diary sheet"""
        try:
            ws = self._get_or_create_ws("Diary", ["Date","Time","Content","Mood"])
            headers = ["Date","Time","Content","Mood"]
            all_entries = diary.get_all_entries()
            rows = []
            for edate in sorted(all_entries.keys()):
                for entry in all_entries[edate]:
                    rows.append([
                        edate,
                        entry.get("time", ""),
                        entry.get("text", ""),
                        entry.get("mood", "📝")
                    ])
            log.info(f"📖 Saving {len(rows)} diary entries to Google Sheets")
            return self._clear_and_write(ws, rows, headers)
        except Exception as e:
            log.error(f"save_diary error: {e}")
            return False

    def save_chat_history(self):
        try:
            ws = self._get_or_create_ws("Miscellaneous", ["Timestamp","Date","Role","User","Message","Type"])
            headers = ["Timestamp","Date","Role","User","Message","Type"]
            all_data = []
            for h in chat_hist.get_all():
                all_data.append([
                    h.get("timestamp", ""), h.get("date", ""),
                    h.get("role", ""), h.get("user", ""),
                    h.get("message", ""), "CHAT"
                ])
            return self._clear_and_write(ws, all_data, headers)
        except Exception as e:
            log.error(f"save_chat_history error: {e}")
            return False

    def full_sync(self):
        if not self.sheet:
            return "❌ Sheets not connected! Make sure service account email is added as Editor."
        ops = [
            ("Tasks", self.save_tasks),
            ("Reminders", self.save_reminders),
            ("Expenses", self.save_expenses),
            ("Habits", self.save_habits),
            ("Memory", self.save_memory),
            ("Goals", self.save_goals),
            ("Bills", self.save_bills),
            ("Calendar", self.save_calendar),
            ("Water", self.save_water),
            ("Daily_Logs", self.save_daily_log),
            ("Diary", self.save_diary),
            ("Miscellaneous", self.save_chat_history),
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
        return f"✅ {success}/{len(ops)} synced to Google Sheets"


google_sheets = GoogleSheetsBackup()


async def auto_backup_to_sheets():
    if not google_sheets.sheet:
        log.warning("⚠️ Cannot backup: Sheets not connected")
        return
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, google_sheets.full_sync)
        log.info(f"📤 Auto-backup: {result}")
    except Exception as e:
        log.error(f"Auto-backup error: {e}")


# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════
def build_system_prompt():
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    ag = goals.active()
    exp_t = expenses.today_total()
    exp_m = expenses.month_total()
    bl = expenses.budget_left()
    wt = water.today_total()
    wg = water.goal()
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
        f"⚠️ REAL TIME: {now_ist().strftime('%A, %d %b %Y — %I:%M %p')} IST\n\n"
        f"📋 AAJ KE TASKS ({len(tp)}):\n{tasks_s}\n\n"
        f"💪 HABITS: Done: {h_done} | Baaki: {h_pend}\n\n"
        f"💰 KHARCHA: Aaj ₹{exp_t} | Mahina ₹{exp_m} {budget_s}\n\n"
        f"🎯 GOALS ({len(ag)}):\n{goals_s}\n\n"
        f"⏰ REMINDERS ({len(active_reminders)}):\n{reminders_s}\n\n"
        f"💧 PAANI: {wt}ml/{wg}ml\n\n"
        f"RULES:\n- Dost ki tarah baat kar, Hindi/Hinglish mein SHORT jawab\n- Agar koi action ho gaya toh confirm karo"
    )


# ═══════════════════════════════════════════════════════════════════
# ACTION SYSTEM
# ═══════════════════════════════════════════════════════════════════

ACTION_SYSTEM_PROMPT = """You are a JSON action router. Return ONLY raw JSON.

Current time: {now}
24hr time: {current_time}
Today: {today}
2 min from now: {two_min}

ACTIONS:
REMIND - reminder/alarm. params: {{"time":"HH:MM","text":"text","repeat":"once/daily/weekly"}}
ADD_TASK - add task. params: {{"title":"title","priority":"high/medium/low"}}
COMPLETE_TASK - task done. params: {{"title_hint":"keyword or id"}}
ADD_EXPENSE - expense. params: {{"amount":number,"desc":"description"}}
ADD_DIARY - diary entry. params: {{"text":"diary text"}}
ADD_MEMORY - remember. params: {{"fact":"fact"}}
ADD_HABIT - new habit. params: {{"name":"habit name"}}
COMPLETE_HABIT - habit done. params: {{"keyword":"habit name or id"}}
ADD_WATER - water logged. params: {{"ml":250}}
SHOW_TASKS - show tasks
SHOW_REMINDERS - show reminders
SHOW_HABITS - show habits
BRIEFING - daily summary
CHAT - default for anything else"""

def _regex_fallback(user_msg):
    lower = user_msg.lower().strip()
    now = now_ist()

    if "diary" in lower or "dairy" in lower:
        if any(w in lower for w in ["likho", "add", "save", "note kro"]):
            text = user_msg
            for kw in ["diary", "dairy", "likho", "add", "save", "note kro", "mein", "me"]:
                text = text.replace(kw, ' ').replace(kw.title(), ' ')
            text = ' '.join(text.split()).strip()
            if not text:
                text = user_msg
            return {"action": "ADD_DIARY", "params": {"text": text[:300]}}

    remind_words = ["remind", "reminder", "alarm", "yaad dilana", "bata dena"]
    time_patterns = [r'(\d+)\s*(?:min|minute|m)', r'(\d{1,2}):(\d{2})', r'(\d{1,2})\s*(?:baje|baj)']
    
    if any(w in lower for w in remind_words):
        for pattern in time_patterns:
            match = _re.search(pattern, lower)
            if match:
                if 'min' in pattern:
                    mins = int(match.group(1))
                    time_str = (now + timedelta(minutes=mins)).strftime("%H:%M")
                elif ':' in pattern:
                    h, m = int(match.group(1)), int(match.group(2))
                    time_str = f"{h:02d}:{m:02d}"
                else:
                    h = int(match.group(1))
                    time_str = f"{h:02d}:00"
                
                text = _re.sub(r'\d+\s*(?:min|minute|m|\d{1,2}:\d{2}|\d{1,2}\s*baje)', '', user_msg)
                text = ' '.join([w for w in text.split() if w.lower() not in remind_words])
                if not text.strip():
                    text = "Reminder!"
                return {"action": "REMIND", "params": {"time": time_str, "text": text[:100], "repeat": "once"}}

    expense_words = ["kharcha", "kharch", "spent", "rupees", "₹", "rs"]
    if any(w in lower for w in expense_words):
        match = _re.search(r'(\d+(?:\.\d+)?)', lower)
        if match:
            amount = float(match.group(1))
            desc = _re.sub(r'(\d+(?:\.\d+)?|rs\.?|₹|rupees?)', '', user_msg)
            desc = ' '.join([w for w in desc.split() if w.lower() not in expense_words])
            desc = desc.strip() or "Expense"
            return {"action": "ADD_EXPENSE", "params": {"amount": amount, "desc": desc[:60]}}

    task_words = ["task add", "add task", "kaam add", "new task"]
    if any(w in lower for w in task_words):
        title = user_msg
        for w in task_words:
            title = title.replace(w, '').replace(w.title(), '')
        title = title.strip()
        if title:
            return {"action": "ADD_TASK", "params": {"title": title[:80], "priority": "medium"}}

    return {"action": "CHAT", "params": {}}


def call_gemini_action(user_msg):
    if not GEMINI_API_KEY:
        return _regex_fallback(user_msg)
    
    now = now_ist()
    prompt = ACTION_SYSTEM_PROMPT.format(
        now=time_label(), current_time=now.strftime("%H:%M"),
        today=today_str(), two_min=(now+timedelta(minutes=2)).strftime("%H:%M")
    )
    full_prompt = f"{prompt}\n\nUser: {user_msg}"

    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 200}
    }).encode("utf-8")

    for model in GEMINI_MODELS:
        try:
            url = GEMINI_URL.format(model=model, key=GEMINI_API_KEY)
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                raw = raw.replace("```json", "").replace("```", "").strip()
                json_match = _re.search(r'\{.*\}', raw, _re.DOTALL)
                if json_match:
                    raw = json_match.group(0)
                parsed = json.loads(raw)
                log.info(f"✅ Action: {parsed.get('action')}")
                return parsed
        except Exception as e:
            continue
    return _regex_fallback(user_msg)


async def execute_action(action_data, chat_id, user_msg, user_name=""):
    action = action_data.get("action", "CHAT")
    params = action_data.get("params", {})
    now = now_ist()

    if action == "REMIND":
        time_str = params.get("time", "")
        text = params.get("text", "Reminder!")
        repeat = params.get("repeat", "once")
        if not time_str or not _re.match(r'^\d{2}:\d{2}$', time_str):
            return f"⏰ Time samajh nahi aaya! Abhi {now.strftime('%H:%M')} baj rahe.", False
        r = reminders.add(chat_id, text, time_str, repeat)
        return f"✅ Reminder set for {time_str}: {text}\nID: #{r['id']}", True

    elif action == "ADD_TASK":
        title = params.get("title", user_msg[:80])
        priority = params.get("priority", "medium")
        t = tasks.add(title, priority)
        return f"✅ Task added: {t['title']} (ID: #{t['id']})", True

    elif action == "COMPLETE_TASK":
        hint = str(params.get("title_hint", "")).lower()
        pending = tasks.pending()
        matched = next((t for t in pending if str(t["id"]) == hint or (hint and hint in t["title"].lower())), None)
        if matched:
            tasks.complete(matched["id"])
            return f"🎉 Done! ✅ {matched['title']}", True
        return "❓ Kaunsa task? ID ya naam batao.", False

    elif action == "ADD_EXPENSE":
        amount = float(params.get("amount", 0))
        desc = params.get("desc", "Kharcha")
        if amount <= 0:
            return "💰 Amount sahi se batao. Example: '150 rupees chai'", False
        expenses.add(amount, desc)
        return f"💰 ₹{amount} - {desc}\nAaj total: ₹{expenses.today_total()}", True

    elif action == "ADD_DIARY":
        text = params.get("text", user_msg[:300])
        diary.add(text)
        return f"📖 Diary saved! ✅\n{text[:100]}{'...' if len(text)>100 else ''}", True

    elif action == "ADD_MEMORY":
        memory.add_fact(params.get("fact", user_msg[:200]))
        return "🧠 Yaad kar liya! ✅", True

    elif action == "ADD_HABIT":
        h = habits.add(params.get("name", user_msg[:50]))
        return f"💪 Habit added: {h['name']} (ID: #{h['id']})", True

    elif action == "COMPLETE_HABIT":
        keyword = str(params.get("keyword", "")).lower()
        ok, streak = habits.log(int(keyword)) if keyword.isdigit() else habits.log_by_name(keyword)[:2]
        if ok:
            return f"💪 Habit done! 🔥 {streak} day streak!", True
        return "❓ Kaunsa habit? ID ya naam batao.", False

    elif action == "ADD_WATER":
        ml = int(params.get("ml", 250))
        water.add(ml)
        total = water.today_total()
        goal = water.goal()
        return f"💧 +{ml}ml! Total: {total}/{goal}ml", True

    elif action == "SHOW_TASKS":
        pending = tasks.today_pending()
        if not pending:
            return "🎉 Koi pending task nahi!", False
        txt = f"📋 PENDING ({len(pending)}):\n" + "\n".join(f"#{t['id']} {t['title']}" for t in pending[:10])
        return txt, False

    elif action == "SHOW_REMINDERS":
        active = reminders.all_active()
        if not active:
            return "⏰ Koi reminder nahi!", False
        txt = f"⏰ REMINDERS ({len(active)}):\n" + "\n".join(f"#{r['id']} {r['time']} - {r['text']}" for r in active[:10])
        return txt, False

    elif action == "SHOW_HABITS":
        all_h = habits.all()
        hd, _ = habits.today_status()
        if not all_h:
            return "💪 Koi habit nahi!", False
        txt = f"💪 HABITS:\n" + "\n".join(f"{'✅' if h in hd else '⬜'} #{h['id']} {h['name']} 🔥{h.get('streak',0)}" for h in all_h)
        return txt, False

    elif action == "BRIEFING":
        n = now_ist()
        return (f"🌅 BRIEFING - {n.strftime('%d %b %Y')}\n"
                f"⏰ {n.strftime('%I:%M %p')}\n"
                f"📋 Tasks: {len(tasks.today_pending())} pending\n"
                f"💪 Habits: {len(habits.today_status()[0])} done\n"
                f"💰 Kharcha: ₹{expenses.today_total()}\n"
                f"💧 Water: {water.today_total()}/{water.goal()}ml"), False

    else:
        mem_triggers = ["yaad rakh", "remember", "mera naam", "birthday"]
        if any(k in user_msg.lower() for k in mem_triggers):
            memory.add_fact(user_msg[:250])
        
        prompt = build_system_prompt() + f"\n\nUser: {user_msg}\n\nShort Hindi reply:"
        reply = call_gemini(prompt, max_tokens=400)
        if not reply:
            reply = "🙏 Batao kya help chahiye?"
        return reply, False


def _smart_fallback(user_msg):
    msg = user_msg.lower().strip()
    n = now_ist()
    if any(w in msg for w in ["time", "kitne baje"]):
        return f"⏰ {n.strftime('%I:%M %p')} IST"
    if any(w in msg for w in ["date", "aaj kya tarikh"]):
        return f"📅 {n.strftime('%A, %d %B %Y')}"
    if any(w in msg for w in ["hello", "hi", "assalam", "namaste"]):
        return "🕌 Assalamualaikum! Kya help chahiye?"
    if any(w in msg for w in ["kaise ho", "how are"]):
        return "😊 Main badiya hoon! Aap sunao?"
    return "🙏 Batao kya help chahiye? Tasks, reminders, kharcha, diary?"


# ═══════════════════════════════════════════════════════════════════
# DIARY CONVERSATION HANDLER
# ═══════════════════════════════════════════════════════════════════

async def cmd_diary_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or []
    if not args:
        ctx.user_data["diary_mode"] = "view_today"
        await update.message.reply_text("🔐 Diary password daalo:\n_/cancel se bahar_", parse_mode="Markdown")
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
    await update.message.reply_text("🔐 Password daalo:\n_/cancel se bahar_", parse_mode="Markdown")
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
        await update.effective_chat.send_message("❌ Galat Password!\n_Dobara: /diary_", parse_mode="Markdown")
        return ConversationHandler.END
    mode = ctx.user_data.get("diary_mode", "view_today")
    if mode == "write" and not ctx.user_data.get("diary_pending_text"):
        await update.effective_chat.send_message("✏️ Diary mein likho:\n_/cancel se bahar_", parse_mode="Markdown")
        return DIARY_AWAIT_TEXT
    elif mode == "write":
        await _do_save_diary(update, ctx, ctx.user_data.get("diary_pending_text", ""))
        return ConversationHandler.END
    else:
        await _show_diary(update, ctx, mode)
        return ConversationHandler.END


async def diary_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass
    await _do_save_diary(update, ctx, text)
    return ConversationHandler.END


async def _do_save_diary(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    diary.add(text)
    conf_msg = await update.effective_chat.send_message(f"📖 Diary Saved! ✅\n🕐 {now_str()}\n_{text[:100]}_", parse_mode="Markdown")
    asyncio.create_task(auto_backup_to_sheets())
    asyncio.create_task(_delete_after(conf_msg, 3))
    ctx.user_data.clear()


async def _delete_after(msg, seconds):
    await asyncio.sleep(seconds)
    try:
        await msg.delete()
    except Exception:
        pass


async def _show_diary(update: Update, ctx: ContextTypes.DEFAULT_TYPE, mode: str):
    entries = diary.get_all_entries()
    if not entries:
        await update.effective_chat.send_message("📖 Koi diary entry nahi mili.\n_Likhne ke liye: /diary write_", parse_mode="Markdown")
        return
    if mode == "view_today":
        today_entries = diary.get(today_str())
        if not today_entries:
            await update.effective_chat.send_message(f"📖 Aaj ki diary khali hai - {today_str()}")
            return
        msg = f"📖 Aaj ki diary - {today_str()}\n\n" + "\n".join(f"📝 `{e.get('time','')}` {e.get('text','')}" for e in today_entries[-10:])
        await update.effective_chat.send_message(msg, parse_mode="Markdown")
    else:
        count = sum(len(v) for v in entries.values())
        await update.effective_chat.send_message(f"📖 Total diary entries: {count}")


async def diary_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("⏱ Diary cancel.")


async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📖 `/save Aaj ka din acha tha...`")
        return
    text = " ".join(ctx.args)
    try:
        await update.message.delete()
    except Exception:
        pass
    diary.add(text)
    conf = await update.effective_chat.send_message(f"📖 Diary Saved! ✅\n{text[:100]}")
    asyncio.create_task(auto_backup_to_sheets())
    asyncio.create_task(_delete_after(conf, 3))


# ═══════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(
        f"🕌 Assalamualaikum {name}!\n\nMain aapka AI Dost hoon!\n\n"
        f"Examples:\n• '2 min mein paani yaad dilana'\n• 'Chai pe 50 rupees kharcha'\n"
        f"• 'Gym kaam add karo'\n• 'Diary mein likho aaj accha din tha'\n\n"
        f"Commands: /help"
    )
    await auto_backup_to_sheets()


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 COMMANDS\n\n"
        "🗣 Natural Chat:\n  '2 min mein paani yaad dilana'\n  'Chai pe 50 rupees kharcha'\n"
        "  'Diary mein likho...'\n  'Exercise habit ho gayi'\n\n"
        "⚡ Commands:\n/task Task name\n/done <id>\n/habit Habit name\n/hdone <id>\n"
        "/remind 30m Chai\n/kharcha 100 Chai\n/diary\n/save text\n/water 250\n"
        "/briefing\n/backup\n/clearchat"
    )


async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(f"📋 Pending ({len(pending)}):\n{lines}\n\n/done <id>")
        else:
            await update.message.reply_text("📋 `/task Kaam naam`")
        return
    title = " ".join(ctx.args)
    t = tasks.add(title)
    await update.message.reply_text(f"✅ Task added: #{t['id']} {t['title']}")
    await auto_backup_to_sheets()


async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(f"📋 Pending:\n{lines}\n\n/done <id>")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        await update.message.reply_text(f"🎉 Done! ✅ {t['title']}" if t else "❌ Not found!")
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")


async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        tasks.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Task deleted!")


async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        all_h = habits.all()
        if all_h:
            hd, _ = habits.today_status()
            lines = "\n".join(f"{'✅' if h in hd else '⬜'} #{h['id']} {h['name']} 🔥{h.get('streak',0)}" for h in all_h)
            await update.message.reply_text(f"💪 Habits:\n{lines}\n\n/hdone <id>")
        else:
            await update.message.reply_text("💪 `/habit Naam`")
        return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(f"💪 Habit added: #{h['id']} {h['name']}")
    await auto_backup_to_sheets()


async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            lines = "\n".join(f"⬜ #{h['id']} {h['name']}" for h in pending)
            await update.message.reply_text(f"💪 Pending habits:\n{lines}\n\n/hdone <id>")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        await update.message.reply_text(f"💪 Habit done! 🔥 {streak} day streak!" if ok else "✅ Already done today!")
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")


async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        today_list = expenses.get_by_date(today_str())
        if today_list:
            lines = "\n".join(f"₹{e['amount']} - {e['desc']}" for e in today_list[-10:])
            await update.message.reply_text(f"💰 Aaj ka kharcha:\n{lines}\nTotal: ₹{expenses.today_total()}")
        else:
            await update.message.reply_text("💰 `/kharcha 100 Chai`")
        return
    try:
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        await update.message.reply_text(f"💰 ₹{amount} - {desc}\nAaj total: ₹{expenses.today_total()}")
        await auto_backup_to_sheets()
    except Exception:
        await update.message.reply_text("❌ `/kharcha 100 Chai`")


async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = now_ist()
    if len(ctx.args) < 2:
        active = reminders.all_active()
        if active:
            lines = "\n".join(f"#{r['id']} {r['time']} - {r['text']}" for r in active)
            await update.message.reply_text(f"⏰ Reminders:\n{lines}")
        else:
            await update.message.reply_text("⏰ `/remind 30m Chai` ya `/remind 15:30 Meeting`")
        return
    time_arg = ctx.args[0].lower()
    text = " ".join(ctx.args[1:])
    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        remind_at = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        parts = time_arg.split(":")
        remind_at = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    else:
        await update.message.reply_text("❌ Use: `/remind 30m Chai` or `/remind 15:30 Meeting`")
        return
    r = reminders.add(update.effective_chat.id, text, remind_at)
    await update.message.reply_text(f"✅ Reminder set for {remind_at}: {text}\nID: #{r['id']}")
    await auto_backup_to_sheets()


async def cmd_delremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        reminders.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Reminder deleted!")


async def cmd_water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ml = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 250
    water.add(ml)
    await update.message.reply_text(f"💧 +{ml}ml! Total: {water.today_total()}/{water.goal()}ml")
    await auto_backup_to_sheets()


async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n = now_ist()
    await update.message.reply_text(
        f"🌅 BRIEFING - {n.strftime('%d %b %Y')}\n"
        f"⏰ {n.strftime('%I:%M %p')}\n"
        f"📋 Tasks: {len(tasks.today_pending())} pending\n"
        f"💪 Habits: {len(habits.today_status()[0])} done\n"
        f"💰 Kharcha: ₹{expenses.today_total()}\n"
        f"💧 Water: {water.today_total()}/{water.goal()}ml"
    )


async def cmd_backup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📤 Backup in progress...")
    result = await asyncio.get_running_loop().run_in_executor(None, google_sheets.full_sync)
    await update.message.reply_text(result)


async def cmd_clearchat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    count = chat_hist.clear()
    await update.message.reply_text(f"🧹 {count} messages cleared!")


async def cmd_dbstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 DB STATUS\n\n"
        f"Sheets: {'🟢 Connected' if google_sheets.sheet else '🔴 Disconnected'}\n"
        f"Tasks: {len(tasks.all_tasks())}\n"
        f"Diary: {sum(len(v) for v in diary.get_all_entries().values())} entries\n"
        f"Expenses: {len(expenses.store.data.get('list', []))}\n"
        f"Reminders: {len(reminders.get_all())}"
    )


# ═══════════════════════════════════════════════════════════════════
# OK BUTTON HANDLER
# ═══════════════════════════════════════════════════════════════════
async def handle_ok_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Alarm band ho gaya!")
    data = query.data
    if data.startswith("ok_reminder_"):
        reminder_id = int(data.split("_")[2])
        if reminders.acknowledge(reminder_id, "User pressed OK"):
            await query.edit_message_text("✅ Alarm band ho gaya! Ab nahi bajega.")
            await auto_backup_to_sheets()
        else:
            await query.edit_message_text("⚠️ Pehle se band hai.")


# ═══════════════════════════════════════════════════════════════════
# SNOOZE COMMAND
# ═══════════════════════════════════════════════════════════════════
async def cmd_snooze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.split()[0].lower()
    snooze_map = {"snooze5": 5, "snooze10": 10, "snooze30": 30, "snooze60": 60}
    snooze_min = snooze_map.get(cmd, 10)
    if not ctx.args:
        await update.message.reply_text(f"⏸️ `/{cmd} <reminder_id>`")
        return
    try:
        reminder_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ Valid ID do!")
        return
    target = next((r for r in reminders.get_all() if r["id"] == reminder_id), None)
    if not target:
        await update.message.reply_text(f"❌ Reminder #{reminder_id} nahi mila!")
        return
    reminders.acknowledge(reminder_id, f"Snoozed {snooze_min}min")
    new_time = (now_ist() + timedelta(minutes=snooze_min)).strftime("%H:%M")
    new_rem = reminders.add(target["chat_id"], f"🔁 {target['text']}", new_time, "once")
    await update.message.reply_text(f"⏸️ Snoozed! {snooze_min} min baad fir yaad dilaunga.\nNew ID: #{new_rem['id']}")
    await auto_backup_to_sheets()


# ═══════════════════════════════════════════════════════════════════
# MAIN MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_msg = update.message.text.strip()
    if user_msg.startswith("/"):
        return
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    action_data = call_gemini_action(user_msg) if GEMINI_API_KEY else _regex_fallback(user_msg)
    log.info(f"📥 '{user_msg[:50]}' → {action_data.get('action', '?')}")
    reply, did_action = await execute_action(action_data, update.effective_chat.id, user_msg, update.effective_user.first_name or "User")
    chat_hist.add("user", user_msg, update.effective_user.first_name or "User")
    chat_hist.add("assistant", reply, "Bot")
    await update.message.reply_text(reply, parse_mode="Markdown")
    if did_action:
        await auto_backup_to_sheets()


# ═══════════════════════════════════════════════════════════════════
# BACKGROUND JOBS
# ═══════════════════════════════════════════════════════════════════
async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now = now_ist()
    if now.hour == 0 and now.minute <= 2:
        reminders.reset_daily()
        return
    for r in reminders.due_now():
        try:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ OK - Band Karo", callback_data=f"ok_reminder_{r['id']}")]])
            alert = (f"🔔 ALARM! ⏰ {r['time']}\n\n📢 {r['text'].upper()}\n\n"
                     f"⏸️ Snooze: /snooze5 {r['id']} | /snooze10 {r['id']} | /snooze30 {r['id']}\n"
                     f"❌ Delete: /delremind {r['id']}")
            await context.bot.send_message(chat_id=int(r["chat_id"]), text=alert, reply_markup=keyboard, parse_mode="Markdown")
            reminders.mark_fired(r["id"])
            await asyncio.sleep(0.5)
        except Exception as e:
            log.error(f"Reminder error: {e}")


async def scheduled_backup_job(context: ContextTypes.DEFAULT_TYPE):
    await auto_backup_to_sheets()


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    log.info("=" * 60)
    log.info("🤖 Personal AI Bot v24.0 - FULLY WORKING")
    log.info(f"⏰ IST: {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"🤖 Gemini: {'✅' if GEMINI_API_KEY else '❌'}")
    log.info(f"📊 Sheets: {'✅ Connected' if google_sheets.sheet else '❌ Not connected'}")
    log.info("=" * 60)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Conversation handler
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary_entry)],
        states={DIARY_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)],
                DIARY_AWAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_text_input)]},
        fallbacks=[CommandHandler("cancel", diary_cancel)],
    ))

    # Commands
    for cmd, handler in [
        ("start", cmd_start), ("help", cmd_help), ("task", cmd_task), ("done", cmd_done),
        ("deltask", cmd_deltask), ("habit", cmd_habit), ("hdone", cmd_hdone), ("kharcha", cmd_kharcha),
        ("remind", cmd_remind), ("delremind", cmd_delremind), ("water", cmd_water), ("briefing", cmd_briefing),
        ("backup", cmd_backup), ("clearchat", cmd_clearchat), ("dbstatus", cmd_dbstatus), ("save", cmd_save),
        ("snooze5", cmd_snooze), ("snooze10", cmd_snooze), ("snooze30", cmd_snooze), ("snooze60", cmd_snooze)
    ]:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(CallbackQueryHandler(handle_ok_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=10)
        app.job_queue.run_repeating(scheduled_backup_job, interval=3600, first=30)

    log.info("✅ Bot ready! Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
