#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PERSONAL AI ASSISTANT v5.0 - COMPLETE
✅ Offline Message Queue
✅ Reminder System Fixed
✅ Task Logs (Done/Pending/All)
✅ Secret Code Lock (Rk1996)
✅ Persistent Logs (Chat clear ke baad bhi safe)
✅ Activity Log (Har action log)
"""

import os, json, logging, time, asyncio, urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta
from xml.etree import ElementTree as ET
import hashlib, threading, re as _re

ssl._create_default_https_context = ssl._create_unverified_context
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()])
log = logging.getLogger(__name__)

# ═══════════════ CONFIG ═══════════════
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    log.error("❌ Set TELEGRAM_TOKEN and GEMINI_API_KEY"); exit(1)

SECRET_CODE = "Rk1996"
SECRET_CODE_HASH = hashlib.sha256(SECRET_CODE.encode()).hexdigest()
GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

DATA = os.path.join(os.getcwd(), "data"); os.makedirs(DATA, exist_ok=True)

# File paths
F_CHAT = os.path.join(DATA, "chat_history.json")
F_MEMORY = os.path.join(DATA, "memory.json")
F_TASKS = os.path.join(DATA, "tasks.json")
F_DIARY = os.path.join(DATA, "diary.json")
F_HABITS = os.path.join(DATA, "habits.json")
F_NOTES = os.path.join(DATA, "notes.json")
F_EXPENSES = os.path.join(DATA, "expenses.json")
F_GOALS = os.path.join(DATA, "goals.json")
F_REMINDERS = os.path.join(DATA, "reminders.json")
F_WATER = os.path.join(DATA, "water.json")
F_BILLS = os.path.join(DATA, "bills.json")
F_CALENDAR = os.path.join(DATA, "calendar.json")
F_NEWS = os.path.join(DATA, "news_cache.json")
F_OFFLINE = os.path.join(DATA, "offline_queue.json")
F_ACTIVITY = os.path.join(DATA, "activity_log.json")

NEWS_FEEDS = {
    "India": "https://feeds.bbci.co.uk/hindi/rss.xml",
    "Technology": "https://feeds.feedburner.com/ndtvnews-tech-news",
    "Business": "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Sports": "https://feeds.bbci.co.uk/sport/rss.xml",
}

# ═══════════════ HELPERS ═══════════════
def load_json(path, default=None):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return default if default is not None else {}

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    except: pass

def today_str(): return date.today().isoformat()
def now_str(): return datetime.now().strftime("%H:%M")
def yesterday_str(): return (date.today() - timedelta(days=1)).isoformat()
def verify_secret(code): return hashlib.sha256(code.encode()).hexdigest() == SECRET_CODE_HASH

# ═══════════════ GEMINI API ═══════════════
def call_gemini(system_prompt, messages, retries=2):
    contents = [
        {"role": "user", "parts": [{"text": f"[SYSTEM]\n{system_prompt}\n[/SYSTEM]"}]},
        {"role": "model", "parts": [{"text": "Haan ready hoon!"}]}
    ]
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    payload = json.dumps({"contents": contents, "generationConfig": {"temperature": 0.75, "maxOutputTokens": 600}}).encode("utf-8")
    for model in GEMINI_MODELS:
        for attempt in range(retries):
            try:
                url = BASE_URL.format(model=model, key=GEMINI_API_KEY)
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=45) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    log.info(f"✅ Model: {model}")
                    return result["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code == 429: time.sleep(2); continue
                elif e.code in (500, 503): time.sleep(1); continue
                elif e.code == 404: break
            except: break
    return None  # Offline indicator

def fetch_news(category="India", max_items=5):
    cache = load_json(F_NEWS, {"cache": {}, "updated": {}})
    if category in cache["cache"] and time.time() - cache["updated"].get(category, 0) < 1800:
        return cache["cache"][category][:max_items]
    url = NEWS_FEEDS.get(category, NEWS_FEEDS["India"]); items = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            tree = ET.parse(resp)
            channel = tree.getroot().find("channel") or tree.getroot()
            for item in channel.findall("item")[:max_items]:
                title = item.findtext("title", "").strip()
                if title: items.append({"title": title, "desc": (item.findtext("description", "") or "")[:120], "link": item.findtext("link", "").strip()})
    except: return [{"title": "News abhi available nahi", "desc": "", "link": ""}]
    cache["cache"][category] = items; cache["updated"][category] = time.time(); save_json(F_NEWS, cache)
    return items

# ═══════════════ CLASSES ═══════════════
class ChatHistory:
    def __init__(self):
        self.data = load_json(F_CHAT, {"history": [], "cleared_at": None, "msg_ids": []})
        if "msg_ids" not in self.data: self.data["msg_ids"] = []
    def add(self, role, content):
        self.data["history"].append({"role": role, "content": content, "time": datetime.now().isoformat()})
        self.data["history"] = self.data["history"][-80:]; save_json(F_CHAT, self.data)
    def track_msg(self, chat_id, msg_id):
        self.data["msg_ids"].append({"chat_id": chat_id, "msg_id": msg_id})
        self.data["msg_ids"] = self.data["msg_ids"][-500:]; save_json(F_CHAT, self.data)
    def get_tracked_ids(self): return self.data.get("msg_ids", [])
    def get_recent(self, n=20): return [{"role": m["role"], "content": m["content"]} for m in self.data["history"][-n:]]
    def clear(self):
        count = len(self.data["history"]); self.data["history"] = []
        self.data["cleared_at"] = datetime.now().isoformat(); save_json(F_CHAT, self.data); return count
    def clear_msg_ids(self): self.data["msg_ids"] = []; save_json(F_CHAT, self.data)
    def count(self): return len(self.data["history"])

class Memory:
    def __init__(self): self.data = load_json(F_MEMORY, {"facts": [], "prefs": {}, "dates": {}, "important_notes": []})
    def save(self): save_json(F_MEMORY, self.data)
    def add_fact(self, fact):
        if fact[:50] in [f["f"][:50] for f in self.data["facts"][-50:]]: return
        self.data["facts"].append({"f": fact, "d": today_str()})
        self.data["facts"] = self.data["facts"][-400:]; self.save()
    def add_important(self, note): self.data["important_notes"].append({"note": note, "d": today_str()}); self.save()
    def context(self):
        facts = "\n".join(f"• {x['f']}" for x in self.data["facts"][-30:]) or "Kuch nahi"
        imp = "\n".join(f"⭐ {n['note']}" for n in self.data["important_notes"][-10:]) or "Kuch nahi"
        return f"FACTS:\n{facts}\n\nIMPORTANT:\n{imp}"
    def get_all(self): return self.data

class Tasks:
    def __init__(self): self.data = load_json(F_TASKS, {"list": [], "counter": 0, "completed_history": []})
    def save(self): save_json(F_TASKS, self.data)
    def add(self, title, priority="medium", due=None):
        self.data["counter"] += 1
        t = {"id": self.data["counter"], "title": title, "priority": priority, "due": due or today_str(),
             "done": False, "done_at": None, "completed_date": None, "created": datetime.now().isoformat()}
        self.data["list"].append(t); self.save(); return t
    def complete(self, tid):
        for t in self.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True; t["done_at"] = datetime.now().isoformat(); t["completed_date"] = today_str()
                self.data["completed_history"].append(t.copy()); self.save(); return t
        return None
    def delete(self, tid):
        before = len(self.data["list"]); self.data["list"] = [t for t in self.data["list"] if t["id"] != tid]; self.save()
        return before != len(self.data["list"])
    def pending(self): return [t for t in self.data["list"] if not t["done"]]
    def all_tasks(self): return self.data["list"]
    def completed_tasks(self): return [t for t in self.data["list"] if t["done"]]
    def done_on(self, d): return [t for t in self.data["list"] if t["done"] and t.get("completed_date") == d]
    def today_pending(self):
        td = today_str(); return [t for t in self.data["list"] if not t["done"] and t.get("due", "") <= td]
    def clear_done(self):
        before = len(self.data["list"]); self.data["list"] = [t for t in self.data["list"] if not t["done"]]; self.save()
        return before - len(self.data["list"])
    def get_history(self, date_filter=None):
        history = [t for t in self.data.get("completed_history", [])]
        if date_filter: history = [t for t in history if t.get("completed_date") == date_filter]
        return history

class Diary:
    def __init__(self): self.data = load_json(F_DIARY, {"entries": {}})
    def save(self): save_json(F_DIARY, self.data)
    def add(self, content, mood="😊"):
        td = today_str()
        if td not in self.data["entries"]: self.data["entries"][td] = []
        self.data["entries"][td].append({"text": content, "mood": mood, "time": now_str()}); self.save()
    def get(self, d): return self.data["entries"].get(d, [])
    def get_all(self): return self.data["entries"]

class Habits:
    def __init__(self): self.data = load_json(F_HABITS, {"list": [], "logs": {}, "counter": 0})
    def save(self): save_json(F_HABITS, self.data)
    def add(self, name, emoji="✅"):
        self.data["counter"] += 1
        h = {"id": self.data["counter"], "name": name, "emoji": emoji, "streak": 0, "best_streak": 0, "created": today_str()}
        self.data["list"].append(h); self.save(); return h
    def log(self, hid):
        td, yd = today_str(), yesterday_str()
        if td not in self.data["logs"]: self.data["logs"][td] = []
        if hid in self.data["logs"][td]: return False, 0
        self.data["logs"][td].append(hid)
        for h in self.data["list"]:
            if h["id"] == hid:
                h["streak"] = h["streak"] + 1 if hid in self.data["logs"].get(yd, []) else 1
                h["best_streak"] = max(h.get("best_streak", 0), h["streak"])
        self.save(); return True, next((x["streak"] for x in self.data["list"] if x["id"] == hid), 1)
    def today_status(self):
        done_ids = self.data["logs"].get(today_str(), [])
        return ([h for h in self.data["list"] if h["id"] in done_ids], [h for h in self.data["list"] if h["id"] not in done_ids])
    def all(self): return self.data["list"]

class Notes:
    def __init__(self): self.data = load_json(F_NOTES, {"list": [], "counter": 0})
    def save(self): save_json(F_NOTES, self.data)
    def add(self, content):
        self.data["counter"] += 1
        n = {"id": self.data["counter"], "text": content, "created": datetime.now().isoformat()}
        self.data["list"].append(n); self.save(); return n
    def recent(self, n=15): return self.data["list"][-n:]

class Expenses:
    def __init__(self): self.data = load_json(F_EXPENSES, {"list": [], "counter": 0, "budget": {}})
    def save(self): save_json(F_EXPENSES, self.data)
    def add(self, amount, desc, category="general"):
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "amount": amount, "desc": desc, "category": category, "date": today_str(), "time": now_str()}
        self.data["list"].append(e); self.save(); return e
    def set_budget(self, amount): self.data["budget"]["monthly"] = amount; self.save()
    def today_total(self): return sum(e["amount"] for e in self.data["list"] if e["date"] == today_str())
    def month_total(self): return sum(e["amount"] for e in self.data["list"] if e["date"][:7] == today_str()[:7])
    def budget_left(self):
        b = self.data["budget"].get("monthly", 0); return b - self.month_total() if b else None
    def get_all(self): return self.data["list"]

class Goals:
    def __init__(self): self.data = load_json(F_GOALS, {"list": [], "counter": 0})
    def save(self): save_json(F_GOALS, self.data)
    def add(self, title, deadline=None):
        self.data["counter"] += 1
        g = {"id": self.data["counter"], "title": title, "deadline": deadline or "", "progress": 0, "done": False, "created": today_str()}
        self.data["list"].append(g); self.save(); return g
    def active(self): return [g for g in self.data["list"] if not g["done"]]
    def completed(self): return [g for g in self.data["list"] if g["done"]]

class Reminders:
    def __init__(self): self.data = load_json(F_REMINDERS, {"list": [], "counter": 0, "history": []})
    def save(self): save_json(F_REMINDERS, self.data)
    def add(self, chat_id, text, remind_at, repeat="once"):
        self.data["counter"] += 1
        r = {"id": self.data["counter"], "chat_id": chat_id, "text": text, "time": remind_at, "repeat": repeat,
             "active": True, "fired_today": False, "created": datetime.now().isoformat(), "fire_history": []}
        self.data["list"].append(r); self.save()
        activity_log.add("reminder_created", chat_id, f"Reminder set: {text} at {remind_at}")
        return r
    def all_active(self): return [r for r in self.data["list"] if r["active"]]
    def delete(self, rid):
        before = len(self.data["list"]); self.data["list"] = [r for r in self.data["list"] if r["id"] != rid]; self.save()
        return before != len(self.data["list"])
    def mark_fired(self, rid):
        for r in self.data["list"]:
            if r["id"] == rid:
                r["fired_today"] = True; r["fire_history"].append({"fired_at": datetime.now().isoformat(), "date": today_str()})
                self.data["history"].append({"reminder_id": rid, "text": r["text"], "fired_at": datetime.now().isoformat()})
                if r["repeat"] == "once": r["active"] = False
                self.save(); break
    def reset_daily(self):
        changed = False
        for r in self.data["list"]:
            if r["fired_today"]: r["fired_today"] = False; changed = True
        if changed: self.save()
    def due_now(self):
        now_dt = datetime.now(); due = []
        for r in self.data["list"]:
            if not r["active"] or r["fired_today"]: continue
            try:
                r_dt = datetime.strptime(today_str() + " " + r["time"], "%Y-%m-%d %H:%M")
                if 0 <= (now_dt - r_dt).total_seconds() < 120: due.append(r)
            except:
                if r["time"] == now_dt.strftime("%H:%M"): due.append(r)
        return due
    def get_history(self): return self.data.get("history", [])

class WaterTracker:
    def __init__(self): self.data = load_json(F_WATER, {"logs": {}, "goal_ml": 2000})
    def save(self): save_json(F_WATER, self.data)
    def add(self, ml=250):
        td = today_str()
        if td not in self.data["logs"]: self.data["logs"][td] = []
        self.data["logs"][td].append({"ml": ml, "time": now_str()}); self.save()
    def today_total(self): return sum(e["ml"] for e in self.data["logs"].get(today_str(), []))
    def goal(self): return self.data.get("goal_ml", 2000)
    def set_goal(self, ml): self.data["goal_ml"] = ml; self.save()

class BillTracker:
    def __init__(self): self.data = load_json(F_BILLS, {"list": [], "counter": 0})
    def save(self): save_json(F_BILLS, self.data)
    def add(self, name, amount, due_day, bill_type="bill"):
        self.data["counter"] += 1
        b = {"id": self.data["counter"], "name": name, "amount": amount, "due_day": due_day, "type": bill_type, "active": True, "paid_months": []}
        self.data["list"].append(b); self.save(); return b
    def all_active(self): return [b for b in self.data["list"] if b["active"]]
    def mark_paid(self, bid):
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid and ym not in b["paid_months"]: b["paid_months"].append(ym); self.save(); return True
        return False
    def is_paid_this_month(self, bid):
        for b in self.data["list"]:
            if b["id"] == bid: return today_str()[:7] in b.get("paid_months", [])
        return False

class CalendarManager:
    def __init__(self): self.data = load_json(F_CALENDAR, {"events": [], "counter": 0})
    def save(self): save_json(F_CALENDAR, self.data)
    def add(self, title, event_date, event_time=""):
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "title": title, "date": event_date, "time": event_time}
        self.data["events"].append(e); self.save(); return e
    def today_events(self): return [e for e in self.data["events"] if e["date"] == today_str()]
    def upcoming(self, days=7):
        today_d = date.today(); cutoff = today_d + timedelta(days=days); result = []
        for e in self.data["events"]:
            try:
                ed = date.fromisoformat(e["date"])
                if today_d <= ed <= cutoff: result.append(e)
            except: pass
        return sorted(result, key=lambda x: x["date"])

class ActivityLog:
    """Har important action ka permanent log"""
    def __init__(self): self.data = load_json(F_ACTIVITY, {"logs": []})
    def save(self): save_json(F_ACTIVITY, self.data)
    def add(self, action_type, user_id, description, protected=False):
        entry = {"timestamp": datetime.now().isoformat(), "type": action_type, "user_id": user_id,
                 "description": description[:500], "date": today_str(), "protected": protected}
        self.data["logs"].append(entry)
        self.data["logs"] = self.data["logs"][-10000:]; self.save()
    def get_logs(self, date_filter=None, action_type=None):
        logs = self.data["logs"]
        if date_filter: logs = [l for l in logs if l["date"] == date_filter]
        if action_type: logs = [l for l in logs if l["type"] == action_type]
        return logs
    def get_protected(self): return [l for l in self.data["logs"] if l.get("protected")]

class OfflineQueue:
    """Jab AI offline ho, messages queue mein save karo"""
    def __init__(self):
        self.qf = F_OFFLINE; self.queue = self.load(); self.lock = threading.Lock()
    def load(self):
        try:
            if os.path.exists(self.qf):
                with open(self.qf, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
        return {"pending": []}
    def save(self):
        with self.lock:
            try:
                with open(self.qf, "w", encoding="utf-8") as f: json.dump(self.queue, f, ensure_ascii=False, indent=2)
            except: pass
    def add(self, user_id, chat_id, username, message):
        with self.lock:
            self.queue["pending"].append({"ts": datetime.now().isoformat(), "uid": user_id, "cid": chat_id,
                                          "uname": username, "msg": message, "done": False})
            self.save()
            log.info(f"📥 Offline queued: {username} - {message[:50]}")
    def get_pending(self): return [m for m in self.queue["pending"] if not m["done"]]
    def mark_done(self, idx):
        with self.lock:
            if 0 <= idx < len(self.queue["pending"]): self.queue["pending"][idx]["done"] = True; self.save()
    def cleanup(self):
        with self.lock:
            self.queue["pending"] = [m for m in self.queue["pending"] if not m["done"]] + [m for m in self.queue["pending"] if m["done"]][-100:]
            self.save()

# ═══════════════ INIT ═══════════════
chat_hist = ChatHistory()
mem = Memory()
tasks = Tasks()
diary = Diary()
habits = Habits()
notes = Notes()
expenses = Expenses()
goals = Goals()
reminders = Reminders()
water = WaterTracker()
bills = BillTracker()
calendar = CalendarManager()
activity_log = ActivityLog()
offline_queue = OfflineQueue()

log.info("✅ All objects initialized!")

# ═══════════════ SYSTEM PROMPT ═══════════════
def build_system_prompt():
    nl = datetime.now().strftime("%A, %d %B %Y — %I:%M %p")
    tp = tasks.today_pending()
    ts = "\n".join(f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}" for t in tp[:6]) or "Koi nahi"
    hd, hp = habits.today_status()
    hdone = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    hpend = ", ".join(h['name'] for h in hp) or "Sab done!"
    return f"""Tu mera AI Assistant 'Dost' hai. Hindi/Hinglish mein baat kar, warm aur helpful reh.
⏰ {nl} | 💬 {chat_hist.count()} msgs
📋 AAJ KE TASKS:\n{ts}
💪 HABITS: Done: {hdone} | Baaki: {hpend}
💰 KHARCHA: Aaj ₹{expenses.today_total()} | Mahina ₹{expenses.month_total()}
💧 PAANI: {water.today_total()}ml / {water.goal()}ml
━━ YAADDASHT ━━\n{mem.context()}
RULES: Hinglish mein jawab de, short aur helpful reh, kabhi "As an AI" mat bol."""

def auto_extract_facts(text):
    if any(k in text.lower() for k in ["yaad rakh", "remember", "mera naam", "meri umar", "main rehta"]):
        mem.add_fact(text[:250])
        activity_log.add("memory_saved", 0, text[:100], True)
        return True
    return False

async def ai_chat(user_msg, chat_id=None):
    auto_extract_facts(user_msg)
    chat_hist.add("user", user_msg)
    reply = call_gemini(build_system_prompt(), chat_hist.get_recent(20))
    if reply is None:
        # AI OFFLINE - queue the message
        return "OFFLINE"
    chat_hist.add("assistant", reply)
    return reply

# ═══════════════ KEYBOARDS ═══════════════
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Daily Briefing", callback_data="briefing"), InlineKeyboardButton("📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("💪 Habits", callback_data="habits"), InlineKeyboardButton("📖 Diary", callback_data="diary")],
        [InlineKeyboardButton("🎯 Goals", callback_data="goals"), InlineKeyboardButton("💰 Kharcha", callback_data="expenses")],
        [InlineKeyboardButton("📰 News", callback_data="news_menu"), InlineKeyboardButton("📝 Notes", callback_data="notes")],
        [InlineKeyboardButton("💧 Water", callback_data="water_status"), InlineKeyboardButton("💳 Bills", callback_data="bills_menu")],
        [InlineKeyboardButton("📅 Calendar", callback_data="cal_menu"), InlineKeyboardButton("📊 Weekly", callback_data="weekly_report")],
        [InlineKeyboardButton("🧹 Clear Chat", callback_data="clear_chat"), InlineKeyboardButton("🧠 Yaaddasht", callback_data="memory")],
        [InlineKeyboardButton("💡 Motivate", callback_data="motivate"), InlineKeyboardButton("📜 Activity Log", callback_data="activity_log_menu")],
    ])

def news_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇳 India", callback_data="news_India"), InlineKeyboardButton("💻 Tech", callback_data="news_Technology")],
        [InlineKeyboardButton("💼 Business", callback_data="news_Business"), InlineKeyboardButton("🌍 World", callback_data="news_World")],
        [InlineKeyboardButton("🏏 Sports", callback_data="news_Sports"), InlineKeyboardButton("🏠 Back", callback_data="menu")],
    ])

# ═══════════════ COMMAND HANDLERS ═══════════════
async def cmd_start(update, ctx):
    name = update.effective_user.first_name or "Dost"
    txt = f"""🕌 *Assalamualaikum {name}!*

🧠 *Smart Memory* — Chat clear bhi ho toh yaad rahunga
📋 *Tasks* — Done/Pending/All alag alag
💪 *Habits* | 📖 *Diary* | 💰 *Kharcha*
⏰ *Reminders* — Loud alarm ke saath
📥 *Offline Queue* — AI offline toh message save
🔐 *Secret Code* — `Rk1996` se protected logs
📜 *Activity Log* — Har action permanent record

✅ *100% FREE — Seedha type karo!* 👇"""
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_help(update, ctx):
    txt = """🤖 *COMMANDS v5.0*

📋 *TASKS:*
`/task Kaam` — Add task
`/task Important high` — High priority
`/done 3` — Complete task
`/deltask 3` — Delete task
`/alltasks` — Saare tasks (done+pending)
`/completed` — Sirf completed tasks
`/pending` — Sirf pending tasks

🔐 *SECRET CODE (Rk1996):*
`/verify Rk1996` — Code verify karo
`/taskhistory Rk1996` — Task completion history
`/activitylog Rk1996` — Poora activity log
`/reminderlog Rk1996` — Reminder firing history
`/offlinemsgs Rk1996` — Offline messages

📖 */diary Text* | 🧠 */remember Fact* | */recall*
💪 */habit Name* | */hdone 1*
💰 */kharcha 100 Food* | */budget 5000*
🎯 */goal Target* | */gprogress 1 50*
⏰ */remind 30m Chai* | */reminders* | */delremind 3*
💧 */water* | */waterstatus* | */watergoal 2500*
💳 */bill Netflix 199 5* | */bills* | */billpaid 3*
📅 */cal 2025-05-10 Meeting* | */calendar*
📊 */weekly* | */yesterday* | 📰 */news*
🧹 */clear* | */nuke*
📜 */activity* — Aaj ka activity log"""
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_task(update, ctx):
    if not ctx.args: await update.message.reply_text("📋 `/task Kaam` | `/task Important high` | `/task Chhota low`", parse_mode="Markdown"); return
    args = " ".join(ctx.args); priority = "medium"
    if args.endswith(" high"): priority = "high"; args = args[:-5].strip()
    elif args.endswith(" low"): priority = "low"; args = args[:-4].strip()
    t = tasks.add(args, priority)
    activity_log.add("task_created", update.effective_user.id, f"Task: {args} ({priority})", True)
    await update.message.reply_text(f"✅ *Task Add!* {'🔴' if priority=='high' else '🟡' if priority=='medium' else '🟢'} {t['title']}\n🆔 `#{t['id']}`", parse_mode="Markdown")

async def cmd_done(update, ctx):
    if not ctx.args: await update.message.reply_text("`/done 3` — Task ID", parse_mode="Markdown"); return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t:
            activity_log.add("task_completed", update.effective_user.id, f"Task: {t['title']}", True)
            await update.message.reply_text(f"🎉 *Complete!* ✅ {t['title']}\n💪 Wah bhai! Zabardast!", parse_mode="Markdown")
        else: await update.message.reply_text("❌ Task nahi mila ya pehle hi done hai.")
    except: pass

async def cmd_deltask(update, ctx):
    if not ctx.args: return
    try:
        ok = tasks.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 *Task Delete!*" if ok else "❌ Nahi mila", parse_mode="Markdown")
    except: pass

async def cmd_all_tasks(update, ctx):
    all_t = tasks.all_tasks()
    if not all_t: await update.message.reply_text("📋 Koi task nahi! `/task Kaam` se add karo"); return
    txt = f"📋 *SAARE TASKS ({len(all_t)})*\n━━━━━━━━━━━━━━━━\n\n"
    pending = [t for t in all_t if not t["done"]]
    completed = [t for t in all_t if t["done"]]
    if pending:
        txt += "*⏳ PENDING:*\n"
        for t in pending:
            e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
            txt += f"{e} *#{t['id']}* {t['title']}\n"
        txt += "\n"
    if completed:
        txt += "*✅ COMPLETED:*\n"
        for t in completed[-10:]: txt += f"✓ *#{t['id']}* {t['title']} _{t.get('completed_date','')}_\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed_tasks(update, ctx):
    comp = tasks.completed_tasks()
    if not comp: await update.message.reply_text("✅ Koi completed task nahi! `/done 3` se complete karo"); return
    txt = f"✅ *COMPLETED TASKS ({len(comp)})*\n━━━━━━━━━━━━━━━━\n\n"
    for t in comp[-15:]: txt += f"✓ *#{t['id']}* {t['title']}\n  📅 {t.get('completed_date','')} | 🕐 {t.get('done_at','')[:16] if t.get('done_at') else ''}\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_pending_tasks(update, ctx):
    pend = tasks.pending()
    if not pend: await update.message.reply_text("🎉 Koi pending task nahi! Sab clear!"); return
    txt = f"⏳ *PENDING TASKS ({len(pend)})*\n━━━━━━━━━━━━━━━━\n\n"
    for t in pend:
        e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
        txt += f"{e} *#{t['id']}* {t['title']}\n  📅 Due: {t.get('due','')}\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_verify(update, ctx):
    if not ctx.args or not verify_secret(ctx.args[0]): await update.message.reply_text("❌ Galat code! `/verify Rk1996`"); return
    activity_log.add("secret_verified", update.effective_user.id, "Secret code verified")
    await update.message.reply_text("✅ *Verified!*\n\nAb ye commands use karo:\n• `/taskhistory` — Task history\n• `/activitylog` — Poora log\n• `/reminderlog` — Reminder history\n• `/offlinemsgs` — Offline messages", parse_mode="Markdown")

async def cmd_task_history(update, ctx):
    if not ctx.args or not verify_secret(ctx.args[0]): await update.message.reply_text("❌ Galat code! `/taskhistory Rk1996`"); return
    history = tasks.get_history()
    if not history: await update.message.reply_text("📋 Koi task history nahi!"); return
    txt = f"🔓 *TASK COMPLETION HISTORY ({len(history)})*\n━━━━━━━━━━━━━━━━\n\n"
    for t in history[-20:]: txt += f"✓ {t.get('title','')}\n  📅 {t.get('completed_date','')}\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_activity_log(update, ctx):
    if not ctx.args or not verify_secret(ctx.args[0]): await update.message.reply_text("❌ Galat code! `/activitylog Rk1996`"); return
    logs = activity_log.get_logs()
    if not logs: await update.message.reply_text("📜 Koi activity log nahi!"); return
    txt = f"🔓 *ACTIVITY LOG ({len(logs)} entries)*\n━━━━━━━━━━━━━━━━\n\n"
    for l in logs[-25:]: txt += f"• {l['timestamp'][:16]} | *{l['type']}*: {l['description'][:80]}...\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_reminder_history(update, ctx):
    if not ctx.args or not verify_secret(ctx.args[0]): await update.message.reply_text("❌ Galat code! `/reminderlog Rk1996`"); return
    history = reminders.get_history()
    if not history: await update.message.reply_text("🔔 Koi reminder history nahi!"); return
    txt = f"🔓 *REMINDER HISTORY ({len(history)})*\n━━━━━━━━━━━━━━━━\n\n"
    for r in history[-20:]: txt += f"🔔 #{r['reminder_id']} — {r['text']}\n  ⏰ {r['fired_at'][:16]}\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_offline_messages(update, ctx):
    if not ctx.args or not verify_secret(ctx.args[0]): await update.message.reply_text("❌ Galat code! `/offlinemsgs Rk1996`"); return
    pending = offline_queue.get_pending()
    if not pending: await update.message.reply_text("📥 Koi offline message nahi!"); return
    txt = f"🔓 *OFFLINE MESSAGES ({len(pending)})*\n━━━━━━━━━━━━━━━━\n\n"
    for i, m in enumerate(pending[:10]): txt += f"*{i+1}.* {m['uname']} ({m['ts'][:16]})\n  {m['msg'][:100]}...\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_activity_today(update, ctx):
    """Aaj ka activity log (bina secret code)"""
    logs = activity_log.get_logs(date_filter=today_str())
    if not logs: await update.message.reply_text("📜 Aaj koi activity nahi!"); return
    txt = f"📜 *AAJ KA ACTIVITY LOG ({len(logs)})*\n━━━━━━━━━━━━━━━━\n\n"
    for l in logs[-20:]: txt += f"• {l['timestamp'][11:16]} | *{l['type']}*: {l['description'][:80]}...\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_diary(update, ctx):
    if not ctx.args: await update.message.reply_text("📖 `/diary Aaj bahut productive tha!`", parse_mode="Markdown"); return
    content = " ".join(ctx.args); diary.add(content)
    activity_log.add("diary_entry", update.effective_user.id, content[:100], True)
    await update.message.reply_text(f"📖 *Diary Mein Likh Diya!* ✅\n\n_{content}_\n🕐 {now_str()}", parse_mode="Markdown")

async def cmd_remember(update, ctx):
    if not ctx.args: await update.message.reply_text("🧠 `/remember Mera birthday 15 August hai`"); return
    fact = " ".join(ctx.args); mem.add_fact(fact)
    activity_log.add("memory_saved", update.effective_user.id, fact[:200], True)
    await update.message.reply_text(f"🧠 *Yaad Kar Liya!* ✅\n\n_{fact}_\n\n🔒 Chat clear ke baad bhi safe rahega!", parse_mode="Markdown")

async def cmd_recall(update, ctx):
    facts = mem.data["facts"]; imp = mem.data.get("important_notes", [])
    if not facts and not imp: await update.message.reply_text("🧠 Kuch yaad nahi! `/remember Koi baat`"); return
    txt = f"🧠 *YAADDASHT ({len(facts)} facts)*\n\n"
    for f in facts[-15:]: txt += f"  📌 {f['f']}\n  _{f['d']}_\n\n"
    if imp:
        txt += "\n⭐ *IMPORTANT NOTES:*\n"
        for n in imp[-5:]: txt += f"  ⭐ {n['note']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_remind(update, ctx):
    if not ctx.args: await update.message.reply_text("⏰ `/remind 30m Chai` | `/remind 15:30 Doctor` | `/remind 8:00 Uthna daily`", parse_mode="Markdown"); return
    ta = ctx.args[0].lower(); rest = ctx.args[1:]; repeat = "once"; text = "Reminder"
    if rest and rest[-1].lower() in ["daily", "weekly"]: repeat = rest[-1].lower(); rest = rest[:-1]
    if rest: text = " ".join(rest)
    now = datetime.now(); time_str = None
    if ta.endswith("m") and ta[:-1].isdigit(): time_str = (now + timedelta(minutes=int(ta[:-1]))).strftime("%H:%M")
    elif ta.endswith("h") and ta[:-1].isdigit(): time_str = (now + timedelta(hours=int(ta[:-1]))).strftime("%H:%M")
    elif ":" in ta:
        parts = ta.split(":")
        if len(parts)==2 and parts[0].isdigit() and parts[1].isdigit(): time_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    if not time_str: await update.message.reply_text("❌ Format galat! `/remind 30m Chai` ya `/remind 15:30 Meeting`"); return
    r = reminders.add(update.effective_chat.id, text, time_str, repeat)
    rl = {"once": "Ek baar", "daily": "Roz 🔁", "weekly": "Har hafte 📅"}.get(repeat, repeat)
    await update.message.reply_text(f"✅ *Reminder Set!*\n\n⏰ *{time_str}* — {rl}\n📝 {text}\n🆔 `#{r['id']}` | `/delremind {r['id']}`", parse_mode="Markdown")

async def cmd_delremind(update, ctx):
    if not ctx.args: return
    try: await update.message.reply_text("🗑 *Delete!*" if reminders.delete(int(ctx.args[0])) else "❌ Nahi mila", parse_mode="Markdown")
    except: pass

async def cmd_reminders_list(update, ctx):
    all_r = reminders.all_active()
    if not all_r: await update.message.reply_text("⏰ Koi reminder nahi! `/remind 30m Chai`"); return
    txt = f"⏰ *REMINDERS ({len(all_r)})*\n\n"
    for r in all_r:
        ri = "🔁" if r["repeat"]=="daily" else "📅" if r["repeat"]=="weekly" else "1️⃣"
        status = "✅ Aaj ho gaya" if r["fired_today"] else "⏳ Baaki"
        txt += f"*#{r['id']}* {ri} `{r['time']}` — {r['text']}\n  _{status}_\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_water(update, ctx):
    ml = 250
    if ctx.args:
        try: ml = int(ctx.args[0])
        except: pass
    water.add(ml); total = water.today_total(); goal = water.goal()
    pct = min(100, int(total/goal*100)) if goal else 0
    activity_log.add("water_drank", update.effective_user.id, f"{ml}ml paani piya", True)
    msg = f"💧 *+{ml}ml!*\n\nAaj: *{total}ml / {goal}ml* ({pct}%)"
    if total >= goal: msg += "\n\n🎉 *Goal pura!* 🏆"
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("💧 +250ml", callback_data="water_250"), InlineKeyboardButton("💧 +500ml", callback_data="water_500")],
        [InlineKeyboardButton("🏠 Menu", callback_data="menu")]
    ]))

async def cmd_kharcha(update, ctx):
    if not ctx.args: await update.message.reply_text("💰 `/kharcha 100 Food` | `/kharcha 500 Petrol travel`", parse_mode="Markdown"); return
    try:
        amount = float(ctx.args[0]); desc = " ".join(ctx.args[1:]) or "Kharcha"
        expenses.add(amount, desc)
        activity_log.add("expense_added", update.effective_user.id, f"₹{amount} - {desc}", True)
        await update.message.reply_text(f"💰 *₹{amount:.0f} — {desc}*\nAaj total: ₹{expenses.today_total():.0f} | Mahina: ₹{expenses.month_total():.0f}", parse_mode="Markdown")
    except: pass

async def cmd_budget(update, ctx):
    if not ctx.args: await update.message.reply_text("💳 `/budget 5000` — Monthly budget"); return
    try: expenses.set_budget(float(ctx.args[0])); await update.message.reply_text(f"💳 *Budget Set: ₹{ctx.args[0]}*", parse_mode="Markdown")
    except: pass

async def cmd_clear(update, ctx):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Haan Clear", callback_data="confirm_clear_chat"), InlineKeyboardButton("❌ Nahi", callback_data="menu")]])
    await update.message.reply_text(f"🧹 *Chat Clear Karna Hai?*\n\n📊 {chat_hist.count()} messages abhi hain\n\n⚠️ *Sirf chat history clear hogi*\n✅ Memory, Tasks, Diary, Activity Log — sab safe rahega!\n🔒 Jo `/remember` kiya woh bhi safe", parse_mode="Markdown", reply_markup=kb)

async def cmd_nuke(update, ctx):
    chat_hist.track_msg(update.effective_chat.id, update.message.message_id)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💣 Haan! Sab Saaf", callback_data="confirm_nuke"), InlineKeyboardButton("❌ Nahi", callback_data="menu")]])
    sent = await update.message.reply_text(f"💣 *FULL NUKE*\n\n🗑 {len(chat_hist.get_tracked_ids())} bot messages delete honge\n🧹 Chat history clear hogi\n✅ Memory, Tasks, Activity Log — safe rahega", parse_mode="Markdown", reply_markup=kb)
    chat_hist.track_msg(update.effective_chat.id, sent.message_id)

# ═══════════════ SHOW FUNCTIONS ═══════════════
async def send_briefing(msg_obj):
    tp = tasks.today_pending(); yd = tasks.done_on(yesterday_str())
    hd, hp = habits.today_status(); tl = datetime.now().strftime("%A, %d %B %Y")
    txt = f"🌅 *DAILY BRIEFING*\n📅 {tl}\n{'━'*22}\n\n"
    if yd: txt += f"✅ *Kal {len(yd)} kaam kiye:*\n" + "\n".join(f"  • {t['title']}" for t in yd[:5]) + "\n\n"
    if tp:
        txt += f"📋 *Aaj {len(tp)} kaam baaki:*\n"
        for t in tp[:7]: txt += f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}\n"
        txt += "\n"
    else: txt += "🎉 Koi pending task nahi!\n\n"
    if hp: txt += f"💪 *{len(hp)} Habits baaki:*\n" + "\n".join(f"  ○ {h['emoji']} {h['name']}" for h in hp[:4]) + "\n\n"
    wt, wg = water.today_total(), water.goal()
    txt += f"💰 Aaj: ₹{expenses.today_total():.0f} | Mahina: ₹{expenses.month_total():.0f}\n"
    txt += f"💧 Paani: {wt}ml / {wg}ml\n\n💪 *Aaj ka din badiya banao!* 🚀"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def show_tasks(msg_obj):
    pending = tasks.pending()
    if not pending: await msg_obj.reply_text("🎉 Koi pending task nahi! `/task Kaam` se add karo"); return
    txt = f"📋 *PENDING TASKS ({len(pending)})*\n\n"; kb = []
    for t in pending[:12]:
        e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
        txt += f"{e} *#{t['id']}* {t['title']}\n"
        kb.append([InlineKeyboardButton(f"✅ #{t['id']}: {t['title'][:32]}", callback_data=f"done_{t['id']}")])
    kb.append([InlineKeyboardButton("🗑 Done wale hatao", callback_data="clear_done_tasks"), InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def show_habits(msg_obj):
    done, pending = habits.today_status()
    if not habits.all(): await msg_obj.reply_text("💪 Koi habit nahi! `/habit Morning walk 🏃`"); return
    txt = "💪 *HABITS*\n\n"; kb = []
    if done: txt += "✅ *Done:*\n" + "\n".join(f"  {h['emoji']} {h['name']} 🔥{h['streak']} din" for h in done) + "\n\n"
    if pending:
        txt += "⏳ *Baaki:*\n"
        for h in pending: txt += f"  ○ {h['emoji']} {h['name']}\n"; kb.append([InlineKeyboardButton(f"✅ {h['emoji']} {h['name']}", callback_data=f"habit_{h['id']}")])
    else: txt += "🎊 Sab complete!"
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def show_news(msg_obj, category="India"):
    items = fetch_news(category, 5)
    txt = f"📰 *{category.upper()} NEWS*\n\n" + "\n\n".join(f"*{i+1}.* {item['title']}" for i, item in enumerate(items))
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=news_kb())

async def show_diary(msg_obj):
    td = diary.get(today_str())
    txt = "📖 *DIARY — AAJ*\n\n" + "\n".join(f"  {e['time']} {e['mood']} {e['text']}" for e in td) if td else "📖 Aaj koi entry nahi!\n`/diary Aaj kya hua...`"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

async def show_goals(msg_obj):
    ag = goals.active()
    if not ag: await msg_obj.reply_text("🎯 Koi goals nahi! `/goal Target`"); return
    txt = f"🎯 *ACTIVE GOALS ({len(ag)})*\n\n"; kb = []
    for g in ag:
        bar = "█"*(g["progress"]//10) + "░"*(10-g["progress"]//10)
        txt += f"*{g['title']}*\n{bar} {g['progress']}%\n\n"
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def show_notes(msg_obj):
    ns = notes.recent(12)
    txt = "📝 *NOTES*\n\n" + "\n".join(f"*#{n['id']}* {n['text']}" for n in ns) if ns else "📝 Koi notes nahi! `/note Kuch important`"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

async def show_yesterday(msg_obj):
    yd = tasks.done_on(yesterday_str()); yd_d = diary.get(yesterday_str())
    txt = "📅 *KAL KA SUMMARY*\n\n"
    if yd: txt += f"✅ *{len(yd)} Tasks Kiye:*\n" + "\n".join(f"  • {t['title']}" for t in yd) + "\n\n"
    if yd_d: txt += "📖 *Diary:*\n" + "\n".join(f"  {e['time']} {e['mood']} {e['text']}" for e in yd_d)
    if not yd and not yd_d: txt += "_Kal ka koi data nahi_"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

# ═══════════════ CALLBACK ═══════════════
async def callback(update, ctx):
    q = update.callback_query; await q.answer(); d = q.data
    if d == "menu": await q.message.reply_text("🏠 *Main Menu*", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "briefing": await send_briefing(q.message)
    elif d == "tasks": await show_tasks(q.message)
    elif d == "habits": await show_habits(q.message)
    elif d == "diary": await show_diary(q.message)
    elif d == "goals": await show_goals(q.message)
    elif d == "notes": await show_notes(q.message)
    elif d == "yesterday": await show_yesterday(q.message)
    elif d == "news_menu": await q.message.reply_text("📰 *News?*", reply_markup=news_kb())
    elif d.startswith("news_"): await show_news(q.message, d.split("_",1)[1])
    elif d == "memory":
        facts = mem.data["facts"]
        txt = f"🧠 *YAADDASHT ({len(facts)} facts)*\n🔒 Chat clear ke baad bhi safe\n\n" + ("\n".join(f"  📌 {f['f']}" for f in facts[-12:]) if facts else "Kuch nahi")
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d == "expenses":
        await q.message.reply_text(f"💰 *KHARCHA*\nAaj: ₹{expenses.today_total():.0f}\nMahina: ₹{expenses.month_total():.0f}", parse_mode="Markdown")
    elif d == "clear_chat":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Haan", callback_data="confirm_clear_chat"), InlineKeyboardButton("❌ Nahi", callback_data="menu")]])
        await q.message.reply_text(f"🧹 *Clear?* {chat_hist.count()} msgs\n✅ Memory, Tasks safe", parse_mode="Markdown", reply_markup=kb)
    elif d == "confirm_clear_chat":
        count = chat_hist.clear(); activity_log.add("chat_cleared", 0, f"{count} messages cleared")
        await q.message.reply_text(f"🧹 *Clear!* 🗑 {count} msgs\n🔒 Memory, Tasks, Activity Log — sab safe!", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "water_status":
        t, g = water.today_total(), water.goal()
        await q.message.reply_text(f"💧 *WATER*\n🎯 {g}ml\n✅ {t}ml ({min(100,int(t/g*100)) if g else 0}%)", parse_mode="Markdown")
    elif d.startswith("water_") and d.split("_")[1].isdigit():
        ml = int(d.split("_")[1]); water.add(ml); activity_log.add("water_drank", 0, f"{ml}ml")
        await q.message.reply_text(f"💧 *+{ml}ml!* Aaj: {water.today_total()}ml", parse_mode="Markdown")
    elif d == "bills_menu":
        all_b = bills.all_active()
        txt = "💳 *BILLS*\n\n" + "\n".join(f"{'✅' if bills.is_paid_this_month(b['id']) else '⏳'} {b['name']} ₹{b['amount']:.0f}" for b in all_b) if all_b else "Koi bill nahi!"
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d.startswith("billpaid_"): bills.mark_paid(int(d.split("_")[1])); await q.message.reply_text("✅ *Paid!*")
    elif d == "cal_menu":
        up = calendar.upcoming(30)
        txt = "📅 *EVENTS*\n\n" + "\n".join(f"{e['date']} — {e['title']}" for e in up) if up else "Koi event nahi!"
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d == "weekly_report": await q.message.reply_text(f"📊 *WEEKLY*\n📋 {len(tasks.pending())} pending\n💰 ₹{expenses.month_total():.0f}\n💧 {water.today_total()}ml", parse_mode="Markdown")
    elif d == "clear_done_tasks":
        count = tasks.clear_done(); await q.message.reply_text(f"🗑 {count} done tasks delete!")
    elif d == "motivate":
        reply = await ai_chat("Mujhe powerful motivation de Hindi mein. 3-4 line. Real, raw. Generic mat dena.")
        if reply == "OFFLINE": await q.message.reply_text("💡 AI abhi offline hai. Thodi der baad try karo.")
        else: await q.message.reply_text(f"💡 *Motivation:*\n\n{reply}", parse_mode="Markdown")
    elif d == "activity_log_menu":
        logs = activity_log.get_logs(date_filter=today_str())
        txt = f"📜 *AAJ KA ACTIVITY LOG ({len(logs)})*\n\n" + "\n".join(f"• {l['timestamp'][11:16]} | {l['type']}: {l['description'][:80]}..." for l in logs[-20:]) if logs else "📜 Aaj koi activity nahi!"
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d.startswith("done_"):
        t = tasks.complete(int(d.split("_")[1]))
        if t: activity_log.add("task_completed", 0, f"Task: {t['title']}", True)
        await q.message.reply_text(f"🎉 *Complete!* ✅ {t['title']}" if t else "❌ Nahi mila", parse_mode="Markdown")
    elif d.startswith("habit_"):
        hid = int(d.split("_")[1]); ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"] == hid), None)
        if ok and h: activity_log.add("habit_done", 0, f"{h['name']} - {streak} day streak")
        await q.message.reply_text(f"💪 *Done!* {h['emoji']} {h['name']} 🔥{streak}" if ok and h else "✅ Pehle hi mark hai!", parse_mode="Markdown")
    elif d == "confirm_nuke":
        tracked = chat_hist.get_tracked_ids(); cid = q.message.chat_id
        await q.message.delete()
        deleted = 0
        for entry in tracked:
            try: await q.get_bot().delete_message(chat_id=entry["chat_id"], message_id=entry["msg_id"]); deleted += 1
            except: pass
        chat_hist.clear(); chat_hist.clear_msg_ids(); activity_log.add("nuke_done", cid, f"{deleted} messages deleted")
        await q.get_bot().send_message(chat_id=cid, text=f"🧹 *CHAT SAAF!*\n🗑 {deleted} delete\n🔒 Memory, Tasks, Activity Log — sab safe!\n_Fresh start!_ ✨", parse_mode="Markdown", reply_markup=main_kb())

# ═══════════════ MESSAGE HANDLER ═══════════════
async def handle_msg(update, ctx):
    user = update.effective_user; chat_id = update.effective_chat.id; msg = update.message.text
    chat_hist.track_msg(chat_id, update.message.message_id)
    activity_log.add("message_received", user.id, msg[:100])
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    reply = await ai_chat(msg, chat_id=chat_id)
    
    if reply == "OFFLINE":
        # AI offline - queue the message
        offline_queue.add(user.id, chat_id, user.first_name, msg)
        activity_log.add("offline_queued", user.id, msg[:100], True)
        sent = await update.message.reply_text(
            "⚠️ *AI Abhi Offline Hai!*\n\n"
            "📥 *Aapka message save kar liya hai!*\n"
            "Jab AI online hoga, automatically process hoga.\n\n"
            "🔒 Important messages/data safe rahega.\n"
            "_Thodi der baad check karna_ ✨",
            parse_mode="Markdown"
        )
    else:
        try: sent = await update.message.reply_text(reply, parse_mode="Markdown")
        except: sent = await update.message.reply_text(reply)
    
    chat_hist.track_msg(chat_id, sent.message_id)

# ═══════════════ JOBS ═══════════════
async def reminder_job(context):
    if datetime.now().strftime("%H:%M") == "00:00": reminders.reset_daily()
    for r in reminders.due_now():
        try:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Ho Gaya!", callback_data=f"remind_done_{r['id']}"),
                InlineKeyboardButton("⏰ 10 min Snooze", callback_data=f"remind_snooze_{r['id']}")
            ]])
            await context.bot.send_message(chat_id=r["chat_id"],
                text=f"🚨🔔 *ALARM!*\n{'═'*22}\n⏰ *{r['time']} BAJ GAYE!*\n{'═'*22}\n\n📢 *{r['text'].upper()}*",
                parse_mode="Markdown", disable_notification=False, reply_markup=kb)
            await asyncio.sleep(2)
            await context.bot.send_message(chat_id=r["chat_id"], text=f"🔔 *REMINDER:* {r['text']}\n⏰ Abhi dekho!", parse_mode="Markdown", disable_notification=False)
            reminders.mark_fired(r["id"])
            activity_log.add("reminder_fired", r["chat_id"], f"#{r['id']}: {r['text']}", True)
            log.info(f"🔔 Reminder fired: #{r['id']} - {r['text']}")
        except Exception as e: log.error(f"Reminder error: {e}")

async def process_offline_queue(context):
    pending = offline_queue.get_pending()
    if not pending: return
    log.info(f"📥 Processing {len(pending)} offline messages...")
    for i, msg in enumerate(pending):
        try:
            reply = await ai_chat(msg["msg"], chat_id=msg["cid"])
            if reply and reply != "OFFLINE":
                await context.bot.send_message(chat_id=msg["cid"],
                    text=f"📥 *Offline Message Processed!*\n\n_{msg['msg'][:100]}_\n\n💬 *Reply:* {reply[:500]}",
                    parse_mode="Markdown")
                offline_queue.mark_done(i)
                activity_log.add("offline_processed", msg["uid"], msg["msg"][:100])
                log.info(f"✅ Processed offline message from {msg['uname']}")
            else: break  # Still offline, stop processing
        except Exception as e: log.error(f"Offline process error: {e}")
    offline_queue.cleanup()

# ═══════════════ MAIN ═══════════════
def main():
    log.info("🤖 Bot v5.0 Starting...")
    log.info("✅ Features: Offline Queue | Secret Code | Activity Log | Persistent Data")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    handlers = [
        ("start", cmd_start), ("help", cmd_help),
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("alltasks", cmd_all_tasks), ("completed", cmd_completed_tasks), ("pending", cmd_pending_tasks),
        ("diary", cmd_diary), ("remember", cmd_remember), ("recall", cmd_recall),
        ("habit", lambda u,c: None), ("hdone", lambda u,c: None),
        ("kharcha", cmd_kharcha), ("budget", cmd_budget),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list), ("delremind", cmd_delremind),
        ("water", cmd_water), ("waterstatus", lambda u,c: None), ("watergoal", lambda u,c: None),
        ("bill", lambda u,c: None), ("bills", lambda u,c: None), ("billpaid", lambda u,c: None),
        ("cal", lambda u,c: None), ("calendar", lambda u,c: None),
        ("verify", cmd_verify), ("taskhistory", cmd_task_history),
        ("activitylog", cmd_activity_log), ("reminderlog", cmd_reminder_history),
        ("offlinemsgs", cmd_offline_messages), ("activity", cmd_activity_today),
        ("clear", cmd_clear), ("nuke", cmd_nuke),
        ("yesterday", lambda u,c: show_yesterday(u.message)),
        ("briefing", lambda u,c: send_briefing(u.message)),
    ]
    for cmd, handler in handlers: app.add_handler(CommandHandler(cmd, handler))
    
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(reminder_job, interval=30, first=5)
        job_queue.run_repeating(process_offline_queue, interval=120, first=30)
        log.info("⏰ Jobs: Reminder (30s) | Offline Processor (2min)")
    
    log.info("✅ Bot ready! /start karo")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
