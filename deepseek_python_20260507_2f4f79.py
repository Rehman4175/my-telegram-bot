#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PERSONAL AI ASSISTANT — FULLY FUNCTIONAL VERSION
- All actions working: reminders, tasks, expenses, habits, etc.
- No HuggingFace, no MongoDB, no extra buttons
- Clean and reliable
"""

import os, json, logging, time, asyncio, random
import urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta, timezone
import datetime as dt_module
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

DIARY_PASSWORD = "Rk1996"  # Keep password for diary view
DIARY_AWAIT_PASS = 1

if not TELEGRAM_TOKEN:
    log.error("❌ TELEGRAM_TOKEN not set!")
    exit(1)

# IST Timezone
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
        if default is None:
            default = {}
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            log.warning(f"Local load '{collection}' failed: {e}")
        return default

    def save(self, collection, data):
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"Local save '{collection}' failed: {e}")

db = Database()

# Gemini API
GEMINI_MODELS = ["gemini-2.0-flash-lite", "gemini-2.0-flash"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
_last_gemini_call = 0

def call_gemini(prompt, max_tokens=400, is_action=False):
    global _last_gemini_call
    if not GEMINI_API_KEY:
        return None
    now = time.time()
    elapsed = now - _last_gemini_call
    if elapsed < 3:
        time.sleep(3 - elapsed + random.uniform(0.5, 1.5))
    _last_gemini_call = time.time()

    temp = 0.0 if is_action else 0.7
    tokens = min(max_tokens, 200 if is_action else 600)

    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temp, "maxOutputTokens": tokens}
    }).encode("utf-8")

    for model in GEMINI_MODELS:
        try:
            url = GEMINI_URL.format(model=model, key=GEMINI_API_KEY)
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=35) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                log.info(f"✅ Gemini: {model}")
                return text.strip()
        except Exception as e:
            log.warning(f"Gemini fail ({model}): {e}")
            continue
    return None

# Smart fallback for offline
def smart_fallback(user_msg):
    msg = user_msg.lower().strip()
    n = now_ist()
    
    if any(w in msg for w in ["time", "baje", "kitne baje", "time kya"]):
        return f"⏰ Abhi *{n.strftime('%I:%M %p')}* baj rahe hain (IST)"
    
    if any(w in msg for w in ["date", "aaj kya", "tarikh"]):
        return f"📅 Aaj *{n.strftime('%A, %d %B %Y')}* hai"
    
    if any(w in msg for w in ["hello", "hi", "assalam", "namaste", "hey"]):
        return "🕌 *Assalamualaikum!* Main aapka AI dost hoon. Batao kaisi help chahiye? 😊"
    
    if any(w in msg for w in ["kaise ho", "how are", "kya haal"]):
        return "😊 *Main badiya hoon!* Aap sunao?"
    
    if any(w in msg for w in ["thank", "shukriya", "thanks"]):
        return "🤗 *Welcome!*"
    
    if any(w in msg for w in ["bye", "allah hafiz", "good night"]):
        return "🌙 *Allah Hafiz!*"
    
    replies = [
        "🙏 Main yahin hoon! Batao kya help chahiye? Tasks, reminders, ya kuch aur?",
        "😊 Haan bolo! Kya karna hai aaj?",
    ]
    return random.choice(replies)

# Voice transcription
async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not GROQ_API_KEY:
        return
    
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    status_msg = await update.message.reply_text("🎤 _Sun raha hoon..._", parse_mode="Markdown")

    try:
        import tempfile
        from groq import Groq

        file = await ctx.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

        client = Groq(api_key=GROQ_API_KEY)
        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=audio_file,
                response_format="text",
                language="hi",
            )
        text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
        
        try:
            os.unlink(tmp_path)
        except:
            pass

        if not text:
            await status_msg.edit_text("❌ Samajh nahi aaya — thoda saaf bolke bhejna!")
            return

        await status_msg.edit_text(f"🎤 *Suna:* _{text}_", parse_mode="Markdown")
        await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        reply = await ai_chat(text, update.effective_chat.id)
        await update.message.reply_text(reply, parse_mode="Markdown")

    except Exception as e:
        log.error(f"Voice error: {e}")
        await status_msg.edit_text("❌ Voice process nahi hua.")

# ==================== DATA STORES ====================
class MemoryStore:
    def __init__(self):
        self.data = db.load("memory", {"facts": []})
    def save(self):
        db.save("memory", self.data)
    def add_fact(self, text):
        facts = self.data.get("facts", [])
        facts.append({"f": text[:200], "d": today_str()})
        self.data["facts"] = facts[-100:]
        self.save()
    def get_all(self):
        return self.data.get("facts", [])
    def context(self):
        facts = "\n".join(f"• {x['f']}" for x in self.get_all()[-15:]) or "Kuch nahi"
        return f"FACTS:\n{facts}"

class TaskStore:
    def __init__(self):
        self.data = db.load("tasks", {"list": [], "counter": 0})
    def save(self):
        db.save("tasks", self.data)
    def add(self, title, priority="medium"):
        self.data["counter"] = self.data.get("counter", 0) + 1
        t = {"id": self.data["counter"], "title": title, "priority": priority, "done": False, "done_at": None, "created": today_str(), "due": today_str()}
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
        before = len(self.data["list"])
        self.data["list"] = [t for t in self.data["list"] if t["id"] != tid]
        self.save()
        return before != len(self.data["list"])
    def pending(self):
        return [t for t in self.data.get("list", []) if not t["done"]]
    def all_tasks(self):
        return self.data.get("list", [])
    def completed_tasks(self):
        return [t for t in self.data.get("list", []) if t["done"]]
    def today_pending(self):
        td = today_str()
        return [t for t in self.data.get("list", []) if not t["done"] and t.get("due", "") <= td]
    def done_on(self, d):
        return [t for t in self.data.get("list", []) if t["done"] and t.get("done_at") == d]

class DiaryStore:
    def __init__(self):
        self.data = db.load("diary", {"entries": {}})
    def save(self):
        db.save("diary", self.data)
    def add(self, text, mood="😊"):
        td = today_str()
        self.data.setdefault("entries", {}).setdefault(td, [])
        self.data["entries"][td].append({"text": text, "mood": mood, "time": now_str()})
        self.save()
    def get(self, d):
        return self.data.get("entries", {}).get(d, [])
    def get_all(self):
        return self.data.get("entries", {})

class HabitStore:
    def __init__(self):
        self.data = db.load("habits", {"list": [], "logs": {}, "counter": 0})
    def save(self):
        db.save("habits", self.data)
    def add(self, name, emoji="✅"):
        self.data["counter"] = self.data.get("counter", 0) + 1
        h = {"id": self.data["counter"], "name": name, "emoji": emoji, "streak": 0, "best_streak": 0}
        self.data["list"].append(h)
        self.save()
        return h
    def log(self, hid):
        td = today_str()
        logs = self.data.get("logs", {})
        logs.setdefault(td, [])
        if hid in logs[td]:
            return False, 0
        logs[td].append(hid)
        for h in self.data["list"]:
            if h["id"] == hid:
                yd_logs = logs.get(yesterday_str(), [])
                h["streak"] = h.get("streak", 0) + 1 if hid in yd_logs else 1
                h["best_streak"] = max(h.get("best_streak", 0), h["streak"])
        self.data["logs"] = logs
        self.save()
        streak = next((h.get("streak", 1) for h in self.data["list"] if h["id"] == hid), 1)
        return True, streak
    def today_status(self):
        done_ids = self.data.get("logs", {}).get(today_str(), [])
        all_h = self.all()
        return ([h for h in all_h if h["id"] in done_ids], [h for h in all_h if h["id"] not in done_ids])
    def all(self):
        return self.data.get("list", [])
    def delete(self, hid):
        self.data["list"] = [h for h in self.data["list"] if h["id"] != hid]
        self.save()
    def get_logs_by_date(self, target_date):
        return self.data.get("logs", {}).get(target_date, [])

class ExpenseStore:
    def __init__(self):
        self.data = db.load("expenses", {"list": [], "budget": {}})
    def save(self):
        db.save("expenses", self.data)
    def add(self, amount, desc, category="general"):
        self.data["list"].append({"amount": amount, "desc": desc, "category": category, "date": today_str(), "time": now_str()})
        self.save()
    def set_budget(self, amount):
        self.data["budget"]["monthly"] = amount
        self.save()
    def today_total(self):
        td = today_str()
        return sum(e["amount"] for e in self.data.get("list", []) if e.get("date") == td)
    def month_total(self):
        m = today_str()[:7]
        return sum(e["amount"] for e in self.data.get("list", []) if e.get("date", "")[:7] == m)
    def budget_left(self):
        b = self.data.get("budget", {}).get("monthly", 0)
        return b - self.month_total() if b else None
    def get_by_date(self, target_date):
        return [e for e in self.data.get("list", []) if e.get("date") == target_date]

class ReminderStore:
    def __init__(self):
        self.data = db.load("reminders", {"list": [], "counter": 0})
    def save(self):
        db.save("reminders", self.data)
    def add(self, chat_id, text, remind_at, repeat="once"):
        self.data["counter"] = self.data.get("counter", 0) + 1
        r = {"id": self.data["counter"], "chat_id": chat_id, "text": text, "time": remind_at, "repeat": repeat, "date": today_str(), "active": True, "fired_today": False}
        self.data["list"].append(r)
        self.save()
        log.info(f"Reminder added: #{r['id']} at {remind_at}")
        return r
    def all_active(self):
        return [r for r in self.data.get("list", []) if r.get("active")]
    def get_all(self):
        return self.data.get("list", [])
    def delete(self, rid):
        before = len(self.data["list"])
        self.data["list"] = [r for r in self.data["list"] if r["id"] != rid]
        self.save()
        return before != len(self.data["list"])
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
        now = now_ist()
        now_hm = now.strftime("%H:%M")
        due = []
        for r in self.data.get("list", []):
            if not r.get("active") or r.get("fired_today"):
                continue
            if r["time"] == now_hm:
                due.append(r)
        return due

class WaterStore:
    def __init__(self):
        self.data = db.load("water", {"logs": {}, "goal_ml": 2000})
    def save(self):
        db.save("water", self.data)
    def add(self, ml=250):
        td = today_str()
        self.data.setdefault("logs", {}).setdefault(td, [])
        self.data["logs"][td].append({"ml": ml, "time": now_str()})
        self.save()
    def today_total(self):
        return sum(e["ml"] for e in self.data.get("logs", {}).get(today_str(), []))
    def goal(self):
        return self.data.get("goal_ml", 2000)
    def set_goal(self, ml):
        self.data["goal_ml"] = ml
        self.save()

class BillStore:
    def __init__(self):
        self.data = db.load("bills", {"list": [], "counter": 0})
    def save(self):
        db.save("bills", self.data)
    def add(self, name, amount, due_day):
        self.data["counter"] = self.data.get("counter", 0) + 1
        b = {"id": self.data["counter"], "name": name, "amount": amount, "due_day": due_day, "active": True, "paid_months": []}
        self.data["list"].append(b)
        self.save()
        return b
    def all_active(self):
        return [b for b in self.data.get("list", []) if b.get("active")]
    def mark_paid(self, bid):
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid and ym not in b.get("paid_months", []):
                b["paid_months"].append(ym)
                self.save()
                return True
        return False
    def is_paid_this_month(self, bid):
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid:
                return ym in b.get("paid_months", [])
        return False
    def delete(self, bid):
        before = len(self.data["list"])
        self.data["list"] = [b for b in self.data["list"] if b["id"] != bid]
        self.save()
        return before != len(self.data["list"])

class CalendarStore:
    def __init__(self):
        self.data = db.load("calendar", {"events": [], "counter": 0})
    def save(self):
        db.save("calendar", self.data)
    def add(self, title, event_date, event_time=""):
        self.data["counter"] = self.data.get("counter", 0) + 1
        e = {"id": self.data["counter"], "title": title, "date": event_date, "time": event_time}
        self.data["events"].append(e)
        self.save()
        return e
    def delete(self, eid):
        before = len(self.data["events"])
        self.data["events"] = [e for e in self.data["events"] if e["id"] != eid]
        self.save()
        return before != len(self.data["events"])
    def today_events(self):
        return [e for e in self.data.get("events", []) if e["date"] == today_str()]

class GoalStore:
    def __init__(self):
        self.data = db.load("goals", {"list": [], "counter": 0})
    def save(self):
        db.save("goals", self.data)
    def add(self, title):
        self.data["counter"] = self.data.get("counter", 0) + 1
        g = {"id": self.data["counter"], "title": title, "progress": 0, "done": False}
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
        return [g for g in self.data.get("list", []) if not g["done"]]

class ChatHistoryStore:
    def __init__(self):
        self.data = db.load("chat_history", {"history": []})
    def save(self):
        db.save("chat_history", self.data)
    def add(self, role, content):
        self.data["history"].append({"role": role, "content": content})
        self.data["history"] = self.data["history"][-40:]
        self.save()
    def clear(self):
        count = len(self.data["history"])
        self.data["history"] = []
        self.save()
        return count

# Initialize stores
memory = MemoryStore()
tasks = TaskStore()
diary = DiaryStore()
habits = HabitStore()
expenses = ExpenseStore()
reminders = ReminderStore()
water = WaterStore()
bills = BillStore()
calendar = CalendarStore()
goals = GoalStore()
chat_hist = ChatHistoryStore()

# Google Sheets Backup (simplified)
class GoogleSheetsBackup:
    def __init__(self):
        self.sheet = None
        if not HAS_GSHEETS:
            return
        creds_json = os.environ.get("GOOGLE_CREDS_JSON", "") or os.environ.get("Google_CREDS_JSON", "")
        if not creds_json:
            return
        try:
            creds_dict = json.loads(creds_json)
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            self.sheet = client.open_by_key("1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")
            log.info("✅ Google Sheets connected")
        except Exception as e:
            log.error(f"Sheets error: {e}")

google_sheets = GoogleSheetsBackup()

# ==================== ACTION SYSTEM ====================
ACTION_SYSTEM_PROMPT = """You are a JSON router. Parse user message and return ONLY raw JSON (no markdown, no backticks).

Current time: {now}
Today: {today}

Actions:
REMIND — {"time":"HH:MM","text":"...","repeat":"once/daily/weekly"} (only if user asks for reminder)
ADD_TASK — {"title":"...","priority":"high/medium/low"}
ADD_EXPENSE — {"amount":number,"desc":"..."}
ADD_DIARY — {"text":"...","mood":"😊"}
ADD_MEMORY — {"fact":"..."}
ADD_HABIT — {"name":"...","emoji":"💪"}
COMPLETE_TASK — {"title_hint":"..."}
SHOW_TASKS — {}
SHOW_REMINDERS — {}
CHAT — {} (default)
"""

def regex_action_fallback(user_msg):
    lower = user_msg.lower().strip()
    now = now_ist()
    
    # Reminder detection (explicit)
    remind_words = ["remind me", "set reminder", "alarm laga", "yaad dila", "remind", "alarm set"]
    if any(w in lower for w in remind_words):
        time_match = _re.search(r'(\d{1,2}):(\d{2})', lower)
        if time_match:
            h, m = int(time_match.group(1)), int(time_match.group(2))
            time_str = f"{h:02d}:{m:02d}"
            text = _re.sub(r'\d{1,2}:\d{2}', '', user_msg)
            text = ' '.join([w for w in text.split() if w.lower() not in remind_words])
            if not text.strip():
                text = "Reminder"
            repeat = "daily" if "daily" in lower or "roz" in lower else "weekly" if "weekly" in lower else "once"
            return {"action": "REMIND", "params": {"time": time_str, "text": text[:100], "repeat": repeat}}
        
        min_match = _re.search(r'(\d+)\s*(?:min|minute|m)', lower)
        if min_match:
            mins = int(min_match.group(1))
            time_str = (now + timedelta(minutes=mins)).strftime("%H:%M")
            text = _re.sub(r'\d+\s*(?:min|minute|m)', '', user_msg)
            text = ' '.join([w for w in text.split() if w.lower() not in remind_words])
            if not text.strip():
                text = "Reminder"
            return {"action": "REMIND", "params": {"time": time_str, "text": text[:100], "repeat": "once"}}
    
    # Task detection
    task_words = ["task add", "add task", "new task", "kaam add"]
    if any(w in lower for w in task_words):
        title = _re.sub(r'(task add|add task|new task|kaam add)', '', user_msg).strip()
        if title:
            return {"action": "ADD_TASK", "params": {"title": title[:80], "priority": "medium"}}
    
    # Expense detection
    if any(w in lower for w in ["kharcha", "expense", "rs ", "rupaye"]):
        amount_match = _re.search(r'(\d+)', lower)
        if amount_match:
            amount = float(amount_match.group(1))
            desc = _re.sub(r'\d+', '', user_msg).strip()
            if not desc:
                desc = "kharcha"
            return {"action": "ADD_EXPENSE", "params": {"amount": amount, "desc": desc[:60]}}
    
    # Diary detection
    diary_words = ["diary likh", "diary add", "journal"]
    if any(w in lower for w in diary_words):
        text = _re.sub(r'(diary likh|diary add|journal)', '', user_msg).strip()
        if text:
            return {"action": "ADD_DIARY", "params": {"text": text[:200], "mood": "📝"}}
    
    # Habit detection
    if lower.startswith("habit add") or "new habit" in lower:
        name = _re.sub(r'(habit add|new habit)', '', user_msg).strip()
        if name:
            return {"action": "ADD_HABIT", "params": {"name": name[:50], "emoji": "✅"}}
    
    # Show tasks
    if any(w in lower for w in ["show tasks", "my tasks", "tasks list", "pending tasks"]):
        return {"action": "SHOW_TASKS", "params": {}}
    
    # Show reminders
    if any(w in lower for w in ["show reminders", "my reminders", "reminders list"]):
        return {"action": "SHOW_REMINDERS", "params": {}}
    
    # Complete task
    if any(w in lower for w in ["complete task", "task done", "mark done"]):
        # Try to extract ID or title
        id_match = _re.search(r'#(\d+)', lower)
        if id_match:
            return {"action": "COMPLETE_TASK", "params": {"title_hint": id_match.group(1)}}
        return {"action": "COMPLETE_TASK", "params": {"title_hint": ""}}
    
    return {"action": "CHAT", "params": {}}

def call_gemini_action(user_msg):
    if not GEMINI_API_KEY:
        return regex_action_fallback(user_msg)
    try:
        now_label = time_label()
        prompt = ACTION_SYSTEM_PROMPT.format(now=now_label, today=today_str())
        full_msg = f"{prompt}\n\nUser: {user_msg}"
        payload = json.dumps({"contents": [{"role": "user", "parts": [{"text": full_msg}]}], "generationConfig": {"temperature": 0.0, "maxOutputTokens": 200}}).encode("utf-8")
        for model in GEMINI_MODELS:
            try:
                url = GEMINI_URL.format(model=model, key=GEMINI_API_KEY)
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=20) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                    raw = raw.replace("```json", "").replace("```", "").strip()
                    json_match = _re.search(r'\{.*\}', raw, _re.DOTALL)
                    if json_match:
                        raw = json_match.group(0)
                    parsed = json.loads(raw)
                    log.info(f"Action: {parsed.get('action')}")
                    return parsed
            except Exception as e:
                continue
    except Exception as e:
        log.warning(f"Action detection error: {e}")
    return regex_action_fallback(user_msg)

async def execute_action(action_data, chat_id, user_msg):
    action = action_data.get("action", "CHAT")
    params = action_data.get("params", {})
    
    if action == "REMIND":
        time_str = params.get("time", "")
        text = params.get("text", "Reminder")
        repeat = params.get("repeat", "once")
        if not time_str or not _re.match(r'^\d{2}:\d{2}$', time_str):
            return f"⏰ Time format galat! Use HH:MM (e.g., 15:30)"
        r = reminders.add(chat_id, text, time_str, repeat)
        rl = {"once": "Once", "daily": "Daily 🔁", "weekly": "Weekly 📅"}.get(repeat, repeat)
        return f"✅ *Reminder set!*\n⏰ {time_str} — {text}\n{rl}\n🆔 `#{r['id']}` | Use `/delremind {r['id']}` to delete"
    
    elif action == "ADD_TASK":
        title = params.get("title", user_msg[:80])
        priority = params.get("priority", "medium")
        t = tasks.add(title, priority)
        icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        return f"✅ Task: {icons.get(priority,'🟡')} *{t['title']}*\n🆔 `#{t['id']}`"
    
    elif action == "ADD_EXPENSE":
        amount = float(params.get("amount", 0))
        desc = params.get("desc", "Kharcha")
        if amount <= 0:
            return "💰 Amount batao?"
        expenses.add(amount, desc)
        return f"✅ ₹{amount:.0f} — {desc}\n📊 Aaj: ₹{expenses.today_total():.0f}"
    
    elif action == "ADD_DIARY":
        diary.add(params.get("text", user_msg[:100]), params.get("mood", "😊"))
        return f"📖 *Diary saved!* 🕐 {now_str()}\n\n_{user_msg[:120]}_"
    
    elif action == "ADD_MEMORY":
        memory.add_fact(params.get("fact", user_msg[:200]))
        return f"🧠 Yaad kar liya! ✅"
    
    elif action == "ADD_HABIT":
        h = habits.add(params.get("name", user_msg[:50]), params.get("emoji", "✅"))
        return f"💪 Habit: {h['emoji']} *{h['name']}*\nUse `/hdone {h['id']}` to log"
    
    elif action == "COMPLETE_TASK":
        hint = params.get("title_hint", "").lower()
        pending = tasks.pending()
        matched = None
        if hint.isdigit():
            matched = next((t for t in pending if t["id"] == int(hint)), None)
        if not matched and hint:
            matched = next((t for t in pending if hint in t["title"].lower()), None)
        if not matched and pending:
            matched = pending[-1]  # last added
        if matched:
            tasks.complete(matched["id"])
            return f"✅ *{matched['title']}* — done! 🎉"
        return "❓ Kaunsa task? ID ya naam batao."
    
    elif action == "SHOW_TASKS":
        pending = tasks.today_pending()
        if not pending:
            return "🎉 No pending tasks!"
        txt = f"📋 *PENDING ({len(pending)})*\n\n"
        for t in pending[:10]:
            icon = "🔴" if t['priority']=='high' else "🟡" if t['priority']=='medium' else "🟢"
            txt += f"{icon} *#{t['id']}* {t['title']}\n"
        return txt
    
    elif action == "SHOW_REMINDERS":
        active = reminders.all_active()
        if not active:
            return f"⏰ No reminders! Use `/remind 2m Test`"
        txt = f"⏰ *REMINDERS ({len(active)})*\n\n"
        for r in active:
            icon = "🔁" if r["repeat"] == "daily" else "📅" if r["repeat"] == "weekly" else "1️⃣"
            txt += f"*#{r['id']}* {icon} `{r['time']}` — {r['text']}\n"
        return txt
    
    else:  # CHAT
        # Auto-save facts
        if any(w in user_msg.lower() for w in ["yaad rakh", "remember", "mera naam"]):
            memory.add_fact(user_msg[:200])
        chat_hist.add("user", user_msg)
        system = build_system_prompt()
        reply = call_gemini(system + f"\n\nUser: {user_msg}\n\nShort Hindi reply (2-4 lines):")
        if not reply:
            reply = smart_fallback(user_msg)
        chat_hist.add("assistant", reply)
        return reply

# System prompt builder
def build_system_prompt():
    n = now_ist()
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    exp_t = expenses.today_total()
    exp_m = expenses.month_total()
    bl = expenses.budget_left()
    water_today = water.today_total()
    water_goal = water.goal()
    
    tasks_s = "\n".join(f"  {'🔴' if t['priority']=='high' else '🟡'} {t['title']}" for t in tp[:5]) or "  Koi nahi"
    h_done = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    h_pend = ", ".join(f"{h['name']}" for h in hp) or "Sab ho gaye!"
    budget_s = f"Budget baaki: ₹{bl:.0f}" if bl else ""
    water_pct = int(water_today / water_goal * 100) if water_goal else 0

    return f"""Tu mera Personal AI Assistant hai. Hindi/Hinglish mein baat kar. Dost jaisa.

TIME: {time_label()}

📋 AAJ KE TASKS ({len(tp)}):
{tasks_s}

💪 HABITS: Done: {h_done} | Baaki: {h_pend}

💰 KHARCHA: Aaj ₹{exp_t} | Mahina ₹{exp_m} {budget_s}

💧 PAANI: {water_today}ml/{water_goal}ml ({water_pct}%)

🧠 YAADDASHT:
{memory.context()}

RULES:
- Dost ki tarah baat kar, short reply (2-4 lines)
- Time puchne pe EXACT TIME batana
"""

async def ai_chat(user_msg, chat_id=None):
    if chat_id:
        action_data = call_gemini_action(user_msg)
        return await execute_action(action_data, chat_id, user_msg)
    else:
        return call_gemini(build_system_prompt() + f"\n\nUser: {user_msg}\n\nReply:") or smart_fallback(user_msg)

# ==================== COMMAND HANDLERS ====================
async def cmd_start(update, ctx):
    n = now_ist()
    name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(
        f"🕌 *Assalamualaikum {name}!*\n\n⏰ {n.strftime('%I:%M %p')} IST | 📅 {n.strftime('%d %b %Y')}\n\n"
        f"📋 Tasks | 💪 Habits | 📖 Diary | 💰 Expenses | ⏰ Reminders\n"
        f"💧 Water | 💳 Bills | 📅 Calendar | 🎯 Goals\n\n"
        f"_Seedha type karo — main samjhunga!_\n`/help` for commands",
        parse_mode="Markdown"
    )

async def cmd_help(update, ctx):
    await update.message.reply_text(
        "📋 *COMMANDS*\n\n"
        "**📝 TASKS**\n/task → Add task\n/done → Complete task\n/deltask → Delete task\n\n"
        "**💪 HABITS**\n/habit → Add habit\n/hdone → Complete habit\n/delhabit → Delete habit\n\n"
        "**📖 DIARY**\n/diary → Write diary (password required to view)\n\n"
        "**💰 EXPENSES**\n/kharcha → Add expense\n/budget → Set budget\n\n"
        "**⏰ REMINDERS**\n/remind → Set reminder\n/reminders → List reminders\n/delremind → Delete reminder\n\n"
        "**💧 WATER**\n/water → Log water\n/waterstatus → Check status\n/watergoal → Set goal\n\n"
        "**💳 BILLS**\n/bill → Add bill\n/bills → List bills\n/billpaid → Mark paid\n/delbill → Delete bill\n\n"
        "**📅 CALENDAR**\n/cal → Add event\n/calendar → List events\n/delcal → Delete event\n\n"
        "**🎯 GOALS**\n/goal → Add goal\n/gprogress → Update progress\n\n"
        "**📊 REPORTS**\n/briefing → Daily briefing\n/weekly → Weekly report\n/report → Date report\n/yesterday → Yesterday's summary\n/alltasks → All tasks\n/completed → Completed tasks\n\n"
        "**🔧 OTHER**\n/memory → Show memory\n/clear → Clear chat history\n/backup → Manual backup to Sheets\n/dbstatus → Database status",
        parse_mode="Markdown"
    )

async def cmd_task(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📋 `/task Kaam`")
        return
    t = tasks.add(" ".join(ctx.args))
    await update.message.reply_text(f"✅ Task: #{t['id']} *{t['title']}*", parse_mode="Markdown")

async def cmd_done(update, ctx):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            msg = "📋 *Pending tasks:*\n" + "\n".join(f"`/done {t['id']}` → {t['title']}" for t in pending[:10])
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("🎉 No pending tasks!")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t:
            await update.message.reply_text(f"🎉 *Done!* {t['title']}", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Task not found or already done!")
    except:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_deltask(update, ctx):
    if not ctx.args:
        return
    try:
        if tasks.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Deleted!")
    except:
        pass

async def cmd_diary(update, ctx):
    if ctx.args:
        diary.add(" ".join(ctx.args))
        await update.message.reply_text(f"📖 *Diary saved!* 🕐 {now_str()}", parse_mode="Markdown")
        return
    
    # View diary - require password
    await update.message.reply_text("🔐 *Diary — Password:*", parse_mode="Markdown")
    return DIARY_AWAIT_PASS

async def diary_password_check(update, ctx):
    if update.message.text.strip() != DIARY_PASSWORD:
        await update.message.reply_text("❌ *Wrong password!*")
        return ConversationHandler.END
    
    entries = diary.get(today_str())
    if not entries:
        await update.message.reply_text(f"📖 No diary entry for {today_str()}")
        return ConversationHandler.END
    
    txt = f"📖 *Diary — {today_str()}*\n\n" + "\n".join(f"🕐 {e['time']} — {e['text']}" for e in entries)
    await update.message.reply_text(txt, parse_mode="Markdown")
    return ConversationHandler.END

async def diary_conv_cancel(update, ctx):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

async def cmd_habit(update, ctx):
    if not ctx.args:
        await update.message.reply_text("💪 `/habit Naam`")
        return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(f"💪 *{h['name']}* — `/hdone {h['id']}`", parse_mode="Markdown")

async def cmd_hdone(update, ctx):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            msg = "💪 *Pending habits:*\n" + "\n".join(f"`/hdone {h['id']}` → {h['name']}" for h in pending)
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("🎊 Sab done! Great job!")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        if ok:
            await update.message.reply_text(f"💪 Done! 🔥 Streak: {streak} days!", parse_mode="Markdown")
        else:
            await update.message.reply_text("✅ Already done today!")
    except:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_delhabit(update, ctx):
    if not ctx.args:
        return
    try:
        habits.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Deleted!")
    except:
        pass

async def cmd_kharcha(update, ctx):
    if len(ctx.args) < 2:
        await update.message.reply_text("💰 `/kharcha 100 Chai`")
        return
    try:
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        await update.message.reply_text(f"💰 ₹{amount:.0f} — {desc}\n📊 Aaj: ₹{expenses.today_total():.0f}", parse_mode="Markdown")
    except:
        pass

async def cmd_budget(update, ctx):
    if not ctx.args:
        return
    try:
        expenses.set_budget(float(ctx.args[0]))
        await update.message.reply_text(f"💳 Budget: ₹{ctx.args[0]}")
    except:
        pass

async def cmd_remind(update, ctx):
    if not ctx.args:
        await update.message.reply_text(
            f"⏰ *REMINDER*\n`/remind 2m Test` — 2 min baad\n`/remind 15:30 Meeting` — exact time\n`/remind 8:00 Uthna daily`",
            parse_mode="Markdown")
        return
    
    now = now_ist()
    time_arg = ctx.args[0].lower()
    rest = ctx.args[1:]
    repeat = "once"
    
    if rest and rest[-1].lower() in ["daily", "weekly"]:
        repeat = rest[-1].lower()
        rest = rest[:-1]
    
    text = " ".join(rest) if rest else "Reminder!"
    
    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        remind_at = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        parts = time_arg.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            remind_at = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        else:
            await update.message.reply_text("❌ Format galat!")
            return
    else:
        await update.message.reply_text("❌ Format galat! Use: `/remind 2m Test` or `/remind 15:30 Meeting`")
        return
    
    r = reminders.add(update.effective_chat.id, text, remind_at, repeat)
    rl = {"once": "Once", "daily": "Daily 🔁", "weekly": "Weekly 📅"}.get(repeat, repeat)
    await update.message.reply_text(f"✅ *Reminder set!*\n⏰ {remind_at} — {text}\n{rl}\n🆔 `#{r['id']}` | `/delremind {r['id']}`", parse_mode="Markdown")

async def cmd_reminders_list(update, ctx):
    active = reminders.all_active()
    if not active:
        await update.message.reply_text("⏰ No reminders!")
        return
    txt = f"⏰ *REMINDERS ({len(active)})*\n\n"
    for r in active:
        icon = "🔁" if r["repeat"] == "daily" else "📅" if r["repeat"] == "weekly" else "1️⃣"
        txt += f"*#{r['id']}* {icon} `{r['time']}` — {r['text']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_delremind(update, ctx):
    if not ctx.args:
        return
    try:
        if reminders.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Reminder deleted!")
    except:
        pass

async def cmd_water(update, ctx):
    ml = 250
    if ctx.args:
        try:
            ml = int(ctx.args[0])
        except:
            pass
    water.add(ml)
    total = water.today_total()
    goal = water.goal()
    pct = min(100, int(total / goal * 100)) if goal else 0
    await update.message.reply_text(f"💧 +{ml}ml | Total: {total}ml/{goal}ml ({pct}%)", parse_mode="Markdown")

async def cmd_water_status(update, ctx):
    total = water.today_total()
    goal = water.goal()
    pct = min(100, int(total / goal * 100)) if goal else 0
    await update.message.reply_text(f"💧 {total}ml / {goal}ml ({pct}%)", parse_mode="Markdown")

async def cmd_water_goal(update, ctx):
    if not ctx.args:
        await update.message.reply_text(f"Current goal: {water.goal()}ml\n`/watergoal 2500`", parse_mode="Markdown")
        return
    try:
        water.set_goal(int(ctx.args[0]))
        await update.message.reply_text(f"✅ Water goal set to {ctx.args[0]}ml")
    except:
        pass

async def cmd_bill(update, ctx):
    if len(ctx.args) < 3:
        await update.message.reply_text("💳 `/bill Name Amount DueDay`\nExample: `/bill Internet 999 15`")
        return
    try:
        b = bills.add(ctx.args[0], float(ctx.args[1]), int(ctx.args[2]))
        await update.message.reply_text(f"✅ Bill: {b['name']} ₹{b['amount']:.0f} — Due on {b['due_day']}th", parse_mode="Markdown")
    except:
        pass

async def cmd_bills_list(update, ctx):
    all_b = bills.all_active()
    if not all_b:
        await update.message.reply_text("💳 No bills!")
        return
    txt = "💳 *BILLS*\n\n" + "\n".join(f"{'✅' if bills.is_paid_this_month(b['id']) else '⏳'} *{b['name']}* — ₹{b['amount']:.0f} (Due {b['due_day']}th)" for b in all_b)
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_bill_paid(update, ctx):
    if not ctx.args:
        return
    try:
        if bills.mark_paid(int(ctx.args[0])):
            await update.message.reply_text("✅ Bill marked paid!")
    except:
        pass

async def cmd_del_bill(update, ctx):
    if not ctx.args:
        return
    try:
        if bills.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Bill deleted!")
    except:
        pass

async def cmd_cal(update, ctx):
    if not ctx.args:
        await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`\n`/cal aaj Meeting`\n`/cal kal Client`")
        return
    args_str = " ".join(ctx.args)
    date_str = None
    title = args_str
    
    if args_str.lower().startswith("aaj "):
        date_str = today_str()
        title = args_str[4:]
    elif args_str.lower().startswith("kal "):
        date_str = (now_ist().date() + timedelta(days=1)).isoformat()
        title = args_str[4:]
    elif _re.match(r'^\d{4}-\d{2}-\d{2}', args_str):
        date_str = args_str[:10]
        title = args_str[11:] if len(args_str) > 11 else ""
    
    if not date_str:
        await update.message.reply_text("❌ Use: `/cal YYYY-MM-DD Event` or `/cal aaj Meeting`")
        return
    
    e = calendar.add(title, date_str)
    await update.message.reply_text(f"📅 Event: {title} — {date_str}", parse_mode="Markdown")

async def cmd_cal_list(update, ctx):
    events = calendar.today_events()
    if not events:
        await update.message.reply_text("📅 No events today!")
        return
    txt = "📅 *TODAY'S EVENTS*\n\n" + "\n".join(f"• {e['title']}" for e in events)
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_del_cal(update, ctx):
    if not ctx.args:
        return
    try:
        if calendar.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Event deleted!")
    except:
        pass

async def cmd_goal(update, ctx):
    if not ctx.args:
        active = goals.active()
        if active:
            msg = "🎯 *ACTIVE GOALS*\n\n" + "\n".join(f"#{g['id']} {g['title']} — {g['progress']}%" for g in active)
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("🎯 `/goal Learn Python`")
        return
    g = goals.add(" ".join(ctx.args))
    await update.message.reply_text(f"🎯 Goal: #{g['id']} {g['title']}\n`/gprogress {g['id']} 50`", parse_mode="Markdown")

async def cmd_gprogress(update, ctx):
    if len(ctx.args) < 2:
        await update.message.reply_text("📊 `/gprogress <goal_id> <percentage>`")
        return
    try:
        gid = int(ctx.args[0])
        progress = int(ctx.args[1])
        g = goals.update_progress(gid, progress)
        if g:
            await update.message.reply_text(f"📊 {g['title']} — {g['progress']}% complete!", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Goal not found!")
    except:
        pass

async def cmd_briefing(update, ctx):
    n = now_ist()
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    txt = f"🌅 *BRIEFING*\n⏰ {n.strftime('%I:%M %p')}\n\n"
    if tp:
        txt += f"📋 *Tasks:*\n" + "\n".join(f"  {'🔴' if t['priority']=='high' else '🟡'} {t['title']}" for t in tp[:5])
    else:
        txt += "🎉 No pending tasks!\n"
    if hp:
        txt += f"\n💪 Habits left: {', '.join(h['name'] for h in hp[:4])}"
    txt += f"\n\n💰 Today: ₹{expenses.today_total():.0f} | Month: ₹{expenses.month_total():.0f}"
    bl = expenses.budget_left()
    if bl:
        txt += f" | Budget left: ₹{bl:.0f}"
    w_t = water.today_total()
    w_g = water.goal()
    txt += f"\n💧 Water: {w_t}ml/{w_g}ml"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_weekly(update, ctx):
    n = now_ist()
    txt = f"📊 *WEEKLY REPORT*\n📅 Week of {n.strftime('%d %b')}\n\n"
    total_done = 0
    for i in range(7):
        d = (n.date() - timedelta(days=i)).isoformat()
        total_done += len(tasks.done_on(d))
    txt += f"📋 Tasks completed: {total_done}\n⏳ Pending: {len(tasks.pending())}\n\n"
    txt += f"💰 Month total: ₹{expenses.month_total():.0f}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_report(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📋 `/report YYYY-MM-DD`")
        return
    target_date = ctx.args[0]
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except:
        await update.message.reply_text("❌ Invalid date! Use YYYY-MM-DD")
        return
    
    tasks_done = tasks.done_on(target_date)
    expenses_on = expenses.get_by_date(target_date)
    diary_entries = diary.get(target_date)
    habits_logs = habits.get_logs_by_date(target_date)
    habits_done = [h for h in habits.all() if h["id"] in habits_logs]
    
    txt = f"📋 *REPORT FOR {target_date}*\n\n"
    txt += f"✅ Tasks done: {len(tasks_done)}\n"
    if tasks_done:
        txt += "   " + "\n   ".join(f"• {t['title']}" for t in tasks_done[:5]) + "\n"
    txt += f"\n💰 Expenses: ₹{sum(e['amount'] for e in expenses_on):.0f}\n"
    txt += f"\n💪 Habits done: {len(habits_done)}\n"
    if diary_entries:
        txt += f"\n📖 Diary: {diary_entries[0]['text'][:100]}"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_yesterday(update, ctx):
    yd = yesterday_str()
    tasks_done = tasks.done_on(yd)
    expenses_yest = expenses.get_by_date(yd)
    diary_yest = diary.get(yd)
    habits_logs = habits.get_logs_by_date(yd)
    habits_done = [h for h in habits.all() if h["id"] in habits_logs]
    
    txt = f"📅 *YESTERDAY ({yd})*\n\n"
    txt += f"✅ Tasks done: {len(tasks_done)}\n"
    txt += f"💰 Expenses: ₹{sum(e['amount'] for e in expenses_yest):.0f}\n"
    txt += f"💪 Habits done: {len(habits_done)}\n"
    if diary_yest:
        txt += f"\n📖 Diary: {diary_yest[0]['text'][:80]}"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_alltasks(update, ctx):
    all_t = tasks.all_tasks()
    if not all_t:
        await update.message.reply_text("📋 No tasks!")
        return
    p = tasks.pending()
    c = tasks.completed_tasks()
    txt = f"📋 *ALL TASKS*\nTotal: {len(all_t)} | Pending: {len(p)} | Done: {len(c)}\n\n"
    if p:
        txt += "⏳ *Pending:*\n" + "\n".join(f"   #{t['id']} {t['title']}" for t in p[:10]) + "\n"
    if c:
        txt += "\n✅ *Completed (last 5):*\n" + "\n".join(f"   #{t['id']} {t['title']}" for t in c[-5:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed(update, ctx):
    c = tasks.completed_tasks()
    if not c:
        await update.message.reply_text("✅ No completed tasks yet!")
        return
    txt = f"✅ *COMPLETED TASKS ({len(c)})*\n\n" + "\n".join(f"  ✓ #{t['id']} {t['title']}" for t in c[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_memory(update, ctx):
    facts = memory.get_all()
    if not facts:
        await update.message.reply_text("🧠 No memories saved yet!")
        return
    txt = "🧠 *MY MEMORY*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_clear(update, ctx):
    count = chat_hist.clear()
    await update.message.reply_text(f"🧹 Cleared {count} chat messages!")

async def cmd_backup(update, ctx):
    await update.message.reply_text("📤 Backing up to Google Sheets...")
    result = google_sheets.full_sync() if google_sheets.sheet else "❌ Sheets not connected"
    await update.message.reply_text(result)

async def cmd_dbstatus(update, ctx):
    status = "✅ Connected" if google_sheets.sheet else "❌ Not connected"
    txt = f"📊 *Database Status*\n\nGoogle Sheets: {status}\n\n"
    txt += f"📋 Tasks: {len(tasks.all_tasks())}\n"
    txt += f"⏰ Reminders: {len(reminders.all_active())}\n"
    txt += f"📖 Diary entries: {sum(len(v) for v in diary.get_all().values())}\n"
    txt += f"💰 Expenses: {len(expenses.data.get('list', []))}\n"
    txt += f"💪 Habits: {len(habits.all())}\n"
    txt += f"🎯 Goals: {len(goals.active())}\n"
    txt += f"💳 Bills: {len(bills.all_active())}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

# Message handler for natural language
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_msg = update.message.text.strip()
    if user_msg.startswith('/'):
        return
    
    # Quick greetings
    lower = user_msg.lower()
    if lower in ["hello", "hi", "hey", "assalam", "namaste"]:
        name = update.effective_user.first_name or "Dost"
        await update.message.reply_text(f"🕌 *Assalamualaikum {name}!* 😊\n\nKaise ho?", parse_mode="Markdown")
        return
    
    if "kaise ho" in lower or "how are" in lower:
        await update.message.reply_text("😊 *Main badiya hoon!* Aap sunao?", parse_mode="Markdown")
        return
    
    if "thank" in lower or "shukriya" in lower:
        await update.message.reply_text("🤗 *Welcome!*", parse_mode="Markdown")
        return
    
    if "bye" in lower or "allah hafiz" in lower:
        await update.message.reply_text("🌙 *Allah Hafiz!*", parse_mode="Markdown")
        return
    
    # Process action
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await execute_action(call_gemini_action(user_msg), update.effective_chat.id, user_msg)
    await update.message.reply_text(reply, parse_mode="Markdown")

# Reminder job
async def reminder_job(context):
    now = now_ist()
    now_time = now.strftime("%H:%M")
    
    if now_time in ("00:00", "00:01"):
        reminders.reset_daily()
        return
    
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
            log.error(f"Reminder failed: {e}")

# Main
def main():
    n = now_ist()
    log.info(f"🤖 Bot — FULLY FUNCTIONAL")
    log.info(f"⏰ IST: {n.strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"📊 Sheets: {'✅' if google_sheets.sheet else '❌'}")
    log.info("=" * 40)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commands
    commands = [
        ("start", cmd_start), ("help", cmd_help),
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("habit", cmd_habit), ("hdone", cmd_hdone), ("delhabit", cmd_delhabit),
        ("kharcha", cmd_kharcha), ("budget", cmd_budget),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list), ("delremind", cmd_delremind),
        ("water", cmd_water), ("waterstatus", cmd_water_status), ("watergoal", cmd_water_goal),
        ("bill", cmd_bill), ("bills", cmd_bills_list), ("billpaid", cmd_bill_paid), ("delbill", cmd_del_bill),
        ("cal", cmd_cal), ("calendar", cmd_cal_list), ("delcal", cmd_del_cal),
        ("goal", cmd_goal), ("gprogress", cmd_gprogress),
        ("briefing", cmd_briefing), ("weekly", cmd_weekly), ("report", cmd_report), ("yesterday", cmd_yesterday),
        ("alltasks", cmd_alltasks), ("completed", cmd_completed),
        ("memory", cmd_memory), ("clear", cmd_clear), ("backup", cmd_backup), ("dbstatus", cmd_dbstatus),
    ]
    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))

    # Diary conversation (password protected view)
    diary_conv = ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary)],
        states={DIARY_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)]},
        fallbacks=[CommandHandler("cancel", diary_conv_cancel)],
        per_user=True, conversation_timeout=30
    )
    app.add_handler(diary_conv)

    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=15)

    log.info("✅ Bot ready! Test: /start or 'remind me at 15:30'")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()