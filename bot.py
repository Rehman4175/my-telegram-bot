#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║   PERSONAL AI ASSISTANT — v15.0 JARVIS EDITION                  ║
║   Second Brain + Intelligence Layer (Free Tools Only)           ║
║                                                                  ║
║   NEW IN v15:                                                    ║
║   + 🧠 INSIGHT ENGINE — Daily performance feedback              ║
║   + 🔮 PREDICTION ENGINE — Trend detection                      ║
║   + 🎯 DECISION ENGINE — Smart action suggestions               ║
║   + 📡 PROACTIVE ENGINE — Auto alerts without asking            ║
║   + 🌙 NIGHT REPORT — End-of-day summary                        ║
║   + 📊 Enhanced inline menus                                     ║
║                                                                  ║
║   GITHUB SECRETS NEEDED:                                         ║
║     TELEGRAM_TOKEN, GEMINI_API_KEY, GOOGLE_CREDS_JSON           ║
║     HF_TOKEN (optional), GROQ_API_KEY (optional voice)          ║
║     ADMIN_CHAT_ID (for proactive alerts)                        ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, json, logging, time, asyncio, random, statistics
import urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta, timezone
import datetime as dt_module
from xml.etree import ElementTree as ET
import re as _re
from collections import defaultdict, Counter

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

def time_label():
    n = now_ist()
    days = {0:"Monday",1:"Tuesday",2:"Wednesday",3:"Thursday",4:"Friday",5:"Saturday",6:"Sunday"}
    return f"{days.get(n.weekday(),'')}, {n.day} {n.strftime('%b')} {n.year} — {n.strftime('%I:%M %p')} IST"

# ═══════════════════════════════════════════════════════════════════
# DATABASE
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
                time.sleep(5)
                continue
            continue
        except Exception:
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
                    return text
        except Exception:
            continue
    return None

# ═══════════════════════════════════════════════════════════════════
# SMART OFFLINE FALLBACK
# ═══════════════════════════════════════════════════════════════════
def smart_fallback(user_msg):
    msg = user_msg.lower()
    n = now_ist()
    if any(w in msg for w in ["time", "baje", "kitne baje"]):
        return f"⏰ Abhi *{n.strftime('%I:%M %p')}* baj rahe hain (IST)"
    if any(w in msg for w in ["date", "aaj kya", "tarikh"]):
        return f"📅 Aaj *{n.strftime('%A, %d %B %Y')}* hai"
    if any(w in msg for w in ["hello", "hi", "assalam", "namaste", "hey"]):
        return "🕌 *Assalamualaikum!* Main aapka AI dost hoon. Batao kaisi help chahiye?"
    if any(w in msg for w in ["kaise ho", "how are", "kya haal"]):
        return "😊 *Main badiya hoon!* Aap sunao, kya ho raha hai aaj kal?"
    if any(w in msg for w in ["thank", "shukriya"]):
        return "🤗 *Welcome!* Aur koi help chahiye toh batana!"
    if any(w in msg for w in ["bye", "allah hafiz", "good night"]):
        return "🌙 *Allah Hafiz!* Apna khayal rakhna."
    if any(w in msg for w in ["help", "madad", "command"]):
        return ("📋 *COMMANDS*\n`/task` `/done` — Tasks\n`/habit` `/hdone` — Habits\n"
                "`/remind` — Reminders\n`/kharcha` — Expenses\n`/diary` — Diary\n"
                "`/insight` — Daily insights\n`/predict` — Predictions\n`/help` — Full list")
    return random.choice([
        "🙏 Abhi AI busy hai. Thodi der baad try karo ya `/help` use karo!",
        "😅 Model unavailable. Commands try karo: `/task` `/remind` `/help`",
    ])

# ═══════════════════════════════════════════════════════════════════
# VOICE TRANSCRIPTION
# ═══════════════════════════════════════════════════════════════════
def _sync_transcribe(file_path):
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
        return text if text else None
    except Exception as e:
        log.warning(f"Groq transcription error: {e}")
        return None

async def handle_voice(update, ctx):
    if not update.message:
        return
    voice = update.message.voice or update.message.audio
    if not voice:
        return
    if not GROQ_API_KEY:
        await update.message.reply_text(
            "🎤 *Voice ke liye GROQ\\_API\\_KEY chahiye!*\n"
            "groq.com pe free account banao → Secret add karo",
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
            await status_msg.edit_text("❌ Samajh nahi aaya — saaf bolke bhejna!")
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

# ═══════════════════════════════════════════════════════════════════
# AI PIPELINE
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
        t = {"id": self.store.data["counter"], "title": title, "priority": priority,
             "due": due or today_str(), "done": False, "done_at": None,
             "created": datetime.now().isoformat()}
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
            result[d] = {"done": len(self.done_on(d)),
                         "created": len([t for t in self.all_tasks() if t.get("created", "")[:10] == d])}
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
            "type": action_type, "description": description, "task_id": task_id,
            "details": details or {}, "timestamp": datetime.now().isoformat(), "date": today_str()
        })
        self.store.data["logs"] = self.store.data["logs"][-500:]
        self.store.save()
    def get_all_logs(self):
        return self.store.data.get("logs", [])
    def get_logs_by_date(self, target_date):
        return [l for l in self.get_all_logs() if l.get("date") == target_date]


class FailedReqStore:
    def __init__(self):
        self.store = Store("failed_requests", {"queue": []})
    def add(self, msg, chat_id, reason):
        self.store.data["queue"].append({"msg": msg, "chat_id": chat_id, "reason": reason,
                                          "time": datetime.now().isoformat(), "retried": False})
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
        return ([h for h in all_h if h["id"] in done_ids],
                [h for h in all_h if h["id"] not in done_ids])
    def all(self):
        return self.store.data.get("list", [])
    def delete(self, hid):
        self.store.data["list"] = [h for h in self.store.data["list"] if h["id"] != hid]
        self.store.save()
    def get_logs_by_date(self, target_date):
        return self.store.data.get("logs", {}).get(target_date, [])
    def weekly_completion_rate(self):
        """Returns dict: habit_id -> %completion in last 7 days"""
        result = {}
        all_h = self.all()
        for h in all_h:
            done_count = 0
            for i in range(7):
                d = (now_ist().date() - timedelta(days=i)).isoformat()
                if h["id"] in self.get_logs_by_date(d):
                    done_count += 1
            result[h["id"]] = {"name": h["name"], "emoji": h["emoji"],
                               "rate": round(done_count / 7 * 100), "done_days": done_count}
        return result


class NotesStore:
    def __init__(self):
        self.store = Store("notes", {"list": [], "counter": 0})
    def add(self, content, tag="general"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        n = {"id": self.store.data["counter"], "text": content, "tag": tag,
             "created": datetime.now().isoformat()}
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
            "id": self.store.data["counter"], "amount": amount, "desc": desc,
            "category": category, "date": today_str(), "time": now_str()
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
    def daily_avg_last_7(self):
        totals = []
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            totals.append(sum(e["amount"] for e in self.get_by_date(d)))
        return statistics.mean(totals) if totals else 0
    def category_breakdown_month(self):
        m = today_str()[:7]
        cats = defaultdict(float)
        for e in self.store.data.get("list", []):
            if e.get("date", "")[:7] == m:
                cats[e.get("category", "general")] += e["amount"]
        return dict(cats)


class GoalStore:
    def __init__(self):
        self.store = Store("goals", {"list": [], "counter": 0})
    def add(self, title, deadline=None, why=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        g = {"id": self.store.data["counter"], "title": title, "deadline": deadline or "",
             "why": why, "progress": 0, "done": False, "created": today_str()}
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


class ReminderStore:
    def __init__(self):
        self.store = Store("reminders", {"list": [], "counter": 0})
    def add(self, chat_id, text, remind_at, repeat="once"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        r = {"id": self.store.data["counter"], "chat_id": chat_id, "text": text,
             "time": remind_at, "repeat": repeat, "date": today_str(), "active": True,
             "fired_today": False, "created": datetime.now().isoformat()}
        self.store.data["list"].append(r)
        self.store.save()
        log.info(f"✅ Reminder #{r['id']} | {remind_at} | {text[:30]}")
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
                r_dt = datetime.strptime(f"{today} {r_time}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
                diff = (now - r_dt).total_seconds()
                if 0 <= diff < 90:
                    due.append(r)
                    continue
            except:
                pass
            if r_time == now_hm and r not in due:
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
        b = {"id": self.store.data["counter"], "name": name, "amount": amount,
             "due_day": due_day, "type": bill_type, "active": True,
             "paid_months": [], "created": today_str()}
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


class CalendarStore:
    def __init__(self):
        self.store = Store("calendar", {"events": [], "counter": 0})
    def add(self, title, event_date, event_time=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        e = {"id": self.store.data["counter"], "title": title, "date": event_date,
             "time": event_time, "created": today_str()}
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
                        items.append({"title": title, "desc": desc[:120] if desc else ""})
        except Exception as e:
            items = [{"title": "News unavailable", "desc": str(e)[:100]}]
        cache.setdefault("cache", {})[category] = items
        cache.setdefault("updated", {})[category] = now_ts
        self.store.save()
        return items


class ChatHistoryStore:
    def __init__(self):
        self.store = Store("chat_history", {"history": [], "msg_ids": []})
    def add(self, role, content):
        self.store.data["history"].append({"role": role, "content": content,
                                            "time": datetime.now().isoformat()})
        self.store.data["history"] = self.store.data["history"][-40:]
        self.store.save()
    def track_msg(self, chat_id, msg_id):
        self.store.data.setdefault("msg_ids", []).append({"chat_id": chat_id, "msg_id": msg_id})
        self.store.data["msg_ids"] = self.store.data["msg_ids"][-200:]
        self.store.save()
    def get_tracked_ids(self):
        return self.store.data.get("msg_ids", [])
    def clear(self):
        count = len(self.store.data["history"])
        self.store.data["history"] = []
        self.store.save()
        return count
    def clear_msg_ids(self):
        self.store.data["msg_ids"] = []
        self.store.save()
    def count(self):
        return len(self.store.data.get("history", []))


class ProactiveStore:
    """Tracks last alert time to avoid spamming"""
    def __init__(self):
        self.store = Store("proactive_state", {"last_alerts": {}})
    def can_alert(self, key, cooldown_hours=6):
        last = self.store.data.get("last_alerts", {}).get(key)
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
            return (datetime.now() - last_dt).total_seconds() >= cooldown_hours * 3600
        except:
            return True
    def mark_alerted(self, key):
        self.store.data.setdefault("last_alerts", {})[key] = datetime.now().isoformat()
        self.store.save()


# ═══════════════════════════════════════════════════════════════════
# INIT STORES
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
proactive = ProactiveStore()

# ═══════════════════════════════════════════════════════════════════
# 🧠 INTELLIGENCE LAYER — INSIGHT / PREDICTION / DECISION ENGINES
# ═══════════════════════════════════════════════════════════════════
class IntelligenceEngine:
    """Combines insight, prediction, decision, and proactive logic."""

    # ─── INSIGHT ENGINE ──────────────────────────────────────────
    @staticmethod
    def daily_insight():
        """Returns Hindi/Hinglish insight about today's performance."""
        n = now_ist()
        today = today_str()
        tasks_done_today = len(tasks.done_on(today))
        tasks_pending = len(tasks.today_pending())
        habits_done, habits_pending = habits.today_status()
        exp_today = expenses.today_total()
        exp_avg = expenses.daily_avg_last_7()
        water_today = water.today_total()
        water_goal = water.goal()
        diary_today = len(diary.get(today))

        score = 0
        score += min(40, tasks_done_today * 10)
        if habits.all():
            score += int(len(habits_done) / max(len(habits.all()), 1) * 30)
        if water_goal:
            score += min(15, int(water_today / water_goal * 15))
        if diary_today > 0:
            score += 10
        if tasks_pending == 0 and tasks_done_today > 0:
            score += 5

        if score >= 80:
            grade, emoji = "Excellent 🔥", "🏆"
        elif score >= 60:
            grade, emoji = "Acha 👍", "✨"
        elif score >= 40:
            grade, emoji = "Theek-thaak", "📊"
        else:
            grade, emoji = "Kam hai", "⚠️"

        lines = [f"🧠 *DAILY INSIGHT* — {n.strftime('%d %b, %I:%M %p')}", "━" * 28]
        lines.append(f"{emoji} *Score: {score}/100 — {grade}*\n")
        lines.append(f"📋 Tasks: ✅ {tasks_done_today} done | ⏳ {tasks_pending} pending")
        lines.append(f"💪 Habits: {len(habits_done)}/{len(habits.all())} complete")
        lines.append(f"💧 Water: {water_today}/{water_goal} ml")
        lines.append(f"💰 Aaj kharcha: ₹{exp_today:.0f} (avg: ₹{exp_avg:.0f})")
        lines.append(f"📖 Diary: {'✅ Likha' if diary_today else '❌ Nahi likha'}")

        # AI-generated insight
        observations = []
        if tasks_done_today == 0 and n.hour > 12:
            observations.append("Aaj ek bhi task complete nahi — chhota sa start karo!")
        if exp_today > exp_avg * 1.5 and exp_avg > 0:
            observations.append(f"Aaj kharcha 50% zyada! (avg ₹{exp_avg:.0f} vs aaj ₹{exp_today:.0f})")
        if water_goal and water_today < water_goal * 0.5 and n.hour > 14:
            observations.append("Paani kam piya — abhi ek glass pee lo!")
        if len(habits_pending) > len(habits_done) and n.hour > 18:
            observations.append("Habits pending hain — sone se pehle kar lo.")
        if score >= 80:
            observations.append("Bahut zabardast din! Keep going 🚀")

        if observations:
            lines.append("\n💡 *Observations:*")
            for obs in observations:
                lines.append(f"  • {obs}")

        return "\n".join(lines)

    # ─── PREDICTION ENGINE ───────────────────────────────────────
    @staticmethod
    def predictions():
        lines = [f"🔮 *PREDICTIONS & TRENDS*", "━" * 28]

        # Expense forecast
        exp_avg = expenses.daily_avg_last_7()
        days_in_month = 30
        day_of_month = now_ist().day
        days_left = days_in_month - day_of_month
        forecast = expenses.month_total() + (exp_avg * days_left)
        budget = expenses.store.data.get("budget", {}).get("monthly", 0)

        lines.append(f"\n💰 *Expense Forecast:*")
        lines.append(f"  • Daily avg (7d): ₹{exp_avg:.0f}")
        lines.append(f"  • Month total estimate: ₹{forecast:.0f}")
        if budget:
            if forecast > budget:
                over = forecast - budget
                lines.append(f"  ⚠️ Budget cross ho sakta hai by ₹{over:.0f}!")
            else:
                lines.append(f"  ✅ Budget mein rahoge (₹{budget - forecast:.0f} bachega)")

        # Habit risk prediction
        rates = habits.weekly_completion_rate()
        if rates:
            lines.append(f"\n💪 *Habit Risk (last 7 days):*")
            for hid, info in rates.items():
                if info["rate"] < 50:
                    lines.append(f"  ⚠️ {info['emoji']} {info['name']} — {info['rate']}% (risk!)")
                elif info["rate"] >= 85:
                    lines.append(f"  🔥 {info['emoji']} {info['name']} — {info['rate']}% (strong!)")

        # Task velocity
        weekly = tasks.get_weekly_summary()
        total_done = sum(v["done"] for v in weekly.values())
        total_created = sum(v["created"] for v in weekly.values())
        lines.append(f"\n📋 *Task Velocity:*")
        lines.append(f"  • Last 7 days: {total_done} done / {total_created} created")
        if total_created > 0:
            ratio = total_done / total_created
            if ratio >= 0.8:
                lines.append(f"  ✅ Strong completion rate ({int(ratio*100)}%)")
            elif ratio >= 0.5:
                lines.append(f"  ⚠️ Backlog growing ({int(ratio*100)}% completion)")
            else:
                lines.append(f"  🚨 Backlog overload! Only {int(ratio*100)}% done")

        # Top expense category
        cats = expenses.category_breakdown_month()
        if cats:
            top_cat = max(cats.items(), key=lambda x: x[1])
            lines.append(f"\n🏷 *Top spend category:* {top_cat[0]} — ₹{top_cat[1]:.0f}")

        return "\n".join(lines)

    # ─── DECISION ENGINE ─────────────────────────────────────────
    @staticmethod
    def suggestions():
        lines = [f"🎯 *SMART SUGGESTIONS*", "━" * 28]
        actions = []

        # Pending high-priority tasks
        high_pending = [t for t in tasks.pending() if t.get("priority") == "high"]
        if high_pending:
            actions.append(f"🔴 {len(high_pending)} HIGH-priority task pending — abhi karo: *{high_pending[0]['title']}*")

        # Bills due
        due_bills = bills.due_soon(3)
        if due_bills:
            for b in due_bills[:2]:
                actions.append(f"💳 Bill due: *{b['name']}* ₹{b['amount']:.0f} on {b['due_date']}")

        # Water low
        wt = water.today_total()
        wg = water.goal()
        if wg and wt < wg * 0.5 and now_ist().hour > 12:
            need = wg - wt
            actions.append(f"💧 {need}ml paani peene ki zaroorat hai aaj!")

        # Habit streak risk
        rates = habits.weekly_completion_rate()
        for hid, info in rates.items():
            if 0 < info["rate"] < 50:
                actions.append(f"⚠️ Habit *{info['name']}* slip ho rahi — aaj zaroor karo")
                break

        # Goal progress
        for g in goals.active():
            if g["progress"] < 25 and g.get("created"):
                try:
                    days_old = (now_ist().date() - date.fromisoformat(g["created"])).days
                    if days_old > 14:
                        actions.append(f"🎯 Goal *{g['title']}* sirf {g['progress']}% hai ({days_old}d old)")
                        break
                except:
                    pass

        # Diary missed
        if not diary.get(today_str()) and now_ist().hour >= 21:
            actions.append("📖 Aaj diary nahi likhi — 1 line hi sahi, likh do!")

        # Budget warning
        bl = expenses.budget_left()
        if bl is not None and bl < 0:
            actions.append(f"🚨 Budget cross ho gaya by ₹{-bl:.0f}!")
        elif bl is not None and bl < expenses.daily_avg_last_7() * 5:
            actions.append(f"⚠️ Budget mein sirf ₹{bl:.0f} bacha — sambhalke!")

        if not actions:
            lines.append("\n✅ Sab kuch on track hai! Maza karo 🎉")
        else:
            lines.append("")
            for a in actions[:8]:
                lines.append(f"  {a}")

        return "\n".join(lines)

    # ─── PROACTIVE ENGINE ────────────────────────────────────────
    @staticmethod
    async def proactive_check(bot, chat_id):
        """Sends auto-alerts only when threshold met + cooldown passed."""
        n = now_ist()

        # Budget overshoot
        bl = expenses.budget_left()
        if bl is not None and bl < 0 and proactive.can_alert("budget_over", 12):
            await bot.send_message(
                chat_id=chat_id,
                text=f"🚨 *BUDGET ALERT!*\n\nMahine ka budget ₹{-bl:.0f} se cross ho gaya!\nAb careful kharcha karo.",
                parse_mode="Markdown"
            )
            proactive.mark_alerted("budget_over")

        # Streak at risk (habit pending and time after 8 PM)
        if n.hour >= 20:
            _, pending = habits.today_status()
            high_streak_pending = [h for h in pending if h.get("streak", 0) >= 3]
            if high_streak_pending and proactive.can_alert("streak_risk", 6):
                names = ", ".join(f"{h['emoji']}{h['name']}({h['streak']}d)" for h in high_streak_pending[:3])
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🔥 *STREAK ALERT!*\n\nYe habits ka streak khatam ho jaayega:\n{names}\n\nAbhi kar lo!",
                    parse_mode="Markdown"
                )
                proactive.mark_alerted("streak_risk")

        # No tasks done by 5 PM
        if n.hour == 17 and len(tasks.done_on(today_str())) == 0 and len(tasks.today_pending()) > 0:
            if proactive.can_alert("no_progress_5pm", 20):
                await bot.send_message(
                    chat_id=chat_id,
                    text="🌅 *Reminder:* Aaj abhi tak ek task complete nahi hua. Ek chhota sa start karo!",
                    parse_mode="Markdown"
                )
                proactive.mark_alerted("no_progress_5pm")

        # High spend day
        if expenses.today_total() > expenses.daily_avg_last_7() * 2 and expenses.daily_avg_last_7() > 100:
            if proactive.can_alert("high_spend", 24):
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"💸 *Heads up:* Aaj kharcha ₹{expenses.today_total():.0f} hua — avg se 2x zyada!",
                    parse_mode="Markdown"
                )
                proactive.mark_alerted("high_spend")

    # ─── NIGHT REPORT ────────────────────────────────────────────
    @staticmethod
    def night_report():
        n = now_ist()
        today = today_str()
        lines = [f"🌙 *NIGHT REPORT* — {n.strftime('%d %b %Y')}", "━" * 28]

        td = tasks.done_on(today)
        tp = tasks.today_pending()
        lines.append(f"\n📋 *Tasks:* ✅ {len(td)} | ⏳ {len(tp)} pending")
        if td:
            for t in td[:5]:
                lines.append(f"  ✓ {t['title']}")

        hd, hp = habits.today_status()
        lines.append(f"\n💪 *Habits:* {len(hd)}/{len(habits.all())} done")
        if hd:
            lines.append("  " + ", ".join(f"{h['emoji']}{h['name']}" for h in hd))
        if hp:
            lines.append(f"  ⏳ Pending: {', '.join(h['name'] for h in hp)}")

        lines.append(f"\n💰 *Kharcha aaj:* ₹{expenses.today_total():.0f}")
        lines.append(f"💧 *Paani:* {water.today_total()}/{water.goal()} ml")

        if diary.get(today):
            lines.append(f"📖 *Diary:* ✅ Likhi")
        else:
            lines.append(f"📖 *Diary:* ❌ Nahi likhi — abhi likh do!")

        lines.append(f"\n{IntelligenceEngine.daily_insight().split('━' * 28)[1].strip()[:300]}")

        # Tomorrow preview
        tomorrow = (n.date() + timedelta(days=1)).isoformat()
        cal_tom = [e for e in calendar.store.data.get("events", []) if e["date"] == tomorrow]
        if cal_tom:
            lines.append(f"\n📅 *Kal ke events:*")
            for e in cal_tom[:3]:
                lines.append(f"  • {e.get('time','')} {e['title']}")

        lines.append("\n_Shubh raatri! Kal milte hain 🌙_")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# GOOGLE SHEETS (Trimmed — same as your version, key methods only)
# ═══════════════════════════════════════════════════════════════════
class GoogleSheetsBackup:
    def __init__(self):
        self.sheet = None
        if not HAS_GSHEETS:
            log.warning("⚠️ gspread not installed!")
            return
        creds_json = os.environ.get("GOOGLE_CREDS_JSON", "") or os.environ.get("Google_CREDS_JSON", "")
        if not creds_json:
            log.warning("⚠️ GOOGLE_CREDS_JSON not found! Backup disabled.")
            return
        try:
            creds_dict = json.loads(creds_json)
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            sheet_id = os.environ.get("GOOGLE_SHEET_ID", "1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")
            self.sheet = client.open_by_key(sheet_id)
            log.info("✅ Google Sheets connected!")
            self.ensure_worksheets()
        except Exception as e:
            log.error(f"❌ Sheets error: {e}")

    def ensure_worksheets(self):
        if not self.sheet:
            return
        required = ["Tasks", "Reminders", "Expenses", "Habits", "Water", "Memory",
                    "Daily_Logs", "Goals", "Bills", "Calendar", "Diary"]
        existing = [ws.title for ws in self.sheet.worksheets()]
        for name in required:
            if name not in existing:
                try:
                    self.sheet.add_worksheet(title=name, rows=1000, cols=20)
                except Exception as e:
                    log.warning(f"Create {name} failed: {e}")
        self.setup_headers()

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
            "Diary": ["Date", "Time", "Mood", "Entry Text"]
        }
        for sheet_name, headers in headers_config.items():
            try:
                ws = self.sheet.worksheet(sheet_name)
                first_row = ws.row_values(1)
                if not first_row or not any(first_row):
                    ws.update('A1', [headers])
            except Exception as e:
                log.warning(f"Headers {sheet_name}: {e}")

    def _upsert_rows(self, ws, new_rows, id_col=0):
        try:
            existing = ws.get_all_values()
            key_to_row = {}
            for i, row in enumerate(existing[1:], start=2):
                if row and len(row) > abs(id_col):
                    key = str(row[id_col]).strip()
                    if key:
                        key_to_row[key] = i
            updates, appends = [], []
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
                    batch.append({"range": f"A{row_num}:{col_end}{row_num}", "values": [data]})
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
            rows = [[str(t.get("id","")), t.get("title",""), t.get("priority","medium"),
                     "Done" if t.get("done") else "Pending", t.get("created","")[:10],
                     t.get("done_at","")[:10] if t.get("done_at") else ""] for t in tasks_list]
            self._upsert_rows(ws, rows, id_col=0)
            return True
        except Exception as e:
            log.error(f"Tasks save: {e}")
            return False

    def save_reminders(self, reminders_list):
        if not self.sheet or not reminders_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Reminders")
            rows = [[str(r.get("id","")), r.get("time",""), r.get("text",""),
                     r.get("repeat","once"), "Active" if r.get("active") else "Inactive",
                     r.get("date",""), "Yes" if r.get("fired_today") else "No",
                     r.get("created","")[:16] if r.get("created") else ""] for r in reminders_list]
            self._upsert_rows(ws, rows, id_col=0)
            return True
        except Exception as e:
            log.error(f"Reminders save: {e}")
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
            for e in expenses_list:
                key = f"{e.get('date','')}|{e.get('amount','')}|{e.get('desc','')}"
                if key not in existing_keys:
                    ws.append_row([e.get("date",""), e.get("amount",0), e.get("desc",""),
                                    e.get("category","general"), e.get("time","")],
                                   value_input_option="USER_ENTERED")
                    existing_keys.add(key)
            return True
        except Exception as e:
            log.error(f"Expenses save: {e}")
            return False

    def save_habits(self, habits_list):
        if not self.sheet or not habits_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Habits")
            rows = [[str(h.get("id","")), h.get("name",""), h.get("emoji","✅"),
                     h.get("streak",0), h.get("best_streak",0), h.get("created","")] for h in habits_list]
            self._upsert_rows(ws, rows, id_col=0)
            return True
        except Exception as e:
            log.error(f"Habits save: {e}")
            return False

    def save_memory(self, facts):
        if not self.sheet or not facts:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Memory")
            existing = ws.get_all_values()
            existing_facts = {row[1] for row in existing[1:] if len(row) > 1}
            for f in facts:
                if f.get("f") and f["f"] not in existing_facts:
                    ws.append_row([f.get("d",""), f["f"], "fact"], value_input_option="USER_ENTERED")
                    existing_facts.add(f["f"])
            return True
        except Exception as e:
            log.error(f"Memory save: {e}")
            return False

    def save_goals(self, goals_list):
        if not self.sheet or not goals_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Goals")
            rows = [[str(g.get("id","")), g.get("title",""), g.get("progress",0),
                     "Done" if g.get("done") else "Active", g.get("deadline",""),
                     g.get("created","")] for g in goals_list]
            self._upsert_rows(ws, rows, id_col=0)
            return True
        except Exception as e:
            log.error(f"Goals save: {e}")
            return False

    def save_bills(self, bills_list):
        if not self.sheet or not bills_list:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Bills")
            rows = [[str(b.get("id","")), b.get("name",""), b.get("amount",0),
                     b.get("due_day",""),
                     "Paid" if bills.is_paid_this_month(b["id"]) else "Pending",
                     b.get("created","")] for b in bills_list]
            self._upsert_rows(ws, rows, id_col=0)
            return True
        except Exception as e:
            log.error(f"Bills save: {e}")
            return False

    def save_calendar(self, events):
        if not self.sheet or not events:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Calendar")
            rows = [[str(e.get("id","")), e.get("title",""), e.get("date",""),
                     e.get("time",""), e.get("created","")] for e in events]
            self._upsert_rows(ws, rows, id_col=0)
            return True
        except Exception as e:
            log.error(f"Calendar save: {e}")
            return False

    def save_water(self, water_obj):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Water")
            goal = water_obj.goal()
            week = water_obj.week_summary()
            rows = []
            for d, total in sorted(week.items()):
                pct = int(total / goal * 100) if goal else 0
                ents = water_obj.get_by_date(d)
                rows.append([d, total, goal, f"{pct}%", len(ents)])
            if rows:
                self._upsert_rows(ws, rows, id_col=0)
            return True
        except Exception as e:
            log.error(f"Water save: {e}")
            return False

    def save_diary(self, all_entries):
        if not self.sheet or not all_entries:
            return bool(self.sheet)
        try:
            ws = self.sheet.worksheet("Diary")
            existing = ws.get_all_values()
            existing_keys = set()
            for row in existing[1:]:
                if len(row) >= 1 and row[0]:
                    text_col = row[3][:50] if len(row) > 3 else ""
                    existing_keys.add(f"{row[0]}|{row[1] if len(row)>1 else ''}|{text_col}")
            for entry_date in sorted(all_entries.keys()):
                for entry in all_entries[entry_date]:
                    key = f"{entry_date}|{entry.get('time','')}|{entry.get('text','')[:50]}"
                    if key not in existing_keys:
                        ws.append_row([entry_date, entry.get("time",""),
                                        entry.get("mood","📝"), entry.get("text","")],
                                       value_input_option="USER_ENTERED")
                        existing_keys.add(key)
            return True
        except Exception as e:
            log.error(f"Diary save: {e}")
            return False

    def save_daily_log(self):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Daily_Logs")
            today = today_str()
            day_name = now_ist().strftime("%A")
            new_row = [today, day_name, len(tasks.done_on(today)), len(tasks.today_pending()),
                       expenses.today_total(), water.today_total(), len(habits.today_status()[0]), "", ""]
            all_values = ws.get_all_values()
            today_idx = None
            for idx, row in enumerate(all_values):
                if row and row[0] == today:
                    today_idx = idx + 1
                    break
            if today_idx:
                ws.update(f'A{today_idx}:I{today_idx}', [new_row])
            else:
                ws.append_row(new_row)
            return True
        except Exception as e:
            log.error(f"Daily log: {e}")
            return False

    def full_sync(self):
        if not self.sheet:
            return "❌ Sheets not connected!"
        ops = [
            ("Tasks", lambda: self.save_tasks(tasks.all_tasks())),
            ("Reminders", lambda: self.save_reminders(reminders.get_all())),
            ("Expenses", lambda: self.save_expenses(expenses.store.data.get("list", []))),
            ("Habits", lambda: self.save_habits(habits.all())),
            ("Memory", lambda: self.save_memory(memory.get_all_facts())),
            ("Goals", lambda: self.save_goals(goals.active() + goals.completed())),
            ("Bills", lambda: self.save_bills(bills.all_active())),
            ("Calendar", lambda: self.save_calendar(calendar.store.data.get("events", []))),
            ("Water", lambda: self.save_water(water)),
            ("DailyLog", lambda: self.save_daily_log()),
            ("Diary", lambda: self.save_diary(diary.get_all_entries())),
        ]
        success, errors = 0, []
        for name, fn in ops:
            try:
                if fn():
                    success += 1
                else:
                    errors.append(name)
            except Exception as e:
                log.error(f"Sync {name}: {e}")
                errors.append(name)
        if errors:
            return f"⚠️ Synced {success}/{len(ops)} | Failed: {', '.join(errors)}"
        return f"✅ Synced {success}/{len(ops)} sheets!"

    def restore_from_sheets(self):
        if not self.sheet:
            return False
        restored = []
        try:
            # Tasks
            ws = self.sheet.worksheet("Tasks")
            rows = ws.get_all_records()
            tlist = []
            for r in rows:
                if not r.get("ID") and not r.get("Title"):
                    continue
                tlist.append({
                    "id": int(r["ID"]) if str(r.get("ID","")).isdigit() else 0,
                    "title": r.get("Title",""), "priority": r.get("Priority","medium"),
                    "done": r.get("Status","") == "Done",
                    "created": r.get("Created At", today_str()),
                    "done_at": r.get("Completed At","")
                })
            if tlist:
                max_id = max((t["id"] for t in tlist), default=0)
                db.save("tasks", {"list": tlist, "counter": max_id})
                restored.append(f"📋 {len(tlist)} tasks")
        except Exception as e:
            log.warning(f"Tasks restore: {e}")

        try:
            ws = self.sheet.worksheet("Reminders")
            rows = ws.get_all_records()
            rlist = []
            for r in rows:
                if not r.get("ID") and not r.get("Text"):
                    continue
                rlist.append({
                    "id": int(r["ID"]) if str(r.get("ID","")).isdigit() else 0,
                    "time": r.get("Time (HH:MM)",""), "text": r.get("Text",""),
                    "repeat": r.get("Repeat","once"),
                    "active": r.get("Status","Active") == "Active",
                    "fired_today": False,
                    "date": r.get("Created Date", today_str()),
                    "created": r.get("Created At",""),
                    "chat_id": int(os.environ.get("ADMIN_CHAT_ID", 0))
                })
            if rlist:
                max_id = max((r["id"] for r in rlist), default=0)
                db.save("reminders", {"list": rlist, "counter": max_id})
                restored.append(f"⏰ {len(rlist)} reminders")
        except Exception as e:
            log.warning(f"Reminders restore: {e}")

        try:
            ws = self.sheet.worksheet("Diary")
            rows = ws.get_all_records()
            entries = {}
            for r in rows:
                d = r.get("Date","")
                if not d:
                    continue
                entries.setdefault(d, []).append({
                    "text": r.get("Entry Text",""), "mood": r.get("Mood","📝"),
                    "time": r.get("Time","")
                })
            if entries:
                db.save("diary", {"entries": entries})
                restored.append(f"📖 {sum(len(v) for v in entries.values())} entries")
        except Exception as e:
            log.warning(f"Diary restore: {e}")

        try:
            ws = self.sheet.worksheet("Expenses")
            rows = ws.get_all_records()
            elist = []
            for r in rows:
                if not r.get("Amount (Rs)") and not r.get("Description"):
                    continue
                elist.append({
                    "date": r.get("Date", today_str()),
                    "amount": float(r.get("Amount (Rs)", 0) or 0),
                    "desc": r.get("Description",""),
                    "category": r.get("Category","general"),
                    "time": r.get("Time","")
                })
            if elist:
                db.save("expenses", {"list": elist, "budget": {}})
                restored.append(f"💰 {len(elist)} expenses")
        except Exception as e:
            log.warning(f"Expenses restore: {e}")

        try:
            ws = self.sheet.worksheet("Habits")
            rows = ws.get_all_records()
            hlist = []
            for r in rows:
                if not r.get("Habit Name"):
                    continue
                hlist.append({
                    "id": int(r["ID"]) if str(r.get("ID","")).isdigit() else 0,
                    "name": r.get("Habit Name",""),
                    "emoji": r.get("Emoji","✅"),
                    "streak": int(r.get("Current Streak", 0) or 0),
                    "best_streak": int(r.get("Best Streak", 0) or 0),
                    "created": r.get("Created", today_str())
                })
            if hlist:
                max_id = max((h["id"] for h in hlist), default=0)
                db.save("habits", {"list": hlist, "logs": {}, "counter": max_id})
                restored.append(f"💪 {len(hlist)} habits")
        except Exception as e:
            log.warning(f"Habits restore: {e}")

        try:
            ws = self.sheet.worksheet("Memory")
            rows = ws.get_all_records()
            facts = []
            for r in rows:
                if r.get("Fact"):
                    facts.append({"d": r.get("Date",""), "f": r.get("Fact","")})
            if facts:
                db.save("memory", {"facts": facts, "prefs": {}, "important_notes": [], "dates": {}})
                restored.append(f"🧠 {len(facts)} memories")
        except Exception as e:
            log.warning(f"Memory restore: {e}")

        if restored:
            log.info(f"✅ Restored: {' | '.join(restored)}")
        return True


google_sheets = GoogleSheetsBackup()

def restore_all_from_sheets():
    if not google_sheets.sheet:
        return
    google_sheets.restore_from_sheets()
    tasks.store.data = db.load("tasks", {"list": [], "counter": 0})
    reminders.store.data = db.load("reminders", {"list": [], "counter": 0})
    diary.store.data = db.load("diary", {"entries": {}})
    expenses.store.data = db.load("expenses", {"list": [], "budget": {}, "counter": 0})
    habits.store.data = db.load("habits", {"list": [], "logs": {}, "counter": 0})
    memory.store.data = db.load("memory", {"facts": [], "prefs": {}, "important_notes": [], "dates": {}})
    log.info("✅ All stores reloaded")

restore_all_from_sheets()

# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
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

    tasks_s = "\n".join(f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}" for t in tp[:5]) or "  Koi nahi"
    yd_s = "\n".join(f"  ✓ {t['title']}" for t in yd[:3]) or "  Koi nahi"
    h_done = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    goals_s = "\n".join(f"  🎯 {g['title']} ({g['progress']}%)" for g in ag[:4]) or "  Koi nahi"
    diary_s = "\n".join(f"  {e['time']} {e['text']}" for e in td_d[-2:]) or "  Kuch nahi"
    budget_s = f"Budget baaki: ₹{bl:.0f}" if bl is not None else ""

    return f"""Tu mera Personal AI Assistant hai — naam 'Dost'. Hindi/Hinglish mein baat kar.

⚠️ TIME: {now_label} ({current_time}) | Aaj: {today_str()}

📋 TASKS ({len(tp)}):
{tasks_s}

✅ KAL ({len(yd)}):
{yd_s}

💪 HABITS: Done: {h_done}

📖 DIARY: {diary_s}

💰 KHARCHA: Aaj ₹{exp_t} | Mahina ₹{exp_m} {budget_s}

🎯 GOALS:
{goals_s}

💧 PAANI: {water_today}/{water_goal}ml

🧠 YAADDASHT:
{memory.context()}

RULES: Dost jaisa, Hindi/Hinglish, SHORT (2-4 lines), exact time bata.
"""

def auto_extract_facts(text):
    lower = text.lower()
    triggers = ["yaad rakh", "remember", "mera naam", "meri umar", "main rehta",
                "mujhe pasand", "meri job", "mera kaam", "birthday", "anniversary"]
    if any(kw in lower for kw in triggers):
        memory.add_fact(text[:250])
        return True
    return False

# ═══════════════════════════════════════════════════════════════════
# ACTION ROUTER
# ═══════════════════════════════════════════════════════════════════
ACTION_SYSTEM_PROMPT = """You are a JSON router. Return ONLY raw JSON.
Time: {now} | 24h: {current_time} | Today: {today} | +2min: {two_min}
Format: {{"action":"X","params":{{...}},"reply":"..."}}

ACTIONS:
REMIND — {{"time":"HH:MM","text":"...","repeat":"once"}}
ADD_TASK — {{"title":"...","priority":"high/medium/low"}}
ADD_EXPENSE — {{"amount":N,"desc":"...","category":"..."}}
ADD_DIARY — {{"text":"...","mood":"😊"}}
ADD_MEMORY — {{"fact":"..."}}
ADD_HABIT — {{"name":"...","emoji":"💪"}}
COMPLETE_TASK — {{"title_hint":"..."}}
SHOW_TASKS / SHOW_REMINDERS — {{}}
INSIGHT / PREDICT / SUGGEST — {{}}
CHAT — {{}} (default)
"""

def _regex_fallback(user_msg):
    lower = user_msg.lower()
    now = now_ist()
    if any(w in lower for w in ["alarm", "reminder", "yaad dila", "remind", "minute baad", "min baad", "ghante baad", "baje"]):
        time_str = None
        m = _re.search(r'(\d+)\s*(?:minute|min|mins)', lower)
        if m:
            time_str = (now + timedelta(minutes=int(m.group(1)))).strftime("%H:%M")
        if not time_str:
            m = _re.search(r'(\d+)\s*(?:ghante|hour|hr)', lower)
            if m:
                time_str = (now + timedelta(hours=int(m.group(1)))).strftime("%H:%M")
        if not time_str:
            m = _re.search(r'(\d{1,2}):(\d{2})', lower)
            if m:
                h, mn = int(m.group(1)), int(m.group(2))
                if 0 <= h <= 23 and 0 <= mn <= 59:
                    time_str = f"{h:02d}:{mn:02d}"
        if time_str:
            text = _re.sub(r'\d+\s*(?:minute|min|ghante|hour|hr)', '', user_msg, flags=_re.I)
            text = _re.sub(r'\d{1,2}(?::\d{2})?\s*(?:baje)?', '', text, flags=_re.I)
            text = _re.sub(r'(?:alarm|reminder|yaad dila|remind|set karo|baad)\s*', '', text, flags=_re.I).strip()
            return {"action": "REMIND", "params": {"time": time_str, "text": text or "⏰ Reminder!", "repeat": "once"}, "reply": ""}
    if any(w in lower for w in ["karna hai", "task add", "kaam add", "to-do", "todo"]):
        return {"action": "ADD_TASK", "params": {"title": user_msg[:80], "priority": "medium"}, "reply": ""}
    if any(w in lower for w in ["rs ", "rupaye", "kharcha", "spend", "lage", "diye"]):
        m = _re.search(r'(\d+)', lower)
        amount = float(m.group(1)) if m else 0
        if amount > 0:
            return {"action": "ADD_EXPENSE", "params": {"amount": amount, "desc": user_msg[:60], "category": "general"}, "reply": ""}
    if any(w in lower for w in ["insight", "kaisa din", "performance"]):
        return {"action": "INSIGHT", "params": {}, "reply": ""}
    if any(w in lower for w in ["predict", "forecast", "trend"]):
        return {"action": "PREDICT", "params": {}, "reply": ""}
    if any(w in lower for w in ["suggest", "kya karu", "advice"]):
        return {"action": "SUGGEST", "params": {}, "reply": ""}
    return {"action": "CHAT", "params": {}, "reply": ""}

def call_gemini_action(user_msg, now_label, today_label):
    now = now_ist()
    two_min = (now + timedelta(minutes=2)).strftime("%H:%M")
    current_time = now.strftime("%H:%M")
    prompt = ACTION_SYSTEM_PROMPT.format(now=now_label, current_time=current_time, today=today_label, two_min=two_min)
    full_msg = f"{prompt}\n\nUser: {user_msg}"
    payload = json.dumps({"contents": [{"role": "user", "parts": [{"text": full_msg}]}],
                          "generationConfig": {"temperature": 0.0, "maxOutputTokens": 200}}).encode("utf-8")
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
                return json.loads(raw)
        except Exception:
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
            return f"⏰ Time format galat! Abhi *{now.strftime('%H:%M')}*"
        r = reminders.add(chat_id, text, time_str, repeat)
        return f"✅ Reminder set! ⏰ *{time_str}* — {text}\n🆔 `#{r['id']}`"

    elif action == "ADD_TASK":
        t = tasks.add(params.get("title", user_msg[:80]), params.get("priority", "medium"))
        icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        return f"✅ Task: {icons.get(t['priority'],'🟡')} *{t['title']}*\n🆔 `#{t['id']}`"

    elif action == "ADD_EXPENSE":
        amount = float(params.get("amount", 0))
        if amount <= 0:
            return "💰 Amount batao?"
        expenses.add(amount, params.get("desc", "Kharcha"))
        return f"✅ ₹{amount:.0f} — {params.get('desc')}\n📊 Aaj: ₹{expenses.today_total():.0f}"

    elif action == "ADD_DIARY":
        diary.add(params.get("text", user_msg[:100]), params.get("mood", "😊"))
        return f"📖 Diary saved! 🕐 {now_str()}"

    elif action == "ADD_MEMORY":
        memory.add_fact(params.get("fact", user_msg[:200]))
        return "🧠 Yaad kar liya! ✅"

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
        return "❓ Kaunsa task?"

    elif action == "SHOW_TASKS":
        pending = tasks.today_pending()
        if not pending:
            return "🎉 No pending tasks!"
        return "📋 *PENDING*\n\n" + "\n".join(f"{'🔴' if t['priority']=='high' else '🟡'} #{t['id']} {t['title']}" for t in pending[:8])

    elif action == "SHOW_REMINDERS":
        active = reminders.all_active()
        if not active:
            return "⏰ No reminders!"
        return "⏰ *REMINDERS*\n\n" + "\n".join(f"#{r['id']} `{r['time']}` — {r['text']}" for r in active)

    elif action == "INSIGHT":
        return IntelligenceEngine.daily_insight()

    elif action == "PREDICT":
        return IntelligenceEngine.predictions()

    elif action == "SUGGEST":
        return IntelligenceEngine.suggestions()

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
    return get_ai_reply(user_msg)

# ═══════════════════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════════════════
def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]])

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Briefing", callback_data="briefing"),
         InlineKeyboardButton("🌙 Night Report", callback_data="night_report")],
        [InlineKeyboardButton("🧠 Insight", callback_data="insight"),
         InlineKeyboardButton("🔮 Predict", callback_data="predict")],
        [InlineKeyboardButton("🎯 Suggest", callback_data="suggest"),
         InlineKeyboardButton("📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("💪 Habits", callback_data="habits"),
         InlineKeyboardButton("📖 Diary", callback_data="diary_write")],
        [InlineKeyboardButton("🎯 Goals", callback_data="goals"),
         InlineKeyboardButton("💰 Kharcha", callback_data="expenses")],
        [InlineKeyboardButton("📰 News", callback_data="news_menu"),
         InlineKeyboardButton("📝 Notes", callback_data="notes")],
        [InlineKeyboardButton("💧 Water", callback_data="water_status"),
         InlineKeyboardButton("💳 Bills", callback_data="bills_menu")],
        [InlineKeyboardButton("📅 Calendar", callback_data="cal_menu"),
         InlineKeyboardButton("📊 Weekly", callback_data="weekly_report")],
        [InlineKeyboardButton("🧠 Memory", callback_data="memory"),
         InlineKeyboardButton("📊 Yesterday", callback_data="yesterday")],
        [InlineKeyboardButton("📤 Backup", callback_data="backup_now"),
         InlineKeyboardButton("🧹 Clear Chat", callback_data="clear_chat")],
    ])

def news_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇳 India", callback_data="news_India"),
         InlineKeyboardButton("💻 Tech", callback_data="news_Technology")],
        [InlineKeyboardButton("💼 Business", callback_data="news_Business"),
         InlineKeyboardButton("🌍 World", callback_data="news_World")],
        [InlineKeyboardButton("🏏 Sports", callback_data="news_Sports"),
         InlineKeyboardButton("🏠 Back", callback_data="menu")],
    ])

# ═══════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════
async def cmd_start(update, ctx):
    n = now_ist()
    name = update.effective_user.first_name or "Dost"
    db_status = "✅ Sheets connected" if google_sheets.sheet else "⚠️ Local only"
    await update.message.reply_text(
        f"🕌 *Assalamualaikum {name}!*\n\n⏰ {n.strftime('%I:%M %p')} IST | 📅 {n.strftime('%d %b %Y')}\n\n"
        f"💾 *{db_status}*\n\n"
        "🧠 *Jarvis Mode Active!*\n"
        "Insight • Predict • Suggest • Auto-Alerts\n\n"
        "_Seedha type karo ya `/help`_ 👇",
        parse_mode="Markdown", reply_markup=main_kb())

async def cmd_help(update, ctx):
    await update.message.reply_text(
        "📋 *COMMANDS*\n\n"
        "*🧠 INTELLIGENCE*\n"
        "`/insight` — Daily performance score\n"
        "`/predict` — Trend forecast\n"
        "`/suggest` — Smart action suggestions\n"
        "`/night` — Night report\n\n"
        "*📝 PRODUCTIVITY*\n"
        "`/task` `/done` `/deltask` `/alltasks` `/completed`\n"
        "`/habit` `/hdone` `/delhabit`\n"
        "`/goal` `/gprogress`\n"
        "`/note` `/delnote`\n\n"
        "*📖 JOURNAL*\n"
        "`/diary` — Write/view diary (password)\n"
        "`/remember` `/recall` — Memory\n\n"
        "*💰 FINANCE*\n"
        "`/kharcha` `/budget`\n"
        "`/bill` `/bills` `/billpaid` `/delbill`\n\n"
        "*⏰ TIME*\n"
        "`/remind` `/reminders` `/delremind`\n"
        "`/cal` `/calendar` `/delcal`\n\n"
        "*💧 HEALTH*\n"
        "`/water` `/waterstatus` `/watergoal`\n\n"
        "*📊 REPORTS*\n"
        "`/briefing` `/weekly` `/yesterday`\n"
        "`/report YYYY-MM-DD`\n\n"
        "*📰 INFO*\n"
        "`/news` `/memory`\n\n"
        "*🔧 UTILS*\n"
        "`/backup` `/dbstatus` `/clear`\n\n"
        "_Natural language bhi chalti hai!_",
        parse_mode="Markdown")

async def cmd_insight(update, ctx):
    await update.message.reply_text(IntelligenceEngine.daily_insight(), parse_mode="Markdown", reply_markup=main_kb())

async def cmd_predict(update, ctx):
    await update.message.reply_text(IntelligenceEngine.predictions(), parse_mode="Markdown", reply_markup=main_kb())

async def cmd_suggest(update, ctx):
    await update.message.reply_text(IntelligenceEngine.suggestions(), parse_mode="Markdown", reply_markup=main_kb())

async def cmd_night(update, ctx):
    await update.message.reply_text(IntelligenceEngine.night_report(), parse_mode="Markdown", reply_markup=main_kb())

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
            msg = "📋 *Pending:*\n" + "\n".join(f"`/done {t['id']}` → {t['title']}" for t in pending[:10])
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("🎉 No pending tasks!")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t:
            await update.message.reply_text(f"🎉 *Done!* {t['title']}", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Not found or already done!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID!")

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
    await update.message.reply_text("🔐 *Diary — Password Enter Karo:*", parse_mode="Markdown")
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
        await update.message.reply_text(f"{title}\n\n_Koi entry nahi._", parse_mode="Markdown")
        return

    chunks = []
    current = f"{title}\n{'━'*28}\n\n"
    for d in sorted(all_entries.keys(), reverse=True):
        block = f"📅 *{d}*\n"
        for e in all_entries[d]:
            block += f"{e.get('mood','📝')} `{e.get('time','')}` — {e.get('text','')}\n"
        block += "\n"
        if len(current) + len(block) > 3800:
            chunks.append(current)
            current = block
        else:
            current += block
    if current.strip():
        chunks.append(current)
    for i, ch in enumerate(chunks):
        kb = back_kb() if i == len(chunks) - 1 else None
        try:
            await update.message.reply_text(ch, parse_mode="Markdown", reply_markup=kb)
        except:
            await update.message.reply_text(ch, reply_markup=kb)

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
    await update.message.reply_text("🔐 *Password:*", parse_mode="Markdown")
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
            msg = "💪 *Pending:*\n" + "\n".join(f"`/hdone {h['id']}` → {h['name']}" for h in pending)
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("🎊 Sab done!")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        if ok:
            await update.message.reply_text(f"💪 Done! 🔥 Streak: {streak} days!")
        else:
            await update.message.reply_text("✅ Already done!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID!")

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
                msg += f"#{g['id']} *{g['title']}*\n`{bar}` {g['progress']}%\n\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("🎯 `/goal Learn Python`")
        return
    g = goals.add(" ".join(ctx.args))
    await update.message.reply_text(f"🎯 #{g['id']} {g['title']}\n`/gprogress {g['id']} 50`")
    await auto_backup_to_sheets()

async def cmd_gprogress(update, ctx):
    if len(ctx.args) < 2:
        await update.message.reply_text("📊 `/gprogress <id> <%>`")
        return
    try:
        g = goals.update_progress(int(ctx.args[0]), int(ctx.args[1]))
        if g:
            bar = "█" * (g['progress'] // 10) + "░" * (10 - (g['progress'] // 10))
            await update.message.reply_text(f"📊 *{g['title']}*\n`{bar}` {g['progress']}%", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Use: `/gprogress <id> <%>`")

async def cmd_remember(update, ctx):
    if not ctx.args:
        await update.message.reply_text("🧠 `/remember Text`")
        return
    memory.add_fact(" ".join(ctx.args))
    await update.message.reply_text("🧠 Yaad! ✅")
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
    txt = f"🌅 *MORNING BRIEFING*\n⏰ {n.strftime('%I:%M %p')} | 📅 {n.strftime('%d %b')}\n\n"
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
    txt += f"\n💧 Water: {water.today_total()}/{water.goal()}ml"

    # Add today's calendar
    cal = calendar.today_events()
    if cal:
        txt += "\n\n📅 *Aaj ke events:*\n" + "\n".join(f"  • {e.get('time','')} {e['title']}" for e in cal)

    # Suggestions
    sugg = IntelligenceEngine.suggestions()
    if "✅ Sab kuch on track" not in sugg:
        # extract first 2 actionable lines
        suggestion_lines = [l for l in sugg.split("\n") if l.strip().startswith(("•", "🔴", "💳", "💧", "⚠️"))]
        if suggestion_lines:
            txt += "\n\n🎯 *Top priorities:*\n" + "\n".join(suggestion_lines[:3])
    return txt

async def cmd_briefing(update, ctx):
    txt = await _build_briefing_text()
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_weekly(update, ctx):
    n = now_ist()
    week_start = n.date() - timedelta(days=n.weekday())
    msg = f"📊 *WEEKLY REPORT*\n📅 {week_start.strftime('%d %b')} - {n.strftime('%d %b %Y')}\n\n"
    tw = tasks.get_weekly_summary()
    msg += f"📋 *TASKS*\n   ✅ Done: {sum(v['done'] for v in tw.values())}\n"
    msg += f"   ➕ Created: {sum(v['created'] for v in tw.values())}\n"
    msg += f"   ⏳ Pending: {len(tasks.pending())}\n\n"
    msg += "💪 *HABITS*\n"
    for h in habits.all():
        msg += f"   {h['emoji']} {h['name']} — 🔥 {h.get('streak', 0)}d\n"
    msg += f"\n💰 *EXPENSES*\n   Mahina: ₹{expenses.month_total():.0f}\n   Aaj: ₹{expenses.today_total():.0f}\n"
    bl = expenses.budget_left()
    if bl is not None:
        msg += f"   Budget left: ₹{bl:.0f}\n"
    week_water = water.week_summary()
    msg += f"\n💧 *WATER*\n   Aaj: {water.today_total()}/{water.goal()}ml\n   Week total: {sum(week_water.values())}ml\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_report(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📋 `/report YYYY-MM-DD`", parse_mode="Markdown")
        return
    target = ctx.args[0]
    try:
        datetime.strptime(target, "%Y-%m-%d")
    except:
        await update.message.reply_text("❌ Use: YYYY-MM-DD")
        return
    msg = f"📋 *REPORT — {target}*\n━━━━━━━━━━━━━━━━━━\n\n"
    td = tasks.done_on(target)
    msg += f"📋 Tasks done: {len(td)}\n"
    if td:
        msg += "  " + "\n  ".join(f"✓ {t['title']}" for t in td[:5]) + "\n"
    rems = reminders.get_by_date(target)
    msg += f"\n⏰ Reminders: {len(rems)}\n"
    exp = expenses.get_by_date(target)
    msg += f"\n💰 Kharcha: ₹{sum(e['amount'] for e in exp):.0f}\n"
    if exp:
        msg += "  " + "\n  ".join(f"₹{e['amount']:.0f} — {e['desc'][:25]}" for e in exp[:5]) + "\n"
    de = diary.get(target)
    if de:
        msg += f"\n📖 Diary:\n" + "\n".join(f"  🕐 {e['time']} — {e['text'][:50]}" for e in de[:3])
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_news(update, ctx):
    await update.message.reply_text("📰 *Category:*", parse_mode="Markdown", reply_markup=news_kb())

async def cmd_clear(update, ctx):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Clear", callback_data="confirm_clear_chat"),
                                InlineKeyboardButton("❌ Cancel", callback_data="menu")]])
    await update.message.reply_text(f"🧹 *Clear chat history?*\n✅ Tasks/data SAFE", parse_mode="Markdown", reply_markup=kb)

async def cmd_alltasks(update, ctx):
    all_t = tasks.all_tasks()
    if not all_t:
        await update.message.reply_text("📋 No tasks!")
        return
    p = tasks.pending()
    c = tasks.completed_tasks()
    txt = f"📋 *ALL ({len(all_t)})*\n⏳ {len(p)} | ✅ {len(c)}\n\n"
    if p:
        txt += "*Pending:*\n" + "\n".join(f"#{t['id']} {t['title']}" for t in p[:10]) + "\n"
    if c:
        txt += "\n*Done:*\n" + "\n".join(f"✓ #{t['id']} {t['title']}" for t in c[-5:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed(update, ctx):
    c = tasks.completed_tasks()
    if not c:
        await update.message.reply_text("✅ No completed!")
        return
    txt = f"✅ *COMPLETED ({len(c)})*\n\n" + "\n".join(f"✓ #{t['id']} {t['title']}" for t in c[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_yesterday(update, ctx):
    yd = yesterday_str()
    td = tasks.done_on(yd)
    exp = expenses.get_by_date(yd)
    de = diary.get(yd)
    hl = habits.get_logs_by_date(yd)
    hd = [h for h in habits.all() if h["id"] in hl]
    txt = f"📅 *YESTERDAY ({yd})*\n━━━━━━━━━━━━━━━━━━\n\n"
    txt += f"✅ Tasks: {len(td)}\n"
    if td:
        txt += "  " + "\n  ".join(f"• {t['title']}" for t in td[:5]) + "\n"
    txt += f"\n💪 Habits: {len(hd)}/{len(habits.all())}\n"
    if hd:
        txt += "  " + ", ".join(f"{h['emoji']}{h['name']}" for h in hd) + "\n"
    txt += f"\n💰 ₹{sum(e['amount'] for e in exp):.0f}\n"
    if de:
        txt += f"\n📖 {de[0]['text'][:80]}"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_memory(update, ctx):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("🧠 No memories!")
        return
    txt = "🧠 *MEMORY*\n━━━━━━━━━━━━━━━━━━\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_dbstatus(update, ctx):
    lines = []
    if google_sheets.sheet:
        lines.append("✅ *Sheets: CONNECTED*")
    else:
        lines.append("❌ *Sheets: NOT CONNECTED*")
    lines.append(f"\n⏰ Reminders: {len(reminders.all_active())}")
    lines.append(f"📋 Tasks: {len(tasks.all_tasks())}")
    lines.append(f"📖 Diary: {sum(len(v) for v in diary.store.data.get('entries', {}).values())}")
    lines.append(f"💰 Expenses: {len(expenses.store.data.get('list', []))}")
    lines.append(f"💪 Habits: {len(habits.all())}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_backup(update, ctx):
    await update.message.reply_text("📤 Backing up...")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, google_sheets.full_sync)
    await update.message.reply_text(result)

async def cmd_remind(update, ctx):
    now = now_ist()
    if not ctx.args:
        await update.message.reply_text(
            f"⏰ Abhi: *{now.strftime('%I:%M %p')}*\n\n"
            "`/remind 2m Test`\n`/remind 30m Chai`\n`/remind 15:30 Doctor`\n"
            "`/remind 8:00 Uthna daily`",
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
                await update.message.reply_text("❌ Invalid time!")
                return
        else:
            await update.message.reply_text("❌ Format galat!")
            return
    else:
        await update.message.reply_text("❌ Format: `/remind 2m Test`")
        return
    r = reminders.add(update.effective_chat.id, text, remind_at, repeat)
    await update.message.reply_text(f"✅ ⏰ {remind_at} — {text}\n🆔 `#{r['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_reminders_list(update, ctx):
    active = reminders.all_active()
    n = now_ist()
    if not active:
        await update.message.reply_text(f"⏰ No reminders! Abhi: *{n.strftime('%I:%M %p')}*", parse_mode="Markdown")
        return
    txt = f"⏰ *REMINDERS ({len(active)})*\nAbhi: *{n.strftime('%I:%M %p')}*\n\n"
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
            await update.message.reply_text("🗑 Deleted!")
        else:
            await update.message.reply_text("❌ Not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid!")

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
    await update.message.reply_text(
        f"💧 +{ml}ml | {total}/{goal}ml ({pct}%)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💧 +250", callback_data="water_250"),
             InlineKeyboardButton("💧 +500", callback_data="water_500")]
        ]))
    await auto_backup_to_sheets()

async def cmd_water_status(update, ctx):
    total = water.today_total()
    goal = water.goal()
    pct = min(100, int(total / goal * 100)) if goal else 0
    await update.message.reply_text(f"💧 {total}/{goal}ml ({pct}%)")

async def cmd_water_goal(update, ctx):
    if not ctx.args:
        await update.message.reply_text(f"Current: {water.goal()}ml\n`/watergoal 2500`")
        return
    try:
        water.set_goal(int(ctx.args[0]))
        await update.message.reply_text(f"✅ Goal: {ctx.args[0]}ml")
    except:
        pass

async def cmd_bill(update, ctx):
    if not ctx.args or len(ctx.args) < 3:
        await update.message.reply_text("💳 `/bill Internet 999 15`")
        return
    try:
        b = bills.add(ctx.args[0], float(ctx.args[1]), int(ctx.args[2]))
        await update.message.reply_text(f"✅ {b['name']} ₹{b['amount']:.0f} (Day {b['due_day']})")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ `/bill Name Amount DueDay`")

async def cmd_bills_list(update, ctx):
    all_b = bills.all_active()
    if not all_b:
        await update.message.reply_text("💳 No bills!")
        return
    txt = "💳 *BILLS*\n\n"
    for b in all_b:
        s = "✅" if bills.is_paid_this_month(b["id"]) else "⏳"
        txt += f"{s} #{b['id']} *{b['name']}* — ₹{b['amount']:.0f} (Day {b['due_day']})\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_bill_paid(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/billpaid <id>`")
        return
    try:
        if bills.mark_paid(int(ctx.args[0])):
            await update.message.reply_text("✅ Paid!")
        else:
            await update.message.reply_text("❌ Not found / already paid!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid!")

async def cmd_del_bill(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delbill <id>`")
        return
    try:
        if bills.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Deleted!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid!")

async def cmd_cal(update, ctx):
    if not ctx.args:
        await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`\n`/cal aaj Doctor`\n`/cal kal Call`")
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
        await update.message.reply_text("❌ Use date format")
        return
    t_match = _re.search(r'(\d{1,2}:\d{2})', title)
    if t_match:
        event_time = t_match.group(1)
        title = title.replace(event_time, "").strip()
    try:
        date.fromisoformat(date_str)
        e = calendar.add(title, date_str, event_time)
        await update.message.reply_text(f"📅 {title} — {date_str}" + (f" ⏰{event_time}" if event_time else ""))
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid date")

async def cmd_cal_list(update, ctx):
    upc = calendar.upcoming(30)
    if not upc:
        await update.message.reply_text("📅 No upcoming events!")
        return
    txt = "📅 *UPCOMING*\n\n"
    for e in upc[:15]:
        flag = "🔴 TODAY" if e["date"] == today_str() else "📆"
        ts = f" @ {e['time']}" if e.get("time") else ""
        txt += f"{flag} {e['date']}{ts} — {e['title']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_del_cal(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delcal <id>`")
        return
    try:
        if calendar.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Deleted!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid!")

# ═══════════════════════════════════════════════════════════════════
# CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════════════
async def callback_handler(update, ctx):
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
            log.error(f"Briefing: {e}")
            await message.edit_text("❌ Try `/briefing`", reply_markup=back_kb())
    elif d == "night_report":
        await message.edit_text(IntelligenceEngine.night_report(), parse_mode="Markdown", reply_markup=back_kb())
    elif d == "insight":
        await message.edit_text(IntelligenceEngine.daily_insight(), parse_mode="Markdown", reply_markup=back_kb())
    elif d == "predict":
        await message.edit_text(IntelligenceEngine.predictions(), parse_mode="Markdown", reply_markup=back_kb())
    elif d == "suggest":
        await message.edit_text(IntelligenceEngine.suggestions(), parse_mode="Markdown", reply_markup=back_kb())
    elif d == "tasks":
        pending = tasks.pending()
        if not pending:
            await message.edit_text("🎉 No pending!", reply_markup=back_kb())
            return
        txt = "📋 *PENDING*\n\n"
        for t in pending[:10]:
            i = "🔴" if t['priority']=='high' else "🟡" if t['priority']=='medium' else "🟢"
            txt += f"{i} #{t['id']} {t['title']}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "habits":
        done, pending = habits.today_status()
        txt = "💪 *HABITS*\n\n"
        if done:
            txt += "✅ Done:\n" + "\n".join(f"  {h['emoji']} {h['name']} 🔥{h.get('streak',0)}d" for h in done) + "\n\n"
        if pending:
            txt += "⏳ Pending:\n" + "\n".join(f"  {h['emoji']} {h['name']} `/hdone {h['id']}`" for h in pending)
        if not done and not pending:
            txt += "_Use `/habit` to add._"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "diary_write":
        ctx.user_data["awaiting_diary_entry"] = True
        await message.edit_text(
            "📖 *Diary likho:*\n\n_Neeche type karo — save ho jayegi!_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="menu")]])
        )
    elif d == "goals":
        ag = goals.active()
        cg = goals.completed()
        if not ag and not cg:
            await message.edit_text("🎯 No goals!", reply_markup=back_kb())
            return
        txt = "🎯 *GOALS*\n\n"
        if ag:
            txt += "*Active:*\n"
            for g in ag[:5]:
                bar = "█" * (g['progress'] // 10) + "░" * (10 - (g['progress'] // 10))
                txt += f"#{g['id']} *{g['title']}*\n`{bar}` {g['progress']}%\n\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "expenses":
        bl = expenses.budget_left()
        txt = f"💰 *EXPENSES*\n\nAaj: ₹{expenses.today_total():.0f}\nMahina: ₹{expenses.month_total():.0f}"
        if bl is not None:
            txt += f"\nBudget left: ₹{bl:.0f}"
        cats = expenses.category_breakdown_month()
        if cats:
            txt += "\n\n*Categories:*\n" + "\n".join(f"  • {k}: ₹{v:.0f}" for k, v in sorted(cats.items(), key=lambda x: -x[1])[:5])
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "notes":
        ns = notes.recent(10)
        if not ns:
            await message.edit_text("📝 No notes!", reply_markup=back_kb())
            return
        txt = "📝 *NOTES*\n\n" + "\n".join(f"#{n['id']} {n['text'][:50]}" for n in ns)
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "memory":
        facts = memory.get_all_facts()
        if not facts:
            await message.edit_text("🧠 Empty!", reply_markup=back_kb())
            return
        txt = "🧠 *MEMORY*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-10:])
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "yesterday":
        yd = yesterday_str()
        td = tasks.done_on(yd)
        exp = expenses.get_by_date(yd)
        de = diary.get(yd)
        txt = f"📊 *YESTERDAY ({yd})*\n\n✅ Tasks: {len(td)}\n💰 ₹{sum(e['amount'] for e in exp):.0f}\n"
        if de:
            txt += f"📖 {de[0]['text'][:60]}"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "weekly_report":
        tw = tasks.get_weekly_summary()
        td_total = sum(v["done"] for v in tw.values())
        tc_total = sum(v["created"] for v in tw.values())
        txt = f"📈 *WEEKLY*\n\n📋 Tasks: ✅{td_total} | ➕{tc_total}\n\n"
        for d_key in sorted(tw.keys(), reverse=True):
            v = tw[d_key]
            ed = sum(e["amount"] for e in expenses.get_by_date(d_key))
            txt += f"{d_key}: ✅{v['done']} | ₹{ed:.0f}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "news_menu":
        await message.edit_text("📰 *Category:*", parse_mode="Markdown", reply_markup=news_kb())
    elif d.startswith("news_"):
        cat = d.split("_", 1)[1]
        items = news_store.get(cat, 5)
        if not items:
            await message.edit_text("📰 Unavailable!", reply_markup=back_kb())
            return
        txt = f"📰 *{cat.upper()}*\n\n" + "\n".join(f"• {i['title']}" for i in items)
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "water_status":
        total = water.today_total()
        goal = water.goal()
        pct = min(100, int(total / goal * 100)) if goal else 0
        await message.edit_text(f"💧 *WATER*\n\n{total}/{goal}ml ({pct}%)", parse_mode="Markdown", reply_markup=back_kb())
    elif d.startswith("water_") and d.split("_")[1].isdigit():
        water.add(int(d.split("_")[1]))
        await message.edit_text(f"💧 +{d.split('_')[1]}ml | {water.today_total()}/{water.goal()}ml", reply_markup=back_kb())
        await auto_backup_to_sheets()
    elif d == "bills_menu":
        all_b = bills.all_active()
        if not all_b:
            await message.edit_text("💳 No bills!", reply_markup=back_kb())
            return
        txt = "💳 *BILLS*\n\n"
        for b in all_b:
            s = "✅" if bills.is_paid_this_month(b["id"]) else "⏳"
            txt += f"{s} *{b['name']}* — ₹{b['amount']:.0f} (Day {b['due_day']})\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "cal_menu":
        upc = calendar.upcoming(30)
        if not upc:
            await message.edit_text("📅 No events!", reply_markup=back_kb())
            return
        txt = "📅 *UPCOMING*\n\n"
        for e in upc[:15]:
            flag = "🔴 TODAY" if e["date"] == today_str() else "📆"
            ts = f" @ {e['time']}" if e.get("time") else ""
            txt += f"{flag} {e['date']}{ts} — {e['title']}\n"
        await message.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())
    elif d == "clear_chat":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅", callback_data="confirm_clear_chat"),
                                    InlineKeyboardButton("❌", callback_data="menu")]])
        await message.edit_text(f"🧹 Clear {chat_hist.count()} messages?", reply_markup=kb)
    elif d == "confirm_clear_chat":
        count = chat_hist.clear()
        await message.edit_text(f"🧹 Cleared {count}! Data SAFE!", reply_markup=main_kb())
    elif d == "backup_now":
        await message.edit_text("📤 Backing up...", reply_markup=back_kb())
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, google_sheets.full_sync)
        await message.edit_text(result, reply_markup=main_kb())
    elif d.startswith("done_"):
        t = tasks.complete(int(d.split("_")[1]))
        if t:
            await message.edit_text(f"🎉 {t['title']}", reply_markup=back_kb())
        await auto_backup_to_sheets()
    elif d.startswith("habit_"):
        hid = int(d.split("_")[1])
        ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"] == hid), None)
        if ok and h:
            await message.edit_text(f"💪 {h['name']} 🔥{streak}d", reply_markup=back_kb())
        else:
            await message.edit_text("✅ Already done!", reply_markup=back_kb())
        await auto_backup_to_sheets()
    elif d.startswith("remind_done_"):
        reminders.mark_fired(int(d.split("_")[2]))
        await message.edit_text("✅ Done!", reply_markup=back_kb())
        await auto_backup_to_sheets()
    elif d.startswith("remind_snooze_"):
        rid = int(d.split("_")[2])
        snooze = (now_ist() + timedelta(minutes=10)).strftime("%H:%M")
        rl = [r for r in reminders.get_all() if r["id"] == rid]
        if rl:
            reminders.add(message.chat_id, rl[0]["text"], snooze, "once")
            reminders.mark_fired(rid)
        await message.edit_text(f"😴 Snoozed → {snooze}", reply_markup=back_kb())
        await auto_backup_to_sheets()

# ═══════════════════════════════════════════════════════════════════
# MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update, ctx):
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
            parse_mode="Markdown", reply_markup=main_kb()
        )
        await auto_backup_to_sheets()
        return

    ctx.user_data.pop("diary_view", None)
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ai_chat(user_msg, update.effective_chat.id)
    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except:
        await update.message.reply_text(reply)

# ═══════════════════════════════════════════════════════════════════
# JOBS
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
            if r["repeat"] == "daily":
                repeat_note = "\n🔁 _Kal bhi!_"
            elif r["repeat"] == "weekly":
                repeat_note = "\n📅 _Agli hafte!_"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Done", callback_data=f"remind_done_{r['id']}"),
                InlineKeyboardButton("⏰ Snooze 10m", callback_data=f"remind_snooze_{r['id']}")
            ]])
            text = (f"🚨🔔 *ALARM!* 🔔🚨\n{'═'*25}\n⏰ *{r['time']} BAJ GAYE!*\n"
                    f"{'═'*25}\n\n📢 *{r['text'].upper()}*{repeat_note}")
            await context.bot.send_message(
                chat_id=r["chat_id"], text=text, parse_mode="Markdown",
                disable_notification=False, reply_markup=kb
            )
            reminders.mark_fired(r["id"])
            await asyncio.sleep(1)
        except Exception as e:
            log.error(f"❌ Reminder #{r['id']}: {e}")
            try:
                reminders.mark_fired(r["id"])
            except:
                pass

async def proactive_job(context):
    """Auto-alerts engine — runs every 30 minutes"""
    if not ADMIN_CHAT_ID:
        return
    try:
        await IntelligenceEngine.proactive_check(context.bot, int(ADMIN_CHAT_ID))
    except Exception as e:
        log.warning(f"Proactive: {e}")

async def morning_briefing_job(context):
    """8 AM — auto morning briefing"""
    if not ADMIN_CHAT_ID:
        return
    try:
        txt = await _build_briefing_text()
        await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=txt, parse_mode="Markdown")
    except Exception as e:
        log.warning(f"Briefing job: {e}")

async def night_report_job(context):
    """10 PM — auto night report"""
    if not ADMIN_CHAT_ID:
        return
    try:
        txt = IntelligenceEngine.night_report()
        await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=txt, parse_mode="Markdown")
    except Exception as e:
        log.warning(f"Night job: {e}")

async def bill_due_job(context):
    if now_ist().strftime("%H:%M") != "09:00":
        return
    due = bills.due_soon(3)
    if not due or not ADMIN_CHAT_ID:
        return
    txt = "💳 *BILL DUE*\n\n" + "\n".join(f"⚠️ {b['name']} ₹{b['amount']:.0f}" for b in due)
    try:
        await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=txt, parse_mode="Markdown")
    except:
        pass

_last_auto_backup = 0
_BACKUP_THROTTLE = 30

async def auto_backup_to_sheets():
    global _last_auto_backup
    now_ts = time.time()
    if now_ts - _last_auto_backup < _BACKUP_THROTTLE:
        return
    _last_auto_backup = now_ts
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, google_sheets.full_sync)

async def scheduled_backup_job(context):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, google_sheets.full_sync)
    log.info(f"🕒 Scheduled: {result}")

async def daily_log_job(context):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, google_sheets.save_daily_log)

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    n = now_ist()
    log.info("=" * 55)
    log.info(f"🤖 Bot v15 — JARVIS EDITION")
    log.info(f"⏰ IST: {n.strftime('%Y-%m-%d %I:%M %p')}")
    log.info(f"📊 Sheets: {'✅' if google_sheets.sheet else '❌'}")
    log.info(f"🔑 Gemini: {'✅' if GEMINI_API_KEY else '❌'} | 🎤 Groq: {'✅' if GROQ_API_KEY else '❌'}")
    log.info("=" * 55)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    async def post_init(app):
        try:
            if ADMIN_CHAT_ID:
                await app.bot.send_message(
                    chat_id=int(ADMIN_CHAT_ID),
                    text=f"🤖 *Bot Restart!*\n⏰ {now_ist().strftime('%I:%M %p')} IST\n\n🧠 Jarvis Mode Active!",
                    parse_mode="Markdown"
                )
        except Exception as e:
            log.warning(f"Startup notify: {e}")

    app.post_init = post_init

    commands = [
        ("start", cmd_start), ("help", cmd_help),
        ("insight", cmd_insight), ("predict", cmd_predict), ("suggest", cmd_suggest), ("night", cmd_night),
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("habit", cmd_habit), ("hdone", cmd_hdone), ("delhabit", cmd_delhabit),
        ("kharcha", cmd_kharcha), ("budget", cmd_budget),
        ("goal", cmd_goal), ("gprogress", cmd_gprogress),
        ("remember", cmd_remember), ("recall", cmd_recall),
        ("note", cmd_note), ("delnote", cmd_delnote),
        ("briefing", cmd_briefing), ("weekly", cmd_weekly), ("report", cmd_report),
        ("news", cmd_news), ("clear", cmd_clear),
        ("alltasks", cmd_alltasks), ("completed", cmd_completed), ("yesterday", cmd_yesterday),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list), ("delremind", cmd_delremind),
        ("water", cmd_water), ("waterstatus", cmd_water_status), ("watergoal", cmd_water_goal),
        ("bill", cmd_bill), ("bills", cmd_bills_list), ("billpaid", cmd_bill_paid), ("delbill", cmd_del_bill),
        ("cal", cmd_cal), ("calendar", cmd_cal_list), ("delcal", cmd_del_cal),
        ("memory", cmd_memory), ("backup", cmd_backup), ("dbstatus", cmd_dbstatus),
    ]
    for cmd, h in commands:
        app.add_handler(CommandHandler(cmd, h))

    diary_conv = ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary), CommandHandler("diaryview", cmd_diary_view)],
        states={
            DIARY_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, diary_conv_cancel)],
        },
        fallbacks=[CommandHandler("cancel", diary_conv_cancel)],
        per_user=True, per_chat=True, conversation_timeout=60,
    )
    app.add_handler(diary_conv)

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=15)
        app.job_queue.run_repeating(proactive_job, interval=1800, first=300)  # 30 min
        app.job_queue.run_repeating(bill_due_job, interval=3600, first=300)
        app.job_queue.run_repeating(scheduled_backup_job, interval=3600, first=120)
        app.job_queue.run_daily(daily_log_job, time=dt_module.time(hour=21, minute=0, tzinfo=IST))
        app.job_queue.run_daily(morning_briefing_job, time=dt_module.time(hour=8, minute=0, tzinfo=IST))
        app.job_queue.run_daily(night_report_job, time=dt_module.time(hour=22, minute=0, tzinfo=IST))
        log.info("⏰ All jobs scheduled (Reminders/Proactive/Bills/Backup/Briefing/NightReport)")

    log.info("✅ Bot ready! /help")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
