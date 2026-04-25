#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════╗
║       PERSONAL AI ASSISTANT — ADVANCED v4.5          ║
║  100% FREE | Gemini Multi-Model | Smart Memory       ║
║  Offline Capture | Secret Code | Enhanced Logging    ║
╚══════════════════════════════════════════════════════╝
"""

import os, json, logging, time, asyncio, urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta
from xml.etree import ElementTree as ET
import hashlib
import threading
import re as _re

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

SECRET_CODE = "Rk1996"
SECRET_CODE_HASH = hashlib.sha256(SECRET_CODE.encode()).hexdigest()

GEMINI_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

# ══════════════════════════════════════════════
# FILE PATHS
# ══════════════════════════════════════════════
DATA = os.path.join(os.getcwd(), "data")
os.makedirs(DATA, exist_ok=True)

F_MEMORY   = os.path.join(DATA, "memory.json")
F_TASKS    = os.path.join(DATA, "tasks.json")
F_DIARY    = os.path.join(DATA, "diary.json")
F_HABITS   = os.path.join(DATA, "habits.json")
F_NOTES    = os.path.join(DATA, "notes.json")
F_EXPENSES = os.path.join(DATA, "expenses.json")
F_GOALS    = os.path.join(DATA, "goals.json")
F_CHAT     = os.path.join(DATA, "chat_history.json")
F_NEWS     = os.path.join(DATA, "news_cache.json")
F_REMINDERS = os.path.join(DATA, "reminders.json")
F_WATER    = os.path.join(DATA, "water.json")
F_BILLS    = os.path.join(DATA, "bills.json")
F_CALENDAR = os.path.join(DATA, "calendar.json")
F_OFFLINE  = os.path.join(DATA, "offline_queue.json")
F_ALL_LOGS = os.path.join(DATA, "all_activity_log.json")

NEWS_FEEDS = {
    "India":      "https://feeds.bbci.co.uk/hindi/rss.xml",
    "Technology": "https://feeds.feedburner.com/ndtvnews-tech-news",
    "Business":   "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "World":      "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Sports":     "https://feeds.bbci.co.uk/sport/rss.xml",
}

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
def verify_secret_code(code: str) -> bool:
    return hashlib.sha256(code.encode()).hexdigest() == SECRET_CODE_HASH

# ══════════════════════════════════════════════
# GEMINI CALLER
# ══════════════════════════════════════════════
def call_gemini(system_prompt: str, messages: list, retries=2) -> str:
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
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
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
                    time.sleep(3 if attempt == 0 else 6)
                    continue
                elif e.code in (500, 503):
                    errors.append(f"{model}: server error")
                    time.sleep(2)
                    continue
                elif e.code == 404:
                    errors.append(f"{model}: not found")
                    break
                elif e.code == 400:
                    return f"❌ Request error: {body[:150]}"
                else:
                    return f"❌ API Error {e.code}: {body[:150]}"
            except Exception as e:
                errors.append(str(e))
                break

    return ("⚠️ *AI Abhi Offline Hai!*\n\n"
            "😔 Gemini API se connection nahi ho pa raha.\n"
            "📝 *Aapka message save kar liya hai* - jab AI online hoga tab process hoga.\n\n"
            f"_({', '.join(errors[:2])})_")

# ══════════════════════════════════════════════
# NEWS FETCH
# ══════════════════════════════════════════════
def fetch_news(category="India", max_items=5) -> list:
    cache = load(F_NEWS, {"cache": {}, "updated": {}})
    now_ts = time.time()
    if category in cache["cache"] and now_ts - cache["updated"].get(category, 0) < 1800:
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
# ALL CLASSES
# ══════════════════════════════════════════════

class ChatHistory:
    def __init__(self):
        self.data = load(F_CHAT, {"history": [], "cleared_at": None, "msg_ids": []})
        if "msg_ids" not in self.data:
            self.data["msg_ids"] = []

    def add(self, role: str, content: str):
        self.data["history"].append({"role": role, "content": content, "time": datetime.now().isoformat()})
        self.data["history"] = self.data["history"][-80:]
        save(F_CHAT, self.data)

    def track_msg(self, chat_id: int, msg_id: int):
        self.data["msg_ids"].append({"chat_id": chat_id, "msg_id": msg_id})
        self.data["msg_ids"] = self.data["msg_ids"][-500:]
        save(F_CHAT, self.data)

    def get_tracked_ids(self):
        return self.data.get("msg_ids", [])

    def get_recent(self, n=20) -> list:
        return [{"role": m["role"], "content": m["content"]} for m in self.data["history"][-n:]]

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


class Memory:
    def __init__(self):
        self.data = load(F_MEMORY, {"facts": [], "prefs": {}, "dates": {}, "important_notes": []})

    def save_data(self): save(F_MEMORY, self.data)

    def add_fact(self, fact: str):
        existing = [f["f"] for f in self.data["facts"][-50:]]
        if fact[:50] in [e[:50] for e in existing]: return
        self.data["facts"].append({"f": fact, "d": today_str()})
        self.data["facts"] = self.data["facts"][-400:]
        self.save_data()

    def add_important(self, note: str):
        self.data["important_notes"].append({"note": note, "d": today_str()})
        self.save_data()

    def set_pref(self, k, v): self.data["prefs"][k] = v; self.save_data()
    def add_date(self, name, d): self.data["dates"][name] = d; self.save_data()

    def clear_facts(self):
        count = len(self.data["facts"])
        self.data["facts"] = []
        self.save_data()
        return count

    def get_all_facts(self): return self.data["facts"]

    def context(self) -> str:
        facts = "\n".join(f"• {x['f']}" for x in self.data["facts"][-30:]) or "Kuch nahi"
        prefs = "\n".join(f"• {k}: {v}" for k, v in self.data["prefs"].items()) or "Kuch nahi"
        dates = "\n".join(f"• {k}: {v}" for k, v in self.data["dates"].items()) or "Kuch nahi"
        imp   = "\n".join(f"⭐ {n['note']}" for n in self.data["important_notes"][-10:]) or "Kuch nahi"
        return (f"FACTS:\n{facts}\n\nPREFERENCES:\n{prefs}\n\nIMPORTANT DATES:\n{dates}\n\nIMPORTANT NOTES:\n{imp}")


class Tasks:
    def __init__(self):
        self.data = load(F_TASKS, {"list": [], "counter": 0, "completed_history": []})

    def save_data(self): save(F_TASKS, self.data)

    def add(self, title, priority="medium", due=None):
        self.data["counter"] += 1
        t = {"id": self.data["counter"], "title": title, "priority": priority,
             "due": due or today_str(), "done": False, "done_at": None,
             "created": datetime.now().isoformat(), "completed_date": None}
        self.data["list"].append(t); self.save_data(); return t

    def complete(self, tid):
        for t in self.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True
                t["done_at"] = datetime.now().isoformat()
                t["completed_date"] = today_str()
                self.data["completed_history"].append({"original_task": t.copy(), "completed_timestamp": datetime.now().isoformat()})
                self.save_data(); return t
        return None

    def delete(self, tid):
        before = len(self.data["list"])
        self.data["list"] = [t for t in self.data["list"] if t["id"] != tid]
        self.save_data()
        return before != len(self.data["list"])

    def pending(self): return [t for t in self.data["list"] if not t["done"]]
    def all_tasks(self): return self.data["list"]
    def completed_tasks(self): return [t for t in self.data["list"] if t["done"]]
    
    def done_on(self, d):
        return [t for t in self.data["list"] if t["done"] and t.get("completed_date", "") == d]
    
    def today_pending(self):
        td = today_str()
        return [t for t in self.data["list"] if not t["done"] and t.get("due", "") <= td]
    
    def clear_done(self):
        before = len(self.data["list"])
        for t in self.data["list"]:
            if t["done"]:
                self.data["completed_history"].append({"task": t, "cleared_at": datetime.now().isoformat()})
        self.data["list"] = [t for t in self.data["list"] if not t["done"]]
        self.save_data()
        return before - len(self.data["list"])
    
    def get_completed_history(self, date_filter=None):
        history = []
        for entry in self.data.get("completed_history", []):
            task = entry.get("original_task", entry.get("task", {}))
            if not date_filter or task.get("completed_date") == date_filter:
                history.append(task)
        return history


class Diary:
    def __init__(self):
        self.data = load(F_DIARY, {"entries": {}})
    def save_data(self): save(F_DIARY, self.data)
    def add(self, content, mood="😊"):
        td = today_str()
        if td not in self.data["entries"]: self.data["entries"][td] = []
        self.data["entries"][td].append({"text": content, "mood": mood, "time": now_str()})
        self.save_data()
    def get(self, d): return self.data["entries"].get(d, [])
    def all_dates(self): return sorted(self.data["entries"].keys(), reverse=True)


class Habits:
    def __init__(self):
        self.data = load(F_HABITS, {"list": [], "logs": {}, "counter": 0})
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
        self.save_data()
        streak = next((x["streak"] for x in self.data["list"] if x["id"] == hid), 1)
        return True, streak
    def today_status(self):
        done_ids = self.data["logs"].get(today_str(), [])
        return ([h for h in self.data["list"] if h["id"] in done_ids],
                [h for h in self.data["list"] if h["id"] not in done_ids])
    def delete(self, hid): self.data["list"] = [h for h in self.data["list"] if h["id"] != hid]; self.save_data()
    def all(self): return self.data["list"]


class Notes:
    def __init__(self):
        self.data = load(F_NOTES, {"list": [], "counter": 0})
    def save_data(self): save(F_NOTES, self.data)
    def add(self, content, tag="general"):
        self.data["counter"] += 1
        n = {"id": self.data["counter"], "text": content, "tag": tag, "created": datetime.now().isoformat()}
        self.data["list"].append(n); self.save_data(); return n
    def search(self, q): return [n for n in self.data["list"] if q.lower() in n["text"].lower()]
    def delete(self, nid): self.data["list"] = [n for n in self.data["list"] if n["id"] != nid]; self.save_data()
    def recent(self, n=15): return self.data["list"][-n:]


class Expenses:
    def __init__(self):
        self.data = load(F_EXPENSES, {"list": [], "counter": 0, "budget": {}})
    def save_data(self): save(F_EXPENSES, self.data)
    def add(self, amount, desc, category="general"):
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "amount": amount, "desc": desc, "category": category, "date": today_str(), "time": now_str()}
        self.data["list"].append(e); self.save_data(); return e
    def set_budget(self, amount): self.data["budget"]["monthly"] = amount; self.save_data()
    def today_total(self): return sum(e["amount"] for e in self.data["list"] if e["date"] == today_str())
    def month_total(self):
        m = today_str()[:7]
        return sum(e["amount"] for e in self.data["list"] if e["date"][:7] == m)
    def today_list(self): return [e for e in self.data["list"] if e["date"] == today_str()]
    def budget_left(self):
        b = self.data["budget"].get("monthly", 0)
        return b - self.month_total() if b else None


class Goals:
    def __init__(self):
        self.data = load(F_GOALS, {"list": [], "counter": 0})
    def save_data(self): save(F_GOALS, self.data)
    def add(self, title, deadline=None, why=""):
        self.data["counter"] += 1
        g = {"id": self.data["counter"], "title": title, "deadline": deadline or "", "why": why,
             "progress": 0, "done": False, "created": today_str(), "milestones": []}
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
    def __init__(self):
        self.data = load(F_REMINDERS, {"list": [], "counter": 0, "log": []})
    def save_data(self): save(F_REMINDERS, self.data)
    def add(self, chat_id: int, text: str, remind_at: str, repeat: str = "once") -> dict:
        self.data["counter"] += 1
        r = {"id": self.data["counter"], "chat_id": chat_id, "text": text, "time": remind_at,
             "repeat": repeat, "date": today_str(), "active": True, "fired_today": False,
             "created": datetime.now().isoformat(), "history": []}
        self.data["list"].append(r)
        self.data["log"].append({"timestamp": datetime.now().isoformat(), "action": "created", "reminder_id": r["id"], "text": text, "time": remind_at})
        self.save_data(); return r
    def all_active(self): return [r for r in self.data["list"] if r["active"]]
    def delete(self, rid: int) -> bool:
        before = len(self.data["list"])
        self.data["list"] = [r for r in self.data["list"] if r["id"] != rid]
        self.save_data()
        return before != len(self.data["list"])
    def mark_fired(self, rid: int):
        for r in self.data["list"]:
            if r["id"] == rid:
                r["fired_today"] = True
                r["history"].append({"fired_at": datetime.now().isoformat(), "date": today_str()})
                if r["repeat"] == "once": r["active"] = False
                self.save_data(); break
    def reset_daily(self):
        changed = False
        for r in self.data["list"]:
            if r["fired_today"]: r["fired_today"] = False; changed = True
        if changed: self.save_data()
    def due_now(self) -> list:
        now_dt = datetime.now(); now_str_hm = now_dt.strftime("%H:%M"); due = []
        for r in self.data["list"]:
            if not r["active"] or r["fired_today"]: continue
            r_time = r["time"]
            try:
                r_dt = datetime.strptime(today_str() + " " + r_time, "%Y-%m-%d %H:%M")
                diff = (now_dt - r_dt).total_seconds()
                if 0 <= diff < 120: due.append(r)
            except Exception:
                if r_time == now_str_hm: due.append(r)
        return due
    def get_all(self): return self.data["list"]
    def get_reminders_history(self, date_filter=None):
        history = []
        for r in self.data["list"]:
            for fire_record in r.get("history", []):
                if not date_filter or fire_record.get("date") == date_filter:
                    history.append({"reminder_id": r["id"], "text": r["text"], "fired_at": fire_record["fired_at"]})
        return sorted(history, key=lambda x: x["fired_at"], reverse=True)


class WaterTracker:
    def __init__(self):
        self.data = load(F_WATER, {"logs": {}, "goal_ml": 2000})
    def save_data(self): save(F_WATER, self.data)
    def add(self, ml: int = 250):
        td = today_str()
        if td not in self.data["logs"]: self.data["logs"][td] = []
        self.data["logs"][td].append({"ml": ml, "time": now_str()})
        self.save_data()
    def today_total(self) -> int: return sum(e["ml"] for e in self.data["logs"].get(today_str(), []))
    def today_count(self) -> int: return len(self.data["logs"].get(today_str(), []))
    def goal(self) -> int: return self.data.get("goal_ml", 2000)
    def set_goal(self, ml: int): self.data["goal_ml"] = ml; self.save_data()
    def today_entries(self): return self.data["logs"].get(today_str(), [])
    def week_summary(self) -> dict:
        result = {}
        for i in range(7):
            d = (date.today() - timedelta(days=i)).isoformat()
            result[d] = sum(e["ml"] for e in self.data["logs"].get(d, []))
        return result


class BillTracker:
    def __init__(self):
        self.data = load(F_BILLS, {"list": [], "counter": 0})
    def save_data(self): save(F_BILLS, self.data)
    def add(self, name: str, amount: float, due_day: int, bill_type: str = "bill", notes: str = "") -> dict:
        self.data["counter"] += 1
        b = {"id": self.data["counter"], "name": name, "amount": amount, "due_day": due_day,
             "type": bill_type, "notes": notes, "active": True, "paid_months": [], "created": today_str()}
        self.data["list"].append(b); self.save_data(); return b
    def all_active(self): return [b for b in self.data["list"] if b["active"]]
    def mark_paid(self, bid: int) -> bool:
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid:
                if ym not in b["paid_months"]: b["paid_months"].append(ym)
                self.save_data(); return True
        return False
    def is_paid_this_month(self, bid: int) -> bool:
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid: return ym in b.get("paid_months", [])
        return False
    def delete(self, bid: int) -> bool:
        before = len(self.data["list"])
        self.data["list"] = [b for b in self.data["list"] if b["id"] != bid]
        self.save_data()
        return before != len(self.data["list"])
    def due_soon(self, days_ahead: int = 3) -> list:
        today_d = date.today(); result = []
        for b in self.data["list"]:
            if not b["active"] or self.is_paid_this_month(b["id"]): continue
            due_day = b["due_day"]
            try: due_date = date(today_d.year, today_d.month, due_day)
            except ValueError: due_date = date(today_d.year, today_d.month, 28)
            if today_d <= due_date <= today_d + timedelta(days=days_ahead):
                result.append({**b, "due_date": due_date.isoformat()})
        return result
    def month_total(self) -> float: return sum(b["amount"] for b in self.data["list"] if b["active"])


class CalendarManager:
    def __init__(self):
        self.data = load(F_CALENDAR, {"events": [], "counter": 0})
    def save_data(self): save(F_CALENDAR, self.data)
    def add(self, title: str, event_date: str, event_time: str = "", notes: str = "") -> dict:
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "title": title, "date": event_date, "time": event_time, "notes": notes, "created": today_str()}
        self.data["events"].append(e); self.save_data(); return e
    def delete(self, eid: int) -> bool:
        before = len(self.data["events"])
        self.data["events"] = [e for e in self.data["events"] if e["id"] != eid]
        self.save_data()
        return before != len(self.data["events"])
    def upcoming(self, days: int = 7) -> list:
        today_d = date.today(); cutoff = today_d + timedelta(days=days); result = []
        for e in self.data["events"]:
            try:
                ed = date.fromisoformat(e["date"])
                if today_d <= ed <= cutoff: result.append(e)
            except Exception: pass
        return sorted(result, key=lambda x: x["date"])
    def today_events(self) -> list: return [e for e in self.data["events"] if e["date"] == today_str()]
    def all_events(self) -> list:
        today_d = today_str()
        return sorted([e for e in self.data["events"] if e["date"] >= today_d], key=lambda x: (x["date"], x.get("time", "")))


class ActivityLogger:
    def __init__(self):
        self.log_file = F_ALL_LOGS
        self.data = self.load_logs()
    def load_logs(self):
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
        return {"activities": [], "protected_activities": []}
    def save_logs(self):
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e: log.error(f"Activity log save error: {e}")
    def log_activity(self, activity_type: str, user_id: int, username: str, content: str, status: str = "completed", protected: bool = False):
        activity = {"timestamp": datetime.now().isoformat(), "type": activity_type, "user_id": user_id,
                    "username": username, "content": content[:500], "status": status, "date": today_str()}
        self.data["activities"].append(activity)
        if protected or activity_type in ["task_added", "task_completed", "memory_saved", "important_note", "reminder_set", "reminder_fired"]:
            self.data["protected_activities"].append(activity)
        self.data["activities"] = self.data["activities"][-10000:]
        self.data["protected_activities"] = self.data["protected_activities"][-5000:]
        self.save_logs()
    def get_protected_activities(self, date_filter=None):
        activities = self.data["protected_activities"]
        if date_filter: activities = [a for a in activities if a["date"] == date_filter]
        return activities
    def get_all_activities(self, date_filter=None, activity_type=None):
        activities = self.data["activities"]
        if date_filter: activities = [a for a in activities if a["date"] == date_filter]
        if activity_type: activities = [a for a in activities if a["type"] == activity_type]
        return activities


class OfflineQueue:
    def __init__(self):
        self.queue_file = F_OFFLINE
        self.queue = self.load_queue()
        self.lock = threading.Lock()
    def load_queue(self):
        try:
            if os.path.exists(self.queue_file):
                with open(self.queue_file, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
        return {"pending_messages": [], "processed_messages": []}
    def save_queue(self):
        with self.lock:
            try:
                with open(self.queue_file, "w", encoding="utf-8") as f:
                    json.dump(self.queue, f, ensure_ascii=False, indent=2)
            except Exception as e: log.error(f"Offline queue save error: {e}")
    def add_message(self, user_id: int, chat_id: int, username: str, message: str):
        with self.lock:
            msg_entry = {"timestamp": datetime.now().isoformat(), "user_id": user_id, "chat_id": chat_id,
                         "username": username, "message": message, "processed": False}
            self.queue["pending_messages"].append(msg_entry)
            self.save_queue()
    def get_pending_messages(self): return [m for m in self.queue["pending_messages"] if not m["processed"]]
    def mark_processed(self, message_index: int):
        with self.lock:
            if 0 <= message_index < len(self.queue["pending_messages"]):
                self.queue["pending_messages"][message_index]["processed"] = True
                self.save_queue()
    def clear_processed(self):
        with self.lock:
            unprocessed = [m for m in self.queue["pending_messages"] if not m["processed"]]
            processed = [m for m in self.queue["pending_messages"] if m["processed"]]
            self.queue["pending_messages"] = unprocessed + processed[-100:]
            self.save_queue()


# ══════════════════════════════════════════════
# INIT ALL OBJECTS
# ══════════════════════════════════════════════
chat_hist = ChatHistory()
mem       = Memory()
tasks     = Tasks()
diary     = Diary()
habits    = Habits()
notes     = Notes()
expenses  = Expenses()
goals     = Goals()
reminders = Reminders()
water     = WaterTracker()
bills     = BillTracker()
calendar  = CalendarManager()
activity_logger = ActivityLogger()
offline_queue = OfflineQueue()

log.info("✅ All objects initialized!")

# ══════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════
def build_system_prompt() -> str:
    now_label = datetime.now().strftime("%A, %d %B %Y — %I:%M %p")
    tp = tasks.today_pending(); yd = tasks.done_on(yesterday_str())
    hd, hp = habits.today_status(); ag = goals.active()
    td_d = diary.get(today_str()); exp_t = expenses.today_total()
    exp_m = expenses.month_total(); bl = expenses.budget_left()
    msgs = chat_hist.count(); water_today = water.today_total()
    water_goal = water.goal(); due_bills = bills.due_soon(3)
    cal_today = calendar.today_events()

    tasks_s = "\n".join(f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}" for t in tp[:6]) or "  Koi nahi"
    yd_s = "\n".join(f"  ✓ {t['title']}" for t in yd[:5]) or "  Koi nahi"
    h_done = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    h_pend = ", ".join(f"{h['name']}" for h in hp) or "Sab ho gaye! 🎉"
    goals_s = "\n".join(f"  🎯 {g['title']} ({g['progress']}%)" for g in ag[:4]) or "  Koi nahi"
    diary_s = "\n".join(f"  {e['time']} {e['text']}" for e in td_d[-3:]) or "  Kuch nahi"
    budget_s = f"Budget baaki: ₹{bl:.0f}" if bl is not None else ""
    water_pct = int(water_today / water_goal * 100) if water_goal else 0
    bills_s = "\n".join(f"  ⚠️ {b['name']} ₹{b['amount']:.0f} — {b['due_date']}" for b in due_bills) or "  Koi nahi"
    cal_s = "\n".join(f"  📅 {e['time'] or ''} {e['title']}" for e in cal_today) or "  Koi nahi"

    return f"""Tu mera Personal AI Assistant hai — naam 'Dost'. Hamesha Hindi/Hinglish mein baat kar.

⏰ ABHI: {now_label}
💬 Chat messages: {msgs}

📋 AAJ KE TASKS:
{tasks_s}

✅ KAL KYA KIYA:
{yd_s}

💪 HABITS: Done: {h_done} | Baaki: {h_pend}

📖 DIARY (aaj):
{diary_s}

💰 KHARCHA: Aaj ₹{exp_t} | Mahina ₹{exp_m} {budget_s}

🎯 GOALS:
{goals_s}

💧 PAANI: {water_today}ml / {water_goal}ml ({water_pct}%)

📅 AAJ KE EVENTS:
{cal_s}

💳 BILLS DUE:
{bills_s}

━━ YAADDASHT ━━
{mem.context()}

RULES: Dost ki tarah baat kar, Hindi/Hinglish mein jawab de, short aur helpful reh."""

# ══════════════════════════════════════════════
# AI CHAT
# ══════════════════════════════════════════════
def auto_extract_facts(text: str):
    lower = text.lower()
    triggers = ["yaad rakh", "remember", "mera naam", "meri umar", "main rehta", "mujhe pasand", "meri job", "mera kaam"]
    if any(kw in lower for kw in triggers):
        mem.add_fact(text[:250])
        return True
    return False

async def ai_chat(user_msg: str, chat_id: int = None) -> str:
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

# ══════════════════════════════════════════════
# SEND BRIEFING
# ══════════════════════════════════════════════
async def send_briefing(msg_obj):
    tp = tasks.today_pending(); yd = tasks.done_on(yesterday_str())
    hd, hp = habits.today_status(); ag = goals.active()
    td_d = diary.get(today_str()); exp_t = expenses.today_total()
    exp_m = expenses.month_total(); bl = expenses.budget_left()
    today_label = datetime.now().strftime("%A, %d %B %Y")
    txt = f"🌅 *DAILY BRIEFING*\n📅 {today_label}\n\n"
    if yd:
        txt += f"✅ *Kal {len(yd)} kaam kiye:*\n" + "\n".join(f"  • {t['title']}" for t in yd[:5]) + "\n\n"
    if tp:
        txt += f"📋 *Aaj {len(tp)} kaam baaki:*\n"
        for t in tp[:7]: txt += f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}\n"
        txt += "\n"
    else: txt += "🎉 *Koi pending task nahi!*\n\n"
    if hp: txt += f"💪 *{len(hp)} Habits baaki:*\n" + "\n".join(f"  ○ {h['emoji']} {h['name']}" for h in hp[:4]) + "\n\n"
    elif habits.all(): txt += "🎊 *Sab habits complete!*\n\n"
    if ag:
        txt += f"🎯 *Goals ({len(ag)} active):*\n"
        for g in ag[:3]: txt += f"  {'█'*(g['progress']//10)+'░'*(10-g['progress']//10)} {g['title']} {g['progress']}%\n"
        txt += "\n"
    txt += f"💰 *Kharcha:* Aaj ₹{exp_t:.0f} | Mahina ₹{exp_m:.0f}"
    if bl is not None: txt += f" | Baaki ₹{bl:.0f}"
    txt += "\n\n"
    water_t = water.today_total(); water_g = water.goal()
    water_pct = min(100, int(water_t/water_g*100)) if water_g else 0
    txt += f"💧 *Paani:* {water_t}ml / {water_g}ml\n{'💧'*(water_pct//10)+'○'*(10-water_pct//10)} {water_pct}%\n\n"
    due_b = bills.due_soon(3)
    if due_b:
        txt += "⚠️ *Bills Due:*\n" + "\n".join(f"  💳 {b['name']} — ₹{b['amount']:.0f}" for b in due_b) + "\n\n"
    cal_t = calendar.today_events()
    if cal_t:
        txt += "📅 *Aaj Ke Events:*\n" + "\n".join(f"  ✨ {e.get('time','')} {e['title']}" for e in cal_t) + "\n\n"
    if td_d: txt += f"📖 Aaj {len(td_d)} diary entries\n\n"
    txt += "💪 *Aaj ka din badiya banao!* 🚀"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

# ══════════════════════════════════════════════
# SHOW FUNCTIONS
# ══════════════════════════════════════════════
async def show_tasks(msg_obj):
    pending = tasks.pending()
    if not pending:
        await msg_obj.reply_text("🎉 *Koi pending task nahi!*\n`/task Kaam naam` se add karo", parse_mode="Markdown"); return
    txt = f"📋 *TASKS ({len(pending)} pending)*\n\n"
    kb = []
    for t in pending[:12]:
        e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
        txt += f"{e} *#{t['id']}* {t['title']}\n"
        kb.append([InlineKeyboardButton(f"✅ #{t['id']}: {t['title'][:32]}", callback_data=f"done_{t['id']}")])
    kb.append([InlineKeyboardButton("🗑 Done hatao", callback_data="clear_done_tasks"), InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def show_habits(msg_obj):
    done, pending = habits.today_status(); all_h = habits.all()
    if not all_h:
        await msg_obj.reply_text("💪 *Koi habit nahi!*\n`/habit Morning walk 🏃`", parse_mode="Markdown"); return
    txt = "💪 *HABITS — AAJ*\n\n"
    if done: txt += "✅ *Ho Gaye:*\n" + "\n".join(f"  {h['emoji']} {h['name']} 🔥{h['streak']} din" for h in done) + "\n\n"
    kb = []
    if pending:
        txt += "⏳ *Baaki Hain:*\n"
        for h in pending:
            txt += f"  ○ {h['emoji']} {h['name']}\n"
            kb.append([InlineKeyboardButton(f"✅ {h['emoji']} {h['name']}", callback_data=f"habit_{h['id']}")])
    else: txt += "🎊 *Sab complete!* 🏆"
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def show_news(msg_obj, category="India"):
    await msg_obj.reply_text(f"📰 *{category} News* fetch ho rahi hai...", parse_mode="Markdown")
    items = fetch_news(category, max_items=5)
    txt = f"📰 *{category.upper()} NEWS*\n\n"
    for i, item in enumerate(items, 1):
        txt += f"*{i}.* {item['title']}\n"
        if item['desc']: txt += f"_{item['desc'][:90]}..._\n"
        txt += "\n"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=news_kb())

async def show_diary(msg_obj):
    td = diary.get(today_str()); yd_e = diary.get(yesterday_str())
    txt = "📖 *DIARY*\n\n"
    if td: txt += "📅 *Aaj:*\n" + "\n".join(f"  {e['time']} {e['mood']} {e['text']}" for e in td) + "\n\n"
    if yd_e: txt += "📅 *Kal:*\n" + "\n".join(f"  {e['time']} {e['mood']} {e['text']}" for e in yd_e[-3:])
    if not td and not yd_e: txt += "_Koi entry nahi_\n`/diary Aaj kya hua...`"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

async def show_goals(msg_obj):
    ag = goals.active(); cg = goals.completed()
    if not ag and not cg:
        await msg_obj.reply_text("🎯 Koi goals nahi!\n`/goal Kuch achieve karna hai`", parse_mode="Markdown"); return
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
    if cg: txt += f"\n✅ *Completed ({len(cg)}):*\n" + "\n".join(f"  🏆 {g['title']}" for g in cg[-3:])
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def show_notes(msg_obj):
    ns = notes.recent(12)
    if not ns:
        await msg_obj.reply_text("📝 Koi notes nahi.\n`/note Kuch important`", parse_mode="Markdown"); return
    txt = f"📝 *NOTES*\n\n" + "\n".join(f"*#{n['id']}* {n['text']}\n_{n['created'][:10]}_\n" for n in ns)
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

async def show_yesterday(msg_obj):
    yd_label = (date.today()-timedelta(days=1)).strftime("%A, %d %B")
    done = tasks.done_on(yesterday_str()); yd_d = diary.get(yesterday_str())
    txt = f"📅 *KAL KA SUMMARY ({yd_label})*\n\n"
    if done: txt += f"✅ *{len(done)} Tasks Kiye:*\n" + "\n".join(f"  • {t['title']}" for t in done) + "\n\n"
    if yd_d: txt += "📖 *Diary:*\n" + "\n".join(f"  {e['time']} {e['mood']} {e['text']}" for e in yd_d)
    if not done and not yd_d: txt += "_Kal ka koi data nahi mila_"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

# ══════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Dost"
    txt = f"🕌 *Assalamualaikum {name}!*\n\n🧠 Smart Memory | 📋 Tasks | 📖 Diary | 💪 Habits\n💰 Kharcha | 🎯 Goals | 📰 News | 💧 Water\n💳 Bills | 📅 Calendar | ⏰ Reminders\n\n🔐 Secret Code: `Rk1996`\n📥 Offline Capture: ACTIVE\n\n✅ *100% FREE — Seedha type karo!* 👇"
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE): await send_briefing(update.message)

async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("📋 `/task Kaam naam`\n`/task Important high`", parse_mode="Markdown"); return
    args = " ".join(ctx.args); priority = "medium"
    if args.endswith(" high"): priority="high"; args=args[:-5].strip()
    elif args.endswith(" low"): priority="low"; args=args[:-4].strip()
    t = tasks.add(args, priority=priority)
    e = "🔴" if priority=="high" else "🟡" if priority=="medium" else "🟢"
    await update.message.reply_text(f"✅ *Task Add!*\n{e} {t['title']}\nPriority: *{priority.upper()}*", parse_mode="Markdown")
    activity_logger.log_activity("task_added", update.effective_user.id, update.effective_user.first_name, args, "completed", True)

async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("`/done 3`", parse_mode="Markdown"); return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t:
            await update.message.reply_text(f"🎉 *Complete!*\n✅ {t['title']}\n💪 Wah bhai!", parse_mode="Markdown")
            activity_logger.log_activity("task_completed", update.effective_user.id, update.effective_user.first_name, t['title'], "completed", True)
        else: await update.message.reply_text("❌ Task nahi mila ya pehle done hai.")
    except: await update.message.reply_text("❌ `/done 3` format", parse_mode="Markdown")

async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("`/deltask 3`", parse_mode="Markdown"); return
    try:
        ok = tasks.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 *Task Delete!*" if ok else "❌ Task nahi mila.", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/deltask 3`", parse_mode="Markdown")

async def cmd_diary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("📖 `/diary Aaj bahut productive tha!`", parse_mode="Markdown"); return
    content = " ".join(ctx.args); diary.add(content)
    await update.message.reply_text(f"📖 *Diary Mein Likh Diya!*\n\n_{content}_\n🕐 {now_str()}", parse_mode="Markdown")

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("💪 `/habit Morning walk 🏃`", parse_mode="Markdown"); return
    name = " ".join(ctx.args); emoji = "✅"
    for em in ["💪","🏃","📚","💧","🧘","🌅","🏋","✍️","🎯","🙏","🥗","😴","🚶"]:
        if em in name: emoji = em; break
    h = habits.add(name, emoji)
    await update.message.reply_text(f"💪 *Habit Add!*\n{h['emoji']} {h['name']}\n`/hdone {h['id']}` se mark karo!", parse_mode="Markdown")

async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        txt = "💪 *Kaunsi habit?*\n" + "\n".join(f"`/hdone {h['id']}` — {h['emoji']} {h['name']}" for h in pending)
        if not pending: txt = "🎊 Aaj sab complete!"
        await update.message.reply_text(txt, parse_mode="Markdown"); return
    try:
        hid = int(ctx.args[0]); ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"]==hid), None)
        if ok and h:
            st = f"🔥 *{streak} din streak!*" if streak>1 else "✨ Pehli baar!"
            await update.message.reply_text(f"💪 *Done!*\n{h['emoji']} {h['name']}\n{st}", parse_mode="Markdown")
        else: await update.message.reply_text("✅ Aaj pehle hi mark hai!")
    except: await update.message.reply_text("❌ `/hdone 1`", parse_mode="Markdown")

async def cmd_delhabit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        all_h = habits.all(); txt = "🗑 *Kaunsi?*\n" + "\n".join(f"`/delhabit {h['id']}` — {h['emoji']} {h['name']}" for h in all_h)
        await update.message.reply_text(txt, parse_mode="Markdown"); return
    try: habits.delete(int(ctx.args[0])); await update.message.reply_text("🗑 *Habit Delete!*", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/delhabit 1`", parse_mode="Markdown")

async def cmd_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("📝 `/note Grocery: Doodh, Bread`", parse_mode="Markdown"); return
    n = notes.add(" ".join(ctx.args))
    await update.message.reply_text(f"📝 *Note #{n['id']} Save!*\n{n['text']}", parse_mode="Markdown")

async def cmd_delnote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("🗑 `/delnote 3`", parse_mode="Markdown"); return
    try: notes.delete(int(ctx.args[0])); await update.message.reply_text("🗑 *Note delete!*", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/delnote 3`", parse_mode="Markdown")

async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("💰 `/kharcha 50 Chai`", parse_mode="Markdown"); return
    try:
        amount = float(ctx.args[0]); rest = ctx.args[1:]
        cats = ["food","travel","shopping","bills","health","entertainment","education","general"]
        category = "general"
        if rest and rest[-1].lower() in cats: category=rest[-1].lower(); desc=" ".join(rest[:-1]) or "Kharcha"
        else: desc=" ".join(rest) or "Kharcha"
        expenses.add(amount, desc, category)
        bl = expenses.budget_left(); bline = f"\n⚠️ Budget baaki: ₹{bl:.0f}" if bl is not None else ""
        await update.message.reply_text(f"💰 *₹{amount:.0f} — {desc}*\nAaj total: *₹{expenses.today_total():.0f}*{bline}", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/kharcha 100 Khana`", parse_mode="Markdown")

async def cmd_kharcha_aaj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    items = expenses.today_list()
    if not items: await update.message.reply_text("💰 Aaj koi kharcha nahi.", parse_mode="Markdown"); return
    txt = "💰 *AAJ KA KHARCHA*\n\n" + "\n".join(f"  ₹{e['amount']:.0f} — {e['desc']} _{e['time']}_" for e in items)
    txt += f"\n\n💵 *Total: ₹{expenses.today_total():.0f}*"
    bl = expenses.budget_left()
    if bl is not None: txt += f"\n💳 *Budget Baaki: ₹{bl:.0f}*"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("💳 `/budget 5000`", parse_mode="Markdown"); return
    try:
        b = float(ctx.args[0]); expenses.set_budget(b)
        await update.message.reply_text(f"💳 *Budget Set: ₹{b:.0f}*", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/budget 5000`", parse_mode="Markdown")

async def cmd_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("🎯 `/goal Weight lose 10kg`", parse_mode="Markdown"); return
    title = " ".join(ctx.args); deadline = None
    parts = title.rsplit(" ", 1)
    if len(parts)==2 and len(parts[1])==10 and parts[1].count("-")==2: deadline=parts[1]; title=parts[0]
    g = goals.add(title, deadline)
    await update.message.reply_text(f"🎯 *Goal Add!*\n✨ {g['title']}" + (f"\n📅 {deadline}" if deadline else ""), parse_mode="Markdown")

async def cmd_gprogress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        gid=int(ctx.args[0]); pct=int(ctx.args[1])
        g = goals.update_progress(gid, pct)
        if g:
            bar = "█"*(pct//10) + "░"*(10-pct//10)
            msg = f"🎯 *Progress!*\n{g['title']}\n{bar} *{pct}%*"
            if pct==100: msg += "\n🏆 *GOAL COMPLETE!* 🎉"
            await update.message.reply_text(msg, parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/gprogress 1 75`", parse_mode="Markdown")

async def cmd_remember(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("🧠 `/remember Mera birthday 15 August hai`", parse_mode="Markdown"); return
    fact = " ".join(ctx.args); mem.add_fact(fact)
    activity_logger.log_activity("memory_saved", update.effective_user.id, update.effective_user.first_name, fact, "completed", True)
    await update.message.reply_text(f"🧠 *Yaad Kar Liya!* ✅\n_{fact}_\n_Chat clear bhi ho toh safe_ 🔒", parse_mode="Markdown")

async def cmd_recall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    facts = mem.data["facts"]
    if not facts: await update.message.reply_text("🧠 Kuch yaad nahi.\n`/remember Koi baat`", parse_mode="Markdown"); return
    txt = f"🧠 *YAADDASHT ({len(facts)})*\n\n" + "\n".join(f"  📌 {f['f']}\n  _{f['d']}_" for f in facts[-15:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Haan Clear", callback_data="confirm_clear_chat"), InlineKeyboardButton("❌ Nahi", callback_data="menu")]])
    await update.message.reply_text(f"🧹 *Chat Clear Karna Hai?*\n📊 {chat_hist.count()} messages\n✅ Memory safe rahegi!", parse_mode="Markdown", reply_markup=kb)

async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📰 *Kaunsi news?*", parse_mode="Markdown", reply_markup=news_kb())

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = """🤖 *COMMANDS v4.5*

📋 */task Kaam* | */done 3* | */deltask 3*
📋 */alltasks* | */completed*
🔐 */verify Rk1996* | */taskhistory Rk1996*
📖 */diary Text* | 🧠 */remember Fact* | */recall*
💪 */habit Name* | */hdone 1* | */delhabit 1*
💰 */kharcha 100 Food* | */budget 5000*
🎯 */goal Target* | */gprogress 1 50*
⏰ */remind 30m Chai* | */reminders* | */delremind 3*
💧 */water* | */waterstatus* | */watergoal 2500*
💳 */bill Name 199 5* | */bills* | */billpaid 3*
📅 */cal YYYY-MM-DD Event* | */calendar*
📊 */weekly* | */yesterday* | 📰 */news*
🧹 */clear* | */nuke* | 🔐 */offlinemsgs Rk1996*"""
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

# ══════════════════════════════════════════════
# NEW COMMANDS
# ══════════════════════════════════════════════
async def cmd_all_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    all_t = tasks.all_tasks()
    if not all_t: await update.message.reply_text("📋 Koi task nahi!", parse_mode="Markdown"); return
    txt = f"📋 *SAARE TASKS ({len(all_t)})*\n\n"
    pending=[t for t in all_t if not t["done"]]
    if pending:
        txt += "*⏳ PENDING:*\n"
        for t in pending: txt += f"{'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} *#{t['id']}* {t['title']}\n"
        txt += "\n"
    completed=[t for t in all_t if t["done"]]
    if completed:
        txt += "*✅ COMPLETED:*\n"
        for t in completed[-10:]: txt += f"✓ *#{t['id']}* {t['title']} _{t.get('completed_date','')}_\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    completed = tasks.completed_tasks()
    if not completed: await update.message.reply_text("✅ Koi completed task nahi!", parse_mode="Markdown"); return
    txt = f"✅ *COMPLETED ({len(completed)})*\n\n"
    for t in completed[-15:]: txt += f"✓ *#{t['id']}* {t['title']}\n  📅 {t.get('completed_date','')}\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_task_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not verify_secret_code(ctx.args[0]): await update.message.reply_text("❌ Galat code! `/taskhistory Rk1996`", parse_mode="Markdown"); return
    ch = tasks.get_completed_history()
    txt = f"🔓 *TASK HISTORY ({len(ch)})*\n\n" + "\n".join(f"✓ {t.get('title','')} - {t.get('completed_date','')}" for t in ch[-20:])
    if not ch: txt = "🔓 *Koi history nahi!*"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_offline_messages(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not verify_secret_code(ctx.args[0]): await update.message.reply_text("❌ Galat code! `/offlinemsgs Rk1996`", parse_mode="Markdown"); return
    pending = offline_queue.get_pending_messages()
    if not pending: await update.message.reply_text("📥 Koi offline message nahi!", parse_mode="Markdown"); return
    txt = f"🔓 *OFFLINE ({len(pending)})*\n\n"
    for i, m in enumerate(pending[:10]): txt += f"*{i+1}.* {m['username']} ({m['timestamp'][:16]})\n   {m['message'][:100]}...\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_verify_secret(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not verify_secret_code(ctx.args[0]): await update.message.reply_text("❌ Galat code!", parse_mode="Markdown"); return
    await update.message.reply_text("✅ *Verified!*\nAb `/taskhistory`, `/offlinemsgs`, `/alllogs`, `/reminderlog` use karo.", parse_mode="Markdown")

async def cmd_reminder_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not verify_secret_code(ctx.args[0]): await update.message.reply_text("❌ Galat code!", parse_mode="Markdown"); return
    history = reminders.get_reminders_history()
    if not history: await update.message.reply_text("📋 Koi reminder history nahi!", parse_mode="Markdown"); return
    txt = f"🔓 *REMINDER HISTORY ({len(history)})*\n\n"
    for r in history[:15]: txt += f"🔔 #{r['reminder_id']} — {r['text']}\n   ⏰ {r['fired_at'][:16]}\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_all_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not verify_secret_code(ctx.args[0]): await update.message.reply_text("❌ Galat code!", parse_mode="Markdown"); return
    acts = activity_logger.data["activities"][-50:]
    if not acts: await update.message.reply_text("📋 Koi log nahi!", parse_mode="Markdown"); return
    txt = f"🔓 *LOGS ({len(acts)} recent)*\n\n"
    for a in acts[-20:]: txt += f"• {a['timestamp'][:16]} | {a['type']}: {a['content'][:80]}...\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

# ══════════════════════════════════════════════
# REMINDER COMMANDS
# ══════════════════════════════════════════════
def parse_reminder_time(args: list):
    if not args: return None, None, None
    time_arg = args[0].lower(); rest = args[1:]; repeat = "once"
    if rest and rest[-1].lower() == "daily": repeat="daily"; rest=rest[:-1]
    elif rest and rest[-1].lower() == "weekly": repeat="weekly"; rest=rest[:-1]
    text = " ".join(rest) if rest else "⏰ Reminder!"; now = datetime.now()
    if time_arg.endswith("m") and time_arg[:-1].isdigit(): return (now+timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M"), repeat, text
    if time_arg.endswith("h") and time_arg[:-1].isdigit(): return (now+timedelta(hours=int(time_arg[:-1]))).strftime("%H:%M"), repeat, text
    if ":" in time_arg:
        parts = time_arg.split(":")
        if len(parts)==2 and parts[0].isdigit() and parts[1].isdigit():
            h,m = int(parts[0]), int(parts[1])
            if 0<=h<=23 and 0<=m<=59: return f"{h:02d}:{m:02d}", repeat, text
    return None, None, None

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not ctx.args: await update.message.reply_text("⏰ `/remind 30m Chai` | `/remind 15:30 Doctor` | `/remind 8:00 Uthna daily`", parse_mode="Markdown"); return
    time_str, repeat, text = parse_reminder_time(ctx.args)
    if not time_str: await update.message.reply_text("❌ Format galat!", parse_mode="Markdown"); return
    r = reminders.add(chat_id, text, time_str, repeat)
    rl = {"once":"Ek baar","daily":"Roz 🔁","weekly":"Har hafte 📅"}.get(repeat, repeat)
    activity_logger.log_activity("reminder_set", update.effective_user.id, update.effective_user.first_name, f"{text} at {time_str}", "completed", True)
    await update.message.reply_text(f"✅ *Reminder Set!*\n⏰ *{time_str}*\n📝 *{text}*\n🔁 *{rl}*\n🆔 `{r['id']}`", parse_mode="Markdown")

async def cmd_reminders_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    all_r = reminders.all_active()
    if not all_r: await update.message.reply_text("⏰ Koi reminder nahi!\n`/remind 30m Chai`", parse_mode="Markdown"); return
    txt = f"⏰ *REMINDERS ({len(all_r)})*\n\n"
    kb = []
    for r in all_r:
        ri = "🔁" if r["repeat"]=="daily" else "📅" if r["repeat"]=="weekly" else "1️⃣"
        s = "✅" if r["fired_today"] else "⏳"
        txt += f"*#{r['id']}* {ri} `{r['time']}` — {r['text']} _{s}_\n\n"
        kb.append([InlineKeyboardButton(f"🗑 #{r['id']}: {r['text'][:30]}", callback_data=f"delremind_{r['id']}")])
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def cmd_delremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("🗑 `/delremind 3`", parse_mode="Markdown"); return
    try:
        ok = reminders.delete(int(ctx.args[0]))
        await update.message.reply_text(f"🗑 *Delete!*" if ok else "❌ Nahi mila", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/delremind 3`", parse_mode="Markdown")

# ══════════════════════════════════════════════
# WATER COMMANDS
# ══════════════════════════════════════════════
async def cmd_water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ml = 250
    if ctx.args:
        try: ml = int(ctx.args[0])
        except: pass
    water.add(ml); total=water.today_total(); goal=water.goal()
    pct = min(100, int(total/goal*100))
    bar = "💧"*(pct//10) + "○"*(10-pct//10)
    msg = f"💧 *+{ml}ml!*\nAaj: *{total}ml / {goal}ml*\n{bar} *{pct}%*"
    if total>=goal: msg += "\n🎉 *Goal pura!* 🏆"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💧 +250ml", callback_data="water_250"), InlineKeyboardButton("💧 +500ml", callback_data="water_500")], [InlineKeyboardButton("🏠 Menu", callback_data="menu")]])
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)

async def cmd_water_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    total=water.today_total(); goal=water.goal()
    pct=min(100,int(total/goal*100)) if goal else 0
    bar="💧"*(pct//10)+"○"*(10-pct//10)
    txt=f"💧 *WATER*\n🎯 Goal: *{goal}ml*\n✅ Aaj: *{total}ml*\n{bar} *{pct}%*"
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("💧 +250ml",callback_data="water_250"),InlineKeyboardButton("💧 +500ml",callback_data="water_500")],[InlineKeyboardButton("🏠 Menu",callback_data="menu")]])
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb)

async def cmd_water_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text(f"💧 Current: *{water.goal()}ml*\n`/watergoal 2500`", parse_mode="Markdown"); return
    try:
        ml=int(ctx.args[0]); water.set_goal(ml)
        await update.message.reply_text(f"✅ *Goal: {ml}ml*", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/watergoal 2000`", parse_mode="Markdown")

# ══════════════════════════════════════════════
# BILL COMMANDS
# ══════════════════════════════════════════════
async def cmd_bill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args)<3: await update.message.reply_text("💳 `/bill Netflix 199 5`", parse_mode="Markdown"); return
    try:
        name=ctx.args[0]; amount=float(ctx.args[1]); due_day=int(ctx.args[2])
        bill_type="emi" if "emi" in name.lower() else "subscription" if name.lower() in ["netflix","amazon","hotstar","spotify"] else "bill"
        if not(1<=due_day<=31): raise ValueError
        b=bills.add(name,amount,due_day,bill_type)
        icons={"emi":"🏦","bill":"📄","subscription":"📺"}
        await update.message.reply_text(f"✅ *{icons.get(bill_type,'💳')} {bill_type.upper()} Add!*\n📌 *{name}*\n💰 ₹{amount:.0f}\n📅 Har {due_day} tarikh\n_ID #{b['id']}_", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/bill Netflix 199 5`", parse_mode="Markdown")

async def cmd_bills_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    all_b=bills.all_active()
    if not all_b: await update.message.reply_text("💳 Koi bill nahi!", parse_mode="Markdown"); return
    txt=f"💳 *BILLS ({len(all_b)})*\n\n"; kb=[]
    for b in all_b:
        paid=bills.is_paid_this_month(b["id"]); status="✅" if paid else "⏳"
        txt+=f"{status} *#{b['id']}* {b['name']} — ₹{b['amount']:.0f} | {b['due_day']} tarikh\n"
        if not paid: kb.append([InlineKeyboardButton(f"✅ Paid: {b['name'][:25]}", callback_data=f"billpaid_{b['id']}")])
    txt+=f"\n💰 Monthly: ₹{bills.month_total():.0f}"
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def cmd_bill_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("✅ `/billpaid 3`", parse_mode="Markdown"); return
    try: await update.message.reply_text("✅ *Paid!*" if bills.mark_paid(int(ctx.args[0])) else "❌ Nahi mila", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/billpaid 3`", parse_mode="Markdown")

async def cmd_del_bill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("`/delbill 3`", parse_mode="Markdown"); return
    try: await update.message.reply_text("🗑 *Delete!*" if bills.delete(int(ctx.args[0])) else "❌ Nahi mila", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/delbill 3`", parse_mode="Markdown")

# ══════════════════════════════════════════════
# CALENDAR COMMANDS
# ══════════════════════════════════════════════
async def cmd_cal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`\n`/cal 10-05-2026 Birthday 14:00`", parse_mode="Markdown"); return
    args_str=" ".join(ctx.args); date_str=None; title=args_str; event_time=""
    m=_re.match(r'^(\d{4}-\d{2}-\d{2})\s+(.*)', args_str)
    if m: date_str=m.group(1); title=m.group(2)
    if not date_str:
        m=_re.match(r'^(\d{2})-(\d{2})-(\d{4})\s+(.*)', args_str)
        if m: date_str=f"{m.group(3)}-{m.group(2)}-{m.group(1)}"; title=m.group(4)
    if not date_str:
        if args_str.lower().startswith("aaj "): date_str=today_str(); title=args_str[4:].strip()
        elif args_str.lower().startswith("kal "): date_str=(date.today()+timedelta(days=1)).isoformat(); title=args_str[4:].strip()
    if not date_str: await update.message.reply_text("❌ Date galat!", parse_mode="Markdown"); return
    t_match=_re.search(r'(\d{1,2}:\d{2})', title)
    if t_match: event_time=t_match.group(1); title=title.replace(event_time,"").strip()
    try: date.fromisoformat(date_str)
    except: await update.message.reply_text("❌ Invalid date!", parse_mode="Markdown"); return
    e=calendar.add(title, date_str, event_time)
    await update.message.reply_text(f"📅 *Event Add!*\n✨ *{title}*\n📆 {date_str}"+(f" | ⏰ {event_time}" if event_time else "")+f"\n_ID #{e['id']}_", parse_mode="Markdown")

async def cmd_cal_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    upcoming=calendar.upcoming(30)
    if not upcoming: await update.message.reply_text("📅 Koi event nahi!", parse_mode="Markdown"); return
    txt="📅 *CALENDAR*\n\n"; kb=[]
    for e in upcoming:
        dl="🔴 Aaj" if e["date"]==today_str() else f"📆 {e['date'][5:]}"
        ts=f" ⏰{e['time']}" if e.get("time") else ""
        txt+=f"{dl}{ts} — *{e['title']}*\n"
        kb.append([InlineKeyboardButton(f"🗑 {e['title'][:35]}", callback_data=f"delcal_{e['id']}")])
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def cmd_del_cal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("`/delcal 3`", parse_mode="Markdown"); return
    try: await update.message.reply_text("🗑 *Delete!*" if calendar.delete(int(ctx.args[0])) else "❌ Nahi mila", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/delcal 3`", parse_mode="Markdown")

# ══════════════════════════════════════════════
# WEEKLY REPORT
# ══════════════════════════════════════════════
async def cmd_weekly_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 *Report ban rahi hai...*", parse_mode="Markdown")
    today_d=date.today(); week_ago=today_d-timedelta(days=6)
    txt=f"📊 *WEEKLY REPORT*\n_{week_ago.strftime('%d %b')} — {today_d.strftime('%d %b %Y')}_\n{'━'*22}\n\n"
    all_td=[tasks.done_on((today_d-timedelta(days=i)).isoformat()) for i in range(7)]
    flat=[t for sub in all_td for t in sub]
    txt+=f"📋 *TASKS*\n  ✅ {len(flat)} complete\n  ⏳ {len(tasks.pending())} pending\n\n"
    week_exp=sum(e["amount"] for e in expenses.data["list"] if e["date"]>=week_ago.isoformat())
    txt+=f"💰 *KHARCHA*\n  Hafte: ₹{week_exp:.0f}\n  Mahine: ₹{expenses.month_total():.0f}\n\n"
    ws=water.week_summary()
    txt+=f"💧 *PAANI*: Avg {int(sum(ws.values())/max(1,len(ws)))}ml/day\n\n"
    txt+=f"{'━'*22}\n💪 *Agli hafte aur badiya!* 🚀"
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

# ══════════════════════════════════════════════
# DELETE & NUKE
# ══════════════════════════════════════════════
async def delete_telegram_messages(bot, tracked_ids: list) -> tuple:
    deleted=0; failed=0
    for i, entry in enumerate(tracked_ids):
        try:
            await bot.delete_message(chat_id=entry["chat_id"], message_id=entry["msg_id"])
            deleted+=1
            if i%20==19: await asyncio.sleep(0.5)
        except Exception: failed+=1
    return deleted, failed

async def cmd_nuke(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_hist.track_msg(update.effective_chat.id, update.message.message_id)
    tracked=chat_hist.get_tracked_ids(); count=chat_hist.count()
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("💣 Haan! Sab Saaf", callback_data="confirm_nuke"), InlineKeyboardButton("❌ Nahi", callback_data="menu")]])
    sent=await update.message.reply_text(f"💣 *NUKE*\n🗑 {len(tracked)} messages\n🧹 {count} history\n✅ Memory safe", parse_mode="Markdown", reply_markup=kb)
    chat_hist.track_msg(update.effective_chat.id, sent.message_id)

# ══════════════════════════════════════════════
# CALLBACK HANDLER
# ══════════════════════════════════════════════
async def callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); d=q.data
    if d=="menu": await q.message.reply_text("🏠 *Menu*", parse_mode="Markdown", reply_markup=main_kb())
    elif d=="briefing": await send_briefing(q.message)
    elif d=="tasks": await show_tasks(q.message)
    elif d=="habits": await show_habits(q.message)
    elif d=="diary": await show_diary(q.message)
    elif d=="goals": await show_goals(q.message)
    elif d=="notes": await show_notes(q.message)
    elif d=="yesterday": await show_yesterday(q.message)
    elif d=="news_menu": await q.message.reply_text("📰 *News?*", parse_mode="Markdown", reply_markup=news_kb())
    elif d.startswith("news_"): await show_news(q.message, d.split("_",1)[1])
    elif d=="memory":
        facts=mem.data["facts"]
        txt=f"🧠 *YAADDASHT ({len(facts)})*\n\n"+("\n".join(f"  📌 {f['f']}" for f in facts[-12:]) if facts else "_Kuch nahi_")
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d=="expenses":
        items=expenses.today_list()
        txt=f"💰 *KHARCHA*\nAaj: ₹{expenses.today_total():.0f} | Mahina: ₹{expenses.month_total():.0f}\n"
        bl=expenses.budget_left()
        if bl is not None: txt+=f"Budget baaki: ₹{bl:.0f}\n"
        txt+="\n"+("\n".join(f"  ₹{e['amount']:.0f} {e['desc']}" for e in items[-8:]) if items else "_Koi nahi_")
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d=="clear_chat":
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Haan", callback_data="confirm_clear_chat"), InlineKeyboardButton("❌ Nahi", callback_data="menu")]])
        await q.message.reply_text(f"🧹 *Clear?*\n📊 {chat_hist.count()} messages\n✅ Memory safe!", parse_mode="Markdown", reply_markup=kb)
    elif d=="confirm_clear_chat":
        count=chat_hist.clear()
        await q.message.reply_text(f"🧹 *Clear!*\n🗑 {count} messages\n🔒 Memory safe!", parse_mode="Markdown", reply_markup=main_kb())
    elif d=="water_status": await cmd_water_status(update, None)
    elif d.startswith("water_") and d.split("_")[1].isdigit():
        ml=int(d.split("_")[1]); water.add(ml)
        total=water.today_total(); goal=water.goal()
        pct=min(100,int(total/goal*100)) if goal else 0
        bar="💧"*(pct//10)+"○"*(10-pct//10)
        msg=f"💧 *+{ml}ml!*\nAaj: *{total}ml / {goal}ml*\n{bar} {pct}%"
        if total>=goal: msg+="\n🎉 *Goal pura!* 🏆"
        await q.message.reply_text(msg, parse_mode="Markdown")
    elif d=="bills_menu":
        all_b=bills.all_active()
        if not all_b: await q.message.reply_text("💳 Koi bill nahi!", parse_mode="Markdown"); return
        txt=f"💳 *BILLS ({len(all_b)})*\n\n"; kb2=[]
        for b in all_b:
            paid=bills.is_paid_this_month(b["id"]); status="✅" if paid else "⏳"
            txt+=f"{status} *{b['name']}* — ₹{b['amount']:.0f} | {b['due_day']} tarikh\n"
            if not paid: kb2.append([InlineKeyboardButton(f"✅ Paid: {b['name'][:25]}", callback_data=f"billpaid_{b['id']}")])
        kb2.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
        await q.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb2))
    elif d.startswith("billpaid_"):
        bid=int(d.split("_")[1]); bills.mark_paid(bid)
        await q.message.reply_text(f"✅ *Bill #{bid} Paid!*", parse_mode="Markdown")
    elif d=="cal_menu":
        upcoming=calendar.upcoming(30)
        if not upcoming: await q.message.reply_text("📅 Koi event nahi!", parse_mode="Markdown"); return
        txt="📅 *EVENTS*\n\n"; kb3=[]
        for e in upcoming:
            dl="🔴 Aaj" if e["date"]==today_str() else f"📆 {e['date'][5:]}"
            ts=f" ⏰{e['time']}" if e.get("time") else ""
            txt+=f"{dl}{ts} — *{e['title']}*\n"
            kb3.append([InlineKeyboardButton(f"🗑 {e['title'][:35]}", callback_data=f"delcal_{e['id']}")])
        kb3.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
        await q.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb3))
    elif d.startswith("delcal_"): await q.message.reply_text("🗑 *Delete!*" if calendar.delete(int(d.split("_")[1])) else "❌ Nahi mila", parse_mode="Markdown")
    elif d=="weekly_report":
        class _Fake: def __init__(self, msg): self.message=msg; self.effective_chat=msg
        await cmd_weekly_report(_Fake(q.message), None)
    elif d=="clear_done_tasks":
        count=tasks.clear_done()
        await q.message.reply_text(f"🗑 *{count} Done Tasks Delete!*", parse_mode="Markdown")
    elif d=="motivate":
        reply=await ai_chat("Mujhe powerful motivation de Hindi mein. 3-4 line. Real, raw.")
        await q.message.reply_text(f"💡 *Motivation:*\n\n{reply}", parse_mode="Markdown")
    elif d.startswith("done_"):
        t=tasks.complete(int(d.split("_")[1]))
        await q.message.reply_text(f"🎉 *Complete!*\n✅ {t['title']}" if t else "❌ Nahi mila", parse_mode="Markdown")
    elif d.startswith("habit_"):
        hid=int(d.split("_")[1]); ok,streak=habits.log(hid)
        h=next((x for x in habits.all() if x["id"]==hid), None)
        if ok and h: await q.message.reply_text(f"💪 *Done!*\n{h['emoji']} {h['name']}\n{'🔥 '+str(streak)+' din!' if streak>1 else '🌟 Pehli baar!'}", parse_mode="Markdown")
        else: await q.message.reply_text("✅ Pehle hi mark hai!")
    elif d.startswith("goal_"): await q.message.reply_text(f"📊 `/gprogress {d.split('_')[1]} 50`", parse_mode="Markdown")
    elif d.startswith("remind_done_"):
        rid=int(d.split("_")[2]); reminders.mark_fired(rid)
        await q.message.reply_text("✅ *Done!*", parse_mode="Markdown")
        try: await q.message.delete()
        except: pass
    elif d.startswith("remind_snooze_"):
        rid=int(d.split("_")[2])
        st=(datetime.now()+timedelta(minutes=10)).strftime("%H:%M")
        rl=[r for r in reminders.get_all() if r["id"]==rid]
        if rl: r=rl[0]; reminders.add(q.message.chat_id, r["text"], st, "once"); reminders.mark_fired(rid)
        await q.message.reply_text(f"😴 *Snooze! 10 min baad...*\n⏰ {st}", parse_mode="Markdown")
        try: await q.message.delete()
        except: pass
    elif d.startswith("delremind_"):
        ok=reminders.delete(int(d.split("_")[1]))
        await q.message.reply_text("🗑 *Delete!*" if ok else "❌ Nahi mila", parse_mode="Markdown")
    elif d=="confirm_nuke":
        tracked=chat_hist.get_tracked_ids(); chat_id=q.message.chat_id
        sm=await q.message.reply_text("🧹 *Saaf ho rahi hai...*", parse_mode="Markdown")
        deleted,failed=await delete_telegram_messages(q.get_bot(), tracked)
        hist_count=chat_hist.clear(); chat_hist.clear_msg_ids()
        try: await sm.delete()
        except: pass
        try: await q.message.delete()
        except: pass
        note=f"_(⚠️ {failed} purane messages nahi hue)_\n" if failed else ""
        await q.get_bot().send_message(chat_id=chat_id, text=f"{'━'*22}\n🧹 *CHAT SAAF!*\n{'━'*22}\n\n🗑 {deleted} delete\n🔒 Memory safe\n{note}_Fresh start!_ ✨", parse_mode="Markdown", reply_markup=main_kb())

# ══════════════════════════════════════════════
# MESSAGE HANDLER
# ══════════════════════════════════════════════
async def handle_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user=update.effective_user; chat_id=update.effective_chat.id; msg=update.message.text
    chat_hist.track_msg(chat_id, update.message.message_id)
    activity_logger.log_activity("message", user.id, user.username or user.first_name, msg, "received")
    imp_kw=["yaad rakh","remember","task","reminder","alarm","important"]
    if any(k in msg.lower() for k in imp_kw): activity_logger.log_activity("important", user.id, user.username or user.first_name, msg, "protected", True)
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        reply=await ai_chat(msg, chat_id=chat_id)
        if "⚠️ *AI Abhi Offline Hai!*" in reply:
            offline_queue.add_message(user.id, chat_id, user.username or user.first_name, msg)
            activity_logger.log_activity("offline", user.id, user.username or user.first_name, msg, "queued", True)
        try: sent=await update.message.reply_text(reply, parse_mode="Markdown")
        except: sent=await update.message.reply_text(reply)
        chat_hist.track_msg(chat_id, sent.message_id)
    except Exception as e:
        log.error(f"Error: {e}")
        await update.message.reply_text("❌ *Error! Offline queue mein save kiya.*", parse_mode="Markdown")
        offline_queue.add_message(user.id, chat_id, user.username or user.first_name, msg)

# ══════════════════════════════════════════════
# BACKGROUND JOBS
# ══════════════════════════════════════════════
async def reminder_job(context):
    now_time=datetime.now().strftime("%H:%M")
    if now_time=="00:00": reminders.reset_daily()
    due=reminders.due_now()
    for r in due:
        try:
            rn=""
            if r["repeat"]=="daily": rn="\n🔁 _Kal bhi!_"
            elif r["repeat"]=="weekly": rn="\n📅 _Agli baar hafte baad!_"
            kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ho Gaya!", callback_data=f"remind_done_{r['id']}"), InlineKeyboardButton("⏰ Snooze", callback_data=f"remind_snooze_{r['id']}")]])
            await context.bot.send_message(chat_id=r["chat_id"], text=f"🚨🔔 *ALARM!*\n{'═'*22}\n⏰ *{r['time']}*\n{'═'*22}\n📢 *{r['text'].upper()}*\n{rn}", parse_mode="Markdown", disable_notification=False, reply_markup=kb)
            await asyncio.sleep(2)
            await context.bot.send_message(chat_id=r["chat_id"], text=f"🔔 *REMINDER:* {r['text']}", parse_mode="Markdown", disable_notification=False)
            reminders.mark_fired(r["id"])
            activity_logger.log_activity("reminder_fired", r["chat_id"], "system", f"#{r['id']}: {r['text']}", "fired", True)
        except Exception as e: log.error(f"Reminder error #{r['id']}: {e}")

async def bill_due_alert_job(context):
    if datetime.now().strftime("%H:%M")!="09:00": return
    due=bills.due_soon(3)
    if not due: return
    cids=set(r["chat_id"] for r in reminders.all_active())
    if not cids: return
    txt="💳 *BILL DUE*\n\n"+"\n".join(f"⚠️ *{b['name']}* — ₹{b['amount']:.0f}\n   📅 {b['due_date']}" for b in due)
    for cid in cids:
        try: await context.bot.send_message(chat_id=cid, text=txt, parse_mode="Markdown")
        except: pass

async def water_reminder_job(context):
    nh=datetime.now().hour
    if not(8<=nh<=22) or nh%2!=0: return
    cids=set(r["chat_id"] for r in reminders.all_active())
    if not cids: return
    total=water.today_total(); goal=water.goal()
    if total>=goal: return
    rem=goal-total; pct=int(total/goal*100) if goal else 0
    txt=f"💧 *Paani Peena Yaad Hai?*\nAaj: {total}ml / {goal}ml ({pct}%)\nAur {rem}ml baaki!\n`/water` se log karo"
    for cid in cids:
        try: await context.bot.send_message(chat_id=cid, text=txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💧 +250ml", callback_data="water_250"), InlineKeyboardButton("💧 +500ml", callback_data="water_500")]]))
        except: pass

async def process_offline_queue(context):
    pending=offline_queue.get_pending_messages()
    if not pending: return
    for i, msg in enumerate(pending):
        try:
            reply=await ai_chat(msg["message"], chat_id=msg["chat_id"])
            await context.bot.send_message(chat_id=msg["chat_id"], text=f"📥 *Offline Processed!*\n\n_{msg['message'][:100]}_\n\n💬 {reply[:500]}", parse_mode="Markdown")
            offline_queue.mark_processed(i)
        except: pass
    offline_queue.clear_processed()

# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
def main():
    log.info("🤖 Bot v4.5 Starting...")
    log.info(f"📡 Models: {', '.join(GEMINI_MODELS)}")
    log.info("🔐 Secret Code: ACTIVE | 📥 Offline Queue: ACTIVE")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Commands
    for cmd, handler in [
        ("start", cmd_start), ("help", cmd_help), ("briefing", cmd_briefing),
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("diary", cmd_diary), ("remember", cmd_remember), ("recall", cmd_recall),
        ("note", cmd_note), ("delnote", cmd_delnote),
        ("habit", cmd_habit), ("hdone", cmd_hdone), ("delhabit", cmd_delhabit),
        ("kharcha", cmd_kharcha), ("kharcha_aaj", cmd_kharcha_aaj), ("budget", cmd_budget),
        ("goal", cmd_goal), ("gprogress", cmd_gprogress),
        ("news", cmd_news), ("clear", cmd_clear), ("nuke", cmd_nuke),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list), ("delremind", cmd_delremind),
        ("yesterday", lambda u,c: show_yesterday(u.message)),
        ("water", cmd_water), ("waterstatus", cmd_water_status), ("watergoal", cmd_water_goal),
        ("bill", cmd_bill), ("bills", cmd_bills_list), ("billpaid", cmd_bill_paid), ("delbill", cmd_del_bill),
        ("cal", cmd_cal), ("calendar", cmd_cal_list), ("delcal", cmd_del_cal),
        ("weekly", cmd_weekly_report),
        ("alltasks", cmd_all_tasks), ("completed", cmd_completed_tasks),
        ("taskhistory", cmd_task_history), ("offlinemsgs", cmd_offline_messages),
        ("verify", cmd_verify_secret), ("reminderlog", cmd_reminder_history), ("alllogs", cmd_all_logs),
    ]:
        app.add_handler(CommandHandler(cmd, handler))
    
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(reminder_job, interval=30, first=5)
        job_queue.run_repeating(bill_due_alert_job, interval=3600, first=60)
        job_queue.run_repeating(water_reminder_job, interval=3600, first=300)
        job_queue.run_repeating(process_offline_queue, interval=300, first=30)
        log.info("⏰ All jobs started!")
    else:
        log.warning("⚠️ JobQueue nahi mila!")
    
    log.info("✅ Bot ready! /start karo")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
