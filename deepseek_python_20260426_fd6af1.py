#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════╗
║       PERSONAL AI ASSISTANT — ADVANCED v4.0      ║
║  100% FREE | Gemini Multi-Model | News | Smart Memory ║
║  Auto-Fallback | 24/7 Ready | Chat Clear + Remember  ║
║  Task Logs | Secret Code | Pending/Completed Tasks  ║
╚══════════════════════════════════════════════════╝
"""

import os, json, logging, time, asyncio, urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta
from xml.etree import ElementTree as ET

# SSL fix for some environments
ssl._create_default_https_context = ssl._create_unverified_context

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    log.error("❌ Environment variables missing!")
    log.error("Please set: TELEGRAM_TOKEN and GEMINI_API_KEY")
    exit(1)

# 🔥 MULTI-MODEL FALLBACK
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

# ══════════════════════════════════════════════
# SECRET CODE
# ══════════════════════════════════════════════
SECRET_CODE = "Rk1996"

# ══════════════════════════════════════════════
# FILE PATHS
# ══════════════════════════════════════════════
DATA = os.path.join(os.getcwd(), "data")
os.makedirs(DATA, exist_ok=True)

F_MEMORY    = os.path.join(DATA, "memory.json")
F_TASKS     = os.path.join(DATA, "tasks.json")
F_TASK_LOGS = os.path.join(DATA, "task_logs.json")  # NEW: Task activity logs
F_FAILED    = os.path.join(DATA, "failed_requests.json")  # NEW: Failed user requests
F_DIARY     = os.path.join(DATA, "diary.json")
F_HABITS    = os.path.join(DATA, "habits.json")
F_NOTES     = os.path.join(DATA, "notes.json")
F_EXPENSES  = os.path.join(DATA, "expenses.json")
F_GOALS     = os.path.join(DATA, "goals.json")
F_CHAT      = os.path.join(DATA, "chat_history.json")
F_NEWS      = os.path.join(DATA, "news_cache.json")
F_REMINDERS = os.path.join(DATA, "reminders.json")
F_WATER     = os.path.join(DATA, "water.json")
F_BILLS     = os.path.join(DATA, "bills.json")
F_CALENDAR  = os.path.join(DATA, "calendar.json")

# ══════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════
def load(path, default=None):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"Load error {path}: {e}")
    return default if default is not None else {}

def save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Save error {path}: {e}")

def today_str():     return date.today().isoformat()
def now_str():       return datetime.now().strftime("%H:%M")
def yesterday_str(): return (date.today() - timedelta(days=1)).isoformat()

# ══════════════════════════════════════════════
# 🔥 FAILED REQUEST TRACKER
# ══════════════════════════════════════════════
class FailedRequests:
    def __init__(self):
        self.data = load(F_FAILED, {"queue": []})

    def save_data(self):
        save(F_FAILED, self.data)

    def add(self, user_msg: str, chat_id: int, reason: str):
        self.data["queue"].append({
            "msg": user_msg,
            "chat_id": chat_id,
            "reason": reason,
            "time": datetime.now().isoformat(),
            "retried": False
        })
        self.save_data()
        log.info(f"📝 Failed request saved: {user_msg[:50]}... (reason: {reason})")

    def get_unretried(self) -> list:
        return [r for r in self.data["queue"] if not r["retried"]]

    def mark_retried(self, index: int):
        if 0 <= index < len(self.data["queue"]):
            self.data["queue"][index]["retried"] = True
            self.save_data()

    def clear_all(self):
        self.data["queue"] = []
        self.save_data()

# ══════════════════════════════════════════════
# 🔥 GEMINI MULTI-MODEL CALLER (with failed request fallback)
# ══════════════════════════════════════════════
def call_gemini(system_prompt: str, messages: list, user_msg: str = None, chat_id: int = None, failed_queue=None, retries=2) -> str:
    contents = [
        {"role": "user",  "parts": [{"text": f"[SYSTEM]\n{system_prompt}\n[/SYSTEM]\n\nReady ho?"}]},
        {"role": "model", "parts": [{"text": "Haan ready hoon! Batao."}]},
    ]
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    payload = json.dumps({
        "contents": contents,
        "generationConfig": {"temperature": 0.75, "maxOutputTokens": 600}
    }).encode("utf-8")

    errors = []
    for model in GEMINI_MODELS:
        for attempt in range(retries):
            try:
                url = BASE_URL.format(model=model, key=GEMINI_API_KEY)
                req = urllib.request.Request(
                    url, data=payload,
                    headers={"Content-Type": "application/json"}, method="POST"
                )
                with urllib.request.urlopen(req, timeout=45) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    text = result["candidates"][0]["content"]["parts"][0]["text"]
                    log.info(f"✅ Model used: {model}")
                    return text

            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8")
                log.warning(f"Model {model} attempt {attempt+1}: HTTP {e.code}")
                if e.code == 429:
                    errors.append(f"{model}: rate limit")
                    wait = 3 if attempt == 0 else 6
                    time.sleep(wait)
                    continue
                elif e.code in (500, 503):
                    errors.append(f"{model}: server error")
                    time.sleep(2)
                    continue
                elif e.code == 404:
                    log.warning(f"Model {model}: 404 Not Found — skipping")
                    errors.append(f"{model}: not found")
                    break
                elif e.code == 400:
                    log.error(f"Model {model}: 400 Bad Request — {body[:200]}")
                    return f"❌ Request error: {body[:150]}"
                else:
                    return f"❌ API Error {e.code}: {body[:150]}"
            except Exception as e:
                log.warning(f"Model {model}: {e}")
                errors.append(str(e))
                break

    # 🔥 SAVE FAILED REQUEST for later retry
    if user_msg and chat_id is not None and failed_queue:
        failed_queue.add(user_msg, chat_id, ", ".join(errors[:3]))
        return ("⚠️ Abhi response nahi mila. Main aapka request save kar liya hai! 📝\n"
                "Net aate hi automatically process kar dunga! 🔄\n\n"
                f"_({', '.join(errors[:3])})_")

    return ("⚠️ Abhi Gemini API se response nahi mila.\n"
            "Thodi der baad dobara try karo! 🙏\n\n"
            f"_({', '.join(errors[:3])})_")

# ══════════════════════════════════════════════
# FREE NEWS via RSS
# ══════════════════════════════════════════════
NEWS_FEEDS = {
    "India":      "https://feeds.bbci.co.uk/hindi/rss.xml",
    "Technology": "https://feeds.feedburner.com/ndtvnews-tech-news",
    "Business":   "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "World":      "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Sports":     "https://feeds.bbci.co.uk/sport/rss.xml",
}

def fetch_news(category="India", max_items=5) -> list:
    cache = load(F_NEWS, {"cache": {}, "updated": {}})
    now_ts = time.time()

    if (category in cache["cache"] and
        now_ts - cache["updated"].get(category, 0) < 1800):
        return cache["cache"][category][:max_items]

    url = NEWS_FEEDS.get(category, NEWS_FEEDS["India"])
    items = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            tree = ET.parse(resp)
            root = tree.getroot()
            channel = root.find("channel")
            if channel is None: channel = root
            for item in channel.findall("item")[:max_items]:
                title = item.findtext("title", "").strip()
                desc  = item.findtext("description", "").strip()
                link  = item.findtext("link", "").strip()
                pub   = item.findtext("pubDate", "").strip()
                if title:
                    items.append({"title": title, "desc": desc[:120], "link": link, "pub": pub})
    except Exception as e:
        log.warning(f"News fetch error: {e}")
        return [{"title": "News abhi available nahi", "desc": str(e), "link": "", "pub": ""}]

    cache["cache"][category] = items
    cache["updated"][category] = now_ts
    save(F_NEWS, cache)
    return items

# ══════════════════════════════════════════════
# CHAT HISTORY
# ══════════════════════════════════════════════
class ChatHistory:
    def __init__(self):
        self.data = load(F_CHAT, {"history": [], "cleared_at": None, "msg_ids": []})
        if "msg_ids" not in self.data:
            self.data["msg_ids"] = []

    def add(self, role: str, content: str):
        self.data["history"].append({
            "role": role, "content": content,
            "time": datetime.now().isoformat()
        })
        self.data["history"] = self.data["history"][-80:]
        save(F_CHAT, self.data)

    def track_msg(self, chat_id: int, msg_id: int):
        self.data["msg_ids"].append({"chat_id": chat_id, "msg_id": msg_id})
        self.data["msg_ids"] = self.data["msg_ids"][-500:]
        save(F_CHAT, self.data)

    def get_tracked_ids(self):
        return self.data.get("msg_ids", [])

    def get_recent(self, n=20) -> list:
        return [{"role": m["role"], "content": m["content"]}
                for m in self.data["history"][-n:]]

    def clear(self):
        count = len(self.data["history"])
        self.data["history"] = []
        self.data["cleared_at"] = datetime.now().isoformat()
        save(F_CHAT, self.data)
        return count

    def clear_msg_ids(self):
        self.data["msg_ids"] = []
        save(F_CHAT, self.data)

    def count(self):
        return len(self.data["history"])

# ══════════════════════════════════════════════
# MEMORY
# ══════════════════════════════════════════════
class Memory:
    def __init__(self):
        self.data = load(F_MEMORY, {
            "facts": [], "prefs": {}, "dates": {},
            "important_notes": []
        })

    def save_data(self): save(F_MEMORY, self.data)

    def add_fact(self, fact: str):
        existing = [f["f"] for f in self.data["facts"][-50:]]
        if fact[:50] in [e[:50] for e in existing]:
            return
        self.data["facts"].append({"f": fact, "d": today_str()})
        self.data["facts"] = self.data["facts"][-400:]
        self.save_data()

    def add_important(self, note: str):
        self.data["important_notes"].append({"note": note, "d": today_str()})
        self.save_data()

    def set_pref(self, k, v):
        self.data["prefs"][k] = v; self.save_data()

    def add_date(self, name, d):
        self.data["dates"][name] = d; self.save_data()

    def clear_facts(self):
        count = len(self.data["facts"])
        self.data["facts"] = []
        self.save_data()
        return count

    def get_all_facts(self):
        return self.data["facts"]

    def context(self) -> str:
        facts = "\n".join(f"• {x['f']}" for x in self.data["facts"][-30:]) or "Kuch nahi"
        prefs = "\n".join(f"• {k}: {v}" for k, v in self.data["prefs"].items()) or "Kuch nahi"
        dates = "\n".join(f"• {k}: {v}" for k, v in self.data["dates"].items()) or "Kuch nahi"
        imp   = "\n".join(f"⭐ {n['note']}" for n in self.data["important_notes"][-10:]) or "Kuch nahi"
        return (f"FACTS (jo tune bataya):\n{facts}\n\n"
                f"PREFERENCES:\n{prefs}\n\n"
                f"IMPORTANT DATES:\n{dates}\n\n"
                f"IMPORTANT NOTES:\n{imp}")

# ══════════════════════════════════════════════
# 🔥 TASK LOGS SYSTEM — Track every action
# ══════════════════════════════════════════════
class TaskLogs:
    def __init__(self):
        self.data = load(F_TASK_LOGS, {"logs": [], "actions": []})

    def save_data(self):
        save(F_TASK_LOGS, self.data)

    def add_log(self, action_type: str, description: str, task_id: int = None, details: dict = None):
        entry = {
            "type": action_type,        # "created", "completed", "deleted", "updated"
            "description": description,
            "task_id": task_id,
            "details": details or {},
            "timestamp": datetime.now().isoformat(),
            "date": today_str()
        }
        self.data["logs"].append(entry)
        self.data["logs"] = self.data["logs"][-1000:]  # Keep last 1000
        self.save_data()
        log.info(f"📋 Task Log: {action_type} — {description[:50]}")

    def get_logs_by_date(self, date_str: str = None) -> list:
        if date_str is None:
            date_str = today_str()
        return [l for l in self.data["logs"] if l.get("date") == date_str]

    def get_all_logs(self) -> list:
        return self.data["logs"]

    def get_created_tasks(self) -> list:
        return [l for l in self.data["logs"] if l["type"] == "created"]

    def get_completed_tasks(self) -> list:
        return [l for l in self.data["logs"] if l["type"] == "completed"]

    def get_pending_from_logs(self) -> list:
        """Calculate pending tasks from logs (created - completed)"""
        created_ids = set()
        completed_ids = set()
        for l in self.data["logs"]:
            if l.get("task_id"):
                if l["type"] == "created":
                    created_ids.add(l["task_id"])
                elif l["type"] == "completed":
                    completed_ids.add(l["task_id"])
        pending_ids = created_ids - completed_ids
        pending_logs = [l for l in self.data["logs"] if l.get("task_id") in pending_ids and l["type"] == "created"]
        return pending_logs

    def get_all_task_summary(self) -> dict:
        """Full summary: created, completed, pending counts"""
        created = self.get_created_tasks()
        completed = self.get_completed_tasks()
        pending = self.get_pending_from_logs()
        return {
            "created": created,
            "completed": completed,
            "pending": pending,
            "total_created": len(created),
            "total_completed": len(completed),
            "total_pending": len(pending)
        }

# ══════════════════════════════════════════════
# TASKS
# ══════════════════════════════════════════════
class Tasks:
    def __init__(self):
        self.data = load(F_TASKS, {"list": [], "counter": 0})

    def save_data(self): save(F_TASKS, self.data)

    def add(self, title, priority="medium", due=None):
        self.data["counter"] += 1
        t = {"id": self.data["counter"], "title": title,
             "priority": priority, "due": due or today_str(),
             "done": False, "done_at": None, "created": datetime.now().isoformat()}
        self.data["list"].append(t); self.save_data()
        # Log to task_logs
        task_logs.add_log("created", title, t["id"], {"priority": priority})
        return t

    def complete(self, tid):
        for t in self.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True; t["done_at"] = datetime.now().isoformat()
                self.save_data()
                # Log to task_logs
                task_logs.add_log("completed", t["title"], tid)
                return t
        return None

    def delete(self, tid):
        before = len(self.data["list"])
        for t in self.data["list"]:
            if t["id"] == tid:
                task_logs.add_log("deleted", t["title"], tid)
        self.data["list"] = [t for t in self.data["list"] if t["id"] != tid]
        self.save_data()
        return before != len(self.data["list"])

    def pending(self):    return [t for t in self.data["list"] if not t["done"]]
    def done_on(self, d): return [t for t in self.data["list"] if t["done"] and (t.get("done_at","") or "")[:10] == d]
    def today_pending(self):
        td = today_str()
        return [t for t in self.data["list"] if not t["done"] and t.get("due","") <= td]
    def all_tasks(self):  return self.data["list"]
    def completed_tasks(self): return [t for t in self.data["list"] if t["done"]]
    def clear_done(self):
        before = len(self.data["list"])
        self.data["list"] = [t for t in self.data["list"] if not t["done"]]
        self.save_data()
        return before - len(self.data["list"])

# ══════════════════════════════════════════════
# DIARY
# ══════════════════════════════════════════════
class Diary:
    def __init__(self):
        self.data = load(F_DIARY, {"entries": {}})

    def save_data(self): save(F_DIARY, self.data)

    def add(self, content, mood="😊"):
        td = today_str()
        if td not in self.data["entries"]:
            self.data["entries"][td] = []
        self.data["entries"][td].append({"text": content, "mood": mood, "time": now_str()})
        self.save_data()

    def get(self, d):     return self.data["entries"].get(d, [])
    def all_dates(self):  return sorted(self.data["entries"].keys(), reverse=True)

# ══════════════════════════════════════════════
# HABITS
# ══════════════════════════════════════════════
class Habits:
    def __init__(self):
        self.data = load(F_HABITS, {"list": [], "logs": {}, "counter": 0})

    def save_data(self): save(F_HABITS, self.data)

    def add(self, name, emoji="✅"):
        self.data["counter"] += 1
        h = {"id": self.data["counter"], "name": name, "emoji": emoji,
             "streak": 0, "best_streak": 0, "created": today_str()}
        self.data["list"].append(h); self.save_data(); return h

    def log(self, hid):
        td, yd = today_str(), yesterday_str()
        if td not in self.data["logs"]:
            self.data["logs"][td] = []
        if hid in self.data["logs"][td]:
            return False, 0
        self.data["logs"][td].append(hid)
        for h in self.data["list"]:
            if h["id"] == hid:
                yd_logs = self.data["logs"].get(yd, [])
                h["streak"] = h["streak"] + 1 if hid in yd_logs else 1
                h["best_streak"] = max(h.get("best_streak", 0), h["streak"])
        self.save_data()
        streak = next((x["streak"] for x in self.data["list"] if x["id"] == hid), 1)
        return True, streak

    def today_status(self):
        done_ids = self.data["logs"].get(today_str(), [])
        return ([h for h in self.data["list"] if h["id"] in done_ids],
                [h for h in self.data["list"] if h["id"] not in done_ids])

    def delete(self, hid):
        self.data["list"] = [h for h in self.data["list"] if h["id"] != hid]
        self.save_data()

    def all(self): return self.data["list"]

# ══════════════════════════════════════════════
# NOTES
# ══════════════════════════════════════════════
class Notes:
    def __init__(self):
        self.data = load(F_NOTES, {"list": [], "counter": 0})

    def save_data(self): save(F_NOTES, self.data)

    def add(self, content, tag="general"):
        self.data["counter"] += 1
        n = {"id": self.data["counter"], "text": content,
             "tag": tag, "created": datetime.now().isoformat()}
        self.data["list"].append(n); self.save_data(); return n

    def search(self, q):
        return [n for n in self.data["list"] if q.lower() in n["text"].lower()]

    def delete(self, nid):
        self.data["list"] = [n for n in self.data["list"] if n["id"] != nid]
        self.save_data()

    def recent(self, n=15): return self.data["list"][-n:]

# ══════════════════════════════════════════════
# EXPENSES
# ══════════════════════════════════════════════
class Expenses:
    def __init__(self):
        self.data = load(F_EXPENSES, {"list": [], "counter": 0, "budget": {}})

    def save_data(self): save(F_EXPENSES, self.data)

    def add(self, amount, desc, category="general"):
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "amount": amount,
             "desc": desc, "category": category,
             "date": today_str(), "time": now_str()}
        self.data["list"].append(e); self.save_data(); return e

    def set_budget(self, amount):
        self.data["budget"]["monthly"] = amount; self.save_data()

    def today_total(self): return sum(e["amount"] for e in self.data["list"] if e["date"] == today_str())
    def month_total(self):
        m = today_str()[:7]
        return sum(e["amount"] for e in self.data["list"] if e["date"][:7] == m)
    def today_list(self): return [e for e in self.data["list"] if e["date"] == today_str()]
    def budget_left(self):
        b = self.data["budget"].get("monthly", 0)
        return b - self.month_total() if b else None

# ══════════════════════════════════════════════
# GOALS
# ══════════════════════════════════════════════
class Goals:
    def __init__(self):
        self.data = load(F_GOALS, {"list": [], "counter": 0})

    def save_data(self): save(F_GOALS, self.data)

    def add(self, title, deadline=None, why=""):
        self.data["counter"] += 1
        g = {"id": self.data["counter"], "title": title,
             "deadline": deadline or "", "why": why,
             "progress": 0, "done": False, "created": today_str(),
             "milestones": []}
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

# ══════════════════════════════════════════════
# REMINDERS / ALARMS
# ══════════════════════════════════════════════
class Reminders:
    def __init__(self):
        self.data = load(F_REMINDERS, {"list": [], "counter": 0})

    def save_data(self): save(F_REMINDERS, self.data)

    def add(self, chat_id: int, text: str, remind_at: str, repeat: str = "once") -> dict:
        self.data["counter"] += 1
        r = {
            "id":        self.data["counter"],
            "chat_id":   chat_id,
            "text":      text,
            "time":      remind_at,
            "repeat":    repeat,
            "date":      today_str(),
            "active":    True,
            "fired_today": False,
            "created":   datetime.now().isoformat()
        }
        self.data["list"].append(r)
        self.save_data()
        return r

    def all_active(self):
        return [r for r in self.data["list"] if r["active"]]

    def delete(self, rid: int) -> bool:
        before = len(self.data["list"])
        self.data["list"] = [r for r in self.data["list"] if r["id"] != rid]
        self.save_data()
        return before != len(self.data["list"])

    def mark_fired(self, rid: int):
        for r in self.data["list"]:
            if r["id"] == rid:
                r["fired_today"] = True
                if r["repeat"] == "once":
                    r["active"] = False
                self.save_data()
                break

    def reset_daily(self):
        changed = False
        for r in self.data["list"]:
            if r["fired_today"]:
                r["fired_today"] = False
                changed = True
        if changed:
            self.save_data()

    def due_now(self) -> list:
        now_dt = datetime.now()
        now_str_hm = now_dt.strftime("%H:%M")
        due = []
        for r in self.data["list"]:
            if not r["active"] or r["fired_today"]:
                continue
            r_time = r["time"]
            try:
                r_dt = datetime.strptime(today_str() + " " + r_time, "%Y-%m-%d %H:%M")
                diff = (now_dt - r_dt).total_seconds()
                if 0 <= diff < 120:
                    due.append(r)
            except Exception:
                if r_time == now_str_hm:
                    due.append(r)
        return due

    def get_all(self):
        return self.data["list"]

# ══════════════════════════════════════════════
# WATER TRACKER
# ══════════════════════════════════════════════
class WaterTracker:
    def __init__(self):
        self.data = load(F_WATER, {"logs": {}, "goal_ml": 2000})

    def save_data(self): save(F_WATER, self.data)

    def add(self, ml: int = 250):
        td = today_str()
        if td not in self.data["logs"]:
            self.data["logs"][td] = []
        self.data["logs"][td].append({"ml": ml, "time": now_str()})
        self.save_data()

    def today_total(self) -> int:
        return sum(e["ml"] for e in self.data["logs"].get(today_str(), []))

    def today_count(self) -> int:
        return len(self.data["logs"].get(today_str(), []))

    def goal(self) -> int:
        return self.data.get("goal_ml", 2000)

    def set_goal(self, ml: int):
        self.data["goal_ml"] = ml
        self.save_data()

    def today_entries(self):
        return self.data["logs"].get(today_str(), [])

    def week_summary(self) -> dict:
        result = {}
        for i in range(7):
            d = (date.today() - timedelta(days=i)).isoformat()
            result[d] = sum(e["ml"] for e in self.data["logs"].get(d, []))
        return result

# ══════════════════════════════════════════════
# BILLS / EMI TRACKER
# ══════════════════════════════════════════════
class BillTracker:
    def __init__(self):
        self.data = load(F_BILLS, {"list": [], "counter": 0})

    def save_data(self): save(F_BILLS, self.data)

    def add(self, name: str, amount: float, due_day: int, bill_type: str = "bill", notes: str = "") -> dict:
        self.data["counter"] += 1
        b = {
            "id":       self.data["counter"],
            "name":     name,
            "amount":   amount,
            "due_day":  due_day,
            "type":     bill_type,
            "notes":    notes,
            "active":   True,
            "paid_months": [],
            "created":  today_str()
        }
        self.data["list"].append(b)
        self.save_data()
        return b

    def all_active(self):
        return [b for b in self.data["list"] if b["active"]]

    def mark_paid(self, bid: int) -> bool:
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid:
                if ym not in b["paid_months"]:
                    b["paid_months"].append(ym)
                self.save_data()
                return True
        return False

    def is_paid_this_month(self, bid: int) -> bool:
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid:
                return ym in b.get("paid_months", [])
        return False

    def delete(self, bid: int) -> bool:
        before = len(self.data["list"])
        self.data["list"] = [b for b in self.data["list"] if b["id"] != bid]
        self.save_data()
        return before != len(self.data["list"])

    def due_soon(self, days_ahead: int = 3) -> list:
        today_d = date.today()
        result = []
        for b in self.data["list"]:
            if not b["active"]: continue
            if self.is_paid_this_month(b["id"]): continue
            due_day = b["due_day"]
            try:
                due_date = date(today_d.year, today_d.month, due_day)
            except ValueError:
                due_date = date(today_d.year, today_d.month, 28)
            if today_d <= due_date <= today_d + timedelta(days=days_ahead):
                result.append({**b, "due_date": due_date.isoformat()})
        return result

    def month_total(self) -> float:
        return sum(b["amount"] for b in self.data["list"] if b["active"])

# ══════════════════════════════════════════════
# GOOGLE CALENDAR (LOCAL)
# ══════════════════════════════════════════════
class CalendarManager:
    def __init__(self):
        self.data = load(F_CALENDAR, {"events": [], "counter": 0})

    def save_data(self): save(F_CALENDAR, self.data)

    def add(self, title: str, event_date: str, event_time: str = "", notes: str = "") -> dict:
        self.data["counter"] += 1
        e = {
            "id":     self.data["counter"],
            "title":  title,
            "date":   event_date,
            "time":   event_time,
            "notes":  notes,
            "created": today_str()
        }
        self.data["events"].append(e)
        self.save_data()
        return e

    def delete(self, eid: int) -> bool:
        before = len(self.data["events"])
        self.data["events"] = [e for e in self.data["events"] if e["id"] != eid]
        self.save_data()
        return before != len(self.data["events"])

    def upcoming(self, days: int = 7) -> list:
        today_d = date.today()
        cutoff  = today_d + timedelta(days=days)
        result  = []
        for e in self.data["events"]:
            try:
                ed = date.fromisoformat(e["date"])
                if today_d <= ed <= cutoff:
                    result.append(e)
            except Exception:
                pass
        return sorted(result, key=lambda x: x["date"])

    def today_events(self) -> list:
        return [e for e in self.data["events"] if e["date"] == today_str()]

    def all_events(self) -> list:
        today_d = today_str()
        return sorted(
            [e for e in self.data["events"] if e["date"] >= today_d],
            key=lambda x: (x["date"], x.get("time", ""))
        )

# ══════════════════════════════════════════════
# INIT ALL
# ══════════════════════════════════════════════
chat_hist   = ChatHistory()
mem         = Memory()
tasks       = Tasks()
task_logs   = TaskLogs()
failed_reqs = FailedRequests()
diary       = Diary()
habits      = Habits()
notes       = Notes()
expenses    = Expenses()
goals       = Goals()
reminders   = Reminders()
water       = WaterTracker()
bills       = BillTracker()
calendar    = CalendarManager()

# ══════════════════════════════════════════════
# SYSTEM PROMPT BUILDER
# ══════════════════════════════════════════════
def build_system_prompt() -> str:
    now_label = datetime.now().strftime("%A, %d %B %Y — %I:%M %p")
    tp    = tasks.today_pending()
    yd    = tasks.done_on(yesterday_str())
    hd, hp = habits.today_status()
    ag    = goals.active()
    td_d  = diary.get(today_str())
    exp_t = expenses.today_total()
    exp_m = expenses.month_total()
    bl    = expenses.budget_left()
    msgs  = chat_hist.count()
    water_today = water.today_total()
    water_goal  = water.goal()
    due_bills   = bills.due_soon(3)
    cal_today   = calendar.today_events()

    tasks_s = "\n".join(f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}" for t in tp[:6]) or "  Koi nahi"
    yd_s    = "\n".join(f"  ✓ {t['title']}" for t in yd[:5]) or "  Koi nahi"
    h_done  = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    h_pend  = ", ".join(f"{h['name']}" for h in hp) or "Sab ho gaye! 🎉"
    goals_s = "\n".join(f"  🎯 {g['title']} ({g['progress']}%)" for g in ag[:4]) or "  Koi nahi"
    diary_s = "\n".join(f"  {e['time']} {e['text']}" for e in td_d[-3:]) or "  Kuch nahi"
    budget_s = f"Budget baaki: ₹{bl:.0f}" if bl is not None else ""
    water_pct = int(water_today / water_goal * 100) if water_goal else 0
    bills_s   = "\n".join(f"  ⚠️ {b['name']} ₹{b['amount']:.0f} — {b['due_date']}" for b in due_bills) or "  Koi nahi"
    cal_s     = "\n".join(f"  📅 {e['time'] or ''} {e['title']}" for e in cal_today) or "  Koi nahi"

    return f"""Tu mera Personal AI Assistant hai — naam 'Dost'. Greet karte waqt "Assalamualaikum" bol.
Hamesha Hindi/Hinglish mein baat kar. Bilkul close dost jaisa — warm, real, helpful.

⏰ ABHI: {now_label}
💬 Chat messages: {msgs}

📋 AAJ KE TASKS:
{tasks_s}

✅ KAL KYA KIYA:
{yd_s}

💪 HABITS:
  Done: {h_done}
  Baaki: {h_pend}

📖 DIARY (aaj):
{diary_s}

💰 KHARCHA: Aaj ₹{exp_t} | Mahina ₹{exp_m} {budget_s}

🎯 GOALS:
{goals_s}

💧 PAANI: {water_today}ml / {water_goal}ml ({water_pct}%)

📅 AAJ KE CALENDAR EVENTS:
{cal_s}

💳 UPCOMING BILLS/EMI (3 din mein):
{bills_s}

━━ YAADDASHT (chat clear bhi ho jai toh yeh safe hai) ━━
{mem.context()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RULES:
- Dost ki tarah baat kar — "As an AI" kabhi mat bol
- Hindi/Hinglish mein jawab de
- Jo yaad hai naturally use kar
- Short aur helpful reh
- Agar user "yaad rakh" bole → confirm karo "Yaad kar liya ✅"
- Chat clear hone se memory delete nahi hoti
- Kabhi payment/upgrade suggest mat kar
"""

# ══════════════════════════════════════════════
# SMART AUTO-SAVE
# ══════════════════════════════════════════════
def auto_extract_facts(text: str):
    lower = text.lower()
    triggers = [
        "yaad rakh", "remember", "mera naam", "meri umar", "main rehta",
        "mujhe pasand", "meri job", "mera kaam", "mere bhai", "meri behen",
        "meri wife", "mere husband", "mera", "meri", "main hoon",
        "birthday", "anniversary", "deadline", "important date"
    ]
    if any(kw in lower for kw in triggers):
        mem.add_fact(text[:250])
        return True
    return False

# ══════════════════════════════════════════════
# AI CHAT
# ══════════════════════════════════════════════

# ══════════════════════════════════════════════
# SMART ACTION SYSTEM
# ══════════════════════════════════════════════

ACTION_SYSTEM_PROMPT = """You are a JSON routing engine for a Telegram bot. Your ONLY job is to parse the user's message and return a JSON object. You cannot set alarms or reminders yourself — the bot's code will do that based on your JSON output.

Current time: {now}
Today's date: {today}

OUTPUT RULES — CRITICAL:
- Return ONLY raw JSON. No explanation, no markdown, no backticks, no text before or after.
- First character of your response must be {{ and last must be }}
- If unsure, use action "CHAT"

JSON format:
{{"action": "ACTION_NAME", "params": {{...}}, "reply": "Hinglish mein confirm message"}}

ACTIONS:

REMIND — user wants a reminder/alarm at a specific time
  params: {{"time": "HH:MM", "text": "reminder text", "repeat": "once"}}
  triggers: alarm, reminder, yaad dilana, X minute baad, X baje, X ghante baad, notify karo

ADD_TASK — user wants to add a task/todo
  params: {{"title": "task name", "priority": "high/medium/low"}}
  triggers: kaam karna hai, task add, yaad rakh karna hai, to-do, schedule

ADD_EXPENSE — user spent money
  params: {{"amount": 150, "desc": "description", "category": "food/travel/shopping/other"}}
  triggers: rupaye lage, kharcha, spent, X rs diye

ADD_DIARY — user wants to write in diary
  params: {{"text": "diary content", "mood": "😊"}}
  triggers: diary mein likho, aaj yeh hua, feeling

ADD_MEMORY — user wants to save something permanently
  params: {{"fact": "the fact to remember"}}
  triggers: yaad rakh, remember, important, hamesha yaad rakhna

ADD_HABIT — user wants to track a new habit
  params: {{"name": "habit name", "emoji": "💪"}}
  triggers: habit banana hai, roz karna hai, daily track

COMPLETE_TASK — user finished a task
  params: {{"title_hint": "task name or id"}}
  triggers: ho gaya, kar liya, complete, done, khatam

SHOW_TASKS — user wants to see pending tasks
  params: {{}}
  triggers: kya baaki hai, tasks dikhao, pending kaam, list karo

SHOW_ALL_TASKS — user wants to see ALL tasks (completed + pending)
  params: {{}}
  triggers: saare task, all tasks, sab task, total task, kitne task, poora task list

SHOW_COMPLETED_TASKS — user wants to see completed tasks
  params: {{}}
  triggers: complete task, ho gaya task, done task, khatam task, jo ho gaya

SHOW_REMINDERS — user wants to see active reminders
  params: {{}}
  triggers: reminders dikhao, alarms list, kya kya set hai

CHAT — normal conversation, no action needed
  params: {{}}
  triggers: everything else

Example inputs and outputs:
Input: "2 minute baad paani pine ka alarm laga do"
Output: {{"action":"REMIND","params":{{"time":"{two_min}","text":"Paani peena hai","repeat":"once"}},"reply":"✅ 2 minute baad yaad dilaunga — paani peena hai!"}}

Input: "kal doctor se milna hai note kar lo"
Output: {{"action":"ADD_TASK","params":{{"title":"Doctor se milna","priority":"high"}},"reply":"✅ Task note kar liya — Doctor se milna!"}}

Input: "aaj 200 rs autorickshaw mein kharch hue"
Output: {{"action":"ADD_EXPENSE","params":{{"amount":200,"desc":"Autorickshaw","category":"travel"}},"reply":"✅ ₹200 autorickshaw kharcha note kar liya!"}}

Input: "saare task dikhao"
Output: {{"action":"SHOW_ALL_TASKS","params":{{}},"reply":""}}

Input: "jo task ho gaye hain wo batao"
Output: {{"action":"SHOW_COMPLETED_TASKS","params":{{}},"reply":""}}

Input: "kya haal hai"
Output: {{"action":"CHAT","params":{{}},"reply":""}}
"""

import re as _re

def _regex_fallback(user_msg: str) -> dict:
    """Agar Gemini JSON fail kare toh regex se reminder/task detect karo"""
    lower = user_msg.lower()
    now   = datetime.now()

    remind_words = ["alarm", "reminder", "yaad dila", "remind", "notify",
                    "minute baad", "min baad", "ghante baad", "baje", "baja"]
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
            m = _re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)?', lower)
            if m:
                h, mn = int(m.group(1)), int(m.group(2))
                if m.group(3) == 'pm' and h != 12: h += 12
                elif m.group(3) == 'am' and h == 12: h = 0
                time_str = f"{h:02d}:{mn:02d}"

        if not time_str:
            m = _re.search(r'(\d{1,2})\s*(?:baje|baj)', lower)
            if m:
                h = int(m.group(1))
                if 'raat' in lower or 'sham' in lower: h = h + 12 if h < 12 else h
                elif 'subah' in lower: h = h if h < 12 else h - 12
                else: h = h + 12 if 1 <= h <= 6 else h
                time_str = f"{h:02d}:00"

        if time_str:
            text = _re.sub(r'\d+\s*(?:minute|min|mins|ghante|ghanta|hour|hr)', '', user_msg, flags=_re.I)
            text = _re.sub(r'\d{1,2}:\d{2}\s*(?:am|pm)?', '', text, flags=_re.I)
            text = _re.sub(r'\d{1,2}\s*baje', '', text, flags=_re.I)
            text = _re.sub(r'(?:alarm|reminder|yaad dila|remind|laga do|laga dena|set karo|baad|notify)\s*', '', text, flags=_re.I).strip()
            text = text or "⏰ Reminder!"
            log.info(f"🔄 Regex fallback REMIND: {time_str} — {text}")
            return {"action": "REMIND", "params": {"time": time_str, "text": text, "repeat": "once"}, "reply": ""}

    task_words = ["karna hai", "task add", "kaam add", "note kar", "to-do", "todo", "schedule"]
    if any(w in lower for w in task_words):
        title = user_msg[:100]
        log.info(f"🔄 Regex fallback ADD_TASK: {title}")
        return {"action": "ADD_TASK", "params": {"title": title, "priority": "medium"}, "reply": ""}

    expense_words = ["rs ", "rupaye", "kharcha", "kharch", "spend", "lage", "diye"]
    if any(w in lower for w in expense_words):
        m = _re.search(r'(\d+)', lower)
        amount = float(m.group(1)) if m else 0
        if amount > 0:
            log.info(f"🔄 Regex fallback ADD_EXPENSE: ₹{amount}")
            return {"action": "ADD_EXPENSE", "params": {"amount": amount, "desc": user_msg[:80], "category": "general"}, "reply": ""}

    log.info("🔄 Regex fallback → CHAT")
    return {"action": "CHAT", "params": {}, "reply": ""}


def call_gemini_action(user_msg: str, now_label: str, today_label: str) -> dict:
    two_min = (datetime.now() + timedelta(minutes=2)).strftime("%H:%M")
    prompt  = ACTION_SYSTEM_PROMPT.format(now=now_label, today=today_label, two_min=two_min)

    full_msg = f"{prompt}\n\nUser message: {user_msg}"

    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": full_msg}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 300}
    }).encode("utf-8")

    raw = ""
    for model in GEMINI_MODELS:
        try:
            url = BASE_URL.format(model=model, key=GEMINI_API_KEY)
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()

                raw = raw.replace("```json", "").replace("```", "").strip()

                json_match = _re.search(r'\{.*\}', raw, _re.DOTALL)
                if json_match:
                    raw = json_match.group(0)

                parsed = json.loads(raw)
                log.info(f"✅ Gemini action: {parsed.get('action')} via {model}")
                return parsed

        except json.JSONDecodeError as e:
            log.warning(f"Gemini JSON fail ({model}): {e} | raw[:80]: {raw[:80]}")
            fallback = _regex_fallback(user_msg)
            if fallback["action"] != "CHAT":
                return fallback
            continue
        except Exception as e:
            log.warning(f"Gemini action call fail ({model}): {e}")
            continue

    log.warning("⚠️ All Gemini models failed for action — using regex fallback")
    return _regex_fallback(user_msg)


async def execute_action(action_data: dict, chat_id: int, user_msg: str) -> str:
    action  = action_data.get("action", "CHAT")
    params  = action_data.get("params", {})
    ai_reply = action_data.get("reply", "")

    now_label   = datetime.now().strftime("%A, %d %B %Y — %I:%M %p")
    today_label = date.today().isoformat()

    if action == "REMIND":
        time_str = params.get("time", "")
        text     = params.get("text", "⏰ Reminder!")
        repeat   = params.get("repeat", "once")

        if not time_str:
            return "⏰ Kaunse waqt pe reminder lagaoon? Bolo — jaise '3 baje' ya '30 minute baad'."

        # Validate time format
        if not _re.match(r'^\d{2}:\d{2}$', time_str):
            return "⏰ Time format sahi nahi hai. HH:MM format use karo — jaise '15:30'"

        try:
            hours, mins = map(int, time_str.split(":"))
            if not (0 <= hours <= 23 and 0 <= mins <= 59):
                return "⏰ Invalid time! Hours 0-23, minutes 0-59 hona chahiye."
        except:
            return "⏰ Time format sahi nahi hai. HH:MM format use karo."

        r = reminders.add(chat_id, text, time_str, repeat)
        repeat_txt = {"once": "Ek baar", "daily": "Roz 🔁", "weekly": "Har hafte 📅"}.get(repeat, repeat)
        reply = ai_reply or f"✅ Set kar diya! *{time_str}* pe yaad dilaunga — _{text}_"
        reply += f"\n\n🆔 `#{r['id']}` | {repeat_txt} | `/delremind {r['id']}` se hatao"
        log.info(f"🔔 Reminder set: ID #{r['id']} — {time_str} — {text}")
        return reply

    elif action == "ADD_TASK":
        title    = params.get("title", user_msg[:80])
        priority = params.get("priority", "medium")
        t = tasks.add(title, priority)
        icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        reply = ai_reply or f"✅ Task add kar diya!\n{icons.get(priority,'🟡')} *{title}*"
        reply += f"\n🆔 `#{t['id']}` | Priority: {priority}"
        log.info(f"📋 Task added: ID #{t['id']} — {title}")
        return reply

    elif action == "ADD_EXPENSE":
        amount   = float(params.get("amount", 0))
        desc     = params.get("desc", "Kharcha")
        category = params.get("category", "general")
        if amount <= 0:
            return "💰 Kitne rupaye kharch hue? Amount bhi batao."
        e = expenses.add(amount, desc, category)
        today_total = expenses.today_total()
        reply = ai_reply or f"✅ Kharcha note kar liya!\n💸 *₹{amount:.0f}* — {desc}"
        reply += f"\n📊 Aaj ka total: *₹{today_total:.0f}*"
        log.info(f"💰 Expense added: ₹{amount} — {desc}")
        return reply

    elif action == "ADD_DIARY":
        text = params.get("text", user_msg)
        mood = params.get("mood", "😊")
        diary.add(text, mood)
        reply = ai_reply or f"📖 Diary mein likh liya {mood}\n_{text[:100]}_"
        log.info(f"📖 Diary entry added")
        return reply

    elif action == "ADD_MEMORY":
        fact = params.get("fact", user_msg[:250])
        mem.add_fact(fact)
        reply = ai_reply or f"🧠 Yaad kar liya ✅\n_{fact[:100]}_\n\nYeh memory hamesha safe rahegi!"
        log.info(f"🧠 Memory saved: {fact[:50]}")
        return reply

    elif action == "ADD_HABIT":
        name  = params.get("name", user_msg[:50])
        emoji = params.get("emoji", "✅")
        h = habits.add(name, emoji)
        reply = ai_reply or f"💪 Habit add kar di!\n{emoji} *{name}*\n\nRoz track hoga — all the best!"
        log.info(f"💪 Habit added: {name}")
        return reply

    elif action == "COMPLETE_TASK":
        hint = params.get("title_hint", "").lower()
        pending = tasks.pending()
        matched = None
        if hint.isdigit():
            matched = next((t for t in pending if t["id"] == int(hint)), None)
        if not matched and hint:
            matched = next((t for t in pending if hint in t["title"].lower()), None)
        if not matched and pending:
            # Try complted logs too
            all_created = task_logs.get_created_tasks()
            for log_entry in reversed(all_created):
                if hint and hint in log_entry.get("description", "").lower():
                    for t in pending:
                        if t["id"] == log_entry.get("task_id"):
                            matched = t
                            break
                    if matched:
                        break
        if not matched and pending:
            matched = pending[-1]

        if matched:
            tasks.complete(matched["id"])
            reply = ai_reply or f"✅ *{matched['title']}* — ho gaya! Zabardast! 🎉"
        else:
            reply = "❓ Kaunsa task complete hua? Thoda hint do ya task ID batao."
        return reply

    elif action == "SHOW_TASKS":
        pending = tasks.today_pending()
        if not pending:
            return "🎉 Aaj koi pending task nahi! Sab clear hai.\n\n_Naya task add karna ho toh bol do._"
        txt = f"📋 *AAJ KE PENDING TASKS ({len(pending)})*\n\n"
        for t in pending[:10]:
            icon = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
            txt += f"{icon} *#{t['id']}* {t['title']}\n"
        txt += "\n_💡 `/done [ID]` se complete karo_"
        return txt

    # 🔥 NEW: SHOW ALL TASKS (pending + completed)
    elif action == "SHOW_ALL_TASKS":
        all_t = tasks.all_tasks()
        if not all_t:
            return "📋 Koi task abhi tak add nahi kiya!\n\n`/task Kaam naam` se shuru karo."

        pending_t = tasks.pending()
        completed_t = tasks.completed_tasks()

        txt = f"📋 *SAARE TASKS ({len(all_t)})*\n\n"

        if pending_t:
            txt += f"⏳ *PENDING ({len(pending_t)}):*\n"
            for t in pending_t[:10]:
                icon = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
                txt += f"  {icon} *#{t['id']}* {t['title']}\n     📅 Created: {t.get('created','')[:10]}\n"
            if len(pending_t) > 10:
                txt += f"  ... _aur {len(pending_t)-10} pending_\n"
            txt += "\n"

        if completed_t:
            txt += f"✅ *COMPLETED ({len(completed_t)}):*\n"
            for t in completed_t[-10:]:
                txt += f"  ✅ *#{t['id']}* {t['title']}\n     📅 Done: {t.get('done_at','')[:10]}\n"
            if len(completed_t) > 10:
                txt += f"  ... _aur {len(completed_t)-10} completed_\n"
            txt += "\n"

        # Logs summary
        summary = task_logs.get_all_task_summary()
        txt += f"━━━━━━━━━━━━━━━━━━\n"
        txt += f"📊 *SUMMARY:*\n"
        txt += f"  ➕ Created: {summary['total_created']}\n"
        txt += f"  ✅ Completed: {summary['total_completed']}\n"
        txt += f"  ⏳ Pending: {summary['total_pending']}\n"

        return txt

    # 🔥 NEW: SHOW COMPLETED TASKS ONLY
    elif action == "SHOW_COMPLETED_TASKS":
        completed_t = tasks.completed_tasks()
        if not completed_t:
            return "✅ Abhi tak koi task complete nahi hua!\n\n_Kaam karo, fir `/done [ID]` se mark karo_"

        txt = f"✅ *COMPLETED TASKS ({len(completed_t)})*\n\n"
        for t in completed_t[-15:]:
            done_date = t.get("done_at", "")[:10] if t.get("done_at") else "?"
            txt += f"  ✅ *#{t['id']}* {t['title']}\n     📅 Done: {done_date}\n"

        # Also show from logs
        log_completed = task_logs.get_completed_tasks()
        if log_completed:
            txt += f"\n📋 *TASK LOGS SE:*\n"
            for l in log_completed[-10:]:
                txt += f"  ✅ {l['description']}\n     📅 {l.get('date','?')}\n"

        return txt

    elif action == "SHOW_REMINDERS":
        active = reminders.all_active()
        if not active:
            return "⏰ Koi active reminder nahi hai.\n\nBolo — _'kal subah 7 baje uthna hai'_ aur set kar dunga!"
        txt = f"⏰ *ACTIVE REMINDERS ({len(active)})*\n\n"
        for r in active:
            icon = "🔁" if r["repeat"]=="daily" else "📅" if r["repeat"]=="weekly" else "1️⃣"
            status = "✅ Aaj ho gaya" if r["fired_today"] else "⏳ Baaki"
            txt += f"{icon} *{r['time']}* — {r['text']}\n_{status}_ | `/delremind {r['id']}`\n\n"
        return txt

    else:
        auto_extract_facts(user_msg)
        chat_hist.add("user", user_msg)
        history = chat_hist.get_recent(20)
        reply = call_gemini(build_system_prompt(), history, user_msg, chat_id, failed_reqs)
        chat_hist.add("assistant", reply)
        return reply


async def ai_chat(user_msg: str, chat_id: int = None) -> str:
    now_label   = datetime.now().strftime("%A, %d %B %Y — %I:%M %p")
    today_label = date.today().isoformat()

    if chat_id:
        action_data = call_gemini_action(user_msg, now_label, today_label)
        result = await execute_action(action_data, chat_id, user_msg)
        return result
    else:
        auto_extract_facts(user_msg)
        chat_hist.add("user", user_msg)
        history = chat_hist.get_recent(20)
        reply = call_gemini(build_system_prompt(), history)
        chat_hist.add("assistant", reply)
        return reply

# ══════════════════════════════════════════════
# KEYBOARDS
# ══════════════════════════════════════════════
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Daily Briefing",  callback_data="briefing"),
         InlineKeyboardButton("📋 Tasks",            callback_data="tasks")],
        [InlineKeyboardButton("💪 Habits",           callback_data="habits"),
         InlineKeyboardButton("📖 Diary",             callback_data="diary")],
        [InlineKeyboardButton("🎯 Goals",             callback_data="goals"),
         InlineKeyboardButton("💰 Kharcha",           callback_data="expenses")],
        [InlineKeyboardButton("📰 News",              callback_data="news_menu"),
         InlineKeyboardButton("📝 Notes",             callback_data="notes")],
        [InlineKeyboardButton("💧 Water Tracker",     callback_data="water_status"),
         InlineKeyboardButton("💳 Bills/EMI",         callback_data="bills_menu")],
        [InlineKeyboardButton("📅 Calendar",          callback_data="cal_menu"),
         InlineKeyboardButton("📊 Weekly Report",     callback_data="weekly_report")],
        [InlineKeyboardButton("📋 All Tasks",         callback_data="all_tasks"),
         InlineKeyboardButton("✅ Completed Tasks",    callback_data="completed_tasks")],
        [InlineKeyboardButton("🧹 Chat Clear",        callback_data="clear_chat"),
         InlineKeyboardButton("🧠 Yaaddasht",         callback_data="memory")],
        [InlineKeyboardButton("📊 Kal Ka Summary",    callback_data="yesterday"),
         InlineKeyboardButton("💡 Motivate Karo",     callback_data="motivate")],
    ])

def news_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇳 India News",      callback_data="news_India"),
         InlineKeyboardButton("💻 Technology",        callback_data="news_Technology")],
        [InlineKeyboardButton("💼 Business",          callback_data="news_Business"),
         InlineKeyboardButton("🌍 World",             callback_data="news_World")],
        [InlineKeyboardButton("🏏 Sports",            callback_data="news_Sports"),
         InlineKeyboardButton("🏠 Back",              callback_data="menu")],
    ])

# ══════════════════════════════════════════════
# SEND BRIEFING
# ══════════════════════════════════════════════
async def send_briefing(msg_obj):
    tp   = tasks.today_pending()
    yd   = tasks.done_on(yesterday_str())
    hd, hp = habits.today_status()
    ag   = goals.active()
    td_d = diary.get(today_str())
    exp_t = expenses.today_total()
    exp_m = expenses.month_total()
    bl    = expenses.budget_left()
    today_label = datetime.now().strftime("%A, %d %B %Y")

    txt = f"🌅 *DAILY BRIEFING*\n📅 {today_label}\n\n"

    if yd:
        txt += f"✅ *Kal {len(yd)} kaam kiye:*\n"
        for t in yd[:5]: txt += f"  • {t['title']}\n"
        txt += "\n"

    if tp:
        txt += f"📋 *Aaj {len(tp)} kaam baaki:*\n"
        for t in tp[:7]:
            e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
            txt += f"  {e} {t['title']}\n"
        txt += "\n"
    else:
        txt += "🎉 *Koi pending task nahi!*\n\n"

    if hp:
        txt += f"💪 *{len(hp)} Habits baaki:*\n"
        for h in hp[:4]: txt += f"  ○ {h['emoji']} {h['name']}\n"
        txt += "\n"
    elif habits.all():
        txt += "🎊 *Sab habits complete!*\n\n"

    if ag:
        txt += f"🎯 *Goals ({len(ag)} active):*\n"
        for g in ag[:3]:
            bar = "█"*(g["progress"]//10) + "░"*(10-g["progress"]//10)
            txt += f"  {bar} {g['title']} {g['progress']}%\n"
        txt += "\n"

    txt += f"💰 *Kharcha:* Aaj ₹{exp_t:.0f} | Mahina ₹{exp_m:.0f}"
    if bl is not None: txt += f" | Baaki ₹{bl:.0f}"
    txt += "\n\n"

    water_t = water.today_total()
    water_g = water.goal()
    water_pct = min(100, int(water_t / water_g * 100)) if water_g else 0
    water_bar = "💧" * (water_pct // 10) + "○" * (10 - water_pct // 10)
    txt += f"💧 *Paani:* {water_t}ml / {water_g}ml\n{water_bar} {water_pct}%\n\n"

    due_b = bills.due_soon(3)
    if due_b:
        txt += f"⚠️ *Bills Due (3 din mein):*\n"
        for b in due_b:
            txt += f"  💳 {b['name']} — ₹{b['amount']:.0f} ({b['due_date'][5:]})\n"
        txt += "\n"

    cal_t = calendar.today_events()
    if cal_t:
        txt += f"📅 *Aaj Ke Events:*\n"
        for e in cal_t:
            time_s = f" {e['time']}" if e.get("time") else ""
            txt += f"  ✨{time_s} {e['title']}\n"
        txt += "\n"

    if td_d: txt += f"📖 Aaj {len(td_d)} diary entries likhi hain\n\n"

    txt += "💪 *Aaj ka din badiya banao!* 🚀"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

# ══════════════════════════════════════════════
# SHOW TASKS
# ══════════════════════════════════════════════
async def show_tasks(msg_obj):
    pending = tasks.pending()
    if not pending:
        await msg_obj.reply_text(
            "🎉 *Koi pending task nahi!*\n\n`/task Kaam naam` se add karo",
            parse_mode="Markdown"); return

    txt = f"📋 *PENDING TASKS ({len(pending)})*\n\n"
    kb = []
    for t in pending[:12]:
        e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
        txt += f"{e} *#{t['id']}* {t['title']}\n"
        kb.append([InlineKeyboardButton(
            f"✅ #{t['id']}: {t['title'][:32]}", callback_data=f"done_{t['id']}")])

    kb.append([
        InlineKeyboardButton("🗑 Done wale hatao", callback_data="clear_done_tasks"),
        InlineKeyboardButton("📋 All Tasks", callback_data="all_tasks"),
        InlineKeyboardButton("🏠 Menu", callback_data="menu")
    ])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# ══════════════════════════════════════════════
# SHOW ALL TASKS
# ══════════════════════════════════════════════
async def show_all_tasks(msg_obj):
    all_t = tasks.all_tasks()
    if not all_t:
        await msg_obj.reply_text(
            "📋 *Koi task nahi!*\n\n`/task Kaam naam` se shuru karo!",
            parse_mode="Markdown"); return

    pending_t = tasks.pending()
    completed_t = tasks.completed_tasks()

    txt = f"📋 *SAARE TASKS ({len(all_t)})*\n\n"

    if pending_t:
        txt += f"⏳ *PENDING ({len(pending_t)}):*\n"
        for t in pending_t[:10]:
            icon = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
            txt += f"  {icon} *#{t['id']}* {t['title']}\n     📅 {t.get('created','')[:10]}\n"
        txt += "\n"

    if completed_t:
        txt += f"✅ *COMPLETED ({len(completed_t)}):*\n"
        for t in completed_t[-10:]:
            txt += f"  ✅ *#{t['id']}* {t['title']}\n     📅 {t.get('done_at','')[:10]}\n"
        txt += "\n"

    txt += f"━━━━━━━━━━━━━━\n📊 Created: {len(all_t)} | ✅ Done: {len(completed_t)} | ⏳ Pending: {len(pending_t)}"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Pendings Only", callback_data="tasks"),
         InlineKeyboardButton("✅ Completed Only", callback_data="completed_tasks")],
        [InlineKeyboardButton("🏠 Menu", callback_data="menu")]
    ])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=kb)

# ══════════════════════════════════════════════
# SHOW HABITS
# ══════════════════════════════════════════════
async def show_habits(msg_obj):
    done, pending = habits.today_status()
    all_h = habits.all()
    if not all_h:
        await msg_obj.reply_text(
            "💪 *Koi habit nahi!*\n\n`/habit Morning walk 🏃` se shuru karo!",
            parse_mode="Markdown"); return

    txt = "💪 *HABITS — AAJ*\n\n"
    if done:
        txt += "✅ *Ho Gaye:*\n"
        for h in done:
            txt += f"  {h['emoji']} {h['name']} 🔥{h['streak']} din\n"
        txt += "\n"

    kb = []
    if pending:
        txt += "⏳ *Baaki Hain:*\n"
        for h in pending:
            txt += f"  ○ {h['emoji']} {h['name']}\n"
            kb.append([InlineKeyboardButton(
                f"✅ {h['emoji']} {h['name']}", callback_data=f"habit_{h['id']}")])
    else:
        txt += "🎊 *Sab complete! Kamaal ho tum!* 🏆"

    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# ══════════════════════════════════════════════
# SHOW NEWS
# ══════════════════════════════════════════════
async def show_news(msg_obj, category="India"):
    await msg_obj.reply_text(f"📰 *{category} News* fetch ho rahi hai...", parse_mode="Markdown")
    items = fetch_news(category, max_items=5)
    txt = f"📰 *{category.upper()} NEWS*\n_(Free RSS — 30 min cache)_\n\n"
    for i, item in enumerate(items, 1):
        txt += f"*{i}.* {item['title']}\n"
        if item['desc']:
            txt += f"_{item['desc'][:90]}..._\n"
        txt += "\n"

    txt += "🔄 _30 minute mein auto-refresh hoti hai_"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=news_kb())

# ══════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Dost"
    txt = (f"🕌 *Assalamualaikum {name}! Main Aapka Personal AI Dost Hoon!*\n\n"
           "🧠 *Smart Memory* — chat clear bhi ho toh yaad rahunga\n"
           "📋 Tasks (Pending/Completed/All) | 📖 Diary | 💪 Habits\n"
           "💰 Kharcha | 🎯 Goals | 📰 Free News\n"
           "💧 Water Tracker | 💳 Bills/EMI\n"
           "📅 Calendar | 📊 Weekly Report\n"
           "🔒 Secret Code: `Rk1996` for old logs\n\n"
           "✅ *100% FREE | Google Gemini Multi-Model*\n"
           "_(503 error pe automatically doosra model try karta hoon!)_\n"
           "📝 _Net down? Failed requests save hojate hain!_ \n\n"
           "_Seedha kuch bhi type karo!_ 👇")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_briefing(update.message)

async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "📋 *Task add karo:*\n"
            "`/task Kaam ka naam` — normal\n"
            "`/task Important kaam high` — urgent\n"
            "`/task Chhota kaam low` — low priority",
            parse_mode="Markdown"); return
    args = " ".join(ctx.args)
    priority = "medium"
    if args.endswith(" high"): priority="high"; args=args[:-5].strip()
    elif args.endswith(" low"):  priority="low";  args=args[:-4].strip()
    t = tasks.add(args, priority=priority)
    e = "🔴" if priority=="high" else "🟡" if priority=="medium" else "🟢"
    await update.message.reply_text(
        f"✅ *Task Add!*\n\n{e} {t['title']}\nPriority: *{priority.upper()}*",
        parse_mode="Markdown")

async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Kaun sa? `/done 3`", parse_mode="Markdown"); return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t: await update.message.reply_text(f"🎉 *Complete!*\n\n✅ {t['title']}\n\n💪 Wah bhai!", parse_mode="Markdown")
        else: await update.message.reply_text("❌ Task nahi mila ya pehle done hai.")
    except: await update.message.reply_text("❌ `/done 3` format use karo", parse_mode="Markdown")

async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Kaunsa delete karo? `/deltask 3`", parse_mode="Markdown"); return
    try:
        ok = tasks.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 *Task Delete Ho Gaya!*" if ok else "❌ Task nahi mila.", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/deltask 3` format", parse_mode="Markdown")

async def cmd_diary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📖 `/diary Aaj bahut productive tha!`", parse_mode="Markdown"); return
    content = " ".join(ctx.args)
    diary.add(content)
    mem.add_fact(f"Diary {today_str()}: {content[:120]}")
    await update.message.reply_text(
        f"📖 *Diary Mein Likh Diya!*\n\n_{content}_\n\n🕐 {now_str()}",
        parse_mode="Markdown")

async def show_diary(msg_obj):
    td = diary.get(today_str()); yd_e = diary.get(yesterday_str())
    txt = "📖 *DIARY*\n\n"
    if td:
        txt += "📅 *Aaj:*\n"
        for e in td: txt += f"  {e['time']} {e['mood']} {e['text']}\n"
        txt += "\n"
    if yd_e:
        txt += "📅 *Kal:*\n"
        for e in yd_e[-3:]: txt += f"  {e['time']} {e['mood']} {e['text']}\n"
    if not td and not yd_e: txt += "_Koi entry nahi_\n\n`/diary Aaj kya hua...`"
    await msg_obj.reply_text(txt, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("💪 `/habit Morning walk 🏃`", parse_mode="Markdown"); return
    name = " ".join(ctx.args)
    emoji = "✅"
    for em in ["💪","🏃","📚","💧","🧘","🌅","🏋","✍️","🎯","🙏","🥗","😴","🚶"]:
        if em in name: emoji = em; break
    h = habits.add(name, emoji)
    await update.message.reply_text(
        f"💪 *Habit Add Ho Gayi!*\n\n{h['emoji']} {h['name']}\n\n"
        f"Roz `/hdone {h['id']}` se mark karo!",
        parse_mode="Markdown")

async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        txt = "💪 *Kaunsi habit complete ki?*\n\n"
        for h in pending: txt += f"`/hdone {h['id']}` — {h['emoji']} {h['name']}\n"
        if not pending: txt = "🎊 Aaj sab habits complete hain!"
        await update.message.reply_text(txt, parse_mode="Markdown"); return
    try:
        hid = int(ctx.args[0])
        ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"]==hid), None)
        if ok and h:
            st = f"🔥 *{streak} din ka streak!*" if streak > 1 else "✨ Pehli baar! Great start!"
            best = h.get("best_streak", streak)
            best_txt = f"\n🏆 Best streak: {best} din" if best >= 5 else ""
            await update.message.reply_text(
                f"💪 *Done!*\n\n{h['emoji']} {h['name']}\n{st}{best_txt}",
                parse_mode="Markdown")
        else:
            await update.message.reply_text("✅ Aaj pehle hi mark hai!")
    except: await update.message.reply_text("❌ `/hdone 1` format", parse_mode="Markdown")

async def cmd_delhabit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        all_h = habits.all()
        txt = "🗑 *Kaunsi habit delete karo?*\n\n"
        for h in all_h: txt += f"`/delhabit {h['id']}` — {h['emoji']} {h['name']}\n"
        await update.message.reply_text(txt, parse_mode="Markdown"); return
    try:
        habits.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 *Habit Delete Ho Gayi!*", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/delhabit 1` format", parse_mode="Markdown")

async def cmd_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📝 `/note Grocery: Doodh, Bread`", parse_mode="Markdown"); return
    n = notes.add(" ".join(ctx.args))
    await update.message.reply_text(f"📝 *Note #{n['id']} Save!*\n\n_{n['text']}_", parse_mode="Markdown")

async def cmd_delnote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🗑 `/delnote 3`", parse_mode="Markdown"); return
    try:
        notes.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 *Note delete ho gaya!*", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/delnote 3` format", parse_mode="Markdown")

async def show_notes(msg_obj):
    ns = notes.recent(12)
    if not ns:
        await msg_obj.reply_text("📝 Koi notes nahi.\n\n`/note Kuch important`", parse_mode="Markdown"); return
    txt = f"📝 *NOTES*\n\n"
    for n in ns: txt += f"*#{n['id']}* {n['text']}\n_{n['created'][:10]}_\n\n"
    await msg_obj.reply_text(txt, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "💰 *Kharcha add karo:*\n"
            "`/kharcha 50 Chai`\n"
            "`/kharcha 500 Grocery food`\n\n"
            "_(Amount phir description — category optional)_",
            parse_mode="Markdown"); return
    try:
        amount = float(ctx.args[0])
        rest = ctx.args[1:]
        categories = ["food","travel","shopping","bills","health","entertainment","education","general"]
        category = "general"
        if rest and rest[-1].lower() in categories:
            category = rest[-1].lower(); desc = " ".join(rest[:-1]) or "Kharcha"
        else:
            desc = " ".join(rest) or "Kharcha"

        expenses.add(amount, desc, category)
        bl = expenses.budget_left()
        budget_line = f"\n⚠️ Budget baaki: ₹{bl:.0f}" if bl is not None else ""

        await update.message.reply_text(
            f"💰 *₹{amount:.0f} — {desc}*\n"
            f"Category: {category}\n"
            f"Aaj total: *₹{expenses.today_total():.0f}*{budget_line}",
            parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/kharcha 100 Khana` format", parse_mode="Markdown")

async def cmd_kharcha_aaj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    items = expenses.today_list()
    if not items:
        await update.message.reply_text("💰 Aaj koi kharcha nahi.\n\n`/kharcha 50 Chai` se shuru karo!", parse_mode="Markdown"); return
    txt = "💰 *AAJ KA KHARCHA*\n\n"
    for e in items: txt += f"  ₹{e['amount']:.0f} — {e['desc']} _{e['time']}_\n"
    txt += f"\n💵 *Aaj Total: ₹{expenses.today_total():.0f}*\n"
    txt += f"📅 *Mahina Total: ₹{expenses.month_total():.0f}*\n"
    bl = expenses.budget_left()
    if bl is not None: txt += f"💳 *Budget Baaki: ₹{bl:.0f}*\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("💳 `/budget 5000` — Monthly budget set karo", parse_mode="Markdown"); return
    try:
        b = float(ctx.args[0])
        expenses.set_budget(b)
        await update.message.reply_text(f"💳 *Monthly Budget Set: ₹{b:.0f}*\n\nIs mahine ka kharcha: ₹{expenses.month_total():.0f}", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/budget 5000` format", parse_mode="Markdown")

async def cmd_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🎯 `/goal Weight lose 10kg`\n`/goal Job change 2025-12-31`", parse_mode="Markdown"); return
    title = " ".join(ctx.args)
    deadline = None
    parts = title.rsplit(" ", 1)
    if len(parts)==2 and len(parts[1])==10 and parts[1].count("-")==2:
        deadline=parts[1]; title=parts[0]
    g = goals.add(title, deadline)
    await update.message.reply_text(
        f"🎯 *Goal Add!*\n\n✨ {g['title']}" + (f"\n📅 Deadline: {deadline}" if deadline else ""),
        parse_mode="Markdown")

async def show_goals(msg_obj):
    ag = goals.active()
    cg = goals.completed()
    if not ag and not cg:
        await msg_obj.reply_text("🎯 Koi goals nahi!\n\n`/goal Kuch achieve karna hai`", parse_mode="Markdown"); return
    txt = f"🎯 *GOALS*\n\n"
    kb = []
    if ag:
        txt += f"*Active ({len(ag)}):*\n"
        for g in ag:
            bar = "█"*(g["progress"]//10) + "░"*(10-g["progress"]//10)
            txt += f"\n*{g['title']}*\n{bar} {g['progress']}%"
            if g["deadline"]: txt += f" | 📅 {g['deadline']}"
            txt += "\n"
            kb.append([InlineKeyboardButton(f"📊 {g['title'][:30]}", callback_data=f"goal_{g['id']}")])
    if cg:
        txt += f"\n✅ *Completed ({len(cg)}):*\n"
        for g in cg[-3:]: txt += f"  🏆 {g['title']}\n"
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def cmd_gprogress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        gid=int(ctx.args[0]); pct=int(ctx.args[1])
        g = goals.update_progress(gid, pct)
        if g:
            bar = "█"*(pct//10) + "░"*(10-pct//10)
            msg = f"🎯 *Progress Update!*\n\n{g['title']}\n{bar} *{pct}%*"
            if pct==100: msg += "\n\n🏆 *GOAL COMPLETE! Congratulations!* 🎉"
            await update.message.reply_text(msg, parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/gprogress 1 75` format", parse_mode="Markdown")

async def cmd_remember(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🧠 `/remember Mera birthday 15 August hai`", parse_mode="Markdown"); return
    fact = " ".join(ctx.args)
    mem.add_fact(fact)
    await update.message.reply_text(f"🧠 *Yaad Kar Liya!* ✅\n\n_{fact}_\n\n_Chat clear bhi ho toh yeh safe rahega_ 🔒", parse_mode="Markdown")

async def cmd_recall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    facts = mem.data["facts"]
    imp = mem.data.get("important_notes", [])
    if not facts and not imp:
        await update.message.reply_text("🧠 Kuch yaad nahi kiya abhi tak.\n\n`/remember Koi baat`", parse_mode="Markdown"); return
    txt = f"🧠 *YAADDASHT ({len(facts)} facts)*\n\n"
    for f in facts[-15:]: txt += f"  📌 {f['f']}\n  _{f['d']}_\n\n"
    if imp:
        txt += "\n⭐ *IMPORTANT NOTES:*\n"
        for n in imp[-5:]: txt += f"  ⭐ {n['note']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Haan, Clear Karo", callback_data="confirm_clear_chat"),
         InlineKeyboardButton("❌ Nahi", callback_data="menu")]
    ])
    count = chat_hist.count()
    await update.message.reply_text(
        f"🧹 *Chat History Clear Karna Chahte Ho?*\n\n"
        f"📊 Abhi {count} messages hain\n\n"
        f"⚠️ *Chat clear hogi — lekin:*\n"
        f"✅ Aapki memory safe rahegi\n"
        f"✅ Tasks, Diary, Habits safe hain\n"
        f"✅ Jo yaad kiya woh nahi jayega\n\n"
        f"_Sirf conversation history clear hogi_",
        parse_mode="Markdown", reply_markup=kb)

async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📰 *Kaunsi category ki news chahiye?*", parse_mode="Markdown", reply_markup=news_kb())

async def show_yesterday(msg_obj):
    yd_label = (date.today()-timedelta(days=1)).strftime("%A, %d %B")
    done = tasks.done_on(yesterday_str())
    yd_d = diary.get(yesterday_str())
    txt = f"📅 *KAL KA SUMMARY ({yd_label})*\n\n"
    if done:
        txt += f"✅ *{len(done)} Tasks Kiye:*\n"
        for t in done: txt += f"  • {t['title']}\n"
        txt += "\n"
    if yd_d:
        txt += "📖 *Diary:*\n"
        for e in yd_d: txt += f"  {e['time']} {e['mood']} {e['text']}\n"
    if not done and not yd_d: txt += "_Kal ka koi data nahi mila_"
    await msg_obj.reply_text(txt, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

# 🔥 SECRET CODE VERIFICATION for old logs
async def verify_secret_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE, action: str):
    """Verify secret code before showing old/private data"""
    if not ctx.args or ctx.args[0] != SECRET_CODE:
        await update.message.reply_text(
            "🔒 *Secret Code Required!*\n\n"
            "Purana data dekhne ke liye secret code daalo:\n"
            f"`/{action} {SECRET_CODE}`\n\n"
            "_Code galat hai toh data nahi dikhega_",
            parse_mode="Markdown")
        return False
    return True

# 🔥 COMMAND: Show task logs (requires secret code)
async def cmd_tasklogs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await verify_secret_code(update, ctx, "tasklogs"):
        return

    all_logs = task_logs.get_all_logs()
    if not all_logs:
        await update.message.reply_text("📋 *Koi task logs nahi hain!*", parse_mode="Markdown")
        return

    txt = f"📋 *TASK ACTIVITY LOGS ({len(all_logs)})*\n\n"
    # Group by date
    from collections import defaultdict
    by_date = defaultdict(list)
    for log_entry in all_logs:
        by_date[log_entry.get("date", "?")].append(log_entry)

    for date_str in sorted(by_date.keys(), reverse=True)[:7]:
        day_logs = by_date[date_str]
        txt += f"📅 *{date_str}* ({len(day_logs)} activities):\n"
        for l in day_logs[-5:]:
            icon = {"created": "➕", "completed": "✅", "deleted": "🗑", "updated": "🔄"}.get(l["type"], "📝")
            txt += f"  {icon} {l['description'][:50]}"
            if l.get("task_id"):
                txt += f" [#{l['task_id']}]"
            txt += "\n"
        txt += "\n"

    txt += "_💡 `/tasklogs Rk1996` — Purane logs dekhne ke liye_"

    await update.message.reply_text(txt, parse_mode="Markdown")

# 🔥 COMMAND: Show failed requests (requires secret code)
async def cmd_failed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await verify_secret_code(update, ctx, "failed"):
        return

    unretried = failed_reqs.get_unretried()
    if not unretried:
        await update.message.reply_text("✅ *Koi failed request pending nahi!* 🎉\n\n_Sab process ho gaye ya abhi tak koi fail nahi hua_", parse_mode="Markdown")
        return

    txt = f"📝 *PENDING FAILED REQUESTS ({len(unretried)})*\n\n"
    txt += "Ye wo messages hain jo network/AI down hone ki wajah se process nahi hue the:\n\n"

    for i, req in enumerate(unretried):
        txt += f"*#{i+1}* {req['msg'][:80]}\n"
        txt += f"  ⏰ {req['time'][:16]}\n"
        txt += f"  ❌ Reason: {req['reason'][:50]}\n\n"

    txt += "_💡 Jab network wapis aayega, ye automatically process honge!_"
    txt += f"\n_🔄 `/retryfailed {SECRET_CODE}` se manually retry karo_"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Retry All Now", callback_data="retry_failed")],
        [InlineKeyboardButton("🏠 Menu", callback_data="menu")]
    ])
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb)

# 🔥 COMMAND: Retry failed requests
async def cmd_retry_failed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await verify_secret_code(update, ctx, "retryfailed"):
        return

    unretried = failed_reqs.get_unretried()
    if not unretried:
        await update.message.reply_text("✅ *Koi failed request nahi!* 🎉", parse_mode="Markdown")
        return

    await update.message.reply_text(f"🔄 *{len(unretried)} failed requests retry ho rahi hain...*\n\n_Thodi der lagegi..._", parse_mode="Markdown")

    success = 0
    fail = 0
    for i, req in enumerate(unretried):
        try:
            reply = await ai_chat(req["msg"], req["chat_id"])
            if "⚠️ Abhi response nahi mila" not in reply:
                failed_reqs.mark_retried(i)
                success += 1
                # Send reply to user
                try:
                    await ctx.bot.send_message(
                        chat_id=req["chat_id"],
                        text=f"📝 *Aapka saved request process ho gaya!*\n\n_{reply}_",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            else:
                fail += 1
        except Exception as e:
            fail += 1
            log.error(f"Retry failed for #{i}: {e}")

    await update.message.reply_text(
        f"🔄 *RETRY COMPLETE!*\n\n"
        f"✅ Success: {success}\n"
        f"❌ Still Failed: {fail}\n\n"
        f"_Jo abhi bhi fail hue, wo agle retry mein process honge_",
        parse_mode="Markdown")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = """🤖 *COMMANDS — ADVANCED v4.0*

*📋 TASKS:*
`/task Kaam [high/low]` — Add
`/done 3` — Complete
`/deltask 3` — Delete
`/alltasks` — Saare tasks (pending + completed)
`/completed` — Sirf completed tasks

*📋 TASK LOGS:*
`/tasklogs Rk1996` — Task activity history (secret code)
`/failed Rk1996` — Failed requests dekho
`/retryfailed Rk1996` — Failed requests retry karo

*📖 DIARY:*
`/diary Aaj yeh hua` — Entry likho

*🧠 MEMORY:*
`/remember Koi baat` — Permanently save
`/recall` — Sab dekho

*📝 NOTES:*
`/note Kuch important`
`/delnote 3` — Delete

*💪 HABITS:*
`/habit Habit naam emoji`
`/hdone 1` — Complete
`/delhabit 1` — Delete

*💰 KHARCHA:*
`/kharcha 100 Khana`
`/kharcha_aaj` — Aaj ka hisaab
`/budget 5000` — Monthly budget

*🎯 GOALS:*
`/goal Goal naam`
`/gprogress 1 50` — 50% done

*💧 WATER TRACKER:*
`/water` — 250ml log karo
`/waterstatus` — Aaj ka status
`/watergoal 2500` — Daily goal set

*💳 BILLS & EMI:*
`/bill Netflix 199 5` — Bill add
`/bills` — Saare bills dekho
`/billpaid 3` — Paid mark

*📅 GOOGLE CALENDAR:*
`/cal 2026-05-10 Meeting` — Event add
`/calendar` — Upcoming events

*📊 WEEKLY REPORT:*
`/weekly` — Poori hafte ki report

*⏰ REMINDERS:*
`/remind 30m Chai peeni hai` — 30 min baad
`/remind 2h Meeting hai` — 2 ghante baad
`/remind 15:30 Doctor` — aaj 3:30 baje
`/reminders` — Saare reminders dekho
`/delremind 3` — Reminder delete

*🔒 SECRET CODE:*
Secret code: `Rk1996`
Purane logs dekhne ke liye code daalna zaroori!

*💬 Seedha kuch bhi type karo!* 😊
_Net down? Failed requests save hojate hain!_"""
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

# ══════════════════════════════════════════════
# CALLBACK HANDLER
# ══════════════════════════════════════════════
async def callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); d = q.data

    if   d == "menu":      await q.message.reply_text("🏠 *Main Menu*", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "briefing":  await send_briefing(q.message)
    elif d == "tasks":     await show_tasks(q.message)
    elif d == "all_tasks": await show_all_tasks(q.message)
    elif d == "completed_tasks":
        completed_t = tasks.completed_tasks()
        if not completed_t:
            await q.message.reply_text("✅ *Koi completed task nahi!*", parse_mode="Markdown")
        else:
            txt = f"✅ *COMPLETED TASKS ({len(completed_t)})*\n\n"
            for t in completed_t[-15:]:
                txt += f"  ✅ *#{t['id']}* {t['title']}\n     📅 {t.get('done_at','')[:10]}\n"
            await q.message.reply_text(txt, parse_mode="Markdown")
    elif d == "habits":    await show_habits(q.message)
    elif d == "diary":     await show_diary(q.message)
    elif d == "goals":     await show_goals(q.message)
    elif d == "notes":     await show_notes(q.message)
    elif d == "yesterday": await show_yesterday(q.message)
    elif d == "news_menu": await q.message.reply_text("📰 *Kaunsi news?*", parse_mode="Markdown", reply_markup=news_kb())

    elif d.startswith("news_"):
        cat = d.split("_", 1)[1]
        await show_news(q.message, cat)

    elif d == "memory":
        facts = mem.data["facts"]
        txt = f"🧠 *YAADDASHT ({len(facts)})*\n_(Chat clear se safe hai)_ 🔒\n\n"
        txt += "\n".join(f"  📌 {f['f']}" for f in facts[-12:]) if facts else "_Kuch nahi_"
        await q.message.reply_text(txt, parse_mode="Markdown")

    elif d == "expenses":
        items = expenses.today_list()
        txt = f"💰 *KHARCHA*\nAaj: ₹{expenses.today_total():.0f} | Mahina: ₹{expenses.month_total():.0f}\n"
        bl = expenses.budget_left()
        if bl is not None: txt += f"Budget baaki: ₹{bl:.0f}\n"
        txt += "\n"
        for e in items[-8:]: txt += f"  ₹{e['amount']:.0f} {e['desc']}\n"
        if not items: txt += "_Aaj koi kharcha nahi_"
        await q.message.reply_text(txt, parse_mode="Markdown")

    elif d == "clear_chat":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Haan Clear Karo", callback_data="confirm_clear_chat"),
             InlineKeyboardButton("❌ Nahi", callback_data="menu")]
        ])
        await q.message.reply_text(
            f"🧹 *Chat clear karna chahte ho?*\n\n"
            f"📊 {chat_hist.count()} messages abhi hain\n"
            f"✅ Memory, Tasks, Diary — sab safe rahega!\n"
            f"_Sirf conversation history hategi_",
            parse_mode="Markdown", reply_markup=kb)

    elif d == "confirm_clear_chat":
        count = chat_hist.clear()
        await q.message.reply_text(
            f"🧹 *Chat Clear Ho Gayi!*\n\n"
            f"🗑 {count} messages hata diye\n"
            f"🔒 Memory, Tasks, Habits — sab safe hai!\n\n"
            f"_Ab fresh start karo!_ 🚀",
            parse_mode="Markdown", reply_markup=main_kb())

    elif d == "water_status":
        total = water.today_total()
        goal  = water.goal()
        pct   = min(100, int(total / goal * 100)) if goal else 0
        bar   = "💧" * (pct // 10) + "○" * (10 - pct // 10)
        txt = f"💧 *WATER STATUS*\n\nAaj: {total}ml / {goal}ml\n{bar} {pct}%"
        await q.message.reply_text(txt, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💧 +250ml", callback_data="water_250"),
                 InlineKeyboardButton("💧 +500ml", callback_data="water_500")],
                [InlineKeyboardButton("🏠 Menu", callback_data="menu")]
            ]))

    elif d.startswith("water_") and d.split("_")[1].isdigit():
        ml = int(d.split("_")[1])
        water.add(ml)
        total = water.today_total()
        goal  = water.goal()
        pct   = min(100, int(total / goal * 100)) if goal else 0
        bar   = "💧" * (pct // 10) + "○" * (10 - pct // 10)
        msg   = f"💧 *+{ml}ml log ho gaya!*\n\nAaj total: *{total}ml / {goal}ml*\n{bar} {pct}%"
        if total >= goal:
            msg += "\n\n🎉 *Goal pura ho gaya!* 🏆"
        await q.message.reply_text(msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💧 +250ml", callback_data="water_250"),
                 InlineKeyboardButton("💧 +500ml", callback_data="water_500")],
                [InlineKeyboardButton("🏠 Menu", callback_data="menu")]
            ]))

    elif d == "bills_menu":
        all_b = bills.all_active()
        if not all_b:
            await q.message.reply_text("💳 *Koi bill nahi!*\n\n`/bill Netflix 199 5` se add karo", parse_mode="Markdown")
            return
        txt = f"💳 *BILLS & EMI ({len(all_b)})*\n\n"
        type_icons = {"emi": "🏦", "bill": "📄", "subscription": "📺"}
        kb2 = []
        for b in all_b:
            paid  = bills.is_paid_this_month(b["id"])
            icon  = type_icons.get(b["type"], "💳")
            status = "✅" if paid else "⏳"
            txt += f"{icon} {status} *{b['name']}* — ₹{b['amount']:.0f} | {b['due_day']} tarikh\n"
            if not paid:
                kb2.append([InlineKeyboardButton(f"✅ Paid: {b['name'][:25]}", callback_data=f"billpaid_{b['id']}")])
        txt += f"\n💰 Monthly Total: ₹{bills.month_total():.0f}"
        kb2.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
        await q.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb2))

    elif d.startswith("billpaid_"):
        bid = int(d.split("_")[1])
        ok  = bills.mark_paid(bid)
        b   = next((x for x in bills.all_active() if x["id"] == bid), None)
        if ok and b:
            await q.message.reply_text(f"✅ *{b['name']} — Paid!*\n₹{b['amount']:.0f} is mahine ka done 🎉", parse_mode="Markdown")
        else:
            await q.message.reply_text(f"✅ Bill #{bid} paid mark ho gaya!", parse_mode="Markdown")

    elif d == "cal_menu":
        upcoming = calendar.upcoming(30)
        if not upcoming:
            await q.message.reply_text(f"📅 *Koi upcoming event nahi!*\n\n`/cal {today_str()} Meeting` se add karo", parse_mode="Markdown")
            return
        txt = "📅 *UPCOMING EVENTS (30 din)*\n\n"
        for e in upcoming:
            td = today_str()
            day_label = "🔴 Aaj" if e["date"] == td else f"📆 {e['date'][5:]}"
            time_s = f" ⏰{e['time']}" if e.get("time") else ""
            txt += f"{day_label}{time_s} — *{e['title']}*\n"
        await q.message.reply_text(txt, parse_mode="Markdown")

    elif d == "weekly_report":
        class _FakeUpdate:
            def __init__(self, msg): self.message = msg; self.effective_chat = msg
        await cmd_weekly_report(_FakeUpdate(q.message), None)

    elif d == "retry_failed":
        unretried = failed_reqs.get_unretried()
        if not unretried:
            await q.message.reply_text("✅ *Koi failed request nahi!*", parse_mode="Markdown")
            return
        await q.message.reply_text(f"🔄 *{len(unretried)} requests retry kar raha hoon...*", parse_mode="Markdown")
        success = 0
        for i, req in enumerate(unretried):
            try:
                reply = await ai_chat(req["msg"], req["chat_id"])
                if "⚠️ Abhi response nahi mila" not in reply:
                    failed_reqs.mark_retried(i)
                    success += 1
            except:
                pass
        await q.message.reply_text(f"🔄 *Retry done!*\n✅ {success}/{len(unretried)} success", parse_mode="Markdown")

    elif d == "clear_done_tasks":
        count = tasks.clear_done()
        await q.message.reply_text(f"🗑 *{count} Done Tasks Delete Ho Gayi!*", parse_mode="Markdown")

    elif d == "motivate":
        reply = await ai_chat("Mujhe ek powerful 3-4 line motivation de Hindi mein. Real, raw, energetic. Generic mat dena.")
        await q.message.reply_text(f"💡 *Motivation:*\n\n{reply}", parse_mode="Markdown")

    elif d.startswith("done_"):
        t = tasks.complete(int(d.split("_")[1]))
        await q.message.reply_text(
            f"🎉 *Complete!*\n\n✅ {t['title']}\n💪 Wah bhai!" if t else "❌ Nahi mila",
            parse_mode="Markdown")

    elif d.startswith("habit_"):
        hid = int(d.split("_")[1])
        ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"]==hid), None)
        if ok and h:
            st = f"🔥 {streak} din ka streak!" if streak > 1 else "Pehli baar! 🌟"
            await q.message.reply_text(f"💪 *Done!*\n{h['emoji']} {h['name']}\n{st}", parse_mode="Markdown")
        else:
            await q.message.reply_text("✅ Aaj pehle hi mark hai!")

    elif d.startswith("goal_"):
        gid = d.split("_")[1]
        await q.message.reply_text(f"📊 Progress:\n`/gprogress {gid} 50` (0-100)", parse_mode="Markdown")

    elif d.startswith("remind_done_"):
        rid = int(d.split("_")[2])
        reminders.mark_fired(rid)
        await q.message.reply_text("✅ *Reminder done mark ho gaya!* 🎉", parse_mode="Markdown")
        try: await q.message.delete()
        except: pass

    elif d.startswith("remind_snooze_"):
        rid = int(d.split("_")[2])
        snooze_time = (datetime.now() + timedelta(minutes=10)).strftime("%H:%M")
        r_list = [r for r in reminders.get_all() if r["id"] == rid]
        if r_list:
            r = r_list[0]
            reminders.add(q.message.chat_id, r["text"], snooze_time, "once")
            reminders.mark_fired(rid)
        await q.message.reply_text(f"😴 *Snooze! 10 minute baad yaad dilaaunga...*\n⏰ {snooze_time} baje", parse_mode="Markdown")
        try: await q.message.delete()
        except: pass

    elif d.startswith("delremind_"):
        rid = int(d.split("_")[1])
        ok = reminders.delete(rid)
        await q.message.reply_text(f"🗑 *Reminder #{rid} delete ho gaya!*" if ok else f"❌ Reminder #{rid} nahi mila", parse_mode="Markdown")

    elif d == "confirm_nuke":
        tracked = chat_hist.get_tracked_ids()
        chat_id = q.message.chat_id
        status_msg = await q.message.reply_text("🧹 *Chat saaf ho rahi hai...*", parse_mode="Markdown")
        deleted, failed = await delete_telegram_messages(q.get_bot(), tracked)
        hist_count = chat_hist.clear()
        chat_hist.clear_msg_ids()
        try: await status_msg.delete()
        except: pass
        try: await q.message.delete()
        except: pass
        note = f"_(⚠️ {failed} purane messages nahi hue — Telegram 48hr limit)_\n" if failed else ""
        await q.get_bot().send_message(
            chat_id=chat_id,
            text=f"━━━━━━━━━━━━━━━━━━━━━━━━\n🧹 *CHAT SAAF HO GAYI!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n🗑 {deleted} messages delete hue\n🔒 Memory, Tasks, Diary safe hai\n{note}\n_Ab fresh start karo!_ ✨",
            parse_mode="Markdown", reply_markup=main_kb())

# ══════════════════════════════════════════════
# MESSAGE HANDLER
# ══════════════════════════════════════════════
async def handle_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_hist.track_msg(update.effective_chat.id, update.message.message_id)
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ai_chat(update.message.text, chat_id=update.effective_chat.id)
    try:
        sent = await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception:
        sent = await update.message.reply_text(reply)
    chat_hist.track_msg(update.effective_chat.id, sent.message_id)

# ══════════════════════════════════════════════
# REMINDER COMMANDS
# ══════════════════════════════════════════════

def parse_reminder_time(args: list):
    if not args:
        return None, None, None

    time_arg = args[0].lower()
    rest = args[1:]
    repeat = "once"

    if rest and rest[-1].lower() == "daily":
        repeat = "daily"; rest = rest[:-1]
    elif rest and rest[-1].lower() == "weekly":
        repeat = "weekly"; rest = rest[:-1]

    text = " ".join(rest) if rest else "⏰ Reminder!"

    now = datetime.now()

    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        mins = int(time_arg[:-1])
        remind_dt = now + timedelta(minutes=mins)
        return remind_dt.strftime("%H:%M"), repeat, text

    if time_arg.endswith("h") and time_arg[:-1].isdigit():
        hrs = int(time_arg[:-1])
        remind_dt = now + timedelta(hours=hrs)
        return remind_dt.strftime("%H:%M"), repeat, text

    if ":" in time_arg:
        parts = time_arg.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                return f"{h:02d}:{m:02d}", repeat, text

    return None, None, None


async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if not ctx.args:
        await update.message.reply_text(
            "⏰ *REMINDER SET KARO*\n\n"
            "*Formats:*\n"
            "`/remind 30m Chai peeni hai` — 30 min baad\n"
            "`/remind 2h Meeting hai` — 2 ghante baad\n"
            "`/remind 15:30 Doctor appointment` — aaj 3:30 baje\n"
            "`/remind 8:00 Subah uthna daily` — roz 8 baje\n\n"
            "*Repeat options:*\n"
            "• `daily` — roz same time\n"
            "• `weekly` — har hafte\n"
            "• (kuch nahi) — sirf ek baar",
            parse_mode="Markdown")
        return

    time_str, repeat, text = parse_reminder_time(ctx.args)

    if not time_str:
        await update.message.reply_text(
            "❌ *Format samajh nahi aaya!*\n\n"
            "Sahi format:\n"
            "`/remind 30m Kaam naam`\n"
            "`/remind 2h Kaam naam`\n"
            "`/remind 15:30 Kaam naam`\n"
            "`/remind 8:00 Kaam naam daily`",
            parse_mode="Markdown")
        return

    # Log reminder creation
    log.info(f"🔔 Creating reminder: chat={chat_id}, time={time_str}, text={text}, repeat={repeat}")

    r = reminders.add(chat_id, text, time_str, repeat)
    repeat_label = {"once": "Sirf ek baar", "daily": "Roz (Daily) 🔁", "weekly": "Har hafte 📅"}.get(repeat, repeat)

    await update.message.reply_text(
        f"✅ *Reminder Set Ho Gaya!*\n\n"
        f"⏰ *Waqt:* {time_str}\n"
        f"📝 *Kaam:* {text}\n"
        f"🔁 *Repeat:* {repeat_label}\n"
        f"🆔 ID: `{r['id']}`\n\n"
        f"_Delete karne ke liye: `/delremind {r['id']}`_\n"
        f"_Waqt aane pe LOUD notification aayega!_ 📳",
        parse_mode="Markdown")


async def cmd_reminders_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    all_r = reminders.all_active()
    if not all_r:
        await update.message.reply_text("⏰ *Koi reminder nahi hai!*\n\n`/remind 30m Chai peeni hai` se set karo", parse_mode="Markdown")
        return

    txt = f"⏰ *REMINDERS ({len(all_r)} active)*\n\n"
    kb  = []
    for r in all_r:
        repeat_icon = "🔁" if r["repeat"] == "daily" else "📅" if r["repeat"] == "weekly" else "1️⃣"
        status = "✅ Aaj ho gaya" if r["fired_today"] else "⏳ Baaki hai"
        txt += f"*#{r['id']}* {repeat_icon} `{r['time']}` — {r['text']}\n_{status}_\n\n"
        kb.append([InlineKeyboardButton(f"🗑 #{r['id']} Delete: {r['text'][:30]}", callback_data=f"delremind_{r['id']}")])

    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cmd_delremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🗑 `/delremind 3` — reminder ka ID daalo\n`/reminders` se ID dekho", parse_mode="Markdown")
        return
    try:
        rid = int(ctx.args[0])
        ok = reminders.delete(rid)
        if ok:
            await update.message.reply_text(f"🗑 *Reminder #{rid} Delete Ho Gaya!*", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Reminder #{rid} nahi mila.", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ `/delremind 3` format use karo", parse_mode="Markdown")


# ══════════════════════════════════════════════
# REMINDER BACKGROUND JOB
# ══════════════════════════════════════════════
async def reminder_job(context):
    now_time = datetime.now().strftime("%H:%M")

    if now_time == "00:00":
        reminders.reset_daily()
        log.info("🔄 Daily reminders reset at midnight")

    due = reminders.due_now()
    for r in due:
        try:
            repeat_note = ""
            if r["repeat"] == "daily":
                repeat_note = "\n🔁 _Kal bhi yaad dilaunga!_"
            elif r["repeat"] == "weekly":
                repeat_note = "\n📅 _Agli baar hafte baad!_"

            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Ho Gaya!", callback_data=f"remind_done_{r['id']}"),
                InlineKeyboardButton("⏰ 10 min Snooze", callback_data=f"remind_snooze_{r['id']}")
            ]])

            alert_text = (
                f"🚨🔔🚨 *ALARM ALARM ALARM* 🚨🔔🚨\n"
                f"{'═'*22}\n"
                f"⏰ *{r['time']} BAJ GAYE!*\n"
                f"{'═'*22}\n\n"
                f"📢 *{r['text'].upper()}*\n\n"
                f"{repeat_note}\n"
                f"⬇️ _Neeche button dabaao_"
            )
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=alert_text,
                parse_mode="Markdown",
                disable_notification=False,
                reply_markup=kb
            )

            await asyncio.sleep(2)
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=f"🔔 *REMINDER:* {r['text']}\n⏰ Abhi dekho!",
                parse_mode="Markdown",
                disable_notification=False
            )

            reminders.mark_fired(r["id"])
            log.info(f"🔔 Reminder fired: #{r['id']} — {r['text']} at {r['time']}")

        except Exception as e:
            log.error(f"Reminder send error #{r['id']}: {e}")

# ══════════════════════════════════════════════
# FAILED REQUEST RETRY JOB (Har 5 minute)
# ══════════════════════════════════════════════
async def failed_retry_job(context):
    """Har 5 minute mein failed requests retry karo"""
    unretried = failed_reqs.get_unretried()
    if not unretried:
        return

    log.info(f"🔄 Auto-retrying {len(unretried)} failed requests...")
    for i, req in enumerate(unretried):
        try:
            reply = await ai_chat(req["msg"], req["chat_id"])
            if "⚠️ Abhi response nahi mila" not in reply:
                failed_reqs.mark_retried(i)
                # Send reply to user
                try:
                    await context.bot.send_message(
                        chat_id=req["chat_id"],
                        text=f"📝 *Aapka saved request process ho gaya!*\n\n_{reply}_",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    log.warning(f"Failed to notify user about retry: {e}")
                log.info(f"✅ Retry success: {req['msg'][:30]}...")
        except Exception as e:
            log.warning(f"Retry failed: {e}")
            continue

# ══════════════════════════════════════════════
# WATER TRACKER COMMANDS
# ══════════════════════════════════════════════
async def cmd_water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ml = 250
    if ctx.args:
        try:
            ml = int(ctx.args[0])
        except:
            pass
    water.add(ml)
    total = water.today_total()
    goal  = water.goal()
    pct   = min(100, int(total / goal * 100))
    filled = pct // 10
    bar = "💧" * filled + "○" * (10 - filled)

    msg = f"💧 *Paani Log Ho Gaya!*\n\n"
    msg += f"Abhi piya: *{ml}ml*\n"
    msg += f"Aaj total: *{total}ml / {goal}ml*\n"
    msg += f"{bar} *{pct}%*\n\n"
    if total >= goal:
        msg += "🎉 *Wah! Aaj ka goal pura ho gaya!* 🏆"
    else:
        remaining = goal - total
        msg += f"_Aur {remaining}ml peena hai aaj!_"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💧 +250ml", callback_data="water_250"),
         InlineKeyboardButton("💧 +500ml", callback_data="water_500")],
        [InlineKeyboardButton("🏠 Menu", callback_data="menu")]
    ])
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)


async def cmd_water_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    total = water.today_total()
    goal  = water.goal()
    pct   = min(100, int(total / goal * 100)) if goal else 0
    filled = pct // 10
    bar   = "💧" * filled + "○" * (10 - filled)
    entries = water.today_entries()
    week  = water.week_summary()

    txt = f"💧 *WATER TRACKER*\n\n"
    txt += f"🎯 Goal: *{goal}ml*\n"
    txt += f"✅ Aaj piya: *{total}ml*\n"
    txt += f"{bar} *{pct}%*\n\n"

    if entries:
        txt += "*Aaj ki entries:*\n"
        for e in entries:
            txt += f"  {e['time']} — {e['ml']}ml\n"
        txt += "\n"

    txt += "*Is hafte:*\n"
    for d, ml in sorted(week.items(), reverse=True)[:5]:
        d_label = "Aaj" if d == today_str() else d[5:]
        bar_w = "█" * min(10, int(ml / goal * 10)) if goal else ""
        txt += f"  {d_label}: {ml}ml {bar_w}\n"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💧 +250ml", callback_data="water_250"),
         InlineKeyboardButton("💧 +500ml", callback_data="water_500"),
         InlineKeyboardButton("💧 +1000ml", callback_data="water_1000")],
        [InlineKeyboardButton("🎯 Goal Set Karo", callback_data="water_set_goal"),
         InlineKeyboardButton("🏠 Menu", callback_data="menu")]
    ])
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb)


async def cmd_water_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(f"💧 *Water Goal Set Karo*\n\nCurrent goal: *{water.goal()}ml*\n\n`/watergoal 2500` — 2.5 liter set karo", parse_mode="Markdown")
        return
    try:
        ml = int(ctx.args[0])
        water.set_goal(ml)
        await update.message.reply_text(f"✅ *Daily Water Goal Set!*\n\n💧 *{ml}ml* ({ml//1000}.{(ml%1000)//100}L) per day", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ `/watergoal 2000` format use karo", parse_mode="Markdown")


# ══════════════════════════════════════════════
# BILLS / EMI COMMANDS
# ══════════════════════════════════════════════
async def cmd_bill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 3:
        await update.message.reply_text(
            "💳 *Bill/EMI Add Karo*\n\n"
            "Format: `/bill [naam] [amount] [tarikh]`\n\n"
            "*Examples:*\n"
            "`/bill Netflix 199 5` — har 5 tarikh ko\n"
            "`/bill Home EMI 15000 1` — har 1 tarikh ko\n"
            "`/bill Bijli 800 15` — 15 tarikh ko",
            parse_mode="Markdown")
        return
    try:
        name     = ctx.args[0]
        amount   = float(ctx.args[1])
        due_day  = int(ctx.args[2])
        bill_type = "emi" if "emi" in name.lower() or "loan" in name.lower() else "bill"
        if "subscription" in name.lower() or name.lower() in ["netflix","amazon","hotstar","spotify"]:
            bill_type = "subscription"

        if not (1 <= due_day <= 31):
            raise ValueError("Invalid day")

        b = bills.add(name, amount, due_day, bill_type)
        type_icons = {"emi": "🏦", "bill": "📄", "subscription": "📺"}
        icon = type_icons.get(bill_type, "💳")
        await update.message.reply_text(
            f"✅ *{icon} {bill_type.upper()} Add Ho Gaya!*\n\n"
            f"📌 *{name}*\n"
            f"💰 Amount: ₹{amount:.0f}\n"
            f"📅 Due date: Har mahine ki *{due_day} tarikh*\n\n"
            f"_ID #{b['id']} — `/billpaid {b['id']}` se paid mark karo_",
            parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Format: `/bill Netflix 199 5`\n(Tarikh 1-31 honi chahiye)", parse_mode="Markdown")


async def cmd_bills_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    all_bills = bills.all_active()
    if not all_bills:
        await update.message.reply_text("💳 *Koi bill nahi!*\n\n`/bill Netflix 199 5` se add karo", parse_mode="Markdown")
        return

    txt = f"💳 *BILLS & EMI ({len(all_bills)})*\n\n"
    total_monthly = bills.month_total()
    kb = []

    type_icons = {"emi": "🏦", "bill": "📄", "subscription": "📺"}

    for b in all_bills:
        paid  = bills.is_paid_this_month(b["id"])
        icon  = type_icons.get(b["type"], "💳")
        status = "✅ Paid" if paid else "⏳ Due"
        txt += f"{icon} *#{b['id']}* {b['name']} — ₹{b['amount']:.0f}\n"
        txt += f"   📅 Har {b['due_day']} tarikh | {status}\n\n"
        if not paid:
            kb.append([InlineKeyboardButton(f"✅ Paid: {b['name'][:25]}", callback_data=f"billpaid_{b['id']}")])

    txt += f"💰 *Monthly Total: ₹{total_monthly:.0f}*"
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cmd_bill_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("✅ `/billpaid 3` — bill ka ID daalo\n`/bills` se ID dekho", parse_mode="Markdown")
        return
    try:
        bid = int(ctx.args[0])
        ok = bills.mark_paid(bid)
        bill_item = next((b for b in bills.all_active() if b["id"] == bid), None)
        if ok and bill_item:
            await update.message.reply_text(f"✅ *Bill Paid Mark Ho Gaya!*\n\n💳 *{bill_item['name']}* — ₹{bill_item['amount']:.0f}\n📅 Is mahine ka payment done! 🎉", parse_mode="Markdown")
        elif ok:
            await update.message.reply_text(f"✅ *Bill #{bid} Paid Mark Ho Gaya!*", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Bill #{bid} nahi mila.", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ `/billpaid 3` format use karo", parse_mode="Markdown")


async def cmd_del_bill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("`/delbill 3` — bill ka ID daalo", parse_mode="Markdown"); return
    try:
        bid = int(ctx.args[0])
        ok = bills.delete(bid)
        await update.message.reply_text(f"🗑 *Bill #{bid} Delete Ho Gaya!*" if ok else f"❌ Bill #{bid} nahi mila.", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ `/delbill 3` format use karo", parse_mode="Markdown")


# ══════════════════════════════════════════════
# CALENDAR COMMANDS
# ══════════════════════════════════════════════
async def cmd_cal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "📅 *Calendar Event Add Karo*\n\n"
            "Format: `/cal [YYYY-MM-DD] [naam]`\n"
            "Ya: `/cal [DD-MM-YYYY] [naam]`\n\n"
            f"`/cal {today_str()} Doctor appointment`\n"
            "`/cal 2026-05-10 Maa ka birthday`\n"
            "`/cal 15-05-2026 Office meeting 14:00`",
            parse_mode="Markdown")
        return

    import re as _re2
    args_str = " ".join(ctx.args)

    date_str = None
    title    = args_str
    event_time = ""

    m = _re2.match(r'^(\d{4}-\d{2}-\d{2})\s+(.*)', args_str)
    if m:
        date_str = m.group(1); title = m.group(2)

    if not date_str:
        m = _re2.match(r'^(\d{2})-(\d{2})-(\d{4})\s+(.*)', args_str)
        if m:
            date_str = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"; title = m.group(4)

    if not date_str:
        if args_str.lower().startswith("aaj "):
            date_str = today_str(); title = args_str[4:].strip()
        elif args_str.lower().startswith("kal "):
            date_str = (date.today() + timedelta(days=1)).isoformat(); title = args_str[4:].strip()

    if not date_str:
        await update.message.reply_text("❌ Date format samajh nahi aaya!\n\nSahi format:\n`/cal 2026-05-10 Meeting`", parse_mode="Markdown")
        return

    t_match = _re2.search(r'(\d{1,2}:\d{2})', title)
    if t_match:
        event_time = t_match.group(1)
        title = title.replace(event_time, "").strip()

    try:
        date.fromisoformat(date_str)
    except:
        await update.message.reply_text("❌ Invalid date! Format: YYYY-MM-DD", parse_mode="Markdown")
        return

    e = calendar.add(title, date_str, event_time)
    day_label = "Aaj" if date_str == today_str() else "Kal" if date_str == (date.today()+timedelta(days=1)).isoformat() else date_str
    await update.message.reply_text(
        f"📅 *Calendar Event Add Ho Gaya!*\n\n"
        f"✨ *{title}*\n"
        f"📆 Date: *{day_label}*" + (f" | ⏰ *{event_time}*" if event_time else "") + f"\n\n"
        f"_ID #{e['id']} — `/delcal {e['id']}` se hatao_",
        parse_mode="Markdown")


async def cmd_cal_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    upcoming = calendar.upcoming(30)
    if not upcoming:
        await update.message.reply_text("📅 *Koi upcoming event nahi!*\n\n`/cal YYYY-MM-DD Meeting` se add karo", parse_mode="Markdown")
        return

    txt = f"📅 *CALENDAR — Agle 30 Din*\n\n"
    today_d = today_str()
    for e in upcoming:
        day_label = "🔴 Aaj" if e["date"] == today_d else f"📆 {e['date'][5:]}"
        time_s = f" ⏰{e['time']}" if e.get("time") else ""
        txt += f"{day_label}{time_s} — *{e['title']}*\n"

    await update.message.reply_text(txt, parse_mode="Markdown")


async def cmd_del_cal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("`/delcal 3` — event ka ID daalo", parse_mode="Markdown"); return
    try:
        eid = int(ctx.args[0])
        ok = calendar.delete(eid)
        await update.message.reply_text(f"🗑 *Event #{eid} Delete Ho Gaya!*" if ok else f"❌ Event #{eid} nahi mila.", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ `/delcal 3` format use karo", parse_mode="Markdown")


# ══════════════════════════════════════════════
# WEEKLY REPORT
# ══════════════════════════════════════════════
async def cmd_weekly_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 *Weekly report ban rahi hai...*", parse_mode="Markdown")

    today_d  = date.today()
    week_ago = today_d - timedelta(days=6)
    txt = f"📊 *WEEKLY REPORT*\n"
    txt += f"_{week_ago.strftime('%d %b')} — {today_d.strftime('%d %b %Y')}_\n"
    txt += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

    all_tasks_done = []
    for i in range(7):
        d = (today_d - timedelta(days=i)).isoformat()
        all_tasks_done.extend(tasks.done_on(d))
    pending_count = len(tasks.pending())
    txt += f"📋 *TASKS*\n"
    txt += f"  ✅ Hafte mein {len(all_tasks_done)} complete kiye\n"
    txt += f"  ⏳ {pending_count} abhi pending hain\n\n"

    all_h = habits.all()
    if all_h:
        txt += f"💪 *HABITS*\n"
        for h in all_h[:5]:
            streak = h.get("streak", 0)
            best   = h.get("best_streak", 0)
            txt += f"  {h['emoji']} {h['name']}: 🔥{streak} streak | Best: {best}\n"
        txt += "\n"

    week_exp = sum(e["amount"] for e in expenses.data["list"] if e["date"] >= week_ago.isoformat())
    month_exp = expenses.month_total()
    bl = expenses.budget_left()
    txt += f"💰 *KHARCHA*\n"
    txt += f"  Hafte mein: ₹{week_exp:.0f}\n"
    txt += f"  Is mahine: ₹{month_exp:.0f}\n"
    if bl is not None:
        txt += f"  Budget baaki: ₹{bl:.0f}\n"
    txt += "\n"

    week_water = water.week_summary()
    avg_water  = int(sum(week_water.values()) / max(1, len(week_water)))
    best_water = max(week_water.values()) if week_water else 0
    goal_days  = sum(1 for ml in week_water.values() if ml >= water.goal())
    txt += f"💧 *PAANI*\n"
    txt += f"  Daily average: {avg_water}ml\n"
    txt += f"  Best day: {best_water}ml\n"
    txt += f"  Goal achieve kiya: {goal_days}/7 din\n\n"

    due = bills.due_soon(7)
    if due:
        txt += f"💳 *BILLS (Agle 7 din mein due)*\n"
        for b in due:
            txt += f"  ⚠️ {b['name']} — ₹{b['amount']:.0f} ({b['due_date'][5:]})\n"
        txt += "\n"

    ag = goals.active()
    if ag:
        txt += f"🎯 *GOALS*\n"
        for g in ag[:4]:
            bar = "█"*(g["progress"]//10) + "░"*(10-g["progress"]//10)
            txt += f"  {bar} {g['title']} {g['progress']}%\n"
        txt += "\n"

    upcoming_cal = calendar.upcoming(7)
    if upcoming_cal:
        txt += f"📅 *UPCOMING EVENTS*\n"
        for e in upcoming_cal[:4]:
            time_s = f" {e['time']}" if e.get("time") else ""
            txt += f"  {e['date'][5:]}{time_s} — {e['title']}\n"
        txt += "\n"

    txt += "━━━━━━━━━━━━━━━━━━━━━━\n"
    txt += "💪 *Agli hafte aur badiya karna hai!* 🚀"

    await update.message.reply_text(txt, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))


# ══════════════════════════════════════════════
# BILL DUE CHECK JOB
# ══════════════════════════════════════════════
async def bill_due_alert_job(context):
    now_time = datetime.now().strftime("%H:%M")
    if now_time != "09:00":
        return

    due = bills.due_soon(3)
    if not due:
        return

    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    if not chat_ids:
        return

    txt = "💳 *BILL DUE REMINDER*\n\n"
    for b in due:
        txt += f"⚠️ *{b['name']}* — ₹{b['amount']:.0f}\n"
        txt += f"   📅 Due: {b['due_date']} | `/billpaid {b['id']}` se paid mark karo\n\n"
    txt += "_Paid ho gaya? `/billpaid [ID]` se mark karo!_"

    for cid in chat_ids:
        try:
            await context.bot.send_message(chat_id=cid, text=txt, parse_mode="Markdown")
        except Exception as e:
            log.warning(f"Bill alert send error: {e}")


# ══════════════════════════════════════════════
# WATER REMINDER JOB
# ══════════════════════════════════════════════
async def water_reminder_job(context):
    now_h = datetime.now().hour
    if not (8 <= now_h <= 22):
        return
    if now_h % 2 != 0:
        return

    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    if not chat_ids:
        return

    total = water.today_total()
    goal  = water.goal()
    if total >= goal:
        return

    remaining = goal - total
    pct = int(total / goal * 100) if goal else 0

    txt = (f"💧 *Paani Peena Yaad Hai?*\n\n"
           f"Aaj: {total}ml / {goal}ml ({pct}%)\n"
           f"Aur {remaining}ml baaki hai!\n\n"
           f"`/water` se log karo 💧")

    for cid in chat_ids:
        try:
            await context.bot.send_message(
                chat_id=cid, text=txt, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💧 +250ml", callback_data="water_250"),
                    InlineKeyboardButton("💧 +500ml", callback_data="water_500")
                ]])
            )
        except Exception as e:
            log.warning(f"Water reminder error: {e}")


# ══════════════════════════════════════════════
async def delete_telegram_messages(bot, tracked_ids: list) -> tuple:
    deleted = 0
    failed = 0
    for i, entry in enumerate(tracked_ids):
        try:
            await bot.delete_message(chat_id=entry["chat_id"], message_id=entry["msg_id"])
            deleted += 1
            if i % 20 == 19:
                await asyncio.sleep(0.5)
        except Exception:
            failed += 1
    return deleted, failed

async def cmd_nuke(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_hist.track_msg(update.effective_chat.id, update.message.message_id)
    tracked = chat_hist.get_tracked_ids()
    count = chat_hist.count()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💣 Haan! Sab Saaf Karo", callback_data="confirm_nuke"),
         InlineKeyboardButton("❌ Nahi", callback_data="menu")]
    ])
    sent = await update.message.reply_text(
        "💣 *FULL CHAT NUKE*\n\n"
        "Yeh button dabane se:\n"
        f"🗑 *{len(tracked)} bot messages* screen se hatenge\n"
        f"🧹 *{count} chat history* clear hogi\n"
        "✅ Memory, Tasks, Diary — safe rahega\n\n"
        "_Note: Sirf bot ke messages delete hote hain_",
        parse_mode="Markdown", reply_markup=kb)
    chat_hist.track_msg(update.effective_chat.id, sent.message_id)

# New command handlers for all tasks and completed tasks
async def cmd_alltasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    all_t = tasks.all_tasks()
    if not all_t:
        await update.message.reply_text("📋 *Koi task nahi!*\n\n`/task Kaam naam` se shuru karo!", parse_mode="Markdown")
        return

    pending_t = tasks.pending()
    completed_t = tasks.completed_tasks()

    txt = f"📋 *SAARE TASKS ({len(all_t)})*\n\n"

    if pending_t:
        txt += f"⏳ *PENDING ({len(pending_t)}):*\n"
        for t in pending_t[:10]:
            icon = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
            txt += f"  {icon} *#{t['id']}* {t['title']}\n     📅 {t.get('created','')[:10]}\n"
        if len(pending_t) > 10:
            txt += f"  ... _aur {len(pending_t)-10} pending_\n"
        txt += "\n"

    if completed_t:
        txt += f"✅ *COMPLETED ({len(completed_t)}):*\n"
        for t in completed_t[-10:]:
            txt += f"  ✅ *#{t['id']}* {t['title']}\n     📅 {t.get('done_at','')[:10]}\n"
        if len(completed_t) > 10:
            txt += f"  ... _aur {len(completed_t)-10} completed_\n"

    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    completed_t = tasks.completed_tasks()
    if not completed_t:
        await update.message.reply_text("✅ *Koi completed task nahi!*", parse_mode="Markdown")
        return

    txt = f"✅ *COMPLETED TASKS ({len(completed_t)})*\n\n"
    for t in completed_t[-15:]:
        txt += f"  ✅ *#{t['id']}* {t['title']}\n     📅 Done: {t.get('done_at','')[:10]}\n"

    # Also from logs
    log_completed = task_logs.get_completed_tasks()
    if log_completed:
        txt += f"\n📋 *TASK LOGS SE:*\n"
        for l in log_completed[-5:]:
            txt += f"  ✅ {l['description']}\n     📅 {l.get('date','?')}\n"

    await update.message.reply_text(txt, parse_mode="Markdown")

# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
def main():
    log.info("🤖 Personal AI Bot v4.0 — Advanced — Starting...")
    log.info(f"📡 Models (fallback order): {', '.join(GEMINI_MODELS)}")
    log.info(f"🔒 Secret Code: {SECRET_CODE}")
    log.info(f"📝 Failed request tracking: ENABLED ✓")
    log.info(f"📋 Task logs tracking: ENABLED ✓")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    handlers = [
        ("start",       cmd_start),
        ("help",        cmd_help),
        ("briefing",    cmd_briefing),
        ("task",        cmd_task),
        ("done",        cmd_done),
        ("deltask",     cmd_deltask),
        ("alltasks",    cmd_alltasks),
        ("completed",   cmd_completed),
        ("tasklogs",    cmd_tasklogs),
        ("failed",      cmd_failed),
        ("retryfailed", cmd_retry_failed),
        ("diary",       cmd_diary),
        ("remember",    cmd_remember),
        ("recall",      cmd_recall),
        ("note",        cmd_note),
        ("delnote",     cmd_delnote),
        ("habit",       cmd_habit),
        ("hdone",       cmd_hdone),
        ("delhabit",    cmd_delhabit),
        ("kharcha",     cmd_kharcha),
        ("kharcha_aaj", cmd_kharcha_aaj),
        ("budget",      cmd_budget),
        ("goal",        cmd_goal),
        ("gprogress",   cmd_gprogress),
        ("news",        cmd_news),
        ("clear",       cmd_clear),
        ("nuke",        cmd_nuke),
        ("remind",      cmd_remind),
        ("reminders",   cmd_reminders_list),
        ("delremind",   cmd_delremind),
        ("yesterday",   lambda u,c: show_yesterday(u.message)),
        ("water",       cmd_water),
        ("waterstatus", cmd_water_status),
        ("watergoal",   cmd_water_goal),
        ("bill",        cmd_bill),
        ("bills",       cmd_bills_list),
        ("billpaid",    cmd_bill_paid),
        ("delbill",     cmd_del_bill),
        ("cal",         cmd_cal),
        ("calendar",    cmd_cal_list),
        ("delcal",      cmd_del_cal),
        ("weekly",      cmd_weekly_report),
    ]
    for cmd, handler in handlers:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    job_queue = app.job_queue
    if job_queue is not None:
        job_queue.run_repeating(reminder_job, interval=30, first=5)
        job_queue.run_repeating(failed_retry_job, interval=300, first=60)  # Har 5 min
        job_queue.run_repeating(bill_due_alert_job, interval=3600, first=60)
        job_queue.run_repeating(water_reminder_job, interval=3600, first=300)
        log.info("⏰ Reminder job queue started — har 30 second check!")
        log.info("🔄 Failed request retry job started — har 5 minute!")
        log.info("💳 Bill due alert job started!")
        log.info("💧 Water reminder job started!")
    else:
        log.warning("⚠️ JobQueue nahi mila!")
        log.warning("Fix: pip install \"python-telegram-bot[job-queue]\"")

    log.info("✅ Bot ready! Telegram pe /start karo.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()