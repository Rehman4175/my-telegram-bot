#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v22.0  NO BUTTONS + REAL ACTIONS   ║
║  ✅ Natural language se REAL kaam hoga — sirf reply nahi        ║
║  ✅ Reminders actually set honge, tasks actually add honge      ║
║  ✅ Google Sheets sync intact                                   ║
║  ✅ Gemini JSON action engine (old v14 proven system)           ║
║  ✅ Diary password flow                                         ║
║  ✅ Background alarms/reminders                                 ║
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

    def complete_by_title(self, keyword):
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
            if rows: self._upsert_by_id(ws, rows, 0)
            return True
        except Exception as e:
            log.warning(f"save_tasks: {e}"); return False

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
            if rows: self._upsert_by_id(ws, rows, 0)
            return True
        except Exception as e:
            log.warning(f"save_reminders: {e}"); return False

    def save_expenses(self):
        try:
            ws = self.sheet.worksheet("Expenses")
            rows = [
                [e.get("date",""), e.get("amount",0),
                 e.get("desc",""), e.get("category","general"), e.get("time","")]
                for e in expenses.store.data.get("list", [])
            ]
            if rows: self._append_unique(ws, rows, [0, 1, 2])
            return True
        except Exception as e:
            log.warning(f"save_expenses: {e}"); return False

    def save_habits(self):
        try:
            ws = self.sheet.worksheet("Habits")
            rows = [
                [str(h.get("id","")), h.get("name",""), h.get("emoji","✅"),
                 h.get("streak",0), h.get("best_streak",0),
                 h.get("created",""), h.get("target","")]
                for h in habits.all()
            ]
            if rows: self._upsert_by_id(ws, rows, 0)
            return True
        except Exception as e:
            log.warning(f"save_habits: {e}"); return False

    def save_memory(self):
        try:
            ws = self.sheet.worksheet("Memory / Important Notes")
            rows = [
                [f.get("d",""), "Fact", f.get("f",""), "", "Medium"]
                for f in memory.get_all_facts()
            ]
            if rows: self._append_unique(ws, rows, [0, 2])
            return True
        except Exception as e:
            log.warning(f"save_memory: {e}"); return False

    def save_goals(self):
        try:
            ws = self.sheet.worksheet("Goals")
            rows = [
                [str(g.get("id","")), g.get("title",""), g.get("progress",0),
                 "Done" if g.get("done") else "Active",
                 g.get("deadline",""), g.get("created",""), g.get("milestones","")]
                for g in goals.active() + goals.completed()
            ]
            if rows: self._upsert_by_id(ws, rows, 0)
            return True
        except Exception as e:
            log.warning(f"save_goals: {e}"); return False

    def save_bills(self):
        try:
            ws = self.sheet.worksheet("Bills & Subscriptions")
            rows = [
                [str(b.get("id","")), b.get("name",""), b.get("amount",0),
                 str(b.get("due_day","")), b.get("auto_pay","No"),
                 "Paid" if bills.is_paid_this_month(b["id"]) else "Pending",
                 b.get("payment_method",""), b.get("notes","")]
                for b in bills.all_active()
            ]
            if rows: self._upsert_by_id(ws, rows, 0)
            return True
        except Exception as e:
            log.warning(f"save_bills: {e}"); return False

    def save_calendar(self):
        try:
            ws = self.sheet.worksheet("Calendar Events")
            rows = [
                [e.get("date",""), e.get("time",""), e.get("title",""),
                 e.get("location",""), e.get("reminder_set","Yes"),
                 e.get("participants",""), e.get("notes","")]
                for e in calendar.store.data.get("events", [])
            ]
            if rows: self._append_unique(ws, rows, [0, 2])
            return True
        except Exception as e:
            log.warning(f"save_calendar: {e}"); return False

    def save_water(self):
        try:
            ws = self.sheet.worksheet("Water Intake")
            goal_ml = water.goal()
            week = water.week_summary()
            rows = []
            for d, total_ml in sorted(week.items()):
                pct = int(total_ml / goal_ml * 100) if goal_ml else 0
                rows.append([d, total_ml, goal_ml, f"{pct}%", total_ml // 250, ""])
            if rows: self._upsert_by_id(ws, rows, 0)
            return True
        except Exception as e:
            log.warning(f"save_water: {e}"); return False

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
            log.warning(f"save_daily_log: {e}"); return False

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
            log.warning(f"save_diary: {e}"); return False

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
                    new_rows.append([ts, h.get("date",""), role, h.get("user",""), msg])
                    existing_keys.add(key)
            if new_rows:
                for row in new_rows:
                    ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            log.error(f"save_chat_history error: {e}"); return False

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
# SYSTEM PROMPT (for normal chat)
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
        f"⚠️ REAL TIME: {now_ist().strftime('%A, %d %b %Y — %I:%M %p')} IST\n\n"
        f"📋 AAJ KE TASKS ({len(tp)}):\n{tasks_s}\n\n"
        f"💪 HABITS: Done: {h_done} | Baaki: {h_pend}\n\n"
        f"💰 KHARCHA: Aaj ₹{exp_t} | Mahina ₹{exp_m} {budget_s}\n\n"
        f"🎯 GOALS ({len(ag)}):\n{goals_s}\n\n"
        f"⏰ REMINDERS ({len(active_reminders)}):\n{reminders_s}\n\n"
        f"💧 PAANI: {wt}ml/{wg}ml\n\n"
        f"RULES:\n"
        f"- Dost ki tarah baat kar, Hindi/Hinglish mein SHORT jawab (2-4 lines)\n"
        f"- Agar koi action ho gaya toh confirm karo clearly\n"
        f"- Commands bhi yaad dilao agar needed: /task /remind /kharcha /diary /habit"
    )


# ═══════════════════════════════════════════════════════════════════
# ACTION SYSTEM — Gemini JSON router (proven from v14)
# ═══════════════════════════════════════════════════════════════════

ACTION_SYSTEM_PROMPT = """You are a JSON action router for a personal assistant bot. Parse the user message and return ONLY raw JSON — no markdown, no backticks, no extra text.

Current EXACT time: {now}
24hr time: {current_time}
Today: {today}
2 min from now: {two_min}

JSON format: {{"action":"ACTION","params":{{...}}}}

ACTIONS and when to use them:
REMIND — User EXPLICITLY asks for reminder/alarm/yaad dilana. params: {{"time":"HH:MM","text":"reminder text","repeat":"once/daily/weekly"}}
ADD_TASK — User wants to add a task/kaam/todo. params: {{"title":"task title","priority":"high/medium/low"}}
COMPLETE_TASK — User says task done/complete/ho gaya. params: {{"title_hint":"keyword or id"}}
ADD_EXPENSE — User mentions spending money/kharcha/rupees. params: {{"amount":number,"desc":"description","category":"general"}}
ADD_DIARY — User wants to write diary. params: {{"text":"diary text","mood":"😊"}}
ADD_MEMORY — User says "remember this" or "yaad rakh". params: {{"fact":"the fact"}}
ADD_HABIT — User wants to add a new habit. params: {{"name":"habit name","emoji":"💪"}}
COMPLETE_HABIT — User says habit done/ho gayi. params: {{"keyword":"habit name or id"}}
ADD_WATER — User says water piya/paani piya. params: {{"ml":250}}
SHOW_TASKS — User asks to see tasks/pending kaam.
SHOW_REMINDERS — User asks to see reminders.
SHOW_HABITS — User asks to see habits.
BRIEFING — User wants daily summary/status/aaj kya hai.
CHAT — Default for greetings, questions, casual talk, anything else.

IMPORTANT:
- Time relative to now: "2 min mein" = {two_min}, "30 min mein" = calculate from {current_time}
- "baje" = clock time (5 baje = 17:00 if evening)
- Return CHAT for greetings (hello, hi, kaise ho) and general questions
- Only return REMIND if user explicitly asks for reminder/alarm
"""

def _regex_fallback(user_msg):
    """Fallback when Gemini fails — regex-based action detection"""
    lower = user_msg.lower().strip()
    now = now_ist()

    # Explicit reminder keywords
    remind_explicit = [
        "remind", "reminder", "alarm", "yaad dila", "yaad dilana", "yaad dilao",
        "alarm laga", "alarm set", "remind kar", "reminder set", "notify",
        "bata dena", "bhool mat", "wake", "uthana"
    ]
    has_time = bool(_re.search(r'(\d{1,2}):(\d{2})', lower))
    has_minutes = bool(_re.search(r'(\d+)\s*(?:minute|min|mins|minut)', lower))
    has_hours = bool(_re.search(r'(\d+)\s*(?:ghante|ghanta|hour|hr)', lower))
    has_baje = bool(_re.search(r'(\d{1,2})\s*(?:baje|bajay|baj)', lower))

    is_explicit_reminder = any(r in lower for r in remind_explicit)
    should_remind = is_explicit_reminder or (
        (has_time or has_minutes or has_hours or has_baje) and
        any(k in lower for k in ["yaad", "remind", "alarm", "bata", "notify"])
    )

    if should_remind:
        time_str = None
        m = _re.search(r'(\d+)\s*(?:minute|min|mins|minut)', lower)
        if m:
            time_str = (now + timedelta(minutes=int(m.group(1)))).strftime("%H:%M")
        if not time_str:
            m = _re.search(r'(\d+)\s*(?:ghante|ghanta|hour|hr)', lower)
            if m:
                time_str = (now + timedelta(hours=int(m.group(1)))).strftime("%H:%M")
        if not time_str:
            m = _re.search(r'(\d{1,2}):(\d{2})', lower)
            if m:
                h, mn = int(m.group(1)), int(m.group(2))
                if 0 <= h <= 23 and 0 <= mn <= 59:
                    time_str = f"{h:02d}:{mn:02d}"
        if not time_str:
            m = _re.search(r'(\d{1,2})\s*(?:baje|bajay|baj)', lower)
            if m:
                h = int(m.group(1))
                if any(w in lower for w in ['raat', 'sham', 'evening', 'night', 'pm']):
                    h = h + 12 if h < 12 else h
                elif any(w in lower for w in ['subah', 'savere', 'morning', 'am']):
                    h = h if h < 12 else h - 12
                else:
                    h = h + 12 if 1 <= h <= 6 else h
                time_str = f"{h:02d}:00"
        if time_str:
            text = user_msg
            text = _re.sub(r'\d+\s*(?:minute|min|mins|minut|ghante|ghanta|hour|hr)', '', text, flags=_re.I)
            text = _re.sub(r'\d{1,2}(?::\d{2})?\s*(?:baje|bajay|baj)?', '', text, flags=_re.I)
            for kw in remind_explicit + ["baad", "mein", "ke", "liye", "set", "karo", "do", "please", "plz"]:
                text = text.replace(kw, ' ')
            text = ' '.join(text.split()).strip()
            if not text or len(text) < 2:
                text = "⏰ Reminder!"
            repeat = "daily" if any(w in lower for w in ["daily", "roz", "har din", "everyday"]) else \
                     "weekly" if any(w in lower for w in ["weekly", "hafte", "har hafte"]) else "once"
            return {"action": "REMIND", "params": {"time": time_str, "text": text[:100], "repeat": repeat}}

    # Task detection
    task_words = ["task add", "add task", "karna hai mujhe", "kaam add", "new task",
                  "todo add", "task create", "kaam hai", "kaam karna hai"]
    if any(t in lower for t in task_words):
        title = _re.sub(
            r'(task add|add task|karna hai|kaam add|new task|todo add|task create|kaam hai mujhe)', '',
            user_msg, flags=_re.I
        ).strip()
        if title:
            return {"action": "ADD_TASK", "params": {"title": title[:80], "priority": "medium"}}

    # Task done
    task_done_words = ["task done", "kaam ho gaya", "ho gaya", "complete kar liya", "kar liya",
                       "finish ho gaya", "khatam", "mark done", "done kar"]
    if any(t in lower for t in task_done_words):
        m = _re.search(r'#?(\d+)', lower)
        hint = m.group(1) if m else ""
        return {"action": "COMPLETE_TASK", "params": {"title_hint": hint or lower[:30]}}

    # Habit done
    habit_done_words = ["habit done", "habit ho gayi", "habit complete", "hdone"]
    if any(t in lower for t in habit_done_words):
        m = _re.search(r'#?(\d+)', lower)
        hint = m.group(1) if m else lower[:30]
        return {"action": "COMPLETE_HABIT", "params": {"keyword": hint}}

    # Expense detection
    if any(w in lower for w in ["kharcha", "kharch", "spent", "rupees", "₹", "rs ", "paisa", "paise",
                                  "khaya", "piya", "kharida", "buy", "bought", "paid", "payment"]):
        m = _re.search(r'(\d+(?:\.\d+)?)', lower)
        amount = float(m.group(1)) if m else 0
        if amount > 0:
            desc = _re.sub(r'(\d+(?:\.\d+)?|rs\.?|₹|rupees?|rupe|kharcha|kharch|spent|spent on|ke liye|ka|ke|ki|mein|par|pr)', '', user_msg, flags=_re.I).strip()
            desc = ' '.join(desc.split()).strip() or "Expense"
            return {"action": "ADD_EXPENSE", "params": {"amount": amount, "desc": desc[:60], "category": "general"}}

    # Water
    water_words = ["paani piya", "water piya", "paani pi", "water pi", "water log", "paani log"]
    if any(w in lower for w in water_words):
        m = _re.search(r'(\d+)\s*(ml|glass|bottle|liter|litre)', lower)
        ml = 250
        if m:
            val, unit = int(m.group(1)), m.group(2)
            ml = val * 1000 if "liter" in unit or "litre" in unit else \
                 val * 500 if "bottle" in unit else \
                 val * 250 if "glass" in unit else val
        return {"action": "ADD_WATER", "params": {"ml": ml}}

    return {"action": "CHAT", "params": {}}


def call_gemini_action(user_msg):
    """Call Gemini to get JSON action"""
    now = now_ist()
    two_min = (now + timedelta(minutes=2)).strftime("%H:%M")
    prompt = ACTION_SYSTEM_PROMPT.format(
        now=time_label(),
        current_time=now.strftime("%H:%M"),
        today=today_str(),
        two_min=two_min
    )
    full_prompt = f"{prompt}\n\nUser: {user_msg}"

    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 200}
    }).encode("utf-8")

    for model in ["gemini-2.5-flash-lite", "gemini-2.5-flash"]:
        try:
            url = GEMINI_URL.format(model=model, key=GEMINI_API_KEY)
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                raw = raw.replace("```json", "").replace("```", "").strip()
                json_match = _re.search(r'\{.*\}', raw, _re.DOTALL)
                if json_match:
                    raw = json_match.group(0)
                parsed = json.loads(raw)
                log.info(f"✅ Action detected: {parsed.get('action')} via {model}")
                return parsed
        except Exception as e:
            log.warning(f"Action detection fail ({model}): {e}")
            continue

    return _regex_fallback(user_msg)


async def execute_action(action_data, chat_id, user_msg, user_name=""):
    """Execute the detected action and return reply string"""
    action = action_data.get("action", "CHAT")
    params = action_data.get("params", {})
    now = now_ist()
    do_backup = True

    if action == "REMIND":
        time_str = params.get("time", "")
        text = params.get("text", "⏰ Reminder!")
        repeat = params.get("repeat", "once")
        if not time_str or not _re.match(r'^\d{2}:\d{2}$', time_str):
            do_backup = False
            return f"⏰ Time samajh nahi aaya! Abhi *{now.strftime('%H:%M')}* baj rahe hain.\nExample: '30 min mein chai yaad dilana'", False
        r = reminders.add(chat_id, text, time_str, repeat)
        rl = {"once": "Ek baar 1️⃣", "daily": "Roz 🔁", "weekly": "Har hafte 📅"}.get(repeat, repeat)
        return (f"✅ *Reminder Set!*\n"
                f"⏰ *{time_str}* — {text}\n"
                f"{rl} | 🆔 `#{r['id']}`\n"
                f"_Delete: /delremind {r['id']}_"), True

    elif action == "ADD_TASK":
        title = params.get("title", user_msg[:80])
        priority = params.get("priority", "medium")
        t = tasks.add(title, priority)
        icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        return (f"✅ *Task Added!*\n"
                f"{icons.get(priority,'🟡')} *{t['title']}*\n"
                f"🆔 `#{t['id']}` | _/done {t['id']} se complete karo_"), True

    elif action == "COMPLETE_TASK":
        hint = str(params.get("title_hint", "")).lower()
        pending = tasks.pending()
        matched = None
        if hint.isdigit():
            matched = next((t for t in pending if t["id"] == int(hint)), None)
        if not matched and hint:
            matched = next((t for t in pending if hint in t["title"].lower()), None)
        if not matched and pending:
            matched = pending[-1]
        if matched:
            tasks.complete(matched["id"])
            return f"🎉 *Done!* ✅\n*{matched['title']}* — Khatam! 💪", True
        return "❓ Kaunsa task? `/done <id>` se complete karo ya task ka naam batao.", False

    elif action == "ADD_EXPENSE":
        amount = float(params.get("amount", 0))
        desc = params.get("desc", "Kharcha")
        if amount <= 0:
            return "💰 Amount clear nahi hua. Example: '150 rupees chai pe kharcha'", False
        expenses.add(amount, desc)
        bl = expenses.budget_left()
        budget_line = f"\n💳 Budget baaki: ₹{bl:.0f}" if bl is not None else ""
        return (f"💰 ₹{amount:.0f} — {desc}\n"
                f"📊 Aaj total: ₹{expenses.today_total():.0f}{budget_line}"), True

    elif action == "ADD_DIARY":
        diary.add(params.get("text", user_msg[:200]), params.get("mood", "📝"))
        return f"📖 *Diary saved!* ✅\n🕐 {now_str()}", True

    elif action == "ADD_MEMORY":
        memory.add_fact(params.get("fact", user_msg[:200]))
        return "🧠 *Yaad kar liya!* ✅", True

    elif action == "ADD_HABIT":
        h = habits.add(params.get("name", user_msg[:50]), params.get("emoji", "✅"))
        return (f"💪 *Habit Added!*\n"
                f"{h['emoji']} *{h['name']}*\n"
                f"🆔 `#{h['id']}` | _/hdone {h['id']} se log karo_"), True

    elif action == "COMPLETE_HABIT":
        keyword = str(params.get("keyword", "")).lower()
        hid = None
        if keyword.isdigit():
            hid = int(keyword)
        if hid:
            ok, streak = habits.log(hid)
            h_obj = next((h for h in habits.all() if h["id"] == hid), None)
            h_name = h_obj["name"] if h_obj else f"#{hid}"
        else:
            ok, streak, h_obj = habits.log_by_name(keyword)
            h_name = h_obj["name"] if h_obj else keyword
        if ok:
            return f"💪 *{h_name} — Done!* 🔥 {streak} din streak!", True
        elif h_obj or hid:
            return f"✅ *{h_name}* — Aaj pehle hi log ho chuka hai!", False
        else:
            _, pending_h = habits.today_status()
            if pending_h:
                lines = "\n".join(f"⬜ #{h['id']} {h['name']}" for h in pending_h[:5])
                return f"💪 *Pending habits:*\n\n{lines}\n\n_/hdone <id> likhao_", False
            return "🎊 Aaj sab habits ho gayi!", False

    elif action == "ADD_WATER":
        ml = int(params.get("ml", 250))
        water.add(ml)
        total = water.today_total()
        goal = water.goal()
        pct = int(total / goal * 100) if goal else 0
        bar = "💧" * min(10, pct // 10) + "⬜" * (10 - min(10, pct // 10))
        return f"💧 +{ml}ml logged!\n{bar}\n{total}ml / {goal}ml ({pct}%)", True

    elif action == "SHOW_TASKS":
        pending = tasks.today_pending()
        if not pending:
            return "🎉 Koi pending task nahi! Sab clear!", False
        txt = f"📋 *PENDING ({len(pending)})*\n\n"
        for t in pending[:10]:
            txt += f"{'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} *#{t['id']}* {t['title']}\n"
        txt += "\n_/done <id> se complete karo_"
        return txt, False

    elif action == "SHOW_REMINDERS":
        active = reminders.all_active()
        if not active:
            return "⏰ Koi active reminder nahi!\n_Example: '30 min mein chai yaad dilana'_", False
        txt = f"⏰ *REMINDERS ({len(active)})*\n\n"
        for r in active:
            icon = "🔁" if r.get("repeat") == "daily" else "📅" if r.get("repeat") == "weekly" else "1️⃣"
            txt += f"*#{r['id']}* {icon} `{r['time']}` — {r['text']}\n"
        txt += "\n_/delremind <id> se delete karo_"
        return txt, False

    elif action == "SHOW_HABITS":
        all_h = habits.all()
        hd, hp = habits.today_status()
        if not all_h:
            return "💪 Koi habit nahi! `/habit Naam` se add karo.", False
        txt = f"💪 *HABITS ({len(all_h)})*\n\n"
        for h in all_h:
            done = h in hd
            txt += f"{'✅' if done else '⬜'} *#{h['id']}* {h['emoji']} {h['name']} 🔥{h.get('streak',0)}\n"
        txt += "\n_/hdone <id> se log karo_"
        return txt, False

    elif action == "BRIEFING":
        n = now_ist()
        tp = tasks.today_pending()
        hd, hp = habits.today_status()
        today_ev = calendar.today_events()
        active_rem = reminders.all_active()
        ev_line = f"\n📅 Events: {', '.join(e['title'] for e in today_ev[:3])}" if today_ev else ""
        rem_line = f"\n⏰ Reminders: {len(active_rem)} active" if active_rem else ""
        txt = (f"🌅 *BRIEFING — {n.strftime('%d %b %Y')}*\n"
               f"⏰ {n.strftime('%I:%M %p')} IST\n\n"
               f"📋 Tasks pending: {len(tp)}\n"
               f"💪 Habits done: {len(hd)}/{len(hd)+len(hp)}\n"
               f"💰 Aaj kharcha: ₹{expenses.today_total():.0f}\n"
               f"💧 Water: {water.today_total()}ml/{water.goal()}ml"
               f"{ev_line}{rem_line}")
        return txt, False

    else:  # CHAT
        # Auto memory extraction
        lower = user_msg.lower()
        mem_triggers = ["yaad rakh", "remember", "mera naam", "meri umar", "birthday",
                        "anniversary", "deadline", "important", "mera", "meri"]
        if any(k in lower for k in mem_triggers):
            memory.add_fact(user_msg[:250])

        # Build context
        recent = chat_hist.get_recent(6)
        context_str = ""
        if recent:
            context_lines = [
                f"{'User' if h['role']=='user' else 'Dost'}: {h['message'][:100]}"
                for h in recent[-6:]
            ]
            context_str = "\n\nHALI BAAT:\n" + "\n".join(context_lines)

        prompt = build_system_prompt() + context_str + f"\n\nUser: {user_msg}\n\nShort Hindi reply (2-4 lines):"
        reply = call_gemini(prompt, max_tokens=400)
        if not reply:
            reply = _smart_fallback(user_msg)
        return reply, False


def _smart_fallback(user_msg):
    msg = user_msg.lower().strip()
    n = now_ist()
    if any(w in msg for w in ["time", "kitne baje", "time kya", "time batao"]):
        return f"⏰ Abhi *{n.strftime('%I:%M %p')}* baj rahe hain (IST)"
    if any(w in msg for w in ["date", "aaj kya", "tarikh"]):
        return f"📅 Aaj *{n.strftime('%A, %d %B %Y')}* hai"
    if any(w in msg for w in ["hello", "hi", "assalam", "namaste", "hey"]):
        return "🕌 *Assalamualaikum!* Batao kya help chahiye? 😊"
    if any(w in msg for w in ["kaise ho", "how are", "kya haal"]):
        return "😊 *Main badiya hoon!* Aap sunao, kya ho raha hai?"
    if any(w in msg for w in ["thank", "shukriya", "thanks"]):
        return "🤗 *Welcome!* Aur koi help chahiye toh batao!"
    if any(w in msg for w in ["bye", "allah hafiz", "good night"]):
        return "🌙 *Allah Hafiz!* Apna khayal rakhna! 🤗"
    return "🙏 Batao kya help chahiye? Tasks, reminders, kharcha, ya kuch aur?"


# ═══════════════════════════════════════════════════════════════════
# DIARY — ConversationHandler (password required)
# ═══════════════════════════════════════════════════════════════════

async def cmd_diary_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or []
    if not args:
        ctx.user_data["diary_mode"] = "view_today"
        await update.message.reply_text(
            "🔐 *Diary password daalo:*\n_/cancel se bahar jao_",
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
            f"📖 *Diary Saved!* ✅\n🕐 {now_str()}\n\n_{text[:120]}{'...' if len(text) > 120 else ''}_",
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
            "📖 `/save Aaj ka din acha tha...`", parse_mode="Markdown"
        )
        return
    text = " ".join(ctx.args)
    await _do_save_diary(update, ctx, text)


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
        f"Main aapka AI Dost hoon! Seedha baat karo — REAL kaam hoga.\n\n"
        f"*Examples:*\n"
        f"• '2 min mein paani yaad dilana' → ⏰ Reminder set\n"
        f"• 'Chai pe 50 rupees kharcha' → 💰 Saved\n"
        f"• 'Gym kaam add karo' → 📋 Task added\n"
        f"• 'Exercise habit ho gayi' → 💪 Logged\n\n"
        f"Ya commands: /task /remind /kharcha /diary /habit /help",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *COMMANDS*\n\n"
        "🗣 *Natural Chat (seedha type karo):*\n"
        "  '2 min mein paani yaad dilana'\n"
        "  'Chai pe 50 rupees kharcha'\n"
        "  '30 min mein meeting reminder'\n"
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
        "`/save Aaj ka din...` — Quick diary\n"
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
        priority = "low"; args = args[:-4].strip()
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
                f"📋 *Pending ({len(pending)}):*\n\n{lines}\n\n_/done <id>_",
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
                f"💪 *Habits ({len(all_h)}):*\n\n{lines}\n\n_Done karne ke liye: /hdone <id>_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("💪 `/habit Naam` — Habit add karo", parse_mode="Markdown")
        return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(
        f"💪 Habit added!\n{h['emoji']} *{h['name']}*\n🆔 `#{h['id']}`",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            lines = "\n".join(f"⬜ #{h['id']} {h['name']}" for h in pending)
            await update.message.reply_text(
                f"💪 *Pending Habits:*\n\n{lines}\n\n_/hdone <id>_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("🎊 Aaj ki saari habits complete!")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        await update.message.reply_text(
            f"💪 *Habit Done!* 🔥 {streak} din streak!" if ok else "✅ Already done today!",
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
                f"💰 *Aaj Ka Kharcha:*\n\n{lines}\n\n*Total: ₹{expenses.today_total():.0f}*\n\n"
                f"_Add: /kharcha 100 Chai_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("💰 `/kharcha amount description`")
        return
    try:
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:])
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
        msg = f"💳 *Budget:* ₹{b}\n💰 Is mahine: ₹{expenses.month_total():.0f}"
        if bl is not None:
            msg += f"\n✅ Baaki: ₹{bl:.0f}"
        await update.message.reply_text(msg, parse_mode="Markdown")
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
                f"_Progress: /gprogress <id> <percent>_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("🎯 `/goal Description`")
        return
    g = goals.add(" ".join(ctx.args))
    await update.message.reply_text(f"🎯 Goal set!\n#{g['id']} {g['title']}", parse_mode="Markdown")
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
        await update.message.reply_text("❌ Format: YYYY-MM-DD")
        return
    exp_t = sum(e["amount"] for e in expenses.get_by_date(target))
    hl = habits.get_logs_by_date(target)
    hd = [h for h in habits.all() if h["id"] in hl]
    wt = sum(w["ml"] for w in water.get_by_date(target))
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
            await update.message.reply_text(f"📰 *NEWS*\n\n{lines}", parse_mode="Markdown")
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
    await update.message.reply_text(f"📋 *All Pending ({len(p)}):*\n\n{lines}", parse_mode="Markdown")


async def cmd_completed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    c = tasks.completed_tasks()
    if not c:
        await update.message.reply_text("✅ Abhi tak koi task complete nahi!")
        return
    lines = "\n".join(f"✓ #{t['id']} {t['title']}" for t in c[-15:])
    await update.message.reply_text(f"✅ *Completed ({len(c)}):*\n\n{lines}", parse_mode="Markdown")


async def cmd_yesterday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    yd = yesterday_str()
    exp_t = sum(e["amount"] for e in expenses.get_by_date(yd))
    hl = habits.get_logs_by_date(yd)
    hd = [h for h in habits.all() if h["id"] in hl]
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
        f"✅ *Reminder Set!*\n⏰ {remind_at} — {text}\n🆔 `#{r['id']}` | {repeat}",
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
        f"⏰ *Active Reminders ({len(active)}):*\n\n{lines}\n\n_Delete: /delremind <id>_",
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
    goal = water.goal()
    pct = int(total / goal * 100) if goal else 0
    bar = "💧" * min(10, pct // 10) + "⬜" * (10 - min(10, pct // 10))
    await update.message.reply_text(
        f"💧 +{ml}ml logged!\n{bar}\n{total}ml / {goal}ml ({pct}%)",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()


async def cmd_water_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    total = water.today_total()
    goal = water.goal()
    pct = int(total / goal * 100) if goal else 0
    bar = "💧" * min(10, pct // 10) + "⬜" * (10 - min(10, pct // 10))
    await update.message.reply_text(
        f"💧 *Water Status*\n{bar}\n{total}ml / {goal}ml ({pct}%)",
        parse_mode="Markdown"
    )


async def cmd_water_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args and ctx.args[0].isdigit():
        water.set_goal(int(ctx.args[0]))
        await update.message.reply_text(f"✅ Water goal: {ctx.args[0]}ml")
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
        f"💳 *Bills ({len(all_b)}):*\n\n{lines}\n\n_Paid: /billpaid <id>_",
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
            await update.message.reply_text(f"📅 *Upcoming:*\n\n{lines}", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`")
        return

    args_str = " ".join(ctx.args)
    date_str = None
    title = args_str

    m = _re.match(r'^(\d{4}-\d{2}-\d{2})\s+(.*)', args_str)
    if m:
        date_str, title = m.group(1), m.group(2)
    if not date_str:
        if args_str.lower().startswith("aaj "):
            date_str = today_str(); title = args_str[4:]
        elif args_str.lower().startswith("kal "):
            date_str = (now_ist().date() + timedelta(days=1)).isoformat(); title = args_str[4:]
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
    await update.message.reply_text(f"📅 *Upcoming:*\n\n{lines}", parse_mode="Markdown")


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
    r = len(reminders.get_all())
    t = len(tasks.all_tasks())
    d = sum(len(v) for v in diary.get_all_entries().values())
    e = len(expenses.store.data.get("list", []))
    ch = len(chat_hist.get_all())
    await update.message.reply_text(
        f"📊 *DB STATUS*\n\n"
        f"Sheets: {'🟢 Connected' if google_sheets.sheet else '🔴 Disconnected'}\n\n"
        f"Reminders: {r}\nTasks: {t}\nDiary: {d} entries\n"
        f"Expenses: {e}\nChat: {ch}",
        parse_mode="Markdown"
    )


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    count = chat_hist.clear()
    await update.message.reply_text(f"🧹 {count} chat messages cleared!")


# ═══════════════════════════════════════════════════════════════════
# MAIN MESSAGE HANDLER — Natural Language → Real Actions
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_msg = update.message.text.strip()
    user_name = update.effective_user.first_name or "User"
    chat_id = update.effective_chat.id

    if user_msg.startswith("/"):
        return

    # Diary awaiting pass inline?
    if ctx.user_data.get("diary_awaiting_pass_inline"):
        ctx.user_data.pop("diary_awaiting_pass_inline", None)
        entered = user_msg.strip()
        try:
            await update.message.delete()
        except Exception:
            pass
        if entered != DIARY_PASSWORD:
            await update.effective_chat.send_message(
                "❌ *Galat Password!*", parse_mode="Markdown"
            )
            ctx.user_data.pop("diary_mode", None)
            return
        mode = ctx.user_data.pop("diary_mode", "view_today")
        await _show_diary(update, ctx, mode)
        return

    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

    # ════ STEP 1: Call Gemini JSON action router ════
    if GEMINI_API_KEY:
        action_data = call_gemini_action(user_msg)
    else:
        action_data = _regex_fallback(user_msg)

    log.info(f"📥 '{user_msg[:50]}' → Action: {action_data.get('action','?')}")

    # ════ STEP 2: Execute action ════
    reply, did_action = await execute_action(action_data, chat_id, user_msg, user_name)

    # ════ STEP 3: Save history ════
    chat_hist.add("user", user_msg, user_name)
    chat_hist.add("assistant", reply, "Bot")

    # ════ STEP 4: Send reply ════
    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(reply)

    # ════ STEP 5: Backup if action was taken ════
    if did_action:
        await auto_backup_to_sheets()


# ═══════════════════════════════════════════════════════════════════
# BACKGROUND JOBS
# ═══════════════════════════════════════════════════════════════════

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now = now_ist()

    if now.hour == 0 and now.minute <= 2:
        reminders.reset_daily()
        log.info("🌙 Midnight: reminders reset")
        return

    due = reminders.due_now()
    if due:
        log.info(f"⏰ Firing {len(due)} reminder(s) at {now.strftime('%H:%M')}")

    for r in due:
        try:
            repeat_note = ""
            if r.get("repeat") == "daily":
                repeat_note = "\n🔁 _Kal bhi yaad dilaunga!_"
            elif r.get("repeat") == "weekly":
                repeat_note = "\n📅 _Agli hafte!_"

            alert_text = (
                f"🚨🔔🚨 *ALARM!* 🚨🔔🚨\n"
                f"{'═'*25}\n"
                f"⏰ *{r['time']} BAJ GAYE!*\n"
                f"{'═'*25}\n\n"
                f"📢 *{r['text'].upper()}*\n\n"
                f"{repeat_note}\n"
                f"_Snooze: /remind 10m {r['text'][:30]}_\n"
                f"_Delete: /delremind {r['id']}_"
            )
            await context.bot.send_message(
                chat_id=int(r["chat_id"]),
                text=alert_text,
                parse_mode="Markdown",
                disable_notification=False
            )
            reminders.mark_fired(r["id"])
            log.info(f"  ✅ Alarm fired #{r['id']}: {r['text']}")
            await asyncio.sleep(1)
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
                    f"_'paani piya' ya '/water' likho_"
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
    log.info("🤖 Personal AI Bot v22.0 — No Buttons + Real Actions")
    log.info("  ✅ Gemini JSON action router")
    log.info("  ✅ Real reminders/tasks/expenses from chat")
    log.info("  ✅ Background alarms working")
    log.info("  ✅ Google Sheets auto-sync")
    log.info("  ✅ Diary password flow")
    log.info(f"⏰ IST: {now_ist().strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"🤖 Gemini: {'✅' if GEMINI_API_KEY else '❌ (regex fallback)'}")
    log.info(f"📊 Sheets: {'✅ Connected' if google_sheets.sheet else '❌ Not connected'}")
    log.info("=" * 60)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Diary ConversationHandler
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

    # Commands
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

    # Natural language handler
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # Background jobs
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

    log.info("✅ Bot v22 ready! Polling shuru...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
