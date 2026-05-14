#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PERSONAL AI ASSISTANT — RK BOT
FIXES v13 (FINAL):
  - FIXED: Hinglish response (Gemini ab Hinglish mein reply karega)
  - REMINDER FIX: Full timestamp support (YYYY-MM-DD HH:MM:SS)
  - Voice handler integration with proper reminder storage
  - Fixed ReminderManager compatibility (no direct store access)
  - Reminder reply mein actual date + time dono show hoti hai
  - /start mein current date & time show hoti hai
  - FIXED: Conflict error - cleanup before starting
  - FIXED: Google Sheets connection handling
"""

import os, json, logging, time
import urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta, timezone
import re as _re
import asyncio

from secure_data_manager import (
    memory, tasks, diary, habits, expenses, goals, reminders,
    water, bills, calendar, chat_hist, now_ist, today_str, now_str,
    sheets_backup, DATA_DIR, repo_manager
    sheets_backup, DATA_DIR, repo_manager, channel_logger 
)

ssl._create_default_https_context = ssl._create_unverified_context

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

# ── NEW ADDON IMPORTS ──────────────────────────────
# Voice handler with multiple transcription methods (UPDATED v8)
from voice_note_handler import register_voice_handlers
from smart_memory_handler import register_memory_handlers, check_smart_memory_intent
# ──────────────────────────────────────────────────

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DIARY_PASSWORD = os.environ.get("DIARY_PASSWORD", "Rk1996")

# These are optional but recommended for voice transcription
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
HUGGINGFACE_API_KEY = os.environ.get("HUGGINGFACE_API_KEY", "")

DIARY_AWAIT_PASS = 0
DIARY_AWAIT_TEXT = 1

if not TELEGRAM_TOKEN:
    print("TELEGRAM_TOKEN not set!")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
_last_gemini_call = 0

def call_gemini(prompt, max_tokens=400):
    """Call Gemini API with Hinglish instruction"""
    global _last_gemini_call
    if not GEMINI_API_KEY:
        return None
    elapsed = time.time() - _last_gemini_call
    if elapsed < 2:
        time.sleep(2 - elapsed)
    _last_gemini_call = time.time()
    
    # Strong Hinglish instruction
    system_instruction = """You are Rk, a personal AI assistant for a Muslim user.

🚨 CRITICAL RULES - FOLLOW STRICTLY:
1. Reply ONLY in HINGLISH (Hindi words written in English/Roman script)
2. ALWAYS start with Assalamualaikum or Alhamdulillah
3. Use Muslim phrases: InshAllah, MashAllah, JazakAllah, SubhanAllah
4. Keep replies SHORT (2-3 lines maximum)
5. NEVER use pure English
6. NEVER use Devanagari/Hindi script

✅ GOOD Examples:
- "Assalamualaikum! Aapki help chahiye? Batao kya kar sakta hoon!"
- "Alhamdulillah! Task complete ho gaya! MashAllah!"
- "InshAllah, reminder set kar diya! Kuch aur?"
- "SubhanAllah! Aaj 3 habits complete! Bohat acha!"

❌ BAD Examples (NEVER use):
- "Hello! How can I help you?" (English - NO)
- "नमस्ते! मैं कैसे मदद कर सकता हूँ?" (Hindi script - NO)
- "Good morning! Your tasks are pending" (English - NO)

Always reply in HINGLISH like a friendly Indian Muslim assistant!"""

    payload = json.dumps({
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": max_tokens}
    }).encode("utf-8")
    
    for model in GEMINI_MODELS:
        try:
            url = GEMINI_URL.format(model=model, key=GEMINI_API_KEY)
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                reply = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                
                # Post-process: Ensure Hinglish
                # Remove pure English greetings
                english_greetings = ["Hello", "Hi", "Hey", "Good morning", "Good evening", "Good afternoon"]
                for eng in english_greetings:
                    if reply.lower().startswith(eng.lower()):
                        reply = "Assalamualaikum! " + reply[len(eng):].strip()
                
                # Add Assalamualaikum if missing
                if not any(word in reply.lower() for word in ['assalamualaikum', 'alaikum', 'salam', 'alhamdulillah']):
                    reply = "Assalamualaikum! " + reply
                
                return reply
        except Exception as e:
            log.warning(f"Gemini error ({model}): {e}")
    return None

def build_system_prompt():
    """Build system prompt with current data"""
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    exp_t = expenses.today_total()
    wt = water.today_total()
    wg = water.goal()
    active_rem = reminders.all_active()
    today_events = calendar.today_events()
    
    return (f"""☪️ ASSALAMUALAIKUM! Main Rk hoon - aapka personal AI assistant.

⏰ TIME: {now_ist().strftime('%A, %d %b — %I:%M %p')} IST

📊 TODAY'S STATUS:
• Tasks pending: {len(tp)}
• Habits done: {len(hd)} / Pending: {len(hp)}
• Kharcha: Rs.{exp_t}
• Paani: {wt}ml/{wg}ml
• Active reminders: {len(active_rem)}
• Aaj ke events: {len(today_events)}

🚨 IMPORTANT - Jab main reply karunga:
- HINGLISH mein karunga (Hindi + English mix)
- Assalamualaikum ya Alhamdulillah se start karunga
- InshAllah, MashAllah, JazakAllah zaroor use karunga
- Short reply hoga (2-3 lines)

User ka message padho aur HINGLISH mein jawab do!""")


def alarm_keyboard(rid):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ OK — Alarm Band Karo", callback_data=f"ok_{rid}")
    ]])


# ================================================================
# CLEANUP FUNCTION - FIX CONFLICT ERROR
# ================================================================

def cleanup_before_start():
    """Force delete webhook and clear pending updates to prevent conflict"""
    token = TELEGRAM_TOKEN
    if not token:
        return
    
    try:
        import requests
        # Delete webhook with drop_pending_updates
        url = f"https://api.telegram.org/bot{token}/deleteWebhook"
        response = requests.post(url, json={"drop_pending_updates": True}, timeout=10)
        log.info(f"Webhook deleted: {response.status_code}")
        
        # Also clear getUpdates queue
        url2 = f"https://api.telegram.org/bot{token}/getUpdates"
        requests.post(url2, json={"offset": -1, "timeout": 1}, timeout=5)
        
        log.info("✅ Cleanup completed - old connections cleared")
    except Exception as e:
        log.warning(f"Cleanup warning (non-critical): {e}")


# ================================================================
# MISCELLANEOUS LOGGER
# ================================================================

def _log_action(user_name: str, action_type: str, detail: str):
    try:
        clean_detail = str(detail).strip()
        if clean_detail.startswith(("=", "+", "-", "@")):
            clean_detail = "'" + clean_detail
        sheets_backup.log_event(action_type, str(user_name), clean_detail)
        log.info(f"[MiscLog] {action_type} | {user_name} | {clean_detail[:60]}")
    except Exception as e:
        log.warning(f"_log_action failed: {e}")


# ================================================================
# DATE PARSER
# ================================================================

MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "mei": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
    "januari": 1, "februari": 2, "maret": 3,
    "juni": 6, "juli": 7, "agustus": 8, "oktober": 10, "desember": 12
}

def _parse_date_from_text(text):
    lower = text.lower()
    today_d = now_ist().date()

    m = _re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', lower)
    if m:
        try:
            yr, mo, dy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            d = date(yr, mo, dy)
            remaining = _re.sub(r'\d{4}-\d{1,2}-\d{1,2}', '', text).strip()
            return d.strftime("%Y-%m-%d"), remaining
        except Exception:
            pass

    m = _re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})', lower)
    if m:
        try:
            a, b, c = m.group(1), m.group(2), m.group(3)
            if len(c) == 4:
                dy, mo, yr = int(a), int(b), int(c)
            elif len(a) == 4:
                yr, mo, dy = int(a), int(b), int(c)
            else:
                dy, mo, yr = int(a), int(b), int(c) + 2000
            d = date(yr, mo, dy)
            remaining = _re.sub(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', '', text).strip()
            return d.strftime("%Y-%m-%d"), remaining
        except Exception:
            pass

    month_names = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
    m = _re.search(r'(\d{1,2})[- ](' + month_names + r')[- ](\d{4})', lower, _re.IGNORECASE)
    if m:
        try:
            dy = int(m.group(1))
            mon_str = m.group(2).lower()
            yr = int(m.group(3))
            mon_map = {
                "jan":1, "feb":2, "mar":3, "apr":4, "may":5, "jun":6,
                "jul":7, "aug":8, "sep":9, "oct":10, "nov":11, "dec":12
            }
            mo = mon_map.get(mon_str, 0)
            if mo and 1 <= mo <= 12:
                d = date(yr, mo, dy)
                remaining = _re.sub(r'\d{1,2}[- ](?:' + month_names + r')[- ]\d{4}', '', text, flags=_re.IGNORECASE).strip()
                return d.strftime("%Y-%m-%d"), remaining
        except Exception:
            pass

    m = _re.search(r'(\d{1,2})\s+(' + month_names + r')\s+(\d{4})', lower, _re.IGNORECASE)
    if m:
        try:
            dy = int(m.group(1))
            mon_str = m.group(2).lower()
            yr = int(m.group(3))
            mon_map = {
                "jan":1, "feb":2, "mar":3, "apr":4, "may":5, "jun":6,
                "jul":7, "aug":8, "sep":9, "oct":10, "nov":11, "dec":12
            }
            mo = mon_map.get(mon_str, 0)
            if mo and 1 <= mo <= 12:
                d = date(yr, mo, dy)
                remaining = _re.sub(r'\d{1,2}\s+(?:' + month_names + r')\s+\d{4}', '', text, flags=_re.IGNORECASE).strip()
                return d.strftime("%Y-%m-%d"), remaining
        except Exception:
            pass

    month_pattern = "|".join(sorted(MONTH_MAP.keys(), key=len, reverse=True))
    m = _re.search(r'(\d{1,2})\s+(' + month_pattern + r')(?:\s+(\d{2,4}))?', lower)
    if m:
        day = int(m.group(1))
        mon = MONTH_MAP.get(m.group(2), 0)
        yr_raw = m.group(3)
        if yr_raw:
            yr = int(yr_raw) if len(yr_raw) == 4 else int(yr_raw) + 2000
        else:
            yr = today_d.year
            if mon and date(yr, mon, day) < today_d:
                yr += 1
        try:
            d = date(yr, mon, day)
            remaining = _re.sub(r'\d{1,2}\s+(?:' + month_pattern + r')(?:\s+\d{2,4})?', '', text, flags=_re.IGNORECASE).strip()
            return d.strftime("%Y-%m-%d"), remaining
        except Exception:
            pass

    if "parso" in lower:
        return (today_d + timedelta(days=2)).strftime("%Y-%m-%d"), _re.sub(r'\bparso\b', '', text, flags=_re.IGNORECASE).strip()
    if _re.search(r'\bkal\b|\bkl\b', lower):
        return (today_d + timedelta(days=1)).strftime("%Y-%m-%d"), _re.sub(r'\bkal\b|\bkl\b', '', text, flags=_re.IGNORECASE).strip()
    if "aaj" in lower:
        return today_d.strftime("%Y-%m-%d"), _re.sub(r'\baaj\b', '', text, flags=_re.IGNORECASE).strip()

    return None, text


# ================================================================
# BASIC COMMANDS
# ================================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Bhai"
    now = now_ist()
    date_time_str = now.strftime("%A, %d %b %Y — %I:%M %p") + " IST"
    await update.message.reply_text(
        f"☪️ Assalamualaikum {name}! 🤝\n\n"
        f"🕐 {date_time_str}\n\n"
        f"Main hoon aapka Personal AI Assistant — *Rk* 🌟\n\n"
        f"Alhamdulillah, main aapki har baat sunne ke liye haazir hoon!\n\n"
        f"📋 Sab commands dekhne ke liye: /help",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *COMMANDS — Rk Bot*\n\n"
        "💬 *Seedha bolo (natural Hinglish):*\n"
        "• `30 min mein chai yaad dilana`\n"
        "• `chai pe 50 rupees laga`\n"
        "• `diary mein likho aaj ka din acha tha`\n"
        "• `gym habit ho gayi`\n"
        "• `simran ki birthday 9 sep 2000 hai`\n"
        "• `bill add netflix 499`\n"
        "• `karcha 200 petrol`\n"
        "• `saare task dikhao / task list`\n"
        "• `diary dikhao / show diary`\n"
        "• `memory mein save karo...`\n\n"
        "✅ *Tasks:*\n"
        "/task Naam — Task add karo\n"
        "/done id — Task complete karo\n"
        "/deltask id — Task delete karo\n\n"
        "🏃 *Habits:*\n"
        "/habit Naam — Habit add karo\n"
        "/hdone id — Habit log karo\n\n"
        "⏰ *Reminders:*\n"
        "/remind 30m Chai — Reminder set karo (relative time)\n"
        "/remind 15:30 Meeting — Reminder set karo (absolute time)\n"
        "/delremind id — Reminder delete karo\n"
        "/snooze5 id | /snooze10 id | /snooze30 id | /snooze60 id\n\n"
        "📖 *Diary (Password Protected):*\n"
        "/diary — Aaj ki entries dekho\n"
        "/diary write — Naya entry likho\n"
        "/diary week — Is hafte ki entries\n"
        "/diary all — Sab entries\n"
        "/save text — Quick diary save\n\n"
        "📅 *Calendar:*\n"
        "/cal — Upcoming events dekho\n"
        "/caltoday — Aaj ke events\n"
        "/calweek — Is hafte ke events\n"
        "/caladd — Naya event/birthday add karo\n"
        "/caldel id — Event delete karo\n\n"
        "💳 *Bills & Subscriptions:*\n"
        "/bills — Sab bills dekho\n"
        "/billadd — Naya bill add karo\n"
        "/billpaid id — Bill paid mark karo\n"
        "/billdel id — Bill delete karo\n\n"
        "💸 *Kharcha & Paani:*\n"
        "/kharcha 100 Chai — Expense add karo\n"
        "/water 250 — Water log karo\n\n"
        "🗑️ *Delete Manager:*\n"
        "/delete — Full delete menu\n"
        "/nuke — Chat history delete\n"
        "/nukeall — Sab kuch delete\n\n"
        "🧠 *Smart Memory:*\n"
        "/memory — Show saved memories\n"
        "/memory add text — Save a memory\n"
        "/memory search word — Search memories\n"
        "/memory clear — Delete all memories\n\n"
        "🎙️ *Voice Notes (UPDATED - Fixed Reminders!):*\n"
        "Voice message bhejo — Main transcribe karunga aur action lunga!\n"
        "✅ Reminders ab sahi time pe bajenge! ⏰\n"
        "/voicenotes — Recent voice notes dekho\n\n"
        "📊 *Other:*\n"
        "/briefing — Daily summary\n"
        "/status — System status\n"
        "/checksync — GitHub & Sheets check",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    github_status = "✅ Connected" if repo_manager.is_connected else "⚠️ Local only"
    sheets_status = "✅ Connected" if sheets_backup.connected else "❌ Not connected"
    all_events = calendar.all_events()
    await update.message.reply_text(
        f"📊 *BOT STATUS*\n\n"
        f"🤖 Bot: Running ✅\n"
        f"🐙 GitHub: {github_status}\n"
        f"📊 Google Sheets: {sheets_status}\n\n"
        f"📁 *Data Stats:*\n"
        f"✅ Tasks: {len(tasks.all_tasks())}\n"
        f"📖 Diary: {sum(len(v) for v in diary.get_all_entries().values())} entries\n"
        f"💸 Expenses: {len(expenses.store.data.get('list', []))}\n"
        f"🏃 Habits: {len(habits.all())}\n"
        f"⏰ Reminders: {len(reminders.get_all())}\n"
        f"📅 Calendar: {len(all_events)} events\n"
        f"💳 Bills: {len(bills.all_active())} active\n"
        f"💧 Water: {water.today_total()}/{water.goal()}ml today",
        parse_mode="Markdown"
    )

async def cmd_checksync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    github_status = "✅ Connected" if repo_manager.is_connected else "⚠️ Local only"
    sheets_status = "✅ Connected" if sheets_backup.connected else "❌ Not connected"
    last_sync = "Not available"
    if repo_manager.is_connected:
        try:
            import subprocess
            result = subprocess.run(
                ["git", "-C", DATA_DIR, "log", "-1", "--format=%cd"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                last_sync = result.stdout.strip()
        except Exception:
            pass
    sheet_url = "Not connected"
    if sheets_backup._book:
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheets_backup._book.id}"
    await update.message.reply_text(
        f"🔄 *SYNC STATUS*\n\n"
        f"🐙 GitHub: {github_status}\n"
        f"📊 Google Sheets: {sheets_status}\n"
        f"🕐 Last Git Commit: {last_sync}\n\n"
        f"Alhamdulillah, sab data safe hai! 🔒\n\n"
        f"🔗 Google Sheet:\n{sheet_url}",
        parse_mode="Markdown"
    )

# ================================================================
# TASK COMMANDS
# ================================================================

async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"  #{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(
                f"📋 *Pending Tasks ({len(pending)}):*\n\n{lines}\n\n"
                f"/done id — Complete karo\n/deltask id — Delete karo",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "✅ Alhamdulillah! Koi pending task nahi hai.\n\n/task Kaam naam — Naya task add karo",
                parse_mode="Markdown"
            )
        return
    title = " ".join(ctx.args)
    t = tasks.add(title)
    _log_action(update.effective_user.first_name or "User", "task_add", f"#{t['id']}: {title}")
    await update.message.reply_text(
        f"✅ *Task Add Ho Gaya!*\n\n📌 #{t['id']} {t['title']}\n\nInshAllah ho jayega! 💪",
        parse_mode="Markdown"
    )

async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"  #{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(
                f"📋 *Pending Tasks:*\n\n{lines}\n\n/done id — Complete karo",
                parse_mode="Markdown"
            )
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t:
            _log_action(update.effective_user.first_name or "User", "task_done", f"#{t['id']}: {t['title']}")
            await update.message.reply_text(
                f"✅ *Alhamdulillah! Task Complete!* 🎉\n\n#{t['id']} ~~{t['title']}~~\n\nMashAllah! 💪",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Task nahi mila! Sahi ID daalo.")
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "/deltask id\n\nPending tasks:\n" +
            "\n".join(f"  #{t['id']} {t['title']}" for t in tasks.pending()[:10])
        )
        return
    try:
        tid = int(ctx.args[0])
        target = next((t for t in tasks.all_tasks() if t["id"] == tid), None)
        if not target:
            await update.message.reply_text(f"❌ Task #{tid} nahi mila!")
            return
        tasks.delete(tid)
        _log_action(update.effective_user.first_name or "User", "task_delete", f"#{tid}: {target['title']}")
        await update.message.reply_text(
            f"🗑️ *Task Delete Ho Gaya!*\n\n#{tid} '{target['title']}'\n\nSheets se bhi hata diya. ✅",
            parse_mode="Markdown"
        )
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")

# ================================================================
# HABIT COMMANDS
# ================================================================

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        all_h = habits.all()
        if all_h:
            hd, _ = habits.today_status()
            done_ids = [h["id"] for h in hd]
            lines = "\n".join(
                f"  {'✅' if h['id'] in done_ids else '⬜'} #{h['id']} {h['name']} 🔥{h.get('streak',0)}"
                for h in all_h
            )
            await update.message.reply_text(
                f"🏃 *Aaj ke Habits:*\n\n{lines}\n\n/hdone id — Log karo",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("/habit Naam — Naya habit add karo", parse_mode="Markdown")
        return
    h = habits.add(" ".join(ctx.args))
    _log_action(update.effective_user.first_name or "User", "habit_add", f"#{h['id']}: {h['name']}")
    await update.message.reply_text(
        f"🏃 *Habit Add Ho Gaya!*\n\n#{h['id']} {h['name']}\n\nInshAllah roz karoge! 💪",
        parse_mode="Markdown"
    )

async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            lines = "\n".join(f"  #{h['id']} {h['name']}" for h in pending)
            await update.message.reply_text(
                f"⬜ *Pending Habits:*\n\n{lines}\n\n/hdone id — Log karo",
                parse_mode="Markdown"
            )
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        if ok:
            _log_action(update.effective_user.first_name or "User", "habit_done", f"Habit #{ctx.args[0]} | streak: {streak}")
            await update.message.reply_text(
                f"🔥 *Habit Done! MashAllah!* 🎉\n\n{streak} din ka streak! 💪",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("✅ Aaj pehle hi log ho chuka hai!")
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")

# ================================================================
# EXPENSE & WATER COMMANDS
# ================================================================

async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        today_list = expenses.get_by_date(today_str())
        if today_list:
            lines = "\n".join(f"  💸 Rs.{e['amount']} — {e['desc']}" for e in today_list[-10:])
            await update.message.reply_text(
                f"💸 *Aaj ka Kharcha:*\n\n{lines}\n\n💰 *Total: Rs.{expenses.today_total()}*",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("/kharcha 100 Chai — Kharcha add karo", parse_mode="Markdown")
        return
    try:
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        _log_action(update.effective_user.first_name or "User", "expense_add", f"Rs.{amount} on {desc}")
        await update.message.reply_text(
            f"💸 *Kharcha Add!*\n\nRs.{amount} — {desc}\n💰 Aaj total: Rs.{expenses.today_total()}",
            parse_mode="Markdown"
        )
    except Exception:
        await update.message.reply_text("/kharcha 100 Chai")

async def cmd_water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ml = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 250
    total = water.add(ml)
    goal = water.goal()
    pct = int(total / goal * 100) if goal else 0
    filled = min(pct // 20, 5)
    bar = "🟦" * filled + "⬜" * (5 - filled)
    _log_action(update.effective_user.first_name or "User", "water_log", f"Added {ml}ml | Total: {total}ml of {goal}ml")
    await update.message.reply_text(
        f"💧 *+{ml}ml Paani!*\n\nTotal: {total}/{goal}ml\n{bar} {pct}%\n\n"
        f"{'Alhamdulillah! Goal complete! 🎉' if total >= goal else 'InshAllah goal poora hoga! 💪'}",
        parse_mode="Markdown"
    )

# ================================================================
# REMINDER COMMANDS (UPDATED for better time display)
# ================================================================

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        active = reminders.all_active()
        if active:
            lines = []
            for r in active:
                due = r.get("due", "")
                if due and len(due) > 5 and ":" in due:
                    try:
                        dt = datetime.strptime(due, "%Y-%m-%d %H:%M:%S")
                        due_display = dt.strftime("%d %b, %I:%M %p")
                    except:
                        due_display = due
                else:
                    due_display = due
                lines.append(f"  ⏰ #{r['id']} {due_display} — {r['text']}")
            await update.message.reply_text(
                f"⏰ *Active Reminders ({len(active)}):*\n\n" + "\n".join(lines) +
                "\n\n/remind 30m Chai — Naya set karo\n/remind 15:30 Meeting",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "⏰ Koi active reminder nahi.\n\n/remind 30m Chai\n/remind 15:30 Meeting",
                parse_mode="Markdown"
            )
        return
    
    time_arg = ctx.args[0].lower()
    text = " ".join(ctx.args[1:])
    now = now_ist()
    
    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        mins = int(time_arg[:-1])
        remind_dt = now + timedelta(minutes=mins)
        due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
        
    elif time_arg.endswith("h") and time_arg[:-1].isdigit():
        hours = int(time_arg[:-1])
        remind_dt = now + timedelta(hours=hours)
        due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
        
    elif time_arg.endswith("min") and time_arg[:-3].isdigit():
        mins = int(time_arg[:-3])
        remind_dt = now + timedelta(minutes=mins)
        due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
        
    elif ":" in time_arg:
        parts = time_arg.split(":")
        remind_dt = datetime(now.year, now.month, now.day, int(parts[0]), int(parts[1]))
        if remind_dt < now:
            remind_dt += timedelta(days=1)
        due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        await update.message.reply_text("/remind 30m Chai ya /remind 15:30 Meeting")
        return
    
    r = reminders.add(update.effective_chat.id, text, due_timestamp)
    
    _log_action(update.effective_user.first_name or "User", "reminder_set", f"#{r['id']} at {due_timestamp}: {text}")

    remind_dt = datetime.strptime(due_timestamp, "%Y-%m-%d %H:%M:%S")
    date_display = remind_dt.strftime("%d %b %Y")
    h, m_val = remind_dt.hour, remind_dt.minute
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    time_display = f"{h12}:{m_val:02d} {ampm}"

    await update.message.reply_text(
        f"⏰ *Reminder Set! InshAllah yaad dilaaunga!*\n\n"
        f"🕐 *{time_display}* — 📅 *{date_display}*\n"
        f"📝 {text}\n"
        f"📌 ID #{r['id']}",
        parse_mode="Markdown"
    )

async def cmd_delremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        active = reminders.all_active()
        if active:
            lines = []
            for r in active[:10]:
                due_display = r.get("due", "")[:16] if r.get("due") else ""
                lines.append(f"  #{r['id']} {due_display} — {r['text']}")
            await update.message.reply_text(f"Active reminders:\n" + "\n".join(lines) + "\n\n/delremind id", parse_mode="Markdown")
        else:
            await update.message.reply_text("/delremind id", parse_mode="Markdown")
        return
    try:
        rid = int(ctx.args[0])
        target = reminders.get_by_id(rid)
        if not target:
            await update.message.reply_text(f"❌ Reminder #{rid} nahi mila!")
            return
        reminders.delete(rid)
        _log_action(update.effective_user.first_name or "User", "reminder_delete", f"#{rid}: {target['text']}")
        await update.message.reply_text(
            f"🗑️ *Reminder Delete Ho Gaya!*\n\n#{rid} '{target['text']}'\n\nSheets se bhi hata diya. ✅",
            parse_mode="Markdown"
        )
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_snooze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.split()[0].lstrip("/").lower()
    snooze_map = {"snooze5": 5, "snooze10": 10, "snooze30": 30, "snooze60": 60}
    mins = snooze_map.get(cmd, 10)
    if not ctx.args:
        await update.message.reply_text(f"/{cmd} reminder_id")
        return
    try:
        rid = int(ctx.args[0])
        target = reminders.get_by_id(rid)
        if not target:
            await update.message.reply_text(f"❌ Reminder #{rid} nahi mila!")
            return
        reminders.acknowledge(rid, f"Snoozed {mins}min")
        new_dt = now_ist() + timedelta(minutes=mins)
        new_timestamp = new_dt.strftime("%Y-%m-%d %H:%M:%S")
        new_rem = reminders.add(target["chat_id"], f"🔁 {target['text']}", new_timestamp, "once")
        _log_action(update.effective_user.first_name or "User", "reminder_snooze", f"#{rid} snoozed {mins}min → #{new_rem['id']} at {new_timestamp}")
        
        new_time_display = new_dt.strftime("%I:%M %p")
        new_date_display = new_dt.strftime("%d %b")
        
        await update.message.reply_text(
            f"😴 *Snooze Ho Gaya!*\n\n{mins} min baad fir yaad dilaaunga.\n🕐 {new_time_display} — 📅 {new_date_display}\nNew ID: #{new_rem['id']}",
            parse_mode="Markdown"
        )
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")

# ================================================================
# DIARY COMMANDS
# ================================================================

async def cmd_diary_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or []
    if not args:
        ctx.user_data["diary_mode"] = "view_today"
    else:
        first = args[0].lower()
        if first == "write":
            ctx.user_data["diary_mode"] = "write"
        elif first == "week":
            ctx.user_data["diary_mode"] = "view_week"
        elif first == "all":
            ctx.user_data["diary_mode"] = "view_all"
        else:
            ctx.user_data["diary_mode"] = "write"
            ctx.user_data["diary_pending_text"] = " ".join(args)
    await update.message.reply_text(
        "🔒 *Diary ka Password daalo:*\n\n(/cancel se bahar)",
        parse_mode="Markdown"
    )
    return DIARY_AWAIT_PASS

async def diary_password_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END
    entered = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass
    if entered != DIARY_PASSWORD:
        await update.effective_chat.send_message(
            "❌ *Galat Password!*\n\nDobara try karo: /diary",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    mode = ctx.user_data.get("diary_mode", "view_today")
    user_name = update.effective_user.first_name or "User"
    if mode == "write":
        pending_text = ctx.user_data.get("diary_pending_text", "")
        if pending_text:
            diary.add(pending_text)
            _log_action(user_name, "diary_write", f"Entry: {pending_text[:80]}")
            await update.effective_chat.send_message(
                f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n_{pending_text[:200]}_\n\nSheets mein bhi backup ho gaya!",
                parse_mode="Markdown"
            )
            ctx.user_data.clear()
            return ConversationHandler.END
        else:
            await update.effective_chat.send_message(
                "✅ Password sahi hai! MashAllah! 🎉\n\nAb likho diary mein:\n(/cancel se bahar)",
                parse_mode="Markdown"
            )
            return DIARY_AWAIT_TEXT
    elif mode == "view_today":
        entries = diary.get(today_str())
        _log_action(user_name, "diary_view", f"Viewed today ({len(entries)} entries)")
        if not entries:
            await update.effective_chat.send_message(
                "📖 Aaj ki koi diary entry nahi hai.\n\n/diary write — Likhna shuru karo!",
                parse_mode="Markdown"
            )
        else:
            lines = "\n\n".join(f"🕐 {e['time']}\n{e['text']}" for e in entries)
            await update.effective_chat.send_message(
                f"📖 *Aaj ki Diary ({today_str()}):*\n\n{lines}",
                parse_mode="Markdown"
            )
    elif mode == "view_week":
        all_entries = diary.get_all_entries()
        today_d = now_ist().date()
        week_entries = []
        for i in range(7):
            d = (today_d - timedelta(days=i)).strftime("%Y-%m-%d")
            for e in all_entries.get(d, []):
                week_entries.append(f"📅 {d} 🕐{e.get('time','')}\n{e['text']}")
        _log_action(user_name, "diary_view", f"Viewed week ({len(week_entries)} entries)")
        if not week_entries:
            await update.effective_chat.send_message("📖 Is hafte koi entry nahi.", parse_mode="Markdown")
        else:
            msg = "\n\n".join(week_entries[:10])
            await update.effective_chat.send_message(f"📖 *Is hafte ki Diary:*\n\n{msg[:3000]}", parse_mode="Markdown")
    elif mode == "view_all":
        all_entries = diary.get_all_entries()
        count = sum(len(v) for v in all_entries.values())
        dates = sorted(all_entries.keys(), reverse=True)
        preview = []
        for d in dates[:5]:
            for e in all_entries[d][:2]:
                preview.append(f"📅 {d}\n{e['text'][:100]}")
        msg = "\n\n".join(preview)
        _log_action(user_name, "diary_view", f"Viewed all ({count} total)")
        await update.effective_chat.send_message(
            f"📖 *Total {count} diary entries*\n\nAlhamdulillah! 🌟\n\n*Latest:*\n\n{msg[:3000]}",
            parse_mode="Markdown"
        )
    ctx.user_data.clear()
    return ConversationHandler.END

async def diary_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass
    diary.add(text)
    _log_action(update.effective_user.first_name or "User", "diary_write", f"Entry: {text[:80]}")
    await update.effective_chat.send_message(
        f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n_{text[:200]}_\n\nSheets mein bhi backup ho gaya!",
        parse_mode="Markdown"
    )
    ctx.user_data.clear()
    return ConversationHandler.END

async def diary_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Diary cancelled.", parse_mode="Markdown")
    return ConversationHandler.END

async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("/save Aaj ka din acha tha...")
        return
    text = " ".join(ctx.args)
    diary.add(text)
    _log_action(update.effective_user.first_name or "User", "diary_write", f"Quick save: {text[:80]}")
    await update.message.reply_text(
        f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n_{text[:200]}_",
        parse_mode="Markdown"
    )

# ================================================================
# CALENDAR COMMANDS
# ================================================================

async def cmd_cal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    events = calendar.upcoming(days=30)
    if not events:
        await update.message.reply_text("📅 Koi upcoming event nahi hai.\n\n/caladd — Add karo", parse_mode="Markdown")
        return
    lines = []
    for e in events[:15]:
        emoji = "🎂" if e.get("type") == "birthday" else "📅"
        ts = f" ⏰{e['time']}" if e.get("time") else ""
        ls = f" 📍{e['location']}" if e.get("location") else ""
        lines.append(f"{emoji} *{e['date']}*{ts} — #{e['id']}\n   {e['title']}{ls}")
    await update.message.reply_text(
        f"📅 *Upcoming Events ({len(events)}):*\n\n" + "\n\n".join(lines) +
        "\n\n/caladd — Naya add karo | /caldel id — Delete karo",
        parse_mode="Markdown"
    )

async def cmd_caltoday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    events = calendar.today_events()
    if not events:
        await update.message.reply_text("📅 Aaj koi event nahi hai.\n\n/caladd — Add karo", parse_mode="Markdown")
        return
    lines = []
    for e in events:
        emoji = "🎂" if e.get("type") == "birthday" else "📅"
        ts = f" ⏰{e['time']}" if e.get("time") else ""
        ls = f"\n   📍{e['location']}" if e.get("location") else ""
        ns = f"\n   📝{e['notes']}" if e.get("notes") else ""
        lines.append(f"{emoji} #{e['id']} *{e['title']}*{ts}{ls}{ns}")
    await update.message.reply_text(f"📅 *Aaj ke Events ({today_str()}):*\n\n" + "\n\n".join(lines), parse_mode="Markdown")

async def cmd_calweek(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    events = calendar.upcoming(days=7)
    if not events:
        await update.message.reply_text("📅 Is hafte koi event nahi.", parse_mode="Markdown")
        return
    lines = []
    for e in events:
        emoji = "🎂" if e.get("type") == "birthday" else "📅"
        ts = f" ⏰{e['time']}" if e.get("time") else ""
        ls = f" 📍{e['location']}" if e.get("location") else ""
        lines.append(f"{emoji} *{e['date']}*{ts} — #{e['id']}\n   {e['title']}{ls}")
    await update.message.reply_text(f"📅 *Is hafte ke Events:*\n\n" + "\n\n".join(lines), parse_mode="Markdown")

async def cmd_caladd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "📅 *Event ya Birthday Add Karo:*\n\n"
            "`/caladd 2026-05-20 Doctor 10:30 Apollo`\n"
            "`/caladd 2000-09-09 Simran birthday`\n\n"
            "Format: `/caladd YYYY-MM-DD Title [HH:MM] [Location]`",
            parse_mode="Markdown"
        )
        return
    args = ctx.args
    event_date = args[0]
    if not _re.match(r'\d{4}-\d{2}-\d{2}', event_date):
        await update.message.reply_text("❌ Date format: YYYY-MM-DD\n\nExample: /caladd 2026-05-20 Meeting", parse_mode="Markdown")
        return
    remaining = args[1:]
    event_time = ""
    location   = ""
    title_parts = []
    for i, part in enumerate(remaining):
        if _re.match(r'^\d{1,2}:\d{2}$', part):
            h, m = part.split(":")
            event_time = f"{int(h):02d}:{int(m):02d}"
            location = " ".join(remaining[i+1:])
            break
        else:
            title_parts.append(part)
    if not title_parts:
        await update.message.reply_text("❌ Event ka title likhna padega!", parse_mode="Markdown")
        return
    title = " ".join(title_parts)
    is_birthday = any(w in title.lower() for w in ["birthday", "bday", "janamdin", "janmdin"])
    event_type = "birthday" if is_birthday else "event"
    actual_date = event_date
    if is_birthday:
        try:
            birth = date.fromisoformat(event_date)
            today_d = now_ist().date()
            next_bday = birth.replace(year=today_d.year)
            if next_bday < today_d:
                next_bday = next_bday.replace(year=today_d.year + 1)
            actual_date = next_bday.strftime("%Y-%m-%d")
        except Exception:
            actual_date = event_date
    e = calendar.add(title, actual_date, event_time, location, "", event_type)
    _log_action(update.effective_user.first_name or "User", "calendar_add", f"{'Birthday' if is_birthday else 'Event'} #{e['id']}: {title} on {actual_date}")
    ts = f"\n⏰ Time: {event_time}" if event_time else ""
    ls = f"\n📍 Location: {location}" if location else ""
    emoji = "🎂" if is_birthday else "📅"
    if is_birthday:
        msg = f"{emoji} *Birthday Add Ho Gaya! MashAllah!* 🎉\n\n#{e['id']} 🎂 *{actual_date}*\n👤 {title}{ls}\n\n✅ Ek din pehle remind karunga!\n📊 Sheets mein save!"
    else:
        msg = f"{emoji} *Event Add Ho Gaya!* ✅\n\n#{e['id']} 📅 *{actual_date}*{ts}\n📌 {title}{ls}\n\n✅ Ek din pehle remind karunga!\n📊 Sheets mein save!"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_caldel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        events = calendar.upcoming(days=30)
        if events:
            lines = "\n".join(
                f"  {'🎂' if e.get('type')=='birthday' else '📅'} #{e['id']} {e['date']} {e['title']}"
                for e in events[:10]
            )
            await update.message.reply_text(f"Kaunsa event?\n\n{lines}\n\n/caldel id", parse_mode="Markdown")
        else:
            await update.message.reply_text("/caldel id", parse_mode="Markdown")
        return
    try:
        eid = int(ctx.args[0])
        target = calendar.get_by_id(eid)
        if not target:
            await update.message.reply_text(f"❌ Event #{eid} nahi mila!")
            return
        calendar.delete(eid)
        _log_action(update.effective_user.first_name or "User", "calendar_delete", f"#{eid}: {target['title']} on {target['date']}")
        await update.message.reply_text(
            f"🗑️ *Event Delete Ho Gaya!*\n\n#{eid} '{target['title']}' ({target['date']})\n\nSheets se bhi hata diya. ✅",
            parse_mode="Markdown"
        )
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")

# ================================================================
# BILLS COMMANDS
# ================================================================

async def cmd_bills(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    all_bills = bills.all_active()
    if not all_bills:
        await update.message.reply_text("💳 Koi active bill nahi hai.\n\n/billadd — Naya add karo", parse_mode="Markdown")
        return
    today_day = now_ist().day
    lines = []
    for b in all_bills:
        paid = bills.is_paid_this_month(b["id"])
        status = "✅ Paid" if paid else "❌ Unpaid"
        try:
            due = int(b.get("due_day", 0))
            days_left = due - today_day
            due_str = f" (due {due} tarikh"
            if not paid:
                if days_left < 0:
                    due_str += f", {abs(days_left)} din late!)"
                elif days_left == 0:
                    due_str += ", AAJ!)"
                elif days_left <= 3:
                    due_str += f", {days_left} din bacha!)"
                else:
                    due_str += ")"
            else:
                due_str += ")"
        except Exception:
            due_str = ""
        lines.append(f"💳 #{b['id']} *{b['name']}*\n   Rs.{b['amount']}{due_str}\n   {status}")
    await update.message.reply_text(
        f"💳 *Bills & Subscriptions ({len(all_bills)}):*\n\n" + "\n\n".join(lines) +
        "\n\n/billpaid id — Paid mark karo\n/billadd — Naya add karo\n/billdel id — Delete karo",
        parse_mode="Markdown"
    )

async def cmd_billadd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 3:
        await update.message.reply_text(
            "💳 *Bill Add Karo:*\n\n`/billadd Name Amount DueDay`\n\n"
            "Examples:\n`/billadd Netflix 499 15`\n`/billadd LIC 3500 5`\n`/billadd Jio 299 1`",
            parse_mode="Markdown"
        )
        return
    try:
        name = ctx.args[0]
        amount = float(ctx.args[1])
        due_day = int(ctx.args[2])
        auto_pay = ctx.args[3] if len(ctx.args) > 3 else "No"
        payment_method = ctx.args[4] if len(ctx.args) > 4 else ""
        b = bills.add(name, amount, due_day, auto_pay, payment_method)
        _log_action(update.effective_user.first_name or "User", "bill_add", f"#{b['id']}: {name} Rs.{amount} due {due_day} tarikh")
        await update.message.reply_text(
            f"💳 *Bill Add Ho Gaya! Alhamdulillah!* ✅\n\n#{b['id']} *{name}*\n"
            f"💰 Rs.{amount}\n📅 Due: {due_day} tarikh\n📊 Sheets mein save!",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ Format sahi nahi!\n/billadd Netflix 499 15", parse_mode="Markdown")

async def cmd_billpaid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        all_bills = bills.all_active()
        unpaid = [b for b in all_bills if not bills.is_paid_this_month(b["id"])]
        if unpaid:
            lines = "\n".join(f"  #{b['id']} {b['name']} — Rs.{b['amount']}" for b in unpaid)
            await update.message.reply_text(f"💳 *Unpaid Bills:*\n\n{lines}\n\n/billpaid id — Paid mark karo", parse_mode="Markdown")
        else:
            await update.message.reply_text("✅ Alhamdulillah! Sab bills paid hain!", parse_mode="Markdown")
        return
    try:
        bid = int(ctx.args[0])
        target = bills.get_by_id(bid)
        if not target:
            await update.message.reply_text(f"❌ Bill #{bid} nahi mila!")
            return
        ok = bills.mark_paid(bid)
        if ok:
            _log_action(update.effective_user.first_name or "User", "bill_paid", f"#{bid}: {target['name']} Rs.{target['amount']}")
            await update.message.reply_text(
                f"✅ *Bill Paid! Alhamdulillah!* 🎉\n\n#{bid} *{target['name']}* — Rs.{target['amount']}\n\nIs mahine mark ho gaya! 📊",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"ℹ️ #{bid} pehle hi paid mark hai!", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_billdel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        all_bills = bills.all_active()
        if all_bills:
            lines = "\n".join(f"  #{b['id']} {b['name']} — Rs.{b['amount']}" for b in all_bills)
            await update.message.reply_text(f"💳 *Active Bills:*\n\n{lines}\n\n/billdel id — Delete karo", parse_mode="Markdown")
        return
    try:
        bid = int(ctx.args[0])
        target = bills.get_by_id(bid)
        if not target:
            await update.message.reply_text(f"❌ Bill #{bid} nahi mila!")
            return
        bills.delete(bid)
        _log_action(update.effective_user.first_name or "User", "bill_delete", f"#{bid}: {target['name']}")
        await update.message.reply_text(
            f"🗑️ *Bill Delete Ho Gaya!*\n\n#{bid} '{target['name']}'\n\nSheets se bhi hata diya. ✅",
            parse_mode="Markdown"
        )
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")

# ================================================================
# BRIEFING
# ================================================================

async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n = now_ist()
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    today_ev = calendar.today_events()
    week_ev  = calendar.upcoming(days=7)
    due_bills = bills.due_soon(days=3)
    events_str = ""
    if today_ev:
        events_str = "\n\n📅 *Aaj ke Events:*\n" + "\n".join(
            f"  {'🎂' if e.get('type')=='birthday' else '📅'} {e['title']} {e.get('time','')}"
            for e in today_ev
        )
    elif week_ev:
        ne = week_ev[0]
        events_str = f"\n\n📅 *Agla Event:*\n  {'🎂' if ne.get('type')=='birthday' else '📅'} {ne['date']} {ne['title']}"
    bills_str = ""
    if due_bills:
        bills_str = "\n\n💳 *Bills Due Soon:*\n" + "\n".join(
            f"  ⚠️ {b['name']} — Rs.{b['amount']} ({b['due_day']} tarikh)" for b in due_bills
        )
    _log_action(update.effective_user.first_name or "User", "briefing_viewed", f"Tasks:{len(tp)} Habits:{len(hd)}/{len(hd)+len(hp)}")
    await update.message.reply_text(
        f"☪️ *Assalamualaikum! Daily Briefing* 📊\n"
        f"📅 {n.strftime('%d %b %Y')} — {n.strftime('%I:%M %p')} IST\n\n"
        f"✅ Tasks pending: {len(tp)}\n"
        f"🏃 Habits done: {len(hd)}/{len(hd)+len(hp)}\n"
        f"💸 Aaj kharcha: Rs.{expenses.today_total()}\n"
        f"💧 Water: {water.today_total()}ml/{water.goal()}ml"
        f"{events_str}{bills_str}\n\nAlhamdulillah! 🌟",
        parse_mode="Markdown"
    )

# ================================================================
# REMINDER JOB (UPDATED for full timestamp - FIXED for ReminderManager)
# ================================================================

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now = now_ist()
    now_str_full = now.strftime("%Y-%m-%d %H:%M")
    now_hm = now.strftime("%H:%M")

    if now.hour == 0 and now.minute <= 1:
        reminders.reset_daily()

    if now_hm == "21:00":
        tomorrow_events = calendar.events_needing_reminder()
        for e in tomorrow_events:
            emoji = "🎂" if e.get("type") == "birthday" else "📅"
            chat_ids = {r.get("chat_id") for r in reminders.get_all() if r.get("chat_id")}
            for cid in chat_ids:
                try:
                    msg = f"{emoji} *Kal ka Event! InshAllah tayaar raho!*\n\n📅 Kal: {e['date']}\n📌 {e['title']}\n"
                    if e.get("time"):
                        msg += f"⏰ Time: {e['time']}\n"
                    if e.get("location"):
                        msg += f"📍 {e['location']}\n"
                    if e.get("type") == "birthday":
                        msg += "\n🎂 Birthday hai! Mubarak dena mat bhoolo! 🎉"
                    await context.bot.send_message(chat_id=int(cid), text=msg, parse_mode="Markdown")
                    _log_action("Bot", "event_reminder_sent", f"Day-before: {e['title']} on {e['date']}")
                except Exception as ex:
                    log.error(f"Day-before reminder failed: {ex}")

    if now_hm == "09:00":
        due_bills = bills.due_soon(days=3)
        if due_bills:
            chat_ids = {r.get("chat_id") for r in reminders.get_all() if r.get("chat_id")}
            for cid in chat_ids:
                try:
                    lines = "\n".join(f"  💳 {b['name']} — Rs.{b['amount']} (due {b['due_day']} tarikh)" for b in due_bills)
                    await context.bot.send_message(
                        chat_id=int(cid),
                        text=f"⚠️ *Bill Due Soon! Dhyan rakhna!*\n\n{lines}\n\n/billpaid id — Paid mark karo",
                        parse_mode="Markdown"
                    )
                    _log_action("Bot", "bill_reminder_sent", f"Bills due: {', '.join(b['name'] for b in due_bills)}")
                except Exception as ex:
                    log.error(f"Bills reminder failed: {ex}")

    # Check active reminders using FULL TIMESTAMP
    active_reminders = reminders.all_active()
    
    for r in active_reminders:
        if r.get("acknowledged", False):
            continue
        reminder_due = r.get("due", "")
        
        if not reminder_due:
            continue
            
        if len(reminder_due) > 10:
            due_min = reminder_due[:16]
            if due_min == now_str_full:
                if r.get("last_fired_minute") == now_str_full:
                    continue
                    
                fire_count = r.get("fire_count", 0)
                suffix = f"\n⚠️ {fire_count + 1}vi baar baj raha hai — OK dabao!" if fire_count > 0 else ""
                
                try:
                    due_dt = datetime.strptime(reminder_due, "%Y-%m-%d %H:%M:%S")
                    due_time_display = due_dt.strftime("%I:%M %p")
                except:
                    due_time_display = reminder_due
                
                alert = (f"🚨 *ALARM!*\n{'━' * 20}\n⏰ *{due_time_display} BAJ GAYE!*\n{'━' * 20}\n\n"
                         f"🔔 *{r['text'].upper()}*\n{suffix}\n\n"
                         f"😴 Snooze: /snooze5 {r['id']} | /snooze10 {r['id']}\n"
                         f"🗑️ Delete: /delremind {r['id']}")
                try:
                    await context.bot.send_message(
                        chat_id=int(r["chat_id"]), text=alert,
                        reply_markup=alarm_keyboard(r["id"]), parse_mode="Markdown"
                    )
                    # Mark as triggered
                    reminders.mark_triggered(r["id"])
                    _log_action("Bot", "alarm_fired", f"Alarm #{r['id']} at {now_hm}: {r['text']}")
                except Exception as e:
                    log.error(f"Failed to send alarm: {e}")

# ================================================================
# OK BUTTON
# ================================================================

async def handle_ok_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Alarm band!")
    if query.data.startswith("ok_"):
        try:
            rid = int(query.data.split("_")[1])
            target = reminders.get_by_id(rid)
            if not target:
                await query.edit_message_text("✅ Reminder already band hai ya nahi mila.")
                return
            reminder_text = target.get("text", "")
            count = reminders.acknowledge_all_by_text(reminder_text)
            reminders.acknowledge(rid, "User pressed OK")
            _log_action("User", "alarm_acknowledged", f"Alarm #{rid} OK: {reminder_text} ({count} dismissed)")
            if count > 1:
                await query.edit_message_text(
                    f"✅ *{count} alarms band ho gaye! Alhamdulillah!*\n\n'{reminder_text}' — sab dismiss!\n\nNaya reminder: /remind",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(
                    f"✅ *Alarm band ho gaya! JazakAllah!*\n\n'{reminder_text}'\n\nNaya reminder: /remind",
                    parse_mode="Markdown"
                )
        except Exception as e:
            log.error(f"OK button error: {e}")
            await query.edit_message_text("❌ Error stopping alarm!")

# ================================================================
# NATURAL LANGUAGE PARSER (UPDATED for better time detection)
# ================================================================

def parse_user_message(user_msg: str):
    lower = user_msg.lower().strip()

    memory_triggers = [
        "yaad rakhna", "yaad rakh", "memory mein save", "memory me save",
        "note karlo", "yaad karo", "remember", "dimaag mein rakh",
        "save memory", "add memory", "yaad rakhoge"
    ]
    if any(t in lower for t in memory_triggers):
        text = user_msg
        for kw in memory_triggers + ["please", "plz", "zara", "kr", "karo"]:
            text = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", text, flags=_re.IGNORECASE)
        text = " ".join(text.split()).strip()
        if text:
            return ("memory_save", {"text": text})
        return ("memory_save", {"text": user_msg})

    if any(p in lower for p in [
        "reminder dikhao", "reminder dekho", "reminder list", "reminders dikhao",
        "active reminder", "reminder show", "show reminder", "mera reminder",
        "reminder batao", "alarm dikhao", "alarm list", "show alarm",
        "kitne reminder", "saare reminder", "sare reminder", "reminder check",
    ]):
        return ("show_reminders", {})

    if any(p in lower for p in [
        "saare task", "sare task", "task list", "task dikhao", "task dekho",
        "task show", "show task", "pending task", "meri task", "tasks dikhao",
        "tasks dekho", "kya task", "task kya hai", "task batao",
    ]):
        return ("show_tasks", {})

    if any(p in lower for p in [
        "saari habit", "sari habit", "habit list", "habit dikhao", "habit dekho",
        "habit show", "show habit", "meri habit", "habits dikhao",
        "kya habit", "habit batao", "aaj ki habit",
    ]):
        return ("show_habits", {})

    if any(p in lower for p in [
        "diary dikhao", "diary dekho", "diary padho", "show diary",
        "diary show", "aaj ki diary", "meri diary", "diary batao",
        "dairy dikhao", "dairy dekho", "dairy padho", "show dairy",
        "dairy show", "aaj ki dairy", "meri dairy",
    ]):
        return ("show_diary", {})

    if any(p in lower for p in [
        "memory dikhao", "memory dekho", "memory show", "show memory",
        "meri memory", "memory list", "saari memory", "sari memory",
        "kya yaad hai", "kya memory hai", "yaad hai kya"
    ]):
        return ("show_memory", {})

    if any(p in lower for p in [
        "calendar dikhao", "events dikhao", "events dekho", "upcoming events",
        "aaj ka event", "cal dikhao", "schedule dikhao",
    ]):
        return ("show_calendar", {})

    remind_words = [
        "remind", "reminder", "alarm", "yaad dilana", "bata dena",
        "yaad dila", "yaad dila do", "yaad kara", "add reminder",
        "set reminder", "set alarm", "yaad dilao", "yaad krao",
    ]
    if any(w in lower for w in remind_words):
        def _parse_reminder_time(lwr):
            now_t = now_ist()
            mm = _re.search(r'(\d+)\s*(?:min(?:ute)?s?)\b', lwr)
            if mm:
                return (now_t + timedelta(minutes=int(mm.group(1)))).strftime("%Y-%m-%d %H:%M:%S"), False
            hh = _re.search(r'(\d+)\s*(?:hour|hr|ghanta)\b', lwr)
            if hh:
                return (now_t + timedelta(hours=int(hh.group(1)))).strftime("%Y-%m-%d %H:%M:%S"), False
            hm = _re.search(r'(\d{1,2}):(\d{2})', lwr)
            if hm:
                h, mi = int(hm.group(1)), int(hm.group(2))
                remind_dt = datetime(now_t.year, now_t.month, now_t.day, h, mi)
                is_tomorrow = "kal" in lwr or "kl" in lwr or "tomorrow" in lwr
                if is_tomorrow:
                    remind_dt += timedelta(days=1)
                elif remind_dt < now_t:
                    remind_dt += timedelta(days=1)
                return remind_dt.strftime("%Y-%m-%d %H:%M:%S"), False
            amp = _re.search(r'(\d{1,2})\s*(?:am|pm)', lwr)
            if amp:
                h = int(amp.group(1))
                is_pm = "pm" in lwr
                if is_pm and h != 12:
                    h += 12
                elif not is_pm and h == 12:
                    h = 0
                remind_dt = datetime(now_t.year, now_t.month, now_t.day, h, 0)
                if remind_dt < now_t:
                    remind_dt += timedelta(days=1)
                return remind_dt.strftime("%Y-%m-%d %H:%M:%S"), False
            return None, False

        due_timestamp, _ = _parse_reminder_time(lower)
        if due_timestamp:
            stop_words = remind_words + [
                "kal","kl","aaj","tomorrow","subha","subah","morning",
                "shaam","sham","raat","night","evening","dopahar",
                "baje","bajay","baj","pe","par","ko","mein","me",
                "mujhe","please","plz","zara","min","minute","hour","hr"
            ]
            text_clean = lower
            text_clean = _re.sub(r'\d+\s*(?:min(?:ute)?s?)\b', '', text_clean)
            text_clean = _re.sub(r'\d+\s*(?:hour|hr|ghanta)\b', '', text_clean)
            text_clean = _re.sub(r'\d{1,2}:\d{2}', '', text_clean)
            text_clean = _re.sub(r'\d{1,2}\s*(?:am|pm)', '', text_clean)
            for sw in stop_words:
                text_clean = _re.sub(r'\b' + _re.escape(sw) + r'\b', ' ', text_clean)
            text_clean = " ".join(text_clean.split()).strip().title() or "Kaam"
            return ("remind", {"time": due_timestamp, "text": text_clean})
        return ("chat", {"text": user_msg})

    if any(p in lower for p in [
        "habit ho gayi", "habit ho gaya", "habit complete", "habit kar li",
        "habit kar liya", "habit done", "gym ho gaya", "gym kar liya",
        "exercise ho gayi", "exercise kar li", "walk ho gayi", "walk kar li",
        "reading ho gayi", "meditation ho gayi", "yoga ho gayi",
    ]):
        m = _re.search(r'#?(\d+)', lower)
        return ("habit_done", {"keyword": m.group(1) if m else lower[:40]})

    if any(p in lower for p in [
        "habit add", "add habit", "naya habit", "habit lagao", "habit bana",
        "habit start", "new habit", "habit banana",
    ]):
        name = user_msg
        for kw in ["habit", "add", "naya", "new", "karo", "kr", "lagao", "bana", "start", "banana"]:
            name = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", name, flags=_re.IGNORECASE)
        return ("add_habit", {"name": " ".join(name.split()).strip()[:50] or "Habit"})

    if any(t in lower for t in [
        "birthday", "bday", "b'day", "janamdin", "janmdin",
        "calendar add", "cal add", "event add", "add event",
        "calendar mein", "cal mein", "ka birthday", "ki birthday",
        "calendar"
    ]):
        date_str, remaining = _parse_date_from_text(user_msg)
        if date_str:
            title = remaining
            for kw in ["calendar", "cal", "event", "add", "karo", "kr", "mein", "me", "hai", "ka", "ki"]:
                title = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", title, flags=_re.IGNORECASE)
            title = " ".join(title.split()).strip()
            is_bday = any(w in lower for w in ["birthday", "bday", "janamdin", "janmdin"])
            event_type = "birthday" if is_bday else "event"
            if is_bday:
                try:
                    birth = date.fromisoformat(date_str)
                    today_d = now_ist().date()
                    next_bday = birth.replace(year=today_d.year)
                    if next_bday < today_d:
                        next_bday = next_bday.replace(year=today_d.year + 1)
                    date_str = next_bday.strftime("%Y-%m-%d")
                except Exception:
                    pass
            return ("add_calendar", {"title": title or "Event", "date": date_str, "type": event_type})
        return ("chat", {"text": user_msg})

    is_bill_msg = ("bill" in lower or "bills" in lower)
    show_bill_words = ["dikhao", "dekho", "show", "list", "batao", "paid", "kya", "kitne", "sab"]
    is_bill_show = any(w in lower for w in show_bill_words)
    if is_bill_msg and not is_bill_show:
        amount_m = _re.search(r'\b(\d+(?:\.\d+)?)\b', lower)
        if amount_m:
            amount = float(amount_m.group(1))
            title = user_msg
            for kw in ["bill", "bills", "add", "kro", "karo", "kr", "daal", "likh",
                       "lagao", "naya", "new", "subscription"]:
                title = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", title, flags=_re.IGNORECASE)
            title = _re.sub(r'\b' + amount_m.group(1) + r'\b', "", title).strip()
            due_day = 0
            due_m = _re.search(r'(\d{1,2})\s*(?:tarikh|taarikh|date|th|st|nd|rd)', title)
            if due_m:
                candidate = int(due_m.group(1))
                if 1 <= candidate <= 31:
                    due_day = candidate
                    title = title.replace(due_m.group(0), "")
            name = " ".join(title.split()).strip() or "Bill"
            return ("add_bill", {"name": name, "amount": amount, "due_day": due_day})

    diary_add_triggers = [
        "diary mein likho", "diary me likho", "diary mein likh", "diary me likh",
        "diary add", "diary mein add", "diary me add",
        "diary mein daalo", "diary me daalo", "diary save",
        "diary mein note", "diary me note", "add diary",
        "dairy mein likho", "dairy me likho", "dairy mein likh", "dairy me likh",
        "dairy add", "dairy mein add", "dairy me add", "dairy save", "add dairy",
    ]
    if any(p in lower for p in diary_add_triggers):
        text = user_msg
        for kw in ["diary", "dairy", "likho", "likh", "add", "save", "mein", "me",
                   "main", "daalo", "daal", "note", "karo"]:
            text = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", text, flags=_re.IGNORECASE)
        text = " ".join(text.split()).strip()
        return ("diary", {"text": text or user_msg})

    if any(w in lower for w in [
        "paani piya", "water piya", "water log", "paani liya",
        "water pi", "paani pi", "pani piya", "pani pi", "pani liya",
    ]):
        m = _re.search(r'(\d+)\s*(ml|glass|bottle)', lower)
        ml = 250
        if m:
            val, unit = int(m.group(1)), m.group(2)
            ml = val * 250 if "glass" in unit else val * 500 if "bottle" in unit else val
        return ("water", {"ml": ml})

    expense_triggers = [
        "kharcha", "kharch", "karcha", "karch", "kharach",
        "spent", "rupees", "rs",
        "kharch kiya", "laga diye", "lagaya",
        "pe lagaya", "mein lagaya", "ka kharcha", "pe laga",
        "expense",
    ]
    non_expense = ["reminder", "task", "habit", "diary", "dairy", "calendar", "bill", "water", "memory", "paani"]
    if any(w in lower for w in expense_triggers) and not any(n in lower for n in non_expense):
        m = _re.search(r'(\d+(?:\.\d+)?)', lower)
        if m:
            amount = float(m.group(1))
            desc = _re.sub(r'(\d+(?:\.\d+)?|rs\.?|rupees?)', "", user_msg, flags=_re.IGNORECASE)
            desc = " ".join(w for w in desc.split() if w.lower() not in expense_triggers).strip()
            return ("expense", {"amount": amount, "desc": desc or "Expense"})

    if any(p in lower for p in [
        "task done", "kaam ho gaya", "kaam kar liya", "complete kar liya",
        "task complete", "ho gaya task", "kar liya task",
    ]):
        m = _re.search(r'#?(\d+)', lower)
        return ("complete_task", {"hint": m.group(1) if m else lower[:30]})

    task_add_words = [
        "task add", "add task", "naya task", "task lagao", "task likh",
        "task banana", "task karo", "new task",
        "kaam add", "kaam likh", "todo add", "add todo",
    ]
    kaam_soft = ["kaam karna hai", "kaam krna hai", "kaam karna he", "kaam krna he"]

    if any(p in lower for p in task_add_words):
        title = user_msg
        for kw in task_add_words + ["task","kaam","todo","add","karo","kro","kr","lagao","likh","naya","new","banana","karna"]:
            title = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", title, flags=_re.IGNORECASE)
        title = " ".join(title.split()).strip()
        if title and len(title) > 1:
            return ("add_task", {"title": title[:80]})

    if any(p in lower for p in kaam_soft):
        title = user_msg
        for kw in ["kaam", "karna hai", "krna hai", "karna he", "krna he", "add", "karo"]:
            title = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", title, flags=_re.IGNORECASE)
        title = " ".join(title.split()).strip()
        if title and len(title) > 1:
            return ("add_task", {"title": title[:80]})

    if any(t in lower for t in [
        "memory mein", "memory me", "yaad rakhna", "note karo", "note kr",
        "save karo", "save kr", "remember karo",
    ]):
        text = user_msg
        for kw in ["memory","mein","me","save","karo","kr","note","yaad","rakhna","remember"]:
            text = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", text, flags=_re.IGNORECASE)
        return ("memory_save", {"text": " ".join(text.split()).strip() or user_msg})

    return ("chat", {"text": user_msg})


# ================================================================
# SHOW HELPERS
# ================================================================

async def _send_reminder_list(update: Update):
    active = reminders.all_active()
    if active:
        lines = []
        for r in active:
            due = r.get("due", "")
            if due and len(due) > 5 and ":" in due:
                try:
                    dt = datetime.strptime(due, "%Y-%m-%d %H:%M:%S")
                    due_display = dt.strftime("%d %b, %I:%M %p")
                except:
                    due_display = due
            else:
                due_display = due
            lines.append(f"  ⏰ #{r['id']} {due_display} — {r['text']}")
            
        await update.message.reply_text(
            f"⏰ *Active Reminders ({len(active)}):*\n\n" + "\n".join(lines) + "\n\n"
            f"/delremind id — Delete karo\n/snooze5 id — Snooze\n/remind 30m Chai — Naya set karo",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "⏰ Koi active reminder nahi hai.\n\n/remind 30m Chai — Naya set karo",
            parse_mode="Markdown"
        )

async def _send_task_list(update: Update):
    pending = tasks.pending()
    if pending:
        lines = "\n".join(f"  #{t['id']} {t['title']}" for t in pending[:15])
        await update.message.reply_text(
            f"📋 *Pending Tasks ({len(pending)}):*\n\n{lines}\n\n"
            f"/done id — Complete karo\n/deltask id — Delete karo",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "✅ Alhamdulillah! Koi pending task nahi hai.\n\n/task Naam — Naya add karo",
            parse_mode="Markdown"
        )

async def _send_habit_list(update: Update):
    all_h = habits.all()
    if all_h:
        hd, _ = habits.today_status()
        done_ids = [h["id"] for h in hd]
        lines = "\n".join(
            f"  {'✅' if h['id'] in done_ids else '⬜'} #{h['id']} {h['name']} 🔥{h.get('streak', 0)}"
            for h in all_h
        )
        await update.message.reply_text(f"🏃 *Aaj ke Habits:*\n\n{lines}\n\n/hdone id — Log karo", parse_mode="Markdown")
    else:
        await update.message.reply_text("🏃 Koi habit nahi.\n\n/habit Naam — Naya add karo", parse_mode="Markdown")

async def _send_diary_today(update: Update):
    entries = diary.get(today_str())
    if not entries:
        await update.message.reply_text(
            "📖 Aaj ki koi diary entry nahi hai.\n\n/diary write — Likhna shuru karo!\nYa bolo: *diary mein likho [text]*",
            parse_mode="Markdown"
        )
    else:
        lines = "\n\n".join(f"🕐 {e['time']}\n{e['text']}" for e in entries)
        await update.message.reply_text(f"📖 *Aaj ki Diary ({today_str()}):*\n\n{lines}", parse_mode="Markdown")

async def _send_calendar_list(update: Update):
    events = calendar.upcoming(days=30)
    if events:
        lines = [f"{'🎂' if e.get('type')=='birthday' else '📅'} *{e['date']}* — #{e['id']}\n   {e['title']}" for e in events[:10]]
        await update.message.reply_text(f"📅 *Upcoming Events ({len(events)}):*\n\n" + "\n\n".join(lines), parse_mode="Markdown")
    else:
        await update.message.reply_text("📅 Koi upcoming event nahi.\n\n/caladd — Add karo", parse_mode="Markdown")

async def _send_memory_list(update: Update):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text(
            "🧠 Koi memory saved nahi hai.\n\n/memory add text — Naya memory save karo\n/memory search word — Search karo",
            parse_mode="Markdown"
        )
        return
    lines = []
    for i, fact in enumerate(facts[-15:], 1):
        date_str = fact.get("d", "unknown date")
        text = fact.get("f", str(fact))
        lines.append(f"📌 *{i}.* _{date_str}_\n   {text[:100]}")
    await update.message.reply_text(
        f"🧠 *Saved Memories ({len(facts)} total):*\n\n" + "\n\n".join(lines) +
        "\n\n/memory add text — Naya add karo\n/memory search word — Search karo\n/memory clear — Sab delete karo",
        parse_mode="Markdown"
    )


# ================================================================
# MESSAGE HANDLER
# ================================================================

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_msg  = update.message.text.strip()
    user_name = update.effective_user.first_name or "User"
    if user_msg.startswith("/"):
        return

    if await check_smart_memory_intent(update, ctx):
        chat_hist.add("user", user_msg, user_name)
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    action_type, params = parse_user_message(user_msg)
    log.info(f"MSG: '{user_msg[:60]}' → {action_type}")

    chat_hist.add("user", user_msg, user_name)

    if action_type == "show_reminders":
        await _send_reminder_list(update)
        _log_action(user_name, "show_reminders", user_msg[:60])

    elif action_type == "show_tasks":
        await _send_task_list(update)
        _log_action(user_name, "show_tasks", user_msg[:60])

    elif action_type == "show_habits":
        await _send_habit_list(update)
        _log_action(user_name, "show_habits", user_msg[:60])

    elif action_type == "show_diary":
        await _send_diary_today(update)
        _log_action(user_name, "show_diary", user_msg[:60])

    elif action_type == "show_memory":
        await _send_memory_list(update)
        _log_action(user_name, "show_memory", user_msg[:60])

    elif action_type == "show_calendar":
        await _send_calendar_list(update)
        _log_action(user_name, "show_calendar", user_msg[:60])

    elif action_type == "remind":
        due_timestamp = params.get("time", "")
        text = params.get("text", "Reminder")
        
        r = reminders.add(update.effective_chat.id, text, due_timestamp)
        
        try:
            remind_dt = datetime.strptime(due_timestamp, "%Y-%m-%d %H:%M:%S")
            date_display = remind_dt.strftime("%d %b %Y")
            h, m_val = remind_dt.hour, remind_dt.minute
            ampm = "AM" if h < 12 else "PM"
            h12 = h % 12 or 12
            time_display = f"{h12}:{m_val:02d} {ampm}"
        except:
            date_display = "today"
            time_display = due_timestamp
        
        _log_action(user_name, "reminder_set", f"#{r['id']} at {due_timestamp}: {text}")
        await update.message.reply_text(
            f"⏰ *Reminder Set! InshAllah yaad dilaaunga!*\n\n"
            f"🕐 *{time_display}* — 📅 *{date_display}*\n"
            f"📝 {text}\n"
            f"📌 ID #{r['id']}",
            parse_mode="Markdown"
        )

    elif action_type == "add_task":
        t = tasks.add(params.get("title", ""))
        _log_action(user_name, "task_add", f"#{t['id']}: {t['title']}")
        await update.message.reply_text(
            f"✅ *Task Add Ho Gaya!*\n\n📌 #{t['id']} {t['title']}\n\nInshAllah ho jayega! 💪",
            parse_mode="Markdown"
        )

    elif action_type == "complete_task":
        hint = params.get("hint", "")
        pending = tasks.pending()
        matched = next((t for t in pending if str(t["id"]) == hint or (hint and hint in t["title"].lower())), None)
        if matched:
            tasks.complete(matched["id"])
            _log_action(user_name, "task_done", f"#{matched['id']}: {matched['title']}")
            await update.message.reply_text(
                f"✅ *Alhamdulillah! Task Complete!* 🎉\n\n#{matched['id']} {matched['title']}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❓ Kaunsa task? ID ya naam batao")

    elif action_type == "expense":
        expenses.add(params.get("amount", 0), params.get("desc", ""))
        _log_action(user_name, "expense_add", f"Rs.{params.get('amount')} on {params.get('desc')} | Total: Rs.{expenses.today_total()}")
        await update.message.reply_text(
            f"💸 Rs.{params.get('amount')} — {params.get('desc')}\n💰 Aaj total: Rs.{expenses.today_total()}",
            parse_mode="Markdown"
        )

    elif action_type == "diary":
        diary.add(params.get("text", ""))
        _log_action(user_name, "diary_write", f"Entry: {params.get('text', '')[:80]}")
        await update.message.reply_text(
            f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n_{params.get('text', '')[:100]}_\n\nSheets mein bhi!",
            parse_mode="Markdown"
        )

    elif action_type == "add_habit":
        h = habits.add(params.get("name", ""))
        _log_action(user_name, "habit_add", f"#{h['id']}: {h['name']}")
        await update.message.reply_text(
            f"🏃 *Habit Add Ho Gaya!*\n\n#{h['id']} {h['name']}\n\nInshAllah roz karoge! 💪",
            parse_mode="Markdown"
        )

    elif action_type == "habit_done":
        keyword = params.get("keyword", "")
        if keyword.isdigit():
            ok, streak = habits.log(int(keyword))
            name = f"#{keyword}"
        else:
            ok, streak, h = habits.log_by_name(keyword)
            name = h["name"] if h else keyword
        if ok:
            _log_action(user_name, "habit_done", f"'{name}' done | streak: {streak}")
            await update.message.reply_text(
                f"🔥 *{name} done! MashAllah!* 🎉\n\n{streak} din ka streak! 💪",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❓ Kaunsa habit? /habit se list dekho aur /hdone id se log karo")

    elif action_type == "add_calendar":
        title   = params.get("title", "Event")
        ev_date = params.get("date", today_str())
        ev_type = params.get("type", "event")
        e = calendar.add(title, ev_date, "", "", "", ev_type)
        _log_action(user_name, "calendar_add", f"{'Birthday' if ev_type=='birthday' else 'Event'} #{e['id']}: {title} on {ev_date}")
        emoji = "🎂" if ev_type == "birthday" else "📅"
        if ev_type == "birthday":
            msg = f"{emoji} *Birthday Add Ho Gaya! MashAllah!* 🎉\n\n#{e['id']} 🎂 *{ev_date}*\n👤 {title}\n\n✅ Ek din pehle remind karunga!\n📊 Sheets mein save!"
        else:
            msg = f"{emoji} *Event Add Ho Gaya!* ✅\n\n#{e['id']} 📅 *{ev_date}*\n📌 {title}\n\n✅ Ek din pehle remind karunga!\n📊 Sheets mein save!"
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif action_type == "add_bill":
        name    = params.get("name", "Bill")
        amount  = params.get("amount", 0)
        due_day = params.get("due_day", 0)
        b = bills.add(name, amount, due_day)
        _log_action(user_name, "bill_add", f"#{b['id']}: {name} Rs.{amount} due {due_day} tarikh")
        await update.message.reply_text(
            f"💳 *Bill Add Ho Gaya! Alhamdulillah!* ✅\n\n#{b['id']} *{name}*\n"
            f"💰 Rs.{amount}\n📅 Due: {due_day} tarikh\n\n"
            f"📊 Sheets mein save!\n_(Due 0 = not set; /billadd se sahi due day set karo)_",
            parse_mode="Markdown"
        )

    elif action_type == "water":
        ml = params.get("ml", 250)
        total = water.add(ml)
        goal_ml = water.goal()
        pct = int(total / goal_ml * 100) if goal_ml else 0
        _log_action(user_name, "water_log", f"Added {ml}ml | Total: {total}ml of {goal_ml}ml")
        await update.message.reply_text(
            f"💧 *{ml}ml Paani!*\n\nTotal: {total}/{goal_ml}ml ({pct}%)\n\n"
            f"{'Alhamdulillah! Goal complete! 🎉' if total >= goal_ml else 'InshAllah goal poora hoga! 💪'}",
            parse_mode="Markdown"
        )

    elif action_type == "memory_save":
        text = params.get("text", "")
        try:
            memory.add(text)
            _log_action(user_name, "memory_save", f"Saved: {text[:80]}")
            await update.message.reply_text(
                f"🧠 *Memory Mein Save Ho Gaya!* ✅\n\n_{text[:150]}_\n\nInshAllah yaad rakhunga! 💡",
                parse_mode="Markdown"
            )
        except Exception:
            diary.add(f"[Memory] {text}")
            _log_action(user_name, "memory_save_fallback", f"Saved as diary: {text[:80]}")
            await update.message.reply_text(f"🧠 *Note Save Ho Gaya!* ✅\n\n_{text[:150]}_", parse_mode="Markdown")

    else:  # AI chat
        # Build prompt with strong Hinglish instruction
        prompt = build_system_prompt() + f"""

USER SAID: {user_msg}

🚨 IMPORTANT - APNA REPLY HINGLISH MEIN DO:
- Hinglish matlab Hindi words English letters mein likhna
- Example: "Assalamualaikum! Aapka task complete ho gaya!"
- Example: "Alhamdulillah! Aaj aapne {len(habits.today_status()[0])} habits kar liye!"
- Example: "InshAllah, main aapki help kar dunga!"

YOUR HINGLISH REPLY (2-3 lines only, Muslim phrases zaroor use karo):"""
        
        reply = call_gemini(prompt)
        
        if not reply:
            reply = "☪️ Assalamualaikum! Batao kya help chahiye?\nTasks, reminders, kharcha, diary, calendar, bills?"
        
        # Fix common English responses
        english_greetings = ["Hello", "Hi", "Hey", "Good morning", "Good evening", "Good afternoon"]
        for eng in english_greetings:
            if reply.lower().startswith(eng.lower()):
                reply = "Assalamualaikum! " + reply[len(eng):].strip()
        
        # Add Assalamualaikum if missing
        if not any(word in reply.lower() for word in ['assalamualaikum', 'alaikum', 'salam', 'alhamdulillah']):
            reply = "Assalamualaikum! " + reply
        
        _log_action(user_name, "ai_chat", f"Q: {user_msg[:60]} | A: {reply[:60]}")
        await update.message.reply_text(reply, parse_mode="Markdown")

    chat_hist.add("assistant", "Reply sent", "Rk")


# ================================================================
# MAIN - UPDATED WITH CLEANUP
# ================================================================

def main():
    # CRITICAL: Cleanup before starting (fixes conflict error)
    cleanup_before_start()
    
    log.info("=" * 60)
    log.info("Rk Bot v13 FINAL | Hinglish fixes | Voice offline | Fixed Reminders")
    log.info(f"IST: {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Sheets: {'Yes' if sheets_backup.connected else 'No'}")
    log.info(f"GitHub: {'Yes' if repo_manager.is_connected else 'No'}")
    log.info("=" * 60)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # ============================================================
    # 🔥 SETUP CHANNEL LOGGER - Personal Space
    # ============================================================
    try:
        from secure_data_manager import channel_logger
        channel_logger.set_bot(app.bot)
        log.info("✅ Channel logger connected to bot")
        
        # Send startup message to channel
        asyncio.create_task(channel_logger.log_startup())
    except Exception as e:
        log.warning(f"Channel logger setup failed: {e}")
    # ============================================================

    # Register handlers
    from delete_manager import register_delete_handlers
    register_delete_handlers(app)

    register_memory_handlers(app)
    
    # Voice handlers with multiple transcription methods (UPDATED v8)
    register_voice_handlers(app)

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary_entry)],
        states={
            DIARY_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)],
            DIARY_AWAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_text_input)],
        },
        fallbacks=[CommandHandler("cancel", diary_cancel)],
        per_user=True, per_chat=True, per_message=False,
    ))

    for cmd, handler in [
        ("start", cmd_start), ("help", cmd_help),
        ("status", cmd_status), ("checksync", cmd_checksync),
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("habit", cmd_habit), ("hdone", cmd_hdone),
        ("kharcha", cmd_kharcha), ("remind", cmd_remind),
        ("delremind", cmd_delremind), ("water", cmd_water),
        ("briefing", cmd_briefing), ("save", cmd_save),
        ("snooze5", cmd_snooze), ("snooze10", cmd_snooze),
        ("snooze30", cmd_snooze), ("snooze60", cmd_snooze),
        ("cal", cmd_cal), ("caltoday", cmd_caltoday),
        ("calweek", cmd_calweek), ("caladd", cmd_caladd), ("caldel", cmd_caldel),
        ("bills", cmd_bills), ("billadd", cmd_billadd),
        ("billpaid", cmd_billpaid), ("billdel", cmd_billdel),
    ]:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(CallbackQueryHandler(handle_ok_button, pattern=r"^ok_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Reminder job runs every 60 seconds
    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=10)
        log.info("⏰ Reminder job scheduled (every 60s)")
    else:
        log.warning("⚠️ JobQueue not available - reminders may not work!")

    log.info("✅ Bot ready! Starting polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
