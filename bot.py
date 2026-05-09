#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PERSONAL AI ASSISTANT BOT — RK v4
Changes:
  - Bot naam: RK
  - Islamic Hinglish replies (Assalamualaikum, Inshallah, MashaAllah, etc.)
  - Start message: 3 lines, no examples
  - DIRECT keyword matching: diary/task/reminder/alarm/yaad dilana/bata dena/
    kharcha/goal/note/save karna — aage jo likha wo SEEDHA action ho
  - Google Sheets: EVERY message/action → Miscellaneous/Daily_Logs tab mein log
  - Logs delete nahi hote, hamesha append hote hain
"""

import os, json, logging, time, asyncio
import urllib.request, ssl
from datetime import datetime, date, timedelta, timezone
import re as _re

from secure_data_manager import (
    memory, tasks, diary, habits, expenses, goals, reminders,
    water, bills, calendar, chat_hist,
    now_ist, today_str, now_str,
    sheets_backup, repo_manager
)

ssl._create_default_https_context = ssl._create_unverified_context

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

# ================================================================
# CONFIG
# ================================================================
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")
DIARY_PASSWORD   = "Rk1996"
DIARY_AWAIT_PASS = 0
DIARY_AWAIT_TEXT = 1
BOT_NAME         = "RK"

if not TELEGRAM_TOKEN:
    print("❌ TELEGRAM_TOKEN not set!")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ================================================================
# SHEETS: LOG EVERYTHING — NEVER DELETES
# ================================================================
def log_to_sheets(action_type, user_msg, result=""):
    """Log EVERY interaction to Miscellaneous/Daily_Logs tab."""
    try:
        details = f"[{action_type.upper()}] {user_msg[:150]} | {str(result)[:100]}"
        sheets_backup.log_event(action_type.upper(), details)
    except Exception as e:
        log.warning(f"Sheets log error: {e}")

# ================================================================
# GEMINI API
# ================================================================
GEMINI_MODELS     = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
GEMINI_URL        = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
_last_gemini_call = 0

def call_gemini(prompt, max_tokens=400):
    global _last_gemini_call
    if not GEMINI_API_KEY:
        return None
    elapsed = time.time() - _last_gemini_call
    if elapsed < 2:
        time.sleep(2 - elapsed)
    _last_gemini_call = time.time()
    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.75, "maxOutputTokens": max_tokens}
    }).encode("utf-8")
    for model in GEMINI_MODELS:
        try:
            url = GEMINI_URL.format(model=model, key=GEMINI_API_KEY)
            req = urllib.request.Request(url, data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            log.warning(f"Gemini error ({model}): {e}")
    return None

# ================================================================
# SYSTEM PROMPT — Islamic Hinglish
# ================================================================
def build_system_prompt():
    tp     = tasks.today_pending()
    hd, hp = habits.today_status()
    return (
        f"Tu ek Personal AI Assistant hai — tera naam '{BOT_NAME}' hai.\n"
        f"Tu ek Muslim assistant hai. Hamesha Islamic Hinglish mein baat kar.\n"
        f"Greetings mein 'Assalamualaikum' use karo.\n"
        f"Reply mein kabhi kabhi 'Inshallah', 'Alhamdulillah', 'MashaAllah', 'SubhanAllah', 'Jazakallah' use karo.\n"
        f"'Namaste' kabhi mat bolna — hamesha Islamic greetings.\n"
        f"Hamesha SHORT jawab do — 2-3 lines maximum. Hinglish mein.\n\n"
        f"⚠️ TIME: {now_ist().strftime('%A, %d %b — %I:%M %p')} IST\n"
        f"📋 Tasks pending: {len(tp)}\n"
        f"💪 Habits: {len(hd)} done, {len(hp)} pending\n"
        f"💰 Aaj kharcha: ₹{expenses.today_total()}\n"
        f"💧 Paani: {water.today_total()}ml/{water.goal()}ml\n"
        f"⏰ Reminders: {len(reminders.all_active())} active\n"
    )

# ================================================================
# ALARM KEYBOARD
# ================================================================
def alarm_keyboard(rid):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ OK — Alarm Band Karo", callback_data=f"ok_{rid}")
    ]])

# ================================================================
# KEYWORD MAP — Order matters (longer phrases first for accuracy)
# ================================================================
KEYWORD_MAP = [
    # DIARY (check these before generic "add")
    ("dairy mein likho",    "diary"),
    ("diary mein likho",    "diary"),
    ("dairy me likho",      "diary"),
    ("diary me likho",      "diary"),
    ("dairy mein",          "diary"),
    ("diary mein",          "diary"),
    ("dairy me",            "diary"),
    ("diary me",            "diary"),
    ("add dairy",           "diary"),
    ("add diary",           "diary"),
    ("dairy add",           "diary"),
    ("diary add",           "diary"),
    ("dairy",               "diary"),
    ("diary",               "diary"),
    ("roz ka haal",         "diary"),
    ("journal",             "diary"),

    # REMINDER / ALARM / YAAD
    ("yaad dilana",         "remind"),
    ("yaad dilao",          "remind"),
    ("yaad dila",           "remind"),
    ("yaad kar",            "remind"),
    ("bata dena",           "remind"),
    ("bata do",             "remind"),
    ("set alarm",           "remind"),
    ("alarm set",           "remind"),
    ("reminder set",        "remind"),
    ("reminder",            "remind"),
    ("remind",              "remind"),
    ("alarm",               "remind"),

    # EXPENSE / KHARCHA
    ("kharcha likhna",      "expense"),
    ("likhna kharcha",      "expense"),
    ("paise gaye",          "expense"),
    ("kharcha",             "expense"),
    ("kharch",              "expense"),
    ("spent",               "expense"),
    ("spend",               "expense"),
    ("rupees",              "expense"),
    ("rupay",               "expense"),
    ("rupee",               "expense"),
    ("₹",                   "expense"),

    # GOAL
    ("goal set",            "add_goal"),
    ("goal",                "add_goal"),
    ("target set",          "add_goal"),
    ("target",              "add_goal"),

    # IMPORTANT NOTE / SAVE
    ("aapne paas save",     "memory"),
    ("apne paas save",      "memory"),
    ("aapne paas rakh",     "memory"),
    ("apne paas rakh",      "memory"),
    ("important note",      "memory"),
    ("note kar lo",         "memory"),
    ("note karo",           "memory"),
    ("note kar",            "memory"),
    ("save kar lo",         "memory"),
    ("save karo",           "memory"),
    ("save kar",            "memory"),
    ("yaad rakh",           "memory"),
    ("important",           "memory"),

    # TASK
    ("task add",            "add_task"),
    ("add task",            "add_task"),
    ("task",                "add_task"),
    ("kaam add",            "add_task"),
    ("todo",                "add_task"),

    # WATER
    ("paani piya",          "water"),
    ("pani piya",           "water"),
    ("water piya",          "water"),
    ("glass paani",         "water"),
    ("glass pani",          "water"),
    ("glass water",         "water"),
    ("bottle paani",        "water"),
    ("bottle pani",         "water"),
    ("ml paani",            "water"),
    ("ml pani",             "water"),
    ("ml water",            "water"),
    ("paani pi",            "water"),
    ("pani pi",             "water"),
    ("water pi",            "water"),
]

def extract_keyword_action(user_msg):
    """
    Message mein keyword dhundo.
    Returns: (action_type, text_after_keyword, matched_keyword)
    """
    lower = user_msg.lower().strip()

    for kw, action in KEYWORD_MAP:
        idx = lower.find(kw)
        if idx == -1:
            continue

        # Keyword ke BAAD ka text
        after = user_msg[idx + len(kw):].strip(" :-,।\n")
        # Keyword ke PEHLE ka text
        before = user_msg[:idx].strip(" :-,।\n")

        # Combine before + after (prefer after, add before if meaningful)
        if after and len(after) > 2:
            combined = after
            if before and len(before) > 2 and before.lower() not in [
                "mujhe", "mujhko", "please", "plz", "bhai", "dost", "yaar"
            ]:
                combined = (before + " " + after).strip()
        elif before and len(before) > 2:
            combined = before
        else:
            combined = user_msg  # fallback

        return (action, combined.strip(), kw)

    return (None, user_msg, None)


def parse_time_from_msg(lower, now):
    """Message se time string nikalo."""
    m_min = _re.search(r'(\d+)\s*(min|minute|minutes)\b', lower)
    m_hr  = _re.search(r'(\d+)\s*(ghanta|ghante|hour|hours|hr)\b', lower)
    m_hm  = _re.search(r'(\d{1,2}):(\d{2})', lower)
    m_baj = _re.search(r'(\d{1,2})\s*baje\b', lower)

    if m_min:
        return (now + timedelta(minutes=int(m_min.group(1)))).strftime("%H:%M")
    elif m_hr:
        return (now + timedelta(hours=int(m_hr.group(1)))).strftime("%H:%M")
    elif m_hm:
        return f"{int(m_hm.group(1)):02d}:{int(m_hm.group(2)):02d}"
    elif m_baj:
        return f"{int(m_baj.group(1)):02d}:00"
    return None


def clean_text(text, extra_words=None):
    """Remove filler words from extracted text."""
    fillers = [
        "add kro", "add karo", "add kar", "add", "karo", "kar",
        "likho", "likh do", "likh", "save karo", "save kar", "save",
        "please", "plz", "mujhe", "mujhko", "bhai", "dost", "yaar",
    ]
    if extra_words:
        fillers.extend(extra_words)
    for f in sorted(fillers, key=len, reverse=True):
        text = _re.sub(r'(?i)\b' + _re.escape(f) + r'\b', ' ', text)
    return " ".join(text.split()).strip(" ,-:।")


# ================================================================
# MAIN PARSER
# ================================================================
def parse_user_message(user_msg):
    lower = user_msg.lower().strip()
    now   = now_ist()

    # ── STEP 1: Keyword match ─────────────────────────────────────
    action, remaining, matched_kw = extract_keyword_action(user_msg)

    if action == "diary":
        text = clean_text(remaining, ["mein", "me", "mein likho", "me likho",
                                       "mein add", "me add"])
        if not text or len(text) < 2:
            text = user_msg
        return ("diary", {"text": text})

    elif action == "add_task":
        text = clean_text(remaining)
        if not text or len(text) < 2:
            text = user_msg
        return ("add_task", {"title": text[:100]})

    elif action == "remind":
        ts   = parse_time_from_msg(lower, now)
        text = remaining

        # Remove time phrases from the reminder text
        text = _re.sub(
            r'\d+\s*(min|minute|minutes|ghanta|ghante|hour|hours|hr)\s*(baad|mein|me|ke baad)?',
            '', text, flags=_re.IGNORECASE)
        text = _re.sub(r'\d{1,2}:\d{2}', '', text)
        text = _re.sub(r'\d+\s*baje\b', '', text, flags=_re.IGNORECASE)
        text = clean_text(text, ["alarm", "reminder", "remind", "set karo", "set kar",
                                  "yaad dilana", "yaad dilao", "yaad dila",
                                  "bata dena", "bata do", "lagao", "laga"])
        if not text or len(text) < 2:
            text = user_msg.strip()

        if ts:
            return ("remind", {"time": ts, "text": text})
        else:
            return ("remind_no_time", {"text": text})

    elif action == "expense":
        # Amount extract karo
        m = (_re.search(r'₹\s*(\d+(?:\.\d+)?)', lower) or
             _re.search(r'(\d+(?:\.\d+)?)\s*(?:rs\.?|rupee[s]?|rupay|paisa)', lower) or
             _re.search(r'\b(\d{2,6}(?:\.\d+)?)\b', lower))
        if m:
            amount = float(m.group(1))
            desc   = remaining
            desc   = _re.sub(r'₹\s*\d+(?:\.\d+)?', '', desc)
            desc   = _re.sub(r'\d+(?:\.\d+)?\s*(?:rs\.?|rupee[s]?|rupay|paisa)?',
                             '', desc, flags=_re.IGNORECASE)
            desc   = clean_text(desc, ["kharcha", "kharch", "spent", "spend",
                                        "rupees", "rupay", "rupee", "paisa",
                                        "pe", "par", "mein", "me", "ka", "ki", "ke",
                                        "pay kiya", "liya", "diya", "lagay", "laga"])
            if not desc or len(desc) < 2:
                desc = "Kharcha"
            return ("expense", {"amount": amount, "desc": desc})
        # Keyword tha but amount nahi mila
        return ("chat", {"text": user_msg})

    elif action == "add_goal":
        text = clean_text(remaining, ["goal", "set", "target", "banao", "bana",
                                       "mera", "meri", "chahiye"])
        if not text or len(text) < 2:
            text = user_msg
        return ("add_goal", {"title": text})

    elif action == "memory":
        text = clean_text(remaining, ["note", "save", "yaad", "rakh", "important",
                                       "aapne", "apne", "paas", "karo", "kar"])
        if not text or len(text) < 2:
            text = user_msg
        return ("save_note", {"text": text})

    elif action == "water":
        m  = _re.search(r'(\d+)\s*(ml|glass|bottle)', lower)
        ml = 250
        if m:
            val, unit = int(m.group(1)), m.group(2)
            if   "glass"  in unit: ml = val * 250
            elif "bottle" in unit: ml = val * 500
            else:                  ml = val
        return ("water", {"ml": ml})

    # ── STEP 2: Natural "X min/ghante baad Y" without keyword ─────
    baad_pattern = _re.search(
        r'(\d+)\s*(min|minute|ghanta|ghante|hour|hr)\s*(baad|mein|me|ke baad)', lower
    )
    if baad_pattern:
        ts = parse_time_from_msg(lower, now)
        if ts:
            text = user_msg
            text = _re.sub(
                r'\d+\s*(min|minute|ghanta|ghante|hour|hr)\s*(baad|mein|me|ke baad)?',
                '', text, flags=_re.IGNORECASE)
            text = " ".join(text.split()).strip(" ,-:")
            if not text:
                text = "Reminder"
            return ("remind", {"time": ts, "text": text})

    # ── STEP 3: Fallback AI chat ──────────────────────────────────
    return ("chat", {"text": user_msg})


# ================================================================
# COMMANDS
# ================================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(
        f"🕌 Assalamualaikum {name}!\n"
        f"Main aapka Personal AI Assistant *{BOT_NAME}* hoon! 🤖\n"
        f"/help — sab commands",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📋 *{BOT_NAME} — COMMANDS*\n\n"
        "🗣 *Seedha bolo (keywords):*\n"
        "  `diary aaj mausam aacha tha`\n"
        "  `task meeting karni hai`\n"
        "  `kharcha 150 chai nashta`\n"
        "  `5 min baad paani pina hai`\n"
        "  `reminder 6 baje namaz`\n"
        "  `note karo ye link important`\n"
        "  `goal quran roz parhna`\n"
        "  `250ml paani piya`\n\n"
        "⚡ *Direct Commands:*\n"
        "`/task <naam>` — task add\n"
        "`/done <id>` — task complete\n"
        "`/habit <naam>` — habit add\n"
        "`/hdone <id>` — habit done\n"
        "`/remind 30m <text>` — reminder\n"
        "`/kharcha 100 <desc>` — expense\n"
        "`/water 250` — water log\n"
        "`/diary` — diary (password)\n"
        "`/save <text>` — quick diary\n"
        "`/briefing` — daily summary\n"
        "`/status` — system status",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    github_ok = "✅ Connected" if repo_manager.is_connected else "⚠️ Local only"
    sheets_ok = "✅ Connected" if sheets_backup.connected   else "❌ NOT connected"
    await update.message.reply_text(
        f"📊 *{BOT_NAME} STATUS*\n\n"
        f"🤖 Bot: ✅ Running\n"
        f"🔐 GitHub: {github_ok}\n"
        f"📊 Google Sheets: {sheets_ok}\n\n"
        f"📁 *Data:*\n"
        f"📋 Tasks: {len(tasks.all_tasks())} total, {len(tasks.pending())} pending\n"
        f"📖 Diary: {sum(len(v) for v in diary.get_all_entries().values())} entries\n"
        f"💰 Today kharcha: ₹{expenses.today_total()}\n"
        f"💪 Habits: {len(habits.all())}\n"
        f"⏰ Active reminders: {len(reminders.all_active())}\n"
        f"💧 Water: {water.today_total()}/{water.goal()}ml",
        parse_mode="Markdown"
    )

async def cmd_datacheck(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    github_ok = repo_manager.is_connected
    sheets_ok = sheets_backup.connected
    total_diary     = sum(len(v) for v in diary.get_all_entries().values())
    total_tasks     = len(tasks.all_tasks())
    total_expenses  = len(expenses.store.data.get("list", []))
    total_habits    = len(habits.all())
    total_reminders = len(reminders.get_all())
    sheets_live = "❓"
    if sheets_ok:
        try:
            ok = sheets_backup.log_event("DATACHECK", f"Check at {now_ist().strftime('%H:%M')}")
            sheets_live = "✅ PASS — Sheets kaam kar raha!" if ok else "❌ FAIL"
        except Exception as e:
            sheets_live = f"❌ {e}"
    await update.message.reply_text(
        f"🔍 *DATA CHECK — Alhamdulillah*\n{'═'*25}\n\n"
        f"📖 Diary: {total_diary} entries\n"
        f"📋 Tasks: {total_tasks}\n"
        f"💰 Expenses: {total_expenses}\n"
        f"💪 Habits: {total_habits}\n"
        f"⏰ Reminders: {total_reminders}\n\n"
        f"🔐 GitHub: {'✅ Safe' if github_ok else '⚠️ Local only'}\n"
        f"📊 Sheets: {'✅ Sync' if sheets_ok else '❌ Disconnected'}\n\n"
        f"🧪 Live Test: {sheets_live}",
        parse_mode="Markdown"
    )

async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(
                f"📋 *Pending ({len(pending)}):*\n{lines}\n\n_/done <id>_",
                parse_mode="Markdown")
        else:
            await update.message.reply_text("📋 Koi task nahi. `/task kaam naam`", parse_mode="Markdown")
        return
    t = tasks.add(" ".join(ctx.args))
    log_to_sheets("TASK_ADD", " ".join(ctx.args), f"#{t['id']}")
    await update.message.reply_text(
        f"✅ *Task #{t['id']}! Inshallah pura hoga.*\n📋 {t['title']}",
        parse_mode="Markdown")

async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(
                f"📋 *Pending:*\n{lines}\n\n_/done <id>_", parse_mode="Markdown")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t:
            log_to_sheets("TASK_DONE", t['title'], f"#{t['id']}")
            await update.message.reply_text(
                f"🎉 *Alhamdulillah! Task complete!* ✅\n_{t['title']}_", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Task nahi mili!")
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        all_h = habits.all()
        if all_h:
            hd, _ = habits.today_status()
            done_ids = [h['id'] for h in hd]
            lines = "\n".join(
                f"{'✅' if h['id'] in done_ids else '⬜'} #{h['id']} {h['name']} 🔥{h.get('streak',0)}"
                for h in all_h)
            await update.message.reply_text(
                f"💪 *Habits:*\n{lines}\n\n_/hdone <id>_", parse_mode="Markdown")
        else:
            await update.message.reply_text("💪 `/habit Naam`", parse_mode="Markdown")
        return
    h = habits.add(" ".join(ctx.args))
    log_to_sheets("HABIT_ADD", " ".join(ctx.args), f"#{h['id']}")
    await update.message.reply_text(f"💪 Habit #{h['id']}: {h['name']}")

async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            lines = "\n".join(f"⬜ #{h['id']} {h['name']}" for h in pending)
            await update.message.reply_text(
                f"💪 *Pending:*\n{lines}\n\n_/hdone <id>_", parse_mode="Markdown")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        if ok:
            log_to_sheets("HABIT_DONE", f"#{ctx.args[0]}", f"streak={streak}")
            await update.message.reply_text(
                f"💪 *MashaAllah!* 🔥 {streak} day streak!", parse_mode="Markdown")
        else:
            await update.message.reply_text("✅ Aaj pehle se ho gayi!")
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        today_list = expenses.get_by_date(today_str())
        if today_list:
            lines = "\n".join(f"₹{e['amount']} - {e['desc']}" for e in today_list[-10:])
            await update.message.reply_text(
                f"💰 *Aaj ka kharcha:*\n{lines}\n*Total: ₹{expenses.today_total()}*",
                parse_mode="Markdown")
        else:
            await update.message.reply_text("💰 `/kharcha 100 Chai`", parse_mode="Markdown")
        return
    try:
        amount = float(ctx.args[0])
        desc   = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        log_to_sheets("EXPENSE", f"₹{amount} {desc}", f"total=₹{expenses.today_total()}")
        await update.message.reply_text(
            f"💰 ₹{amount} — {desc}\n📊 Aaj total: ₹{expenses.today_total()}")
    except Exception:
        await update.message.reply_text("❌ `/kharcha 100 Chai`")

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        active = reminders.all_active()
        if active:
            lines = "\n".join(f"#{r['id']} `{r['time']}` — {r['text']}" for r in active)
            await update.message.reply_text(
                f"⏰ *Active:*\n{lines}\n\n_/remind 30m Chai_", parse_mode="Markdown")
        else:
            await update.message.reply_text(
                "⏰ `/remind 30m Chai` ya `/remind 18:00 Namaz`", parse_mode="Markdown")
        return
    time_arg = ctx.args[0].lower()
    text     = " ".join(ctx.args[1:])
    now_t    = now_ist()
    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        remind_at = (now_t + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        parts = time_arg.split(":")
        remind_at = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    else:
        await update.message.reply_text("❌ `/remind 30m Chai` ya `/remind 18:00 Namaz`")
        return
    r = reminders.add(update.effective_chat.id, text, remind_at)
    log_to_sheets("REMINDER_SET", text, f"at {remind_at} #{r['id']}")
    await update.message.reply_text(
        f"✅ *Reminder Set! Inshallah yaad dilaun ga.*\n"
        f"🕐 {remind_at} — {text}\n🆔 #{r['id']}",
        parse_mode="Markdown")

async def cmd_water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ml    = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 250
    total = water.add(ml)
    goal  = water.goal()
    pct   = int(total / goal * 100) if goal else 0
    bar   = "💧" * min(10, pct // 10) + "⬜" * (10 - min(10, pct // 10))
    log_to_sheets("WATER", f"+{ml}ml", f"total={total}ml")
    await update.message.reply_text(f"💧 +{ml}ml\n{bar}\n{total}ml / {goal}ml ({pct}%)")

async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n      = now_ist()
    tp     = tasks.today_pending()
    hd, hp = habits.today_status()
    await update.message.reply_text(
        f"🌅 *Assalamualaikum! Aaj ka Briefing*\n"
        f"📅 {n.strftime('%d %b %Y')} — {n.strftime('%I:%M %p')}\n\n"
        f"📋 Pending tasks: {len(tp)}\n"
        f"💪 Habits: {len(hd)}/{len(hd)+len(hp)} done\n"
        f"💰 Kharcha: ₹{expenses.today_total()}\n"
        f"💧 Water: {water.today_total()}/{water.goal()}ml\n\n"
        f"_Inshallah aaj ka din aacha guzre!_ 🤲",
        parse_mode="Markdown")

async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📖 `/save Aaj ka din...`")
        return
    text = " ".join(ctx.args)
    diary.add(text)
    log_to_sheets("DIARY_SAVE", text, "saved")
    await update.message.reply_text(
        f"📖 *Diary save! Alhamdulillah* ✅\n_{text[:100]}_",
        parse_mode="Markdown")

async def cmd_delremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        try:
            reminders.delete(int(ctx.args[0]))
            await update.message.reply_text("🗑 Reminder delete ho gaya!")
        except Exception:
            await update.message.reply_text("❌ Invalid ID!")
    else:
        await update.message.reply_text("❌ `/delremind <id>`")

async def cmd_snooze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmd_name = update.message.text.split()[0].lstrip("/").lower()
    mins = {"snooze5": 5, "snooze10": 10, "snooze30": 30, "snooze60": 60}.get(cmd_name, 10)
    if not ctx.args:
        await update.message.reply_text(f"⏸️ `/{cmd_name} <id>`", parse_mode="Markdown")
        return
    try:
        rid    = int(ctx.args[0])
        target = reminders.get_by_id(rid)
        if not target:
            await update.message.reply_text(f"❌ #{rid} nahi mila!")
            return
        reminders.acknowledge(rid, f"Snoozed {mins}min")
        new_time = (now_ist() + timedelta(minutes=mins)).strftime("%H:%M")
        new_rem  = reminders.add(target["chat_id"], f"🔁 {target['text']}", new_time, "once")
        log_to_sheets("SNOOZE", target['text'], f"{mins}min → #{new_rem['id']}")
        await update.message.reply_text(
            f"⏸️ *Snoozed! Inshallah {mins} min baad bajega.*\n🆔 #{new_rem['id']}",
            parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")

# ================================================================
# DIARY CONVERSATION
# ================================================================
async def cmd_diary_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or []
    if not args:
        ctx.user_data["diary_mode"] = "view_today"
    else:
        first = args[0].lower()
        ctx.user_data["diary_mode"] = (
            "write"     if first == "write" else
            "view_week" if first == "week"  else
            "view_all"  if first == "all"   else "write"
        )
        if ctx.user_data["diary_mode"] == "write":
            ctx.user_data["diary_pending_text"] = " ".join(args[1:]) if len(args) > 1 else ""
    await update.message.reply_text(
        "🔐 *Password daalo:*\n_/cancel se bahar_", parse_mode="Markdown")
    return DIARY_AWAIT_PASS

async def diary_password_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END
    entered = update.message.text.strip()
    try: await update.message.delete()
    except Exception: pass
    if entered != DIARY_PASSWORD:
        await update.effective_chat.send_message("❌ *Galat Password!*", parse_mode="Markdown")
        return ConversationHandler.END
    mode = ctx.user_data.get("diary_mode", "view_today")
    if mode == "write" and not ctx.user_data.get("diary_pending_text"):
        await update.effective_chat.send_message(
            "✏️ *Diary mein kya likhna hai?*\n_/cancel_", parse_mode="Markdown")
        return DIARY_AWAIT_TEXT
    elif mode == "write":
        text = ctx.user_data.get("diary_pending_text", "")
        diary.add(text)
        log_to_sheets("DIARY", text, "via /diary")
        await update.effective_chat.send_message(
            f"📖 *Save! Alhamdulillah* ✅\n_{text[:100]}_", parse_mode="Markdown")
        return ConversationHandler.END
    else:
        count = sum(len(v) for v in diary.get_all_entries().values())
        await update.effective_chat.send_message(
            f"📖 *Total diary entries: {count}*", parse_mode="Markdown")
        return ConversationHandler.END

async def diary_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END
    text = update.message.text.strip()
    try: await update.message.delete()
    except Exception: pass
    diary.add(text)
    log_to_sheets("DIARY", text, "via /diary input")
    await update.effective_chat.send_message(
        f"📖 *Save! Alhamdulillah* ✅\n_{text[:100]}_", parse_mode="Markdown")
    return ConversationHandler.END

async def diary_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Diary band.")
    return ConversationHandler.END

# ================================================================
# ALARM JOB
# ================================================================
async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now = now_ist()
    if now.hour == 0 and now.minute <= 1:
        reminders.reset_daily()
        return

    for r in reminders.due_now():
        await _send_alarm(context, r)

    for r in reminders.all_active():
        if r.get("fired_today", False) and not r.get("acknowledged", False):
            await _send_alarm(context, r)

async def _send_alarm(context, r):
    try:
        count      = r.get("fire_count", 0)
        repeat_msg = f"\n🔁 *{count+1}vi baar — OK dabao!*" if count > 0 else ""
        alert = (
            f"🔔🔔🔔 *ALARM!* 🔔🔔🔔\n"
            f"{'═'*22}\n"
            f"⏰ *{r['time']} BAJ GAYE!*\n"
            f"{'═'*22}\n\n"
            f"📢 *{r['text'].upper()}*\n"
            f"{repeat_msg}\n\n"
            f"⏸️ `/snooze5 {r['id']}` | `/snooze10 {r['id']}`\n"
            f"🗑 `/delremind {r['id']}`"
        )
        await context.bot.send_message(
            chat_id=int(r["chat_id"]), text=alert,
            reply_markup=alarm_keyboard(r["id"]), parse_mode="Markdown"
        )
        reminders.mark_fired(r["id"])
        log_to_sheets("ALARM_RING", r['text'], f"at {r['time']} ring#{count+1}")
    except Exception as e:
        log.error(f"❌ Alarm error #{r.get('id','?')}: {e}")

# ================================================================
# OK BUTTON
# ================================================================
async def handle_ok_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Alarm band!")
    if not query.data.startswith("ok_"):
        return
    try:
        rid = int(query.data.split("_")[1])
        if reminders.acknowledge(rid, "User pressed OK"):
            await query.edit_message_text(
                "✅ *Alarm band! Jazakallah Khair.* 🔕", parse_mode="Markdown")
            log_to_sheets("ALARM_OK", f"#{rid}", "stopped by user")
        else:
            await query.edit_message_text("⚠️ Pehle se band hai.")
    except Exception as e:
        log.error(f"OK button error: {e}")

# ================================================================
# MESSAGE HANDLER
# ================================================================
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_msg = update.message.text.strip()
    if user_msg.startswith("/"):
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    action_type, params = parse_user_message(user_msg)

    log.info(f"📥 '{user_msg[:60]}' → 🎯 {action_type} {params}")

    # Log EVERY message to Sheets (append only, never delete)
    log_to_sheets(action_type, user_msg, str(params)[:120])

    if action_type == "remind":
        r = reminders.add(
            update.effective_chat.id,
            params.get("text", "Reminder"),
            params.get("time", "")
        )
        await update.message.reply_text(
            f"✅ *Reminder Set! Inshallah yaad dilaun ga.*\n"
            f"🕐 {params.get('time')} — {params.get('text')}\n"
            f"🆔 #{r['id']} | once",
            parse_mode="Markdown"
        )

    elif action_type == "remind_no_time":
        await update.message.reply_text(
            f"⏰ *Kab yaad dilana hai?* Waqt batao!\n"
            f"Misal: `reminder 5 min baad {params.get('text','')[:30]}`",
            parse_mode="Markdown"
        )

    elif action_type == "add_task":
        t = tasks.add(params.get("title", ""))
        await update.message.reply_text(
            f"✅ *Task add! Inshallah pura hoga.* 📋\n"
            f"#{t['id']} — {t['title']}",
            parse_mode="Markdown"
        )

    elif action_type == "expense":
        expenses.add(params.get("amount", 0), params.get("desc", "Kharcha"))
        await update.message.reply_text(
            f"💰 *₹{params.get('amount')} — {params.get('desc')}*\n"
            f"📊 Aaj total: *₹{expenses.today_total()}*",
            parse_mode="Markdown"
        )

    elif action_type == "diary":
        text = params.get("text", "")
        diary.add(text)
        await update.message.reply_text(
            f"📖 *Diary mein save! Alhamdulillah* ✅\n"
            f"_{text[:120]}_",
            parse_mode="Markdown"
        )

    elif action_type == "add_goal":
        title = params.get("title", "")
        g = goals.add(title)
        await update.message.reply_text(
            f"🎯 *Goal set! Inshallah pura hoga.* 🤲\n"
            f"#{g['id']} — {g['title']}",
            parse_mode="Markdown"
        )

    elif action_type == "save_note":
        text = params.get("text", "")
        memory.add_fact(text)
        await update.message.reply_text(
            f"📌 *Note save ho gaya!*\n_{text[:120]}_",
            parse_mode="Markdown"
        )

    elif action_type == "water":
        ml    = params.get("ml", 250)
        total = water.add(ml)
        goal  = water.goal()
        pct   = int(total / goal * 100) if goal else 0
        bar   = "💧" * min(10, pct // 10) + "⬜" * (10 - min(10, pct // 10))
        await update.message.reply_text(
            f"💧 *+{ml}ml! Alhamdulillah*\n{bar}\n{total}ml / {goal}ml ({pct}%)",
            parse_mode="Markdown"
        )

    else:  # AI chat
        prompt = build_system_prompt() + f"\n\nUser: {user_msg}\n\nShort Islamic Hinglish reply (2-3 lines max):"
        reply  = call_gemini(prompt)
        if not reply:
            reply = _smart_fallback(user_msg)
        await update.message.reply_text(reply, parse_mode="Markdown")

    chat_hist.add("user",      user_msg, update.effective_user.first_name or "User")
    chat_hist.add("assistant", f"Action: {action_type}", BOT_NAME)


def _smart_fallback(user_msg):
    msg = user_msg.lower()
    n   = now_ist()
    if any(w in msg for w in ["time", "kitne baje", "waqt", "time kya"]):
        return f"⏰ Abhi *{n.strftime('%I:%M %p')}* IST hai."
    if any(w in msg for w in ["date", "tarikh", "aaj kya"]):
        return f"📅 *{n.strftime('%A, %d %B %Y')}*"
    if any(w in msg for w in ["hello", "hi", "assalam", "walekum", "salam", "aadab"]):
        return f"🕌 *Wa Alaikum Assalam!* {BOT_NAME} hazir hai. Kya madad karun?"
    if any(w in msg for w in ["kaise ho", "kaisa hai", "how are", "theek ho"]):
        return f"😊 *Alhamdulillah, sab theek!* Aap sunao?"
    if any(w in msg for w in ["shukriya", "thanks", "thank you", "jazakallah", "shukria"]):
        return "🤲 *Jazakallah Khair!* Koi aur kaam ho toh batao."
    return (f"🕌 *Assalamualaikum!* {BOT_NAME} hazir hai.\n"
            "Kya help chahiye? Diary, task, reminder, kharcha — sab kar sakta hoon.")

# ================================================================
# MAIN
# ================================================================
def main():
    log.info("=" * 60)
    log.info(f"🤖 {BOT_NAME} — Personal AI Bot v4 (Islamic Hinglish)")
    log.info(f"⏰ IST: {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"📊 Sheets: {'✅' if sheets_backup.connected else '❌'}")
    log.info(f"🔐 GitHub: {'✅' if repo_manager.is_connected else '⚠️'}")
    log.info("=" * 60)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary_entry)],
        states={
            DIARY_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)],
            DIARY_AWAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_text_input)]
        },
        fallbacks=[CommandHandler("cancel", diary_cancel)],
    ))

    for cmd, handler in [
        ("start",      cmd_start),
        ("help",       cmd_help),
        ("status",     cmd_status),
        ("datacheck",  cmd_datacheck),
        ("task",       cmd_task),
        ("done",       cmd_done),
        ("habit",      cmd_habit),
        ("hdone",      cmd_hdone),
        ("kharcha",    cmd_kharcha),
        ("remind",     cmd_remind),
        ("delremind",  cmd_delremind),
        ("water",      cmd_water),
        ("briefing",   cmd_briefing),
        ("save",       cmd_save),
        ("snooze5",    cmd_snooze),
        ("snooze10",   cmd_snooze),
        ("snooze30",   cmd_snooze),
        ("snooze60",   cmd_snooze),
    ]:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(CallbackQueryHandler(handle_ok_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=10)
        log.info("⏰ Alarm job: every 60s")

    log.info(f"✅ {BOT_NAME} polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
