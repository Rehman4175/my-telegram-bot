#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v15.0 JARVIS ENHANCED             ║
║  ✅ ALL PREVIOUS FEATURES INTACT                               ║
║  🆕 INSIGHT SYSTEM — one-click context view                   ║
║  🆕 PREDICTION ENGINE — overload/spending alerts              ║
║  🆕 DECISION ENGINE — auto focus & budget warnings            ║
║  🆕 SMART AUTO-COMMANDS — natural language actions             ║
║  🆕 PROACTIVE ALERTS — background monitoring                  ║
║  + Hello/Hi instant greeting                                  ║
║  + Reminder ONLY on explicit request                          ║
║  + Google Sheets restore fixed (expected_headers)             ║
║  + VOICE COMMANDS (Groq Whisper)                               ║
║  + GOOGLE SHEETS BACKUP                                       ║
║  + REMINDERS | TASKS | HABITS | DIARY | EXPENSES | GOALS      ║
║  + WATER | BILLS | CALENDAR | MEMORY | NOTES | NEWS           ║
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
# DATABASE — JSON local cache
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
    msg = user_msg.lower().strip()
    n = now_ist()
    if any(w in msg for w in ["time", "baje", "kitne baje", "time kya"]):
        return f"⏰ Abhi *{n.strftime('%I:%M %p')}* baj rahe hain (IST)"
    if any(w in msg for w in ["date", "aaj kya", "tarikh", "aaj kitni"]):
        return f"📅 Aaj *{n.strftime('%A, %d %B %Y')}* hai"
    if any(w in msg for w in ["hello", "hi", "assalam", "namaste", "hey"]):
        return "🕌 *Assalamualaikum!* Main aapka AI dost hoon. Batao kaisi help chahiye? 😊"
    if any(w in msg for w in ["kaise ho", "how are", "kya haal"]):
        return "😊 *Main badiya hoon!* Aap sunao, kya ho raha hai aaj kal?"
    if any(w in msg for w in ["thank", "shukriya", "thanks"]):
        return "🤗 *Welcome!* Aur koi help chahiye toh batana!"
    if any(w in msg for w in ["bye", "allah hafiz", "good night"]):
        return "🌙 *Allah Hafiz!* Apna khayal rakhna. Fir milenge! 🤗"
    replies = ["🙏 Main yahin hoon! Batao kya help chahiye?", "😊 Haan bolo! Kya karna hai aaj?", "🤖 Ready hoon! `/help` se commands dekho."]
    return random.choice(replies)

# ═══════════════════════════════════════════════════════════════════
# VOICE TRANSCRIPTION (Groq Whisper)
# ═══════════════════════════════════════════════════════════════════
async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    voice = update.message.voice or update.message.audio
    if not voice: return
    if not GROQ_API_KEY:
        await update.message.reply_text("🎤 *Voice ke liye GROQ_API_KEY chahiye!*\n\n1. groq.com pe free account banao\n2. API key lo\n3. GitHub Secrets mein add karo", parse_mode="Markdown")
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
        try: os.unlink(tmp_path)
        except: pass
        if not text:
            await status_msg.edit_text("❌ Samajh nahi aaya — text mein likh do.", parse_mode="Markdown")
            return
        await status_msg.edit_text(f"🎤 *Suna:* _{text}_", parse_mode="Markdown")
        await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        reply = await ai_chat(text, update.effective_chat.id)
        try: await update.message.reply_text(reply, parse_mode="Markdown")
        except: await update.message.reply_text(reply)
    except Exception as e:
        log.error(f"Voice handler error: {e}")
        await status_msg.edit_text("❌ Voice process nahi hua.")

def _sync_transcribe(file_path: str) -> str:
    if not GROQ_API_KEY: return None
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        with open(file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo", file=audio_file,
                response_format="text", language="hi")
        text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
        if text: log.info(f"🎤 Transcribed: {text[:80]}"); return text
    except Exception as e: log.warning(f"Groq error: {e}")
    return None

# ═══════════════════════════════════════════════════════════════════
# MAIN AI PIPELINE
# ═══════════════════════════════════════════════════════════════════
def get_ai_reply(user_msg, chat_id=None, system_ctx=None):
    if not system_ctx: system_ctx = build_system_prompt()
    user_msg_short = user_msg[:500]
    prompt = f"""{system_ctx}

User message: {user_msg_short}

Reply in Hindi/Hinglish (2-4 lines, warm & friendly like a close friend):
- Dost ki tarah natural baat karo
- "As an AI" kabhi mat bol
- Agar time puchhe to upar diya hua exact time batana
- Short aur helpful jawab do"""
    reply = call_gemini(prompt, max_tokens=300)
    if reply and len(reply) > 5: return reply
    reply = call_huggingface(prompt)
    if reply and len(reply) > 5: return reply + "\n\n_⚡ (via free model)_"
    return smart_fallback(user_msg)

# ═══════════════════════════════════════════════════════════════════
# ALL DATA STORES
# ═══════════════════════════════════════════════════════════════════

class MemoryStore:
    def __init__(self): self.store = Store("memory", {"facts": [], "prefs": {}, "dates": {}, "important_notes": []})
    def add_fact(self, text):
        facts = self.store.data.get("facts", [])
        if facts and text[:50] in [f.get("f", "")[:50] for f in facts[-30:]]: return
        facts.append({"f": text, "d": today_str()})
        self.store.data["facts"] = facts[-200:]; self.store.save()
    def add_important(self, note): self.store.data.setdefault("important_notes", []).append({"note": note, "d": today_str()}); self.store.save()
    def set_pref(self, k, v): self.store.data.setdefault("prefs", {})[k] = v; self.store.save()
    def add_date(self, name, d): self.store.data.setdefault("dates", {})[name] = d; self.store.save()
    def get_all_facts(self): return self.store.data.get("facts", [])
    def context(self):
        facts = "\n".join(f"• {x['f']}" for x in self.get_all_facts()[-15:]) or "Kuch nahi"
        prefs = "\n".join(f"• {k}: {v}" for k, v in self.store.data.get("prefs", {}).items()) or "Kuch nahi"
        return f"FACTS:\n{facts}\n\nPREFERENCES:\n{prefs}"

class TaskStore:
    def __init__(self): self.store = Store("tasks", {"list": [], "counter": 0})
    def _save(self): self.store.save()
    def add(self, title, priority="medium", due=None):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        t = {"id": self.store.data["counter"], "title": title, "priority": priority, "due": due or today_str(), "done": False, "done_at": None, "created": datetime.now().isoformat()}
        self.store.data["list"].append(t); self._save(); return t
    def complete(self, tid):
        for t in self.store.data["list"]:
            if t["id"] == tid and not t["done"]: t["done"] = True; t["done_at"] = datetime.now().isoformat(); self._save(); return t
        return None
    def delete(self, tid):
        before = len(self.store.data["list"])
        self.store.data["list"] = [t for t in self.store.data["list"] if t["id"] != tid]; self._save()
        return before != len(self.store.data["list"])
    def pending(self): return [t for t in self.store.data.get("list", []) if not t["done"]]
    def done_on(self, d): return [t for t in self.store.data.get("list", []) if t["done"] and (t.get("done_at", "") or "")[:10] == d]
    def today_pending(self):
        td = today_str()
        return [t for t in self.store.data.get("list", []) if not t["done"] and t.get("due", "") <= td]
    def all_tasks(self): return self.store.data.get("list", [])
    def completed_tasks(self): return [t for t in self.store.data.get("list", []) if t["done"]]
    def get_weekly_summary(self):
        result = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            result[d] = {"done": len(self.done_on(d)), "created": len([t for t in self.all_tasks() if t.get("created", "")[:10] == d])}
        return result

class FailedReqStore:
    def __init__(self): self.store = Store("failed_requests", {"queue": []})
    def add(self, msg, chat_id, reason): self.store.data["queue"].append({"msg": msg, "chat_id": chat_id, "reason": reason, "time": datetime.now().isoformat(), "retried": False}); self.store.data["queue"] = self.store.data["queue"][-50:]; self.store.save()
    def get_unretried(self): return [r for r in self.store.data.get("queue", []) if not r["retried"]]
    def mark_retried(self, idx):
        if 0 <= idx < len(self.store.data["queue"]): self.store.data["queue"][idx]["retried"] = True; self.store.save()

class DiaryStore:
    def __init__(self): self.store = Store("diary", {"entries": {}})
    def add(self, text, mood="😊"): td = today_str(); self.store.data.setdefault("entries", {}).setdefault(td, []); self.store.data["entries"][td].append({"text": text, "mood": mood, "time": now_str()}); self.store.save()
    def get(self, d): return self.store.data.get("entries", {}).get(d, [])
    def get_all_entries(self): return self.store.data.get("entries", {})

class HabitStore:
    def __init__(self): self.store = Store("habits", {"list": [], "logs": {}, "counter": 0})
    def add(self, name, emoji="✅"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        h = {"id": self.store.data["counter"], "name": name, "emoji": emoji, "streak": 0, "best_streak": 0, "created": today_str()}
        self.store.data["list"].append(h); self.store.save(); return h
    def log(self, hid):
        td, yd = today_str(), yesterday_str()
        logs = self.store.data.get("logs", {}); logs.setdefault(td, [])
        if hid in logs[td]: return False, 0
        logs[td].append(hid)
        for h in self.store.data.get("list", []):
            if h["id"] == hid:
                yd_logs = logs.get(yd, [])
                h["streak"] = h.get("streak", 0) + 1 if hid in yd_logs else 1
                h["best_streak"] = max(h.get("best_streak", 0), h.get("streak", 0))
        self.store.data["logs"] = logs; self.store.save()
        streak = next((h.get("streak", 1) for h in self.store.data["list"] if h["id"] == hid), 1)
        return True, streak
    def today_status(self):
        done_ids = self.store.data.get("logs", {}).get(today_str(), []); all_h = self.all()
        return ([h for h in all_h if h["id"] in done_ids], [h for h in all_h if h["id"] not in done_ids])
    def all(self): return self.store.data.get("list", [])
    def delete(self, hid): self.store.data["list"] = [h for h in self.store.data["list"] if h["id"] != hid]; self.store.save()
    def get_logs_by_date(self, target_date): return self.store.data.get("logs", {}).get(target_date, [])

class NotesStore:
    def __init__(self): self.store = Store("notes", {"list": [], "counter": 0})
    def add(self, content, tag="general"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        n = {"id": self.store.data["counter"], "text": content, "tag": tag, "created": datetime.now().isoformat()}
        self.store.data["list"].append(n); self.store.save(); return n
    def delete(self, nid): self.store.data["list"] = [n for n in self.store.data["list"] if n["id"] != nid]; self.store.save()
    def recent(self, n=15): return self.store.data.get("list", [])[-n:]
    def count(self): return len(self.store.data.get("list", []))

class ExpenseStore:
    def __init__(self): self.store = Store("expenses", {"list": [], "counter": 0, "budget": {}})
    def add(self, amount, desc, category="general"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        self.store.data["list"].append({"id": self.store.data["counter"], "amount": amount, "desc": desc, "category": category, "date": today_str(), "time": now_str()}); self.store.save()
    def set_budget(self, amount): self.store.data["budget"]["monthly"] = amount; self.store.save()
    def today_total(self): return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date") == today_str())
    def month_total(self):
        m = today_str()[:7]
        return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date", "")[:7] == m)
    def budget_left(self):
        b = self.store.data.get("budget", {}).get("monthly", 0); return b - self.month_total() if b else None
    def get_by_date(self, target_date): return [e for e in self.store.data.get("list", []) if e.get("date") == target_date]
    def total_count(self): return len(self.store.data.get("list", []))

class GoalStore:
    def __init__(self): self.store = Store("goals", {"list": [], "counter": 0})
    def add(self, title, deadline=None, why=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        g = {"id": self.store.data["counter"], "title": title, "deadline": deadline or "", "why": why, "progress": 0, "done": False, "created": today_str()}
        self.store.data["list"].append(g); self.store.save(); return g
    def update_progress(self, gid, pct):
        for g in self.store.data["list"]:
            if g["id"] == gid: g["progress"] = min(100, max(0, pct))
                if g["progress"] == 100: g["done"] = True
                self.store.save(); return g
        return None
    def active(self): return [g for g in self.store.data.get("list", []) if not g["done"]]
    def completed(self): return [g for g in self.store.data.get("list", []) if g["done"]]
    def count(self): return len(self.store.data.get("list", []))

class ReminderStore:
    def __init__(self): self.store = Store("reminders", {"list": [], "counter": 0})
    def add(self, chat_id, text, remind_at, repeat="once"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        r = {"id": self.store.data["counter"], "chat_id": chat_id, "text": text, "time": remind_at, "repeat": repeat, "date": today_str(), "active": True, "fired_today": False, "created": datetime.now().isoformat()}
        self.store.data["list"].append(r); self.store.save(); return r
    def all_active(self): return [r for r in self.store.data.get("list", []) if r.get("active")]
    def get_all(self): return self.store.data.get("list", [])
    def get_by_date(self, target_date): return [r for r in self.get_all() if r.get("date") == target_date]
    def delete(self, rid):
        before = len(self.store.data["list"]); self.store.data["list"] = [r for r in self.store.data["list"] if r["id"] != rid]; self.store.save()
        return before != len(self.store.data["list"])
    def mark_fired(self, rid):
        for r in self.store.data["list"]:
            if r["id"] == rid: r["fired_today"] = True
                if r["repeat"] == "once": r["active"] = False
                self.store.save(); break
    def reset_daily(self):
        for r in self.store.data["list"]: r["fired_today"] = False
        self.store.save()
    def due_now(self):
        now = now_ist(); now_hm = now.strftime("%H:%M"); today = today_str(); due = []
        for r in self.store.data.get("list", []):
            if not r.get("active") or r.get("fired_today"): continue
            try:
                r_dt_str = f"{today} {r['time']}"; r_dt = datetime.strptime(r_dt_str, "%Y-%m-%d %H:%M")
                r_dt_ist = r_dt.replace(tzinfo=IST); diff_seconds = (now - r_dt_ist).total_seconds()
                if 0 <= diff_seconds < 120: due.append(r); continue
            except: pass
            if r["time"] == now_hm and r not in due: due.append(r)
        return due

class WaterStore:
    def __init__(self): self.store = Store("water", {"logs": {}, "goal_ml": 2000})
    def add(self, ml=250):
        td = today_str(); self.store.data.setdefault("logs", {}).setdefault(td, [])
        self.store.data["logs"][td].append({"ml": ml, "time": now_str()}); self.store.save()
    def today_total(self): return sum(e["ml"] for e in self.store.data.get("logs", {}).get(today_str(), []))
    def goal(self): return self.store.data.get("goal_ml", 2000)
    def set_goal(self, ml): self.store.data["goal_ml"] = ml; self.store.save()
    def get_by_date(self, target_date): return self.store.data.get("logs", {}).get(target_date, [])
    def week_summary(self):
        result = {}
        for i in range(7): d = (now_ist().date() - timedelta(days=i)).isoformat(); result[d] = sum(e["ml"] for e in self.store.data.get("logs", {}).get(d, []))
        return result

class BillStore:
    def __init__(self): self.store = Store("bills", {"list": [], "counter": 0})
    def add(self, name, amount, due_day, bill_type="bill"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        b = {"id": self.store.data["counter"], "name": name, "amount": amount, "due_day": due_day, "type": bill_type, "active": True, "paid_months": [], "created": today_str()}
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
    def delete(self, bid):
        before = len(self.store.data["list"]); self.store.data["list"] = [b for b in self.store.data["list"] if b["id"] != bid]; self.store.save()
        return before != len(self.store.data["list"])
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
    def add(self, title, event_date, event_time=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        e = {"id": self.store.data["counter"], "title": title, "date": event_date, "time": event_time, "created": today_str()}
        self.store.data["events"].append(e); self.store.save(); return e
    def delete(self, eid):
        before = len(self.store.data["events"]); self.store.data["events"] = [e for e in self.store.data["events"] if e["id"] != eid]; self.store.save()
        return before != len(self.store.data["events"])
    def upcoming(self, days=7):
        today_d = now_ist().date(); cutoff = today_d + timedelta(days=days); result = []
        for e in self.store.data.get("events", []):
            try: ed = date.fromisoformat(e["date"])
                if today_d <= ed <= cutoff: result.append(e)
            except: pass
        return sorted(result, key=lambda x: x["date"])
    def today_events(self): return [e for e in self.store.data.get("events", []) if e["date"] == today_str()]

class NewsStore:
    def __init__(self): self.store = Store("news_cache", {"cache": {}, "updated": {}})
    def get(self, category="India", max_items=5):
        now_ts = time.time(); cache = self.store.data
        if category in cache.get("cache", {}) and now_ts - cache.get("updated", {}).get(category, 0) < 1800: return cache["cache"][category][:max_items]
        feeds = {"India": "https://feeds.bbci.co.uk/hindi/rss.xml", "Technology": "https://feeds.feedburner.com/ndtvnews-tech-news", "Business": "https://economictimes.indiatimes.com/rssfeedstopstories.cms", "World": "https://feeds.bbci.co.uk/news/world/rss.xml", "Sports": "https://feeds.bbci.co.uk/sport/rss.xml"}
        url = feeds.get(category, feeds["India"]); items = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                tree = ET.parse(resp); root = tree.getroot(); channel = root.find("channel")
                if channel is None: channel = root
                for item in channel.findall("item")[:max_items]:
                    title = item.findtext("title", "").strip(); desc = item.findtext("description", "").strip()
                    if title: items.append({"title": title, "desc": desc[:120] if desc else "", "link": "", "pub": ""})
        except Exception as e: items = [{"title": "News unavailable", "desc": str(e)[:100], "link": "", "pub": ""}]
        cache.setdefault("cache", {})[category] = items; cache.setdefault("updated", {})[category] = now_ts; self.store.save()
        return items

class ChatHistoryStore:
    def __init__(self): self.store = Store("chat_history", {"history": [], "cleared_at": None, "msg_ids": []})
    def add(self, role, content): self.store.data["history"].append({"role": role, "content": content, "time": datetime.now().isoformat()}); self.store.data["history"] = self.store.data["history"][-40:]; self.store.save()
    def track_msg(self, chat_id, msg_id): self.store.data.setdefault("msg_ids", []).append({"chat_id": chat_id, "msg_id": msg_id}); self.store.data["msg_ids"] = self.store.data["msg_ids"][-200:]; self.store.save()
    def get_tracked_ids(self): return self.store.data.get("msg_ids", [])
    def clear(self):
        count = len(self.store.data["history"]); self.store.data["history"] = []; self.store.data["cleared_at"] = datetime.now().isoformat(); self.store.save(); return count
    def clear_msg_ids(self): self.store.data["msg_ids"] = []; self.store.save()
    def count(self): return len(self.store.data.get("history", []))

# ═══════════════════════════════════════════════════════════════════
# 🆕 JARVIS ENHANCEMENTS
# ═══════════════════════════════════════════════════════════════════

def build_jarvis_context():
    """Build insight context for Jarvis features"""
    n = now_ist()
    lines = []
    lines.append(f"🧠 *JARVIS INSIGHT*")
    lines.append(f"⏰ {n.strftime('%I:%M %p')} | 📅 {n.strftime('%d %b %Y')}")
    lines.append(f"{'═'*30}")
    
    p = tasks.pending()
    d = tasks.completed_tasks()
    lines.append(f"\n📋 *Tasks:* ⏳{len(p)} pending | ✅{len(d)} done")
    if p:
        for t in p[:5]:
            icon = "🔴" if t.get("priority")=="high" else "🟡" if t.get("priority")=="medium" else "🟢"
            lines.append(f"  {icon} #{t['id']} {t['title']}")
    
    hd, hp = habits.today_status()
    lines.append(f"\n💪 *Habits:* ✅{len(hd)} done | ⏳{len(hp)} pending")
    
    exp_t = expenses.today_total()
    exp_m = expenses.month_total()
    bl = expenses.budget_left()
    lines.append(f"\n💰 *Expenses:* Today ₹{exp_t:.0f} | Month ₹{exp_m:.0f}")
    if bl is not None: lines.append(f"  Budget left: ₹{bl:.0f}")
    
    w_t = water.today_total()
    w_g = water.goal()
    lines.append(f"\n💧 *Water:* {w_t}ml / {w_g}ml ({int(w_t/w_g*100) if w_g else 0}%)")
    
    ag = goals.active()
    cg = goals.completed()
    lines.append(f"\n🎯 *Goals:* {len(ag)} active | 🏆{len(cg)} completed")
    
    lines.append(f"\n📝 *Notes:* {notes.count()} total")
    lines.append(f"📖 *Diary:* {len(diary.get(today_str()))} entries today")
    lines.append(f"🧠 *Memories:* {len(memory.get_all_facts())} facts")
    
    return "\n".join(lines)

def prediction_engine():
    """🔮 Predict potential issues based on data patterns"""
    warnings = []
    
    # Task overload check
    pending = tasks.pending()
    if len(pending) > 10:
        warnings.append("📉 *Overload Risk:* 10+ pending tasks! Focus on top 3")
    elif len(pending) > 5:
        warnings.append("⚠️ *Task Alert:* 5+ pending tasks, plan karo")
    
    high_priority = [t for t in pending if t.get("priority") == "high"]
    if high_priority:
        warnings.append(f"🔴 *{len(high_priority)} high-priority tasks pending!*")
    
    # Spending check
    today_exp = expenses.today_total()
    month_exp = expenses.month_total()
    bl = expenses.budget_left()
    
    if bl is not None and bl < 0:
        warnings.append("💸 *Budget exceeded!* Spending rok lo")
    elif bl is not None and bl < (expenses.store.data.get("budget", {}).get("monthly", 0) * 0.3):
        warnings.append(f"⚠️ *Budget low:* Only ₹{bl:.0f} left")
    
    if today_exp > 2000:
        warnings.append(f"💸 *High spending today:* ₹{today_exp:.0f} — control karo")
    
    # Habit consistency
    hd, hp = habits.today_status()
    if len(hp) > 0 and len(habits.all()) > 3:
        warnings.append(f"💪 *{len(hp)} habits pending today* — consistency matters!")
    
    # Diary/reflection gap
    diary_today = diary.get(today_str())
    if not diary_today:
        warnings.append("📖 *No diary entry today* — reflect karo!")
    
    # Water intake
    w_t = water.today_total()
    w_g = water.goal()
    if w_t < w_g * 0.5 and now_ist().hour > 14:
        warnings.append(f"💧 *Low water intake:* {w_t}ml/{w_g}ml — paani piyo!")
    
    # Bill due soon
    due_bills = bills.due_soon(3)
    if due_bills:
        bill_names = ", ".join(f"{b['name']} ₹{b['amount']:.0f}" for b in due_bills[:3])
        warnings.append(f"💳 *Bills due soon:* {bill_names}")
    
    return warnings if warnings else ["✅ *All systems stable!*"]

def decision_engine():
    """⚡ Auto-detect actions needed based on data"""
    actions = []
    
    pending = tasks.pending()
    
    # Focus recommendation
    if len(pending) > 5:
        high_pr = [t for t in pending if t.get("priority") == "high"]
        if high_pr:
            actions.append({"type": "focus", "msg": f"🧠 *FOCUS MODE:* {len(high_pr)} high-priority tasks! Do:`\n" + "\n".join(f"• #{t['id']} {t['title']}" for t in high_pr[:3])})
        else:
            actions.append({"type": "focus", "msg": f"🧠 *FOCUS:* Top 3 tasks first:`\n" + "\n".join(f"• #{t['id']} {t['title']}" for t in pending[:3])})
    
    # Spending alert
    bl = expenses.budget_left()
    if bl is not None and bl < 0:
        actions.append({"type": "spend", "msg": "💸 *STOP SPENDING!* Budget exceeded!"})
    elif bl is not None and bl < 500:
        actions.append({"type": "spend", "msg": f"⚠️ *Budget alert:* Only ₹{bl:.0f} left this month"})
    
    # Water reminder
    w_t = water.today_total()
    w_g = water.goal()
    if w_t < w_g * 0.4 and now_ist().hour > 12:
        actions.append({"type": "water", "msg": f"💧 *PAANI PIYO!* Only {w_t}ml/{w_g}ml"})
    
    # Habit nudge
    _, hp = habits.today_status()
    if hp and now_ist().hour > 18:
        actions.append({"type": "habit", "msg": f"💪 *Habits pending:* {', '.join(h['name'] for h in hp[:3])}"})
    
    return actions

# ═══════════════════════════════════════════════════════════════════
# INIT ALL STORES
# ═══════════════════════════════════════════════════════════════════
memory = MemoryStore()
tasks = TaskStore()
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
# GOOGLE SHEETS BACKUP INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class GoogleSheetsBackup:
    def __init__(self):
        self.sheet = None
        if not HAS_GSHEETS: log.warning("⚠️ gspread not installed!"); return
        creds_json = os.environ.get("GOOGLE_CREDS_JSON", "") or os.environ.get("Google_CREDS_JSON", "")
        if not creds_json: log.warning("⚠️ GOOGLE_CREDS_JSON not found!"); return
        try:
            creds_dict = json.loads(creds_json)
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            self.sheet = client.open_by_key("1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")
            log.info("✅ Google Sheets connected!")
            self.ensure_worksheets()
        except Exception as e: log.error(f"❌ Google Sheets error: {e}")

    def ensure_worksheets(self):
        if not self.sheet: return
        required = ["Tasks", "Reminders", "Expenses", "Habits", "Water", "Memory", "Daily_Logs", "Goals", "Bills", "Calendar", "Diary"]
        existing_ws = self.sheet.worksheets(); existing_lower = {ws.title.lower(): ws.title for ws in existing_ws}
        for name in required:
            if name.lower() not in existing_lower:
                try: self.sheet.add_worksheet(title=name, rows=1000, cols=20)
                except: pass
        self.setup_headers()

    def setup_headers(self):
        if not self.sheet: return
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
            "Diary": ["Date", "Time", "Mood", "Entry Text"]
        }
        for sheet_name, headers in headers_config.items():
            try:
                ws = self.sheet.worksheet(sheet_name); first_row = ws.row_values(1)
                if not first_row or not any(first_row): ws.update('A1', [headers])
            except: pass

    def _upsert_rows(self, ws, new_rows, id_col=0):
        try:
            existing = ws.get_all_values(); key_to_row = {}
            for i, row in enumerate(existing[1:], start=2):
                if row and len(row) > abs(id_col):
                    key = str(row[id_col]).strip()
                    if key: key_to_row[key] = i
            updates = []; appends = []
            for row in new_rows:
                key = str(row[id_col]).strip() if row else ""
                if key and key in key_to_row: updates.append((key_to_row[key], row))
                else: appends.append(row)
            if updates:
                batch = []
                for row_num, data in updates:
                    col_end = chr(ord("A") + len(data) - 1)
                    batch.append({"range": f"A{row_num}:{col_end}{row_num}", "values": [data]})
                ws.batch_update(batch)
            for row in appends: ws.append_row(row, value_input_option="USER_ENTERED")
            return len(updates), len(appends)
        except Exception as e: log.error(f"Upsert error: {e}"); return 0, 0

    def save_tasks(self, tasks_list):
        if not self.sheet or not tasks_list: return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Tasks")
            rows = [[str(t.get("id","")), t.get("title",""), t.get("priority","medium"), "Done" if t.get("done") else "Pending", t.get("created","")[:10], t.get("done_at","")[:10] if t.get("done_at") else ""] for t in tasks_list]
            self._upsert_rows(ws, rows, id_col=0); return True
        except Exception as e: log.error(f"Tasks save error: {e}"); return False

    def save_reminders(self, reminders_list):
        if not self.sheet or not reminders_list: return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Reminders")
            rows = [[str(r.get("id","")), r.get("time",""), r.get("text",""), r.get("repeat","once"), "Active" if r.get("active") else "Inactive", r.get("date",""), "Yes" if r.get("fired_today") else "No", r.get("created","")[:16] if r.get("created") else ""] for r in reminders_list]
            self._upsert_rows(ws, rows, id_col=0); return True
        except Exception as e: log.error(f"Reminders save error: {e}"); return False

    def save_expenses(self, expenses_list):
        if not self.sheet or not expenses_list: return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Expenses"); existing = ws.get_all_values(); existing_keys = set()
            for row in existing[1:]:
                if len(row) >= 5: existing_keys.add(f"{row[0]}|{row[1]}|{row[2]}")
            new_rows = []
            for e in expenses_list:
                key = f"{e.get('date','')}|{e.get('amount','')}|{e.get('desc','')}"
                if key not in existing_keys: new_rows.append([e.get("date",""), e.get("amount",0), e.get("desc",""), e.get("category","general"), e.get("time","")]); existing_keys.add(key)
            for row in new_rows: ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except Exception as e: log.error(f"Expenses save error: {e}"); return False

    def save_daily_log(self):
        if not self.sheet: return False
        try:
            ws = self.sheet.worksheet("Daily_Logs"); today = today_str(); now = now_ist(); day_name = now.strftime("%A")
            tasks_done = len(tasks.done_on(today)); tasks_pending = len(tasks.today_pending())
            expenses_total = expenses.today_total(); water_total = water.today_total(); habits_done = len(habits.today_status()[0])
            new_row = [today, day_name, tasks_done, tasks_pending, expenses_total, water_total, habits_done, "", ""]
            all_values = ws.get_all_values(); today_row_idx = None
            for idx, row in enumerate(all_values):
                if row and row[0] == today: today_row_idx = idx + 1; break
            if today_row_idx: ws.update(f'A{today_row_idx}:I{today_row_idx}', [new_row])
            else: ws.append_row(new_row)
            return True
        except Exception as e: log.error(f"Daily log error: {e}"); return False

    def full_sync(self):
        if not self.sheet: return "❌ Google Sheets not connected!"
        ops = [("Tasks", lambda: self.save_tasks(tasks.all_tasks())), ("Reminders", lambda: self.save_reminders(reminders.get_all())), ("Expenses", lambda: self.save_expenses(expenses.store.data.get("list", []))), ("Daily_Log", lambda: self.save_daily_log())]
        success_count = 0; errors = []
        for name, fn in ops:
            try:
                if fn(): success_count += 1
                else: errors.append(name)
            except Exception as e: log.error(f"Sync error [{name}]: {e}"); errors.append(name)
        if errors: return f"⚠️ Synced {success_count}/{len(ops)} | Failed: {', '.join(errors)}"
        return f"✅ Synced {success_count}/{len(ops)} sheets!"

    def restore_from_sheets(self):
        if not self.sheet: return False
        restored = []; log.info("🔄 Restoring data from Google Sheets...")
        def _safe_int(val, default=0):
            try: return int(str(val).strip())
            except: return default
        def _safe_str(val, default=""):
            try: return str(val).strip()
            except: return default
        def _is_header(val, h): return str(val).strip().lower() == h.lower()
        try:
            ws = self.sheet.worksheet("Tasks")
            rows = ws.get_all_records(expected_headers=["ID", "Title", "Priority", "Status", "Created At", "Completed At"])
            task_list = []
            for r in rows:
                if _is_header(r.get("ID",""), "id"): continue
                tid = _safe_int(r.get("ID",0)); title = _safe_str(r.get("Title",""))
                if not tid and not title: continue
                task_list.append({"id": tid, "title": title, "priority": _safe_str(r.get("Priority","medium")).lower(), "done": _safe_str(r.get("Status","")).lower() in ["done","completed","true"], "created": _safe_str(r.get("Created At", today_str())), "done_at": _safe_str(r.get("Completed At",""))})
            if task_list:
                max_id = max((t["id"] for t in task_list), default=0); db.save("tasks", {"list": task_list, "counter": max_id}); restored.append(f"📋 {len(task_list)} tasks")
        except Exception as e: log.warning(f"Tasks restore failed: {e}")
        try:
            ws = self.sheet.worksheet("Reminders")
            rows = ws.get_all_records(expected_headers=["ID", "Time (HH:MM)", "Text", "Repeat", "Status", "Created Date", "Fired Today", "Created At"])
            rem_list = []
            for r in rows:
                if _is_header(r.get("ID",""), "id"): continue
                rid = _safe_int(r.get("ID",0)); text = _safe_str(r.get("Text",""))
                if not rid and not text: continue
                rem_list.append({"id": rid, "text": text, "time": _safe_str(r.get("Time (HH:MM)","")), "repeat": _safe_str(r.get("Repeat","once")).lower(), "active": _safe_str(r.get("Status","Active")).lower() in ["active","true"], "fired_today": False, "date": _safe_str(r.get("Created Date", today_str())), "chat_id": int(os.environ.get("ADMIN_CHAT_ID","0") or "0")})
            if rem_list:
                max_id = max((r["id"] for r in rem_list), default=0); db.save("reminders", {"list": rem_list, "counter": max_id}); restored.append(f"⏰ {len(rem_list)} reminders")
        except Exception as e: log.warning(f"Reminders restore failed: {e}")
        if restored: log.info(f"✅ Restored: {' | '.join(restored)}")
        else: log.info("📋 Nothing to restore")
        return True

google_sheets = GoogleSheetsBackup()

def restore_all_from_sheets():
    if not google_sheets.sheet: return
    log.info("🔄 Loading all data from Google Sheets..."); google_sheets.restore_from_sheets()
    tasks.store.data = db.load("tasks", {"list": [], "counter": 0})
    reminders.store.data = db.load("reminders", {"list": [], "counter": 0})
    diary.store.data = db.load("diary", {"entries": {}})
    expenses.store.data = db.load("expenses", {"list": [], "budget": {}, "counter": 0})
    habits.store.data = db.load("habits", {"list": [], "logs": {}, "counter": 0})
    memory.store.data = db.load("memory", {"facts": [], "prefs": {}, "important_notes": [], "dates": {}})
    goals.store.data = db.load("goals", {"list": [], "counter": 0})
    bills.store.data = db.load("bills", {"list": [], "counter": 0})
    calendar.store.data = db.load("calendar", {"events": [], "counter": 0})
    # Fix counters
    for store_obj, key in [(tasks, "counter"), (reminders, "counter"), (habits, "counter"), (goals, "counter"), (bills, "counter"), (calendar, "counter")]:
        if store_obj.store.data.get("list"): store_obj.store.data[key] = max((item.get("id",0) for item in store_obj.store.data["list"]), default=0)
    log.info("✅ All stores reloaded!")

restore_all_from_sheets()

# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════════
def build_system_prompt():
    now_label = time_label(); current_time = now_str()
    tp = tasks.today_pending(); yd = tasks.done_on(yesterday_str())
    hd, hp = habits.today_status(); ag = goals.active()
    td_d = diary.get(today_str()); exp_t = expenses.today_total(); exp_m = expenses.month_total()
    bl = expenses.budget_left(); water_today = water.today_total(); water_goal = water.goal()
    due_b = bills.due_soon(3); cal_today = calendar.today_events()
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

📋 AAJ KE TASKS ({len(tp)}):\n{tasks_s}

✅ KAL KYA KIYA ({len(yd)}):\n{yd_s}

💪 HABITS: Done: {h_done} | Baaki: {h_pend}

📖 DIARY (aaj):\n{diary_s}

💰 KHARCHA: Aaj ₹{exp_t} | Mahina ₹{exp_m} {budget_s}

🎯 GOALS ({len(ag)}):\n{goals_s}

💧 PAANI: {water_today}ml/{water_goal}ml ({water_pct}%)

📅 AAJ KE EVENTS:\n{cal_s}

💳 BILLS DUE:\n{bills_s}

🧠 YAADDASHT:\n{memory.context()}

RULES:
- Dost ki tarah baat kar — "As an AI" kabhi mat bol
- Hindi/Hinglish mein jawab de, SHORT (2-4 lines)
- TIME PUCHNE PE EXACT TIME BATANA jo upar likha hai
- Jo yaad hai naturally use kar
"""

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
REMIND — {{"time":"HH:MM","text":"...","repeat":"once"}} (Only if user EXPLICITLY asks)
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
CHAT — {{}} (default for greetings, questions)
"""

def _regex_fallback(user_msg):
    lower = user_msg.lower().strip(); now = now_ist()
    remind_explicit = ["remind me", "set reminder", "set alarm", "yaad dila", "alarm laga", "reminder set", "notify me", "yaad dilana"]
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
        if m: time_str = (now + timedelta(minutes=int(m.group(1)))).strftime("%H:%M")
        if not time_str:
            m = _re.search(r'(\d+)\s*(?:ghante|ghanta|hour|hr)', lower)
            if m: time_str = (now + timedelta(hours=int(m.group(1)))).strftime("%H:%M")
        if not time_str:
            m = _re.search(r'(\d{1,2}):(\d{2})', lower)
            if m: h, mn = int(m.group(1)), int(m.group(2))
                if 0 <= h <= 23 and 0 <= mn <= 59: time_str = f"{h:02d}:{mn:02d}"
        if not time_str:
            m = _re.search(r'(\d{1,2})\s*(?:baje|baj)', lower)
            if m: h = int(m.group(1))
                if 'raat' in lower or 'sham' in lower: h = h + 12 if h < 12 else h
                elif 'subah' in lower: h = h if h < 12 else h - 12
                else: h = h + 12 if 1 <= h <= 6 else h
                time_str = f"{h:02d}:00"
        if time_str:
            text = user_msg
            text = _re.sub(r'\d+\s*(?:minute|min|mins|ghante|ghanta|hour|hr)', '', text, flags=_re.I)
            text = _re.sub(r'\d{1,2}(?::\d{2})?\s*(?:baje|baj)?', '', text, flags=_re.I)
            for kw in remind_explicit + ["baad", "mein", "ke liye"]: text = text.replace(kw, '')
            text = ' '.join(text.split())
            if not text or len(text) < 2: text = "⏰ Reminder!"
            return {"action": "REMIND", "params": {"time": time_str, "text": text[:100], "repeat": "daily" if "daily" in lower or "roz" in lower else "weekly" if "weekly" in lower else "once"}, "reply": ""}
    
    if any(t in lower for t in ["task add", "add task", "karna hai", "kaam add", "new task"]):
        title = _re.sub(r'(task add|add task|karna hai|kaam add|new task)', '', user_msg, flags=_re.I).strip()
        if title: return {"action": "ADD_TASK", "params": {"title": title[:80], "priority": "medium"}, "reply": ""}
    
    if any(w in lower for w in ["kharcha add", "add expense", "rs ", "rupaye kharch", "spent", "kharch kiya"]):
        m = _re.search(r'(\d+)', lower); amount = float(m.group(1)) if m else 0
        if amount > 0: return {"action": "ADD_EXPENSE", "params": {"amount": amount, "desc": user_msg[:60], "category": "general"}, "reply": ""}
    
    if any(w in lower for w in ["diary likh", "journal entry", "diary add"]):
        return {"action": "ADD_DIARY", "params": {"text": user_msg[:200], "mood": "📝"}, "reply": ""}
    
    return {"action": "CHAT", "params": {}, "reply": ""}

def call_gemini_action(user_msg, now_label, today_label):
    now = now_ist(); two_min = (now + timedelta(minutes=2)).strftime("%H:%M"); current_time = now.strftime("%H:%M")
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
                if json_match: raw = json_match.group(0)
                parsed = json.loads(raw); log.info(f"✅ Action: {parsed.get('action')} via {model}"); return parsed
        except Exception as e: log.warning(f"Action fail ({model}): {e}"); continue
    return _regex_fallback(user_msg)

async def execute_action(action_data, chat_id, user_msg):
    action = action_data.get("action", "CHAT"); params = action_data.get("params", {}); now = now_ist()
    if action == "REMIND":
        time_str = params.get("time", ""); text = params.get("text", "⏰ Reminder!"); repeat = params.get("repeat", "once")
        if not time_str or not _re.match(r'^\d{2}:\d{2}$', time_str): return f"⏰ Time format galat! Abhi *{now.strftime('%H:%M')}* hue hain."
        r = reminders.add(chat_id, text, time_str, repeat)
        rl = {"once": "Ek baar", "daily": "Roz 🔁", "weekly": "Har hafte 📅"}.get(repeat, repeat)
        return f"✅ Reminder set! ⏰ *{time_str}* — {text}\n{rl}\n🆔 `#{r['id']}`"
    elif action == "ADD_TASK":
        title = params.get("title", user_msg[:80]); priority = params.get("priority", "medium")
        t = tasks.add(title, priority); icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        return f"✅ Task: {icons.get(priority,'🟡')} *{t['title']}*\n🆔 `#{t['id']}`"
    elif action == "ADD_EXPENSE":
        amount = float(params.get("amount", 0)); desc = params.get("desc", "Kharcha")
        if amount <= 0: return "💰 Amount batao?"
        expenses.add(amount, desc); return f"✅ ₹{amount:.0f} — {desc}\n📊 Aaj: ₹{expenses.today_total():.0f}"
    elif action == "ADD_DIARY": diary.add(params.get("text", user_msg[:100])); return f"📖 Diary saved! 🕐 {now_str()}"
    elif action == "ADD_MEMORY": memory.add_fact(params.get("fact", user_msg[:200])); return f"🧠 Yaad kar liya! ✅"
    elif action == "ADD_HABIT": h = habits.add(params.get("name", user_msg[:50])); return f"💪 Habit: {h['emoji']} *{h['name']}*"
    elif action == "COMPLETE_TASK":
        hint = params.get("title_hint", "").lower(); pending = tasks.pending(); matched = None
        if hint.isdigit(): matched = next((t for t in pending if t["id"] == int(hint)), None)
        if not matched and hint: matched = next((t for t in pending if hint in t["title"].lower()), None)
        if not matched and pending: matched = pending[-1]
        if matched: tasks.complete(matched["id"]); return f"✅ *{matched['title']}* — done! 🎉"
        return "❓ Kaunsa task?"
    elif action == "SHOW_TASKS":
        pending = tasks.today_pending()
        if not pending: return "🎉 No pending tasks!"
        txt = f"📋 *PENDING ({len(pending)})*\n\n"
        for t in pending[:8]: txt += f"{'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} *#{t['id']}* {t['title']}\n"
        return txt
    elif action == "SHOW_ALL_TASKS":
        all_t = tasks.all_tasks()
        if not all_t: return "📋 No tasks!"
        p = tasks.pending(); c = tasks.completed_tasks()
        txt = f"📋 *ALL ({len(all_t)})*\n⏳{len(p)} pending | ✅{len(c)} done"
        return txt
    elif action == "SHOW_COMPLETED_TASKS":
        c = tasks.completed_tasks()
        if not c: return "✅ No completed tasks yet!"
        return f"✅ *COMPLETED ({len(c)})*\n\n" + "".join(f"✓ #{t['id']} {t['title']}\n" for t in c[-10:])
    elif action == "SHOW_REMINDERS":
        active = reminders.all_active()
        if not active: return f"⏰ No reminders!"
        txt = f"⏰ *REMINDERS ({len(active)})*\n\n"
        for r in active: txt += f"*#{r['id']}* `{r['time']}` — {r['text']}\n"
        return txt
    else:
        chat_hist.add("user", user_msg)
        reply = call_gemini(build_system_prompt() + "\n\nUser: " + user_msg + "\n\nShort Hindi reply:")
        if not reply: reply = call_huggingface(build_system_prompt() + "\n\nUser: " + user_msg + "\n\nShort Hindi reply:")
        if not reply: reply = smart_fallback(user_msg)
        chat_hist.add("assistant", reply); return reply

async def ai_chat(user_msg, chat_id=None):
    now_label = time_label(); today_label = today_str()
    if chat_id: action_data = call_gemini_action(user_msg, now_label, today_label); return await execute_action(action_data, chat_id, user_msg)
    else: return get_ai_reply(user_msg)

# ═══════════════════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════════════════
def back_kb(): return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]])

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Briefing", callback_data="briefing"), InlineKeyboardButton("📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("💪 Habits", callback_data="habits"), InlineKeyboardButton("📖 Write Diary", callback_data="diary_write")],
        [InlineKeyboardButton("🎯 Goals", callback_data="goals"), InlineKeyboardButton("💰 Kharcha", callback_data="expenses")],
        [InlineKeyboardButton("📰 News", callback_data="news_menu"), InlineKeyboardButton("📝 Notes", callback_data="notes")],
        [InlineKeyboardButton("💧 Water", callback_data="water_status"), InlineKeyboardButton("💳 Bills", callback_data="bills_menu")],
        [InlineKeyboardButton("📅 Calendar", callback_data="cal_menu"), InlineKeyboardButton("📊 Weekly", callback_data="weekly_report")],
        [InlineKeyboardButton("🧠 Insight", callback_data="jarvis_insight"), InlineKeyboardButton("🔮 Predict", callback_data="jarvis_predict")],
        [InlineKeyboardButton("⚡ Decision", callback_data="jarvis_decision"), InlineKeyboardButton("🧹 Clear Chat", callback_data="clear_chat")],
        [InlineKeyboardButton("📤 Backup", callback_data="backup_now"), InlineKeyboardButton("📅 Report", callback_data="report_menu")],
    ])

def news_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇳 India", callback_data="news_India"), InlineKeyboardButton("💻 Tech", callback_data="news_Technology")],
        [InlineKeyboardButton("💼 Business", callback_data="news_Business"), InlineKeyboardButton("🌍 World", callback_data="news_World")],
        [InlineKeyboardButton("🏏 Sports", callback_data="news_Sports"), InlineKeyboardButton("🏠 Back", callback_data="menu")],
    ])

# ═══════════════════════════════════════════════════════════════════
# COMMAND HANDLERS (All previous commands preserved)
# ═══════════════════════════════════════════════════════════════════
async def cmd_start(update, ctx):
    n = now_ist(); name = update.effective_user.first_name or "Dost"
    db_status = "✅ Google Sheets connected!" if google_sheets.sheet else "⚠️ Sheets not connected!"
    await update.message.reply_text(f"🕌 *Assalamualaikum {name}!*\n\n⏰ {n.strftime('%I:%M %p')} IST | 📅 {n.strftime('%d %b %Y')}\n\n💾 *{db_status}*\n\n🧠 *New:* `/insight` `/predict` `/decide`\n_Seedha type karo ya /help_ 👇", parse_mode="Markdown", reply_markup=main_kb())

async def cmd_hello(update, ctx):
    name = update.effective_user.first_name or "Dost"; n = now_ist()
    await update.message.reply_text(f"🕌 *Assalamualaikum {name}!* 😊\n\n⏰ {n.strftime('%I:%M %p')} IST\n\nMain ready hoon! 🧠 `/insight` try karo.", parse_mode="Markdown", reply_markup=main_kb())

async def cmd_help(update, ctx):
    await update.message.reply_text("📋 *COMMANDS*\n\n**CORE:** `/task` `/done` `/deltask` | `/habit` `/hdone` | `/kharcha` `/budget` | `/remind` `/reminders` | `/diary` | `/goal` | `/water` | `/bill` | `/cal` | `/note` | `/remember`\n\n**🧠 JARVIS:** `/insight` | `/predict` | `/decide`\n\n**📊 REPORTS:** `/briefing` `/weekly` `/report YYYY-MM-DD`\n\n_Seedha type karo — AI jawab dega!_", parse_mode="Markdown")

# 🆕 JARVIS COMMANDS
async def cmd_insight(update, ctx):
    """🧠 Show complete insight snapshot"""
    txt = build_jarvis_context()
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_predict(update, ctx):
    """🔮 Show predictions/warnings"""
    warnings = prediction_engine()
    txt = "🔮 *PREDICTION ENGINE*\n{'═'*25}\n\n" + "\n\n".join(warnings)
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_decide(update, ctx):
    """⚡ Show decision engine recommendations"""
    actions = decision_engine()
    if not actions: await update.message.reply_text("✅ *All clear!* No actions needed.", parse_mode="Markdown"); return
    txt = "⚡ *DECISION ENGINE*\n{'═'*25}\n\n"
    for a in actions: txt += f"**{a['msg']}**\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

# All existing command handlers (task, done, deltask, habit, hdone, etc.) remain unchanged
# ... (keeping all previous commands exactly as they were)

async def cmd_task(update, ctx):
    if not ctx.args: await update.message.reply_text("📋 `/task Kaam [high/low]`"); return
    args = " ".join(ctx.args); priority = "medium"
    if args.endswith(" high"): priority = "high"; args = args[:-5].strip()
    elif args.endswith(" low"): priority = "low"; args = args[:-4].strip()
    t = tasks.add(args, priority); e = "🔴" if priority=="high" else "🟡" if priority=="medium" else "🟢"
    await update.message.reply_text(f"✅ {e} *{t['title']}*\n🆔 `#{t['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_done(update, ctx):
    if not ctx.args:
        pending = tasks.pending()
        if pending: msg = "📋 *Pending:*\n" + "\n".join(f"`/done {t['id']}` → {t['title']}" for t in pending[:10]); await update.message.reply_text(msg, parse_mode="Markdown")
        else: await update.message.reply_text("🎉 No pending tasks!")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t: await update.message.reply_text(f"🎉 Done: {t['title']}", parse_mode="Markdown")
        else: await update.message.reply_text("❌ Not found!")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid ID!")

async def cmd_deltask(update, ctx):
    if not ctx.args: await update.message.reply_text("`/deltask <id>`"); return
    try:
        if tasks.delete(int(ctx.args[0])): await update.message.reply_text("🗑 Deleted!")
        else: await update.message.reply_text("❌ Not found")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid ID")

async def cmd_diary(update, ctx):
    args = ctx.args
    if args and args[0] not in ("date", "all", "week"):
        text = " ".join(args); diary.add(text, mood="📝")
        await update.message.reply_text(f"📖 *Diary saved!* 🕐 {now_str()}\n\n_{text[:120]}_", parse_mode="Markdown")
        await auto_backup_to_sheets(); return ConversationHandler.END
    if args and args[0] == "date" and len(args) >= 2: ctx.user_data["diary_view"] = ("date", args[1])
    elif args and args[0] == "all": ctx.user_data["diary_view"] = ("all", None)
    elif args and args[0] == "week": ctx.user_data["diary_view"] = ("week", None)
    else: ctx.user_data["diary_view"] = ("today", None)
    await update.message.reply_text("🔐 *Password Enter Karo:*", parse_mode="Markdown"); return DIARY_AWAIT_PASS

async def diary_password_check(update, ctx):
    if update.message.text.strip() != DIARY_PASSWORD: await update.message.reply_text("❌ Galat password!"); return ConversationHandler.END
    view_type, view_arg = ctx.user_data.get("diary_view", ("today", None))
    await _show_diary(update, view_type, view_arg); return ConversationHandler.END

async def diary_conv_cancel(update, ctx):
    try:
        if update.message: await update.message.reply_text("⏱ Expired.")
    except: pass
    return ConversationHandler.END

async def _show_diary(update, view_type, view_arg):
    if view_type == "today": entries = diary.get(today_str()); title = f"📖 *Aaj Ki Diary*"; all_entries = {today_str(): entries} if entries else {}
    elif view_type == "date": d = view_arg or today_str(); entries = diary.get(d); title = f"📖 *{d}*"; all_entries = {d: entries} if entries else {}
    elif view_type == "week":
        n = now_ist(); all_entries = {}
        for i in range(7): d = (n - timedelta(days=i)).strftime("%Y-%m-%d"); e = diary.get(d)
            if e: all_entries[d] = e
        title = "📖 *Is Hafte Ki Diary*"
    elif view_type == "all": all_entries = diary.get_all_entries(); title = f"📖 *Puri Diary*"
    else: all_entries = {}; title = "📖 *Diary*"
    if not all_entries: await update.message.reply_text(f"{title}\n\n_Koi entry nahi._", parse_mode="Markdown"); return
    chunks = []; current_chunk = f"{title}\n{'━'*28}\n\n"
    for date_key in sorted(all_entries.keys(), reverse=True):
        entries = all_entries[date_key]; date_block = f"📅 *{date_key}*\n"
        for e in entries: date_block += f"{e.get('mood','📝')} `{e.get('time','')}` — {e.get('text','')}\n"
        date_block += "\n"
        if len(current_chunk) + len(date_block) > 3800: chunks.append(current_chunk); current_chunk = date_block
        else: current_chunk += date_block
    if current_chunk.strip(): chunks.append(current_chunk)
    for i, chunk in enumerate(chunks):
        kb = back_kb() if i == len(chunks)-1 else None
        try: await update.message.reply_text(chunk, parse_mode="Markdown", reply_markup=kb)
        except: await update.message.reply_text(chunk, reply_markup=kb)

async def cmd_habit(update, ctx):
    if not ctx.args: await update.message.reply_text("💪 `/habit Naam`"); return
    h = habits.add(" ".join(ctx.args)); await update.message.reply_text(f"💪 {h['emoji']} *{h['name']}*\n`/hdone {h['id']}`", parse_mode="Markdown"); await auto_backup_to_sheets()

async def cmd_hdone(update, ctx):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending: msg = "💪 *Pending:*\n" + "\n".join(f"`/hdone {h['id']}` → {h['name']}" for h in pending); await update.message.reply_text(msg, parse_mode="Markdown")
        else: await update.message.reply_text("🎊 Sab done!")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        if ok: await update.message.reply_text(f"💪 Done! 🔥 {streak}d", parse_mode="Markdown")
        else: await update.message.reply_text("✅ Already done!")
        await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid ID!")

async def cmd_kharcha(update, ctx):
    if not ctx.args or len(ctx.args) < 2: await update.message.reply_text("💰 `/kharcha 100 Chai`"); return
    try:
        amount = float(ctx.args[0]); desc = " ".join(ctx.args[1:]); expenses.add(amount, desc)
        await update.message.reply_text(f"💰 ₹{amount:.0f} — {desc}\n📊 Aaj: ₹{expenses.today_total():.0f}", parse_mode="Markdown"); await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Format: `/kharcha 100 Chai`")

async def cmd_budget(update, ctx):
    if not ctx.args: await update.message.reply_text("💳 `/budget 5000`"); return
    try: expenses.set_budget(float(ctx.args[0])); await update.message.reply_text(f"💳 Budget: ₹{ctx.args[0]}"); await auto_backup_to_sheets()
    except: pass

async def cmd_goal(update, ctx):
    if not ctx.args:
        active = goals.active()
        if active: msg = "🎯 *ACTIVE*\n\n" + "\n".join(f"#{g['id']} {g['title']} ({g['progress']}%)" for g in active); await update.message.reply_text(msg, parse_mode="Markdown")
        else: await update.message.reply_text("🎯 `/goal Learn Python`")
        return
    g = goals.add(" ".join(ctx.args)); await update.message.reply_text(f"🎯 Goal set: #{g['id']} {g['title']}"); await auto_backup_to_sheets()

async def cmd_remember(update, ctx):
    if not ctx.args: await update.message.reply_text("🧠 `/remember Text`"); return
    memory.add_fact(" ".join(ctx.args)); await update.message.reply_text("🧠 Yaad kar liya! ✅"); await auto_backup_to_sheets()

async def cmd_recall(update, ctx):
    facts = memory.get_all_facts()
    if not facts: await update.message.reply_text("🧠 Kuch yaad nahi."); return
    txt = "🧠 *YAADDASHT*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-10:]); await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_note(update, ctx):
    if not ctx.args: await update.message.reply_text("📝 `/note Text`"); return
    n = notes.add(" ".join(ctx.args)); await update.message.reply_text(f"📝 Note #{n['id']} saved!"); await auto_backup_to_sheets()

async def cmd_briefing(update, ctx):
    tp = tasks.today_pending(); hd, hp = habits.today_status(); n = now_ist()
    txt = f"🌅 *BRIEFING*\n⏰ {n.strftime('%I:%M %p')} | 📅 {n.strftime('%d %b')}\n\n"
    if tp: txt += f"📋 Pending ({len(tp)}): " + ", ".join(t['title'] for t in tp[:5])
    else: txt += "🎉 No pending!"
    txt += f"\n💰 Aaj: ₹{expenses.today_total():.0f} | 💧 {water.today_total()}ml"; await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_weekly(update, ctx):
    n = now_ist(); week_start = n.date() - timedelta(days=n.weekday())
    task_week = tasks.get_weekly_summary(); total_done = sum(v["done"] for v in task_week.values()); total_created = sum(v["created"] for v in task_week.values())
    msg = f"📊 *WEEKLY*\n📅 {week_start.strftime('%d %b')} - {n.strftime('%d %b')}\n\n📋 Tasks: ✅{total_done} | ➕{total_created}\n💰 Month: ₹{expenses.month_total():.0f}"; await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_report(update, ctx):
    if not ctx.args: await update.message.reply_text("`/report YYYY-MM-DD`"); return
    target_date = ctx.args[0]
    try: datetime.strptime(target_date, "%Y-%m-%d")
    except: await update.message.reply_text("❌ Invalid date!"); return
    tasks_done = tasks.done_on(target_date); exp = expenses.get_by_date(target_date); exp_total = sum(e["amount"] for e in exp)
    diary_e = diary.get(target_date); msg = f"📋 *{target_date}*\n✅ Tasks: {len(tasks_done)}\n💰 Expenses: ₹{exp_total:.0f}\n📖 Diary: {len(diary_e)} entries"; await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_news(update, ctx): await update.message.reply_text("📰 *Category:*", parse_mode="Markdown", reply_markup=news_kb())

async def cmd_clear(update, ctx):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Clear", callback_data="confirm_clear_chat"), InlineKeyboardButton("❌ Cancel", callback_data="menu")]])
    await update.message.reply_text(f"🧹 Clear chat?\n✅ Data SAFE", parse_mode="Markdown", reply_markup=kb)

async def cmd_remind(update, ctx):
    now = now_ist()
    if not ctx.args: await update.message.reply_text(f"⏰ `/remind 2m Test` | `/remind 15:30 Meeting`"); return
    time_arg = ctx.args[0].lower(); rest = ctx.args[1:]; repeat = "once"
    if rest and rest[-1].lower() in ["daily","weekly"]: repeat = rest[-1].lower(); rest = rest[:-1]
    text = " ".join(rest) if rest else "⏰ Reminder!"
    if time_arg.endswith("m") and time_arg[:-1].isdigit(): remind_at = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif time_arg.endswith("h") and time_arg[:-1].isdigit(): remind_at = (now + timedelta(hours=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        parts = time_arg.split(":")
        if len(parts)==2 and parts[0].isdigit() and parts[1].isdigit():
            h,m = int(parts[0]),int(parts[1])
            if 0<=h<=23 and 0<=m<=59: remind_at = f"{h:02d}:{m:02d}"
            else: await update.message.reply_text("❌ Invalid time!"); return
        else: await update.message.reply_text("❌ Format: `/remind 15:30`"); return
    else: await update.message.reply_text("❌ Format: `/remind 2m` or `/remind 15:30`"); return
    r = reminders.add(update.effective_chat.id, text, remind_at, repeat)
    await update.message.reply_text(f"✅ Reminder set! ⏰ {remind_at} — {text}\n🆔 `#{r['id']}`", parse_mode="Markdown"); await auto_backup_to_sheets()

async def cmd_reminders_list(update, ctx):
    active = reminders.all_active()
    if not active: await update.message.reply_text("⏰ No reminders!"); return
    txt = f"⏰ *REMINDERS ({len(active)})*\n\n"
    for r in active: txt += f"*#{r['id']}* `{r['time']}` — {r['text']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_water(update, ctx):
    ml=250
    if ctx.args:
        try: ml=int(ctx.args[0])
        except: pass
    water.add(ml); total=water.today_total(); goal=water.goal(); pct=min(100,int(total/goal*100)) if goal else 0
    await update.message.reply_text(f"💧 +{ml}ml | {total}ml/{goal}ml ({pct}%)", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("+250ml",callback_data="water_250"),InlineKeyboardButton("+500ml",callback_data="water_500")]]))
    await auto_backup_to_sheets()

async def cmd_bill(update, ctx):
    if not ctx.args or len(ctx.args)<3: await update.message.reply_text("💳 `/bill Naam Amount DueDay`"); return
    try: b=bills.add(ctx.args[0],float(ctx.args[1]),int(ctx.args[2])); await update.message.reply_text(f"✅ Bill: {b['name']} ₹{b['amount']:.0f}"); await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Format: `/bill Name Amount DueDay`")

async def cmd_cal(update, ctx):
    if not ctx.args: await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`"); return
    args_str=" ".join(ctx.args); date_str=None; title=args_str
    m=_re.match(r'^(\d{4}-\d{2}-\d{2})\s+(.*)', args_str)
    if m: date_str=m.group(1); title=m.group(2)
    if not date_str:
        if args_str.lower().startswith("aaj "): date_str=today_str(); title=args_str[4:]
        elif args_str.lower().startswith("kal "): date_str=(now_ist().date()+timedelta(days=1)).isoformat(); title=args_str[4:]
    if not date_str: await update.message.reply_text("❌ `/cal YYYY-MM-DD Event`"); return
    try: date.fromisoformat(date_str); e=calendar.add(title,date_str); await update.message.reply_text(f"📅 Event added: {title} — {date_str}", parse_mode="Markdown"); await auto_backup_to_sheets()
    except: await update.message.reply_text("❌ Invalid date!")

# ═══════════════════════════════════════════════════════════════════
# CALLBACK HANDLER (Updated with Jarvis buttons)
# ═══════════════════════════════════════════════════════════════════
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); d = query.data; message = query.message
    if not message: return
    
    # 🆕 JARVIS CALLBACKS
    if d == "jarvis_insight":
        txt = build_jarvis_context(); await message.edit_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    elif d == "jarvis_predict":
        warnings = prediction_engine(); txt = "🔮 *PREDICTIONS*\n{'═'*25}\n\n" + "\n\n".join(warnings)
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    elif d == "jarvis_decision":
        actions = decision_engine()
        if not actions: await message.edit_text("✅ *All clear!*", parse_mode="Markdown", reply_markup=main_kb())
        else: txt = "⚡ *DECISIONS*\n{'═'*25}\n\n" + "\n\n".join(f"**{a['msg']}**" for a in actions); await message.edit_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    
    elif d == "menu": await message.edit_text("🏠 *Main Menu*", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "briefing":
        try: txt = await _build_briefing_text(); await message.edit_text(txt, parse_mode="Markdown", reply_markup=main_kb())
        except: await message.edit_text("❌ Error", reply_markup=back_kb())
    elif d == "tasks":
        pending = tasks.pending()
        if not pending: await message.edit_text("🎉 No pending!", reply_markup=back_kb()); return
        txt = "📋 *PENDING*\n\n"
        for t in pending[:10]: icon = "🔴" if t.get('priority')=='high' else "🟡" if t.get('priority')=='medium' else "🟢"; txt += f"{icon} *#{t['id']}* {t['title']}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "expenses":
        txt = f"💰 *EXPENSES*\n📅 Today: ₹{expenses.today_total():.0f}\n📆 Month: ₹{expenses.month_total():.0f}"
        bl = expenses.budget_left()
        if bl is not None: txt += f"\n💳 Left: ₹{bl:.0f}"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "water_status":
        total=water.today_total(); goal=water.goal(); pct=min(100,int(total/goal*100)) if goal else 0
        await message.edit_text(f"💧 {total}ml / {goal}ml ({pct}%)", parse_mode="Markdown")
    elif d.startswith("water_"): water.add(int(d.split("_")[1])); total=water.today_total(); await message.edit_text(f"💧 +{d.split('_')[1]}ml | {total}ml", reply_markup=back_kb()); await auto_backup_to_sheets()
    elif d == "bills_menu":
        all_b=bills.all_active()
        if not all_b: await message.edit_text("💳 No bills!", reply_markup=back_kb()); return
        txt="💳 *BILLS*\n\n"
        for b in all_b: status="✅" if bills.is_paid_this_month(b["id"]) else "⏳"; txt+=f"{status} *{b['name']}* — ₹{b['amount']:.0f}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "cal_menu":
        upcoming=calendar.upcoming(30)
        if not upcoming: await message.edit_text("📅 No events!", reply_markup=back_kb()); return
        txt="📅 *UPCOMING*\n\n"
        for e in upcoming[:15]: flag="🔴" if e["date"]==today_str() else "📆"; txt+=f"{flag} {e['date']} — {e['title']}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "news_menu": await message.edit_text("📰 *Category:*", parse_mode="Markdown", reply_markup=news_kb())
    elif d.startswith("news_"):
        category = d.split("_",1)[1]; items = news_store.get(category,5)
        if not items: await message.edit_text("📰 Unavailable.", reply_markup=back_kb()); return
        txt = f"📰 *{category.upper()}*\n\n" + "\n".join(f"• {item['title']}" for item in items)
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "backup_now":
        await message.edit_text("📤 Backing up..."); result=google_sheets.full_sync(); await message.edit_text(result, reply_markup=main_kb())
    elif d == "clear_chat":
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Clear",callback_data="confirm_clear_chat"),InlineKeyboardButton("❌ Cancel",callback_data="menu")]])
        await message.edit_text(f"🧹 Clear chat?\n✅ Data SAFE", parse_mode="Markdown", reply_markup=kb)
    elif d == "confirm_clear_chat":
        count=chat_hist.clear(); await message.edit_text(f"🧹 Cleared {count}! ✅", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "diary_write":
        ctx.user_data["awaiting_diary_entry"] = True
        await message.edit_text("📖 *Diary Entry Likho:*\n\n_Type karo — save hoga!_", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="menu")]]))
    elif d.startswith("done_"):
        tid=int(d.split("_")[1]); t=tasks.complete(tid)
        if t: await message.edit_text(f"🎉 Done: {t['title']}", parse_mode="Markdown", reply_markup=back_kb())
        else: await message.edit_text("❌ Not found!", reply_markup=back_kb())
        await auto_backup_to_sheets()
    elif d.startswith("habit_"):
        hid=int(d.split("_")[1]); ok,streak=habits.log(hid)
        h=next((x for x in habits.all() if x["id"]==hid),None)
        if ok and h: await message.edit_text(f"💪 {h['emoji']}{h['name']} — 🔥{streak}d", parse_mode="Markdown", reply_markup=back_kb())
        else: await message.edit_text("✅ Already done!", reply_markup=back_kb())
        await auto_backup_to_sheets()
    elif d.startswith("remind_done_"):
        rid=int(d.split("_")[2]); reminders.mark_fired(rid)
        await message.edit_text("✅ Done!", reply_markup=back_kb()); await auto_backup_to_sheets()
        try: await message.delete()
        except: pass
    elif d.startswith("remind_snooze_"):
        rid=int(d.split("_")[2]); snooze=(now_ist()+timedelta(minutes=10)).strftime("%H:%M")
        r_list=[r for r in reminders.get_all() if r["id"]==rid]
        if r_list: reminders.add(message.chat_id, r_list[0]["text"], snooze, "once"); reminders.mark_fired(rid)
        await message.edit_text(f"😴 Snoozed to {snooze}", reply_markup=back_kb()); await auto_backup_to_sheets()
        try: await message.delete()
        except: pass

# ═══════════════════════════════════════════════════════════════════
# IMPROVED MESSAGE HANDLER (with auto-command detection)
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_msg = update.message.text.strip()
    if user_msg.startswith('/'): return

    if ctx.user_data.get("awaiting_diary_entry"):
        ctx.user_data.pop("awaiting_diary_entry", None)
        diary.add(user_msg, mood="📝")
        await update.message.reply_text(f"📖 *Diary saved!* 🕐 {now_str()}\n\n_{user_msg[:150]}_", parse_mode="Markdown", reply_markup=main_kb())
        await auto_backup_to_sheets(); return

    ctx.user_data.pop("diary_view", None); ctx.user_data.pop("diary_from_callback", None)

    lower_msg = user_msg.lower().strip()
    
    # 🆕 SMART AUTO-COMMANDS (Jarvis feature)
    auto_result = auto_command_detect(user_msg)
    if auto_result:
        await update.message.reply_text(auto_result, parse_mode="Markdown")
        await auto_backup_to_sheets()
        return
    
    # Quick greetings
    greetings = ["hello", "hi", "hey", "assalam", "namaste", "hola", "yo", "sup", "heya"]
    if any(lower_msg == g or lower_msg.startswith(g + " ") for g in greetings):
        name = update.effective_user.first_name or "Dost"; n = now_ist()
        replies = [f"🕌 *Assalamualaikum {name}!* 😊\n\n⏰ {n.strftime('%I:%M %p')} IST", f"😊 *Hey {name}!* 👋\n\nBatao kya help chahiye?", f"👋 *Namaste {name}!*\n\nMain yahan hoon!"]
        await update.message.reply_text(random.choice(replies), parse_mode="Markdown", reply_markup=main_kb()); return
    
    how_are = ["kaise ho", "how are", "kya haal"]
    if any(h in lower_msg for h in how_are):
        name = update.effective_user.first_name or "Dost"
        await update.message.reply_text(f"😊 *Main badiya hoon, {name}!* 💪\n\nAap sunao?", parse_mode="Markdown"); return
    
    thanks = ["thank", "shukriya", "dhanyavad"]
    if any(t in lower_msg for t in thanks): await update.message.reply_text("🤗 *Welcome!* 😊", parse_mode="Markdown"); return
    
    bye = ["bye", "allah hafiz", "good night", "fir milenge"]
    if any(b in lower_msg for b in bye): await update.message.reply_text("🌙 *Allah Hafiz!* 🤗", parse_mode="Markdown"); return

    # Normal AI chat
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ai_chat(user_msg, update.effective_chat.id)
    try: await update.message.reply_text(reply, parse_mode="Markdown")
    except: await update.message.reply_text(reply)

def auto_command_detect(msg):
    """🆕 Smart auto-command detection from natural language"""
    lower = msg.lower().strip()
    
    # Auto add task
    if any(w in lower for w in ["add task", "task add", "new task", "karna hai", "kaam hai"]):
        title = _re.sub(r'(add task|task add|new task|karna hai|kaam hai)', '', msg, flags=_re.I).strip()
        if title:
            t = tasks.add(title[:80])
            return f"✅ Task added: *{t['title']}*\n🆔 `#{t['id']}`"
    
    # Auto add expense (Rs detection)
    if "rs" in lower or "₹" in lower or "rupaye" in lower:
        try:
            numbers = _re.findall(r'\d+', msg)
            if numbers:
                amt = float(numbers[0])
                desc = _re.sub(r'(rs|₹|rupaye|\d+)', '', msg, flags=_re.I).strip()
                if not desc: desc = "Kharcha"
                expenses.add(amt, desc[:60])
                return f"💰 ₹{amt:.0f} — {desc}\n📊 Aaj total: ₹{expenses.today_total():.0f}"
        except: pass
    
    # Auto add note
    if lower.startswith("note ") or "note add" in lower or "note:" in lower:
        text = _re.sub(r'(note|note add|note:)', '', msg, flags=_re.I).strip()
        if text:
            n = notes.add(text[:100])
            return f"📝 Note #{n['id']} saved!"
    
    # Auto add diary
    if "diary" in lower and ("likh" in lower or "add" in lower or "save" in lower):
        text = _re.sub(r'(diary|likh|add|save)', '', msg, flags=_re.I).strip()
        if text:
            diary.add(text[:200])
            return f"📖 Diary saved! 🕐 {now_str()}"
    
    # Auto add memory
    if any(w in lower for w in ["yaad rakh", "remember this", "yaad rakho"]):
        text = _re.sub(r'(yaad rakh|remember this|yaad rakho)', '', msg, flags=_re.I).strip()
        if text:
            memory.add_fact(text[:200])
            return f"🧠 Yaad kar liya! ✅"
    
    # Auto complete task
    if any(w in lower for w in ["task done", "complete task", "task complete", "done task"]):
        pending = tasks.pending()
        if pending:
            # Try to find by number or name
            for t in pending:
                if t['title'].lower() in lower:
                    tasks.complete(t['id'])
                    return f"✅ *{t['title']}* — done! 🎉"
            # Complete most recent if none matched
            if len(pending) == 1:
                tasks.complete(pending[0]['id'])
                return f"✅ *{pending[0]['title']}* — done! 🎉"
    
    # Auto check insight
    if any(w in lower for w in ["insight", "status", "summary", "kya chal raha", "report"]):
        return build_jarvis_context()
    
    return None

# ═══════════════════════════════════════════════════════════════════
# BACKGROUND JOBS
# ═══════════════════════════════════════════════════════════════════
async def reminder_job(context):
    now = now_ist(); now_time = now.strftime("%H:%M")
    if now_time in ("00:00", "00:01"): reminders.reset_daily(); return
    due = reminders.due_now()
    for r in due:
        try:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Done", callback_data=f"remind_done_{r['id']}"),
                InlineKeyboardButton("⏰ Snooze", callback_data=f"remind_snooze_{r['id']}")]])
            await context.bot.send_message(chat_id=r["chat_id"],
                text=f"🚨🔔 *ALARM!*\n{'═'*25}\n⏰ *{r['time']}*\n📢 *{r['text'].upper()}*",
                parse_mode="Markdown", replay_markup=kb)
            reminders.mark_fired(r["id"]); await asyncio.sleep(1)
        except Exception as e: log.error(f"❌ FAILED #{r['id']}: {e}")

# 🆕 JARVIS PROACTIVE JOB
async def jarvis_proactive_job(context):
    """Proactive monitoring - checks every 30 minutes"""
    try:
        if not ADMIN_CHAT_ID: return
        chat_id = int(ADMIN_CHAT_ID)
        
        pending = tasks.pending()
        if len(pending) > 5:
            high_priority = [t for t in pending if t.get("priority") == "high"]
            msg = f"⚠️ *Task Alert!*\n{pending} pending tasks"
            if high_priority: msg += f"\n🔴 {len(high_priority)} high-priority!"
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
        
        bl = expenses.budget_left()
        if bl is not None and bl < 0:
            await context.bot.send_message(chat_id=chat_id, text="💸 *Budget exceeded!* Stop spending!", parse_mode="Markdown")
    except Exception as e: log.warning(f"Proactive job error: {e}")

# 🆕 JARVIS DECISION JOB
async def jarvis_decision_job(context):
    """Auto decision - checks every 30 minutes"""
    try:
        if not ADMIN_CHAT_ID: return
        chat_id = int(ADMIN_CHAT_ID)
        actions = decision_engine()
        for a in actions:
            await context.bot.send_message(chat_id=chat_id, text=f"⚡ *{a['type'].upper()}*\n{a['msg']}", parse_mode="Markdown")
    except Exception as e: log.warning(f"Decision job error: {e}")

async def failed_retry_job(context):
    unretried = failed_reqs.get_unretried()
    if not unretried: return
    for i, r in enumerate(unretried[:3]):
        try:
            reply = await ai_chat(r["msg"], r["chat_id"])
            if not reply.startswith("⚠️"): failed_reqs.mark_retried(i)
        except: pass

async def bill_due_job(context):
    if now_ist().strftime("%H:%M") != "09:00": return
    due = bills.due_soon(3)
    if not due: return
    chat_ids = set(r["chat_id"] for r in reminders.all_active())
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
        try: await context.bot.send_message(chat_id=cid, text=f"💧 *Paani time!*\n{total}ml/{goal}ml", parse_mode="Markdown")
        except: pass

_last_auto_backup = 0
_BACKUP_THROTTLE_SECS = 30

async def auto_backup_to_sheets():
    global _last_auto_backup
    now_ts = time.time()
    if now_ts - _last_auto_backup < _BACKUP_THROTTLE_SECS: return
    _last_auto_backup = now_ts
    loop = asyncio.get_event_loop(); await loop.run_in_executor(None, google_sheets.full_sync)

async def scheduled_backup_job(context):
    loop = asyncio.get_event_loop(); await loop.run_in_executor(None, google_sheets.full_sync)

async def daily_log_job(context):
    loop = asyncio.get_event_loop(); await loop.run_in_executor(None, google_sheets.save_daily_log)

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    n = now_ist()
    log.info("=" * 55)
    log.info(f"🤖 Bot v15.0 — JARVIS ENHANCED (All Features Intact)")
    log.info(f"⏰ IST: {n.strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"📊 Sheets: {'✅' if google_sheets.sheet else '❌'}")
    log.info(f"🧠 Jarvis: Insight | Predict | Decision | Auto-Commands | Proactive")
    log.info("=" * 55)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    async def post_init(app):
        try:
            chat_id = os.environ.get("ADMIN_CHAT_ID", "")
            if chat_id:
                r_count = len(reminders.store.data.get("list", []))
                t_count = len(tasks.store.data.get("list", []))
                d_count = sum(len(v) for v in diary.store.data.get("entries", {}).values())
                sheets_msg = "✅ Sheets connected" if google_sheets.sheet else "❌ Sheets NOT connected"
                n2 = now_ist()
                await app.bot.send_message(chat_id=int(chat_id),
                    text=f"🤖 *Bot v15.0 JARVIS Started!*\n\n⏰ {n2.strftime('%d %b %Y %I:%M %p')} IST\n"
                         f"📊 {sheets_msg}\n\n"
                         f"📦 Restored: ⏰{r_count} 📋{t_count} 📖{d_count}\n"
                         f"🧠 Jarvis: `/insight` `/predict` `/decide`",
                    parse_mode="Markdown")
        except Exception as e: log.warning(f"Startup notification failed: {e}")

    app.post_init = post_init

    # All commands (previous + new Jarvis commands)
    commands = [
        ("start", cmd_start), ("hello", cmd_hello), ("help", cmd_help),
        # 🆕 Jarvis commands
        ("insight", cmd_insight), ("predict", cmd_predict), ("decide", cmd_decide),
        # Core commands
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("habit", cmd_habit), ("hdone", cmd_hdone),
        ("kharcha", cmd_kharcha), ("budget", cmd_budget),
        ("goal", cmd_goal), ("remember", cmd_remember), ("recall", cmd_recall),
        ("note", cmd_note), ("briefing", cmd_briefing), ("weekly", cmd_weekly),
        ("report", cmd_report), ("news", cmd_news), ("clear", cmd_clear),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list),
        ("water", cmd_water), ("bill", cmd_bill), ("cal", cmd_cal),
    ]

    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))

    diary_conv = ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary)],
        states={DIARY_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)]},
        fallbacks=[CommandHandler("cancel", diary_conv_cancel)],
        per_user=True, per_chat=True, conversation_timeout=30)
    app.add_handler(diary_conv)

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=15)
        app.job_queue.run_repeating(jarvis_proactive_job, interval=1800, first=60)  # 🆕 Every 30 min
        app.job_queue.run_repeating(jarvis_decision_job, interval=1800, first=120) # 🆕 Every 30 min
        app.job_queue.run_repeating(failed_retry_job, interval=300, first=180)
        app.job_queue.run_repeating(bill_due_job, interval=3600, first=300)
        app.job_queue.run_repeating(water_reminder_job, interval=3600, first=600)
        app.job_queue.run_repeating(scheduled_backup_job, interval=3600, first=120)
        app.job_queue.run_daily(daily_log_job, time=dt_module.time(hour=21, minute=0, tzinfo=IST))
        log.info("⏰ All jobs scheduled (including Jarvis proactive)")

    log.info("✅ Bot v15.0 JARVIS ready!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
