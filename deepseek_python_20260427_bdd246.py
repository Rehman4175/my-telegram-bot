#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v9.0 FINAL FIXED    ║
║  Google Sheets Backup + Secret Code + All Features║
║  Gemini → HuggingFace → Smart Offline           ║
║  IST Time | Alarm Fixed | 100% FREE | 24/7      ║
╚══════════════════════════════════════════════════╝
"""

import os, json, logging, time, asyncio, random, re as _re
import urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta, timezone
from xml.etree import ElementTree as ET

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
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as GoogleRequest
    HAS_GOOGLE_AUTH = True
except ImportError:
    HAS_GOOGLE_AUTH = False

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ══════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")
SHEET_ID = os.environ.get("SHEET_ID", "1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS", "")

SECRET_CODE = "Rk1996"

if not TELEGRAM_TOKEN:
    log.error("❌ TELEGRAM_TOKEN not set!")
    exit(1)

# ══════════════════════════════════════════════
# IST TIME
# ══════════════════════════════════════════════
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

# ══════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════
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
        if default is None: default = {}
        if self.use_mongo:
            try:
                doc = self.db[collection].find_one({"_id": "data"})
                if doc: doc.pop("_id", None); return doc
            except: pass
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
        return default

    def save(self, collection, data):
        if self.use_mongo:
            try: self.db[collection].replace_one({"_id": "data"}, {"_id": "data", **data}, upsert=True)
            except: pass
        path = os.path.join(self.data_dir, f"{collection}.json")
        try:
            with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

db = Database()

class Store:
    def __init__(self, name, default=None):
        self.name = name; self.data = db.load(name, default if default is not None else {})
    def save(self): db.save(self.name, self.data)

# ══════════════════════════════════════════════
# GOOGLE SHEETS BACKUP
# ══════════════════════════════════════════════
class GoogleSheetsBackup:
    def __init__(self):
        self.use_gsheets = bool(SHEET_ID) and bool(GOOGLE_CREDS_JSON) and HAS_GOOGLE_AUTH and HAS_REQUESTS
        self._sheets_url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}" if self.use_gsheets else ""
        self._creds = None
        if self.use_gsheets:
            try:
                creds_dict = json.loads(GOOGLE_CREDS_JSON)
                self._creds = service_account.Credentials.from_service_account_info(
                    creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]
                )
                log.info("✅ Google Sheets backup ENABLED!")
            except Exception as e:
                log.warning(f"⚠️ Google Sheets init failed: {e}"); self.use_gsheets = False
        else:
            log.info("ℹ️ Google Sheets not configured — local backup only")

    def _get_token(self):
        if not self._creds: return None
        try: self._creds.refresh(GoogleRequest()); return self._creds.token
        except: return None

    def _append(self, sheet_name, values):
        if not self.use_gsheets: return
        token = self._get_token()
        if not token: return
        try:
            url = f"{self._sheets_url}/values/{sheet_name}!A:Z:append"
            params = {"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"}
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = req_lib.post(url, params=params, headers=headers, json={"values": [values]}, timeout=10)
            if resp.status_code == 200: log.info(f"✅ Sheets: {sheet_name} updated")
            else: log.warning(f"Sheets append failed: {resp.status_code}")
        except Exception as e: log.error(f"Sheets error: {e}")

    def save_data(self, sheet_name, user_name, user_id, data_type, *extra):
        row = [today_str(), now_str(), str(user_name), str(user_id), data_type] + list(extra)
        self._append(sheet_name, row)

gsheets = GoogleSheetsBackup()

# ══════════════════════════════════════════════
# GEMINI API
# ══════════════════════════════════════════════
GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
_last_gemini = 0

def call_gemini(prompt, max_tokens=400):
    global _last_gemini
    if not GEMINI_API_KEY: return None
    now = time.time()
    if now - _last_gemini < 3: time.sleep(3 - (now - _last_gemini))
    _last_gemini = time.time()
    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.75, "maxOutputTokens": max_tokens}
    }).encode("utf-8")
    for model in GEMINI_MODELS:
        try:
            url = GEMINI_URL.format(model=model, key=GEMINI_API_KEY)
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = json.loads(resp.read().decode("utf-8"))["candidates"][0]["content"]["parts"][0]["text"]
                log.info(f"✅ Gemini: {model}"); return text.strip()
        except: continue
    return None

# ══════════════════════════════════════════════
# HUGGINGFACE
# ══════════════════════════════════════════════
HF_MODELS = ["mistralai/Mistral-7B-Instruct-v0.2", "google/gemma-2b-it"]

def call_huggingface(prompt):
    if not HAS_REQUESTS or not HF_TOKEN: return None
    for model_id in HF_MODELS:
        try:
            resp = req_lib.post(
                f"https://api-inference.huggingface.co/models/{model_id}",
                headers={"Authorization": f"Bearer {HF_TOKEN}"},
                json={"inputs": prompt, "parameters": {"max_new_tokens": 150, "temperature": 0.7}}, timeout=25
            )
            if resp.status_code == 200:
                result = resp.json()
                text = result[0].get("generated_text", "") if isinstance(result, list) else result.get("generated_text", "")
                if text and len(text) > 10: return text.replace(prompt, "").strip()
        except: continue
    return None

# ══════════════════════════════════════════════
# SMART OFFLINE
# ══════════════════════════════════════════════
def smart_fallback(msg):
    m = msg.lower(); n = now_ist()
    if any(w in m for w in ["time", "baje"]): return f"⏰ *{n.strftime('%I:%M %p')}* IST"
    if any(w in m for w in ["date", "tarikh"]): return f"📅 *{n.strftime('%A, %d %B %Y')}*"
    if any(w in m for w in ["hello", "hi", "assalam"]): return "🕌 *Assalamualaikum!* Kaise help karun?"
    return "🙏 AI busy. `/help` try karo!"

# ══════════════════════════════════════════════
# DATA STORES
# ══════════════════════════════════════════════
class MemoryStore:
    def __init__(self): self.store = Store("memory", {"facts": []})
    def add(self, text, user_name="User", user_id=0):
        facts = self.store.data.get("facts", [])
        if facts and text[:50] in [f.get("f","")[:50] for f in facts[-20:]]: return
        facts.append({"f": text, "d": today_str()})
        self.store.data["facts"] = facts[-150:]; self.store.save()
        gsheets.save_data("Memory", user_name, user_id, "MEMORY", text[:400])
    def get_all(self): return self.store.data.get("facts", [])
    def context(self):
        f = self.get_all()[-10:]
        return "\n".join(f"• {x['f']}" for x in f) if f else "Kuch nahi"

class TaskStore:
    def __init__(self): self.store = Store("tasks", {"list": [], "counter": 0})
    def _s(self): self.store.save()
    def add(self, title, priority="medium", user_name="User", user_id=0):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        t = {"id": self.store.data["counter"], "title": title, "priority": priority, "done": False, "created": today_str()}
        self.store.data["list"].append(t); self._s()
        gsheets.save_data("Tasks", user_name, user_id, "TASK", title[:200], priority)
        return t
    def complete(self, tid, user_name="User", user_id=0):
        for t in self.store.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True; t["done_date"] = today_str(); self._s()
                gsheets.save_data("Tasks", user_name, user_id, "TASK_DONE", t["title"][:200], "COMPLETED")
                return t
        return None
    def delete(self, tid): self.store.data["list"] = [t for t in self.store.data["list"] if t["id"] != tid]; self._s()
    def pending(self): return [t for t in self.store.data.get("list", []) if not t["done"]]
    def done_on(self, d): return [t for t in self.store.data.get("list", []) if t.get("done") and (t.get("done_date","") or "")[:10] == d]
    def today_pending(self):
        td = today_str()
        return [t for t in self.pending() if t.get("due", t.get("created","")) <= td]
    def all_tasks(self): return self.store.data.get("list", [])
    def completed_tasks(self): return [t for t in self.store.data.get("list", []) if t.get("done")]

class HabitStore:
    def __init__(self): self.store = Store("habits", {"list": [], "logs": {}, "counter": 0})
    def add(self, name, emoji="✅"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        h = {"id": self.store.data["counter"], "name": name, "emoji": emoji, "streak": 0}
        self.store.data["list"].append(h); self.store.save(); return h
    def log(self, hid):
        td, yd = today_str(), yesterday_str(); logs = self.store.data.get("logs", {})
        logs.setdefault(td, [])
        if hid in logs[td]: return False, 0
        logs[td].append(hid)
        for h in self.store.data.get("list", []):
            if h["id"] == hid: h["streak"] = h.get("streak", 0) + 1 if hid in logs.get(yd, []) else 1
        self.store.data["logs"] = logs; self.store.save()
        return True, next((h.get("streak", 1) for h in self.store.data["list"] if h["id"] == hid), 1)
    def all(self): return self.store.data.get("list", [])
    def today_status(self):
        done_ids = self.store.data.get("logs", {}).get(today_str(), [])
        return ([h for h in self.all() if h["id"] in done_ids], [h for h in self.all() if h["id"] not in done_ids])

class DiaryStore:
    def __init__(self): self.store = Store("diary", {"entries": {}})
    def add(self, text, mood="😊", user_name="User", user_id=0):
        td = today_str(); self.store.data.setdefault("entries", {}).setdefault(td, [])
        self.store.data["entries"][td].append({"text": text, "mood": mood, "time": now_str()}); self.store.save()
        gsheets.save_data("Diary", user_name, user_id, "DIARY", text[:300], mood)
    def get(self, d): return self.store.data.get("entries", {}).get(d, [])

class ExpenseStore:
    def __init__(self): self.store = Store("expenses", {"list": [], "budget": {}})
    def add(self, amount, desc, user_name="User", user_id=0):
        self.store.data["list"].append({"amount": amount, "desc": desc, "date": today_str(), "time": now_str()}); self.store.save()
        gsheets.save_data("Expenses", user_name, user_id, "EXPENSE", str(amount), desc[:200])
    def set_budget(self, amount): self.store.data["budget"]["monthly"] = amount; self.store.save()
    def today_total(self): return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date") == today_str())
    def month_total(self): return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date","")[:7] == today_str()[:7])
    def budget_left(self):
        b = self.store.data.get("budget", {}).get("monthly", 0); return b - self.month_total() if b else None

class GoalStore:
    def __init__(self): self.store = Store("goals", {"list": [], "counter": 0})
    def add(self, title):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        g = {"id": self.store.data["counter"], "title": title, "progress": 0, "done": False}
        self.store.data["list"].append(g); self.store.save(); return g
    def update(self, gid, pct):
        for g in self.store.data["list"]:
            if g["id"] == gid: g["progress"] = min(100, max(0, pct)); self.store.save(); return g
        return None
    def active(self): return [g for g in self.store.data.get("list", []) if not g["done"]]

class NotesStore:
    def __init__(self): self.store = Store("notes", {"list": [], "counter": 0})
    def add(self, content):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        n = {"id": self.store.data["counter"], "text": content}
        self.store.data["list"].append(n); self.store.save(); return n
    def recent(self, n=8): return self.store.data.get("list", [])[-n:]

class ReminderStore:
    def __init__(self): self.store = Store("reminders", {"list": [], "counter": 0})
    def add(self, chat_id, text, remind_at, repeat="once", user_name="User", user_id=0):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        r = {"id": self.store.data["counter"], "chat_id": chat_id, "text": text, "time": remind_at, "repeat": repeat, "active": True, "fired_today": False}
        self.store.data["list"].append(r); self.store.save()
        gsheets.save_data("Reminders", user_name, user_id, "REMINDER", remind_at, text[:200], repeat)
        log.info(f"✅ Reminder #{r['id']} | {remind_at} | {text[:30]}")
        return r
    def all_active(self): return [r for r in self.store.data.get("list", []) if r.get("active")]
    def delete(self, rid): self.store.data["list"] = [r for r in self.store.data["list"] if r["id"] != rid]; self.store.save()
    def mark_fired(self, rid):
        for r in self.store.data["list"]:
            if r["id"] == rid: r["fired_today"] = True
            if r["repeat"] == "once": r["active"] = False
            self.store.save(); break
    def reset_daily(self):
        for r in self.store.data["list"]: r["fired_today"] = False
        self.store.save()
    def due_now(self):
        now = now_ist(); due = []
        for r in self.store.data.get("list", []):
            if not r.get("active") or r.get("fired_today"): continue
            try:
                r_dt = datetime.strptime(f"{today_str()} {r['time']}", "%Y-%m-%d %H:%M")
                if 0 <= (now.replace(tzinfo=None) - r_dt).total_seconds() < 120: due.append(r)
            except: pass
        return due
    def get_all(self): return self.store.data.get("list", [])

class WaterStore:
    def __init__(self): self.store = Store("water", {"logs": {}, "goal_ml": 2000})
    def add(self, ml=250):
        td = today_str(); self.store.data.setdefault("logs", {}).setdefault(td, [])
        self.store.data["logs"][td].append({"ml": ml, "time": now_str()}); self.store.save()
    def today_total(self): return sum(e["ml"] for e in self.store.data.get("logs", {}).get(today_str(), []))
    def goal(self): return self.store.data.get("goal_ml", 2000)
    def set_goal(self, ml): self.store.data["goal_ml"] = ml; self.store.save()

class BillStore:
    def __init__(self): self.store = Store("bills", {"list": [], "counter": 0})
    def add(self, name, amount, due_day):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        b = {"id": self.store.data["counter"], "name": name, "amount": amount, "due_day": due_day, "active": True, "paid_months": []}
        self.store.data["list"].append(b); self.store.save(); return b
    def all_active(self): return [b for b in self.store.data.get("list", []) if b.get("active")]
    def mark_paid(self, bid):
        ym = today_str()[:7]
        for b in self.store.data["list"]:
            if b["id"] == bid and ym not in b.get("paid_months", []): b["paid_months"].append(ym); self.store.save(); return True
        return False
    def is_paid(self, bid):
        for b in self.store.data["list"]:
            if b["id"] == bid: return today_str()[:7] in b.get("paid_months", [])
        return False

class CalendarStore:
    def __init__(self): self.store = Store("calendar", {"events": [], "counter": 0})
    def add(self, title, event_date, event_time=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        e = {"id": self.store.data["counter"], "title": title, "date": event_date, "time": event_time}
        self.store.data["events"].append(e); self.store.save(); return e
    def today_events(self): return [e for e in self.store.data.get("events", []) if e["date"] == today_str()]

class NewsStore:
    def __init__(self): self.store = Store("news_cache", {"cache": {}, "updated": {}})
    def get(self, category="India", max_items=5):
        now_ts = time.time(); cache = self.store.data
        if category in cache.get("cache", {}) and now_ts - cache.get("updated", {}).get(category, 0) < 1800:
            return cache["cache"][category][:max_items]
        feeds = {"India": "https://feeds.bbci.co.uk/hindi/rss.xml", "Technology": "https://feeds.feedburner.com/ndtvnews-tech-news", "Business": "https://economictimes.indiatimes.com/rssfeedstopstories.cms", "World": "https://feeds.bbci.co.uk/news/world/rss.xml", "Sports": "https://feeds.bbci.co.uk/sport/rss.xml"}
        url = feeds.get(category, feeds["India"]); items = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                tree = ET.parse(resp); root = tree.getroot()
                for item in (root.find("channel") or root).findall("item")[:max_items]:
                    title = item.findtext("title", "").strip()
                    if title: items.append({"title": title, "desc": (item.findtext("description", "") or "")[:100]})
        except: items = [{"title": "News unavailable", "desc": ""}]
        cache.setdefault("cache", {})[category] = items; cache.setdefault("updated", {})[category] = now_ts; self.store.save()
        return items

class ChatHistoryStore:
    def __init__(self): self.store = Store("chat_history", {"history": [], "msg_ids": []})
    def add(self, role, content):
        self.store.data["history"].append({"role": role, "content": content})
        self.store.data["history"] = self.store.data["history"][-20:]; self.store.save()
    def track(self, chat_id, msg_id):
        self.store.data.setdefault("msg_ids", []).append({"chat_id": chat_id, "msg_id": msg_id})
        self.store.data["msg_ids"] = self.store.data["msg_ids"][-50:]; self.store.save()
    def get_tracked(self): return self.store.data.get("msg_ids", [])
    def get_recent(self, n=5): return [{"role": m["role"], "content": m["content"]} for m in self.store.data.get("history", [])[-n:]]
    def clear(self):
        count = len(self.store.data["history"]); self.store.data["history"] = []; self.store.save(); return count
    def clear_ids(self): self.store.data["msg_ids"] = []; self.store.save()
    def count(self): return len(self.store.data.get("history", []))

# ══════════════════════════════════════════════
# WEATHER + CRYPTO + FLIRTY
# ══════════════════════════════════════════════
CITIES = {"delhi": (28.61, 77.20), "mumbai": (19.07, 72.87), "bangalore": (12.97, 77.59), "kolkata": (22.57, 88.36), "chennai": (13.08, 80.27), "hyderabad": (17.38, 78.48), "pune": (18.52, 73.85), "jaipur": (26.91, 75.78), "lucknow": (26.84, 80.94), "patna": (25.59, 85.13)}

def get_weather(city="Delhi"):
    c = city.lower().strip(); lat, lon = CITIES.get(c, (28.61, 77.20))
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&timezone=Asia/Kolkata"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cw = data.get("current_weather", {}); temp = cw.get("temperature", "?"); wind = cw.get("windspeed", "?")
        wd = {0:"☀️ Saaf", 1:"⛅ Thode baadal", 2:"☁️ Baadal", 3:"☁️ Poora baadal", 45:"🌫️ Dhundh", 51:"🌦️ Halki boondein", 61:"🌧️ Baarish", 95:"⛈️ Bijli"}
        return f"🌤️ *{city.title()}*\n🌡️ {temp}°C | 💨 {wind} km/h\n📊 {wd.get(cw.get('weathercode',0),'Badal raha')}\n\n_Open-Meteo (FREE)_"
    except: return f"❌ {city} ka weather nahi mila."

CRYPTO_IDS = {"bitcoin":"bitcoin","btc":"bitcoin","ethereum":"ethereum","eth":"ethereum","dogecoin":"dogecoin","doge":"dogecoin","solana":"solana","sol":"solana"}

def get_crypto(coin="bitcoin"):
    cid = CRYPTO_IDS.get(coin.lower().strip(), coin.lower().strip())
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cid}&vs_currencies=usd,inr&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if cid in data:
            p = data[cid]; usd = p.get("usd",0); inr = p.get("inr",0); ch = p.get("usd_24h_change",0)
            return f"💰 *{coin.upper()}*\n💵 ${usd:,.2f}\n🇮🇳 ₹{inr:,.2f}\n{'📈' if ch>0 else '📉'} 24h: *{ch:+.2f}%*\n\n_CoinGecko (FREE)_"
        return f"❌ '{coin}' nahi mila."
    except: return "❌ Crypto price nahi mila."

FLIRTY = ["😊 Tumhari smile dekh kar din accha lagta hai! ☀️", "💕 Tum special ho, bas yahi kehna tha! 💖", "🌹 Tumhari yaad aayi toh message kar diya. Khayal rakhna! 💫", "✨ Aaj tum bahut achche lag rahe ho. Haan, tum! 😘", "🦋 Tumhari energy bohot positive hai. Aise hi raho! 🌈", "💝 Tumhari kindness ka impact bohot logon pe hota hai. Proud! 🏆", "🌟 Chamakte raho, duniya mein brightness tumse hai! ✨", "🎀 You're awesome! Kabhi doubt mat karna! 💪"]

def get_flirty(): return random.choice(FLIRTY)

# ══════════════════════════════════════════════
# INIT ALL
# ══════════════════════════════════════════════
memory = MemoryStore()
tasks = TaskStore()
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

# ══════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════
def build_system_prompt():
    n = time_label(); tp = tasks.today_pending()
    return f"""Tu 'Dost' AI assistant hai. Hindi/Hinglish, SHORT (2-4 lines), warm.

⚠️ REAL TIME: {n} | 📅 {today_str()}
📋 Tasks: {len(tp)} | 💰 Aaj: ₹{expenses.today_total():.0f}
🧠 Memory: {memory.context()}

RULES: Hindi/Hinglish, SHORT, TIME exact batana, "As an AI" mat bolna"""

# ══════════════════════════════════════════════
# AI PIPELINE
# ══════════════════════════════════════════════
def get_ai(user_msg):
    p = f"{build_system_prompt()}\n\nUser: {user_msg}\n\nShort Hindi reply:"
    r = call_gemini(p)
    if r: return r
    r = call_huggingface(p)
    if r: return r + "\n_⚡_"
    return smart_fallback(user_msg)

def call_action(user_msg):
    now = now_ist(); t2 = (now + timedelta(minutes=2)).strftime("%H:%M")
    p = f"""JSON router. ONLY raw JSON.
Now: {time_label()} ({now.strftime('%H:%M')}) | 2min: {t2}
{{"action":"ACT","params":{{...}},"reply":"msg"}}
ACT: REMIND(time:"{t2}",text,repeat), ADD_TASK(title,priority), ADD_EXPENSE(amount,desc), ADD_DIARY(text,mood), ADD_MEMORY(fact), ADD_HABIT(name,emoji), COMPLETE_TASK(hint), SHOW_TASKS, SHOW_ALL_TASKS, SHOW_COMPLETED_TASKS, SHOW_REMINDERS, WEATHER(city), CRYPTO(coin), FLIRT, CHAT(default)
User: {user_msg}"""
    payload = json.dumps({"contents":[{"role":"user","parts":[{"text":p}]}],"generationConfig":{"temperature":0,"maxOutputTokens":200}}).encode()
    for m in ["gemini-2.5-flash-lite","gemini-2.5-flash"]:
        try:
            url = GEMINI_URL.format(model=m, key=GEMINI_API_KEY)
            req = urllib.request.Request(url, data=payload, headers={"Content-Type":"application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = json.loads(resp.read().decode())["candidates"][0]["content"]["parts"][0]["text"].strip()
                raw = raw.replace("```json","").replace("```","").strip()
                jm = _re.search(r'\{.*\}', raw, _re.DOTALL)
                if jm: raw = jm.group(0)
                return json.loads(raw)
        except: continue
    return {"action":"CHAT","params":{},"reply":""}

async def do_action(update, ctx, action_data, chat_id, user_msg):
    action = action_data.get("action","CHAT"); params = action_data.get("params",{})
    u = update.effective_user; uname = u.first_name or "User"; uid = u.id
    now = now_ist()

    if action == "REMIND":
        ts = params.get("time",""); txt = params.get("text","⏰ Reminder!"); rp = params.get("repeat","once")
        if not ts or not _re.match(r'^\d{2}:\d{2}$', ts): return f"⏰ Format galat! Abhi *{now.strftime('%H:%M')}* hue. HH:MM use karo."
        r = reminders.add(chat_id, txt, ts, rp, uname, uid)
        return f"✅ Reminder! ⏰ *{ts}* — {txt}\n🆔 `#{r['id']}` | `/delremind {r['id']}`\n\n💾 _Sheets saved_"
    
    elif action == "ADD_TASK":
        t = tasks.add(params.get("title", user_msg[:80]), params.get("priority","medium"), uname, uid)
        return f"✅ Task: *{t['title']}*\n🆔 `#{t['id']}` | 💾 Sheets saved"
    
    elif action == "ADD_EXPENSE":
        a = float(params.get("amount",0))
        if a <= 0: return "💰 Amount batao?"
        expenses.add(a, params.get("desc","Kharcha"), uname, uid)
        return f"✅ ₹{a:.0f} — {params.get('desc','')}\n📊 Aaj: ₹{expenses.today_total():.0f} | 💾 Saved"
    
    elif action == "ADD_DIARY":
        diary.add(params.get("text", user_msg[:100]), params.get("mood","😊"), uname, uid)
        return f"📖 Diary saved! 🕐 {now_str()} | 💾 Saved"
    
    elif action == "ADD_MEMORY":
        memory.add(params.get("fact", user_msg[:200]), uname, uid)
        return "🧠 Yaad kar liya! ✅ | 💾 Sheets saved"
    
    elif action == "ADD_HABIT":
        h = habits.add(params.get("name", user_msg[:50]), params.get("emoji","✅"))
        return f"💪 Habit: {h['emoji']} *{h['name']}*\n`/hdone {h['id']}`"
    
    elif action == "COMPLETE_TASK":
        hint = params.get("title_hint","").lower(); pending = tasks.pending(); matched = None
        if hint.isdigit(): matched = next((t for t in pending if t["id"]==int(hint)), None)
        if not matched and hint: matched = next((t for t in pending if hint in t["title"].lower()), None)
        if not matched and pending: matched = pending[-1]
        if matched: tasks.complete(matched["id"], uname, uid); return f"✅ *{matched['title']}* — done! 🎉 | 💾 Saved"
        return "❓ Kaunsa task?"
    
    elif action == "SHOW_TASKS":
        p = tasks.today_pending()
        if not p: return "🎉 No pending!"
        return f"📋 *PENDING ({len(p)})*\n\n" + "".join(f"{'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} *#{t['id']}* {t['title']}\n" for t in p[:8])
    
    elif action in ["SHOW_ALL_TASKS","SHOW_COMPLETED_TASKS","SHOW_REMINDERS"]:
        if action == "SHOW_ALL_TASKS":
            p = tasks.pending(); c = tasks.completed_tasks()
            return f"📋 *ALL*\n⏳{len(p)} | ✅{len(c)}\n\n" + "⏳ "+", ".join(f"#{t['id']} {t['title'][:15]}" for t in p[:5])
        elif action == "SHOW_COMPLETED_TASKS":
            c = tasks.completed_tasks()
            return "✅ *COMPLETED*\n\n" + "".join(f"✓ #{t['id']} {t['title']}\n" for t in c[-8:]) if c else "✅ None yet!"
        else:
            a = reminders.all_active()
            return "⏰ *REMINDERS*\n\n" + "".join(f"*#{r['id']}* `{r['time']}` — {r['text']}\n" for r in a) if a else "⏰ None!"
    
    elif action == "WEATHER": return get_weather(params.get("city","Delhi"))
    elif action == "CRYPTO": return get_crypto(params.get("coin","bitcoin"))
    elif action == "FLIRT": return get_flirty()
    
    else:
        chat_hist.add("user", user_msg); r = get_ai(user_msg); chat_hist.add("assistant", r); return r

# ══════════════════════════════════════════════
# KEYBOARDS
# ══════════════════════════════════════════════
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Briefing", "briefing"), InlineKeyboardButton("📋 Tasks", "tasks")],
        [InlineKeyboardButton("💪 Habits", "habits"), InlineKeyboardButton("📖 Diary", "diary")],
        [InlineKeyboardButton("💰 Kharcha", "expenses"), InlineKeyboardButton("🧠 Memory", "memory")],
        [InlineKeyboardButton("🌤️ Weather", "weather_delhi"), InlineKeyboardButton("💕 Flirt", "flirt_msg")],
        [InlineKeyboardButton("💰 Crypto", "crypto_btc"), InlineKeyboardButton("📰 News", "news_menu")],
        [InlineKeyboardButton("📊 Weekly", "weekly_report"), InlineKeyboardButton("💡 Motivate", "motivate")],
        [InlineKeyboardButton("💾 Backup Now", "backup_now"), InlineKeyboardButton("🧹 Clear Chat", "clear_chat")],
    ])

def news_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇳 India", "news_India"), InlineKeyboardButton("💻 Tech", "news_Technology")],
        [InlineKeyboardButton("💼 Business", "news_Business"), InlineKeyboardButton("🌍 World", "news_World")],
        [InlineKeyboardButton("🏏 Sports", "news_Sports"), InlineKeyboardButton("🏠 Back", "menu")],
    ])

# ══════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════
async def cmd_start(update, ctx):
    n = now_ist(); name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(f"🕌 *Assalamualaikum {name}!*\n\n⏰ {n.strftime('%I:%M %p')} IST\n\n🌤️ Weather | 💕 Flirty | 📈 Crypto\n📋 Tasks | 💪 Habits | 📖 Diary\n💰 Expenses | ⏰ Reminders | 📰 News\n💾 Google Sheets Backup\n\n_Type or /help_ 👇", parse_mode="Markdown", reply_markup=main_kb())

async def cmd_help(update, ctx):
    await update.message.reply_text("📋 *COMMANDS*\n\n`/task` `/done` — Tasks\n`/habit` `/hdone` — Habits\n`/diary` — Diary\n`/kharcha` `/budget` — Expenses\n`/remind 2m Test` — Reminders\n`/remember` `/recall` — Memory\n🌤️ `/weather Delhi` | 💕 `/flirt` | 📈 `/crypto BTC`\n📰 `/news` | `/briefing` `/weekly`\n💾 `/backup` — Force Google Sheets backup\n🧹 `/clear` — Clear chat (data SAFE in Sheets!)\n\n_Type — AI jawab dega!_", parse_mode="Markdown")

async def cmd_task(update, ctx):
    if not ctx.args: await update.message.reply_text("📋 `/task Kaam [high/low]`"); return
    args = " ".join(ctx.args); priority = "medium"
    if args.endswith(" high"): priority = "high"; args = args[:-5].strip()
    elif args.endswith(" low"): priority = "low"; args = args[:-4].strip()
    u = update.effective_user; t = tasks.add(args, priority, u.first_name or "User", u.id)
    await update.message.reply_text(f"✅ *{t['title']}*\n🆔 `#{t['id']}` | 💾 Sheets saved", parse_mode="Markdown")

async def cmd_done(update, ctx):
    if not ctx.args: await update.message.reply_text("`/done <id>`"); return
    try:
        u = update.effective_user; t = tasks.complete(int(ctx.args[0]), u.first_name or "User", u.id)
        await update.message.reply_text(f"🎉 *Done!* {t['title']} | 💾 Saved" if t else "❌", parse_mode="Markdown")
    except: pass

async def cmd_deltask(update, ctx):
    if not ctx.args: await update.message.reply_text("`/deltask <id>`"); return
    try: tasks.delete(int(ctx.args[0])); await update.message.reply_text("🗑 Deleted!")
    except: pass

async def cmd_diary(update, ctx):
    if not ctx.args: await update.message.reply_text("📖 `/diary Text`"); return
    u = update.effective_user; diary.add(" ".join(ctx.args), "😊", u.first_name or "User", u.id)
    await update.message.reply_text(f"📖 Saved! 🕐 {now_str()} | 💾 Sheets saved")

async def cmd_habit(update, ctx):
    if not ctx.args: await update.message.reply_text("💪 `/habit Naam`"); return
    h = habits.add(" ".join(ctx.args)); await update.message.reply_text(f"💪 {h['emoji']} *{h['name']}*\n`/hdone {h['id']}`", parse_mode="Markdown")

async def cmd_hdone(update, ctx):
    if not ctx.args:
        _, p = habits.today_status()
        await update.message.reply_text("Kaunsi? " + " ".join(f"`/hdone {h['id']}`" for h in p) if p else "🎊 Sab done!"); return
    try: ok, s = habits.log(int(ctx.args[0])); await update.message.reply_text(f"💪 Done! 🔥{s}d!" if ok else "✅ Already done!")
    except: pass

async def cmd_kharcha(update, ctx):
    if not ctx.args or len(ctx.args) < 2: await update.message.reply_text("💰 `/kharcha 100 Chai`"); return
    try:
        u = update.effective_user; expenses.add(float(ctx.args[0]), " ".join(ctx.args[1:]), u.first_name or "User", u.id)
        await update.message.reply_text(f"💰 ₹{ctx.args[0]} — {' '.join(ctx.args[1:])}\n📊 Aaj: ₹{expenses.today_total():.0f} | 💾 Saved", parse_mode="Markdown")
    except: pass

async def cmd_budget(update, ctx):
    if not ctx.args: await update.message.reply_text("💳 `/budget 5000`"); return
    try: expenses.set_budget(float(ctx.args[0])); await update.message.reply_text(f"💳 Budget: ₹{ctx.args[0]}")
    except: pass

async def cmd_remember(update, ctx):
    if not ctx.args: await update.message.reply_text("🧠 `/remember Text`"); return
    u = update.effective_user; memory.add(" ".join(ctx.args), u.first_name or "User", u.id)
    await update.message.reply_text("🧠 Yaad kar liya! ✅ | 💾 Sheets saved")

async def cmd_recall(update, ctx):
    f = memory.get_all()
    await update.message.reply_text("🧠 *YAADDASHT*\n\n" + "\n".join(f"📌 {x['f']}" for x in f[-10:]) if f else "🧠 Kuch yaad nahi.", parse_mode="Markdown")

async def cmd_briefing(update, ctx):
    tp = tasks.today_pending(); n = now_ist()
    await update.message.reply_text(f"🌅 *BRIEFING*\n⏰ {n.strftime('%I:%M %p')}\n\n📋 Pending: {len(tp)}\n💰 Aaj: ₹{expenses.today_total():.0f}\n💧 Water: {water.today_total()}ml", parse_mode="Markdown", reply_markup=main_kb())

async def cmd_weekly(update, ctx):
    await update.message.reply_text(f"📊 *WEEKLY*\n📋 Pending: {len(tasks.pending())} | ✅ Done: {len(tasks.completed())}\n💰 Month: ₹{expenses.month_total():.0f}\n💪 Agli hafte aur badiya! 🚀", parse_mode="Markdown")

async def cmd_news(update, ctx):
    items = news_store.get("India", 5)
    await update.message.reply_text("📰 *INDIA KI TAAZA KHABAR*\n\n" + "".join(f"*{i+1}.* {item['title']}\n" for i, item in enumerate(items)), parse_mode="Markdown", reply_markup=news_kb())

async def cmd_weather(update, ctx):
    city = " ".join(ctx.args) if ctx.args else "Delhi"
    await update.message.reply_text(get_weather(city), parse_mode="Markdown")

async def cmd_flirt(update, ctx): await update.message.reply_text(get_flirty(), parse_mode="Markdown")

async def cmd_crypto(update, ctx):
    coin = ctx.args[0] if ctx.args else "bitcoin"
    await update.message.reply_text(get_crypto(coin), parse_mode="Markdown")

async def cmd_remind(update, ctx):
    now = now_ist()
    if not ctx.args:
        await update.message.reply_text(f"⏰ *REMINDER*\nAbhi: *{now.strftime('%I:%M %p')}*\n\n`/remind 2m Test` | `/remind 15:30 Doctor`", parse_mode="Markdown"); return
    time_arg = ctx.args[0].lower(); rest = ctx.args[1:]; repeat = "once"
    if rest and rest[-1].lower() == "daily": repeat = "daily"; rest = rest[:-1]
    text = " ".join(rest) if rest else "⏰ Reminder!"
    ts = None
    if time_arg.endswith("m") and time_arg[:-1].isdigit(): ts = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        p = time_arg.split(":")
        if len(p)==2 and p[0].isdigit() and p[1].isdigit(): ts = f"{int(p[0]):02d}:{int(p[1]):02d}"
    if not ts: await update.message.reply_text(f"❌ Format! `/remind 2m Test`"); return
    u = update.effective_user; r = reminders.add(update.effective_chat.id, text, ts, repeat, u.first_name or "User", u.id)
    await update.message.reply_text(f"✅ Set! ⏰ *{ts}* — {text}\n🆔 `#{r['id']}` | 💾 Sheets saved", parse_mode="Markdown")

async def cmd_reminders_list(update, ctx):
    a = reminders.all_active()
    await update.message.reply_text("⏰ *REMINDERS*\n\n" + "".join(f"*#{r['id']}* `{r['time']}` — {r['text']}\n" for r in a) if a else f"⏰ None!\n`/remind 2m Test`", parse_mode="Markdown")

async def cmd_delremind(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delremind <id>`"); return
    try: await update.message.reply_text("🗑 Deleted!" if reminders.delete(int(ctx.args[0])) else "❌")
    except: pass

async def cmd_water(update, ctx):
    ml = 250
    if ctx.args:
        try: ml = int(ctx.args[0])
        except: pass
    water.add(ml); await update.message.reply_text(f"💧 +{ml}ml | {water.today_total()}ml/{water.goal()}ml")

async def cmd_water_goal(update, ctx):
    if not ctx.args: await update.message.reply_text(f"Current: {water.goal()}ml"); return
    try: water.set_goal(int(ctx.args[0])); await update.message.reply_text(f"✅ Goal: {ctx.args[0]}ml")
    except: pass

async def cmd_bill(update, ctx):
    if not ctx.args or len(ctx.args)<3: await update.message.reply_text("💳 `/bill Naam Amount Tarikh`"); return
    try: b = bills.add(ctx.args[0], float(ctx.args[1]), int(ctx.args[2])); await update.message.reply_text(f"✅ {b['name']} ₹{b['amount']:.0f}")
    except: pass

async def cmd_bills_list(update, ctx):
    ab = bills.all_active()
    await update.message.reply_text("💳 *BILLS*\n\n" + "".join(f"{'✅' if bills.is_paid(b['id']) else '⏳'} {b['name']} ₹{b['amount']:.0f}\n" for b in ab) if ab else "💳 No bills!", parse_mode="Markdown")

async def cmd_bill_paid(update, ctx):
    if not ctx.args: await update.message.reply_text("`/billpaid <id>`"); return
    try: await update.message.reply_text("✅ Paid!" if bills.mark_paid(int(ctx.args[0])) else "❌")
    except: pass

async def cmd_cal(update, ctx):
    if not ctx.args: await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`"); return
    args_str = " ".join(ctx.args); date_str = today_str(); title = args_str
    m = _re.match(r'^(\d{4}-\d{2}-\d{2})\s+(.*)', args_str)
    if m: date_str = m.group(1); title = m.group(2)
    try:
        date.fromisoformat(date_str); calendar.add(title, date_str)
        await update.message.reply_text(f"📅 {title} — {date_str}", parse_mode="Markdown")
    except: await update.message.reply_text("❌ Invalid date")

async def cmd_cal_list(update, ctx):
    up = calendar.upcoming(30)
    await update.message.reply_text("📅 *UPCOMING*\n\n" + "".join(f"{'🔴' if e['date']==today_str() else '📆'} {e['date']} — {e['title']}\n" for e in up[:10]) if up else "📅 No events!", parse_mode="Markdown")

async def cmd_goal(update, ctx):
    if not ctx.args: await update.message.reply_text("🎯 `/goal Goal`"); return
    g = goals.add(" ".join(ctx.args)); await update.message.reply_text(f"🎯 *{g['title']}*", parse_mode="Markdown")

async def cmd_gprogress(update, ctx):
    try: g = goals.update(int(ctx.args[0]), int(ctx.args[1])); await update.message.reply_text(f"📊 *{g['title']}* — {ctx.args[1]}%" if g else "❌", parse_mode="Markdown")
    except: pass

async def cmd_alltasks(update, ctx):
    p = tasks.pending(); c = tasks.completed_tasks()
    await update.message.reply_text(f"📋 *ALL TASKS*\n⏳{len(p)} | ✅{len(c)}", parse_mode="Markdown")

async def cmd_completed(update, ctx):
    c = tasks.completed_tasks()
    await update.message.reply_text("✅ *COMPLETED*\n\n" + "".join(f"✓ #{t['id']} {t['title']}\n" for t in c[-10:]) if c else "✅ None!", parse_mode="Markdown")

async def cmd_yesterday(update, ctx):
    d = tasks.done_on(yesterday_str())
    await update.message.reply_text(f"📅 *YESTERDAY*\n\n" + (f"✅ {len(d)} tasks done\n" + "".join(f"• {t['title']}\n" for t in d[:5])) if d else "No data", parse_mode="Markdown")

# ══════════════════════════════════════════════
# 🔥 BACKUP COMMAND
# ══════════════════════════════════════════════
async def cmd_backup(update, ctx):
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    u = update.effective_user; uname = u.first_name or "User"; uid = u.id
    for t in tasks.all_tasks(): gsheets.save_data("Tasks", uname, uid, "BACKUP_TASK", t["title"][:200], t.get("priority",""), "✅" if t.get("done") else "⏳")
    for r in reminders.all_active(): gsheets.save_data("Reminders", uname, uid, "BACKUP_REMINDER", r["time"], r["text"][:200], r.get("repeat",""))
    for f in memory.get_all()[-10:]: gsheets.save_data("Memory", uname, uid, "BACKUP_MEMORY", f["f"][:400])
    gsheets.save_data("Daily_Logs", uname, uid, "BACKUP", f"Full backup at {now_ist().strftime('%I:%M %p')}")
    await update.message.reply_text("💾 *BACKUP COMPLETE!*\n\n✅ Google Sheets mein sab save ho gaya!\n✅ Reminders, Tasks, Memory — sab safe!\n🔒 _Chat clear hone ke baad bhi data rahega!_", parse_mode="Markdown")

# ══════════════════════════════════════════════
# 🔥 CHAT CLEAR WITH BACKUP
# ══════════════════════════════════════════════
async def cmd_clear(update, ctx):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Backup + Clear", "backup_clear"), InlineKeyboardButton("🧹 Just Clear", "confirm_clear_chat")],
        [InlineKeyboardButton("❌ Cancel", "menu")]
    ])
    await update.message.reply_text(f"🧹 *CHAT CLEAR OPTIONS*\n\n📊 {chat_hist.count()} messages\n\n💾 *Backup + Clear:* Sheets save, fir chat clear\n🧹 *Just Clear:* Sirf chat, data Sheets mein hai\n\n✅ Reminders, Tasks, Memory — *Sheets mein SAFE!*\n🔒 `/recall` `/reminders` `/alltasks` chalega!", parse_mode="Markdown", reply_markup=kb)

# ══════════════════════════════════════════════
# 🔥 SECRET COMMANDS
# ══════════════════════════════════════════════
def check_secret(a): return a and a[0] == SECRET_CODE

async def cmd_tasklogs(update, ctx):
    if not check_secret(ctx.args): await update.message.reply_text("🔒"); return
    all_t = tasks.all_tasks(); p = tasks.pending(); c = tasks.completed_tasks()
    txt = f"📋 *TASK LOGS ({len(all_t)})*\n\n⏳ *Pending ({len(p)}):*\n" + "".join(f"  #{t['id']} {t['title'][:40]}\n" for t in p[-10:])
    txt += f"\n✅ *Completed ({len(c)}):*\n" + "".join(f"  #{t['id']} {t['title'][:40]}\n" for t in c[-10:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_fulldata(update, ctx):
    if not check_secret(ctx.args): await update.message.reply_text("🔒"); return
    txt = f"📊 *FULL DATA*\n\n🧠 Facts: {len(memory.get_all())}\n📋 Tasks: {len(tasks.all_tasks())}\n💪 Habits: {len(habits.all())}\n⏰ Reminders: {len(reminders.all_active())}\n💰 Month: ₹{expenses.month_total():.0f}\n💧 Water: {water.today_total()}ml\n📖 Diary: {len(diary.get(today_str()))}\n\n💾 Sheets: {'CONNECTED' if gsheets.use_gsheets else 'NOT CONNECTED'}"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_allreminders(update, ctx):
    if not check_secret(ctx.args): await update.message.reply_text("🔒"); return
    all_r = reminders.get_all(); txt = f"⏰ *ALL REMINDERS ({len(all_r)})*\n\n"
    for r in all_r: txt += f"*#{r['id']}* `{r['time']}` — {r['text'][:40]} _{'✅ Active' if r.get('active') else '❌ Done' if r.get('fired_today') else '⏳ Pending'}_\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

# ══════════════════════════════════════════════
# CALLBACK HANDLER
# ══════════════════════════════════════════════
async def callback_handler(update, ctx):
    q = update.callback_query; await q.answer(); d = q.data
    u = update.effective_user; uname = u.first_name or "User"; uid = u.id

    if d == "menu": await q.message.reply_text("🏠 *Menu*", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "briefing": await cmd_briefing(update, ctx)
    elif d == "tasks":
        p = tasks.pending()
        await q.message.reply_text("📋 *PENDING*\n\n" + "".join(f"{'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} *#{t['id']}* {t['title']}\n" for t in p[:8]) if p else "🎉 No pending!", parse_mode="Markdown")
    elif d == "habits":
        done, pend = habits.today_status()
        done_str = ", ".join(f"{h['emoji']}{h['name']}" for h in done)
        pend_str = ", ".join(h['name'] for h in pend)
        await q.message.reply_text(f"💪 *HABITS*\n✅ {done_str}\n⏳ {pend_str}", parse_mode="Markdown")
    elif d == "diary":
        td = diary.get(today_str())
        await q.message.reply_text("📖 *DIARY*\n\n" + ("\n".join(f"{e['time']} {e['text']}" for e in td[-3:])) if td else "_No entries_", parse_mode="Markdown")
    elif d == "expenses": await q.message.reply_text(f"💰 Aaj: ₹{expenses.today_total():.0f} | Month: ₹{expenses.month_total():.0f}")
    elif d == "memory":
        f = memory.get_all(); txt_str = "\n".join(f"📌 {x['f']}" for x in f[-10:]) if f else "_Empty_"
        await q.message.reply_text(f"🧠 *MEMORY*\n\n{txt_str}", parse_mode="Markdown")
    elif d == "news_menu": await q.message.reply_text("📰 Category:", parse_mode="Markdown", reply_markup=news_kb())
    elif d.startswith("news_"):
        items = news_store.get(d.split("_",1)[1], 5)
        await q.message.reply_text("📰 *NEWS*\n\n" + "".join(f"• {i['title']}\n" for i in items), parse_mode="Markdown")
    elif d == "weather_delhi": await q.message.reply_text(get_weather("Delhi"), parse_mode="Markdown")
    elif d == "flirt_msg": await q.message.reply_text(get_flirty(), parse_mode="Markdown")
    elif d == "crypto_btc": await q.message.reply_text(get_crypto("bitcoin"), parse_mode="Markdown")
    elif d == "weekly_report": await cmd_weekly(update, ctx)
    elif d == "backup_now": await cmd_backup(update, ctx)
    elif d == "backup_clear":
        await cmd_backup(update, ctx); await asyncio.sleep(1)
        count = chat_hist.clear()
        await q.message.reply_text(f"💾 *Backup done + Chat cleared!*\n🗑 {count} msgs deleted\n✅ Data Google Sheets mein safe!", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "confirm_clear_chat":
        count = chat_hist.clear()
        await q.message.reply_text(f"🧹 *Cleared!*\n🗑 {count} msgs\n✅ Data Sheets mein safe hai!\n`/recall` `/alltasks` `/reminders` se dekho", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "motivate":
        r = get_ai("Powerful Hindi motivation 2 lines")
        await q.message.reply_text(f"💡 *Motivation:*\n\n{r}", parse_mode="Markdown")
    elif d.startswith("done_"):
        t = tasks.complete(int(d.split("_")[1]), uname, uid)
        await q.message.reply_text(f"🎉 Done: {t['title']} | 💾 Saved" if t else "❌", parse_mode="Markdown")
    elif d.startswith("habit_"):
        hid = int(d.split("_")[1]); ok, s = habits.log(hid)
        await q.message.reply_text(f"💪 Done! 🔥{s}d!" if ok else "✅ Already done!")
    elif d.startswith("remind_done_"):
        reminders.mark_fired(int(d.split("_")[2])); await q.message.reply_text("✅ Done!")
        try: await q.message.delete()
        except: pass
    elif d.startswith("remind_snooze_"):
        rid = int(d.split("_")[2]); snooze = (now_ist()+timedelta(minutes=10)).strftime("%H:%M")
        rl = [r for r in reminders.get_all() if r["id"]==rid]
        if rl: reminders.add(q.message.chat_id, rl[0]["text"], snooze, "once"); reminders.mark_fired(rid)
        await q.message.reply_text(f"😴 Snoozed to {snooze}")
        try: await q.message.delete()
        except: pass
    elif d.startswith("delremind_"): reminders.delete(int(d.split("_")[1])); await q.message.reply_text("🗑 Deleted!")

# ══════════════════════════════════════════════
# MESSAGE HANDLER
# ══════════════════════════════════════════════
async def handle_message(update, ctx):
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    ad = call_action(update.message.text)
    reply = await do_action(update, ctx, ad, update.effective_chat.id, update.message.text)
    try: await update.message.reply_text(reply, parse_mode="Markdown")
    except: await update.message.reply_text(reply)

# ══════════════════════════════════════════════
# REMINDER JOB
# ══════════════════════════════════════════════
async def reminder_job(context):
    now = now_ist()
    if now.strftime("%H:%M") in ("00:00","00:01"): reminders.reset_daily()
    for r in reminders.due_now():
        try:
            await context.bot.send_message(chat_id=r["chat_id"], text=f"🚨⏰ *ALARM!*\n⏰ {r['time']}\n📢 {r['text']}", parse_mode="Markdown", disable_notification=False)
            await asyncio.sleep(2)
            await context.bot.send_message(chat_id=r["chat_id"], text=f"🔔 *REMINDER:* {r['text']}\n⏰ {now.strftime('%I:%M %p')} IST", parse_mode="Markdown")
            reminders.mark_fired(r["id"])
            log.info(f"🔔 FIRED: #{r['id']}")
        except Exception as e: log.error(f"Reminder fail: {e}")

async def delete_msgs(bot, tracked):
    d = 0
    for e in tracked:
        try: await bot.delete_message(chat_id=e["chat_id"], message_id=e["msg_id"]); d += 1
        except: pass
        await asyncio.sleep(0.1)
    return d, 0

# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
def main():
    n = now_ist()
    log.info(f"🤖 Bot v9.0 FINAL | ⏰ {n.strftime('%Y-%m-%d %I:%M:%S %p')} IST")
    log.info(f"🔑 Gemini: {'YES' if GEMINI_API_KEY else 'NO'} | 🤗 HF: {'YES' if HF_TOKEN else 'NO'} | 💾 Sheets: {'YES' if gsheets.use_gsheets else 'NO'} | 💾 MongoDB: {'YES' if HAS_MONGO and MONGO_URI else 'NO'}")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    cmds = [
        ("start", cmd_start), ("help", cmd_help), ("task", cmd_task), ("done", cmd_done),
        ("deltask", cmd_deltask), ("diary", cmd_diary), ("habit", cmd_habit), ("hdone", cmd_hdone),
        ("kharcha", cmd_kharcha), ("budget", cmd_budget), ("remember", cmd_remember),
        ("recall", cmd_recall), ("briefing", cmd_briefing), ("weekly", cmd_weekly),
        ("news", cmd_news), ("weather", cmd_weather), ("flirt", cmd_flirt), ("crypto", cmd_crypto),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list), ("delremind", cmd_delremind),
        ("water", cmd_water), ("watergoal", cmd_water_goal), ("bill", cmd_bill), ("bills", cmd_bills_list),
        ("billpaid", cmd_bill_paid), ("cal", cmd_cal), ("calendar", cmd_cal_list),
        ("goal", cmd_goal), ("gprogress", cmd_gprogress), ("alltasks", cmd_alltasks),
        ("completed", cmd_completed), ("yesterday", cmd_yesterday),
        ("backup", cmd_backup), ("clear", cmd_clear),
        ("tasklogs", cmd_tasklogs), ("fulldata", cmd_fulldata), ("allreminders", cmd_allreminders),
    ]
    for c, h in cmds: app.add_handler(CommandHandler(c, h))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=30, first=5)
        log.info("⏰ Reminder job started (30s)")

    log.info("✅ Bot ready! Telegram pe /start karo.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()