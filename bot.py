#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v20.0 100% WORKING                 ║
║  + ORIGINAL v10 ACTION SYSTEM (Gemini detection)               ║
║  + ALL FEATURES WORKING (Tasks/Reminders/Diary/Habits etc)     ║
║  + NO BUTTONS (only alarm Done/Snooze)                         ║
║  + DIARY AUTO-DELETE AFTER SAVE                                 ║
║  + CHAT LOGS → MISCELLANEOUS SHEET                             ║
║  + AUTO-BACKUP ON EVERY ACTION                                  ║
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
# 🔥 INDIAN STANDARD TIME (IST)
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
        self.use_mongo = False
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
                    data = json.load(f)
                    return data
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
# HUGGINGFACE FALLBACK
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
    msg = user_msg.lower()
    n = now_ist()
    
    if any(w in msg for w in ["time", "baje", "kitne baje", "time kya"]):
        return f"⏰ Abhi *{n.strftime('%I:%M %p')}* baj rahe hain (IST)"
    
    if any(w in msg for w in ["date", "aaj kya", "tarikh", "aaj kitni"]):
        return f"📅 Aaj *{n.strftime('%A, %d %B %Y')}* hai"
    
    if any(w in msg for w in ["hello", "hi", "assalam", "namaste", "hey"]):
        return "🕌 *Assalamualaikum!* Main aapka AI dost hoon. Batao kaisi help chahiye?"
    
    if any(w in msg for w in ["kaise ho", "how are", "kya haal"]):
        return "😊 *Main badiya hoon!* Aap sunao, kya ho raha hai aaj kal?"
    
    if any(w in msg for w in ["thank", "shukriya", "thanks"]):
        return "🤗 *Welcome!* Aur koi help chahiye toh batana!"
    
    if any(w in msg for w in ["bye", "allah hafiz", "good night", "shabba"]):
        return "🌙 *Allah Hafiz!* Apna khayal rakhna. Fir milenge!"
    
    if any(w in msg for w in ["help", "madad", "command", "kya kar"]):
        return ("📋 *COMMANDS*\n"
                "`/task` `/done` — Tasks\n"
                "`/habit` `/hdone` — Habits\n"
                "`/remind` — Reminders\n"
                "`/kharcha` — Expenses\n"
                "`/diary` — Diary\n"
                "`/remember` `/recall` — Memory\n"
                "`/news` — News\n"
                "`/briefing` — Daily summary\n"
                "`/report` — Date-wise report\n"
                "`/weekly` — Weekly report\n"
                "`/help` — Full list")
    
    replies = [
        "🙏 Abhi AI busy hai. Thodi der baad try karo ya `/help` use karo!",
        "😅 Model unavailable right now. Commands try karo: `/task` `/remind` `/help`",
        "🤖 Response nahi aa pa raha. Kuch commands use karo ya wait karo!",
    ]
    return random.choice(replies)

# ═══════════════════════════════════════════════════════════════════
# 🎤 VOICE TRANSCRIPTION (Groq Whisper)
# ═══════════════════════════════════════════════════════════════════
async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    if not GROQ_API_KEY:
        await update.message.reply_text(
            "🎤 *Voice ke liye GROQ_API_KEY chahiye!*\n\n"
            "1. groq.com pe free account banao\n"
            "2. API key lo\n"
            "3. GitHub repo → Settings → Secrets → `GROQ_API_KEY` add karo\n"
            "4. Bot restart karo\n\n"
            "_Free tier: 14,400 min/day — kaafi zyada!_",
            parse_mode="Markdown"
        )
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    status_msg = await update.message.reply_text("🎤 _Sun raha hoon..._", parse_mode="Markdown")

    try:
        import tempfile, os as _os

        file = await ctx.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _sync_transcribe, tmp_path)

        try:
            _os.unlink(tmp_path)
        except:
            pass

        if not text:
            await status_msg.edit_text(
                "❌ Samajh nahi aaya — thoda saaf bolke bhejna!\n_Ya text mein likh do._",
                parse_mode="Markdown"
            )
            return

        await status_msg.edit_text(f"🎤 *Suna:* _{text}_", parse_mode="Markdown")

        await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        reply = await ai_chat(text, update.effective_chat.id)

        try:
            await update.message.reply_text(reply, parse_mode="Markdown")
        except:
            await update.message.reply_text(reply)

    except Exception as e:
        log.error(f"Voice handler error: {e}")
        await status_msg.edit_text("❌ Voice process nahi hua. Text mein likh ke bhejo!")

def _sync_transcribe(file_path: str) -> str:
    if not GROQ_API_KEY:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        with open(file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=audio_file,
                response_format="text",
                language="hi",
            )
        text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
        if text:
            log.info(f"🎤 Transcribed: {text[:80]}")
            return text
    except Exception as e:
        log.warning(f"Groq transcription error: {e}")
    return None

# ═══════════════════════════════════════════════════════════════════
# MAIN AI PIPELINE
# ═══════════════════════════════════════════════════════════════════
def get_ai_reply(user_msg, chat_id=None, system_ctx=None):
    if not system_ctx:
        system_ctx = build_system_prompt()
    prompt = f"{system_ctx}\n\nUser: {user_msg}\n\nReply in Hindi/Hinglish (2-4 lines, warm & friendly):"
    
    reply = call_gemini(prompt)
    if reply:
        return reply
    
    reply = call_huggingface(prompt)
    if reply:
        return reply + "\n\n_⚡ (via free model)_"
    
    return smart_fallback(user_msg)

# ═══════════════════════════════════════════════════════════════════
# ALL DATA STORES (Original v10)
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
    
    def add_important(self, note):
        self.store.data.setdefault("important_notes", []).append({"note": note, "d": today_str()})
        self.store.save()
    
    def set_pref(self, k, v):
        self.store.data.setdefault("prefs", {})[k] = v
        self.store.save()
    
    def add_date(self, name, d):
        self.store.data.setdefault("dates", {})[name] = d
        self.store.save()
    
    def get_all_facts(self):
        return self.store.data.get("facts", [])
    
    def get_all_dates(self):
        return self.store.data.get("dates", {})
    
    def get_all_prefs(self):
        return self.store.data.get("prefs", {})
    
    def get_all_important(self):
        return self.store.data.get("important_notes", [])
    
    def context(self):
        facts = "\n".join(f"• {x['f']}" for x in self.get_all_facts()[-15:]) or "Kuch nahi"
        prefs = "\n".join(f"• {k}: {v}" for k, v in self.get_all_prefs().items()) or "Kuch nahi"
        dates = "\n".join(f"• {k}: {v}" for k, v in self.get_all_dates().items()) or "Kuch nahi"
        imp = "\n".join(f"⭐ {n['note']}" for n in self.get_all_important()[-5:]) or "Kuch nahi"
        return f"FACTS:\n{facts}\n\nPREFERENCES:\n{prefs}\n\nDATES:\n{dates}\n\nIMPORTANT:\n{imp}"


class TaskStore:
    def __init__(self):
        self.store = Store("tasks", {"list": [], "counter": 0})
    
    def _save(self):
        self.store.save()
    
    def add(self, title, priority="medium", due=None):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        t = {
            "id": self.store.data["counter"], "title": title,
            "priority": priority, "due": due or today_str(),
            "done": False, "done_at": None, "created": datetime.now().isoformat()
        }
        self.store.data["list"].append(t)
        self._save()
        return t
    
    def complete(self, tid):
        for t in self.store.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True
                t["done_at"] = datetime.now().isoformat()
                self._save()
                return t
        return None
    
    def delete(self, tid):
        self.store.data["list"] = [t for t in self.store.data["list"] if t["id"] != tid]
        self._save()
    
    def pending(self):
        return [t for t in self.store.data.get("list", []) if not t["done"]]
    
    def done_on(self, d):
        return [t for t in self.store.data.get("list", []) if t["done"] and (t.get("done_at", "") or "")[:10] == d]
    
    def today_pending(self):
        td = today_str()
        return [t for t in self.store.data.get("list", []) if not t["done"] and t.get("due", "") <= td]
    
    def all_tasks(self):
        return self.store.data.get("list", [])
    
    def completed_tasks(self):
        return [t for t in self.store.data.get("list", []) if t["done"]]
    
    def get_tasks_by_date(self, target_date):
        return [t for t in self.all_tasks() if t.get("created", "")[:10] == target_date or t.get("due", "") == target_date]
    
    def get_weekly_summary(self):
        result = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            result[d] = {
                "done": len(self.done_on(d)),
                "created": len([t for t in self.all_tasks() if t.get("created", "")[:10] == d])
            }
        return result
    
    def clear_done(self):
        before = len(self.store.data["list"])
        self.store.data["list"] = [t for t in self.store.data["list"] if not t["done"]]
        self._save()
        return before - len(self.store.data["list"])


class DiaryStore:
    def __init__(self):
        self.store = Store("diary", {"entries": {}})
    
    def add(self, text, mood="😊"):
        td = today_str()
        self.store.data.setdefault("entries", {}).setdefault(td, [])
        self.store.data["entries"][td].append({"text": text, "mood": mood, "time": now_str()})
        self.store.save()
    
    def get(self, d):
        return self.store.data.get("entries", {}).get(d, [])
    
    def get_all_entries(self):
        return self.store.data.get("entries", {})

    def get_by_date_range(self, start_date, end_date):
        result = {}
        current = start_date
        while current <= end_date:
            entries = self.get(current)
            if entries:
                result[current] = entries
            current = (datetime.strptime(current, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        return result


class HabitStore:
    def __init__(self):
        self.store = Store("habits", {"list": [], "logs": {}, "counter": 0})
    
    def add(self, name, emoji="✅"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        h = {"id": self.store.data["counter"], "name": name, "emoji": emoji, "streak": 0, "best_streak": 0, "created": today_str()}
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
        streak = next((h.get("streak", 1) for h in self.store.data["list"] if h["id"] == hid), 1)
        return True, streak
    
    def today_status(self):
        done_ids = self.store.data.get("logs", {}).get(today_str(), [])
        all_h = self.all()
        return ([h for h in all_h if h["id"] in done_ids], [h for h in all_h if h["id"] not in done_ids])
    
    def all(self):
        return self.store.data.get("list", [])
    
    def delete(self, hid):
        self.store.data["list"] = [h for h in self.store.data["list"] if h["id"] != hid]
        self.store.save()
    
    def get_streak_history(self, hid, days=30):
        logs = self.store.data.get("logs", {})
        result = {}
        for i in range(days):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            result[d] = hid in logs.get(d, [])
        return result
    
    def get_logs_by_date(self, target_date):
        return self.store.data.get("logs", {}).get(target_date, [])


class NotesStore:
    def __init__(self):
        self.store = Store("notes", {"list": [], "counter": 0})
    
    def add(self, content, tag="general"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        n = {"id": self.store.data["counter"], "text": content, "tag": tag, "created": datetime.now().isoformat()}
        self.store.data["list"].append(n)
        self.store.save()
        return n
    
    def delete(self, nid):
        self.store.data["list"] = [n for n in self.store.data["list"] if n["id"] != nid]
        self.store.save()
    
    def search(self, q):
        return [n for n in self.store.data.get("list", []) if q.lower() in n["text"].lower()]
    
    def recent(self, n=15):
        return self.store.data.get("list", [])[-n:]


class ExpenseStore:
    def __init__(self):
        self.store = Store("expenses", {"list": [], "counter": 0, "budget": {}})
    
    def add(self, amount, desc, category="general"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        self.store.data["list"].append({
            "id": self.store.data["counter"], "amount": amount,
            "desc": desc, "category": category, "date": today_str(), "time": now_str()
        })
        self.store.save()
    
    def set_budget(self, amount):
        self.store.data["budget"]["monthly"] = amount
        self.store.save()
    
    def today_total(self):
        td = today_str()
        return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date") == td)
    
    def month_total(self):
        m = today_str()[:7]
        return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date", "")[:7] == m)
    
    def today_list(self):
        td = today_str()
        return [e for e in self.store.data.get("list", []) if e.get("date") == td]
    
    def budget_left(self):
        b = self.store.data.get("budget", {}).get("monthly", 0)
        return b - self.month_total() if b else None
    
    def get_by_date(self, target_date):
        return [e for e in self.store.data.get("list", []) if e.get("date") == target_date]
    
    def get_monthly_summary(self, year_month):
        return [e for e in self.store.data.get("list", []) if e.get("date", "")[:7] == year_month]


class GoalStore:
    def __init__(self):
        self.store = Store("goals", {"list": [], "counter": 0})
    
    def add(self, title, deadline=None, why=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        g = {"id": self.store.data["counter"], "title": title, "deadline": deadline or "", "why": why, "progress": 0, "done": False, "created": today_str()}
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
    
    def get_by_id(self, gid):
        for g in self.store.data.get("list", []):
            if g["id"] == gid:
                return g
        return None


class ReminderStore:
    def __init__(self):
        self.store = Store("reminders", {"list": [], "counter": 0})
    
    def add(self, chat_id, text, remind_at, repeat="once"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        r = {
            "id": self.store.data["counter"], "chat_id": chat_id,
            "text": text, "time": remind_at, "repeat": repeat,
            "date": today_str(), "active": True, "fired_today": False,
            "created": datetime.now().isoformat()
        }
        self.store.data["list"].append(r)
        self.store.save()
        return r
    
    def all_active(self):
        return [r for r in self.store.data.get("list", []) if r.get("active")]
    
    def get_all(self):
        return self.store.data.get("list", [])
    
    def get_by_date(self, target_date):
        return [r for r in self.get_all() if r.get("date") == target_date]
    
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
                break
    
    def reset_daily(self):
        for r in self.store.data["list"]:
            r["fired_today"] = False
        self.store.save()
    
    def due_now(self):
        now = now_ist()
        now_hm = now.strftime("%H:%M")
        today = today_str()
        
        due = []
        for r in self.store.data.get("list", []):
            if not r.get("active") or r.get("fired_today"):
                continue
            
            r_time = r["time"]
            
            try:
                r_dt_str = f"{today} {r_time}"
                r_dt = datetime.strptime(r_dt_str, "%Y-%m-%d %H:%M")
                r_dt_ist = r_dt.replace(tzinfo=IST)
                diff_seconds = (now - r_dt_ist).total_seconds()
                if 0 <= diff_seconds < 90:
                    due.append(r)
                    continue
            except:
                pass
            
            if r_time == now_hm:
                if r not in due:
                    due.append(r)
        
        return due


class WaterStore:
    def __init__(self):
        self.store = Store("water", {"logs": {}, "goal_ml": 2000})
    
    def add(self, ml=250):
        td = today_str()
        self.store.data.setdefault("logs", {}).setdefault(td, [])
        self.store.data["logs"][td].append({"ml": ml, "time": now_str()})
        self.store.save()
    
    def today_total(self):
        return sum(e["ml"] for e in self.store.data.get("logs", {}).get(today_str(), []))
    
    def today_count(self):
        return len(self.store.data.get("logs", {}).get(today_str(), []))
    
    def goal(self):
        return self.store.data.get("goal_ml", 2000)
    
    def set_goal(self, ml):
        self.store.data["goal_ml"] = ml
        self.store.save()
    
    def today_entries(self):
        return self.store.data.get("logs", {}).get(today_str(), [])
    
    def get_by_date(self, target_date):
        return self.store.data.get("logs", {}).get(target_date, [])
    
    def week_summary(self):
        result = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            result[d] = sum(e["ml"] for e in self.store.data.get("logs", {}).get(d, []))
        return result


class BillStore:
    def __init__(self):
        self.store = Store("bills", {"list": [], "counter": 0})
    
    def add(self, name, amount, due_day, bill_type="bill"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        b = {"id": self.store.data["counter"], "name": name, "amount": amount, "due_day": due_day, "type": bill_type, "active": True, "paid_months": [], "created": today_str()}
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
        before = len(self.store.data["list"])
        self.store.data["list"] = [b for b in self.store.data["list"] if b["id"] != bid]
        self.store.save()
        return before != len(self.store.data["list"])
    
    def due_soon(self, days_ahead=3):
        today_d = now_ist().date()
        result = []
        for b in self.store.data.get("list", []):
            if not b.get("active") or self.is_paid_this_month(b["id"]):
                continue
            try:
                due_date = date(today_d.year, today_d.month, min(b["due_day"], 28))
            except:
                continue
            if today_d <= due_date <= today_d + timedelta(days=days_ahead):
                result.append({**b, "due_date": due_date.isoformat()})
        return result
    
    def month_total(self):
        return sum(b["amount"] for b in self.store.data.get("list", []) if b.get("active"))


class CalendarStore:
    def __init__(self):
        self.store = Store("calendar", {"events": [], "counter": 0})
    
    def add(self, title, event_date, event_time=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        e = {"id": self.store.data["counter"], "title": title, "date": event_date, "time": event_time, "created": today_str()}
        self.store.data["events"].append(e)
        self.store.save()
        return e
    
    def delete(self, eid):
        before = len(self.store.data["events"])
        self.store.data["events"] = [e for e in self.store.data["events"] if e["id"] != eid]
        self.store.save()
        return before != len(self.store.data["events"])
    
    def upcoming(self, days=7):
        today_d = now_ist().date()
        cutoff = today_d + timedelta(days=days)
        result = []
        for e in self.store.data.get("events", []):
            try:
                ed = date.fromisoformat(e["date"])
                if today_d <= ed <= cutoff:
                    result.append(e)
            except:
                pass
        return sorted(result, key=lambda x: x["date"])
    
    def today_events(self):
        return [e for e in self.store.data.get("events", []) if e["date"] == today_str()]
    
    def get_by_date(self, target_date):
        return [e for e in self.store.data.get("events", []) if e["date"] == target_date]


class NewsStore:
    def __init__(self):
        self.store = Store("news_cache", {"cache": {}, "updated": {}})
    
    def get(self, category="India", max_items=5):
        now_ts = time.time()
        cache = self.store.data
        if category in cache.get("cache", {}) and now_ts - cache.get("updated", {}).get(category, 0) < 1800:
            return cache["cache"][category][:max_items]
        feeds = {
            "India": "https://feeds.bbci.co.uk/hindi/rss.xml",
            "Technology": "https://feeds.feedburner.com/ndtvnews-tech-news",
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
                channel = root.find("channel")
                if channel is None:
                    channel = root
                for item in channel.findall("item")[:max_items]:
                    title = item.findtext("title", "").strip()
                    desc = item.findtext("description", "").strip()
                    if title:
                        items.append({"title": title, "desc": desc[:120] if desc else "", "link": "", "pub": ""})
        except Exception as e:
            items = [{"title": "News unavailable", "desc": str(e)[:100], "link": "", "pub": ""}]
        cache.setdefault("cache", {})[category] = items
        cache.setdefault("updated", {})[category] = now_ts
        self.store.save()
        return items


class ChatHistoryStore:
    def __init__(self):
        self.store = Store("chat_history", {"history": []})
    
    def add(self, role, content, user_name=""):
        self.store.data["history"].append({
            "timestamp": datetime.now().isoformat(),
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
# INIT ALL STORES
# ═══════════════════════════════════════════════════════════════════
memory = MemoryStore()
tasks = TaskStore()
diary = DiaryStore()
habits = HabitStore()
notes = NotesStore()
expenses = ExpenseStore()
goals = GoalStore()
reminders = ReminderStore()
water = WaterStore()
bills = BillStore()
calendar = CalendarStore()
news_store = NewsStore()
chat_hist = ChatHistoryStore()

# ═══════════════════════════════════════════════════════════════════
# ⭐ GOOGLE SHEETS BACKUP — EXACT HEADERS ⭐
# ═══════════════════════════════════════════════════════════════════

class GoogleSheetsBackup:
    def __init__(self):
        self.sheet = None
        if not HAS_GSHEETS:
            log.warning("⚠️ gspread not installed!")
            return
        
        creds_json = GOOGLE_CREDS_JSON
        
        if not creds_json:
            log.warning("⚠️ GOOGLE_CREDS_JSON not found! Backup disabled.")
            return
        
        try:
            creds_dict = json.loads(creds_json)
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
            log.error(f"❌ Google Sheets connection error: {e}")
    
    def ensure_worksheets(self):
        if not self.sheet:
            return
        
        sheet_configs = {
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
        
        existing_ws = {ws.title: ws for ws in self.sheet.worksheets()}
        
        for name, headers in sheet_configs.items():
            if name not in existing_ws:
                try:
                    ws = self.sheet.add_worksheet(title=name, rows=1000, cols=len(headers))
                    ws.update('A1', [headers])
                    log.info(f"📊 Created sheet: {name}")
                except Exception as e:
                    log.warning(f"Could not create {name}: {e}")

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
            log.error(f"Upsert error: {e}")

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
            log.error(f"Append error: {e}")

    def save_tasks(self):
        try:
            ws = self.sheet.worksheet("Tasks")
            rows = []
            for t in tasks.all_tasks():
                rows.append([
                    str(t.get("id","")),
                    t.get("title",""),
                    t.get("priority","medium"),
                    "Done" if t.get("done") else "Pending",
                    t.get("created","")[:10] if t.get("created") else "",
                    t.get("done_at","")[:10] if t.get("done_at") else "",
                    t.get("due",""),
                    t.get("tags","")
                ])
            if rows:
                self._upsert_by_id(ws, rows, 0)
            return True
        except:
            return False

    def save_reminders(self):
        try:
            ws = self.sheet.worksheet("Reminders")
            rows = []
            for r in reminders.get_all():
                rows.append([
                    str(r.get("id","")),
                    r.get("time",""),
                    r.get("text",""),
                    r.get("repeat","once"),
                    "Active" if r.get("active") else "Inactive",
                    r.get("date",""),
                    str(r.get("chat_id","")),
                    r.get("last_fired",""),
                    r.get("remarks","")
                ])
            if rows:
                self._upsert_by_id(ws, rows, 0)
            return True
        except:
            return False

    def save_expenses(self):
        try:
            ws = self.sheet.worksheet("Expenses")
            rows = []
            for e in expenses.store.data.get("list", []):
                rows.append([
                    e.get("date",""),
                    e.get("amount",0),
                    e.get("desc",""),
                    e.get("category","general"),
                    e.get("time","")
                ])
            if rows:
                self._append_unique(ws, rows, [0, 1, 2])
            return True
        except:
            return False

    def save_habits(self):
        try:
            ws = self.sheet.worksheet("Habits")
            rows = []
            for h in habits.all():
                rows.append([
                    str(h.get("id","")),
                    h.get("name",""),
                    h.get("emoji","✅"),
                    h.get("streak",0),
                    h.get("best_streak",0),
                    h.get("created",""),
                    h.get("target","")
                ])
            if rows:
                self._upsert_by_id(ws, rows, 0)
            return True
        except:
            return False

    def save_memory(self):
        try:
            ws = self.sheet.worksheet("Memory / Important Notes")
            rows = []
            for f in memory.get_all_facts():
                rows.append([f.get("d",""), "Fact", f.get("f",""), "", "Medium"])
            if rows:
                self._append_unique(ws, rows, [0, 2])
            return True
        except:
            return False

    def save_goals(self):
        try:
            ws = self.sheet.worksheet("Goals")
            rows = []
            for g in goals.active() + goals.completed():
                rows.append([
                    str(g.get("id","")),
                    g.get("title",""),
                    g.get("progress",0),
                    "Done" if g.get("done") else "Active",
                    g.get("deadline",""),
                    g.get("created",""),
                    g.get("milestones","")
                ])
            if rows:
                self._upsert_by_id(ws, rows, 0)
            return True
        except:
            return False

    def save_bills(self):
        try:
            ws = self.sheet.worksheet("Bills & Subscriptions")
            rows = []
            for b in bills.all_active():
                rows.append([
                    str(b.get("id","")),
                    b.get("name",""),
                    b.get("amount",0),
                    str(b.get("due_day","")),
                    b.get("auto_pay","No"),
                    "Paid" if bills.is_paid_this_month(b["id"]) else "Pending",
                    b.get("payment_method",""),
                    b.get("notes","")
                ])
            if rows:
                self._upsert_by_id(ws, rows, 0)
            return True
        except:
            return False

    def save_calendar(self):
        try:
            ws = self.sheet.worksheet("Calendar Events")
            rows = []
            for e in calendar.store.data.get("events", []):
                rows.append([
                    e.get("date",""),
                    e.get("time",""),
                    e.get("title",""),
                    e.get("location",""),
                    e.get("reminder_set","Yes"),
                    e.get("participants",""),
                    e.get("notes","")
                ])
            if rows:
                self._append_unique(ws, rows, [0, 2])
            return True
        except:
            return False

    def save_water(self):
        try:
            ws = self.sheet.worksheet("Water Intake")
            goal = water.goal()
            week = water.week_summary()
            rows = []
            for d, total_ml in sorted(week.items()):
                pct = int(total_ml / goal * 100) if goal else 0
                glasses = total_ml // 250
                rows.append([d, total_ml, goal, f"{pct}%", glasses, ""])
            if rows:
                self._upsert_by_id(ws, rows, 0)
            return True
        except:
            return False

    def save_daily_log(self):
        try:
            ws = self.sheet.worksheet("Daily_Logs")
            today = today_str()
            row = [today, len(tasks.done_on(today)), len(tasks.today_pending()),
                   expenses.today_total(), len(reminders.all_active()),
                   len(habits.today_status()[0]), water.today_total(), "", ""]
            all_vals = ws.get_all_values()
            found = False
            for i, r in enumerate(all_vals):
                if r and r[0] == today:
                    ws.update(f'A{i+1}:I{i+1}', [row])
                    found = True
                    break
            if not found:
                ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except:
            return False

    def save_diary(self):
        try:
            ws = self.sheet.worksheet("Diary")
            existing = ws.get_all_values()
            existing_keys = set()
            for row in existing[1:]:
                if row and row[0]:
                    existing_keys.add(f"{row[0]}|{row[1] if len(row)>1 else ''}|{row[2][:50] if len(row)>2 else ''}")
            
            new_rows = []
            for entry_date in sorted(diary.get_all_entries().keys()):
                for entry in diary.get_all_entries()[entry_date]:
                    key = f"{entry_date}|{entry.get('time','')}|{entry.get('text','')[:50]}"
                    if key not in existing_keys:
                        new_rows.append([entry_date, entry.get("time",""), entry.get("text",""), entry.get("mood","📝")])
                        existing_keys.add(key)
            
            for row in new_rows:
                ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except:
            return False

    # 🔥 CHAT HISTORY SAVE TO MISCELLANEOUS
    def save_chat_history(self):
        try:
            ws = self.sheet.worksheet("Miscellaneous")
            existing = ws.get_all_values()
            existing_keys = set()
            for row in existing[1:]:
                if row and row[0]:
                    existing_keys.add(f"{row[0]}|{row[2]}|{row[4][:50] if len(row)>4 else ''}")
            
            new_rows = []
            for h in chat_hist.get_all()[-50:]:
                key = f"{h.get('timestamp','')}|{h.get('role','')}|{h.get('message','')[:50]}"
                if key not in existing_keys:
                    new_rows.append([
                        h.get("timestamp",""),
                        h.get("date",""),
                        h.get("role",""),
                        h.get("user",""),
                        h.get("message","")
                    ])
                    existing_keys.add(key)
            
            for row in new_rows:
                ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except:
            return False

    def full_sync(self):
        if not self.sheet:
            return "❌ Sheets not connected!"
        
        success_count = 0
        errors = []

        ops = [
            ("Tasks",     self.save_tasks),
            ("Reminders", self.save_reminders),
            ("Expenses",  self.save_expenses),
            ("Habits",    self.save_habits),
            ("Memory",    self.save_memory),
            ("Goals",     self.save_goals),
            ("Bills",     self.save_bills),
            ("Calendar",  self.save_calendar),
            ("Water",     self.save_water),
            ("Daily_Log", self.save_daily_log),
            ("Diary",     self.save_diary),
            ("Chat",      self.save_chat_history),
        ]

        for name, fn in ops:
            try:
                if fn():
                    success_count += 1
                else:
                    errors.append(name)
            except Exception as e:
                log.error(f"Sync error [{name}]: {e}")
                errors.append(name)

        if errors:
            return f"⚠️ Synced {success_count}/{len(ops)} | Failed: {', '.join(errors)}"
        return f"✅ Synced {success_count}/{len(ops)} sheets to Google Sheets!"

google_sheets = GoogleSheetsBackup()

# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════════
def build_system_prompt():
    now_label = time_label()
    current_time = now_str()
    tp = tasks.today_pending()
    yd = tasks.done_on(yesterday_str())
    hd, hp = habits.today_status()
    ag = goals.active()
    td_d = diary.get(today_str())
    exp_t = expenses.today_total()
    exp_m = expenses.month_total()
    bl = expenses.budget_left()
    water_today = water.today_total()
    water_goal = water.goal()
    due_b = bills.due_soon(3)
    cal_today = calendar.today_events()

    tasks_s = "\n".join(f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}" for t in tp[:5]) or "  Koi nahi"
    yd_s = "\n".join(f"  ✓ {t['title']}" for t in yd[:3]) or "  Koi nahi"
    h_done = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    h_pend = ", ".join(f"{h['name']}" for h in hp) or "Sab ho gaye!"
    goals_s = "\n".join(f"  🎯 {g['title']} ({g['progress']}%)" for g in ag[:4]) or "  Koi nahi"
    diary_s = "\n".join(f"  {e['time']} {e['text']}" for e in td_d[-2:]) or "  Kuch nahi"
    budget_s = f"Budget baaki: ₹{bl:.0f}" if bl is not None else ""
    water_pct = int(water_today / water_goal * 100) if water_goal else 0
    bills_s = "\n".join(f"  ⚠️ {b['name']} ₹{b['amount']:.0f}" for b in due_b) or "  Koi nahi"
    cal_s = "\n".join(f"  📅 {e['time'] or ''} {e['title']}" for e in cal_today) or "  Koi nahi"

    return f"""Tu mera Personal AI Assistant hai — naam 'Dost'. Hamesha Hindi/Hinglish mein baat kar. Bilkul close dost jaisa — warm, real, helpful.

⚠️ CRITICAL REAL TIME: {now_label} ({current_time})
• Aaj ki date: {today_str()}
• Jab koi time puche — YEHI BATANA. Kabhi guess mat karna.

📋 AAJ KE TASKS ({len(tp)}):
{tasks_s}

✅ KAL KYA KIYA ({len(yd)}):
{yd_s}

💪 HABITS: Done: {h_done} | Baaki: {h_pend}

📖 DIARY (aaj):
{diary_s}

💰 KHARCHA: Aaj ₹{exp_t} | Mahina ₹{exp_m} {budget_s}

🎯 GOALS ({len(ag)}):
{goals_s}

💧 PAANI: {water_today}ml/{water_goal}ml ({water_pct}%)

📅 AAJ KE EVENTS:
{cal_s}

💳 BILLS DUE:
{bills_s}

🧠 YAADDASHT:
{memory.context()}

RULES:
- Dost ki tarah baat kar — "As an AI" kabhi mat bol
- Hindi/Hinglish mein jawab de, SHORT (2-4 lines)
- TIME PUCHNE PE EXACT TIME BATANA jo upar likha hai
- Jo yaad hai naturally use kar
"""

# ═══════════════════════════════════════════════════════════════════
# SMART AUTO-SAVE
# ═══════════════════════════════════════════════════════════════════
def auto_extract_facts(text):
    lower = text.lower()
    triggers = [
        "yaad rakh", "remember", "mera naam", "meri umar", "main rehta",
        "mujhe pasand", "meri job", "mera kaam", "mere bhai", "meri behen",
        "meri wife", "mere husband", "mera", "meri", "main hoon",
        "birthday", "anniversary", "deadline", "important date"
    ]
    if any(kw in lower for kw in triggers):
        memory.add_fact(text[:250])
        return True
    return False

# ═══════════════════════════════════════════════════════════════════
# SMART ACTION SYSTEM (Gemini → Regex Fallback)
# ═══════════════════════════════════════════════════════════════════

ACTION_SYSTEM_PROMPT = """You are a JSON router. Parse user message and return ONLY raw JSON (no markdown, no backticks).

Current EXACT time: {now}
24hr time: {current_time}
Today: {today}
2 min from now: {two_min}

JSON format: {{"action":"ACTION","params":{{...}},"reply":"confirm msg"}}

ACTIONS:
REMIND — {{"time":"HH:MM","text":"...","repeat":"once"}} (USE provided times, never calculate)
ADD_TASK — {{"title":"...","priority":"high/medium/low"}}
ADD_EXPENSE — {{"amount":number,"desc":"...","category":"..."}}
ADD_DIARY — {{"text":"...","mood":"😊"}}
ADD_MEMORY — {{"fact":"..."}}
ADD_HABIT — {{"name":"...","emoji":"💪"}}
COMPLETE_TASK — {{"title_hint":"..."}}
SHOW_TASKS — {{}}
SHOW_ALL_TASKS — {{}}
SHOW_COMPLETED_TASKS — {{}}
SHOW_REMINDERS — {{}}
CHAT — {{}} (default)
"""

def _regex_fallback(user_msg):
    lower = user_msg.lower()
    now = now_ist()
    
    remind_words = ["alarm", "reminder", "yaad dila", "remind", "notify", "minute baad", "min baad", "ghante baad", "baje"]
    if any(w in lower for w in remind_words):
        time_str = None
        m = _re.search(r'(\d+)\s*(?:minute|min|mins)', lower)
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
            m = _re.search(r'(\d{1,2})\s*(?:baje|baj)', lower)
            if m:
                h = int(m.group(1))
                if 'raat' in lower or 'sham' in lower:
                    h = h + 12 if h < 12 else h
                elif 'subah' in lower:
                    h = h if h < 12 else h - 12
                else:
                    h = h + 12 if 1 <= h <= 6 else h
                time_str = f"{h:02d}:00"
        if time_str:
            text = _re.sub(r'\d+\s*(?:minute|min|mins|ghante|ghanta|hour|hr)', '', user_msg, flags=_re.I)
            text = _re.sub(r'\d{1,2}(?::\d{2})?\s*(?:baje|baj)?', '', text, flags=_re.I)
            text = _re.sub(r'(?:alarm|reminder|yaad dila|remind|laga do|set karo|baad|notify)\s*', '', text, flags=_re.I).strip()
            return {"action": "REMIND", "params": {"time": time_str, "text": text or "⏰ Reminder!", "repeat": "once"}, "reply": ""}
    
    if any(w in lower for w in ["karna hai", "task add", "kaam add", "to-do", "todo", "schedule"]):
        return {"action": "ADD_TASK", "params": {"title": user_msg[:80], "priority": "medium"}, "reply": ""}
    
    if any(w in lower for w in ["rs ", "rupaye", "kharcha", "spend", "lage", "diye"]):
        m = _re.search(r'(\d+)', lower)
        amount = float(m.group(1)) if m else 0
        if amount > 0:
            return {"action": "ADD_EXPENSE", "params": {"amount": amount, "desc": user_msg[:60], "category": "general"}, "reply": ""}
    
    return {"action": "CHAT", "params": {}, "reply": ""}

def call_gemini_action(user_msg, now_label, today_label):
    now = now_ist()
    two_min = (now + timedelta(minutes=2)).strftime("%H:%M")
    current_time = now.strftime("%H:%M")
    prompt = ACTION_SYSTEM_PROMPT.format(now=now_label, current_time=current_time, today=today_label, two_min=two_min)
    full_msg = f"{prompt}\n\nUser: {user_msg}"

    payload = json.dumps({"contents": [{"role": "user", "parts": [{"text": full_msg}]}], "generationConfig": {"temperature": 0.0, "maxOutputTokens": 200}}).encode("utf-8")

    for model in ["gemini-2.5-flash-lite", "gemini-2.5-flash"]:
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
                log.info(f"✅ Action: {parsed.get('action')} via {model}")
                return parsed
        except Exception as e:
            log.warning(f"Action fail ({model}): {e}")
            continue

    return _regex_fallback(user_msg)

async def execute_action(action_data, chat_id, user_msg):
    action = action_data.get("action", "CHAT")
    params = action_data.get("params", {})
    now = now_ist()

    if action == "REMIND":
        time_str = params.get("time", "")
        text = params.get("text", "⏰ Reminder!")
        repeat = params.get("repeat", "once")
        if not time_str or not _re.match(r'^\d{2}:\d{2}$', time_str):
            return f"⏰ Time format galat! Abhi *{now.strftime('%H:%M')}* hue hain. HH:MM use karo."
        r = reminders.add(chat_id, text, time_str, repeat)
        rl = {"once": "Ek baar", "daily": "Roz 🔁", "weekly": "Har hafte 📅"}.get(repeat, repeat)
        return f"✅ Reminder set! ⏰ *{time_str}* — {text}\n{rl}\n🆔 `#{r['id']}` | `/delremind {r['id']}`"

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
        diary_text = params.get("text", user_msg[:100])
        diary.add(diary_text, params.get("mood", "😊"))
        # 🔥 DELETE user message + confirmation
        return f"📖 Diary saved! 🕐 {now_str()}"

    elif action == "ADD_MEMORY":
        memory.add_fact(params.get("fact", user_msg[:200]))
        return f"🧠 Yaad kar liya! ✅"

    elif action == "ADD_HABIT":
        h = habits.add(params.get("name", user_msg[:50]), params.get("emoji", "✅"))
        return f"💪 Habit: {h['emoji']} *{h['name']}*\n`/hdone {h['id']}`"

    elif action == "COMPLETE_TASK":
        hint = params.get("title_hint", "").lower()
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
            return f"✅ *{matched['title']}* — done! 🎉"
        return "❓ Kaunsa task? ID ya naam batao."

    elif action == "SHOW_TASKS":
        pending = tasks.today_pending()
        if not pending:
            return "🎉 No pending tasks!"
        txt = f"📋 *PENDING ({len(pending)})*\n\n"
        for t in pending[:8]:
            txt += f"{'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} *#{t['id']}* {t['title']}\n"
        return txt

    elif action == "SHOW_ALL_TASKS":
        all_t = tasks.all_tasks()
        if not all_t:
            return "📋 No tasks!"
        p = tasks.pending()
        c = tasks.completed_tasks()
        txt = f"📋 *ALL ({len(all_t)})*\n⏳{len(p)} pending | ✅{len(c)} done\n\n"
        if p:
            txt += "⏳ " + ", ".join(f"#{t['id']} {t['title'][:20]}" for t in p[:5])
        if c:
            txt += "\n✅ " + ", ".join(f"#{t['id']} {t['title'][:20]}" for t in c[-5:])
        return txt

    elif action == "SHOW_COMPLETED_TASKS":
        c = tasks.completed_tasks()
        if not c:
            return "✅ No completed tasks yet!"
        txt = f"✅ *COMPLETED ({len(c)})*\n\n" + "".join(f"  ✓ #{t['id']} {t['title']}\n" for t in c[-10:])
        return txt

    elif action == "SHOW_REMINDERS":
        active = reminders.all_active()
        if not active:
            return f"⏰ No reminders!\n`/remind 30m Kaam` se set karo"
        txt = f"⏰ *REMINDERS ({len(active)})*\n\n"
        for r in active:
            icon = "🔁" if r["repeat"] == "daily" else "📅" if r["repeat"] == "weekly" else "1️⃣"
            txt += f"*#{r['id']}* {icon} `{r['time']}` — {r['text']} {'✅' if r['fired_today'] else '⏳'}\n"
        return txt

    else:
        auto_extract_facts(user_msg)
        chat_hist.add("user", user_msg)
        reply = call_gemini(build_system_prompt() + "\n\nUser: " + user_msg + "\n\nShort Hindi reply:")
        if not reply:
            reply = call_huggingface(build_system_prompt() + "\n\nUser: " + user_msg + "\n\nShort Hindi reply:")
            if reply:
                reply += "\n_⚡ (free model)_"
        if not reply:
            reply = smart_fallback(user_msg)
        chat_hist.add("assistant", reply)
        return reply

async def ai_chat(user_msg, chat_id=None):
    now_label = time_label()
    today_label = today_str()
    if chat_id:
        action_data = call_gemini_action(user_msg, now_label, today_label)
        return await execute_action(action_data, chat_id, user_msg)
    else:
        reply = get_ai_reply(user_msg)
        chat_hist.add("user", user_msg)
        chat_hist.add("assistant", reply)
        return reply

# ═══════════════════════════════════════════════════════════════════
# COMMAND HANDLERS (ZERO BUTTONS)
# ═══════════════════════════════════════════════════════════════════
async def cmd_start(update, ctx):
    n = now_ist()
    name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(
        f"🕌 *Assalamualaikum {name}!* 🥰\n\n"
        f"⏰ {n.strftime('%I:%M %p')} IST | 📅 {n.strftime('%d %b %Y')}\n\n"
        f"Main aapka AI dost hoon! Jo marzi likho, main jawab dunga.\n\n"
        f"📋 *Commands use kar sakte ho:*\n"
        f"`/task` — Task add karo\n"
        f"`/done` — Task complete karo\n"
        f"`/habit` — Habit add karo\n"
        f"`/hdone` — Habit done mark karo\n"
        f"`/remind` — Reminder set karo\n"
        f"`/kharcha` — Expense add karo\n"
        f"`/diary` — Diary likho (text ke saath)\n"
        f"`/diary` — Diary dekho (bina text, password: Rk1996)\n"
        f"`/news` — News padho\n"
        f"`/water` — Paani log karo\n"
        f"`/briefing` — Aaj ka summary\n"
        f"`/report YYYY-MM-DD` — Date-wise report\n"
        f"`/weekly` — Weekly report\n"
        f"`/help` — Poori list\n\n"
        f"_Seedha type karo, main samjhunga!_ 👇",
        parse_mode="Markdown"
    )

async def cmd_help(update, ctx):
    await update.message.reply_text(
        "📋 *COMMANDS*\n\n"
        "**📝 TASKS & HABITS**\n"
        "`/task` `/done` `/deltask` — Tasks\n"
        "`/habit` `/hdone` `/delhabit` — Habits\n\n"
        "**📖 JOURNAL**\n"
        "`/diary` — Diary\n"
        "`/remember` `/recall` — Memory\n"
        "`/note` `/delnote` — Notes\n\n"
        "**💰 FINANCE**\n"
        "`/kharcha` `/budget` — Expenses\n"
        "`/bill` `/bills` `/billpaid` `/delbill` — Bills\n\n"
        "**⏰ REMINDERS & CALENDAR**\n"
        "`/remind` `/reminders` `/delremind` — Reminders\n"
        "`/cal` `/calendar` `/delcal` — Calendar\n\n"
        "**💪 HEALTH**\n"
        "`/water` `/waterstatus` `/watergoal` — Water intake\n\n"
        "**📊 REPORTS**\n"
        "`/report YYYY-MM-DD` — Date-wise report\n"
        "`/weekly` — Weekly summary\n"
        "`/briefing` — Daily briefing\n"
        "`/alltasks` `/completed` — Task views\n"
        "`/yesterday` — Yesterday's summary\n\n"
        "**🎯 GOALS**\n"
        "`/goal` `/gprogress` — Goals\n\n"
        "**📰 NEWS**\n"
        "`/news` — News\n\n"
        "**🔧 UTILITIES**\n"
        "`/clear` — Cleanup\n"
        "`/backup` — Manual backup to Google Sheets\n\n"
        "_Seedha type karo — AI jawab dega!_",
        parse_mode="Markdown"
    )

async def cmd_task(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📋 `/task Kaam [high/low]`")
        return
    args = " ".join(ctx.args)
    priority = "medium"
    if args.endswith(" high"):
        priority = "high"; args = args[:-5].strip()
    elif args.endswith(" low"):
        priority = "low"; args = args[:-4].strip()
    t = tasks.add(args, priority)
    e = "🔴" if priority == "high" else "🟡" if priority == "medium" else "🟢"
    await update.message.reply_text(f"✅ {e} *{t['title']}*\n🆔 `#{t['id']}`", parse_mode="Markdown")
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
            await update.message.reply_text("❌ Task not found or already done!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID! Use `/done` to see pending tasks.")

async def cmd_deltask(update, ctx):
    if not ctx.args: await update.message.reply_text("`/deltask <id>`"); return
    try:
        tasks.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Deleted!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

# ═══════════════════════════════════════════════════════════════════
# 🔥 DIARY — FIXED: View=Password, Write=Save+Delete
# ═══════════════════════════════════════════════════════════════════
async def cmd_diary(update, ctx):
    args = ctx.args

    # Write mode: /diary some text
    if args and args[0] not in ("date", "all", "week"):
        text = " ".join(args)
        diary.add(text, mood="📝")
        
        # 🔥 DELETE user message
        try:
            await update.message.delete()
        except:
            pass
        
        # Send confirmation
        sent = await update.message.reply_text(
            f"📖 *Diary saved!* 🕐 {now_str()}\n\n_{text[:150]}_",
            parse_mode="Markdown"
        )
        
        # Auto-backup
        await auto_backup_to_sheets()
        
        # Delete confirmation after 3 seconds
        await asyncio.sleep(3)
        try:
            await sent.delete()
        except:
            pass
        
        return ConversationHandler.END

    # View mode: password required
    if args and args[0] == "date" and len(args) >= 2:
        ctx.user_data["diary_view"] = ("date", args[1])
    elif args and args[0] == "all":
        ctx.user_data["diary_view"] = ("all", None)
    elif args and args[0] == "week":
        ctx.user_data["diary_view"] = ("week", None)
    else:
        ctx.user_data["diary_view"] = ("today", None)

    await update.message.reply_text(
        "🔐 *Diary — Password Enter Karo:*\n\n"
        "_Tumhari diary private hai. Password daalo:_",
        parse_mode="Markdown"
    )
    return DIARY_AWAIT_PASS

async def diary_password_check(update, ctx):
    entered = update.message.text.strip()

    if entered != DIARY_PASSWORD:
        await update.message.reply_text(
            "❌ *Galat password!* Diary access nahi hua.\n"
            "_/diary likhne ke liye: `/diary Aaj ka din acha tha`_",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    view_type, view_arg = ctx.user_data.get("diary_view", ("today", None))
    await _show_diary(update, view_type, view_arg)
    return ConversationHandler.END

async def diary_conv_cancel(update, ctx):
    try:
        if update.message:
            await update.message.reply_text("⏱ Diary session expired. Fir se /diary likhein.")
    except:
        pass
    return ConversationHandler.END

async def _show_diary(update, view_type, view_arg):
    if view_type == "today":
        entries = diary.get(today_str())
        all_entries = {today_str(): entries} if entries else {}
        title = f"📖 *Aaj Ki Diary — {today_str()}*"
    elif view_type == "date":
        entries = diary.get(view_arg)
        all_entries = {view_arg: entries} if entries else {}
        title = f"📖 *Diary — {view_arg}*"
    elif view_type == "week":
        n = now_ist()
        all_entries = {}
        for i in range(7):
            d = (n - timedelta(days=i)).strftime("%Y-%m-%d")
            e = diary.get(d)
            if e:
                all_entries[d] = e
        title = "📖 *Is Hafte Ki Diary*"
    elif view_type == "all":
        all_entries = diary.get_all_entries()
        title = f"📖 *Puri Diary ({len(all_entries)} din)*"
    else:
        all_entries = {}
        title = "📖 *Diary*"

    if not all_entries:
        await update.message.reply_text(
            f"{title}\n\n_Koi entry nahi mili._\n\n"
            "_Likhne ke liye: `/diary Aaj kuch acha hua...`_",
            parse_mode="Markdown"
        )
        return

    chunks = []
    current_chunk = f"{title}\n{'━'*28}\n\n"

    for date_key in sorted(all_entries.keys(), reverse=True):
        entries = all_entries[date_key]
        date_block = f"📅 *{date_key}*\n"
        for i, e in enumerate(entries, 1):
            mood = e.get("mood", "📝")
            time_ = e.get("time", "")
            text = e.get("text", "")
            date_block += f"{mood} `{time_}` — {text}\n"
        date_block += "\n"

        if len(current_chunk) + len(date_block) > 3800:
            chunks.append(current_chunk)
            current_chunk = date_block
        else:
            current_chunk += date_block

    if current_chunk.strip():
        chunks.append(current_chunk)

    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except:
            await update.message.reply_text(chunk)

async def cmd_habit(update, ctx):
    if not ctx.args: await update.message.reply_text("💪 `/habit Naam`"); return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(f"💪 {h['emoji']} *{h['name']}*\n`/hdone {h['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_hdone(update, ctx):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            msg = "💪 *Pending habits:*\n"
            for h in pending:
                msg += f"`/hdone {h['id']}` → {h['name']}\n"
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
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid habit ID!")

async def cmd_delhabit(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delhabit <id>`"); return
    try:
        habits.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Deleted!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_kharcha(update, ctx):
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text("💰 `/kharcha 100 Chai`")
        return
    try:
        amount = float(ctx.args[0]); desc = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        await update.message.reply_text(f"💰 ₹{amount:.0f} — {desc}\n📊 Aaj: ₹{expenses.today_total():.0f}", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Format: `/kharcha 100 Chai`")

async def cmd_budget(update, ctx):
    if not ctx.args: await update.message.reply_text("💳 `/budget 5000`"); return
    try:
        expenses.set_budget(float(ctx.args[0]))
        await update.message.reply_text(f"💳 Budget: ₹{ctx.args[0]}")
        await auto_backup_to_sheets()
    except: pass

async def cmd_goal(update, ctx):
    if not ctx.args:
        active = goals.active()
        if active:
            msg = "🎯 *ACTIVE GOALS*\n\n"
            for g in active:
                bar = "█" * (g['progress'] // 10) + "░" * (10 - (g['progress'] // 10))
                msg += f"**#{g['id']} {g['title']}**\n`{bar}` {g['progress']}%\n\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("🎯 `/goal Learn Python in 30 days`")
        return
    g = goals.add(" ".join(ctx.args))
    await update.message.reply_text(f"🎯 Goal set: #{g['id']} {g['title']}\nUse `/gprogress {g['id']} 50` to update progress")
    await auto_backup_to_sheets()

async def cmd_gprogress(update, ctx):
    if len(ctx.args) < 2: await update.message.reply_text("📊 `/gprogress <id> <pct>`"); return
    try:
        g = goals.update_progress(int(ctx.args[0]), int(ctx.args[1]))
        if g:
            bar = "█" * (g['progress'] // 10) + "░" * (10 - (g['progress'] // 10))
            await update.message.reply_text(f"📊 *{g['title']}*\n`{bar}` {g['progress']}% complete!", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Goal not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Use: `/gprogress <goal_id> <percentage>`")

async def cmd_remember(update, ctx):
    if not ctx.args: await update.message.reply_text("🧠 `/remember Text`"); return
    memory.add_fact(" ".join(ctx.args))
    await update.message.reply_text("🧠 Yaad kar liya! ✅")
    await auto_backup_to_sheets()

async def cmd_recall(update, ctx):
    facts = memory.get_all_facts()
    if not facts: await update.message.reply_text("🧠 Kuch yaad nahi."); return
    txt = "🧠 *YAADDASHT*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-10:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_note(update, ctx):
    if not ctx.args: await update.message.reply_text("📝 `/note Text`"); return
    n = notes.add(" ".join(ctx.args))
    await update.message.reply_text(f"📝 Note #{n['id']} saved!")
    await auto_backup_to_sheets()

async def cmd_delnote(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delnote <id>`"); return
    try:
        notes.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Deleted!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_briefing(update, ctx):
    tp = tasks.today_pending(); hd, hp = habits.today_status(); n = now_ist()
    txt = f"🌅 *BRIEFING*\n⏰ {n.strftime('%I:%M %p')} | 📅 {n.strftime('%d %b')}\n\n"
    if tp: txt += f"📋 *Pending ({len(tp)}):*\n" + "".join(f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}\n" for t in tp[:5])
    else: txt += "🎉 No pending tasks!\n"
    if hp: txt += f"\n💪 Habits left: {', '.join(h['name'] for h in hp[:4])}"
    txt += f"\n\n💰 Aaj: ₹{expenses.today_total():.0f} | Mahina: ₹{expenses.month_total():.0f}"
    bl = expenses.budget_left()
    if bl is not None: txt += f" | Budget: ₹{bl:.0f}"
    txt += f"\n💧 Water: {water.today_total()}ml/{water.goal()}ml"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_weekly(update, ctx):
    n = now_ist(); week_start = n.date() - timedelta(days=n.weekday())
    msg = f"📊 *WEEKLY REPORT*\n📅 {week_start.strftime('%d %b')} - {n.strftime('%d %b %Y')}\n\n"
    tw = tasks.get_weekly_summary()
    total_done = sum(v["done"] for v in tw.values())
    total_created = sum(v["created"] for v in tw.values())
    msg += f"📋 *TASKS*\n   ✅ Completed: {total_done}\n   ➕ Created: {total_created}\n   ⏳ Pending: {len(tasks.pending())}\n\n"
    msg += f"💪 *HABITS*\n"
    for h in habits.all(): msg += f"   {h['emoji']} {h['name']} — 🔥 Streak: {h.get('streak', 0)} days\n"
    msg += f"\n💰 *EXPENSES*\n   This month: ₹{expenses.month_total():.0f}\n   Today: ₹{expenses.today_total():.0f}\n"
    bl = expenses.budget_left()
    if bl is not None: msg += f"   Budget remaining: ₹{bl:.0f}\n"
    msg += f"\n💧 *WATER*\n   Today: {water.today_total()}ml / {water.goal()}ml"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_report(update, ctx):
    if not ctx.args: await update.message.reply_text("📋 `/report YYYY-MM-DD`", parse_mode="Markdown"); return
    target_date = ctx.args[0]
    try: datetime.strptime(target_date, "%Y-%m-%d")
    except: await update.message.reply_text("❌ Invalid date! Use: YYYY-MM-DD"); return
    msg = f"📋 *REPORT FOR {target_date}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    tasks_done = tasks.done_on(target_date)
    msg += f"📋 *TASKS*\n   Completed: {len(tasks_done)}\n"
    if tasks_done: msg += f"   ✅ " + "\n      ".join(f"#{t['id']} {t['title'][:30]}" for t in tasks_done[:5]) + "\n"
    msg += "\n"
    exp = expenses.get_by_date(target_date)
    total_exp = sum(e["amount"] for e in exp)
    msg += f"💰 *EXPENSES*\n   Total: ₹{total_exp:.0f}\n"
    if exp:
        for e in exp[:5]: msg += f"   • ₹{e['amount']:.0f} — {e['desc'][:25]}\n"
    msg += "\n"
    dentries = diary.get(target_date)
    if dentries: msg += f"📖 *DIARY*\n   {dentries[0]['text'][:50]}\n"
    msg += "\n"
    hlogs = habits.get_logs_by_date(target_date)
    hdone = [h for h in habits.all() if h["id"] in hlogs]
    msg += f"💪 *HABITS*\n"
    if hdone: msg += f"   ✅ " + ", ".join(f"{h['emoji']}{h['name']}" for h in hdone) + "\n"
    else: msg += f"   No habits logged\n"
    msg += "\n"
    wentries = water.get_by_date(target_date)
    total_w = sum(w["ml"] for w in wentries)
    msg += f"💧 *WATER*\n   Total: {total_w}ml"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_news(update, ctx):
    items = news_store.get("India", 5)
    if not items: await update.message.reply_text("📰 News unavailable right now."); return
    txt = f"📰 *INDIA NEWS*\n\n"
    for item in items: txt += f"• *{item['title']}*\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_alltasks(update, ctx):
    all_t = tasks.all_tasks()
    if not all_t: await update.message.reply_text("📋 No tasks!"); return
    p = tasks.pending(); c = tasks.completed_tasks()
    txt = f"📋 *ALL TASKS*\n📊 Total: {len(all_t)} | ⏳ Pending: {len(p)} | ✅ Done: {len(c)}\n\n"
    if p: txt += "⏳ *PENDING:*\n" + "\n".join(f"   #{t['id']} {t['title']}" for t in p[:10])
    if c: txt += "\n\n✅ *RECENTLY COMPLETED:*\n" + "\n".join(f"   #{t['id']} {t['title']}" for t in c[-5:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed(update, ctx):
    c = tasks.completed_tasks()
    if not c: await update.message.reply_text("✅ No completed tasks yet!"); return
    txt = f"✅ *COMPLETED TASKS ({len(c)})*\n\n" + "\n".join(f"  ✓ #{t['id']} {t['title']}" for t in c[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_yesterday(update, ctx):
    yd = yesterday_str(); td = tasks.done_on(yd); exp = expenses.get_by_date(yd)
    diaryyd = diary.get(yd); hlogs = habits.get_logs_by_date(yd)
    hdone = [h for h in habits.all() if h["id"] in hlogs]
    txt = f"📅 *YESTERDAY'S SUMMARY* ({yd})\n━━━━━━━━━━━━━━━━━━━━\n\n"
    txt += f"✅ *Tasks completed:* {len(td)}\n"
    if td: txt += "   " + "\n   ".join(f"• {t['title']}" for t in td[:5]) + "\n"
    txt += f"\n💪 *Habits done:* {len(hdone)}/{len(habits.all())}\n"
    if hdone: txt += "   " + ", ".join(f"{h['emoji']}{h['name']}" for h in hdone) + "\n"
    txt += f"\n💰 *Expenses:* ₹{sum(e['amount'] for e in exp):.0f}\n"
    if exp: txt += "   " + "\n   ".join(f"• ₹{e['amount']:.0f} — {e['desc']}" for e in exp[:3]) + "\n"
    if diaryyd: txt += f"\n📖 *Diary:* {diaryyd[0]['text'][:60]}"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_remind(update, ctx):
    now = now_ist()
    if not ctx.args:
        await update.message.reply_text(f"⏰ *REMINDER*\nAbhi: *{now.strftime('%I:%M %p')} IST*\n\n`/remind 2m Test` — 2 min baad\n`/remind 30m Chai` — 30 min baad\n`/remind 15:30 Doctor` — exact time\n`/remind 8:00 Uthna daily` — daily\n`/remind 9:00 Meeting weekly` — weekly", parse_mode="Markdown")
        return
    time_arg = ctx.args[0].lower(); rest = ctx.args[1:]; repeat = "once"
    if rest and rest[-1].lower() in ["daily", "weekly"]: repeat = rest[-1].lower(); rest = rest[:-1]
    text = " ".join(rest) if rest else "⏰ Reminder!"
    if time_arg.endswith("m") and time_arg[:-1].isdigit(): remind_at = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif time_arg.endswith("h") and time_arg[:-1].isdigit(): remind_at = (now + timedelta(hours=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        parts = time_arg.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit() and 0 <= int(parts[0]) <= 23: remind_at = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        else: await update.message.reply_text("❌ Invalid time! Use HH:MM (00:00 to 23:59)"); return
    else: await update.message.reply_text("❌ Format galat! Use: `/remind 2m Test` or `/remind 15:30 Meeting`"); return
    r = reminders.add(update.effective_chat.id, text, remind_at, repeat)
    rl = {"once": "Once", "daily": "Daily 🔁", "weekly": "Weekly 📅"}.get(repeat, repeat)
    await update.message.reply_text(f"✅ *Reminder set!* ⏰ {remind_at} — {text}\n{rl}\n🆔 `#{r['id']}` | `/delremind {r['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_reminders_list(update, ctx):
    active = reminders.all_active()
    now = now_ist()
    if not active: await update.message.reply_text(f"⏰ No reminders!\nAbhi: *{now.strftime('%I:%M %p')}*\n`/remind 2m Test` se set karo", parse_mode="Markdown"); return
    txt = f"⏰ *REMINDERS ({len(active)})*\nAbhi: *{now.strftime('%I:%M %p')} IST*\n\n"
    for r in active:
        icon = "🔁" if r["repeat"] == "daily" else "📅" if r["repeat"] == "weekly" else "1️⃣"
        txt += f"*#{r['id']}* {icon} `{r['time']}` — {r['text']} {'✅' if r['fired_today'] else '⏳'}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_delremind(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delremind <id>`\nUse `/reminders` to see all IDs"); return
    try:
        reminders.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Reminder deleted!")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid ID!")

async def cmd_water(update, ctx):
    ml = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 250
    water.add(ml); total = water.today_total(); goal = water.goal()
    pct = min(100, int(total / goal * 100)) if goal else 0
    await update.message.reply_text(f"💧 +{ml}ml | Total: {total}ml/{goal}ml ({pct}%)", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_water_status(update, ctx):
    total = water.today_total(); goal = water.goal()
    pct = min(100, int(total / goal * 100)) if goal else 0
    await update.message.reply_text(f"💧 {total}ml / {goal}ml ({pct}%)", parse_mode="Markdown")

async def cmd_water_goal(update, ctx):
    if not ctx.args: await update.message.reply_text(f"Current goal: {water.goal()}ml\n`/watergoal 2500` to change"); return
    try: water.set_goal(int(ctx.args[0])); await update.message.reply_text(f"✅ Water goal set to {ctx.args[0]}ml")
    except: pass

async def cmd_bill(update, ctx):
    if not ctx.args or len(ctx.args) < 3: await update.message.reply_text("💳 `/bill Naam Amount DueDay`\nExample: `/bill Internet 999 15`"); return
    try:
        b = bills.add(ctx.args[0], float(ctx.args[1]), int(ctx.args[2]))
        await update.message.reply_text(f"✅ Bill added: {b['name']} ₹{b['amount']:.0f} — Due on {b['due_day']}th of every month", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Format: `/bill Name Amount DueDay`")

async def cmd_bills_list(update, ctx):
    all_b = bills.all_active()
    if not all_b: await update.message.reply_text("💳 No bills added yet!\nUse `/bill` to add"); return
    txt = "💳 *BILLS*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for b in all_b:
        status = "✅" if bills.is_paid_this_month(b["id"]) else "⏳ Pending"
        txt += f"{status} *{b['name']}* — ₹{b['amount']:.0f} (Due {b['due_day']}th)\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_bill_paid(update, ctx):
    if not ctx.args: await update.message.reply_text("`/billpaid <bill_id>`\nUse `/bills` to see IDs"); return
    try:
        if bills.mark_paid(int(ctx.args[0])): await update.message.reply_text("✅ Bill marked as paid for this month!")
        else: await update.message.reply_text("❌ Already paid or bill not found!")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid bill ID!")

async def cmd_del_bill(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delbill <bill_id>`"); return
    try:
        bills.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Bill deleted!")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid ID!")

async def cmd_cal(update, ctx):
    if not ctx.args: await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`\n`/cal kal Client call`\n`/cal aaj Doctor appointment`"); return
    args_str = " ".join(ctx.args); date_str = None; title = args_str; event_time = ""
    m = _re.match(r'^(\d{4}-\d{2}-\d{2})\s+(.*)', args_str)
    if m: date_str = m.group(1); title = m.group(2)
    if not date_str:
        if args_str.lower().startswith("aaj "): date_str = today_str(); title = args_str[4:]
        elif args_str.lower().startswith("kal "): date_str = (now_ist().date() + timedelta(days=1)).isoformat(); title = args_str[4:]
    if not date_str: await update.message.reply_text("❌ Use: `/cal YYYY-MM-DD Event`\n`/cal aaj Meeting`\n`/cal kal Doctor`"); return
    t_match = _re.search(r'(\d{1,2}:\d{2})', title)
    if t_match: event_time = t_match.group(1); title = title.replace(event_time, "").strip()
    try:
        date.fromisoformat(date_str)
        e = calendar.add(title, date_str, event_time)
        await update.message.reply_text(f"📅 Event added: {title} — {date_str}" + (f" ⏰{event_time}" if event_time else ""), parse_mode="Markdown")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid date! Use YYYY-MM-DD")

async def cmd_cal_list(update, ctx):
    upcoming = calendar.upcoming(30)
    if not upcoming: await update.message.reply_text("📅 No upcoming events!"); return
    txt = "📅 *UPCOMING EVENTS*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for e in upcoming[:15]:
        today_flag = "🔴 TODAY" if e["date"] == today_str() else "📆"
        time_str = f" @ {e['time']}" if e.get("time") else ""
        txt += f"{today_flag} {e['date']}{time_str} — {e['title']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_del_cal(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delcal <event_id>`\nUse `/calendar` to see IDs"); return
    try:
        calendar.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Event deleted!")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid ID!")

async def cmd_memory(update, ctx):
    facts = memory.get_all_facts()
    if not facts: await update.message.reply_text("🧠 No memories saved yet! Use `/remember` to add."); return
    txt = "🧠 *MY MEMORY*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for f in facts[-15:]: txt += f"📌 {f['f']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_backup(update, ctx):
    await update.message.reply_text("📤 Backing up to Google Sheets...")
    result = google_sheets.full_sync()
    await update.message.reply_text(result)

async def cmd_dbstatus(update, ctx):
    lines = []
    if google_sheets.sheet: lines.append("✅ *Google Sheets: CONNECTED — Data safe hai!*")
    else: lines.append("❌ *Sheets NOT connected!*")
    lines.append(f"\n📊 *Data stats:*")
    lines.append(f"  ⏰ Reminders: {len(reminders.store.data.get('list', []))}")
    lines.append(f"  📋 Tasks: {len(tasks.store.data.get('list', []))}")
    lines.append(f"  📖 Diary: {sum(len(v) for v in diary.store.data.get('entries', {}).values())}")
    lines.append(f"  💰 Expenses: {len(expenses.store.data.get('list', []))}")
    lines.append(f"  💪 Habits: {len(habits.store.data.get('list', []))}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_clear(update, ctx):
    count = chat_hist.clear()
    await update.message.reply_text(f"🧹 Chat history cleared ({count} msgs)!\n✅ All data SAFE!", parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════════
# MESSAGE HANDLER — AI CHAT + LOG
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_msg = update.message.text.strip()
    user_name = update.effective_user.first_name or "User"

    if user_msg.startswith('/'):
        return

    # Diary write mode from button (agar kabhi use ho)
    if ctx.user_data.get("awaiting_diary_entry"):
        ctx.user_data.pop("awaiting_diary_entry", None)
        diary.add(user_msg, mood="📝")
        loop = asyncio.get_event_loop()
        loop.create_task(auto_backup_to_sheets())
        try:
            await update.message.delete()
        except:
            pass
        sent = await update.effective_chat.send_message(f"📖 *Diary saved!* 🕐 {now_str()}\n\n_{user_msg[:150]}_", parse_mode="Markdown")
        await asyncio.sleep(3)
        try:
            await sent.delete()
        except:
            pass
        return

    ctx.user_data.pop("diary_view", None)

    # AI Chat with action detection
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ai_chat(user_msg, update.effective_chat.id)

    # 🔥 LOG TO CHAT HISTORY
    chat_hist.add("user", user_msg, user_name)
    chat_hist.add("assistant", reply, "Bot")

    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(reply)

    # 🔥 AUTO-BACKUP AFTER EVERY MESSAGE
    await auto_backup_to_sheets()

# ═══════════════════════════════════════════════════════════════════
# BACKGROUND JOBS
# ═══════════════════════════════════════════════════════════════════
async def reminder_job(context):
    now = now_ist()
    now_time = now.strftime("%H:%M")
    
    if now_time in ("00:00", "00:01", "00:02"):
        reminders.reset_daily()
        return
    
    due = reminders.due_now()
    
    for r in due:
        try:
            repeat_note = ""
            if r["repeat"] == "daily": repeat_note = "\n🔁 _Kal bhi yaad dilaunga!_"
            elif r["repeat"] == "weekly": repeat_note = "\n📅 _Agli hafte!_"
            
            # 🔥 ALARM BUTTONS
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Done", callback_data=f"remind_done_{r['id']}"),
                InlineKeyboardButton("⏰ 10 min Snooze", callback_data=f"remind_snooze_{r['id']}")
            ]])
            
            alert_text = (
                f"🚨🔔🚨 *ALARM!* 🚨🔔🚨\n"
                f"{'═'*25}\n"
                f"⏰ *{r['time']} BAJ GAYE!*\n"
                f"{'═'*25}\n\n"
                f"📢 *{r['text'].upper()}*\n\n"
                f"{repeat_note}"
            )
            
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=alert_text,
                parse_mode="Markdown",
                disable_notification=False,
                reply_markup=kb
            )
            
            reminders.mark_fired(r["id"])
            await asyncio.sleep(1)
            
        except Exception as e:
            log.error(f"❌ FAILED #{r['id']}: {e}")

async def bill_due_job(context):
    if now_ist().strftime("%H:%M") != "09:00": return
    due = bills.due_soon(3)
    if not due: return
    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    if not chat_ids: return
    txt = "💳 *BILL DUE SOON*\n\n" + "\n".join(f"⚠️ {b['name']} — ₹{b['amount']:.0f}" for b in due)
    for cid in chat_ids:
        try: await context.bot.send_message(chat_id=cid, text=txt, parse_mode="Markdown")
        except: pass

async def water_reminder_job(context):
    now = now_ist()
    if not (8 <= now.hour <= 22) or now.hour % 3 != 0: return
    total = water.today_total(); goal = water.goal()
    if total >= goal: return
    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    for cid in chat_ids:
        try: await context.bot.send_message(chat_id=cid, text=f"💧 *Paani peene ka time!*\nToday: {total}ml/{goal}ml\n`/water` se log karo", parse_mode="Markdown")
        except: pass

_last_auto_backup = 0
_BACKUP_THROTTLE_SECS = 10

async def auto_backup_to_sheets():
    global _last_auto_backup
    now_ts = time.time()
    if now_ts - _last_auto_backup < _BACKUP_THROTTLE_SECS: return
    _last_auto_backup = now_ts
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, google_sheets.full_sync)
    log.info(f"📤 {result}")
    return result

async def daily_log_job(context):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, google_sheets.save_daily_log)

async def scheduled_backup_job(context):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, google_sheets.full_sync)
    log.info(f"🕒 {result}")

# ═══════════════════════════════════════════════════════════════════
# CALLBACK HANDLER — ALARM ONLY
# ═══════════════════════════════════════════════════════════════════
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    d = query.data
    message = query.message
    
    if not message: return
    
    if d.startswith("remind_done_"):
        rid = int(d.split("_")[2])
        reminders.mark_fired(rid)
        await message.edit_text("✅ Reminder marked as done!")
        await auto_backup_to_sheets()
        await asyncio.sleep(2)
        try: await message.delete()
        except: pass
    
    elif d.startswith("remind_snooze_"):
        rid = int(d.split("_")[2])
        snooze = (now_ist() + timedelta(minutes=10)).strftime("%H:%M")
        r_list = [r for r in reminders.get_all() if r["id"] == rid]
        if r_list:
            reminders.add(message.chat_id, r_list[0]["text"], snooze, "once")
            reminders.mark_fired(rid)
        await message.edit_text(f"😴 Snoozed to {snooze}")
        await auto_backup_to_sheets()
        await asyncio.sleep(2)
        try: await message.delete()
        except: pass

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    n = now_ist()
    log.info("=" * 55)
    log.info(f"🤖 Bot v20 — 100% WORKING (Original v10 Action System)")
    log.info(f"⏰ IST: {n.strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"📊 Google Sheets: {'✅ CONNECTED' if google_sheets.sheet else '❌ NOT connected!'}")
    log.info(f"🔑 Gemini: {'YES' if GEMINI_API_KEY else 'NO'} | 🎤 Groq: {'YES' if GROQ_API_KEY else 'NO'}")
    log.info("=" * 55)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # No startup notification
    app.post_init = lambda app: None

    # All commands
    commands = [
        ("start", cmd_start), ("help", cmd_help),
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("habit", cmd_habit), ("hdone", cmd_hdone), ("delhabit", cmd_delhabit),
        ("kharcha", cmd_kharcha), ("budget", cmd_budget),
        ("goal", cmd_goal), ("gprogress", cmd_gprogress),
        ("remember", cmd_remember), ("recall", cmd_recall),
        ("note", cmd_note), ("delnote", cmd_delnote),
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

    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))

    # Diary ConversationHandler
    diary_conv = ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary)],
        states={DIARY_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)]},
        fallbacks=[CommandHandler("cancel", diary_conv_cancel)],
        per_user=True, per_chat=True, conversation_timeout=60,
    )
    app.add_handler(diary_conv)
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    
    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=15)
        app.job_queue.run_repeating(bill_due_job, interval=3600, first=300)
        app.job_queue.run_repeating(water_reminder_job, interval=3600, first=600)
        app.job_queue.run_repeating(scheduled_backup_job, interval=3600, first=120)
        app.job_queue.run_daily(daily_log_job, time=dt_module.time(hour=21, minute=0, tzinfo=IST))
        log.info("⏰ Jobs started!")
    
    log.info("✅ Bot ready! Test: /help")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
