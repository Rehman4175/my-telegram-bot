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

# Secret code for accessing old logs
SECRET_CODE = "Rk1996"
SECRET_CODE_HASH = hashlib.sha256(SECRET_CODE.encode()).hexdigest()

# Multi-Model Fallback
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

# ══════════════════════════════════════════════
# FILE PATHS - Enhanced with offline queue
# ══════════════════════════════════════════════
DATA = os.path.join(os.getcwd(), "data")
os.makedirs(DATA, exist_ok=True)

F_MEMORY    = os.path.join(DATA, "memory.json")
F_TASKS     = os.path.join(DATA, "tasks.json")
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
F_OFFLINE   = os.path.join(DATA, "offline_queue.json")  # NEW: Offline message queue
F_ALL_LOGS  = os.path.join(DATA, "all_activity_log.json")  # NEW: Complete activity log

# ══════════════════════════════════════════════
# ENHANCED LOGGING SYSTEM
# ══════════════════════════════════════════════
class ActivityLogger:
    """Har activity ko log karo - chahe AI online ho ya offline"""
    
    def __init__(self):
        self.log_file = F_ALL_LOGS
        self.data = self.load_logs()
    
    def load_logs(self):
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return {"activities": [], "protected_activities": []}
    
    def save_logs(self):
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"Activity log save error: {e}")
    
    def log_activity(self, activity_type: str, user_id: int, username: str, 
                     content: str, status: str = "completed", protected: bool = False):
        """Activity log karo"""
        activity = {
            "timestamp": datetime.now().isoformat(),
            "type": activity_type,
            "user_id": user_id,
            "username": username,
            "content": content[:500],  # Limit content length
            "status": status,  # completed, failed, offline
            "date": today_str()
        }
        
        self.data["activities"].append(activity)
        
        # Important activities ko protected list mein bhi rakho
        if protected or activity_type in ["task_added", "task_completed", "memory_saved", 
                                          "important_note", "reminder_set"]:
            self.data["protected_activities"].append(activity)
        
        # Keep last 10000 activities
        self.data["activities"] = self.data["activities"][-10000:]
        self.data["protected_activities"] = self.data["protected_activities"][-5000:]
        
        self.save_logs()
    
    def get_protected_activities(self, date_filter=None):
        """Protected activities lo"""
        activities = self.data["protected_activities"]
        if date_filter:
            activities = [a for a in activities if a["date"] == date_filter]
        return activities
    
    def get_all_activities(self, date_filter=None, activity_type=None):
        """Filtered activities lo"""
        activities = self.data["activities"]
        if date_filter:
            activities = [a for a in activities if a["date"] == date_filter]
        if activity_type:
            activities = [a for a in activities if a["type"] == activity_type]
        return activities

# ══════════════════════════════════════════════
# OFFLINE QUEUE SYSTEM
# ══════════════════════════════════════════════
class OfflineQueue:
    """Jab AI offline ho, messages queue mein save karo"""
    
    def __init__(self):
        self.queue_file = F_OFFLINE
        self.queue = self.load_queue()
        self.lock = threading.Lock()
    
    def load_queue(self):
        try:
            if os.path.exists(self.queue_file):
                with open(self.queue_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return {"pending_messages": [], "processed_messages": []}
    
    def save_queue(self):
        with self.lock:
            try:
                with open(self.queue_file, "w", encoding="utf-8") as f:
                    json.dump(self.queue, f, ensure_ascii=False, indent=2)
            except Exception as e:
                log.error(f"Offline queue save error: {e}")
    
    def add_message(self, user_id: int, chat_id: int, username: str, message: str):
        """Message queue mein add karo jab AI offline ho"""
        with self.lock:
            msg_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "chat_id": chat_id,
                "username": username,
                "message": message,
                "processed": False
            }
            self.queue["pending_messages"].append(msg_entry)
            self.save_queue()
            log.info(f"📥 Offline queue: Message saved from {username}")
    
    def get_pending_messages(self):
        """Pending messages lo"""
        return [m for m in self.queue["pending_messages"] if not m["processed"]]
    
    def mark_processed(self, message_index: int):
        """Message processed mark karo"""
        with self.lock:
            if 0 <= message_index < len(self.queue["pending_messages"]):
                self.queue["pending_messages"][message_index]["processed"] = True
                self.save_queue()
    
    def clear_processed(self):
        """Processed messages clear karo (keep last 100)"""
        with self.lock:
            unprocessed = [m for m in self.queue["pending_messages"] if not m["processed"]]
            processed = [m for m in self.queue["pending_messages"] if m["processed"]]
            self.queue["pending_messages"] = unprocessed + processed[-100:]
            self.save_queue()

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
    """Secret code verify karo"""
    return hashlib.sha256(code.encode()).hexdigest() == SECRET_CODE_HASH

# ══════════════════════════════════════════════
# ENHANCED GEMINI CALLER WITH OFFLINE HANDLING
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

    # All models failed - return offline message
    offline_msg = ("⚠️ *AI Abhi Offline Hai!*\n\n"
                   "😔 Gemini API se connection nahi ho pa raha.\n"
                   "📝 *Aapka message save kar liya hai* - jab AI online hoga tab process hoga.\n\n"
                   "_Important messages automatically save ho jate hain_ ✅\n"
                   f"_({', '.join(errors[:2])})_")
    return offline_msg

# Class definitions continue with enhanced features...
# [Memory, Tasks, Diary, Habits, Notes, Expenses, Goals classes remain similar]

# ══════════════════════════════════════════════
# ENHANCED REMINDERS WITH BETTER TRACKING
# ══════════════════════════════════════════════
class Reminders:
    def __init__(self):
        self.data = load(F_REMINDERS, {"list": [], "counter": 0, "log": []})

    def save_data(self): 
        save(F_REMINDERS, self.data)

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
            "created":   datetime.now().isoformat(),
            "history": []  # Track when it fired
        }
        self.data["list"].append(r)
        
        # Log this action
        self.data["log"].append({
            "timestamp": datetime.now().isoformat(),
            "action": "created",
            "reminder_id": r["id"],
            "text": text,
            "time": remind_at
        })
        
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
                r["history"].append({
                    "fired_at": datetime.now().isoformat(),
                    "date": today_str()
                })
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
                if 0 <= diff < 120:  # 2 minute window
                    due.append(r)
            except Exception:
                if r_time == now_str_hm:
                    due.append(r)
        return due

    def get_all(self):
        return self.data["list"]
    
    def get_reminders_history(self, date_filter=None):
        """Reminder firing history lo"""
        history = []
        for r in self.data["list"]:
            for fire_record in r.get("history", []):
                if not date_filter or fire_record.get("date") == date_filter:
                    history.append({
                        "reminder_id": r["id"],
                        "text": r["text"],
                        "fired_at": fire_record["fired_at"]
                    })
        return sorted(history, key=lambda x: x["fired_at"], reverse=True)

# ══════════════════════════════════════════════
# ENHANCED TASKS WITH COMPLETE HISTORY
# ══════════════════════════════════════════════
class Tasks:
    def __init__(self):
        self.data = load(F_TASKS, {"list": [], "counter": 0, "completed_history": []})

    def save_data(self): 
        save(F_TASKS, self.data)

    def add(self, title, priority="medium", due=None):
        self.data["counter"] += 1
        t = {"id": self.data["counter"], "title": title,
             "priority": priority, "due": due or today_str(),
             "done": False, "done_at": None, "created": datetime.now().isoformat(),
             "completed_date": None}
        self.data["list"].append(t)
        self.save_data()
        return t

    def complete(self, tid):
        for t in self.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True
                t["done_at"] = datetime.now().isoformat()
                t["completed_date"] = today_str()
                # Move to completed history
                self.data["completed_history"].append({
                    "original_task": t.copy(),
                    "completed_timestamp": datetime.now().isoformat()
                })
                self.save_data()
                return t
        return None

    def delete(self, tid):
        before = len(self.data["list"])
        self.data["list"] = [t for t in self.data["list"] if t["id"] != tid]
        self.save_data()
        return before != len(self.data["list"])

    def pending(self):
        return [t for t in self.data["list"] if not t["done"]]
    
    def all_tasks(self):
        """Saare tasks - pending + done"""
        return self.data["list"]
    
    def completed_tasks(self):
        """Sirf completed tasks"""
        return [t for t in self.data["list"] if t["done"]]
    
    def done_on(self, d):
        """Kisi specific date pe complete hue tasks"""
        return [t for t in self.data["list"] 
                if t["done"] and t.get("completed_date", "") == d]
    
    def today_pending(self):
        td = today_str()
        return [t for t in self.data["list"] 
                if not t["done"] and t.get("due", "") <= td]
    
    def clear_done(self):
        before = len(self.data["list"])
        # Move to history before clearing
        for t in self.data["list"]:
            if t["done"]:
                self.data["completed_history"].append({
                    "task": t,
                    "cleared_at": datetime.now().isoformat()
                })
        self.data["list"] = [t for t in self.data["list"] if not t["done"]]
        self.save_data()
        return before - len(self.data["list"])
    
    def get_completed_history(self, date_filter=None):
        """Completed tasks history lo"""
        history = []
        for entry in self.data.get("completed_history", []):
            task = entry.get("original_task", entry.get("task", {}))
            if not date_filter or task.get("completed_date") == date_filter:
                history.append(task)
        return history

# ══════════════════════════════════════════════
# INIT ALL
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

# ══════════════════════════════════════════════
# ENHANCED COMMAND HANDLERS
# ══════════════════════════════════════════════

async def cmd_all_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Saare tasks dikhao - pending + completed"""
    all_t = tasks.all_tasks()
    if not all_t:
        await update.message.reply_text("📋 *Koi task nahi hai!*\n\n`/task Task naam` se add karo", 
                                       parse_mode="Markdown")
        return
    
    txt = f"📋 *SAARE TASKS ({len(all_t)})*\n\n"
    
    # Pending tasks
    pending = [t for t in all_t if not t["done"]]
    if pending:
        txt += "*⏳ PENDING:*\n"
        for t in pending:
            e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
            txt += f"{e} *#{t['id']}* {t['title']} _{t.get('due', '')}_\n"
        txt += "\n"
    
    # Completed tasks
    completed = [t for t in all_t if t["done"]]
    if completed:
        txt += "*✅ COMPLETED:*\n"
        for t in completed[-10:]:  # Last 10 completed
            completed_date = t.get("completed_date", "Unknown")
            txt += f"✓ *#{t['id']}* {t['title']} _{completed_date}_\n"
    
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Sirf completed tasks dikhao"""
    completed = tasks.completed_tasks()
    if not completed:
        await update.message.reply_text("✅ *Koi completed task nahi hai!*\n\nAbhi tak kuch complete nahi kiya?", 
                                       parse_mode="Markdown")
        return
    
    txt = f"✅ *COMPLETED TASKS ({len(completed)})*\n\n"
    for t in completed[-15:]:  # Last 15 completed
        completed_date = t.get("completed_date", "Unknown")
        done_time = t.get("done_at", "")[:16] if t.get("done_at") else ""
        txt += f"✓ *#{t['id']}* {t['title']}\n"
        txt += f"  📅 Completed: {completed_date} at {done_time}\n\n"
    
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_task_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Task history with secret code"""
    if not ctx.args:
        await update.message.reply_text(
            "🔐 *Secret code daalo:*\n`/taskhistory Rk1996`",
            parse_mode="Markdown")
        return
    
    if not verify_secret_code(ctx.args[0]):
        await update.message.reply_text("❌ *Galat secret code!* Access denied.", 
                                       parse_mode="Markdown")
        return
    
    # Get all history
    completed_history = tasks.get_completed_history()
    all_activities = activity_logger.get_all_activities(activity_type="task_completed")
    
    txt = f"🔓 *TASK HISTORY (Authorized Access)*\n\n"
    txt += f"📊 Total completed tasks: {len(completed_history)}\n"
    txt += f"📝 Activity logs: {len(all_activities)}\n\n"
    
    if completed_history:
        txt += "*Recent Completed Tasks:*\n"
        for t in completed_history[-10:]:
            txt += f"✓ {t.get('title', 'Unknown')} - {t.get('completed_date', 'Unknown')}\n"
    
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_offline_messages(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Offline messages dekho"""
    if not ctx.args:
        await update.message.reply_text(
            "🔐 *Secret code daalo:*\n`/offlinemsgs Rk1996`",
            parse_mode="Markdown")
        return
    
    if not verify_secret_code(ctx.args[0]):
        await update.message.reply_text("❌ *Galat secret code!*", parse_mode="Markdown")
        return
    
    pending = offline_queue.get_pending_messages()
    if not pending:
        await update.message.reply_text("📥 *Koi offline message nahi hai!*", parse_mode="Markdown")
        return
    
    txt = f"🔓 *OFFLINE MESSAGES ({len(pending)})*\n\n"
    for i, msg in enumerate(pending[:10]):
        txt += f"*{i+1}.* {msg['username']} ({msg['timestamp'][:16]})\n"
        txt += f"   {msg['message'][:100]}...\n\n"
    
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_verify_secret(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Secret code verify karo for session"""
    if not ctx.args:
        await update.message.reply_text("🔐 `/verify Rk1996` - Code daalo", parse_mode="Markdown")
        return
    
    if verify_secret_code(ctx.args[0]):
        # Store verification in user data
        chat_hist.add("system", f"User verified with secret code at {datetime.now()}")
        await update.message.reply_text(
            "✅ *Code verified!*\n\n"
            "Aap abhi protected data access kar sakte hain:\n"
            "• `/taskhistory` - Task history\n"
            "• `/offlinemsgs` - Offline messages\n"
            "• `/alllogs` - Complete activity logs\n"
            "• `/reminderlog` - Reminder firing history",
            parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ *Galat code!*", parse_mode="Markdown")

# ══════════════════════════════════════════════
# ENHANCED MESSAGE HANDLER WITH OFFLINE CAPTURE
# ══════════════════════════════════════════════
async def handle_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Enhanced message handler with offline capture"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    message_text = update.message.text
    
    # Track message
    chat_hist.track_msg(chat_id, update.message.message_id)
    
    # Log activity
    activity_logger.log_activity(
        "message_received", 
        user.id, 
        user.username or user.first_name,
        message_text,
        "received"
    )
    
    # Check if message contains important keywords - mark as protected
    important_keywords = ["yaad rakh", "remember", "task", "reminder", "alarm", "important"]
    is_important = any(keyword in message_text.lower() for keyword in important_keywords)
    
    if is_important:
        activity_logger.log_activity(
            "important_message",
            user.id,
            user.username or user.first_name,
            message_text,
            "protected",
            protected=True
        )
    
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        reply = await ai_chat(message_text, chat_id=chat_id)
        
        # Check if AI is offline
        if "⚠️ *AI Abhi Offline Hai!*" in reply:
            # Save to offline queue
            offline_queue.add_message(user.id, chat_id, 
                                     user.username or user.first_name, 
                                     message_text)
            activity_logger.log_activity(
                "offline_saved",
                user.id,
                user.username or user.first_name,
                message_text,
                "queued",
                protected=is_important
            )
        
        try:
            sent = await update.message.reply_text(reply, parse_mode="Markdown")
        except Exception:
            sent = await update.message.reply_text(reply)
        
        chat_hist.track_msg(chat_id, sent.message_id)
        activity_logger.log_activity(
            "response_sent",
            user.id,
            user.username or user.first_name,
            reply[:200],
            "sent"
        )
        
    except Exception as e:
        log.error(f"Message handling error: {e}")
        error_msg = "❌ *Error!* Message process nahi ho paaya. Offline queue mein save kar diya hai."
        await update.message.reply_text(error_msg, parse_mode="Markdown")
        
        # Save to offline queue on error
        offline_queue.add_message(user.id, chat_id, 
                                 user.username or user.first_name, 
                                 message_text)

# ══════════════════════════════════════════════
# ENHANCED REMINDER JOB WITH BETTER LOGGING
# ══════════════════════════════════════════════
async def reminder_job(context):
    """Enhanced reminder job with better tracking"""
    now_time = datetime.now().strftime("%H:%M")
    
    # Midnight reset
    if now_time == "00:00":
        reminders.reset_daily()
        log.info("🔄 Daily reminders reset at midnight")
    
    # Due reminders fire karo
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
            
            # LOUD alert
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
                disable_notification=False,  # LOUD!
                reply_markup=kb
            )
            
            # Second ping after 2 seconds
            await asyncio.sleep(2)
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=f"🔔 *REMINDER:* {r['text']}\n⏰ Abhi dekho!",
                parse_mode="Markdown",
                disable_notification=False
            )
            
            reminders.mark_fired(r["id"])
            
            # Log the firing
            activity_logger.log_activity(
                "reminder_fired",
                r["chat_id"],
                "system",
                f"Reminder #{r['id']}: {r['text']} at {r['time']}",
                "fired",
                protected=True
            )
            
            log.info(f"🔔 Reminder fired: #{r['id']} — {r['text']}")
            
        except Exception as e:
            log.error(f"Reminder send error #{r['id']}: {e}")
            activity_logger.log_activity(
                "reminder_error",
                r["chat_id"],
                "system",
                f"Error firing reminder #{r['id']}: {str(e)}",
                "error"
            )

# ══════════════════════════════════════════════
# OFFLINE QUEUE PROCESSOR (Background)
# ══════════════════════════════════════════════
async def process_offline_queue(context):
    """Har 5 minute mein check karo - offline messages process karo"""
    pending = offline_queue.get_pending_messages()
    
    if not pending:
        return
    
    log.info(f"📥 Processing {len(pending)} offline messages...")
    
    for i, msg in enumerate(pending):
        try:
            # Try to process with AI
            reply = await ai_chat(msg["message"], chat_id=msg["chat_id"])
            
            # Send reply to user
            await context.bot.send_message(
                chat_id=msg["chat_id"],
                text=f"📥 *Offline Message Processed!*\n\n"
                     f"_{msg['message'][:100]}_\n\n"
                     f"💬 *Reply:* {reply[:500]}",
                parse_mode="Markdown"
            )
            
            offline_queue.mark_processed(i)
            activity_logger.log_activity(
                "offline_processed",
                msg["user_id"],
                msg["username"],
                msg["message"][:200],
                "processed"
            )
            
            log.info(f"✅ Processed offline message from {msg['username']}")
            
        except Exception as e:
            log.error(f"Failed to process offline message: {e}")
    
    # Clean old processed messages
    offline_queue.clear_processed()

# ══════════════════════════════════════════════
# MAIN WITH ENHANCED JOBS
# ══════════════════════════════════════════════
def main():
    log.info("🤖 Personal AI Bot v4.5 — Enhanced with Offline Capture & Secret Code")
    log.info(f"📡 Models (fallback order): {', '.join(GEMINI_MODELS)}")
    log.info(f"🔐 Secret code protection: ACTIVE")
    log.info(f"📥 Offline queue system: ACTIVE")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add new command handlers
    enhanced_handlers = [
        ("alltasks",       cmd_all_tasks),      # Saare tasks dikhao
        ("completed",      cmd_completed_tasks), # Sirf completed tasks
        ("taskhistory",    cmd_task_history),    # Task history with secret code
        ("offlinemsgs",    cmd_offline_messages),# Offline messages
        ("verify",         cmd_verify_secret),   # Verify secret code
        ("reminderlog",    cmd_reminder_history),# Reminder history
        ("alllogs",        cmd_all_logs),        # All activity logs
    ]
    
    for cmd, handler in enhanced_handlers:
        app.add_handler(CommandHandler(cmd, handler))
    
    # Existing handlers
    existing_handlers = [
        ("start",       cmd_start),
        ("help",        cmd_help),
        ("task",        cmd_task),
        ("done",        cmd_done),
        ("deltask",     cmd_deltask),
        ("remind",      cmd_remind),
        ("reminders",   cmd_reminders_list),
        ("delremind",   cmd_delremind),
        # ... other handlers
    ]
    
    for cmd, handler in existing_handlers:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    # Enhanced job queue
    job_queue = app.job_queue
    if job_queue is not None:
        job_queue.run_repeating(reminder_job, interval=30, first=5)
        job_queue.run_repeating(bill_due_alert_job, interval=3600, first=60)
        job_queue.run_repeating(water_reminder_job, interval=3600, first=300)
        job_queue.run_repeating(process_offline_queue, interval=300, first=30)  # Every 5 minutes
        log.info("⏰ All background jobs started!")
        log.info("📥 Offline queue processor: Every 5 minutes")
    else:
        log.warning("⚠️ JobQueue nahi mila!")

    log.info("✅ Bot ready! /start karo")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
