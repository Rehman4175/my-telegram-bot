#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, logging, time, asyncio, urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta
from xml.etree import ElementTree as ET
import hashlib, threading, re as _re

ssl._create_default_https_context = ssl._create_unverified_context

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()])
log = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    log.error("❌ Set TELEGRAM_TOKEN and GEMINI_API_KEY")
    exit(1)

SECRET_CODE = "Rk1996"
SECRET_CODE_HASH = hashlib.sha256(SECRET_CODE.encode()).hexdigest()
GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

DATA = os.path.join(os.getcwd(), "data")
os.makedirs(DATA, exist_ok=True)

F_MEMORY = os.path.join(DATA, "memory.json")
F_TASKS = os.path.join(DATA, "tasks.json")
F_DIARY = os.path.join(DATA, "diary.json")
F_HABITS = os.path.join(DATA, "habits.json")
F_NOTES = os.path.join(DATA, "notes.json")
F_EXPENSES = os.path.join(DATA, "expenses.json")
F_GOALS = os.path.join(DATA, "goals.json")
F_CHAT = os.path.join(DATA, "chat_history.json")
F_NEWS = os.path.join(DATA, "news_cache.json")
F_REMINDERS = os.path.join(DATA, "reminders.json")
F_WATER = os.path.join(DATA, "water.json")
F_BILLS = os.path.join(DATA, "bills.json")
F_CALENDAR = os.path.join(DATA, "calendar.json")
F_OFFLINE = os.path.join(DATA, "offline_queue.json")
F_ALL_LOGS = os.path.join(DATA, "all_activity_log.json")

NEWS_FEEDS = {
    "India": "https://feeds.bbci.co.uk/hindi/rss.xml",
    "Technology": "https://feeds.feedburner.com/ndtvnews-tech-news",
    "Business": "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Sports": "https://feeds.bbci.co.uk/sport/rss.xml",
}

def load(path, default=None):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception as e: log.warning(f"Load error {path}: {e}")
    return default if default is not None else {}

def save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e: log.error(f"Save error {path}: {e}")

def today_str(): return date.today().isoformat()
def now_str(): return datetime.now().strftime("%H:%M")
def yesterday_str(): return (date.today() - timedelta(days=1)).isoformat()
def verify_secret_code(code: str): return hashlib.sha256(code.encode()).hexdigest() == SECRET_CODE_HASH

def call_gemini(system_prompt: str, messages: list, retries=2) -> str:
    contents = [
        {"role": "user", "parts": [{"text": f"[SYSTEM]\n{system_prompt}\n[/SYSTEM]\n\nReady ho?"}]},
        {"role": "model", "parts": [{"text": "Haan ready hoon! Batao."}]},
    ]
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    payload = json.dumps({"contents": contents, "generationConfig": {"temperature": 0.75, "maxOutputTokens": 600}}).encode("utf-8")
    errors = []
    for model in GEMINI_MODELS:
        for attempt in range(retries):
            try:
                url = BASE_URL.format(model=model, key=GEMINI_API_KEY)
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=45) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    return result["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code == 429: time.sleep(3 if attempt == 0 else 6); continue
                elif e.code in (500, 503): time.sleep(2); continue
                elif e.code == 404: break
                else: return f"❌ API Error {e.code}"
            except Exception as e: errors.append(str(e)); break
    return "⚠️ *AI Abhi Offline Hai!*\n\n📝 Aapka message save kar liya hai - jab AI online hoga tab process hoga."

def fetch_news(category="India", max_items=5) -> list:
    cache = load(F_NEWS, {"cache": {}, "updated": {}})
    now_ts = time.time()
    if category in cache["cache"] and now_ts - cache["updated"].get(category, 0) < 1800:
        return cache["cache"][category][:max_items]
    url = NEWS_FEEDS.get(category, NEWS_FEEDS["India"]); items = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            tree = ET.parse(resp)
            for item in (tree.getroot().find("channel") or tree.getroot()).findall("item")[:max_items]:
                title = item.findtext("title", "").strip()
                if title: items.append({"title": title, "desc": (item.findtext("description", "") or "")[:120], "link": item.findtext("link", "").strip(), "pub": item.findtext("pubDate", "").strip()})
    except Exception as e: return [{"title": "News abhi available nahi", "desc": str(e), "link": "", "pub": ""}]
    cache["cache"][category] = items; cache["updated"][category] = now_ts; save(F_NEWS, cache)
    return items

# ═══════════════════ CLASSES ═══════════════════
class ChatHistory:
    def __init__(self):
        self.data = load(F_CHAT, {"history": [], "cleared_at": None, "msg_ids": []})
        if "msg_ids" not in self.data: self.data["msg_ids"] = []
    def add(self, role, content):
        self.data["history"].append({"role": role, "content": content, "time": datetime.now().isoformat()})
        self.data["history"] = self.data["history"][-80:]; save(F_CHAT, self.data)
    def track_msg(self, chat_id, msg_id):
        self.data["msg_ids"].append({"chat_id": chat_id, "msg_id": msg_id})
        self.data["msg_ids"] = self.data["msg_ids"][-500:]; save(F_CHAT, self.data)
    def get_tracked_ids(self): return self.data.get("msg_ids", [])
    def get_recent(self, n=20): return [{"role": m["role"], "content": m["content"]} for m in self.data["history"][-n:]]
    def clear(self):
        count = len(self.data["history"]); self.data["history"] = []
        self.data["cleared_at"] = datetime.now().isoformat(); save(F_CHAT, self.data); return count
    def clear_msg_ids(self): self.data["msg_ids"] = []; save(F_CHAT, self.data)
    def count(self): return len(self.data["history"])

class Memory:
    def __init__(self):
        self.data = load(F_MEMORY, {"facts": [], "prefs": {}, "dates": {}, "important_notes": []})
    def save_data(self): save(F_MEMORY, self.data)
    def add_fact(self, fact):
        if fact[:50] in [f["f"][:50] for f in self.data["facts"][-50:]]: return
        self.data["facts"].append({"f": fact, "d": today_str()})
        self.data["facts"] = self.data["facts"][-400:]; self.save_data()
    def add_important(self, note): self.data["important_notes"].append({"note": note, "d": today_str()}); self.save_data()
    def set_pref(self, k, v): self.data["prefs"][k] = v; self.save_data()
    def add_date(self, name, d): self.data["dates"][name] = d; self.save_data()
    def context(self):
        facts = "\n".join(f"• {x['f']}" for x in self.data["facts"][-30:]) or "Kuch nahi"
        prefs = "\n".join(f"• {k}: {v}" for k, v in self.data["prefs"].items()) or "Kuch nahi"
        dates = "\n".join(f"• {k}: {v}" for k, v in self.data["dates"].items()) or "Kuch nahi"
        imp = "\n".join(f"⭐ {n['note']}" for n in self.data["important_notes"][-10:]) or "Kuch nahi"
        return f"FACTS:\n{facts}\n\nPREFERENCES:\n{prefs}\n\nDATES:\n{dates}\n\nIMPORTANT:\n{imp}"

class Tasks:
    def __init__(self):
        self.data = load(F_TASKS, {"list": [], "counter": 0, "completed_history": []})
    def save_data(self): save(F_TASKS, self.data)
    def add(self, title, priority="medium", due=None):
        self.data["counter"] += 1
        t = {"id": self.data["counter"], "title": title, "priority": priority, "due": due or today_str(),
             "done": False, "done_at": None, "created": datetime.now().isoformat(), "completed_date": None}
        self.data["list"].append(t); self.save_data(); return t
    def complete(self, tid):
        for t in self.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True; t["done_at"] = datetime.now().isoformat(); t["completed_date"] = today_str()
                self.data["completed_history"].append({"original_task": t.copy(), "completed_timestamp": datetime.now().isoformat()})
                self.save_data(); return t
        return None
    def delete(self, tid):
        before = len(self.data["list"]); self.data["list"] = [t for t in self.data["list"] if t["id"] != tid]; self.save_data()
        return before != len(self.data["list"])
    def pending(self): return [t for t in self.data["list"] if not t["done"]]
    def all_tasks(self): return self.data["list"]
    def completed_tasks(self): return [t for t in self.data["list"] if t["done"]]
    def done_on(self, d): return [t for t in self.data["list"] if t["done"] and t.get("completed_date", "") == d]
    def today_pending(self):
        td = today_str(); return [t for t in self.data["list"] if not t["done"] and t.get("due", "") <= td]
    def clear_done(self):
        before = len(self.data["list"])
        self.data["list"] = [t for t in self.data["list"] if not t["done"]]; self.save_data()
        return before - len(self.data["list"])
    def get_completed_history(self, date_filter=None):
        history = []
        for entry in self.data.get("completed_history", []):
            task = entry.get("original_task", entry.get("task", {}))
            if not date_filter or task.get("completed_date") == date_filter: history.append(task)
        return history

class Diary:
    def __init__(self): self.data = load(F_DIARY, {"entries": {}})
    def save_data(self): save(F_DIARY, self.data)
    def add(self, content, mood="😊"):
        td = today_str()
        if td not in self.data["entries"]: self.data["entries"][td] = []
        self.data["entries"][td].append({"text": content, "mood": mood, "time": now_str()}); self.save_data()
    def get(self, d): return self.data["entries"].get(d, [])

class Habits:
    def __init__(self): self.data = load(F_HABITS, {"list": [], "logs": {}, "counter": 0})
    def save_data(self): save(F_HABITS, self.data)
    def add(self, name, emoji="✅"):
        self.data["counter"] += 1
        h = {"id": self.data["counter"], "name": name, "emoji": emoji, "streak": 0, "best_streak": 0, "created": today_str()}
        self.data["list"].append(h); self.save_data(); return h
    def log(self, hid):
        td, yd = today_str(), yesterday_str()
        if td not in self.data["logs"]: self.data["logs"][td] = []
        if hid in self.data["logs"][td]: return False, 0
        self.data["logs"][td].append(hid)
        for h in self.data["list"]:
            if h["id"] == hid:
                yd_logs = self.data["logs"].get(yd, [])
                h["streak"] = h["streak"] + 1 if hid in yd_logs else 1
                h["best_streak"] = max(h.get("best_streak", 0), h["streak"])
        self.save_data(); return True, next((x["streak"] for x in self.data["list"] if x["id"] == hid), 1)
    def today_status(self):
        done_ids = self.data["logs"].get(today_str(), [])
        return ([h for h in self.data["list"] if h["id"] in done_ids], [h for h in self.data["list"] if h["id"] not in done_ids])
    def delete(self, hid): self.data["list"] = [h for h in self.data["list"] if h["id"] != hid]; self.save_data()
    def all(self): return self.data["list"]

class Notes:
    def __init__(self): self.data = load(F_NOTES, {"list": [], "counter": 0})
    def save_data(self): save(F_NOTES, self.data)
    def add(self, content, tag="general"):
        self.data["counter"] += 1
        n = {"id": self.data["counter"], "text": content, "tag": tag, "created": datetime.now().isoformat()}
        self.data["list"].append(n); self.save_data(); return n
    def delete(self, nid): self.data["list"] = [n for n in self.data["list"] if n["id"] != nid]; self.save_data()
    def recent(self, n=15): return self.data["list"][-n:]

class Expenses:
    def __init__(self): self.data = load(F_EXPENSES, {"list": [], "counter": 0, "budget": {}})
    def save_data(self): save(F_EXPENSES, self.data)
    def add(self, amount, desc, category="general"):
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "amount": amount, "desc": desc, "category": category, "date": today_str(), "time": now_str()}
        self.data["list"].append(e); self.save_data(); return e
    def set_budget(self, amount): self.data["budget"]["monthly"] = amount; self.save_data()
    def today_total(self): return sum(e["amount"] for e in self.data["list"] if e["date"] == today_str())
    def month_total(self): return sum(e["amount"] for e in self.data["list"] if e["date"][:7] == today_str()[:7])
    def today_list(self): return [e for e in self.data["list"] if e["date"] == today_str()]
    def budget_left(self):
        b = self.data["budget"].get("monthly", 0); return b - self.month_total() if b else None

class Goals:
    def __init__(self): self.data = load(F_GOALS, {"list": [], "counter": 0})
    def save_data(self): save(F_GOALS, self.data)
    def add(self, title, deadline=None, why=""):
        self.data["counter"] += 1
        g = {"id": self.data["counter"], "title": title, "deadline": deadline or "", "why": why, "progress": 0, "done": False, "created": today_str(), "milestones": []}
        self.data["list"].append(g); self.save_data(); return g
    def update_progress(self, gid, pct):
        for g in self.data["list"]:
            if g["id"] == gid:
                g["progress"] = min(100, max(0, pct))
                if g["progress"] == 100: g["done"] = True
                self.save_data(); return g
        return None
    def active(self): return [g for g in self.data["list"] if not g["done"]]
    def completed(self): return [g for g in self.data["list"] if g["done"]]

class Reminders:
    def __init__(self): self.data = load(F_REMINDERS, {"list": [], "counter": 0, "log": []})
    def save_data(self): save(F_REMINDERS, self.data)
    def add(self, chat_id, text, remind_at, repeat="once"):
        self.data["counter"] += 1
        r = {"id": self.data["counter"], "chat_id": chat_id, "text": text, "time": remind_at, "repeat": repeat,
             "date": today_str(), "active": True, "fired_today": False, "created": datetime.now().isoformat(), "history": []}
        self.data["list"].append(r); self.save_data(); return r
    def all_active(self): return [r for r in self.data["list"] if r["active"]]
    def delete(self, rid):
        before = len(self.data["list"]); self.data["list"] = [r for r in self.data["list"] if r["id"] != rid]; self.save_data()
        return before != len(self.data["list"])
    def mark_fired(self, rid):
        for r in self.data["list"]:
            if r["id"] == rid:
                r["fired_today"] = True; r["history"].append({"fired_at": datetime.now().isoformat(), "date": today_str()})
                if r["repeat"] == "once": r["active"] = False
                self.save_data(); break
    def reset_daily(self):
        changed = False
        for r in self.data["list"]:
            if r["fired_today"]: r["fired_today"] = False; changed = True
        if changed: self.save_data()
    def due_now(self):
        now_dt = datetime.now(); now_hm = now_dt.strftime("%H:%M"); due = []
        for r in self.data["list"]:
            if not r["active"] or r["fired_today"]: continue
            try:
                r_dt = datetime.strptime(today_str() + " " + r["time"], "%Y-%m-%d %H:%M")
                if 0 <= (now_dt - r_dt).total_seconds() < 120: due.append(r)
            except:
                if r["time"] == now_hm: due.append(r)
        return due
    def get_all(self): return self.data["list"]

class WaterTracker:
    def __init__(self): self.data = load(F_WATER, {"logs": {}, "goal_ml": 2000})
    def save_data(self): save(F_WATER, self.data)
    def add(self, ml=250):
        td = today_str()
        if td not in self.data["logs"]: self.data["logs"][td] = []
        self.data["logs"][td].append({"ml": ml, "time": now_str()}); self.save_data()
    def today_total(self): return sum(e["ml"] for e in self.data["logs"].get(today_str(), []))
    def goal(self): return self.data.get("goal_ml", 2000)
    def set_goal(self, ml): self.data["goal_ml"] = ml; self.save_data()
    def week_summary(self):
        result = {}
        for i in range(7): d = (date.today() - timedelta(days=i)).isoformat(); result[d] = sum(e["ml"] for e in self.data["logs"].get(d, []))
        return result

class BillTracker:
    def __init__(self): self.data = load(F_BILLS, {"list": [], "counter": 0})
    def save_data(self): save(F_BILLS, self.data)
    def add(self, name, amount, due_day, bill_type="bill", notes=""):
        self.data["counter"] += 1
        b = {"id": self.data["counter"], "name": name, "amount": amount, "due_day": due_day, "type": bill_type, "notes": notes, "active": True, "paid_months": [], "created": today_str()}
        self.data["list"].append(b); self.save_data(); return b
    def all_active(self): return [b for b in self.data["list"] if b["active"]]
    def mark_paid(self, bid):
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid and ym not in b["paid_months"]: b["paid_months"].append(ym); self.save_data(); return True
        return False
    def is_paid_this_month(self, bid):
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid: return ym in b.get("paid_months", [])
        return False
    def delete(self, bid):
        before = len(self.data["list"]); self.data["list"] = [b for b in self.data["list"] if b["id"] != bid]; self.save_data()
        return before != len(self.data["list"])
    def due_soon(self, days_ahead=3):
        today_d = date.today(); result = []
        for b in self.data["list"]:
            if not b["active"] or self.is_paid_this_month(b["id"]): continue
            try: due_date = date(today_d.year, today_d.month, b["due_day"])
            except: due_date = date(today_d.year, today_d.month, 28)
            if today_d <= due_date <= today_d + timedelta(days=days_ahead): result.append({**b, "due_date": due_date.isoformat()})
        return result
    def month_total(self): return sum(b["amount"] for b in self.data["list"] if b["active"])

class CalendarManager:
    def __init__(self): self.data = load(F_CALENDAR, {"events": [], "counter": 0})
    def save_data(self): save(F_CALENDAR, self.data)
    def add(self, title, event_date, event_time="", notes=""):
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "title": title, "date": event_date, "time": event_time, "notes": notes, "created": today_str()}
        self.data["events"].append(e); self.save_data(); return e
    def delete(self, eid):
        before = len(self.data["events"]); self.data["events"] = [e for e in self.data["events"] if e["id"] != eid]; self.save_data()
        return before != len(self.data["events"])
    def upcoming(self, days=7):
        today_d = date.today(); cutoff = today_d + timedelta(days=days); result = []
        for e in self.data["events"]:
            try:
                ed = date.fromisoformat(e["date"])
                if today_d <= ed <= cutoff: result.append(e)
            except: pass
        return sorted(result, key=lambda x: x["date"])
    def today_events(self): return [e for e in self.data["events"] if e["date"] == today_str()]

class ActivityLogger:
    def __init__(self):
        self.log_file = F_ALL_LOGS; self.data = self.load_logs()
    def load_logs(self):
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
        return {"activities": [], "protected_activities": []}
    def save_logs(self):
        try:
            with open(self.log_file, "w", encoding="utf-8") as f: json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass
    def log_activity(self, atype, uid, uname, content, status="completed", protected=False):
        a = {"timestamp": datetime.now().isoformat(), "type": atype, "user_id": uid, "username": uname, "content": content[:500], "status": status, "date": today_str()}
        self.data["activities"].append(a)
        if protected or atype in ["task_added", "task_completed", "memory_saved", "reminder_set", "reminder_fired"]:
            self.data["protected_activities"].append(a)
        self.data["activities"] = self.data["activities"][-10000:]; self.data["protected_activities"] = self.data["protected_activities"][-5000:]; self.save_logs()

class OfflineQueue:
    def __init__(self):
        self.queue_file = F_OFFLINE; self.queue = self.load_queue(); self.lock = threading.Lock()
    def load_queue(self):
        try:
            if os.path.exists(self.queue_file):
                with open(self.queue_file, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
        return {"pending_messages": [], "processed_messages": []}
    def save_queue(self):
        with self.lock:
            try:
                with open(self.queue_file, "w", encoding="utf-8") as f: json.dump(self.queue, f, ensure_ascii=False, indent=2)
            except: pass
    def add_message(self, uid, cid, uname, msg):
        with self.lock:
            self.queue["pending_messages"].append({"timestamp": datetime.now().isoformat(), "user_id": uid, "chat_id": cid, "username": uname, "message": msg, "processed": False})
            self.save_queue()
    def get_pending_messages(self): return [m for m in self.queue["pending_messages"] if not m["processed"]]
    def mark_processed(self, idx):
        with self.lock:
            if 0 <= idx < len(self.queue["pending_messages"]): self.queue["pending_messages"][idx]["processed"] = True; self.save_queue()
    def clear_processed(self):
        with self.lock:
            unprocessed = [m for m in self.queue["pending_messages"] if not m["processed"]]
            processed = [m for m in self.queue["pending_messages"] if m["processed"]]
            self.queue["pending_messages"] = unprocessed + processed[-100:]; self.save_queue()

# ═══════════════════ INIT OBJECTS ═══════════════════
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
activity_logger = ActivityLogger()
offline_queue = OfflineQueue()
log.info("✅ All objects initialized!")

# ═══════════════════ FUNCTIONS ═══════════════════
def build_system_prompt():
    nl = datetime.now().strftime("%A, %d %B %Y — %I:%M %p")
    tp = tasks.today_pending(); hd, hp = habits.today_status()
    ts = "\n".join(f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}" for t in tp[:6]) or "  Koi nahi"
    hdone = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    hpend = ", ".join(h['name'] for h in hp) or "Sab ho gaye!"
    return f"""Tu mera AI Assistant 'Dost' hai. Hindi/Hinglish mein baat kar.
⏰ {nl} | 💬 {chat_hist.count()} msgs
📋 AAJ KE TASKS:\n{ts}
💪 HABITS: Done: {hdone} | Baaki: {hpend}
💰 KHARCHA: Aaj ₹{expenses.today_total()} | Mahina ₹{expenses.month_total()}
💧 PAANI: {water.today_total()}ml / {water.goal()}ml
━━ YAADDASHT ━━\n{mem.context()}
RULES: Dost ki tarah baat kar, short aur helpful reh."""

def auto_extract_facts(text):
    if any(k in text.lower() for k in ["yaad rakh", "remember", "mera naam", "meri umar"]):
        mem.add_fact(text[:250]); return True
    return False

async def ai_chat(user_msg, chat_id=None):
    auto_extract_facts(user_msg); chat_hist.add("user", user_msg)
    reply = call_gemini(build_system_prompt(), chat_hist.get_recent(20))
    chat_hist.add("assistant", reply); return reply

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Daily Briefing", callback_data="briefing"), InlineKeyboardButton("📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("💪 Habits", callback_data="habits"), InlineKeyboardButton("📖 Diary", callback_data="diary")],
        [InlineKeyboardButton("🎯 Goals", callback_data="goals"), InlineKeyboardButton("💰 Kharcha", callback_data="expenses")],
        [InlineKeyboardButton("📰 News", callback_data="news_menu"), InlineKeyboardButton("📝 Notes", callback_data="notes")],
        [InlineKeyboardButton("💧 Water", callback_data="water_status"), InlineKeyboardButton("💳 Bills", callback_data="bills_menu")],
        [InlineKeyboardButton("📅 Calendar", callback_data="cal_menu"), InlineKeyboardButton("📊 Weekly", callback_data="weekly_report")],
        [InlineKeyboardButton("🧹 Clear Chat", callback_data="clear_chat"), InlineKeyboardButton("🧠 Yaaddasht", callback_data="memory")],
        [InlineKeyboardButton("📊 Kal Summary", callback_data="yesterday"), InlineKeyboardButton("💡 Motivate", callback_data="motivate")],
    ])

def news_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇳 India", callback_data="news_India"), InlineKeyboardButton("💻 Tech", callback_data="news_Technology")],
        [InlineKeyboardButton("💼 Business", callback_data="news_Business"), InlineKeyboardButton("🌍 World", callback_data="news_World")],
        [InlineKeyboardButton("🏏 Sports", callback_data="news_Sports"), InlineKeyboardButton("🏠 Back", callback_data="menu")],
    ])

# ═══════════════════ HANDLERS ═══════════════════
async def send_briefing(msg_obj):
    tp = tasks.today_pending(); yd = tasks.done_on(yesterday_str())
    hd, hp = habits.today_status(); tl = datetime.now().strftime("%A, %d %B %Y")
    txt = f"🌅 *DAILY BRIEFING*\n📅 {tl}\n\n"
    if yd: txt += f"✅ *Kal {len(yd)} kaam kiye:*\n" + "\n".join(f"  • {t['title']}" for t in yd[:5]) + "\n\n"
    if tp:
        txt += f"📋 *Aaj {len(tp)} kaam baaki:*\n"
        for t in tp[:7]: txt += f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}\n"
        txt += "\n"
    else: txt += "🎉 *Koi pending task nahi!*\n\n"
    if hp: txt += f"💪 *{len(hp)} Habits baaki:*\n" + "\n".join(f"  ○ {h['emoji']} {h['name']}" for h in hp[:4]) + "\n\n"
    txt += f"💰 *Kharcha:* Aaj ₹{expenses.today_total():.0f} | Mahina ₹{expenses.month_total():.0f}\n"
    wt = water.today_total(); wg = water.goal(); wp = min(100, int(wt/wg*100)) if wg else 0
    txt += f"💧 *Paani:* {wt}ml / {wg}ml ({wp}%)\n\n💪 *Aaj ka din badiya banao!* 🚀"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def show_tasks(msg_obj):
    pending = tasks.pending()
    if not pending: await msg_obj.reply_text("🎉 Koi pending task nahi!", parse_mode="Markdown"); return
    txt = f"📋 *TASKS ({len(pending)})*\n\n"; kb = []
    for t in pending[:12]:
        txt += f"{'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} *#{t['id']}* {t['title']}\n"
        kb.append([InlineKeyboardButton(f"✅ #{t['id']}: {t['title'][:32]}", callback_data=f"done_{t['id']}")])
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def show_habits(msg_obj):
    done, pending = habits.today_status()
    if not habits.all(): await msg_obj.reply_text("💪 Koi habit nahi!", parse_mode="Markdown"); return
    txt = "💪 *HABITS*\n\n"; kb = []
    if done: txt += "✅ *Done:*\n" + "\n".join(f"  {h['emoji']} {h['name']} 🔥{h['streak']}" for h in done) + "\n\n"
    if pending:
        txt += "⏳ *Baaki:*\n"
        for h in pending: txt += f"  ○ {h['emoji']} {h['name']}\n"; kb.append([InlineKeyboardButton(f"✅ {h['emoji']} {h['name']}", callback_data=f"habit_{h['id']}")])
    else: txt += "🎊 Sab complete!"
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def show_news(msg_obj, category="India"):
    items = fetch_news(category, 5)
    txt = f"📰 *{category.upper()} NEWS*\n\n" + "\n".join(f"*{i+1}.* {item['title']}" for i, item in enumerate(items))
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=news_kb())

async def show_diary(msg_obj):
    td = diary.get(today_str()); txt = "📖 *DIARY*\n\n"
    if td: txt += "\n".join(f"  {e['time']} {e['mood']} {e['text']}" for e in td)
    else: txt += "_Koi entry nahi_"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

async def show_goals(msg_obj):
    ag = goals.active()
    if not ag: await msg_obj.reply_text("🎯 Koi goals nahi!", parse_mode="Markdown"); return
    txt = f"🎯 *GOALS ({len(ag)})*\n\n"; kb = []
    for g in ag:
        bar = "█"*(g["progress"]//10) + "░"*(10-g["progress"]//10)
        txt += f"*{g['title']}*\n{bar} {g['progress']}%\n\n"
        kb.append([InlineKeyboardButton(f"📊 {g['title'][:30]}", callback_data=f"goal_{g['id']}")])
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def show_notes(msg_obj):
    ns = notes.recent(12)
    if not ns: await msg_obj.reply_text("📝 Koi notes nahi!", parse_mode="Markdown"); return
    txt = "📝 *NOTES*\n\n" + "\n".join(f"*#{n['id']}* {n['text']}" for n in ns)
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

async def show_yesterday(msg_obj):
    yd = tasks.done_on(yesterday_str())
    txt = f"📅 *KAL KA SUMMARY*\n\n"
    if yd: txt += f"✅ *{len(yd)} Tasks Kiye:*\n" + "\n".join(f"  • {t['title']}" for t in yd)
    else: txt += "_Koi data nahi_"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

# Commands
async def cmd_start(update, ctx):
    await update.message.reply_text(f"🕌 *Assalamualaikum {update.effective_user.first_name or 'Dost'}!*\n\n🧠 Smart Memory | 📋 Tasks | 💪 Habits\n💰 Kharcha | ⏰ Reminders | 📰 News\n🔐 Secret Code: `Rk1996`\n\n✅ Seedha type karo! 👇", parse_mode="Markdown", reply_markup=main_kb())

async def cmd_briefing(update, ctx): await send_briefing(update.message)

async def cmd_task(update, ctx):
    if not ctx.args: await update.message.reply_text("📋 `/task Kaam naam` | `/task Important high`", parse_mode="Markdown"); return
    args = " ".join(ctx.args); priority = "medium"
    if args.endswith(" high"): priority = "high"; args = args[:-5].strip()
    elif args.endswith(" low"): priority = "low"; args = args[:-4].strip()
    t = tasks.add(args, priority)
    await update.message.reply_text(f"✅ *Task Add!*\n{'🔴' if priority=='high' else '🟡' if priority=='medium' else '🟢'} {t['title']}", parse_mode="Markdown")

async def cmd_done(update, ctx):
    if not ctx.args: await update.message.reply_text("`/done 3`", parse_mode="Markdown"); return
    try:
        t = tasks.complete(int(ctx.args[0]))
        await update.message.reply_text(f"🎉 *Complete!*\n✅ {t['title']}" if t else "❌ Nahi mila", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/done 3`", parse_mode="Markdown")

async def cmd_deltask(update, ctx):
    if not ctx.args: await update.message.reply_text("`/deltask 3`", parse_mode="Markdown"); return
    try: await update.message.reply_text("🗑 *Delete!*" if tasks.delete(int(ctx.args[0])) else "❌ Nahi mila", parse_mode="Markdown")
    except: pass

async def cmd_diary(update, ctx):
    if not ctx.args: await update.message.reply_text("📖 `/diary Aaj bahut productive tha!`", parse_mode="Markdown"); return
    diary.add(" ".join(ctx.args))
    await update.message.reply_text(f"📖 *Diary Mein Likh Diya!*", parse_mode="Markdown")

async def cmd_remember(update, ctx):
    if not ctx.args: await update.message.reply_text("🧠 `/remember Mera birthday 15 August`", parse_mode="Markdown"); return
    mem.add_fact(" ".join(ctx.args))
    await update.message.reply_text("🧠 *Yaad Kar Liya!* ✅\n_Chat clear bhi ho toh safe_ 🔒", parse_mode="Markdown")

async def cmd_recall(update, ctx):
    facts = mem.data["facts"]
    txt = f"🧠 *YAADDASHT ({len(facts)})*\n\n" + "\n".join(f"  📌 {f['f']}" for f in facts[-15:]) if facts else "🧠 Kuch yaad nahi."
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_habit(update, ctx):
    if not ctx.args: await update.message.reply_text("💪 `/habit Morning walk 🏃`", parse_mode="Markdown"); return
    name = " ".join(ctx.args); emoji = "✅"
    for em in ["💪","🏃","📚","💧","🧘","🌅"]:
        if em in name: emoji = em; break
    h = habits.add(name, emoji)
    await update.message.reply_text(f"💪 *Habit Add!*\n{h['emoji']} {h['name']}\n`/hdone {h['id']}`", parse_mode="Markdown")

async def cmd_hdone(update, ctx):
    if not ctx.args:
        _, pending = habits.today_status()
        txt = "💪 *Kaunsi?*\n" + "\n".join(f"`/hdone {h['id']}` — {h['emoji']} {h['name']}" for h in pending) if pending else "🎊 Sab done!"
        await update.message.reply_text(txt, parse_mode="Markdown"); return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        await update.message.reply_text(f"💪 *Done!* 🔥{streak} din!" if ok else "✅ Pehle hi mark hai!", parse_mode="Markdown")
    except: pass

async def cmd_kharcha(update, ctx):
    if not ctx.args: await update.message.reply_text("💰 `/kharcha 100 Food`", parse_mode="Markdown"); return
    try:
        amount = float(ctx.args[0]); rest = " ".join(ctx.args[1:]) or "Kharcha"
        expenses.add(amount, rest)
        await update.message.reply_text(f"💰 *₹{amount:.0f} — {rest}*\nAaj total: ₹{expenses.today_total():.0f}", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/kharcha 100 Khana`", parse_mode="Markdown")

async def cmd_budget(update, ctx):
    if not ctx.args: await update.message.reply_text("💳 `/budget 5000`", parse_mode="Markdown"); return
    try: expenses.set_budget(float(ctx.args[0])); await update.message.reply_text(f"💳 *Budget Set: ₹{ctx.args[0]}*", parse_mode="Markdown")
    except: pass

async def cmd_goal(update, ctx):
    if not ctx.args: await update.message.reply_text("🎯 `/goal Weight lose`", parse_mode="Markdown"); return
    goals.add(" ".join(ctx.args))
    await update.message.reply_text("🎯 *Goal Add!*", parse_mode="Markdown")

async def cmd_news(update, ctx): await update.message.reply_text("📰 *Kaunsi news?*", parse_mode="Markdown", reply_markup=news_kb())

async def cmd_clear(update, ctx):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Haan", callback_data="confirm_clear_chat"), InlineKeyboardButton("❌ Nahi", callback_data="menu")]])
    await update.message.reply_text(f"🧹 *Clear?* 📊 {chat_hist.count()} msgs", parse_mode="Markdown", reply_markup=kb)

async def cmd_remind(update, ctx):
    if not ctx.args: await update.message.reply_text("⏰ `/remind 30m Chai` | `/remind 15:30 Doctor`", parse_mode="Markdown"); return
    time_str, repeat, text = None, "once", "Reminder"
    ta = ctx.args[0].lower(); rest = ctx.args[1:]
    if rest and rest[-1].lower() in ["daily", "weekly"]: repeat = rest[-1].lower(); rest = rest[:-1]
    if rest: text = " ".join(rest)
    now = datetime.now()
    if ta.endswith("m") and ta[:-1].isdigit(): time_str = (now + timedelta(minutes=int(ta[:-1]))).strftime("%H:%M")
    elif ta.endswith("h") and ta[:-1].isdigit(): time_str = (now + timedelta(hours=int(ta[:-1]))).strftime("%H:%M")
    elif ":" in ta:
        parts = ta.split(":")
        if len(parts)==2 and parts[0].isdigit() and parts[1].isdigit(): time_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    if not time_str: await update.message.reply_text("❌ Format galat!", parse_mode="Markdown"); return
    r = reminders.add(update.effective_chat.id, text, time_str, repeat)
    await update.message.reply_text(f"✅ *Reminder Set!*\n⏰ {time_str}\n📝 {text}\n🆔 `{r['id']}`", parse_mode="Markdown")

async def cmd_reminders_list(update, ctx):
    all_r = reminders.all_active()
    if not all_r: await update.message.reply_text("⏰ Koi reminder nahi!", parse_mode="Markdown"); return
    txt = f"⏰ *REMINDERS ({len(all_r)})*\n\n"
    for r in all_r: txt += f"*#{r['id']}* `{r['time']}` — {r['text']}\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_delremind(update, ctx):
    if not ctx.args: await update.message.reply_text("🗑 `/delremind 3`", parse_mode="Markdown"); return
    try: await update.message.reply_text("🗑 *Delete!*" if reminders.delete(int(ctx.args[0])) else "❌ Nahi mila", parse_mode="Markdown")
    except: pass

async def cmd_water(update, ctx):
    ml = 250
    if ctx.args:
        try: ml = int(ctx.args[0])
        except: pass
    water.add(ml)
    await update.message.reply_text(f"💧 *+{ml}ml!*\nAaj: {water.today_total()}ml / {water.goal()}ml", parse_mode="Markdown")

async def cmd_water_status(update, ctx):
    t, g = water.today_total(), water.goal()
    pct = min(100, int(t/g*100)) if g else 0
    await update.message.reply_text(f"💧 *WATER*\n🎯 {g}ml\n✅ {t}ml ({pct}%)", parse_mode="Markdown")

async def cmd_bill(update, ctx):
    if not ctx.args or len(ctx.args)<3: await update.message.reply_text("💳 `/bill Netflix 199 5`", parse_mode="Markdown"); return
    try: b = bills.add(ctx.args[0], float(ctx.args[1]), int(ctx.args[2])); await update.message.reply_text(f"✅ *Bill Add!*\n📌 {b['name']} ₹{b['amount']:.0f}", parse_mode="Markdown")
    except: await update.message.reply_text("❌ Format galat!", parse_mode="Markdown")

async def cmd_bills_list(update, ctx):
    all_b = bills.all_active()
    if not all_b: await update.message.reply_text("💳 Koi bill nahi!", parse_mode="Markdown"); return
    txt = "💳 *BILLS*\n\n"
    for b in all_b: txt += f"{'✅' if bills.is_paid_this_month(b['id']) else '⏳'} {b['name']} — ₹{b['amount']:.0f}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_cal(update, ctx):
    if not ctx.args: await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`", parse_mode="Markdown"); return
    args_str = " ".join(ctx.args); date_str = today_str(); title = args_str
    m = _re.match(r'^(\d{4}-\d{2}-\d{2})\s+(.*)', args_str)
    if m: date_str, title = m.group(1), m.group(2)
    calendar.add(title, date_str)
    await update.message.reply_text(f"📅 *Event Add!*\n✨ {title}\n📆 {date_str}", parse_mode="Markdown")

async def cmd_cal_list(update, ctx):
    up = calendar.upcoming(30)
    if not up: await update.message.reply_text("📅 Koi event nahi!", parse_mode="Markdown"); return
    txt = "📅 *CALENDAR*\n\n" + "\n".join(f"📆 {e['date']} — {e['title']}" for e in up)
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_weekly_report(update, ctx):
    await update.message.reply_text(f"📊 *WEEKLY REPORT*\n\n📋 Tasks: {len(tasks.pending())} pending\n💰 Kharcha: ₹{expenses.month_total():.0f}\n💧 Paani: {water.today_total()}ml", parse_mode="Markdown")

async def cmd_all_tasks(update, ctx):
    all_t = tasks.all_tasks()
    if not all_t: await update.message.reply_text("📋 Koi task nahi!"); return
    txt = f"📋 *ALL TASKS ({len(all_t)})*\n\n"
    for t in all_t: txt += f"{'✅' if t['done'] else '⏳'} #{t['id']} {t['title']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed_tasks(update, ctx):
    comp = tasks.completed_tasks()
    if not comp: await update.message.reply_text("✅ Koi completed task nahi!"); return
    txt = f"✅ *COMPLETED ({len(comp)})*\n\n" + "\n".join(f"✓ #{t['id']} {t['title']} _{t.get('completed_date','')}_" for t in comp[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_verify_secret(update, ctx):
    if not ctx.args or not verify_secret_code(ctx.args[0]): await update.message.reply_text("❌ Galat code!"); return
    await update.message.reply_text("✅ *Verified!* Ab protected data access karo.", parse_mode="Markdown")

async def cmd_task_history(update, ctx):
    if not ctx.args or not verify_secret_code(ctx.args[0]): await update.message.reply_text("❌ `/taskhistory Rk1996`"); return
    ch = tasks.get_completed_history()
    txt = f"🔓 *TASK HISTORY ({len(ch)})*\n\n" + "\n".join(f"✓ {t.get('title','')} - {t.get('completed_date','')}" for t in ch[-20:])
    await update.message.reply_text(txt or "Koi history nahi!", parse_mode="Markdown")

async def cmd_help(update, ctx):
    await update.message.reply_text("🤖 *COMMANDS*\n📋 /task | /done | /alltasks | /completed\n🔐 /verify Rk1996 | /taskhistory Rk1996\n💪 /habit | /hdone | 💰 /kharcha | /budget\n⏰ /remind | /reminders | 💧 /water\n💳 /bill | /bills | 📅 /cal | /calendar\n📊 /weekly | 🧹 /clear", parse_mode="Markdown")

async def cmd_nuke(update, ctx):
    chat_hist.track_msg(update.effective_chat.id, update.message.message_id)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💣 Haan! Sab Saaf", callback_data="confirm_nuke"), InlineKeyboardButton("❌ Nahi", callback_data="menu")]])
    sent = await update.message.reply_text(f"💣 *NUKE*\n🗑 {len(chat_hist.get_tracked_ids())} msgs delete honge", parse_mode="Markdown", reply_markup=kb)
    chat_hist.track_msg(update.effective_chat.id, sent.message_id)

async def delete_telegram_messages(bot, tracked_ids):
    deleted, failed = 0, 0
    for i, entry in enumerate(tracked_ids):
        try: await bot.delete_message(chat_id=entry["chat_id"], message_id=entry["msg_id"]); deleted += 1
        except: failed += 1
        if i % 20 == 19: await asyncio.sleep(0.5)
    return deleted, failed

# ═══════════════════ CALLBACK ═══════════════════
async def callback(update, ctx):
    q = update.callback_query; await q.answer(); d = q.data
    if d == "menu": await q.message.reply_text("🏠 *Menu*", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "briefing": await send_briefing(q.message)
    elif d == "tasks": await show_tasks(q.message)
    elif d == "habits": await show_habits(q.message)
    elif d == "diary": await show_diary(q.message)
    elif d == "goals": await show_goals(q.message)
    elif d == "notes": await show_notes(q.message)
    elif d == "yesterday": await show_yesterday(q.message)
    elif d == "news_menu": await q.message.reply_text("📰 *News?*", parse_mode="Markdown", reply_markup=news_kb())
    elif d.startswith("news_"): await show_news(q.message, d.split("_", 1)[1])
    elif d == "memory":
        facts = mem.data["facts"]
        await q.message.reply_text(f"🧠 *YAADDASHT ({len(facts)})*", parse_mode="Markdown")
    elif d == "expenses":
        await q.message.reply_text(f"💰 *Kharcha* Aaj: ₹{expenses.today_total():.0f}", parse_mode="Markdown")
    elif d == "clear_chat":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Haan", callback_data="confirm_clear_chat"), InlineKeyboardButton("❌ Nahi", callback_data="menu")]])
        await q.message.reply_text(f"🧹 *Clear?* {chat_hist.count()} msgs", parse_mode="Markdown", reply_markup=kb)
    elif d == "confirm_clear_chat":
        count = chat_hist.clear()
        await q.message.reply_text(f"🧹 *Clear!* 🗑 {count} msgs\n🔒 Memory safe!", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "water_status": await cmd_water_status(update, ctx)
    elif d.startswith("water_") and d.split("_")[1].isdigit():
        ml = int(d.split("_")[1]); water.add(ml)
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
    elif d == "weekly_report": await cmd_weekly_report(update, ctx)
    elif d == "clear_done_tasks":
        count = tasks.clear_done(); await q.message.reply_text(f"🗑 {count} done tasks delete!")
    elif d == "motivate":
        reply = await ai_chat("Mujhe powerful motivation de Hindi mein. 3-4 line.")
        await q.message.reply_text(f"💡 *Motivation:*\n\n{reply}", parse_mode="Markdown")
    elif d.startswith("done_"):
        t = tasks.complete(int(d.split("_")[1]))
        await q.message.reply_text(f"🎉 *Complete!* ✅ {t['title']}" if t else "❌ Nahi mila", parse_mode="Markdown")
    elif d.startswith("habit_"):
        hid = int(d.split("_")[1]); ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"] == hid), None)
        await q.message.reply_text(f"💪 *Done!* {h['emoji']} {h['name']} 🔥{streak}" if ok and h else "✅ Pehle hi mark hai!", parse_mode="Markdown")
    elif d == "confirm_nuke":
        tracked = chat_hist.get_tracked_ids(); chat_id = q.message.chat_id
        sm = await q.message.reply_text("🧹 *Saaf ho rahi hai...*")
        deleted, _ = await delete_telegram_messages(q.get_bot(), tracked)
        chat_hist.clear(); chat_hist.clear_msg_ids()
        try: await sm.delete()
        except: pass
        try: await q.message.delete()
        except: pass
        await q.get_bot().send_message(chat_id=chat_id, text=f"🧹 *CHAT SAAF!*\n🗑 {deleted} delete\n🔒 Memory safe!\n_Fresh start!_ ✨", parse_mode="Markdown", reply_markup=main_kb())

# ═══════════════════ MESSAGE HANDLER ═══════════════════
async def handle_msg(update, ctx):
    user = update.effective_user; chat_id = update.effective_chat.id; msg = update.message.text
    chat_hist.track_msg(chat_id, update.message.message_id)
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        reply = await ai_chat(msg, chat_id=chat_id)
        if "⚠️ *AI Abhi Offline Hai!*" in reply: offline_queue.add_message(user.id, chat_id, user.username or user.first_name, msg)
        try: sent = await update.message.reply_text(reply, parse_mode="Markdown")
        except: sent = await update.message.reply_text(reply)
        chat_hist.track_msg(chat_id, sent.message_id)
    except Exception as e:
        log.error(f"Error: {e}")
        await update.message.reply_text("❌ *Error! Offline queue mein save kiya.*", parse_mode="Markdown")
        offline_queue.add_message(user.id, chat_id, user.username or user.first_name, msg)

# ═══════════════════ JOBS ═══════════════════
async def reminder_job(context):
    if datetime.now().strftime("%H:%M") == "00:00": reminders.reset_daily()
    for r in reminders.due_now():
        try:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ho Gaya!", callback_data=f"remind_done_{r['id']}"), InlineKeyboardButton("⏰ Snooze", callback_data=f"remind_snooze_{r['id']}")]])
            await context.bot.send_message(chat_id=r["chat_id"], text=f"🚨🔔 *ALARM!*\n⏰ *{r['time']}*\n📢 *{r['text'].upper()}*", parse_mode="Markdown", disable_notification=False, reply_markup=kb)
            await asyncio.sleep(2)
            await context.bot.send_message(chat_id=r["chat_id"], text=f"🔔 *REMINDER:* {r['text']}", parse_mode="Markdown", disable_notification=False)
            reminders.mark_fired(r["id"])
        except Exception as e: log.error(f"Reminder error: {e}")

async def process_offline_queue(context):
    for i, msg in enumerate(offline_queue.get_pending_messages()):
        try:
            reply = await ai_chat(msg["message"], chat_id=msg["chat_id"])
            await context.bot.send_message(chat_id=msg["chat_id"], text=f"📥 *Offline Processed!*\n\n💬 {reply[:500]}", parse_mode="Markdown")
            offline_queue.mark_processed(i)
        except: pass
    offline_queue.clear_processed()

# ═══════════════════ MAIN ═══════════════════
def main():
    log.info("🤖 Bot v4.5 Starting...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    handlers = [
        ("start", cmd_start), ("help", cmd_help), ("briefing", cmd_briefing),
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("diary", cmd_diary), ("remember", cmd_remember), ("recall", cmd_recall),
        ("habit", cmd_habit), ("hdone", cmd_hdone),
        ("kharcha", cmd_kharcha), ("budget", cmd_budget),
        ("goal", cmd_goal), ("news", cmd_news), ("clear", cmd_clear), ("nuke", cmd_nuke),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list), ("delremind", cmd_delremind),
        ("water", cmd_water), ("waterstatus", cmd_water_status),
        ("bill", cmd_bill), ("bills", cmd_bills_list),
        ("cal", cmd_cal), ("calendar", cmd_cal_list),
        ("weekly", cmd_weekly_report),
        ("alltasks", cmd_all_tasks), ("completed", cmd_completed_tasks),
        ("verify", cmd_verify_secret), ("taskhistory", cmd_task_history),
        ("yesterday", lambda u,c: show_yesterday(u.message)),
    ]
    for cmd, handler in handlers: app.add_handler(CommandHandler(cmd, handler))
    
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(reminder_job, interval=30, first=5)
        job_queue.run_repeating(process_offline_queue, interval=300, first=30)
        log.info("⏰ Jobs started!")
    
    log.info("✅ Bot ready! /start karo")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
