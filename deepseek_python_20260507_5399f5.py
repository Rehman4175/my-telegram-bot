#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v19.0 COMPLETE FIXED               ║
║  + DIARY PASSWORD WORKING (view mode only)                      ║
║  + DIARY DIRECT SAVE + AUTO DELETE                              ║
║  + CHAT LOGS IN MISCELLANEOUS SHEET                            ║
║  + AUTO-BACKUP ON EVERY ACTION                                  ║
║  + ZERO BUTTONS (only alarm)                                    ║
║  + NO STARTUP WARNING                                           ║
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
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler()])
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", os.environ.get("Google_CREDS_JSON", ""))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

DIARY_PASSWORD = "Rk1996"
DIARY_AWAIT_PASS = 1

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
        if default is None: default = {}
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except: pass
        return default
    def save(self, collection, data):
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

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
    if not GEMINI_API_KEY: return None
    now = time.time()
    if now - _last_gemini_call < 3:
        time.sleep(3 - (now - _last_gemini_call) + random.uniform(0.5, 1.5))
    _last_gemini_call = time.time()
    payload = json.dumps({"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.75, "maxOutputTokens": min(max_tokens, 600)}}).encode("utf-8")
    for model in GEMINI_MODELS:
        try:
            url = GEMINI_URL.format(model=model, key=GEMINI_API_KEY)
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=35) as resp:
                return json.loads(resp.read().decode("utf-8"))["candidates"][0]["content"]["parts"][0]["text"].strip()
        except: continue
    return None

# ═══════════════════════════════════════════════════════════════════
# DATA STORES
# ═══════════════════════════════════════════════════════════════════

class MemoryStore:
    def __init__(self): self.store = Store("memory", {"facts": []})
    def add_fact(self, text):
        facts = self.store.data.get("facts", [])
        facts.append({"f": text, "d": today_str()})
        self.store.data["facts"] = facts[-200:]
        self.store.save()
    def get_all_facts(self): return self.store.data.get("facts", [])

class TaskStore:
    def __init__(self): self.store = Store("tasks", {"list": [], "counter": 0})
    def _save(self): self.store.save()
    def add(self, title, priority="medium"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        t = {"id": self.store.data["counter"], "title": title, "priority": priority, "done": False, "created": today_str(), "due": today_str(), "tags": "", "done_date": ""}
        self.store.data["list"].append(t)
        self._save(); return t
    def complete(self, tid):
        for t in self.store.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True; t["done_date"] = today_str(); self._save(); return t
        return None
    def delete(self, tid): self.store.data["list"] = [t for t in self.store.data["list"] if t["id"] != tid]; self._save()
    def pending(self): return [t for t in self.store.data.get("list", []) if not t["done"]]
    def done_on(self, d): return [t for t in self.store.data.get("list", []) if t["done"] and t.get("done_date") == d]
    def today_pending(self): return [t for t in self.pending() if t.get("due", "") <= today_str()]
    def all_tasks(self): return self.store.data.get("list", [])
    def completed_tasks(self): return [t for t in self.all_tasks() if t["done"]]

class DiaryStore:
    def __init__(self): self.store = Store("diary", {"entries": {}})
    def add(self, text, mood="📝"):
        td = today_str()
        self.store.data.setdefault("entries", {}).setdefault(td, [])
        self.store.data["entries"][td].append({"text": text, "mood": mood, "time": now_str()})
        self.store.save()
    def get(self, d): return self.store.data.get("entries", {}).get(d, [])
    def get_all_entries(self): return self.store.data.get("entries", {})

class HabitStore:
    def __init__(self): self.store = Store("habits", {"list": [], "logs": {}, "counter": 0})
    def add(self, name, emoji="✅"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        h = {"id": self.store.data["counter"], "name": name, "emoji": emoji, "streak": 0, "best_streak": 0, "created": today_str(), "target": ""}
        self.store.data["list"].append(h); self.store.save(); return h
    def log(self, hid):
        td, yd = today_str(), yesterday_str()
        logs = self.store.data.get("logs", {})
        logs.setdefault(td, [])
        if hid in logs[td]: return False, 0
        logs[td].append(hid)
        for h in self.store.data.get("list", []):
            if h["id"] == hid:
                h["streak"] = h.get("streak", 0) + 1 if hid in logs.get(yd, []) else 1
                h["best_streak"] = max(h.get("best_streak", 0), h.get("streak", 0))
        self.store.data["logs"] = logs; self.store.save()
        streak = next((h.get("streak", 1) for h in self.store.data["list"] if h["id"] == hid), 1)
        return True, streak
    def today_status(self):
        done_ids = self.store.data.get("logs", {}).get(today_str(), [])
        all_h = self.all()
        return ([h for h in all_h if h["id"] in done_ids], [h for h in all_h if h["id"] not in done_ids])
    def all(self): return self.store.data.get("list", [])
    def delete(self, hid): self.store.data["list"] = [h for h in self.store.data["list"] if h["id"] != hid]; self.store.save()
    def get_logs_by_date(self, d): return self.store.data.get("logs", {}).get(d, [])

class ExpenseStore:
    def __init__(self): self.store = Store("expenses", {"list": [], "budget": 0})
    def add(self, amount, desc, category="general"):
        self.store.data["list"].append({"amount": amount, "desc": desc, "category": category, "date": today_str(), "time": now_str()})
        self.store.save()
    def set_budget(self, amount): self.store.data["budget"] = amount; self.store.save()
    def today_total(self): return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date") == today_str())
    def month_total(self): return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date", "")[:7] == today_str()[:7])
    def budget_left(self): b = self.store.data.get("budget", 0); return b - self.month_total() if b else None
    def get_by_date(self, d): return [e for e in self.store.data.get("list", []) if e.get("date") == d]

class GoalStore:
    def __init__(self): self.store = Store("goals", {"list": [], "counter": 0})
    def add(self, title, deadline=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        g = {"id": self.store.data["counter"], "title": title, "progress": 0, "done": False, "deadline": deadline, "created": today_str(), "milestones": ""}
        self.store.data["list"].append(g); self.store.save(); return g
    def update_progress(self, gid, pct):
        for g in self.store.data["list"]:
            if g["id"] == gid: g["progress"] = min(100, max(0, pct)); g["done"] = g["progress"] == 100; self.store.save(); return g
        return None
    def active(self): return [g for g in self.store.data.get("list", []) if not g["done"]]
    def completed(self): return [g for g in self.store.data.get("list", []) if g["done"]]

class ReminderStore:
    def __init__(self): self.store = Store("reminders", {"list": [], "counter": 0})
    def add(self, chat_id, text, remind_at, repeat="once"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        r = {"id": self.store.data["counter"], "chat_id": str(chat_id), "text": text, "time": remind_at, "repeat": repeat, "date": today_str(), "active": True, "fired_today": False, "last_fired": "", "remarks": ""}
        self.store.data["list"].append(r); self.store.save(); return r
    def all_active(self): return [r for r in self.store.data.get("list", []) if r.get("active")]
    def get_all(self): return self.store.data.get("list", [])
    def delete(self, rid): self.store.data["list"] = [r for r in self.store.data["list"] if r["id"] != rid]; self.store.save()
    def mark_fired(self, rid):
        for r in self.store.data["list"]:
            if r["id"] == rid:
                r["fired_today"] = True; r["last_fired"] = now_ist().isoformat()
                if r["repeat"] == "once": r["active"] = False
                self.store.save(); break
    def reset_daily(self):
        for r in self.store.data["list"]: r["fired_today"] = False
        self.store.save()
    def due_now(self):
        now_hm = now_ist().strftime("%H:%M")
        return [r for r in self.store.data.get("list", []) if r.get("active") and not r.get("fired_today") and r["time"] == now_hm]

class WaterStore:
    def __init__(self): self.store = Store("water", {"logs": {}, "goal_ml": 2000})
    def add(self, ml=250):
        td = today_str()
        self.store.data.setdefault("logs", {}).setdefault(td, [])
        self.store.data["logs"][td].append({"ml": ml, "time": now_str()}); self.store.save()
    def today_total(self): return sum(e["ml"] for e in self.store.data.get("logs", {}).get(today_str(), []))
    def goal(self): return self.store.data.get("goal_ml", 2000)
    def set_goal(self, ml): self.store.data["goal_ml"] = ml; self.store.save()
    def get_by_date(self, d): return self.store.data.get("logs", {}).get(d, [])
    def week_summary(self):
        result = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            result[d] = sum(e["ml"] for e in self.store.data.get("logs", {}).get(d, []))
        return result

class BillStore:
    def __init__(self): self.store = Store("bills", {"list": [], "counter": 0})
    def add(self, name, amount, due_day):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        b = {"id": self.store.data["counter"], "name": name, "amount": amount, "due_day": due_day, "active": True, "paid_months": [], "created": today_str(), "auto_pay": "No", "payment_method": "", "notes": ""}
        self.store.data["list"].append(b); self.store.save(); return b
    def all_active(self): return [b for b in self.store.data.get("list", []) if b.get("active")]
    def mark_paid(self, bid):
        ym = today_str()[:7]
        for b in self.store.data["list"]:
            if b["id"] == bid and ym not in b.get("paid_months", []): b["paid_months"].append(ym); self.store.save(); return True
        return False
    def is_paid_this_month(self, bid):
        ym = today_str()[:7]
        for b in self.store.data["list"]:
            if b["id"] == bid: return ym in b.get("paid_months", [])
        return False
    def delete(self, bid): self.store.data["list"] = [b for b in self.store.data["list"] if b["id"] != bid]; self.store.save()
    def due_soon(self, days_ahead=3):
        today_d = now_ist().date(); result = []
        for b in self.store.data.get("list", []):
            if not b.get("active") or self.is_paid_this_month(b["id"]): continue
            try: due_date = date(today_d.year, today_d.month, min(b["due_day"], 28))
            except: continue
            if today_d <= due_date <= today_d + timedelta(days=days_ahead): result.append({**b, "due_date": due_date.isoformat()})
        return result

class CalendarStore:
    def __init__(self): self.store = Store("calendar", {"events": [], "counter": 0})
    def add(self, title, event_date, event_time="", location="", notes=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        e = {"id": self.store.data["counter"], "title": title, "date": event_date, "time": event_time, "location": location, "reminder_set": "Yes", "participants": "", "notes": notes, "created": today_str()}
        self.store.data["events"].append(e); self.store.save(); return e
    def delete(self, eid): self.store.data["events"] = [e for e in self.store.data["events"] if e["id"] != eid]; self.store.save()
    def upcoming(self, days=7):
        today_d = now_ist().date(); cutoff = today_d + timedelta(days=days)
        return sorted([e for e in self.store.data.get("events", []) if today_d <= date.fromisoformat(e["date"]) <= cutoff], key=lambda x: x["date"])
    def today_events(self): return [e for e in self.store.data.get("events", []) if e["date"] == today_str()]

class ChatHistoryStore:
    def __init__(self): self.store = Store("chat_history", {"history": []})
    def add(self, role, content, user_name=""):
        self.store.data["history"].append({"timestamp": now_ist().isoformat(), "date": today_str(), "role": role, "message": content, "user": user_name})
        self.store.data["history"] = self.store.data["history"][-500:]; self.store.save()
    def get_all(self): return self.store.data.get("history", [])
    def clear(self): count = len(self.store.data["history"]); self.store.data["history"] = []; self.store.save(); return count

# ═══════════════════════════════════════════════════════════════════
# INIT STORES
# ═══════════════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════════════
# GOOGLE SHEETS BACKUP
# ═══════════════════════════════════════════════════════════════════
class GoogleSheetsBackup:
    def __init__(self):
        self.sheet = None
        if not HAS_GSHEETS or not GOOGLE_CREDS_JSON: return
        try:
            creds_dict = json.loads(GOOGLE_CREDS_JSON)
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            self.sheet = client.open_by_key("1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")
            log.info("✅ Google Sheets connected!")
            self.ensure_worksheets()
        except Exception as e: log.error(f"❌ Sheets error: {e}")

    def ensure_worksheets(self):
        if not self.sheet: return
        configs = {
            "Reminders": ["ID", "Time", "Text", "Repeat", "Status", "Created Date", "Chat ID", "Last Fired", "Remarks"],
            "Tasks": ["ID", "Title", "Priority", "Status", "Created Date", "Completed Date", "Due Date", "Tags"],
            "Expenses": ["Date", "Amount (Rs)", "Description", "Category", "Time"],
            "Habits": ["ID", "Habit Name", "Emoji", "Streak", "Best Streak", "Created Date", "Target (per day)"],
            "Water Intake": ["Date", "Total ML", "Goal ML", "Percentage", "Glasses (250ml)", "Hourly Logs"],
            "Memory / Important Notes": ["Date", "Category", "Content", "Tags", "Priority"],
            "Daily_Logs": ["Date", "Tasks Done", "Tasks Pending", "Expenses (Rs)", "Reminders Active", "Habits Done", "Water ML", "Mood", "Notes"],
            "Goals": ["ID", "Title", "Progress %", "Status", "Deadline", "Created Date", "Milestones"],
            "Bills & Subscriptions": ["ID", "Name", "Amount (₹)", "Due Date", "Auto-pay", "Paid Status", "Payment Method", "Notes"],
            "Calendar Events": ["Date", "Time", "Event Title", "Location", "Reminder Set", "Participants", "Notes"],
            "Diary": ["Date", "Time", "Content", "Mood"],
            "Miscellaneous": ["Timestamp", "Date", "Role", "User", "Message"],
        }
        existing = {ws.title: ws for ws in self.sheet.worksheets()}
        for name, headers in configs.items():
            if name not in existing:
                try:
                    ws = self.sheet.add_worksheet(title=name, rows=1000, cols=len(headers))
                    ws.update('A1', [headers])
                except: pass

    def _upsert_by_id(self, ws, rows, id_col=0):
        try:
            existing = ws.get_all_values()
            key_to_row = {}
            for i, row in enumerate(existing[1:], start=2):
                if row and len(row) > id_col and row[id_col]: key_to_row[str(row[id_col]).strip()] = i
            updates, appends = [], []
            for row in rows:
                key = str(row[id_col]).strip() if row else ""
                if key and key in key_to_row: updates.append((key_to_row[key], row))
                else: appends.append(row)
            if updates:
                batch = []
                for rn, data in updates:
                    col_end = chr(ord("A") + len(data) - 1)
                    batch.append({"range": f"A{rn}:{col_end}{rn}", "values": [data]})
                ws.batch_update(batch)
            for row in appends: ws.append_row(row, value_input_option="USER_ENTERED")
        except: pass

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
                if key not in existing_keys: new_rows.append(row); existing_keys.add(key)
            for row in new_rows: ws.append_row(row, value_input_option="USER_ENTERED")
        except: pass

    def save_tasks(self):
        try:
            ws = self.sheet.worksheet("Tasks")
            rows = [[str(t.get("id","")), t.get("title",""), t.get("priority","medium"), "Done" if t.get("done") else "Pending", t.get("created",""), t.get("done_date",""), t.get("due",""), t.get("tags","")] for t in tasks.all_tasks()]
            if rows: self._upsert_by_id(ws, rows, 0)
            return True
        except: return False

    def save_reminders(self):
        try:
            ws = self.sheet.worksheet("Reminders")
            rows = [[str(r.get("id","")), r.get("time",""), r.get("text",""), r.get("repeat","once"), "Active" if r.get("active") else "Inactive", r.get("date",""), str(r.get("chat_id","")), r.get("last_fired",""), r.get("remarks","")] for r in reminders.get_all()]
            if rows: self._upsert_by_id(ws, rows, 0)
            return True
        except: return False

    def save_expenses(self):
        try:
            ws = self.sheet.worksheet("Expenses")
            rows = [[e.get("date",""), e.get("amount",0), e.get("desc",""), e.get("category","general"), e.get("time","")] for e in expenses.store.data.get("list", [])]
            if rows: self._append_unique(ws, rows, [0, 1, 2])
            return True
        except: return False

    def save_habits(self):
        try:
            ws = self.sheet.worksheet("Habits")
            rows = [[str(h.get("id","")), h.get("name",""), h.get("emoji","✅"), h.get("streak",0), h.get("best_streak",0), h.get("created",""), h.get("target","")] for h in habits.all()]
            if rows: self._upsert_by_id(ws, rows, 0)
            return True
        except: return False

    def save_memory(self):
        try:
            ws = self.sheet.worksheet("Memory / Important Notes")
            rows = [[f.get("d",""), "Fact", f.get("f",""), "", "Medium"] for f in memory.get_all_facts()]
            if rows: self._append_unique(ws, rows, [0, 2])
            return True
        except: return False

    def save_goals(self):
        try:
            ws = self.sheet.worksheet("Goals")
            rows = [[str(g.get("id","")), g.get("title",""), g.get("progress",0), "Done" if g.get("done") else "Active", g.get("deadline",""), g.get("created",""), g.get("milestones","")] for g in goals.active() + goals.completed()]
            if rows: self._upsert_by_id(ws, rows, 0)
            return True
        except: return False

    def save_bills(self):
        try:
            ws = self.sheet.worksheet("Bills & Subscriptions")
            rows = [[str(b.get("id","")), b.get("name",""), b.get("amount",0), str(b.get("due_day","")), b.get("auto_pay","No"), "Paid" if bills.is_paid_this_month(b["id"]) else "Pending", b.get("payment_method",""), b.get("notes","")] for b in bills.all_active()]
            if rows: self._upsert_by_id(ws, rows, 0)
            return True
        except: return False

    def save_calendar(self):
        try:
            ws = self.sheet.worksheet("Calendar Events")
            rows = [[e.get("date",""), e.get("time",""), e.get("title",""), e.get("location",""), e.get("reminder_set","Yes"), e.get("participants",""), e.get("notes","")] for e in calendar.store.data.get("events", [])]
            if rows: self._append_unique(ws, rows, [0, 2])
            return True
        except: return False

    def save_water(self):
        try:
            ws = self.sheet.worksheet("Water Intake")
            goal = water.goal(); week = water.week_summary()
            rows = []
            for d, total_ml in sorted(week.items()):
                pct = int(total_ml / goal * 100) if goal else 0
                rows.append([d, total_ml, goal, f"{pct}%", total_ml // 250, ""])
            if rows: self._upsert_by_id(ws, rows, 0)
            return True
        except: return False

    def save_daily_log(self):
        try:
            ws = self.sheet.worksheet("Daily_Logs")
            today = today_str()
            row = [today, len(tasks.done_on(today)), len(tasks.today_pending()), expenses.today_total(), len(reminders.all_active()), len(habits.today_status()[0]), water.today_total(), "", ""]
            all_vals = ws.get_all_values()
            for i, r in enumerate(all_vals):
                if r and r[0] == today: ws.update(f'A{i+1}:I{i+1}', [row]); return True
            ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except: return False

    def save_diary(self):
        try:
            ws = self.sheet.worksheet("Diary")
            existing = ws.get_all_values()
            existing_keys = set()
            for row in existing[1:]:
                if row and row[0]: existing_keys.add(f"{row[0]}|{row[1] if len(row)>1 else ''}|{row[2][:50] if len(row)>2 else ''}")
            new_rows = []
            for edate in sorted(diary.get_all_entries().keys()):
                for entry in diary.get_all_entries()[edate]:
                    key = f"{edate}|{entry.get('time','')}|{entry.get('text','')[:50]}"
                    if key not in existing_keys: new_rows.append([edate, entry.get("time",""), entry.get("text",""), entry.get("mood","📝")]); existing_keys.add(key)
            for row in new_rows: ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except: return False

    def save_chat_history(self):
        try:
            ws = self.sheet.worksheet("Miscellaneous")
            existing = ws.get_all_values()
            existing_keys = set()
            for row in existing[1:]:
                if row and row[0]: existing_keys.add(f"{row[0]}|{row[2]}|{row[4][:50] if len(row)>4 else ''}")
            new_rows = []
            for h in chat_hist.get_all()[-50:]:
                key = f"{h.get('timestamp','')}|{h.get('role','')}|{h.get('message','')[:50]}"
                if key not in existing_keys: new_rows.append([h.get("timestamp",""), h.get("date",""), h.get("role",""), h.get("user",""), h.get("message","")]); existing_keys.add(key)
            for row in new_rows: ws.append_row(row, value_input_option="USER_ENTERED")
            if new_rows: log.info(f"💬 Chat: {len(new_rows)} msgs")
            return True
        except: return False

    def full_sync(self):
        if not self.sheet: return "❌ Sheets not connected!"
        ops = [self.save_tasks, self.save_reminders, self.save_expenses, self.save_habits, self.save_memory, self.save_goals, self.save_bills, self.save_calendar, self.save_water, self.save_daily_log, self.save_diary, self.save_chat_history]
        success = sum(1 for fn in ops if fn())
        return f"✅ {success}/{len(ops)} synced"

google_sheets = GoogleSheetsBackup()

# ═══════════════════════════════════════════════════════════════════
# AUTO-BACKUP
# ═══════════════════════════════════════════════════════════════════
_last_auto_backup = 0
async def auto_backup_to_sheets():
    global _last_auto_backup
    now_ts = time.time()
    if now_ts - _last_auto_backup < 10: return
    _last_auto_backup = now_ts
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, google_sheets.full_sync)
        log.info(f"📤 {result}")
    except: pass

# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════
def build_system_prompt():
    tp = tasks.today_pending(); hd, hp = habits.today_status(); ag = goals.active()
    exp_t, exp_m = expenses.today_total(), expenses.month_total()
    bl = expenses.budget_left(); wt, wg = water.today_total(), water.goal()
    tasks_s = "\n".join(f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}" for t in tp[:5]) or "  Koi nahi"
    h_done = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    h_pend = ", ".join(f"{h['name']}" for h in hp) or "Sab ho gaye!"
    goals_s = "\n".join(f"  🎯 {g['title']} ({g['progress']}%)" for g in ag[:4]) or "  Koi nahi"
    budget_s = f"Budget baaki: ₹{bl:.0f}" if bl is not None else ""
    return f"""Tu mera Personal AI Assistant hai — naam 'Dost'. Hamesha Hindi/Hinglish mein baat kar.
⚠️ REAL TIME: {now_ist().strftime('%A, %d %b %Y — %I:%M %p')} IST
📋 AAJ KE TASKS ({len(tp)}):\n{tasks_s}
💪 HABITS: Done: {h_done} | Baaki: {h_pend}
💰 KHARCHA: Aaj ₹{exp_t} | Mahina ₹{exp_m} {budget_s}
🎯 GOALS ({len(ag)}):\n{goals_s}
💧 PAANI: {wt}ml/{wg}ml
RULES: Dost ki tarah baat kar, Hindi/Hinglish mein SHORT jawab (2-4 lines)."""

# ═══════════════════════════════════════════════════════════════════
# AI CHAT
# ═══════════════════════════════════════════════════════════════════
async def ai_chat(user_msg, chat_id=None, user_name=""):
    reply = call_gemini(build_system_prompt() + "\n\nUser: " + user_msg + "\n\nShort Hindi reply:")
    if not reply:
        msg = user_msg.lower(); n = now_ist()
        if any(w in msg for w in ["time", "baje"]): reply = f"⏰ *{n.strftime('%I:%M %p')}* (IST)"
        elif any(w in msg for w in ["hello", "hi", "assalam"]): reply = "🕌 *Assalamualaikum!*"
        else: reply = "🙏 `/help` try karo!"
    return reply

# ═══════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════
async def cmd_start(update, ctx):
    name = update.effective_user.first_name or "Dost"; n = now_ist()
    await update.message.reply_text(f"🕌 *Assalamualaikum {name}!*\n\n⏰ {n.strftime('%I:%M %p')} IST | 📅 {n.strftime('%d %b %Y')}\n\nMain aapka AI dost hoon! Jo marzi likho, main jawab dunga.\n\n📋 `/task` `/done` `/habit` `/remind` `/kharcha` `/diary` `/help`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_help(update, ctx):
    await update.message.reply_text("📋 *COMMANDS*\n\n`/task` `/done` `/deltask` — Tasks\n`/habit` `/hdone` `/delhabit` — Habits\n`/remind` `/reminders` `/delremind` — Reminders\n`/kharcha` `/budget` — Expenses\n`/diary` — Diary (text = save, bina text = view with password)\n`/remember` `/recall` — Memory\n`/goal` `/gprogress` — Goals\n`/bill` `/bills` `/billpaid` `/delbill` — Bills\n`/cal` `/calendar` `/delcal` — Calendar\n`/water` `/waterstatus` `/watergoal` — Water\n`/news` — News\n`/briefing` `/weekly` `/report` `/yesterday` — Reports\n`/alltasks` `/completed` — Views\n`/backup` `/dbstatus` `/clear` — Utils", parse_mode="Markdown")

async def cmd_task(update, ctx):
    if not ctx.args: await update.message.reply_text("📋 `/task Kaam [high/low]`", parse_mode="Markdown"); return
    args = " ".join(ctx.args); priority = "medium"
    if args.endswith(" high"): priority = "high"; args = args[:-5].strip()
    elif args.endswith(" low"): priority = "low"; args = args[:-4].strip()
    t = tasks.add(args, priority)
    e = "🔴" if priority == "high" else "🟡" if priority == "medium" else "🟢"
    await update.message.reply_text(f"✅ {e} *{t['title']}*\n🆔 `#{t['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_done(update, ctx):
    if not ctx.args:
        pending = tasks.pending()
        if pending: await update.message.reply_text("📋 *Pending:*\n" + "\n".join(f"`/done {t['id']}` → {t['title']}" for t in pending[:15]), parse_mode="Markdown")
        else: await update.message.reply_text("🎉 No pending!"); return
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        await update.message.reply_text(f"🎉 *Done!* {t['title']} ✅" if t else "❌ Not found!", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid ID!")

async def cmd_deltask(update, ctx):
    if not ctx.args: await update.message.reply_text("`/deltask <id>`"); return
    tasks.delete(int(ctx.args[0])); await update.message.reply_text("🗑 Deleted!"); await auto_backup_to_sheets()

# ═══════════════════════════════════════════════════════════════════
# 🔥 DIARY — COMPLETE FIXED VERSION
# ═══════════════════════════════════════════════════════════════════
async def cmd_diary(update, ctx):
    """ /diary → password, /diary text → save """
    full_text = update.message.text.strip()
    rest = full_text[6:].strip() if len(full_text) > 6 else ""
    
    # CASE 1: Direct save
    if rest and not rest.startswith("date ") and rest not in ("date", "all", "week", "view", "today"):
        diary.add(rest, mood="📝")
        try: await update.message.delete()
        except: pass
        sent = await update.message.reply_text(f"📖 *Diary saved!* 🕐 {now_str()}\n\n_{rest[:150]}_", parse_mode="Markdown")
        loop = asyncio.get_event_loop(); loop.create_task(auto_backup_to_sheets())
        await asyncio.sleep(3)
        try: await sent.delete()
        except: pass
        return ConversationHandler.END
    
    # CASE 2: View — PASSWORD REQUIRED
    if rest.startswith("date ") and len(rest) > 5: ctx.user_data["diary_view"] = ("date", rest[5:].strip())
    elif rest == "all": ctx.user_data["diary_view"] = ("all", None)
    elif rest == "week": ctx.user_data["diary_view"] = ("week", None)
    else: ctx.user_data["diary_view"] = ("today", None)
    
    await update.message.reply_text("🔐 *Diary Password Enter Karo:*\n\n_Password: Rk1996_", parse_mode="Markdown")
    return DIARY_AWAIT_PASS

async def diary_password_check(update, ctx):
    entered = update.message.text.strip()
    if entered != DIARY_PASSWORD:
        await update.message.reply_text("❌ *Galat password!*\n\n_Diary likhne ke liye: `/diary Aaj ka din acha tha`_\n_Diary dekhne ke liye: `/diary` (fir password daalo)_", parse_mode="Markdown")
        return ConversationHandler.END
    
    view_type, view_arg = ctx.user_data.get("diary_view", ("today", None))
    if view_type == "today":
        entries = diary.get(today_str()); all_entries = {today_str(): entries} if entries else {}
        title = f"📖 *Aaj Ki Diary — {today_str()}*"
    elif view_type == "date":
        entries = diary.get(view_arg); all_entries = {view_arg: entries} if entries else {}
        title = f"📖 *Diary — {view_arg}*"
    elif view_type == "week":
        n = now_ist(); all_entries = {}
        for i in range(7):
            d = (n - timedelta(days=i)).strftime("%Y-%m-%d"); e = diary.get(d)
            if e: all_entries[d] = e
        title = "📖 *Is Hafte Ki Diary*"
    elif view_type == "all": all_entries = diary.get_all_entries(); title = f"📖 *Puri Diary ({len(all_entries)} din)*"
    else: all_entries = {}; title = "📖 *Diary*"
    
    if not all_entries or not any(all_entries.values()):
        await update.message.reply_text(f"{title}\n\n_Koi entry nahi mili._\n\n_Likhne ke liye: `/diary Aaj kuch acha hua...`_", parse_mode="Markdown")
        return ConversationHandler.END
    
    chunks, current = [], f"{title}\n{'━'*25}\n\n"
    for dk in sorted(all_entries.keys(), reverse=True):
        if not all_entries[dk]: continue
        block = f"📅 *{dk}*\n"
        for e in all_entries[dk]: block += f"{e.get('mood','📝')} `{e.get('time','')}` — {e.get('text','')}\n"
        block += "\n"
        if len(current) + len(block) > 3800: chunks.append(current); current = block
        else: current += block
    if current.strip(): chunks.append(current)
    for chunk in chunks:
        try: await update.message.reply_text(chunk, parse_mode="Markdown")
        except: await update.message.reply_text(chunk)
    return ConversationHandler.END

async def diary_conv_cancel(update, ctx):
    try:
        if update.message: await update.message.reply_text("⏱ Diary session expired. /diary fir se try karo.")
    except: pass
    return ConversationHandler.END

# ═══════════════════════════════════════════════════════════════════
async def cmd_habit(update, ctx):
    if not ctx.args: await update.message.reply_text("💪 `/habit Naam`"); return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(f"💪 {h['emoji']} *{h['name']}*\n`/hdone {h['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_hdone(update, ctx):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending: await update.message.reply_text("💪 *Pending:*\n" + "\n".join(f"`/hdone {h['id']}` → {h['name']}" for h in pending), parse_mode="Markdown")
        else: await update.message.reply_text("🎊 Sab done!"); return
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        await update.message.reply_text(f"💪 *Done!* 🔥 {streak}d!" if ok else "✅ Already done!", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid!")

async def cmd_kharcha(update, ctx):
    if not ctx.args or len(ctx.args) < 2: await update.message.reply_text("💰 `/kharcha amount desc`"); return
    try:
        amount = float(ctx.args[0]); desc = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        await update.message.reply_text(f"💰 ₹{amount:.0f} — {desc}\n📊 Aaj: ₹{expenses.today_total():.0f}", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ `/kharcha 100 Chai`")

async def cmd_budget(update, ctx):
    if not ctx.args: await update.message.reply_text(f"💳 Budget: ₹{expenses.store.data.get('budget','Not set')}\n`/budget 5000`", parse_mode="Markdown"); return
    expenses.set_budget(float(ctx.args[0])); await update.message.reply_text(f"💳 Budget: ₹{ctx.args[0]}"); await auto_backup_to_sheets()

async def cmd_goal(update, ctx):
    if not ctx.args:
        active = goals.active()
        if active: await update.message.reply_text("🎯 *ACTIVE*\n\n" + "\n".join(f"#{g['id']} {g['title']} — {g['progress']}%" for g in active), parse_mode="Markdown")
        else: await update.message.reply_text("🎯 `/goal Description`"); return
        return
    g = goals.add(" ".join(ctx.args)); await update.message.reply_text(f"🎯 Goal set! #{g['id']} {g['title']}", parse_mode="Markdown"); await auto_backup_to_sheets()

async def cmd_gprogress(update, ctx):
    if len(ctx.args) < 2: await update.message.reply_text("📊 `/gprogress <id> <pct>`"); return
    try:
        g = goals.update_progress(int(ctx.args[0]), int(ctx.args[1]))
        await update.message.reply_text(f"📊 *{g['title']}* — {g['progress']}%" if g else "❌ Not found!", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid!")

async def cmd_remember(update, ctx):
    if not ctx.args: await update.message.reply_text("🧠 `/remember text`"); return
    memory.add_fact(" ".join(ctx.args)); await update.message.reply_text("🧠 Yaad kar liya! ✅"); await auto_backup_to_sheets()

async def cmd_recall(update, ctx):
    facts = memory.get_all_facts()
    if not facts: await update.message.reply_text("🧠 Kuch yaad nahi."); return
    await update.message.reply_text("🧠 *MEMORY*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-15:]), parse_mode="Markdown")

async def cmd_briefing(update, ctx):
    n = now_ist(); tp = tasks.today_pending(); hd, _ = habits.today_status()
    await update.message.reply_text(f"🌅 *BRIEFING*\n⏰ {n.strftime('%I:%M %p')} | 📅 {n.strftime('%d %b')}\n\n📋 Pending: {len(tp)}\n💪 Done: {len(hd)}\n💰 Aaj: ₹{expenses.today_total():.0f}\n💧 Water: {water.today_total()}ml/{water.goal()}ml", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_weekly(update, ctx):
    n = now_ist(); ws = n.date() - timedelta(days=n.weekday()); tw = tasks.get_weekly_summary()
    await update.message.reply_text(f"📊 *WEEKLY*\n📅 {ws.strftime('%d %b')} - {n.strftime('%d %b %Y')}\n\n📋 Done: {sum(v['done'] for v in tw.values())}\n💰 Month: ₹{expenses.month_total():.0f}", parse_mode="Markdown")

async def cmd_report(update, ctx):
    if not ctx.args: await update.message.reply_text("📋 `/report YYYY-MM-DD`"); return
    target = ctx.args[0]
    try: datetime.strptime(target, "%Y-%m-%d")
    except: await update.message.reply_text("❌ Invalid date!"); return
    exp_t = sum(e["amount"] for e in expenses.get_by_date(target)); hl = habits.get_logs_by_date(target)
    hd = [h for h in habits.all() if h["id"] in hl]; wt = sum(w["ml"] for w in water.get_by_date(target))
    await update.message.reply_text(f"📋 *REPORT {target}*\n\n📋 Done: {len(tasks.done_on(target))}\n💰 ₹{exp_t:.0f}\n📖 {len(diary.get(target))} entries\n💪 {len(hd)} habits\n💧 {wt}ml", parse_mode="Markdown")

async def cmd_news(update, ctx):
    try:
        req = urllib.request.Request("https://feeds.bbci.co.uk/hindi/rss.xml", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            items = ET.parse(resp).getroot().find("channel").findall("item")[:5]
            await update.message.reply_text("📰 *INDIA NEWS*\n\n" + "\n".join(f"• *{item.findtext('title','')}*" for item in items if item.findtext('title','')), parse_mode="Markdown")
    except: await update.message.reply_text("📰 News unavailable.")

async def cmd_alltasks(update, ctx):
    p = tasks.pending()
    if not p: await update.message.reply_text("📋 No tasks!"); return
    await update.message.reply_text(f"📋 *ALL*\n⏳ {len(p)} pending\n\n" + "\n".join(f"   #{t['id']} {t['title']}" for t in p[:10]), parse_mode="Markdown")

async def cmd_completed(update, ctx):
    c = tasks.completed_tasks()
    if not c: await update.message.reply_text("✅ None!"); return
    await update.message.reply_text(f"✅ *COMPLETED ({len(c)})*\n\n" + "\n".join(f"  ✓ #{t['id']} {t['title']}" for t in c[-15:]), parse_mode="Markdown")

async def cmd_yesterday(update, ctx):
    yd = yesterday_str(); exp_t = sum(e["amount"] for e in expenses.get_by_date(yd))
    hl = habits.get_logs_by_date(yd); hd = [h for h in habits.all() if h["id"] in hl]
    await update.message.reply_text(f"📅 *YESTERDAY ({yd})*\n\n✅ Tasks: {len(tasks.done_on(yd))}\n💪 Habits: {len(hd)}/{len(habits.all())}\n💰 ₹{exp_t:.0f}", parse_mode="Markdown")

async def cmd_remind(update, ctx):
    now = now_ist()
    if not ctx.args: await update.message.reply_text("⏰ `/remind 2m Test` | `/remind 30m Chai` | `/remind 15:30 Doctor`", parse_mode="Markdown"); return
    time_arg = ctx.args[0].lower(); rest = ctx.args[1:]; repeat = "once"
    if rest and rest[-1].lower() in ["daily", "weekly"]: repeat = rest[-1].lower(); rest = rest[:-1]
    text = " ".join(rest) if rest else "⏰ Reminder!"
    if time_arg.endswith("m") and time_arg[:-1].isdigit(): remind_at = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif time_arg.endswith("h") and time_arg[:-1].isdigit(): remind_at = (now + timedelta(hours=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        parts = time_arg.split(":")
        if len(parts) == 2 and parts[0].isdigit() and 0 <= int(parts[0]) <= 23: remind_at = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        else: await update.message.reply_text("❌ Invalid time!"); return
    else: await update.message.reply_text("❌ Format!"); return
    r = reminders.add(update.effective_chat.id, text, remind_at, repeat)
    await update.message.reply_text(f"✅ *Reminder!* ⏰ {remind_at} — {text}\n🆔 `#{r['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_reminders_list(update, ctx):
    active = reminders.all_active()
    if not active: await update.message.reply_text("⏰ None!"); return
    await update.message.reply_text(f"⏰ *REMINDERS ({len(active)})*\n\n" + "\n".join(f"*#{r['id']}* `{r['time']}` — {r['text']}" for r in active), parse_mode="Markdown")

async def cmd_delremind(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delremind <id>`"); return
    reminders.delete(int(ctx.args[0])); await update.message.reply_text("🗑 Deleted!"); await auto_backup_to_sheets()

async def cmd_water(update, ctx):
    ml = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 250
    water.add(ml); total = water.today_total(); goal = water.goal()
    await update.message.reply_text(f"💧 +{ml}ml | {total}ml/{goal}ml", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_water_status(update, ctx): await update.message.reply_text(f"💧 {water.today_total()}ml / {water.goal()}ml", parse_mode="Markdown")
async def cmd_water_goal(update, ctx):
    if ctx.args and ctx.args[0].isdigit(): water.set_goal(int(ctx.args[0]))
    await update.message.reply_text(f"✅ Goal: {water.goal()}ml")

async def cmd_bill(update, ctx):
    if not ctx.args or len(ctx.args) < 3: await update.message.reply_text("💳 `/bill Name Amount DueDay`"); return
    try:
        b = bills.add(ctx.args[0], float(ctx.args[1]), int(ctx.args[2]))
        await update.message.reply_text(f"✅ Bill: {b['name']} ₹{b['amount']:.0f} — Due {b['due_day']}th", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Format!")

async def cmd_bills_list(update, ctx):
    all_b = bills.all_active()
    if not all_b: await update.message.reply_text("💳 None!"); return
    await update.message.reply_text("💳 *BILLS*\n\n" + "\n".join(f"{'✅' if bills.is_paid_this_month(b['id']) else '⏳'} *{b['name']}* — ₹{b['amount']:.0f} (Due {b['due_day']}th)" for b in all_b), parse_mode="Markdown")

async def cmd_bill_paid(update, ctx):
    if not ctx.args: await update.message.reply_text("`/billpaid <id>`"); return
    try: await update.message.reply_text("✅ Paid!" if bills.mark_paid(int(ctx.args[0])) else "❌ Already!"); await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid!")

async def cmd_del_bill(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delbill <id>`"); return
    bills.delete(int(ctx.args[0])); await update.message.reply_text("🗑 Deleted!"); await auto_backup_to_sheets()

async def cmd_cal(update, ctx):
    if not ctx.args: await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`"); return
    args_str = " ".join(ctx.args); date_str, title = None, args_str
    m = _re.match(r'^(\d{4}-\d{2}-\d{2})\s+(.*)', args_str)
    if m: date_str, title = m.group(1), m.group(2)
    if not date_str:
        if args_str.lower().startswith("aaj "): date_str = today_str(); title = args_str[4:]
        elif args_str.lower().startswith("kal "): date_str = (now_ist().date() + timedelta(days=1)).isoformat(); title = args_str[4:]
    if not date_str: await update.message.reply_text("❌ Format!"); return
    event_time = ""; t_match = _re.search(r'(\d{1,2}:\d{2})', title)
    if t_match: event_time = t_match.group(1); title = title.replace(event_time, "").strip()
    try:
        date.fromisoformat(date_str); calendar.add(title, date_str, event_time)
        await update.message.reply_text(f"📅 Event: {title} — {date_str}" + (f" ⏰{event_time}" if event_time else ""), parse_mode="Markdown")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid date!")

async def cmd_cal_list(update, ctx):
    upcoming = calendar.upcoming(30)
    if not upcoming: await update.message.reply_text("📅 None!"); return
    await update.message.reply_text("📅 *UPCOMING*\n\n" + "\n".join(f"{'🔴' if e['date']==today_str() else '📆'} {e['date']} — {e['title']}" for e in upcoming[:10]), parse_mode="Markdown")

async def cmd_del_cal(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delcal <id>`"); return
    calendar.delete(int(ctx.args[0])); await update.message.reply_text("🗑 Deleted!"); await auto_backup_to_sheets()

async def cmd_memory(update, ctx):
    facts = memory.get_all_facts()
    if not facts: await update.message.reply_text("🧠 None!"); return
    await update.message.reply_text("🧠 *MEMORY*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-15:]), parse_mode="Markdown")

async def cmd_backup(update, ctx):
    await update.message.reply_text("📤 Backing up..."); await update.message.reply_text(google_sheets.full_sync())

async def cmd_dbstatus(update, ctx):
    r = len(reminders.get_all()); t = len(tasks.all_tasks()); d = sum(len(v) for v in diary.get_all_entries().values()); e = len(expenses.store.data.get("list",[]))
    await update.message.reply_text(f"✅ Sheets: {'🟢' if google_sheets.sheet else '🔴'}\n📊 R:{r} | T:{t} | D:{d} | E:{e}")

async def cmd_clear(update, ctx): await update.message.reply_text(f"🧹 {chat_hist.clear()} msgs cleared!", parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════════
# MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_msg = update.message.text.strip(); user_name = update.effective_user.first_name or "User"
    if user_msg.startswith('/'): return
    ctx.user_data.pop("diary_view", None)
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ai_chat(user_msg, update.effective_chat.id, user_name)
    chat_hist.add("user", user_msg, user_name); chat_hist.add("assistant", reply, "Bot")
    try: await update.message.reply_text(reply, parse_mode="Markdown")
    except: await update.message.reply_text(reply)
    await auto_backup_to_sheets()

# ═══════════════════════════════════════════════════════════════════
# BACKGROUND JOBS
# ═══════════════════════════════════════════════════════════════════
async def reminder_job(context):
    now = now_ist()
    if now.strftime("%H:%M") in ("00:00", "00:01"): reminders.reset_daily(); return
    for r in reminders.due_now():
        try:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Done", callback_data=f"remind_done_{r['id']}"), InlineKeyboardButton("⏰ Snooze 10m", callback_data=f"remind_snooze_{r['id']}")]])
            await context.bot.send_message(chat_id=int(r["chat_id"]), text=f"🚨🔔 *ALARM!*\n{'═'*20}\n⏰ *{r['time']}*\n📢 *{r['text']}*", parse_mode="Markdown", reply_markup=kb)
            reminders.mark_fired(r["id"]); await asyncio.sleep(1)
        except: pass

async def bill_due_job(context):
    if now_ist().strftime("%H:%M") != "09:00": return
    due = bills.due_soon(3)
    if due:
        for cid in set(r["chat_id"] for r in reminders.all_active()):
            try: await context.bot.send_message(chat_id=int(cid), text="💳 *BILL DUE*\n" + "\n".join(f"⚠️ {b['name']} ₹{b['amount']:.0f}" for b in due), parse_mode="Markdown")
            except: pass

async def water_reminder_job(context):
    now = now_ist()
    if not (8 <= now.hour <= 22) or now.hour % 3 != 0 or water.today_total() >= water.goal(): return
    for cid in set(r["chat_id"] for r in reminders.all_active()):
        try: await context.bot.send_message(chat_id=int(cid), text=f"💧 *Paani time!*\n{water.today_total()}ml/{water.goal()}ml\n`/water`", parse_mode="Markdown")
        except: pass

async def scheduled_backup_job(context):
    result = await asyncio.get_event_loop().run_in_executor(None, google_sheets.full_sync)
    log.info(f"🕒 {result}")

# ═══════════════════════════════════════════════════════════════════
# CALLBACK HANDLER — ALARM ONLY
# ═══════════════════════════════════════════════════════════════════
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    d = query.data; message = query.message
    if not message: return
    if d.startswith("remind_done_"):
        reminders.mark_fired(int(d.split("_")[2])); await message.edit_text("✅ Done!")
        await asyncio.sleep(2)
        try: await message.delete()
        except: pass
    elif d.startswith("remind_snooze_"):
        rid = int(d.split("_")[2]); snooze = (now_ist() + timedelta(minutes=10)).strftime("%H:%M")
        r_list = [r for r in reminders.get_all() if r["id"] == rid]
        if r_list: reminders.add(int(r_list[0]["chat_id"]), r_list[0]["text"], snooze, "once"); reminders.mark_fired(rid)
        await message.edit_text(f"😴 Snoozed to {snooze}")
        await asyncio.sleep(2)
        try: await message.delete()
        except: pass

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    log.info("=" * 55)
    log.info(f"🤖 Bot v19 — COMPLETE FIXED")
    log.info(f"⏰ IST: {now_ist().strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"📊 Sheets: {'✅' if google_sheets.sheet else '❌'}")
    log.info("=" * 55)

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.post_init = lambda app: None

    cmds = [
        ("start", cmd_start), ("help", cmd_help),
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("habit", cmd_habit), ("hdone", cmd_hdone),
        ("kharcha", cmd_kharcha), ("budget", cmd_budget),
        ("goal", cmd_goal), ("gprogress", cmd_gprogress),
        ("remember", cmd_remember), ("recall", cmd_recall),
        ("briefing", cmd_briefing), ("weekly", cmd_weekly), ("report", cmd_report),
        ("news", cmd_news),
        ("alltasks", cmd_alltasks), ("completed", cmd_completed), ("yesterday", cmd_yesterday),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list), ("delremind", cmd_delremind),
        ("water", cmd_water), ("waterstatus", cmd_water_status), ("watergoal", cmd_water_goal),
        ("bill", cmd_bill), ("bills", cmd_bills_list), ("billpaid", cmd_bill_paid), ("delbill", cmd_del_bill),
        ("cal", cmd_cal), ("calendar", cmd_cal_list), ("delcal", cmd_del_cal),
        ("memory", cmd_memory), ("backup", cmd_backup), ("dbstatus", cmd_dbstatus),
        ("clear", cmd_clear),
    ]
    for cmd, handler in cmds: app.add_handler(CommandHandler(cmd, handler))

    diary_conv = ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary)],
        states={DIARY_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)]},
        fallbacks=[CommandHandler("cancel", diary_conv_cancel)],
        per_user=True, per_chat=True, conversation_timeout=60,
    )
    app.add_handler(diary_conv)
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=15)
        app.job_queue.run_repeating(bill_due_job, interval=3600, first=300)
        app.job_queue.run_repeating(water_reminder_job, interval=3600, first=600)
        app.job_queue.run_repeating(scheduled_backup_job, interval=3600, first=120)
        log.info("⏰ Jobs started!")

    log.info("✅ Bot ready!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()