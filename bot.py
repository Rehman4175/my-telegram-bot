#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v14.0 FINAL STABLE EDITION         ║
║  ✅ ALL BUGS FIXED                                              ║
║  ✅ Hello/Hi ka jawab instant                                  ║
║  ✅ Reminder sirf explicitly maangne pe set hota hai           ║
║  ✅ AI responses consistent & reliable                        ║
║  ✅ ConversationHandler blocking issue fixed                   ║
║  ✅ All features intact: Tasks, Habits, Diary, Expenses etc.   ║
║  + VOICE COMMANDS (Groq Whisper)                                ║
║  + GOOGLE SHEETS FIXED (batch_clear + batch_update)            ║
║  + DAILY_LOGS UPSERT (no duplicate rows)                       ║
║  + ALL REMINDERS SAVED (active + inactive history)             ║
║  + BACKUP THROTTLED (no rate limit)                            ║
║  + ALL BUTTONS FIXED (back button on every screen)             ║
║  + REMINDERS | TASKS | HABITS | DIARY | EXPENSES | GOALS       ║
║  + WATER | BILLS | CALENDAR | MEMORY | NOTES | NEWS            ║
║                                                                  ║
║  GITHUB SECRETS NEEDED:                                          ║
║    TELEGRAM_TOKEN   — BotFather se milta hai                    ║
║    GEMINI_API_KEY   — aistudio.google.com (free)               ║
║    GOOGLE_CREDS_JSON — Google Service Account JSON             ║
║    MONGO_URI        — MongoDB Atlas (optional)                  ║
║    HF_TOKEN         — HuggingFace (optional fallback)          ║
║    GROQ_API_KEY     — groq.com (free, voice ke liye)           ║
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
# 🔥 INDIAN STANDARD TIME (IST) — ALWAYS ACCURATE
# ═══════════════════════════════════════════════════════════════════
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    """Current IST time — works on ANY server timezone"""
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
                    log.debug(f"📂 Loaded '{collection}' from local cache")
                    return data
        except Exception as e:
            log.warning(f"Local load '{collection}' failed: {e}")
        return default if default is not None else {}

    def save(self, collection, data):
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log.debug(f"💾 Saved '{collection}' locally")
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
# GEMINI API (Rate Limited)
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
# ✅ IMPROVED SMART OFFLINE FALLBACK
# ═══════════════════════════════════════════════════════════════════
def smart_fallback(user_msg):
    msg = user_msg.lower().strip()
    n = now_ist()
    
    if any(w in msg for w in ["time", "baje", "kitne baje", "time kya", "time batao", "time bata"]):
        return f"⏰ Abhi *{n.strftime('%I:%M %p')}* baj rahe hain (IST)"
    
    if any(w in msg for w in ["date", "aaj kya", "tarikh", "aaj kitni", "aaj ki date"]):
        return f"📅 Aaj *{n.strftime('%A, %d %B %Y')}* hai"
    
    if any(w in msg for w in ["hello", "hi", "assalam", "namaste", "hey", "hola", "yo"]):
        return "🕌 *Assalamualaikum!* Main aapka AI dost hoon. Batao kaisi help chahiye? 😊"
    
    if any(w in msg for w in ["kaise ho", "how are", "kya haal", "kaisi ho", "how r u"]):
        return "😊 *Main badiya hoon!* Aap sunao, kya ho raha hai aaj kal?"
    
    if any(w in msg for w in ["thank", "shukriya", "thanks", "dhanyavad", "thx"]):
        return "🤗 *Welcome!* Aur koi help chahiye toh batana!"
    
    if any(w in msg for w in ["bye", "allah hafiz", "good night", "shabba", "fir milenge"]):
        return "🌙 *Allah Hafiz!* Apna khayal rakhna. Fir milenge! 🤗"
    
    if any(w in msg for w in ["help", "madad", "command", "kya kar", "kya karte"]):
        return ("📋 *COMMANDS*\n\n"
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
                "**⏰ REMINDERS**\n"
                "`/remind` `/reminders` `/delremind` — Reminders\n"
                "`/cal` `/calendar` `/delcal` — Calendar\n\n"
                "**📊 REPORTS**\n"
                "`/briefing` `/weekly` `/report YYYY-MM-DD` — Reports\n\n"
                "_Ya seedha type karo — main samjhunga!_")
    
    replies = [
        "🙏 Main yahin hoon! Batao kya help chahiye? Tasks, reminders, ya kuch aur?",
        "😊 Haan bolo! Kya karna hai aaj? Task add karna, reminder set karna, ya bas baat karni?",
        "🤖 Ready hoon! Batao kya karna hai? `/help` se saare commands dekh sakte ho.",
    ]
    return random.choice(replies)

# ═══════════════════════════════════════════════════════════════════
# 🎤 VOICE TRANSCRIPTION (Groq Whisper — Free & Fast)
# ═══════════════════════════════════════════════════════════════════
async def transcribe_voice(file_path: str) -> str:
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
        log.warning(f"Voice transcription failed: {e}")
    return None

async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    if not GROQ_API_KEY:
        await update.message.reply_text(
            "🎤 *Voice ke liye GROQ\\_API\\_KEY chahiye!*\n\n"
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
        import tempfile

        file = await ctx.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _sync_transcribe, tmp_path)

        try:
            os.unlink(tmp_path)
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
# ✅ IMPROVED MAIN AI PIPELINE
# ═══════════════════════════════════════════════════════════════════
def get_ai_reply(user_msg, chat_id=None, system_ctx=None):
    if not system_ctx:
        system_ctx = build_system_prompt()
    
    user_msg_short = user_msg[:500]
    
    prompt = f"""{system_ctx}

User message: {user_msg_short}

Reply in Hindi/Hinglish (2-4 lines, warm & friendly like a close friend):
- Dost ki tarah natural baat karo
- "As an AI" kabhi mat bol
- Agar time puchhe to upar diya hua exact time batana
- Short aur helpful jawab do
- Agar user hello/hi bole to warmly greet karo
- Agar user kuch puchhe to helpful jawab do"""
    
    reply = call_gemini(prompt, max_tokens=300)
    if reply and len(reply) > 5:
        return reply
    
    reply = call_huggingface(prompt)
    if reply and len(reply) > 5:
        return reply + "\n\n_⚡ (via free model)_"
    
    return smart_fallback(user_msg)

# ═══════════════════════════════════════════════════════════════════
# ALL DATA STORES
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
        task_logs.add_log("created", title, t["id"], {"priority": priority})
        return t
    
    def complete(self, tid):
        for t in self.store.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True
                t["done_at"] = datetime.now().isoformat()
                self._save()
                task_logs.add_log("completed", t["title"], tid)
                return t
        return None
    
    def delete(self, tid):
        before = len(self.store.data["list"])
        for t in self.store.data["list"]:
            if t["id"] == tid:
                task_logs.add_log("deleted", t["title"], tid)
        self.store.data["list"] = [t for t in self.store.data["list"] if t["id"] != tid]
        self._save()
        return before != len(self.store.data["list"])
    
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


class TaskLogsStore:
    def __init__(self):
        self.store = Store("task_logs", {"logs": []})
    
    def add_log(self, action_type, description, task_id=None, details=None):
        self.store.data["logs"].append({
            "type": action_type, "description": description,
            "task_id": task_id, "details": details or {},
            "timestamp": datetime.now().isoformat(), "date": today_str()
        })
        self.store.data["logs"] = self.store.data["logs"][-500:]
        self.store.save()
    
    def get_all_logs(self):
        return self.store.data.get("logs", [])
    
    def get_logs_by_date(self, target_date):
        return [l for l in self.get_all_logs() if l.get("date") == target_date]
    
    def get_weekly_summary(self):
        result = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            result[d] = {
                "created": len([l for l in self.get_logs_by_date(d) if l["type"] == "created"]),
                "completed": len([l for l in self.get_logs_by_date(d) if l["type"] == "completed"])
            }
        return result
    
    def get_created_tasks(self):
        return [l for l in self.get_all_logs() if l["type"] == "created"]
    
    def get_completed_tasks(self):
        return [l for l in self.get_all_logs() if l["type"] == "completed"]
    
    def get_all_task_summary(self):
        created_ids = set(l.get("task_id") for l in self.get_created_tasks() if l.get("task_id"))
        completed_ids = set(l.get("task_id") for l in self.get_completed_tasks() if l.get("task_id"))
        return {
            "total_created": len(created_ids),
            "total_completed": len(completed_ids),
            "total_pending": len(created_ids - completed_ids)
        }


class FailedReqStore:
    def __init__(self):
        self.store = Store("failed_requests", {"queue": []})
    
    def add(self, msg, chat_id, reason):
        self.store.data["queue"].append({
            "msg": msg, "chat_id": chat_id, "reason": reason,
            "time": datetime.now().isoformat(), "retried": False
        })
        self.store.data["queue"] = self.store.data["queue"][-50:]
        self.store.save()
    
    def get_unretried(self):
        return [r for r in self.store.data.get("queue", []) if not r["retried"]]
    
    def mark_retried(self, idx):
        if 0 <= idx < len(self.store.data["queue"]):
            self.store.data["queue"][idx]["retried"] = True
            self.store.save()


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
        log.info(f"✅ Reminder CREATED: #{r['id']} | chat={chat_id} | time={remind_at} | text={text[:30]}")
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
                if 0 <= diff_seconds < 120:
                    due.append(r)
                    log.info(f"⏰ DUE: #{r['id']} | {r_time} | Now: {now_hm}")
                    continue
            except:
                pass
            
            if r_time == now_hm:
                if r not in due:
                    due.append(r)
                    log.info(f"⏰ DUE (exact): #{r['id']} | {r_time} == {now_hm}")
        
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
        self.store = Store("chat_history", {"history": [], "cleared_at": None, "msg_ids": []})
    
    def add(self, role, content):
        self.store.data["history"].append({"role": role, "content": content, "time": datetime.now().isoformat()})
        self.store.data["history"] = self.store.data["history"][-40:]
        self.store.save()
    
    def track_msg(self, chat_id, msg_id):
        self.store.data.setdefault("msg_ids", []).append({"chat_id": chat_id, "msg_id": msg_id})
        self.store.data["msg_ids"] = self.store.data["msg_ids"][-200:]
        self.store.save()
    
    def get_tracked_ids(self):
        return self.store.data.get("msg_ids", [])
    
    def get_recent(self, n=10):
        return [{"role": m["role"], "content": m["content"]} for m in self.store.data.get("history", [])[-n:]]
    
    def clear(self):
        count = len(self.store.data["history"])
        self.store.data["history"] = []
        self.store.data["cleared_at"] = datetime.now().isoformat()
        self.store.save()
        return count
    
    def clear_msg_ids(self):
        self.store.data["msg_ids"] = []
        self.store.save()
    
    def count(self):
        return len(self.store.data.get("history", []))


# ═══════════════════════════════════════════════════════════════════
# INIT ALL STORES
# ═══════════════════════════════════════════════════════════════════
memory = MemoryStore()
tasks = TaskStore()
task_logs = TaskLogsStore()
failed_reqs = FailedReqStore()
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
# ⭐ GOOGLE SHEETS BACKUP INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class GoogleSheetsBackup:
    def __init__(self):
        self.sheet = None
        if not HAS_GSHEETS:
            log.warning("⚠️ gspread not installed! Run: pip install gspread oauth2client")
            return
        
        creds_json = os.environ.get("GOOGLE_CREDS_JSON", "") or os.environ.get("Google_CREDS_JSON", "")
        
        if not creds_json:
            log.warning("⚠️ GOOGLE_CREDS_JSON not found in secrets! Backup disabled.")
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
            log.info("✅ Google Sheets connected via GOOGLE_CREDS_JSON!")
            
            self.ensure_worksheets()
            
        except json.JSONDecodeError as e:
            log.error(f"❌ Google Sheets JSON parse error: {e}")
        except Exception as e:
            log.error(f"❌ Google Sheets connection error: {e}")
    
    def ensure_worksheets(self):
        if not self.sheet:
            return
        
        required = ["Tasks", "Reminders", "Expenses", "Habits", "Water", "Memory", "Daily_Logs", "Goals", "Bills", "Calendar", "Diary"]
        existing_ws = self.sheet.worksheets()
        existing_titles = [ws.title for ws in existing_ws]
        existing_lower = {t.lower(): t for t in existing_titles}
        
        for name in required:
            if name.lower() not in existing_lower:
                try:
                    self.sheet.add_worksheet(title=name, rows=1000, cols=20)
                    log.info(f"📊 Created sheet: {name}")
                    existing_lower[name.lower()] = name
                except Exception as e:
                    log.warning(f"Could not create {name}: {e}")
        
        self.setup_headers()
        self.fix_daily_logs_duplicates()

    def fix_daily_logs_duplicates(self):
        if not self.sheet:
            return
        try:
            ws = self.sheet.worksheet("Daily_Logs")
            all_rows = ws.get_all_values()
            if len(all_rows) <= 2:
                return
            header = all_rows[0]
            data_rows = all_rows[1:]
            seen = {}
            for i, row in enumerate(data_rows):
                if row and row[0]:
                    seen[row[0]] = i
            unique_rows = [data_rows[i] for i in sorted(seen.values())]
            if len(unique_rows) < len(data_rows):
                ws.batch_clear(["A2:Z1000"])
                if unique_rows:
                    ws.update(f'A2:Z{len(unique_rows)+1}', unique_rows)
                log.info(f"🧹 Daily_Logs deduplicated: {len(data_rows)} → {len(unique_rows)} rows")
        except Exception as e:
            log.warning(f"Daily_Logs dedup error: {e}")
    
    def setup_headers(self):
        if not self.sheet:
            return
        
        headers_config = {
            "Tasks": ["ID", "Title", "Priority", "Status", "Created At", "Completed At"],
            "Reminders": ["ID", "Time (HH:MM)", "Text", "Repeat", "Status", "Created Date", "Fired Today", "Created At"],
            "Expenses": ["Date", "Amount (Rs)", "Description", "Category", "Time"],
            "Habits": ["ID", "Habit Name", "Emoji", "Current Streak", "Best Streak", "Created"],
            "Water": ["Date", "Total ML", "Goal ML", "Percentage", "Entries Count"],
            "Memory": ["Date", "Fact", "Type"],
            "Daily_Logs": ["Date", "Day", "Tasks Done", "Tasks Pending", "Expenses (Rs)", "Water (ml)", "Habits Done", "Mood", "Notes"],
            "Goals": ["ID", "Title", "Progress %", "Status", "Deadline", "Created"],
            "Bills": ["ID", "Name", "Amount", "Due Day", "Paid Status", "Created"],
            "Calendar": ["ID", "Title", "Date", "Time", "Created"],
            "Diary":    ["Date", "Time", "Mood", "Entry Text"]
        }
        
        for sheet_name, headers in headers_config.items():
            try:
                ws = self.sheet.worksheet(sheet_name)
                first_row = ws.row_values(1)
                if not first_row or not any(first_row):
                    ws.update('A1', [headers])
                    log.info(f"📝 Headers set for {sheet_name}")
            except Exception as e:
                log.warning(f"Headers setup failed for {sheet_name}: {e}")
    
    def _upsert_rows(self, ws, new_rows, id_col=0):
        try:
            existing = ws.get_all_values()
            key_to_row = {}
            for i, row in enumerate(existing[1:], start=2):
                if row and len(row) > abs(id_col):
                    key = str(row[id_col]).strip()
                    if key:
                        key_to_row[key] = i

            updates = []
            appends = []

            for row in new_rows:
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

            return len(updates), len(appends)
        except Exception as e:
            log.error(f"Upsert error: {e}")
            return 0, 0

    def save_tasks(self, tasks_list):
        if not self.sheet or not tasks_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Tasks")
            rows = [
                [str(t.get("id","")), t.get("title",""), t.get("priority","medium"),
                 "Done" if t.get("done") else "Pending",
                 t.get("created","")[:10], t.get("done_at","")[:10] if t.get("done_at") else ""]
                for t in tasks_list
            ]
            u, a = self._upsert_rows(ws, rows, id_col=0)
            log.info(f"📋 Tasks: {u} updated, {a} new")
            return True
        except Exception as e:
            log.error(f"Tasks save error: {e}")
            return False

    def save_reminders(self, reminders_list):
        if not self.sheet or not reminders_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Reminders")
            rows = [
                [str(r.get("id","")), r.get("time",""), r.get("text",""),
                 r.get("repeat","once"), "Active" if r.get("active") else "Inactive",
                 r.get("date",""), "Yes" if r.get("fired_today") else "No",
                 r.get("created","")[:16] if r.get("created") else ""]
                for r in reminders_list
            ]
            u, a = self._upsert_rows(ws, rows, id_col=0)
            log.info(f"⏰ Reminders: {u} updated, {a} new")
            return True
        except Exception as e:
            log.error(f"Reminders save error: {e}")
            return False

    def save_expenses(self, expenses_list):
        if not self.sheet or not expenses_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Expenses")
            existing = ws.get_all_values()
            existing_keys = set()
            for row in existing[1:]:
                if len(row) >= 5:
                    existing_keys.add(f"{row[0]}|{row[1]}|{row[2]}")
            new_rows = []
            for e in expenses_list:
                key = f"{e.get('date','')}|{e.get('amount','')}|{e.get('desc','')}"
                if key not in existing_keys:
                    new_rows.append([e.get("date",""), e.get("amount",0),
                                     e.get("desc",""), e.get("category","general"), e.get("time","")])
                    existing_keys.add(key)
            for row in new_rows:
                ws.append_row(row, value_input_option="USER_ENTERED")
            if new_rows:
                log.info(f"💰 Expenses: {len(new_rows)} new rows added")
            return True
        except Exception as e:
            log.error(f"Expenses save error: {e}")
            return False

    def save_habits(self, habits_list):
        if not self.sheet or not habits_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Habits")
            rows = [[str(h.get("id","")), h.get("name",""), h.get("emoji","OK"),
                     h.get("streak",0), h.get("best_streak",0), h.get("created","")] for h in habits_list]
            u, a = self._upsert_rows(ws, rows, id_col=0)
            log.info(f"💪 Habits: {u} updated, {a} new")
            return True
        except Exception as e:
            log.error(f"Habits save error: {e}")
            return False

    def save_memory(self, memory_facts):
        if not self.sheet or not memory_facts:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Memory")
            existing = ws.get_all_values()
            existing_facts = {row[1] for row in existing[1:] if len(row) > 1}
            new_rows = []
            for f in memory_facts:
                fact_text = f.get("f","")
                if fact_text and fact_text not in existing_facts:
                    new_rows.append([f.get("d",""), fact_text, "fact"])
                    existing_facts.add(fact_text)
            for row in new_rows:
                ws.append_row(row, value_input_option="USER_ENTERED")
            if new_rows:
                log.info(f"🧠 Memory: {len(new_rows)} new facts added")
            return True
        except Exception as e:
            log.error(f"Memory save error: {e}")
            return False

    def save_goals(self, goals_list):
        if not self.sheet or not goals_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Goals")
            rows = [[str(g.get("id","")), g.get("title",""), g.get("progress",0),
                     "Done" if g.get("done") else "Active", g.get("deadline",""), g.get("created","")] for g in goals_list]
            u, a = self._upsert_rows(ws, rows, id_col=0)
            log.info(f"🎯 Goals: {u} updated, {a} new")
            return True
        except Exception as e:
            log.error(f"Goals save error: {e}")
            return False

    def save_bills(self, bills_list):
        if not self.sheet or not bills_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Bills")
            rows = [[str(b.get("id","")), b.get("name",""), b.get("amount",0),
                     b.get("due_day",""), "Paid" if bills.is_paid_this_month(b["id"]) else "Pending",
                     b.get("created","")] for b in bills_list]
            u, a = self._upsert_rows(ws, rows, id_col=0)
            log.info(f"💳 Bills: {u} updated, {a} new")
            return True
        except Exception as e:
            log.error(f"Bills save error: {e}")
            return False

    def save_calendar(self, events_list):
        if not self.sheet or not events_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Calendar")
            rows = [[str(e.get("id","")), e.get("title",""), e.get("date",""),
                     e.get("time",""), e.get("created","")] for e in events_list]
            u, a = self._upsert_rows(ws, rows, id_col=0)
            log.info(f"📅 Calendar: {u} updated, {a} new")
            return True
        except Exception as e:
            log.error(f"Calendar save error: {e}")
            return False

    def save_water(self, water_store_obj):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Water")
            goal = water_store_obj.goal()
            week = water_store_obj.week_summary()
            rows = []
            for d, total_ml in sorted(week.items()):
                pct = int(total_ml / goal * 100) if goal else 0
                ents = water_store_obj.get_by_date(d)
                rows.append([d, total_ml, goal, f"{pct}%", len(ents)])
            if rows:
                u, a = self._upsert_rows(ws, rows, id_col=0)
                log.info(f"💧 Water: {u} updated, {a} new")
            return True
        except Exception as e:
            log.error(f"Water save error: {e}")
            return False

    def save_diary(self, all_entries_dict):
        if not self.sheet or not all_entries_dict:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Diary")
            existing = ws.get_all_values()
            existing_keys = set()
            for row in existing[1:]:
                if len(row) >= 1 and row[0]:
                    text_col = row[3][:50] if len(row) > 3 else ""
                    existing_keys.add(f"{row[0]}|{row[1] if len(row)>1 else ''}|{text_col}")
            new_rows = []
            for entry_date in sorted(all_entries_dict.keys()):
                for entry in all_entries_dict[entry_date]:
                    text_key = entry.get("text", "")[:50]
                    key = f"{entry_date}|{entry.get('time','')}|{text_key}"
                    if key not in existing_keys:
                        new_rows.append([entry_date, entry.get("time",""),
                                         entry.get("mood","📝"), entry.get("text","")])
                        existing_keys.add(key)
            for row in new_rows:
                ws.append_row(row, value_input_option="USER_ENTERED")
            if new_rows:
                log.info(f"📖 Diary: {len(new_rows)} new entries added to Sheets")
            return True
        except Exception as e:
            log.error(f"Diary save error: {e}")
            return False

    def save_daily_log(self):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Daily_Logs")
            today = today_str()
            now = now_ist()
            day_name = now.strftime("%A")

            tasks_done     = len(tasks.done_on(today))
            tasks_pending  = len(tasks.today_pending())
            expenses_total = expenses.today_total()
            water_total    = water.today_total()
            habits_done    = len(habits.today_status()[0])

            new_row = [today, day_name, tasks_done, tasks_pending,
                       expenses_total, water_total, habits_done, "", ""]

            all_values = ws.get_all_values()
            today_row_idx = None
            for idx, row in enumerate(all_values):
                if row and row[0] == today:
                    today_row_idx = idx + 1
                    break

            if today_row_idx:
                ws.update(f'A{today_row_idx}:I{today_row_idx}', [new_row])
                log.info(f"📅 Daily log UPDATED for {today} (row {today_row_idx})")
            else:
                ws.append_row(new_row)
                log.info(f"📅 Daily log ADDED for {today}")
            return True
        except Exception as e:
            log.error(f"Daily log error: {e}")
            return False
    
    def full_sync(self):
        if not self.sheet:
            return "❌ Google Sheets not connected!"
        
        success_count = 0
        errors = []

        ops = [
            ("Tasks",     lambda: self.save_tasks(tasks.all_tasks())),
            ("Reminders", lambda: self.save_reminders(reminders.get_all())),
            ("Expenses",  lambda: self.save_expenses(expenses.store.data.get("list", []))),
            ("Habits",    lambda: self.save_habits(habits.all())),
            ("Memory",    lambda: self.save_memory(memory.get_all_facts())),
            ("Goals",     lambda: self.save_goals(goals.active() + goals.completed())),
            ("Bills",     lambda: self.save_bills(bills.all_active())),
            ("Calendar",  lambda: self.save_calendar(calendar.store.data.get("events", []))),
            ("Water",     lambda: self.save_water(water)),
            ("Daily_Log", lambda: self.save_daily_log()),
            ("Diary",     lambda: self.save_diary(diary.get_all_entries())),
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

    def restore_from_sheets(self):
        if not self.sheet:
            log.warning("⚠️ Cannot restore — Google Sheets not connected!")
            return False

        restored = []
        log.info("🔄 Restoring data from Google Sheets...")

        try:
            ws = self.sheet.worksheet("Tasks")
            rows = ws.get_all_records()
            task_list = []
            for r in rows:
                if not r.get("ID") and not r.get("Title"):
                    continue
                task_list.append({
                    "id": int(r["ID"]) if str(r.get("ID","")).isdigit() else 0,
                    "title": r.get("Title", ""),
                    "priority": r.get("Priority", "medium"),
                    "done": r.get("Status", "") == "Done",
                    "created": r.get("Created At", today_str()),
                    "done_at": r.get("Completed At", ""),
                })
            if task_list:
                max_id = max((t["id"] for t in task_list), default=0)
                db.save("tasks", {"list": task_list, "counter": max_id, "failed": []})
                restored.append(f"📋 {len(task_list)} tasks")
        except Exception as e:
            log.warning(f"Tasks restore failed: {e}")

        try:
            ws = self.sheet.worksheet("Reminders")
            rows = ws.get_all_records()
            rem_list = []
            for r in rows:
                if not r.get("ID") and not r.get("Text"):
                    continue
                rem_list.append({
                    "id": int(r["ID"]) if str(r.get("ID","")).isdigit() else 0,
                    "time": r.get("Time (HH:MM)", ""),
                    "text": r.get("Text", ""),
                    "repeat": r.get("Repeat", "once"),
                    "active": r.get("Status", "Active") == "Active",
                    "fired_today": False,
                    "date": r.get("Created Date", today_str()),
                    "created": r.get("Created At", ""),
                    "chat_id": int(os.environ.get("ADMIN_CHAT_ID", 0)),
                })
            if rem_list:
                max_id = max((r["id"] for r in rem_list), default=0)
                db.save("reminders", {"list": rem_list, "counter": max_id})
                restored.append(f"⏰ {len(rem_list)} reminders")
        except Exception as e:
            log.warning(f"Reminders restore failed: {e}")

        try:
            ws = self.sheet.worksheet("Diary")
            rows = ws.get_all_records()
            entries = {}
            for r in rows:
                d = r.get("Date", "")
                if not d:
                    continue
                entries.setdefault(d, [])
                entries[d].append({
                    "text": r.get("Entry Text", ""),
                    "mood": r.get("Mood", "📝"),
                    "time": r.get("Time", ""),
                })
            if entries:
                db.save("diary", {"entries": entries})
                total = sum(len(v) for v in entries.values())
                restored.append(f"📖 {total} diary entries")
        except Exception as e:
            log.warning(f"Diary restore failed: {e}")

        try:
            ws = self.sheet.worksheet("Expenses")
            rows = ws.get_all_records()
            exp_list = []
            for r in rows:
                if not r.get("Amount (Rs)") and not r.get("Description"):
                    continue
                exp_list.append({
                    "date": r.get("Date", today_str()),
                    "amount": float(r.get("Amount (Rs)", 0) or 0),
                    "desc": r.get("Description", ""),
                    "category": r.get("Category", "general"),
                    "time": r.get("Time", ""),
                })
            if exp_list:
                db.save("expenses", {"list": exp_list, "budget": None})
                restored.append(f"💰 {len(exp_list)} expenses")
        except Exception as e:
            log.warning(f"Expenses restore failed: {e}")

        try:
            ws = self.sheet.worksheet("Habits")
            rows = ws.get_all_records()
            hab_list = []
            for r in rows:
                if not r.get("Habit Name"):
                    continue
                hab_list.append({
                    "id": int(r["ID"]) if str(r.get("ID","")).isdigit() else 0,
                    "name": r.get("Habit Name", ""),
                    "emoji": r.get("Emoji", "✅"),
                    "streak": int(r.get("Current Streak", 0) or 0),
                    "best_streak": int(r.get("Best Streak", 0) or 0),
                    "created": r.get("Created", today_str()),
                })
            if hab_list:
                max_id = max((h["id"] for h in hab_list), default=0)
                db.save("habits", {"list": hab_list, "logs": {}, "counter": max_id})
                restored.append(f"💪 {len(hab_list)} habits")
        except Exception as e:
            log.warning(f"Habits restore failed: {e}")

        try:
            ws = self.sheet.worksheet("Memory")
            rows = ws.get_all_records()
            facts = []
            for r in rows:
                if r.get("Fact"):
                    facts.append({"d": r.get("Date",""), "f": r.get("Fact","")})
            if facts:
                db.save("memory", {"facts": facts, "prefs": {}, "important": [], "dates": {}})
                restored.append(f"🧠 {len(facts)} memories")
        except Exception as e:
            log.warning(f"Memory restore failed: {e}")

        try:
            ws = self.sheet.worksheet("Goals")
            rows = ws.get_all_records()
            goal_list = []
            for r in rows:
                if not r.get("Title"):
                    continue
                goal_list.append({
                    "id": int(r["ID"]) if str(r.get("ID","")).isdigit() else 0,
                    "title": r.get("Title",""),
                    "progress": int(r.get("Progress %", 0) or 0),
                    "done": r.get("Status","") == "Done",
                    "deadline": r.get("Deadline",""),
                    "created": r.get("Created",""),
                })
            if goal_list:
                max_id = max((g["id"] for g in goal_list), default=0)
                db.save("goals", {"list": goal_list, "counter": max_id})
                restored.append(f"🎯 {len(goal_list)} goals")
        except Exception as e:
            log.warning(f"Goals restore failed: {e}")

        try:
            ws = self.sheet.worksheet("Bills")
            rows = ws.get_all_records()
            bill_list = []
            for r in rows:
                if not r.get("Name"):
                    continue
                bill_list.append({
                    "id": int(r["ID"]) if str(r.get("ID","")).isdigit() else 0,
                    "name": r.get("Name",""),
                    "amount": float(r.get("Amount",0) or 0),
                    "due_day": int(r.get("Due Day",1) or 1),
                    "active": True,
                    "created": r.get("Created",""),
                })
            if bill_list:
                max_id = max((b["id"] for b in bill_list), default=0)
                db.save("bills", {"list": bill_list, "paid": {}, "counter": max_id})
                restored.append(f"💳 {len(bill_list)} bills")
        except Exception as e:
            log.warning(f"Bills restore failed: {e}")

        try:
            ws = self.sheet.worksheet("Calendar")
            rows = ws.get_all_records()
            ev_list = []
            for r in rows:
                if not r.get("Title"):
                    continue
                ev_list.append({
                    "id": int(r["ID"]) if str(r.get("ID","")).isdigit() else 0,
                    "title": r.get("Title",""),
                    "date": r.get("Date",""),
                    "time": r.get("Time",""),
                    "created": r.get("Created",""),
                })
            if ev_list:
                max_id = max((e["id"] for e in ev_list), default=0)
                db.save("calendar", {"events": ev_list, "counter": max_id})
                restored.append(f"📅 {len(ev_list)} events")
        except Exception as e:
            log.warning(f"Calendar restore failed: {e}")

        if restored:
            log.info(f"✅ Restored from Sheets: {' | '.join(restored)}")
        else:
            log.info("📋 Nothing to restore (sheets empty or first run)")
        return True

google_sheets = GoogleSheetsBackup()

def restore_all_from_sheets():
    if not google_sheets.sheet:
        log.warning("⚠️ Sheets not connected — cannot restore data!")
        return

    log.info("🔄 Loading all data from Google Sheets...")
    google_sheets.restore_from_sheets()

    tasks_data = db.load("tasks", {"list": [], "counter": 0, "failed": []})
    if tasks_data.get("list"):
        tasks_data["counter"] = max((t.get("id",0) for t in tasks_data["list"]), default=0)
    tasks.store.data = tasks_data

    rem_data = db.load("reminders", {"list": [], "counter": 0})
    if rem_data.get("list"):
        rem_data["counter"] = max((r.get("id",0) for r in rem_data["list"]), default=0)
    reminders.store.data = rem_data

    diary.store.data    = db.load("diary",    {"entries": {}})

    exp_data = db.load("expenses", {"list": [], "budget": None, "counter": 0})
    if exp_data.get("list") and not exp_data.get("counter"):
        exp_data["counter"] = len(exp_data["list"])
    expenses.store.data = exp_data

    hab_data = db.load("habits", {"list": [], "logs": {}, "counter": 0})
    if hab_data.get("list"):
        hab_data["counter"] = max((h.get("id",0) for h in hab_data["list"]), default=0)
    habits.store.data = hab_data

    memory.store.data   = db.load("memory",   {"facts": [], "prefs": {}, "important": [], "dates": {}})

    goal_data = db.load("goals", {"list": [], "counter": 0})
    if goal_data.get("list"):
        goal_data["counter"] = max((g.get("id",0) for g in goal_data["list"]), default=0)
    goals.store.data = goal_data

    bill_data = db.load("bills", {"list": [], "paid": {}, "counter": 0})
    if bill_data.get("list"):
        bill_data["counter"] = max((b.get("id",0) for b in bill_data["list"]), default=0)
    bills.store.data = bill_data

    cal_data = db.load("calendar", {"events": [], "counter": 0})
    if cal_data.get("events"):
        cal_data["counter"] = max((e.get("id",0) for e in cal_data["events"]), default=0)
    calendar.store.data = cal_data

    log.info("✅ All stores reloaded from Sheets backup — counters fixed!")

restore_all_from_sheets()

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
# ✅ IMPROVED SMART ACTION SYSTEM
# ═══════════════════════════════════════════════════════════════════

ACTION_SYSTEM_PROMPT = """You are a JSON router. Parse user message and return ONLY raw JSON (no markdown, no backticks).

Current EXACT time: {now}
24hr time: {current_time}
Today: {today}
2 min from now: {two_min}

JSON format: {{"action":"ACTION","params":{{...}},"reply":"confirm msg"}}

ACTIONS:
REMIND — {{"time":"HH:MM","text":"...","repeat":"once"}} (Only if user EXPLICITLY asks for reminder/alarm)
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
CHAT — {{}} (default for greetings, questions, casual talk - NOT reminder)
"""

def _regex_fallback(user_msg):
    """✅ Improved regex fallback - more accurate action detection"""
    lower = user_msg.lower().strip()
    now = now_ist()
    
    # ✅ Only set reminder if EXPLICITLY asked
    remind_explicit = [
        "remind me", "remind me to", "set reminder", "set alarm", "yaad dila", 
        "alarm laga", "reminder set", "notify me", "yaad dilana", "yaad dilao",
        "alarm set karo", "reminder laga", "reminder create"
    ]
    
    is_explicit_reminder = any(r in lower for r in remind_explicit)
    
    has_time = bool(_re.search(r'(\d{1,2}):(\d{2})', lower))
    has_minutes = bool(_re.search(r'(\d+)\s*(?:minute|min|mins)', lower))
    has_hours = bool(_re.search(r'(\d+)\s*(?:ghante|ghanta|hour|hr)', lower))
    has_baje = bool(_re.search(r'(\d{1,2})\s*(?:baje|baj)', lower))
    
    time_keywords = ["baje", "minute", "min", "ghante", "hour", "alarm", "remind", "notify"]
    has_time_keyword = any(k in lower for k in time_keywords)
    
    should_remind = is_explicit_reminder or ((has_time or has_minutes or has_hours or has_baje) and has_time_keyword)
    
    if should_remind:
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
                elif 'subah' in lower or 'savere' in lower:
                    h = h if h < 12 else h - 12
                else:
                    h = h + 12 if 1 <= h <= 6 else h
                time_str = f"{h:02d}:00"
        
        if time_str:
            text = user_msg
            text = _re.sub(r'\d+\s*(?:minute|min|mins|ghante|ghanta|hour|hr)', '', text, flags=_re.I)
            text = _re.sub(r'\d{1,2}(?::\d{2})?\s*(?:baje|baj)?', '', text, flags=_re.I)
            for kw in remind_explicit + ["baad", "mein", "ke liye", "set karo", "laga do"]:
                text = text.replace(kw, '')
            text = ' '.join(text.split())
            
            if not text or len(text) < 2:
                text = "⏰ Reminder!"
            
            return {
                "action": "REMIND", 
                "params": {
                    "time": time_str, 
                    "text": text[:100], 
                    "repeat": "daily" if "daily" in lower or "roz" in lower else 
                             "weekly" if "weekly" in lower or "hafte" in lower else "once"
                }, 
                "reply": ""
            }
    
    # ✅ Task detection
    task_words = [
        "task add", "add task", "karna hai", "kaam add", "new task", 
        "todo add", "to-do add", "task create", "kaam hai mujhe"
    ]
    if any(t in lower for t in task_words):
        title = _re.sub(r'(task add|add task|karna hai|kaam add|new task|todo add|to-do add|task create|kaam hai mujhe)', '', user_msg, flags=_re.I).strip()
        if title:
            return {"action": "ADD_TASK", "params": {"title": title[:80], "priority": "medium"}, "reply": ""}
    
    # ✅ Expense detection
    if any(w in lower for w in ["kharcha add", "add expense", "rs ", "rupaye kharch", "spent", "kharch kiya", "paise diye"]):
        m = _re.search(r'(\d+)', lower)
        amount = float(m.group(1)) if m else 0
        if amount > 0:
            return {"action": "ADD_EXPENSE", "params": {"amount": amount, "desc": user_msg[:60], "category": "general"}, "reply": ""}
    
    # ✅ Diary detection
    if any(w in lower for w in ["diary likh", "journal entry", "aaj ka din", "diary add"]):
        return {"action": "ADD_DIARY", "params": {"text": user_msg[:200], "mood": "📝"}, "reply": ""}
    
    # Default: CHAT
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
        diary.add(params.get("text", user_msg[:100]), params.get("mood", "😊"))
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
        return get_ai_reply(user_msg)

# ═══════════════════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════════════════
def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]])

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Briefing", callback_data="briefing"), InlineKeyboardButton("📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("💪 Habits", callback_data="habits"), InlineKeyboardButton("📖 Write Diary", callback_data="diary_write")],
        [InlineKeyboardButton("🎯 Goals", callback_data="goals"), InlineKeyboardButton("💰 Kharcha", callback_data="expenses")],
        [InlineKeyboardButton("📰 News", callback_data="news_menu"), InlineKeyboardButton("📝 Notes", callback_data="notes")],
        [InlineKeyboardButton("💧 Water", callback_data="water_status"), InlineKeyboardButton("💳 Bills", callback_data="bills_menu")],
        [InlineKeyboardButton("📅 Calendar", callback_data="cal_menu"), InlineKeyboardButton("📊 Weekly", callback_data="weekly_report")],
        [InlineKeyboardButton("📋 All Tasks", callback_data="all_tasks"), InlineKeyboardButton("✅ Completed", callback_data="completed_tasks")],
        [InlineKeyboardButton("🧹 Clear Chat", callback_data="clear_chat"), InlineKeyboardButton("🧠 Memory", callback_data="memory")],
        [InlineKeyboardButton("📊 Yesterday", callback_data="yesterday"), InlineKeyboardButton("💡 Motivate", callback_data="motivate")],
        [InlineKeyboardButton("📤 Backup to Sheets", callback_data="backup_now"), InlineKeyboardButton("📅 Report", callback_data="report_menu")],
    ])

def news_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇳 India", callback_data="news_India"), InlineKeyboardButton("💻 Tech", callback_data="news_Technology")],
        [InlineKeyboardButton("💼 Business", callback_data="news_Business"), InlineKeyboardButton("🌍 World", callback_data="news_World")],
        [InlineKeyboardButton("🏏 Sports", callback_data="news_Sports"), InlineKeyboardButton("🏠 Back", callback_data="menu")],
    ])

# ═══════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════
async def cmd_start(update, ctx):
    n = now_ist()
    name = update.effective_user.first_name or "Dost"
    db_status = "✅ Google Sheets — Data permanent hai!" if google_sheets.sheet else "⚠️ Sheets not connected — data temporary hai!"
    await update.message.reply_text(
        f"🕌 *Assalamualaikum {name}!*\n\n⏰ {n.strftime('%I:%M %p')} IST | 📅 {n.strftime('%d %b %Y')}\n\n"
        f"💾 *{db_status}*\n\n"
        "📋 Tasks | 💪 Habits | 📖 Diary\n"
        "💰 Expenses | ⏰ Reminders | 📰 News\n💧 Water | 💳 Bills | 📅 Calendar\n"
        "📤 Auto-backup to Google Sheets\n\n"
        "_Seedha type karo ya /help_ 👇", parse_mode="Markdown", reply_markup=main_kb())

async def cmd_hello(update, ctx):
    """✅ Dedicated hello command - always works"""
    name = update.effective_user.first_name or "Dost"
    n = now_ist()
    await update.message.reply_text(
        f"🕌 *Assalamualaikum {name}!*\n\n"
        f"⏰ {n.strftime('%I:%M %p')} IST | 📅 {n.strftime('%d %b %Y')}\n\n"
        f"Main aapka AI assistant hoon, ready to help!\n\n"
        f"🗣 *Bolo kya karna hai:*\n"
        f"• Task ya reminder set karna?\n"
        f"• Kharcha note karna?\n"
        f"• Diary likhni hai?\n"
        f"• Ya bas baat karni hai? 😊\n\n"
        f"_Seedha type karo, main samjhunga!_ 👇",
        parse_mode="Markdown",
        reply_markup=main_kb()
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
        "`/hello` — Quick greeting\n"
        "`/clear` `/nuke` — Cleanup\n"
        "`/backup` — Manual backup to Google Sheets\n\n"
        "_Seedha type karo — AI jawab dega!_", parse_mode="Markdown")

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
    if not ctx.args:
        await update.message.reply_text("`/deltask <id>`")
        return
    try:
        if tasks.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Deleted!")
        else:
            await update.message.reply_text("❌ Not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_diary(update, ctx):
    args = ctx.args

    if args and args[0] not in ("date", "all", "week"):
        text = " ".join(args)
        diary.add(text, mood="📝")
        await update.message.reply_text(
            f"📖 *Diary saved!* 🕐 {now_str()}\n\n_{text[:120]}_",
            parse_mode="Markdown"
        )
        await auto_backup_to_sheets()
        return ConversationHandler.END

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
    except Exception:
        pass
    return ConversationHandler.END

async def _show_diary(update, view_type, view_arg):
    if view_type == "today":
        entries = diary.get(today_str())
        title = f"📖 *Aaj Ki Diary — {today_str()}*"
        all_entries = {today_str(): entries} if entries else {}

    elif view_type == "date":
        d = view_arg or today_str()
        entries = diary.get(d)
        title = f"📖 *Diary — {d}*"
        all_entries = {d: entries} if entries else {}

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
        for e in entries:
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

    for i, chunk in enumerate(chunks):
        kb = back_kb() if i == len(chunks) - 1 else None
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown", reply_markup=kb)
        except:
            await update.message.reply_text(chunk, reply_markup=kb)

async def cmd_diary_view(update, ctx):
    arg = ctx.args[0] if ctx.args else "today"
    if arg == "week":
        ctx.user_data["diary_view"] = ("week", None)
    elif arg == "all":
        ctx.user_data["diary_view"] = ("all", None)
    elif len(arg) == 10 and arg[4] == "-":
        ctx.user_data["diary_view"] = ("date", arg)
    else:
        ctx.user_data["diary_view"] = ("today", None)

    await update.message.reply_text(
        "🔐 *Diary — Password Enter Karo:*",
        parse_mode="Markdown"
    )
    return DIARY_AWAIT_PASS

async def cmd_habit(update, ctx):
    if not ctx.args:
        await update.message.reply_text("💪 `/habit Naam`")
        return
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
    if not ctx.args:
        await update.message.reply_text("`/delhabit <id>`")
        return
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
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        await update.message.reply_text(f"💰 ₹{amount:.0f} — {desc}\n📊 Aaj: ₹{expenses.today_total():.0f}", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Format: `/kharcha 100 Chai`")

async def cmd_budget(update, ctx):
    if not ctx.args:
        await update.message.reply_text("💳 `/budget 5000`")
        return
    try:
        expenses.set_budget(float(ctx.args[0]))
        await update.message.reply_text(f"💳 Budget: ₹{ctx.args[0]}")
        await auto_backup_to_sheets()
    except:
        pass

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
    if len(ctx.args) < 2:
        await update.message.reply_text("📊 `/gprogress <goal_id> <progress_percentage>`\nExample: `/gprogress 1 50`")
        return
    try:
        gid = int(ctx.args[0])
        progress = int(ctx.args[1])
        g = goals.update_progress(gid, progress)
        if g:
            bar = "█" * (g['progress'] // 10) + "░" * (10 - (g['progress'] // 10))
            await update.message.reply_text(f"📊 *{g['title']}*\n`{bar}` {g['progress']}% complete!", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Goal not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Use: `/gprogress <goal_id> <percentage>`")

async def cmd_remember(update, ctx):
    if not ctx.args:
        await update.message.reply_text("🧠 `/remember Text`")
        return
    memory.add_fact(" ".join(ctx.args))
    await update.message.reply_text("🧠 Yaad kar liya! ✅")
    await auto_backup_to_sheets()

async def cmd_recall(update, ctx):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("🧠 Kuch yaad nahi.")
        return
    txt = "🧠 *YAADDASHT*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-10:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_note(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📝 `/note Text`")
        return
    n = notes.add(" ".join(ctx.args))
    await update.message.reply_text(f"📝 Note #{n['id']} saved!")
    await auto_backup_to_sheets()

async def cmd_delnote(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delnote <id>`")
        return
    try:
        if notes.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Deleted!")
        else:
            await update.message.reply_text("❌ Not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def _build_briefing_text():
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    n = now_ist()
    txt = f"🌅 *BRIEFING*\n⏰ {n.strftime('%I:%M %p')} | 📅 {n.strftime('%d %b')}\n\n"
    if tp:
        txt += f"📋 *Pending ({len(tp)}):*\n" + "".join(f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}\n" for t in tp[:5])
    else:
        txt += "🎉 No pending tasks!\n"
    if hp:
        txt += f"\n💪 Habits left: {', '.join(h['name'] for h in hp[:4])}"
    txt += f"\n\n💰 Aaj: ₹{expenses.today_total():.0f} | Mahina: ₹{expenses.month_total():.0f}"
    bl = expenses.budget_left()
    if bl is not None:
        txt += f" | Budget: ₹{bl:.0f}"
    w_t = water.today_total()
    w_g = water.goal()
    txt += f"\n💧 Water: {w_t}ml/{w_g}ml"
    return txt

async def cmd_briefing(update, ctx):
    txt = await _build_briefing_text()
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_weekly(update, ctx):
    n = now_ist()
    week_start = n.date() - timedelta(days=n.weekday())
    
    msg = f"📊 *WEEKLY REPORT*\n"
    msg += f"📅 {week_start.strftime('%d %b')} - {n.strftime('%d %b %Y')}\n\n"
    
    task_weekly = tasks.get_weekly_summary()
    total_done = sum(v["done"] for v in task_weekly.values())
    total_created = sum(v["created"] for v in task_weekly.values())
    msg += f"📋 *TASKS*\n"
    msg += f"   ✅ Completed this week: {total_done}\n"
    msg += f"   ➕ Created this week: {total_created}\n"
    msg += f"   ⏳ Currently pending: {len(tasks.pending())}\n\n"
    
    msg += f"💪 *HABITS*\n"
    habits_list = habits.all()
    if habits_list:
        for h in habits_list:
            msg += f"   {h['emoji']} {h['name']} — 🔥 Streak: {h.get('streak', 0)} days\n"
    else:
        msg += "   No habits added yet\n"
    msg += "\n"
    
    msg += f"💰 *EXPENSES*\n"
    msg += f"   This month total: ₹{expenses.month_total():.0f}\n"
    msg += f"   Today's expenses: ₹{expenses.today_total():.0f}\n"
    bl = expenses.budget_left()
    if bl is not None:
        msg += f"   Budget remaining: ₹{bl:.0f}\n"
    msg += "\n"
    
    msg += f"💧 *WATER INTAKE*\n"
    msg += f"   Today: {water.today_total()}ml / {water.goal()}ml\n"
    water_weekly = water.week_summary()
    total_water = sum(water_weekly.values())
    msg += f"   This week total: {total_water}ml\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_report(update, ctx):
    if not ctx.args:
        await update.message.reply_text(
            "📋 *DATE-WISE REPORT*\n\n"
            "`/report YYYY-MM-DD`\n"
            "Example: `/report 2026-04-28`",
            parse_mode="Markdown")
        return
    
    target_date = ctx.args[0]
    
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except:
        await update.message.reply_text("❌ Invalid date! Use: YYYY-MM-DD (e.g., 2026-04-28)")
        return
    
    msg = f"📋 *REPORT FOR {target_date}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    tasks_created = [t for t in tasks.all_tasks() if t.get("created", "")[:10] == target_date]
    tasks_done = tasks.done_on(target_date)
    
    msg += f"📋 *TASKS*\n"
    msg += f"   Created: {len(tasks_created)}\n"
    msg += f"   Completed: {len(tasks_done)}\n"
    if tasks_done:
        msg += f"   ✅ " + "\n      ".join(f"#{t['id']} {t['title'][:30]}" for t in tasks_done[:5]) + "\n"
    msg += "\n"
    
    reminders_on_date = reminders.get_by_date(target_date)
    msg += f"⏰ *REMINDERS SET ON {target_date}*\n"
    if reminders_on_date:
        for r in reminders_on_date:
            msg += f"   ⏰ {r['time']} — {r['text'][:40]}\n"
    else:
        msg += f"   No reminders set\n"
    msg += "\n"
    
    expenses_on_date = expenses.get_by_date(target_date)
    total_exp = sum(e["amount"] for e in expenses_on_date)
    msg += f"💰 *EXPENSES*\n"
    msg += f"   Total spent: ₹{total_exp:.0f}\n"
    if expenses_on_date:
        for e in expenses_on_date[:5]:
            msg += f"   • ₹{e['amount']:.0f} — {e['desc'][:25]}\n"
    msg += "\n"
    
    diary_entries = diary.get(target_date)
    if diary_entries:
        msg += f"📖 *DIARY ENTRY*\n"
        for entry in diary_entries[:3]:
            msg += f"   🕐 {entry['time']} — {entry['text'][:50]}\n"
    else:
        msg += f"📖 No diary entry\n"
    msg += "\n"
    
    logs = habits.store.data.get("logs", {})
    habits_done_ids = logs.get(target_date, [])
    habits_done = [h for h in habits.all() if h["id"] in habits_done_ids]
    msg += f"💪 *HABITS DONE*\n"
    if habits_done:
        msg += f"   ✅ " + ", ".join(f"{h['emoji']}{h['name']}" for h in habits_done) + "\n"
    else:
        msg += f"   No habits logged\n"
    msg += "\n"
    
    water_entries = water.get_by_date(target_date)
    total_water = sum(w["ml"] for w in water_entries)
    msg += f"💧 *WATER INTAKE*\n"
    msg += f"   Total: {total_water}ml\n"
    if water_entries:
        msg += f"   Entries: {len(water_entries)} times\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_news(update, ctx):
    await update.message.reply_text("📰 *Category:*", parse_mode="Markdown", reply_markup=news_kb())

async def cmd_clear(update, ctx):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Clear Chat History", callback_data="confirm_clear_chat"),
        InlineKeyboardButton("❌ Cancel", callback_data="menu")
    ]])
    await update.message.reply_text(
        f"🧹 *Clear chat history only?*\n\n"
        f"📋 Tasks: {len(tasks.all_tasks())} (safe)\n"
        f"⏰ Reminders: {len(reminders.all_active())} (safe)\n"
        f"💰 Kharcha: ₹{expenses.month_total():.0f} (safe)\n"
        f"💪 Habits: {len(habits.all())} (safe)\n\n"
        f"✅ *Reminders, tasks, kharcha, habits, diary — KUCH NAHI HATEGA*\n"
        f"❌ Sirf chat history delete hogi",
        parse_mode="Markdown",
        reply_markup=kb
    )

async def cmd_nuke(update, ctx):
    tracked = chat_hist.get_tracked_ids()
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💣 Delete Messages Only", callback_data="confirm_nuke"),
        InlineKeyboardButton("❌ Cancel", callback_data="menu")
    ]])
    sent = await update.message.reply_text(
        f"💣 *Delete {len(tracked)} Telegram messages?*\n\n"
        f"⚠️ *Sirf messages delete honge!*\n"
        f"✅ Tasks, Reminders, Kharcha, Habits — *SAFE RAHENGE*\n\n"
        f"Database data kisi ko delete nahi hoga.",
        parse_mode="Markdown",
        reply_markup=kb
    )
    chat_hist.track_msg(update.effective_chat.id, sent.message_id)

async def cmd_alltasks(update, ctx):
    all_t = tasks.all_tasks()
    if not all_t:
        await update.message.reply_text("📋 No tasks!")
        return
    p = tasks.pending()
    c = tasks.completed_tasks()
    txt = f"📋 *ALL TASKS*\n📊 Total: {len(all_t)} | ⏳ Pending: {len(p)} | ✅ Done: {len(c)}\n\n"
    if p:
        txt += "⏳ *PENDING:*\n" + "\n".join(f"   #{t['id']} {t['title']}" for t in p[:10])
        if len(p) > 10:
            txt += f"\n   ... and {len(p) - 10} more"
    if c:
        txt += "\n\n✅ *RECENTLY COMPLETED:*\n" + "\n".join(f"   #{t['id']} {t['title']}" for t in c[-5:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed(update, ctx):
    c = tasks.completed_tasks()
    if not c:
        await update.message.reply_text("✅ No completed tasks yet!")
        return
    txt = f"✅ *COMPLETED TASKS ({len(c)})*\n\n" + "\n".join(f"  ✓ #{t['id']} {t['title']} — {t.get('done_at', '')[:10]}" for t in c[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_yesterday(update, ctx):
    yd = yesterday_str()
    tasks_done = tasks.done_on(yd)
    expenses_yest = expenses.get_by_date(yd)
    diary_yest = diary.get(yd)
    habits_logs = habits.get_logs_by_date(yd)
    habits_done = [h for h in habits.all() if h["id"] in habits_logs]
    
    txt = f"📅 *YESTERDAY'S SUMMARY* ({yd})\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    txt += f"✅ *Tasks completed:* {len(tasks_done)}\n"
    if tasks_done:
        txt += "   " + "\n   ".join(f"• {t['title']}" for t in tasks_done[:5]) + "\n"
    else:
        txt += "   No tasks completed\n"
    txt += "\n"
    
    txt += f"💪 *Habits done:* {len(habits_done)}/{len(habits.all())}\n"
    if habits_done:
        txt += "   " + ", ".join(f"{h['emoji']}{h['name']}" for h in habits_done) + "\n"
    txt += "\n"
    
    txt += f"💰 *Expenses:* ₹{sum(e['amount'] for e in expenses_yest):.0f}\n"
    if expenses_yest:
        txt += "   " + "\n   ".join(f"• ₹{e['amount']:.0f} — {e['desc']}" for e in expenses_yest[:3]) + "\n"
    txt += "\n"
    
    if diary_yest:
        txt += f"📖 *Diary:*\n   {diary_yest[0]['text'][:60]}\n"
    
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_memory(update, ctx):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("🧠 No memories saved yet!")
        return
    txt = "🧠 *MY MEMORY*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for f in facts[-15:]:
        txt += f"📌 {f['f']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_dbstatus(update, ctx):
    lines = []
    if google_sheets.sheet:
        lines.append("✅ *Google Sheets: CONNECTED — Data permanent hai!*")
        lines.append("_Har restart ke baad Sheets se data reload hota hai_\n")
    else:
        lines.append("❌ *Google Sheets: NOT CONNECTED*")
        lines.append("_Data temporary hai — restart pe reset hoga!_")
        lines.append("_GOOGLE\\_CREDS\\_JSON secret check karo_\n")

    r = reminders.store.data.get("list", [])
    t = tasks.store.data.get("list", [])
    d_entries = sum(len(v) for v in diary.store.data.get("entries", {}).values())
    exp = expenses.store.data.get("list", [])
    hab = habits.store.data.get("list", [])

    lines.append("📊 *Current data (in memory + Sheets):*")
    lines.append(f"  ⏰ Reminders: {len(r)}")
    lines.append(f"  📋 Tasks: {len(t)}")
    lines.append(f"  📖 Diary entries: {d_entries}")
    lines.append(f"  💰 Expenses: {len(exp)}")
    lines.append(f"  💪 Habits: {len(hab)}")

    active_rem = [x for x in r if x.get("active")]
    if active_rem:
        lines.append(f"\n⏰ *Active reminders:*")
        for rem in active_rem[:5]:
            lines.append(f"  • {rem['time']} — {rem['text']}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_backup(update, ctx):
    await update.message.reply_text("📤 Backing up to Google Sheets...")
    result = google_sheets.full_sync()
    await update.message.reply_text(result)

async def cmd_remind(update, ctx):
    now = now_ist()
    if not ctx.args:
        await update.message.reply_text(
            f"⏰ *REMINDER*\nAbhi: *{now.strftime('%I:%M %p')} IST*\n\n"
            "`/remind 2m Test` — 2 min baad\n"
            "`/remind 30m Chai` — 30 min baad\n"
            "`/remind 15:30 Doctor` — exact time\n"
            "`/remind 8:00 Uthna daily` — daily\n"
            "`/remind 9:00 Meeting weekly` — weekly",
            parse_mode="Markdown")
        return
    
    time_arg = ctx.args[0].lower()
    rest = ctx.args[1:]
    repeat = "once"
    
    if rest and rest[-1].lower() in ["daily", "weekly"]:
        repeat = rest[-1].lower()
        rest = rest[:-1]
    
    text = " ".join(rest) if rest else "⏰ Reminder!"
    
    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        mins = int(time_arg[:-1])
        remind_at = (now + timedelta(minutes=mins)).strftime("%H:%M")
    elif time_arg.endswith("h") and time_arg[:-1].isdigit():
        hrs = int(time_arg[:-1])
        remind_at = (now + timedelta(hours=hrs)).strftime("%H:%M")
    elif ":" in time_arg:
        parts = time_arg.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                remind_at = f"{h:02d}:{m:02d}"
            else:
                await update.message.reply_text("❌ Invalid time! Use HH:MM (00:00 to 23:59)")
                return
        else:
            await update.message.reply_text("❌ Format galat! Use: `/remind 15:30 Meeting`")
            return
    else:
        await update.message.reply_text("❌ Format galat! Use: `/remind 2m Test` or `/remind 15:30 Meeting`")
        return
    
    r = reminders.add(update.effective_chat.id, text, remind_at, repeat)
    rl = {"once": "Once", "daily": "Daily 🔁", "weekly": "Weekly 📅"}.get(repeat, repeat)
    await update.message.reply_text(f"✅ *Reminder set!* ⏰ {remind_at} — {text}\n{rl}\n🆔 `#{r['id']}` | `/delremind {r['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_reminders_list(update, ctx):
    active = reminders.all_active()
    now = now_ist()
    if not active:
        await update.message.reply_text(f"⏰ No reminders!\nAbhi: *{now.strftime('%I:%M %p')}*\n`/remind 2m Test` se set karo", parse_mode="Markdown")
        return
    txt = f"⏰ *REMINDERS ({len(active)})*\nAbhi: *{now.strftime('%I:%M %p')} IST*\n\n"
    for r in active:
        icon = "🔁" if r["repeat"] == "daily" else "📅" if r["repeat"] == "weekly" else "1️⃣"
        txt += f"*#{r['id']}* {icon} `{r['time']}` — {r['text']} {'✅' if r['fired_today'] else '⏳'}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_delremind(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delremind <id>`\nUse `/reminders` to see all IDs")
        return
    try:
        if reminders.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Reminder deleted!")
        else:
            await update.message.reply_text("❌ Reminder not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID!")

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
    await update.message.reply_text(f"💧 +{ml}ml | Total: {total}ml/{goal}ml ({pct}%)", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💧 +250ml", callback_data="water_250"), InlineKeyboardButton("💧 +500ml", callback_data="water_500")]]))
    await auto_backup_to_sheets()

async def cmd_water_status(update, ctx):
    total = water.today_total()
    goal = water.goal()
    pct = min(100, int(total / goal * 100)) if goal else 0
    await update.message.reply_text(f"💧 {total}ml / {goal}ml ({pct}%)", parse_mode="Markdown")

async def cmd_water_goal(update, ctx):
    if not ctx.args:
        await update.message.reply_text(f"Current goal: {water.goal()}ml\n`/watergoal 2500` to change")
        return
    try:
        water.set_goal(int(ctx.args[0]))
        await update.message.reply_text(f"✅ Water goal set to {ctx.args[0]}ml")
    except:
        pass

async def cmd_bill(update, ctx):
    if not ctx.args or len(ctx.args) < 3:
        await update.message.reply_text("💳 `/bill Naam Amount DueDay`\nExample: `/bill Internet 999 15`")
        return
    try:
        b = bills.add(ctx.args[0], float(ctx.args[1]), int(ctx.args[2]))
        await update.message.reply_text(f"✅ Bill added: {b['name']} ₹{b['amount']:.0f} — Due on {b['due_day']}th of every month", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Format: `/bill Name Amount DueDay`")

async def cmd_bills_list(update, ctx):
    all_b = bills.all_active()
    if not all_b:
        await update.message.reply_text("💳 No bills added yet!\nUse `/bill` to add")
        return
    txt = "💳 *BILLS*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for b in all_b:
        status = "✅" if bills.is_paid_this_month(b["id"]) else "⏳ Pending"
        txt += f"{status} *{b['name']}* — ₹{b['amount']:.0f} (Due {b['due_day']}th)\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_bill_paid(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/billpaid <bill_id>`\nUse `/bills` to see IDs")
        return
    try:
        if bills.mark_paid(int(ctx.args[0])):
            await update.message.reply_text("✅ Bill marked as paid for this month!")
        else:
            await update.message.reply_text("❌ Already paid or bill not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid bill ID!")

async def cmd_del_bill(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delbill <bill_id>`")
        return
    try:
        if bills.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Bill deleted!")
        else:
            await update.message.reply_text("❌ Bill not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_cal(update, ctx):
    if not ctx.args:
        await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`\n`/cal kal Client call`\n`/cal aaj Doctor appointment`")
        return
    args_str = " ".join(ctx.args)
    date_str = None
    title = args_str
    event_time = ""
    
    m = _re.match(r'^(\d{4}-\d{2}-\d{2})\s+(.*)', args_str)
    if m:
        date_str = m.group(1)
        title = m.group(2)
    
    if not date_str:
        if args_str.lower().startswith("aaj "):
            date_str = today_str()
            title = args_str[4:]
        elif args_str.lower().startswith("kal "):
            date_str = (now_ist().date() + timedelta(days=1)).isoformat()
            title = args_str[4:]
    
    if not date_str:
        await update.message.reply_text("❌ Use: `/cal YYYY-MM-DD Event`\n`/cal aaj Meeting`\n`/cal kal Doctor`")
        return
    
    t_match = _re.search(r'(\d{1,2}:\d{2})', title)
    if t_match:
        event_time = t_match.group(1)
        title = title.replace(event_time, "").strip()
    
    try:
        date.fromisoformat(date_str)
        e = calendar.add(title, date_str, event_time)
        await update.message.reply_text(f"📅 Event added: {title} — {date_str}" + (f" ⏰{event_time}" if event_time else ""), parse_mode="Markdown")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid date! Use YYYY-MM-DD")

async def cmd_cal_list(update, ctx):
    upcoming = calendar.upcoming(30)
    if not upcoming:
        await update.message.reply_text("📅 No upcoming events!")
        return
    txt = "📅 *UPCOMING EVENTS*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for e in upcoming[:15]:
        today_flag = "🔴 TODAY" if e["date"] == today_str() else "📆"
        time_str = f" @ {e['time']}" if e.get("time") else ""
        txt += f"{today_flag} {e['date']}{time_str} — {e['title']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_del_cal(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delcal <event_id>`\nUse `/calendar` to see IDs")
        return
    try:
        if calendar.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Event deleted!")
        else:
            await update.message.reply_text("❌ Event not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID!")

# ═══════════════════════════════════════════════════════════════════
# SECRET COMMANDS
# ═══════════════════════════════════════════════════════════════════
async def verify_secret(update, ctx, action):
    if not ctx.args or ctx.args[0] != SECRET_CODE:
        await update.message.reply_text("🔒 Access denied!")
        return False
    return True

async def cmd_tasklogs(update, ctx):
    if not await verify_secret(update, ctx, "tasklogs"):
        return
    logs = task_logs.get_all_logs()
    if not logs:
        await update.message.reply_text("📋 No logs!")
        return
    by_date = defaultdict(list)
    for l in logs:
        by_date[l.get("date", "?")].append(l)
    txt = f"📋 *TASK LOGS ({len(logs)})*\n\n"
    for d in sorted(by_date.keys(), reverse=True)[:5]:
        txt += f"📅 *{d}*\n"
        for l in by_date[d][-3:]:
            txt += f"  {'➕' if l['type']=='created' else '✅' if l['type']=='completed' else '🗑'} {l['description'][:40]}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_failed(update, ctx):
    if not await verify_secret(update, ctx, "failed"):
        return
    unretried = failed_reqs.get_unretried()
    if not unretried:
        await update.message.reply_text("✅ No failed requests!")
        return
    txt = f"📝 *FAILED REQUESTS ({len(unretried)})*\n\n"
    for r in unretried[:5]:
        txt += f"• {r['msg'][:50]}...\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_retry_failed(update, ctx):
    if not await verify_secret(update, ctx, "retryfailed"):
        return
    unretried = failed_reqs.get_unretried()
    if not unretried:
        await update.message.reply_text("✅ No failed requests!")
        return
    success = 0
    for i, r in enumerate(unretried[:3]):
        try:
            reply = await ai_chat(r["msg"], r["chat_id"])
            if not reply.startswith("⚠️"):
                failed_reqs.mark_retried(i)
                success += 1
        except:
            pass
    await update.message.reply_text(f"🔄 Retried! ✅ {success}/{len(unretried)}")

async def cmd_fulldata(update, ctx):
    if not await verify_secret(update, ctx, "fulldata"):
        return
    txt = f"📊 *FULL DATA STATS*\n\n"
    txt += f"🧠 Memory facts: {len(memory.get_all_facts())}\n"
    txt += f"📋 Tasks: {len(tasks.all_tasks())}\n"
    txt += f"💪 Habits: {len(habits.all())}\n"
    txt += f"⏰ Reminders: {len(reminders.all_active())}\n"
    txt += f"💰 Month expenses: ₹{expenses.month_total():.0f}\n"
    txt += f"📖 Diary entries today: {len(diary.get(today_str()))}\n"
    txt += f"📝 Notes: {len(notes.recent(100))}\n"
    txt += f"🎯 Goals active: {len(goals.active())}\n"
    txt += f"💧 Water today: {water.today_total()}ml\n"
    txt += f"💳 Bills: {len(bills.all_active())}\n"
    txt += f"📅 Calendar events: {len(calendar.store.data.get('events', []))}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════════
# CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════════════
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    d = query.data
    message = query.message
    
    if not message:
        log.error("No message in callback")
        return
    
    if d == "menu":
        await message.edit_text("🏠 *Main Menu*", parse_mode="Markdown", reply_markup=main_kb())
    
    elif d == "briefing":
        try:
            briefing_text = await _build_briefing_text()
            await message.edit_text(briefing_text, parse_mode="Markdown", reply_markup=main_kb())
        except Exception as e:
            log.error(f"Briefing callback error: {e}")
            await message.edit_text("❌ Briefing load nahi hua, /briefing try karo.", reply_markup=back_kb())
    
    elif d == "tasks":
        pending = tasks.pending()
        if not pending:
            await message.edit_text("🎉 No pending tasks!", reply_markup=back_kb())
            return
        txt = "📋 *PENDING TASKS*\n\n"
        for t in pending[:10]:
            priority_icon = "🔴" if t['priority'] == 'high' else "🟡" if t['priority'] == 'medium' else "🟢"
            txt += f"{priority_icon} *#{t['id']}* {t['title']}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "all_tasks":
        all_t = tasks.all_tasks()
        if not all_t:
            await message.edit_text("📋 Koi task nahi!", reply_markup=back_kb())
            return
        p = tasks.pending()
        c = tasks.completed_tasks()
        txt = f"📋 *ALL TASKS ({len(all_t)})*\n⏳ {len(p)} pending | ✅ {len(c)} done\n\n"
        if p:
            txt += "*⏳ Pending:*\n"
            for t in p[:8]:
                e = "🔴" if t['priority']=='high' else "🟡" if t['priority']=='medium' else "🟢"
                txt += f"  {e} #{t['id']} {t['title']}\n"
        if c:
            txt += "\n*✅ Completed (last 5):*\n"
            for t in c[-5:]:
                txt += f"  ✓ #{t['id']} {t['title']}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "completed_tasks":
        c = tasks.completed_tasks()
        if not c:
            await message.edit_text("✅ Koi completed task nahi abhi tak!", reply_markup=back_kb())
            return
        txt = f"✅ *COMPLETED TASKS ({len(c)})*\n\n"
        for t in c[-15:]:
            txt += f"  ✓ #{t['id']} {t['title']}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "habits":
        done, pending = habits.today_status()
        txt = "💪 *HABITS TODAY*\n\n"
        if done:
            txt += "✅ *Done:*\n" + "\n".join(f"   {h['emoji']} {h['name']} — 🔥 {h.get('streak', 0)}d" for h in done) + "\n\n"
        if pending:
            txt += "⏳ *Pending:*\n" + "\n".join(f"   {h['emoji']} {h['name']}\n   `/hdone {h['id']}`" for h in pending) + "\n"
        if not done and not pending:
            txt += "_No habits added yet! Use `/habit` to add._"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "diary_write":
        ctx.user_data["awaiting_diary_entry"] = True
        await message.edit_text(
            "📖 *Diary Entry Likho:*\n\n"
            "_Neeche apni baat type karo — seedha save ho jayegi!_\n\n"
            "_Example: Aaj ka din bahut productive tha..._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="menu")]])
        )
    
    elif d == "goals":
        ag = goals.active()
        cg = goals.completed()
        if not ag and not cg:
            await message.edit_text("🎯 No goals yet! Use `/goal` to add.", reply_markup=back_kb())
            return
        txt = "🎯 *GOALS*\n\n"
        if ag:
            txt += "*Active:*\n"
            for g in ag[:5]:
                bar = "█" * (g['progress'] // 10) + "░" * (10 - (g['progress'] // 10))
                txt += f"   #{g['id']} **{g['title']}**\n   `{bar}` {g['progress']}%\n\n"
        if cg:
            txt += "*Completed:*\n"
            for g in cg[-3:]:
                txt += f"   🏆 #{g['id']} {g['title']}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "expenses":
        today_exp = expenses.today_total()
        month_exp = expenses.month_total()
        bl = expenses.budget_left()
        txt = f"💰 *EXPENSES*\n\n📅 Today: ₹{today_exp:.0f}\n📆 This month: ₹{month_exp:.0f}"
        if bl is not None:
            txt += f"\n💳 Budget left: ₹{bl:.0f}"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "notes":
        ns = notes.recent(10)
        if not ns:
            await message.edit_text("📝 No notes! Use `/note` to add.", reply_markup=back_kb())
            return
        txt = "📝 *RECENT NOTES*\n\n"
        for n in ns:
            txt += f"#{n['id']} — {n['text'][:50]}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "memory":
        facts = memory.get_all_facts()
        if not facts:
            await message.edit_text("🧠 No memories saved yet!", reply_markup=back_kb())
            return
        txt = "🧠 *MY MEMORY*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-10:])
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "yesterday":
        yd = yesterday_str()
        td = tasks.done_on(yd)
        exp = expenses.get_by_date(yd)
        diaryyd = diary.get(yd)
        exp_total = sum(e["amount"] for e in exp)
        txt = f"📊 *YESTERDAY ({yd})*\n\n"
        txt += f"✅ Tasks done: {len(td)}\n"
        if td:
            for t in td[:5]:
                txt += f"  • {t['title']}\n"
        txt += f"\n💰 Kharcha: ₹{exp_total:.0f}"
        if exp:
            for e in exp[:5]:
                txt += f"\n  • ₹{e['amount']:.0f} — {e['desc']}"
        txt += f"\n\n📖 Diary: {len(diaryyd)} entry"
        if diaryyd:
            for en in diaryyd[:2]:
                txt += f"\n  • {en['text'][:60]}"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "weekly_report":
        txt = f"📈 *WEEKLY SUMMARY*\n\n"
        task_week = tasks.get_weekly_summary()
        total_done = sum(v["done"] for v in task_week.values())
        total_created = sum(v["created"] for v in task_week.values())
        txt += f"📋 Tasks this week: ✅ {total_done} done | ➕ {total_created} created\n\n"
        txt += "*Daily breakdown:*\n"
        for d_key in sorted(task_week.keys(), reverse=True):
            v = task_week[d_key]
            exp_day = expenses.get_by_date(d_key)
            exp_total = sum(e["amount"] for e in exp_day)
            txt += f"📅 {d_key}: ✅{v['done']} done | ₹{exp_total:.0f}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "news_menu":
        await message.edit_text("📰 *Category:*", parse_mode="Markdown", reply_markup=news_kb())
    
    elif d.startswith("news_"):
        category = d.split("_", 1)[1]
        items = news_store.get(category, 5)
        if not items:
            await message.edit_text("📰 News unavailable right now.", reply_markup=back_kb())
            return
        txt = f"📰 *{category.upper()} NEWS*\n\n"
        for item in items:
            txt += f"• {item['title']}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "water_status":
        total = water.today_total()
        goal = water.goal()
        pct = min(100, int(total / goal * 100)) if goal else 0
        await message.edit_text(
            f"💧 *WATER INTAKE*\n\nToday: {total}ml / {goal}ml ({pct}%)\n\nUse `/water` to log more!",
            parse_mode="Markdown"
        )
    
    elif d.startswith("water_") and d.split("_")[1].isdigit():
        water.add(int(d.split("_")[1]))
        total = water.today_total()
        goal = water.goal()
        await message.edit_text(f"💧 +{d.split('_')[1]}ml | Total: {total}ml/{goal}ml", reply_markup=back_kb())
        await auto_backup_to_sheets()
    
    elif d == "bills_menu":
        all_b = bills.all_active()
        if not all_b:
            await message.edit_text("💳 No bills! Use `/bill` to add.", reply_markup=back_kb())
            return
        txt = "💳 *BILLS*\n\n"
        for b in all_b:
            status = "✅" if bills.is_paid_this_month(b["id"]) else "⏳"
            txt += f"{status} *{b['name']}* — ₹{b['amount']:.0f} (Due {b['due_day']}th)\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "cal_menu":
        upcoming = calendar.upcoming(30)
        if not upcoming:
            await message.edit_text("📅 Koi upcoming events nahi!", reply_markup=back_kb())
            return
        txt = "📅 *UPCOMING EVENTS*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for e in upcoming[:15]:
            today_flag = "🔴 TODAY" if e["date"] == today_str() else "📆"
            time_str = f" @ {e['time']}" if e.get("time") else ""
            txt += f"{today_flag} {e['date']}{time_str} — {e['title']}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "report_menu":
        await message.edit_text(
            "📅 *DATE-WISE REPORT*\n\n"
            "Send date in format: `/report YYYY-MM-DD`\n\n"
            "Example: `/report 2026-04-28`\n\n"
            "Get complete report for any date including:\n"
            "• Tasks\n• Reminders\n• Expenses\n• Diary\n• Habits\n• Water",
            parse_mode="Markdown"
        )
    
    elif d == "clear_chat":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Clear", callback_data="confirm_clear_chat"),
            InlineKeyboardButton("❌ Cancel", callback_data="menu")
        ]])
        await message.edit_text(
            f"🧹 Clear {chat_hist.count()} chat messages?\n\n"
            f"✅ Reminders, tasks, kharcha, habits — KUCH NAHI HATEGA",
            parse_mode="Markdown",
            reply_markup=kb
        )
    
    elif d == "confirm_clear_chat":
        count = chat_hist.clear()
        await message.edit_text(
            f"🧹 Cleared {count} chat messages! 🚀\n\n"
            f"✅ All your data (tasks, reminders, expenses) is SAFE!",
            parse_mode="Markdown",
            reply_markup=main_kb()
        )
    
    elif d == "confirm_nuke":
        tracked = chat_hist.get_tracked_ids()
        cid = message.chat_id
        status = await message.reply_text("🧹 Clearing messages...")
        deleted, failed = await delete_telegram_messages(query.get_bot(), tracked)
        chat_hist.clear()
        chat_hist.clear_msg_ids()
        try:
            await status.delete()
        except:
            pass
        try:
            await message.delete()
        except:
            pass
        await query.get_bot().send_message(
            chat_id=cid,
            text=f"🧹 Done! {deleted} messages deleted.\n✅ Your data is SAFE!",
            reply_markup=main_kb()
        )
    
    elif d == "motivate":
        reply = get_ai_reply("Give me a powerful short motivation in Hindi (2 lines)")
        await message.edit_text(f"💡 *MOTIVATION*\n\n{reply}", parse_mode="Markdown", reply_markup=back_kb())
    
    elif d == "backup_now":
        await message.edit_text("📤 Backing up to Google Sheets...", reply_markup=back_kb())
        result = google_sheets.full_sync()
        await message.edit_text(result, reply_markup=main_kb())
    
    elif d.startswith("done_"):
        tid = int(d.split("_")[1])
        t = tasks.complete(tid)
        if t:
            await message.edit_text(f"🎉 Done: {t['title']}", parse_mode="Markdown", reply_markup=back_kb())
        else:
            await message.edit_text("❌ Task not found or already done!", parse_mode="Markdown", reply_markup=back_kb())
        await auto_backup_to_sheets()
    
    elif d.startswith("habit_"):
        hid = int(d.split("_")[1])
        ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"] == hid), None)
        if ok and h:
            await message.edit_text(f"💪 {h['emoji']} {h['name']} — 🔥 Streak: {streak} days!", parse_mode="Markdown", reply_markup=back_kb())
        else:
            await message.edit_text("✅ Already done today!", parse_mode="Markdown", reply_markup=back_kb())
        await auto_backup_to_sheets()
    
    elif d.startswith("remind_done_"):
        rid = int(d.split("_")[2])
        reminders.mark_fired(rid)
        await message.edit_text("✅ Reminder marked as done!", reply_markup=back_kb())
        await auto_backup_to_sheets()
        try:
            await message.delete()
        except:
            pass
    
    elif d.startswith("remind_snooze_"):
        rid = int(d.split("_")[2])
        snooze = (now_ist() + timedelta(minutes=10)).strftime("%H:%M")
        r_list = [r for r in reminders.get_all() if r["id"] == rid]
        if r_list:
            reminders.add(message.chat_id, r_list[0]["text"], snooze, "once")
            reminders.mark_fired(rid)
        await message.edit_text(f"😴 Snoozed to {snooze}", reply_markup=back_kb())
        await auto_backup_to_sheets()
        try:
            await message.delete()
        except:
            pass
    
    elif d.startswith("delremind_"):
        reminders.delete(int(d.split("_")[1]))
        await message.edit_text("🗑 Reminder deleted!", reply_markup=back_kb())
        await auto_backup_to_sheets()

# ═══════════════════════════════════════════════════════════════════
# ✅ IMPROVED MESSAGE HANDLER - Quick greetings, no blocking
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_msg = update.message.text.strip()

    if user_msg.startswith('/'):
        return

    # ✅ Diary write — button flow (no password, direct save)
    if ctx.user_data.get("awaiting_diary_entry"):
        ctx.user_data.pop("awaiting_diary_entry", None)
        diary.add(user_msg, mood="📝")
        await update.message.reply_text(
            f"📖 *Diary saved!* 🕐 {now_str()}\n\n_{user_msg[:150]}_",
            parse_mode="Markdown",
            reply_markup=main_kb()
        )
        await auto_backup_to_sheets()
        return

    # ✅ CRITICAL: Clear any stale diary state
    ctx.user_data.pop("diary_view", None)
    ctx.user_data.pop("diary_from_callback", None)

    # ✅ QUICK GREETINGS - Instant response, bypass AI
    lower_msg = user_msg.lower().strip()
    
    # Common greetings - instant response
    greetings = ["hello", "hi", "hey", "assalam", "namaste", "hola", "yo", "sup", "heya", "hii", "helloo", "hlo"]
    if any(lower_msg == g or lower_msg.startswith(g + " ") or lower_msg.startswith(g) for g in greetings):
        name = update.effective_user.first_name or "Dost"
        n = now_ist()
        replies = [
            f"🕌 *Assalamualaikum {name}!* 😊\n\nKaise ho? Main bilkul ready hoon aapki help ke liye!\n\n⏰ {n.strftime('%I:%M %p')} IST",
            f"😊 *Hey {name}!* 👋\n\nSab badiya? Batao kya help chahiye aaj?",
            f"👋 *Namaste {name}!*\n\nAapka din kaisa chal raha hai? Main yahan hoon help ke liye!",
        ]
        await update.message.reply_text(random.choice(replies), parse_mode="Markdown", reply_markup=main_kb())
        return
    
    # How are you type messages
    how_are = ["kaise ho", "how are you", "kya haal", "kaisi ho", "how r u", "how're you", "how are u"]
    if any(h in lower_msg for h in how_are):
        name = update.effective_user.first_name or "Dost"
        await update.message.reply_text(
            f"😊 *Main badiya hoon, {name}!* 💪\n\nBas aapke messages ka wait tha. Aap sunao, sab theek?",
            parse_mode="Markdown"
        )
        return
    
    # Thanks
    thanks = ["thank", "thanks", "shukriya", "dhanyavad", "thx", "ty", "thank u", "thankyou"]
    if any(t in lower_msg for t in thanks):
        await update.message.reply_text(
            "🤗 *Welcome!*\n\nAur koi help chahiye toh bindaas batao, main yahin hoon! 😊",
            parse_mode="Markdown"
        )
        return

    # Goodbye
    bye = ["bye", "allah hafiz", "good night", "goodnight", "shabba khair", "see you", "tata", "fir milenge", "gn"]
    if any(b in lower_msg for b in bye):
        await update.message.reply_text(
            "🌙 *Allah Hafiz!*\n\nApna khayal rakhna, fir baat hogi! 🤗",
            parse_mode="Markdown"
        )
        return

    # ✅ What can you do / help
    what_can = ["kya kar sakte", "kya karte", "what can you", "tum kya kar", "aap kya kar"]
    if any(w in lower_msg for w in what_can):
        await update.message.reply_text(
            "🤖 *Main kya kar sakta hoon:*\n\n"
            "📋 *Tasks* — `/task Kaam` se task add, `/done` se complete\n"
            "⏰ *Reminders* — `/remind 2m Chai` ya `/remind 15:30 Meeting`\n"
            "💰 *Kharcha* — `/kharcha 100 Chai` se expense track\n"
            "📖 *Diary* — `/diary Aaj ka din...` se diary likho\n"
            "💪 *Habits* — `/habit Exercise` se habit track\n"
            "🎯 *Goals* — `/goal Python seekhna` se goal set\n"
            "📰 *News* — `/news` se latest news\n"
            "💧 *Water* — `/water` se water intake log\n"
            "💳 *Bills* — `/bill Internet 999 15` se bill track\n\n"
            "_Seedha type karo — main samjhunga!_ 👇",
            parse_mode="Markdown",
            reply_markup=main_kb()
        )
        return

    # ✅ Normal AI chat for everything else
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ai_chat(user_msg, update.effective_chat.id)

    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(reply)

# ═══════════════════════════════════════════════════════════════════
# BACKGROUND JOBS
# ═══════════════════════════════════════════════════════════════════
async def reminder_job(context):
    now = now_ist()
    now_time = now.strftime("%H:%M")
    
    active_count = len(reminders.all_active())
    if active_count > 0 and now.second < 35:
        log.info(f"⏰ Check at {now_time} IST | Active reminders: {active_count}")
    
    if now_time in ("00:00", "00:01", "00:02"):
        reminders.reset_daily()
        log.info("🔄 Daily reset at midnight IST")
        return
    
    due = reminders.due_now()
    
    if due:
        log.info(f"🔔 FIRING {len(due)} reminders at {now_time} IST!")
    
    for r in due:
        try:
            repeat_note = ""
            if r["repeat"] == "daily":
                repeat_note = "\n🔁 _Kal bhi yaad dilaunga!_"
            elif r["repeat"] == "weekly":
                repeat_note = "\n📅 _Agli hafte!_"
            
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
            log.info(f"📤 Alarm #{r['id']} sent!")
            
            reminders.mark_fired(r["id"])
            
            await asyncio.sleep(1)
            
        except Exception as e:
            log.error(f"❌ FAILED #{r['id']}: {e}")

async def failed_retry_job(context):
    unretried = failed_reqs.get_unretried()
    if not unretried:
        return
    log.info(f"🔄 Retrying {len(unretried)} failed...")
    for i, r in enumerate(unretried[:3]):
        try:
            reply = await ai_chat(r["msg"], r["chat_id"])
            if not reply.startswith("⚠️"):
                failed_reqs.mark_retried(i)
                try:
                    await context.bot.send_message(
                        chat_id=r["chat_id"],
                        text=f"📝 *Saved request processed!*\n\n_{reply}_",
                        parse_mode="Markdown"
                    )
                except:
                    pass
        except:
            pass

async def bill_due_job(context):
    if now_ist().strftime("%H:%M") != "09:00":
        return
    due = bills.due_soon(3)
    if not due:
        return
    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    if not chat_ids:
        return
    txt = "💳 *BILL DUE SOON*\n\n" + "\n".join(f"⚠️ {b['name']} — ₹{b['amount']:.0f}" for b in due)
    for cid in chat_ids:
        try:
            await context.bot.send_message(chat_id=cid, text=txt, parse_mode="Markdown")
        except:
            pass

async def water_reminder_job(context):
    now = now_ist()
    if not (8 <= now.hour <= 22) or now.hour % 3 != 0:
        return
    total = water.today_total()
    goal = water.goal()
    if total >= goal:
        return
    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    for cid in chat_ids:
        try:
            await context.bot.send_message(
                chat_id=cid,
                text=f"💧 *Paani peene ka time!*\nToday: {total}ml/{goal}ml\n`/water` se log karo",
                parse_mode="Markdown"
            )
        except:
            pass

_last_auto_backup = 0
_BACKUP_THROTTLE_SECS = 30

async def auto_backup_to_sheets():
    global _last_auto_backup
    now_ts = time.time()
    if now_ts - _last_auto_backup < _BACKUP_THROTTLE_SECS:
        return
    _last_auto_backup = now_ts
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, google_sheets.full_sync)
    log.info(f"📤 {result}")
    return result

async def scheduled_backup_job(context):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, google_sheets.full_sync)
    log.info(f"🕒 Scheduled backup: {result}")

async def daily_log_job(context):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, google_sheets.save_daily_log)
    log.info(f"📅 Daily log backup: {result}")

async def delete_telegram_messages(bot, tracked_ids):
    deleted, failed = 0, 0
    for entry in tracked_ids:
        try:
            await bot.delete_message(chat_id=entry["chat_id"], message_id=entry["msg_id"])
            deleted += 1
        except:
            failed += 1
        await asyncio.sleep(0.1)
    return deleted, failed

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    n = now_ist()
    log.info("=" * 55)
    log.info(f"🤖 Bot v14 — FINAL STABLE (All Bugs Fixed)")
    log.info(f"⏰ IST: {n.strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"📊 Google Sheets (Primary DB): {'✅ CONNECTED' if google_sheets.sheet else '❌ NOT connected!'}")
    log.info(f"🔑 Gemini: {'YES' if GEMINI_API_KEY else 'NO'} | 🎤 Groq: {'YES' if GROQ_API_KEY else 'NO'}")
    log.info(f"✅ Fixes: Hello instant | Reminder explicit | AI consistent | No blocking")
    log.info("=" * 55)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    async def post_init(app):
        try:
            chat_id = os.environ.get("ADMIN_CHAT_ID", "")
            if chat_id:
                r_count = len(reminders.store.data.get("list", []))
                t_count = len(tasks.store.data.get("list", []))
                d_count = sum(len(v) for v in diary.store.data.get("entries", {}).values())
                active_rem = [r for r in reminders.store.data.get("list", []) if r.get("active")]
                rem_info = "\n".join(f"  • {r['time']} — {r['text']}" for r in active_rem[:3]) or "  Koi nahi"
                sheets_msg = "✅ Google Sheets connected — Data restore ho gaya!" if google_sheets.sheet else "❌ Sheets NOT connected!"
                n2 = now_ist()
                await app.bot.send_message(
                    chat_id=int(chat_id),
                    text=f"🤖 *Bot Start/Restart hua!*\n\n"
                         f"⏰ {n2.strftime('%d %b %Y %I:%M %p')} IST\n\n"
                         f"📊 {sheets_msg}\n\n"
                         f"✅ *All bugs fixed:*\n"
                         f"  • Hello/Hi ka instant jawab\n"
                         f"  • Reminder sirf maangne pe set\n"
                         f"  • AI responses consistent\n"
                         f"  • No blocking issues\n\n"
                         f"📦 *Restored data:*\n"
                         f"  ⏰ Reminders: {r_count} | 📋 Tasks: {t_count} | 📖 Diary: {d_count}\n\n"
                         f"⏰ *Active reminders:*\n{rem_info}",
                    parse_mode="Markdown"
                )
        except Exception as e:
            log.warning(f"Startup notification failed: {e}")

    app.post_init = post_init

    commands = [
        ("start", cmd_start), ("hello", cmd_hello), ("help", cmd_help),
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("habit", cmd_habit), ("hdone", cmd_hdone), ("delhabit", cmd_delhabit),
        ("kharcha", cmd_kharcha), ("budget", cmd_budget),
        ("goal", cmd_goal), ("gprogress", cmd_gprogress),
        ("remember", cmd_remember), ("recall", cmd_recall),
        ("note", cmd_note), ("delnote", cmd_delnote),
        ("briefing", cmd_briefing), ("weekly", cmd_weekly), ("report", cmd_report),
        ("news", cmd_news), ("clear", cmd_clear), ("nuke", cmd_nuke),
        ("alltasks", cmd_alltasks), ("completed", cmd_completed), ("yesterday", cmd_yesterday),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list), ("delremind", cmd_delremind),
        ("water", cmd_water), ("waterstatus", cmd_water_status), ("watergoal", cmd_water_goal),
        ("bill", cmd_bill), ("bills", cmd_bills_list), ("billpaid", cmd_bill_paid), ("delbill", cmd_del_bill),
        ("cal", cmd_cal), ("calendar", cmd_cal_list), ("delcal", cmd_del_cal),
        ("memory", cmd_memory), ("backup", cmd_backup), ("dbstatus", cmd_dbstatus),
        ("tasklogs", cmd_tasklogs), ("failed", cmd_failed), ("retryfailed", cmd_retry_failed), ("fulldata", cmd_fulldata),
    ]

    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))

    # ✅ FIXED: Diary ConversationHandler with proper timeout
    diary_conv = ConversationHandler(
        entry_points=[
            CommandHandler("diary", cmd_diary),
            CommandHandler("diaryview", cmd_diary_view),
        ],
        states={
            DIARY_AWAIT_PASS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", diary_conv_cancel),
        ],
        per_user=True,
        per_chat=True,
        conversation_timeout=30,
        allow_reentry=True,
    )
    app.add_handler(diary_conv)
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    if app.job_queue:
        app.job_queue.run_repeating(reminder_job,       interval=60,    first=15)
        app.job_queue.run_repeating(failed_retry_job,   interval=300,   first=180)
        app.job_queue.run_repeating(bill_due_job,       interval=3600,  first=300)
        app.job_queue.run_repeating(water_reminder_job, interval=3600,  first=600)
        app.job_queue.run_repeating(scheduled_backup_job, interval=3600, first=120)
        app.job_queue.run_daily(daily_log_job, time=dt_module.time(hour=21, minute=0, tzinfo=IST))
        
        log.info("⏰ Jobs started: Reminder (60s) | Retry (5min) | Bills/Water (1hr) | Backup (1hr) | Daily Log (9PM)")
    else:
        log.error("❌ JobQueue NOT AVAILABLE! Alarms won't work!")
    
    log.info("✅ Bot ready! Test: /hello")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
