#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     PERSONAL AI ASSISTANT — BOT ONLY                          ║
║     Data handling data_manager.py se hota hai                  ║
║     Aap is file mein changes kar sakte ho                      ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, json, logging, time, asyncio, random
import urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta, timezone
import re as _re

# Import data manager (YEH KABHI CHANGE MAT KARNA)
from data_manager import (
    memory, tasks, diary, habits, expenses, goals, reminders, 
    water, bills, calendar, chat_hist, now_ist, today_str, now_str,
    GoogleSheetsBackup, ALL_STORES
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
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", os.environ.get("Google_CREDS_JSON", ""))

DIARY_PASSWORD = "Rk1996"
DIARY_AWAIT_PASS = 0
DIARY_AWAIT_TEXT = 1

if not TELEGRAM_TOKEN:
    log.error("❌ TELEGRAM_TOKEN not set!")
    exit(1)

# ================================================================
# LOGGING
# ================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ================================================================
# GOOGLE SHEETS BACKUP INSTANCE
# ================================================================
google_sheets = GoogleSheetsBackup(GOOGLE_CREDS_JSON) if GOOGLE_CREDS_JSON else None

async def backup_to_sheets():
    """Backup all data to Google Sheets (doesn't delete existing)"""
    if not google_sheets or not google_sheets.sheet:
        log.warning("⚠️ Cannot backup: Sheets not connected")
        return "❌ Sheets not connected"
    
    try:
        backup_data = {}
        for name, data_func in ALL_STORES.items():
            backup_data[name] = data_func()
        
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, google_sheets.backup_all_data, backup_data)
        
        success_count = sum(1 for v in results.values() if v.startswith("✅"))
        return f"✅ {success_count}/{len(results)} sheets backed up"
    except Exception as e:
        log.error(f"Backup error: {e}")
        return f"❌ Backup error: {str(e)[:100]}"

# ================================================================
# GEMINI API
# ================================================================
GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
_last_gemini_call = 0

def call_gemini(prompt, max_tokens=500, is_action=False):
    global _last_gemini_call
    if not GEMINI_API_KEY:
        return None
    now_t = time.time()
    elapsed = now_t - _last_gemini_call
    if elapsed < 2:
        time.sleep(2 - elapsed)
    _last_gemini_call = time.time()
    
    temp = 0.0 if is_action else 0.75
    tokens = min(max_tokens, 200 if is_action else 700)
    
    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temp, "maxOutputTokens": tokens}
    }).encode("utf-8")
    
    for model in GEMINI_MODELS:
        try:
            url = GEMINI_URL.format(model=model, key=GEMINI_API_KEY)
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            log.warning(f"Gemini error: {e}")
            continue
    return None

# ================================================================
# SYSTEM PROMPT
# ================================================================
def build_system_prompt():
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    exp_t = expenses.today_total()
    wt = water.today_total()
    wg = water.goal()
    
    return f"""Tu mera Personal AI Assistant hai — naam 'Dost'.
⚠️ TIME: {now_ist().strftime('%A, %d %b — %I:%M %p')} IST

📋 Aaj ke tasks: {len(tp)} pending
💪 Habits: {len(hd)} done, {len(hp)} pending
💰 Aaj kharcha: ₹{exp_t}
💧 Paani: {wt}ml/{wg}ml

Hamesha Hindi/Hinglish mein short jawab do (2-3 lines maximum)."""

# ================================================================
# ACTION HANDLERS
# ================================================================

async def handle_remind(update, text, time_str, repeat="once"):
    r = reminders.add(update.effective_chat.id, text, time_str, repeat)
    await update.message.reply_text(f"✅ Reminder set for {time_str}: {text}\nID: #{r['id']}")

async def handle_add_task(update, title):
    t = tasks.add(title)
    await update.message.reply_text(f"✅ Task added: #{t['id']} {t['title']}")

async def handle_complete_task(update, hint):
    pending = tasks.pending()
    matched = next((t for t in pending if str(t["id"]) == hint or (hint and hint in t["title"].lower())), None)
    if matched:
        tasks.complete(matched["id"])
        await update.message.reply_text(f"🎉 Done! ✅ {matched['title']}")
    else:
        await update.message.reply_text("❓ Kaunsa task? ID ya naam batao")

async def handle_expense(update, amount, desc):
    expenses.add(amount, desc)
    await update.message.reply_text(f"💰 ₹{amount} - {desc}\nAaj total: ₹{expenses.today_total()}")

async def handle_diary(update, text):
    diary.add(text)
    await update.message.reply_text(f"📖 Diary saved! ✅\n_{text[:100]}_")

async def handle_habit_add(update, name):
    h = habits.add(name)
    await update.message.reply_text(f"💪 Habit added: #{h['id']} {h['name']}")

async def handle_habit_done(update, keyword):
    if keyword.isdigit():
        ok, streak = habits.log(int(keyword))
        name = f"#{keyword}"
    else:
        ok, streak, h = habits.log_by_name(keyword)
        name = h.name if h else keyword
    if ok:
        await update.message.reply_text(f"💪 {name} done! 🔥 {streak} day streak!")
    else:
        await update.message.reply_text("❓ Kaunsa habit? ID ya naam batao")

async def handle_water(update, ml=250):
    water.add(ml)
    total = water.today_total()
    goal = water.goal()
    await update.message.reply_text(f"💧 +{ml}ml! Total: {total}/{goal}ml")

# ================================================================
# REGEX FALLBACK
# ================================================================
def parse_user_message(user_msg):
    lower = user_msg.lower().strip()
    now = now_ist()
    
    # Reminder detection
    remind_words = ["remind", "reminder", "alarm", "yaad dilana", "bata dena"]
    if any(w in lower for w in remind_words):
        # Check for time patterns
        time_match = _re.search(r'(\d+)\s*(?:min|minute|m)', lower)
        if time_match:
            mins = int(time_match.group(1))
            time_str = (now + timedelta(minutes=mins)).strftime("%H:%M")
            text = _re.sub(r'\d+\s*(?:min|minute|m)', '', user_msg)
            text = ' '.join([w for w in text.split() if w.lower() not in remind_words])
            return ("remind", {"time": time_str, "text": text[:100]})
        
        time_match = _re.search(r'(\d{1,2}):(\d{2})', lower)
        if time_match:
            time_str = f"{int(time_match.group(1)):02d}:{int(time_match.group(2)):02d}"
            text = _re.sub(r'\d{1,2}:\d{2}', '', user_msg)
            text = ' '.join([w for w in text.split() if w.lower() not in remind_words])
            return ("remind", {"time": time_str, "text": text[:100]})
        
        time_match = _re.search(r'(\d{1,2})\s*(?:baje|baj)', lower)
        if time_match:
            h = int(time_match.group(1))
            if any(w in lower for w in ['raat', 'sham', 'evening', 'night', 'pm']):
                h = h + 12 if h < 12 else h
            time_str = f"{h:02d}:00"
            text = _re.sub(r'\d{1,2}\s*(?:baje|baj)', '', user_msg)
            text = ' '.join([w for w in text.split() if w.lower() not in remind_words])
            return ("remind", {"time": time_str, "text": text[:100]})
    
    # Diary detection
    if "diary" in lower or "dairy" in lower:
        if any(w in lower for w in ["likho", "add", "save", "note kro"]):
            text = user_msg
            for kw in ["diary", "dairy", "likho", "add", "save", "note kro", "mein", "me"]:
                text = text.replace(kw, ' ').replace(kw.title(), ' ')
            text = ' '.join(text.split()).strip()
            return ("diary", {"text": text[:300]})
    
    # Task detection
    if any(w in lower for w in ["task add", "add task", "kaam add", "new task"]):
        title = user_msg
        for w in ["task add", "add task", "kaam add", "new task"]:
            title = title.replace(w, '').replace(w.title(), '')
        title = title.strip()
        if title:
            return ("add_task", {"title": title[:80]})
    
    # Task complete detection
    if any(w in lower for w in ["task done", "kaam ho gaya", "complete kar liya"]):
        match = _re.search(r'#?(\d+)', lower)
        hint = match.group(1) if match else ""
        return ("complete_task", {"hint": hint or lower[:30]})
    
    # Expense detection
    expense_words = ["kharcha", "kharch", "spent", "rupees", "₹", "rs"]
    if any(w in lower for w in expense_words):
        match = _re.search(r'(\d+(?:\.\d+)?)', lower)
        if match:
            amount = float(match.group(1))
            desc = _re.sub(r'(\d+(?:\.\d+)?|rs\.?|₹|rupees?)', '', user_msg)
            desc = ' '.join([w for w in desc.split() if w.lower() not in expense_words])
            desc = desc.strip() or "Expense"
            return ("expense", {"amount": amount, "desc": desc[:60]})
    
    # Habit detection
    if "habit add" in lower or "add habit" in lower:
        name = user_msg.replace("habit add", "").replace("add habit", "").strip()
        return ("add_habit", {"name": name[:50]})
    
    if "habit done" in lower or "habit ho gayi" in lower:
        match = _re.search(r'#?(\d+)', lower)
        keyword = match.group(1) if match else lower[:30]
        return ("habit_done", {"keyword": keyword})
    
    # Water detection
    if any(w in lower for w in ["paani piya", "water piya", "water log"]):
        match = _re.search(r'(\d+)\s*(ml|glass|bottle)', lower)
        ml = 250
        if match:
            val = int(match.group(1))
            unit = match.group(2)
            if "glass" in unit:
                ml = val * 250
            elif "bottle" in unit:
                ml = val * 500
            else:
                ml = val
        return ("water", {"ml": ml})
    
    return ("chat", {"text": user_msg})

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
    
    # Parse message
    action_type, params = parse_user_message(user_msg)
    log.info(f"📥 '{user_msg[:50]}' → {action_type}")
    
    # Execute action
    if action_type == "remind":
        await handle_remind(update, params.get("text", "Reminder"), params.get("time", ""))
    elif action_type == "add_task":
        await handle_add_task(update, params.get("title", ""))
    elif action_type == "complete_task":
        await handle_complete_task(update, params.get("hint", ""))
    elif action_type == "expense":
        await handle_expense(update, params.get("amount", 0), params.get("desc", ""))
    elif action_type == "diary":
        await handle_diary(update, params.get("text", ""))
    elif action_type == "add_habit":
        await handle_habit_add(update, params.get("name", ""))
    elif action_type == "habit_done":
        await handle_habit_done(update, params.get("keyword", ""))
    elif action_type == "water":
        await handle_water(update, params.get("ml", 250))
    else:
        # Chat mode
        prompt = build_system_prompt() + f"\n\nUser: {user_msg}\n\nShort Hindi reply:"
        reply = call_gemini(prompt, max_tokens=400)
        if not reply:
            reply = "🙏 Batao kya help chahiye? Tasks, reminders, kharcha, diary?"
        await update.message.reply_text(reply, parse_mode="Markdown")
    
    # Save to chat history
    chat_hist.add("user", user_msg, update.effective_user.first_name or "User")
    
    # Auto backup
    asyncio.create_task(backup_to_sheets())


# ================================================================
# COMMAND HANDLERS
# ================================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕌 Assalamualaikum! Main aapka AI Dost hoon.\n\n"
        "Examples:\n"
        "• '2 min mein paani yaad dilana'\n"
        "• 'Chai pe 50 rupees kharcha'\n"
        "• 'Gym kaam add karo'\n"
        "• 'Diary mein likho aaj accha din tha'\n\n"
        "Commands: /help"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 COMMANDS\n\n"
        "🗣 Natural Chat:\n"
        "  '2 min mein paani yaad dilana'\n"
        "  'Chai pe 50 rupees kharcha'\n"
        "  'Diary mein likho...'\n"
        "  'Exercise habit ho gayi'\n\n"
        "⚡ Commands:\n"
        "/task Task name\n/done <id>\n/habit Habit name\n/hdone <id>\n"
        "/remind 30m Chai\n/kharcha 100 Chai\n/diary\n/save text\n/water 250\n"
        "/briefing\n/backup\n/status"
    )

async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(f"📋 Pending ({len(pending)}):\n{lines}")
        else:
            await update.message.reply_text("📋 `/task Kaam naam`")
        return
    title = " ".join(ctx.args)
    t = tasks.add(title)
    await update.message.reply_text(f"✅ Task added: #{t['id']} {t['title']}")
    await backup_to_sheets()

async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(f"📋 Pending:\n{lines}\n\n/done <id>")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        await update.message.reply_text(f"🎉 Done! ✅ {t['title']}" if t else "❌ Not found!")
        await backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        all_h = habits.all()
        if all_h:
            hd, _ = habits.today_status()
            lines = "\n".join(f"{'✅' if h in hd else '⬜'} #{h['id']} {h['name']} 🔥{h.get('streak',0)}" for h in all_h)
            await update.message.reply_text(f"💪 Habits:\n{lines}")
        else:
            await update.message.reply_text("💪 `/habit Naam`")
        return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(f"💪 Habit added: #{h['id']} {h['name']}")
    await backup_to_sheets()

async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            lines = "\n".join(f"⬜ #{h['id']} {h['name']}" for h in pending)
            await update.message.reply_text(f"💪 Pending habits:\n{lines}\n\n/hdone <id>")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        await update.message.reply_text(f"💪 Habit done! 🔥 {streak} day streak!" if ok else "✅ Already done today!")
        await backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        today_list = expenses.get_by_date(today_str())
        if today_list:
            lines = "\n".join(f"₹{e['amount']} - {e['desc']}" for e in today_list[-10:])
            await update.message.reply_text(f"💰 Aaj ka kharcha:\n{lines}\nTotal: ₹{expenses.today_total()}")
        else:
            await update.message.reply_text("💰 `/kharcha 100 Chai`")
        return
    try:
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        await update.message.reply_text(f"💰 ₹{amount} - {desc}\nAaj total: ₹{expenses.today_total()}")
        await backup_to_sheets()
    except:
        await update.message.reply_text("❌ `/kharcha 100 Chai`")

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        active = reminders.all_active()
        if active:
            lines = "\n".join(f"#{r['id']} {r['time']} - {r['text']}" for r in active)
            await update.message.reply_text(f"⏰ Reminders:\n{lines}")
        else:
            await update.message.reply_text("⏰ `/remind 30m Chai`")
        return
    time_arg = ctx.args[0].lower()
    text = " ".join(ctx.args[1:])
    now = now_ist()
    
    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        remind_at = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        parts = time_arg.split(":")
        remind_at = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    else:
        await update.message.reply_text("❌ Use: `/remind 30m Chai`")
        return
    
    r = reminders.add(update.effective_chat.id, text, remind_at)
    await update.message.reply_text(f"✅ Reminder set for {remind_at}: {text}\nID: #{r['id']}")
    await backup_to_sheets()

async def cmd_water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ml = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 250
    water.add(ml)
    await update.message.reply_text(f"💧 +{ml}ml! Total: {water.today_total()}/{water.goal()}ml")
    await backup_to_sheets()

async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n = now_ist()
    await update.message.reply_text(
        f"🌅 BRIEFING - {n.strftime('%d %b %Y')}\n"
        f"⏰ {n.strftime('%I:%M %p')}\n"
        f"📋 Tasks: {len(tasks.today_pending())} pending\n"
        f"💪 Habits: {len(habits.today_status()[0])} done\n"
        f"💰 Kharcha: ₹{expenses.today_total()}\n"
        f"💧 Water: {water.today_total()}/{water.goal()}ml"
    )

async def cmd_backup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📤 Backup in progress...")
    result = await backup_to_sheets()
    await update.message.reply_text(result)

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 STATUS\n\n"
        f"Tasks: {len(tasks.all_tasks())}\n"
        f"Diary: {sum(len(v) for v in diary.get_all_entries().values())} entries\n"
        f"Expenses: {len(expenses.store.data.get('list', []))}\n"
        f"Reminders: {len(reminders.get_all())}\n"
        f"Habits: {len(habits.all())}\n"
        f"Sheets: {'✅' if google_sheets and google_sheets.sheet else '❌'}"
    )

async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📖 `/save Aaj ka din acha tha...`")
        return
    text = " ".join(ctx.args)
    diary.add(text)
    await update.message.reply_text(f"📖 Diary saved! ✅\n_{text[:100]}_")
    await backup_to_sheets()

# ================================================================
# DIARY CONVERSATION
# ================================================================
async def cmd_diary_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or []
    if not args:
        ctx.user_data["diary_mode"] = "view_today"
        await update.message.reply_text("🔐 Diary password daalo:\n_/cancel se bahar_", parse_mode="Markdown")
        return DIARY_AWAIT_PASS
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
    await update.message.reply_text("🔐 Password daalo:\n_/cancel se bahar_", parse_mode="Markdown")
    return DIARY_AWAIT_PASS

async def diary_password_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END
    entered = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    if entered != DIARY_PASSWORD:
        await update.effective_chat.send_message("❌ Galat Password!\n_Dobara: /diary_", parse_mode="Markdown")
        return ConversationHandler.END
    mode = ctx.user_data.get("diary_mode", "view_today")
    if mode == "write" and not ctx.user_data.get("diary_pending_text"):
        await update.effective_chat.send_message("✏️ Diary mein likho:\n_/cancel se bahar_", parse_mode="Markdown")
        return DIARY_AWAIT_TEXT
    elif mode == "write":
        text = ctx.user_data.get("diary_pending_text", "")
        diary.add(text)
        await update.effective_chat.send_message(f"📖 Diary saved! ✅\n_{text[:100]}_")
        await backup_to_sheets()
        return ConversationHandler.END
    else:
        entries = diary.get_all_entries()
        if not entries:
            await update.effective_chat.send_message("📖 Koi diary entry nahi.")
        else:
            count = sum(len(v) for v in entries.values())
            await update.effective_chat.send_message(f"📖 Total diary entries: {count}")
        return ConversationHandler.END

async def diary_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    diary.add(text)
    await update.effective_chat.send_message(f"📖 Diary saved! ✅\n_{text[:100]}_")
    await backup_to_sheets()
    return ConversationHandler.END

async def diary_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("⏱ Diary cancel.")

# ================================================================
# ALARM JOBS
# ================================================================
async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now = now_ist()
    if now.hour == 0 and now.minute <= 2:
        reminders.reset_daily()
        return
    
    for r in reminders.due_now():
        try:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ OK - Band Karo", callback_data=f"ok_{r['id']}")]])
            alert = f"🔔 ALARM! ⏰ {r['time']}\n\n📢 {r['text'].upper()}\n\n⏸️ Snooze: /snooze5 {r['id']} | /snooze10 {r['id']}\n❌ Delete: /delremind {r['id']}"
            await context.bot.send_message(chat_id=int(r["chat_id"]), text=alert, reply_markup=keyboard)
            reminders.mark_fired(r["id"])
            await asyncio.sleep(0.5)
        except Exception as e:
            log.error(f"Reminder error: {e}")

async def handle_ok_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Alarm band!")
    data = query.data
    if data.startswith("ok_"):
        try:
            rid = int(data.split("_")[1])
            if reminders.acknowledge(rid, "User pressed OK"):
                await query.edit_message_text("✅ Alarm band ho gaya!")
                await backup_to_sheets()
            else:
                await query.edit_message_text("⚠️ Pehle se band hai.")
        except:
            await query.edit_message_text("❌ Error!")

async def cmd_snooze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.split()[0].lower()
    snooze_map = {"snooze5": 5, "snooze10": 10}
    mins = snooze_map.get(cmd, 10)
    if not ctx.args:
        await update.message.reply_text(f"⏸️ `/{cmd} <id>`")
        return
    try:
        rid = int(ctx.args[0])
        target = next((r for r in reminders.get_all() if r["id"] == rid), None)
        if not target:
            await update.message.reply_text(f"❌ Reminder #{rid} nahi mila!")
            return
        reminders.acknowledge(rid, f"Snoozed {mins}min")
        new_time = (now_ist() + timedelta(minutes=mins)).strftime("%H:%M")
        new_rem = reminders.add(target["chat_id"], f"🔁 {target['text']}", new_time, "once")
        await update.message.reply_text(f"⏸️ Snoozed! {mins} min baad fir yaad dilaunga.\nNew ID: #{new_rem['id']}")
        await backup_to_sheets()
    except:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_delremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        reminders.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Reminder deleted!")

# ================================================================
# MAIN
# ================================================================
def main():
    log.info("=" * 60)
    log.info("🤖 Personal AI Bot v24.0 - DATA IS SEPARATE!")
    log.info("   All data stored in 'data/' folder (JSON files)")
    log.info("   You can change bot.py without losing data")
    log.info("=" * 60)
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Diary conversation
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary_entry)],
        states={DIARY_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)],
                DIARY_AWAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_text_input)]},
        fallbacks=[CommandHandler("cancel", diary_cancel)],
    ))
    
    # Commands
    commands = [
        ("start", cmd_start), ("help", cmd_help), ("task", cmd_task), ("done", cmd_done),
        ("habit", cmd_habit), ("hdone", cmd_hdone), ("kharcha", cmd_kharcha),
        ("remind", cmd_remind), ("delremind", cmd_delremind), ("water", cmd_water),
        ("briefing", cmd_briefing), ("backup", cmd_backup), ("status", cmd_status),
        ("save", cmd_save), ("snooze5", cmd_snooze), ("snooze10", cmd_snooze),
    ]
    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))
    
    app.add_handler(CallbackQueryHandler(handle_ok_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=10)
    
    log.info("✅ Bot ready!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
