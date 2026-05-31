#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PERSONAL AI ASSISTANT — RK BOT v18.5 COMPLETE
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
  ✅ Smart reminders use separate smart_counter (secure_data_manager)
  ✅ No ID conflict between normal and smart reminders
  ✅ reminder_job checks BOTH normal AND smart reminders
"""

import os, json, logging, time
from command_parser import get_action
import urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta, timezone
import re as _re
import re
import asyncio

from secure_data_manager import (
    memory, tasks, diary, habits, expenses, goals, reminders, smart_reminders,
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
try:
    WEEKLY_BUDGET_THRESHOLD = int(os.environ.get("WEEKLY_BUDGET_THRESHOLD", "1000"))
except (ValueError, TypeError):
    WEEKLY_BUDGET_THRESHOLD = 1000

DIARY_AWAIT_TEXT = 0
# ── ADD THESE 2 LINES ──
AWAITING_CONFIRMATION = 100
pending_actions = {}

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

async def cleanup_chat_context():
    global _last_context_cleanup
    async with _chat_context_lock:
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
            last_ts = last_msg[2]
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
            log.info(f"🧹 Cleaned {len(to_remove)} old chat contexts")


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
    #cleanup_chat_context()
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
    token = TELEGRAM_TOKEN
    if not token:
        return
    
    try:
        url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info(f"Webhook deleted: {resp.status}")
        
        time.sleep(5)  # 2 → 5 karo
        
        url2 = f"https://api.telegram.org/bot{token}/getUpdates?offset=-1&timeout=1"
        req2 = urllib.request.Request(url2, method="POST")
        with urllib.request.urlopen(req2, timeout=5):
            pass
        
        time.sleep(3)  # 1 → 3 karo
        log.info("✅ Cleanup completed")
    except Exception as e:
        log.warning(f"Cleanup warning: {e}")


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
    Smart daily summary - sends as SMART REMINDER so it repeats until seen
    Times: 9:00 AM, 1:00 PM, 6:00 PM, 8:00 PM(habits), 9:00 PM IST
    """
    # Add small random delay to avoid conflicts
    import random
    await asyncio.sleep(random.uniform(0.5, 2.0))
    now = now_ist()
    current_time = now.strftime("%H:%M")
    
    # Get chat IDs from BOTH stores
    chat_ids = set()
    for r in list(reminders.get_all()) + list(smart_reminders.get_all()):
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
    priority = "HIGH"        # Har summary HIGH priority
    repeat_mins = 5          # Har 5 min repeat
    max_repeats = 12         # Max 1 ghante tak (12 x 5min)
    
    # ── 9:00 AM - Morning Summary ──
    if current_time == "09:00":
        msg = f"☀️ *Assalamualaikum! Good Morning!* ☀️\n\n"
        msg += f"📋 *Aaj ke Pending Tasks:* {len(pending_tasks)}\n"
        if pending_tasks:
            task_list = "\n".join([f"   {i+1}. {t['title'][:50]}" 
                                   for i, t in enumerate(pending_tasks[:5])])
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
        priority = "HIGH"
        repeat_mins = 5
        max_repeats = 6   # 30 min tak repeat
    
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
        priority = "MEDIUM"
        repeat_mins = 10
        max_repeats = 4   # 40 min tak repeat
    
    # ── 6:00 PM - Evening Summary ──
    elif current_time == "18:00":
        completed_tasks = len([t for t in tasks.all_tasks() 
                               if t.get("done") and t.get("done_date") == today_str_val])
        
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
        priority = "HIGH"
        repeat_mins = 5
        max_repeats = 6   # 30 min tak repeat
    
    # ── 8:00 PM - Habit Streak Guard ──
    elif current_time == "20:00":
        if not habits_pending:
            return  # Sab done, skip
        msg = f"⚠️ *Raat ho rahi hai! Ye habits abhi pending hain:*\n\n"
        for h in habits_pending[:5]:
            msg += f"   ⬜ #{h['id']} *{h['name']}*\n"
        msg += f"\n🏃 *Jaldi kar lo! /hdone id se log karo!*\n"
        msg += f"\n💪 _InshAllah streak tootne mat do!_"
        priority = "HIGH"
        repeat_mins = 5
        max_repeats = 8   # 40 min tak repeat
    
    # ── 9:00 PM - Night Summary ──
    elif current_time == "21:00":
        completed_tasks = len([t for t in tasks.all_tasks() 
                               if t.get("done") and t.get("done_date") == today_str_val])
        
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
        priority = "MEDIUM"
        repeat_mins = 10
        max_repeats = 3   # 30 min tak repeat
    
    else:
        return
    
    if not msg:
        return
    
    # Deduplication key - ek time slot mein sirf ek baar bhejo
    dedup_key = f"daily_summary_{current_time}_{today_str_val}"
    dedup_file = os.path.join(DATA_DIR, "summary_dedup.json")
    
    try:
        if os.path.exists(dedup_file):
            with open(dedup_file, 'r') as f:
                dedup_data = json.load(f)
        else:
            dedup_data = {}
        
        if dedup_key in dedup_data:
            log.info(f"Summary already sent for {current_time} today, skipping")
            return
        
        dedup_data[dedup_key] = now.strftime("%Y-%m-%d %H:%M:%S")
        # Purane entries clean karo (sirf aaj ke rakho)
        dedup_data = {k: v for k, v in dedup_data.items() 
                      if today_str_val in k}
        
        with open(dedup_file, 'w') as f:
            json.dump(dedup_data, f)
    except Exception as e:
        log.warning(f"Dedup check failed: {e}")
    
    # ── SMART REMINDER KE ROOP MEIN BHEJO ──
    # Pehle normal message bhejo
    # Phir smart reminder set karo jo tab tak repeat kare jab tak seen na ho
    
    msg += f"\n\n_✅ Seen karne ke liye button dabao_\n_/briefing - Detailed summary_"
    
    for chat_id in chat_ids:
        try:
            # Smart reminder add karo - ye tab tak fire karega jab tak complete na ho
            due_now = now.strftime("%Y-%m-%d %H:%M:%S")
            
            reminder = smart_reminders.add(
                chat_id=chat_id,
                text=msg,
                due_timestamp=due_now,
                priority=priority,
                repeat_until_done=True,        # Tab tak repeat karo jab tak user complete na kare
                repeat_interval=repeat_mins,
                max_repeats=max_repeats
            )
            
            # Turant bhi bhejo
            buttons = [
                InlineKeyboardButton(
                    "✅ Dekh Liya - Band Karo", 
                    callback_data=f"smart_complete_{reminder['id']}"
                ),
            ]
            keyboard = InlineKeyboardMarkup([buttons])
            
            await context.bot.send_message(
                chat_id=chat_id, 
                text=msg,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
            log.info(f"Smart daily summary sent to {chat_id} at {current_time}, "
                    f"reminder #{reminder['id']} will repeat every {repeat_mins}min "
                    f"max {max_repeats} times")
                    
        except Exception as e:
            log.error(f"Failed to send smart daily summary to {chat_id}: {e}")

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
    """Send comprehensive weekly review every Sunday at 9 PM - max 5 repeats"""
    now = now_ist()
    if now.weekday() != 6:  # Sunday only
        return
    if now.strftime("%H:%M") != "21:00":  # Only at 9 PM
        return

    # ── Deduplication ──
    dedup_key = f"weekly_review_{now.strftime('%Y-%m-%d')}"
    dedup_file = os.path.join(DATA_DIR, "summary_dedup.json")

    try:
        dedup_data = {}
        if os.path.exists(dedup_file):
            with open(dedup_file, 'r') as f:
                dedup_data = json.load(f)

        if dedup_key in dedup_data:
            log.info("Weekly review already sent today, skipping")
            return

        dedup_data[dedup_key] = now.strftime("%Y-%m-%d %H:%M:%S")
        with open(dedup_file, 'w') as f:
            json.dump(dedup_data, f)
    except Exception as e:
        log.warning(f"Weekly dedup check failed: {e}")

    # ── Collect chat IDs ──
    chat_ids = set()
    for r in reminders.get_all():
        if r.get("chat_id"):
            try:
                chat_ids.add(int(r["chat_id"]))
            except:
                pass

    if not chat_ids:
        return

    # ── Build message ──
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
    msg += f"🌟 *MashAllah! Agla hafte aur acha hoga InshAllah!*\n\n"
    msg += f"_✅ Dekh liya? Button dabao band karne ke liye_"

    # ── Send as smart reminder - max 5 repeats ──
    for chat_id in chat_ids:
        try:
            reminder = smart_reminders.add(
                chat_id=chat_id,
                text=msg,
                due_timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
                priority="MEDIUM",
                repeat_until_done=True,
                repeat_interval=10,    # Har 10 min repeat
                max_repeats=5          # Max 5 baar - phir band
            )

            buttons = [[InlineKeyboardButton(
                "✅ Dekh Liya - Band Karo",
                callback_data=f"smart_complete_{reminder['id']}"
            )]]
            keyboard = InlineKeyboardMarkup(buttons)

            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )

            log.info(f"Weekly review sent to {chat_id}, reminder #{reminder['id']} "
                     f"will repeat max 5 times every 10 min")
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
        "📖 *COMMANDS — Rk Bot v18.5*\n\n"
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
        f"🧠 Smart Reminders: {len(smart_reminders.get_all())}\n"
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
# SMART REMINDER INTELLIGENCE (UPDATED - uses smart_reminders)
# ════════════════════════════════════════════════════

SMART_PRIORITY_CONFIG = {
    "HIGH": {"repeat_interval": 5, "max_repeats": 12, "emoji": "🔴", "prefix": "🔴 *URGENT!* "},
    "MEDIUM": {"repeat_interval": 15, "max_repeats": 8, "emoji": "🟠", "prefix": "🟠 *Reminder!* "},
    "LOW": {"repeat_interval": 30, "max_repeats": 4, "emoji": "🔵", "prefix": "🔵 "},
}

def _get_next_smart_id():
    """Get next unique ID for smart reminder using smart_reminders store"""
    from secure_data_manager import smart_reminders
    smart_reminders.store.data["smart_counter"] = smart_reminders.store.data.get("smart_counter", 0) + 1
    return smart_reminders.store.data["smart_counter"]

def _add_smart_reminder(chat_id: int, text: str, due_timestamp: str, priority: str = "MEDIUM", repeat_until_done: bool = False):
    """Add a smart reminder with priority and repeat logic - uses smart_reminders store"""
    from secure_data_manager import smart_reminders, sheets_backup
    
    config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
    
    reminder = smart_reminders.add(
        chat_id=chat_id,
        text=text,
        due_timestamp=due_timestamp,
        priority=priority,
        repeat_until_done=repeat_until_done,
        repeat_interval=config["repeat_interval"],
        max_repeats=config["max_repeats"]
    )
    
    return reminder

def _process_smart_followup(reminder):
    """Create follow-up reminder for smart reminder chain - uses smart_reminders"""
    from secure_data_manager import smart_reminders
    return smart_reminders.process_followup(reminder)

def _find_root_parent(reminder_id, reminders_store=None):
    """Recursively find the root parent of a smart reminder chain - uses smart_reminders"""
    from secure_data_manager import smart_reminders
    return smart_reminders.find_root_parent(reminder_id)

def _acknowledge_smart_chain(reminder_id: int):
    """Acknowledge entire smart reminder chain from root - uses smart_reminders"""
    from secure_data_manager import smart_reminders
    return smart_reminders.acknowledge_chain(reminder_id)


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
    """List all active smart reminders - uses smart_reminders"""
    from secure_data_manager import smart_reminders
    
    active = smart_reminders.get_active_smart()
    # Filter by chat_id
    active = [r for r in active if r.get("chat_id") == update.effective_chat.id]
    
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
# DIARY COMMANDS (NO PASSWORD) - FULL VERSION
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
# REMINDER JOB - CHECKS BOTH NORMAL AND SMART REMINDERS
# ════════════════════════════════════════════════════

# Fired tracker cache
FIRED_TRACKER_FILE = os.path.join(DATA_DIR, "fired_reminders.json")
_fired_cache = None
_fired_cache_time = 0
_chat_context_lock = asyncio.Lock()

def _load_fired_tracker():
    global _fired_cache, _fired_cache_time
    now = time.time()
    if _fired_cache is not None and now - _fired_cache_time < 60:
        return _fired_cache
    try:
        if os.path.exists(FIRED_TRACKER_FILE):
            with open(FIRED_TRACKER_FILE, 'r') as f:
                _fired_cache = json.load(f)
                _fired_cache_time = now
                return _fired_cache
    except:
        pass
    _fired_cache = {}
    _fired_cache_time = now
    return _fired_cache

def _save_fired_tracker(tracker):
    """Save fired reminders tracker to disk"""
    try:
        with open(FIRED_TRACKER_FILE, 'w') as f:
            json.dump(tracker, f)
    except Exception as e:
        log.warning(f"Failed to save fired tracker: {e}")

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """Main reminder checker - runs every 60 seconds with deduplication"""
    await cleanup_chat_context()
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
    
    # ── CHECK NORMAL REMINDERS (reminders store) ──
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
                fire_key = f"normal_{rid}_{due_min}"
                
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
    
    # ── CHECK SMART REMINDERS (smart_reminders store) ──
    smart_active = smart_reminders.get_active_smart()
    
    for r in smart_active:
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
                fire_key = f"smart_{rid}_{due_min}"
                
                if fire_key in fired_tracker and fired_tracker[fire_key].get("fired"):
                    continue
                
                fired_tracker[fire_key] = {"fired": True, "date": today_key, "time": now_hm}
                _save_fired_tracker(fired_tracker)
                
                try:
                    due_dt = datetime.strptime(reminder_due, "%Y-%m-%d %H:%M:%S")
                    due_time_display = due_dt.strftime("%I:%M %p")
                except:
                    due_time_display = reminder_due
                
                priority = r.get("priority", "MEDIUM")
                config = SMART_PRIORITY_CONFIG.get(priority, SMART_PRIORITY_CONFIG["MEDIUM"])
                prefix = config["prefix"]
                current_repeat = r.get("current_repeat", 0)
                max_repeats = r.get("max_repeats", config["max_repeats"])
                
                # ── ROOT TEXT use karo - nested text avoid karne ke liye ──
                display_text = r.get("root_text") or r.get("text", "")
                
                # Max repeats check - agar limit cross ho gayi to acknowledge karo aur skip karo
                if not r.get("repeat_until_done", False) and current_repeat >= max_repeats:
                    log.info(f"Smart reminder #{r['id']} reached max repeats ({max_repeats}), auto-acknowledging")
                    smart_reminders.acknowledge(r["id"], "Max repeats reached")
                    continue
                
                progress = f"\n\n📊 *Progress:* Attempt {current_repeat + 1}/{max_repeats}"
                
                alert = (f"{prefix}🚨 *ALARM!*\n{'━' * 20}\n⏰ *{due_time_display} BAJ GAYE!*\n{'━' * 20}\n\n"
                         f"🔔 *{display_text.upper()}*{progress}\n\n"
                         f"😴 Snooze: /snooze5 {r['id']} | /snooze10 {r['id']}\n"
                         f"🗑️ Delete: /delremind {r['id']}\n"
                         f"✅ Complete: /smartcomplete {r['id']}")
                
                buttons = [
                    InlineKeyboardButton("✅ Complete - Stop Reminding", callback_data=f"smart_complete_{r['id']}"),
                    InlineKeyboardButton("⏰ Snooze 5min", callback_data=f"smart_snooze5_{r['id']}"),
                    InlineKeyboardButton("🔁 Remind Again", callback_data=f"smart_again_{r['id']}"),
                ]
                keyboard = InlineKeyboardMarkup([buttons])
                
                try:
                    await context.bot.send_message(
                        chat_id=int(r["chat_id"]), text=alert,
                        reply_markup=keyboard, parse_mode="Markdown"
                    )
                    smart_reminders.mark_triggered(r["id"])
                    
                    # Follow-up schedule karo - process_followup ke andar bhi max_repeats check hai
                    if not r.get("acknowledged", False):
                        _process_smart_followup(r)
                    
                    _log_action("Bot", "alarm_fired", f"Smart Alarm #{r['id']} at {now_hm}: {display_text[:50]}")
                except Exception as e:
                    log.error(f"Failed to send smart alarm: {e}")

# ════════════════════════════════════════════════════
# OK BUTTON HANDLER
# ════════════════════════════════════════════════════

async def handle_ok_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle alarm OK button press for both normal and smart reminders"""
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

    elif query.data.startswith("smart_complete_"):
        try:
            rid = int(query.data.split("_")[2])
            count = _acknowledge_smart_chain(rid)
            await query.edit_message_text(
                f"✅ *Smart Reminder Completed!* 🎉\n\nStopped {count} reminder(s). Alhamdulillah!",
                parse_mode="Markdown"
            )
        except Exception as e:
            log.error(f"Smart complete error: {e}")
            await query.edit_message_text("❌ Error!")

    elif query.data.startswith("smart_snooze5_"):
        try:
            rid = int(query.data.split("_")[2])
            target = smart_reminders.get_by_id(rid)
            if target:
                smart_reminders.acknowledge(rid, "Snoozed 5min")
                new_dt = now_ist() + timedelta(minutes=5)
                _add_smart_reminder(
                    target["chat_id"], target["text"],
                    new_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    target.get("priority", "MEDIUM"),
                    target.get("repeat_until_done", False)
                )
                await query.edit_message_text(f"😴 *Snoozed 5 minutes!*", parse_mode="Markdown")
            else:
                await query.edit_message_text("❌ Reminder not found!")
        except Exception as e:
            log.error(f"Smart snooze error: {e}")
            await query.edit_message_text("❌ Error!")

    elif query.data.startswith("smart_again_"):
        try:
            rid = int(query.data.split("_")[2])
            target = smart_reminders.get_by_id(rid)
            if target:
                smart_reminders.acknowledge(rid, "Remind again")
                new_dt = now_ist() + timedelta(minutes=target.get("repeat_interval", 15))
                _add_smart_reminder(
                    target["chat_id"], target["text"],
                    new_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    target.get("priority", "MEDIUM"),
                    target.get("repeat_until_done", False)
                )
                await query.edit_message_text(f"🔁 *Will remind again!*", parse_mode="Markdown")
            else:
                await query.edit_message_text("❌ Reminder not found!")
        except Exception as e:
            log.error(f"Smart again error: {e}")
            await query.edit_message_text("❌ Error!")

    elif query.data.startswith("quick_done_"):
        try:
            tid = int(query.data.split("_")[2])
            t = tasks.complete(tid)
            if t:
                _log_action("User", "quick_task_done", f"#{tid}: {t['title']}")
                await query.edit_message_text(
                    f"✅ *Alhamdulillah! Task Complete!* 🎉\n\n"
                    f"#{tid} {t['title']}\n\nMashAllah! 💪",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("❌ Task nahi mila!")
        except Exception as e:
            log.error(f"Quick done error: {e}")
            await query.edit_message_text("❌ Error!")

    elif query.data.startswith("postpone_"):
        try:
            tid = int(query.data.split("_")[1])
            target = next((t for t in tasks.all_tasks() if t["id"] == tid), None)
            if target:
                kal = (now_ist() + timedelta(days=1)).strftime("%Y-%m-%d 09:00:00")
                reminders.add(query.message.chat.id, f"Task: {target['title']}", kal)
                _log_action("User", "task_postponed", f"#{tid}: {target['title']}")
                await query.edit_message_text(
                    f"⏰ *Kal ke liye set ho gaya!*\n\n"
                    f"#{tid} {target['title']}\n\n"
                    f"_Kal 9 AM pe yaad dilaaunga! InshAllah_",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("❌ Task nahi mila!")
        except Exception as e:
            log.error(f"Postpone error: {e}")
            await query.edit_message_text("❌ Error!")

    elif query.data.startswith("quick_del_"):
        try:
            tid = int(query.data.split("_")[2])
            target = next((t for t in tasks.all_tasks() if t["id"] == tid), None)
            if target:
                tasks.delete(tid)
                _log_action("User", "quick_task_delete", f"#{tid}: {target['title']}")
                await query.edit_message_text(
                    f"🗑️ *Task Delete Ho Gaya!*\n\n"
                    f"#{tid} '{target['title']}'",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("❌ Task nahi mila!")
        except Exception as e:
            log.error(f"Quick del error: {e}")
            await query.edit_message_text("❌ Error!")

    elif query.data.startswith("habit_quick_"):
        try:
            hid = int(query.data.split("_")[2])
            ok, streak = habits.log(hid)
            if ok:
                _log_action("User", "habit_quick_done", f"#{hid} streak: {streak}")
                if streak >= 7:
                    msg = f"🔥 *MashAllah! Streak Bacha Li!* 🎉\n\n{streak} din ka streak! SubhanAllah! 💪"
                else:
                    msg = f"✅ *Habit Done! Alhamdulillah!* 🎉\n\n{streak} din ka streak! 💪"
                await query.edit_message_text(msg, parse_mode="Markdown")
            else:
                await query.edit_message_text("✅ Pehle hi log ho chuka hai!")
        except Exception as e:
            log.error(f"Habit quick done error: {e}")
            await query.edit_message_text("❌ Error!")


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
            if date_str:
                remind_dt = datetime(due_date.year, due_date.month, due_date.day, 9, 0)
                if remind_dt < now and due_date == now.date():
                    remind_dt += timedelta(days=1)
            elif 'min' in lower or 'minute' in lower or 'baad' in lower:
                num_match = _re.search(r'(\d+)', lower)
                if num_match:
                    mins = int(num_match.group(1))
                    remind_dt = now + timedelta(minutes=mins)
                else:
                    remind_dt = now + timedelta(minutes=5)
            else:
                remind_dt = now + timedelta(minutes=5)

        text = user_msg
        remove_words = reminder_keywords + ['kal', 'kl', 'aaj', 'parso', 'subha', 'subah',
                    'shaam', 'raat', 'baje', 'bajay', 'am', 'pm', 'mein', 'me', 'ko', 'pe',
                    'add', 'kro', 'karo', 'set']
        for rw in remove_words:
            text = _re.sub(r'\b' + _re.escape(rw) + r'\b', '', text, flags=_re.IGNORECASE)
        if date_str:
            text = _re.sub(r'\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*', '', text, flags=_re.IGNORECASE)
        text = _re.sub(r'\d{1,2}[:]\d{2}', '', text)
        text = _re.sub(r'\d{1,2}\s*(?:baje|bajay|am|pm)', '', text)
        text = text.strip()
        if not text or len(text) < 2:
            text = "Reminder"

        return ("remind", {"time": remind_dt.strftime("%Y-%m-%d %H:%M:%S"), "text": text})

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
    """Send active reminders list - shows BOTH normal and smart reminders"""
    active = reminders.all_active()
    smart_active = [r for r in smart_reminders.get_active_smart() 
                    if str(r.get("chat_id", "")) == str(update.effective_chat.id)]
    
    all_active = active + smart_active
    
    if all_active:
        lines = []
        for r in all_active:
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
        
        normal_count = len(active)
        smart_count = len(smart_active)
        total_count = len(all_active)
        
        header = f"⏰ *Active Reminders ({total_count}):*"
        if smart_count > 0:
            header += f"\n_Normal: {normal_count} | Smart: {smart_count}_"
        
        await update.message.reply_text(
            f"{header}\n\n" + "\n".join(lines) + "\n\n"
            f"/delremind id — Delete karo\n/snooze5 id — Snooze\n/remind 30m Chai — Naya set karo\n"
            f"/smartlist — Smart reminders detail\n/smartcomplete id — Smart reminder band karo",
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
    """
    Main message handler — New Command Parser + Old Parser fallback.
    
    Flow:
    1. New parser (command_parser.py) pehle try karta hai
    2. Agar new parser samjhe → action lo
    3. Agar new parser "unknown" return kare → old parser try karo
    4. Agar dono fail → Gemini AI se reply lo
    """
    if not update.message or not update.message.text:
        return
 
    user_msg = update.message.text.strip()
    user_name = update.effective_user.first_name or "User"
    chat_id = update.effective_chat.id
 
    if user_msg.startswith("/"):
        return
 
    # Context mein add karo
    add_to_context(chat_id, "user", user_msg)
 
    # Smart memory check
    if await check_smart_memory_intent(update, ctx):
        chat_hist.add("user", user_msg, user_name)
        return
 
    await ctx.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )
 
    chat_hist.add("user", user_msg, user_name)
 
    # ════════════════════════════════════════════════════
    # STEP 1: NEW PARSER (command_parser.py)
    # ════════════════════════════════════════════════════
    new_action, new_params, needs_confirm = get_action(user_msg, now_ist)
    log.info(f"NEW PARSER: '{user_msg[:60]}' → {new_action}")
    
    # ── CONFIRMATION CHECK (ADD THIS BEFORE OTHER HANDLERS) ──
    if needs_confirm and new_action not in ["show_tasks", "show_reminders", "show_habits", "show_diary", "show_all_diary", "show_memory", "show_calendar", "show_bills", "show_expense", "show_water", "complete"]:
        
        # ── FIND PARENT SMART REMINDER ID (to stop repeats later) ──
        parent_reminder_id = None
        try:
            # Check if there's an active smart reminder that matches this intent
            for r in smart_reminders.get_active_smart():
                if str(r.get("chat_id")) == str(chat_id):
                    # Check if user message relates to this reminder
                    r_text = r.get("text", "").lower()
                    if any(word in user_msg.lower() for word in r_text.split()[:3]):
                        parent_reminder_id = r.get("id")
                        log.info(f"Found parent smart reminder #{parent_reminder_id} for this action")
                        break
        except Exception as e:
            log.warning(f"Error finding parent reminder: {e}")
        
        pending_actions[chat_id] = {
            "action": new_action, 
            "params": new_params, 
            "msg": user_msg,
            "parent_reminder_id": parent_reminder_id  # Store parent ID to acknowledge later
        }
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Haan, Karo", callback_data="confirm_add"),
            InlineKeyboardButton("❌ Nahi", callback_data="confirm_cancel")
        ]])
        
        await update.message.reply_text(
            f"❓ *Confirm karo?*\n\n{user_msg[:150]}\n\nYe sahi hai?",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return
    
    if new_action != "unknown":
        # ── NEW PARSER NE SAMJHA ──────────────────────
        handled = True
 
        # ── DIARY ──────────────────────────────────────
        if new_action == "diary":
            text = new_params.get("text", "").strip()
            if not text or len(text) < 2:
                text = user_msg
            diary.add(text)
            _log_action(user_name, "diary_write", f"Saved: {text[:60]}")
            await update.message.reply_text(
                f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n"
                f"_{text[:200]}_\n\n"
                f"📊 Sheets mein bhi backup ho gaya!",
                parse_mode="Markdown"
            )
 
        # ── TASK ───────────────────────────────────────
        elif new_action == "task":
            title = new_params.get("title", "").strip()
            if not title or len(title) < 2:
                title = user_msg
            t = tasks.add(title)
            _log_action(user_name, "task_add", f"#{t['id']}: {t['title']}")
            await update.message.reply_text(
                f"✅ *Task Add Ho Gaya!*\n\n"
                f"📌 #{t['id']} {t['title']}\n\n"
                f"InshAllah ho jayega! 💪",
                parse_mode="Markdown"
            )
 
        # ── REMINDER ───────────────────────────────────
        elif new_action == "remind":
            due_timestamp = new_params.get("due", "")
            text = new_params.get("text", "Reminder").strip()
 
            if not due_timestamp:
                # Default: 5 min baad
                remind_dt = now_ist() + timedelta(minutes=5)
                due_timestamp = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
 
            if not text or len(text) < 2:
                text = "Reminder"
 
            r = reminders.add(chat_id, text, due_timestamp)
 
            try:
                remind_dt = datetime.strptime(due_timestamp, "%Y-%m-%d %H:%M:%S")
                date_display = remind_dt.strftime("%d %b %Y")
                h_val = remind_dt.hour
                m_val = remind_dt.minute
                ampm = "AM" if h_val < 12 else "PM"
                h12 = h_val % 12 or 12
                time_display = f"{h12}:{m_val:02d} {ampm}"
            except Exception:
                date_display = "Aaj"
                time_display = due_timestamp
 
            _log_action(user_name, "reminder_set", f"#{r['id']} at {due_timestamp}: {text}")
            await update.message.reply_text(
                f"⏰ *Reminder Set! InshAllah yaad dilaaunga!*\n\n"
                f"🕐 *{time_display}* — 📅 *{date_display}*\n"
                f"📝 {text}\n"
                f"📌 ID #{r['id']}\n\n"
                f"_/snooze5 {r['id']} — Snooze | /delremind {r['id']} — Delete_",
                parse_mode="Markdown"
            )
 
        # ── HABIT ADD ──────────────────────────────────
        elif new_action == "habit":
            name = new_params.get("name", "").strip()
            if not name or len(name) < 2:
                name = user_msg
            h = habits.add(name)
            _log_action(user_name, "habit_add", f"#{h['id']}: {h['name']}")
            await update.message.reply_text(
                f"🏃 *Habit Add Ho Gaya!*\n\n"
                f"#{h['id']} {h['name']}\n\n"
                f"InshAllah roz karoge! 💪",
                parse_mode="Markdown"
            )
 
        # ── HABIT DONE ─────────────────────────────────
        elif new_action == "habit_done":
            keyword = new_params.get("keyword", "").strip()
            try:
                if keyword.isdigit():
                    ok, streak = habits.log(int(keyword))
                    habit_name = f"#{keyword}"
                else:
                    ok, streak, h = habits.log_by_name(keyword)
                    habit_name = h["name"] if h else keyword
 
                if ok:
                    _log_action(user_name, "habit_done", f"'{habit_name}' done | streak: {streak}")
                    streak_msg = (
                        f"🔥 *MashAllah! {streak} din ka streak!* SubhanAllah! 💪"
                        if streak >= 7
                        else f"✅ Streak: {streak} din! 💪"
                    )
                    await update.message.reply_text(
                        f"🏃 *{habit_name} Done! Alhamdulillah!* 🎉\n\n"
                        f"{streak_msg}",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        f"✅ *{habit_name}* aaj pehle hi log ho chuka hai!\n\n"
                        f"_Kal ke liye ready raho InshAllah!_",
                        parse_mode="Markdown"
                    )
            except Exception as e:
                log.error(f"Habit done error: {e}")
                await update.message.reply_text(
                    "❓ Kaunsa habit? /habit se list dekho aur /hdone id se log karo"
                )
 
        # ── EXPENSE ────────────────────────────────────
        elif new_action == "expense":
            amount = new_params.get("amount", 0)
            desc = new_params.get("desc", "Expense").strip()
 
            if not amount or amount <= 0:
                await update.message.reply_text(
                    "❓ *Amount samajh nahi aaya!*\n\n"
                    "Example:\n"
                    "• `kharcha 200 petrol`\n"
                    "• `200 chai`\n"
                    "• `paisa 500 grocery`",
                    parse_mode="Markdown"
                )
            else:
                if not desc or len(desc) < 2:
                    desc = "Expense"
                expenses.add(amount, desc)
                _log_action(user_name, "expense_add", f"Rs.{amount} on {desc} | Total: Rs.{expenses.today_total()}")
                await update.message.reply_text(
                    f"💸 *Kharcha Add!* ✅\n\n"
                    f"Rs.{amount} — {desc}\n"
                    f"💰 Aaj total: Rs.{expenses.today_total()}",
                    parse_mode="Markdown"
                )
 
        # ── WATER ──────────────────────────────────────
        elif new_action == "water":
            ml = new_params.get("ml", 250)
            total = water.add(ml)
            goal_ml = water.goal()
            pct = int(total / goal_ml * 100) if goal_ml else 0
            filled = min(pct // 20, 5)
            bar = "🟦" * filled + "⬜" * (5 - filled)
            _log_action(user_name, "water_log", f"Added {ml}ml | Total: {total}ml of {goal_ml}ml")
            await update.message.reply_text(
                f"💧 *+{ml}ml Paani!* ✅\n\n"
                f"Total: {total}/{goal_ml}ml\n"
                f"{bar} {pct}%\n\n"
                f"{'🎉 Alhamdulillah! Goal complete!' if total >= goal_ml else 'InshAllah goal poora hoga! 💪'}",
                parse_mode="Markdown"
            )
 
        # ── MEMORY ─────────────────────────────────────
        elif new_action == "memory":
            text = new_params.get("text", "").strip()
            if not text or len(text) < 2:
                text = user_msg
            category = auto_tag_memory(text)
            try:
                memory.add(text, category=category)
                _log_action(user_name, "memory_save", f"Saved [{category}]: {text[:80]}")
                await update.message.reply_text(
                    f"🧠 *Memory Mein Save Ho Gaya!* ✅\n\n"
                    f"🏷️ Category: *{category}*\n"
                    f"_{text[:200]}_\n\n"
                    f"InshAllah yaad rakhunga! 💡",
                    parse_mode="Markdown"
                )
            except Exception:
                # Fallback to diary
                diary.add(f"[Memory] [{category}] {text}")
                _log_action(user_name, "memory_save_fallback", f"Saved as diary [{category}]: {text[:80]}")
                await update.message.reply_text(
                    f"🧠 *Note Save Ho Gaya!* ✅ [{category}]\n\n"
                    f"_{text[:200]}_",
                    parse_mode="Markdown"
                )
 
        # ── CALENDAR ───────────────────────────────────
        elif new_action == "calendar":
            title = new_params.get("title", "Event").strip()
            ev_date = new_params.get("date", get_today_str())
            ev_type = new_params.get("type", "event")
 
            if not title or len(title) < 2:
                title = "Event"
 
            # Birthday date fix
            if ev_type == "birthday":
                try:
                    from datetime import date as date_cls
                    birth = date_cls.fromisoformat(ev_date)
                    today_d = now_ist().date()
                    next_bday = birth.replace(year=today_d.year)
                    if next_bday < today_d:
                        next_bday = next_bday.replace(year=today_d.year + 1)
                    ev_date = next_bday.strftime("%Y-%m-%d")
                except Exception:
                    pass
 
            e = calendar.add(title, ev_date, "", "", "", ev_type)
            emoji = "🎂" if ev_type == "birthday" else "📅"
            _log_action(user_name, "calendar_add", f"{'Birthday' if ev_type == 'birthday' else 'Event'} #{e['id']}: {title} on {ev_date}")
 
            if ev_type == "birthday":
                msg = (f"🎂 *Birthday Add Ho Gaya! MashAllah!* 🎉\n\n"
                       f"#{e['id']} 🎂 *{ev_date}*\n"
                       f"👤 {title}\n\n"
                       f"✅ Ek din pehle remind karunga!\n"
                       f"📊 Sheets mein save!")
            else:
                msg = (f"📅 *Event Add Ho Gaya!* ✅\n\n"
                       f"#{e['id']} 📅 *{ev_date}*\n"
                       f"📌 {title}\n\n"
                       f"✅ Ek din pehle remind karunga!\n"
                       f"📊 Sheets mein save!")
            await update.message.reply_text(msg, parse_mode="Markdown")
 
        # ── BILL ───────────────────────────────────────
        elif new_action == "bill":
            name = new_params.get("name", "Bill").strip()
            amount = new_params.get("amount", 0)
            due_day = new_params.get("due_day", 0)
 
            if not name or len(name) < 2:
                name = "Bill"
 
            b = bills.add(name, amount, due_day)
            _log_action(user_name, "bill_add", f"#{b['id']}: {name} Rs.{amount} due {due_day} tarikh")
            await update.message.reply_text(
                f"💳 *Bill Add Ho Gaya! Alhamdulillah!* ✅\n\n"
                f"#{b['id']} *{name}*\n"
                f"💰 Rs.{amount}\n"
                f"📅 Due: {due_day if due_day else 'Set nahi'} tarikh\n\n"
                f"📊 Sheets mein save!\n"
                f"_(/billadd se sahi details set karo)_",
                parse_mode="Markdown"
            )
 
        # ── COMPLETE TASK ──────────────────────────────
        elif new_action == "complete":
            task_id = new_params.get("id")
            hint = new_params.get("hint", "")
            pending = tasks.pending()
 
            matched = None
            if task_id:
                matched = next((t for t in pending if t["id"] == task_id), None)
            if not matched and hint:
                matched = next((t for t in pending if hint.lower() in t["title"].lower()), None)
 
            if matched:
                tasks.complete(matched["id"])
                _log_action(user_name, "task_done", f"#{matched['id']}: {matched['title']}")
                await update.message.reply_text(
                    f"✅ *Alhamdulillah! Task Complete!* 🎉\n\n"
                    f"#{matched['id']} ~~{matched['title']}~~\n\n"
                    f"MashAllah! 💪",
                    parse_mode="Markdown"
                )
            else:
                if pending:
                    lines = "\n".join(f"  #{t['id']} {t['title']}" for t in pending[:10])
                    await update.message.reply_text(
                        f"❓ *Kaunsa task complete karna hai?*\n\n{lines}\n\n"
                        f"/done id — Complete karo",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        "✅ Alhamdulillah! Koi pending task nahi hai!"
                    )
 
        # ── SHOW TASKS ─────────────────────────────────
        elif new_action == "show_tasks":
            pending = tasks.pending()
            if pending:
                lines = "\n".join(f"  #{t['id']} {t['title']}" for t in pending[:15])
                await update.message.reply_text(
                    f"📋 *Pending Tasks ({len(pending)}):*\n\n{lines}\n\n"
                    f"/done id — Complete karo\n"
                    f"/deltask id — Delete karo",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "✅ *Alhamdulillah! Koi pending task nahi!* 🎉\n\n"
                    "/task Naam — Naya task add karo",
                    parse_mode="Markdown"
                )
            _log_action(user_name, "show_tasks", user_msg[:60])
 
        # ── SHOW REMINDERS ─────────────────────────────
        elif new_action == "show_reminders":
            await _send_reminder_list(update)
            _log_action(user_name, "show_reminders", user_msg[:60])
 
        # ── SHOW HABITS ────────────────────────────────
        elif new_action == "show_habits":
            await _send_habit_list(update)
            _log_action(user_name, "show_habits", user_msg[:60])
 
        # ── SHOW DIARY (today) ─────────────────────────
        elif new_action == "show_diary":
            await _send_diary_today(update)
            _log_action(user_name, "show_diary", user_msg[:60])
 
        # ── SHOW ALL DIARY ─────────────────────────────
        elif new_action == "show_all_diary":
            await _send_diary_all(update, user_name)
            _log_action(user_name, "show_all_diary", user_msg[:60])
 
        # ── SHOW MEMORY ────────────────────────────────
        elif new_action == "show_memory":
            await _send_memory_list(update)
            _log_action(user_name, "show_memory", user_msg[:60])
 
        # ── SHOW CALENDAR ──────────────────────────────
        elif new_action == "show_calendar":
            await _send_calendar_list(update)
            _log_action(user_name, "show_calendar", user_msg[:60])
 
        # ── SHOW BILLS ─────────────────────────────────
        elif new_action == "show_bills":
            all_bills = bills.all_active()
            if all_bills:
                today_day = now_ist().day
                lines = []
                for b in all_bills:
                    paid = bills.is_paid_this_month(b["id"])
                    status = "✅ Paid" if paid else "❌ Unpaid"
                    try:
                        due = int(b.get("due_day", 0))
                        days_left = due - today_day
                        due_str = f" ({due} tarikh"
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
                    lines.append(
                        f"💳 #{b['id']} *{b['name']}*\n"
                        f"   Rs.{b['amount']}{due_str} — {status}"
                    )
                await update.message.reply_text(
                    f"💳 *Bills ({len(all_bills)}):*\n\n"
                    + "\n\n".join(lines)
                    + "\n\n/billpaid id — Paid mark karo",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "💳 Koi active bill nahi.\n\n/billadd — Naya add karo",
                    parse_mode="Markdown"
                )
            _log_action(user_name, "show_bills", user_msg[:60])
 
        # ── SHOW EXPENSE ───────────────────────────────
        elif new_action == "show_expense":
            today_list = expenses.get_by_date(get_today_str())
            if today_list:
                lines = "\n".join(f"  💸 Rs.{e['amount']} — {e['desc']}" for e in today_list[-10:])
                await update.message.reply_text(
                    f"💸 *Aaj ka Kharcha:*\n\n{lines}\n\n"
                    f"💰 *Total: Rs.{expenses.today_total()}*",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"💸 Aaj koi kharcha nahi hua.\n\n"
                    f"/kharcha 100 Chai — Add karo",
                    parse_mode="Markdown"
                )
            _log_action(user_name, "show_expense", user_msg[:60])
 
        # ── SHOW WATER ─────────────────────────────────
        elif new_action == "show_water":
            total = water.today_total()
            goal_ml = water.goal()
            pct = int(total / goal_ml * 100) if goal_ml else 0
            filled = min(pct // 20, 5)
            bar = "🟦" * filled + "⬜" * (5 - filled)
            await update.message.reply_text(
                f"💧 *Aaj ka Paani:*\n\n"
                f"{bar} {pct}%\n"
                f"Total: {total}/{goal_ml}ml\n\n"
                f"{'✅ Goal complete! Alhamdulillah!' if total >= goal_ml else f'⚠️ {goal_ml - total}ml aur piyo!'}",
                parse_mode="Markdown"
            )
            _log_action(user_name, "show_water", user_msg[:60])
 
        else:
            # New parser ne kuch return kiya jo handle nahi hua
            handled = False
 
        if handled:
            chat_hist.add("assistant", "Reply sent", "Rk")
            return
 
    # ════════════════════════════════════════════════════
    # STEP 2: OLD PARSER FALLBACK
    # ════════════════════════════════════════════════════
    log.info(f"OLD PARSER FALLBACK: '{user_msg[:60]}'")
    action_type, params = parse_user_message(user_msg)
    log.info(f"OLD PARSER: '{user_msg[:60]}' → {action_type}")
 
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
        r = reminders.add(chat_id, text, due_timestamp)
        try:
            remind_dt = datetime.strptime(due_timestamp, "%Y-%m-%d %H:%M:%S")
            date_display = remind_dt.strftime("%d %b %Y")
            h_val = remind_dt.hour
            m_val = remind_dt.minute
            ampm = "AM" if h_val < 12 else "PM"
            h12 = h_val % 12 or 12
            time_display = f"{h12}:{m_val:02d} {ampm}"
        except Exception:
            date_display = "Aaj"
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
            chat_id=chat_id,
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
        except Exception:
            date_display = "Aaj"
            time_display = due_timestamp
        repeat_info = (
            " (repeat until done)"
            if repeat_until_done
            else f" (max {config['max_repeats']} times, every {interval} min)"
        )
        _log_action(user_name, "smart_reminder_set", f"#{r['id']} [{priority}]: {text}")
        await update.message.reply_text(
            f"{config['emoji']} *Smart Reminder Set!* {config['emoji']}\n\n"
            f"🕐 *{time_display}* — 📅 *{date_display}*\n"
            f"📝 {text}\n"
            f"🎯 Priority: *{priority}*{repeat_info}\n"
            f"📌 ID #{r['id']}\n\n"
            f"_/smartcomplete {r['id']} — Band karo_",
            parse_mode="Markdown"
        )
 
    elif action_type == "add_task":
        t = tasks.add(params.get("title", ""))
        _log_action(user_name, "task_add", f"#{t['id']}: {t['title']}")
        await update.message.reply_text(
            f"✅ *Task Add Ho Gaya!*\n\n"
            f"📌 #{t['id']} {t['title']}\n\n"
            f"InshAllah ho jayega! 💪",
            parse_mode="Markdown"
        )
 
    elif action_type == "complete_task":
        hint = params.get("hint", "")
        pending = tasks.pending()
        matched = next(
            (t for t in pending
             if str(t["id"]) == hint or
             (hint and hint in t["title"].lower())),
            None
        )
        if matched:
            tasks.complete(matched["id"])
            _log_action(user_name, "task_done", f"#{matched['id']}: {matched['title']}")
            await update.message.reply_text(
                f"✅ *Alhamdulillah! Task Complete!* 🎉\n\n"
                f"#{matched['id']} ~~{matched['title']}~~\n\n"
                f"MashAllah! 💪",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❓ Kaunsa task? ID ya naam batao")
 
    elif action_type == "expense":
        expenses.add(params.get("amount", 0), params.get("desc", ""))
        _log_action(user_name, "expense_add", f"Rs.{params.get('amount')} on {params.get('desc')} | Total: Rs.{expenses.today_total()}")
        await update.message.reply_text(
            f"💸 Rs.{params.get('amount')} — {params.get('desc')}\n"
            f"💰 Aaj total: Rs.{expenses.today_total()}",
            parse_mode="Markdown"
        )
 
    elif action_type == "diary":
        text = params.get("text", "")
        diary.add(text)
        _log_action(user_name, "diary_write", "Entry saved")
        await update.message.reply_text(
            f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n"
            f"📊 Sheets mein bhi backup ho gaya!",
            parse_mode="Markdown"
        )
 
    elif action_type == "add_habit":
        h = habits.add(params.get("name", ""))
        _log_action(user_name, "habit_add", f"#{h['id']}: {h['name']}")
        await update.message.reply_text(
            f"🏃 *Habit Add Ho Gaya!*\n\n"
            f"#{h['id']} {h['name']}\n\n"
            f"InshAllah roz karoge! 💪",
            parse_mode="Markdown"
        )
 
    elif action_type == "add_calendar":
        title = params.get("title", "Event")
        ev_date = params.get("date", get_today_str())
        ev_type = params.get("type", "event")
        e = calendar.add(title, ev_date, "", "", "", ev_type)
        _log_action(user_name, "calendar_add", f"{'Birthday' if ev_type == 'birthday' else 'Event'} #{e['id']}: {title} on {ev_date}")
        emoji = "🎂" if ev_type == "birthday" else "📅"
        if ev_type == "birthday":
            msg = (f"{emoji} *Birthday Add Ho Gaya! MashAllah!* 🎉\n\n"
                   f"#{e['id']} 🎂 *{ev_date}*\n👤 {title}\n\n"
                   f"✅ Ek din pehle remind karunga!\n📊 Sheets mein save!")
        else:
            msg = (f"{emoji} *Event Add Ho Gaya!* ✅\n\n"
                   f"#{e['id']} 📅 *{ev_date}*\n📌 {title}\n\n"
                   f"✅ Ek din pehle remind karunga!\n📊 Sheets mein save!")
        await update.message.reply_text(msg, parse_mode="Markdown")
 
    elif action_type == "add_bill":
        name = params.get("name", "Bill")
        amount = params.get("amount", 0)
        due_day = params.get("due_day", 0)
        b = bills.add(name, amount, due_day)
        _log_action(user_name, "bill_add", f"#{b['id']}: {name} Rs.{amount} due {due_day} tarikh")
        await update.message.reply_text(
            f"💳 *Bill Add Ho Gaya! Alhamdulillah!* ✅\n\n"
            f"#{b['id']} *{name}*\n"
            f"💰 Rs.{amount}\n📅 Due: {due_day} tarikh\n\n"
            f"📊 Sheets mein save!\n"
            f"_(Due 0 = not set; /billadd se sahi due day set karo)_",
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
                    f"🔥 *{habit_name} done! MashAllah!* 🎉\n\n"
                    f"{streak} din ka streak! 💪",
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
            f"💧 *{ml}ml Paani!*\n\n"
            f"Total: {total}/{goal_ml}ml ({pct}%)\n\n"
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
                f"🧠 *Memory Mein Save Ho Gaya!* ✅ [{category}]\n\n"
                f"_{text[:150]}_\n\n"
                f"InshAllah yaad rakhunga! 💡",
                parse_mode="Markdown"
            )
        except Exception:
            diary.add(f"[Memory] [{category}] {text}")
            _log_action(user_name, "memory_save_fallback", f"Saved as diary [{category}]: {text[:80]}")
            await update.message.reply_text(
                f"🧠 *Note Save Ho Gaya!* ✅ [{category}]\n\n"
                f"_{text[:150]}_",
                parse_mode="Markdown"
            )
 
    else:
        # ════════════════════════════════════════════════
        # STEP 3: GEMINI AI CHAT (dono parsers fail hue)
        # ════════════════════════════════════════════════
        prompt = (
            build_system_prompt(chat_id)
            + f"\n\nUSER SAID: {user_msg}\n\n"
            "🚨 HINGLISH MEIN REPLY DO (2-3 lines, Muslim phrases use karo):"
        )
 
        reply = call_gemini(prompt)
 
        if not reply:
            reply = (
                "☪️ Assalamualaikum! Batao kya help chahiye?\n"
                "Tasks, reminders, kharcha, diary, calendar, bills?"
            )
 
        # English greeting fix
        english_greetings = [
            "Hello", "Hi", "Hey",
            "Good morning", "Good evening", "Good afternoon"
        ]
        for eng in english_greetings:
            if reply.lower().startswith(eng.lower()):
                reply = "Assalamualaikum! " + reply[len(eng):].strip()
 
        if not any(
            word in reply.lower()
            for word in ["assalamualaikum", "alaikum", "salam", "alhamdulillah"]
        ):
            reply = "Assalamualaikum! " + reply
 
        _log_action(user_name, "ai_chat", f"Q: {user_msg[:60]} | A: {reply[:60]}")
        await update.message.reply_text(reply, parse_mode="Markdown")
        add_to_context(chat_id, "assistant", reply[:100])
 
    chat_hist.add("assistant", "Reply sent", "Rk")

async def confirm_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global pending_actions
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name or "User"
    
    if query.data == "confirm_add":
        pending = pending_actions.get(chat_id)
        if pending:
            action = pending["action"]
            params = pending["params"]
            
            # ── FIRST: Stop ALL smart reminders for this user ──
            try:
                for smart_r in smart_reminders.get_active_smart():
                    if smart_r.get("chat_id") == chat_id:
                        _acknowledge_smart_chain(smart_r["id"])
                        log.info(f"Stopped smart reminder #{smart_r['id']} before adding new one")
            except Exception as e:
                log.error(f"Error cleaning smart reminders: {e}")
            
            # Execute based on action
            if action == "remind":
                r = reminders.add(chat_id, params["text"], params["due"])
                
                try:
                    remind_dt = datetime.strptime(params["due"], "%Y-%m-%d %H:%M:%S")
                    date_display = remind_dt.strftime("%d %b %Y")
                    time_display = remind_dt.strftime("%I:%M %p")
                    await query.edit_message_text(
                        f"✅ *Reminder Set!* 🎉\n\n"
                        f"📝 *{params['text']}*\n"
                        f"🕐 *{time_display}* — 📅 *{date_display}*\n"
                        f"📌 ID #{r['id']}\n\n"
                        f"_InshAllah yaad dilaaunga!_",
                        parse_mode="Markdown"
                    )
                except:
                    await query.edit_message_text(
                        f"✅ *Reminder Set!* 🎉\n\n"
                        f"📝 {params['text']}\n"
                        f"⏰ {params['due']}\n"
                        f"📌 ID #{r['id']}",
                        parse_mode="Markdown"
                    )
                _log_action(user_name, "reminder_set", f"#{r['id']}: {params['text']} at {params['due']}")
            
            elif action == "task":
                t = tasks.add(params["title"])
                await query.edit_message_text(
                    f"✅ *Task Add Ho Gaya!* 🎉\n\n"
                    f"📌 #{t['id']} *{t['title']}*\n\n"
                    f"InshAllah ho jayega! 💪",
                    parse_mode="Markdown"
                )
                _log_action(user_name, "task_add", f"#{t['id']}: {t['title']}")
            
            elif action == "diary":
                diary.add(params["text"])
                await query.edit_message_text(
                    f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n"
                    f"_{params['text'][:200]}_\n\n"
                    f"📊 Sheets mein bhi backup ho gaya!",
                    parse_mode="Markdown"
                )
                _log_action(user_name, "diary_write", "Entry saved")
            
            elif action == "expense":
                expenses.add(params["amount"], params["desc"])
                await query.edit_message_text(
                    f"💸 *Kharcha Add!* ✅\n\n"
                    f"Rs.{params['amount']} — {params['desc']}\n"
                    f"💰 Aaj total: Rs.{expenses.today_total()}",
                    parse_mode="Markdown"
                )
                _log_action(user_name, "expense_add", f"Rs.{params['amount']} on {params['desc']}")
            
            elif action == "habit":
                h = habits.add(params["name"])
                await query.edit_message_text(
                    f"🏃 *Habit Add Ho Gaya!* 🎉\n\n"
                    f"#{h['id']} *{h['name']}*\n\n"
                    f"InshAllah roz karoge! 💪",
                    parse_mode="Markdown"
                )
                _log_action(user_name, "habit_add", f"#{h['id']}: {h['name']}")
            
            elif action == "habit_done":
                keyword = params.get("keyword", "")
                if keyword.isdigit():
                    ok, streak = habits.log(int(keyword))
                    habit_name = f"#{keyword}"
                else:
                    ok, streak, h = habits.log_by_name(keyword)
                    habit_name = h["name"] if h else keyword
                if ok:
                    await query.edit_message_text(
                        f"🔥 *{habit_name} Done! MashAllah!* 🎉\n\n"
                        f"{streak} din ka streak! 💪",
                        parse_mode="Markdown"
                    )
                    _log_action(user_name, "habit_done", f"'{habit_name}' done | streak: {streak}")
                else:
                    await query.edit_message_text(
                        f"✅ *{habit_name}* aaj pehle hi log ho chuka hai!",
                        parse_mode="Markdown"
                    )
            
            elif action == "calendar":
                e = calendar.add(params["title"], params["date"], "", "", "", params["type"])
                emoji = "🎂" if params["type"] == "birthday" else "📅"
                await query.edit_message_text(
                    f"{emoji} *Event Add Ho Gaya!* ✅\n\n"
                    f"#{e['id']} 📅 *{params['date']}*\n"
                    f"📌 {params['title']}\n\n"
                    f"✅ Ek din pehle remind karunga!",
                    parse_mode="Markdown"
                )
                _log_action(user_name, "calendar_add", f"{params['type']} #{e['id']}: {params['title']}")
            
            elif action == "bill":
                b = bills.add(params["name"], params["amount"], params["due_day"])
                await query.edit_message_text(
                    f"💳 *Bill Add Ho Gaya! Alhamdulillah!* ✅\n\n"
                    f"#{b['id']} *{params['name']}*\n"
                    f"💰 Rs.{params['amount']}\n"
                    f"📅 Due: {params['due_day'] if params['due_day'] else 'Not set'} tarikh\n\n"
                    f"📊 Sheets mein save!",
                    parse_mode="Markdown"
                )
                _log_action(user_name, "bill_add", f"#{b['id']}: {params['name']}")
            
            elif action == "water":
                water.add(params["ml"])
                total = water.today_total()
                goal = water.goal()
                pct = int(total / goal * 100) if goal else 0
                filled = min(pct // 20, 5)
                bar = "🟦" * filled + "⬜" * (5 - filled)
                await query.edit_message_text(
                    f"💧 *+{params['ml']}ml Paani!* ✅\n\n"
                    f"Total: {total}/{goal}ml\n"
                    f"{bar} {pct}%",
                    parse_mode="Markdown"
                )
                _log_action(user_name, "water_log", f"Added {params['ml']}ml")
            
            elif action == "memory":
                category = auto_tag_memory(params["text"])
                memory.add(params["text"], category=category)
                await query.edit_message_text(
                    f"🧠 *Memory Save Ho Gaya!* ✅\n\n"
                    f"🏷️ Category: *{category}*\n"
                    f"_{params['text'][:200]}_\n\n"
                    f"InshAllah yaad rakhunga! 💡",
                    parse_mode="Markdown"
                )
                _log_action(user_name, "memory_save", f"[{category}]: {params['text'][:80]}")
              
            # ── SAFE DELETION ──
            if chat_id in pending_actions:
                del pending_actions[chat_id]   # ← YEH LINE SAHI INDENT PE HONI CHAHIYE
    
    else:  # cancel
        await query.edit_message_text("❌ *Cancelled!*", parse_mode="Markdown")
        if chat_id in pending_actions:
            del pending_actions[chat_id]
# ════════════════════════════════════════════════════
# STARTUP NOTIFICATION FUNCTION (main se BAHAR)
# ════════════════════════════════════════════════════

async def send_startup_notification(context: ContextTypes.DEFAULT_TYPE):
    """Send startup message to all known chat IDs"""
    try:
        chat_ids = set()
        for r in reminders.get_all():
            if r.get("chat_id"):
                try:
                    chat_ids.add(int(r["chat_id"]))
                except:
                    pass
        
        # Voice notes se bhi chat_ids collect karo
        try:
            from secure_data_manager import voice_notes
            for vn in voice_notes.get_all():
                if vn.get("chat_id"):
                    chat_ids.add(int(vn["chat_id"]))
        except:
            pass

        if not chat_ids:
            # Instead of warning, just log info
            log.info("No active chats yet - waiting for first user interaction")
            return

        for cid in chat_ids:
            try:
                await context.bot.send_message(
                    chat_id=cid,
                    text="🟢 Rk Bot v19.0 Active!\n\n✅ All systems running\n✅ Confirmation feature active\n✅ Date parsing for reminders\n\nAlhamdulillah!"
                )
                log.info(f"Startup notification sent to {cid}")
            except Exception as e:
                log.error(f"Failed to send startup notification to {cid}: {e}")
    except Exception as e:
        log.error(f"Startup notification error: {e}")


# ════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════

def main():
    """Main entry point - initialize and start the bot"""
    cleanup_before_start()

    log.info("=" * 60)
    log.info("Rk Bot v18.5 COMPLETE | ALL v17 Features + ALL v18.x Improvements + ALL Fixes")
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
            async def send_channel_startup(context):
                await channel_logger.log_startup()

            if app.job_queue:
                app.job_queue.run_once(send_channel_startup, 3)
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

    app.add_handler(CallbackQueryHandler(handle_ok_button, pattern=r"^(ok_|smart_complete_|smart_snooze5_|smart_again_|quick_done_|postpone_|quick_del_|habit_quick_)"))
    app.add_handler(CallbackQueryHandler(confirm_callback, pattern=r"^confirm_"))
    # Natural language message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ── Job Queue Setup ──
    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=10)
        log.info("⏰ Reminder job scheduled (every 60s) - checks BOTH normal AND smart reminders")

        app.job_queue.run_repeating(smart_daily_summary, interval=60, first=30)
        log.info("📊 Smart Daily Summary checker scheduled (every 60s)")

        app.job_queue.run_repeating(proactive_followup_job, interval=10800, first=300)
        log.info("🔄 Proactive followup scheduled (every 3 hours)")

        app.job_queue.run_repeating(weekly_review_job, interval=3600, first=120)
        log.info("📊 Weekly review checker scheduled (every hour)")

        app.job_queue.run_repeating(expense_insight_job, interval=21600, first=180)
        log.info("💰 Expense insight checker scheduled (every 6 hours)")

        app.job_queue.run_once(send_startup_notification, 5)
        log.info("📢 Startup notification scheduled (5 sec delay)")

    else:
        log.warning("⚠️ JobQueue not available - reminders and daily summaries disabled!")

    # ── Start Bot ──
    log.info("✅ Bot ready! Starting polling...")
    log.info("📊 Daily summaries will now trigger automatically every 60 seconds check")
    log.info("📌 reminder_job checks BOTH reminders (normal) AND smart_reminders stores")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True, close_loop=False)


if __name__ == "__main__":
    main()
