#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════╗
║       PERSONAL AI ASSISTANT — ADVANCED v4.2      ║
║  100% FREE | Rate Limit Fixed | Real-Time Clock  ║
║  Smart Retry | Failed Queue | Secret Code        ║
╚══════════════════════════════════════════════════╝
"""

import os, json, logging, time, asyncio, urllib.request, urllib.error, ssl, random
from datetime import datetime, date, timedelta, timezone
from xml.etree import ElementTree as ET

# SSL fix
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
    log.error("❌ TELEGRAM_TOKEN and GEMINI_API_KEY required!")
    exit(1)

# ══════════════════════════════════════════════
# 🔥 RATE LIMIT CONFIG
# ══════════════════════════════════════════════
# Gemini free tier: ~15 requests per minute
# Thoda conservative rakho — 10 requests per minute max
RATE_LIMIT_DELAY = 6  # seconds between requests
MAX_RETRIES = 1  # Kam retries — 429 pe zyada try karna pointless

# Multiple API keys support (agar ek key rate limit ho jaye toh doosri use karo)
GEMINI_API_KEYS = [
    key.strip() for key in GEMINI_API_KEY.split(",") if key.strip()
]
# Agar comma separated nahi hai toh single key
if len(GEMINI_API_KEYS) == 1:
    # Single key — same key repeat karo (itna hi option hai free tier mein)
    pass
elif not GEMINI_API_KEYS:
    GEMINI_API_KEYS = [GEMINI_API_KEY]

log.info(f"🔑 API Keys loaded: {len(GEMINI_API_KEYS)}")

# 🔥 MULTI-MODEL FALLBACK — Updated for rate limits
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",   # Sabse high rate limit
    "gemini-2.5-flash",        # Medium rate limit
    "gemini-2.5-pro",          # Kam rate limit (jyada 429 aata hai)
]

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

# ══════════════════════════════════════════════
# RATE LIMIT TRACKER
# ══════════════════════════════════════════════
class RateLimitTracker:
    """Track karo ki kaunsi key/model kitni baar use hua"""
    def __init__(self):
        self.last_request_time = 0
        self.request_count = 0
        self.key_index = 0
    
    def wait_if_needed(self):
        """Rate limit se bachne ke liye wait karo"""
        now = time.time()
        elapsed = now - self.last_request_time
        
        if elapsed < RATE_LIMIT_DELAY:
            wait = RATE_LIMIT_DELAY - elapsed + random.uniform(0.5, 2.0)
            log.info(f"⏳ Rate limit wait: {wait:.1f}s")
            time.sleep(wait)
        
        self.last_request_time = time.time()
        self.request_count += 1
    
    def get_next_key(self) -> str:
        """Round-robin API keys"""
        key = GEMINI_API_KEYS[self.key_index % len(GEMINI_API_KEYS)]
        self.key_index += 1
        return key
    
    def rotate_key(self):
        """429 error aane pe key rotate karo"""
        self.key_index = (self.key_index + 1) % len(GEMINI_API_KEYS)
        log.info(f"🔄 Key rotated to index {self.key_index}")

rate_tracker = RateLimitTracker()

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
F_TASK_LOGS = os.path.join(DATA, "task_logs.json")
F_FAILED    = os.path.join(DATA, "failed_requests.json")
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
# 🔥 REAL TIME HELPERS — ALWAYS ACCURATE
# ══════════════════════════════════════════════
# IST = UTC + 5:30
IST_OFFSET = timedelta(hours=5, minutes=30)
IST = timezone(IST_OFFSET)

def get_indian_time():
    """Current IST time — chahe server kisi bhi timezone mein ho"""
    # Method 1: Server time se IST calculate karo
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST)
    return now_ist

def today_str():
    return get_indian_time().strftime("%Y-%m-%d")

def now_str():
    return get_indian_time().strftime("%H:%M")

def now_ist():
    return get_indian_time()

def yesterday_str():
    return (get_indian_time() - timedelta(days=1)).strftime("%Y-%m-%d")

def get_current_time_label():
    """Detailed Hindi time label"""
    now = get_indian_time()
    days_hi = {
        0: "Monday/सोमवार", 1: "Tuesday/मंगलवार", 2: "Wednesday/बुधवार",
        3: "Thursday/गुरुवार", 4: "Friday/शुक्रवार", 5: "Saturday/शनिवार",
        6: "Sunday/रविवार"
    }
    months_hi = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
    }
    day_name = days_hi.get(now.weekday(), "")
    month_name = months_hi.get(now.month, "")
    return f"{day_name}, {now.day} {month_name} {now.year} — {now.strftime('%I:%M %p')} IST"

# Log karo ki time kya hai
current_time_now = get_indian_time()
log.info(f"⏰ CURRENT IST TIME: {current_time_now.strftime('%Y-%m-%d %I:%M:%S %p')}")
log.info(f"📅 TODAY: {today_str()}")

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

# ══════════════════════════════════════════════
# FAILED REQUEST TRACKER
# ══════════════════════════════════════════════
class FailedRequests:
    def __init__(self):
        self.data = load(F_FAILED, {"queue": []})

    def save_data(self):
        save(F_FAILED, self.data)

    def add(self, user_msg: str, chat_id: int, reason: str):
        # Duplicate check — same message 2 baar save mat karo
        for req in self.data["queue"][-20:]:
            if req["msg"] == user_msg and not req.get("retried"):
                return  # Already queued
        
        self.data["queue"].append({
            "msg": user_msg,
            "chat_id": chat_id,
            "reason": reason,
            "time": datetime.now().isoformat(),
            "retried": False
        })
        # Max 50 failed requests rakho
        self.data["queue"] = self.data["queue"][-50:]
        self.save_data()

    def get_unretried(self) -> list:
        return [r for r in self.data["queue"] if not r["retried"]]

    def mark_retried(self, index: int):
        if 0 <= index < len(self.data["queue"]):
            self.data["queue"][index]["retried"] = True
            self.save_data()

# ══════════════════════════════════════════════
# 🔥 GEMINI MULTI-MODEL CALLER — RATE LIMIT FIXED
# ══════════════════════════════════════════════
def call_gemini(system_prompt: str, messages: list, user_msg: str = None, 
                chat_id: int = None, failed_queue=None, is_action: bool = False) -> str:
    
    contents = [
        {"role": "user",  "parts": [{"text": f"[SYSTEM]\n{system_prompt}\n[/SYSTEM]\n\nReady?"}]},
        {"role": "model", "parts": [{"text": "Haan ready!"}]},
    ]
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    # Temperature action ke liye 0, chat ke liye 0.75
    temperature = 0.0 if is_action else 0.75
    max_tokens = 300 if is_action else 600
    
    payload = json.dumps({
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}
    }).encode("utf-8")

    errors = []
    
    # Random model order for rate limit distribution
    models_to_try = list(GEMINI_MODELS)
    if not is_action:
        # Chat ke liye fast models pehle
        models_to_try = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]
    else:
        # Action ke liye bhi fast models pehle
        models_to_try = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
    
    for model in models_to_try:
        for attempt in range(MAX_RETRIES + 1):
            # Rate limit wait
            rate_tracker.wait_if_needed()
            
            try:
                api_key = rate_tracker.get_next_key()
                url = BASE_URL.format(model=model, key=api_key)
                
                req = urllib.request.Request(
                    url, data=payload,
                    headers={"Content-Type": "application/json"}, method="POST"
                )
                
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    text = result["candidates"][0]["content"]["parts"][0]["text"]
                    log.info(f"✅ Gemini success: {model}")
                    return text

            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8")[:200]
                except:
                    pass
                
                if e.code == 429:
                    # Rate limit — KEY CHANGES:
                    # 1. Zyada wait karo
                    # 2. Key rotate karo
                    # 3. Agla model try karo immediately
                    wait_time = (attempt + 1) * 10 + random.uniform(2, 5)  # 10-30 seconds
                    log.warning(f"⚠️ Rate limit ({model}): {wait_time:.0f}s wait...")
                    
                    # Agar multiple keys hain toh rotate karo
                    if len(GEMINI_API_KEYS) > 1:
                        rate_tracker.rotate_key()
                    
                    time.sleep(wait_time)
                    
                    # Is model ko skip karo, agla try
                    if attempt >= MAX_RETRIES:
                        errors.append(f"{model}: rate limited")
                        break
                    continue
                    
                elif e.code in (500, 503, 502):
                    log.warning(f"⚠️ Server error ({model}): {e.code}")
                    time.sleep(3)
                    errors.append(f"{model}: server {e.code}")
                    continue
                    
                elif e.code == 404:
                    log.warning(f"⚠️ Model not found: {model}")
                    errors.append(f"{model}: 404")
                    break
                    
                elif e.code == 400:
                    log.error(f"❌ Bad request ({model}): {body}")
                    return f"❌ Request error"
                    
                else:
                    errors.append(f"{model}: HTTP {e.code}")
                    break
                    
            except urllib.error.URLError as e:
                log.warning(f"⚠️ Network error ({model}): {e.reason}")
                errors.append(f"{model}: network")
                time.sleep(5)
                break
                
            except Exception as e:
                log.warning(f"⚠️ Unexpected error ({model}): {e}")
                errors.append(f"{model}: {str(e)[:50]}")
                break

    # Sab models fail — save karo ya fallback message do
    error_summary = ", ".join(errors[:3]) if errors else "all models failed"
    
    if user_msg and chat_id is not None and failed_queue:
        failed_queue.add(user_msg, chat_id, error_summary)
        return (f"⚠️ *Rate Limit!* Thodi der baad try karo! 🙏\n"
                f"_({error_summary[:80]})_")
    
    return f"⚠️ Gemini busy hai — thodi der baad try karo! 🙏\n_({error_summary[:80]})_"

# ══════════════════════════════════════════════
# FREE NEWS via RSS (with rate limit)
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
                if title:
                    items.append({"title": title, "desc": desc[:120] if desc else "", 
                                 "link": link or "", "pub": ""})
    except Exception as e:
        log.warning(f"News fetch error: {e}")
        return [{"title": "News unavailable right now", "desc": str(e)[:100], "link": "", "pub": ""}]

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

    def add(self, role: str, content: str):
        self.data["history"].append({
            "role": role, "content": content,
            "time": datetime.now().isoformat()
        })
        self.data["history"] = self.data["history"][-40:]  # Reduced from 80
        save(F_CHAT, self.data)

    def track_msg(self, chat_id: int, msg_id: int):
        self.data["msg_ids"].append({"chat_id": chat_id, "msg_id": msg_id})
        self.data["msg_ids"] = self.data["msg_ids"][-200:]  # Reduced from 500
        save(F_CHAT, self.data)

    def get_tracked_ids(self):
        return self.data.get("msg_ids", [])

    def get_recent(self, n=10) -> list:  # Reduced from 20
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
        self.data["facts"] = self.data["facts"][-200:]  # Reduced from 400
        self.save_data()

    def context(self) -> str:
        facts = "\n".join(f"• {x['f']}" for x in self.data["facts"][-15:]) or "Kuch nahi"
        prefs = "\n".join(f"• {k}: {v}" for k, v in self.data["prefs"].items()) or "Kuch nahi"
        dates = "\n".join(f"• {k}: {v}" for k, v in self.data["dates"].items()) or "Kuch nahi"
        imp   = "\n".join(f"⭐ {n['note']}" for n in self.data.get("important_notes", [])[-5:]) or "Kuch nahi"
        return (f"FACTS:\n{facts}\n\nPREFERENCES:\n{prefs}\n\nDATES:\n{dates}\n\nIMPORTANT:\n{imp}")

# ══════════════════════════════════════════════
# TASK LOGS SYSTEM
# ══════════════════════════════════════════════
class TaskLogs:
    def __init__(self):
        self.data = load(F_TASK_LOGS, {"logs": []})

    def save_data(self):
        save(F_TASK_LOGS, self.data)

    def add_log(self, action_type: str, description: str, task_id: int = None, details: dict = None):
        entry = {
            "type": action_type,
            "description": description,
            "task_id": task_id,
            "details": details or {},
            "timestamp": datetime.now().isoformat(),
            "date": today_str()
        }
        self.data["logs"].append(entry)
        self.data["logs"] = self.data["logs"][-500:]  # Reduced from 1000
        self.save_data()

    def get_all_logs(self) -> list:
        return self.data["logs"]
    
    def get_created_tasks(self) -> list:
        return [l for l in self.data["logs"] if l["type"] == "created"]

    def get_completed_tasks(self) -> list:
        return [l for l in self.data["logs"] if l["type"] == "completed"]

    def get_all_task_summary(self) -> dict:
        created = self.get_created_tasks()
        completed = self.get_completed_tasks()
        created_ids = set(l.get("task_id") for l in created if l.get("task_id"))
        completed_ids = set(l.get("task_id") for l in completed if l.get("task_id"))
        return {
            "total_created": len(created_ids),
            "total_completed": len(completed_ids),
            "total_pending": len(created_ids - completed_ids)
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
        task_logs.add_log("created", title, t["id"], {"priority": priority})
        return t

    def complete(self, tid):
        for t in self.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True; t["done_at"] = datetime.now().isoformat()
                self.save_data()
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

    def delete(self, nid):
        self.data["list"] = [n for n in self.data["list"] if n["id"] != nid]
        self.save_data()

    def recent(self, n=10): return self.data["list"][-n:]

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

    def add(self, title, deadline=None):
        self.data["counter"] += 1
        g = {"id": self.data["counter"], "title": title,
             "deadline": deadline or "", "progress": 0,
             "done": False, "created": today_str()}
        self.data["list"].append(g); self.save_data(); return g

    def update_progress(self, gid, pct):
        for g in self.data["list"]:
            if g["id"] == gid:
                g["progress"] = min(100, max(0, pct))
                if g["progress"] == 100: g["done"] = True
                self.save_data(); return g
        return None

    def active(self): return [g for g in self.data["list"] if not g["done"]]

# ══════════════════════════════════════════════
# REMINDERS
# ══════════════════════════════════════════════
class Reminders:
    def __init__(self):
        self.data = load(F_REMINDERS, {"list": [], "counter": 0})

    def save_data(self): save(F_REMINDERS, self.data)

    def add(self, chat_id: int, text: str, remind_at: str, repeat: str = "once") -> dict:
        self.data["counter"] += 1
        r = {
            "id": self.data["counter"], "chat_id": chat_id,
            "text": text, "time": remind_at, "repeat": repeat,
            "date": today_str(), "active": True,
            "fired_today": False, "created": datetime.now().isoformat()
        }
        self.data["list"].append(r); self.save_data()
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
        for r in self.data["list"]:
            if r["fired_today"]:
                r["fired_today"] = False
        self.save_data()

    def due_now(self) -> list:
        """REAL server time IST se check karo"""
        now = get_indian_time()
        due = []
        for r in self.data["list"]:
            if not r["active"] or r["fired_today"]:
                continue
            try:
                r_dt = datetime.strptime(today_str() + " " + r["time"], "%Y-%m-%d %H:%M")
                diff = (now - r_dt).total_seconds()
                if 0 <= diff < 120:  # 2 minute window
                    due.append(r)
            except:
                pass
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

    def goal(self) -> int:
        return self.data.get("goal_ml", 2000)

    def set_goal(self, ml: int):
        self.data["goal_ml"] = ml; self.save_data()

    def week_summary(self) -> dict:
        result = {}
        for i in range(7):
            d = (get_indian_time().date() - timedelta(days=i)).isoformat()
            result[d] = sum(e["ml"] for e in self.data["logs"].get(d, []))
        return result

# ══════════════════════════════════════════════
# BILLS
# ══════════════════════════════════════════════
class BillTracker:
    def __init__(self):
        self.data = load(F_BILLS, {"list": [], "counter": 0})

    def save_data(self): save(F_BILLS, self.data)

    def add(self, name: str, amount: float, due_day: int, bill_type: str = "bill") -> dict:
        self.data["counter"] += 1
        b = {"id": self.data["counter"], "name": name, "amount": amount,
             "due_day": due_day, "type": bill_type, "active": True,
             "paid_months": [], "created": today_str()}
        self.data["list"].append(b); self.save_data(); return b

    def all_active(self):
        return [b for b in self.data["list"] if b["active"]]

    def mark_paid(self, bid: int) -> bool:
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid:
                if ym not in b["paid_months"]:
                    b["paid_months"].append(ym)
                self.save_data(); return True
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
        today_d = get_indian_time().date()
        result = []
        for b in self.data["list"]:
            if not b["active"] or self.is_paid_this_month(b["id"]):
                continue
            try:
                due_date = date(today_d.year, today_d.month, min(b["due_day"], 28))
            except:
                continue
            if today_d <= due_date <= today_d + timedelta(days=days_ahead):
                result.append({**b, "due_date": due_date.isoformat()})
        return result

    def month_total(self) -> float:
        return sum(b["amount"] for b in self.data["list"] if b["active"])

# ══════════════════════════════════════════════
# CALENDAR
# ══════════════════════════════════════════════
class CalendarManager:
    def __init__(self):
        self.data = load(F_CALENDAR, {"events": [], "counter": 0})

    def save_data(self): save(F_CALENDAR, self.data)

    def add(self, title: str, event_date: str, event_time: str = "") -> dict:
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "title": title,
             "date": event_date, "time": event_time, "created": today_str()}
        self.data["events"].append(e); self.save_data(); return e

    def delete(self, eid: int) -> bool:
        before = len(self.data["events"])
        self.data["events"] = [e for e in self.data["events"] if e["id"] != eid]
        self.save_data()
        return before != len(self.data["events"])

    def upcoming(self, days: int = 7) -> list:
        today_d = get_indian_time().date()
        cutoff  = today_d + timedelta(days=days)
        result = []
        for e in self.data["events"]:
            try:
                if today_d <= date.fromisoformat(e["date"]) <= cutoff:
                    result.append(e)
            except: pass
        return sorted(result, key=lambda x: x["date"])

    def today_events(self) -> list:
        return [e for e in self.data["events"] if e["date"] == today_str()]

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
# 🔥 SYSTEM PROMPT — SHORT & EFFICIENT
# ══════════════════════════════════════════════
def build_system_prompt() -> str:
    now_label = get_current_time_label()
    current_time = now_str()
    
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    water_today = water.today_total()
    water_goal  = water.goal()
    
    tasks_s = "\n".join(f"  {t['title']}" for t in tp[:5]) or "None"
    
    return f"""You are 'Dost' — a helpful AI assistant. Speak in Hindi/Hinglish. Be warm and friendly like a close friend.

⚠️ CURRENT REAL TIME: {now_label}
• 24hr: {current_time} | Date: {today_str()}
• When asked "what time is it?" — respond with THIS EXACT TIME. Never guess.

📋 TODAY'S TASKS ({len(tp)}):
{tasks_s}

💧 Water: {water_today}ml / {water_goal}ml

🧠 MEMORY:
{mem.context()}

RULES:
- Always use Hindi/Hinglish
- Short responses (2-4 lines max)
- For time questions, use the exact time provided above
- Never say "As an AI"
- Never suggest payment/upgrade
"""

# ══════════════════════════════════════════════
# ACTION SYSTEM PROMPT — SHORT
# ══════════════════════════════════════════════

ACTION_SYSTEM_PROMPT = """Parse user message into JSON action. Return ONLY raw JSON (no backticks, no markdown).

Current time: {now}
Current 24hr: {current_time}
Today: {today}
2 min from now: {two_min}

JSON format: {{"action":"ACTION","params":{{...}},"reply":"confirm msg"}}

ACTIONS:
REMIND — params: {{"time":"HH:MM","text":"...","repeat":"once"}}
  For "X min baad": use two_min value above
  For "X baje": subah 7=07:00, raat 7=19:00
ADD_TASK — {{"title":"...","priority":"high/medium/low"}}
ADD_EXPENSE — {{"amount":numeric,"desc":"...","category":"..."}}
ADD_DIARY — {{"text":"...","mood":"😊"}}
ADD_MEMORY — {{"fact":"..."}}
COMPLETE_TASK — {{"title_hint":"..."}}
SHOW_TASKS — {{}}
SHOW_ALL_TASKS — {{}}
SHOW_COMPLETED_TASKS — {{}}
CHAT — {{}} (default)

Example: "2 min baad chai" → {{"action":"REMIND","params":{{"time":"{two_min}","text":"Chai peena","repeat":"once"}},"reply":"✅ {two_min} baje yaad dilaunga!"}}
"""

import re as _re

def _regex_fallback(user_msg: str) -> dict:
    """Regex fallback with REAL server time"""
    lower = user_msg.lower()
    now = get_indian_time()

    # REMIND detection
    remind_words = ["alarm", "reminder", "yaad dila", "remind", "notify",
                    "minute baad", "min baad", "ghante baad", "baje"]
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
            # Clean text
            text = _re.sub(r'\d+\s*(?:minute|min|mins|ghante|ghanta|hour|hr)', '', user_msg, flags=_re.I)
            text = _re.sub(r'\d{1,2}(?::\d{2})?\s*(?:baje|baj)?', '', text, flags=_re.I)
            text = _re.sub(r'(?:alarm|reminder|yaad dila|remind|laga do|set karo|baad|notify)\s*', '', text, flags=_re.I).strip()
            text = text or "⏰ Reminder!"
            return {"action": "REMIND", "params": {"time": time_str, "text": text, "repeat": "once"}, "reply": ""}

    # TASK detection
    if any(w in lower for w in ["karna hai", "task add", "kaam add", "to-do", "todo"]):
        return {"action": "ADD_TASK", "params": {"title": user_msg[:80], "priority": "medium"}, "reply": ""}

    # EXPENSE detection
    if any(w in lower for w in ["rs ", "rupaye", "kharcha", "spend"]):
        m = _re.search(r'(\d+)', lower)
        amount = float(m.group(1)) if m else 0
        if amount > 0:
            return {"action": "ADD_EXPENSE", "params": {"amount": amount, "desc": user_msg[:60], "category": "general"}, "reply": ""}

    return {"action": "CHAT", "params": {}, "reply": ""}


def call_gemini_action(user_msg: str, now_label: str, today_label: str) -> dict:
    """Gemini se action lo — agar fail toh regex fallback"""
    now = get_indian_time()
    two_min = (now + timedelta(minutes=2)).strftime("%H:%M")
    current_time = now.strftime("%H:%M")
    
    prompt = ACTION_SYSTEM_PROMPT.format(
        now=now_label, current_time=current_time,
        today=today_label, two_min=two_min
    )

    full_msg = f"{prompt}\n\nUser: {user_msg}"

    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": full_msg}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 200}
    }).encode("utf-8")

    raw = ""
    for model in ["gemini-2.5-flash-lite", "gemini-2.5-flash"]:
        for attempt in range(MAX_RETRIES + 1):
            rate_tracker.wait_if_needed()
            try:
                api_key = rate_tracker.get_next_key()
                url = BASE_URL.format(model=model, key=api_key)
                req = urllib.request.Request(url, data=payload,
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=25) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                    raw = raw.replace("```json", "").replace("```", "").strip()
                    
                    json_match = _re.search(r'\{.*\}', raw, _re.DOTALL)
                    if json_match:
                        raw = json_match.group(0)
                    
                    parsed = json.loads(raw)
                    return parsed

            except json.JSONDecodeError:
                if attempt >= MAX_RETRIES:
                    break
                continue
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(8 + random.uniform(0, 3))
                    if attempt >= MAX_RETRIES:
                        break
                    continue
                break
            except Exception:
                break

    # Fallback to regex
    return _regex_fallback(user_msg)


async def execute_action(action_data: dict, chat_id: int, user_msg: str) -> str:
    action = action_data.get("action", "CHAT")
    params = action_data.get("params", {})
    ai_reply = action_data.get("reply", "")

    now = get_indian_time()

    # ── REMIND ──────────────────────────────────
    if action == "REMIND":
        time_str = params.get("time", "")
        text = params.get("text", "⏰ Reminder!")
        repeat = params.get("repeat", "once")

        if not time_str or not _re.match(r'^\d{2}:\d{2}$', time_str):
            return f"⏰ Time format galat! HH:MM use karo. Abhi *{now.strftime('%H:%M')}* hue hain."

        r = reminders.add(chat_id, text, time_str, repeat)
        repeat_txt = {"once": "Ek baar", "daily": "Roz 🔁", "weekly": "Har hafte 📅"}.get(repeat, repeat)
        
        # Calculate time left
        try:
            remind_dt = datetime.strptime(today_str() + " " + time_str, "%Y-%m-%d %H:%M")
            diff = (remind_dt - now).total_seconds()
            if diff < 0:
                remind_dt += timedelta(days=1)
                diff = (remind_dt - now).total_seconds()
            mins = max(0, int(diff / 60))
            if mins >= 60:
                time_left = f"\n⏳ _{mins//60}h {mins%60}m mein_"
            elif mins > 0:
                time_left = f"\n⏳ _{mins}m mein_"
            else:
                time_left = ""
        except:
            time_left = ""
        
        return (f"✅ *Reminder set!* ⏰ {time_str}\n"
                f"📝 {text}\n🆔 `#{r['id']}` | {repeat_txt}"
                f"{time_left}\n`/delremind {r['id']}`")

    # ── ADD_TASK ─────────────────────────────────
    elif action == "ADD_TASK":
        title = params.get("title", user_msg[:80])
        priority = params.get("priority", "medium")
        t = tasks.add(title, priority)
        icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        return f"✅ Task added: {icons.get(priority,'🟡')} *{title}*\n🆔 `#{t['id']}`"

    # ── ADD_EXPENSE ──────────────────────────────
    elif action == "ADD_EXPENSE":
        amount = float(params.get("amount", 0))
        desc = params.get("desc", "Kharcha")
        if amount <= 0:
            return "💰 Amount batao?"
        expenses.add(amount, desc)
        today_total = expenses.today_total()
        return f"✅ ₹{amount:.0f} — {desc}\n📊 Aaj total: ₹{today_total:.0f}"

    # ── ADD_DIARY ────────────────────────────────
    elif action == "ADD_DIARY":
        text = params.get("text", user_msg[:100])
        mood = params.get("mood", "😊")
        diary.add(text, mood)
        return f"📖 Diary mein likh diya {mood}"

    # ── ADD_MEMORY ───────────────────────────────
    elif action == "ADD_MEMORY":
        fact = params.get("fact", user_msg[:200])
        mem.add_fact(fact)
        return f"🧠 Yaad kar liya ✅\n_{fact[:80]}_"

    # ── COMPLETE_TASK ────────────────────────────
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

    # ── SHOW_TASKS ───────────────────────────────
    elif action == "SHOW_TASKS":
        pending = tasks.today_pending()
        if not pending:
            return "🎉 Koi pending task nahi!"
        txt = f"📋 *PENDING ({len(pending)})*\n\n"
        for t in pending[:8]:
            icon = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
            txt += f"{icon} *#{t['id']}* {t['title']}\n"
        return txt

    # ── SHOW_ALL_TASKS ───────────────────────────
    elif action == "SHOW_ALL_TASKS":
        all_t = tasks.all_tasks()
        if not all_t:
            return "📋 Koi task nahi!"
        pending_t = tasks.pending()
        completed_t = tasks.completed_tasks()
        txt = f"📋 *ALL TASKS ({len(all_t)})*\n"
        txt += f"⏳ Pending: {len(pending_t)} | ✅ Done: {len(completed_t)}\n\n"
        if pending_t:
            for t in pending_t[:5]:
                txt += f"⏳ *#{t['id']}* {t['title']}\n"
        if completed_t:
            txt += "\n✅ *Completed:*\n"
            for t in completed_t[-5:]:
                txt += f"✅ *#{t['id']}* {t['title']}\n"
        return txt

    # ── SHOW_COMPLETED_TASKS ─────────────────────
    elif action == "SHOW_COMPLETED_TASKS":
        completed_t = tasks.completed_tasks()
        if not completed_t:
            return "✅ Abhi tak koi task complete nahi hua!"
        txt = f"✅ *COMPLETED ({len(completed_t)})*\n\n"
        for t in completed_t[-10:]:
            txt += f"✅ *#{t['id']}* {t['title']}\n"
        return txt

    # ── CHAT ─────────────────────────────────────
    else:
        auto_extract_facts(user_msg)
        chat_hist.add("user", user_msg)
        history = chat_hist.get_recent(6)  # Kam history = kam tokens = kam rate limit issues
        reply = call_gemini(build_system_prompt(), history, user_msg, chat_id, failed_reqs)
        chat_hist.add("assistant", reply)
        return reply


async def ai_chat(user_msg: str, chat_id: int = None) -> str:
    now_label = get_current_time_label()
    today_label = today_str()

    if chat_id:
        action_data = call_gemini_action(user_msg, now_label, today_label)
        return await execute_action(action_data, chat_id, user_msg)
    else:
        auto_extract_facts(user_msg)
        chat_hist.add("user", user_msg)
        history = chat_hist.get_recent(6)
        reply = call_gemini(build_system_prompt(), history)
        chat_hist.add("assistant", reply)
        return reply

# ══════════════════════════════════════════════
# KEYBOARD (Simplified)
# ══════════════════════════════════════════════
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Briefing", callback_data="briefing"),
         InlineKeyboardButton("📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("💪 Habits", callback_data="habits"),
         InlineKeyboardButton("💰 Kharcha", callback_data="expenses")],
        [InlineKeyboardButton("📰 News", callback_data="news_menu"),
         InlineKeyboardButton("📝 Notes", callback_data="notes")],
        [InlineKeyboardButton("💧 Water", callback_data="water_status"),
         InlineKeyboardButton("💳 Bills", callback_data="bills_menu")],
        [InlineKeyboardButton("📊 Weekly", callback_data="weekly_report"),
         InlineKeyboardButton("🧠 Memory", callback_data="memory")],
        [InlineKeyboardButton("🧹 Clear Chat", callback_data="clear_chat"),
         InlineKeyboardButton("🏠 Menu", callback_data="menu")],
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

# ══════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Dost"
    now = get_indian_time()
    txt = (f"🕌 *Assalamualaikum {name}!*\n\n"
           f"⏰ *{now.strftime('%I:%M %p')} IST* | 📅 {now.strftime('%d %b %Y')}\n\n"
           "✅ 100% FREE | Rate Limit Fixed\n"
           "📝 Type anything or use buttons 👇")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tp = tasks.today_pending()
    yd = tasks.done_on(yesterday_str())
    hd, hp = habits.today_status()
    now = get_indian_time()
    
    txt = f"🌅 *DAILY BRIEFING*\n⏰ {now.strftime('%I:%M %p')} | 📅 {now.strftime('%d %b')}\n\n"
    
    if yd:
        txt += f"✅ *Kal kiye:*\n" + "".join(f"  • {t['title']}\n" for t in yd[:3]) + "\n"
    
    if tp:
        txt += f"📋 *Aaj baaki ({len(tp)}):*\n"
        for t in tp[:5]:
            e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
            txt += f"  {e} {t['title']}\n"
    else:
        txt += "🎉 *Koi pending task nahi!*\n"
    
    if hp:
        txt += f"\n💪 *Habits baaki:* " + ", ".join(h["name"] for h in hp[:3])
    
    water_t = water.today_total()
    water_g = water.goal()
    pct = min(100, int(water_t/water_g*100)) if water_g else 0
    txt += f"\n\n💧 Water: {water_t}ml/{water_g}ml ({pct}%)"
    txt += f"\n💰 Kharcha: ₹{expenses.today_total():.0f} aaj | ₹{expenses.month_total():.0f} month"
    
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📋 `/task Kaam naam [high/low]`", parse_mode="Markdown"); return
    args = " ".join(ctx.args)
    priority = "medium"
    if args.endswith(" high"): priority="high"; args=args[:-5].strip()
    elif args.endswith(" low"): priority="low"; args=args[:-4].strip()
    t = tasks.add(args, priority=priority)
    await update.message.reply_text(f"✅ *Task added!*\n🟡 *{t['title']}*\n🆔 `#{t['id']}`", parse_mode="Markdown")

async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("`/done <ID>`", parse_mode="Markdown"); return
    try:
        t = tasks.complete(int(ctx.args[0]))
        await update.message.reply_text(f"🎉 *Done!* {t['title']}" if t else "❌ Not found", parse_mode="Markdown")
    except: await update.message.reply_text("❌ Invalid ID", parse_mode="Markdown")

async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("`/deltask <ID>`", parse_mode="Markdown"); return
    try:
        ok = tasks.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Deleted!" if ok else "❌ Not found", parse_mode="Markdown")
    except: pass

async def cmd_diary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📖 `/diary Aaj kya hua...`", parse_mode="Markdown"); return
    diary.add(" ".join(ctx.args))
    await update.message.reply_text(f"📖 Diary entry saved! 🕐 {now_str()}", parse_mode="Markdown")

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("💪 `/habit Morning walk 🏃`", parse_mode="Markdown"); return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(f"💪 Habit added: {h['emoji']} {h['name']}\n`/hdone {h['id']}` se mark karo!", parse_mode="Markdown")

async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            txt = "Kaunsi? " + ", ".join(f"`/hdone {h['id']}` {h['name']}" for h in pending)
        else:
            txt = "🎊 Sab done!"
        await update.message.reply_text(txt, parse_mode="Markdown"); return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        await update.message.reply_text(f"💪 Done! 🔥{streak} day streak!" if ok else "✅ Already marked", parse_mode="Markdown")
    except: pass

async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text("💰 `/kharcha 100 Chai`", parse_mode="Markdown"); return
    try:
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        await update.message.reply_text(f"💰 ₹{amount:.0f} — {desc}\n📊 Aaj: ₹{expenses.today_total():.0f}", parse_mode="Markdown")
    except: pass

async def cmd_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("💳 `/budget 5000`", parse_mode="Markdown"); return
    try:
        expenses.set_budget(float(ctx.args[0]))
        await update.message.reply_text(f"💳 Budget set: ₹{ctx.args[0]}", parse_mode="Markdown")
    except: pass

async def cmd_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🎯 `/goal Goal naam`", parse_mode="Markdown"); return
    g = goals.add(" ".join(ctx.args))
    await update.message.reply_text(f"🎯 Goal added: {g['title']}", parse_mode="Markdown")

async def cmd_gprogress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        gid, pct = int(ctx.args[0]), int(ctx.args[1])
        g = goals.update_progress(gid, pct)
        await update.message.reply_text(f"📊 *{g['title']}* — {pct}%" if g else "❌ Not found", parse_mode="Markdown")
    except: pass

async def cmd_remember(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🧠 `/remember Koi baat`", parse_mode="Markdown"); return
    mem.add_fact(" ".join(ctx.args))
    await update.message.reply_text("🧠 Yaad kar liya! ✅", parse_mode="Markdown")

async def cmd_recall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    facts = mem.data.get("facts", [])
    if not facts:
        await update.message.reply_text("🧠 Kuch yaad nahi.", parse_mode="Markdown"); return
    txt = "🧠 *YAADDASHT*\n\n" + "\n".join(f"📌 {f['f']}" for f in facts[-10:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📝 `/note Kuch important`", parse_mode="Markdown"); return
    n = notes.add(" ".join(ctx.args))
    await update.message.reply_text(f"📝 Note #{n['id']} saved!", parse_mode="Markdown")

async def cmd_delnote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("`/delnote <ID>`", parse_mode="Markdown"); return
    try:
        notes.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Deleted!", parse_mode="Markdown")
    except: pass

async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📰 Category choose karo:", parse_mode="Markdown", reply_markup=news_kb())

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Clear", callback_data="confirm_clear_chat"),
         InlineKeyboardButton("❌ Cancel", callback_data="menu")]
    ])
    await update.message.reply_text(f"🧹 Clear {chat_hist.count()} messages?\n✅ Data safe rahega", parse_mode="Markdown", reply_markup=kb)

async def cmd_nuke(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tracked = chat_hist.get_tracked_ids()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💣 NUKE", callback_data="confirm_nuke"),
         InlineKeyboardButton("❌ Cancel", callback_data="menu")]
    ])
    sent = await update.message.reply_text(f"💣 Delete {len(tracked)} bot msgs + {chat_hist.count()} history?\n✅ Data safe", parse_mode="Markdown", reply_markup=kb)
    chat_hist.track_msg(update.effective_chat.id, sent.message_id)

# ══════════════════════════════════════════════
# REMINDER COMMANDS
# ══════════════════════════════════════════════
def parse_reminder_time(args: list):
    if not args: return None, None, None
    
    time_arg = args[0].lower()
    rest = args[1:]
    repeat = "once"
    
    if rest and rest[-1].lower() == "daily":
        repeat = "daily"; rest = rest[:-1]
    elif rest and rest[-1].lower() == "weekly":
        repeat = "weekly"; rest = rest[:-1]
    
    text = " ".join(rest) if rest else "⏰ Reminder!"
    now = get_indian_time()
    
    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        return (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M"), repeat, text
    if time_arg.endswith("h") and time_arg[:-1].isdigit():
        return (now + timedelta(hours=int(time_arg[:-1]))).strftime("%H:%M"), repeat, text
    if ":" in time_arg:
        parts = time_arg.split(":")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                return f"{h:02d}:{m:02d}", repeat, text
    return None, None, None

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = get_indian_time()
    if not ctx.args:
        await update.message.reply_text(
            f"⏰ *REMINDER*\nAbhi: *{now.strftime('%I:%M %p')}*\n\n"
            "`/remind 30m Chai` — 30 min baad\n"
            "`/remind 15:30 Doctor` — exact time\n"
            "`/remind 8:00 Uthna daily` — daily",
            parse_mode="Markdown"); return
    
    time_str, repeat, text = parse_reminder_time(ctx.args)
    if not time_str:
        await update.message.reply_text("❌ Format: `/remind 30m Kaam` ya `/remind 15:30 Kaam`", parse_mode="Markdown"); return
    
    r = reminders.add(update.effective_chat.id, text, time_str, repeat)
    repeat_label = {"once": "Once", "daily": "Daily 🔁", "weekly": "Weekly 📅"}.get(repeat, repeat)
    
    # Calculate time left
    try:
        remind_dt = datetime.strptime(today_str() + " " + time_str, "%Y-%m-%d %H:%M")
        diff = (remind_dt - now).total_seconds()
        if diff < 0:
            remind_dt += timedelta(days=1)
            diff = (remind_dt - now).total_seconds()
        mins = max(0, int(diff / 60))
        if mins >= 60:
            time_left = f"\n⏳ _{mins//60}h {mins%60}m mein_"
        elif mins > 0:
            time_left = f"\n⏳ _{mins}m mein_"
        else:
            time_left = ""
    except:
        time_left = ""
    
    await update.message.reply_text(
        f"✅ *Reminder set!*\n⏰ {time_str} — {text}\n"
        f"{repeat_label}{time_left}\n🆔 `#{r['id']}` | `/delremind {r['id']}`",
        parse_mode="Markdown")

async def cmd_reminders_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    active = reminders.all_active()
    now = get_indian_time()
    if not active:
        await update.message.reply_text(f"⏰ No reminders!\nAbhi: *{now.strftime('%I:%M %p')}*\n`/remind 30m Kaam` se set karo", parse_mode="Markdown"); return
    
    txt = f"⏰ *REMINDERS ({len(active)})*\nAbhi: *{now.strftime('%I:%M %p')}*\n\n"
    for r in active:
        icon = "🔁" if r["repeat"] == "daily" else "📅" if r["repeat"] == "weekly" else "1️⃣"
        status = "✅ Done" if r["fired_today"] else "⏳ Pending"
        txt += f"*#{r['id']}* {icon} `{r['time']}` — {r['text']} _{status}_\n"
    
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_delremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("`/delremind <ID>`", parse_mode="Markdown"); return
    try:
        ok = reminders.delete(int(ctx.args[0]))
        await update.message.reply_text(f"🗑 Deleted!" if ok else "❌ Not found", parse_mode="Markdown")
    except: pass

# ══════════════════════════════════════════════
# WATER COMMANDS
# ══════════════════════════════════════════════
async def cmd_water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ml = 250
    if ctx.args:
        try: ml = int(ctx.args[0])
        except: pass
    water.add(ml)
    total = water.today_total(); goal = water.goal()
    pct = min(100, int(total/goal*100)) if goal else 0
    await update.message.reply_text(f"💧 +{ml}ml | Total: {total}ml/{goal}ml ({pct}%)", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💧 +250ml", callback_data="water_250"),
             InlineKeyboardButton("💧 +500ml", callback_data="water_500")],
        ]))

async def cmd_water_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    total = water.today_total(); goal = water.goal()
    pct = min(100, int(total/goal*100)) if goal else 0
    await update.message.reply_text(f"💧 {total}ml / {goal}ml ({pct}%)", parse_mode="Markdown")

async def cmd_water_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text(f"Current: {water.goal()}ml\n`/watergoal 2500`", parse_mode="Markdown"); return
    try:
        water.set_goal(int(ctx.args[0]))
        await update.message.reply_text(f"✅ Goal: {ctx.args[0]}ml", parse_mode="Markdown")
    except: pass

# ══════════════════════════════════════════════
# BILL COMMANDS
# ══════════════════════════════════════════════
async def cmd_bill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 3:
        await update.message.reply_text("💳 `/bill Naam Amount Tarikh`\n`/bill Netflix 199 5`", parse_mode="Markdown"); return
    try:
        name, amount, due_day = ctx.args[0], float(ctx.args[1]), int(ctx.args[2])
        b = bills.add(name, amount, due_day)
        await update.message.reply_text(f"✅ {b['name']} ₹{b['amount']:.0f} — {due_day} tarikh", parse_mode="Markdown")
    except: pass

async def cmd_bills_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    all_b = bills.all_active()
    if not all_b:
        await update.message.reply_text("💳 No bills!", parse_mode="Markdown"); return
    txt = "💳 *BILLS*\n\n" + "".join(f"{'✅' if bills.is_paid_this_month(b['id']) else '⏳'} *{b['name']}* ₹{b['amount']:.0f} — {b['due_day']}th\n" for b in all_b)
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_bill_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("`/billpaid <ID>`", parse_mode="Markdown"); return
    try:
        ok = bills.mark_paid(int(ctx.args[0]))
        await update.message.reply_text("✅ Paid!" if ok else "❌ Not found", parse_mode="Markdown")
    except: pass

async def cmd_del_bill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("`/delbill <ID>`", parse_mode="Markdown"); return
    try:
        ok = bills.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Deleted!" if ok else "❌ Not found", parse_mode="Markdown")
    except: pass

# ══════════════════════════════════════════════
# CALENDAR COMMANDS
# ══════════════════════════════════════════════
async def cmd_cal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`", parse_mode="Markdown"); return
    import re as _re2
    args_str = " ".join(ctx.args)
    date_str = None; title = args_str; event_time = ""
    m = _re2.match(r'^(\d{4}-\d{2}-\d{2})\s+(.*)', args_str)
    if m: date_str = m.group(1); title = m.group(2)
    if not date_str:
        m = _re2.match(r'^(\d{2})-(\d{2})-(\d{4})\s+(.*)', args_str)
        if m: date_str = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"; title = m.group(4)
    if not date_str:
        if args_str.lower().startswith("aaj "): date_str = today_str(); title = args_str[4:]
        elif args_str.lower().startswith("kal "): date_str = (get_indian_time().date()+timedelta(days=1)).isoformat(); title = args_str[4:]
    if not date_str:
        await update.message.reply_text("❌ `/cal YYYY-MM-DD Event`", parse_mode="Markdown"); return
    t_match = _re2.search(r'(\d{1,2}:\d{2})', title)
    if t_match: event_time = t_match.group(1); title = title.replace(event_time, "").strip()
    try:
        date.fromisoformat(date_str)
        e = calendar.add(title, date_str, event_time)
        await update.message.reply_text(f"📅 {title} — {date_str}" + (f" ⏰{event_time}" if event_time else ""), parse_mode="Markdown")
    except: await update.message.reply_text("❌ Invalid date", parse_mode="Markdown")

async def cmd_cal_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    upcoming = calendar.upcoming(30)
    if not upcoming: await update.message.reply_text("📅 No events!", parse_mode="Markdown"); return
    txt = "📅 *UPCOMING*\n\n" + "".join(f"{'🔴' if e['date']==today_str() else '📆'} {e['date']} — {e['title']}\n" for e in upcoming[:10])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_del_cal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("`/delcal <ID>`", parse_mode="Markdown"); return
    try:
        ok = calendar.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Deleted!" if ok else "❌ Not found", parse_mode="Markdown")
    except: pass

# ══════════════════════════════════════════════
# WEEKLY REPORT
# ══════════════════════════════════════════════
async def cmd_weekly_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    today_d = get_indian_time().date(); week_ago = today_d - timedelta(days=6)
    week_exp = sum(e["amount"] for e in expenses.data["list"] if e["date"] >= week_ago.isoformat())
    pending = len(tasks.pending())
    
    txt = f"📊 *WEEKLY REPORT*\n{week_ago.strftime('%d %b')} — {today_d.strftime('%d %b')}\n\n"
    txt += f"📋 Tasks pending: {pending}\n"
    txt += f"💰 Week spend: ₹{week_exp:.0f}\n"
    txt += f"💧 Water avg: {int(water.today_total()/max(1, water.goal())*100)}%\n"
    
    await update.message.reply_text(txt, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

# ══════════════════════════════════════════════
# CALLBACK HANDLER
# ══════════════════════════════════════════════
async def callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); d = q.data

    if d == "menu": await q.message.reply_text("🏠 *Menu*", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "briefing": await cmd_briefing(update, ctx)
    elif d == "tasks":
        pending = tasks.pending()
        if not pending: await q.message.reply_text("🎉 No pending tasks!"); return
        txt = f"📋 *PENDING ({len(pending)})*\n\n"
        for t in pending[:10]:
            e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
            txt += f"{e} *#{t['id']}* {t['title']}\n"
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d == "habits":
        done, pending = habits.today_status()
        txt = "💪 *HABITS*\n\n"
        if done: txt += "✅ " + ", ".join(f"{h['emoji']}{h['name']}" for h in done) + "\n"
        if pending: txt += "⏳ " + ", ".join(h["name"] for h in pending)
        if not done and not pending: txt += "_No habits_"
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d == "expenses":
        txt = f"💰 Aaj: ₹{expenses.today_total():.0f} | Month: ₹{expenses.month_total():.0f}"
        bl = expenses.budget_left()
        if bl is not None: txt += f"\nBudget left: ₹{bl:.0f}"
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d == "news_menu": await q.message.reply_text("📰 Choose:", parse_mode="Markdown", reply_markup=news_kb())
    elif d.startswith("news_"):
        items = fetch_news(d.split("_", 1)[1], 5)
        txt = f"📰 *{d.split('_', 1)[1]} NEWS*\n\n" + "".join(f"• {i['title']}\n" for i in items)
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d == "notes":
        ns = notes.recent(8)
        txt = "📝 *NOTES*\n\n" + ("\n".join(f"#{n['id']} {n['text']}" for n in ns) if ns else "_None_")
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d == "water_status":
        total = water.today_total(); goal = water.goal()
        pct = min(100, int(total/goal*100)) if goal else 0
        await q.message.reply_text(f"💧 {total}ml / {goal}ml ({pct}%)", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💧 +250ml", callback_data="water_250"),
                 InlineKeyboardButton("💧 +500ml", callback_data="water_500")],
            ]))
    elif d.startswith("water_") and d.split("_")[1].isdigit():
        ml = int(d.split("_")[1]); water.add(ml)
        total = water.today_total()
        await q.message.reply_text(f"💧 +{ml}ml | Total: {total}ml", parse_mode="Markdown")
    elif d == "bills_menu":
        all_b = bills.all_active()
        txt = "💳 *BILLS*\n\n" + ("\n".join(f"{'✅' if bills.is_paid_this_month(b['id']) else '⏳'} {b['name']} ₹{b['amount']:.0f}" for b in all_b) if all_b else "_No bills_")
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d.startswith("billpaid_"):
        ok = bills.mark_paid(int(d.split("_")[1]))
        await q.message.reply_text("✅ Paid!" if ok else "❌ Error", parse_mode="Markdown")
    elif d == "weekly_report": await cmd_weekly_report(update, ctx)
    elif d == "memory":
        facts = mem.data.get("facts", [])
        txt = "🧠 *MEMORY*\n\n" + ("\n".join(f"📌 {f['f']}" for f in facts[-10:]) if facts else "_Empty_")
        await q.message.reply_text(txt, parse_mode="Markdown")
    elif d == "clear_chat":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Clear", callback_data="confirm_clear_chat"),
             InlineKeyboardButton("❌ Cancel", callback_data="menu")]
        ])
        await q.message.reply_text(f"Clear {chat_hist.count()} msgs?", parse_mode="Markdown", reply_markup=kb)
    elif d == "confirm_clear_chat":
        count = chat_hist.clear()
        await q.message.reply_text(f"🧹 Cleared {count} msgs! 🚀", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "confirm_nuke":
        tracked = chat_hist.get_tracked_ids(); chat_id = q.message.chat_id
        status = await q.message.reply_text("🧹 Clearing...", parse_mode="Markdown")
        deleted, failed = await delete_telegram_messages(q.get_bot(), tracked)
        chat_hist.clear(); chat_hist.clear_msg_ids()
        try: await status.delete()
        except: pass
        try: await q.message.delete()
        except: pass
        note = f"\n⚠️ {failed} old msgs not deleted" if failed else ""
        await q.get_bot().send_message(chat_id=chat_id, text=f"🧹 Done! {deleted} msgs deleted{note}", reply_markup=main_kb())
    elif d == "motivate":
        reply = await ai_chat("Motivation do Hindi mein 2 line")
        await q.message.reply_text(f"💡 {reply}", parse_mode="Markdown")
    elif d.startswith("done_"):
        t = tasks.complete(int(d.split("_")[1]))
        await q.message.reply_text(f"🎉 Done: {t['title']}" if t else "❌ Not found", parse_mode="Markdown")
    elif d.startswith("habit_"):
        hid = int(d.split("_")[1]); ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"]==hid), None)
        await q.message.reply_text(f"💪 {h['emoji']} {h['name']} 🔥{streak}d" if ok and h else "✅ Already done", parse_mode="Markdown")
    elif d.startswith("remind_done_"):
        reminders.mark_fired(int(d.split("_")[2]))
        await q.message.reply_text("✅ Done!", parse_mode="Markdown")
        try: await q.message.delete()
        except: pass
    elif d.startswith("remind_snooze_"):
        rid = int(d.split("_")[2])
        snooze = (get_indian_time() + timedelta(minutes=10)).strftime("%H:%M")
        r_list = [r for r in reminders.get_all() if r["id"] == rid]
        if r_list:
            reminders.add(q.message.chat_id, r_list[0]["text"], snooze, "once")
            reminders.mark_fired(rid)
        await q.message.reply_text(f"😴 Snoozed to {snooze}", parse_mode="Markdown")
        try: await q.message.delete()
        except: pass
    elif d.startswith("delremind_"):
        reminders.delete(int(d.split("_")[1]))
        await q.message.reply_text("🗑 Deleted!", parse_mode="Markdown")

# ══════════════════════════════════════════════
# MESSAGE HANDLER
# ══════════════════════════════════════════════
async def handle_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ai_chat(update.message.text, chat_id=update.effective_chat.id)
    try:
        sent = await update.message.reply_text(reply, parse_mode="Markdown")
    except:
        sent = await update.message.reply_text(reply)

# ══════════════════════════════════════════════
# REMINDER JOB — REAL-TIME CHECK
# ══════════════════════════════════════════════
async def reminder_job(context):
    now = get_indian_time()
    
    if now.strftime("%H:%M") == "00:00":
        reminders.reset_daily()
        log.info("🔄 Daily reminders reset")
    
    due = reminders.due_now()
    for r in due:
        try:
            repeat_note = ""
            if r["repeat"] == "daily": repeat_note = "\n🔁 _Kal bhi!_"
            
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=f"🚨⏰ *ALARM!*\n⏰ *{r['time']}*\n📢 {r['text']}{repeat_note}",
                parse_mode="Markdown",
                disable_notification=False
            )
            
            await asyncio.sleep(2)
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=f"🔔 *REMINDER:* {r['text']}\n⏰ {now.strftime('%I:%M %p')}",
                parse_mode="Markdown",
                disable_notification=False
            )
            
            reminders.mark_fired(r["id"])
            log.info(f"🔔 Fired: #{r['id']} at {now.strftime('%H:%M')}")
        except Exception as e:
            log.error(f"Reminder error #{r['id']}: {e}")

# ══════════════════════════════════════════════
# FAILED RETRY JOB
# ══════════════════════════════════════════════
async def failed_retry_job(context):
    unretried = failed_reqs.get_unretried()
    if not unretried: return
    
    log.info(f"🔄 Retrying {len(unretried)} failed...")
    for i, req in enumerate(unretried[:3]):  # Max 3 per cycle
        try:
            reply = await ai_chat(req["msg"], req["chat_id"])
            if "⚠️" not in reply:
                failed_reqs.mark_retried(i)
                try:
                    await context.bot.send_message(
                        chat_id=req["chat_id"],
                        text=f"📝 *Saved request processed!*\n\n_{reply}_",
                        parse_mode="Markdown"
                    )
                except: pass
        except Exception as e:
            log.warning(f"Retry failed: {e}")

# ══════════════════════════════════════════════
# WATER & BILL JOBS
# ══════════════════════════════════════════════
async def water_reminder_job(context):
    now = get_indian_time()
    if not (8 <= now.hour <= 22) or now.hour % 3 != 0:  # Har 3 ghante
        return
    
    total = water.today_total()
    goal = water.goal()
    if total >= goal: return
    
    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    for cid in chat_ids:
        try:
            await context.bot.send_message(
                chat_id=cid,
                text=f"💧 *Paani peena!* {total}ml / {goal}ml\n`/water` se log karo",
                parse_mode="Markdown"
            )
        except: pass

async def bill_due_alert_job(context):
    now = get_indian_time()
    if now.strftime("%H:%M") != "09:00": return
    
    due = bills.due_soon(3)
    if not due: return
    
    chat_ids = set(r["chat_id"] for r in reminders.all_active())
    if not chat_ids: return
    
    txt = "💳 *BILL DUE*\n\n" + "".join(f"⚠️ {b['name']} ₹{b['amount']:.0f}\n" for b in due)
    for cid in chat_ids:
        try: await context.bot.send_message(chat_id=cid, text=txt, parse_mode="Markdown")
        except: pass

# ══════════════════════════════════════════════
async def delete_telegram_messages(bot, tracked_ids: list) -> tuple:
    deleted, failed = 0, 0
    for entry in tracked_ids:
        try:
            await bot.delete_message(chat_id=entry["chat_id"], message_id=entry["msg_id"])
            deleted += 1
        except: failed += 1
        await asyncio.sleep(0.1)
    return deleted, failed

# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
def main():
    now = get_indian_time()
    log.info(f"🤖 Bot v4.2 — RATE LIMIT FIXED")
    log.info(f"⏰ IST: {now.strftime('%Y-%m-%d %I:%M:%S %p')}")
    log.info(f"🔑 Keys: {len(GEMINI_API_KEYS)} | Models: {len(GEMINI_MODELS)}")
    log.info(f"⏱️ Rate limit delay: {RATE_LIMIT_DELAY}s")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    commands = [
        ("start", cmd_start), ("help", lambda u,c: u.message.reply_text("All commands: /task /done /diary /habit /kharcha /goal /remind /news /water /bill /cal /weekly /clear /recall /note")),
        ("briefing", cmd_briefing), ("task", cmd_task), ("done", cmd_done),
        ("deltask", cmd_deltask), ("diary", cmd_diary), ("habit", cmd_habit),
        ("hdone", cmd_hdone), ("kharcha", cmd_kharcha), ("budget", cmd_budget),
        ("goal", cmd_goal), ("gprogress", cmd_gprogress),
        ("remember", cmd_remember), ("recall", cmd_recall),
        ("note", cmd_note), ("delnote", cmd_delnote), ("news", cmd_news),
        ("clear", cmd_clear), ("nuke", cmd_nuke),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list),
        ("delremind", cmd_delremind),
        ("water", cmd_water), ("waterstatus", cmd_water_status),
        ("watergoal", cmd_water_goal),
        ("bill", cmd_bill), ("bills", cmd_bills_list),
        ("billpaid", cmd_bill_paid), ("delbill", cmd_del_bill),
        ("cal", cmd_cal), ("calendar", cmd_cal_list), ("delcal", cmd_del_cal),
        ("weekly", cmd_weekly_report),
    ]
    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    job_queue = app.job_queue
    if job_queue is not None:
        job_queue.run_repeating(reminder_job, interval=30, first=5)
        job_queue.run_repeating(failed_retry_job, interval=300, first=60)
        job_queue.run_repeating(bill_due_alert_job, interval=3600, first=60)
        job_queue.run_repeating(water_reminder_job, interval=3600, first=300)
        log.info("⏰ Jobs started: Reminder 30s, Retry 5min, Bills/Water 1hr")
    else:
        log.warning("⚠️ JobQueue not available!")

    log.info(f"✅ Bot ready! Current IST: {get_current_time_label()}")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
