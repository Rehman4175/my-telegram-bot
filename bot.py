#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════╗
║       PERSONAL AI ASSISTANT — ADVANCED v3.0          ║
║  100% FREE | Gemini Multi-Model | News | Smart Memory ║
╚══════════════════════════════════════════════════════╝
"""

import os, json, logging, time, asyncio, urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta
from xml.etree import ElementTree as ET
import re as _re

# SSL fix
ssl._create_default_https_context = ssl._create_unverified_context

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    log.error("❌ Environment variables missing!")
    exit(1)

GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

# FILE PATHS
DATA = os.path.join(os.getcwd(), "data")
os.makedirs(DATA, exist_ok=True)

F_MEMORY   = os.path.join(DATA, "memory.json")
F_TASKS    = os.path.join(DATA, "tasks.json")
F_DIARY    = os.path.join(DATA, "diary.json")
F_HABITS   = os.path.join(DATA, "habits.json")
F_NOTES    = os.path.join(DATA, "notes.json")
F_EXPENSES = os.path.join(DATA, "expenses.json")
F_GOALS    = os.path.join(DATA, "goals.json")
F_CHAT     = os.path.join(DATA, "chat_history.json")
F_NEWS     = os.path.join(DATA, "news_cache.json")
F_REMINDERS = os.path.join(DATA, "reminders.json")
F_WATER    = os.path.join(DATA, "water.json")
F_BILLS    = os.path.join(DATA, "bills.json")
F_CALENDAR = os.path.join(DATA, "calendar.json")

# ══════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════
def load(path, default=None):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"Load error {path}: {e}")
    return default if default is not None else {}

def save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Save error {path}: {e}")

def today_str():     return date.today().isoformat()
def now_str():       return datetime.now().strftime("%H:%M")
def yesterday_str(): return (date.today() - timedelta(days=1)).isoformat()

# ══════════════════════════════════════════════
# 1. CHAT HISTORY CLASS (Sabse Pehle Define Kiya)
# ══════════════════════════════════════════════
class ChatHistory:
    def __init__(self):
        self.data = load(F_CHAT, {"history": [], "cleared_at": None, "msg_ids": []})
        if "msg_ids" not in self.data:
            self.data["msg_ids"] = []

    def add(self, role: str, content: str):
        self.data["history"].append({"role": role, "content": content, "time": datetime.now().isoformat()})
        self.data["history"] = self.data["history"][-80:]
        save(F_CHAT, self.data)

    def track_msg(self, chat_id: int, msg_id: int):
        self.data["msg_ids"].append({"chat_id": chat_id, "msg_id": msg_id})
        self.data["msg_ids"] = self.data["msg_ids"][-500:]
        save(F_CHAT, self.data)

    def get_tracked_ids(self):
        return self.data.get("msg_ids", [])

    def get_recent(self, n=20) -> list:
        return [{"role": m["role"], "content": m["content"]} for m in self.data["history"][-n:]]

    def clear(self):
        count = len(self.data["history"])
        self.data["history"] = []
        self.data["cleared_at"] = datetime.now().isoformat()
        save(F_CHAT, self.data)
        return count

    def clear_msg_ids(self):
        self.data["msg_ids"] = []
        save(F_CHAT, self.data)

    def count(self):
        return len(self.data["history"])

# ══════════════════════════════════════════════
# 2. GEMINI CALLER
# ══════════════════════════════════════════════
def call_gemini(system_prompt: str, messages: list) -> str:
    try:
        contents = [{"role": "user", "parts": [{"text": system_prompt}]}]
        for m in messages:
            contents.append({"role": m.get("role", "user"), "parts": [{"text": m.get("content", "")}]})

        payload = json.dumps({
            "contents": contents,
            "generationConfig": {"temperature": 0.75, "maxOutputTokens": 600}
        }).encode("utf-8")

        for model in GEMINI_MODELS:
            try:
                url = BASE_URL.format(model=model, key=GEMINI_API_KEY)
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=45) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    return result["candidates"][0]["content"]["parts"][0]["text"]
            except:
                continue
        return "⚠️ Gemini API busy hai. Thodi der baad try karo!"
    except:
        return "❌ Kuch technical issue hai. Baad mein try karo."

# ══════════════════════════════════════════════
# 3. NEWS FUNCTION
# ══════════════════════════════════════════════
NEWS_FEEDS = {
    "India": "https://feeds.bbci.co.uk/hindi/rss.xml",
    "Technology": "https://feeds.feedburner.com/ndtvnews-tech-news",
    "Business": "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Sports": "https://feeds.bbci.co.uk/sport/rss.xml",
}

def fetch_news(category="India", max_items=5):
    return [{"title": "News service abhi available nahi", "desc": "", "link": ""}]

# ══════════════════════════════════════════════
# 4. BAaki SAB CLASSES
# ══════════════════════════════════════════════
class Memory:
    def __init__(self):
        self.data = load(F_MEMORY, {"facts": [], "prefs": {}, "dates": {}, "important_notes": []})
    def save_data(self): save(F_MEMORY, self.data)
    def add_fact(self, fact): 
        self.data["facts"].append({"f": fact, "d": today_str()})
        self.save_data()

class Tasks:
    def __init__(self):
        self.data = load(F_TASKS, {"list": [], "counter": 0})
    def save_data(self): save(F_TASKS, self.data)
    def add(self, title, priority="medium"):
        self.data["counter"] += 1
        t = {"id": self.data["counter"], "title": title, "priority": priority, "done": False}
        self.data["list"].append(t)
        self.save_data()
        return t
    def pending(self): return [t for t in self.data["list"] if not t.get("done")]

class Diary:
    def __init__(self):
        self.data = load(F_DIARY, {"entries": {}})
    def save_data(self): save(F_DIARY, self.data)
    def add(self, content, mood="😊"):
        td = today_str()
        if td not in self.data["entries"]:
            self.data["entries"][td] = []
        self.data["entries"][td].append({"text": content, "mood": mood, "time": now_str()})
        self.save_data()

class Habits:
    def __init__(self):
        self.data = load(F_HABITS, {"list": [], "logs": {}, "counter": 0})
    def save_data(self): save(F_HABITS, self.data)
    def add(self, name, emoji="✅"):
        self.data["counter"] += 1
        h = {"id": self.data["counter"], "name": name, "emoji": emoji, "streak": 0}
        self.data["list"].append(h)
        self.save_data()

class Notes:
    def __init__(self):
        self.data = load(F_NOTES, {"list": [], "counter": 0})
    def save_data(self): save(F_NOTES, self.data)
    def add(self, content):
        self.data["counter"] += 1
        n = {"id": self.data["counter"], "text": content}
        self.data["list"].append(n)
        self.save_data()

class Expenses:
    def __init__(self):
        self.data = load(F_EXPENSES, {"list": [], "counter": 0})
    def save_data(self): save(F_EXPENSES, self.data)
    def add(self, amount, desc):
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "amount": amount, "desc": desc, "date": today_str()}
        self.data["list"].append(e)
        self.save_data()

class Goals:
    def __init__(self):
        self.data = load(F_GOALS, {"list": [], "counter": 0})
    def save_data(self): save(F_GOALS, self.data)
    def add(self, title):
        self.data["counter"] += 1
        g = {"id": self.data["counter"], "title": title, "progress": 0, "done": False}
        self.data["list"].append(g)
        self.save_data()

class Reminders:
    def __init__(self):
        self.data = load(F_REMINDERS, {"list": [], "counter": 0})
    def save_data(self): save(F_REMINDERS, self.data)
    def add(self, chat_id, text, time_str):
        self.data["counter"] += 1
        r = {"id": self.data["counter"], "chat_id": chat_id, "text": text, "time": time_str}
        self.data["list"].append(r)
        self.save_data()

class WaterTracker:
    def __init__(self):
        self.data = load(F_WATER, {"logs": {}, "goal_ml": 2000})
    def save_data(self): save(F_WATER, self.data)
    def add(self, ml=250):
        td = today_str()
        if td not in self.data["logs"]: self.data["logs"][td] = []
        self.data["logs"][td].append({"ml": ml})
        self.save_data()

class BillTracker:
    def __init__(self):
        self.data = load(F_BILLS, {"list": [], "counter": 0})
    def save_data(self): save(F_BILLS, self.data)
    def add(self, name, amount, due_day):
        self.data["counter"] += 1
        b = {"id": self.data["counter"], "name": name, "amount": amount, "due_day": due_day}
        self.data["list"].append(b)
        self.save_data()

class CalendarManager:
    def __init__(self):
        self.data = load(F_CALENDAR, {"events": [], "counter": 0})
    def save_data(self): save(F_CALENDAR, self.data)
    def add(self, title, event_date):
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "title": title, "date": event_date}
        self.data["events"].append(e)
        self.save_data()

# ══════════════════════════════════════════════
# INIT ALL — Ab sab classes define ho chuke hain
# ══════════════════════════════════════════════
chat_hist = ChatHistory()
mem       = Memory()
tasks     = Tasks()
diary     = Diary()
habits    = Habits()
notes     = Notes()
expenses  = Expenses()
goals     = Goals()
reminders = Reminders()
water     = WaterTracker()
bills     = BillTracker()
calendar  = CalendarManager()

# ══════════════════════════════════════════════
# START COMMAND
# ══════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(f"🕌 *Assalamualaikum {name}!*\nMain tumhara Personal AI Dost hoon.\nKya madad karun aaj?", parse_mode="Markdown")

# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
def main():
    log.info("🤖 Personal AI Bot v4.0 Starting...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))

    log.info("✅ Bot successfully started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
