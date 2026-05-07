#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PERSONAL AI ASSISTANT — COMPLETE NATURAL LANGUAGE VERSION
All features from original v14, but speak naturally.
Auto-backup to Google Sheets after every change.
"""

import os, json, logging, time, asyncio, random, re
import urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta, timezone
import datetime as dt_module
from xml.etree import ElementTree as ET

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

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# Config
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", os.environ.get("Google_CREDS_JSON", ""))

DIARY_PASSWORD = "Rk1996"

if not TELEGRAM_TOKEN:
    log.error("❌ TELEGRAM_TOKEN not set!")
    exit(1)

# IST
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

# Database
class Database:
    def __init__(self):
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)
    def load(self, collection, default=None):
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            log.warning(f"Load {collection} failed: {e}")
        return default if default is not None else {}
    def save(self, collection, data):
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"Save {collection} failed: {e}")

db = Database()

# Gemini API
GEMINI_MODELS = ["gemini-2.0-flash-lite", "gemini-2.0-flash"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
_last_gemini_call = 0

def call_gemini(prompt, max_tokens=400, temp=0.7):
    global _last_gemini_call
    if not GEMINI_API_KEY:
        return None
    now = time.time()
    elapsed = now - _last_gemini_call
    if elapsed < 2:
        time.sleep(2 - elapsed)
    _last_gemini_call = time.time()
    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temp, "maxOutputTokens": min(max_tokens, 600)}
    }).encode()
    for model in GEMINI_MODELS:
        try:
            url = GEMINI_URL.format(model=model, key=GEMINI_API_KEY)
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip()
        except Exception:
            continue
    return None

# ==================== ALL DATA STORES (FULL) ====================
class MemoryStore:
    def __init__(self):
        self.data = db.load("memory", {"facts": [], "important": [], "dates": {}})
    def save(self):
        db.save("memory", self.data)
    def add_fact(self, text):
        self.data["facts"].append({"f": text[:200], "d": today_str()})
        self.data["facts"] = self.data["facts"][-200:]
        self.save()
    def add_important(self, text):
        self.data["important"].append({"note": text, "d": today_str()})
        self.data["important"] = self.data["important"][-50:]
        self.save()
    def add_date(self, name, date_str):
        self.data["dates"][name] = date_str
        self.save()
    def get_all_facts(self):
        return self.data.get("facts", [])
    def get_important(self):
        return self.data.get("important", [])
    def get_dates(self):
        return self.data.get("dates", {})
    def context(self):
        facts = "\n".join(f"• {x['f']}" for x in self.get_all_facts()[-15:]) or "Kuch nahi"
        imp = "\n".join(f"⭐ {x['note']}" for x in self.get_important()[-5:]) or "Kuch nahi"
        dates = "\n".join(f"• {k}: {v}" for k,v in self.get_dates().items()) or "Kuch nahi"
        return f"FACTS:\n{facts}\n\nIMPORTANT:\n{imp}\n\nDATES:\n{dates}"

class TaskStore:
    def __init__(self):
        self.data = db.load("tasks", {"list": [], "counter": 0})
    def save(self):
        db.save("tasks", self.data)
    def add(self, title, priority="medium"):
        self.data["counter"] += 1
        t = {"id": self.data["counter"], "title": title, "priority": priority, "done": False, "created": today_str(), "due": today_str()}
        self.data["list"].append(t)
        self.save()
        return t
    def complete(self, tid):
        for t in self.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True
                t["done_at"] = today_str()
                self.save()
                return t
        return None
    def delete(self, tid):
        self.data["list"] = [t for t in self.data["list"] if t["id"] != tid]
        self.save()
    def pending(self):
        return [t for t in self.data["list"] if not t["done"]]
    def all_tasks(self):
        return self.data["list"]
    def completed(self):
        return [t for t in self.data["list"] if t["done"]]
    def done_on(self, d):
        return [t for t in self.data["list"] if t.get("done") and t.get("done_at") == d]
    def today_pending(self):
        return [t for t in self.data["list"] if not t["done"] and t.get("due") <= today_str()]
    def weekly_summary(self):
        result = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            result[d] = {"done": len(self.done_on(d)), "created": len([t for t in self.data["list"] if t["created"] == d])}
        return result

class DiaryStore:
    def __init__(self):
        self.data = db.load("diary", {"entries": {}})
    def save(self):
        db.save("diary", self.data)
    def add(self, text, mood="😊"):
        td = today_str()
        self.data["entries"].setdefault(td, []).append({"text": text, "mood": mood, "time": now_str()})
        self.save()
    def get(self, d):
        return self.data["entries"].get(d, [])
    def get_all(self):
        return self.data["entries"]
    def get_date_range(self, start, end):
        result = {}
        cur = start
        while cur <= end:
            entries = self.get(cur)
            if entries:
                result[cur] = entries
            cur = (datetime.strptime(cur, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        return result

class HabitStore:
    def __init__(self):
        self.data = db.load("habits", {"list": [], "logs": {}, "counter": 0})
    def save(self):
        db.save("habits", self.data)
    def add(self, name, emoji="✅"):
        self.data["counter"] += 1
        h = {"id": self.data["counter"], "name": name, "emoji": emoji, "streak": 0, "best_streak": 0}
        self.data["list"].append(h)
        self.save()
        return h
    def log(self, hid):
        td = today_str()
        if hid in self.data["logs"].get(td, []):
            return False, 0
        self.data["logs"].setdefault(td, []).append(hid)
        for h in self.data["list"]:
            if h["id"] == hid:
                if hid in self.data["logs"].get(yesterday_str(), []):
                    h["streak"] += 1
                else:
                    h["streak"] = 1
                h["best_streak"] = max(h["best_streak"], h["streak"])
        self.save()
        streak = next((h["streak"] for h in self.data["list"] if h["id"] == hid), 1)
        return True, streak
    def today_status(self):
        done_ids = self.data["logs"].get(today_str(), [])
        all_h = self.data["list"]
        return ([h for h in all_h if h["id"] in done_ids], [h for h in all_h if h["id"] not in done_ids])
    def all(self):
        return self.data["list"]
    def delete(self, hid):
        self.data["list"] = [h for h in self.data["list"] if h["id"] != hid]
        self.save()

class NoteStore:
    def __init__(self):
        self.data = db.load("notes", {"list": [], "counter": 0})
    def save(self):
        db.save("notes", self.data)
    def add(self, content):
        self.data["counter"] += 1
        n = {"id": self.data["counter"], "text": content, "created": today_str()}
        self.data["list"].append(n)
        self.save()
        return n
    def delete(self, nid):
        self.data["list"] = [n for n in self.data["list"] if n["id"] != nid]
        self.save()
    def recent(self, n=10):
        return self.data["list"][-n:]

class ExpenseStore:
    def __init__(self):
        self.data = db.load("expenses", {"list": [], "budget": None})
    def save(self):
        db.save("expenses", self.data)
    def add(self, amount, desc, category="general"):
        self.data["list"].append({"amount": amount, "desc": desc, "category": category, "date": today_str(), "time": now_str()})
        self.save()
    def set_budget(self, amount):
        self.data["budget"] = amount
        self.save()
    def today_total(self):
        return sum(e["amount"] for e in self.data["list"] if e["date"] == today_str())
    def month_total(self):
        m = today_str()[:7]
        return sum(e["amount"] for e in self.data["list"] if e["date"].startswith(m))
    def budget_left(self):
        if self.data["budget"]:
            return self.data["budget"] - self.month_total()
        return None
    def get_by_date(self, d):
        return [e for e in self.data["list"] if e["date"] == d]

class ReminderStore:
    def __init__(self):
        self.data = db.load("reminders", {"list": [], "counter": 0})
    def save(self):
        db.save("reminders", self.data)
    def add(self, chat_id, text, remind_at, repeat="once"):
        self.data["counter"] += 1
        r = {"id": self.data["counter"], "chat_id": chat_id, "text": text, "time": remind_at, "repeat": repeat, "active": True, "fired_today": False, "date": today_str()}
        self.data["list"].append(r)
        self.save()
        return r
    def all_active(self):
        return [r for r in self.data["list"] if r["active"]]
    def get_all(self):
        return self.data["list"]
    def delete(self, rid):
        self.data["list"] = [r for r in self.data["list"] if r["id"] != rid]
        self.save()
    def mark_fired(self, rid):
        for r in self.data["list"]:
            if r["id"] == rid:
                r["fired_today"] = True
                if r["repeat"] == "once":
                    r["active"] = False
                self.save()
                break
    def reset_daily(self):
        for r in self.data["list"]:
            r["fired_today"] = False
        self.save()
    def due_now(self):
        now_hm = now_ist().strftime("%H:%M")
        return [r for r in self.data["list"] if r["active"] and not r["fired_today"] and r["time"] == now_hm]

class WaterStore:
    def __init__(self):
        self.data = db.load("water", {"logs": {}, "goal_ml": 2000})
    def save(self):
        db.save("water", self.data)
    def add(self, ml=250):
        td = today_str()
        self.data["logs"].setdefault(td, []).append({"ml": ml, "time": now_str()})
        self.save()
    def today_total(self):
        return sum(e["ml"] for e in self.data["logs"].get(today_str(), []))
    def goal(self):
        return self.data.get("goal_ml", 2000)
    def set_goal(self, ml):
        self.data["goal_ml"] = ml
        self.save()
    def week_summary(self):
        res = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            res[d] = sum(e["ml"] for e in self.data["logs"].get(d, []))
        return res

class BillStore:
    def __init__(self):
        self.data = db.load("bills", {"list": [], "counter": 0})
    def save(self):
        db.save("bills", self.data)
    def add(self, name, amount, due_day):
        self.data["counter"] += 1
        b = {"id": self.data["counter"], "name": name, "amount": amount, "due_day": due_day, "active": True, "paid_months": []}
        self.data["list"].append(b)
        self.save()
        return b
    def all_active(self):
        return [b for b in self.data["list"] if b["active"]]
    def mark_paid(self, bid):
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid and ym not in b["paid_months"]:
                b["paid_months"].append(ym)
                self.save()
                return True
        return False
    def is_paid_this_month(self, bid):
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid:
                return ym in b["paid_months"]
        return False
    def delete(self, bid):
        self.data["list"] = [b for b in self.data["list"] if b["id"] != bid]
        self.save()
    def due_soon(self, days=3):
        today_d = now_ist().date()
        due = []
        for b in self.data["list"]:
            if not b["active"] or self.is_paid_this_month(b["id"]):
                continue
            try:
                due_date = date(today_d.year, today_d.month, min(b["due_day"], 28))
                if today_d <= due_date <= today_d + timedelta(days=days):
                    due.append(b)
            except:
                pass
        return due

class CalendarStore:
    def __init__(self):
        self.data = db.load("calendar", {"events": [], "counter": 0})
    def save(self):
        db.save("calendar", self.data)
    def add(self, title, event_date, event_time=""):
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "title": title, "date": event_date, "time": event_time}
        self.data["events"].append(e)
        self.save()
        return e
    def delete(self, eid):
        self.data["events"] = [e for e in self.data["events"] if e["id"] != eid]
        self.save()
    def today(self):
        return [e for e in self.data["events"] if e["date"] == today_str()]
    def upcoming(self, days=30):
        today_d = now_ist().date()
        cutoff = today_d + timedelta(days=days)
        return sorted([e for e in self.data["events"] if today_d <= datetime.strptime(e["date"], "%Y-%m-%d").date() <= cutoff], key=lambda x: x["date"])

class GoalStore:
    def __init__(self):
        self.data = db.load("goals", {"list": [], "counter": 0})
    def save(self):
        db.save("goals", self.data)
    def add(self, title, deadline="", why=""):
        self.data["counter"] += 1
        g = {"id": self.data["counter"], "title": title, "deadline": deadline, "why": why, "progress": 0, "done": False}
        self.data["list"].append(g)
        self.save()
        return g
    def update_progress(self, gid, pct):
        for g in self.data["list"]:
            if g["id"] == gid:
                g["progress"] = min(100, max(0, pct))
                if g["progress"] == 100:
                    g["done"] = True
                self.save()
                return g
        return None
    def active(self):
        return [g for g in self.data["list"] if not g["done"]]
    def completed(self):
        return [g for g in self.data["list"] if g["done"]]

class NewsStore:
    def __init__(self):
        self.data = db.load("news_cache", {"cache": {}})
    def get(self, category="India"):
        feeds = {
            "India": "https://feeds.bbci.co.uk/hindi/rss.xml",
            "Tech": "https://feeds.feedburner.com/ndtvnews-tech-news",
            "Business": "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
            "World": "https://feeds.bbci.co.uk/news/world/rss.xml",
            "Sports": "https://feeds.bbci.co.uk/sport/rss.xml"
        }
        url = feeds.get(category, feeds["India"])
        items = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                tree = ET.parse(resp)
                root = tree.getroot()
                channel = root.find("channel") or root
                for item in channel.findall("item")[:5]:
                    title = item.findtext("title", "").strip()
                    if title:
                        items.append({"title": title})
        except:
            items = [{"title": "News unavailable"}]
        return items

class ChatStore:
    def __init__(self):
        self.data = db.load("chat", {"history": []})
    def save(self):
        db.save("chat", self.data)
    def add(self, role, content):
        self.data["history"].append({"role": role, "content": content, "time": now_str()})
        self.data["history"] = self.data["history"][-50:]
        self.save()
    def clear(self):
        self.data["history"] = []
        self.save()

# Initialize all stores
memory = MemoryStore()
tasks = TaskStore()
diary = DiaryStore()
habits = HabitStore()
notes = NoteStore()
expenses = ExpenseStore()
reminders = ReminderStore()
water = WaterStore()
bills = BillStore()
calendar = CalendarStore()
goals = GoalStore()
news_store = NewsStore()
chat = ChatStore()

# ==================== GOOGLE SHEETS BACKUP (AUTO) ====================
class GoogleSheetsBackup:
    def __init__(self):
        self.sheet = None
        if not HAS_GSHEETS:
            return
        creds_json = os.environ.get("GOOGLE_CREDS_JSON", "")
        if not creds_json:
            return
        try:
            creds_dict = json.loads(creds_json)
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            self.sheet = client.open_by_key("1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")
            log.info("✅ Google Sheets connected")
            self.ensure_worksheets()
        except Exception as e:
            log.error(f"Sheets error: {e}")

    def ensure_worksheets(self):
        if not self.sheet:
            return
        required = ["Tasks", "Reminders", "Expenses", "Habits", "Water", "Memory", "Daily_Logs", "Goals", "Bills", "Calendar", "Diary", "Notes"]
        existing = [ws.title for ws in self.sheet.worksheets()]
        for name in required:
            if name not in existing:
                try:
                    self.sheet.add_worksheet(title=name, rows=1000, cols=20)
                except:
                    pass

    def full_sync(self):
        if not self.sheet:
            return "❌ Sheets not connected"
        try:
            # Tasks
            ws = self.sheet.worksheet("Tasks")
            ws.clear()
            for t in tasks.all_tasks():
                ws.append_row([t["id"], t["title"], t["priority"], "Done" if t["done"] else "Pending", t["created"], t.get("done_at","")])
            # Reminders
            ws = self.sheet.worksheet("Reminders")
            ws.clear()
            for r in reminders.get_all():
                ws.append_row([r["id"], r["time"], r["text"], r["repeat"], "Active" if r["active"] else "Inactive", r["date"]])
            # Expenses (append only)
            ws = self.sheet.worksheet("Expenses")
            for e in expenses.data["list"]:
                ws.append_row([e["date"], e["amount"], e["desc"], e["category"], e["time"]])
            # Habits
            ws = self.sheet.worksheet("Habits")
            ws.clear()
            for h in habits.all():
                ws.append_row([h["id"], h["name"], h["emoji"], h["streak"], h["best_streak"]])
            # Water - weekly
            ws = self.sheet.worksheet("Water")
            ws.clear()
            goal = water.goal()
            for d, total in water.week_summary().items():
                pct = int(total/goal*100) if goal else 0
                ws.append_row([d, total, goal, f"{pct}%"])
            # Memory
            ws = self.sheet.worksheet("Memory")
            for f in memory.get_all_facts():
                ws.append_row([f["d"], f["f"], "fact"])
            # Daily Log
            ws = self.sheet.worksheet("Daily_Logs")
            today = today_str()
            row = [today, len(tasks.done_on(today)), len(tasks.today_pending()), expenses.today_total(), water.today_total(), len(habits.today_status()[0]), "", ""]
            all_rows = ws.get_all_values()
            found = False
            for i, r in enumerate(all_rows):
                if r and r[0] == today:
                    ws.update(f'A{i+1}:H{i+1}', [row])
                    found = True
                    break
            if not found:
                ws.append_row(row)
            # Goals
            ws = self.sheet.worksheet("Goals")
            ws.clear()
            for g in goals.active() + goals.completed():
                ws.append_row([g["id"], g["title"], g["progress"], "Done" if g["done"] else "Active", g.get("deadline",""), g.get("why","")])
            # Bills
            ws = self.sheet.worksheet("Bills")
            ws.clear()
            for b in bills.all_active():
                ws.append_row([b["id"], b["name"], b["amount"], b["due_day"], "Paid" if bills.is_paid_this_month(b["id"]) else "Pending"])
            # Calendar
            ws = self.sheet.worksheet("Calendar")
            ws.clear()
            for e in calendar.data["events"]:
                ws.append_row([e["id"], e["title"], e["date"], e["time"]])
            # Diary
            ws = self.sheet.worksheet("Diary")
            for d_key, entries in diary.get_all().items():
                for e in entries:
                    ws.append_row([d_key, e["time"], e["mood"], e["text"]])
            # Notes
            ws = self.sheet.worksheet("Notes")
            ws.clear()
            for n in notes.recent(100):
                ws.append_row([n["id"], n["text"], n["created"]])
            return "✅ Auto-backup complete"
        except Exception as e:
            return f"❌ Backup error: {e}"

google_sheets = GoogleSheetsBackup()

async def auto_backup():
    if google_sheets.sheet:
        result = google_sheets.full_sync()
        log.info(f"Auto-backup: {result}")

# ==================== NATURAL LANGUAGE PARSER (COMPLETE) ====================
def parse_natural_action(text):
    lower = text.lower().strip()
    
    # --- REMINDER ---
    if re.search(r'(remind|yaad dilana|alarm)', lower):
        # Time patterns
        min_match = re.search(r'(\d+)\s*(?:min|minute|मिनट)\s*(?:baad|बाद)', lower)
        if min_match:
            minutes = int(min_match.group(1))
            remind_time = (now_ist() + timedelta(minutes=minutes)).strftime("%H:%M")
            # Extract text after minutes
            parts = re.split(r'\d+\s*(?:min|minute|मिनट)\s*(?:baad|बाद)', text)
            reminder_text = parts[-1].strip() if len(parts) > 1 else "Reminder"
            reminder_text = re.sub(r'(remind|yaad dilana|alarm)', '', reminder_text, flags=re.I).strip()
            if not reminder_text:
                reminder_text = "Reminder"
            repeat = "daily" if "daily" in lower or "roz" in lower else "once"
            return ("reminder", {"time": remind_time, "text": reminder_text[:100], "repeat": repeat})
        
        hour_match = re.search(r'(\d+)\s*(?:ghante|घंटे|hour)', lower)
        if hour_match:
            hours = int(hour_match.group(1))
            remind_time = (now_ist() + timedelta(hours=hours)).strftime("%H:%M")
            reminder_text = re.sub(r'\d+\s*(?:ghante|घंटे|hour).*?(remind|yaad dilana|alarm)', '', text, flags=re.I).strip()
            if not reminder_text:
                reminder_text = "Reminder"
            return ("reminder", {"time": remind_time, "text": reminder_text[:100], "repeat": "once"})
        
        time_match = re.search(r'(\d{1,2}):(\d{2})', lower)
        if time_match:
            h, m = int(time_match.group(1)), int(time_match.group(2))
            remind_time = f"{h:02d}:{m:02d}"
            reminder_text = re.sub(r'\d{1,2}:\d{2}', '', text).strip()
            reminder_text = re.sub(r'(remind|yaad dilana|alarm)', '', reminder_text, flags=re.I).strip()
            if not reminder_text:
                reminder_text = "Reminder"
            repeat = "daily" if "daily" in lower or "roz" in lower else "once"
            return ("reminder", {"time": remind_time, "text": reminder_text[:100], "repeat": repeat})
        
        # Simple: "remind me to call mum"
        if re.search(r'remind me to', lower):
            reminder_text = re.sub(r'remind me to', '', text).strip()
            # default 10 minutes later
            remind_time = (now_ist() + timedelta(minutes=10)).strftime("%H:%M")
            return ("reminder", {"time": remind_time, "text": reminder_text[:100], "repeat": "once"})
    
    # --- TASK ---
    if re.search(r'(task add|add task|new task|kaam add|टास्क ऐड)', lower):
        title = re.sub(r'(task add|add task|new task|kaam add|टास्क ऐड)', '', text).strip()
        if title:
            return ("add_task", {"title": title[:80]})
    
    if re.search(r'(mujhe|मुझे)\s+(.+?)\s+(karni hai|karna hai|करनी है|करना है)', lower):
        match = re.search(r'(mujhe|मुझे)\s+(.+?)\s+(karni hai|karna hai|करनी है|करना है)', lower)
        if match:
            return ("add_task", {"title": match.group(2).strip()[:80]})
    
    # --- TASK DONE ---
    if re.search(r'(task done|complete task|mark done|हो गया|done)', lower):
        id_match = re.search(r'#(\d+)', lower)
        if id_match:
            return ("complete_task", {"id": int(id_match.group(1))})
        return ("complete_task", {"id": None})
    
    # --- TASK DELETE ---
    if re.search(r'(delete task|remove task|टास्क हटाओ)', lower):
        id_match = re.search(r'#(\d+)', lower)
        if id_match:
            return ("delete_task", {"id": int(id_match.group(1))})
        return ("delete_task", {"id": None})
    
    # --- SHOW TASKS ---
    if re.search(r'(show tasks|my tasks|tasks list|pending tasks|सारे टास्क|all tasks)', lower):
        return ("show_tasks", {})
    
    if re.search(r'(completed tasks|done tasks|finished tasks)', lower):
        return ("show_completed", {})
    
    # --- HABIT ---
    if re.search(r'(habit add|add habit|new habit|आदत डालें)', lower):
        name = re.sub(r'(habit add|add habit|new habit|आदत डालें)', '', text).strip()
        if name:
            return ("add_habit", {"name": name[:50]})
    
    if re.search(r'(habit done|log habit|habit mark)', lower):
        id_match = re.search(r'#(\d+)', lower)
        if id_match:
            return ("log_habit", {"id": int(id_match.group(1))})
        return ("log_habit", {"id": None})
    
    if re.search(r'(show habits|my habits)', lower):
        return ("show_habits", {})
    
    # --- EXPENSE ---
    kharcha_match = re.search(r'(kharcha|खर्चा|expense|खर्च)\s+(\d+)\s*(.+)?', lower)
    if kharcha_match:
        amount = float(kharcha_match.group(2))
        desc = kharcha_match.group(3).strip() if kharcha_match.group(3) else "kharcha"
        return ("add_expense", {"amount": amount, "desc": desc[:60]})
    
    rupay_match = re.search(r'(\d+)\s*(?:rupaye|रुपये|rs)\s*(.+?)(?:ke|के|का|की|for)?', lower)
    if rupay_match:
        amount = float(rupay_match.group(1))
        desc = rupay_match.group(2).strip()
        return ("add_expense", {"amount": amount, "desc": desc[:60]})
    
    # --- BUDGET ---
    if re.search(r'(set budget|budget set|बजट सेट)', lower):
        num_match = re.search(r'(\d+)', lower)
        if num_match:
            return ("set_budget", {"amount": float(num_match.group(1))})
    
    # --- DIARY (multi-turn) ---
    if re.search(r'(diary add|diary likh|journal|डायरी लिख|डायरी ऐड)', lower):
        return ("diary_start", {})
    
    if re.search(r'(show diary|diary dikhao|read diary|diary view)', lower):
        return ("diary_view", {"date": "today"})
    
    # --- NOTES ---
    if re.search(r'(note add|add note|नोट ऐड)', lower):
        content = re.sub(r'(note add|add note|नोट ऐड)', '', text).strip()
        if content:
            return ("add_note", {"content": content[:200]})
    
    if re.search(r'(show notes|my notes|सारे नोट्स)', lower):
        return ("show_notes", {})
    
    if re.search(r'(delete note|remove note)', lower):
        id_match = re.search(r'#(\d+)', lower)
        if id_match:
            return ("delete_note", {"id": int(id_match.group(1))})
    
    # --- MEMORY ---
    if re.search(r'(yaad rakh|remember|याद रख|mera naam|meri umar)', lower):
        fact = text
        return ("add_memory", {"fact": fact[:200]})
    
    if re.search(r'(show memory|what do you remember|kya yaad hai)', lower):
        return ("show_memory", {})
    
    # --- WATER ---
    if re.search(r'(water|पानी|paani)', lower):
        ml_match = re.search(r'(\d+)\s*(?:ml|ML|गिलास)', lower)
        if ml_match:
            ml = int(ml_match.group(1))
        else:
            ml = 250
        return ("add_water", {"ml": ml})
    
    if re.search(r'(water status|kitna paani piya|water goal)', lower):
        return ("water_status", {})
    
    # --- BILL ---
    if re.search(r'(bill add|add bill|नया बिल)', lower):
        # try to extract name, amount, due_day
        parts = text.split()
        for i, p in enumerate(parts):
            if p.isdigit() and i+1 < len(parts) and parts[i+1].isdigit():
                name = " ".join(parts[:i]) if i>0 else "Bill"
                amount = float(p)
                due_day = int(parts[i+1])
                return ("add_bill", {"name": name[:30], "amount": amount, "due_day": due_day})
        return ("add_bill", {"name": text[:30], "amount": 0, "due_day": 1})
    
    if re.search(r'(bill paid|pay bill|बिल भर दिया)', lower):
        id_match = re.search(r'#(\d+)', lower)
        if id_match:
            return ("pay_bill", {"id": int(id_match.group(1))})
        return ("pay_bill", {"id": None})
    
    if re.search(r'(show bills|my bills|bills list)', lower):
        return ("show_bills", {})
    
    # --- CALENDAR ---
    if re.search(r'(calendar add|event add|add event|कैलेंडर ऐड)', lower):
        # extract date
        if 'kal' in lower:
            event_date = (now_ist().date() + timedelta(days=1)).isoformat()
        elif 'aaj' in lower:
            event_date = today_str()
        else:
            date_match = re.search(r'(\d{1,2})[-/](\d{1,2})', lower)
            if date_match:
                d, m = int(date_match.group(1)), int(date_match.group(2))
                event_date = f"{now_ist().year}-{m:02d}-{d:02d}"
            else:
                event_date = today_str()
        title = re.sub(r'(calendar add|event add|add event|कैलेंडर ऐड|aaj|kal|\d{1,2}[-/]\d{1,2})', '', text).strip()
        if title:
            return ("add_calendar", {"title": title[:60], "date": event_date})
    
    if re.search(r'(show calendar|my events|calendar dikhao)', lower):
        return ("show_calendar", {})
    
    # --- GOAL ---
    if re.search(r'(goal add|add goal|new goal|गोल ऐड|लक्ष्य जोड़)', lower):
        title = re.sub(r'(goal add|add goal|new goal|गोल ऐड|लक्ष्य जोड़)', '', text).strip()
        if title:
            return ("add_goal", {"title": title[:60]})
    
    if re.search(r'(goal progress|update goal|progress)', lower):
        id_match = re.search(r'#(\d+)', lower)
        pct_match = re.search(r'(\d+)\s*(?:%|percent)', lower)
        if id_match and pct_match:
            return ("update_goal", {"id": int(id_match.group(1)), "progress": int(pct_match.group(1))})
        elif id_match:
            return ("update_goal", {"id": int(id_match.group(1)), "progress": None})
    
    if re.search(r'(show goals|my goals|active goals)', lower):
        return ("show_goals", {})
    
    # --- NEWS ---
    if re.search(r'(news|समाचार|headlines)', lower):
        if 'tech' in lower:
            cat = "Tech"
        elif 'business' in lower:
            cat = "Business"
        elif 'sports' in lower:
            cat = "Sports"
        elif 'world' in lower:
            cat = "World"
        else:
            cat = "India"
        return ("get_news", {"category": cat})
    
    # --- REPORTS ---
    if re.search(r'(briefing|daily briefing|briefing dedo)', lower):
        return ("briefing", {})
    
    if re.search(r'(weekly report|weekly summary|hafta report)', lower):
        return ("weekly_report", {})
    
    if re.search(r'(yesterday|yesterday report|kal kya hua)', lower):
        return ("yesterday_report", {})
    
    if re.search(r'report for (\d{4}-\d{2}-\d{2})', lower):
        match = re.search(r'report for (\d{4}-\d{2}-\d{2})', lower)
        return ("date_report", {"date": match.group(1)})
    
    # --- CLEAR CHAT ---
    if re.search(r'(clear chat|sab clean|चैट क्लियर|सब क्लीन)', lower):
        return ("clear_chat", {})
    
    # --- SHOW REMINDERS ---
    if re.search(r'(show reminders|my reminders|reminders list|सारे रिमाइंडर)', lower):
        return ("show_reminders", {})
    
    # --- DELETE REMINDER ---
    if re.search(r'(delete reminder|remove reminder|हटाओ reminder)', lower):
        id_match = re.search(r'#(\d+)', lower)
        if id_match:
            return ("delete_reminder", {"id": int(id_match.group(1))})
    
    # Default: chat
    return ("chat", {})

# ==================== ACTION EXECUTOR (FULL) ====================
async def execute_action(action, params, chat_id, user_msg):
    if action == "reminder":
        r = reminders.add(chat_id, params["text"], params["time"], params["repeat"])
        repeat_txt = "Once" if params["repeat"]=="once" else "Daily 🔁" if params["repeat"]=="daily" else "Weekly 📅"
        await auto_backup()
        return f"✅ Reminder set!\n⏰ {params['time']} — {params['text']}\n{repeat_txt}\nID: #{r['id']}\n(delete: 'delete reminder #{r['id']}')"
    
    elif action == "add_task":
        t = tasks.add(params["title"])
        await auto_backup()
        return f"✅ Task added: #{t['id']} {t['title']}\n(complete: 'task done #{t['id']}')"
    
    elif action == "complete_task":
        tid = params["id"]
        if tid is None:
            pending = tasks.pending()
            if pending:
                tid = pending[0]["id"]
            else:
                return "❌ No pending task to complete."
        t = tasks.complete(tid)
        if t:
            await auto_backup()
            return f"✅ *Done!* {t['title']} 🎉"
        else:
            return "❌ Task not found or already done."
    
    elif action == "delete_task":
        tid = params["id"]
        if tid:
            tasks.delete(tid)
            await auto_backup()
            return f"🗑 Task #{tid} deleted."
        return "❌ Task ID not found."
    
    elif action == "show_tasks":
        pending = tasks.pending()
        if not pending:
            return "🎉 No pending tasks!"
        txt = "📋 *Pending tasks:*\n"
        for t in pending[:15]:
            priority_icon = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
            txt += f"  {priority_icon} #{t['id']} {t['title']}\n"
        return txt
    
    elif action == "show_completed":
        comp = tasks.completed()
        if not comp:
            return "✅ No completed tasks yet."
        txt = f"✅ *Completed tasks ({len(comp)}):*\n"
        for t in comp[-10:]:
            txt += f"  #{t['id']} {t['title']}\n"
        return txt
    
    elif action == "add_habit":
        h = habits.add(params["name"])
        await auto_backup()
        return f"💪 Habit added: {h['name']} (ID #{h['id']})\nTo log: 'habit done #{h['id']}'"
    
    elif action == "log_habit":
        hid = params["id"]
        if hid is None:
            pending = habits.today_pending()
            if pending:
                hid = pending[0]["id"]
            else:
                return "🎊 All habits done today!"
        ok, streak = habits.log(hid)
        if ok:
            await auto_backup()
            h = next((h for h in habits.all() if h["id"] == hid), None)
            return f"💪 {h['name'] if h else 'Habit'} done! 🔥 Streak: {streak} days!"
        else:
            return "✅ Already done today!"
    
    elif action == "show_habits":
        done, pending = habits.today_status()
        txt = "💪 *Habits today:*\n"
        if done:
            txt += "✅ Done: " + ", ".join(f"{h['emoji']}{h['name']}" for h in done) + "\n"
        if pending:
            txt += "⏳ Pending: " + ", ".join(f"{h['name']} (ID #{h['id']})" for h in pending) + "\n"
        if not done and not pending:
            txt = "💪 No habits added yet. Say: 'habit add exercise'"
        return txt
    
    elif action == "add_expense":
        expenses.add(params["amount"], params["desc"])
        await auto_backup()
        bl = expenses.budget_left()
        budget_msg = f" | Budget left: ₹{bl:.0f}" if bl else ""
        return f"✅ ₹{params['amount']:.0f} — {params['desc']}\nAaj total: ₹{expenses.today_total():.0f}{budget_msg}"
    
    elif action == "set_budget":
        expenses.set_budget(params["amount"])
        await auto_backup()
        return f"💳 Monthly budget set to ₹{params['amount']:.0f}"
    
    elif action == "diary_start":
        return ("DIARY_AWAIT", "📖 *Diary entry:* Send me the content. (Type /cancel to cancel)")
    
    elif action == "diary_view":
        entries = diary.get(today_str())
        if not entries:
            return f"📖 No diary entry for today. Say: 'diary add ...'"
        txt = f"📖 *Diary for {today_str()}:*\n\n"
        for e in entries:
            txt += f"🕐 {e['time']} — {e['text']}\n"
        return txt
    
    elif action == "add_note":
        n = notes.add(params["content"])
        await auto_backup()
        return f"📝 Note #{n['id']} saved.\n(delete: 'delete note #{n['id']}')"
    
    elif action == "show_notes":
        ns = notes.recent(10)
        if not ns:
            return "📝 No notes. Say: 'note add ...'"
        txt = "📝 *Recent notes:*\n"
        for n in ns:
            txt += f"  #{n['id']} {n['text'][:50]}\n"
        return txt
    
    elif action == "delete_note":
        notes.delete(params["id"])
        await auto_backup()
        return f"🗑 Note #{params['id']} deleted."
    
    elif action == "add_memory":
        memory.add_fact(params["fact"])
        await auto_backup()
        return "🧠 *Yaad rakh liya!* ✅"
    
    elif action == "show_memory":
        facts = memory.get_all_facts()
        if not facts:
            return "🧠 No memories yet."
        txt = "🧠 *What I remember:*\n"
        for f in facts[-15:]:
            txt += f"  📌 {f['f']}\n"
        return txt
    
    elif action == "add_water":
        water.add(params["ml"])
        await auto_backup()
        total = water.today_total()
        goal = water.goal()
        pct = int(total/goal*100) if goal else 0
        return f"💧 +{params['ml']}ml | Total: {total}ml/{goal}ml ({pct}%)"
    
    elif action == "water_status":
        total = water.today_total()
        goal = water.goal()
        pct = int(total/goal*100) if goal else 0
        return f"💧 Today: {total}ml / {goal}ml ({pct}%)"
    
    elif action == "add_bill":
        if params["amount"] == 0:
            return "Please say: 'bill add internet 500 15'"
        b = bills.add(params["name"], params["amount"], params["due_day"])
        await auto_backup()
        return f"✅ Bill added: {b['name']} ₹{b['amount']:.0f} due on {b['due_day']}th\nTo mark paid: 'bill paid #{b['id']}'"
    
    elif action == "pay_bill":
        bid = params["id"]
        if bid is None:
            due = bills.due_soon()
            if due:
                bid = due[0]["id"]
            else:
                return "No due bills found."
        if bills.mark_paid(bid):
            await auto_backup()
            return f"✅ Bill #{bid} marked paid for this month."
        else:
            return "❌ Bill not found or already paid."
    
    elif action == "show_bills":
        all_b = bills.all_active()
        if not all_b:
            return "💳 No bills added. Say: 'bill add internet 500 15'"
        txt = "💳 *Bills:*\n"
        for b in all_b:
            status = "✅" if bills.is_paid_this_month(b["id"]) else "⏳"
            txt += f"  {status} #{b['id']} {b['name']} ₹{b['amount']:.0f} due {b['due_day']}th\n"
        return txt
    
    elif action == "add_calendar":
        e = calendar.add(params["title"], params["date"])
        await auto_backup()
        return f"📅 Event added: {e['title']} on {e['date']}\n(ID #{e['id']})"
    
    elif action == "show_calendar":
        events = calendar.upcoming(30)
        if not events:
            return "📅 No upcoming events."
        txt = "📅 *Upcoming events:*\n"
        for e in events[:15]:
            today_flag = "🔴 TODAY" if e["date"] == today_str() else "📆"
            txt += f"  {today_flag} {e['date']} — {e['title']}\n"
        return txt
    
    elif action == "add_goal":
        g = goals.add(params["title"])
        await auto_backup()
        return f"🎯 Goal added: #{g['id']} {g['title']}\nUpdate progress: 'goal progress #{g['id']} 50'"
    
    elif action == "update_goal":
        gid = params["id"]
        pct = params.get("progress")
        if not gid:
            return "Please specify goal ID: 'goal progress #1 50'"
        if pct is None:
            g = next((g for g in goals.active() if g["id"] == gid), None)
            if g:
                return f"📊 Goal #{gid}: {g['title']} — {g['progress']}% complete."
            else:
                return f"Goal #{gid} not found."
        g = goals.update_progress(gid, pct)
        if g:
            await auto_backup()
            bar = "█" * (g['progress']//10) + "░" * (10 - (g['progress']//10))
            return f"📊 {g['title']}\n`{bar}` {g['progress']}% complete!"
        else:
            return f"❌ Goal #{gid} not found."
    
    elif action == "show_goals":
        active = goals.active()
        if not active:
            return "🎯 No active goals. Say: 'goal add learn Python'"
        txt = "🎯 *Active goals:*\n"
        for g in active[:10]:
            bar = "█" * (g['progress']//10) + "░" * (10 - (g['progress']//10))
            txt += f"  #{g['id']} {g['title']} `{bar}` {g['progress']}%\n"
        return txt
    
    elif action == "get_news":
        items = news_store.get(params["category"])
        if not items:
            return "📰 News unavailable."
        txt = f"📰 *{params['category']} NEWS:*\n\n"
        for item in items[:5]:
            txt += f"• {item['title']}\n"
        return txt
    
    elif action == "briefing":
        n = now_ist()
        tp = tasks.today_pending()
        hd, hp = habits.today_status()
        txt = f"🌅 *BRIEFING* {n.strftime('%I:%M %p')}\n\n"
        if tp:
            txt += f"📋 Tasks ({len(tp)}):\n" + "\n".join(f"  • {t['title']}" for t in tp[:5]) + "\n"
        else:
            txt += "📋 No pending tasks.\n"
        if hp:
            txt += f"💪 Habits left: {', '.join(h['name'] for h in hp[:4])}\n"
        txt += f"\n💰 Today ₹{expenses.today_total():.0f} | Month ₹{expenses.month_total():.0f}"
        bl = expenses.budget_left()
        if bl:
            txt += f" | Budget left ₹{bl:.0f}"
        txt += f"\n💧 Water: {water.today_total()}ml/{water.goal()}ml"
        return txt
    
    elif action == "weekly_report":
        n = now_ist()
        task_week = tasks.weekly_summary()
        total_done = sum(v["done"] for v in task_week.values())
        total_created = sum(v["created"] for v in task_week.values())
        txt = f"📊 *WEEKLY REPORT*\n"
        txt += f"📅 {n.strftime('%d %b')} - {(n+timedelta(days=6)).strftime('%d %b')}\n\n"
        txt += f"📋 Tasks: {total_done} done, {total_created} created\n"
        txt += f"⏳ Currently pending: {len(tasks.pending())}\n\n"
        txt += f"💰 Month expenses: ₹{expenses.month_total():.0f}\n"
        txt += f"💧 Water this week: {sum(water.week_summary().values())}ml"
        return txt
    
    elif action == "yesterday_report":
        yd = yesterday_str()
        tasks_done = tasks.done_on(yd)
        expenses_yest = expenses.get_by_date(yd)
        diary_yest = diary.get(yd)
        habits_logs = habits.data["logs"].get(yd, [])
        habits_done = [h for h in habits.all() if h["id"] in habits_logs]
        txt = f"📅 *YESTERDAY ({yd})*\n\n"
        txt += f"✅ Tasks done: {len(tasks_done)}\n"
        if tasks_done:
            txt += "   " + "\n   ".join(f"• {t['title']}" for t in tasks_done[:5]) + "\n"
        txt += f"💰 Expenses: ₹{sum(e['amount'] for e in expenses_yest):.0f}\n"
        txt += f"💪 Habits done: {len(habits_done)}\n"
        if diary_yest:
            txt += f"\n📖 Diary: {diary_yest[0]['text'][:80]}"
        return txt
    
    elif action == "date_report":
        target = params["date"]
        try:
            datetime.strptime(target, "%Y-%m-%d")
        except:
            return "Invalid date format. Use YYYY-MM-DD"
        tasks_done = tasks.done_on(target)
        expenses_on = expenses.get_by_date(target)
        diary_entries = diary.get(target)
        habits_logs = habits.data["logs"].get(target, [])
        habits_done = [h for h in habits.all() if h["id"] in habits_logs]
        txt = f"📋 *REPORT FOR {target}*\n\n"
        txt += f"✅ Tasks done: {len(tasks_done)}\n"
        if tasks_done:
            txt += "   " + "\n   ".join(f"• {t['title']}" for t in tasks_done[:5]) + "\n"
        txt += f"💰 Expenses: ₹{sum(e['amount'] for e in expenses_on):.0f}\n"
        if expenses_on:
            txt += "   " + "\n   ".join(f"• ₹{e['amount']:.0f} {e['desc']}" for e in expenses_on[:5]) + "\n"
        txt += f"💪 Habits done: {len(habits_done)}\n"
        if diary_entries:
            txt += f"\n📖 Diary: {diary_entries[0]['text'][:100]}"
        return txt
    
    elif action == "clear_chat":
        chat.clear()
        return "🧹 Chat history cleared! (Your tasks, reminders, etc. are safe)"
    
    elif action == "show_reminders":
        active = reminders.all_active()
        if not active:
            return "⏰ No active reminders. Say: 'remind me at 15:30'"
        txt = "⏰ *Reminders:*\n"
        for r in active:
            icon = "🔁" if r["repeat"] == "daily" else "📅" if r["repeat"] == "weekly" else "1️⃣"
            txt += f"  {icon} #{r['id']} {r['time']} — {r['text']}\n"
        return txt
    
    elif action == "delete_reminder":
        reminders.delete(params["id"])
        await auto_backup()
        return f"🗑 Reminder #{params['id']} deleted."
    
    else:  # chat
        # Build context for AI
        context = f"Today: {today_str()} {time_label()}\n"
        pending_tasks = tasks.pending()
        if pending_tasks:
            context += f"Pending tasks: {', '.join(t['title'][:30] for t in pending_tasks[:3])}\n"
        context += memory.context()
        prompt = f"""You are a friendly personal assistant. Reply in Hindi/Hinglish (2-4 lines). Be warm and helpful.

{context}

User: {user_msg}

Reply:"""
        reply = call_gemini(prompt, max_tokens=200)
        if not reply:
            reply = "Haan bolo, main sun raha hoon! 😊"
        chat.add("user", user_msg)
        chat.add("assistant", reply)
        return reply

# ==================== TELEGRAM HANDLERS ====================
DIARY_STATE = 1

async def start(update, ctx):
    name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(
        f"🕌 *Assalamualaikum {name}!*\n\n"
        f"Main aapka personal assistant hoon.\n\n"
        f"*Jo bolo, main samjh jaunga:*\n"
        f"✅ '2 min baad paani peene ki yaad dilana'\n"
        f"✅ 'task add meeting kal 3 baje'\n"
        f"✅ 'kharcha 100 chai'\n"
        f"✅ 'diary add karo' (then type content)\n"
        f"✅ 'habit add exercise'\n"
        f"✅ 'water 250ml'\n"
        f"✅ 'bill add internet 500 15'\n"
        f"✅ 'calendar add doctor Friday'\n"
        f"✅ 'goal add learn Python'\n"
        f"✅ 'show tasks', 'show reminders', 'show habits'\n"
        f"✅ 'briefing', 'weekly report', 'yesterday'\n"
        f"✅ 'report for 2026-05-01'\n"
        f"✅ 'news', 'tech news'\n"
        f"✅ 'sab clean karo' - clear chat history\n\n"
        f"_Sab kuch auto-backup ho raha hai Google Sheets me!_\n"
        f"_Kuch bhi bolo, main ready hoon!_",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.strip()
    if text.startswith('/'):
        if text == '/start':
            await start(update, ctx)
        elif text == '/cancel':
            ctx.user_data.pop("awaiting_diary", None)
            await update.message.reply_text("❌ Cancelled.")
        return
    
    # Check if waiting for diary content
    if ctx.user_data.get("awaiting_diary"):
        ctx.user_data.pop("awaiting_diary")
        diary.add(text)
        await auto_backup()
        await update.message.reply_text(f"📖 *Diary saved!* 🕐 {now_str()}\n\n_{text[:150]}_", parse_mode="Markdown")
        return
    
    # Parse natural action
    action, params = parse_natural_action(text)
    result = await execute_action(action, params, update.effective_chat.id, text)
    
    if isinstance(result, tuple) and result[0] == "DIARY_AWAIT":
        ctx.user_data["awaiting_diary"] = True
        await update.message.reply_text(result[1], parse_mode="Markdown")
    else:
        await update.message.reply_text(result, parse_mode="Markdown")

async def cancel(update, ctx):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")

# Voice handler
async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not GROQ_API_KEY:
        await update.message.reply_text("🎤 Voice requires GROQ_API_KEY")
        return
    voice = update.message.voice or update.message.audio
    if not voice:
        return
    status = await update.message.reply_text("🎤 _Sun raha hoon..._", parse_mode="Markdown")
    try:
        import tempfile
        from groq import Groq
        file = await ctx.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)
        client = Groq(api_key=GROQ_API_KEY)
        with open(tmp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=f,
                response_format="text",
                language="hi",
            )
        text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
        os.unlink(tmp_path)
        if text:
            await status.edit_text(f"🎤 *Suna:* _{text}_", parse_mode="Markdown")
            # Process as normal message
            action, params = parse_natural_action(text)
            result = await execute_action(action, params, update.effective_chat.id, text)
            if isinstance(result, tuple) and result[0] == "DIARY_AWAIT":
                ctx.user_data["awaiting_diary"] = True
                await update.message.reply_text(result[1], parse_mode="Markdown")
            else:
                await update.message.reply_text(result, parse_mode="Markdown")
        else:
            await status.edit_text("❌ Samajh nahi aaya.")
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")

# Reminder job
async def reminder_job(context):
    now = now_ist()
    now_time = now.strftime("%H:%M")
    if now_time in ("00:00", "00:01"):
        reminders.reset_daily()
    due = reminders.due_now()
    for r in due:
        try:
            repeat_note = "\n🔁 _Kal bhi yaad dilaunga!_" if r["repeat"] == "daily" else ""
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=f"🔔 *{r['time']}* — {r['text']}{repeat_note}",
                parse_mode="Markdown"
            )
            reminders.mark_fired(r["id"])
            await asyncio.sleep(1)
        except Exception as e:
            log.error(f"Reminder send failed: {e}")

# Main
def main():
    n = now_ist()
    log.info(f"🤖 Natural Language Assistant — FULL FEATURES")
    log.info(f"⏰ IST: {n.strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"📊 Sheets: {'✅' if google_sheets.sheet else '❌'}")
    log.info(f"📦 All features: Tasks | Habits | Diary | Expenses | Reminders | Water | Bills | Calendar | Goals | Notes | News | Reports | Memory")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    
    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=15)
    
    log.info("✅ Bot ready! Start speaking naturally.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
