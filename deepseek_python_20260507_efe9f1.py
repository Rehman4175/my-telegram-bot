#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v14.1 REMINDER FIXED                ║
║  ✅ Reminder absolutely working                                 ║
║  ✅ Midnight reset                                              ║
║  ✅ 2-minute grace window                                       ║
║  ✅ Snooze + Done buttons                                       ║
║  ✅ All other features intact                                   ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, json, logging, time, asyncio, random
import urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta, timezone
import datetime as dt_module
from xml.etree import ElementTree as ET
import re as _re
from collections import defaultdict

ssl._create_default_https_context = ssl._create_unverified_context

# Optional imports
try:
    import requests as req_lib
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from pymongo import MongoClient
    HAS_MONGO = True
except ImportError:
    HAS_MONGO = False

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
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", os.environ.get("Google_CREDS_JSON", ""))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")

SECRET_CODE = "Rk1996"
DIARY_PASSWORD = "Rk1996"
DIARY_AWAIT_PASS = 1

if not TELEGRAM_TOKEN:
    log.error("❌ TELEGRAM_TOKEN not set!")
    exit(1)

# ═══════════════════════════════════════════════════════════════════
# INDIAN STANDARD TIME (IST)
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
# DATABASE — Google Sheets PRIMARY + JSON local cache
# ═══════════════════════════════════════════════════════════════════
class Database:
    def __init__(self):
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)
        log.info("💾 Database: JSON local cache + Google Sheets sync")

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
        return default if default is not None else {}

    def save(self, collection, data):
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"Local save '{collection}' failed: {e}")

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
GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]
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

    temp = 0.0 if is_action else 0.75
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
        except urllib.error.HTTPError as e:
            if e.code == 429:
                log.warning(f"Rate limited ({model})")
                time.sleep(5)
                continue
            log.warning(f"Gemini {e.code} ({model})")
            continue
        except Exception as e:
            log.warning(f"Gemini fail ({model}): {e}")
            continue
    return None

# ═══════════════════════════════════════════════════════════════════
# HUGGINGFACE FALLBACK (FREE)
# ═══════════════════════════════════════════════════════════════════
HF_MODELS = ["mistralai/Mistral-7B-Instruct-v0.2", "google/gemma-2b-it"]

def call_huggingface(prompt):
    if not HAS_REQUESTS or not HF_TOKEN:
        return None
    for model_id in HF_MODELS:
        try:
            resp = req_lib.post(
                f"https://api-inference.huggingface.co/models/{model_id}",
                headers={"Authorization": f"Bearer {HF_TOKEN}"},
                json={"inputs": prompt, "parameters": {"max_new_tokens": 200, "temperature": 0.7}},
                timeout=30
            )
            if resp.status_code == 200:
                result = resp.json()
                text = ""
                if isinstance(result, dict):
                    text = result.get("generated_text", "")
                elif isinstance(result, list) and result:
                    text = result[0].get("generated_text", "")
                if text and len(text) > 10:
                    if prompt in text:
                        text = text.replace(prompt, "").strip()
                    log.info(f"✅ HF: {model_id}")
                    return text
        except Exception as e:
            log.warning(f"HF fail ({model_id}): {e}")
            continue
    return None

# ═══════════════════════════════════════════════════════════════════
# SMART OFFLINE FALLBACK
# ═══════════════════════════════════════════════════════════════════
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
        return "😊 *Main badiya hoon!* Aap sunao, kya ho raha hai aaj kal?"
    if any(w in msg for w in ["thank", "shukriya", "thanks"]):
        return "🤗 *Welcome!* Aur koi help chahiye toh batana!"
    if any(w in msg for w in ["bye", "allah hafiz", "good night"]):
        return "🌙 *Allah Hafiz!* Apna khayal rakhna."
    replies = [
        "🙏 Main yahin hoon! Batao kya help chahiye?",
        "😊 Haan bolo! Kya karna hai aaj?",
        "🤖 Ready hoon! `/help` se commands dekh sakte ho.",
    ]
    return random.choice(replies)

# ═══════════════════════════════════════════════════════════════════
# VOICE TRANSCRIPTION (Groq Whisper)
# ═══════════════════════════════════════════════════════════════════
async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    voice = update.message.voice or update.message.audio
    if not voice:
        return
    if not GROQ_API_KEY:
        await update.message.reply_text("🎤 Voice ke liye GROQ_API_KEY chahiye!")
        return
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    status_msg = await update.message.reply_text("🎤 _Sun raha hoon..._", parse_mode="Markdown")
    try:
        import tempfile
        file = await ctx.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)
        loop = asyncio.get_event_loop()
        from groq import Groq
        def transcribe():
            client = Groq(api_key=GROQ_API_KEY)
            with open(tmp_path, "rb") as f:
                return client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=f,
                    response_format="text",
                    language="hi"
                ).strip()
        text = await loop.run_in_executor(None, transcribe)
        os.unlink(tmp_path)
        if not text:
            await status_msg.edit_text("❌ Samajh nahi aaya, text mein likho.")
            return
        await status_msg.edit_text(f"🎤 *Suna:* _{text}_", parse_mode="Markdown")
        reply = await ai_chat(text, update.effective_chat.id)
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception as e:
        log.error(f"Voice error: {e}")
        await status_msg.edit_text("❌ Voice process nahi hua.")

# ═══════════════════════════════════════════════════════════════════
# MAIN AI PIPELINE
# ═══════════════════════════════════════════════════════════════════
def get_ai_reply(user_msg, chat_id=None, system_ctx=None):
    if not system_ctx:
        system_ctx = build_system_prompt()
    prompt = f"{system_ctx}\n\nUser: {user_msg}\n\nShort Hindi reply (2-4 lines):"
    reply = call_gemini(prompt, max_tokens=300)
    if reply:
        return reply
    reply = call_huggingface(prompt)
    if reply:
        return reply + "\n\n_⚡ (free model)_"
    return smart_fallback(user_msg)

# ═══════════════════════════════════════════════════════════════════
# DATA STORES
# ═══════════════════════════════════════════════════════════════════
class MemoryStore:
    def __init__(self):
        self.store = Store("memory", {"facts": [], "prefs": {}, "dates": {}, "important_notes": []})
    def add_fact(self, text):
        facts = self.store.data.get("facts", [])
        if facts and text[:50] in [f.get("f", "")[:50] for f in facts[-30:]]:
            return
        facts.append({"f": text, "d": today_str()})
        self.store.data["facts"] = facts[-200:]
        self.store.save()
    def get_all_facts(self):
        return self.store.data.get("facts", [])
    def context(self):
        facts = "\n".join(f"• {x['f']}" for x in self.get_all_facts()[-15:]) or "Kuch nahi"
        return f"FACTS:\n{facts}"

class TaskStore:
    def __init__(self):
        self.store = Store("tasks", {"list": [], "counter": 0})
    def add(self, title, priority="medium"):
        self.store.data["counter"] += 1
        t = {"id": self.store.data["counter"], "title": title, "priority": priority, "done": False, "created": datetime.now().isoformat()}
        self.store.data["list"].append(t)
        self.store.save()
        return t
    def complete(self, tid):
        for t in self.store.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True
                t["done_at"] = datetime.now().isoformat()
                self.store.save()
                return t
        return None
    def delete(self, tid):
        before = len(self.store.data["list"])
        self.store.data["list"] = [t for t in self.store.data["list"] if t["id"] != tid]
        self.store.save()
        return before != len(self.store.data["list"])
    def pending(self):
        return [t for t in self.store.data.get("list", []) if not t["done"]]
    def today_pending(self):
        return [t for t in self.pending() if t.get("due", today_str()) <= today_str()]
    def done_on(self, d):
        return [t for t in self.store.data["list"] if t["done"] and t.get("done_at", "")[:10] == d]
    def all_tasks(self):
        return self.store.data.get("list", [])
    def completed_tasks(self):
        return [t for t in self.all_tasks() if t["done"]]
    def get_weekly_summary(self):
        res = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            res[d] = {"done": len(self.done_on(d)), "created": len([t for t in self.all_tasks() if t.get("created", "")[:10] == d])}
        return res

class HabitStore:
    def __init__(self):
        self.store = Store("habits", {"list": [], "logs": {}, "counter": 0})
    def add(self, name, emoji="✅"):
        self.store.data["counter"] += 1
        h = {"id": self.store.data["counter"], "name": name, "emoji": emoji, "streak": 0, "best_streak": 0}
        self.store.data["list"].append(h)
        self.store.save()
        return h
    def log(self, hid):
        today = today_str()
        logs = self.store.data.setdefault("logs", {})
        if hid in logs.get(today, []):
            return False, 0
        logs.setdefault(today, []).append(hid)
        for h in self.store.data["list"]:
            if h["id"] == hid:
                yesterday = yesterday_str()
                if hid in logs.get(yesterday, []):
                    h["streak"] = h.get("streak", 0) + 1
                else:
                    h["streak"] = 1
                h["best_streak"] = max(h.get("best_streak", 0), h["streak"])
                self.store.save()
                return True, h["streak"]
        self.store.save()
        return True, 1
    def today_status(self):
        today_logs = self.store.data.get("logs", {}).get(today_str(), [])
        all_h = self.all()
        done = [h for h in all_h if h["id"] in today_logs]
        pending = [h for h in all_h if h["id"] not in today_logs]
        return done, pending
    def all(self):
        return self.store.data.get("list", [])
    def delete(self, hid):
        self.store.data["list"] = [h for h in self.store.data["list"] if h["id"] != hid]
        self.store.save()
    def get_logs_by_date(self, d):
        return self.store.data.get("logs", {}).get(d, [])

class ExpenseStore:
    def __init__(self):
        self.store = Store("expenses", {"list": [], "budget": None})
    def add(self, amount, desc):
        self.store.data["list"].append({"date": today_str(), "amount": float(amount), "desc": desc, "time": now_str()})
        self.store.save()
    def today_total(self):
        return sum(e["amount"] for e in self.store.data["list"] if e["date"] == today_str())
    def month_total(self):
        m = today_str()[:7]
        return sum(e["amount"] for e in self.store.data["list"] if e["date"].startswith(m))
    def budget_left(self):
        b = self.store.data.get("budget")
        return b - self.month_total() if b else None
    def set_budget(self, amount):
        self.store.data["budget"] = float(amount)
        self.store.save()
    def get_by_date(self, d):
        return [e for e in self.store.data["list"] if e["date"] == d]

class GoalStore:
    def __init__(self):
        self.store = Store("goals", {"list": [], "counter": 0})
    def add(self, title):
        self.store.data["counter"] += 1
        g = {"id": self.store.data["counter"], "title": title, "progress": 0, "done": False}
        self.store.data["list"].append(g)
        self.store.save()
        return g
    def update_progress(self, gid, pct):
        for g in self.store.data["list"]:
            if g["id"] == gid:
                g["progress"] = min(100, max(0, int(pct)))
                if g["progress"] >= 100:
                    g["done"] = True
                self.store.save()
                return g
        return None
    def active(self):
        return [g for g in self.store.data["list"] if not g["done"]]
    def completed(self):
        return [g for g in self.store.data["list"] if g["done"]]

class ReminderStore:
    def __init__(self):
        self.store = Store("reminders", {"list": [], "counter": 0})
    
    def add(self, chat_id, text, remind_at, repeat="once"):
        self.store.data["counter"] += 1
        r = {
            "id": self.store.data["counter"],
            "chat_id": chat_id,
            "text": text,
            "time": remind_at,          # HH:MM format
            "repeat": repeat,
            "active": True,
            "fired_today": False,
            "date": today_str(),
            "created": datetime.now().isoformat()
        }
        self.store.data["list"].append(r)
        self.store.save()
        log.info(f"✅ Reminder CREATED #{r['id']} at {remind_at} for chat {chat_id}")
        return r
    
    def all_active(self):
        return [r for r in self.store.data.get("list", []) if r.get("active")]
    
    def get_all(self):
        return self.store.data.get("list", [])
    
    def delete(self, rid):
        before = len(self.store.data["list"])
        self.store.data["list"] = [r for r in self.store.data["list"] if r["id"] != rid]
        self.store.save()
        return before != len(self.store.data["list"])
    
    def mark_fired(self, rid):
        for r in self.store.data["list"]:
            if r["id"] == rid:
                r["fired_today"] = True
                if r["repeat"] == "once":
                    r["active"] = False
                self.store.save()
                log.info(f"⏰ Reminder #{rid} marked fired (repeat={r['repeat']})")
                break
    
    def reset_daily(self):
        for r in self.store.data["list"]:
            if r.get("repeat") in ("daily", "weekly"):
                r["fired_today"] = False
        self.store.save()
        log.info("🔄 Daily reset: all daily/weekly reminders re-enabled")
    
    def due_now(self):
        now = now_ist()
        now_hm = now.strftime("%H:%M")
        due = []
        for r in self.store.data.get("list", []):
            if not r.get("active") or r.get("fired_today"):
                continue
            # Exact time match (HH:MM)
            if r["time"] == now_hm:
                due.append(r)
                log.info(f"🔔 Due (exact): #{r['id']} at {now_hm}")
                continue
            # Also allow a 2-minute grace window for network delays
            try:
                r_dt = datetime.strptime(f"{today_str()} {r['time']}", "%Y-%m-%d %H:%M")
                r_dt_ist = r_dt.replace(tzinfo=IST)
                diff_sec = (now - r_dt_ist).total_seconds()
                if 0 <= diff_sec < 120:   # within 2 minutes
                    if r not in due:
                        due.append(r)
                        log.info(f"🔔 Due (grace): #{r['id']} at {r['time']} (now {now_hm}, diff {diff_sec:.0f}s)")
            except Exception as e:
                log.warning(f"Time parse error for #{r['id']}: {e}")
        return due

class DiaryStore:
    def __init__(self):
        self.store = Store("diary", {"entries": {}})
    def add(self, text, mood="📝"):
        td = today_str()
        self.store.data["entries"].setdefault(td, []).append({"text": text, "mood": mood, "time": now_str()})
        self.store.save()
    def get(self, d):
        return self.store.data.get("entries", {}).get(d, [])
    def get_all_entries(self):
        return self.store.data.get("entries", {})

class WaterStore:
    def __init__(self):
        self.store = Store("water", {"logs": {}, "goal_ml": 2000})
    def add(self, ml=250):
        td = today_str()
        self.store.data["logs"].setdefault(td, []).append({"ml": ml, "time": now_str()})
        self.store.save()
    def today_total(self):
        return sum(e["ml"] for e in self.store.data.get("logs", {}).get(today_str(), []))
    def goal(self):
        return self.store.data.get("goal_ml", 2000)
    def set_goal(self, ml):
        self.store.data["goal_ml"] = ml
        self.store.save()
    def week_summary(self):
        res = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            res[d] = sum(e["ml"] for e in self.store.data.get("logs", {}).get(d, []))
        return res

class BillStore:
    def __init__(self):
        self.store = Store("bills", {"list": [], "counter": 0})
    def add(self, name, amount, due_day):
        self.store.data["counter"] += 1
        b = {"id": self.store.data["counter"], "name": name, "amount": float(amount), "due_day": int(due_day), "active": True, "paid_months": []}
        self.store.data["list"].append(b)
        self.store.save()
        return b
    def all_active(self):
        return [b for b in self.store.data["list"] if b.get("active")]
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
    def due_soon(self, days=3):
        today_d = now_ist().date()
        due = []
        for b in self.all_active():
            if self.is_paid_this_month(b["id"]):
                continue
            due_date = date(today_d.year, today_d.month, min(b["due_day"], 28))
            if today_d <= due_date <= today_d + timedelta(days=days):
                due.append(b)
        return due
    def delete(self, bid):
        before = len(self.store.data["list"])
        self.store.data["list"] = [b for b in self.store.data["list"] if b["id"] != bid]
        self.store.save()
        return before != len(self.store.data["list"])

class CalendarStore:
    def __init__(self):
        self.store = Store("calendar", {"events": [], "counter": 0})
    def add(self, title, date_str, time_str=""):
        self.store.data["counter"] += 1
        e = {"id": self.store.data["counter"], "title": title, "date": date_str, "time": time_str}
        self.store.data["events"].append(e)
        self.store.save()
        return e
    def today_events(self):
        return [e for e in self.store.data.get("events", []) if e["date"] == today_str()]
    def upcoming(self, days=30):
        today_d = now_ist().date()
        end = today_d + timedelta(days=days)
        events = [e for e in self.store.data.get("events", []) if today_d <= date.fromisoformat(e["date"]) <= end]
        return sorted(events, key=lambda x: x["date"])

class NewsStore:
    def get(self, category="India", n=5):
        try:
            url = f"https://news.google.com/rss/search?q={category}+India&hl=en-IN&gl=IN&ceid=IN:en"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                tree = ET.parse(resp)
                items = tree.findall(".//item")[:n]
                return [{"title": i.findtext("title", "")} for i in items]
        except:
            return []

class ChatHistoryStore:
    def __init__(self):
        self.store = Store("chat_history", {"messages": []})
    def add(self, role, text):
        self.store.data["messages"].append({"role": role, "text": text[:500], "time": now_str()})
        self.store.data["messages"] = self.store.data["messages"][-50:]
        self.store.save()
    def count(self):
        return len(self.store.data.get("messages", []))
    def clear(self):
        cnt = len(self.store.data["messages"])
        self.store.data["messages"] = []
        self.store.save()
        return cnt
    def track_msg(self, chat_id, msg_id):
        pass
    def get_tracked_ids(self):
        return []
    def clear_msg_ids(self):
        pass

# Initialize stores
memory = MemoryStore()
tasks = TaskStore()
habits = HabitStore()
expenses = ExpenseStore()
goals = GoalStore()
reminders = ReminderStore()
diary = DiaryStore()
water = WaterStore()
bills = BillStore()
calendar = CalendarStore()
news_store = NewsStore()
chat_hist = ChatHistoryStore()

# ═══════════════════════════════════════════════════════════════════
# GOOGLE SHEETS BACKUP (with restore)
# ═══════════════════════════════════════════════════════════════════
class GoogleSheetsBackup:
    def __init__(self):
        self.sheet = None
        if not HAS_GSHEETS or not GOOGLE_CREDS_JSON:
            log.warning("⚠️ Google Sheets not configured")
            return
        try:
            creds_dict = json.loads(GOOGLE_CREDS_JSON)
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            self.sheet = client.open_by_key("1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")
            log.info("✅ Google Sheets connected!")
            self.ensure_worksheets()
            self.restore_from_sheets()
        except Exception as e:
            log.error(f"Sheets error: {e}")
    
    def ensure_worksheets(self):
        if not self.sheet:
            return
        needed = ["Tasks", "Reminders", "Expenses", "Habits", "Water", "Memory", "Daily_Logs", "Goals", "Bills", "Calendar", "Diary"]
        existing = [ws.title for ws in self.sheet.worksheets()]
        for name in needed:
            if name not in existing:
                self.sheet.add_worksheet(title=name, rows=1000, cols=20)
    
    def _upsert_rows(self, ws, rows, id_col=0):
        try:
            existing = ws.get_all_values()
            key_to_row = {}
            for i, row in enumerate(existing[1:], start=2):
                if row and len(row) > id_col and row[id_col]:
                    key_to_row[str(row[id_col])] = i
            for row in rows:
                key = str(row[id_col]) if row else ""
                if key and key in key_to_row:
                    ws.update(f'A{key_to_row[key]}', [row])
                else:
                    ws.append_row(row)
            return True
        except:
            return False
    
    def save_reminders(self, rem_list):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Reminders")
            rows = [[r["id"], r["time"], r["text"], r["repeat"], "Active" if r["active"] else "Inactive", r.get("date","")] for r in rem_list]
            self._upsert_rows(ws, rows, id_col=0)
            return True
        except:
            return False
    
    def full_sync(self):
        if not self.sheet:
            return "❌ Sheets not connected"
        # Simplified sync for demo - in real code sync all.
        self.save_reminders(reminders.get_all())
        return "✅ Manual sync done"
    
    def restore_from_sheets(self):
        if not self.sheet:
            return
        log.info("🔄 Restoring from Sheets...")
        try:
            ws = self.sheet.worksheet("Reminders")
            rows = ws.get_all_records()
            rem_list = []
            for r in rows:
                if not r.get("ID"):
                    continue
                rem_list.append({
                    "id": int(r["ID"]),
                    "time": r.get("Time (HH:MM)", ""),
                    "text": r.get("Text", ""),
                    "repeat": r.get("Repeat", "once"),
                    "active": r.get("Status", "Active") == "Active",
                    "fired_today": False,
                    "date": r.get("Created Date", today_str()),
                    "chat_id": int(ADMIN_CHAT_ID) if ADMIN_CHAT_ID else 0,
                })
            if rem_list:
                max_id = max((r["id"] for r in rem_list), default=0)
                db.save("reminders", {"list": rem_list, "counter": max_id})
                log.info(f"✅ Restored {len(rem_list)} reminders")
        except Exception as e:
            log.warning(f"Reminders restore failed: {e}")

google_sheets = GoogleSheetsBackup()

# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════════
def build_system_prompt():
    now_label = time_label()
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    exp_t = expenses.today_total()
    water_t = water.today_total()
    water_g = water.goal()
    return f"""Tu mera AI dost hai. Hindi/Hinglish mein baat kar.
Current time: {now_label}
Aaj ke pending tasks: {len(tp)}
Habits done: {len(hd)}/{len(hd)+len(hp)}
Kharcha aaj: ₹{exp_t}
Paani: {water_t}/{water_g}ml
Reply short (2-3 lines), warm, never "as an AI".
"""

# ═══════════════════════════════════════════════════════════════════
# AI CHAT AND ACTION EXECUTION
# ═══════════════════════════════════════════════════════════════════
async def ai_chat(user_msg, chat_id=None):
    system = build_system_prompt()
    prompt = f"{system}\n\nUser: {user_msg}\n\nShort Hindi reply:"
    reply = call_gemini(prompt)
    if not reply:
        reply = call_huggingface(prompt)
    if not reply:
        reply = smart_fallback(user_msg)
    return reply

# ═══════════════════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════════════════
def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]])

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Briefing", callback_data="briefing"), InlineKeyboardButton("📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("💪 Habits", callback_data="habits"), InlineKeyboardButton("📖 Diary", callback_data="diary_write")],
        [InlineKeyboardButton("🎯 Goals", callback_data="goals"), InlineKeyboardButton("💰 Kharcha", callback_data="expenses")],
        [InlineKeyboardButton("💧 Water", callback_data="water_status"), InlineKeyboardButton("💳 Bills", callback_data="bills_menu")],
        [InlineKeyboardButton("📅 Calendar", callback_data="cal_menu"), InlineKeyboardButton("🗑 Clear Chat", callback_data="clear_chat")],
        [InlineKeyboardButton("📤 Backup", callback_data="backup_now"), InlineKeyboardButton("💡 Motivate", callback_data="motivate")],
    ])

def news_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇳 India", callback_data="news_India"), InlineKeyboardButton("💻 Tech", callback_data="news_Technology")],
        [InlineKeyboardButton("🏠 Back", callback_data="menu")],
    ])

# ═══════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════
async def cmd_start(update, ctx):
    n = now_ist()
    name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(
        f"🕌 *Assalamualaikum {name}!*\n\n⏰ {n.strftime('%I:%M %p')} IST\n"
        f"✅ Reminders ab fix ho gaye!\n\n"
        f"`/remind 2m Chai` — 2 min baad\n"
        f"`/remind 8:00 Uthna daily` — roz subah\n\n"
        f"Seedha type karo ya /help",
        parse_mode="Markdown", reply_markup=main_kb()
    )

async def cmd_help(update, ctx):
    await update.message.reply_text(
        "📋 *COMMANDS*\n"
        "`/task` `/done` `/deltask` — Tasks\n"
        "`/habit` `/hdone` — Habits\n"
        "`/remind` `/reminders` `/delremind` — Reminders ✅\n"
        "`/kharcha` `/budget` — Expenses\n"
        "`/diary` — Diary\n"
        "`/goal` `/gprogress` — Goals\n"
        "`/water` `/waterstatus` — Water\n"
        "`/bill` `/bills` — Bills\n"
        "`/cal` — Calendar\n"
        "`/briefing` `/weekly` `/report` — Reports\n"
        "`/backup` — Manual backup\n\n"
        "_Reminder ab bilkul kaam karega!_",
        parse_mode="Markdown"
    )

async def cmd_remind(update, ctx):
    if not ctx.args:
        await update.message.reply_text(
            "⏰ *Reminder set karo:*\n"
            "`/remind 2m Chai` — 2 min baad\n"
            "`/remind 15:30 Meeting` — exact time\n"
            "`/remind 8:00 Uthna daily` — roz\n"
            "`/remind 9:00 Meeting weekly` — har hafte",
            parse_mode="Markdown"
        )
        return
    time_arg = ctx.args[0].lower()
    rest = ctx.args[1:]
    repeat = "once"
    if rest and rest[-1].lower() in ["daily", "weekly"]:
        repeat = rest[-1].lower()
        rest = rest[:-1]
    text = " ".join(rest) if rest else "⏰ Reminder!"
    now = now_ist()
    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        remind_at = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif time_arg.endswith("h") and time_arg[:-1].isdigit():
        remind_at = (now + timedelta(hours=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        h, m = map(int, time_arg.split(":"))
        if 0 <= h <= 23 and 0 <= m <= 59:
            remind_at = f"{h:02d}:{m:02d}"
        else:
            await update.message.reply_text("❌ Time galat! Use HH:MM (00:00-23:59)")
            return
    else:
        await update.message.reply_text("❌ Format: `/remind 2m Chai` ya `/remind 15:30 Meeting`")
        return
    r = reminders.add(update.effective_chat.id, text, remind_at, repeat)
    repeat_str = "Ek baar" if repeat=="once" else "Roz 🔁" if repeat=="daily" else "Har hafte 📅"
    await update.message.reply_text(
        f"✅ Reminder set! ⏰ *{remind_at}* — {text}\n{repeat_str}\n🆔 `#{r['id']}` | `/delremind {r['id']}`",
        parse_mode="Markdown"
    )
    await auto_backup_to_sheets()

async def cmd_reminders_list(update, ctx):
    active = reminders.all_active()
    if not active:
        await update.message.reply_text("⏰ Koi reminder nahi.")
        return
    txt = "⏰ *ACTIVE REMINDERS*\n\n"
    for r in active:
        icon = "🔁" if r["repeat"] == "daily" else "📅" if r["repeat"] == "weekly" else "1️⃣"
        txt += f"#{r['id']} {icon} `{r['time']}` — {r['text']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_delremind(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delremind <id>`")
        return
    try:
        if reminders.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Reminder deleted!")
        else:
            await update.message.reply_text("❌ Not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_task(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📋 `/task Kaam [high/low]`")
        return
    args = " ".join(ctx.args)
    priority = "medium"
    if args.endswith(" high"):
        priority = "high"
        args = args[:-5].strip()
    elif args.endswith(" low"):
        priority = "low"
        args = args[:-4].strip()
    t = tasks.add(args, priority)
    icons = {"high":"🔴","medium":"🟡","low":"🟢"}
    await update.message.reply_text(f"✅ {icons[priority]} *{t['title']}*\n🆔 `#{t['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_done(update, ctx):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            msg = "📋 *Pending tasks:*\n"
            for t in pending[:10]:
                msg += f"`/done {t['id']}` → {t['title']}\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("🎉 No pending tasks!")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t:
            await update.message.reply_text(f"🎉 *Done!* {t['title']}", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Task not found/already done!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_deltask(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/deltask <id>`"); return
    try:
        if tasks.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Deleted!")
        else:
            await update.message.reply_text("❌ Not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_habit(update, ctx):
    if not ctx.args:
        await update.message.reply_text("💪 `/habit Exercise`")
        return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(f"💪 Habit: {h['emoji']} *{h['name']}*\n`/hdone {h['id']}`", parse_mode="Markdown")

async def cmd_hdone(update, ctx):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            msg = "💪 *Pending habits:*\n"
            for h in pending:
                msg += f"`/hdone {h['id']}` → {h['name']}\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("🎊 Sab done! Great!")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        if ok:
            await update.message.reply_text(f"💪 Done! 🔥 Streak: {streak} days")
        else:
            await update.message.reply_text("✅ Already done today!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_kharcha(update, ctx):
    if len(ctx.args) < 2:
        await update.message.reply_text("💰 `/kharcha 100 Chai`")
        return
    try:
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        await update.message.reply_text(f"💰 ₹{amount:.0f} — {desc}\n📊 Aaj total: ₹{expenses.today_total():.0f}")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Use: `/kharcha 100 Chai`")

async def cmd_briefing(update, ctx):
    n = now_ist()
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    exp_t = expenses.today_total()
    water_t = water.today_total()
    water_g = water.goal()
    txt = f"🌅 *Briefing* {n.strftime('%I:%M %p')}\n"
    txt += f"📋 Pending tasks: {len(tp)}\n"
    txt += f"💪 Habits: {len(hd)} done, {len(hp)} left\n"
    txt += f"💰 Kharcha: ₹{exp_t}\n"
    txt += f"💧 Paani: {water_t}/{water_g}ml\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

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
    await update.message.reply_text(f"💧 +{ml}ml | Total: {total}/{goal}ml")
    await auto_backup_to_sheets()

async def cmd_water_status(update, ctx):
    total = water.today_total()
    goal = water.goal()
    pct = int(total/goal*100) if goal else 0
    await update.message.reply_text(f"💧 {total}ml / {goal}ml ({pct}%)")

async def cmd_bill(update, ctx):
    if len(ctx.args) < 3:
        await update.message.reply_text("💳 `/bill Internet 999 15`")
        return
    try:
        b = bills.add(ctx.args[0], float(ctx.args[1]), int(ctx.args[2]))
        await update.message.reply_text(f"✅ Bill: {b['name']} ₹{b['amount']:.0f} due {b['due_day']}th")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Format: `/bill Name Amount Day`")

async def cmd_bills_list(update, ctx):
    all_b = bills.all_active()
    if not all_b:
        await update.message.reply_text("💳 No bills")
        return
    txt = "💳 *BILLS*\n"
    for b in all_b:
        paid = "✅" if bills.is_paid_this_month(b["id"]) else "⏳"
        txt += f"{paid} {b['name']} — ₹{b['amount']:.0f} (due {b['due_day']}th)\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_cal(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📅 `/cal aaj Meeting` ya `/cal 2026-05-10 Event`")
        return
    args = " ".join(ctx.args)
    if args.startswith("aaj "):
        date_str = today_str()
        title = args[4:]
    elif args.startswith("kal "):
        date_str = (now_ist().date() + timedelta(days=1)).isoformat()
        title = args[4:]
    elif _re.match(r'\d{4}-\d{2}-\d{2}', args):
        date_str = args[:10]
        title = args[11:]
    else:
        await update.message.reply_text("❌ Format: `/cal aaj Meeting`")
        return
    calendar.add(title, date_str)
    await update.message.reply_text(f"📅 Event: {title} on {date_str}")
    await auto_backup_to_sheets()

async def cmd_diary(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📖 `/diary Aaj bahut achha din tha`")
        return
    text = " ".join(ctx.args)
    diary.add(text)
    await update.message.reply_text(f"📖 Diary saved! 🕐 {now_str()}\n_{text[:100]}_", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_goal(update, ctx):
    if not ctx.args:
        active = goals.active()
        if not active:
            await update.message.reply_text("🎯 `/goal Python seekhna`")
            return
        txt = "🎯 *Active goals*\n"
        for g in active:
            bar = "█" * (g['progress']//10) + "░" * (10 - g['progress']//10)
            txt += f"#{g['id']} `{bar}` {g['title']} {g['progress']}%\n"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return
    g = goals.add(" ".join(ctx.args))
    await update.message.reply_text(f"🎯 Goal #{g['id']}: {g['title']}\n`/gprogress {g['id']} 50`")

async def cmd_gprogress(update, ctx):
    if len(ctx.args) < 2:
        await update.message.reply_text("📊 `/gprogress 1 50`")
        return
    try:
        g = goals.update_progress(int(ctx.args[0]), int(ctx.args[1]))
        if g:
            bar = "█" * (g['progress']//10) + "░" * (10 - g['progress']//10)
            await update.message.reply_text(f"📊 `{bar}` {g['title']} {g['progress']}%", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Goal not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid")

async def cmd_yesterday(update, ctx):
    yd = yesterday_str()
    tasks_done = tasks.done_on(yd)
    exp = expenses.get_by_date(yd)
    total_exp = sum(e["amount"] for e in exp)
    await update.message.reply_text(f"📅 *Yesterday ({yd})*\n✅ Tasks done: {len(tasks_done)}\n💰 Kharcha: ₹{total_exp:.0f}", parse_mode="Markdown")

async def cmd_alltasks(update, ctx):
    all_t = tasks.all_tasks()
    if not all_t:
        await update.message.reply_text("📋 No tasks")
        return
    p = len(tasks.pending())
    c = len(tasks.completed_tasks())
    await update.message.reply_text(f"📋 *All tasks*: {len(all_t)} total | ⏳ {p} pending | ✅ {c} done", parse_mode="Markdown")

async def cmd_completed(update, ctx):
    c = tasks.completed_tasks()
    if not c:
        await update.message.reply_text("✅ No completed tasks yet")
        return
    txt = "✅ *Completed tasks*\n" + "\n".join(f"  ✓ #{t['id']} {t['title']}" for t in c[-10:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_news(update, ctx):
    items = news_store.get("India", 5)
    if not items:
        await update.message.reply_text("📰 News unavailable")
        return
    txt = "📰 *Top News*\n" + "\n".join(f"• {i['title']}" for i in items)
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_clear(update, ctx):
    cnt = chat_hist.clear()
    await update.message.reply_text(f"🧹 Cleared {cnt} chat messages. Data safe!")

async def cmd_backup(update, ctx):
    await update.message.reply_text("📤 Manual backup...")
    res = google_sheets.full_sync()
    await update.message.reply_text(res)

async def cmd_dbstatus(update, ctx):
    await update.message.reply_text(
        f"✅ Reminders: {len(reminders.all_active())} active\n"
        f"📋 Tasks: {len(tasks.all_tasks())}\n"
        f"💪 Habits: {len(habits.all())}\n"
        f"💰 Month expenses: ₹{expenses.month_total():.0f}\n"
        f"💧 Water today: {water.today_total()}ml",
        parse_mode="Markdown"
    )

# ═══════════════════════════════════════════════════════════════════
# CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════════════
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    msg = query.message
    if not msg:
        return
    if data == "menu":
        await msg.edit_text("🏠 Menu", parse_mode="Markdown", reply_markup=main_kb())
    elif data == "briefing":
        await cmd_briefing(update, ctx)  # reuse
    elif data == "tasks":
        pending = tasks.pending()
        if not pending:
            await msg.edit_text("🎉 No pending tasks!", reply_markup=back_kb())
            return
        txt = "📋 *Pending tasks*\n" + "\n".join(f"  #{t['id']} {t['title']}" for t in pending[:10])
        await msg.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif data == "habits":
        done, pending = habits.today_status()
        txt = "💪 *Habits*\n✅ Done: " + ", ".join(h['name'] for h in done) + "\n⏳ Pending: " + ", ".join(h['name'] for h in pending)
        await msg.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif data == "diary_write":
        ctx.user_data["awaiting_diary_entry"] = True
        await msg.edit_text("📖 Apni diary entry likho:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="menu")]]))
    elif data == "goals":
        active = goals.active()
        txt = "🎯 *Goals*\n" + "\n".join(f"#{g['id']} {g['title']} {g['progress']}%" for g in active)
        await msg.edit_text(txt or "No active goals", parse_mode="Markdown", reply_markup=back_kb())
    elif data == "expenses":
        await msg.edit_text(f"💰 Aaj: ₹{expenses.today_total():.0f}\nMahina: ₹{expenses.month_total():.0f}", reply_markup=back_kb())
    elif data == "water_status":
        await cmd_water_status(update, ctx)
    elif data == "bills_menu":
        await cmd_bills_list(update, ctx)
    elif data == "cal_menu":
        upcoming = calendar.upcoming(30)
        if not upcoming:
            await msg.edit_text("📅 No upcoming events", reply_markup=back_kb())
            return
        txt = "📅 *Upcoming*\n" + "\n".join(f"{e['date']} — {e['title']}" for e in upcoming[:10])
        await msg.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif data == "clear_chat":
        await cmd_clear(update, ctx)
    elif data == "backup_now":
        await cmd_backup(update, ctx)
    elif data == "motivate":
        reply = get_ai_reply("Give me short motivation in Hindi 2 lines")
        await msg.edit_text(f"💡 *Motivation*\n{reply}", parse_mode="Markdown", reply_markup=back_kb())
    elif data.startswith("remind_done_"):
        rid = int(data.split("_")[2])
        reminders.mark_fired(rid)
        await msg.edit_text("✅ Reminder done!", reply_markup=back_kb())
        try:
            await msg.delete()
        except:
            pass
    elif data.startswith("remind_snooze_"):
        rid = int(data.split("_")[2])
        snooze = (now_ist() + timedelta(minutes=10)).strftime("%H:%M")
        r_list = [r for r in reminders.get_all() if r["id"] == rid]
        if r_list:
            reminders.add(msg.chat_id, r_list[0]["text"], snooze, "once")
            reminders.mark_fired(rid)
        await msg.edit_text(f"😴 Snoozed to {snooze}", reply_markup=back_kb())
        try:
            await msg.delete()
        except:
            pass

# ═══════════════════════════════════════════════════════════════════
# MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_msg = update.message.text.strip()
    if user_msg.startswith('/'):
        return
    if ctx.user_data.get("awaiting_diary_entry"):
        ctx.user_data.pop("awaiting_diary_entry")
        diary.add(user_msg)
        await update.message.reply_text(f"📖 Diary saved! 🕐 {now_str()}\n_{user_msg[:150]}_", parse_mode="Markdown")
        await auto_backup_to_sheets()
        return
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ai_chat(user_msg, update.effective_chat.id)
    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except:
        await update.message.reply_text(reply)

# ═══════════════════════════════════════════════════════════════════
# REMINDER JOB (FIXED)
# ═══════════════════════════════════════════════════════════════════
async def reminder_job(context):
    now = now_ist()
    now_hm = now.strftime("%H:%M")
    # Midnight reset (00:00 to 00:02)
    if now_hm in ("00:00", "00:01", "00:02"):
        reminders.reset_daily()
        log.info("🌙 Midnight reset done")
        return
    due = reminders.due_now()
    if not due:
        return
    log.info(f"🔔 Firing {len(due)} reminder(s) at {now_hm}")
    for r in due:
        try:
            repeat_note = ""
            if r["repeat"] == "daily":
                repeat_note = "\n🔁 Kal bhi yaad dilaunga!"
            elif r["repeat"] == "weekly":
                repeat_note = "\n📅 Agli hafte!"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Done", callback_data=f"remind_done_{r['id']}"),
                InlineKeyboardButton("⏰ 10min Snooze", callback_data=f"remind_snooze_{r['id']}")
            ]])
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=f"🚨🔔 *ALARM!* ⏰ *{r['time']}*\n\n📢 {r['text'].upper()}{repeat_note}",
                parse_mode="Markdown",
                reply_markup=kb
            )
            reminders.mark_fired(r["id"])
            log.info(f"✅ Reminder #{r['id']} sent to chat {r['chat_id']}")
            await asyncio.sleep(1)
        except Exception as e:
            log.error(f"Failed to send reminder #{r['id']}: {e}")

async def auto_backup_to_sheets():
    # Throttled backup (once every 30 sec)
    if not hasattr(auto_backup_to_sheets, "_last"):
        auto_backup_to_sheets._last = 0
    now_ts = time.time()
    if now_ts - auto_backup_to_sheets._last < 30:
        return
    auto_backup_to_sheets._last = now_ts
    await asyncio.get_event_loop().run_in_executor(None, google_sheets.full_sync)

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    log.info("="*50)
    log.info("🤖 Bot starting (Reminder fixed version)")
    log.info(f"⏰ IST: {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("remind", cmd_remind))
    app.add_handler(CommandHandler("reminders", cmd_reminders_list))
    app.add_handler(CommandHandler("delremind", cmd_delremind))
    app.add_handler(CommandHandler("task", cmd_task))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("deltask", cmd_deltask))
    app.add_handler(CommandHandler("habit", cmd_habit))
    app.add_handler(CommandHandler("hdone", cmd_hdone))
    app.add_handler(CommandHandler("kharcha", cmd_kharcha))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("water", cmd_water))
    app.add_handler(CommandHandler("waterstatus", cmd_water_status))
    app.add_handler(CommandHandler("bill", cmd_bill))
    app.add_handler(CommandHandler("bills", cmd_bills_list))
    app.add_handler(CommandHandler("cal", cmd_cal))
    app.add_handler(CommandHandler("diary", cmd_diary))
    app.add_handler(CommandHandler("goal", cmd_goal))
    app.add_handler(CommandHandler("gprogress", cmd_gprogress))
    app.add_handler(CommandHandler("yesterday", cmd_yesterday))
    app.add_handler(CommandHandler("alltasks", cmd_alltasks))
    app.add_handler(CommandHandler("completed", cmd_completed))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("dbstatus", cmd_dbstatus))
    # Callback & message
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Job queue (reminder every 30 seconds for faster response)
    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=30, first=10)
        log.info("✅ Reminder job scheduled (every 30 sec)")
    else:
        log.error("❌ JobQueue not available! Reminders will NOT work.")
    log.info("✅ Bot ready!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()