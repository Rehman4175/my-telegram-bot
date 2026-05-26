#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PERSONAL AI ASSISTANT — RK BOT v18.4 COMPLETE
===============================================
ALL v17 FEATURES RESTORED + ALL v18.x FIXES:
  ✅ Smart Reminder time parsing bug fixed
  ✅ smart_daily_summary today_str consistency
  ✅ Reminder deduplication with persistent tracking
  ✅ Smart chain full acknowledge (recursive parent search)
  ✅ cleanup_before_start uses urllib
  ✅ Chat history used in Gemini context
  ✅ Proactive Follow-up (pending tasks > 2 days)
  ✅ Context-aware Replies (last 5 messages)
  ✅ Smart Morning Brief (personalized)
  ✅ Habit Streak Guard (8 PM pending habits only)
  ✅ Weekly Review (Sunday 9 PM auto-summary)
  ✅ Bill Smart Alert (only when 2 days left & unpaid)
  ✅ "Kya kiya aaj?" Command (/today)
  ✅ Expense Insights (weekly budget warning)
  ✅ One-line Quick Add (fast syntax)
  ✅ Memory Auto-tag (automatic categorization)
  ✅ "may" regex ambiguity fixed
  ✅ (\d+)s\b false positive fixed
  ✅ cmd_billpaid None-safe
  ✅ dd-MMM-yyyy date pattern restored
  ✅ ALL v17 natural language patterns preserved
  ✅ Water bar visualization restored
  ✅ Full detailed help restored
  ✅ All _log_action calls restored
  ✅ 8 PM Habit Guard separate slot
  ✅ show_all_diary handler restored
  ✅ add_bill/add_calendar handlers restored
  ✅ kaam_soft patterns restored
"""

import os, json, logging, time
import urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta, timezone
import re as _re
import re
import asyncio

from secure_data_manager import (
    memory, tasks, diary, habits, expenses, goals, reminders,
    water, bills, calendar, chat_hist, now_ist, today_str, now_str,
    sheets_backup, DATA_DIR, repo_manager
)

ssl._create_default_https_context = ssl._create_unverified_context

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

# ── NEW ADDON IMPORTS ──────────────────────────────
from voice_note_handler import register_voice_handlers
from smart_memory_handler import register_memory_handlers, check_smart_memory_intent
# ──────────────────────────────────────────────────

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
HUGGINGFACE_API_KEY = os.environ.get("HUGGINGFACE_API_KEY", "")

# Configurable budget threshold for expense insights
WEEKLY_BUDGET_THRESHOLD = int(os.environ.get("WEEKLY_BUDGET_THRESHOLD", "1000"))

DIARY_AWAIT_TEXT = 0

if not TELEGRAM_TOKEN:
    print("TELEGRAM_TOKEN not set!")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ── UTILITY: Safe today_str wrapper ─────────────────
def get_today_str():
    """Safe wrapper - returns today's date string YYYY-MM-DD whether today_str is callable or string"""
    if callable(today_str):
        return today_str()
    return str(today_str)

def get_now_str():
    """Safe wrapper for now_str"""
    if callable(now_str):
        return now_str()
    return str(now_str)

GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
_last_gemini_call = 0

# ── CONTEXT MANAGEMENT (for smart replies) ─────────
chat_context = {}
_last_context_cleanup = time.time()

def cleanup_chat_context():
    """Periodic cleanup - removes chats inactive for > 24 hours"""
    global _last_context_cleanup
    now = time.time()
    if now - _last_context_cleanup < 3600:
        return
    _last_context_cleanup = now
    
    cutoff_date = now_ist().date() - timedelta(days=1)
    to_remove = []
    
    for chat_id, msgs in list(chat_context.items()):
        if not msgs:
            to_remove.append(chat_id)
            continue
        
        last_msg = msgs[-1]
        last_ts = last_msg[2]  # Full datetime string "YYYY-MM-DD HH:MM"
        
        try:
            last_dt = datetime.strptime(last_ts[:16], "%Y-%m-%d %H:%M")
            if last_dt.date() < cutoff_date:
                to_remove.append(chat_id)
        except:
            if len(msgs) >= 20:
                to_remove.append(chat_id)
    
    for cid in to_remove:
        del chat_context[cid]
    
    if to_remove:
        log.info(f"🧹 Cleaned {len(to_remove)} old chat contexts, {len(chat_context)} remaining")


# ── GEMINI API CALL ─────────────────────────────────
def call_gemini(prompt, max_tokens=400):
    """Call Gemini API with strong Hinglish instruction"""
    global _last_gemini_call
    if not GEMINI_API_KEY:
        return None
    elapsed = time.time() - _last_gemini_call
    if elapsed < 2:
        time.sleep(2 - elapsed)
    _last_gemini_call = time.time()
    
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
                
                english_greetings = ["Hello", "Hi", "Hey", "Good morning", "Good evening", "Good afternoon"]
                for eng in english_greetings:
                    if reply.lower().startswith(eng.lower()):
                        reply = "Assalamualaikum! " + reply[len(eng):].strip()
                
                if not any(word in reply.lower() for word in ['assalamualaikum', 'alaikum', 'salam', 'alhamdulillah']):
                    reply = "Assalamualaikum! " + reply
                
                return reply
        except Exception as e:
            log.warning(f"Gemini error ({model}): {e}")
    
    log.error("All Gemini models failed!")
    return None

# ── CONTEXT-AWARE PROMPT BUILDER ────────────────────
def get_chat_context(chat_id, last_n=5):
    """Get last N messages for context-aware replies"""
    cleanup_chat_context()
    if chat_id not in chat_context:
        return ""
    recent = chat_context[chat_id][-last_n:]
    lines = []
    for role, text, ts in recent:
        prefix = "USER" if role == "user" else "RK"
        try:
            display_ts = datetime.strptime(ts[:16], "%Y-%m-%d %H:%M").strftime("%H:%M")
        except:
            display_ts = ts
        lines.append(f"[{prefix} at {display_ts}]: {text[:100]}")
    return "\n".join(lines)

def add_to_context(chat_id, role, text):
    """Add message to context store with full timestamp"""
    if chat_id not in chat_context:
        chat_context[chat_id] = []
    full_ts = now_ist().strftime("%Y-%m-%d %H:%M")
    chat_context[chat_id].append((role, text, full_ts))
    if len(chat_context[chat_id]) > 20:
        chat_context[chat_id] = chat_context[chat_id][-20:]

def build_system_prompt(chat_id=None):
    """Build system prompt with current data and context"""
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    exp_t = expenses.today_total()
    wt = water.today_total()
    wg = water.goal()
    active_rem = reminders.all_active()
    today_events = calendar.today_events()
    
    base = f"""☪️ ASSALAMUALAIKUM! Main Rk hoon - aapka personal AI assistant.

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
- Short reply hoga (2-3 lines)"""
    
    if chat_id:
        context = get_chat_context(chat_id, 5)
        if context:
            base += f"\n\n📝 RECENT CONVERSATION:\n{context}\n\n(Is context ko dhyan mein rakh kar jawab do)"
    
    return base + "\n\nUser ka message padho aur HINGLISH mein jawab do!"


# ── ALARM KEYBOARD ──────────────────────────────────
def alarm_keyboard(rid):
    """Create inline keyboard for alarm OK button"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ OK — Alarm Band Karo", callback_data=f"ok_{rid}")
    ]])


# ── CLEANUP FUNCTION ────────────────────────────────
def cleanup_before_start():
    """Force delete webhook and clear pending updates to prevent conflict"""
    token = TELEGRAM_TOKEN
    if not token:
        return
    
    try:
        url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info(f"Webhook deleted: {resp.status}")
        
        url2 = f"https://api.telegram.org/bot{token}/getUpdates?offset=-1&timeout=1"
        req2 = urllib.request.Request(url2, method="POST")
        with urllib.request.urlopen(req2, timeout=5):
            pass
        
        log.info("✅ Cleanup completed - old connections cleared")
    except Exception as e:
        log.warning(f"Cleanup warning (non-critical): {e}")


# ── MISCELLANEOUS LOGGER ────────────────────────────
def _log_action(user_name: str, action_type: str, detail: str):
    """Log user actions to Google Sheets"""
    try:
        clean_detail = str(detail).strip()
        if clean_detail.startswith(("=", "+", "-", "@")):
            clean_detail = "'" + clean_detail
        sheets_backup.log_event(action_type, str(user_name), clean_detail)
        log.info(f"[MiscLog] {action_type} | {user_name} | {clean_detail[:60]}")
    except Exception as e:
        log.warning(f"_log_action failed: {e}")


# ── SAFE EXPENSE ACCESSOR ───────────────────────────
def _get_expenses_list():
    """Safe wrapper to get expenses list without direct store access"""
    try:
        if hasattr(expenses, 'get_all'):
            result = expenses.get_all()
            if isinstance(result, list):
                return result
        if hasattr(expenses, 'list_all'):
            result = expenses.list_all()
            if isinstance(result, list):
                return result
        data = expenses.store.data.get("list", [])
        return data if isinstance(data, list) else []
    except Exception:
        return []


# ════════════════════════════════════════════════════
# DATE PARSER
# ════════════════════════════════════════════════════

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
    """Parse date from natural language - supports multiple formats"""
    lower = text.lower()
    today_d = now_ist().date()

    # YYYY-MM-DD
    m = _re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', lower)
    if m:
        try:
            yr, mo, dy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            d = date(yr, mo, dy)
            remaining = _re.sub(r'\d{4}-\d{1,2}-\d{1,2}', '', text).strip()
            return d.strftime("%Y-%m-%d"), remaining
        except Exception:
            pass

    # DD/MM/YYYY or DD/MM/YY or YYYY/MM/DD
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

    # DD Mon YYYY (e.g., "20 May 2026") - "may(?:i)?" for reduced ambiguity
    month_names = "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may(?:i)?|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    
    m = _re.search(r'(\d{1,2})\s+(' + month_names + r')\s+(\d{4})', lower)
    if m:
        try:
            dy = int(m.group(1))
            mon_str = m.group(2)[:3].lower()
            yr = int(m.group(3))
            mon_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
            mo = mon_map.get(mon_str, 0)
            if mo and 1 <= mo <= 12:
                d = date(yr, mo, dy)
                remaining = _re.sub(r'\d{1,2}\s+' + month_names + r'\s+\d{4}', '', text, flags=_re.IGNORECASE).strip()
                return d.strftime("%Y-%m-%d"), remaining
        except Exception:
            pass

    # DD-Mon-YYYY
    m = _re.search(r'(\d{1,2})[- ](' + "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec" + r')[- ](\d{4})', lower, _re.IGNORECASE)
    if m:
        try:
            dy = int(m.group(1))
            mon_str = m.group(2).lower()
            yr = int(m.group(3))
            mon_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
            mo = mon_map.get(mon_str, 0)
            if mo and 1 <= mo <= 12:
                d = date(yr, mo, dy)
                remaining = _re.sub(r'\d{1,2}[- ](?:' + "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec" + r')[- ]\d{4}', '', text, flags=_re.IGNORECASE).strip()
                return d.strftime("%Y-%m-%d"), remaining
        except Exception:
            pass

    # Generic month name pattern
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

    # Relative dates
    if "parso" in lower:
        return (today_d + timedelta(days=2)).strftime("%Y-%m-%d"), _re.sub(r'\bparso\b', '', text, flags=_re.IGNORECASE).strip()
    if _re.search(r'\bkal\b|\bkl\b', lower):
        return (today_d + timedelta(days=1)).strftime("%Y-%m-%d"), _re.sub(r'\bkal\b|\bkl\b', '', text, flags=_re.IGNORECASE).strip()
    if "aaj" in lower:
        return today_d.strftime("%Y-%m-%d"), _re.sub(r'\baaj\b', '', text, flags=_re.IGNORECASE).strip()

    return None, text


def _parse_time_from_text(text):
    """Parse time like '9 baje', '9 am', '9:00' from text"""
    lower = text.lower()
    
    match = _re.search(r'(\d{1,2})\s*(?:baje|bajay|am|pm|subah|shaam|raat|morning|evening|night)', lower)
    if match:
        hour = int(match.group(1))
        if any(x in lower for x in ['pm', 'shaam', 'raat', 'evening', 'night']):
            if hour != 12:
                hour += 12
        elif any(x in lower for x in ['am', 'subah', 'morning']):
            if hour == 12:
                hour = 0
        return f"{hour:02d}:00"
    
    match = _re.search(r'(\d{1,2}):(\d{2})', lower)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        return f"{hour:02d}:{minute:02d}"
    
    match = _re.search(r'(\d{1,2})\s*(?:o\'clock|baje|bajay)', lower)
    if match:
        hour = int(match.group(1))
        return f"{hour:02d}:00"
    
    return None


def _parse_reminder_time(lwr):
    """Parse reminder time from text with safe regex patterns"""
    now_t = now_ist()
    
    # Minutes - full word then bare 'm' with negative lookahead
    mm = _re.search(r'(\d+)\s*(?:minutes?|mins?)\b', lwr, _re.IGNORECASE)
    if not mm:
        mm = _re.search(r'\b(\d+)m\b(?!\w)', lwr, _re.IGNORECASE)
    if mm:
        mins = int(mm.group(1))
        remind_dt = now_t + timedelta(minutes=mins)
        return remind_dt.strftime("%Y-%m-%d %H:%M:%S"), False
    
    # Hours
    hh = _re.search(r'(\d+)\s*(?:hours?|hrs?|ghanta|ghante)\b', lwr, _re.IGNORECASE)
    if not hh:
        hh = _re.search(r'\b(\d+)h\b(?!\w)', lwr, _re.IGNORECASE)
    if hh:
        hours = int(hh.group(1))
        remind_dt = now_t + timedelta(hours=hours)
        return remind_dt.strftime("%Y-%m-%d %H:%M:%S"), False
    
    # Seconds - CRITICAL: (?!\w) prevents matching "tasks", "bills", "events"
    ss = _re.search(r'(\d+)\s*(?:seconds?|secs?)\b', lwr, _re.IGNORECASE)
    if not ss:
        ss = _re.search(r'\b(\d+)s\b(?!\w)', lwr, _re.IGNORECASE)
    if ss:
        secs = int(ss.group(1))
        remind_dt = now_t + timedelta(seconds=secs)
        return remind_dt.strftime("%Y-%m-%d %H:%M:%S"), False
    
    # Days
    dd = _re.search(r'(\d+)\s*(?:days?|din)\b', lwr, _re.IGNORECASE)
    if not dd:
        dd = _re.search(r'\b(\d+)d\b(?!\w)', lwr, _re.IGNORECASE)
    if dd:
        days = int(dd.group(1))
        remind_dt = now_t + timedelta(days=days)
        return remind_dt.strftime("%Y-%m-%d %H:%M:%S"), False
    
    # HH:MM format
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
    
    # AM/PM format
    amp = _re.search(r'(\d{1,2})\s*(?:am|pm|baje|bajay|subah|shaam|raat)', lwr, _re.IGNORECASE)
    if amp:
        h = int(amp.group(1))
        is_pm = any(x in lwr for x in ['pm', 'shaam', 'raat'])
        if is_pm and h != 12:
            h += 12
        elif not is_pm and h == 12:
            h = 0
        remind_dt = datetime(now_t.year, now_t.month, now_t.day, h, 0)
        if remind_dt < now_t:
            remind_dt += timedelta(days=1)
        return remind_dt.strftime("%Y-%m-%d %H:%M:%S"), False
    
    return None, False


# ════════════════════════════════════════════════════
# MEMORY AUTO-TAG
# ════════════════════════════════════════════════════

def auto_tag_memory(text):
    """Automatically categorize memory based on keyword analysis"""
    text_lower = text.lower()
    
    health_keywords = ['doctor', 'medicine', 'dawai', 'health', 'hospital', 'bimar',
                       'fever', 'bukhar', 'pain', 'dard', 'exercise', 'gym', 'yoga', 'diet',
                       'blood', 'sugar', 'bp', 'pressure', 'weight', 'vajan']
    
    finance_keywords = ['paisa', 'rupees', 'rs', 'kharcha', 'salary', 'loan', 'emi', 'bank',
                        'payment', 'bill', 'invest', 'saving', 'budget', 'money', 'finance']
    
    personal_keywords = ['family', 'ghar', 'home', 'friend', 'dost', 'wife', 'husband', 'bache',
                         'bacha', 'birthday', 'anniversary', 'shaadi', 'marriage', 'rishta']
    
    work_keywords = ['job', 'naukri', 'office', 'kaam', 'work', 'meeting', 'boss', 'project',
                     'client', 'deadline', 'presentation', 'interview']
    
    if any(kw in text_lower for kw in health_keywords):
        return "health"
    elif any(kw in text_lower for kw in finance_keywords):
        return "finance"
    elif any(kw in text_lower for kw in personal_keywords):
        return "personal"
    elif any(kw in text_lower for kw in work_keywords):
        return "work"
    return "general"


# ════════════════════════════════════════════════════
# SMART DAILY SUMMARY (with 8 PM Habit Guard)
# ════════════════════════════════════════════════════

async def smart_daily_summary(context: ContextTypes.DEFAULT_TYPE):
    """
    Smart daily summary - sends personalized reminders 5 times a day
    Times: 9:00 AM, 1:00 PM, 6:00 PM, 8:00 PM(habits), 9:00 PM IST
    """
    now = now_ist()
    current_time = now.strftime("%H:%M")
    
    chat_ids = set()
    for r in reminders.get_all():
        if r.get("chat_id"):
            try:
                chat_ids.add(int(r["chat_id"]))
            except:
                pass
    
    if not chat_ids:
        log.info("No active chats found for daily summary")
        return
    
    pending_tasks = tasks.pending()
    habits_done, habits_pending = habits.today_status()
    today_expense = expenses.today_total()
    today_water = water.today_total()
    water_goal = water.goal()
    today_events = calendar.today_events()
    today_str_val = get_today_str()
    
    msg = None
    
    # ── 9:00 AM - Morning Summary ──
    if current_time == "09:00":
        msg = f"☀️ *Assalamualaikum! Good Morning!* ☀️\n\n"
        msg += f"📋 *Aaj ke Pending Tasks:* {len(pending_tasks)}\n"
        if pending_tasks:
            task_list = "\n".join([f"   {i+1}. {t['title'][:50]}" for i, t in enumerate(pending_tasks[:5])])
            msg += f"{task_list}\n"
            if len(pending_tasks) > 5:
                msg += f"   ... aur {len(pending_tasks)-5} tasks\n"
        else:
            msg += f"   ✅ Koi pending task nahi! Alhamdulillah!\n"
        
        msg += f"\n🏃 *Aaj ki Habits:* {len(habits_done)}/{len(habits_done)+len(habits_pending)} done\n"
        if habits_pending:
            habit_list = "\n".join([f"   ⬜ {h['name']}" for h in habits_pending[:3]])
            msg += f"{habit_list}\n"
        
        msg += f"\n📅 *Aaj ke Events:* {len(today_events)}\n"
        if today_events:
            event_list = "\n".join([f"   📌 {e['title']}" for e in today_events[:3]])
            msg += f"{event_list}\n"
        
        msg += f"\n💡 *InshAllah aaj ka din productive rahega!*"
    
    # ── 1:00 PM - Afternoon Reminder ──
    elif current_time == "13:00":
        msg = f"🍽️ *Dopahar ho gayi!* 🍽️\n\n"
        msg += f"📋 *Aaj abhi tak pending tasks:* {len(pending_tasks)}\n"
        if pending_tasks:
            task_list = "\n".join([f"   ⏰ {t['title'][:50]}" for t in pending_tasks[:3]])
            msg += f"{task_list}\n"
        
        msg += f"\n💧 *Paani:* {today_water}ml / {water_goal}ml\n"
        if today_water < water_goal:
            msg += f"   ⚠️ {water_goal - today_water}ml aur piyo!\n"
        else:
            msg += f"   ✅ Goal complete! MashAllah!\n"
        
        msg += f"\n🏃 *Habits pending:* {len(habits_pending)}\n"
        msg += f"\n☕ *Lunch break! InshAllah baaki kaam bhi ho jayega!*"
    
    # ── 6:00 PM - Evening Summary ──
    elif current_time == "18:00":
        completed_tasks = len([t for t in tasks.all_tasks() if t.get("done") and t.get("done_date") == today_str_val])
        
        msg = f"🌙 *Shaam ho gayi!* 🌙\n\n"
        msg += f"✅ *Aaj complete kiye:* {completed_tasks} tasks\n"
        msg += f"📋 *Abhi baki:* {len(pending_tasks)} tasks\n"
        
        if pending_tasks:
            msg += f"\n⚠️ *Baki tasks:*\n"
            for i, t in enumerate(pending_tasks[:5]):
                msg += f"   {i+1}. {t['title'][:50]}\n"
        
        msg += f"\n💸 *Aaj ka kharcha:* Rs.{today_expense}\n"
        msg += f"💧 *Paani:* {today_water}ml/{water_goal}ml\n"
        msg += f"\n🌙 *InshAllah raat tak sab ho jayega!*"
    
    # ── 8:00 PM - Habit Streak Guard ──
    elif current_time == "20:00":
        if habits_pending:
            msg = f"⚠️ *Raat ho rahi hai! Ye habits abhi pending hain:*\n\n"
            for h in habits_pending[:5]:
                msg += f"   ⬜ #{h['id']} *{h['name']}*\n"
            msg += f"\n🏃 *Jaldi kar lo! /hdone id se log karo!*\n"
            msg += f"\n💪 _InshAllah streak tootne mat do!_"
        else:
            return  # Sab habits done, chup chaap
    
    # ── 9:00 PM - Night Summary ──
    elif current_time == "21:00":
        completed_tasks = len([t for t in tasks.all_tasks() if t.get("done") and t.get("done_date") == today_str_val])
        
        msg = f"🌟 *Assalamualaikum! Day Summary* 🌟\n\n"
        msg += f"✅ *Aaj complete kiye:* {completed_tasks} tasks\n"
        msg += f"📋 *Baki rahe:* {len(pending_tasks)} tasks\n"
        
        if habits_done:
            msg += f"🏃 *Habits done:* {len(habits_done)}/{len(habits_done)+len(habits_pending)}\n"
        
        msg += f"💸 *Aaj ka kharcha:* Rs.{today_expense}\n"
        msg += f"💧 *Paani:* {today_water}ml/{water_goal}ml\n\n"
        
        tomorrow_events = calendar.tomorrow_events()
        if tomorrow_events:
            msg += f"📅 *Kal ke events:*\n"
            for e in tomorrow_events:
                emoji = "🎂" if e.get("type") == "birthday" else "📌"
                msg += f"   {emoji} {e['title']}\n"
        else:
            msg += f"📅 *Kal koi event nahi hai*\n"
        
        msg += f"\n💤 *Good night! InshAllah kal phir se shuru karenge!*"
    else:
        return
    
    if msg:
        msg += f"\n\n_/briefing - Detailed summary_"
        
        for chat_id in chat_ids:
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                log.info(f"Daily summary sent to {chat_id} at {current_time}")
            except Exception as e:
                log.error(f"Failed to send daily summary to {chat_id}: {e}")


# ════════════════════════════════════════════════════
# PROACTIVE FOLLOW-UP JOB
# ════════════════════════════════════════════════════

async def proactive_followup_job(context: ContextTypes.DEFAULT_TYPE):
    """Check for pending tasks older than 2 days and send gentle reminders"""
    chat_ids = set()
    for r in reminders.get_all():
        if r.get("chat_id"):
            try:
                chat_ids.add(int(r["chat_id"]))
            except:
                pass
    
    if not chat_ids:
        return
    
    now = now_ist()
    
    for chat_id in chat_ids:
        try:
            old_tasks = []
            for t in tasks.pending():
                created = t.get("created", t.get("date", ""))
                if created:
                    try:
                        created_date = datetime.strptime(created[:10], "%Y-%m-%d").date()
                        days_old = (now.date() - created_date).days
                        if days_old >= 2:
                            old_tasks.append((t, days_old))
                    except:
                        pass
            
            if old_tasks:
                msg = f"🤔 *Assalamualaikum! Kuch purane tasks yaad dila raha hoon:*\n\n"
                for t, days in old_tasks[:3]:
                    msg += f"📋 #{t['id']} *{t['title'][:40]}*\n   ⚠️ {days} din se pending hai!\n"
                msg += f"\n_InshAllah aaj kar loge? /done id se complete karo_"
                
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                log.info(f"Proactive followup sent to {chat_id}: {len(old_tasks)} old tasks")
        except Exception as e:
            log.error(f"Proactive followup error for {chat_id}: {e}")


# ════════════════════════════════════════════════════
# WEEKLY REVIEW JOB
# ════════════════════════════════════════════════════

async def weekly_review_job(context: ContextTypes.DEFAULT_TYPE):
    """Send comprehensive weekly review every Sunday at 9 PM"""
    now = now_ist()
    if now.weekday() != 6:  # Sunday only
        return
    
    chat_ids = set()
    for r in reminders.get_all():
        if r.get("chat_id"):
            try:
                chat_ids.add(int(r["chat_id"]))
            except:
                pass
    
    if not chat_ids:
        return
    
    week_start = now.date() - timedelta(days=7)
    week_start_str = week_start.strftime("%Y-%m-%d")
    
    completed_this_week = 0
    for t in tasks.all_tasks():
        done_date = t.get("done_date", "")
        if done_date and done_date >= week_start_str:
            completed_this_week += 1
    
    habits_this_week = 0
    for h in habits.all():
        if h.get("last_done"):
            try:
                last_date = datetime.strptime(h["last_done"][:10], "%Y-%m-%d").date()
                if last_date >= week_start:
                    habits_this_week += 1
            except:
                pass
    
    weekly_expense = 0
    for e in _get_expenses_list():
        try:
            exp_date = str(e.get("date", ""))[:10]
            if exp_date >= week_start_str:
                weekly_expense += float(e.get("amount", 0))
        except:
            pass
    
    diary_entries = 0
    all_diary = diary.get_all_entries()
    for date_key, entries in all_diary.items():
        if date_key >= week_start_str:
            diary_entries += len(entries)
    
    msg = f"📊 *Assalamualaikum! Weekly Review* 📊\n\n"
    msg += f"📅 *{week_start.strftime('%d %b')} — {now.strftime('%d %b %Y')}*\n\n"
    msg += f"✅ *Tasks Complete:* {completed_this_week}\n"
    msg += f"🏃 *Habits Logged:* {habits_this_week}\n"
    msg += f"💸 *Total Kharcha:* Rs.{weekly_expense}\n"
    msg += f"📖 *Diary Entries:* {diary_entries}\n"
    msg += f"📋 *Abhi Pending Tasks:* {len(tasks.pending())}\n\n"
    msg += f"🌟 *MashAllah! Agla hafte aur acha hoga InshAllah!*"
    
    for chat_id in chat_ids:
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            log.info(f"Weekly review sent to {chat_id}")
        except Exception as e:
            log.error(f"Weekly review error for {chat_id}: {e}")


# ════════════════════════════════════════════════════
# EXPENSE INSIGHT JOB
# ════════════════════════════════════════════════════

async def expense_insight_job(context: ContextTypes.DEFAULT_TYPE):
    """Monitor weekly expenses and alert when budget threshold crossed"""
    now = now_ist()
    if now.weekday() not in [4, 5]:  # Friday, Saturday
        return
    
    chat_ids = set()
    for r in reminders.get_all():
        if r.get("chat_id"):
            try:
                chat_ids.add(int(r["chat_id"]))
            except:
                pass
    
    if not chat_ids:
        return
    
    week_start = (now.date() - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    
    weekly_expense = 0
    for e in _get_expenses_list():
        try:
            exp_date = str(e.get("date", ""))[:10]
            if exp_date >= week_start:
                weekly_expense += float(e.get("amount", 0))
        except:
            pass
    
    if weekly_expense >= WEEKLY_BUDGET_THRESHOLD:
        msg = f"💰 *Bhai, budget alert!*\n\n"
        msg += f"Is hafte Rs.{int(weekly_expense)} kharcha ho gaya hai.\n"
        msg += f"(Budget: Rs.{WEEKLY_BUDGET_THRESHOLD})\n"
        msg += f"⚠️ _Budget tight ho raha hai, dhyan rakhna!_"
        
        for chat_id in chat_ids:
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                log.info(f"Expense insight sent to {chat_id}: Rs.{weekly_expense}")
            except Exception as e:
                log.error(f"Expense insight error for {chat_id}: {e}")


# ════════════════════════════════════════════════════
# BASIC COMMANDS
# ════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Welcome message with current time"""
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
    """Complete help message with all commands"""
    await update.message.reply_text(
        "📖 *COMMANDS — Rk Bot v18.4*\n\n"
        "💬 *Quick Commands (One-line):*\n"
        "• `done 3` — Task #3 complete karo\n"
        "• `add chai 20` — Expense add karo\n"
        "• `r 10m medicine` — Reminder set karo\n\n"
        "💬 *Seedha bolo (natural Hinglish):*\n"
        "• `30 min mein chai yaad dilana`\n"
        "• `chai pe 50 rupees laga`\n"
        "• `diary mein likho aaj ka din acha tha`\n"
        "• `gym habit ho gayi`\n"
        "• `simran ki birthday 9 sep 2000 hai`\n"
        "• `bill add netflix 499 15`\n"
        "• `karcha 200 petrol`\n"
        "• `saare task dikhao / task list`\n"
        "• `diary dikhao / show diary`\n"
        "• `purani diary dikhao / saari diary dikhao`\n"
        "• `kaam karna hai doctor appointment`\n"
        "• `memory mein save karo...`\n\n"
        "✅ *Tasks:*\n"
        "/task Naam — Task add karo\n"
        "/done id — Task complete karo\n"
        "/deltask id — Task delete karo\n\n"
        "🏃 *Habits:*\n"
        "/habit Naam — Habit add karo\n"
        "/hdone id — Habit log karo\n\n"
        "⏰ *Reminders:*\n"
        "/remind 30m Chai — Reminder set karo\n"
        "/delremind id — Reminder delete karo\n"
        "/snooze5 id | /snooze10 id | /snooze30 id | /snooze60 id\n"
        "/smartremind HIGH 5m Doctor — Smart reminder with priority\n"
        "/smartlist — List smart reminders\n"
        "/smartcomplete id — Complete smart reminder\n\n"
        "📖 *Diary (No Password):*\n"
        "/diary — Aaj ki entries dekho\n"
        "/diary write — Naya entry likho\n"
        "/diary week — Is hafte ki entries\n"
        "/diary all — Sab entries\n"
        "/diaryall — Sab entries (shortcut)\n"
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
        "/memory health — Health memories\n"
        "/memory search word — Search memories\n"
        "/memory clear — Delete all memories\n\n"
        "🎙️ *Voice Notes:*\n"
        "Voice message bhejo — Main transcribe karunga!\n"
        "/voicenotes — Recent voice notes dekho\n\n"
        "📊 *Special:*\n"
        "/today — Aaj ka pura progress\n"
        "/weekly — Is hafte ka review\n"
        "/briefing — Daily summary\n"
        "/status — System status\n"
        "/checksync — GitHub & Sheets check",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive bot status"""
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
        f"💸 Expenses: {len(_get_expenses_list())}\n"
        f"🏃 Habits: {len(habits.all())}\n"
        f"⏰ Reminders: {len(reminders.get_all())}\n"
        f"📅 Calendar: {len(all_events)} events\n"
        f"💳 Bills: {len(bills.all_active())} active\n"
        f"💧 Water: {water.today_total()}/{water.goal()}ml today\n"
        f"💰 Budget: Rs.{WEEKLY_BUDGET_THRESHOLD}/week",
        parse_mode="Markdown"
    )

async def cmd_checksync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show sync status with GitHub and Google Sheets"""
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
        try:
            sheet_url = f"https://docs.google.com/spreadsheets/d/{sheets_backup._book.id}"
        except:
            pass
    await update.message.reply_text(
        f"🔄 *SYNC STATUS*\n\n"
        f"🐙 GitHub: {github_status}\n"
        f"📊 Google Sheets: {sheets_status}\n"
        f"🕐 Last Git Commit: {last_sync}\n\n"
        f"Alhamdulillah, sab data safe hai! 🔒\n\n"
        f"🔗 Google Sheet:\n{sheet_url}",
        parse_mode="Markdown"
    )


# ════════════════════════════════════════════════════
# SPECIAL COMMANDS (/today, /weekly)
# ════════════════════════════════════════════════════

async def cmd_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    #"""Show today's complete progress - 'Kya kiya aaj?'"""
    now = now_ist()
    today_str_val = get_today_str()
    
    done_today = []
    for t in tasks.all_tasks():
        if t.get("done") and t.get("done_date") == today_str_val:
            done_today.append(t)
    
    hd, hp = habits.today_status()
    today_exp = expenses.today_total()
    today_w = water.today_total()
    today_diary = diary.get(today_str_val)
    
    msg = f"📊 *Kya Kiya Aaj? — {now.strftime('%d %b %Y')}* 📊\n\n"
    msg += f"✅ *Tasks Complete:* {len(done_today)}\n"
    if done_today:
        for t in done_today[:5]:
            msg += f"   ✅ #{t['id']} {t['title'][:40]}\n"
    else:
        msg += f"   ❌ Koi task complete nahi hua\n"
    
    msg += f"\n🏃 *Habits:* {len(hd)}/{len(hd)+len(hp)} done\n"
    if hd:
        for h in hd[:3]:
            msg += f"   🔥 {h['name']} (streak: {h.get('streak', 0)})\n"
    if hp:
        msg += f"   ⬜ Pending: {', '.join(h['name'] for h in hp[:3])}\n"
    
    msg += f"\n💸 *Kharcha:* Rs.{today_exp}\n"
    msg += f"💧 *Paani:* {today_w}ml/{water.goal()}ml\n"
    msg += f"📖 *Diary Entries:* {len(today_diary)}\n"
    msg += f"📋 *Pending Tasks:* {len(tasks.pending())}\n\n"
    msg += f"🌟 *_Alhamdulillah! Keep going!_*"
    
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_weekly(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show this week's comprehensive review"""
    now = now_ist()
    week_start = now.date() - timedelta(days=now.weekday())
    week_start_str = week_start.strftime("%Y-%m-%d")
    
    completed_this_week = 0
    for t in tasks.all_tasks():
        done_date = t.get("done_date", "")
        if done_date and done_date >= week_start_str:
            completed_this_week += 1
    
    habits_this_week = 0
    for h in habits.all():
        if h.get("last_done"):
            try:
                last_date = datetime.strptime(h["last_done"][:10], "%Y-%m-%d").date()
                if last_date >= week_start:
                    habits_this_week += 1
            except:
                pass
    
    weekly_expense = 0
    for e in _get_expenses_list():
        try:
            exp_date = str(e.get("date", ""))[:10]
            if exp_date >= week_start_str:
                weekly_expense += float(e.get("amount", 0))
        except:
            pass
    
    diary_entries = 0
    all_diary = diary.get_all_entries()
    for date_key, entries in all_diary.items():
        if date_key >= week_start_str:
            diary_entries += len(entries)
    
    msg = f"📊 *Weekly Review — {week_start.strftime('%d %b')} to {now.strftime('%d %b %Y')}* 📊\n\n"
    msg += f"✅ Tasks Complete: {completed_this_week}\n"
    msg += f"🏃 Habits Logged: {habits_this_week}\n"
    msg += f"💸 Total Kharcha: Rs.{weekly_expense}\n"
    msg += f"📖 Diary Entries: {diary_entries}\n"
    msg += f"📋 Pending Tasks: {len(tasks.pending())}\n\n"
    msg += f"🌟 *MashAllah!*"
    
    await update.message.reply_text(msg, parse_mode="Markdown")


# ════════════════════════════════════════════════════
# TASK COMMANDS
# ════════════════════════════════════════════════════

async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Add or view tasks"""
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
    """Mark task as complete"""
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
    """Delete a task"""
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


# ════════════════════════════════════════════════════
# HABIT COMMANDS
# ════════════════════════════════════════════════════

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Add or view habits"""
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
    """Log a habit as done"""
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


# ════════════════════════════════════════════════════
# EXPENSE & WATER COMMANDS
# ════════════════════════════════════════════════════

async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Add or view expenses"""
    if len(ctx.args) < 2:
        today_list = expenses.get_by_date(get_today_str())
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
    """Log water intake with visual progress bar"""
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


# ════════════════════════════════════════════════════
# REMINDER COMMANDS
# ════════════════════════════════════════════════════

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Set a reminder with natural time parsing"""
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
    """Delete a reminder"""
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
    """Snooze a reminder"""
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


# ════════════════════════════════════════════════════
# SMART REMINDER INTELLIGENCE
# ════════════════════════════════════════════════════

SMART_PRIORITY_CONFIG = {
    "HIGH": {"repeat_interval": 5, "max_repeats": 12, "emoji": "🔴", "prefix": "🔴 *URGENT!* "},
    "MEDIUM": {"repeat_interval": 15, "max_repeats": 8, "emoji": "🟠", "prefix": "🟠 *Reminder!* "},
    "LOW": {"repeat_interval": 30, "max_repeats": 4, "emoji": "🔵", "prefix": "🔵 "},
}

def _get_next_smart_id():
    """Get next unique ID for smart reminder"""
    from secure_data_manager import reminders
    reminders.store.data["counter"] = reminders.store.data.get("counter", 0) + 1
    return reminders.store.data["counter"]

def _add_smart_reminder(chat_id: int, text: str, due_timestamp: str, priority: str = "MEDIUM", repeat_until_done: bool = False):
    """Add a smart reminder with priority and repeat logic"""
    from secure_data_manager import reminders, sheets_backup
    
    config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
    
    smart_reminder = {
        "id": _get_next_smart_id(),
        "chat_id": chat_id,
        "text": text,
        "due": due_timestamp,
        "repeat": "smart",
        "priority": priority,
        "repeat_until_done": repeat_until_done,
        "repeat_interval": config["repeat_interval"],
        "max_repeats": config["max_repeats"],
        "current_repeat": 0,
        "triggered": False,
        "acknowledged": False,
        "created_at": now_ist().strftime("%Y-%m-%d %H:%M:%S"),
        "last_fired": "",
        "last_fired_minute": "",
        "is_smart": True
    }
    
    reminders.store.data["list"].append(smart_reminder)
    reminders.store.save()
    
    try:
        row = [
            smart_reminder.get("id", ""),
            smart_reminder.get("due", ""),
            smart_reminder.get("text", ""),
            f"Smart-{priority}",
            "Active",
            smart_reminder.get("created_at", ""),
            smart_reminder.get("chat_id", ""),
            "",
            "False",
            f"Repeat:{config['repeat_interval']}min"
        ]
        sheets_backup._append("Reminders", row)
    except Exception as e:
        log.debug(f"Sheet sync error: {e}")
    
    return smart_reminder

def _process_smart_followup(reminder):
    """Create follow-up reminder for smart reminder chain"""
    from secure_data_manager import reminders, sheets_backup
    
    if reminder.get("acknowledged", False):
        return None
    
    priority = reminder.get("priority", "MEDIUM")
    config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
    current_repeat = reminder.get("current_repeat", 0)
    max_repeats = reminder.get("max_repeats", config["max_repeats"])
    repeat_until_done = reminder.get("repeat_until_done", False)
    
    if not repeat_until_done and current_repeat >= max_repeats:
        log.info(f"Smart reminder #{reminder['id']} reached max repeats")
        return None
    
    next_interval = reminder.get("repeat_interval", config["repeat_interval"])
    next_due = now_ist() + timedelta(minutes=next_interval)
    next_timestamp = next_due.strftime("%Y-%m-%d %H:%M:%S")
    
    followup_text = f"🔁 {reminder['text']}"
    if current_repeat >= 1:
        followup_text = f"⚠️ Reminder #{reminder['id']} (Attempt {current_repeat + 1}/{max_repeats}): {reminder['text']}"
    
    new_id = _get_next_smart_id()
    followup = {
        "id": new_id,
        "chat_id": reminder["chat_id"],
        "text": followup_text,
        "due": next_timestamp,
        "repeat": "smart_followup",
        "priority": priority,
        "repeat_until_done": repeat_until_done,
        "repeat_interval": next_interval,
        "max_repeats": max_repeats,
        "current_repeat": current_repeat + 1,
        "triggered": False,
        "acknowledged": False,
        "created_at": now_ist().strftime("%Y-%m-%d %H:%M:%S"),
        "parent_id": reminder.get("parent_id", reminder["id"]),
        "last_fired_minute": "",
        "is_smart": True
    }
    
    reminders.store.data["list"].append(followup)
    reminders.store.save()
    
    try:
        row = [
            followup.get("id", ""),
            followup.get("due", ""),
            followup.get("text", ""),
            f"SmartFollowup-{priority}",
            "Active",
            followup.get("created_at", ""),
            followup.get("chat_id", ""),
            "",
            "False",
            f"Followup of #{reminder['id']}"
        ]
        sheets_backup._append("Reminders", row)
    except Exception as e:
        log.debug(f"Sheet sync error: {e}")
    
    log.info(f"🔄 Smart follow-up #{new_id} scheduled for {next_timestamp}")
    return followup

def _find_root_parent(reminder_id, reminders_store):
    """Recursively find the root parent of a smart reminder chain"""
    if not reminders_store or not hasattr(reminders_store, 'data'):
        return reminder_id
    
    data = reminders_store.data
    if not data or "list" not in data:
        return reminder_id
    
    visited = set()
    current_id = reminder_id
    max_iterations = 50
    
    for _ in range(max_iterations):
        if current_id in visited:
            break
        visited.add(current_id)
        found = False
        for r in data.get("list", []):
            if r and r.get("id") == current_id:
                parent = r.get("parent_id")
                if parent and parent != current_id and parent is not None:
                    current_id = parent
                    found = True
                    break
        if not found:
            break
    
    return current_id

def _acknowledge_smart_chain(reminder_id: int):
    """Acknowledge entire smart reminder chain from root"""
    from secure_data_manager import reminders
    
    root_id = _find_root_parent(reminder_id, reminders)
    
    count = 0
    for r in reminders.store.data.get("list", []):
        if not r:
            continue
        r_id = r.get("id")
        r_parent = r.get("parent_id")
        
        if r_id == root_id or (r_parent and r_parent == root_id) or r_id == reminder_id:
            if not r.get("acknowledged", False):
                r["acknowledged"] = True
                r["acknowledged_at"] = now_ist().strftime("%Y-%m-%d %H:%M:%S")
                count += 1
    
    if count > 0:
        reminders.store.save()
        log.info(f"✅ Acknowledged {count} smart reminders (root: {root_id})")
    
    return count


async def cmd_smart_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Smart reminder with priority and repeat options"""
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "📌 *Smart Reminder Help*\n\n"
            "*Priority Levels:*\n"
            "🔴 `HIGH` - Urgent (repeats every 5 min, max 12 times)\n"
            "🟠 `MEDIUM` - Normal (repeats every 15 min, max 8 times)\n"
            "🔵 `LOW` - Low priority (repeats every 30 min, max 4 times)\n\n"
            "*Usage:*\n"
            "`/smartremind HIGH 5m Doctor appointment`\n"
            "`/smartremind MEDIUM repeat 30m Take medicine`\n"
            "`/smartremind LOW tomorrow 9am Meeting`\n\n"
            "*Commands:*\n"
            "/smartlist - List smart reminders\n"
            "/smartcomplete id - Mark as complete",
            parse_mode="Markdown"
        )
        return
    
    args = list(ctx.args)
    now = now_ist()
    
    priority = "MEDIUM"
    if args and args[0].upper() in ["HIGH", "MEDIUM", "LOW"]:
        priority = args[0].upper()
        args = args[1:]
    
    repeat_until_done = False
    if args and args[0].lower() in ["repeat", "r", "until"]:
        repeat_until_done = True
        args = args[1:]
    
    if len(args) < 2:
        await update.message.reply_text("❌ Please specify time and message!\nExample: `/smartremind HIGH 5m Doctor appointment`", parse_mode="Markdown")
        return
    
    time_arg = args[0].lower()
    text = " ".join(args[1:])
    
    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        mins = int(time_arg[:-1])
        remind_dt = now + timedelta(minutes=mins)
        due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
    elif time_arg.endswith("h") and time_arg[:-1].isdigit():
        hours = int(time_arg[:-1])
        remind_dt = now + timedelta(hours=hours)
        due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
    elif ":" in time_arg:
        parts = time_arg.split(":")
        remind_dt = datetime(now.year, now.month, now.day, int(parts[0]), int(parts[1]))
        if remind_dt < now:
            remind_dt += timedelta(days=1)
        due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        await update.message.reply_text("❌ Invalid time format!\nExamples: `5m`, `1h`, `15:30`", parse_mode="Markdown")
        return
    
    config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
    r = _add_smart_reminder(
        chat_id=update.effective_chat.id,
        text=text,
        due_timestamp=due_timestamp,
        priority=priority,
        repeat_until_done=repeat_until_done
    )
    
    remind_dt = datetime.strptime(due_timestamp, "%Y-%m-%d %H:%M:%S")
    date_display = remind_dt.strftime("%d %b %Y")
    time_display = remind_dt.strftime("%I:%M %p")
    
    repeat_info = " (will repeat until completed)" if repeat_until_done else f" (max {config['max_repeats']} times)"
    
    _log_action(update.effective_user.first_name or "User", "smart_reminder_set", f"#{r['id']} [{priority}]: {text}")
    await update.message.reply_text(
        f"{config['emoji']} *Smart Reminder Set!* {config['emoji']}\n\n"
        f"🕐 *{time_display}* — 📅 *{date_display}*\n"
        f"📝 {text}\n"
        f"🎯 Priority: *{priority}*{repeat_info}\n"
        f"⏰ Repeat every: *{config['repeat_interval']} minutes*\n"
        f"📌 ID #{r['id']}\n\n"
        f"_/smartcomplete {r['id']} - Mark as complete_",
        parse_mode="Markdown"
    )


async def cmd_smart_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """List all active smart reminders"""
    from secure_data_manager import reminders
    
    active = []
    for r in reminders.get_all():
        if r.get("is_smart") and not r.get("acknowledged", False):
            if r.get("chat_id") == update.effective_chat.id:
                active.append(r)
    
    if not active:
        await update.message.reply_text(
            "📭 *No active smart reminders*\n\n"
            "Create one: `/smartremind HIGH 5m Doctor appointment`",
            parse_mode="Markdown"
        )
        return
    
    lines = ["📌 *Smart Reminders:*\n"]
    
    for r in active[:15]:
        due = r.get("due", "")
        try:
            dt = datetime.strptime(due, "%Y-%m-%d %H:%M:%S")
            due_display = dt.strftime("%d %b, %I:%M %p")
        except:
            due_display = due
        
        priority = r.get("priority", "MEDIUM")
        config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
        emoji = config["emoji"]
        current = r.get("current_repeat", 0)
        max_r = r.get("max_repeats", config["max_repeats"])
        
        lines.append(f"{emoji} #{r['id']} *{r['text'][:40]}*\n   🕐 {due_display} | 🔁 {current}/{max_r}")
    
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_smart_complete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mark a smart reminder as complete (stops all repeats)"""
    if not ctx.args:
        await update.message.reply_text("/smartcomplete reminder_id", parse_mode="Markdown")
        return
    
    try:
        rid = int(ctx.args[0])
        count = _acknowledge_smart_chain(rid)
        
        if count > 0:
            _log_action(update.effective_user.first_name or "User", "smart_reminder_complete", f"#{rid}: {count} stopped")
            await update.message.reply_text(
                f"✅ *Smart Reminder Completed!* 🎉\n\n"
                f"Stopped {count} reminder(s). Alhamdulillah!",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ Reminder #{rid} not found or already completed.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}", parse_mode="Markdown")


# ════════════════════════════════════════════════════
# DIARY COMMANDS (NO PASSWORD)
# ════════════════════════════════════════════════════

async def cmd_diary_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Diary command - NO PASSWORD REQUIRED"""
    args = ctx.args or []
    user_name = update.effective_user.first_name or "User"
    
    if not args:
        entries = diary.get(get_today_str())
        _log_action(user_name, "diary_view", f"Viewed today ({len(entries)} entries)")
        if not entries:
            await update.message.reply_text(
                "📖 *Aaj ki koi diary entry nahi hai.*\n\n"
                "Likhne ke liye: `/diary write`\n"
                "Ya direct bolo: `diary mein likho [text]`\n\n"
                "📚 *Purani diary dekhne ke liye:*\n"
                "• `/diary all` ya bolo `purani diary dikhao`\n"
                "• `/diary week` — is hafte ki",
                parse_mode="Markdown"
            )
        else:
            lines = []
            for idx, e in enumerate(entries, 1):
                lines.append(f"📌 *#{idx}* 🕐 *{e['time']}*\n{e['text']}")
            await update.message.reply_text(
                f"📖 *Aaj ki Diary ({get_today_str()}):*\n\n" + "\n\n".join(lines) +
                f"\n\n📚 _Purani entries: /diary all_",
                parse_mode="Markdown"
            )
        return ConversationHandler.END
    
    first = args[0].lower()
    
    if first == "write":
        pending_text = " ".join(args[1:]) if len(args) > 1 else ""
        if pending_text:
            diary.add(pending_text)
            _log_action(user_name, "diary_write", f"Entry saved")
            await update.message.reply_text(
                f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n"
                f"📊 Sheets mein bhi backup ho gaya!",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        else:
            ctx.user_data["diary_mode"] = "write"
            await update.message.reply_text(
                "📖 *Diary Entry Likho:*\n\n"
                "Apna text bhejo, main save kar dunga!\n"
                "*(/cancel se bahar aana)*",
                parse_mode="Markdown"
            )
            return DIARY_AWAIT_TEXT
    
    elif first == "week":
        all_entries = diary.get_all_entries()
        today_d = now_ist().date()
        week_entries = []
        for i in range(7):
            date_key = (today_d - timedelta(days=i)).strftime("%Y-%m-%d")
            for e in all_entries.get(date_key, []):
                week_entries.append(f"📌 *#{len(week_entries)+1}* 📅 *{date_key}* 🕐 {e.get('time','')}\n{e['text']}")
        
        _log_action(user_name, "diary_view", f"Viewed week ({len(week_entries)} entries)")
        if not week_entries:
            await update.message.reply_text("📖 *Is hafte koi diary entry nahi hai.*", parse_mode="Markdown")
        else:
            msg_text = "\n\n".join(week_entries[:15])
            if len(msg_text) > 4000:
                msg_text = msg_text[:3900] + "\n\n... (aur bhi entries hain)"
            await update.message.reply_text(f"📖 *Is hafte ki Diary (Last 7 days):*\n\n{msg_text}", parse_mode="Markdown")
        return ConversationHandler.END
    
    elif first == "all":
        all_entries = diary.get_all_entries()
        total_count = sum(len(v) for v in all_entries.values())
        dates = sorted(all_entries.keys(), reverse=True)
        
        preview = []
        for date_key in dates[:10]:
            for e in all_entries[date_key][:2]:
                      preview.append(f"📌 *#{len(preview)+1}* 📅 *{date_key}* 🕐 {e.get('time','')}\n{e['text'][:150]}")
        
        _log_action(user_name, "diary_view", f"Viewed all ({total_count} total entries)")
        
        msg_text = f"📖 *Total {total_count} Diary Entries*\n\n"
        msg_text += "*Latest Entries:*\n\n"
        msg_text += "\n\n".join(preview[:20])
        
        if total_count > 20:
            msg_text += f"\n\n... aur {total_count - 20} entries hain. /diary week recent dekho"
        
        await update.message.reply_text(msg_text[:4000], parse_mode="Markdown")
        return ConversationHandler.END
    
    else:
        text = " ".join(args)
        diary.add(text)
        _log_action(user_name, "diary_write", f"Entry saved")
        await update.message.reply_text(
            f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n"
            f"📊 Sheets mein bhi backup ho gaya!",
            parse_mode="Markdown"
        )
        return ConversationHandler.END


async def cmd_diaryall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Shortcut to show all diary entries"""
    await _send_diary_all(update, update.effective_user.first_name or "User")


async def diary_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle diary text input"""
    if not update.message:
        return ConversationHandler.END
    
    text = update.message.text.strip()
    diary.add(text)
    _log_action(update.effective_user.first_name or "User", "diary_write", f"Entry saved")
    
    await update.message.reply_text(
        f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n"
        f"📊 Sheets mein bhi backup ho gaya!",
        parse_mode="Markdown"
    )
    
    ctx.user_data.clear()
    return ConversationHandler.END


async def diary_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Cancel diary operation"""
    ctx.user_data.clear()
    await update.message.reply_text("❌ Diary operation cancelled.", parse_mode="Markdown")
    return ConversationHandler.END


async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Quick save to diary"""
    if not ctx.args:
        await update.message.reply_text(
            "📖 *Quick Diary Save*\n\n"
            "Usage: `/save Aaj ka din acha tha`\n\n"
            "Ya direct bolo: `diary mein likho [text]`",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    text = " ".join(ctx.args)
    diary.add(text)
    _log_action(update.effective_user.first_name or "User", "diary_write", f"Entry saved")
    await update.message.reply_text(
        f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n"
        f"📊 Sheets mein bhi backup ho gaya!",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def _send_diary_week(update_or_msg, user_name="User"):
    """Send this week's diary entries"""
    all_entries = diary.get_all_entries()
    today_d = now_ist().date()
    week_entries = []
    for i in range(7):
        date_key = (today_d - timedelta(days=i)).strftime("%Y-%m-%d")
        for e in all_entries.get(date_key, []):
              week_entries.append(f"📌 *#{len(week_entries)+1}* 📅 *{date_key}* 🕐 {e.get('time','')}\n{e['text']}")
    
    _log_action(user_name, "diary_view", f"Viewed week ({len(week_entries)} entries)")
    
    if not week_entries:
        msg = "📖 *Is hafte koi diary entry nahi hai.*"
    else:
        msg_text = "\n\n".join(week_entries[:15])
        if len(msg_text) > 4000:
            msg_text = msg_text[:3900] + "\n\n... (aur bhi entries hain)"
        msg = f"📖 *Is hafte ki Diary (Last 7 days):*\n\n{msg_text}"
    
    if hasattr(update_or_msg, 'message'):
        await update_or_msg.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update_or_msg.reply_text(msg, parse_mode="Markdown")


async def _send_diary_all(update_or_msg, user_name="User"):
    """Send ALL diary entries"""
    all_entries = diary.get_all_entries()
    total_count = sum(len(v) for v in all_entries.values())
    dates = sorted(all_entries.keys(), reverse=True)
    
    _log_action(user_name, "diary_view", f"Viewed all ({total_count} total entries)")
    
    if total_count == 0:
        msg = "📖 *Koi diary entry nahi hai.*"
    else:
        preview = []
        for date_key in dates[:10]:
            for e in all_entries[date_key][:2]:
                  preview.append(f"📌 *#{len(preview)+1}* 📅 *{date_key}* 🕐 {e.get('time','')}\n{e['text'][:200]}")
        
        msg_text = f"📖 *Total {total_count} Diary Entries*\n\n"
        msg_text += "*Latest Entries:*\n\n"
        msg_text += "\n\n".join(preview[:20])
        
        if total_count > 20:
            msg_text += f"\n\n_... aur {total_count - 20} entries hain._"
        msg = msg_text[:4000]
    
    if hasattr(update_or_msg, 'message'):
        await update_or_msg.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update_or_msg.reply_text(msg, parse_mode="Markdown")


async def _send_diary_today(update: Update):
    """Send today's diary entries"""
    today_str_val = get_today_str()
    entries = diary.get(today_str_val)
    if not entries:
        await update.message.reply_text(
            "📖 *Aaj ki koi diary entry nahi hai.*\n\n"
            "/diary write — Likhna shuru karo!\n"
            "Ya bolo: *diary mein likho [text]*\n\n"
            "📚 *Purani diary:* `/diary all` ya bolo `purani diary dikhao`",
            parse_mode="Markdown"
        )
    else:
            lines = "\n\n".join(f"📌 *#{i+1}* 🕐 {e['time']}\n{e['text']}" for i, e in enumerate(entries))
        await update.message.reply_text(
            f"📖 *Aaj ki Diary ({today_str_val}):*\n\n{lines}\n\n"
            f"📚 _Purani entries: /diary all_",
            parse_mode="Markdown"
        )


# ════════════════════════════════════════════════════
# CALENDAR COMMANDS
# ════════════════════════════════════════════════════

async def cmd_cal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show upcoming events"""
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
    """Show today's events"""
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
    await update.message.reply_text(f"📅 *Aaj ke Events ({get_today_str()}):*\n\n" + "\n\n".join(lines), parse_mode="Markdown")

async def cmd_calweek(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show this week's events"""
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
    """Add a calendar event or birthday"""
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
    """Delete a calendar event"""
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


# ════════════════════════════════════════════════════
# BILLS COMMANDS
# ════════════════════════════════════════════════════

async def cmd_bills(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show all active bills"""
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
    """Add a new bill"""
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
    """Mark a bill as paid"""
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
    """Delete a bill"""
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


# ════════════════════════════════════════════════════
# BRIEFING
# ════════════════════════════════════════════════════

async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show daily briefing with events and bills"""
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


# ════════════════════════════════════════════════════
# REMINDER JOB (with persistent deduplication)
# ════════════════════════════════════════════════════

FIRED_TRACKER_FILE = os.path.join(DATA_DIR, "fired_reminders.json")

def _load_fired_tracker():
    """Load persistent fired reminders tracker"""
    try:
        if os.path.exists(FIRED_TRACKER_FILE):
            with open(FIRED_TRACKER_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def _save_fired_tracker(tracker):
    """Save fired reminders tracker to disk"""
    try:
        with open(FIRED_TRACKER_FILE, 'w') as f:
            json.dump(tracker, f)
    except Exception as e:
        log.warning(f"Failed to save fired tracker: {e}")

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """Main reminder checker - runs every 60 seconds with deduplication"""
    now = now_ist()
    now_str_full = now.strftime("%Y-%m-%d %H:%M")
    now_hm = now.strftime("%H:%M")

    # Daily reset at midnight
    if now.hour == 0 and now.minute <= 1:
        reminders.reset_daily()
        fired = _load_fired_tracker()
        today = now.strftime("%Y-%m-%d")
        fired = {k: v for k, v in fired.items() if v.get("date") == today}
        _save_fired_tracker(fired)

    # 9 PM - Send event reminders for tomorrow
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

    # 9 AM - Bill Smart Alert (only 2 days before due & unpaid)
    if now_hm == "09:00":
        today_day = now.day
        due_soon_bills = []
        for b in bills.all_active():
            if not bills.is_paid_this_month(b["id"]):
                due = int(b.get("due_day", 0))
                if due > 0 and 0 <= (due - today_day) <= 2:
                    due_soon_bills.append(b)
        
        if due_soon_bills:
            chat_ids = {r.get("chat_id") for r in reminders.get_all() if r.get("chat_id")}
            for cid in chat_ids:
                try:
                    lines = "\n".join(f"  💳 {b['name']} — Rs.{b['amount']} (due {b['due_day']} tarikh)" for b in due_soon_bills)
                    await context.bot.send_message(
                        chat_id=int(cid),
                        text=f"⚠️ *Bill Due Soon! Dhyan rakhna!*\n\n{lines}\n\n/billpaid id — Paid mark karo",
                        parse_mode="Markdown"
                    )
                    _log_action("Bot", "bill_reminder_sent", f"Bills due: {', '.join(b['name'] for b in due_soon_bills)}")
                except Exception as ex:
                    log.error(f"Bills reminder failed: {ex}")

    # Check active reminders with persistent deduplication
    fired_tracker = _load_fired_tracker()
    today_key = now.strftime("%Y-%m-%d")
    
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
                # Deduplication check
                rid = str(r.get("id", ""))
                fire_key = f"{rid}_{due_min}"
                
                if fire_key in fired_tracker and fired_tracker[fire_key].get("fired"):
                    continue
                
                fired_tracker[fire_key] = {"fired": True, "date": today_key, "time": now_hm}
                _save_fired_tracker(fired_tracker)
                r["last_fired_minute"] = now_str_full
                    
                fire_count = r.get("fire_count", 0)
                suffix = f"\n⚠️ {fire_count + 1}vi baar baj raha hai — OK dabao!" if fire_count > 0 else ""
                
                try:
                    due_dt = datetime.strptime(reminder_due, "%Y-%m-%d %H:%M:%S")
                    due_time_display = due_dt.strftime("%I:%M %p")
                except:
                    due_time_display = reminder_due
                
                is_smart = r.get("is_smart", False)
                priority = r.get("priority", "MEDIUM")
                config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
                prefix = config["prefix"] if is_smart else ""
                
                alert = (f"{prefix}🚨 *ALARM!*\n{'━' * 20}\n⏰ *{due_time_display} BAJ GAYE!*\n{'━' * 20}\n\n"
                         f"🔔 *{r['text'].upper()}*\n{suffix}\n\n"
                         f"😴 Snooze: /snooze5 {r['id']} | /snooze10 {r['id']}\n"
                         f"🗑️ Delete: /delremind {r['id']}")
                
                if is_smart:
                    alert += f"\n✅ Complete: /smartcomplete {r['id']}"
                
                try:
                    await context.bot.send_message(
                        chat_id=int(r["chat_id"]), text=alert,
                        reply_markup=alarm_keyboard(r["id"]), parse_mode="Markdown"
                    )
                    reminders.mark_triggered(r["id"])
                    
                    if is_smart and not r.get("acknowledged", False):
                        _process_smart_followup(r)
                    
                    _log_action("Bot", "alarm_fired", f"Alarm #{r['id']} at {now_hm}: {r['text']}")
                except Exception as e:
                    log.error(f"Failed to send alarm: {e}")


# ════════════════════════════════════════════════════
# OK BUTTON HANDLER
# ════════════════════════════════════════════════════

async def handle_ok_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle alarm OK button press"""
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
            reminders.store.save()
            
            if target.get("is_smart", False):
                _acknowledge_smart_chain(rid)
            
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


# ════════════════════════════════════════════════════
# NATURAL LANGUAGE PARSER (COMPLETE)
# ════════════════════════════════════════════════════

def parse_user_message(user_msg: str):
    """Parse natural language Hinglish messages into actions"""
    lower = user_msg.lower().strip()
    
    # ── ONE-LINE QUICK ADD ──
    m = _re.match(r'^done\s+(\d+)$', lower)
    if m:
        return ("complete_task", {"hint": m.group(1)})
    
    m = _re.match(r'^add\s+(.+?)\s+(\d+(?:\.\d+)?)$', lower)
    if m:
        return ("expense", {"amount": float(m.group(2)), "desc": m.group(1).strip()})
    
    m = _re.match(r'^r\s+(\d+(?:m|min|h|hr)?)\s+(.+)$', lower)
    if m:
        time_arg = m.group(1)
        text = m.group(2).strip()
        
        def _quick_parse_time(t):
            now_t = now_ist()
            if t.endswith("m") or t.endswith("min"):
                mins = int(_re.sub(r'[^0-9]', '', t))
                return (now_t + timedelta(minutes=mins)).strftime("%Y-%m-%d %H:%M:%S")
            elif t.endswith("h") or t.endswith("hr"):
                hours = int(_re.sub(r'[^0-9]', '', t))
                return (now_t + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
            elif t.isdigit():
                return (now_t + timedelta(minutes=int(t))).strftime("%Y-%m-%d %H:%M:%S")
            return None
        
        due = _quick_parse_time(time_arg)
        if due:
            return ("remind", {"time": due, "text": text})
    
    # ── SMART REMINDER PATTERNS ──
    smart_match = _re.search(r'(urgent|jaldi|important|high|high priority|jaruri|जरूरी)\s*(?:reminder|remind|yaad dilao|yaad dila|bata dena)', lower)
    if smart_match:
        priority = "HIGH"
        time_match = _re.search(r'(\d+)\s*(?:min|minute|m|second|sec|hour|hr|ghanta)\s*(?:baad|mein|main|after)', lower)
        if time_match:
            value = int(time_match.group(1))
            unit = time_match.group(2) if len(time_match.groups()) > 1 else "min"
            if 'min' in unit or 'm' == unit:
                mins = value
            elif 'hour' in unit or 'hr' in unit or 'ghanta' in unit:
                mins = value * 60
            elif 'second' in unit or 'sec' in unit:
                mins = max(1, value // 60)
            else:
                mins = value
            remind_dt = now_ist() + timedelta(minutes=mins)
            due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
            
            text = user_msg
            for kw in ['urgent', 'jaldi', 'important', 'high priority', 'jaruri', 'reminder', 'remind', 'yaad dilao', 'yaad dila', 'bata dena']:
                text = _re.sub(r'\b' + _re.escape(kw) + r'\b', '', text, flags=_re.IGNORECASE)
            text = _re.sub(r'\d+\s*(?:min|minute|m|second|sec|hour|hr|ghanta)\s*(?:baad|mein|main|after)', '', text)
            text = text.strip()
            if not text:
                text = "Urgent Reminder"
            
            config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
            return ("smart_remind", {
                "priority": priority, 
                "text": text, 
                "due": due_timestamp,
                "repeat_until_done": False,
                "interval": config['repeat_interval']
            })
    
    # ── REPEATING REMINDER ──
    repeat_match = _re.search(r'(tak|until|jab tak|tab tak|repeat|bar bar|baar baar|lagatar|rehna)\s*(?:yaad dilate rehna|remind karte rehna|bata te rehna)', lower)
    if repeat_match:
        priority = "MEDIUM"
        repeat_until_done = True
        
        date_str, remaining = _parse_date_from_text(user_msg)
        time_str = _parse_time_from_text(remaining)
        
        now = now_ist()
        if date_str:
            due_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            due_date = now.date()
        
        if time_str:
            hour, minute = map(int, time_str.split(':'))
            remind_dt = datetime(due_date.year, due_date.month, due_date.day, hour, minute)
            if remind_dt < now:
                remind_dt += timedelta(days=1)
        else:
            remind_dt = now + timedelta(minutes=30)
        
        due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        text = user_msg
        for kw in ['yaad dilate rehna', 'remind karte rehna', 'bata te rehna', 'tak', 'until', 'jab tak', 'tab tak', 'repeat', 'bar bar', 'baar baar', 'lagatar', 'rehna']:
            text = _re.sub(r'\b' + _re.escape(kw) + r'\b', '', text, flags=_re.IGNORECASE)
        text = re.sub(r'\d+\s*(?:min|minute|m|second|sec|hour|hr|ghanta)\s*(?:baad|mein|main|after)?', '', text)
        text = text.strip()
        if not text:
            text = "Repeating Reminder"
        
        config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
        return ("smart_remind", {
            "priority": priority, 
            "text": text, 
            "due": due_timestamp,
            "repeat_until_done": repeat_until_done,
            "interval": config['repeat_interval']
        })
    
    # ── LOW PRIORITY REMINDER ──
    low_match = _re.search(r'(low|normal|simple|easy|basic|normal priority|simple reminder|normal reminder|aam|साधारण|low priority)', lower)
    if low_match and ('remind' in lower or 'reminder' in lower or 'yaad' in lower):
        priority = "LOW"
        
        time_match = _re.search(r'(\d+)\s*(?:min|minute|m|hour|hr|ghanta)\s*(?:baad|mein|main|after)', lower)
        if time_match:
            value = int(time_match.group(1))
            unit = time_match.group(2) if len(time_match.groups()) > 1 else "min"
            if 'hour' in unit or 'hr' in unit or 'ghanta' in unit:
                mins = value * 60
            else:
                mins = value
            remind_dt = now_ist() + timedelta(minutes=mins)
            due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            remind_dt = now_ist() + timedelta(minutes=30)
            due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        text = user_msg
        for kw in ['low', 'normal', 'simple', 'easy', 'basic', 'normal priority', 'simple reminder', 'normal reminder', 'aam', 'reminder', 'remind', 'yaad']:
            text = _re.sub(r'\b' + _re.escape(kw) + r'\b', '', text, flags=_re.IGNORECASE)
        text = re.sub(r'\d+\s*(?:min|minute|m|hour|hr|ghanta)\s*(?:baad|mein|main|after)?', '', text)
        text = text.strip()
        if not text:
            text = "Reminder"
        
        config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
        return ("smart_remind", {
            "priority": priority, 
            "text": text, 
            "due": due_timestamp,
            "repeat_until_done": False,
            "interval": config['repeat_interval']
        })
    
    # ── DEFAULT SMART REMINDER ──
    if ('remind' in lower or 'reminder' in lower or 'yaad dilana' in lower or 'yaad dila' in lower):
        time_match = _re.search(r'(\d+)\s*(?:min|minute|m|second|sec|hour|hr|ghanta)\s*(?:baad|mein|main|after)', lower)
        if time_match:
            priority = "MEDIUM"
            value = int(time_match.group(1))
            unit = time_match.group(2) if len(time_match.groups()) > 1 else "min"
            if 'hour' in unit or 'hr' in unit or 'ghanta' in unit:
                mins = value * 60
            else:
                mins = value
            remind_dt = now_ist() + timedelta(minutes=mins)
            due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
            
            text = user_msg
            for kw in ['reminder', 'remind', 'yaad dilana', 'yaad dila', 'bata dena']:
                text = _re.sub(r'\b' + _re.escape(kw) + r'\b', '', text, flags=_re.IGNORECASE)
            text = re.sub(r'\d+\s*(?:min|minute|m|second|sec|hour|hr|ghanta)\s*(?:baad|mein|main|after)?', '', text)
            text = text.strip()
            if not text:
                text = "Reminder"
            
            config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
            return ("smart_remind", {
                "priority": priority, 
                "text": text, 
                "due": due_timestamp,
                "repeat_until_done": False,
                "interval": config['repeat_interval']
            })
    
    # ── REGULAR REMINDER KEYWORDS ──
    reminder_keywords = ['remind', 'reminder', 'reminder add', 'remind me', 
                         'yaad dilana', 'bata dena', 'alarm', 'remindme']
    
    if any(kw in lower for kw in reminder_keywords):
        date_str, remaining = _parse_date_from_text(user_msg)
        time_str = _parse_time_from_text(remaining)
        
        now = now_ist()
        
        if date_str:
            due_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            due_date = now.date()
        
        if time_str:
            hour, minute = map(int, time_str.split(':'))
            remind_dt = datetime(due_date.year, due_date.month, due_date.day, hour, minute)
            if remind_dt < now and due_date == now.date():
                remind_dt += timedelta(days=1)
        else:
            if 'min' in lower or 'minute' in lower or 'baad' in lower:
                num_match = _re.search(r'(\d+)', lower)
                if num_match:
                    mins = int(num_match.group(1))
                    remind_dt = now + timedelta(minutes=mins)
                else:
                    remind_dt = now + timedelta(minutes=5)
            else:
                remind_dt = now + timedelta(minutes=5)
        
        due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        text = user_msg
        remove_words = reminder_keywords + ['kal', 'kl', 'aaj', 'parso', 'subha', 'subah', 
                    'shaam', 'raat', 'baje', 'bajay', 'am', 'pm', 'mein', 'me', 'ko', 'pe']
        for rw in remove_words:
            text = _re.sub(r'\b' + _re.escape(rw) + r'\b', '', text, flags=_re.IGNORECASE)
        text = _re.sub(r'\d{1,2}[:]\d{2}', '', text)
        text = _re.sub(r'\d{1,2}\s*(?:baje|bajay|am|pm)', '', text)
        text = text.strip()
        if not text or len(text) < 2:
            text = "Reminder"
        
        return ("remind", {"time": due_timestamp, "text": text})
    
    # ── MEMORY TRIGGERS ──
    memory_triggers = ["yaad rakhna", "memory mein save", "memory me save", 
                       "note karlo", "remember", "dimaag mein rakh"]
    if any(t in lower for t in memory_triggers):
        text = user_msg
        for kw in memory_triggers + ["please", "plz", "zara", "kr", "karo"]:
            text = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", text, flags=_re.IGNORECASE)
        text = " ".join(text.split()).strip()
        if text:
            return ("memory_save", {"text": text})
        return ("memory_save", {"text": user_msg})

    # ── SHOW COMMANDS ──
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
        "purani diary", "poorani diary", "saari diary", "sari diary",
        "all diary", "poorani dairy", "purani dairy", "saari dairy",
        "sari dairy", "all dairy", "diary all", "dairy all",
        "sab diary", "sab dairy", "poori diary", "puraani diary",
    ]):
        return ("show_all_diary", {})

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

    # ── REMIND WORDS WITH TIME PARSING ──
    remind_words = [
        "remind", "reminder", "alarm", "yaad dilana", "bata dena",
        "yaad dila", "yaad dila do", "yaad kara", "add reminder",
        "set reminder", "set alarm", "yaad dilao", "yaad krao",
    ]
    if any(w in lower for w in remind_words):
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

    # ── HABIT DONE ──
    if any(p in lower for p in [
        "habit ho gayi", "habit ho gaya", "habit complete", "habit kar li",
        "habit kar liya", "habit done", "gym ho gaya", "gym kar liya",
        "exercise ho gayi", "exercise kar li", "walk ho gayi", "walk kar li",
        "reading ho gayi", "meditation ho gayi", "yoga ho gayi",
    ]):
        m = _re.search(r'#?(\d+)', lower)
        return ("habit_done", {"keyword": m.group(1) if m else lower[:40]})

    # ── ADD HABIT ──
    if any(p in lower for p in [
        "habit add", "add habit", "naya habit", "habit lagao", "habit bana",
        "habit start", "new habit", "habit banana",
    ]):
        name = user_msg
        for kw in ["habit", "add", "naya", "new", "karo", "kr", "lagao", "bana", "start", "banana"]:
            name = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", name, flags=_re.IGNORECASE)
        return ("add_habit", {"name": " ".join(name.split()).strip()[:50] or "Habit"})

    # ── CALENDAR / BIRTHDAY ──
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

    # ── BILL NATURAL LANGUAGE ──
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

    # ── DIARY ADD ──
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

    # ── WATER ──
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

    # ── EXPENSE ──
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

    # ── TASK DONE ──
    if any(p in lower for p in [
        "task done", "kaam ho gaya", "kaam kar liya", "complete kar liya",
        "task complete", "ho gaya task", "kar liya task",
    ]):
        m = _re.search(r'#?(\d+)', lower)
        return ("complete_task", {"hint": m.group(1) if m else lower[:30]})

    # ── ADD TASK ──
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

    # ── MEMORY SAVE ──
    if any(t in lower for t in [
        "memory mein", "memory me", "yaad rakhna", "note karo", "note kr",
        "save karo", "save kr", "remember karo",
    ]):
        text = user_msg
        for kw in ["memory","mein","me","save","karo","kr","note","yaad","rakhna","remember"]:
            text = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", text, flags=_re.IGNORECASE)
        return ("memory_save", {"text": " ".join(text.split()).strip() or user_msg})

    return ("chat", {"text": user_msg})


# ════════════════════════════════════════════════════
# SHOW HELPERS
# ════════════════════════════════════════════════════

async def _send_reminder_list(update: Update):
    """Send active reminders list"""
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
            if r.get("is_smart", False):
                priority = r.get("priority", "MEDIUM")
                config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
                lines.append(f"  {config['emoji']} #{r['id']} {due_display} — {r['text']} (Smart-{priority})")
            else:
                lines.append(f"  ⏰ #{r['id']} {due_display} — {r['text']}")
            
        await update.message.reply_text(
            f"⏰ *Active Reminders ({len(active)}):*\n\n" + "\n".join(lines) + "\n\n"
            f"/delremind id — Delete karo\n/snooze5 id — Snooze\n/remind 30m Chai — Naya set karo\n"
            f"/smartlist — Smart reminders",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "⏰ Koi active reminder nahi hai.\n\n/remind 30m Chai — Naya set karo\n/smartremind HIGH 5m — Smart reminder",
            parse_mode="Markdown"
        )

async def _send_task_list(update: Update):
    """Send pending tasks list"""
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
    """Send habits list"""
    all_h = habits.all()
    if all_h:
        hd, _ = habits.today_status()
        done_ids = [h["id"] for h in hd]
        lines = "\n".join(
            f"  {'✅' if h['id'] in done_ids else '⬜'} #{h['id']} {h['name']} 🔥{h.get('streak',0)}"
            for h in all_h
        )
        await update.message.reply_text(f"🏃 *Aaj ke Habits:*\n\n{lines}\n\n/hdone id — Log karo", parse_mode="Markdown")
    else:
        await update.message.reply_text("🏃 Koi habit nahi.\n\n/habit Naam — Naya add karo", parse_mode="Markdown")

async def _send_calendar_list(update: Update):
    """Send upcoming events"""
    events = calendar.upcoming(days=30)
    if events:
        lines = [f"{'🎂' if e.get('type')=='birthday' else '📅'} *{e['date']}* — #{e['id']}\n   {e['title']}" for e in events[:10]]
        await update.message.reply_text(f"📅 *Upcoming Events ({len(events)}):*\n\n" + "\n\n".join(lines), parse_mode="Markdown")
    else:
        await update.message.reply_text("📅 Koi upcoming event nahi.\n\n/caladd — Add karo", parse_mode="Markdown")

async def _send_memory_list(update: Update):
    """Send saved memories"""
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


# ════════════════════════════════════════════════════
# MESSAGE HANDLER
# ════════════════════════════════════════════════════

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Main message handler - routes natural language to appropriate actions"""
    if not update.message or not update.message.text:
        return
    
    user_msg = update.message.text.strip()
    user_name = update.effective_user.first_name or "User"
    chat_id = update.effective_chat.id
    
    if user_msg.startswith("/"):
        return
    
    # Add to context for smart replies
    add_to_context(chat_id, "user", user_msg)

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

    elif action_type == "show_all_diary":
        await _send_diary_all(update, user_name)
        _log_action(user_name, "show_all_diary", user_msg[:60])

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
    
    elif action_type == "smart_remind":
        priority = params.get("priority", "MEDIUM")
        text = params.get("text", "Reminder")
        due_timestamp = params.get("due", "")
        repeat_until_done = params.get("repeat_until_done", False)
        interval = params.get("interval", 15)
        
        r = _add_smart_reminder(
            chat_id=update.effective_chat.id,
            text=text,
            due_timestamp=due_timestamp,
            priority=priority,
            repeat_until_done=repeat_until_done
        )
        
        config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
        
        try:
            remind_dt = datetime.strptime(due_timestamp, "%Y-%m-%d %H:%M:%S")
            date_display = remind_dt.strftime("%d %b %Y")
            time_display = remind_dt.strftime("%I:%M %p")
        except:
            date_display = "today"
            time_display = due_timestamp
        
        repeat_info = " (will repeat until completed)" if repeat_until_done else f" (max {config['max_repeats']} times, every {interval} min)"
        
        _log_action(user_name, "smart_reminder_set", f"#{r['id']} [{priority}]: {text}")
        await update.message.reply_text(
            f"{config['emoji']} *Smart Reminder Set!* {config['emoji']}\n\n"
            f"🕐 *{time_display}* — 📅 *{date_display}*\n"
            f"📝 {text}\n"
            f"🎯 Priority: *{priority}*{repeat_info}\n"
            f"⏰ Will remind you every *{interval} minutes* until done\n"
            f"📌 ID #{r['id']}\n\n"
            f"_To stop: /smartcomplete {r['id']}_",
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
        text = params.get("text", "")
        diary.add(text)
        _log_action(user_name, "diary_write", f"Entry saved")
        await update.message.reply_text(
            f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n"
            f"📊 Sheets mein bhi backup ho gaya!",
            parse_mode="Markdown"
        )

    elif action_type == "add_habit":
        h = habits.add(params.get("name", ""))
        _log_action(user_name, "habit_add", f"#{h['id']}: {h['name']}")
        await update.message.reply_text(
            f"🏃 *Habit Add Ho Gaya!*\n\n#{h['id']} {h['name']}\n\nInshAllah roz karoge! 💪",
            parse_mode="Markdown"
        )

    elif action_type == "add_calendar":
        title   = params.get("title", "Event")
        ev_date = params.get("date", get_today_str())
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

    elif action_type == "habit_done":
        try:
            keyword = params.get("keyword", "")
            if keyword.isdigit():
                ok, streak = habits.log(int(keyword))
                habit_name = f"#{keyword}"
            else:
                ok, streak, h = habits.log_by_name(keyword)
                habit_name = h["name"] if h else keyword
            if ok:
                _log_action(user_name, "habit_done", f"'{habit_name}' done | streak: {streak}")
                await update.message.reply_text(
                    f"🔥 *{habit_name} done! MashAllah!* 🎉\n\n{streak} din ka streak! 💪",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❓ Kaunsa habit? /habit se list dekho aur /hdone id se log karo")
        except Exception as e:
            log.error(f"Habit done error: {e}")
            await update.message.reply_text("❌ Kuch galat ho gaya! /hdone id try karo")

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
        category = auto_tag_memory(text)
        try:
            memory.add(text, category=category)
            _log_action(user_name, "memory_save", f"Saved [{category}]: {text[:80]}")
            await update.message.reply_text(
                f"🧠 *Memory Mein Save Ho Gaya!* ✅ [{category}]\n\n_{text[:150]}_\n\nInshAllah yaad rakhunga! 💡",
                parse_mode="Markdown"
            )
        except Exception:
            diary.add(f"[Memory] [{category}] {text}")
            _log_action(user_name, "memory_save_fallback", f"Saved as diary [{category}]: {text[:80]}")
            await update.message.reply_text(f"🧠 *Note Save Ho Gaya!* ✅ [{category}]\n\n_{text[:150]}_", parse_mode="Markdown")

    else:  # AI chat with context
        prompt = build_system_prompt(chat_id) + f"""

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
        
        english_greetings = ["Hello", "Hi", "Hey", "Good morning", "Good evening", "Good afternoon"]
        for eng in english_greetings:
            if reply.lower().startswith(eng.lower()):
                reply = "Assalamualaikum! " + reply[len(eng):].strip()
        
        if not any(word in reply.lower() for word in ['assalamualaikum', 'alaikum', 'salam', 'alhamdulillah']):
            reply = "Assalamualaikum! " + reply
        
        _log_action(user_name, "ai_chat", f"Q: {user_msg[:60]} | A: {reply[:60]}")
        await update.message.reply_text(reply, parse_mode="Markdown")
        add_to_context(chat_id, "assistant", reply[:100])

    chat_hist.add("assistant", "Reply sent", "Rk")


# ════════════════════════════════════════════════════
# MAIN - FIXED JOB QUEUE FOR DAILY SUMMARIES
# ════════════════════════════════════════════════════

def main():
    """Main entry point - initialize and start the bot"""
    cleanup_before_start()
    
    log.info("=" * 60)
    log.info("Rk Bot v18.4 COMPLETE | ALL v17 Features + ALL v18.x Improvements + ALL Fixes")
    log.info(f"IST: {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Sheets: {'Yes' if sheets_backup.connected else 'No'}")
    log.info(f"GitHub: {'Yes' if repo_manager.is_connected else 'No'}")
    log.info(f"Budget: Rs.{WEEKLY_BUDGET_THRESHOLD}/week")
    log.info("=" * 60)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # ── Channel Logger Setup ──
    try:
        from secure_data_manager import channel_logger
        channel_logger.set_bot(app.bot)
        log.info("✅ Channel logger connected to bot")
        
        if channel_logger.enabled:
            async def send_startup_log(context):
                await channel_logger.log_startup()
            
            if app.job_queue:
                app.job_queue.run_once(send_startup_log, 3)
                log.info("📢 Startup log scheduled (will send in 3 seconds)")
            else:
                log.warning("JobQueue not available")
    except Exception as e:
        log.warning(f"Channel logger setup failed: {e}")

    # ── Register All Handlers ──
    from delete_manager import register_delete_handlers
    register_delete_handlers(app)

    register_memory_handlers(app)
    
    register_voice_handlers(app)

    # Diary conversation handler
    diary_handler = ConversationHandler(
        entry_points=[
            CommandHandler("diary", cmd_diary_entry),
            CommandHandler("save", cmd_save)
        ],
        states={
            DIARY_AWAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_text_input)],
        },
        fallbacks=[CommandHandler("cancel", diary_cancel)],
        per_user=True, per_chat=True, per_message=False,
    )
    app.add_handler(diary_handler)

    # Command handlers
    for cmd, handler in [
        ("start", cmd_start), ("help", cmd_help),
        ("status", cmd_status), ("checksync", cmd_checksync),
        ("task", cmd_task), ("done", cmd_done), ("deltask", cmd_deltask),
        ("habit", cmd_habit), ("hdone", cmd_hdone),
        ("kharcha", cmd_kharcha), ("remind", cmd_remind),
        ("delremind", cmd_delremind), ("water", cmd_water),
        ("briefing", cmd_briefing),
        ("snooze5", cmd_snooze), ("snooze10", cmd_snooze),
        ("snooze30", cmd_snooze), ("snooze60", cmd_snooze),
        ("cal", cmd_cal), ("caltoday", cmd_caltoday),
        ("calweek", cmd_calweek), ("caladd", cmd_caladd), ("caldel", cmd_caldel),
        ("bills", cmd_bills), ("billadd", cmd_billadd),
        ("billpaid", cmd_billpaid), ("billdel", cmd_billdel),
        ("smartremind", cmd_smart_remind),
        ("smartlist", cmd_smart_list),
        ("smartcomplete", cmd_smart_complete),
        ("diaryall", cmd_diaryall),
        ("today", cmd_today), ("weekly", cmd_weekly),
    ]:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(CallbackQueryHandler(handle_ok_button, pattern=r"^ok_"))
    
    # Natural language message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ── Job Queue Setup ──
    if app.job_queue:
        # Main reminder checker - every 60 seconds
        app.job_queue.run_repeating(reminder_job, interval=60, first=10)
        log.info("⏰ Reminder job scheduled (every 60s)")
        
        # ✅ FIXED: Use run_repeating for daily summaries instead of run_daily
        # This ensures they fire even without user interaction
        
        # Smart Daily Summary checker - runs every 60 seconds
        # The function itself checks if it's the right time to send
        app.job_queue.run_repeating(smart_daily_summary, interval=60, first=30)
        log.info("📊 Smart Daily Summary checker scheduled (every 60s)")
        
        # Proactive Follow-up - every 3 hours
        app.job_queue.run_repeating(proactive_followup_job, interval=10800, first=300)
        log.info("🔄 Proactive followup scheduled (every 3 hours)")
        
        # Weekly Review checker - every hour, function checks if Sunday 9 PM
        app.job_queue.run_repeating(weekly_review_job, interval=3600, first=120)
        log.info("📊 Weekly review checker scheduled (every hour)")
        
        # Expense Insight checker - every 6 hours, function checks if Fri/Sat
        app.job_queue.run_repeating(expense_insight_job, interval=21600, first=180)
        log.info("💰 Expense insight checker scheduled (every 6 hours)")
        
    else:
        log.warning("⚠️ JobQueue not available - reminders and daily summaries disabled!")

    # ✅ FIXED: Send immediate startup notification to confirm bot is working
    async def send_startup_notification(context: ContextTypes.DEFAULT_TYPE):
        """Send a test notification on startup to confirm jobs are working"""
        try:
            # Get all known chat IDs
            chat_ids = set()
            for r in reminders.get_all():
                if r.get("chat_id"):
                    try:
                        chat_ids.add(int(r["chat_id"]))
                    except:
                        pass
            
            # If no chat IDs found from reminders, try from chat_hist
            if not chat_ids:
                log.warning("No chat IDs found for startup notification")
                return
            
            for cid in chat_ids:
                try:
                    await context.bot.send_message(
                        chat_id=cid,
                        text="🟢 *Rk Bot v18.4 Active!*\n\n✅ All systems running\n⏰ Daily summaries active\n📊 Proactive follow-ups active\n\n_Alhamdulillah!_",
                        parse_mode="Markdown"
                    )
                    log.info(f"Startup notification sent to {cid}")
                except Exception as e:
                    log.error(f"Failed to send startup notification to {cid}: {e}")
        except Exception as e:
            log.error(f"Startup notification error: {e}")
    
    if app.job_queue:
        app.job_queue.run_once(send_startup_notification, 5)
        log.info("📢 Startup notification scheduled (5 sec delay)")

    # ── Start Bot ──
    log.info("✅ Bot ready! Starting polling...")
    log.info("📊 Daily summaries will now trigger automatically every 60 seconds check")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
