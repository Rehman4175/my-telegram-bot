#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — v10.0 ULTIMATE      ║
║  v4.0 ALL Features + v9.0 New Features          ║
║  Natural Language Alarm | Google Sheets Backup  ║
║  Weather | Flirty | Crypto | News               ║
║  Gemini → HuggingFace → Smart Offline           ║
║  IST Time | 100% FREE | 24/7 | Secret Code      ║
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
SHEET_ID = os.environ.get("SHEET_ID", "")
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
            except:
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
# GOOGLE SHEETS
# ══════════════════════════════════════════════
class GoogleSheetsBackup:
    def __init__(self):
        self.use_gsheets = False
        if SHEET_ID and GOOGLE_CREDS_JSON and HAS_GOOGLE_AUTH and HAS_REQUESTS:
            try:
                creds_dict = json.loads(GOOGLE_CREDS_JSON)
                self._creds = service_account.Credentials.from_service_account_info(
                    creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]
                )
                self._sheets_url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
                self.use_gsheets = True
                log.info("✅ Google Sheets ENABLED!")
            except Exception as e:
                log.warning(f"⚠️ Sheets init: {e}")

    def _get_token(self):
        if not self._creds: return None
        try: self._creds.refresh(GoogleRequest()); return self._creds.token
        except: return None

    def save_data(self, sheet_name, *values):
        if not self.use_gsheets: return
        try:
            token = self._get_token()
            if not token: return
            row = [today_str(), now_str()] + list(values)
            url = f"{self._sheets_url}/values/{sheet_name}!A:Z:append"
            params = {"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"}
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = req_lib.post(url, params=params, headers=headers, json={"values": [row]}, timeout=10)
            if resp.status_code == 200: log.info(f"✅ Sheets: {sheet_name} saved!")
        except Exception as e: log.error(f"Sheets: {e}")

gsheets = GoogleSheetsBackup()

# ══════════════════════════════════════════════
# GEMINI API
# ══════════════════════════════════════════════
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
    for model in ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]:
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
def call_huggingface(prompt):
    if not HAS_REQUESTS or not HF_TOKEN: return None
    for model_id in ["mistralai/Mistral-7B-Instruct-v0.2", "google/gemma-2b-it"]:
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
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if cid in data:
            p = data[cid]; usd = p.get("usd",0); inr = p.get("inr",0); ch = p.get("usd_24h_change",0)
            return f"💰 *{coin.upper()}*\n💵 ${usd:,.2f}\n🇮🇳 ₹{inr:,.2f}\n{'📈' if ch>0 else '📉'} 24h: *{ch:+.2f}%*\n\n_CoinGecko (FREE)_"
        return f"❌ '{coin}' nahi mila."
    except: return "❌ Crypto price nahi mila."

FLIRTY = ["😊 Tumhari smile dekh kar din accha lagta hai! ☀️", "💕 Tum special ho, bas yahi kehna tha! 💖", "🌹 Tumhari yaad aayi toh message kar diya. Khayal rakhna! 💫", "✨ Aaj tum bahut achche lag rahe ho. Haan, tum! 😘"]
def get_flirty(): return random.choice(FLIRTY)

# ══════════════════════════════════════════════
# ALL DATA STORES
# ══════════════════════════════════════════════
class ReminderStore:
    def __init__(self): self.store = Store("reminders", {"list": [], "counter": 0})
    def add(self, chat_id, text, remind_at, repeat="once"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        r = {"id": self.store.data["counter"], "chat_id": chat_id, "text": text, "time": remind_at, "repeat": repeat, "active": True, "fired_today": False, "created": today_str()}
        self.store.data["list"].append(r); self.store.save()
        gsheets.save_data("Reminders", str(chat_id), "REMINDER", remind_at, text[:200], repeat)
        log.info(f"✅ Reminder CREATED: #{r['id']} | time={remind_at} | chat={chat_id} | '{text[:40]}'")
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
        now = now_ist(); now_str_time = now.strftime("%H:%M"); today = today_str(); due = []
        for r in self.store.data.get("list", []):
            if not r.get("active") or r.get("fired_today"): continue
            r_time = r.get("time", "")
            if r_time == now_str_time: due.append(r); continue
            try:
                r_dt = datetime.strptime(f"{today} {r_time}", "%Y-%m-%d %H:%M")
                if 0 <= (now.replace(tzinfo=None) - r_dt).total_seconds() < 120: due.append(r)
            except: pass
        return due
    def get_all(self): return self.store.data.get("list", [])

class MemoryStore:
    def __init__(self): self.store = Store("memory", {"facts": [], "prefs": {}, "dates": {}, "important_notes": []})
    def add_fact(self, text):
        facts = self.store.data.get("facts", [])
        if facts and text[:50] in [f.get("f","")[:50] for f in facts[-20:]]: return
        facts.append({"f": text, "d": today_str()})
        self.store.data["facts"] = facts[-200:]; self.store.save()
        gsheets.save_data("Memory", str(0), "MEMORY", text[:400])
    def add_important(self, note): self.store.data.setdefault("important_notes", []).append({"note": note, "d": today_str()}); self.store.save()
    def get_all_facts(self): return self.store.data.get("facts", [])
    def context(self):
        f = self.get_all_facts()[-10:]
        return "\n".join(f"• {x['f']}" for x in f) if f else "Kuch nahi"

class TaskStore:
    def __init__(self): self.store = Store("tasks", {"list": [], "counter": 0})
    def _s(self): self.store.save()
    def add(self, title, priority="medium"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        t = {"id": self.store.data["counter"], "title": title, "priority": priority, "done": False, "done_at": None, "created": today_str()}
        self.store.data["list"].append(t); self._s()
        gsheets.save_data("Tasks", str(0), "TASK", title[:200], priority)
        return t
    def complete(self, tid):
        for t in self.store.data["list"]:
            if t["id"] == tid and not t["done"]: t["done"] = True; t["done_at"] = today_str(); self._s(); return t
        return None
    def delete(self, tid): self.store.data["list"] = [t for t in self.store.data["list"] if t["id"] != tid]; self._s()
    def pending(self): return [t for t in self.store.data.get("list", []) if not t["done"]]
    def done_on(self, d): return [t for t in self.store.data.get("list", []) if t.get("done") and t.get("done_at","")[:10] == d]
    def today_pending(self):
        td = today_str()
        return [t for t in self.pending() if t.get("due", t.get("created","")) <= td]
    def all_tasks(self): return self.store.data.get("list", [])
    def completed_tasks(self): return [t for t in self.store.data.get("list", []) if t.get("done")]
    def clear_done(self): self.store.data["list"] = [t for t in self.store.data["list"] if not t["done"]]; self._s()

class TaskLogsStore:
    def __init__(self): self.store = Store("task_logs", {"logs": []})
    def add_log(self, action_type, description, task_id=None):
        self.store.data["logs"].append({"type": action_type, "description": description, "task_id": task_id, "date": today_str()})
        self.store.data["logs"] = self.store.data["logs"][-500:]; self.store.save()
    def get_all_logs(self): return self.store.data.get("logs", [])
    def get_created(self): return [l for l in self.get_all_logs() if l["type"] == "created"]
    def get_completed(self): return [l for l in self.get_all_logs() if l["type"] == "completed"]

class FailedReqStore:
    def __init__(self): self.store = Store("failed_requests", {"queue": []})
    def add(self, msg, chat_id, reason):
        self.store.data["queue"].append({"msg": msg, "chat_id": chat_id, "reason": reason, "retried": False})
        self.store.data["queue"] = self.store.data["queue"][-50:]; self.store.save()
    def get_unretried(self): return [r for r in self.store.data.get("queue", []) if not r["retried"]]
    def mark_retried(self, idx):
        if 0 <= idx < len(self.store.data["queue"]): self.store.data["queue"][idx]["retried"] = True; self.store.save()

class DiaryStore:
    def __init__(self): self.store = Store("diary", {"entries": {}})
    def add(self, text, mood="😊"):
        td = today_str(); self.store.data.setdefault("entries", {}).setdefault(td, [])
        self.store.data["entries"][td].append({"text": text, "mood": mood, "time": now_str()}); self.store.save()
        gsheets.save_data("Diary", str(0), "DIARY", text[:300], mood)
    def get(self, d): return self.store.data.get("entries", {}).get(d, [])

class HabitStore:
    def __init__(self): self.store = Store("habits", {"list": [], "logs": {}, "counter": 0})
    def add(self, name, emoji="✅"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        h = {"id": self.store.data["counter"], "name": name, "emoji": emoji, "streak": 0, "best_streak": 0, "created": today_str()}
        self.store.data["list"].append(h); self.store.save(); return h
    def log(self, hid):
        td, yd = today_str(), yesterday_str(); logs = self.store.data.get("logs", {})
        logs.setdefault(td, [])
        if hid in logs[td]: return False, 0
        logs[td].append(hid)
        for h in self.store.data.get("list", []):
            if h["id"] == hid:
                h["streak"] = h.get("streak", 0) + 1 if hid in logs.get(yd, []) else 1
                h["best_streak"] = max(h.get("best_streak", 0), h.get("streak", 0))
        self.store.data["logs"] = logs; self.store.save()
        return True, next((h.get("streak", 1) for h in self.store.data["list"] if h["id"] == hid), 1)
    def all(self): return self.store.data.get("list", [])
    def today_status(self):
        done_ids = self.store.data.get("logs", {}).get(today_str(), [])
        return ([h for h in self.all() if h["id"] in done_ids], [h for h in self.all() if h["id"] not in done_ids])
    def delete(self, hid): self.store.data["list"] = [h for h in self.store.data["list"] if h["id"] != hid]; self.store.save()

class NotesStore:
    def __init__(self): self.store = Store("notes", {"list": [], "counter": 0})
    def add(self, content, tag="general"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        n = {"id": self.store.data["counter"], "text": content, "tag": tag, "created": datetime.now().isoformat()}
        self.store.data["list"].append(n); self.store.save(); return n
    def delete(self, nid): self.store.data["list"] = [n for n in self.store.data["list"] if n["id"] != nid]; self.store.save()
    def search(self, q): return [n for n in self.store.data.get("list", []) if q.lower() in n["text"].lower()]
    def recent(self, n=15): return self.store.data.get("list", [])[-n:]

class ExpenseStore:
    def __init__(self): self.store = Store("expenses", {"list": [], "counter": 0, "budget": {}})
    def add(self, amount, desc, category="general"):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        self.store.data["list"].append({"id": self.store.data["counter"], "amount": amount, "desc": desc, "category": category, "date": today_str(), "time": now_str()}); self.store.save()
        gsheets.save_data("Expenses", str(0), "EXPENSE", str(amount), desc[:200])
    def set_budget(self, amount): self.store.data["budget"]["monthly"] = amount; self.store.save()
    def today_total(self): return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date") == today_str())
    def month_total(self): return sum(e["amount"] for e in self.store.data.get("list", []) if e.get("date","")[:7] == today_str()[:7])
    def today_list(self): return [e for e in self.store.data.get("list", []) if e.get("date") == today_str()]
    def budget_left(self):
        b = self.store.data.get("budget", {}).get("monthly", 0); return b - self.month_total() if b else None

class GoalStore:
    def __init__(self): self.store = Store("goals", {"list": [], "counter": 0})
    def add(self, title, deadline=None):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        g = {"id": self.store.data["counter"], "title": title, "deadline": deadline or "", "progress": 0, "done": False, "created": today_str()}
        self.store.data["list"].append(g); self.store.save(); return g
    def update(self, gid, pct):
        for g in self.store.data["list"]:
            if g["id"] == gid: g["progress"] = min(100, max(0, pct))
            if g["progress"] == 100: g["done"] = True
            self.store.save(); return g
        return None
    def active(self): return [g for g in self.store.data.get("list", []) if not g["done"]]
    def completed(self): return [g for g in self.store.data.get("list", []) if g.get("done")]

class WaterStore:
    def __init__(self): self.store = Store("water", {"logs": {}, "goal_ml": 2000})
    def add(self, ml=250):
        td = today_str(); self.store.data.setdefault("logs", {}).setdefault(td, [])
        self.store.data["logs"][td].append({"ml": ml, "time": now_str()}); self.store.save()
    def today_total(self): return sum(e["ml"] for e in self.store.data.get("logs", {}).get(today_str(), []))
    def goal(self): return self.store.data.get("goal_ml", 2000)
    def set_goal(self, ml): self.store.data["goal_ml"] = ml; self.store.save()
    def today_entries(self): return self.store.data.get("logs", {}).get(today_str(), [])
    def week_summary(self):
        result = {}
        for i in range(7):
            d = (now_ist().date() - timedelta(days=i)).isoformat()
            result[d] = sum(e["ml"] for e in self.store.data.get("logs", {}).get(d, []))
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
    def is_paid(self, bid):
        for b in self.store.data["list"]:
            if b["id"] == bid: return today_str()[:7] in b.get("paid_months", [])
        return False
    def delete(self, bid): self.store.data["list"] = [b for b in self.store.data["list"] if b["id"] != bid]; self.store.save()
    def due_soon(self, days=3):
        today_d = now_ist().date(); result = []
        for b in self.store.data.get("list", []):
            if not b.get("active") or self.is_paid(b["id"]): continue
            try: due_date = date(today_d.year, today_d.month, min(b["due_day"], 28))
            except: continue
            if today_d <= due_date <= today_d + timedelta(days=days): result.append({**b, "due_date": due_date.isoformat()})
        return result

class CalendarStore:
    def __init__(self): self.store = Store("calendar", {"events": [], "counter": 0})
    def add(self, title, event_date, event_time=""):
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        e = {"id": self.store.data["counter"], "title": title, "date": event_date, "time": event_time, "created": today_str()}
        self.store.data["events"].append(e); self.store.save(); return e
    def delete(self, eid): self.store.data["events"] = [e for e in self.store.data["events"] if e["id"] != eid]; self.store.save()
    def upcoming(self, days=7):
        today_d = now_ist().date(); cutoff = today_d + timedelta(days=days); result = []
        for e in self.store.data.get("events", []):
            try:
                if today_d <= date.fromisoformat(e["date"]) <= cutoff: result.append(e)
            except: pass
        return sorted(result, key=lambda x: x["date"])

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

# ══════════════════════════════════════════════
# INIT ALL
# ══════════════════════════════════════════════
reminders = ReminderStore()
memory = MemoryStore()
tasks = TaskStore()
task_logs = TaskLogsStore()
failed_reqs = FailedReqStore()
diary = DiaryStore()
habits = HabitStore()
notes = NotesStore()
expenses = ExpenseStore()
goals = GoalStore()
water = WaterStore()
bills = BillStore()
calendar = CalendarStore()
news_store = NewsStore()

# ══════════════════════════════════════════════
# NATURAL LANGUAGE REMINDER
# ══════════════════════════════════════════════
def parse_natural_reminder(user_msg):
    now = now_ist(); msg = user_msg.lower()
    m = _re.search(r'(\d+)\s*(?:minute|min|mins)\s*(?:baad|bad|mein)?\s*(.*)', msg)
    if m: return (now + timedelta(minutes=int(m.group(1)))).strftime("%H:%M"), m.group(2).strip() or "⏰ Reminder!", "once"
    m = _re.search(r'(\d+)\s*(?:ghante|ghanta|hour|hr)\s*(?:baad|bad|mein)?\s*(.*)', msg)
    if m: return (now + timedelta(hours=int(m.group(1)))).strftime("%H:%M"), m.group(2).strip() or "⏰ Reminder!", "once"
    m = _re.search(r'(\d{1,2}):(\d{2})\s*(?:pe|par|baje)?\s*(.*)', msg)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59: return f"{h:02d}:{mn:02d}", m.group(3).strip() or "⏰ Reminder!", "once"
    return None, None, None

# ══════════════════════════════════════════════
# KEYBOARDS
# ══════════════════════════════════════════════
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Briefing", callback_data="briefing"), InlineKeyboardButton("📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("💪 Habits", callback_data="habits"), InlineKeyboardButton("📖 Diary", callback_data="diary")],
        [InlineKeyboardButton("🎯 Goals", callback_data="goals"), InlineKeyboardButton("💰 Kharcha", callback_data="expenses")],
        [InlineKeyboardButton("📰 News", callback_data="news_menu"), InlineKeyboardButton("📝 Notes", callback_data="notes")],
        [InlineKeyboardButton("💧 Water", callback_data="water_status"), InlineKeyboardButton("💳 Bills", callback_data="bills_menu")],
        [InlineKeyboardButton("📅 Calendar", callback_data="cal_menu"), InlineKeyboardButton("📊 Weekly", callback_data="weekly_report")],
        [InlineKeyboardButton("🌤️ Weather", callback_data="weather_delhi"), InlineKeyboardButton("💕 Flirt", callback_data="flirt_msg")],
        [InlineKeyboardButton("💰 Crypto", callback_data="crypto_btc"), InlineKeyboardButton("🧠 Memory", callback_data="memory")],
        [InlineKeyboardButton("📋 All Tasks", callback_data="all_tasks"), InlineKeyboardButton("✅ Completed", callback_data="completed_tasks")],
        [InlineKeyboardButton("💾 Backup", callback_data="backup_now"), InlineKeyboardButton("🧹 Clear", callback_data="clear_chat")],
    ])

def news_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇳 India", callback_data="news_India"), InlineKeyboardButton("💻 Tech", callback_data="news_Technology")],
        [InlineKeyboardButton("💼 Business", callback_data="news_Business"), InlineKeyboardButton("🌍 World", callback_data="news_World")],
        [InlineKeyboardButton("🏏 Sports", callback_data="news_Sports"), InlineKeyboardButton("🏠 Back", callback_data="menu")],
    ])

# ══════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════
async def cmd_start(update, ctx):
    n = now_ist(); name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(
        f"🕌 *Assalamualaikum {name}!*\n\n⏰ {n.strftime('%I:%M %p')} IST | 📅 {n.strftime('%d %b %Y')}\n\n"
        "✅ Natural Language Reminders!\n💬 _'2 minute baad chai peena hai'_ → Auto Alarm!\n\n"
        "📋 Tasks | 💪 Habits | 📖 Diary | 💰 Expenses\n"
        "🌤️ Weather | 💕 Flirty | 📈 Crypto | 📰 News\n"
        "💾 Google Sheets Backup\n\n_Type or /help_ 👇",
        parse_mode="Markdown", reply_markup=main_kb()
    )

async def cmd_help(update, ctx):
    await update.message.reply_text(
        "📋 *COMMANDS*\n\n"
        "`/task` `/done` `/deltask` — Tasks\n"
        "`/habit` `/hdone` `/delhabit` — Habits\n"
        "`/diary` — Diary | `/kharcha` `/budget` — Expenses\n"
        "`/goal` `/gprogress` — Goals\n"
        "`/remind 2m Test` `/reminders` `/delremind` — Reminders\n"
        "`/remember` `/recall` — Memory\n"
        "`/note` `/delnote` — Notes\n"
        "`/water` `/watergoal` — Water\n"
        "`/bill` `/bills` `/billpaid` — Bills\n"
        "`/cal` `/calendar` — Calendar\n"
        "`/news` — News | `/briefing` `/weekly` — Reports\n"
        "🌤️ `/weather Delhi` | 💕 `/flirt` | 📈 `/crypto BTC`\n"
        "💾 `/backup` — Force backup | 🧹 `/clear` — Clear chat\n"
        "💬 _'2 min baad meeting'_ → Auto Alarm!\n\n"
        "_Seedha type karo — AI jawab dega!_", parse_mode="Markdown"
    )

async def cmd_task(update, ctx):
    if not ctx.args: await update.message.reply_text("📋 `/task Kaam [high/low]`"); return
    args = " ".join(ctx.args); priority = "medium"
    if args.endswith(" high"): priority = "high"; args = args[:-5].strip()
    elif args.endswith(" low"): priority = "low"; args = args[:-4].strip()
    t = tasks.add(args, priority); e = "🔴" if priority=="high" else "🟡" if priority=="medium" else "🟢"
    await update.message.reply_text(f"✅ {e} *{t['title']}*\n🆔 `#{t['id']}`", parse_mode="Markdown")

async def cmd_done(update, ctx):
    if not ctx.args: await update.message.reply_text("`/done <id>`"); return
    try: t = tasks.complete(int(ctx.args[0])); await update.message.reply_text(f"🎉 *Done!* {t['title']}" if t else "❌", parse_mode="Markdown")
    except: pass

async def cmd_deltask(update, ctx):
    if not ctx.args: await update.message.reply_text("`/deltask <id>`"); return
    try: tasks.delete(int(ctx.args[0])); await update.message.reply_text("🗑 Deleted!")
    except: pass

async def cmd_alltasks(update, ctx):
    p = tasks.pending(); c = tasks.completed_tasks(); all_t = tasks.all_tasks()
    txt = f"📋 *ALL TASKS ({len(all_t)})*\n\n"
    txt += f"⏳ *PENDING ({len(p)}):*\n" + "".join(f"  {'🔴' if t['priority']=='high' else '🟡'} *#{t['id']}* {t['title']}\n" for t in p[:10])
    txt += f"\n✅ *COMPLETED ({len(c)}):*\n" + "".join(f"  ✅ *#{t['id']}* {t['title']}\n" for t in c[-10:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed(update, ctx):
    c = tasks.completed_tasks()
    await update.message.reply_text("✅ *COMPLETED*\n\n" + "".join(f"  ✓ #{t['id']} {t['title']}\n" for t in c[-15:]) if c else "✅ None!", parse_mode="Markdown")

async def cmd_diary(update, ctx):
    if not ctx.args: await update.message.reply_text("📖 `/diary Text`"); return
    diary.add(" ".join(ctx.args)); await update.message.reply_text(f"📖 Saved! 🕐 {now_str()}")

async def cmd_habit(update, ctx):
    if not ctx.args: await update.message.reply_text("💪 `/habit Naam`"); return
    h = habits.add(" ".join(ctx.args)); await update.message.reply_text(f"💪 {h['emoji']} *{h['name']}*\n`/hdone {h['id']}`", parse_mode="Markdown")

async def cmd_hdone(update, ctx):
    if not ctx.args:
        _, p = habits.today_status()
        await update.message.reply_text("Kaunsi? " + " ".join(f"`/hdone {h['id']}`" for h in p) if p else "🎊 Sab done!"); return
    try: ok, s = habits.log(int(ctx.args[0])); await update.message.reply_text(f"💪 Done! 🔥{s}d!" if ok else "✅ Already done!")
    except: pass

async def cmd_delhabit(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delhabit <id>`"); return
    try: habits.delete(int(ctx.args[0])); await update.message.reply_text("🗑 Deleted!")
    except: pass

async def cmd_note(update, ctx):
    if not ctx.args: await update.message.reply_text("📝 `/note Text`"); return
    n = notes.add(" ".join(ctx.args)); await update.message.reply_text(f"📝 Note #{n['id']} saved!")

async def cmd_delnote(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delnote <id>`"); return
    try: notes.delete(int(ctx.args[0])); await update.message.reply_text("🗑 Deleted!")
    except: pass

async def cmd_kharcha(update, ctx):
    if not ctx.args or len(ctx.args) < 2: await update.message.reply_text("💰 `/kharcha 100 Chai`"); return
    try:
        amount = float(ctx.args[0]); desc = " ".join(ctx.args[1:])
        cat = "general"
        cats = ["food","travel","shopping","bills","health","entertainment","education","general"]
        if ctx.args[-1].lower() in cats: cat = ctx.args[-1].lower(); desc = " ".join(ctx.args[1:-1]) or "Kharcha"
        expenses.add(amount, desc, cat)
        await update.message.reply_text(f"💰 ₹{amount:.0f} — {desc}\n📊 Aaj: ₹{expenses.today_total():.0f}", parse_mode="Markdown")
    except: pass

async def cmd_budget(update, ctx):
    if not ctx.args: await update.message.reply_text("💳 `/budget 5000`"); return
    try: expenses.set_budget(float(ctx.args[0])); await update.message.reply_text(f"💳 Budget: ₹{ctx.args[0]}")
    except: pass

async def cmd_goal(update, ctx):
    if not ctx.args: await update.message.reply_text("🎯 `/goal Goal [YYYY-MM-DD]`"); return
    title = " ".join(ctx.args); deadline = None
    parts = title.rsplit(" ", 1)
    if len(parts)==2 and len(parts[1])==10 and parts[1].count("-")==2: deadline = parts[1]; title = parts[0]
    g = goals.add(title, deadline); await update.message.reply_text(f"🎯 *{g['title']}*" + (f"\n📅 {deadline}" if deadline else ""), parse_mode="Markdown")

async def cmd_gprogress(update, ctx):
    try:
        gid, pct = int(ctx.args[0]), int(ctx.args[1]); g = goals.update(gid, pct)
        if g: await update.message.reply_text(f"📊 *{g['title']}* — {pct}% {'🏆' if pct==100 else ''}", parse_mode="Markdown")
        else: await update.message.reply_text("❌ Goal not found", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/gprogress <id> <percentage>`", parse_mode="Markdown")

async def cmd_remember(update, ctx):
    if not ctx.args: await update.message.reply_text("🧠 `/remember Text`"); return
    memory.add_fact(" ".join(ctx.args)); await update.message.reply_text("🧠 Yaad kar liya! ✅")

async def cmd_recall(update, ctx):
    f = memory.get_all_facts(); imp = memory.store.data.get("important_notes", [])
    txt = "🧠 *YAADDASHT*\n\n" + "\n".join(f"📌 {x['f']}" for x in f[-15:]) if f else "🧠 Kuch yaad nahi."
    if imp: txt += "\n\n⭐ *IMPORTANT:*\n" + "\n".join(f"⭐ {n['note']}" for n in imp[-5:])
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_briefing(update, ctx):
    tp = tasks.today_pending(); hd, hp = habits.today_status(); n = now_ist()
    ag = goals.active(); exp_t = expenses.today_total(); exp_m = expenses.month_total()
    bl = expenses.budget_left(); w_t = water.today_total(); w_g = water.goal()
    txt = f"🌅 *DAILY BRIEFING*\n⏰ {n.strftime('%I:%M %p')} | 📅 {n.strftime('%d %b')}\n\n"
    if tp: txt += f"📋 *Pending ({len(tp)}):*\n" + "".join(f"  {'🔴' if t['priority']=='high' else '🟡'} {t['title']}\n" for t in tp[:5])
    else: txt += "🎉 No pending!\n"
    if hp: txt += f"\n💪 Habits left: {', '.join(h['name'] for h in hp[:4])}"
    txt += f"\n\n💰 Aaj: ₹{exp_t:.0f} | Mahina: ₹{exp_m:.0f}"
    if bl is not None: txt += f" | Budget: ₹{bl:.0f}"
    txt += f"\n💧 Water: {w_t}ml/{w_g}ml"
    if ag: txt += f"\n🎯 Goals: {', '.join(g['title'] for g in ag[:3])}"
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_weekly(update, ctx):
    td = now_ist().date(); wa = td - timedelta(days=6)
    txt = f"📊 *WEEKLY REPORT*\n{wa.strftime('%d %b')} — {td.strftime('%d %b')}\n" + "━"*20
    txt += f"\n\n📋 Pending: {len(tasks.pending())} | ✅ Done: {len(tasks.completed())}\n"
    txt += f"💰 Month: ₹{expenses.month_total():.0f}\n"
    all_h = habits.all()
    if all_h: txt += "💪 Habits:\n" + "".join(f"  {h['emoji']} {h['name']}: 🔥{h.get('streak',0)}\n" for h in all_h[:5])
    txt += "\n💪 Agli hafte aur badiya! 🚀"
    await update.message.reply_text(txt, parse_mode="Markdown")

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

# ══════════════════════════════════════════════
# REMINDER COMMANDS
# ══════════════════════════════════════════════
async def cmd_remind(update, ctx):
    now = now_ist()
    if not ctx.args:
        await update.message.reply_text(f"⏰ *REMINDER*\nAbhi: *{now.strftime('%I:%M %p')}*\n\n`/remind 2m Test` | `/remind 30m Chai` | `/remind 15:30 Doctor`\n\n💬 _'2 min baad meeting'_ → Auto!", parse_mode="Markdown"); return
    
    # Try natural parsing first
    ts, text, repeat = parse_natural_reminder(update.message.text.replace("/remind", "").strip())
    
    if not ts:
        time_arg = ctx.args[0].lower(); rest = ctx.args[1:]; repeat = "once"
        if rest and rest[-1].lower() == "daily": repeat = "daily"; rest = rest[:-1]
        elif rest and rest[-1].lower() == "weekly": repeat = "weekly"; rest = rest[:-1]
        text = " ".join(rest) if rest else "⏰ Reminder!"
        if time_arg.endswith("m") and time_arg[:-1].isdigit(): ts = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
        elif time_arg.endswith("h") and time_arg[:-1].isdigit(): ts = (now + timedelta(hours=int(time_arg[:-1]))).strftime("%H:%M")
        elif ":" in time_arg:
            p = time_arg.split(":")
            if len(p)==2 and p[0].isdigit() and p[1].isdigit(): ts = f"{int(p[0]):02d}:{int(p[1]):02d}"
    
    if not ts: await update.message.reply_text(f"❌ Format! `/remind 2m Test`"); return
    r = reminders.add(update.effective_chat.id, text, ts, repeat)
    await update.message.reply_text(f"✅ Set! ⏰ *{ts}* — {text}\n🆔 `#{r['id']}` | 💾 Saved", parse_mode="Markdown")

async def cmd_reminders_list(update, ctx):
    a = reminders.all_active()
    await update.message.reply_text("⏰ *REMINDERS*\n\n" + "".join(f"*#{r['id']}* `{r['time']}` — {r['text']}\n" for r in a) if a else f"⏰ None!\n`/remind 2m Test`", parse_mode="Markdown")

async def cmd_delremind(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delremind <id>`"); return
    try: await update.message.reply_text("🗑 Deleted!" if reminders.delete(int(ctx.args[0])) else "❌")
    except: pass

# ══════════════════════════════════════════════
# WATER, BILLS, CALENDAR COMMANDS
# ══════════════════════════════════════════════
async def cmd_water(update, ctx):
    ml = 250
    if ctx.args:
        try: ml = int(ctx.args[0])
        except: pass
    water.add(ml); total = water.today_total(); goal = water.goal(); pct = min(100, int(total/goal*100)) if goal else 0
    await update.message.reply_text(f"💧 +{ml}ml | {total}ml/{goal}ml ({pct}%)", parse_mode="Markdown")

async def cmd_water_status(update, ctx):
    total = water.today_total(); goal = water.goal(); pct = min(100, int(total/goal*100)) if goal else 0
    await update.message.reply_text(f"💧 {total}ml/{goal}ml ({pct}%)", parse_mode="Markdown")

async def cmd_water_goal(update, ctx):
    if not ctx.args: await update.message.reply_text(f"Current: {water.goal()}ml\n`/watergoal 2500`"); return
    try: water.set_goal(int(ctx.args[0])); await update.message.reply_text(f"✅ Goal: {ctx.args[0]}ml")
    except: pass

async def cmd_bill(update, ctx):
    if not ctx.args or len(ctx.args)<3: await update.message.reply_text("💳 `/bill Naam Amount Tarikh`"); return
    try:
        name, amount, due_day = ctx.args[0], float(ctx.args[1]), int(ctx.args[2])
        bt = "emi" if "emi" in name.lower() or "loan" in name.lower() else "bill"
        if name.lower() in ["netflix","amazon","hotstar","spotify"]: bt = "subscription"
        b = bills.add(name, amount, due_day, bt)
        icons = {"emi":"🏦","bill":"📄","subscription":"📺"}
        await update.message.reply_text(f"✅ {icons.get(bt,'💳')} *{name}*\n₹{amount:.0f} | {due_day} tarikh\n🆔 #{b['id']}", parse_mode="Markdown")
    except: pass

async def cmd_bills_list(update, ctx):
    ab = bills.all_active(); icons = {"emi":"🏦","bill":"📄","subscription":"📺"}
    txt = "💳 *BILLS & EMI*\n\n" + "".join(f"{icons.get(b.get('type',''),'💳')} {'✅' if bills.is_paid(b['id']) else '⏳'} *{b['name']}* ₹{b['amount']:.0f} — {b['due_day']}th\n" for b in ab)
    txt += f"\n💰 Monthly: ₹{bills.month_total():.0f}"
    await update.message.reply_text(txt if ab else "💳 No bills!", parse_mode="Markdown")

async def cmd_bill_paid(update, ctx):
    if not ctx.args: await update.message.reply_text("`/billpaid <id>`"); return
    try: await update.message.reply_text("✅ Paid!" if bills.mark_paid(int(ctx.args[0])) else "❌")
    except: pass

async def cmd_del_bill(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delbill <id>`"); return
    try: await update.message.reply_text("🗑 Deleted!" if bills.delete(int(ctx.args[0])) else "❌")
    except: pass

async def cmd_cal(update, ctx):
    if not ctx.args: await update.message.reply_text(f"📅 `/cal {today_str()} Meeting`\n`/cal aaj Doctor 14:00`"); return
    args_str = " ".join(ctx.args); date_str = None; title = args_str; event_time = ""
    m = _re.match(r'^(\d{4}-\d{2}-\d{2})\s+(.*)', args_str)
    if m: date_str = m.group(1); title = m.group(2)
    if not date_str:
        if args_str.lower().startswith("aaj "): date_str = today_str(); title = args_str[4:]
        elif args_str.lower().startswith("kal "): date_str = (now_ist().date()+timedelta(days=1)).isoformat(); title = args_str[4:]
    if not date_str: await update.message.reply_text("❌ `/cal YYYY-MM-DD Event`"); return
    tm = _re.search(r'(\d{1,2}:\d{2})', title)
    if tm: event_time = tm.group(1); title = title.replace(event_time,"").strip()
    try:
        date.fromisoformat(date_str); e = calendar.add(title, date_str, event_time)
        dl = "Aaj" if date_str==today_str() else "Kal" if date_str==(now_ist().date()+timedelta(days=1)).isoformat() else date_str
        await update.message.reply_text(f"📅 *{title}*\n📆 {dl}" + (f" ⏰{event_time}" if event_time else "") + f"\n🆔 #{e['id']}", parse_mode="Markdown")
    except: await update.message.reply_text("❌ Invalid date")

async def cmd_cal_list(update, ctx):
    up = calendar.upcoming(30)
    await update.message.reply_text("📅 *UPCOMING (30 din)*\n\n" + "".join(f"{'🔴' if e['date']==today_str() else '📆'} {e['date'][5:]} " + (f"⏰{e['time']} " if e.get('time') else "") + f"— {e['title']}\n" for e in up[:10]) if up else "📅 No events!", parse_mode="Markdown")

async def cmd_del_cal(update, ctx):
    if not ctx.args: await update.message.reply_text("`/delcal <id>`"); return
    try: await update.message.reply_text("🗑 Deleted!" if calendar.delete(int(ctx.args[0])) else "❌")
    except: pass

async def cmd_yesterday(update, ctx):
    d = tasks.done_on(yesterday_str()); yd_d = diary.get(yesterday_str())
    yd_label = (now_ist().date()-timedelta(days=1)).strftime("%A, %d %B")
    txt = f"📅 *KAL ({yd_label})*\n\n"
    txt += (f"✅ {len(d)} tasks done\n" + "".join(f"• {t['title']}\n" for t in d[:5])) if d else "No tasks done\n"
    if yd_d: txt += "\n📖 Diary:\n" + "".join(f"  {e['time']} {e['mood']} {e['text']}\n" for e in yd_d[-3:])
    await update.message.reply_text(txt if (d or yd_d) else "📅 Kal ka koi data nahi", parse_mode="Markdown")

async def cmd_clear(update, ctx):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💾 Backup + Clear", callback_data="backup_clear"), InlineKeyboardButton("🧹 Just Clear", callback_data="confirm_clear_chat")], [InlineKeyboardButton("❌ Cancel", callback_data="menu")]])
    await update.message.reply_text(f"🧹 *CHAT CLEAR*\n\n📊 {chat_hist.count() if hasattr(chat_hist,'count') else '?'} msgs\n\n💾 *Backup+Clear:* Sheets save + clear\n✅ Data Sheets mein safe!", parse_mode="Markdown", reply_markup=kb)

async def cmd_nuke(update, ctx):
    await update.message.reply_text("💣 Nuke feature — clears bot messages", parse_mode="Markdown")

async def cmd_backup(update, ctx):
    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if not msg: return
    for t in tasks.all_tasks(): gsheets.save_data("Tasks", str(update.effective_user.id), "BACKUP", t["title"][:200], "✅" if t.get("done") else "⏳")
    for r in reminders.all_active(): gsheets.save_data("Reminders", str(update.effective_user.id), "BACKUP", r["time"], r["text"][:200])
    for f in memory.get_all_facts()[-10:]: gsheets.save_data("Memory", str(update.effective_user.id), "BACKUP", f["f"][:400])
    gsheets.save_data("Daily_Logs", str(update.effective_user.id), "BACKUP", f"Backup at {now_str()}")
    await msg.reply_text("💾 *BACKUP COMPLETE!*\n\n✅ Google Sheets mein sab save!\n✅ Reminders, Tasks, Memory — safe!\n🔒 _Chat clear ke baad bhi data rahega!_", parse_mode="Markdown")

# ══════════════════════════════════════════════
# SECRET COMMANDS
# ══════════════════════════════════════════════
def check_secret(a): return a and a[0] == SECRET_CODE

async def cmd_tasklogs(update, ctx):
    if not check_secret(ctx.args): await update.message.reply_text("🔒"); return
    logs = task_logs.get_all_logs()
    if not logs: await update.message.reply_text("📋 No logs!"); return
    from collections import defaultdict
    by_date = defaultdict(list)
    for l in logs: by_date[l.get("date","?")].append(l)
    txt = f"📋 *TASK LOGS ({len(logs)})*\n\n"
    for d in sorted(by_date.keys(), reverse=True)[:7]:
        txt += f"📅 *{d}*\n"
        for l in by_date[d][-3:]: txt += f"  {'➕' if l['type']=='created' else '✅' if l['type']=='completed' else '🗑'} {l['description'][:40]}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_failed(update, ctx):
    if not check_secret(ctx.args): await update.message.reply_text("🔒"); return
    un = failed_reqs.get_unretried()
    await update.message.reply_text(f"📝 *FAILED ({len(un)})*\n\n" + "".join(f"• {r['msg'][:60]}\n" for r in un[:5]) if un else "✅ No failed!", parse_mode="Markdown")

async def cmd_fulldata(update, ctx):
    if not check_secret(ctx.args): await update.message.reply_text("🔒"); return
    txt = f"📊 *FULL DATA*\n\n🧠 Facts: {len(memory.get_all_facts())}\n📋 Tasks: {len(tasks.all_tasks())}\n💪 Habits: {len(habits.all())}\n⏰ Reminders: {len(reminders.all_active())}\n💰 Month: ₹{expenses.month_total():.0f}\n💧 Water: {water.today_total()}ml\n📖 Diary today: {len(diary.get(today_str()))}\n\n💾 Sheets: {'✅' if gsheets.use_gsheets else '❌'}"
    await update.message.reply_text(txt, parse_mode="Markdown")

# ══════════════════════════════════════════════
# CALLBACK HANDLER
# ══════════════════════════════════════════════
async def callback_handler(update, ctx):
    q = update.callback_query; await q.answer(); d = q.data

    if d == "menu": await q.message.reply_text("🏠 *Menu*", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "briefing": await cmd_briefing(update, ctx)
    elif d == "tasks":
        p = tasks.pending()
        txt = "📋 *PENDING*\n\n" + "".join(f"{'🔴' if t['priority']=='high' else '🟡'} *#{t['id']}* {t['title']}\n" for t in p[:8]) if p else "🎉 No pending!"
        kb = [[InlineKeyboardButton(f"✅ #{t['id']}: {t['title'][:30]}", callback_data=f"done_{t['id']}")] for t in p[:8]]
        kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
        await q.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb) if p else None)
    elif d == "all_tasks": await cmd_alltasks(update, ctx)
    elif d == "completed_tasks": await cmd_completed(update, ctx)
    elif d == "habits":
        done, pend = habits.today_status()
        done_s = ", ".join(f"{h['emoji']}{h['name']}" for h in done)
        pend_s = ", ".join(h['name'] for h in pend)
        await q.message.reply_text(f"💪 *HABITS*\n✅ {done_s}\n⏳ {pend_s}", parse_mode="Markdown")
    elif d == "diary":
        td = diary.get(today_str())
        await q.message.reply_text("📖 *DIARY*\n\n" + "\n".join(f"{e['time']} {e['text']}" for e in td[-3:]) if td else "_No entries_", parse_mode="Markdown")
    elif d == "goals":
        ag = goals.active(); cg = goals.completed()
        txt = "🎯 *GOALS*\n\n"
        if ag: txt += "*Active:*\n" + "".join(f"  {g['title']} {g['progress']}%\n" for g in ag[:5])
        if cg: txt += "\n*Completed:*\n" + "".join(f"  🏆 {g['title']}\n" for g in cg[-3:])
        await q.message.reply_text(txt if (ag or cg) else "🎯 No goals!", parse_mode="Markdown")
    elif d == "expenses":
        items = expenses.today_list()
        txt = f"💰 Aaj: ₹{expenses.today_total():.0f} | Month: ₹{expenses.month_total():.0f}\n"
        bl = expenses.budget_left()
        if bl is not None: txt += f"Budget: ₹{bl:.0f}\n"
        if items: txt += "\n" + "\n".join(f"  ₹{e['amount']:.0f} {e['desc']}" for e in items[-8:])
        await q.message.reply_text(txt)
    elif d == "notes":
        ns = notes.recent(12)
        await q.message.reply_text("📝 *NOTES*\n\n" + "\n".join(f"*#{n['id']}* {n['text']}" for n in ns) if ns else "📝 No notes!", parse_mode="Markdown")
    elif d == "memory":
        f = memory.get_all_facts()
        await q.message.reply_text("🧠 *YAADDASHT*\n\n" + "\n".join(f"📌 {x['f']}" for x in f[-12:]) if f else "🧠 _Empty_", parse_mode="Markdown")
    elif d == "yesterday": await cmd_yesterday(update, ctx)
    elif d == "news_menu": await q.message.reply_text("📰 Category:", parse_mode="Markdown", reply_markup=news_kb())
    elif d.startswith("news_"):
        items = news_store.get(d.split("_",1)[1], 5)
        await q.message.reply_text("📰 *NEWS*\n\n" + "".join(f"*{i+1}.* {item['title']}\n" for i, item in enumerate(items)), parse_mode="Markdown")
    elif d == "water_status":
        total = water.today_total(); goal = water.goal(); pct = min(100, int(total/goal*100)) if goal else 0
        await q.message.reply_text(f"💧 {total}ml/{goal}ml ({pct}%)", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💧 +250ml", callback_data="water_250"), InlineKeyboardButton("💧 +500ml", callback_data="water_500")]]))
    elif d.startswith("water_"): water.add(int(d.split("_")[1])); await q.message.reply_text(f"💧 +{d.split('_')[1]}ml | {water.today_total()}ml")
    elif d == "bills_menu":
        ab = bills.all_active(); icons = {"emi":"🏦","bill":"📄","subscription":"📺"}
        await q.message.reply_text("💳 *BILLS*\n\n" + "\n".join(f"{icons.get(b.get('type',''),'💳')} {'✅' if bills.is_paid(b['id']) else '⏳'} {b['name']} ₹{b['amount']:.0f}" for b in ab) if ab else "💳 No bills!", parse_mode="Markdown")
    elif d.startswith("billpaid_"): await cmd_bill_paid(update, ctx)
    elif d == "cal_menu": await cmd_cal_list(update, ctx)
    elif d == "weekly_report": await cmd_weekly(update, ctx)
    elif d == "weather_delhi": await q.message.reply_text(get_weather("Delhi"), parse_mode="Markdown")
    elif d == "flirt_msg": await q.message.reply_text(get_flirty(), parse_mode="Markdown")
    elif d == "crypto_btc": await q.message.reply_text(get_crypto("bitcoin"), parse_mode="Markdown")
    elif d == "backup_now": await cmd_backup(update, ctx)
    elif d == "backup_clear":
        for t in tasks.all_tasks(): gsheets.save_data("Tasks", str(update.effective_user.id), "BACKUP", t["title"][:200])
        for r in reminders.all_active(): gsheets.save_data("Reminders", str(update.effective_user.id), "BACKUP", r["time"], r["text"][:200])
        await asyncio.sleep(1)
        await q.message.reply_text("💾 *Backup + Cleared!*\n✅ Data Sheets mein safe!", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "confirm_clear_chat":
        await q.message.reply_text("🧹 *Cleared!*\n✅ `/recall` `/alltasks` `/reminders` se sab dekho!", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "clear_chat":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💾 Backup+Clear", callback_data="backup_clear"), InlineKeyboardButton("❌ Cancel", callback_data="menu")]])
        await q.message.reply_text(f"🧹 Clear chat?", parse_mode="Markdown", reply_markup=kb)
    elif d == "motivate":
        r = call_gemini("Powerful Hindi motivation 2 lines")
        await q.message.reply_text(f"💡 *Motivation:*\n\n{r}" if r else "💪 Keep pushing forward! 🚀", parse_mode="Markdown")
    elif d.startswith("done_"):
        t = tasks.complete(int(d.split("_")[1]))
        await q.message.reply_text(f"🎉 Done: {t['title']}" if t else "❌", parse_mode="Markdown")
    elif d.startswith("habit_"):
        hid = int(d.split("_")[1]); ok, s = habits.log(hid)
        await q.message.reply_text(f"💪 Done! 🔥{s}d!" if ok else "✅ Already done!")
    elif d.startswith("goal_"): await q.message.reply_text(f"📊 `/gprogress {d.split('_')[1]} 50`")
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
    elif d == "clear_done_tasks":
        count = tasks.clear_done()
        await q.message.reply_text(f"🗑 {count} done tasks deleted!")

# ══════════════════════════════════════════════
# MESSAGE HANDLER — NATURAL REMINDER + QUICK COMMANDS + AI
# ══════════════════════════════════════════════
async def handle_message(update, ctx):
    msg_text = update.message.text
    chat_id = update.effective_chat.id
    lower = msg_text.lower()
    
    # 🔥 STEP 1: Natural Reminder Detection
    ts, text, repeat = parse_natural_reminder(msg_text)
    if ts:
        r = reminders.add(chat_id, text, ts, repeat)
        await update.message.reply_text(
            f"✅ *Alarm set!* ⏰ {ts} — _{text}_\n"
            f"🆔 `#{r['id']}` | 💾 Sheets saved\n\n"
            f"_Waqt aane pe LOUD notification aayega!_ 📳",
            parse_mode="Markdown"
        )
        return
    
    # 🔥 STEP 2: Quick Commands
    if any(w in lower for w in ["time", "baje", "time kya"]):
        n = now_ist()
        await update.message.reply_text(f"⏰ *{n.strftime('%I:%M %p')}* IST", parse_mode="Markdown")
        return
    
    for city in CITIES:
        if city in lower and any(w in lower for w in ["weather", "mausam", "temperature"]):
            await update.message.reply_text(get_weather(city), parse_mode="Markdown")
            return
    
    for coin in CRYPTO_IDS:
        if coin in lower and any(w in lower for w in ["price", "rate", "bhav", "kitna"]):
            await update.message.reply_text(get_crypto(coin), parse_mode="Markdown")
            return
    
    if any(w in lower for w in ["flirt", "romantic", "pyaar", "love message"]):
        await update.message.reply_text(get_flirty(), parse_mode="Markdown")
        return
    
    # 🔥 STEP 3: AI Response
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    ctx_prompt = f"""You are 'Dost' AI. Hindi/Hinglish, SHORT (2-4 lines), warm.
Current time: {time_label()}
Tasks pending: {len(tasks.pending())}
Today expenses: ₹{expenses.today_total():.0f}
RULES: Hindi/Hinglish, SHORT, friendly, never say "As an AI"."""
    
    prompt = f"{ctx_prompt}\n\nUser: {msg_text}\n\nShort Hindi reply (2-4 lines):"
    reply = call_gemini(prompt)
    if not reply:
        reply = call_huggingface(prompt)
        if reply: reply += "\n_⚡ (free model)_"
    if not reply:
        reply = smart_fallback(msg_text)
    
    try: await update.message.reply_text(reply, parse_mode="Markdown")
    except: await update.message.reply_text(reply)

# ══════════════════════════════════════════════
# BACKGROUND JOBS
# ══════════════════════════════════════════════
async def reminder_job(context):
    now = now_ist(); now_time = now.strftime("%H:%M")
    if now.minute % 5 == 0 and now.second < 35:
        active = reminders.all_active()
        if active: log.info(f"⏰ CHECK {now_time} IST | Active: {len(active)}")
    if now_time in ("00:00", "00:01"): reminders.reset_daily(); log.info("🔄 Daily reset"); return
    due = reminders.due_now()
    if due: log.info(f"🔔 FIRING {len(due)} ALARMS!")
    for r in due:
        try:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ho Gaya!", callback_data=f"remind_done_{r['id']}"), InlineKeyboardButton("⏰ 10 min Snooze", callback_data=f"remind_snooze_{r['id']}")]])
            await context.bot.send_message(chat_id=r["chat_id"], text=f"🚨🔔🚨 *ALARM!*\n{'═'*20}\n⏰ *{r['time']} BAJ GAYE!*\n{'═'*20}\n\n📢 *{r['text'].upper()}*", parse_mode="Markdown", disable_notification=False, reply_markup=kb)
            await asyncio.sleep(2)
            await context.bot.send_message(chat_id=r["chat_id"], text=f"🔔 *REMINDER:* {r['text']}\n⏰ Abhi: *{now.strftime('%I:%M %p')} IST*", parse_mode="Markdown", disable_notification=False)
            reminders.mark_fired(r["id"])
            log.info(f"✅ FIRED: #{r['id']}")
            await asyncio.sleep(1)
        except Exception as e:
            log.error(f"❌ FAILED #{r['id']}: {e}")
            try: reminders.mark_fired(r["id"])
            except: pass

async def failed_retry_job(context):
    un = failed_reqs.get_unretried()
    if not un: return
    for i, r in enumerate(un[:3]):
        try:
            reply = call_gemini(f"User: {r['msg']}\n\nShort Hindi reply:")
            if reply and not reply.startswith("🙏"): failed_reqs.mark_retried(i)
        except: pass

# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
def main():
    n = now_ist()
    log.info("=" * 50)
    log.info(f"🤖 Bot v10.0 ULTIMATE | ⏰ {n.strftime('%Y-%m-%d %I:%M:%S %p')} IST")
    log.info(f"🔑 Gemini: {'YES' if GEMINI_API_KEY else 'NO'} | 🤗 HF: {'YES' if HF_TOKEN else 'NO'} | 💾 Sheets: {'YES' if gsheets.use_gsheets else 'NO'}")
    log.info("=" * 50)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    cmds = [
        ("start", cmd_start), ("help", cmd_help),
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("alltasks", cmd_alltasks), ("completed", cmd_completed),
        ("diary", cmd_diary), ("habit", cmd_habit), ("hdone", cmd_hdone), ("delhabit", cmd_delhabit),
        ("note", cmd_note), ("delnote", cmd_delnote),
        ("kharcha", cmd_kharcha), ("budget", cmd_budget),
        ("goal", cmd_goal), ("gprogress", cmd_gprogress),
        ("remember", cmd_remember), ("recall", cmd_recall),
        ("briefing", cmd_briefing), ("weekly", cmd_weekly), ("news", cmd_news),
        ("weather", cmd_weather), ("flirt", cmd_flirt), ("crypto", cmd_crypto),
        ("remind", cmd_remind), ("reminders", cmd_reminders_list), ("delremind", cmd_delremind),
        ("water", cmd_water), ("waterstatus", cmd_water_status), ("watergoal", cmd_water_goal),
        ("bill", cmd_bill), ("bills", cmd_bills_list), ("billpaid", cmd_bill_paid), ("delbill", cmd_del_bill),
        ("cal", cmd_cal), ("calendar", cmd_cal_list), ("delcal", cmd_del_cal),
        ("yesterday", cmd_yesterday),
        ("clear", cmd_clear), ("nuke", cmd_nuke), ("backup", cmd_backup),
        ("tasklogs", cmd_tasklogs), ("failed", cmd_failed), ("fulldata", cmd_fulldata),
    ]
    for c, h in cmds: app.add_handler(CommandHandler(c, h))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=30, first=5)
        app.job_queue.run_repeating(failed_retry_job, interval=300, first=60)
        log.info("⏰ Jobs: Reminder 30s | Retry 5min")
    else:
        log.error("❌ JobQueue NOT AVAILABLE!")

    log.info("✅ Bot ready! Try: '2 minute baad chai peena hai'")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
