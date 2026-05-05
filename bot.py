#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v15.0 JARVIS UPGRADE               ║
║  + GROQ TEXT (Llama 3.3 70B) — NEW FREE AI fallback            ║
║  + SMART LOCAL ROUTER — zero API calls for simple queries       ║
║  + AI RESPONSE CACHE — 5min TTL, saves rate limits             ║
║  + PROACTIVE MORNING BRIEFING — 7:30 AM smart digest           ║
║  + DAILY NIGHT SUMMARY — 10 PM + Sunday weekly analytics       ║
║  + ALL v14 FEATURES INTACT                                      ║
║                                                                  ║
║  GITHUB SECRETS NEEDED:                                          ║
║    TELEGRAM_TOKEN   — BotFather se milta hai                    ║
║    GEMINI_API_KEY   — aistudio.google.com (free)               ║
║    GOOGLE_CREDS_JSON — Google Service Account JSON             ║
║    GROQ_API_KEY     — groq.com (free — voice + text dono)      ║
║    HF_TOKEN         — HuggingFace (optional fallback)          ║
║    ADMIN_CHAT_ID    — Tumhara Telegram chat ID                 ║
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

# ✅ v15 NEW: Groq text model
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"  # Free tier — 6000 RPD

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
# 🦙 v15 NEW: GROQ TEXT API (FREE — Llama 3.3 70B)
# Same GROQ_API_KEY jo voice ke liye use ho raha hai!
# Free tier: 6000 requests/day, 14400 tokens/min
# ═══════════════════════════════════════════════════════════════════
_last_groq_text_call = 0

def call_groq_text(prompt, max_tokens=400):
    """Groq Llama 3.3 70B — free, fast, smart. Gemini ke baad fallback."""
    global _last_groq_text_call
    if not GROQ_API_KEY:
        return None

    now = time.time()
    elapsed = now - _last_groq_text_call
    if elapsed < 2:
        time.sleep(2 - elapsed)
    _last_groq_text_call = time.time()

    try:
        payload = json.dumps({
            "model": GROQ_TEXT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": min(max_tokens, 500),
            "temperature": 0.75
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GROQ_API_KEY}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            text = result["choices"][0]["message"]["content"].strip()
            if text and len(text) > 5:
                log.info(f"✅ Groq text: {GROQ_TEXT_MODEL}")
                return text
    except urllib.error.HTTPError as e:
        if e.code == 429:
            log.warning("Groq text rate limited")
        else:
            log.warning(f"Groq text HTTP {e.code}")
    except Exception as e:
        log.warning(f"Groq text fail: {e}")
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
                "`/help` — Full list")

    replies = [
        "🙏 Abhi AI busy hai. Thodi der baad try karo ya `/help` use karo!",
        "😅 Model unavailable. Commands try karo: `/task` `/remind` `/help`",
        "🤖 Response nahi aa pa raha. Kuch commands use karo ya wait karo!",
    ]
    return random.choice(replies)

# ═══════════════════════════════════════════════════════════════════
# 🎤 VOICE TRANSCRIPTION (Groq Whisper)
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
            "groq.com pe free account → API key → GitHub Secrets mein add karo",
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
                "❌ Samajh nahi aaya — thoda saaf bolke bhejna!",
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
        return transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
    except Exception as e:
        log.warning(f"Sync transcribe fail: {e}")
    return None

# ═══════════════════════════════════════════════════════════════════
# 🧠 v15 NEW: AI RESPONSE CACHE
# Same query pe dobara API call nahi — 5 min TTL
# ═══════════════════════════════════════════════════════════════════
_ai_cache = {}
_AI_CACHE_TTL = 300  # 5 minutes

def _get_cached_reply(key):
    if key in _ai_cache:
        reply, ts = _ai_cache[key]
        if time.time() - ts < _AI_CACHE_TTL:
            log.info("⚡ Cache hit!")
            return reply
        del _ai_cache[key]
    return None

def _set_cache(key, reply):
    if len(_ai_cache) > 50:
        oldest = min(_ai_cache, key=lambda k: _ai_cache[k][1])
        del _ai_cache[oldest]
    _ai_cache[key] = (reply, time.time())

# ═══════════════════════════════════════════════════════════════════
# 🚀 v15 NEW: SMART LOCAL ROUTER
# Simple queries local handle karo — zero API tokens waste nahi
# ═══════════════════════════════════════════════════════════════════
_LOCAL_INTENTS = {
    "time":      ("time", "baje", "kitne baje", "time kya", "abhi kya time", "clock"),
    "date":      ("date", "aaj kya", "tarikh", "aaj kitni", "kaun sa din", "din kya"),
    "greet":     ("hello", "hi", "assalam", "namaste", "hey", "aoa", "salam"),
    "wellbeing": ("kaise ho", "how are", "kya haal", "kaisi ho", "theek ho"),
    "thanks":    ("thank", "shukriya", "thanks", "thankyou", "bahut shukriya"),
    "bye":       ("bye", "allah hafiz", "good night", "shabba", "khuda hafiz", "alvida"),
}

def _smart_local_router(msg):
    lower = msg.lower()
    for intent, keywords in _LOCAL_INTENTS.items():
        if any(kw in lower for kw in keywords):
            return intent
    return None

def _local_reply(intent):
    n = now_ist()
    if intent == "time":
        return f"⏰ Abhi *{n.strftime('%I:%M %p')}* baj rahe hain (IST)"
    if intent == "date":
        days_hi = {0:"Somwar",1:"Mangalwar",2:"Budh",3:"Guruwar",4:"Shukrawar",5:"Shaniwar",6:"Itwar"}
        months_en = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                     7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
        return f"📅 Aaj *{days_hi[n.weekday()]}, {n.day} {months_en[n.month]} {n.year}* hai"
    if intent == "greet":
        options = ["🕌 *Assalamualaikum!* Kya haal hai?",
                   "😊 *Salam!* Batao kya kaam hai?",
                   "👋 *Hello!* Main yahaan hoon — batao kya chahiye?"]
        return random.choice(options)
    if intent == "wellbeing":
        return "😊 *Main bilkul theek hoon!* Aap sunao — kya ho raha hai?"
    if intent == "thanks":
        return "🤗 *Welcome!* Aur kuch help chahiye toh batao!"
    if intent == "bye":
        return "🌙 *Allah Hafiz!* Apna khayal rakhna!"
    return None

# ═══════════════════════════════════════════════════════════════════
# 🚀 v15 UPGRADED: MAIN AI PIPELINE
# Flow: Local → Cache → Gemini → Groq → HuggingFace → Offline
# ═══════════════════════════════════════════════════════════════════
def get_ai_reply(user_msg, chat_id=None, system_ctx=None):
    """
    UPGRADED v15 AI Pipeline:
    1. Local router  — zero cost, instant
    2. Cache check   — zero cost if hit
    3. Gemini        — primary free AI
    4. Groq Llama    — NEW fast free fallback
    5. HuggingFace   — slow free fallback
    6. Offline       — always works
    """
    # Step 1: Local router
    intent = _smart_local_router(user_msg)
    if intent:
        return _local_reply(intent)

    # Step 2: Cache
    cache_key = user_msg[:80].lower().strip()
    cached = _get_cached_reply(cache_key)
    if cached:
        return cached

    # Step 3: Build prompt
    if not system_ctx:
        system_ctx = build_system_prompt()
    prompt = f"{system_ctx}\n\nUser: {user_msg}\n\nReply in Hindi/Hinglish (2-4 lines, warm & friendly):"

    # Step 4: Gemini
    reply = call_gemini(prompt)
    if reply:
        _set_cache(cache_key, reply)
        return reply

    # Step 5: Groq Llama 3.3 (NEW)
    reply = call_groq_text(prompt)
    if reply:
        _set_cache(cache_key, reply)
        return reply

    # Step 6: HuggingFace
    reply = call_huggingface(prompt)
    if reply:
        tagged = reply + "\n\n_⚡ (via free model)_"
        _set_cache(cache_key, tagged)
        return tagged

    # Step 7: Offline fallback
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
        q = self.store.data.get("queue", [])
        if idx < len(q):
            q[idx]["retried"] = True
            self.store.save()


class HabitStore:
    def __init__(self):
        self.store = Store("habits", {"list": [], "logs": {}, "counter": 0})

    def add(self, name, emoji="✅"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        h = {"id": self.store.data["counter"], "name": name, "emoji": emoji,
             "streak": 0, "best_streak": 0, "created": today_str()}
        self.store.data["list"].append(h)
        self.store.save()
        return h

    def all(self):
        return self.store.data.get("list", [])

    def log(self, hid):
        logs = self.store.data.setdefault("logs", {})
        today = today_str()
        day_logs = logs.setdefault(today, [])
        if hid in day_logs:
            return False, 0
        day_logs.append(hid)
        # Update streak
        for h in self.store.data["list"]:
            if h["id"] == hid:
                yesterday = yesterday_str()
                yest_logs = logs.get(yesterday, [])
                if hid in yest_logs:
                    h["streak"] = h.get("streak", 0) + 1
                else:
                    h["streak"] = 1
                h["best_streak"] = max(h.get("best_streak", 0), h["streak"])
                self.store.save()
                return True, h["streak"]
        self.store.save()
        return True, 1

    def delete(self, hid):
        before = len(self.store.data["list"])
        self.store.data["list"] = [h for h in self.store.data["list"] if h["id"] != hid]
        self.store.save()
        return before != len(self.store.data["list"])

    def today_status(self):
        logs = self.store.data.get("logs", {})
        today_logs = logs.get(today_str(), [])
        done = [h for h in self.all() if h["id"] in today_logs]
        pending = [h for h in self.all() if h["id"] not in today_logs]
        return done, pending

    def get_logs_by_date(self, d):
        return self.store.data.get("logs", {}).get(d, [])


class ExpenseStore:
    def __init__(self):
        self.store = Store("expenses", {"list": [], "budget": None})

    def add(self, amount, desc, category="general"):
        e = {"date": today_str(), "amount": float(amount), "desc": desc,
             "category": category, "time": now_str()}
        self.store.data["list"].append(e)
        self.store.save()
        return e

    def today_total(self):
        return sum(e["amount"] for e in self.store.data.get("list", []) if e["date"] == today_str())

    def month_total(self):
        m = now_ist().strftime("%Y-%m")
        return sum(e["amount"] for e in self.store.data.get("list", []) if e["date"].startswith(m))

    def budget_left(self):
        b = self.store.data.get("budget")
        if b is None:
            return None
        return b - self.month_total()

    def set_budget(self, amount):
        self.store.data["budget"] = float(amount)
        self.store.save()

    def get_by_date(self, d):
        return [e for e in self.store.data.get("list", []) if e["date"] == d]

    def get_by_month(self, m):
        return [e for e in self.store.data.get("list", []) if e["date"].startswith(m)]


class ReminderStore:
    def __init__(self):
        self.store = Store("reminders", {"list": [], "counter": 0})

    def add(self, chat_id, text, time_str, repeat="once"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        r = {
            "id": self.store.data["counter"], "chat_id": chat_id,
            "text": text, "time": time_str, "repeat": repeat,
            "active": True, "fired_today": False,
            "date": today_str(), "created": datetime.now().isoformat()
        }
        self.store.data["list"].append(r)
        self.store.save()
        return r

    def all_active(self):
        return [r for r in self.store.data.get("list", []) if r.get("active")]

    def get_all(self):
        return self.store.data.get("list", [])

    def due_now(self):
        now_time = now_str()
        due = []
        for r in self.all_active():
            if r["time"] == now_time and not r.get("fired_today"):
                due.append(r)
        return due

    def mark_fired(self, rid):
        for r in self.store.data["list"]:
            if r["id"] == rid:
                r["fired_today"] = True
                if r["repeat"] == "once":
                    r["active"] = False
                break
        self.store.save()

    def reset_daily(self):
        for r in self.store.data["list"]:
            if r.get("active") and r.get("repeat") in ("daily", "weekly"):
                r["fired_today"] = False
        self.store.save()

    def delete(self, rid):
        before = len(self.store.data["list"])
        self.store.data["list"] = [r for r in self.store.data["list"] if r["id"] != rid]
        self.store.save()
        return before != len(self.store.data["list"])


class DiaryStore:
    def __init__(self):
        self.store = Store("diary", {"entries": {}})

    def add(self, text, mood="📝"):
        entries = self.store.data.setdefault("entries", {})
        today = today_str()
        entries.setdefault(today, []).append({"text": text, "mood": mood, "time": now_str()})
        self.store.save()

    def get(self, d):
        return self.store.data.get("entries", {}).get(d, [])

    def get_all_entries(self):
        return self.store.data.get("entries", {})


class GoalStore:
    def __init__(self):
        self.store = Store("goals", {"list": [], "counter": 0})

    def add(self, title, deadline=None):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        g = {"id": self.store.data["counter"], "title": title,
             "progress": 0, "done": False, "deadline": deadline or "",
             "created": today_str()}
        self.store.data["list"].append(g)
        self.store.save()
        return g

    def active(self):
        return [g for g in self.store.data.get("list", []) if not g["done"]]

    def completed(self):
        return [g for g in self.store.data.get("list", []) if g["done"]]

    def update_progress(self, gid, pct):
        for g in self.store.data["list"]:
            if g["id"] == gid:
                g["progress"] = min(100, max(0, int(pct)))
                if g["progress"] >= 100:
                    g["done"] = True
                self.store.save()
                return g
        return None

    def delete(self, gid):
        before = len(self.store.data["list"])
        self.store.data["list"] = [g for g in self.store.data["list"] if g["id"] != gid]
        self.store.save()
        return before != len(self.store.data["list"])


class NoteStore:
    def __init__(self):
        self.store = Store("notes", {"list": [], "counter": 0})

    def add(self, text):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        n = {"id": self.store.data["counter"], "text": text, "date": today_str()}
        self.store.data["list"].append(n)
        self.store.save()
        return n

    def recent(self, n=10):
        return self.store.data.get("list", [])[-n:]

    def delete(self, nid):
        before = len(self.store.data["list"])
        self.store.data["list"] = [n for n in self.store.data["list"] if n["id"] != nid]
        self.store.save()
        return before != len(self.store.data["list"])


class WaterStore:
    def __init__(self):
        self.store = Store("water", {"entries": {}, "goal": 2000})

    def add(self, ml):
        today = today_str()
        entries = self.store.data.setdefault("entries", {})
        entries.setdefault(today, []).append({"ml": ml, "time": now_str()})
        self.store.save()

    def today_total(self):
        return sum(e["ml"] for e in self.store.data.get("entries", {}).get(today_str(), []))

    def goal(self):
        return self.store.data.get("goal", 2000)

    def set_goal(self, ml):
        self.store.data["goal"] = ml
        self.store.save()


class BillStore:
    def __init__(self):
        self.store = Store("bills", {"list": [], "paid": {}, "counter": 0})

    def add(self, name, amount, due_day):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        b = {"id": self.store.data["counter"], "name": name,
             "amount": float(amount), "due_day": int(due_day),
             "active": True, "created": today_str()}
        self.store.data["list"].append(b)
        self.store.save()
        return b

    def all_active(self):
        return [b for b in self.store.data.get("list", []) if b.get("active")]

    def due_soon(self, days=3):
        today = now_ist().day
        result = []
        for b in self.all_active():
            diff = b["due_day"] - today
            if 0 <= diff <= days:
                result.append(b)
        return result

    def mark_paid(self, bid):
        month = now_ist().strftime("%Y-%m")
        paid = self.store.data.setdefault("paid", {})
        paid.setdefault(month, []).append(bid)
        self.store.save()

    def is_paid_this_month(self, bid):
        month = now_ist().strftime("%Y-%m")
        return bid in self.store.data.get("paid", {}).get(month, [])

    def delete(self, bid):
        before = len(self.store.data["list"])
        self.store.data["list"] = [b for b in self.store.data["list"] if b["id"] != bid]
        self.store.save()
        return before != len(self.store.data["list"])


class CalendarStore:
    def __init__(self):
        self.store = Store("calendar", {"events": [], "counter": 0})

    def add(self, title, date_str, time_str=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        e = {"id": self.store.data["counter"], "title": title,
             "date": date_str, "time": time_str, "created": today_str()}
        self.store.data["events"].append(e)
        self.store.save()
        return e

    def today_events(self):
        return [e for e in self.store.data.get("events", []) if e["date"] == today_str()]

    def upcoming(self, days=30):
        today = today_str()
        end = (now_ist().date() + timedelta(days=days)).isoformat()
        return sorted([e for e in self.store.data.get("events", []) if today <= e["date"] <= end],
                      key=lambda x: x["date"])

    def delete(self, eid):
        before = len(self.store.data["events"])
        self.store.data["events"] = [e for e in self.store.data["events"] if e["id"] != eid]
        self.store.save()
        return before != len(self.store.data["events"])


class NewsStore:
    def __init__(self):
        self._cache = {}
        self._cache_ts = {}
        self._ttl = 1800  # 30 min

    def get(self, category="India", n=5):
        now_ts = time.time()
        if category in self._cache and now_ts - self._cache_ts.get(category, 0) < self._ttl:
            return self._cache[category][:n]
        try:
            url = f"https://news.google.com/rss/search?q={category}+India&hl=en-IN&gl=IN&ceid=IN:en"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                tree = ET.parse(resp)
                items = tree.findall(".//item")[:10]
                news = [{"title": i.findtext("title", ""), "link": i.findtext("link", "")} for i in items]
            self._cache[category] = news
            self._cache_ts[category] = now_ts
            return news[:n]
        except Exception as e:
            log.warning(f"News fetch failed: {e}")
            return []


class ChatHistStore:
    def __init__(self):
        self.store = Store("chat_history", {"messages": [], "tracked": []})

    def add(self, role, text):
        msgs = self.store.data.setdefault("messages", [])
        msgs.append({"role": role, "text": text[:500], "time": now_str()})
        self.store.data["messages"] = msgs[-50:]
        self.store.save()

    def recent(self, n=10):
        return self.store.data.get("messages", [])[-n:]

    def clear(self):
        count = len(self.store.data.get("messages", []))
        self.store.data["messages"] = []
        self.store.save()
        return count

    def track_msg(self, chat_id, msg_id):
        self.store.data.setdefault("tracked", []).append({"chat_id": chat_id, "msg_id": msg_id})
        self.store.data["tracked"] = self.store.data["tracked"][-100:]
        self.store.save()

    def get_tracked_ids(self):
        return self.store.data.get("tracked", [])

    def clear_msg_ids(self):
        self.store.data["tracked"] = []
        self.store.save()

    def count(self):
        return len(self.store.data.get("messages", []))


# Initialize all stores
memory = MemoryStore()
tasks = TaskStore()
task_logs = TaskLogsStore()
failed_reqs = FailedReqStore()
habits = HabitStore()
expenses = ExpenseStore()
reminders = ReminderStore()
diary = DiaryStore()
goals = GoalStore()
notes = NoteStore()
water = WaterStore()
bills = BillStore()
calendar = CalendarStore()
news_store = NewsStore()
chat_hist = ChatHistStore()

# ═══════════════════════════════════════════════════════════════════
# GOOGLE SHEETS INTEGRATION
# ═══════════════════════════════════════════════════════════════════
class GoogleSheetsDB:
    def __init__(self):
        self.sheet = None
        self._connect()

    def _connect(self):
        if not HAS_GSHEETS or not GOOGLE_CREDS_JSON:
            log.warning("⚠️ Google Sheets not configured")
            return
        try:
            creds_data = json.loads(GOOGLE_CREDS_JSON)
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_data, scope)
            client = gspread.authorize(creds)
            sheet_name = creds_data.get("sheet_name", "PersonalAI_DB")
            try:
                self.sheet = client.open(sheet_name)
            except Exception:
                self.sheet = client.create(sheet_name)
            log.info("✅ Google Sheets connected!")
            self._ensure_worksheets()
            self.restore_from_sheets()
        except Exception as e:
            log.error(f"Sheets connect failed: {e}")

    def _ensure_worksheets(self):
        if not self.sheet:
            return
        needed = ["Tasks", "Reminders", "Expenses", "Habits", "Memory",
                  "Goals", "Bills", "Calendar", "Water", "Daily_Logs", "Diary"]
        existing = [ws.title for ws in self.sheet.worksheets()]
        for name in needed:
            if name not in existing:
                self.sheet.add_worksheet(title=name, rows=1000, cols=20)

    def _upsert_rows(self, ws, rows, id_col=0):
        try:
            existing = ws.get_all_values()
            if not existing:
                if rows:
                    ws.append_row([str(c) for c in rows[0]])
                existing = ws.get_all_values()
            existing_ids = {str(row[id_col]): idx+1 for idx, row in enumerate(existing[1:], 1) if len(row) > id_col and row[id_col]}
            updated, added = 0, 0
            for row in rows:
                key = str(row[id_col])
                if key in existing_ids:
                    ws.update(f'A{existing_ids[key]}', [row])
                    updated += 1
                else:
                    ws.append_row(row, value_input_option="USER_ENTERED")
                    added += 1
            return updated, added
        except Exception as e:
            log.error(f"Upsert error: {e}")
            return 0, 0

    def save_tasks(self, task_list):
        if not self.sheet or not task_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Tasks")
            rows = [[t["id"], t["title"], t["priority"],
                     "Done" if t["done"] else "Pending",
                     t.get("created", "")[:10], t.get("done_at", "")[:10]] for t in task_list]
            self._upsert_rows(ws, rows)
            return True
        except Exception as e:
            log.error(f"Tasks save error: {e}")
            return False

    def save_reminders(self, rem_list):
        if not self.sheet or not rem_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Reminders")
            rows = [[r["id"], r["time"], r["text"], r["repeat"],
                     "Active" if r["active"] else "Inactive",
                     r.get("date", ""), r.get("created", "")] for r in rem_list]
            self._upsert_rows(ws, rows)
            return True
        except Exception as e:
            log.error(f"Reminders save error: {e}")
            return False

    def save_expenses(self, exp_list):
        if not self.sheet or not exp_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Expenses")
            rows = [[e["date"], e["time"], e["amount"], e["desc"], e.get("category", "general")] for e in exp_list]
            existing = ws.get_all_values()
            existing_keys = set()
            for row in existing[1:]:
                if len(row) >= 4:
                    existing_keys.add(f"{row[0]}|{row[1]}|{str(row[3])[:30]}")
            new_rows = []
            for row in rows:
                key = f"{row[0]}|{row[1]}|{str(row[3])[:30]}"
                if key not in existing_keys:
                    new_rows.append(row)
                    existing_keys.add(key)
            for row in new_rows:
                ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            log.error(f"Expenses save error: {e}")
            return False

    def save_habits(self, hab_list):
        if not self.sheet or not hab_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Habits")
            rows = [[h["id"], h["name"], h.get("emoji","✅"),
                     h.get("streak",0), h.get("best_streak",0), h.get("created","")] for h in hab_list]
            self._upsert_rows(ws, rows)
            return True
        except Exception as e:
            log.error(f"Habits save error: {e}")
            return False

    def save_memory(self, facts):
        if not self.sheet or not facts:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Memory")
            existing = ws.get_all_values()
            existing_facts = set(str(row[1])[:50] for row in existing[1:] if len(row) > 1 and row[1])
            new_rows = [[f["d"], f["f"]] for f in facts if str(f["f"])[:50] not in existing_facts]
            for row in new_rows:
                ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            log.error(f"Memory save error: {e}")
            return False

    def save_goals(self, goal_list):
        if not self.sheet or not goal_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Goals")
            rows = [[g["id"], g["title"], g["progress"],
                     "Done" if g["done"] else "Active",
                     g.get("deadline",""), g.get("created","")] for g in goal_list]
            self._upsert_rows(ws, rows)
            return True
        except Exception as e:
            log.error(f"Goals save error: {e}")
            return False

    def save_bills(self, bill_list):
        if not self.sheet or not bill_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Bills")
            rows = [[b["id"], b["name"], b["amount"], b["due_day"],
                     "Active" if b["active"] else "Inactive",
                     b.get("created","")] for b in bill_list]
            self._upsert_rows(ws, rows)
            return True
        except Exception as e:
            log.error(f"Bills save error: {e}")
            return False

    def save_calendar(self, events):
        if not self.sheet or not events:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Calendar")
            rows = [[e["id"], e["title"], e["date"], e.get("time",""),
                     e.get("created","")] for e in events]
            self._upsert_rows(ws, rows)
            return True
        except Exception as e:
            log.error(f"Calendar save error: {e}")
            return False

    def save_water(self, water_obj):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Water")
            entries = water_obj.store.data.get("entries", {})
            goal = water_obj.goal()
            rows = []
            for d, ents in sorted(entries.items())[-30:]:
                total_ml = sum(e["ml"] for e in ents)
                pct = f"{min(100, int(total_ml/goal*100))}%" if goal else "0%"
                rows.append([d, total_ml, goal, pct, len(ents)])
            if rows:
                self._upsert_rows(ws, rows, id_col=0)
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
                    text_col = str(row[3])[:50] if len(row) > 3 else ""
                    time_col = str(row[1]) if len(row) > 1 else ""
                    existing_keys.add(f"{row[0]}|{time_col}|{text_col}")
            new_rows = []
            for entry_date in sorted(all_entries_dict.keys()):
                for entry in all_entries_dict[entry_date]:
                    text_key = str(entry.get("text", ""))[:50]
                    time_col = str(entry.get("time", ""))
                    key = f"{entry_date}|{time_col}|{text_key}"
                    if key not in existing_keys:
                        new_rows.append([entry_date, entry.get("time",""),
                                         entry.get("mood","📝"), entry.get("text","")])
                        existing_keys.add(key)
            for row in new_rows:
                ws.append_row(row, value_input_option="USER_ENTERED")
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
            tasks_done = len(tasks.done_on(today))
            tasks_pending = len(tasks.today_pending())
            expenses_total = expenses.today_total()
            water_total = water.today_total()
            habits_done = len(habits.today_status()[0])
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
            else:
                ws.append_row(new_row)
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
        return f"✅ Synced {success_count}/{len(ops)} sheets!"

    def restore_from_sheets(self):
        if not self.sheet:
            return False
        restored = []
        log.info("🔄 Restoring from Google Sheets...")

        # Helper function to safely get values from rows
        def get_val(row, *keys):
            for key in keys:
                val = row.get(key, "")
                if val:
                    return val
            return row.get(keys[0], "") if keys else ""

        # ═══════════ Tasks Restore ═══════════
        try:
            ws = self.sheet.worksheet("Tasks")
            rows = ws.get_all_records()
            task_list = []
            for r in rows:
                tid = get_val(r, "ID", "id")
                title = get_val(r, "Title", "title")
                if not tid and not title:
                    continue
                task_list.append({
                    "id": int(tid) if str(tid).isdigit() else 0,
                    "title": title,
                    "priority": get_val(r, "Priority", "priority") or "medium",
                    "done": str(get_val(r, "Status", "status")).lower() == "done",
                    "created": get_val(r, "Created At", "created_at", "Created", "created") or today_str(),
                    "done_at": get_val(r, "Completed At", "completed_at", "Completed", "done_at") or "",
                    "due": get_val(r, "Due", "due") or today_str(),
                })
            if task_list:
                max_id = max((t["id"] for t in task_list), default=0)
                db.save("tasks", {"list": task_list, "counter": max_id})
                restored.append(f"📋 {len(task_list)} tasks")
        except Exception as e:
            log.warning(f"Tasks restore: {e}")

        # ═══════════ Reminders Restore ═══════════
        try:
            ws = self.sheet.worksheet("Reminders")
            rows = ws.get_all_records()
            rem_list = []
            for r in rows:
                rid = get_val(r, "ID", "id")
                text = get_val(r, "Text", "text")
                if not rid and not text:
                    continue
                rem_list.append({
                    "id": int(rid) if str(rid).isdigit() else 0,
                    "time": get_val(r, "Time", "Time (HH:MM)", "time") or "",
                    "text": text,
                    "repeat": get_val(r, "Repeat", "repeat") or "once",
                    "active": str(get_val(r, "Status", "status")).lower() != "inactive",
                    "fired_today": False,
                    "date": get_val(r, "Date", "Created Date", "date") or today_str(),
                    "created": get_val(r, "Created", "Created At", "created") or "",
                    "chat_id": int(os.environ.get("ADMIN_CHAT_ID", 0)),
                })
            if rem_list:
                max_id = max((r["id"] for r in rem_list), default=0)
                db.save("reminders", {"list": rem_list, "counter": max_id})
                restored.append(f"⏰ {len(rem_list)} reminders")
        except Exception as e:
            log.warning(f"Reminders restore: {e}")

        # ═══════════ Expenses Restore ═══════════
        try:
            ws = self.sheet.worksheet("Expenses")
            rows = ws.get_all_records()
            exp_list = []
            for r in rows:
                amount = get_val(r, "Amount", "Amount (Rs)", "amount") or "0"
                desc = get_val(r, "Description", "Desc", "description", "desc") or ""
                try:
                    amount_val = float(amount)
                    if amount_val <= 0:
                        continue
                except:
                    continue
                exp_list.append({
                    "date": get_val(r, "Date", "date") or today_str(),
                    "amount": amount_val,
                    "desc": desc,
                    "category": get_val(r, "Category", "category") or "general",
                    "time": get_val(r, "Time", "time") or "",
                })
            if exp_list:
                db.save("expenses", {"list": exp_list, "budget": None})
                restored.append(f"💰 {len(exp_list)} expenses")
        except Exception as e:
            log.warning(f"Expenses restore: {e}")

        # ═══════════ Habits Restore ═══════════
        try:
            ws = self.sheet.worksheet("Habits")
            rows = ws.get_all_records()
            hab_list = []
            for r in rows:
                name = get_val(r, "Habit Name", "Name", "name", "habit_name") or ""
                hid = get_val(r, "ID", "id")
                if not name and not hid:
                    continue
                hab_list.append({
                    "id": int(hid) if str(hid).isdigit() else 0,
                    "name": name or f"Habit {hid}",
                    "emoji": get_val(r, "Emoji", "emoji") or "✅",
                    "streak": int(get_val(r, "Current Streak", "Streak", "current_streak", "streak") or 0),
                    "best_streak": int(get_val(r, "Best Streak", "best_streak") or 0),
                    "created": get_val(r, "Created", "created") or today_str(),
                })
            if hab_list:
                max_id = max((h["id"] for h in hab_list), default=0)
                db.save("habits", {"list": hab_list, "logs": {}, "counter": max_id})
                restored.append(f"💪 {len(hab_list)} habits")
        except Exception as e:
            log.warning(f"Habits restore: {e}")

        # ═══════════ Memory Restore ═══════════
        try:
            ws = self.sheet.worksheet("Memory")
            rows = ws.get_all_records()
            facts = []
            for r in rows:
                fact = get_val(r, "Fact", "f", "fact") or ""
                if fact:
                    facts.append({
                        "d": get_val(r, "Date", "d", "date") or "",
                        "f": fact
                    })
            if facts:
                db.save("memory", {"facts": facts, "prefs": {}, "important_notes": [], "dates": {}})
                restored.append(f"🧠 {len(facts)} memories")
        except Exception as e:
            log.warning(f"Memory restore: {e}")

        # ═══════════ Goals Restore ═══════════
        try:
            ws = self.sheet.worksheet("Goals")
            rows = ws.get_all_records()
            goal_list = []
            for r in rows:
                title = get_val(r, "Title", "title") or ""
                gid = get_val(r, "ID", "id")
                if not title and not gid:
                    continue
                goal_list.append({
                    "id": int(gid) if str(gid).isdigit() else 0,
                    "title": title or f"Goal {gid}",
                    "progress": int(get_val(r, "Progress", "Progress %", "progress") or 0),
                    "done": str(get_val(r, "Status", "status")).lower() == "done",
                    "deadline": get_val(r, "Deadline", "deadline") or "",
                    "created": get_val(r, "Created", "created") or "",
                })
            if goal_list:
                max_id = max((g["id"] for g in goal_list), default=0)
                db.save("goals", {"list": goal_list, "counter": max_id})
                restored.append(f"🎯 {len(goal_list)} goals")
        except Exception as e:
            log.warning(f"Goals restore: {e}")

        # ═══════════ Bills Restore ═══════════
        try:
            ws = self.sheet.worksheet("Bills")
            rows = ws.get_all_records()
            bill_list = []
            for r in rows:
                name = get_val(r, "Name", "name") or ""
                bid = get_val(r, "ID", "id")
                if not name and not bid:
                    continue
                bill_list.append({
                    "id": int(bid) if str(bid).isdigit() else 0,
                    "name": name or f"Bill {bid}",
                    "amount": float(get_val(r, "Amount", "amount") or "0"),
                    "due_day": int(get_val(r, "Due Day", "due_day", "DueDay") or "1"),
                    "active": str(get_val(r, "Status", "Active", "status", "active")).lower() != "inactive",
                    "created": get_val(r, "Created", "created") or "",
                })
            if bill_list:
                max_id = max((b["id"] for b in bill_list), default=0)
                db.save("bills", {"list": bill_list, "paid": {}, "counter": max_id})
                restored.append(f"💳 {len(bill_list)} bills")
        except Exception as e:
            log.warning(f"Bills restore: {e}")

        # ═══════════ Calendar Restore ═══════════
        try:
            ws = self.sheet.worksheet("Calendar")
            rows = ws.get_all_records()
            events = []
            for r in rows:
                title = get_val(r, "Title", "title") or ""
                eid = get_val(r, "ID", "id")
                if not title and not eid:
                    continue
                events.append({
                    "id": int(eid) if str(eid).isdigit() else 0,
                    "title": title or f"Event {eid}",
                    "date": get_val(r, "Date", "date") or "",
                    "time": get_val(r, "Time", "time") or "",
                    "created": get_val(r, "Created", "created") or "",
                })
            if events:
                max_id = max((e["id"] for e in events), default=0)
                db.save("calendar", {"events": events, "counter": max_id})
                restored.append(f"📅 {len(events)} calendar events")
        except Exception as e:
            log.warning(f"Calendar restore: {e}")

        # ═══════════ Diary Restore ═══════════
        try:
            ws = self.sheet.worksheet("Diary")
            rows = ws.get_all_records()
            entries = {}
            for r in rows:
                d = get_val(r, "Date", "date") or ""
                if not d:
                    continue
                entries.setdefault(d, []).append({
                    "text": get_val(r, "Entry Text", "Text", "entry_text", "text") or "",
                    "mood": get_val(r, "Mood", "mood") or "📝",
                    "time": get_val(r, "Time", "time") or "",
                })
            if entries:
                db.save("diary", {"entries": entries})
                total = sum(len(v) for v in entries.values())
                restored.append(f"📖 {total} diary entries")
        except Exception as e:
            log.warning(f"Diary restore: {e}")

        if restored:
            log.info(f"✅ Restored: {' | '.join(restored)}")
        return bool(restored)


google_sheets = GoogleSheetsDB()

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
# SMART ACTION SYSTEM
# ═══════════════════════════════════════════════════════════════════
ACTION_SYSTEM_PROMPT = """You are a JSON router. Parse user message and return ONLY raw JSON (no markdown, no backticks).

Current EXACT time: {now}
24hr time: {current_time}
Today: {today}
2 min from now: {two_min}

JSON format: {{"action":"ACTION","params":{{...}},"reply":"confirm msg"}}

ACTIONS:
REMIND — {{"time":"HH:MM","text":"...","repeat":"once"}}
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
        return f"✅ *COMPLETED ({len(c)})*\n\n" + "".join(f"  ✓ #{t['id']} {t['title']}\n" for t in c[-10:])

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
            reply = call_groq_text(build_system_prompt() + "\n\nUser: " + user_msg + "\n\nShort Hindi reply:")
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
# BRIEFING BUILDER
# ═══════════════════════════════════════════════════════════════════
async def _build_briefing_text():
    n = now_ist()
    hour = n.hour
    greeting = "🌅 Subah Bakhair" if hour < 12 else "🌞 Dopahar Mubarak" if hour < 17 else "🌆 Shaam Bakhair" if hour < 20 else "🌙 Raat Bakhair"

    tp = tasks.today_pending()
    done_today = tasks.done_on(today_str())
    hd, hp = habits.today_status()
    exp_t = expenses.today_total()
    exp_m = expenses.month_total()
    bl = expenses.budget_left()
    water_t = water.today_total()
    water_g = water.goal()
    water_pct = int(water_t / water_g * 100) if water_g else 0
    cal_today = calendar.today_events()
    due_b = bills.due_soon(3)
    ag = goals.active()

    txt = f"{greeting}!\n"
    txt += f"⏰ *{n.strftime('%I:%M %p')}* | 📅 *{n.strftime('%A, %d %b')}*\n"
    txt += "━━━━━━━━━━━━━━━━━━━━\n\n"

    txt += f"📋 *TASKS* — {len(tp)} pending"
    if done_today:
        txt += f" | ✅ {len(done_today)} done today"
    txt += "\n"
    for t in tp[:4]:
        icon = "🔴" if t['priority'] == 'high' else "🟡" if t['priority'] == 'medium' else "🟢"
        txt += f"  {icon} {t['title']}\n"
    if len(tp) > 4:
        txt += f"  _...aur {len(tp)-4} aur_\n"

    txt += f"\n💪 *HABITS* — {len(hd)}/{len(hd)+len(hp)} done\n"
    if hd:
        txt += "  ✅ " + ", ".join(f"{h['emoji']}{h['name']}" for h in hd[:3]) + "\n"
    if hp:
        txt += "  ⏳ " + ", ".join(h['name'] for h in hp[:3]) + "\n"

    txt += f"\n💰 *KHARCHA* — Aaj ₹{exp_t:.0f} | Mahina ₹{exp_m:.0f}"
    if bl is not None:
        txt += f" | Budget left: ₹{bl:.0f}"
    txt += "\n"

    txt += f"\n💧 *PAANI* — {water_t}ml/{water_g}ml ({water_pct}%)\n"

    if cal_today:
        txt += "\n📅 *AAJ KE EVENTS*\n"
        for e in cal_today[:3]:
            t_str = f" @ {e['time']}" if e.get('time') else ""
            txt += f"  • {e['title']}{t_str}\n"

    if due_b:
        txt += "\n💳 *BILLS DUE*\n"
        for b in due_b[:2]:
            txt += f"  ⚠️ {b['name']} — ₹{b['amount']:.0f}\n"

    if ag:
        txt += f"\n🎯 *GOALS* — {len(ag)} active\n"
        for g in ag[:2]:
            bar = "█" * (g['progress'] // 10) + "░" * (10 - g['progress'] // 10)
            txt += f"  `{bar}` {g['title']} {g['progress']}%\n"

    return txt

# ═══════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════
async def cmd_start(update, ctx):
    n = now_ist()
    name = update.effective_user.first_name or "Dost"
    db_status = "✅ Google Sheets — Data permanent hai!" if google_sheets.sheet else "⚠️ Sheets not connected!"
    await update.message.reply_text(
        f"🕌 *Assalamualaikum {name}!*\n\n⏰ {n.strftime('%I:%M %p')} IST | 📅 {n.strftime('%d %b %Y')}\n\n"
        f"💾 *{db_status}*\n\n"
        "📋 Tasks | 💪 Habits | 📖 Diary\n"
        "💰 Expenses | ⏰ Reminders | 📰 News\n💧 Water | 💳 Bills | 📅 Calendar\n"
        "🆕 *v15: Groq AI + Smart Cache + Morning Briefing*\n\n"
        "_Seedha type karo ya /help_ 👇", parse_mode="Markdown", reply_markup=main_kb())

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
        "`/water` `/waterstatus` `/watergoal` — Water\n\n"
        "**📊 REPORTS**\n"
        "`/report YYYY-MM-DD` `/weekly` `/briefing` `/yesterday`\n\n"
        "**🎯 GOALS**\n"
        "`/goal` `/gprogress` — Goals\n\n"
        "**🔧 UTILITIES**\n"
        "`/clear` `/nuke` `/backup` `/memory`\n\n"
        "_🆕 v15: Groq AI fallback + 7:30 AM morning briefing + 10 PM digest_\n\n"
        "_Seedha type karo — AI jawab dega!_", parse_mode="Markdown")

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
        await update.message.reply_text("❌ Invalid ID!")

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
        all_h = habits.all()
        if not all_h:
            await update.message.reply_text("💪 No habits! `/habit Naam`")
            return
        hd, hp = habits.today_status()
        txt = "💪 *HABITS*\n\n"
        txt += "✅ *Done:*\n" + "\n".join(f"  {h['emoji']} {h['name']} 🔥{h.get('streak',0)}d" for h in hd) + "\n\n" if hd else ""
        txt += "⏳ *Pending:*\n" + "\n".join(f"  {h['emoji']} {h['name']} — `/hdone {h['id']}`" for h in hp) if hp else "✅ Sab done!"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return
    emoji = "✅"
    name = " ".join(ctx.args)
    for e in ["💪","🧘","📚","🏃","🥗","💧","😴","🎯","✍️","🔥"]:
        if e in name:
            emoji = e
            name = name.replace(e, "").strip()
            break
    h = habits.add(name, emoji)
    await update.message.reply_text(f"💪 Habit added: {h['emoji']} *{h['name']}*\n`/hdone {h['id']}` se mark karo!", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_hdone(update, ctx):
    if not ctx.args:
        _, pending = habits.today_status()
        if not pending:
            await update.message.reply_text("🎉 Sab habits done!")
            return
        txt = "💪 *Pending habits:*\n"
        for h in pending:
            txt += f"`/hdone {h['id']}` — {h['emoji']} {h['name']}\n"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return
    try:
        hid = int(ctx.args[0])
        ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"] == hid), None)
        if ok and h:
            await update.message.reply_text(f"💪 {h['emoji']} *{h['name']}* — Done! 🔥 Streak: {streak} days", parse_mode="Markdown")
        else:
            await update.message.reply_text("✅ Already done today!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_delhabit(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delhabit <id>`"); return
    try:
        if habits.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Habit deleted!")
        else:
            await update.message.reply_text("❌ Not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_kharcha(update, ctx):
    if not ctx.args:
        today_exp = expenses.get_by_date(today_str())
        total = expenses.today_total()
        bl = expenses.budget_left()
        txt = f"💰 *AAJ KA KHARCHA* — ₹{total:.0f}\n\n"
        for e in today_exp[-8:]:
            txt += f"  • ₹{e['amount']:.0f} — {e['desc']}\n"
        if bl is not None:
            txt += f"\n💳 Budget left: ₹{bl:.0f}"
        await update.message.reply_text(txt or "💰 Aaj koi kharcha nahi!", parse_mode="Markdown")
        return
    try:
        args = " ".join(ctx.args)
        parts = args.split(maxsplit=1)
        amount = float(parts[0])
        desc = parts[1] if len(parts) > 1 else "Kharcha"
        expenses.add(amount, desc)
        await update.message.reply_text(f"✅ ₹{amount:.0f} — {desc}\n📊 Aaj total: ₹{expenses.today_total():.0f}", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Format: `/kharcha 150 Chai`")

async def cmd_budget(update, ctx):
    if not ctx.args:
        bl = expenses.budget_left()
        bud = expenses.store.data.get("budget")
        if bud:
            await update.message.reply_text(f"💳 Budget: ₹{bud:.0f}/month\nSpent: ₹{expenses.month_total():.0f}\nLeft: ₹{bl:.0f}")
        else:
            await update.message.reply_text("💳 `/budget 5000` se set karo")
        return
    try:
        expenses.set_budget(float(ctx.args[0]))
        await update.message.reply_text(f"✅ Budget set: ₹{float(ctx.args[0]):.0f}/month")
    except:
        await update.message.reply_text("❌ Invalid amount")

async def cmd_goal(update, ctx):
    if not ctx.args:
        ag = goals.active()
        cg = goals.completed()
        if not ag and not cg:
            await update.message.reply_text("🎯 No goals! `/goal Mera goal`")
            return
        txt = "🎯 *GOALS*\n\n"
        for g in ag[:5]:
            bar = "█" * (g['progress'] // 10) + "░" * (10 - g['progress'] // 10)
            txt += f"*#{g['id']}* `{bar}` {g['title']} — {g['progress']}%\n"
        if cg:
            txt += "\n🏆 *Completed:* " + ", ".join(g['title'][:20] for g in cg[-3:])
        await update.message.reply_text(txt, parse_mode="Markdown")
        return
    g = goals.add(" ".join(ctx.args))
    await update.message.reply_text(f"🎯 Goal set: *{g['title']}*\n`/gprogress {g['id']} 50` se update karo", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_gprogress(update, ctx):
    if len(ctx.args) < 2:
        await update.message.reply_text("`/gprogress <id> <0-100>`"); return
    try:
        g = goals.update_progress(int(ctx.args[0]), int(ctx.args[1]))
        if g:
            bar = "█" * (g['progress'] // 10) + "░" * (10 - g['progress'] // 10)
            done_msg = " 🏆 *COMPLETED!*" if g['done'] else ""
            await update.message.reply_text(f"✅ *{g['title']}*\n`{bar}` {g['progress']}%{done_msg}", parse_mode="Markdown")
            await auto_backup_to_sheets()
        else:
            await update.message.reply_text("❌ Goal not found")
    except:
        await update.message.reply_text("❌ Invalid input")

async def cmd_remember(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/remember Kuch important`"); return
    fact = " ".join(ctx.args)
    memory.add_fact(fact)
    await update.message.reply_text(f"🧠 Yaad kar liya! ✅\n_{fact[:80]}_", parse_mode="Markdown")

async def cmd_recall(update, ctx):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("🧠 Koi yaad nahi abhi tak!")
        return
    query = " ".join(ctx.args).lower() if ctx.args else ""
    if query:
        filtered = [f for f in facts if query in f["f"].lower()]
        facts = filtered if filtered else facts
    txt = "🧠 *MEMORY*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_note(update, ctx):
    if not ctx.args:
        ns = notes.recent(10)
        if not ns:
            await update.message.reply_text("📝 No notes! `/note Kuch likhna hai`")
            return
        txt = "📝 *NOTES*\n\n" + "\n".join(f"#{n['id']} — {n['text'][:60]}" for n in ns)
        await update.message.reply_text(txt, parse_mode="Markdown")
        return
    n = notes.add(" ".join(ctx.args))
    await update.message.reply_text(f"📝 Note saved! `#{n['id']}`")

async def cmd_delnote(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delnote <id>`"); return
    try:
        if notes.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Note deleted!")
        else:
            await update.message.reply_text("❌ Not found")
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_briefing(update, ctx):
    txt = await _build_briefing_text()
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_weekly(update, ctx):
    n = now_ist()
    task_week = tasks.get_weekly_summary()
    total_done = sum(v["done"] for v in task_week.values())
    total_created = sum(v["created"] for v in task_week.values())
    all_h = habits.all()
    habit_completions = 0
    for i in range(7):
        d = (n.date() - timedelta(days=i)).isoformat()
        habit_completions += len(habits.get_logs_by_date(d))
    week_exp = sum(sum(e["amount"] for e in expenses.get_by_date((n.date() - timedelta(days=i)).isoformat())) for i in range(7))
    txt = f"📈 *WEEKLY SUMMARY*\n_{n.strftime('%d %b')} week_\n\n"
    txt += f"📋 Tasks: ✅ {total_done} done | ➕ {total_created} created\n"
    txt += f"💪 Habits: {habit_completions} completions\n"
    txt += f"💰 Expenses: ₹{week_exp:.0f} this week\n\n"
    txt += "*Daily:*\n"
    for d_key in sorted(task_week.keys(), reverse=True):
        v = task_week[d_key]
        exp_day = sum(e["amount"] for e in expenses.get_by_date(d_key))
        txt += f"📅 {d_key}: ✅{v['done']} done | ₹{exp_day:.0f}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_report(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📅 `/report YYYY-MM-DD`\nExample: `/report 2026-05-01`")
        return
    target = ctx.args[0]
    try:
        date.fromisoformat(target)
    except:
        await update.message.reply_text("❌ Invalid date! Use YYYY-MM-DD")
        return
    td = tasks.get_tasks_by_date(target)
    done = [t for t in td if t["done"]]
    pending = [t for t in td if not t["done"]]
    exp_day = expenses.get_by_date(target)
    diary_day = diary.get(target)
    habits_logs = habits.get_logs_by_date(target)
    habits_done = [h for h in habits.all() if h["id"] in habits_logs]
    water_day = sum(e["ml"] for e in water.store.data.get("entries", {}).get(target, []))
    txt = f"📊 *REPORT: {target}*\n━━━━━━━━━━━━━━\n\n"
    txt += f"✅ Tasks done: {len(done)}\n"
    for t in done[:5]:
        txt += f"  • {t['title']}\n"
    if pending:
        txt += f"⏳ Pending: {len(pending)}\n"
    txt += f"\n💪 Habits: {len(habits_done)}/{len(habits.all())}\n"
    if habits_done:
        txt += "  " + ", ".join(f"{h['emoji']}{h['name']}" for h in habits_done) + "\n"
    txt += f"\n💰 Kharcha: ₹{sum(e['amount'] for e in exp_day):.0f}\n"
    for e in exp_day[:4]:
        txt += f"  • ₹{e['amount']:.0f} — {e['desc']}\n"
    txt += f"\n💧 Water: {water_day}ml\n"
    if diary_day:
        txt += f"\n📖 Diary ({len(diary_day)} entries):\n"
        for en in diary_day[:2]:
            txt += f"  {en['time']} — {en['text'][:60]}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_news(update, ctx):
    await update.message.reply_text("📰 *News category:*", parse_mode="Markdown", reply_markup=news_kb())

async def cmd_clear(update, ctx):
    count = chat_hist.clear()
    await update.message.reply_text(f"🧹 Cleared {count} messages! Data safe hai ✅")

async def cmd_nuke(update, ctx):
    tracked = chat_hist.get_tracked_ids()
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💣 Delete Messages Only", callback_data="confirm_nuke"),
        InlineKeyboardButton("❌ Cancel", callback_data="menu")
    ]])
    await update.message.reply_text(
        f"💣 *Delete {len(tracked)} messages?*\n✅ Tasks, Reminders, Data — SAFE RAHENGE",
        parse_mode="Markdown", reply_markup=kb)

async def cmd_alltasks(update, ctx):
    all_t = tasks.all_tasks()
    if not all_t:
        await update.message.reply_text("📋 No tasks!")
        return
    p = tasks.pending(); c = tasks.completed_tasks()
    txt = f"📋 *ALL TASKS*\nTotal: {len(all_t)} | ⏳ {len(p)} | ✅ {len(c)}\n\n"
    if p:
        txt += "⏳ *Pending:*\n" + "\n".join(f"  #{t['id']} {t['title']}" for t in p[:10])
    if c:
        txt += "\n\n✅ *Recent:*\n" + "\n".join(f"  #{t['id']} {t['title']}" for t in c[-5:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed(update, ctx):
    c = tasks.completed_tasks()
    if not c:
        await update.message.reply_text("✅ No completed tasks yet!")
        return
    txt = f"✅ *COMPLETED ({len(c)})*\n\n" + "\n".join(f"  ✓ #{t['id']} {t['title']} — {t.get('done_at','')[:10]}" for t in c[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_yesterday(update, ctx):
    yd = yesterday_str()
    td = tasks.done_on(yd); exp = expenses.get_by_date(yd)
    diary_yd = diary.get(yd); habits_logs = habits.get_logs_by_date(yd)
    habits_done = [h for h in habits.all() if h["id"] in habits_logs]
    txt = f"📅 *YESTERDAY ({yd})*\n━━━━━━━━━━━━━━\n\n"
    txt += f"✅ Tasks: {len(td)}\n"
    for t in td[:4]:
        txt += f"  • {t['title']}\n"
    txt += f"\n💪 Habits: {len(habits_done)}/{len(habits.all())}\n"
    txt += f"\n💰 Kharcha: ₹{sum(e['amount'] for e in exp):.0f}\n"
    if diary_yd:
        txt += f"\n📖 Diary: {diary_yd[0]['text'][:60]}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_memory(update, ctx):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("🧠 No memories yet!")
        return
    txt = "🧠 *MEMORY*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_dbstatus(update, ctx):
    lines = []
    if google_sheets.sheet:
        lines.append("✅ *Google Sheets: CONNECTED!*")
    else:
        lines.append("❌ *Google Sheets: NOT CONNECTED*")
    lines.append(f"\n📊 *Data:*")
    lines.append(f"  📋 Tasks: {len(tasks.all_tasks())}")
    lines.append(f"  ⏰ Reminders: {len(reminders.all_active())}")
    lines.append(f"  💪 Habits: {len(habits.all())}")
    lines.append(f"  💰 Expenses: {len(expenses.store.data.get('list',[]))}")
    lines.append(f"  📖 Diary: {sum(len(v) for v in diary.get_all_entries().values())}")
    lines.append(f"\n🤖 *v15 AI:*")
    lines.append(f"  💎 Gemini: {'✅' if GEMINI_API_KEY else '❌'}")
    lines.append(f"  🦙 Groq (text): {'✅' if GROQ_API_KEY else '❌'}")
    lines.append(f"  🎤 Groq (voice): {'✅' if GROQ_API_KEY else '❌'}")
    lines.append(f"  🤗 HuggingFace: {'✅' if HF_TOKEN else '❌'}")
    lines.append(f"  💾 Cache entries: {len(_ai_cache)}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_backup(update, ctx):
    await update.message.reply_text("📤 Backing up...")
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
            "`/remind 8:00 Uthna daily` — daily",
            parse_mode="Markdown"); return
    time_arg = ctx.args[0].lower()
    rest = ctx.args[1:]
    repeat = "once"
    if rest and rest[-1].lower() in ["daily", "weekly"]:
        repeat = rest[-1].lower(); rest = rest[:-1]
    text = " ".join(rest) if rest else "⏰ Reminder!"
    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        remind_at = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif time_arg.endswith("h") and time_arg[:-1].isdigit():
        remind_at = (now + timedelta(hours=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        parts = time_arg.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                remind_at = f"{h:02d}:{m:02d}"
            else:
                await update.message.reply_text("❌ Invalid time!"); return
        else:
            await update.message.reply_text("❌ Format galat!"); return
    else:
        await update.message.reply_text("❌ Format galat! `/remind 2m Test`"); return
    r = reminders.add(update.effective_chat.id, text, remind_at, repeat)
    rl = {"once": "Once", "daily": "Daily 🔁", "weekly": "Weekly 📅"}.get(repeat, repeat)
    await update.message.reply_text(f"✅ *Reminder set!* ⏰ {remind_at} — {text}\n{rl}\n🆔 `#{r['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_reminders_list(update, ctx):
    active = reminders.all_active()
    now = now_ist()
    if not active:
        await update.message.reply_text(f"⏰ No reminders!\n`/remind 2m Test`", parse_mode="Markdown")
        return
    txt = f"⏰ *REMINDERS ({len(active)})*\nAbhi: *{now.strftime('%I:%M %p')} IST*\n\n"
    for r in active:
        icon = "🔁" if r["repeat"] == "daily" else "📅" if r["repeat"] == "weekly" else "1️⃣"
        txt += f"*#{r['id']}* {icon} `{r['time']}` — {r['text']} {'✅' if r['fired_today'] else '⏳'}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_delremind(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delremind <id>`"); return
    try:
        if reminders.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Reminder deleted!")
        else:
            await update.message.reply_text("❌ Not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_water(update, ctx):
    if not ctx.args:
        total = water.today_total(); goal = water.goal()
        pct = min(100, int(total/goal*100)) if goal else 0
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💧 200ml", callback_data="water_200"),
            InlineKeyboardButton("💧 300ml", callback_data="water_300"),
            InlineKeyboardButton("💧 500ml", callback_data="water_500"),
        ]])
        await update.message.reply_text(
            f"💧 *WATER*\n\nToday: {total}ml/{goal}ml ({pct}%)\n\nQuick add:",
            parse_mode="Markdown", reply_markup=kb)
        return
    try:
        ml = int(ctx.args[0])
        water.add(ml)
        total = water.today_total(); goal = water.goal()
        await update.message.reply_text(f"💧 +{ml}ml! Total: {total}ml/{goal}ml")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ `/water 250`")

async def cmd_water_status(update, ctx):
    total = water.today_total(); goal = water.goal()
    pct = min(100, int(total/goal*100)) if goal else 0
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    await update.message.reply_text(f"💧 *Water Today*\n`{bar}` {pct}%\n{total}ml / {goal}ml", parse_mode="Markdown")

async def cmd_water_goal(update, ctx):
    if not ctx.args:
        await update.message.reply_text(f"💧 Goal: {water.goal()}ml\n`/watergoal 2500` se change karo"); return
    try:
        water.set_goal(int(ctx.args[0]))
        await update.message.reply_text(f"✅ Water goal: {int(ctx.args[0])}ml/day")
    except:
        await update.message.reply_text("❌ Invalid amount")

async def cmd_bill(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/bill BillName Amount DueDay`\nExample: `/bill Electricity 500 15`"); return
    try:
        args = ctx.args
        name = args[0]; amount = float(args[1]); due_day = int(args[2])
        b = bills.add(name, amount, due_day)
        await update.message.reply_text(f"✅ Bill: *{b['name']}* — ₹{b['amount']:.0f} (due {b['due_day']}th)", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ `/bill Name Amount DueDay`")

async def cmd_bills_list(update, ctx):
    all_b = bills.all_active()
    if not all_b:
        await update.message.reply_text("💳 No bills! `/bill Name Amount Day`")
        return
    txt = "💳 *BILLS*\n\n"
    for b in all_b:
        status = "✅ Paid" if bills.is_paid_this_month(b["id"]) else "⏳ Pending"
        txt += f"*#{b['id']}* {status} — *{b['name']}* ₹{b['amount']:.0f} (due {b['due_day']}th)\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_bill_paid(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/billpaid <id>`"); return
    try:
        bills.mark_paid(int(ctx.args[0]))
        await update.message.reply_text("✅ Bill marked as paid!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_del_bill(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delbill <id>`"); return
    try:
        if bills.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Bill deleted!")
        else:
            await update.message.reply_text("❌ Not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_cal(update, ctx):
    if not ctx.args:
        upcoming = calendar.upcoming(30)
        if not upcoming:
            await update.message.reply_text("📅 No events! `/cal 2026-05-10 Meeting`")
            return
        txt = "📅 *UPCOMING*\n\n"
        for e in upcoming[:10]:
            flag = "🔴 TODAY" if e["date"] == today_str() else "📆"
            t = f" @ {e['time']}" if e.get("time") else ""
            txt += f"{flag} {e['date']}{t} — {e['title']}\n"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return
    args_str = " ".join(ctx.args)
    date_str = None; title = ""; event_time = ""
    if args_str.lower().startswith("aaj "):
        date_str = today_str(); title = args_str[4:]
    elif args_str.lower().startswith("kal "):
        date_str = (now_ist().date() + timedelta(days=1)).isoformat(); title = args_str[4:]
    elif _re.match(r'\d{4}-\d{2}-\d{2}', args_str):
        date_str = args_str[:10]; title = args_str[11:]
    if not date_str:
        await update.message.reply_text("❌ `/cal YYYY-MM-DD Event`\n`/cal aaj Meeting`"); return
    t_match = _re.search(r'(\d{1,2}:\d{2})', title)
    if t_match:
        event_time = t_match.group(1); title = title.replace(event_time, "").strip()
    try:
        date.fromisoformat(date_str)
        e = calendar.add(title, date_str, event_time)
        await update.message.reply_text(f"📅 Event: *{title}* — {date_str}" + (f" ⏰{event_time}" if event_time else ""), parse_mode="Markdown")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid date!")

async def cmd_cal_list(update, ctx):
    upcoming = calendar.upcoming(30)
    if not upcoming:
        await update.message.reply_text("📅 No upcoming events!")
        return
    txt = "📅 *UPCOMING EVENTS*\n\n"
    for e in upcoming[:15]:
        flag = "🔴 TODAY" if e["date"] == today_str() else "📆"
        t = f" @ {e['time']}" if e.get("time") else ""
        txt += f"{flag} {e['date']}{t} — {e['title']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_del_cal(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delcal <id>`"); return
    try:
        if calendar.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Event deleted!")
        else:
            await update.message.reply_text("❌ Not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID!")

# ═══════════════════════════════════════════════════════════════════
# DIARY COMMANDS
# ═══════════════════════════════════════════════════════════════════
async def cmd_diary(update, ctx):
    args = ctx.args
    if args and args[0] not in ("date", "all", "week"):
        text = " ".join(args)
        diary.add(text, mood="📝")
        await update.message.reply_text(f"📖 *Diary saved!* 🕐 {now_str()}\n\n_{text[:120]}_", parse_mode="Markdown")
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
    await update.message.reply_text("🔐 *Diary Password:*\n_Password daalo:_", parse_mode="Markdown")
    return DIARY_AWAIT_PASS

async def cmd_diary_view(update, ctx):
    ctx.user_data["diary_view"] = ("today", None)
    await update.message.reply_text("🔐 *Diary Password:*", parse_mode="Markdown")
    return DIARY_AWAIT_PASS

async def diary_password_check(update, ctx):
    entered = update.message.text.strip()
    if entered != DIARY_PASSWORD:
        await update.message.reply_text("❌ *Galat password!*", parse_mode="Markdown")
        return ConversationHandler.END
    view_type, view_arg = ctx.user_data.get("diary_view", ("today", None))
    await _show_diary(update, view_type, view_arg)
    return ConversationHandler.END

async def diary_conv_cancel(update, ctx):
    try:
        if update.message:
            await update.message.reply_text("⏱ Diary session expired.")
    except:
        pass
    return ConversationHandler.END

async def _show_diary(update, view_type, view_arg):
    if view_type == "today":
        entries = diary.get(today_str())
        title = f"📖 *Aaj Ki Diary — {today_str()}*"
        all_entries = {today_str(): entries} if entries else {}
    elif view_type == "date" and view_arg:
        entries = diary.get(view_arg)
        title = f"📖 *Diary — {view_arg}*"
        all_entries = {view_arg: entries} if entries else {}
    elif view_type == "all":
        all_entries = diary.get_all_entries()
        title = "📖 *All Diary Entries*"
    elif view_type == "week":
        all_entries = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            ents = diary.get(d)
            if ents:
                all_entries[d] = ents
        title = "📖 *This Week's Diary*"
    else:
        all_entries = {}
        title = "📖 *Diary*"

    if not all_entries:
        await update.message.reply_text(f"{title}\n\n_Koi entry nahi._", parse_mode="Markdown")
        return

    txt = f"{title}\n\n"
    for d_key in sorted(all_entries.keys(), reverse=True)[:7]:
        txt += f"📅 *{d_key}*\n"
        for e in all_entries[d_key][-3:]:
            txt += f"  {e.get('mood','📝')} {e.get('time','')} — {e.get('text','')[:100]}\n"
        txt += "\n"
    try:
        await update.message.reply_text(txt, parse_mode="Markdown")
    except:
        await update.message.reply_text(txt)

# ═══════════════════════════════════════════════════════════════════
# SECRET COMMANDS
# ═══════════════════════════════════════════════════════════════════
async def verify_secret(update, ctx, action):
    if not ctx.args or ctx.args[0] != SECRET_CODE:
        await update.message.reply_text("🔒 Access denied!")
        return False
    return True

async def cmd_tasklogs(update, ctx):
    if not await verify_secret(update, ctx, "tasklogs"): return
    logs_data = task_logs.get_all_logs()
    if not logs_data:
        await update.message.reply_text("📋 No logs!"); return
    by_date = defaultdict(list)
    for l in logs_data:
        by_date[l.get("date","?")].append(l)
    txt = f"📋 *TASK LOGS ({len(logs_data)})*\n\n"
    for d in sorted(by_date.keys(), reverse=True)[:5]:
        txt += f"📅 *{d}*\n"
        for l in by_date[d][-3:]:
            icon = '➕' if l['type']=='created' else '✅' if l['type']=='completed' else '🗑'
            txt += f"  {icon} {l['description'][:40]}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_failed(update, ctx):
    if not await verify_secret(update, ctx, "failed"): return
    unretried = failed_reqs.get_unretried()
    if not unretried:
        await update.message.reply_text("✅ No failed requests!"); return
    txt = f"📝 *FAILED ({len(unretried)})*\n\n"
    for r in unretried[:5]:
        txt += f"• {r['msg'][:50]}...\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_retry_failed(update, ctx):
    if not await verify_secret(update, ctx, "retryfailed"): return
    unretried = failed_reqs.get_unretried()
    if not unretried:
        await update.message.reply_text("✅ No failed requests!"); return
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
    if not await verify_secret(update, ctx, "fulldata"): return
    txt = f"📊 *FULL DATA*\n\n"
    txt += f"🧠 Memory: {len(memory.get_all_facts())}\n"
    txt += f"📋 Tasks: {len(tasks.all_tasks())}\n"
    txt += f"💪 Habits: {len(habits.all())}\n"
    txt += f"⏰ Reminders: {len(reminders.all_active())}\n"
    txt += f"💰 Month: ₹{expenses.month_total():.0f}\n"
    txt += f"📖 Diary today: {len(diary.get(today_str()))}\n"
    txt += f"🎯 Goals: {len(goals.active())}\n"
    txt += f"💧 Water: {water.today_total()}ml\n"
    txt += f"💳 Bills: {len(bills.all_active())}\n"
    txt += f"💾 AI Cache: {len(_ai_cache)} entries\n"
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
        return

    if d == "menu":
        await message.edit_text("🏠 *Main Menu*", parse_mode="Markdown", reply_markup=main_kb())

    elif d == "briefing":
        try:
            txt = await _build_briefing_text()
            await message.edit_text(txt, parse_mode="Markdown", reply_markup=main_kb())
        except Exception as e:
            log.error(f"Briefing callback: {e}")
            await message.edit_text("❌ Briefing load nahi hua, /briefing try karo.", reply_markup=back_kb())

    elif d == "tasks":
        pending = tasks.pending()
        if not pending:
            await message.edit_text("🎉 No pending tasks!", reply_markup=back_kb()); return
        txt = "📋 *PENDING TASKS*\n\n"
        for t in pending[:10]:
            icon = "🔴" if t['priority']=='high' else "🟡" if t['priority']=='medium' else "🟢"
            txt += f"{icon} *#{t['id']}* {t['title']}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "all_tasks":
        all_t = tasks.all_tasks()
        if not all_t:
            await message.edit_text("📋 Koi task nahi!", reply_markup=back_kb()); return
        p = tasks.pending(); c = tasks.completed_tasks()
        txt = f"📋 *ALL ({len(all_t)})*\n⏳{len(p)} | ✅{len(c)}\n\n"
        if p:
            txt += "*⏳ Pending:*\n" + "\n".join(f"  #{t['id']} {t['title']}" for t in p[:8])
        if c:
            txt += "\n*✅ Done (last 5):*\n" + "\n".join(f"  #{t['id']} {t['title']}" for t in c[-5:])
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "completed_tasks":
        c = tasks.completed_tasks()
        if not c:
            await message.edit_text("✅ Koi completed task nahi!", reply_markup=back_kb()); return
        txt = f"✅ *COMPLETED ({len(c)})*\n\n" + "\n".join(f"  ✓ #{t['id']} {t['title']}" for t in c[-15:])
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "habits":
        done, pending = habits.today_status()
        txt = "💪 *HABITS TODAY*\n\n"
        if done:
            txt += "✅ *Done:*\n" + "\n".join(f"   {h['emoji']} {h['name']} 🔥{h.get('streak',0)}d" for h in done) + "\n\n"
        if pending:
            txt += "⏳ *Pending:*\n" + "\n".join(f"   {h['emoji']} {h['name']}\n   `/hdone {h['id']}`" for h in pending)
        if not done and not pending:
            txt += "_No habits! `/habit` se add karo._"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "diary_write":
        ctx.user_data["awaiting_diary_entry"] = True
        await message.edit_text(
            "📖 *Diary Entry Likho:*\n\n_Neeche type karo — save ho jayegi!_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="menu")]]))

    elif d == "goals":
        ag = goals.active(); cg = goals.completed()
        if not ag and not cg:
            await message.edit_text("🎯 No goals! `/goal` se add karo.", reply_markup=back_kb()); return
        txt = "🎯 *GOALS*\n\n"
        for g in ag[:5]:
            bar = "█" * (g['progress'] // 10) + "░" * (10 - g['progress'] // 10)
            txt += f"*#{g['id']}* `{bar}` {g['title']} — {g['progress']}%\n\n"
        if cg:
            txt += "*Completed:*\n" + "\n".join(f"  🏆 {g['title']}" for g in cg[-3:])
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "expenses":
        txt = f"💰 *EXPENSES*\n\nAaj: ₹{expenses.today_total():.0f}\nMahina: ₹{expenses.month_total():.0f}"
        bl = expenses.budget_left()
        if bl is not None:
            txt += f"\nBudget left: ₹{bl:.0f}"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "notes":
        ns = notes.recent(10)
        if not ns:
            await message.edit_text("📝 No notes! `/note` se add.", reply_markup=back_kb()); return
        txt = "📝 *NOTES*\n\n" + "\n".join(f"#{n['id']} — {n['text'][:50]}" for n in ns)
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "memory":
        facts = memory.get_all_facts()
        if not facts:
            await message.edit_text("🧠 No memories!", reply_markup=back_kb()); return
        txt = "🧠 *MEMORY*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-10:])
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "yesterday":
        yd = yesterday_str(); td = tasks.done_on(yd); exp = expenses.get_by_date(yd)
        diary_yd = diary.get(yd)
        txt = f"📊 *YESTERDAY ({yd})*\n\n✅ Tasks: {len(td)}\n"
        for t in td[:4]:
            txt += f"  • {t['title']}\n"
        txt += f"\n💰 Kharcha: ₹{sum(e['amount'] for e in exp):.0f}"
        if diary_yd:
            txt += f"\n\n📖 Diary: {diary_yd[0]['text'][:60]}"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "weekly_report":
        task_week = tasks.get_weekly_summary()
        total_done = sum(v["done"] for v in task_week.values())
        total_created = sum(v["created"] for v in task_week.values())
        txt = f"📈 *WEEKLY*\n\n📋 {total_done} done | {total_created} created\n\n*Daily:*\n"
        for d_key in sorted(task_week.keys(), reverse=True):
            v = task_week[d_key]
            exp_d = sum(e["amount"] for e in expenses.get_by_date(d_key))
            txt += f"📅 {d_key}: ✅{v['done']} | ₹{exp_d:.0f}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "news_menu":
        await message.edit_text("📰 *Category:*", parse_mode="Markdown", reply_markup=news_kb())

    elif d.startswith("news_"):
        category = d.split("_", 1)[1]
        items = news_store.get(category, 5)
        if not items:
            await message.edit_text("📰 News unavailable.", reply_markup=back_kb()); return
        txt = f"📰 *{category.upper()}*\n\n" + "\n".join(f"• {item['title']}" for item in items)
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "water_status":
        total = water.today_total(); goal = water.goal()
        pct = min(100, int(total/goal*100)) if goal else 0
        await message.edit_text(f"💧 *Water*\n\n{total}ml/{goal}ml ({pct}%)\n\n`/water` to log!", parse_mode="Markdown")

    elif d.startswith("water_") and d.split("_")[1].isdigit():
        water.add(int(d.split("_")[1]))
        total = water.today_total(); goal = water.goal()
        await message.edit_text(f"💧 +{d.split('_')[1]}ml | Total: {total}ml/{goal}ml", reply_markup=back_kb())
        await auto_backup_to_sheets()

    elif d == "bills_menu":
        all_b = bills.all_active()
        if not all_b:
            await message.edit_text("💳 No bills! `/bill`", reply_markup=back_kb()); return
        txt = "💳 *BILLS*\n\n"
        for b in all_b:
            status = "✅" if bills.is_paid_this_month(b["id"]) else "⏳"
            txt += f"{status} *{b['name']}* — ₹{b['amount']:.0f} (due {b['due_day']}th)\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "cal_menu":
        upcoming = calendar.upcoming(30)
        if not upcoming:
            await message.edit_text("📅 No events!", reply_markup=back_kb()); return
        txt = "📅 *UPCOMING*\n\n"
        for e in upcoming[:15]:
            flag = "🔴 TODAY" if e["date"] == today_str() else "📆"
            t = f" @ {e['time']}" if e.get("time") else ""
            txt += f"{flag} {e['date']}{t} — {e['title']}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

    elif d == "report_menu":
        await message.edit_text("📅 `/report YYYY-MM-DD`\nExample: `/report 2026-05-01`", parse_mode="Markdown")

    elif d == "motivate":
        reply = get_ai_reply("Give me a powerful short motivation in Hindi (2 lines)")
        await message.edit_text(f"💡 *MOTIVATION*\n\n{reply}", parse_mode="Markdown", reply_markup=back_kb())

    elif d == "backup_now":
        await message.edit_text("📤 Backing up...", reply_markup=back_kb())
        result = google_sheets.full_sync()
        await message.edit_text(result, reply_markup=main_kb())

    elif d == "clear_chat":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Clear", callback_data="confirm_clear_chat"),
            InlineKeyboardButton("❌ Cancel", callback_data="menu")
        ]])
        await message.edit_text("🧹 Clear chat messages?\n✅ Data SAFE rahega!", parse_mode="Markdown", reply_markup=kb)

    elif d == "confirm_clear_chat":
        count = chat_hist.clear()
        await message.edit_text(f"🧹 Cleared {count} messages!\n✅ Data safe!", reply_markup=main_kb())

    elif d == "confirm_nuke":
        tracked = chat_hist.get_tracked_ids()
        cid = message.chat_id
        status = await message.reply_text("🧹 Clearing...")
        deleted = 0
        for entry in tracked:
            try:
                await query.get_bot().delete_message(chat_id=entry["chat_id"], message_id=entry["msg_id"])
                deleted += 1
            except:
                pass
        chat_hist.clear(); chat_hist.clear_msg_ids()
        try:
            await status.delete()
        except:
            pass
        await query.get_bot().send_message(
            chat_id=cid, text=f"🧹 {deleted} messages deleted!\n✅ Data SAFE!", reply_markup=main_kb())

    elif d.startswith("done_"):
        tid = int(d.split("_")[1])
        t = tasks.complete(tid)
        if t:
            await message.edit_text(f"🎉 Done: {t['title']}", reply_markup=back_kb())
        else:
            await message.edit_text("❌ Not found!", reply_markup=back_kb())
        await auto_backup_to_sheets()

    elif d.startswith("habit_"):
        hid = int(d.split("_")[1])
        ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"] == hid), None)
        if ok and h:
            await message.edit_text(f"💪 {h['emoji']} {h['name']} — 🔥 {streak} days!", reply_markup=back_kb())
        else:
            await message.edit_text("✅ Already done today!", reply_markup=back_kb())
        await auto_backup_to_sheets()

    elif d.startswith("remind_done_"):
        rid = int(d.split("_")[2])
        reminders.mark_fired(rid)
        await message.edit_text("✅ Done!", reply_markup=back_kb())
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
        await message.edit_text("🗑 Deleted!", reply_markup=back_kb())
        await auto_backup_to_sheets()

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
        ctx.user_data.pop("awaiting_diary_entry", None)
        diary.add(user_msg, mood="📝")
        await update.message.reply_text(
            f"📖 *Diary saved!* 🕐 {now_str()}\n\n_{user_msg[:150]}_",
            parse_mode="Markdown", reply_markup=main_kb())
        await auto_backup_to_sheets()
        return

    if ctx.user_data.get("diary_from_callback"):
        ctx.user_data.pop("diary_from_callback", None)
        if user_msg == DIARY_PASSWORD:
            view_type, view_arg = ctx.user_data.get("diary_view", ("today", None))
            await _show_diary(update, view_type, view_arg)
        else:
            await update.message.reply_text("❌ *Galat password!*", parse_mode="Markdown")
        return

    ctx.user_data.pop("diary_view", None)

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ai_chat(user_msg, update.effective_chat.id)
    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(reply)

# ═══════════════════════════════════════════════════════════════════
# JOB QUEUE — BACKGROUND TASKS
# ═══════════════════════════════════════════════════════════════════
async def reminder_job(context):
    now = now_ist()
    now_time = now.strftime("%H:%M")
    active_count = len(reminders.all_active())
    if active_count > 0 and now.second < 35:
        log.info(f"⏰ Check {now_time} IST | Active: {active_count}")
    if now_time in ("00:00", "00:01", "00:02"):
        reminders.reset_daily()
        log.info("🔄 Daily reset")
        return
    due = reminders.due_now()
    for r in due:
        try:
            repeat_note = ""
            if r["repeat"] == "daily":
                repeat_note = "\n🔁 _Kal bhi yaad dilaunga!_"
            elif r["repeat"] == "weekly":
                repeat_note = "\n📅 _Agli hafte!_"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Done", callback_data=f"remind_done_{r['id']}"),
                InlineKeyboardButton("⏰ 10min Snooze", callback_data=f"remind_snooze_{r['id']}")
            ]])
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=f"🚨🔔🚨 *ALARM!* 🚨🔔🚨\n{'═'*25}\n⏰ *{r['time']} BAJ GAYE!*\n{'═'*25}\n\n📢 *{r['text'].upper()}*\n{repeat_note}",
                parse_mode="Markdown", disable_notification=False, reply_markup=kb
            )
            reminders.mark_fired(r["id"])
            log.info(f"✅ Fired #{r['id']}")
            await asyncio.sleep(1)
        except Exception as e:
            log.error(f"❌ Reminder #{r['id']} failed: {e}")
            try:
                reminders.mark_fired(r["id"])
            except:
                pass

async def failed_retry_job(context):
    unretried = failed_reqs.get_unretried()
    if not unretried:
        return
    for i, r in enumerate(unretried[:3]):
        try:
            reply = await ai_chat(r["msg"], r["chat_id"])
            if not reply.startswith("⚠️"):
                failed_reqs.mark_retried(i)
                try:
                    await context.bot.send_message(chat_id=r["chat_id"],
                        text=f"📝 *Saved request:*\n_{reply}_", parse_mode="Markdown")
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
    total = water.today_total(); goal = water.goal()
    if total >= goal:
        return
    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    for cid in chat_ids:
        try:
            await context.bot.send_message(
                chat_id=cid,
                text=f"💧 *Paani peene ka time!*\nToday: {total}ml/{goal}ml\n`/water` se log karo",
                parse_mode="Markdown")
        except:
            pass

# ═══════════════════════════════════════════════════════════════════
# 🌅 v15 NEW: PROACTIVE MORNING BRIEFING (7:30 AM)
# Smart local analysis — zero AI API call
# ═══════════════════════════════════════════════════════════════════
async def proactive_morning_job(context):
    now = now_ist()
    if now.strftime("%H:%M") != "07:30":
        return

    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    if not chat_ids:
        return

    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    due_bills = bills.due_soon(2)
    cal_today = calendar.today_events()
    water_goal_val = water.goal()
    all_h = habits.all()

    insights = []

    # Task load analysis
    if len(tp) >= 5:
        high_priority = [t for t in tp if t.get("priority") == "high"]
        if high_priority:
            insights.append(f"🔴 *{len(high_priority)} HIGH priority tasks!* Focus inpe pehle")
        else:
            insights.append(f"⚠️ *Aaj workload zyada hai* — {len(tp)} tasks pending!")
    elif len(tp) == 0:
        insights.append("✅ *Aaj koi pending task nahi!* Clean slate — naya kaam add karo")
    else:
        insights.append(f"📋 *{len(tp)} task(s) pending* aaj ke liye")

    # Habit streak at risk
    at_risk = [h for h in all_h if h.get('streak', 0) >= 3 and h['id'] not in [x['id'] for x in hd]]
    if at_risk:
        names = ", ".join(h['name'] for h in at_risk[:2])
        insights.append(f"🔥 *Streak at risk!* {names} — aaj zaroor complete karo!")

    # Bills
    for b in due_bills[:2]:
        insights.append(f"💳 *{b['name']}* ka bill due — ₹{b['amount']:.0f}")

    # Calendar
    for e in cal_today[:2]:
        t_str = f" @ {e['time']}" if e.get('time') else ""
        insights.append(f"📅 *{e['title']}*{t_str} — aaj")

    # Day-specific motivation
    day_name = now.strftime("%A")
    day_msgs = {
        "Monday":    "💪 *Naya hafta, naya jazbaa!* Best effort dena.",
        "Friday":    "🎉 *Friday hai!* Week strong finish karo.",
        "Saturday":  "☕ *Saturday!* Thoda rest, thodi planning.",
        "Sunday":    "☀️ *Sunday!* Agli hafte ki tayyari karo.",
        "Wednesday": "📈 *Hafte ka beech!* Momentum maintain karo.",
    }
    if day_name in day_msgs:
        insights.append(day_msgs[day_name])

    msg = (f"🌅 *GOOD MORNING!*\n"
           f"_{now.strftime('%A, %d %b')} — {now.strftime('%I:%M %p')} IST_\n\n")
    msg += "\n".join(f"• {i}" for i in insights[:6])
    msg += f"\n\n💧 Paani goal aaj: *{water_goal_val}ml*"
    msg += "\n\n_/briefing se full summary_ 👇"

    for cid in chat_ids:
        try:
            await context.bot.send_message(chat_id=cid, text=msg, parse_mode="Markdown")
        except Exception as e:
            log.warning(f"Morning briefing failed {cid}: {e}")

# ═══════════════════════════════════════════════════════════════════
# 📊 v15 NEW: NIGHTLY ANALYTICS (10 PM daily + Sunday weekly)
# ═══════════════════════════════════════════════════════════════════
async def weekly_analytics_job(context):
    now = now_ist()
    if now.strftime("%H:%M") != "22:00":
        return

    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    if not chat_ids:
        return

    today_done = len(tasks.done_on(today_str()))
    today_exp = expenses.today_total()
    habits_done_today, habits_pending_today = habits.today_status()
    all_h = habits.all()
    is_sunday = now.weekday() == 6

    if is_sunday:
        # Full weekly analytics
        task_week = tasks.get_weekly_summary()
        week_done = sum(v["done"] for v in task_week.values())
        week_created = sum(v["created"] for v in task_week.values())
        habit_completions = sum(len(habits.get_logs_by_date((now.date() - timedelta(days=i)).isoformat())) for i in range(7))
        week_expense = sum(sum(e["amount"] for e in expenses.get_by_date((now.date() - timedelta(days=i)).isoformat())) for i in range(7))
        max_possible = len(all_h) * 7
        habit_score = int(habit_completions / max_possible * 100) if max_possible > 0 else 0
        task_score = int(week_done / week_created * 100) if week_created > 0 else 100
        avg_score = (task_score + habit_score) // 2

        msg = (f"📊 *WEEKLY ANALYTICS*\n"
               f"_{now.strftime('%d %b')} week review_\n\n"
               f"📋 *Tasks:* ✅ {week_done}/{week_created} — *{task_score}%*\n"
               f"💪 *Habits:* {habit_completions} completions — *{habit_score}%*\n"
               f"💰 *Expenses:* ₹{week_expense:.0f} this week\n\n")

        if avg_score >= 80:
            msg += "🏆 *Grade: EXCELLENT!* Mazaa aa gaya yaar!"
        elif avg_score >= 60:
            msg += "👍 *Grade: GOOD!* Aur better ho sakta hai!"
        elif avg_score >= 40:
            msg += "📈 *Grade: AVERAGE.* Agli hafte zyada focus karo!"
        else:
            msg += "💪 *Grade: NEEDS WORK.* Kal se naya jazbaa!"
        msg += f"\n\n_/weekly se detailed breakdown dekho_"
    else:
        # Daily night digest
        msg = (f"🌙 *Aaj ka Summary*\n"
               f"_{now.strftime('%A, %d %b')}_\n\n"
               f"✅ Tasks done: {today_done}\n"
               f"💪 Habits: {len(habits_done_today)}/{len(all_h)}\n"
               f"💰 Kharcha: ₹{today_exp:.0f}\n")
        if habits_pending_today:
            msg += f"\n⏳ Abhi pending: {', '.join(h['name'] for h in habits_pending_today[:3])}"
        msg += "\n\n_Kal phir fresh start!_ 🌟"

    for cid in chat_ids:
        try:
            await context.bot.send_message(chat_id=cid, text=msg, parse_mode="Markdown")
        except Exception as e:
            log.warning(f"Analytics failed {cid}: {e}")

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
    log.info(f"📅 Daily log: {result}")

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    n = now_ist()
    log.info("=" * 60)
    log.info(f"🤖 Bot v15 — JARVIS UPGRADE")
    log.info(f"⏰ IST: {n.strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"📊 Sheets: {'✅' if google_sheets.sheet else '❌'}")
    log.info(f"💎 Gemini: {'YES' if GEMINI_API_KEY else 'NO'} | 🦙 Groq: {'YES' if GROQ_API_KEY else 'NO'} | 🤗 HF: {'YES' if HF_TOKEN else 'NO'}")
    log.info(f"🆕 v15: Groq text + Smart router + Cache + Morning briefing")
    log.info("=" * 60)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    async def post_init(app):
        try:
            chat_id = os.environ.get("ADMIN_CHAT_ID", "")
            if chat_id:
                r_count = len(reminders.store.data.get("list", []))
                t_count = len(tasks.store.data.get("list", []))
                active_rem = [r for r in reminders.store.data.get("list", []) if r.get("active")]
                rem_info = "\n".join(f"  • {r['time']} — {r['text']}" for r in active_rem[:3]) or "  Koi nahi"
                sheets_msg = "✅ Sheets connected!" if google_sheets.sheet else "❌ Sheets NOT connected!"
                ai_status = f"💎 Gemini {'✅' if GEMINI_API_KEY else '❌'} | 🦙 Groq {'✅' if GROQ_API_KEY else '❌'}"
                n2 = now_ist()
                await app.bot.send_message(
                    chat_id=int(chat_id),
                    text=(f"🤖 *Bot v15 Start!*\n\n"
                          f"⏰ {n2.strftime('%d %b %Y %I:%M %p')} IST\n\n"
                          f"📊 {sheets_msg}\n"
                          f"🤖 {ai_status}\n\n"
                          f"📦 *Data:* ⏰ {r_count} reminders | 📋 {t_count} tasks\n\n"
                          f"⏰ *Active reminders:*\n{rem_info}\n\n"
                          f"🆕 *v15 upgrades:* Groq text + Cache + Morning briefing"),
                    parse_mode="Markdown"
                )
        except Exception as e:
            log.warning(f"Startup notification failed: {e}")

    app.post_init = post_init

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
        ("news", cmd_news), ("clear", cmd_clear), ("nuke", cmd_nuke),
        ("alltasks", cmd_alltasks), ("completed", cmd_completed), ("yesterday", cmd_yesterday),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list), ("delremind", cmd_delremind),
        ("water", cmd_water), ("waterstatus", cmd_water_status), ("watergoal", cmd_water_goal),
        ("bill", cmd_bill), ("bills", cmd_bills_list), ("billpaid", cmd_bill_paid), ("delbill", cmd_del_bill),
        ("cal", cmd_cal), ("calendar", cmd_cal_list), ("delcal", cmd_del_cal),
        ("memory", cmd_memory), ("backup", cmd_backup), ("dbstatus", cmd_dbstatus),
        # Secret commands
        ("tasklogs", cmd_tasklogs), ("failed", cmd_failed),
        ("retryfailed", cmd_retry_failed), ("fulldata", cmd_fulldata),
    ]

    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))

    # Diary conversation
    diary_conv = ConversationHandler(
        entry_points=[
            CommandHandler("diary", cmd_diary),
            CommandHandler("diaryview", cmd_diary_view),
        ],
        states={
            DIARY_AWAIT_PASS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, diary_conv_cancel)
            ],
        },
        fallbacks=[CommandHandler("cancel", diary_conv_cancel)],
        per_user=True, per_chat=True, conversation_timeout=60,
    )
    app.add_handler(diary_conv)

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    # JOB QUEUE
    if app.job_queue:
        app.job_queue.run_repeating(reminder_job,            interval=60,    first=15)
        app.job_queue.run_repeating(proactive_morning_job,   interval=60,    first=30)   # v15 NEW
        app.job_queue.run_repeating(weekly_analytics_job,    interval=60,    first=45)   # v15 NEW
        app.job_queue.run_repeating(failed_retry_job,        interval=300,   first=180)
        app.job_queue.run_repeating(bill_due_job,            interval=3600,  first=300)
        app.job_queue.run_repeating(water_reminder_job,      interval=3600,  first=600)
        app.job_queue.run_repeating(scheduled_backup_job,    interval=3600,  first=120)
        app.job_queue.run_daily(daily_log_job, time=dt_module.time(hour=21, minute=0, tzinfo=IST))
        log.info("⏰ Jobs: Reminders(60s) | Morning(60s) | Analytics(60s) | Retry(5min) | Bills/Water(1hr) | Backup(1hr)")
    else:
        log.error("❌ JobQueue NOT AVAILABLE!")

    log.info("✅ Bot v15 ready!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
