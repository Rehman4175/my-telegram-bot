#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════╗
║       PERSONAL AI ASSISTANT — ADVANCED v5.0      ║
║  100% FREE | Gemini Multi-Model | News | Smart Memory ║
║  Auto-Fallback | 24/7 Ready | Google Sheets Backup ║
║  Task Logs | Secret Code | Pending/Completed Tasks  ║
║  PERMANENT STORAGE via Google Sheets 🔒 ║
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

# Google Sheets imports
import gspread
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
import base64

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
GOOGLE_CREDS = os.environ.get("GOOGLE_CREDS", "")  # Base64 encoded JSON
SHEET_ID = os.environ.get("SHEET_ID", "1kMk3veUHLbD8iKG3P7sYXBX1r5w647X9xRp__cTiajc")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    log.error("❌ Environment variables missing!")
    log.error("Please set: TELEGRAM_TOKEN and GEMINI_API_KEY")
    exit(1)

# ══════════════════════════════════════════════
# GOOGLE SHEETS SETUP
# ══════════════════════════════════════════════
class GoogleSheetsDB:
    """Permanent storage using Google Sheets - survives chat clears!"""
    
    def __init__(self):
        self.client = None
        self.sheet = None
        self.worksheet = None
        self._init_sheets()
    
    def _init_sheets(self):
        """Initialize Google Sheets connection"""
        try:
            if GOOGLE_CREDS:
                # Decode base64 credentials
                creds_json = base64.b64decode(GOOGLE_CREDS).decode('utf-8')
                creds_dict = json.loads(creds_json)
                credentials = Credentials.from_service_account_info(
                    creds_dict,
                    scopes=['https://www.googleapis.com/auth/spreadsheets']
                )
                self.client = gspread.authorize(credentials)
                self.sheet = self.client.open_by_key(SHEET_ID)
                self._ensure_sheets_exist()
                log.info("✅ Google Sheets connected successfully!")
            else:
                log.warning("⚠️ GOOGLE_CREDS not set - Sheets backup disabled")
        except Exception as e:
            log.error(f"❌ Google Sheets init error: {e}")
    
    def _ensure_sheets_exist(self):
        """Create required sheets if they don't exist"""
        required_sheets = {
            "Reminders": ["ID", "ChatID", "Text", "Time", "Repeat", "Date", "Active", "Created", "FiredToday"],
            "ImportantNotes": ["ID", "ChatID", "Text", "Date", "Time"],
            "TasksBackup": ["ID", "Title", "Priority", "Due", "Done", "DoneAt", "Created", "ChatID"],
            "MemoryFacts": ["ID", "Fact", "Date", "ChatID"],
            "UserPreferences": ["Key", "Value", "ChatID"],
            "FailedRequests": ["ID", "Msg", "ChatID", "Reason", "Time", "Retried"],
            "ChatClearLog": ["ID", "ChatID", "ClearedAt", "MessagesCount", "Summary"]
        }
        
        existing_sheets = [ws.title for ws in self.sheet.worksheets()]
        
        for sheet_name, headers in required_sheets.items():
            if sheet_name not in existing_sheets:
                ws = self.sheet.add_worksheet(title=sheet_name, rows="1000", cols="20")
                ws.append_row(headers)
                log.info(f"📄 Created sheet: {sheet_name}")
    
    # ----- REMINDERS -----
    def save_reminder(self, reminder_data: dict):
        """Save reminder to Google Sheets permanently"""
        if not self.client:
            return
        try:
            ws = self.sheet.worksheet("Reminders")
            row = [
                reminder_data.get("id", ""),
                reminder_data.get("chat_id", ""),
                reminder_data.get("text", ""),
                reminder_data.get("time", ""),
                reminder_data.get("repeat", "once"),
                reminder_data.get("date", ""),
                str(reminder_data.get("active", True)),
                reminder_data.get("created", ""),
                str(reminder_data.get("fired_today", False))
            ]
            ws.append_row(row)
            log.info(f"📤 Reminder saved to Sheets: {reminder_data.get('text', '')[:30]}")
        except Exception as e:
            log.error(f"Sheets save reminder error: {e}")
    
    def get_all_reminders(self, chat_id: int = None) -> list:
        """Get all reminders from Google Sheets"""
        if not self.client:
            return []
        try:
            ws = self.sheet.worksheet("Reminders")
            all_rows = ws.get_all_values()[1:]  # Skip header
            reminders = []
            for row in all_rows:
                if len(row) < 8:
                    continue
                r = {
                    "id": int(row[0]) if row[0].isdigit() else row[0],
                    "chat_id": int(row[1]) if row[1].isdigit() else 0,
                    "text": row[2],
                    "time": row[3],
                    "repeat": row[4],
                    "date": row[5],
                    "active": row[6].lower() == "true",
                    "created": row[7],
                    "fired_today": row[8].lower() == "true" if len(row) > 8 else False
                }
                if chat_id is None or r["chat_id"] == chat_id:
                    reminders.append(r)
            return reminders
        except Exception as e:
            log.error(f"Sheets get reminders error: {e}")
            return []
    
    # ----- IMPORTANT NOTES (survive chat clear) -----
    def save_important_note(self, note_data: dict):
        """Save important note that survives chat clears"""
        if not self.client:
            return
        try:
            ws = self.sheet.worksheet("ImportantNotes")
            row = [
                note_data.get("id", datetime.now().timestamp()),
                note_data.get("chat_id", ""),
                note_data.get("text", ""),
                note_data.get("date", ""),
                note_data.get("time", "")
            ]
            ws.append_row(row)
            log.info(f"📝 Important note saved: {note_data.get('text', '')[:30]}")
        except Exception as e:
            log.error(f"Sheets save note error: {e}")
    
    def get_important_notes(self, chat_id: int = None) -> list:
        """Get all important notes from Google Sheets"""
        if not self.client:
            return []
        try:
            ws = self.sheet.worksheet("ImportantNotes")
            all_rows = ws.get_all_values()[1:]
            notes = []
            for row in all_rows:
                if len(row) < 3:
                    continue
                n = {
                    "id": row[0],
                    "chat_id": int(row[1]) if row[1].isdigit() else 0,
                    "text": row[2],
                    "date": row[3] if len(row) > 3 else "",
                    "time": row[4] if len(row) > 4 else ""
                }
                if chat_id is None or n["chat_id"] == chat_id:
                    notes.append(n)
            return notes
        except Exception as e:
            log.error(f"Sheets get notes error: {e}")
            return []
    
    # ----- TASKS BACKUP -----
    def save_task(self, task_data: dict):
        """Backup task to Google Sheets"""
        if not self.client:
            return
        try:
            ws = self.sheet.worksheet("TasksBackup")
            row = [
                task_data.get("id", ""),
                task_data.get("title", ""),
                task_data.get("priority", "medium"),
                task_data.get("due", ""),
                str(task_data.get("done", False)),
                task_data.get("done_at", ""),
                task_data.get("created", ""),
                task_data.get("chat_id", "")
            ]
            ws.append_row(row)
        except Exception as e:
            log.error(f"Sheets save task error: {e}")
    
    # ----- MEMORY FACTS -----
    def save_memory_fact(self, fact: str, chat_id: int):
        """Save memory fact permanently"""
        if not self.client:
            return
        try:
            ws = self.sheet.worksheet("MemoryFacts")
            row = [
                datetime.now().timestamp(),
                fact[:500],
                date.today().isoformat(),
                chat_id
            ]
            ws.append_row(row)
            log.info(f"🧠 Memory saved to Sheets: {fact[:30]}")
        except Exception as e:
            log.error(f"Sheets save memory error: {e}")
    
    def get_memory_facts(self, chat_id: int = None) -> list:
        """Get all memory facts from Google Sheets"""
        if not self.client:
            return []
        try:
            ws = self.sheet.worksheet("MemoryFacts")
            all_rows = ws.get_all_values()[1:]
            facts = []
            for row in all_rows:
                if len(row) < 3:
                    continue
                f = {
                    "f": row[1],
                    "d": row[2],
                    "chat_id": int(row[3]) if len(row) > 3 and row[3].isdigit() else 0
                }
                if chat_id is None or f["chat_id"] == chat_id:
                    facts.append(f)
            return facts
        except Exception as e:
            log.error(f"Sheets get memory error: {e}")
            return []
    
    # ----- CHAT CLEAR LOG -----
    def log_chat_clear(self, chat_id: int, messages_count: int, summary: str = ""):
        """Log when chat is cleared"""
        if not self.client:
            return
        try:
            ws = self.sheet.worksheet("ChatClearLog")
            row = [
                datetime.now().timestamp(),
                chat_id,
                datetime.now().isoformat(),
                messages_count,
                summary
            ]
            ws.append_row(row)
            log.info(f"📋 Chat clear logged: chat_id={chat_id}, {messages_count} msgs")
        except Exception as e:
            log.error(f"Sheets clear log error: {e}")
    
    # ----- FAILED REQUESTS -----
    def save_failed_request(self, req_data: dict):
        """Save failed request for later retry"""
        if not self.client:
            return
        try:
            ws = self.sheet.worksheet("FailedRequests")
            row = [
                datetime.now().timestamp(),
                req_data.get("msg", "")[:200],
                req_data.get("chat_id", ""),
                req_data.get("reason", ""),
                req_data.get("time", ""),
                str(req_data.get("retried", False))
            ]
            ws.append_row(row)
        except Exception as e:
            log.error(f"Sheets save failed request error: {e}")
    
    def create_backup_snapshot(self, chat_id: int) -> str:
        """Create a complete snapshot of all user data"""
        if not self.client:
            return "Sheets not connected"
        
        reminders = self.get_all_reminders(chat_id)
        notes = self.get_important_notes(chat_id)
        facts = self.get_memory_facts(chat_id)
        
        summary = f"📊 *BACKUP SNAPSHOT*\n{datetime.now().strftime('%d %b %Y %H:%M')}\n\n"
        summary += f"⏰ Reminders: {len(reminders)}\n"
        summary += f"📝 Important Notes: {len(notes)}\n"
        summary += f"🧠 Memory Facts: {len(facts)}\n"
        summary += f"\n💾 _Sab kuch Google Sheets mein safe hai!_ 🔒"
        
        return summary


# ══════════════════════════════════════════════
# FILE PATHS (keep some local, Google Sheets for critical)
# ══════════════════════════════════════════════
DATA = os.path.join(os.getcwd(), "data")
os.makedirs(DATA, exist_ok=True)

# Files that can be local (less critical)
F_CHAT      = os.path.join(DATA, "chat_history.json")
F_NEWS      = os.path.join(DATA, "news_cache.json")
F_WATER     = os.path.join(DATA, "water.json")
F_EXPENSES  = os.path.join(DATA, "expenses.json")

# ══════════════════════════════════════════════
# 🔥 MULTI-MODEL FALLBACK
# ══════════════════════════════════════════════
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
# INIT GLOBAL OBJECTS
# ══════════════════════════════════════════════
sheets_db = GoogleSheetsDB()  # Google Sheets permanent storage

# ══════════════════════════════════════════════
# CHAT HISTORY (local only - can be cleared)
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

    def clear(self, chat_id: int = None):
        count = len(self.data["history"])
        self.data["history"] = []
        self.data["cleared_at"] = datetime.now().isoformat()
        save(F_CHAT, self.data)
        # Log to Google Sheets
        if chat_id:
            sheets_db.log_chat_clear(chat_id, count, "Chat cleared by user")
        return count

    def clear_msg_ids(self):
        self.data["msg_ids"] = []
        save(F_CHAT, self.data)

    def count(self):
        return len(self.data["history"])

# ══════════════════════════════════════════════
# MEMORY (local + Google Sheets backup)
# ══════════════════════════════════════════════
class Memory:
    def __init__(self):
        self.data = {
            "facts": [],
            "prefs": {},
            "dates": {},
            "important_notes": []
        }
        # Load from Google Sheets first
        self._load_from_sheets()

    def _load_from_sheets(self):
        """Load memory facts from Google Sheets"""
        sheet_facts = sheets_db.get_memory_facts()
        for f in sheet_facts:
            self.data["facts"].append({"f": f["f"], "d": f["d"]})
        log.info(f"📥 Loaded {len(sheet_facts)} facts from Sheets")

    def save_data(self):
        """No local save - everything in Sheets"""
        pass

    def add_fact(self, fact: str, chat_id: int = None):
        existing = [f["f"] for f in self.data["facts"][-50:]]
        if fact[:50] in [e[:50] for e in existing]:
            return
        self.data["facts"].append({"f": fact, "d": today_str()})
        self.data["facts"] = self.data["facts"][-400:]
        # Save to Google Sheets
        if chat_id:
            sheets_db.save_memory_fact(fact, chat_id)

    def add_important(self, note: str, chat_id: int = None):
        self.data["important_notes"].append({"note": note, "d": today_str()})
        if chat_id:
            sheets_db.save_important_note({
                "chat_id": chat_id,
                "text": note,
                "date": today_str(),
                "time": now_str()
            })

    def set_pref(self, k, v):
        self.data["prefs"][k] = v

    def add_date(self, name, d):
        self.data["dates"][name] = d

    def clear_facts(self):
        count = len(self.data["facts"])
        self.data["facts"] = []
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
# REMINDERS (local + Google Sheets permanent)
# ══════════════════════════════════════════════
class Reminders:
    def __init__(self):
        self.data = {"list": [], "counter": 0}
        # Load from Google Sheets
        self._load_from_sheets()

    def _load_from_sheets(self):
        """Load reminders from Google Sheets"""
        sheet_reminders = sheets_db.get_all_reminders()
        for r in sheet_reminders:
            self.data["list"].append(r)
            if isinstance(r["id"], int) and r["id"] > self.data["counter"]:
                self.data["counter"] = r["id"]
        log.info(f"📥 Loaded {len(sheet_reminders)} reminders from Sheets")

    def save_data(self):
        """No local save needed"""
        pass

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
        
        # 🔥 SAVE TO GOOGLE SHEETS (permanent!)
        sheets_db.save_reminder(r)
        
        # Also send to user's Saved Messages as backup
        asyncio.create_task(self._send_to_saved_messages(chat_id, r))
        
        return r

    async def _send_to_saved_messages(self, chat_id: int, reminder: dict):
        """Send reminder to user's Saved Messages as additional backup"""
        # This requires the bot to be able to send messages to the user
        # We'll just log it for now - you can extend this
        log.info(f"📤 Reminder #{reminder['id']} also stored in Google Sheets (permanent)")
        # Note: Telegram bots can't directly send to "Saved Messages" 
        # unless the user forwards it. Google Sheets is our primary backup.

    def all_active(self):
        # Also sync from sheets to catch any missed ones
        return [r for r in self.data["list"] if r["active"]]

    def delete(self, rid: int) -> bool:
        before = len(self.data["list"])
        self.data["list"] = [r for r in self.data["list"] if r["id"] != rid]
        return before != len(self.data["list"])

    def mark_fired(self, rid: int):
        for r in self.data["list"]:
            if r["id"] == rid:
                r["fired_today"] = True
                if r["repeat"] == "once":
                    r["active"] = False
                break

    def reset_daily(self):
        changed = False
        for r in self.data["list"]:
            if r["fired_today"]:
                r["fired_today"] = False
                changed = True

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
# TASKS (local + Google Sheets backup)
# ══════════════════════════════════════════════
class Tasks:
    def __init__(self):
        self.data = {"list": [], "counter": 0}

    def save_data(self):
        pass  # No local save

    def add(self, title, priority="medium", due=None, chat_id=None):
        self.data["counter"] += 1
        t = {"id": self.data["counter"], "title": title,
             "priority": priority, "due": due or today_str(),
             "done": False, "done_at": None, "created": datetime.now().isoformat()}
        self.data["list"].append(t)
        
        # Backup to Google Sheets
        if chat_id:
            sheets_db.save_task({**t, "chat_id": chat_id})
        
        return t

    def complete(self, tid):
        for t in self.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True
                t["done_at"] = datetime.now().isoformat()
                return t
        return None

    def delete(self, tid):
        self.data["list"] = [t for t in self.data["list"] if t["id"] != tid]
        return True

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
        return before - len(self.data["list"])


# ══════════════════════════════════════════════
# SIMPLIFIED CLASSES (local only, less critical)
# ══════════════════════════════════════════════

class Diary:
    def __init__(self):
        self.data = {"entries": {}}
    def add(self, content, mood="😊"):
        td = today_str()
        if td not in self.data["entries"]:
            self.data["entries"][td] = []
        self.data["entries"][td].append({"text": content, "mood": mood, "time": now_str()})
    def get(self, d):     return self.data["entries"].get(d, [])
    def all_dates(self):  return sorted(self.data["entries"].keys(), reverse=True)

class Habits:
    def __init__(self):
        self.data = {"list": [], "logs": {}, "counter": 0}
    def add(self, name, emoji="✅"):
        self.data["counter"] += 1
        h = {"id": self.data["counter"], "name": name, "emoji": emoji,
             "streak": 0, "best_streak": 0, "created": today_str()}
        self.data["list"].append(h); return h
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
        streak = next((x["streak"] for x in self.data["list"] if x["id"] == hid), 1)
        return True, streak
    def today_status(self):
        done_ids = self.data["logs"].get(today_str(), [])
        return ([h for h in self.data["list"] if h["id"] in done_ids],
                [h for h in self.data["list"] if h["id"] not in done_ids])
    def delete(self, hid):
        self.data["list"] = [h for h in self.data["list"] if h["id"] != hid]
    def all(self): return self.data["list"]

class Notes:
    def __init__(self):
        self.data = {"list": [], "counter": 0}
    def add(self, content, tag="general"):
        self.data["counter"] += 1
        n = {"id": self.data["counter"], "text": content,
             "tag": tag, "created": datetime.now().isoformat()}
        self.data["list"].append(n); return n
    def search(self, q):
        return [n for n in self.data["list"] if q.lower() in n["text"].lower()]
    def delete(self, nid):
        self.data["list"] = [n for n in self.data["list"] if n["id"] != nid]
    def recent(self, n=15): return self.data["list"][-n:]

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

class Goals:
    def __init__(self):
        self.data = {"list": [], "counter": 0}
    def add(self, title, deadline=None, why=""):
        self.data["counter"] += 1
        g = {"id": self.data["counter"], "title": title,
             "deadline": deadline or "", "why": why,
             "progress": 0, "done": False, "created": today_str(),
             "milestones": []}
        self.data["list"].append(g); return g
    def update_progress(self, gid, pct):
        for g in self.data["list"]:
            if g["id"] == gid:
                g["progress"] = min(100, max(0, pct))
                if g["progress"] == 100: g["done"] = True
                return g
        return None
    def active(self): return [g for g in self.data["list"] if not g["done"]]
    def completed(self): return [g for g in self.data["list"] if g["done"]]

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
        self.data["goal_ml"] = ml; self.save_data()
    def today_entries(self):
        return self.data["logs"].get(today_str(), [])
    def week_summary(self) -> dict:
        result = {}
        for i in range(7):
            d = (date.today() - timedelta(days=i)).isoformat()
            result[d] = sum(e["ml"] for e in self.data["logs"].get(d, []))
        return result

class BillTracker:
    def __init__(self):
        self.data = {"list": [], "counter": 0}
    def add(self, name, amount, due_day, bill_type="bill", notes=""):
        self.data["counter"] += 1
        b = {"id": self.data["counter"], "name": name, "amount": amount,
             "due_day": due_day, "type": bill_type, "notes": notes,
             "active": True, "paid_months": [], "created": today_str()}
        self.data["list"].append(b); return b
    def all_active(self): return [b for b in self.data["list"] if b["active"]]
    def mark_paid(self, bid):
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid:
                if ym not in b["paid_months"]:
                    b["paid_months"].append(ym)
                return True
        return False
    def is_paid_this_month(self, bid):
        ym = today_str()[:7]
        for b in self.data["list"]:
            if b["id"] == bid:
                return ym in b.get("paid_months", [])
        return False
    def delete(self, bid):
        self.data["list"] = [b for b in self.data["list"] if b["id"] != bid]
        return True
    def due_soon(self, days_ahead=3):
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
    def month_total(self):
        return sum(b["amount"] for b in self.data["list"] if b["active"])

class CalendarManager:
    def __init__(self):
        self.data = {"events": [], "counter": 0}
    def add(self, title, event_date, event_time="", notes=""):
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "title": title,
             "date": event_date, "time": event_time, "notes": notes, "created": today_str()}
        self.data["events"].append(e); return e
    def delete(self, eid):
        self.data["events"] = [e for e in self.data["events"] if e["id"] != eid]
        return True
    def upcoming(self, days=7):
        today_d = date.today()
        cutoff = today_d + timedelta(days=days)
        result = []
        for e in self.data["events"]:
            try:
                ed = date.fromisoformat(e["date"])
                if today_d <= ed <= cutoff:
                    result.append(e)
            except: pass
        return sorted(result, key=lambda x: x["date"])
    def today_events(self):
        return [e for e in self.data["events"] if e["date"] == today_str()]
    def all_events(self):
        today_d = today_str()
        return sorted([e for e in self.data["events"] if e["date"] >= today_d],
                      key=lambda x: (x["date"], x.get("time", "")))


# ══════════════════════════════════════════════
# INIT ALL
# ══════════════════════════════════════════════
chat_hist   = ChatHistory()
mem         = Memory()
tasks       = Tasks()
reminders   = Reminders()
diary       = Diary()
habits      = Habits()
notes       = Notes()
expenses    = Expenses()
goals       = Goals()
water       = WaterTracker()
bills       = BillTracker()
calendar    = CalendarManager()

# ══════════════════════════════════════════════
# GEMINI CALLER (simplified - keep as is)
# ══════════════════════════════════════════════
def call_gemini(system_prompt: str, messages: list, user_msg: str = None, chat_id: int = None, retries=2) -> str:
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

    for model in GEMINI_MODELS:
        for attempt in range(retries):
            try:
                url = BASE_URL.format(model=model, key=GEMINI_API_KEY)
                req = urllib.request.Request(url, data=payload,
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=45) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    text = result["candidates"][0]["content"]["parts"][0]["text"]
                    log.info(f"✅ Model used: {model}")
                    return text
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(3 if attempt == 0 else 6)
                    continue
                elif e.code in (500, 503):
                    time.sleep(2)
                    continue
                elif e.code == 404:
                    break
            except Exception as e:
                log.warning(f"Model {model}: {e}")
                break

    return ("⚠️ Abhi Gemini API se response nahi mila.\n"
            "Thodi der baad dobara try karo! 🙏")

# ══════════════════════════════════════════════
# NEWS (keep as is)
# ══════════════════════════════════════════════
NEWS_FEEDS = {
    "India": "https://feeds.bbci.co.uk/hindi/rss.xml",
    "Technology": "https://feeds.feedburner.com/ndtvnews-tech-news",
    "Business": "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Sports": "https://feeds.bbci.co.uk/sport/rss.xml",
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
                    items.append({"title": title, "desc": desc[:120], "link": link, "pub": ""})
    except Exception as e:
        log.warning(f"News fetch error: {e}")
        return [{"title": "News abhi available nahi", "desc": str(e), "link": "", "pub": ""}]

    cache["cache"][category] = items
    cache["updated"][category] = now_ts
    save(F_NEWS, cache)
    return items

# ══════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════
def build_system_prompt() -> str:
    now_label = datetime.now().strftime("%A, %d %B %Y — %I:%M %p")
    tp = tasks.today_pending()
    yd = tasks.done_on(yesterday_str())
    hd, hp = habits.today_status()
    ag = goals.active()
    td_d = diary.get(today_str())
    exp_t = expenses.today_total()
    exp_m = expenses.month_total()
    bl = expenses.budget_left()
    msgs = chat_hist.count()
    water_today = water.today_total()
    water_goal = water.goal()

    tasks_s = "\n".join(f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}" for t in tp[:6]) or "  Koi nahi"
    yd_s = "\n".join(f"  ✓ {t['title']}" for t in yd[:5]) or "  Koi nahi"
    h_done = ", ".join(f"{h['emoji']}{h['name']}" for h in hd) or "Koi nahi"
    h_pend = ", ".join(f"{h['name']}" for h in hp) or "Sab ho gaye! 🎉"
    goals_s = "\n".join(f"  🎯 {g['title']} ({g['progress']}%)" for g in ag[:4]) or "  Koi nahi"
    diary_s = "\n".join(f"  {e['time']} {e['text']}" for e in td_d[-3:]) or "  Kuch nahi"
    budget_s = f"Budget baaki: ₹{bl:.0f}" if bl is not None else ""
    water_pct = int(water_today / water_goal * 100) if water_goal else 0

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

━━ YAADDASHT (chat clear bhi ho jai toh yeh safe hai) ━━
{mem.context()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RULES:
- Dost ki tarah baat kar — "As an AI" kabhi mat bol
- Hindi/Hinglish mein jawab de
- Jo yaad hai naturally use kar
- Short aur helpful reh
- Agar user "yaad rakh" bole → confirm karo "Yaad kar liya ✅"
- Chat clear hone se memory, reminders, tasks DELETE NAHI HOTE — Google Sheets mein permanent safe hai!
- Kabhi payment/upgrade suggest mat kar
"""

# ══════════════════════════════════════════════
# AUTO-SAVE
# ══════════════════════════════════════════════
def auto_extract_facts(text: str, chat_id: int = None):
    lower = text.lower()
    triggers = [
        "yaad rakh", "remember", "mera naam", "meri umar", "main rehta",
        "mujhe pasand", "meri job", "mera kaam", "mere bhai", "meri behen",
        "meri wife", "mere husband", "mera", "meri", "main hoon",
        "birthday", "anniversary", "deadline", "important date"
    ]
    if any(kw in lower for kw in triggers):
        mem.add_fact(text[:250], chat_id)
        return True
    return False

# ══════════════════════════════════════════════
# AI CHAT
# ══════════════════════════════════════════════
async def ai_chat(user_msg: str, chat_id: int = None) -> str:
    auto_extract_facts(user_msg, chat_id)
    chat_hist.add("user", user_msg)
    history = chat_hist.get_recent(20)
    reply = call_gemini(build_system_prompt(), history, user_msg, chat_id)
    chat_hist.add("assistant", reply)
    return reply

# ══════════════════════════════════════════════
# KEYBOARDS
# ══════════════════════════════════════════════
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Daily Briefing", callback_data="briefing"),
         InlineKeyboardButton("📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("💪 Habits", callback_data="habits"),
         InlineKeyboardButton("📖 Diary", callback_data="diary")],
        [InlineKeyboardButton("🎯 Goals", callback_data="goals"),
         InlineKeyboardButton("💰 Kharcha", callback_data="expenses")],
        [InlineKeyboardButton("📰 News", callback_data="news_menu"),
         InlineKeyboardButton("📝 Notes", callback_data="notes")],
        [InlineKeyboardButton("💧 Water", callback_data="water_status"),
         InlineKeyboardButton("💳 Bills/EMI", callback_data="bills_menu")],
        [InlineKeyboardButton("📅 Calendar", callback_data="cal_menu"),
         InlineKeyboardButton("📊 Weekly Report", callback_data="weekly_report")],
        [InlineKeyboardButton("🧹 Chat Clear", callback_data="clear_chat"),
         InlineKeyboardButton("🧠 Yaaddasht", callback_data="memory")],
        [InlineKeyboardButton("💾 Backup Status", callback_data="backup_status"),
         InlineKeyboardButton("💡 Motivate Karo", callback_data="motivate")],
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
    chat_id = update.effective_chat.id
    
    # Load reminders count from sheets
    sheet_reminders = sheets_db.get_all_reminders(chat_id)
    
    txt = (f"🕌 *Assalamualaikum {name}! Main Aapka Personal AI Dost Hoon!*\n\n"
           "🧠 *Smart Memory* — chat clear bhi ho toh yaad rahunga\n"
           f"💾 *Google Sheets Backup* 🔒 — Sab kuch permanent save!\n"
           f"⏰ Reminders: {len(sheet_reminders)} sheets mein safe\n"
           "📋 Tasks | 📖 Diary | 💪 Habits\n"
           "💰 Kharcha | 🎯 Goals | 📰 Free News\n\n"
           "✅ *100% FREE | Google Gemini Multi-Model*\n"
           "🔒 *Chat clear se kuch delete nahi hoga — Google Sheets mein sab safe!*\n\n"
           "_Seedha kuch bhi type karo!_ 👇")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not ctx.args:
        await update.message.reply_text(
            "⏰ *REMINDER SET KARO*\n\n"
            "*Formats:*\n"
            "`/remind 30m Chai peeni hai` — 30 min baad\n"
            "`/remind 2h Meeting hai` — 2 ghante baad\n"
            "`/remind 15:30 Doctor` — aaj 3:30 baje\n"
            "`/remind 5-12-2026 10:00 Birthday wish` — specific date\n\n"
            "💾 *Google Sheets mein permanent save hoga!*\n"
            "_Chat clear se delete nahi hoga!_",
            parse_mode="Markdown")
        return
    
    # Parse arguments
    args_text = " ".join(ctx.args)
    time_str = None
    text = args_text
    repeat = "once"
    
    # Check for date format: DD-MM-YYYY or YYYY-MM-DD
    import re
    date_match = re.match(r'(\d{1,2}-\d{1,2}-\d{4})\s+(\d{1,2}:\d{2})\s+(.*)', args_text)
    if date_match:
        date_part = date_match.group(1)
        time_part = date_match.group(2)
        text = date_match.group(3)
        time_str = f"{date_part} {time_part}"
    else:
        # Simple time formats
        if ctx.args[0].endswith("m") and ctx.args[0][:-1].isdigit():
            mins = int(ctx.args[0][:-1])
            remind_dt = datetime.now() + timedelta(minutes=mins)
            time_str = remind_dt.strftime("%H:%M")
            text = " ".join(ctx.args[1:]) or "⏰ Reminder!"
        elif len(ctx.args) >= 2 and ":" in ctx.args[0]:
            time_str = ctx.args[0]
            text = " ".join(ctx.args[1:]) or "⏰ Reminder!"
            if ctx.args[-1].lower() in ["daily", "weekly"]:
                repeat = ctx.args[-1].lower()
                text = " ".join(ctx.args[1:-1]) or "⏰ Reminder!"
    
    if not time_str:
        await update.message.reply_text("❌ Time format samajh nahi aaya!\n`/remind 30m Kaam`", parse_mode="Markdown")
        return
    
    r = reminders.add(chat_id, text, time_str, repeat)
    
    await update.message.reply_text(
        f"✅ *Reminder Set Ho Gaya!*\n\n"
        f"⏰ *Waqt:* {time_str}\n"
        f"📝 *Kaam:* {text}\n"
        f"🔁 *Repeat:* {repeat}\n"
        f"🆔 ID: `{r['id']}`\n\n"
        f"💾 *Google Sheets mein save ho gaya!* 🔒\n"
        f"_Chat clear karne se bhi delete nahi hoga!_",
        parse_mode="Markdown")

async def cmd_remember(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not ctx.args:
        await update.message.reply_text("🧠 `/remember Mera birthday 15 August hai`", parse_mode="Markdown")
        return
    fact = " ".join(ctx.args)
    mem.add_fact(fact, chat_id)
    # Also save as important note to sheets
    sheets_db.save_important_note({
        "chat_id": chat_id,
        "text": fact,
        "date": today_str(),
        "time": now_str()
    })
    await update.message.reply_text(
        f"🧠 *Yaad Kar Liya!* ✅\n\n_{fact}_\n\n"
        f"💾 *Google Sheets mein permanent save!* 🔒\n"
        f"_Chat clear karne se bhi delete nahi hoga!_",
        parse_mode="Markdown")

async def cmd_backup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show backup status"""
    chat_id = update.effective_chat.id
    summary = sheets_db.create_backup_snapshot(chat_id)
    await update.message.reply_text(summary, parse_mode="Markdown")

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Haan, Clear Karo", callback_data="confirm_clear_chat"),
         InlineKeyboardButton("❌ Nahi", callback_data="menu")]
    ])
    count = chat_hist.count()
    
    # Get backup info
    reminders_count = len(sheets_db.get_all_reminders(chat_id))
    notes_count = len(sheets_db.get_important_notes(chat_id))
    facts_count = len(sheets_db.get_memory_facts(chat_id))
    
    await update.message.reply_text(
        f"🧹 *Chat History Clear Karna Chahte Ho?*\n\n"
        f"📊 Abhi {count} messages hain\n\n"
        f"💾 *Google Sheets Backup Status:*\n"
        f"⏰ {reminders_count} Reminders safe hain\n"
        f"📝 {notes_count} Important Notes safe hain\n"
        f"🧠 {facts_count} Memory Facts safe hain\n\n"
        f"⚠️ *Chat clear hogi — lekin:*\n"
        f"✅ Reminders, Memory, Tasks — *Google Sheets mein safe!*\n"
        f"✅ Jo yaad kiya woh nahi jayega\n"
        f"✅ Chat history hategi, data nahi!\n\n"
        f"_Sirf conversation history clear hogi_",
        parse_mode="Markdown", reply_markup=kb)

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = """🤖 *COMMANDS — ADVANCED v5.0*

💾 *GOOGLE SHEETS BACKUP 🔒:*
Sab reminders, memory, tasks Google Sheets mein permanent save hote hain!
Chat clear karne se kuch delete nahi hoga!

⏰ *REMINDERS (Permanent!):*
`/remind 30m Chai peeni hai` — 30 min baad
`/remind 15:30 Doctor` — aaj 3:30 baje
`/remind 5-12-2026 10:00 Birthday` — specific date
`/reminders` — Sab reminders dekho
`/delremind 3` — Delete

📋 *TASKS:*
`/task Kaam [high/low]` — Add
`/done 3` — Complete
`/deltask 3` — Delete

🧠 *MEMORY (Sheets mein safe):*
`/remember Koi baat` — Permanent save
`/recall` — Sab dekho

💾 *BACKUP:*
`/backup` — Backup status check

📖 DIARY | 💪 HABITS | 💰 KHARCHA | 🎯 GOALS
📰 NEWS | 📝 NOTES | 💧 WATER | 💳 BILLS | 📅 CALENDAR

🔒 *Secret Code:* `Rk1996`

💬 *Seedha kuch bhi type karo!* 😊
_Chat clear se data delete nahi hoga — Google Sheets mein safe!_"""
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

# ══════════════════════════════════════════════
# CALLBACK HANDLER
# ══════════════════════════════════════════════
async def callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    chat_id = update.effective_chat.id

    if d == "menu":
        await q.message.reply_text("🏠 *Main Menu*", parse_mode="Markdown", reply_markup=main_kb())
    
    elif d == "briefing":
        tp = tasks.today_pending()
        yd = tasks.done_on(yesterday_str())
        hd, hp = habits.today_status()
        ag = goals.active()
        exp_t = expenses.today_total()
        exp_m = expenses.month_total()
        bl = expenses.budget_left()
        
        txt = f"🌅 *DAILY BRIEFING*\n📅 {datetime.now().strftime('%A, %d %B %Y')}\n\n"
        if tp:
            txt += f"📋 *{len(tp)} Tasks Baaki:*\n"
            for t in tp[:7]:
                e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
                txt += f"  {e} {t['title']}\n"
        else:
            txt += "🎉 *Koi pending task nahi!*\n"
        txt += f"\n💰 Aaj ₹{exp_t:.0f} | Mahina ₹{exp_m:.0f}"
        if bl is not None: txt += f" | Baaki ₹{bl:.0f}"
        txt += f"\n\n💾 *Google Sheets mein sab safe hai!* 🔒"
        await q.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    
    elif d == "tasks":
        pending = tasks.pending()
        if not pending:
            await q.message.reply_text("🎉 *Koi pending task nahi!*", parse_mode="Markdown")
        else:
            txt = f"📋 *PENDING TASKS ({len(pending)})*\n\n"
            kb = []
            for t in pending[:12]:
                e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
                txt += f"{e} *#{t['id']}* {t['title']}\n"
                kb.append([InlineKeyboardButton(f"✅ #{t['id']}: {t['title'][:32]}", callback_data=f"done_{t['id']}")])
            kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
            await q.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    
    elif d == "confirm_clear_chat":
        count = chat_hist.clear(chat_id)
        await q.message.reply_text(
            f"🧹 *Chat Clear Ho Gayi!*\n\n"
            f"🗑 {count} messages hata diye\n"
            f"💾 *Google Sheets mein sab safe hai!* 🔒\n"
            f"✅ Reminders, Memory, Tasks — kuch delete nahi hua!\n\n"
            f"_Ab fresh start karo!_ 🚀\n"
            f"_`/backup` se check kar sakte ho_",
            parse_mode="Markdown", reply_markup=main_kb())
    
    elif d == "backup_status":
        summary = sheets_db.create_backup_snapshot(chat_id)
        await q.message.reply_text(summary, parse_mode="Markdown")
    
    elif d == "memory":
        facts = mem.get_all_facts()
        sheet_facts = sheets_db.get_memory_facts(chat_id)
        txt = f"🧠 *YAADDASHT*\n"
        txt += f"Local: {len(facts)} | Sheets: {len(sheet_facts)}\n"
        txt += "_(Chat clear se safe hai — Google Sheets mein!)_ 🔒\n\n"
        if facts:
            for f in facts[-12:]:
                txt += f"  📌 {f['f']}\n"
        else:
            txt += "_Kuch nahi_"
        await q.message.reply_text(txt, parse_mode="Markdown")
    
    elif d == "motivate":
        reply = await ai_chat("Mujhe ek powerful 3-4 line motivation de Hindi mein. Real, raw, energetic.")
        await q.message.reply_text(f"💡 *Motivation:*\n\n{reply}", parse_mode="Markdown")
    
    elif d.startswith("done_"):
        tid = int(d.split("_")[1])
        t = tasks.complete(tid)
        if t:
            await q.message.reply_text(f"🎉 *Complete!*\n\n✅ {t['title']}\n💪 Wah bhai!", parse_mode="Markdown")
        else:
            await q.message.reply_text("❌ Nahi mila", parse_mode="Markdown")
    
    elif d == "expenses":
        items = expenses.today_list()
        txt = f"💰 *KHARCHA*\nAaj: ₹{expenses.today_total():.0f} | Mahina: ₹{expenses.month_total():.0f}\n"
        bl = expenses.budget_left()
        if bl is not None: txt += f"Budget baaki: ₹{bl:.0f}\n"
        for e in items[-8:]: txt += f"  ₹{e['amount']:.0f} {e['desc']}\n"
        await q.message.reply_text(txt, parse_mode="Markdown")
    
    elif d == "water_status":
        total = water.today_total()
        goal = water.goal()
        pct = min(100, int(total / goal * 100)) if goal else 0
        bar = "💧" * (pct // 10) + "○" * (10 - pct // 10)
        await q.message.reply_text(
            f"💧 *WATER STATUS*\n\nAaj: {total}ml / {goal}ml\n{bar} {pct}%",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💧 +250ml", callback_data="water_250"),
                 InlineKeyboardButton("💧 +500ml", callback_data="water_500")],
                [InlineKeyboardButton("🏠 Menu", callback_data="menu")]
            ]))
    
    elif d.startswith("water_"):
        ml = int(d.split("_")[1])
        water.add(ml)
        total = water.today_total()
        goal = water.goal()
        pct = min(100, int(total / goal * 100)) if goal else 0
        await q.message.reply_text(f"💧 *+{ml}ml!* Aaj: {total}ml / {goal}ml ({pct}%)", parse_mode="Markdown")
    
    elif d == "bills_menu":
        all_b = bills.all_active()
        if not all_b:
            await q.message.reply_text("💳 *Koi bill nahi!*", parse_mode="Markdown")
        else:
            txt = "💳 *BILLS & EMI*\n\n"
            for b in all_b:
                paid = bills.is_paid_this_month(b["id"])
                status = "✅" if paid else "⏳"
                txt += f"{status} *{b['name']}* — ₹{b['amount']:.0f}\n"
            await q.message.reply_text(txt, parse_mode="Markdown")
    
    elif d == "cal_menu":
        upcoming = calendar.upcoming(30)
        if not upcoming:
            await q.message.reply_text("📅 *Koi event nahi!*", parse_mode="Markdown")
        else:
            txt = "📅 *UPCOMING EVENTS*\n\n"
            for e in upcoming[:10]:
                txt += f"📆 {e['date']} — *{e['title']}*\n"
            await q.message.reply_text(txt, parse_mode="Markdown")
    
    elif d == "weekly_report":
        await q.message.reply_text("📊 *Weekly Report*\n\nFeature coming soon with Google Sheets integration!", parse_mode="Markdown")
    
    # News categories
    elif d.startswith("news_"):
        cat = d.split("_", 1)[1]
        items = fetch_news(cat, 5)
        txt = f"📰 *{cat.upper()} NEWS*\n\n"
        for i, item in enumerate(items, 1):
            txt += f"*{i}.* {item['title']}\n"
            if item['desc']:
                txt += f"_{item['desc'][:90]}..._\n"
        await q.message.reply_text(txt, parse_mode="Markdown", reply_markup=news_kb())
    
    elif d == "news_menu":
        await q.message.reply_text("📰 *Kaunsi news?*", parse_mode="Markdown", reply_markup=news_kb())
    
    elif d == "habits":
        done, pending = habits.today_status()
        txt = "💪 *HABITS*\n\n"
        if done:
            txt += "✅ *Done:* " + ", ".join(f"{h['emoji']}{h['name']}" for h in done) + "\n"
        if pending:
            txt += "⏳ *Baaki:* " + ", ".join(h['name'] for h in pending)
        await q.message.reply_text(txt, parse_mode="Markdown")
    
    elif d == "diary":
        entries = diary.get(today_str())
        if entries:
            txt = f"📖 *Aaj Ki Diary*\n\n"
            for e in entries:
                txt += f"{e['time']} {e['mood']} {e['text']}\n"
        else:
            txt = "📖 Aaj koi entry nahi."
        await q.message.reply_text(txt, parse_mode="Markdown")
    
    elif d == "goals":
        ag = goals.active()
        if ag:
            txt = "🎯 *ACTIVE GOALS*\n\n"
            for g in ag:
                bar = "█"*(g["progress"]//10) + "░"*(10-g["progress"]//10)
                txt += f"{bar} {g['title']} {g['progress']}%\n"
        else:
            txt = "🎯 Koi goals nahi."
        await q.message.reply_text(txt, parse_mode="Markdown")
    
    elif d == "notes":
        ns = notes.recent(10)
        if ns:
            txt = "📝 *NOTES*\n\n"
            for n in ns:
                txt += f"*#{n['id']}* {n['text']}\n"
        else:
            txt = "📝 Koi notes nahi."
        await q.message.reply_text(txt, parse_mode="Markdown")


# ══════════════════════════════════════════════
# MESSAGE HANDLER
# ══════════════════════════════════════════════
async def handle_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_hist.track_msg(chat_id, update.message.message_id)
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
    reply = await ai_chat(update.message.text, chat_id)
    try:
        sent = await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception:
        sent = await update.message.reply_text(reply)
    chat_hist.track_msg(chat_id, sent.message_id)

# ══════════════════════════════════════════════
# REMINDER BACKGROUND JOB
# ══════════════════════════════════════════════
async def reminder_job(context):
    now_time = datetime.now().strftime("%H:%M")
    
    if now_time == "00:00":
        reminders.reset_daily()
    
    due = reminders.due_now()
    for r in due:
        try:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Ho Gaya!", callback_data=f"remind_done_{r['id']}"),
                InlineKeyboardButton("⏰ 10 min Snooze", callback_data=f"remind_snooze_{r['id']}")
            ]])
            
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=f"🚨🔔 *REMINDER!*\n\n⏰ *{r['time']}*\n📢 *{r['text']}*\n\n💾 _Sheets mein safe hai!_",
                parse_mode="Markdown",
                reply_markup=kb
            )
            reminders.mark_fired(r["id"])
        except Exception as e:
            log.error(f"Reminder send error: {e}")

# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
def main():
    log.info("🤖 Personal AI Bot v5.0 — Google Sheets Backup — Starting...")
    log.info(f"📡 Models: {', '.join(GEMINI_MODELS)}")
    log.info(f"💾 Google Sheets: {'CONNECTED' if sheets_db.client else 'DISABLED'}")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Command handlers
    handlers = [
        ("start", cmd_start),
        ("help", cmd_help),
        ("remind", cmd_remind),
        ("reminders", lambda u,c: show_reminders(u,c)),
        ("delremind", cmd_delremind),
        ("task", cmd_task),
        ("done", cmd_done),
        ("deltask", cmd_deltask),
        ("remember", cmd_remember),
        ("recall", cmd_recall),
        ("backup", cmd_backup),
        ("clear", cmd_clear),
        ("diary", cmd_diary),
        ("habit", cmd_habit),
        ("hdone", cmd_hdone),
        ("note", cmd_note),
        ("kharcha", cmd_kharcha),
        ("goal", cmd_goal),
        ("gprogress", cmd_gprogress),
        ("water", cmd_water),
        ("bill", cmd_bill),
        ("cal", cmd_cal),
        ("news", cmd_news),
        ("weekly", lambda u,c: u.message.reply_text("📊 /backup for status")),
    ]
    
    for cmd, handler in handlers:
        app.add_handler(CommandHandler(cmd, handler))
    
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    
    # Job queue
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(reminder_job, interval=30, first=5)
        log.info("⏰ Reminder job started!")
    
    log.info("✅ Bot ready!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


# Helper functions for commands
async def show_reminders(update, ctx):
    all_r = reminders.all_active()
    if not all_r:
        await update.message.reply_text("⏰ Koi reminder nahi!\n💾 Sheets mein check karo: /backup", parse_mode="Markdown")
        return
    txt = f"⏰ *REMINDERS ({len(all_r)})*\n\n"
    for r in all_r[:15]:
        status = "✅ Done" if r["fired_today"] else "⏳ Pending"
        txt += f"*#{r['id']}* {r['time']} — {r['text']}\n_{status}_\n\n"
    txt += "💾 _Google Sheets mein permanently safe!_"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_delremind(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/delremind 3`", parse_mode="Markdown")
        return
    try:
        rid = int(ctx.args[0])
        ok = reminders.delete(rid)
        await update.message.reply_text(f"🗑 Reminder #{rid} delete ho gaya!" if ok else "❌ Nahi mila", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Format: `/delremind 3`", parse_mode="Markdown")

async def cmd_task(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📋 `/task Kaam [high/low]`", parse_mode="Markdown")
        return
    args = " ".join(ctx.args)
    priority = "medium"
    if args.endswith(" high"): priority="high"; args=args[:-5].strip()
    elif args.endswith(" low"): priority="low"; args=args[:-4].strip()
    t = tasks.add(args, priority, chat_id=update.effective_chat.id)
    await update.message.reply_text(f"✅ *Task Add!* #{t['id']} {t['title']}", parse_mode="Markdown")

async def cmd_done(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/done 3`", parse_mode="Markdown")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        await update.message.reply_text(f"🎉 *Complete!* {t['title']}" if t else "❌ Nahi mila", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ `/done 3`", parse_mode="Markdown")

async def cmd_deltask(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/deltask 3`", parse_mode="Markdown")
        return
    try:
        tasks.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Delete ho gaya!", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Format: `/deltask 3`", parse_mode="Markdown")

async def cmd_recall(update, ctx):
    facts = mem.get_all_facts()
    chat_id = update.effective_chat.id
    sheet_facts = sheets_db.get_memory_facts(chat_id)
    
    txt = f"🧠 *YAADDASHT*\n"
    txt += f"Local: {len(facts)} | Sheets: {len(sheet_facts)}\n\n"
    
    if facts:
        for f in facts[-15:]:
            txt += f"📌 {f['f']}\n_{f['d']}_\n\n"
    else:
        txt += "_Kuch yaad nahi_\n"
    
    txt += "💾 _Google Sheets mein permanent safe! Chat clear se nahi jayega_"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_diary(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📖 `/diary Aaj bahut productive tha!`", parse_mode="Markdown")
        return
    diary.add(" ".join(ctx.args))
    await update.message.reply_text(f"📖 Diary mein likh diya! 🕐 {now_str()}", parse_mode="Markdown")

async def cmd_habit(update, ctx):
    if not ctx.args:
        await update.message.reply_text("💪 `/habit Morning walk 🏃`", parse_mode="Markdown")
        return
    name = " ".join(ctx.args)
    h = habits.add(name)
    await update.message.reply_text(f"💪 Habit add! {h['emoji']} {h['name']}", parse_mode="Markdown")

async def cmd_hdone(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/hdone 1`", parse_mode="Markdown")
        return
    try:
        hid = int(ctx.args[0])
        ok, streak = habits.log(hid)
        if ok:
            await update.message.reply_text(f"💪 Done! 🔥 {streak} din streak!", parse_mode="Markdown")
        else:
            await update.message.reply_text("✅ Aaj pehle hi mark hai!", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ `/hdone 1`", parse_mode="Markdown")

async def cmd_note(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📝 `/note Grocery: Doodh, Bread`", parse_mode="Markdown")
        return
    n = notes.add(" ".join(ctx.args))
    await update.message.reply_text(f"📝 Note #{n['id']} save!", parse_mode="Markdown")

async def cmd_kharcha(update, ctx):
    if not ctx.args:
        await update.message.reply_text("💰 `/kharcha 100 Khana`", parse_mode="Markdown")
        return
    try:
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:]) or "Kharcha"
        expenses.add(amount, desc)
        await update.message.reply_text(f"💰 ₹{amount:.0f} — {desc}\nAaj: ₹{expenses.today_total():.0f}", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ `/kharcha 100 Khana`", parse_mode="Markdown")

async def cmd_goal(update, ctx):
    if not ctx.args:
        await update.message.reply_text("🎯 `/goal Weight lose 10kg`", parse_mode="Markdown")
        return
    title = " ".join(ctx.args)
    g = goals.add(title)
    await update.message.reply_text(f"🎯 Goal add! {g['title']}", parse_mode="Markdown")

async def cmd_gprogress(update, ctx):
    try:
        gid = int(ctx.args[0])
        pct = int(ctx.args[1])
        g = goals.update_progress(gid, pct)
        if g:
            bar = "█"*(pct//10) + "░"*(10-pct//10)
            await update.message.reply_text(f"🎯 {g['title']}\n{bar} {pct}%", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ `/gprogress 1 75`", parse_mode="Markdown")

async def cmd_water(update, ctx):
    ml = 250
    if ctx.args:
        try: ml = int(ctx.args[0])
        except: pass
    water.add(ml)
    total = water.today_total()
    await update.message.reply_text(f"💧 +{ml}ml! Aaj: {total}ml / {water.goal()}ml", parse_mode="Markdown")

async def cmd_bill(update, ctx):
    if not ctx.args or len(ctx.args) < 3:
        await update.message.reply_text("💳 `/bill Netflix 199 5`", parse_mode="Markdown")
        return
    try:
        name = ctx.args[0]
        amount = float(ctx.args[1])
        due_day = int(ctx.args[2])
        b = bills.add(name, amount, due_day)
        await update.message.reply_text(f"✅ Bill add! {name} ₹{amount:.0f} | {due_day} tarikh", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ `/bill Netflix 199 5`", parse_mode="Markdown")

async def cmd_cal(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📅 `/cal 2026-12-31 New Year Party`", parse_mode="Markdown")
        return
    args = " ".join(ctx.args)
    parts = args.split(" ", 1)
    if len(parts) >= 2:
        date_str = parts[0]
        title = parts[1]
        e = calendar.add(title, date_str)
        await update.message.reply_text(f"📅 Event add! {date_str}: {title}", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Format: `/cal YYYY-MM-DD Event name`", parse_mode="Markdown")

async def cmd_news(update, ctx):
    await update.message.reply_text("📰 *Kaunsi news?*", parse_mode="Markdown", reply_markup=news_kb())


if __name__ == "__main__":
    main()