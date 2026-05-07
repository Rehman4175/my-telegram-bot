#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
в•”в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•—
в•‘     PERSONAL AI ASSISTANT вҖ” v15.0 JARVIS                        в•‘
в•‘  + GROQ TEXT (Llama 3.3 70B) + Gemini primary                   в•‘
в•‘  + Google Sheets permanent storage (auto-backup every step)     в•‘
в•‘  + Smart local router + AI cache (5min TTL)                     в•‘
в•‘  + Clean code: no HF, no keyboards, no unused stores            в•‘
в•ҡв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•қ
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

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# LOGGING
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# CONFIG
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", os.environ.get("Google_CREDS_JSON", ""))
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
SECRET_CODE = "Rk1996"
DIARY_PASSWORD = "Rk1996"
DIARY_AWAIT_PASS = 1

if not TELEGRAM_TOKEN:
    log.error("вқҢ TELEGRAM_TOKEN not set!")
    exit(1)

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# INDIAN STANDARD TIME (IST)
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
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
    return f"{days.get(n.weekday(),'')}, {n.day} {n.strftime('%b')} {n.year} вҖ” {n.strftime('%I:%M %p')} IST"

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# DATABASE вҖ” JSON local cache + Google Sheets sync
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
class Database:
    def __init__(self):
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)
        log.info("рҹ’ҫ Database: JSON local cache + Google Sheets sync")

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

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# GEMINI API
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
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
                log.info(f"вң… Gemini: {model}")
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

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# GROQ TEXT API (FREE вҖ” Llama 3.3 70B)
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"
_last_groq_text_call = 0

def call_groq_text(prompt, max_tokens=400):
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
                log.info(f"вң… Groq text: {GROQ_TEXT_MODEL}")
                return text
    except Exception as e:
        log.warning(f"Groq text fail: {e}")
    return None

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# SMART OFFLINE FALLBACK
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
def smart_fallback(user_msg):
    msg = user_msg.lower()
    n = now_ist()

    if any(w in msg for w in ["time", "baje", "kitne baje", "time kya"]):
        return f"вҸ° Abhi *{n.strftime('%I:%M %p')}* baj rahe hain (IST)"
    if any(w in msg for w in ["date", "aaj kya", "tarikh", "aaj kitni"]):
        return f"рҹ“… Aaj *{n.strftime('%A, %d %B %Y')}* hai"
    if any(w in msg for w in ["hello", "hi", "assalam", "namaste", "hey"]):
        return "рҹ•Ң *Assalamualaikum!* Main aapka AI dost hoon. Batao kaisi help chahiye?"
    if any(w in msg for w in ["kaise ho", "how are", "kya haal"]):
        return "рҹҳҠ *Main badiya hoon!* Aap sunao, kya ho raha hai aaj kal?"
    if any(w in msg for w in ["thank", "shukriya", "thanks"]):
        return "рҹӨ— *Welcome!* Aur koi help chahiye toh batana!"
    if any(w in msg for w in ["bye", "allah hafiz", "good night", "shabba"]):
        return "рҹҢҷ *Allah Hafiz!* Apna khayal rakhna. Fir milenge!"
    if any(w in msg for w in ["help", "madad", "command", "kya kar"]):
        return ("рҹ“Ӣ *COMMANDS*\n"
                "`/task` `/done` вҖ” Tasks\n"
                "`/habit` `/hdone` вҖ” Habits\n"
                "`/remind` вҖ” Reminders\n"
                "`/kharcha` вҖ” Expenses\n"
                "`/diary` вҖ” Diary\n"
                "`/remember` `/recall` вҖ” Memory\n"
                "`/news` вҖ” News\n"
                "`/briefing` вҖ” Daily summary\n"
                "`/help` вҖ” Full list")
    replies = [
        "рҹҷҸ Abhi AI busy hai. Thodi der baad try karo ya `/help` use karo!",
        "рҹҳ… Model unavailable. Commands try karo: `/task` `/remind` `/help`",
        "рҹӨ– Response nahi aa pa raha. Kuch commands use karo ya wait karo!",
    ]
    return random.choice(replies)

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# AI RESPONSE CACHE (5min TTL)
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
_ai_cache = {}
_AI_CACHE_TTL = 300

def _get_cached_reply(key):
    if key in _ai_cache:
        reply, ts = _ai_cache[key]
        if time.time() - ts < _AI_CACHE_TTL:
            log.info("вҡЎ Cache hit!")
            return reply
        del _ai_cache[key]
    return None

def _set_cache(key, reply):
    if len(_ai_cache) > 50:
        oldest = min(_ai_cache, key=lambda k: _ai_cache[k][1])
        del _ai_cache[oldest]
    _ai_cache[key] = (reply, time.time())

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# SMART LOCAL ROUTER
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
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
        return f"вҸ° Abhi *{n.strftime('%I:%M %p')}* baj rahe hain (IST)"
    if intent == "date":
        days_hi = {0:"Somwar",1:"Mangalwar",2:"Budh",3:"Guruwar",4:"Shukrawar",5:"Shaniwar",6:"Itwar"}
        months_en = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                     7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
        return f"рҹ“… Aaj *{days_hi[n.weekday()]}, {n.day} {months_en[n.month]} {n.year}* hai"
    if intent == "greet":
        options = ["рҹ•Ң *Assalamualaikum!* Kya haal hai?",
                   "рҹҳҠ *Salam!* Batao kya kaam hai?",
                   "рҹ‘Ӣ *Hello!* Main yahaan hoon вҖ” batao kya chahiye?"]
        return random.choice(options)
    if intent == "wellbeing":
        return "рҹҳҠ *Main bilkul theek hoon!* Aap sunao вҖ” kya ho raha hai?"
    if intent == "thanks":
        return "рҹӨ— *Welcome!* Aur kuch help chahiye toh batao!"
    if intent == "bye":
        return "рҹҢҷ *Allah Hafiz!* Apna khayal rakhna!"
    return None

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# MAIN AI PIPELINE
# Flow: Local вҶ’ Cache вҶ’ Gemini вҶ’ Groq вҶ’ Offline
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
def get_ai_reply(user_msg, chat_id=None, system_ctx=None):
    intent = _smart_local_router(user_msg)
    if intent:
        return _local_reply(intent)

    cache_key = user_msg[:80].lower().strip()
    cached = _get_cached_reply(cache_key)
    if cached:
        return cached

    if not system_ctx:
        system_ctx = build_system_prompt()
    prompt = f"{system_ctx}\n\nUser: {user_msg}\n\nReply in Hindi/Hinglish (2-4 lines, warm & friendly):"

    reply = call_gemini(prompt)
    if reply:
        _set_cache(cache_key, reply)
        return reply

    reply = call_groq_text(prompt)
    if reply:
        _set_cache(cache_key, reply)
        return reply

    return smart_fallback(user_msg)

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# DATA STORES (simplified, no logs, no notes store, memory only)
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
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
        facts = "\n".join(f"вҖў {x['f']}" for x in self.get_all_facts()[-15:]) or "Kuch nahi"
        prefs = "\n".join(f"вҖў {k}: {v}" for k, v in self.get_all_prefs().items()) or "Kuch nahi"
        dates = "\n".join(f"вҖў {k}: {v}" for k, v in self.get_all_dates().items()) or "Kuch nahi"
        imp = "\n".join(f"вӯҗ {n['note']}" for n in self.get_all_important()[-5:]) or "Kuch nahi"
        return f"FACTS:\n{facts}\n\nPREFERENCES:\n{prefs}\n\nDATES:\n{dates}\n\nIMPORTANT:\n{imp}"

class TaskStore:
    def __init__(self):
        self.store = Store("tasks", {"list": [], "counter": 0})
    def _save(self):
        self.store.save()
    def add(self, title, priority="medium", due=None):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        t = {"id": self.store.data["counter"], "title": title,
             "priority": priority, "due": due or today_str(),
             "done": False, "done_at": None, "created": datetime.now().isoformat()}
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
        before = len(self.store.data["list"])
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
            result[d] = {"done": len(self.done_on(d)), "created": len([t for t in self.all_tasks() if t.get("created", "")[:10] == d])}
        return result
    def clear_done(self):
        before = len(self.store.data["list"])
        self.store.data["list"] = [t for t in self.store.data["list"] if not t["done"]]
        self._save()
        return before - len(self.store.data["list"])

class HabitStore:
    def __init__(self):
        self.store = Store("habits", {"list": [], "logs": {}, "counter": 0})
    def add(self, name, emoji="вң…"):
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
        r = {"id": self.store.data["counter"], "chat_id": chat_id,
             "text": text, "time": time_str, "repeat": repeat,
             "active": True, "fired_today": False,
             "date": today_str(), "created": datetime.now().isoformat()}
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
    def add(self, text, mood="рҹ“қ"):
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
    def get(self, category="India", n=5):
        try:
            url = f"https://news.google.com/rss/search?q={category}+India&hl=en-IN&gl=IN&ceid=IN:en"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                tree = ET.parse(resp)
                items = tree.findall(".//item")[:n]
                news = [{"title": i.findtext("title", ""), "link": i.findtext("link", "")} for i in items]
            return news
        except Exception as e:
            log.warning(f"News fetch failed: {e}")
            return []

class ChatHistStore:
    def __init__(self):
        self.store = Store("chat_history", {"messages": []})
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

# Initialize stores
memory = MemoryStore()
tasks = TaskStore()
habits = HabitStore()
expenses = ExpenseStore()
reminders = ReminderStore()
diary = DiaryStore()
goals = GoalStore()
water = WaterStore()
bills = BillStore()
calendar = CalendarStore()
news_store = NewsStore()
chat_hist = ChatHistStore()

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# GOOGLE SHEETS INTEGRATION (Full header mapping)
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
class GoogleSheetsDB:
    def __init__(self):
        self.sheet = None
        self._connect()

    def _connect(self):
        if not HAS_GSHEETS or not GOOGLE_CREDS_JSON:
            log.warning("вҡ пёҸ Google Sheets not configured")
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
            log.info("вң… Google Sheets connected!")
            self._ensure_worksheets()
            self.restore_from_sheets()
        except Exception as e:
            log.error(f"Sheets connect failed: {e}")

    def _ensure_worksheets(self):
        if not self.sheet:
            return
        needed = ["Tasks", "Reminders", "Memory", "Goals", "Calendar", "Bills",
                  "Expenses", "Habits", "Water", "Daily_Logs", "Diary", "Miscellaneous"]
        existing = [ws.title for ws in self.sheet.worksheets()]
        for name in needed:
            if name not in existing:
                self.sheet.add_worksheet(title=name, rows=1000, cols=20)
                if name == "Tasks":
                    self.sheet.worksheet(name).append_row(["ID","Title","Priority","Status","Created Date","Completed Date","Due Date","Tags"])
                elif name == "Reminders":
                    self.sheet.worksheet(name).append_row(["ID","Time","Text","Repeat","Status","Created Date","Chat ID","Last Fired","Remarks"])
                elif name == "Memory":
                    self.sheet.worksheet(name).append_row(["Date","Category","Content","Tags","Priority"])
                elif name == "Goals":
                    self.sheet.worksheet(name).append_row(["ID","Title","Progress %","Status","Deadline","Created Date","Milestones"])
                elif name == "Calendar":
                    self.sheet.worksheet(name).append_row(["Date","Time","Event Title","Location","Reminder Set","Participants","Notes"])
                elif name == "Bills":
                    self.sheet.worksheet(name).append_row(["ID","Name","Amount (РІР‚№)","Due Date","Auto-pay","Paid Status","Payment Method","Notes"])
                elif name == "Expenses":
                    self.sheet.worksheet(name).append_row(["Date","Amount (Rs)","Description","Category","Time","Location"])
                elif name == "Habits":
                    self.sheet.worksheet(name).append_row(["ID","Habit Name","Emoji","Streak","Best Streak","Created Date","Target (per day)"])
                elif name == "Water":
                    self.sheet.worksheet(name).append_row(["Date","Total ML","Goal ML","Percentage","Glasses (250ml)","Hourly Logs"])
                elif name == "Daily_Logs":
                    self.sheet.worksheet(name).append_row(["Date","Tasks Done","Tasks Pending","Expenses (Rs)","Reminders Active","Habits Done","Water ML","Mood","Notes"])
                elif name == "Diary":
                    self.sheet.worksheet(name).append_row(["Date","Time","Content","Mood"])
                elif name == "Miscellaneous":
                    self.sheet.worksheet(name).append_row(["Timestamp","Date","Role","Message"])

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
                     t.get("created", "")[:10], t.get("done_at", "")[:10],
                     t.get("due", ""), ""] for t in task_list]
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
                     r.get("date", ""), r.get("chat_id", ""), "", ""] for r in rem_list]
            self._upsert_rows(ws, rows)
            return True
        except Exception as e:
            log.error(f"Reminders save error: {e}")
            return False

    def save_memory(self, facts):
        if not self.sheet or not facts:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Memory")
            existing = ws.get_all_values()
            existing_facts = set(str(row[2])[:50] for row in existing[1:] if len(row) > 2 and row[2])
            new_rows = []
            for f in facts:
                if str(f["f"])[:50] not in existing_facts:
                    new_rows.append([f["d"], "General", f["f"], "", ""])
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
                     g.get("deadline",""), g.get("created",""), ""] for g in goal_list]
            self._upsert_rows(ws, rows)
            return True
        except Exception as e:
            log.error(f"Goals save error: {e}")
            return False

    def save_calendar(self, events):
        if not self.sheet or not events:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Calendar")
            rows = [[e["date"], e.get("time",""), e["title"], "", "", "", ""] for e in events]
            for row in rows:
                ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            log.error(f"Calendar save error: {e}")
            return False

    def save_bills(self, bill_list):
        if not self.sheet or not bill_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Bills")
            rows = [[b["id"], b["name"], b["amount"], b["due_day"],
                     "", "Paid" if self.is_paid_this_month(b["id"]) else "Pending", "", ""] for b in bill_list]
            self._upsert_rows(ws, rows)
            return True
        except Exception as e:
            log.error(f"Bills save error: {e}")
            return False

    def save_expenses(self, exp_list):
        if not self.sheet or not exp_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Expenses")
            existing = ws.get_all_values()
            existing_keys = set()
            for row in existing[1:]:
                if len(row) >= 4:
                    existing_keys.add(f"{row[0]}|{row[3]}")
            new_rows = []
            for e in exp_list:
                key = f"{e['date']}|{e['desc']}"
                if key not in existing_keys:
                    new_rows.append([e["date"], e["amount"], e["desc"], e.get("category","general"), e.get("time",""), ""])
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
            rows = [[h["id"], h["name"], h.get("emoji","вң…"),
                     h.get("streak",0), h.get("best_streak",0), h.get("created",""), ""] for h in hab_list]
            self._upsert_rows(ws, rows)
            return True
        except Exception as e:
            log.error(f"Habits save error: {e}")
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
                glasses = total_ml // 250
                rows.append([d, total_ml, goal, pct, glasses, ""])
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
                if len(row) >= 3:
                    existing_keys.add(f"{row[0]}|{row[2]}")
            new_rows = []
            for entry_date in sorted(all_entries_dict.keys()):
                for entry in all_entries_dict[entry_date]:
                    key = f"{entry_date}|{entry.get('text','')[:50]}"
                    if key not in existing_keys:
                        new_rows.append([entry_date, entry.get("time",""), entry.get("text",""), entry.get("mood","рҹ“қ")])
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
            tasks_done = len(tasks.done_on(today))
            tasks_pending = len(tasks.today_pending())
            expenses_total = expenses.today_total()
            water_total = water.today_total()
            habits_done = len(habits.today_status()[0])
            new_row = [today, tasks_done, tasks_pending, expenses_total, len(reminders.all_active()), habits_done, water_total, "", ""]
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
            return "вқҢ Google Sheets not connected!"
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
            return f"вҡ пёҸ Synced {success_count}/{len(ops)} | Failed: {', '.join(errors)}"
        return f"вң… Synced {success_count}/{len(ops)} sheets!"

    def restore_from_sheets(self):
        if not self.sheet:
            return False
        log.info("рҹ”„ Restoring from Google Sheets...")
        try:
            ws = self.sheet.worksheet("Tasks")
            all_vals = ws.get_all_values()
            if len(all_vals) > 1:
                task_list = []
                for row in all_vals[1:]:
                    if len(row) < 2:
                        continue
                    try:
                        tid = int(float(row[0])) if row[0] else 0
                    except:
                        tid = 0
                    task_list.append({
                        "id": tid,
                        "title": row[1] if len(row)>1 else "",
                        "priority": row[2] if len(row)>2 else "medium",
                        "done": (row[3] if len(row)>3 else "").lower() == "done",
                        "created": row[4] if len(row)>4 else today_str(),
                        "done_at": row[5] if len(row)>5 else "",
                        "due": row[6] if len(row)>6 else today_str(),
                    })
                if task_list:
                    max_id = max((t["id"] for t in task_list), default=0)
                    db.save("tasks", {"list": task_list, "counter": max_id})
        except Exception as e:
            log.warning(f"Tasks restore: {e}")

        try:
            ws = self.sheet.worksheet("Reminders")
            all_vals = ws.get_all_values()
            if len(all_vals) > 1:
                rem_list = []
                for row in all_vals[1:]:
                    if len(row) < 3:
                        continue
                    try:
                        rid = int(float(row[0])) if row[0] else 0
                    except:
                        rid = 0
                    rem_list.append({
                        "id": rid,
                        "time": row[1] if len(row)>1 else "",
                        "text": row[2] if len(row)>2 else "",
                        "repeat": row[3] if len(row)>3 else "once",
                        "active": (row[4] if len(row)>4 else "").lower() != "inactive",
                        "fired_today": False,
                        "date": row[5] if len(row)>5 else today_str(),
                        "chat_id": int(ADMIN_CHAT_ID) if ADMIN_CHAT_ID else 0,
                    })
                if rem_list:
                    max_id = max((r["id"] for r in rem_list), default=0)
                    db.save("reminders", {"list": rem_list, "counter": max_id})
        except Exception as e:
            log.warning(f"Reminders restore: {e}")

        try:
            ws = self.sheet.worksheet("Expenses")
            all_vals = ws.get_all_values()
            if len(all_vals) > 1:
                exp_list = []
                for row in all_vals[1:]:
                    if len(row) < 2:
                        continue
                    try:
                        amt = float(row[1]) if row[1] else 0
                        if amt <= 0:
                            continue
                    except:
                        continue
                    exp_list.append({
                        "date": row[0] if row[0] else today_str(),
                        "amount": amt,
                        "desc": row[2] if len(row)>2 else "",
                        "category": row[3] if len(row)>3 else "general",
                        "time": row[4] if len(row)>4 else "",
                    })
                if exp_list:
                    db.save("expenses", {"list": exp_list, "budget": None})
        except Exception as e:
            log.warning(f"Expenses restore: {e}")

        try:
            ws = self.sheet.worksheet("Habits")
            all_vals = ws.get_all_values()
            if len(all_vals) > 1:
                hab_list = []
                for row in all_vals[1:]:
                    if len(row) < 2:
                        continue
                    try:
                        hid = int(float(row[0])) if row[0] else 0
                    except:
                        hid = 0
                    hab_list.append({
                        "id": hid,
                        "name": row[1] if len(row)>1 else "",
                        "emoji": row[2] if len(row)>2 else "вң…",
                        "streak": int(float(row[3])) if len(row)>3 and row[3] else 0,
                        "best_streak": int(float(row[4])) if len(row)>4 and row[4] else 0,
                        "created": row[5] if len(row)>5 else today_str(),
                    })
                if hab_list:
                    max_id = max((h["id"] for h in hab_list), default=0)
                    db.save("habits", {"list": hab_list, "logs": {}, "counter": max_id})
        except Exception as e:
            log.warning(f"Habits restore: {e}")

        return True

google_sheets = GoogleSheetsDB()

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# SYSTEM PROMPT BUILDER
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
def build_system_prompt():
    now_label = time_label()
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

    tasks_s = "\n".join(f"  {'рҹ”ҙ' if t['priority']=='high' else 'рҹҹЎ' if t['priority']=='medium' else 'рҹҹў'} {t['title']}" for t in tp[:5]) or "  Koi nahi"
    yd_s = "\n".join(f"  вң“ {t['title']}" for t in yd[:3]) or "  Koi nahi"
    h_done = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    h_pend = ", ".join(f"{h['name']}" for h in hp) or "Sab ho gaye!"
    goals_s = "\n".join(f"  рҹҺҜ {g['title']} ({g['progress']}%)" for g in ag[:4]) or "  Koi nahi"
    diary_s = "\n".join(f"  {e['time']} {e['text']}" for e in td_d[-2:]) or "  Kuch nahi"
    budget_s = f"Budget baaki: вӮ№{bl:.0f}" if bl is not None else ""
    water_pct = int(water_today / water_goal * 100) if water_goal else 0
    bills_s = "\n".join(f"  вҡ пёҸ {b['name']} вӮ№{b['amount']:.0f}" for b in due_b) or "  Koi nahi"
    cal_s = "\n".join(f"  рҹ“… {e['time'] or ''} {e['title']}" for e in cal_today) or "  Koi nahi"

    return f"""Tu mera Personal AI Assistant hai вҖ” naam 'Dost'. Hamesha Hindi/Hinglish mein baat kar. Bilkul close dost jaisa вҖ” warm, real, helpful.

вҡ пёҸ CRITICAL REAL TIME: {now_label}
вҖў Aaj ki date: {today_str()}
вҖў Jab koi time puche вҖ” YEHI BATANA. Kabhi guess mat karna.

рҹ“Ӣ AAJ KE TASKS ({len(tp)}):
{tasks_s}

вң… KAL KYA KIYA ({len(yd)}):
{yd_s}

рҹ’Ә HABITS: Done: {h_done} | Baaki: {h_pend}

рҹ“– DIARY (aaj):
{diary_s}

рҹ’° KHARCHA: Aaj вӮ№{exp_t} | Mahina вӮ№{exp_m} {budget_s}

рҹҺҜ GOALS ({len(ag)}):
{goals_s}

рҹ’§ PAANI: {water_today}ml/{water_goal}ml ({water_pct}%)

рҹ“… AAJ KE EVENTS:
{cal_s}

рҹ’і BILLS DUE:
{bills_s}

рҹ§  YAADDASHT:
{memory.context()}

RULES:
- Dost ki tarah baat kar вҖ” "As an AI" kabhi mat bol
- Hindi/Hinglish mein jawab de, SHORT (2-4 lines)
- TIME PUCHNE PE EXACT TIME BATANA jo upar likha hai
- Jo yaad hai naturally use kar
"""

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# SMART ACTION SYSTEM
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
ACTION_SYSTEM_PROMPT = """You are a JSON router. Parse user message and return ONLY raw JSON (no markdown, no backticks).

Current EXACT time: {now}
24hr time: {current_time}
Today: {today}
2 min from now: {two_min}

JSON format: {{"action":"ACTION","params":{{...}},"reply":"confirm msg"}}

ACTIONS:
REMIND вҖ” {{"time":"HH:MM","text":"...","repeat":"once"}}
ADD_TASK вҖ” {{"title":"...","priority":"high/medium/low"}}
ADD_EXPENSE вҖ” {{"amount":number,"desc":"...","category":"..."}}
ADD_DIARY вҖ” {{"text":"...","mood":"рҹҳҠ"}}
ADD_MEMORY вҖ” {{"fact":"..."}}
ADD_HABIT вҖ” {{"name":"...","emoji":"рҹ’Ә"}}
COMPLETE_TASK вҖ” {{"title_hint":"..."}}
SHOW_TASKS вҖ” {{}}
SHOW_ALL_TASKS вҖ” {{}}
SHOW_COMPLETED_TASKS вҖ” {{}}
SHOW_REMINDERS вҖ” {{}}
CHAT вҖ” {{}} (default)
"""

def _regex_fallback(user_msg):
    lower = user_msg.lower()
    now = now_ist()
    if any(w in lower for w in ["alarm","reminder","yaad dila","remind","notify","minute baad","min baad","ghante baad","baje"]):
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
            return {"action": "REMIND", "params": {"time": time_str, "text": text or "вҸ° Reminder!", "repeat": "once"}, "reply": ""}
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
                log.info(f"вң… Action: {parsed.get('action')} via {model}")
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
        text = params.get("text", "вҸ° Reminder!")
        repeat = params.get("repeat", "once")
        if not time_str or not _re.match(r'^\d{2}:\d{2}$', time_str):
            return f"вҸ° Time format galat! Abhi *{now.strftime('%H:%M')}* hue hain. HH:MM use karo."
        r = reminders.add(chat_id, text, time_str, repeat)
        rl = {"once": "Ek baar", "daily": "Roz рҹ”Ғ", "weekly": "Har hafte рҹ“…"}.get(repeat, repeat)
        return f"вң… Reminder set! вҸ° *{time_str}* вҖ” {text}\n{rl}\nрҹҶ” `#{r['id']}` | `/delremind {r['id']}`"

    elif action == "ADD_TASK":
        title = params.get("title", user_msg[:80])
        priority = params.get("priority", "medium")
        t = tasks.add(title, priority)
        icons = {"high": "рҹ”ҙ", "medium": "рҹҹЎ", "low": "рҹҹў"}
        return f"вң… Task: {icons.get(priority,'рҹҹЎ')} *{t['title']}*\nрҹҶ” `#{t['id']}`"

    elif action == "ADD_EXPENSE":
        amount = float(params.get("amount", 0))
        desc = params.get("desc", "Kharcha")
        if amount <= 0:
            return "рҹ’° Amount batao?"
        expenses.add(amount, desc)
        return f"вң… вӮ№{amount:.0f} вҖ” {desc}\nрҹ“Ҡ Aaj: вӮ№{expenses.today_total():.0f}"

    elif action == "ADD_DIARY":
        diary.add(params.get("text", user_msg[:100]), params.get("mood", "рҹҳҠ"))
        return f"рҹ“– Diary saved! рҹ•җ {now_str()}"

    elif action == "ADD_MEMORY":
        memory.add_fact(params.get("fact", user_msg[:200]))
        return f"рҹ§  Yaad kar liya! вң…"

    elif action == "ADD_HABIT":
        h = habits.add(params.get("name", user_msg[:50]), params.get("emoji", "вң…"))
        return f"рҹ’Ә Habit: {h['emoji']} *{h['name']}*\n`/hdone {h['id']}`"

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
            return f"вң… *{matched['title']}* вҖ” done! рҹҺү"
        return "вқ“ Kaunsa task? ID ya naam batao."

    elif action == "SHOW_TASKS":
        pending = tasks.today_pending()
        if not pending:
            return "рҹҺү No pending tasks!"
        txt = f"рҹ“Ӣ *PENDING ({len(pending)})*\n\n"
        for t in pending[:8]:
            txt += f"{'рҹ”ҙ' if t['priority']=='high' else 'рҹҹЎ' if t['priority']=='medium' else 'рҹҹў'} *#{t['id']}* {t['title']}\n"
        return txt

    elif action == "SHOW_ALL_TASKS":
        all_t = tasks.all_tasks()
        if not all_t:
            return "рҹ“Ӣ No tasks!"
        p = tasks.pending()
        c = tasks.completed_tasks()
        txt = f"рҹ“Ӣ *ALL ({len(all_t)})*\nвҸі{len(p)} pending | вң…{len(c)} done\n\n"
        if p:
            txt += "вҸі " + ", ".join(f"#{t['id']} {t['title'][:20]}" for t in p[:5])
        if c:
            txt += "\nвң… " + ", ".join(f"#{t['id']} {t['title'][:20]}" for t in c[-5:])
        return txt

    elif action == "SHOW_COMPLETED_TASKS":
        c = tasks.completed_tasks()
        if not c:
            return "вң… No completed tasks yet!"
        return f"вң… *COMPLETED ({len(c)})*\n\n" + "".join(f"  вң“ #{t['id']} {t['title']}\n" for t in c[-10:])

    elif action == "SHOW_REMINDERS":
        active = reminders.all_active()
        if not active:
            return f"вҸ° No reminders!\n`/remind 30m Kaam` se set karo"
        txt = f"вҸ° *REMINDERS ({len(active)})*\n\n"
        for r in active:
            icon = "рҹ”Ғ" if r["repeat"] == "daily" else "рҹ“…" if r["repeat"] == "weekly" else "1пёҸвғЈ"
            txt += f"*#{r['id']}* {icon} `{r['time']}` вҖ” {r['text']}\n"
        return txt

    else:
        memory.add_fact(user_msg)
        chat_hist.add("user", user_msg)
        reply = get_ai_reply(user_msg, chat_id, build_system_prompt())
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

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# BRIEFING BUILDER
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
async def _build_briefing_text():
    n = now_ist()
    hour = n.hour
    greeting = "рҹҢ… Subah Bakhair" if hour < 12 else "рҹҢһ Dopahar Mubarak" if hour < 17 else "рҹҢҶ Shaam Bakhair" if hour < 20 else "рҹҢҷ Raat Bakhair"
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
    txt += f"вҸ° *{n.strftime('%I:%M %p')}* | рҹ“… *{n.strftime('%A, %d %b')}*\n"
    txt += "в”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғ\n\n"
    txt += f"рҹ“Ӣ *TASKS* вҖ” {len(tp)} pending"
    if done_today:
        txt += f" | вң… {len(done_today)} done today"
    txt += "\n"
    for t in tp[:4]:
        icon = "рҹ”ҙ" if t['priority'] == 'high' else "рҹҹЎ" if t['priority'] == 'medium' else "рҹҹў"
        txt += f"  {icon} {t['title']}\n"
    if len(tp) > 4:
        txt += f"  _...aur {len(tp)-4} aur_\n"
    txt += f"\nрҹ’Ә *HABITS* вҖ” {len(hd)}/{len(hd)+len(hp)} done\n"
    if hd:
        txt += "  вң… " + ", ".join(f"{h['emoji']}{h['name']}" for h in hd[:3]) + "\n"
    if hp:
        txt += "  вҸі " + ", ".join(h['name'] for h in hp[:3]) + "\n"
    txt += f"\nрҹ’° *KHARCHA* вҖ” Aaj вӮ№{exp_t:.0f} | Mahina вӮ№{exp_m:.0f}"
    if bl is not None:
        txt += f" | Budget left: вӮ№{bl:.0f}"
    txt += "\n"
    txt += f"\nрҹ’§ *PAANI* вҖ” {water_t}ml/{water_g}ml ({water_pct}%)\n"
    if cal_today:
        txt += "\nрҹ“… *AAJ KE EVENTS*\n"
        for e in cal_today[:3]:
            t_str = f" @ {e['time']}" if e.get('time') else ""
            txt += f"  вҖў {e['title']}{t_str}\n"
    if due_b:
        txt += "\nрҹ’і *BILLS DUE*\n"
        for b in due_b[:2]:
            txt += f"  вҡ пёҸ {b['name']} вҖ” вӮ№{b['amount']:.0f}\n"
    if ag:
        txt += f"\nрҹҺҜ *GOALS* вҖ” {len(ag)} active\n"
        for g in ag[:2]:
            bar = "в–Ҳ" * (g['progress'] // 10) + "в–‘" * (10 - g['progress'] // 10)
            txt += f"  `{bar}` {g['title']} {g['progress']}%\n"
    return txt

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# COMMAND HANDLERS (simplified, no keyboards)
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
async def cmd_start(update, ctx):
    n = now_ist()
    name = update.effective_user.first_name or "Dost"
    db_status = "вң… Google Sheets вҖ” Data permanent hai!" if google_sheets.sheet else "вҡ пёҸ Sheets not connected!"
    await update.message.reply_text(
        f"рҹ•Ң *Assalamualaikum {name}!*\n\nвҸ° {n.strftime('%I:%M %p')} IST | рҹ“… {n.strftime('%d %b %Y')}\n\n"
        f"рҹ’ҫ *{db_status}*\n\n"
        "рҹ“Ӣ Tasks | рҹ’Ә Habits | рҹ“– Diary\n"
        "рҹ’° Expenses | вҸ° Reminders | рҹ“° News\nрҹ’§ Water | рҹ’і Bills | рҹ“… Calendar\n"
        "рҹҶ• *v15: Groq AI + Smart Cache + Morning Briefing*\n\n"
        "_Seedha type karo ya /help_ рҹ‘Ү", parse_mode="Markdown")

async def cmd_help(update, ctx):
    await update.message.reply_text(
        "рҹ“Ӣ *COMMANDS*\n\n"
        "**рҹ“қ TASKS & HABITS**\n"
        "`/task` `/done` `/deltask` вҖ” Tasks\n"
        "`/habit` `/hdone` `/delhabit` вҖ” Habits\n\n"
        "**рҹ“– JOURNAL**\n"
        "`/diary` вҖ” Diary\n"
        "`/remember` `/recall` вҖ” Memory\n\n"
        "**рҹ’° FINANCE**\n"
        "`/kharcha` `/budget` вҖ” Expenses\n"
        "`/bill` `/bills` `/billpaid` `/delbill` вҖ” Bills\n\n"
        "**вҸ° REMINDERS & CALENDAR**\n"
        "`/remind` `/reminders` `/delremind` вҖ” Reminders\n"
        "`/cal` `/calendar` `/delcal` вҖ” Calendar\n\n"
        "**рҹ’Ә HEALTH**\n"
        "`/water` `/waterstatus` `/watergoal` вҖ” Water\n\n"
        "**рҹ“Ҡ REPORTS**\n"
        "`/report YYYY-MM-DD` `/weekly` `/briefing` `/yesterday`\n\n"
        "**рҹҺҜ GOALS**\n"
        "`/goal` `/gprogress` вҖ” Goals\n\n"
        "**рҹ”§ UTILITIES**\n"
        "`/clear` `/nuke` `/backup` `/memory`\n\n"
        "_Seedha type karo вҖ” AI jawab dega!_", parse_mode="Markdown")

async def cmd_task(update, ctx):
    if not ctx.args:
        await update.message.reply_text("рҹ“Ӣ `/task Kaam [high/low]`")
        return
    args = " ".join(ctx.args)
    priority = "medium"
    if args.endswith(" high"):
        priority = "high"; args = args[:-5].strip()
    elif args.endswith(" low"):
        priority = "low"; args = args[:-4].strip()
    t = tasks.add(args, priority)
    e = "рҹ”ҙ" if priority == "high" else "рҹҹЎ" if priority == "medium" else "рҹҹў"
    await update.message.reply_text(f"вң… {e} *{t['title']}*\nрҹҶ” `#{t['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_done(update, ctx):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            msg = "рҹ“Ӣ *Pending tasks:*\n"
            for t in pending[:10]:
                msg += f"`/done {t['id']}` вҶ’ {t['title']}\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("рҹҺү No pending tasks!")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t:
            await update.message.reply_text(f"рҹҺү *Done!* {t['title']}", parse_mode="Markdown")
        else:
            await update.message.reply_text("вқҢ Task not found or already done!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("вқҢ Invalid ID!")

async def cmd_deltask(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/deltask <id>`"); return
    try:
        if tasks.delete(int(ctx.args[0])):
            await update.message.reply_text("рҹ—‘ Deleted!")
        else:
            await update.message.reply_text("вқҢ Not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("вқҢ Invalid ID")

async def cmd_habit(update, ctx):
    if not ctx.args:
        all_h = habits.all()
        if not all_h:
            await update.message.reply_text("рҹ’Ә No habits! `/habit Naam`")
            return
        hd, hp = habits.today_status()
        txt = "рҹ’Ә *HABITS*\n\n"
        txt += "вң… *Done:*\n" + "\n".join(f"  {h['emoji']} {h['name']} рҹ”Ҙ{h.get('streak',0)}d" for h in hd) + "\n\n" if hd else ""
        txt += "вҸі *Pending:*\n" + "\n".join(f"  {h['emoji']} {h['name']} вҖ” `/hdone {h['id']}`" for h in hp) if hp else "вң… Sab done!"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return
    emoji = "вң…"
    name = " ".join(ctx.args)
    for e in ["рҹ’Ә","рҹ§ҳ","рҹ“ҡ","рҹҸғ","рҹҘ—","рҹ’§","рҹҳҙ","рҹҺҜ","вңҚпёҸ","рҹ”Ҙ"]:
        if e in name:
            emoji = e
            name = name.replace(e, "").strip()
            break
    h = habits.add(name, emoji)
    await update.message.reply_text(f"рҹ’Ә Habit added: {h['emoji']} *{h['name']}*\n`/hdone {h['id']}` se mark karo!", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_hdone(update, ctx):
    if not ctx.args:
        _, pending = habits.today_status()
        if not pending:
            await update.message.reply_text("рҹҺү Sab habits done!")
            return
        txt = "рҹ’Ә *Pending habits:*\n"
        for h in pending:
            txt += f"`/hdone {h['id']}` вҖ” {h['emoji']} {h['name']}\n"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return
    try:
        hid = int(ctx.args[0])
        ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"] == hid), None)
        if ok and h:
            await update.message.reply_text(f"рҹ’Ә {h['emoji']} *{h['name']}* вҖ” Done! рҹ”Ҙ Streak: {streak} days", parse_mode="Markdown")
        else:
            await update.message.reply_text("вң… Already done today!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("вқҢ Invalid ID")

async def cmd_delhabit(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delhabit <id>`"); return
    try:
        if habits.delete(int(ctx.args[0])):
            await update.message.reply_text("рҹ—‘ Habit deleted!")
        else:
            await update.message.reply_text("вқҢ Not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("вқҢ Invalid ID")

async def cmd_kharcha(update, ctx):
    if not ctx.args:
        today_exp = expenses.get_by_date(today_str())
        total = expenses.today_total()
        bl = expenses.budget_left()
        txt = f"рҹ’° *AAJ KA KHARCHA* вҖ” вӮ№{total:.0f}\n\n"
        for e in today_exp[-8:]:
            txt += f"  вҖў вӮ№{e['amount']:.0f} вҖ” {e['desc']}\n"
        if bl is not None:
            txt += f"\nрҹ’і Budget left: вӮ№{bl:.0f}"
        await update.message.reply_text(txt or "рҹ’° Aaj koi kharcha nahi!", parse_mode="Markdown")
        return
    try:
        args = " ".join(ctx.args)
        parts = args.split(maxsplit=1)
        amount = float(parts[0])
        desc = parts[1] if len(parts) > 1 else "Kharcha"
        expenses.add(amount, desc)
        await update.message.reply_text(f"вң… вӮ№{amount:.0f} вҖ” {desc}\nрҹ“Ҡ Aaj total: вӮ№{expenses.today_total():.0f}", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("вқҢ Format: `/kharcha 150 Chai`")

async def cmd_budget(update, ctx):
    if not ctx.args:
        bl = expenses.budget_left()
        bud = expenses.store.data.get("budget")
        if bud:
            await update.message.reply_text(f"рҹ’і Budget: вӮ№{bud:.0f}/month\nSpent: вӮ№{expenses.month_total():.0f}\nLeft: вӮ№{bl:.0f}")
        else:
            await update.message.reply_text("рҹ’і `/budget 5000` se set karo")
        return
    try:
        expenses.set_budget(float(ctx.args[0]))
        await update.message.reply_text(f"вң… Budget set: вӮ№{float(ctx.args[0]):.0f}/month")
    except:
        await update.message.reply_text("вқҢ Invalid amount")

async def cmd_goal(update, ctx):
    if not ctx.args:
        ag = goals.active()
        cg = goals.completed()
        if not ag and not cg:
            await update.message.reply_text("рҹҺҜ No goals! `/goal Mera goal`")
            return
        txt = "рҹҺҜ *GOALS*\n\n"
        for g in ag[:5]:
            bar = "в–Ҳ" * (g['progress'] // 10) + "в–‘" * (10 - g['progress'] // 10)
            txt += f"*#{g['id']}* `{bar}` {g['title']} вҖ” {g['progress']}%\n"
        if cg:
            txt += "\nрҹҸҶ *Completed:* " + ", ".join(g['title'][:20] for g in cg[-3:])
        await update.message.reply_text(txt, parse_mode="Markdown")
        return
    g = goals.add(" ".join(ctx.args))
    await update.message.reply_text(f"рҹҺҜ Goal set: *{g['title']}*\n`/gprogress {g['id']} 50` se update karo", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_gprogress(update, ctx):
    if len(ctx.args) < 2:
        await update.message.reply_text("`/gprogress <id> <0-100>`"); return
    try:
        g = goals.update_progress(int(ctx.args[0]), int(ctx.args[1]))
        if g:
            bar = "в–Ҳ" * (g['progress'] // 10) + "в–‘" * (10 - g['progress'] // 10)
            done_msg = " рҹҸҶ *COMPLETED!*" if g['done'] else ""
            await update.message.reply_text(f"вң… *{g['title']}*\n`{bar}` {g['progress']}%{done_msg}", parse_mode="Markdown")
            await auto_backup_to_sheets()
        else:
            await update.message.reply_text("вқҢ Goal not found")
    except:
        await update.message.reply_text("вқҢ Invalid input")

async def cmd_remember(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/remember Kuch important`"); return
    fact = " ".join(ctx.args)
    memory.add_fact(fact)
    await update.message.reply_text(f"рҹ§  Yaad kar liya! вң…\n_{fact[:80]}_", parse_mode="Markdown")

async def cmd_recall(update, ctx):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("рҹ§  Koi yaad nahi abhi tak!")
        return
    query = " ".join(ctx.args).lower() if ctx.args else ""
    if query:
        filtered = [f for f in facts if query in f["f"].lower()]
        facts = filtered if filtered else facts
    txt = "рҹ§  *MEMORY*\n\n" + "\n".join(f"рҹ“Ң {f['f']}" for f in facts[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_briefing(update, ctx):
    txt = await _build_briefing_text()
    await update.message.reply_text(txt, parse_mode="Markdown")

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
    txt = f"рҹ“Ҳ *WEEKLY SUMMARY*\n_{n.strftime('%d %b')} week_\n\n"
    txt += f"рҹ“Ӣ Tasks: вң… {total_done} done | вһ• {total_created} created\n"
    txt += f"рҹ’Ә Habits: {habit_completions} completions\n"
    txt += f"рҹ’° Expenses: вӮ№{week_exp:.0f} this week\n\n"
    txt += "*Daily:*\n"
    for d_key in sorted(task_week.keys(), reverse=True):
        v = task_week[d_key]
        exp_day = sum(e["amount"] for e in expenses.get_by_date(d_key))
        txt += f"рҹ“… {d_key}: вң…{v['done']} done | вӮ№{exp_day:.0f}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_report(update, ctx):
    if not ctx.args:
        await update.message.reply_text("рҹ“… `/report YYYY-MM-DD`\nExample: `/report 2026-05-01`")
        return
    target = ctx.args[0]
    try:
        date.fromisoformat(target)
    except:
        await update.message.reply_text("вқҢ Invalid date! Use YYYY-MM-DD")
        return
    td = tasks.get_tasks_by_date(target)
    done = [t for t in td if t["done"]]
    pending = [t for t in td if not t["done"]]
    exp_day = expenses.get_by_date(target)
    diary_day = diary.get(target)
    habits_logs = habits.get_logs_by_date(target)
    habits_done = [h for h in habits.all() if h["id"] in habits_logs]
    water_day = sum(e["ml"] for e in water.store.data.get("entries", {}).get(target, []))
    txt = f"рҹ“Ҡ *REPORT: {target}*\nв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғ\n\n"
    txt += f"вң… Tasks done: {len(done)}\n"
    for t in done[:5]:
        txt += f"  вҖў {t['title']}\n"
    if pending:
        txt += f"вҸі Pending: {len(pending)}\n"
    txt += f"\nрҹ’Ә Habits: {len(habits_done)}/{len(habits.all())}\n"
    if habits_done:
        txt += "  " + ", ".join(f"{h['emoji']}{h['name']}" for h in habits_done) + "\n"
    txt += f"\nрҹ’° Kharcha: вӮ№{sum(e['amount'] for e in exp_day):.0f}\n"
    for e in exp_day[:4]:
        txt += f"  вҖў вӮ№{e['amount']:.0f} вҖ” {e['desc']}\n"
    txt += f"\nрҹ’§ Water: {water_day}ml\n"
    if diary_day:
        txt += f"\nрҹ“– Diary ({len(diary_day)} entries):\n"
        for en in diary_day[:2]:
            txt += f"  {en['time']} вҖ” {en['text'][:60]}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_news(update, ctx):
    items = news_store.get("India", 5)
    if not items:
        await update.message.reply_text("рҹ“° News unavailable.")
        return
    txt = "рҹ“° *TOP NEWS*\n\n" + "\n".join(f"вҖў {item['title']}" for item in items)
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_clear(update, ctx):
    count = chat_hist.clear()
    await update.message.reply_text(f"рҹ§№ Cleared {count} messages! Data safe hai вң…")

async def cmd_nuke(update, ctx):
    await update.message.reply_text("рҹ’Ј Nuke command disabled. Use /clear for chat history.")

async def cmd_alltasks(update, ctx):
    all_t = tasks.all_tasks()
    if not all_t:
        await update.message.reply_text("рҹ“Ӣ No tasks!")
        return
    p = tasks.pending(); c = tasks.completed_tasks()
    txt = f"рҹ“Ӣ *ALL TASKS*\nTotal: {len(all_t)} | вҸі {len(p)} | вң… {len(c)}\n\n"
    if p:
        txt += "вҸі *Pending:*\n" + "\n".join(f"  #{t['id']} {t['title']}" for t in p[:10])
    if c:
        txt += "\n\nвң… *Recent:*\n" + "\n".join(f"  #{t['id']} {t['title']}" for t in c[-5:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed(update, ctx):
    c = tasks.completed_tasks()
    if not c:
        await update.message.reply_text("вң… No completed tasks yet!")
        return
    txt = f"вң… *COMPLETED ({len(c)})*\n\n" + "\n".join(f"  вң“ #{t['id']} {t['title']} вҖ” {t.get('done_at','')[:10]}" for t in c[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_yesterday(update, ctx):
    yd = yesterday_str()
    td = tasks.done_on(yd); exp = expenses.get_by_date(yd)
    diary_yd = diary.get(yd); habits_logs = habits.get_logs_by_date(yd)
    habits_done = [h for h in habits.all() if h["id"] in habits_logs]
    txt = f"рҹ“… *YESTERDAY ({yd})*\nв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғв”Ғ\n\n"
    txt += f"вң… Tasks: {len(td)}\n"
    for t in td[:4]:
        txt += f"  вҖў {t['title']}\n"
    txt += f"\nрҹ’Ә Habits: {len(habits_done)}/{len(habits.all())}\n"
    txt += f"\nрҹ’° Kharcha: вӮ№{sum(e['amount'] for e in exp):.0f}\n"
    if diary_yd:
        txt += f"\nрҹ“– Diary: {diary_yd[0]['text'][:60]}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_memory(update, ctx):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("рҹ§  No memories yet!")
        return
    txt = "рҹ§  *MEMORY*\n\n" + "\n".join(f"рҹ“Ң {f['f']}" for f in facts[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_dbstatus(update, ctx):
    lines = []
    if google_sheets.sheet:
        lines.append("вң… *Google Sheets: CONNECTED!*")
    else:
        lines.append("вқҢ *Google Sheets: NOT CONNECTED*")
    lines.append(f"\nрҹ“Ҡ *Data:*")
    lines.append(f"  рҹ“Ӣ Tasks: {len(tasks.all_tasks())}")
    lines.append(f"  вҸ° Reminders: {len(reminders.all_active())}")
    lines.append(f"  рҹ’Ә Habits: {len(habits.all())}")
    lines.append(f"  рҹ’° Expenses: {len(expenses.store.data.get('list',[]))}")
    lines.append(f"  рҹ“– Diary: {sum(len(v) for v in diary.get_all_entries().values())}")
    lines.append(f"\nрҹӨ– *v15 AI:*")
    lines.append(f"  рҹ’Һ Gemini: {'вң…' if GEMINI_API_KEY else 'вқҢ'}")
    lines.append(f"  рҹҰҷ Groq (text): {'вң…' if GROQ_API_KEY else 'вқҢ'}")
    lines.append(f"  рҹ’ҫ Cache entries: {len(_ai_cache)}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_backup(update, ctx):
    await update.message.reply_text("рҹ“Ө Backing up...")
    result = google_sheets.full_sync()
    await update.message.reply_text(result)

async def cmd_remind(update, ctx):
    now = now_ist()
    if not ctx.args:
        await update.message.reply_text(
            f"вҸ° *REMINDER*\nAbhi: *{now.strftime('%I:%M %p')} IST*\n\n"
            "`/remind 2m Test` вҖ” 2 min baad\n"
            "`/remind 30m Chai` вҖ” 30 min baad\n"
            "`/remind 15:30 Doctor` вҖ” exact time\n"
            "`/remind 8:00 Uthna daily` вҖ” daily",
            parse_mode="Markdown"); return
    time_arg = ctx.args[0].lower()
    rest = ctx.args[1:]
    repeat = "once"
    if rest and rest[-1].lower() in ["daily", "weekly"]:
        repeat = rest[-1].lower(); rest = rest[:-1]
    text = " ".join(rest) if rest else "вҸ° Reminder!"
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
                await update.message.reply_text("вқҢ Invalid time!"); return
        else:
            await update.message.reply_text("вқҢ Format galat!"); return
    else:
        await update.message.reply_text("вқҢ Format galat! `/remind 2m Test`"); return
    r = reminders.add(update.effective_chat.id, text, remind_at, repeat)
    rl = {"once": "Once", "daily": "Daily рҹ”Ғ", "weekly": "Weekly рҹ“…"}.get(repeat, repeat)
    await update.message.reply_text(f"вң… *Reminder set!* вҸ° {remind_at} вҖ” {text}\n{rl}\nрҹҶ” `#{r['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_reminders_list(update, ctx):
    active = reminders.all_active()
    now = now_ist()
    if not active:
        await update.message.reply_text(f"вҸ° No reminders!\n`/remind 2m Test`", parse_mode="Markdown")
        return
    txt = f"вҸ° *REMINDERS ({len(active)})*\nAbhi: *{now.strftime('%I:%M %p')} IST*\n\n"
    for r in active:
        icon = "рҹ”Ғ" if r["repeat"] == "daily" else "рҹ“…" if r["repeat"] == "weekly" else "1пёҸвғЈ"
        txt += f"*#{r['id']}* {icon} `{r['time']}` вҖ” {r['text']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_delremind(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delremind <id>`"); return
    try:
        if reminders.delete(int(ctx.args[0])):
            await update.message.reply_text("рҹ—‘ Reminder deleted!")
        else:
            await update.message.reply_text("вқҢ Not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("вқҢ Invalid ID!")

async def cmd_water(update, ctx):
    if not ctx.args:
        total = water.today_total(); goal = water.goal()
        pct = min(100, int(total/goal*100)) if goal else 0
        await update.message.reply_text(
            f"рҹ’§ *WATER*\n\nToday: {total}ml/{goal}ml ({pct}%)\n\n`/water 250` to log more.",
            parse_mode="Markdown")
        return
    try:
        ml = int(ctx.args[0])
        water.add(ml)
        total = water.today_total(); goal = water.goal()
        await update.message.reply_text(f"рҹ’§ +{ml}ml! Total: {total}ml/{goal}ml")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("вқҢ `/water 250`")

async def cmd_water_status(update, ctx):
    total = water.today_total(); goal = water.goal()
    pct = min(100, int(total/goal*100)) if goal else 0
    bar = "в–Ҳ" * (pct // 10) + "в–‘" * (10 - pct // 10)
    await update.message.reply_text(f"рҹ’§ *Water Today*\n`{bar}` {pct}%\n{total}ml / {goal}ml", parse_mode="Markdown")

async def cmd_water_goal(update, ctx):
    if not ctx.args:
        await update.message.reply_text(f"рҹ’§ Goal: {water.goal()}ml\n`/watergoal 2500` se change karo"); return
    try:
        water.set_goal(int(ctx.args[0]))
        await update.message.reply_text(f"вң… Water goal: {int(ctx.args[0])}ml/day")
    except:
        await update.message.reply_text("вқҢ Invalid amount")

async def cmd_bill(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/bill BillName Amount DueDay`\nExample: `/bill Electricity 500 15`"); return
    try:
        args = ctx.args
        name = args[0]; amount = float(args[1]); due_day = int(args[2])
        b = bills.add(name, amount, due_day)
        await update.message.reply_text(f"вң… Bill: *{b['name']}* вҖ” вӮ№{b['amount']:.0f} (due {b['due_day']}th)", parse_mode="Markdown")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("вқҢ `/bill Name Amount DueDay`")

async def cmd_bills_list(update, ctx):
    all_b = bills.all_active()
    if not all_b:
        await update.message.reply_text("рҹ’і No bills! `/bill Name Amount Day`")
        return
    txt = "рҹ’і *BILLS*\n\n"
    for b in all_b:
        status = "вң… Paid" if bills.is_paid_this_month(b["id"]) else "вҸі Pending"
        txt += f"*#{b['id']}* {status} вҖ” *{b['name']}* вӮ№{b['amount']:.0f} (due {b['due_day']}th)\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_bill_paid(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/billpaid <id>`"); return
    try:
        bills.mark_paid(int(ctx.args[0]))
        await update.message.reply_text("вң… Bill marked as paid!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("вқҢ Invalid ID")

async def cmd_del_bill(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delbill <id>`"); return
    try:
        if bills.delete(int(ctx.args[0])):
            await update.message.reply_text("рҹ—‘ Bill deleted!")
        else:
            await update.message.reply_text("вқҢ Not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("вқҢ Invalid ID")

async def cmd_cal(update, ctx):
    if not ctx.args:
        upcoming = calendar.upcoming(30)
        if not upcoming:
            await update.message.reply_text("рҹ“… No events! `/cal 2026-05-10 Meeting`")
            return
        txt = "рҹ“… *UPCOMING*\n\n"
        for e in upcoming[:10]:
            flag = "рҹ”ҙ TODAY" if e["date"] == today_str() else "рҹ“Ҷ"
            t = f" @ {e['time']}" if e.get("time") else ""
            txt += f"{flag} {e['date']}{t} вҖ” {e['title']}\n"
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
        await update.message.reply_text("вқҢ `/cal YYYY-MM-DD Event`\n`/cal aaj Meeting`"); return
    t_match = _re.search(r'(\d{1,2}:\d{2})', title)
    if t_match:
        event_time = t_match.group(1); title = title.replace(event_time, "").strip()
    try:
        date.fromisoformat(date_str)
        e = calendar.add(title, date_str, event_time)
        await update.message.reply_text(f"рҹ“… Event: *{title}* вҖ” {date_str}" + (f" вҸ°{event_time}" if event_time else ""), parse_mode="Markdown")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("вқҢ Invalid date!")

async def cmd_cal_list(update, ctx):
    upcoming = calendar.upcoming(30)
    if not upcoming:
        await update.message.reply_text("рҹ“… No upcoming events!")
        return
    txt = "рҹ“… *UPCOMING EVENTS*\n\n"
    for e in upcoming[:15]:
        flag = "рҹ”ҙ TODAY" if e["date"] == today_str() else "рҹ“Ҷ"
        t = f" @ {e['time']}" if e.get("time") else ""
        txt += f"{flag} {e['date']}{t} вҖ” {e['title']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_del_cal(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delcal <id>`"); return
    try:
        if calendar.delete(int(ctx.args[0])):
            await update.message.reply_text("рҹ—‘ Event deleted!")
        else:
            await update.message.reply_text("вқҢ Not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("вқҢ Invalid ID!")

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# DIARY COMMANDS
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
async def cmd_diary(update, ctx):
    args = ctx.args
    if args and args[0] not in ("date", "all", "week"):
        text = " ".join(args)
        diary.add(text, mood="рҹ“қ")
        await update.message.reply_text(f"рҹ“– *Diary saved!* рҹ•җ {now_str()}\n\n_{text[:120]}_", parse_mode="Markdown")
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
    await update.message.reply_text("рҹ”җ *Diary Password:*\n_Password daalo:_", parse_mode="Markdown")
    return DIARY_AWAIT_PASS

async def cmd_diary_view(update, ctx):
    ctx.user_data["diary_view"] = ("today", None)
    await update.message.reply_text("рҹ”җ *Diary Password:*", parse_mode="Markdown")
    return DIARY_AWAIT_PASS

async def diary_password_check(update, ctx):
    entered = update.message.text.strip()
    if entered != DIARY_PASSWORD:
        await update.message.reply_text("вқҢ *Galat password!*", parse_mode="Markdown")
        return ConversationHandler.END
    view_type, view_arg = ctx.user_data.get("diary_view", ("today", None))
    await _show_diary(update, view_type, view_arg)
    return ConversationHandler.END

async def diary_conv_cancel(update, ctx):
    try:
        if update.message:
            await update.message.reply_text("вҸұ Diary session expired.")
    except:
        pass
    return ConversationHandler.END

async def _show_diary(update, view_type, view_arg):
    if view_type == "today":
        entries = diary.get(today_str())
        title = f"рҹ“– *Aaj Ki Diary вҖ” {today_str()}*"
        all_entries = {today_str(): entries} if entries else {}
    elif view_type == "date" and view_arg:
        entries = diary.get(view_arg)
        title = f"рҹ“– *Diary вҖ” {view_arg}*"
        all_entries = {view_arg: entries} if entries else {}
    elif view_type == "all":
        all_entries = diary.get_all_entries()
        title = "рҹ“– *All Diary Entries*"
    elif view_type == "week":
        all_entries = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            ents = diary.get(d)
            if ents:
                all_entries[d] = ents
        title = "рҹ“– *This Week's Diary*"
    else:
        all_entries = {}
        title = "рҹ“– *Diary*"

    if not all_entries:
        await update.message.reply_text(f"{title}\n\n_Koi entry nahi._", parse_mode="Markdown")
        return

    txt = f"{title}\n\n"
    for d_key in sorted(all_entries.keys(), reverse=True)[:7]:
        txt += f"рҹ“… *{d_key}*\n"
        for e in all_entries[d_key][-3:]:
            txt += f"  {e.get('mood','рҹ“қ')} {e.get('time','')} вҖ” {e.get('text','')[:100]}\n"
        txt += "\n"
    try:
        await update.message.reply_text(txt, parse_mode="Markdown")
    except:
        await update.message.reply_text(txt)

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# MESSAGE HANDLER
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_msg = update.message.text.strip()
    if user_msg.startswith('/'):
        return

    if ctx.user_data.get("awaiting_diary_entry"):
        ctx.user_data.pop("awaiting_diary_entry", None)
        diary.add(user_msg, mood="рҹ“қ")
        await update.message.reply_text(
            f"рҹ“– *Diary saved!* рҹ•җ {now_str()}\n\n_{user_msg[:150]}_",
            parse_mode="Markdown")
        await auto_backup_to_sheets()
        return

    ctx.user_data.pop("diary_view", None)

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ai_chat(user_msg, update.effective_chat.id)
    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(reply)

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# JOB QUEUE вҖ” BACKGROUND TASKS
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
async def reminder_job(context):
    now = now_ist()
    now_time = now.strftime("%H:%M")
    if now_time in ("00:00", "00:01", "00:02"):
        reminders.reset_daily()
        log.info("рҹ”„ Daily reset")
        return
    due = reminders.due_now()
    for r in due:
        try:
            repeat_note = ""
            if r["repeat"] == "daily":
                repeat_note = "\nрҹ”Ғ _Kal bhi yaad dilaunga!_"
            elif r["repeat"] == "weekly":
                repeat_note = "\nрҹ“… _Agli hafte!_"
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=f"рҹҡЁ *ALARM!* вҸ° *{r['time']}*\nрҹ“ў {r['text'].upper()}{repeat_note}",
                parse_mode="Markdown", disable_notification=False
            )
            reminders.mark_fired(r["id"])
            log.info(f"вң… Fired #{r['id']}")
            await asyncio.sleep(1)
        except Exception as e:
            log.error(f"вқҢ Reminder #{r['id']} failed: {e}")
            try:
                reminders.mark_fired(r["id"])
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
    txt = "рҹ’і *BILL DUE SOON*\n\n" + "\n".join(f"вҡ пёҸ {b['name']} вҖ” вӮ№{b['amount']:.0f}" for b in due)
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
                text=f"рҹ’§ *Paani peene ka time!*\nToday: {total}ml/{goal}ml\n`/water` se log karo",
                parse_mode="Markdown")
        except:
            pass

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
    if len(tp) >= 5:
        high_priority = [t for t in tp if t.get("priority") == "high"]
        if high_priority:
            insights.append(f"рҹ”ҙ *{len(high_priority)} HIGH priority tasks!* Focus inpe pehle")
        else:
            insights.append(f"вҡ пёҸ *Aaj workload zyada hai* вҖ” {len(tp)} tasks pending!")
    elif len(tp) == 0:
        insights.append("вң… *Aaj koi pending task nahi!* Clean slate вҖ” naya kaam add karo")
    else:
        insights.append(f"рҹ“Ӣ *{len(tp)} task(s) pending* aaj ke liye")
    at_risk = [h for h in all_h if h.get('streak', 0) >= 3 and h['id'] not in [x['id'] for x in hd]]
    if at_risk:
        names = ", ".join(h['name'] for h in at_risk[:2])
        insights.append(f"рҹ”Ҙ *Streak at risk!* {names} вҖ” aaj zaroor complete karo!")
    for b in due_bills[:2]:
        insights.append(f"рҹ’і *{b['name']}* ka bill due вҖ” вӮ№{b['amount']:.0f}")
    for e in cal_today[:2]:
        t_str = f" @ {e['time']}" if e.get('time') else ""
        insights.append(f"рҹ“… *{e['title']}*{t_str} вҖ” aaj")
    day_name = now.strftime("%A")
    day_msgs = {
        "Monday":    "рҹ’Ә *Naya hafta, naya jazbaa!* Best effort dena.",
        "Friday":    "рҹҺү *Friday hai!* Week strong finish karo.",
        "Saturday":  "вҳ• *Saturday!* Thoda rest, thodi planning.",
        "Sunday":    "вҳҖпёҸ *Sunday!* Agli hafte ki tayyari karo.",
        "Wednesday": "рҹ“Ҳ *Hafte ka beech!* Momentum maintain karo.",
    }
    if day_name in day_msgs:
        insights.append(day_msgs[day_name])
    msg = (f"рҹҢ… *GOOD MORNING!*\n"
           f"_{now.strftime('%A, %d %b')} вҖ” {now.strftime('%I:%M %p')} IST_\n\n")
    msg += "\n".join(f"вҖў {i}" for i in insights[:6])
    msg += f"\n\nрҹ’§ Paani goal aaj: *{water_goal_val}ml*"
    msg += "\n\n_/briefing se full summary_ рҹ‘Ү"
    for cid in chat_ids:
        try:
            await context.bot.send_message(chat_id=cid, text=msg, parse_mode="Markdown")
        except Exception as e:
            log.warning(f"Morning briefing failed {cid}: {e}")

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
        task_week = tasks.get_weekly_summary()
        week_done = sum(v["done"] for v in task_week.values())
        week_created = sum(v["created"] for v in task_week.values())
        habit_completions = sum(len(habits.get_logs_by_date((now.date() - timedelta(days=i)).isoformat())) for i in range(7))
        week_expense = sum(sum(e["amount"] for e in expenses.get_by_date((now.date() - timedelta(days=i)).isoformat())) for i in range(7))
        max_possible = len(all_h) * 7
        habit_score = int(habit_completions / max_possible * 100) if max_possible > 0 else 0
        task_score = int(week_done / week_created * 100) if week_created > 0 else 100
        avg_score = (task_score + habit_score) // 2
        msg = (f"рҹ“Ҡ *WEEKLY ANALYTICS*\n"
               f"_{now.strftime('%d %b')} week review_\n\n"
               f"рҹ“Ӣ *Tasks:* вң… {week_done}/{week_created} вҖ” *{task_score}%*\n"
               f"рҹ’Ә *Habits:* {habit_completions} completions вҖ” *{habit_score}%*\n"
               f"рҹ’° *Expenses:* вӮ№{week_expense:.0f} this week\n\n")
        if avg_score >= 80:
            msg += "рҹҸҶ *Grade: EXCELLENT!* Mazaa aa gaya yaar!"
        elif avg_score >= 60:
            msg += "рҹ‘Қ *Grade: GOOD!* Aur better ho sakta hai!"
        elif avg_score >= 40:
            msg += "рҹ“Ҳ *Grade: AVERAGE.* Agli hafte zyada focus karo!"
        else:
            msg += "рҹ’Ә *Grade: NEEDS WORK.* Kal se naya jazbaa!"
        msg += f"\n\n_/weekly se detailed breakdown dekho_"
    else:
        msg = (f"рҹҢҷ *Aaj ka Summary*\n"
               f"_{now.strftime('%A, %d %b')}_\n\n"
               f"вң… Tasks done: {today_done}\n"
               f"рҹ’Ә Habits: {len(habits_done_today)}/{len(all_h)}\n"
               f"рҹ’° Kharcha: вӮ№{today_exp:.0f}\n")
        if habits_pending_today:
            msg += f"\nвҸі Abhi pending: {', '.join(h['name'] for h in habits_pending_today[:3])}"
        msg += "\n\n_Kal phir fresh start!_ рҹҢҹ"
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
    log.info(f"рҹ“Ө {result}")
    return result

async def scheduled_backup_job(context):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, google_sheets.full_sync)
    log.info(f"рҹ•’ Scheduled backup: {result}")

async def daily_log_job(context):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, google_sheets.save_daily_log)
    log.info(f"рҹ“… Daily log: {result}")

# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
# MAIN
# в•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җв•җ
def main():
    n = now_ist()
    log.info("=" * 60)
    log.info(f"рҹӨ– Bot v15 JARVIS (Cleaned)")
    log.info(f"вҸ° IST: {n.strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"рҹ“Ҡ Sheets: {'вң…' if google_sheets.sheet else 'вқҢ'}")
    log.info(f"рҹ’Һ Gemini: {'YES' if GEMINI_API_KEY else 'NO'} | рҹҰҷ Groq: {'YES' if GROQ_API_KEY else 'NO'}")
    log.info("=" * 60)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    async def post_init(app):
        try:
            chat_id = os.environ.get("ADMIN_CHAT_ID", "")
            if chat_id:
                r_count = len(reminders.store.data.get("list", []))
                t_count = len(tasks.store.data.get("list", []))
                active_rem = [r for r in reminders.store.data.get("list", []) if r.get("active")]
                rem_info = "\n".join(f"  вҖў {r['time']} вҖ” {r['text']}" for r in active_rem[:3]) or "  Koi nahi"
                sheets_msg = "вң… Sheets connected!" if google_sheets.sheet else "вқҢ Sheets NOT connected!"
                ai_status = f"рҹ’Һ Gemini {'вң…' if GEMINI_API_KEY else 'вқҢ'} | рҹҰҷ Groq {'вң…' if GROQ_API_KEY else 'вқҢ'}"
                n2 = now_ist()
                msg_text = (
                    f"рҹӨ– *Bot v15 Start!*\n\n"
                    f"вҸ° {n2.strftime('%d %b %Y %I:%M %p')} IST\n\n"
                    f"рҹ“Ҡ {sheets_msg}\n"
                    f"рҹӨ– {ai_status}\n\n"
                    f"рҹ“Ұ Data: вҸ° {r_count} reminders \\| рҹ“Ӣ {t_count} tasks\n\n"
                    f"вҸ° *Active reminders:*\n{rem_info}\n\n"
                    f"рҹҶ• v15 cleaned version: no keyboards, no HF, no dead stores"
                )
                await app.bot.send_message(
                    chat_id=int(chat_id),
                    text=msg_text,
                    parse_mode="Markdown"
                )
        except Exception as e:
            log.warning(f"Startup notification failed: {e}")

    app.post_init = post_init

    commands = [
        ("start", cmd_start), ("help", cmd_help),
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("habit", cmd_habit), ("hdone", cmd_hdone), ("delhabit", cmd_delhabit),
        ("kharcha", cmd_kharcha), ("budget", cmd_budget),
        ("goal", cmd_goal), ("gprogress", cmd_gprogress),
        ("remember", cmd_remember), ("recall", cmd_recall),
        ("briefing", cmd_briefing), ("weekly", cmd_weekly), ("report", cmd_report),
        ("news", cmd_news), ("clear", cmd_clear), ("nuke", cmd_nuke),
        ("alltasks", cmd_alltasks), ("completed", cmd_completed), ("yesterday", cmd_yesterday),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list), ("delremind", cmd_delremind),
        ("water", cmd_water), ("waterstatus", cmd_water_status), ("watergoal", cmd_water_goal),
        ("bill", cmd_bill), ("bills", cmd_bills_list), ("billpaid", cmd_bill_paid), ("delbill", cmd_del_bill),
        ("cal", cmd_cal), ("calendar", cmd_cal_list), ("delcal", cmd_del_cal),
        ("memory", cmd_memory), ("backup", cmd_backup), ("dbstatus", cmd_dbstatus),
    ]
    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))

    diary_conv = ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary), CommandHandler("diaryview", cmd_diary_view)],
        states={DIARY_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)]},
        fallbacks=[CommandHandler("cancel", diary_conv_cancel)],
        per_user=True, per_chat=True, conversation_timeout=60,
    )
    app.add_handler(diary_conv)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(reminder_job,            interval=60,    first=15)
        app.job_queue.run_repeating(proactive_morning_job,   interval=60,    first=30)
        app.job_queue.run_repeating(weekly_analytics_job,    interval=60,    first=45)
        app.job_queue.run_repeating(bill_due_job,            interval=3600,  first=300)
        app.job_queue.run_repeating(water_reminder_job,      interval=3600,  first=600)
        app.job_queue.run_repeating(scheduled_backup_job,    interval=3600,  first=120)
        app.job_queue.run_daily(daily_log_job, time=dt_module.time(hour=21, minute=0, tzinfo=IST))
        log.info("вҸ° Jobs: Reminders | Morning | Analytics | Bills/Water | Backup")
    else:
        log.error("вқҢ JobQueue NOT AVAILABLE!")

    log.info("вң… Bot v15 ready!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()