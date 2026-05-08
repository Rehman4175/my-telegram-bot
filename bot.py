#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PERSONAL AI ASSISTANT - Using Secure Data Manager
"""

import os, json, logging, time, asyncio, random
import urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta, timezone
import re as _re

# ================================================================
# IMPORT FROM SECURE DATA MANAGER
# ================================================================
from secure_data_manager import (
    memory, tasks, diary, habits, expenses, goals, reminders,
    water, bills, calendar, chat_hist, now_ist, today_str, now_str
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

DIARY_PASSWORD = "Rk1996"
DIARY_AWAIT_PASS = 0
DIARY_AWAIT_TEXT = 1

if not TELEGRAM_TOKEN:
    print("❌ TELEGRAM_TOKEN not set!")
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
# GEMINI API
# ================================================================
GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
_last_gemini_call = 0

def call_gemini(prompt, max_tokens=400):
    global _last_gemini_call
    if not GEMINI_API_KEY:
        return None
    now_t = time.time()
    elapsed = now_t - _last_gemini_call
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
    active_rem = reminders.all_active()
    
    return f"""Tu mera Personal AI Assistant hai — naam 'Dost'.
⚠️ TIME: {now_ist().strftime('%A, %d %b — %I:%M %p')} IST

📋 Aaj ke tasks: {len(tp)} pending
💪 Habits: {len(hd)} done, {len(hp)} pending
💰 Aaj kharcha: ₹{exp_t}
💧 Paani: {wt}ml/{wg}ml
⏰ Reminders: {len(active_rem)} active

Hamesha Hindi/Hinglish mein SHORT jawab do (2-3 lines maximum)."""

# ================================================================
# COMMAND HANDLERS
# ================================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(
        f"🕌 Assalamualaikum {name}!\n\n"
        f"Main aapka AI Dost hoon! 🔐\n\n"
        f"*Examples:*\n"
        f"• '2 min mein paani yaad dilana'\n"
        f"• 'Chai pe 50 rupees kharcha'\n"
        f"• 'Gym kaam add karo'\n"
        f"• 'Diary mein likho aaj accha din tha'\n\n"
        f"Commands: /help",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *COMMANDS*\n\n"
        "🗣 *Natural Chat:*\n"
        "  '2 min mein paani yaad dilana'\n"
        "  'Chai pe 50 rupees kharcha'\n"
        "  'Diary mein likho...'\n"
        "  'Exercise habit ho gayi'\n\n"
        "⚡ *Commands:*\n"
        "`/task Task name` - Add task\n"
        "`/done <id>` - Complete task\n"
        "`/habit Habit name` - Add habit\n"
        "`/hdone <id>` - Log habit\n"
        "`/remind 30m Chai` - Set reminder\n"
        "`/kharcha 100 Chai` - Add expense\n"
        "`/diary` - View diary (password)\n"
        "`/save text` - Quick diary save\n"
        "`/water 250` - Log water\n"
        "`/briefing` - Daily summary\n"
        "`/status` - Check system status\n"
        "`/help` - This menu",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Check bot status and data connection"""
    try:
        from secure_data_manager import repo_manager, sheets_backup
        github_status = "✅ Connected" if repo_manager.is_connected else "⚠️ Local only"
        sheets_status = "✅ Connected" if sheets_backup and sheets_backup.sheet else "⚠️ Not connected"
    except:
        github_status = "❌ Check secure_data_manager"
        sheets_status = "❌ Not configured"
    
    await update.message.reply_text(
        f"📊 *BOT STATUS*\n\n"
        f"🤖 Bot: ✅ Running\n"
        f"🔐 GitHub: {github_status}\n"
        f"📊 Google Sheets: {sheets_status}\n\n"
        f"📁 *Data Stats:*\n"
        f"📋 Tasks: {len(tasks.all_tasks())}\n"
        f"📖 Diary: {sum(len(v) for v in diary.get_all_entries().values())} entries\n"
        f"💰 Expenses: {len(expenses.store.data.get('list', []))}\n"
        f"💪 Habits: {len(habits.all())}\n"
        f"⏰ Reminders: {len(reminders.get_all())}\n"
        f"💧 Water: {water.today_total()}/{water.goal()}ml today",
        parse_mode="Markdown"
    )

async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(f"📋 *Pending ({len(pending)}):*\n{lines}\n\n_/done <id>_", parse_mode="Markdown")
        else:
            await update.message.reply_text("📋 `/task Kaam naam`", parse_mode="Markdown")
        return
    title = " ".join(ctx.args)
    t = tasks.add(title)
    await update.message.reply_text(f"✅ Task added: #{t['id']} {t['title']}")

async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(f"📋 *Pending:*\n{lines}\n\n_/done <id>_", parse_mode="Markdown")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        await update.message.reply_text(f"🎉 *Done!* ✅ {t['title']}" if t else "❌ Not found!", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        all_h = habits.all()
        if all_h:
            hd, _ = habits.today_status()
            lines = "\n".join(f"{'✅' if h in hd else '⬜'} #{h['id']} {h['name']} 🔥{h.get('streak',0)}" for h in all_h)
            await update.message.reply_text(f"💪 *Habits:*\n{lines}\n\n_/hdone <id>_", parse_mode="Markdown")
        else:
            await update.message.reply_text("💪 `/habit Naam`", parse_mode="Markdown")
        return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(f"💪 Habit added: #{h['id']} {h['name']}")

async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            lines = "\n".join(f"⬜ #{h['id']} {h['name']}" for h in pending)
            await update.message.reply_text(f"💪 *Pending Habits:*\n{lines}\n\n_/hdone <id>_", parse_mode="Markdown")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        await update.message.reply_text(f"💪 *Habit done!* 🔥 {streak} day streak!" if ok else "✅ Already done today!", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        today_list = expenses.get_by_date(today_str())
        if today_list:
            lines = "\n".join(f"₹{e['amount']} - {e['desc']}" for e in today_list[-10:])
            await update.message.reply_text(f"💰 *Aaj ka kharcha:*\n{lines}\n*Total: ₹{expenses.today_total()}*", parse_mode="Markdown")
        else:
            await update.message.reply_text("💰 `/kharcha 100 Chai`", parse_mode="Markdown")
        return
    try:
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        await update.message.reply_text(f"💰 ₹{amount} - {desc}\n📊 Aaj total: ₹{expenses.today_total()}", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ `/kharcha 100 Chai`")

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        active = reminders.all_active()
        if active:
            lines = "\n".join(f"#{r['id']} `{r['time']}` - {r['text']}" for r in active)
            await update.message.reply_text(f"⏰ *Active Reminders:*\n{lines}\n\n_/remind 30m Chai_", parse_mode="Markdown")
        else:
            await update.message.reply_text("⏰ `/remind 30m Chai` ya `/remind 15:30 Meeting`", parse_mode="Markdown")
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
        await update.message.reply_text("❌ Use: `/remind 30m Chai` or `/remind 15:30 Meeting`")
        return
    
    r = reminders.add(update.effective_chat.id, text, remind_at)
    await update.message.reply_text(f"✅ Reminder set for {remind_at}: {text}\n🆔 #{r['id']}")

async def cmd_water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ml = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 250
    water.add(ml)
    total = water.today_total()
    goal = water.goal()
    pct = int(total / goal * 100) if goal else 0
    bar = "💧" * min(10, pct // 10) + "⬜" * (10 - min(10, pct // 10))
    await update.message.reply_text(f"💧 +{ml}ml!\n{bar}\n{total}ml / {goal}ml ({pct}%)", parse_mode="Markdown")

async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n = now_ist()
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    await update.message.reply_text(
        f"🌅 *BRIEFING - {n.strftime('%d %b %Y')}*\n"
        f"⏰ {n.strftime('%I:%M %p')} IST\n\n"
        f"📋 Tasks pending: {len(tp)}\n"
        f"💪 Habits done: {len(hd)}/{len(hd)+len(hp)}\n"
        f"💰 Aaj kharcha: ₹{expenses.today_total()}\n"
        f"💧 Water: {water.today_total()}ml/{water.goal()}ml",
        parse_mode="Markdown"
    )

async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📖 `/save Aaj ka din acha tha...`")
        return
    text = " ".join(ctx.args)
    diary.add(text)
    await update.message.reply_text(f"📖 *Diary saved!* ✅\n_{text[:100]}_", parse_mode="Markdown")

# ================================================================
# DIARY CONVERSATION HANDLER
# ================================================================
async def cmd_diary_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or []
    if not args:
        ctx.user_data["diary_mode"] = "view_today"
        await update.message.reply_text("🔐 *Diary password daalo:*\n_/cancel se bahar_", parse_mode="Markdown")
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
    await update.message.reply_text("🔐 *Password daalo:*\n_/cancel se bahar_", parse_mode="Markdown")
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
        await update.effective_chat.send_message("❌ *Galat Password!*\n_Dobara: /diary_", parse_mode="Markdown")
        return ConversationHandler.END
    mode = ctx.user_data.get("diary_mode", "view_today")
    if mode == "write" and not ctx.user_data.get("diary_pending_text"):
        await update.effective_chat.send_message("✏️ *Diary mein likho:*\n_/cancel se bahar_", parse_mode="Markdown")
        return DIARY_AWAIT_TEXT
    elif mode == "write":
        text = ctx.user_data.get("diary_pending_text", "")
        diary.add(text)
        await update.effective_chat.send_message(f"📖 *Diary saved!* ✅\n_{text[:100]}_", parse_mode="Markdown")
        return ConversationHandler.END
    else:
        entries = diary.get_all_entries()
        if not entries:
            await update.effective_chat.send_message("📖 *Koi diary entry nahi mili.*", parse_mode="Markdown")
        else:
            count = sum(len(v) for v in entries.values())
            await update.effective_chat.send_message(f"📖 *Total diary entries: {count}*", parse_mode="Markdown")
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
    await update.effective_chat.send_message(f"📖 *Diary saved!* ✅\n_{text[:100]}_", parse_mode="Markdown")
    return ConversationHandler.END

async def diary_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("⏱ *Diary cancelled.*", parse_mode="Markdown")
    return ConversationHandler.END

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
            # Create keyboard with OK button
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ OK - Band Karo", callback_data=f"ok_{r['id']}")]
            ])
            
            alert = (
                f"🔔🔔🔔 *ALARM!* 🔔🔔🔔\n"
                f"{'═'*25}\n"
                f"⏰ *{r['time']} BAJ GAYE!*\n"
                f"{'═'*25}\n\n"
                f"📢 *{r['text'].upper()}*\n\n"
                f"⏸️ *Snooze:* `/snooze5 {r['id']}` | `/snooze10 {r['id']}`\n"
                f"❌ *Delete:* `/delremind {r['id']}`"
            )
            await context.bot.send_message(
                chat_id=int(r["chat_id"]), 
                text=alert, 
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            reminders.mark_fired(r["id"])
            log.info(f"🔔 Alarm fired for #{r['id']}: {r['text']}")
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
                await query.edit_message_text("✅ *Alarm band ho gaya! Ab nahi bajega.*", parse_mode="Markdown")
                log.info(f"✅ Reminder #{rid} stopped by OK button")
            else:
                await query.edit_message_text("⚠️ *Pehle se band hai.*", parse_mode="Markdown")
        except Exception as e:
            log.error(f"OK button error: {e}")
            await query.edit_message_text("❌ Error!")

async def cmd_snooze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.split()[0].lower()
    snooze_map = {"snooze5": 5, "snooze10": 10, "snooze30": 30, "snooze60": 60}
    mins = snooze_map.get(cmd, 10)
    if not ctx.args:
        await update.message.reply_text(f"⏸️ `/{cmd} <reminder_id>`", parse_mode="Markdown")
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
        await update.message.reply_text(f"⏸️ *Snoozed!* {mins} min baad fir yaad dilaunga.\n🆔 New ID: #{new_rem['id']}", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_delremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        reminders.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 Reminder deleted!")

# ================================================================
# NATURAL LANGUAGE HANDLER
# ================================================================
def parse_user_message(user_msg):
    lower = user_msg.lower().strip()
    now = now_ist()
    
    # Reminder detection
    remind_words = ["remind", "reminder", "alarm", "yaad dilana", "bata dena"]
    if any(w in lower for w in remind_words):
        time_match = _re.search(r'(\d+)\s*(?:min|minute|m)', lower)
        if time_match:
            mins = int(time_match.group(1))
            time_str = (now + timedelta(minutes=mins)).strftime("%H:%M")
            text = _re.sub(r'\d+\s*(?:min|minute|m)', '', user_msg)
            text = ' '.join([w for w in text.split() if w.lower() not in remind_words])
            if not text.strip():
                text = "Reminder!"
            return ("remind", {"time": time_str, "text": text[:100]})
        
        time_match = _re.search(r'(\d{1,2}):(\d{2})', lower)
        if time_match:
            time_str = f"{int(time_match.group(1)):02d}:{int(time_match.group(2)):02d}"
            text = _re.sub(r'\d{1,2}:\d{2}', '', user_msg)
            text = ' '.join([w for w in text.split() if w.lower() not in remind_words])
            return ("remind", {"time": time_str, "text": text[:100]})
    
    # Diary detection
    if "diary" in lower or "dairy" in lower or "diary mein likho" in lower:
        text = user_msg
        for kw in ["diary", "dairy", "likho", "add", "save", "mein", "me", "main"]:
            text = text.replace(kw, ' ').replace(kw.title(), ' ')
        text = ' '.join(text.split()).strip()
        if not text:
            text = user_msg
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
        hint = match.group(1) if match else lower[:30]
        return ("complete_task", {"hint": hint})
    
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

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_msg = update.message.text.strip()
    if user_msg.startswith("/"):
        return
    
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    action_type, params = parse_user_message(user_msg)
    log.info(f"📥 '{user_msg[:50]}' → {action_type}")
    
    if action_type == "remind":
        r = reminders.add(update.effective_chat.id, params.get("text", "Reminder"), params.get("time", ""))
        await update.message.reply_text(f"✅ Reminder set for {params.get('time')}: {params.get('text')}\n🆔 #{r['id']}")
    
    elif action_type == "add_task":
        t = tasks.add(params.get("title", ""))
        await update.message.reply_text(f"✅ Task added: #{t['id']} {t['title']}")
    
    elif action_type == "complete_task":
        hint = params.get("hint", "")
        pending = tasks.pending()
        matched = next((t for t in pending if str(t["id"]) == hint or (hint and hint in t["title"].lower())), None)
        if matched:
            tasks.complete(matched["id"])
            await update.message.reply_text(f"🎉 Done! ✅ {matched['title']}")
        else:
            await update.message.reply_text("❓ Kaunsa task? ID ya naam batao")
    
    elif action_type == "expense":
        expenses.add(params.get("amount", 0), params.get("desc", ""))
        await update.message.reply_text(f"💰 ₹{params.get('amount')} - {params.get('desc')}\n📊 Aaj total: ₹{expenses.today_total()}")
    
    elif action_type == "diary":
        diary.add(params.get("text", ""))
        await update.message.reply_text(f"📖 Diary saved! ✅\n_{params.get('text', '')[:100]}_")
    
    elif action_type == "add_habit":
        h = habits.add(params.get("name", ""))
        await update.message.reply_text(f"💪 Habit added: #{h['id']} {h['name']}")
    
    elif action_type == "habit_done":
        keyword = params.get("keyword", "")
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
    
    elif action_type == "water":
        water.add(params.get("ml", 250))
        total = water.today_total()
        goal = water.goal()
        await update.message.reply_text(f"💧 +{params.get('ml', 250)}ml! Total: {total}/{goal}ml")
    
    else:
        prompt = build_system_prompt() + f"\n\nUser: {user_msg}\n\nShort Hindi reply (2-3 lines):"
        reply = call_gemini(prompt)
        if not reply:
            reply = _smart_fallback(user_msg)
        await update.message.reply_text(reply, parse_mode="Markdown")
    
    chat_hist.add("user", user_msg, update.effective_user.first_name or "User")
    chat_hist.add("assistant", "Reply sent", "Bot")

def _smart_fallback(user_msg):
    msg = user_msg.lower().strip()
    n = now_ist()
    if any(w in msg for w in ["time", "kitne baje"]):
        return f"⏰ Abhi *{n.strftime('%I:%M %p')}* baj rahe hain"
    if any(w in msg for w in ["date", "aaj kya tarikh"]):
        return f"📅 Aaj *{n.strftime('%A, %d %B %Y')}* hai"
    if any(w in msg for w in ["hello", "hi", "assalam", "namaste"]):
        return "🕌 *Assalamualaikum!* Kya help chahiye?"
    if any(w in msg for w in ["kaise ho", "how are"]):
        return "😊 *Main badiya hoon!* Aap sunao?"
    return "🙏 *Batao kya help chahiye?* Tasks, reminders, kharcha, diary?"

# ================================================================
# MAIN
# ================================================================
def main():
    log.info("=" * 60)
    log.info("🤖 Personal AI Bot v24.0 - SECURE DATA")
    log.info("   Using private GitHub repo + Google Sheets backup")
    log.info(f"⏰ IST: {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Diary conversation
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary_entry)],
        states={
            DIARY_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)],
            DIARY_AWAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_text_input)]
        },
        fallbacks=[CommandHandler("cancel", diary_cancel)],
    ))
    
    # Commands
    commands = [
        ("start", cmd_start), ("help", cmd_help), ("status", cmd_status),
        ("task", cmd_task), ("done", cmd_done),
        ("habit", cmd_habit), ("hdone", cmd_hdone),
        ("kharcha", cmd_kharcha), ("remind", cmd_remind), ("delremind", cmd_delremind),
        ("water", cmd_water), ("briefing", cmd_briefing), ("save", cmd_save),
        ("snooze5", cmd_snooze), ("snooze10", cmd_snooze), ("snooze30", cmd_snooze), ("snooze60", cmd_snooze),
    ]
    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))
    
    app.add_handler(CallbackQueryHandler(handle_ok_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Background jobs
    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=10)
    
    log.info("✅ Bot ready! Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
