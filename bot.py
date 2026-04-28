#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v7.0 FINAL + GOOGLE SHEETS          ║
║  + ALL ORIGINAL FEATURES INTACT                                 ║
║  + BUTTONS FIXED | REPORT COMMANDS | WEEKLY SUMMARY            ║
║  + GOOGLE SHEETS BACKUP | REMINDERS | TASKS | HABITS           ║
║  + DIARY | EXPENSES | GOALS | WATER | BILLS | CALENDAR         ║
║  + MEMORY | NOTES | NEWS | CHAT HISTORY                        ║
║  + HINGLISH REPLIES | 4-LAYER FALLBACK                         ║
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
    CallbackQueryHandler, filters, ContextTypes
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

SECRET_CODE = "Rk1996"

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
# DATABASE (MongoDB + Local JSON)
# ═══════════════════════════════════════════════════════════════════
class Database:
    def __init__(self):
        self.use_mongo = HAS_MONGO and bool(MONGO_URI)
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)
        if self.use_mongo:
            try:
                self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
                self.client.admin.command("ping")
                self.db = self.client["telegram_bot"]
                log.info("✅ MongoDB connected!")
            except Exception as e:
                log.warning(f"⚠️ MongoDB failed: {e}")
                self.use_mongo = False

    def load(self, collection, default=None):
        if default is None:
            default = {}
        if self.use_mongo:
            try:
                doc = self.db[collection].find_one({"_id": "data"})
                if doc:
                    doc.pop("_id", None)
                    return doc
            except:
                pass
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return default

    def save(self, collection, data):
        if self.use_mongo:
            try:
                self.db[collection].replace_one({"_id": "data"}, {"_id": "data", **data}, upsert=True)
            except:
                pass
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except:
            pass

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
# HUGGINGFACE API
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
# LOCAL SMART REPLIES (4th Layer Fallback)
# ═══════════════════════════════════════════════════════════════════
def local_smart_reply(user_msg):
    msg = user_msg.lower().strip()
    n = now_ist()
    
    if any(w in msg for w in ["time", "baje", "kitne baje", "time kya"]):
        return f"Abhi {n.strftime('%I:%M %p')} baj rahe hain bhai! ⏰"
    
    if any(w in msg for w in ["date", "aaj kya", "tarikh"]):
        return f"Aaj {n.strftime('%A, %d %B %Y')} hai 📅"
    
    if any(w in msg for w in ["hello", "hi", "hey", "namaste", "assalam"]):
        return "Namaste bhai! Main tera dost hoon. Kaisa chal raha hai? 🫡"
    
    if any(w in msg for w in ["kaise ho", "how are you", "kya haal"]):
        return "Main badiya hoon bhai! Tu suna, kya chal raha hai? 😊"
    
    if any(w in msg for w in ["thank", "shukriya", "thanks"]):
        return "Welcome bhai! 😊 Koi aur help chahiye toh batana!"
    
    if any(w in msg for w in ["bye", "allah hafiz", "good night"]):
        return "Allah Hafiz bhai! 🙏 Apna khayal rakhna!"
    
    if any(w in msg for w in ["task", "kaam"]):
        pending = tasks.pending()
        if pending:
            return f"📋 Tere {len(pending)} tasks pending hain. `/tasks` se dekh sakte ho!"
        return "🎉 Koi task pending nahi hai! Well done!"
    
    if any(w in msg for w in ["kharcha", "expense"]):
        return f"💰 Aaj ka kharcha: ₹{expenses.today_total():.0f} | Mahina: ₹{expenses.month_total():.0f}"
    
    if any(w in msg for w in ["water", "paani"]):
        total = water.today_total()
        goal = water.goal()
        remaining = goal - total
        if remaining > 0:
            return f"💧 Aaj {total}ml/{goal}ml paani piya hai. {remaining}ml aur pi lo!"
        return f"💧 Badhiya! Aaj ka {goal}ml target complete hai! 👍"
    
    if any(w in msg for w in ["help", "madad", "command"]):
        return """📋 MAIN COMMANDS:
/task, /done — Tasks
/habit, /hdone — Habits
/diary — Diary
/kharcha — Expenses
/remind — Reminders
/water — Water intake
/weekly — Weekly report
/report YYYY-MM-DD — Date report"""
    
    return None

def emergency_fallback(user_msg):
    responses = [
        "Han bhai, main sun raha hu! 👂 Kya kehna chahte ho?",
        "Bilkul sahi kaha bhai! Main agree hu. Aage batao. 🙌",
        "Hmm, interesting point hai. Main samajh gaya. Continue karo. 🤔",
        "Bilkul! Tere saath hu main. Tu jo bole, main sun raha hu. 💪",
        "Bhai, main yahan hu tere liye! Kuch bhi help chahiye, bata de. 🫂"
    ]
    return random.choice(responses)

# ═══════════════════════════════════════════════════════════════════
# SMART FALLBACK (Hinglish)
# ═══════════════════════════════════════════════════════════════════
def smart_fallback(user_msg):
    msg = user_msg.lower()
    n = now_ist()
    
    if any(w in msg for w in ["time", "baje", "kitne baje", "time kya"]):
        return f"⏰ Abhi *{n.strftime('%I:%M %p')}* baj rahe hain (IST)"
    
    if any(w in msg for w in ["date", "aaj kya", "tarikh", "aaj kitni"]):
        return f"📅 Aaj *{n.strftime('%A, %d %B %Y')}* hai"
    
    if any(w in msg for w in ["hello", "hi", "assalam", "namaste", "hey"]):
        return "🕌 Assalamualaikum! Main tera dost hoon. Bata kya help chahiye?"
    
    if any(w in msg for w in ["kaise ho", "how are", "kya haal"]):
        return "😊 Main badiya hoon! Tu suna, kya chal raha hai?"
    
    if any(w in msg for w in ["thank", "shukriya", "thanks"]):
        return "🤗 Welcome bhai! Aur koi help chahiye toh batana!"
    
    if any(w in msg for w in ["bye", "allah hafiz", "good night", "shabba"]):
        return "🌙 Allah Hafiz! Apna khayal rakhna."
    
    replies = [
        "🙏 Thoda busy hoon abhi. `/help` se commands dekh lo!",
        "😅 Model unavailable. Try `/task`, `/remind`, or `/help`",
        "🤖 Response nahi aa pa raha. Kuch commands use karo!",
    ]
    return random.choice(replies)

# ═══════════════════════════════════════════════════════════════════
# MAIN AI PIPELINE (4-Layer Fallback)
# ═══════════════════════════════════════════════════════════════════
def get_ai_reply(user_msg, chat_id=None, system_ctx=None):
    if not system_ctx:
        system_ctx = build_system_prompt()
    
    hinglish_prompt = f"{system_ctx}\n\nUser: {user_msg}\n\nHinglish mein short reply (2-3 lines, friendly, like a real friend):"
    
    # Layer 1: Gemini
    reply = call_gemini(hinglish_prompt)
    if reply:
        return reply
    
    # Layer 2: HuggingFace
    reply = call_huggingface(hinglish_prompt)
    if reply:
        return reply + "\n\n_⚡ (free model)_"
    
    # Layer 3: Local Smart Replies
    reply = local_smart_reply(user_msg)
    if reply:
        return reply + "\n\n_📱 (offline)_"
    
    # Layer 4: Emergency Fallback
    return emergency_fallback(user_msg)

# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT BUILDER (Hinglish)
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

    tasks_s = "\n".join(f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}" for t in tp[:5]) or "Koi nahi"
    yd_s = "\n".join(f"  ✓ {t['title']}" for t in yd[:3]) or "Koi nahi"
    h_done = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    h_pend = ", ".join(f"{h['name']}" for h in hp) or "Sab ho gaye!"
    goals_s = "\n".join(f"  🎯 {g['title']} ({g['progress']}%)" for g in ag[:4]) or "Koi nahi"
    diary_s = "\n".join(f"  {e['time']} {e['text']}" for e in td_d[-2:]) or "Kuch nahi"
    budget_s = f"Budget baaki: ₹{bl:.0f}" if bl is not None else ""
    water_pct = int(water_today / water_goal * 100) if water_goal else 0
    bills_s = "\n".join(f"  ⚠️ {b['name']} ₹{b['amount']:.0f}" for b in due_b) or "Koi nahi"
    cal_s = "\n".join(f"  📅 {e['time'] or ''} {e['title']}" for e in cal_today) or "Koi nahi"

    return f"""Tu mera dost hai. HINGLISH mein baat kar (Hindi+English mix).

EXAMPLES:
- "Bhai, tera task ho gaya!"
- "Chalo, ab water pi le bhai!"
- "Bilkul sahi, main help karta hu!"

RULES:
- NEVER say "as an AI"
- Short reply (2-3 lines max)
- Friendly, casual, like a real friend
- Use "bhai", "yaar", "chalo" like normal conversation

⚠️ REAL TIME: {now_label} ({current_time})
• Aaj ki date: {today_str()}

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

Reply in Hinglish:"""

# ═══════════════════════════════════════════════════════════════════
# DATA STORES (ALL ORIGINAL FEATURES)
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
        log.info(f"✅ Reminder CREATED: #{r['id']} | chat={chat_id} | time={remind_at}")
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
                diff_seconds = (now.replace(tzinfo=None) - r_dt).total_seconds()
                if 0 <= diff_seconds < 120:
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
                if today_d <= due_date <= today_d + timedelta(days=days_ahead):
                    result.append({**b, "due_date": due_date.isoformat()})
            except:
                continue
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
# GOOGLE SHEETS BACKUP (FULLY WORKING)
# ═══════════════════════════════════════════════════════════════════

class GoogleSheetsBackup:
    def __init__(self):
        self.sheet = None
        if not HAS_GSHEETS:
            log.warning("⚠️ gspread not installed!")
            return
        
        creds_json = os.environ.get("GOOGLE_CREDS_JSON", "") or os.environ.get("Google_CREDS_JSON", "")
        
        if not creds_json:
            log.warning("⚠️ GOOGLE_CREDS_JSON not found!")
            return
        
        try:
            creds_dict = json.loads(creds_json)
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            self.sheet = client.open_by_key("1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")
            log.info("✅ Google Sheets connected!")
            self.ensure_worksheets()
        except Exception as e:
            log.error(f"❌ Google Sheets error: {e}")
    
    def ensure_worksheets(self):
        if not self.sheet:
            return
        
        sheets_config = {
            "Tasks": ["ID", "Title", "Priority", "Status", "Created At", "Completed At"],
            "Reminders": ["ID", "Time", "Text", "Repeat", "Active", "Created Date"],
            "Expenses": ["Date", "Amount (₹)", "Description", "Category", "Time"],
            "Habits": ["ID", "Habit Name", "Emoji", "Current Streak", "Best Streak", "Created"],
            "Water": ["Date", "Total ML", "Goal ML", "Entries"],
            "Memory": ["Date", "Fact", "Type"],
            "Diary": ["Date", "Time", "Content", "Mood"],
            "Daily_Logs": ["Date", "Tasks Done", "Tasks Pending", "Expenses (₹)", "Water ML", "Habits Done"]
        }
        
        existing = [ws.title for ws in self.sheet.worksheets()]
        
        for sheet_name, headers in sheets_config.items():
            if sheet_name not in existing:
                try:
                    ws = self.sheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
                    ws.append_row(headers)
                    log.info(f"📊 Created sheet: {sheet_name}")
                except Exception as e:
                    log.warning(f"Could not create {sheet_name}: {e}")
    
    def save_tasks(self, tasks_list):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Tasks")
            ws.clear()
            ws.append_row(["ID", "Title", "Priority", "Status", "Created At", "Completed At"])
            for task in tasks_list[-200:]:
                ws.append_row([
                    str(task.get("id", "")), task.get("title", ""), task.get("priority", "medium"),
                    "✅ Done" if task.get("done") else "⏳ Pending",
                    task.get("created", "")[:10], task.get("done_at", "")[:10] if task.get("done_at") else ""
                ])
            return True
        except Exception as e:
            log.error(f"Tasks save error: {e}")
            return False
    
    def save_reminders(self, reminders_list):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Reminders")
            ws.clear()
            ws.append_row(["ID", "Time", "Text", "Repeat", "Active", "Created Date"])
            for r in reminders_list[:100]:
                ws.append_row([
                    str(r.get("id", "")), r.get("time", ""), r.get("text", ""),
                    r.get("repeat", "once"), "✅" if r.get("active") else "❌", r.get("date", "")
                ])
            return True
        except Exception as e:
            log.error(f"Reminders save error: {e}")
            return False
    
    def save_expenses(self, expenses_list):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Expenses")
            ws.clear()
            ws.append_row(["Date", "Amount (₹)", "Description", "Category", "Time"])
            for e in expenses_list[-200:]:
                ws.append_row([
                    e.get("date", ""), str(e.get("amount", 0)), e.get("desc", ""),
                    e.get("category", "general"), e.get("time", "")
                ])
            return True
        except Exception as e:
            log.error(f"Expenses save error: {e}")
            return False
    
    def save_habits(self, habits_list):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Habits")
            ws.clear()
            ws.append_row(["ID", "Habit Name", "Emoji", "Current Streak", "Best Streak", "Created"])
            for h in habits_list:
                ws.append_row([
                    str(h.get("id", "")), h.get("name", ""), h.get("emoji", "✅"),
                    str(h.get("streak", 0)), str(h.get("best_streak", 0)), h.get("created", "")
                ])
            return True
        except Exception as e:
            log.error(f"Habits save error: {e}")
            return False
    
    def save_water(self):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Water")
            ws.clear()
            ws.append_row(["Date", "Total ML", "Goal ML", "Entries"])
            logs = water.store.data.get("logs", {})
            goal = water.goal()
            for date, entries in logs.items():
                total = sum(e["ml"] for e in entries)
                ws.append_row([date, str(total), str(goal), str(len(entries))])
            return True
        except Exception as e:
            log.error(f"Water save error: {e}")
            return False
    
    def save_memory(self, memory_facts):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Memory")
            ws.clear()
            ws.append_row(["Date", "Fact", "Type"])
            for fact in memory_facts[-100:]:
                ws.append_row([fact.get("d", ""), fact.get("f", ""), "fact"])
            return True
        except Exception as e:
            log.error(f"Memory save error: {e}")
            return False
    
    def save_diary(self):
        if not self.sheet:
            return False
        try:
            ws = self.sheet.worksheet("Diary")
            ws.clear()
            ws.append_row(["Date", "Time", "Content", "Mood"])
            entries = diary.store.data.get("entries", {})
            for date, date_entries in entries.items():
                for entry in date_entries[-10:]:
                    ws.append_row([date, entry.get("time", ""), entry.get("text", ""), entry.get("mood", "😊")])
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
            
            all_rows = ws.get_all_values()
            found = False
            for i, row in enumerate(all_rows):
                if row and row[0] == today:
                    for col, val in enumerate([tasks_done, tasks_pending, expenses_total, water_total, habits_done], start=2):
                        try:
                            ws.update_cell(i+1, col, val)
                        except:
                            pass
                    found = True
                    break
            if not found:
                ws.append_row([today, tasks_done, tasks_pending, expenses_total, water_total, habits_done])
            return True
        except Exception as e:
            log.error(f"Daily log error: {e}")
            return False
    
    def full_sync(self):
        if not self.sheet:
            return "❌ Google Sheets not connected!"
        success = []
        if self.save_tasks(tasks.all_tasks()):
            success.append("Tasks")
        if self.save_reminders(reminders.all_active()):
            success.append("Reminders")
        if self.save_expenses(expenses.store.data.get("list", [])):
            success.append("Expenses")
        if self.save_habits(habits.all()):
            success.append("Habits")
        if self.save_water():
            success.append("Water")
        if self.save_memory(memory.get_all_facts()):
            success.append("Memory")
        if self.save_diary():
            success.append("Diary")
        self.save_daily_log()
        return f"✅ Synced: {', '.join(success)} to Google Sheets!"

google_sheets = GoogleSheetsBackup()

async def auto_backup_to_sheets():
    result = google_sheets.full_sync()
    log.info(result)
    return result

# ═══════════════════════════════════════════════════════════════════
# ACTION SYSTEM
# ═══════════════════════════════════════════════════════════════════

ACTION_SYSTEM_PROMPT = """You are a JSON router. Return ONLY JSON.

Current time: {now}
Today: {today}

Actions:
REMIND - {{"time":"HH:MM","text":"...","repeat":"once"}}
ADD_TASK - {{"title":"...","priority":"medium"}}
ADD_EXPENSE - {{"amount":number,"desc":"..."}}
ADD_DIARY - {{"text":"..."}}
ADD_MEMORY - {{"fact":"..."}}
ADD_HABIT - {{"name":"..."}}
CHAT - {{}} (default)"""

def _regex_fallback(user_msg):
    lower = user_msg.lower()
    now = now_ist()
    
    if any(w in lower for w in ["remind", "alarm", "yaad dila"]):
        time_str = None
        m = _re.search(r'(\d+)\s*m', lower)
        if m:
            time_str = (now + timedelta(minutes=int(m.group(1)))).strftime("%H:%M")
        if not time_str:
            m = _re.search(r'(\d{1,2}):(\d{2})', lower)
            if m:
                time_str = f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
        if time_str:
            return {"action": "REMIND", "params": {"time": time_str, "text": user_msg, "repeat": "once"}, "reply": ""}
    
    if any(w in lower for w in ["task", "kaam", "karna hai"]):
        return {"action": "ADD_TASK", "params": {"title": user_msg, "priority": "medium"}, "reply": ""}
    
    if any(w in lower for w in ["kharcha", "rs", "rupaye"]):
        m = _re.search(r'(\d+)', lower)
        if m:
            return {"action": "ADD_EXPENSE", "params": {"amount": float(m.group(1)), "desc": user_msg}, "reply": ""}
    
    return {"action": "CHAT", "params": {}, "reply": ""}

def call_gemini_action(user_msg, now_label, today_label):
    now = now_ist()
    prompt = ACTION_SYSTEM_PROMPT.format(now=now.strftime("%H:%M"), today=today_str())
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
                return json.loads(raw)
        except:
            continue
    return _regex_fallback(user_msg)

async def execute_action(action_data, chat_id, user_msg):
    action = action_data.get("action", "CHAT")
    params = action_data.get("params", {})
    
    if action == "REMIND":
        time_str = params.get("time", "")
        text = params.get("text", "Reminder!")
        repeat = params.get("repeat", "once")
        r = reminders.add(chat_id, text, time_str, repeat)
        await auto_backup_to_sheets()
        return f"✅ Reminder set for {time_str}: {text}\nID: #{r['id']}"
    
    elif action == "ADD_TASK":
        t = tasks.add(params.get("title", user_msg[:80]), params.get("priority", "medium"))
        await auto_backup_to_sheets()
        return f"✅ Task added: #{t['id']} {t['title']}"
    
    elif action == "ADD_EXPENSE":
        amount = params.get("amount", 0)
        desc = params.get("desc", user_msg[:50])
        expenses.add(amount, desc)
        await auto_backup_to_sheets()
        return f"✅ ₹{amount:.0f} added: {desc}\nToday total: ₹{expenses.today_total():.0f}"
    
    elif action == "ADD_DIARY":
        diary.add(params.get("text", user_msg[:100]))
        await auto_backup_to_sheets()
        return f"📖 Diary saved at {now_str()}"
    
    elif action == "ADD_MEMORY":
        memory.add_fact(params.get("fact", user_msg[:200]))
        await auto_backup_to_sheets()
        return "🧠 Yaad kar liya!"
    
    elif action == "ADD_HABIT":
        h = habits.add(params.get("name", user_msg[:50]))
        await auto_backup_to_sheets()
        return f"💪 Habit added: {h['name']}\nUse /hdone {h['id']} to log"
    
    else:
        auto_extract_facts(user_msg)
        chat_hist.add("user", user_msg)
        reply = get_ai_reply(user_msg, chat_id)
        chat_hist.add("assistant", reply)
        return reply

async def ai_chat(user_msg, chat_id=None):
    if chat_id:
        action_data = call_gemini_action(user_msg, time_label(), today_str())
        return await execute_action(action_data, chat_id, user_msg)
    else:
        return get_ai_reply(user_msg)

def auto_extract_facts(text):
    triggers = ["yaad rakh", "remember", "mera naam", "meri umar", "meri job"]
    if any(kw in text.lower() for kw in triggers):
        memory.add_fact(text[:250])
        return True
    return False

# ═══════════════════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════════════════
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Briefing", callback_data="briefing"), InlineKeyboardButton("📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("💪 Habits", callback_data="habits"), InlineKeyboardButton("📖 Diary", callback_data="diary")],
        [InlineKeyboardButton("🎯 Goals", callback_data="goals"), InlineKeyboardButton("💰 Kharcha", callback_data="expenses")],
        [InlineKeyboardButton("📰 News", callback_data="news"), InlineKeyboardButton("📝 Notes", callback_data="notes")],
        [InlineKeyboardButton("💧 Water", callback_data="water"), InlineKeyboardButton("💳 Bills", callback_data="bills")],
        [InlineKeyboardButton("📅 Calendar", callback_data="calendar"), InlineKeyboardButton("📊 Weekly", callback_data="weekly")],
        [InlineKeyboardButton("📋 All Tasks", callback_data="all_tasks"), InlineKeyboardButton("✅ Completed", callback_data="completed")],
        [InlineKeyboardButton("📊 Yesterday", callback_data="yesterday"), InlineKeyboardButton("🧠 Memory", callback_data="memory")],
        [InlineKeyboardButton("📤 Backup", callback_data="backup"), InlineKeyboardButton("❓ Help", callback_data="help")],
    ])

# ═══════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def cmd_start(update, ctx):
    n = now_ist()
    name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(
        f"🕌 Assalamualaikum {name}!\n\n⏰ {n.strftime('%I:%M %p')} IST\n\n"
        "✅ AI Assistant with Hinglish replies\n"
        "✅ Tasks | Habits | Diary | Expenses\n"
        "✅ Reminders | Water | Bills | Calendar\n"
        "✅ Google Sheets Backup | Reports\n\n"
        "_Type /help or use menu_ 👇",
        parse_mode="Markdown", reply_markup=main_kb())

async def cmd_help(update, ctx):
    await update.message.reply_text(
        "📋 *COMMANDS*\n\n"
        "`/task` `/done` — Tasks\n"
        "`/habit` `/hdone` — Habits\n"
        "`/diary` — Diary\n"
        "`/kharcha` — Expenses\n"
        "`/remind` — Reminders\n"
        "`/remember` `/recall` — Memory\n"
        "`/water` — Water intake\n"
        "`/bill` — Bills\n"
        "`/cal` — Calendar\n"
        "`/news` — News\n"
        "`/weekly` — Weekly report\n"
        "`/report YYYY-MM-DD` — Date report\n"
        "`/backup` — Google Sheets backup\n\n"
        "_Mujhe Hinglish mein baat karo!_",
        parse_mode="Markdown")

async def cmd_task(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📋 `/task Kaam ka naam`")
        return
    t = tasks.add(" ".join(ctx.args))
    await update.message.reply_text(f"✅ Task: #{t['id']} {t['title']}")
    await auto_backup_to_sheets()

async def cmd_done(update, ctx):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            msg = "📋 Pending tasks:\n"
            for t in pending[:10]:
                msg += f"`/done {t['id']}` → {t['title']}\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("🎉 No pending tasks!")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t:
            await update.message.reply_text(f"🎉 Done! {t['title']}")
        else:
            await update.message.reply_text("❌ Task not found!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_diary(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📖 `/diary Aaj kya kiya?`")
        return
    diary.add(" ".join(ctx.args))
    await update.message.reply_text(f"📖 Diary saved! {now_str()}")
    await auto_backup_to_sheets()

async def cmd_habit(update, ctx):
    if not ctx.args:
        await update.message.reply_text("💪 `/habit Subah utna`")
        return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(f"💪 Habit: {h['name']}\n`/hdone {h['id']}`", parse_mode="Markdown")
    await auto_backup_to_sheets()

async def cmd_hdone(update, ctx):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            msg = "💪 Pending habits:\n"
            for h in pending:
                msg += f"`/hdone {h['id']}` → {h['name']}\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("🎊 Sab done! Great job!")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        if ok:
            await update.message.reply_text(f"💪 Done! 🔥 Streak: {streak} days!")
        else:
            await update.message.reply_text("✅ Already done today!")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid habit ID!")

async def cmd_kharcha(update, ctx):
    if len(ctx.args) < 2:
        await update.message.reply_text("💰 `/kharcha 100 Chai`")
        return
    try:
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        await update.message.reply_text(f"💰 ₹{amount:.0f} — {desc}\nToday: ₹{expenses.today_total():.0f}")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Use: `/kharcha 100 Chai`")

async def cmd_goal(update, ctx):
    if not ctx.args:
        active = goals.active()
        if active:
            msg = "🎯 *ACTIVE GOALS*\n\n"
            for g in active:
                bar = "█" * (g['progress'] // 10) + "░" * (10 - (g['progress'] // 10))
                msg += f"**{g['title']}**\n`{bar}` {g['progress']}%\n\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("🎯 `/goal Learn Python`")
        return
    g = goals.add(" ".join(ctx.args))
    await update.message.reply_text(f"🎯 Goal set: {g['title']}\nUse `/gprogress {g['id']} 50`")
    await auto_backup_to_sheets()

async def cmd_gprogress(update, ctx):
    if len(ctx.args) < 2:
        await update.message.reply_text("📊 `/gprogress 1 50`")
        return
    try:
        gid = int(ctx.args[0])
        progress = int(ctx.args[1])
        g = goals.update_progress(gid, progress)
        if g:
            bar = "█" * (g['progress'] // 10) + "░" * (10 - (g['progress'] // 10))
            await update.message.reply_text(f"📊 {g['title']}\n`{bar}` {g['progress']}%")
        else:
            await update.message.reply_text("❌ Goal not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Use: `/gprogress ID 50`")

async def cmd_remember(update, ctx):
    if not ctx.args:
        await update.message.reply_text("🧠 `/remember Mera naam Rahul hai`")
        return
    memory.add_fact(" ".join(ctx.args))
    await update.message.reply_text("🧠 Yaad kar liya!")
    await auto_backup_to_sheets()

async def cmd_recall(update, ctx):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("🧠 Kuch yaad nahi!")
        return
    msg = "🧠 *YAAD HAI:*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-15:])
    await update.message.reply_text(msg, parse_mode="Markdown")

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
    pct = int(total / goal * 100) if goal else 0
    await update.message.reply_text(f"💧 +{ml}ml | Total: {total}ml/{goal}ml ({pct}%)")
    await auto_backup_to_sheets()

async def cmd_water_status(update, ctx):
    total = water.today_total()
    goal = water.goal()
    pct = int(total / goal * 100) if goal else 0
    await update.message.reply_text(f"💧 Today: {total}ml / {goal}ml ({pct}%)")

async def cmd_water_goal(update, ctx):
    if not ctx.args:
        await update.message.reply_text(f"Current goal: {water.goal()}ml\n`/watergoal 2500`")
        return
    try:
        water.set_goal(int(ctx.args[0]))
        await update.message.reply_text(f"✅ Goal set to {ctx.args[0]}ml")
    except:
        pass

async def cmd_bill(update, ctx):
    if len(ctx.args) < 3:
        await update.message.reply_text("💳 `/bill Internet 999 15`")
        return
    try:
        b = bills.add(ctx.args[0], float(ctx.args[1]), int(ctx.args[2]))
        await update.message.reply_text(f"✅ Bill: {b['name']} ₹{b['amount']:.0f} due on {b['due_day']}th")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Use: `/bill Name Amount Day`")

async def cmd_bills(update, ctx):
    all_b = bills.all_active()
    if not all_b:
        await update.message.reply_text("💳 No bills!")
        return
    msg = "💳 *BILLS*\n\n"
    for b in all_b:
        status = "✅" if bills.is_paid_this_month(b["id"]) else "⏳"
        msg += f"{status} {b['name']} ₹{b['amount']:.0f} — {b['due_day']}th\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_bill_paid(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/billpaid <id>`")
        return
    try:
        if bills.mark_paid(int(ctx.args[0])):
            await update.message.reply_text("✅ Paid this month!")
        else:
            await update.message.reply_text("❌ Already paid or not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_del_bill(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delbill <id>`")
        return
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
        await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`")
        return
    args_str = " ".join(ctx.args)
    if args_str.startswith("aaj "):
        date_str = today_str()
        title = args_str[4:]
    elif args_str.startswith("kal "):
        date_str = (now_ist().date() + timedelta(days=1)).isoformat()
        title = args_str[4:]
    elif _re.match(r'^\d{4}-\d{2}-\d{2}', args_str):
        date_str = args_str[:10]
        title = args_str[11:]
    else:
        await update.message.reply_text("❌ Use: `/cal YYYY-MM-DD Event` or `/cal aaj Meeting`")
        return
    calendar.add(title, date_str)
    await update.message.reply_text(f"📅 Added: {title} on {date_str}")
    await auto_backup_to_sheets()

async def cmd_calendar(update, ctx):
    upcoming = calendar.upcoming(14)
    if not upcoming:
        await update.message.reply_text("📅 No upcoming events!")
        return
    msg = "📅 *UPCOMING EVENTS*\n\n"
    for e in upcoming[:10]:
        msg += f"📆 {e['date']} — {e['title']}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_del_cal(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delcal <id>`")
        return
    try:
        if calendar.delete(int(ctx.args[0])):
            await update.message.reply_text("🗑 Event deleted!")
        else:
            await update.message.reply_text("❌ Not found")
        await auto_backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID")

async def cmd_news(update, ctx):
    items = news_store.get("India", 5)
    if not items:
        await update.message.reply_text("📰 News unavailable")
        return
    msg = "📰 *NEWS*\n\n" + "\n".join(f"• {i['title']}" for i in items)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_weekly(update, ctx):
    n = now_ist()
    msg = f"📊 *WEEKLY REPORT*\n📅 Week of {n.strftime('%d %b')}\n\n"
    msg += f"📋 Pending tasks: {len(tasks.pending())}\n"
    msg += f"✅ Completed this week: {sum(tasks.get_weekly_summary().values())[0] if tasks.get_weekly_summary() else 0}\n\n"
    msg += f"💰 Month expenses: ₹{expenses.month_total():.0f}\n"
    msg += f"💧 Water today: {water.today_total()}ml\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_report(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📋 `/report YYYY-MM-DD`\nExample: `/report 2026-04-28`")
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
    
    msg = f"📋 *REPORT FOR {target_date}*\n\n"
    msg += f"✅ Tasks done: {len(tasks_done)}\n"
    if tasks_done:
        msg += "   " + "\n   ".join(t['title'][:30] for t in tasks_done[:5]) + "\n"
    msg += f"\n💰 Expenses: ₹{sum(e['amount'] for e in expenses_on):.0f}\n"
    msg += f"💪 Habits done: {len(habits_done)}/{len(habits.all())}\n"
    if diary_entries:
        msg += f"\n📖 Diary: {diary_entries[0]['text'][:50]}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_briefing(update, ctx):
    n = now_ist()
    tp = tasks.today_pending()
    hp = habits.today_status()[1]
    msg = f"🌅 *BRIEFING*\n⏰ {n.strftime('%I:%M %p')}\n\n"
    if tp:
        msg += f"📋 Today's tasks ({len(tp)}):\n" + "\n".join(f"   • {t['title']}" for t in tp[:5]) + "\n"
    else:
        msg += "🎉 No tasks today!\n"
    if hp:
        msg += f"\n💪 Habits to do: {', '.join(h['name'] for h in hp[:4])}\n"
    msg += f"\n💰 Today spent: ₹{expenses.today_total():.0f}\n"
    msg += f"💧 Water: {water.today_total()}ml/{water.goal()}ml"
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_backup(update, ctx):
    await update.message.reply_text("📤 Syncing to Google Sheets...")
    result = google_sheets.full_sync()
    await update.message.reply_text(result)

async def cmd_alltasks(update, ctx):
    all_t = tasks.all_tasks()
    if not all_t:
        await update.message.reply_text("📋 No tasks!")
        return
    p = tasks.pending()
    c = tasks.completed_tasks()
    msg = f"📋 *ALL TASKS*\nTotal: {len(all_t)} | Pending: {len(p)} | Done: {len(c)}\n\n"
    if p:
        msg += "⏳ PENDING:\n" + "\n".join(f"   #{t['id']} {t['title']}" for t in p[:10]) + "\n"
    if c:
        msg += "\n✅ RECENTLY DONE:\n" + "\n".join(f"   #{t['id']} {t['title']}" for t in c[-5:])
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_completed(update, ctx):
    c = tasks.completed_tasks()
    if not c:
        await update.message.reply_text("✅ No completed tasks yet!")
        return
    msg = f"✅ *COMPLETED TASKS* ({len(c)})\n\n" + "\n".join(f"   #{t['id']} {t['title']}" for t in c[-15:])
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_yesterday(update, ctx):
    yd = yesterday_str()
    tasks_done = tasks.done_on(yd)
    expenses_yest = expenses.get_by_date(yd)
    diary_yest = diary.get(yd)
    msg = f"📅 *YESTERDAY* ({yd})\n\n"
    msg += f"✅ Tasks done: {len(tasks_done)}\n"
    if tasks_done:
        msg += "   " + ", ".join(t['title'][:20] for t in tasks_done[:3]) + "\n"
    msg += f"💰 Expenses: ₹{sum(e['amount'] for e in expenses_yest):.0f}\n"
    if diary_yest:
        msg += f"📖 Diary: {diary_yest[0]['text'][:50]}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_memory(update, ctx):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("🧠 No memories yet!")
        return
    msg = "🧠 *MY MEMORY*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-15:])
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_notes(update, ctx):
    notes_list = notes.recent(10)
    if not notes_list:
        await update.message.reply_text("📝 No notes! Use `/note`")
        return
    msg = "📝 *NOTES*\n\n" + "\n".join(f"#{n['id']} — {n['text'][:40]}" for n in notes_list)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_note(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📝 `/note Something important`")
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

async def cmd_remind(update, ctx):
    if len(ctx.args) < 2:
        await update.message.reply_text("⏰ `/remind 15:30 Meeting`\n`/remind 2m Chai`")
        return
    time_str = ctx.args[0]
    text = " ".join(ctx.args[1:])
    repeat = "once"
    if text.endswith(" daily"):
        repeat = "daily"
        text = text[:-6].strip()
    if text.endswith(" weekly"):
        repeat = "weekly"
        text = text[:-7].strip()
    if time_str.endswith("m") and time_str[:-1].isdigit():
        remind_at = (now_ist() + timedelta(minutes=int(time_str[:-1]))).strftime("%H:%M")
    elif ":" in time_str:
        remind_at = time_str
    else:
        await update.message.reply_text("❌ Use: `/remind 15:30 Meeting`")
        return
    r = reminders.add(update.effective_chat.id, text, remind_at, repeat)
    await update.message.reply_text(f"✅ Reminder set for {remind_at}: {text}")
    await auto_backup_to_sheets()

async def cmd_reminders_list(update, ctx):
    active = reminders.all_active()
    if not active:
        await update.message.reply_text("⏰ No reminders!")
        return
    msg = "⏰ *REMINDERS*\n\n"
    for r in active:
        msg += f"#{r['id']} {r['time']} — {r['text']} ({r['repeat']})\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

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

async def cmd_clear(update, ctx):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes", callback_data="confirm_clear"),
        InlineKeyboardButton("❌ No", callback_data="menu")
    ]])
    await update.message.reply_text(f"🧹 Clear {chat_hist.count()} chat messages?\n(Data safe)", reply_markup=kb)

async def cmd_nuke(update, ctx):
    tracked = chat_hist.get_tracked_ids()
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💣 Delete Messages", callback_data="confirm_nuke"),
        InlineKeyboardButton("❌ Cancel", callback_data="menu")
    ]])
    sent = await update.message.reply_text(
        f"💣 *{len(tracked)} messages delete karein?*\n\n"
        f"⚠️ *Sirf messages delete honge!*\n"
        f"✅ Tasks, Reminders, Kharcha — *SAFE RAHENGE*",
        parse_mode="Markdown",
        reply_markup=kb
    )
    chat_hist.track_msg(update.effective_chat.id, sent.message_id)

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
        await msg.edit_text("🏠 *Menu*", parse_mode="Markdown", reply_markup=main_kb())
    elif data == "briefing":
        await cmd_briefing(update, ctx)
    elif data == "tasks":
        pending = tasks.pending()
        if not pending:
            await msg.edit_text("🎉 No pending tasks!")
        else:
            txt = "📋 *PENDING TASKS*\n\n" + "\n".join(f"#{t['id']} {t['title']}" for t in pending[:10])
            await msg.edit_text(txt, parse_mode="Markdown")
    elif data == "habits":
        done, pending = habits.today_status()
        txt = "💪 *HABITS TODAY*\n\n"
        if done:
            txt += "✅ Done: " + ", ".join(h['name'] for h in done) + "\n\n"
        if pending:
            txt += "⏳ Pending: " + ", ".join(h['name'] for h in pending) + "\n"
        await msg.edit_text(txt, parse_mode="Markdown")
    elif data == "diary":
        entries = diary.get(today_str())
        if not entries:
            await msg.edit_text("📖 No diary entry today. Use `/diary` to add.")
        else:
            txt = "📖 *TODAY'S DIARY*\n\n" + "\n".join(f"{e['time']} — {e['text']}" for e in entries)
            await msg.edit_text(txt, parse_mode="Markdown")
    elif data == "goals":
        active = goals.active()
        if not active:
            await msg.edit_text("🎯 No active goals! Use `/goal` to add.")
        else:
            txt = "🎯 *ACTIVE GOALS*\n\n"
            for g in active:
                bar = "█" * (g['progress'] // 10) + "░" * (10 - (g['progress'] // 10))
                txt += f"**{g['title']}**\n`{bar}` {g['progress']}%\n\n"
            await msg.edit_text(txt, parse_mode="Markdown")
    elif data == "expenses":
        txt = f"💰 Today: ₹{expenses.today_total():.0f}\n📆 Month: ₹{expenses.month_total():.0f}"
        bl = expenses.budget_left()
        if bl:
            txt += f"\n💳 Budget left: ₹{bl:.0f}"
        await msg.edit_text(txt, parse_mode="Markdown")
    elif data == "news":
        items = news_store.get("India", 5)
        if not items:
            await msg.edit_text("📰 News unavailable")
        else:
            txt = "📰 *NEWS*\n\n" + "\n".join(f"• {i['title']}" for i in items)
            await msg.edit_text(txt, parse_mode="Markdown")
    elif data == "notes":
        recent = notes.recent(8)
        if not recent:
            await msg.edit_text("📝 No notes! Use `/note` to add.")
        else:
            txt = "📝 *RECENT NOTES*\n\n" + "\n".join(f"#{n['id']} — {n['text'][:40]}" for n in recent)
            await msg.edit_text(txt, parse_mode="Markdown")
    elif data == "water":
        total = water.today_total()
        goal = water.goal()
        pct = int(total / goal * 100) if goal else 0
        await msg.edit_text(f"💧 {total}ml / {goal}ml ({pct}%)\n\nUse `/water` to log more!")
    elif data == "bills":
        due = bills.due_soon(7)
        if not due:
            await msg.edit_text("💳 No bills due this week!")
        else:
            txt = "💳 *BILLS DUE SOON*\n\n" + "\n".join(f"⚠️ {b['name']} — ₹{b['amount']:.0f}" for b in due)
            await msg.edit_text(txt, parse_mode="Markdown")
    elif data == "calendar":
        upcoming = calendar.upcoming(7)
        if not upcoming:
            await msg.edit_text("📅 No upcoming events!")
        else:
            txt = "📅 *UPCOMING EVENTS*\n\n" + "\n".join(f"📆 {e['date']} — {e['title']}" for e in upcoming[:7])
            await msg.edit_text(txt, parse_mode="Markdown")
    elif data == "weekly":
        await cmd_weekly(update, ctx)
    elif data == "all_tasks":
        await cmd_alltasks(update, ctx)
    elif data == "completed":
        await cmd_completed(update, ctx)
    elif data == "yesterday":
        await cmd_yesterday(update, ctx)
    elif data == "memory":
        await cmd_memory(update, ctx)
    elif data == "backup":
        await cmd_backup(update, ctx)
    elif data == "help":
        await cmd_help(update, ctx)
    elif data == "confirm_clear":
        count = chat_hist.clear()
        await msg.edit_text(f"🧹 Cleared {count} chat messages!\n\n✅ All data safe!", reply_markup=main_kb())
    elif data == "confirm_nuke":
        tracked = chat_hist.get_tracked_ids()
        cid = msg.chat_id
        status = await msg.reply_text("🧹 Clearing messages...")
        deleted, failed = await delete_telegram_messages(query.get_bot(), tracked)
        chat_hist.clear()
        chat_hist.clear_msg_ids()
        try:
            await status.delete()
        except:
            pass
        try:
            await msg.delete()
        except:
            pass
        await query.get_bot().send_message(
            chat_id=cid,
            text=f"🧹 Done! {deleted} messages deleted.\n✅ Your data is SAFE!",
            reply_markup=main_kb()
        )

# ═══════════════════════════════════════════════════════════════════
# MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_msg = update.message.text
    if user_msg.startswith('/'):
        return
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ai_chat(user_msg, update.effective_chat.id)
    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except:
        await update.message.reply_text(reply)

# ═══════════════════════════════════════════════════════════════════
# BACKGROUND JOBS
# ═══════════════════════════════════════════════════════════════════

async def reminder_job(context):
    now = now_ist()
    now_time = now.strftime("%H:%M")
    if now_time in ("00:00", "00:01"):
        reminders.reset_daily()
        log.info("Daily reset")
        return
    due = reminders.due_now()
    for r in due:
        try:
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=f"🔔 *REMINDER*\n⏰ {r['time']}\n📝 {r['text']}",
                parse_mode="Markdown"
            )
            reminders.mark_fired(r["id"])
            log.info(f"Reminder #{r['id']} sent")
        except Exception as e:
            log.error(f"Reminder failed: {e}")

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
                    await context.bot.send_message(chat_id=r["chat_id"], text=f"📝 *Processed!*\n\n{reply}", parse_mode="Markdown")
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

async def delete_telegram_messages(bot, tracked_ids):
    deleted = 0
    for entry in tracked_ids:
        try:
            await bot.delete_message(chat_id=entry["chat_id"], message_id=entry["msg_id"])
            deleted += 1
        except:
            pass
        await asyncio.sleep(0.1)
    return deleted, 0

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    n = now_ist()
    log.info("=" * 50)
    log.info("🤖 PERSONAL AI ASSISTANT v7.0 FINAL")
    log.info(f"⏰ IST: {n.strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"🔑 Gemini: {'YES' if GEMINI_API_KEY else 'NO'}")
    log.info(f"📊 Google Sheets: {'YES' if google_sheets.sheet else 'NO'}")
    log.info("=" * 50)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    commands = [
        ("start", cmd_start), ("help", cmd_help),
        ("task", cmd_task), ("done", cmd_done),
        ("diary", cmd_diary), ("habit", cmd_habit), ("hdone", cmd_hdone),
        ("kharcha", cmd_kharcha),
        ("goal", cmd_goal), ("gprogress", cmd_gprogress),
        ("remember", cmd_remember), ("recall", cmd_recall),
        ("water", cmd_water), ("waterstatus", cmd_water_status), ("watergoal", cmd_water_goal),
        ("bill", cmd_bill), ("bills", cmd_bills), ("billpaid", cmd_bill_paid), ("delbill", cmd_del_bill),
        ("cal", cmd_cal), ("calendar", cmd_calendar), ("delcal", cmd_del_cal),
        ("news", cmd_news), ("weekly", cmd_weekly), ("report", cmd_report),
        ("briefing", cmd_briefing), ("backup", cmd_backup),
        ("alltasks", cmd_alltasks), ("completed", cmd_completed), ("yesterday", cmd_yesterday),
        ("memory", cmd_memory), ("notes", cmd_notes), ("note", cmd_note), ("delnote", cmd_delnote),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list), ("delremind", cmd_delremind),
        ("clear", cmd_clear), ("nuke", cmd_nuke),
    ]
    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=30, first=5)
        app.job_queue.run_repeating(failed_retry_job, interval=300, first=60)
        app.job_queue.run_repeating(bill_due_job, interval=3600, first=60)
        app.job_queue.run_repeating(water_reminder_job, interval=3600, first=300)
        log.info("✅ Jobs started: Reminders (30s), Retry (5min), Bills (1hr), Water (1hr)")
    else:
        log.error("❌ JobQueue not available!")
    
    log.info("✅ Bot ready!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
