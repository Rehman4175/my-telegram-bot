#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PERSONAL AI ASSISTANT BOT
FIXED v2:
  - Alarm RINGS EVERY MINUTE until OK pressed (correct logic)
  - OK button ALWAYS visible on every alarm message
  - Google Sheets sync on every action with proper error logging
  - /datacheck command shows what is saved where
  - /status shows connection details
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
# SYSTEM PROMPT
# ================================================================
def build_system_prompt():
    tp     = tasks.today_pending()
    hd, hp = habits.today_status()
    return (
        f"Tu mera Personal AI Assistant hai — naam 'Dost'.\n"
        f"⚠️ TIME: {now_ist().strftime('%A, %d %b — %I:%M %p')} IST\n\n"
        f"📋 Tasks pending: {len(tp)}\n"
        f"💪 Habits: {len(hd)} done, {len(hp)} pending\n"
        f"💰 Aaj kharcha: ₹{expenses.today_total()}\n"
        f"💧 Paani: {water.today_total()}ml/{water.goal()}ml\n"
        f"⏰ Reminders: {len(reminders.all_active())} active\n\n"
        f"Hamesha Hindi/Hinglish mein SHORT jawab do (2-3 lines maximum)."
    )

# ================================================================
# ALARM KEYBOARD — OK button har baar
# ================================================================
def alarm_keyboard(rid):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ OK — Alarm Band Karo", callback_data=f"ok_{rid}")
    ]])

# ================================================================
# COMMANDS
# ================================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(
        f"🕌 Assalamualaikum {name}!\n\n"
        f"Main aapka AI Dost hoon! 🔐\n\n"
        f"*Examples:*\n"
        f"• '2 min mein paani yaad dilana'\n"
        f"• 'Chai pe 50 rupees kharcha'\n"
        f"• 'Diary mein likho aaj accha din tha'\n\n"
        f"/help — sab commands",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *COMMANDS*\n\n"
        "🗣 *Natural Language:*\n"
        "  '2 min mein paani yaad dilana'\n"
        "  'Chai pe 50 rupees kharcha'\n"
        "  'Diary mein likho...'\n"
        "  'Exercise habit ho gayi'\n\n"
        "⚡ *Direct Commands:*\n"
        "`/task <naam>` — task add\n"
        "`/done <id>` — task complete\n"
        "`/habit <naam>` — habit add\n"
        "`/hdone <id>` — habit log\n"
        "`/remind 30m <text>` — reminder\n"
        "`/kharcha 100 <desc>` — expense\n"
        "`/water 250` — water log\n"
        "`/diary` — diary (password)\n"
        "`/save <text>` — quick diary\n"
        "`/briefing` — daily summary\n"
        "`/status` — system status\n"
        "`/datacheck` — data safety check\n"
        "`/sheetstest` — test Sheets sync",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    github_ok = "✅ Connected" if repo_manager.is_connected else "⚠️ Local only"
    sheets_ok = "✅ Connected" if sheets_backup.connected   else "❌ NOT connected"
    await update.message.reply_text(
        f"📊 *BOT STATUS*\n\n"
        f"🤖 Bot: ✅ Running\n"
        f"🔐 GitHub (private data): {github_ok}\n"
        f"📊 Google Sheets: {sheets_ok}\n\n"
        f"📁 *Data:*\n"
        f"📋 Tasks: {len(tasks.all_tasks())} total, {len(tasks.pending())} pending\n"
        f"📖 Diary: {sum(len(v) for v in diary.get_all_entries().values())} entries\n"
        f"💰 Expenses today: ₹{expenses.today_total()}\n"
        f"💪 Habits: {len(habits.all())}\n"
        f"⏰ Reminders active: {len(reminders.all_active())}\n"
        f"💧 Water today: {water.today_total()}/{water.goal()}ml",
        parse_mode="Markdown"
    )

async def cmd_datacheck(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    NEW: Shows exactly what data is saved and where.
    Confirms GitHub + Sheets sync status so user knows data is safe.
    """
    github_ok = repo_manager.is_connected
    sheets_ok = sheets_backup.connected

    # Count all data
    total_diary    = sum(len(v) for v in diary.get_all_entries().values())
    total_tasks    = len(tasks.all_tasks())
    total_expenses = len(expenses.store.data.get("list", []))
    total_habits   = len(habits.all())
    total_water    = len(water.store.data.get("logs", {}))
    total_reminders= len(reminders.get_all())

    github_status = "✅ GitHub pe safe hai" if github_ok else "⚠️ Sirf local (GitHub nahi)"
    sheets_status = "✅ Sheets mein sync ho raha hai" if sheets_ok else "❌ Sheets sync BAND hai"

    # Test sheets right now
    sheets_live = "❓"
    if sheets_ok:
        try:
            ok = sheets_backup.log_event("DATACHECK", f"Manual check at {now_ist().strftime('%H:%M')}")
            sheets_live = "✅ Abhi test kiya — kaam kar raha hai!" if ok else "❌ Test FAIL hua"
        except Exception as e:
            sheets_live = f"❌ Error: {e}"

    await update.message.reply_text(
        f"🔍 *DATA SAFETY CHECK*\n"
        f"{'═'*25}\n\n"
        f"📦 *Kitna data saved hai:*\n"
        f"  📖 Diary entries: {total_diary}\n"
        f"  📋 Tasks: {total_tasks}\n"
        f"  💰 Expenses: {total_expenses}\n"
        f"  💪 Habits: {total_habits}\n"
        f"  💧 Water logs: {total_water} din\n"
        f"  ⏰ Reminders (total): {total_reminders}\n\n"
        f"💾 *Kahan save ho raha hai:*\n"
        f"  🔐 {github_status}\n"
        f"  📊 {sheets_status}\n\n"
        f"🧪 *Live Sheets Test:*\n"
        f"  {sheets_live}\n\n"
        f"{'✅ Sab theek hai! Naya bot.py dalne se data NAHI udega.' if github_ok else '⚠️ GitHub nahi connected — restart pe data local rahega'}",
        parse_mode="Markdown"
    )

async def cmd_sheetstest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Sheets test chal raha hai...")
    try:
        ok = sheets_backup.test_connection()
        if ok:
            await update.message.reply_text(
                "✅ *Google Sheets WORKING!*\n"
                "Daily\\_Logs tab mein ek test row aa gayi hogi.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "❌ *Sheets test FAILED!*\n\n"
                "Check karo:\n"
                "1. `GOOGLE_CREDS_JSON` env var sahi set hai?\n"
                "2. Service account email ko sheet ka *Editor* access diya hai?\n"
                "   (Sheet → Share → service account email paste karo)",
                parse_mode="Markdown"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(
                f"📋 *Pending ({len(pending)}):*\n{lines}\n\n_/done <id>_",
                parse_mode="Markdown")
        else:
            await update.message.reply_text("📋 `/task Kaam naam`", parse_mode="Markdown")
        return
    t = tasks.add(" ".join(ctx.args))
    await update.message.reply_text(f"✅ Task #{t['id']} added: {t['title']}")

async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(
                f"📋 *Pending:*\n{lines}\n\n_/done <id>_",
                parse_mode="Markdown")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t:
            await update.message.reply_text(f"🎉 Done! ✅ {t['title']}", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Task nahi mili!")
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        all_h = habits.all()
        if all_h:
            hd, _ = habits.today_status()
            lines = "\n".join(
                f"{'✅' if h in hd else '⬜'} #{h['id']} {h['name']} 🔥{h.get('streak',0)}"
                for h in all_h
            )
            await update.message.reply_text(
                f"💪 *Habits:*\n{lines}\n\n_/hdone <id>_",
                parse_mode="Markdown")
        else:
            await update.message.reply_text("💪 `/habit Naam`", parse_mode="Markdown")
        return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(f"💪 Habit #{h['id']} added: {h['name']}")

async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            lines = "\n".join(f"⬜ #{h['id']} {h['name']}" for h in pending)
            await update.message.reply_text(
                f"💪 *Pending:*\n{lines}\n\n_/hdone <id>_",
                parse_mode="Markdown")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        if ok:
            await update.message.reply_text(
                f"💪 *Done!* 🔥 {streak} day streak!", parse_mode="Markdown")
        else:
            await update.message.reply_text("✅ Already done today!")
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
                f"⏰ *Active:*\n{lines}\n\n_/remind 30m Chai_",
                parse_mode="Markdown")
        else:
            await update.message.reply_text(
                "⏰ `/remind 30m Chai` ya `/remind 15:30 Meeting`",
                parse_mode="Markdown")
        return
    time_arg = ctx.args[0].lower()
    text     = " ".join(ctx.args[1:])
    now      = now_ist()
    if time_arg.endswith("m") and time_arg[:-1].isdigit():
        remind_at = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        parts     = time_arg.split(":")
        remind_at = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    else:
        await update.message.reply_text("❌ `/remind 30m Chai` ya `/remind 15:30 Meeting`")
        return
    r = reminders.add(update.effective_chat.id, text, remind_at)
    await update.message.reply_text(
        f"✅ Reminder set: *{remind_at}* — {text}\n🆔 #{r['id']}",
        parse_mode="Markdown")

async def cmd_water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ml    = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 250
    total = water.add(ml)
    goal  = water.goal()
    pct   = int(total / goal * 100) if goal else 0
    bar   = "💧" * min(10, pct // 10) + "⬜" * (10 - min(10, pct // 10))
    await update.message.reply_text(f"💧 +{ml}ml\n{bar}\n{total}ml / {goal}ml ({pct}%)")

async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n      = now_ist()
    tp     = tasks.today_pending()
    hd, hp = habits.today_status()
    await update.message.reply_text(
        f"🌅 *BRIEFING — {n.strftime('%d %b %Y')}*\n"
        f"⏰ {n.strftime('%I:%M %p')} IST\n\n"
        f"📋 Tasks pending: {len(tp)}\n"
        f"💪 Habits: {len(hd)}/{len(hd)+len(hp)}\n"
        f"💰 Kharcha: ₹{expenses.today_total()}\n"
        f"💧 Water: {water.today_total()}/{water.goal()}ml",
        parse_mode="Markdown")

async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📖 `/save Aaj ka din acha tha...`")
        return
    text = " ".join(ctx.args)
    diary.add(text)
    await update.message.reply_text(
        f"📖 *Diary saved!* ✅\n_{text[:100]}_",
        parse_mode="Markdown")

async def cmd_delremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        try:
            reminders.delete(int(ctx.args[0]))
            await update.message.reply_text("🗑 Reminder deleted!")
        except Exception:
            await update.message.reply_text("❌ Invalid ID!")
    else:
        await update.message.reply_text("❌ `/delremind <id>`")

async def cmd_snooze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmd  = update.message.text.split()[0].lstrip("/").lower()
    mins = {"snooze5": 5, "snooze10": 10, "snooze30": 30, "snooze60": 60}.get(cmd, 10)
    if not ctx.args:
        await update.message.reply_text(f"⏸️ `/{cmd} <id>`", parse_mode="Markdown")
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
        await update.message.reply_text(
            f"⏸️ *Snoozed!* {mins} min baad bajega.\n🆔 New: #{new_rem['id']}",
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
        if ctx.user_data["diary_mode"] == "write" and args:
            ctx.user_data["diary_pending_text"] = " ".join(args)
    await update.message.reply_text(
        "🔐 *Password daalo:*\n_/cancel se bahar_",
        parse_mode="Markdown")
    return DIARY_AWAIT_PASS

async def diary_password_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END
    entered = update.message.text.strip()
    try: await update.message.delete()
    except Exception: pass
    if entered != DIARY_PASSWORD:
        await update.effective_chat.send_message(
            "❌ *Galat Password!*", parse_mode="Markdown")
        return ConversationHandler.END
    mode = ctx.user_data.get("diary_mode", "view_today")
    if mode == "write" and not ctx.user_data.get("diary_pending_text"):
        await update.effective_chat.send_message(
            "✏️ *Likho:*\n_/cancel se bahar_", parse_mode="Markdown")
        return DIARY_AWAIT_TEXT
    elif mode == "write":
        text = ctx.user_data.get("diary_pending_text", "")
        diary.add(text)
        await update.effective_chat.send_message(
            f"📖 *Saved!* ✅\n_{text[:100]}_", parse_mode="Markdown")
        return ConversationHandler.END
    else:
        entries = diary.get_all_entries()
        count   = sum(len(v) for v in entries.values())
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
    await update.effective_chat.send_message(
        f"📖 *Saved!* ✅\n_{text[:100]}_", parse_mode="Markdown")
    return ConversationHandler.END

async def diary_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Diary cancelled.", parse_mode="Markdown")
    return ConversationHandler.END

# ================================================================
# ALARM JOB — FIXED
# Logic:
#   1. due_now()  → fire reminders whose time == HH:MM RIGHT NOW (first ring)
#   2. ringing()  → re-ring every minute for reminders already fired but not acknowledged
# ================================================================
async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now    = now_ist()
    now_hm = now.strftime("%H:%M")

    # Midnight reset
    if now.hour == 0 and now.minute <= 1:
        reminders.reset_daily()
        log.info("🔄 Midnight reset done")
        return

    # Step 1: Fire reminders due RIGHT NOW (first ring)
    for r in reminders.due_now():
        log.info(f"🔔 First ring — #{r['id']} '{r['text']}' at {r['time']}")
        await _send_alarm(context, r)

    # Step 2: Re-ring every minute for unacknowledged reminders
    # These are already fired (fired_today=True) but user hasn't pressed OK
    for r in reminders.all_active():
        if (r.get("fired_today", False)
                and not r.get("acknowledged", False)):
            log.info(f"🔔 Re-ring #{r['id']} (count={r.get('fire_count',0)}) '{r['text']}'")
            await _send_alarm(context, r)


async def _send_alarm(context, r):
    """Send alarm message with OK button. Always includes the OK button."""
    try:
        count      = r.get("fire_count", 0)
        repeat_msg = f"\n🔁 *{count+1}vi baar baj raha hai — OK dabao!*" if count > 0 else ""
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
            chat_id      = int(r["chat_id"]),
            text         = alert,
            reply_markup = alarm_keyboard(r["id"]),   # ← OK button ALWAYS present
            parse_mode   = "Markdown"
        )
        reminders.mark_fired(r["id"])
        log.info(f"✅ Alarm sent #{r['id']} (total rings={r.get('fire_count',0)+1}): {r['text']}")
    except Exception as e:
        log.error(f"❌ Alarm send error for #{r.get('id','?')}: {e}")

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
                "✅ *Alarm band! Ab nahi bajega.* 🔕",
                parse_mode="Markdown")
            log.info(f"✅ Alarm #{rid} stopped by OK button")
        else:
            await query.edit_message_text("⚠️ Pehle se band hai.")
    except Exception as e:
        log.error(f"OK button error: {e}")
        await query.edit_message_text("❌ Error!")

# ================================================================
# NATURAL LANGUAGE PARSER
# ================================================================
def parse_user_message(user_msg):
    lower = user_msg.lower().strip()
    now   = now_ist()

    # Reminder
    remind_words = ["remind", "reminder", "alarm", "yaad dilana", "bata dena", "yaad dilao"]
    if any(w in lower for w in remind_words):
        m = _re.search(r'(\d+)\s*(?:min|minute|m)\b', lower)
        if m:
            mins = int(m.group(1))
            ts   = (now + timedelta(minutes=mins)).strftime("%H:%M")
            text = _re.sub(r'\d+\s*(?:min|minute|m)\b', '', user_msg)
            text = " ".join(w for w in text.split()
                            if w.lower() not in ["remind","reminder","alarm","yaad","dilana","bata","dena","yaad","dilao","mujhe","mein"]).strip()
            return ("remind", {"time": ts, "text": text or "Reminder!"})
        m = _re.search(r'(\d{1,2}):(\d{2})', lower)
        if m:
            ts   = f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
            text = _re.sub(r'\d{1,2}:\d{2}', '', user_msg)
            text = " ".join(w for w in text.split()
                            if w.lower() not in ["remind","reminder","alarm","yaad","dilana","bata","dena"]).strip()
            return ("remind", {"time": ts, "text": text or "Reminder!"})

    # Diary — FIXED: preserve original text properly
    if any(w in lower for w in ["diary", "dairy", "diary mein", "dairy mein"]):
        # Remove only the trigger keywords, keep rest of text
        text = user_msg
        # Remove diary/dairy trigger phrases first
        for kw in ["diary mein likho", "dairy mein likho", "diary mein", "dairy mein",
                   "diary me likho", "dairy me likho", "diary me", "dairy me",
                   "diary", "dairy", "likho"]:
            text = _re.sub(r'(?i)\b' + _re.escape(kw) + r'\b', ' ', text)
        text = " ".join(text.split()).strip()
        if not text:
            text = user_msg  # fallback to original if everything got removed
        return ("diary", {"text": text})

    # Add task
    if any(w in lower for w in ["task add", "add task", "kaam add", "new task"]):
        title = user_msg
        for w in ["task add", "add task", "kaam add", "new task"]:
            title = _re.sub(w, "", title, flags=_re.IGNORECASE)
        title = title.strip()
        if title:
            return ("add_task", {"title": title[:80]})

    # Complete task
    if any(w in lower for w in ["task done", "kaam ho gaya", "complete kar liya"]):
        m    = _re.search(r'#?(\d+)', lower)
        hint = m.group(1) if m else lower[:30]
        return ("complete_task", {"hint": hint})

    # Expense
    expense_words = ["kharcha", "kharch", "spent", "rupees", "₹", "rs"]
    if any(w in lower for w in expense_words):
        m = _re.search(r'(\d+(?:\.\d+)?)', lower)
        if m:
            amount = float(m.group(1))
            desc   = _re.sub(r'(\d+(?:\.\d+)?|rs\.?|₹|rupees?)', "", user_msg, flags=_re.IGNORECASE)
            desc   = " ".join(w for w in desc.split()
                              if w.lower() not in expense_words).strip()
            return ("expense", {"amount": amount, "desc": desc or "Expense"})

    # Habit add
    if "habit add" in lower or "add habit" in lower:
        name = _re.sub(r'habit add|add habit', "", user_msg, flags=_re.IGNORECASE).strip()
        return ("add_habit", {"name": name[:50]})

    # Habit done
    if "habit done" in lower or "habit ho gayi" in lower:
        m       = _re.search(r'#?(\d+)', lower)
        keyword = m.group(1) if m else lower[:30]
        return ("habit_done", {"keyword": keyword})

    # Water
    if any(w in lower for w in ["paani piya", "water piya", "water log"]):
        m  = _re.search(r'(\d+)\s*(ml|glass|bottle)', lower)
        ml = 250
        if m:
            val, unit = int(m.group(1)), m.group(2)
            ml = val*250 if "glass" in unit else val*500 if "bottle" in unit else val
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
    log.info(f"📥 '{user_msg[:60]}' → {action_type} | params={params}")

    if action_type == "remind":
        r = reminders.add(update.effective_chat.id,
                          params.get("text", "Reminder"),
                          params.get("time", ""))
        await update.message.reply_text(
            f"✅ Reminder: *{params.get('time')}* — {params.get('text')}\n🆔 #{r['id']}",
            parse_mode="Markdown")

    elif action_type == "add_task":
        t = tasks.add(params.get("title", ""))
        await update.message.reply_text(f"✅ Task #{t['id']}: {t['title']}")

    elif action_type == "complete_task":
        hint    = params.get("hint", "")
        matched = next(
            (t for t in tasks.pending()
             if str(t["id"]) == hint or (hint and hint in t["title"].lower())), None)
        if matched:
            tasks.complete(matched["id"])
            await update.message.reply_text(f"🎉 Done! ✅ {matched['title']}")
        else:
            await update.message.reply_text("❓ Kaunsa task? ID ya naam batao")

    elif action_type == "expense":
        expenses.add(params.get("amount", 0), params.get("desc", ""))
        await update.message.reply_text(
            f"💰 ₹{params.get('amount')} — {params.get('desc')}\n"
            f"📊 Aaj total: ₹{expenses.today_total()}")

    elif action_type == "diary":
        text = params.get("text", "")
        diary.add(text)
        await update.message.reply_text(
            f"📖 *Diary saved!* ✅\n_{text[:100]}_",
            parse_mode="Markdown")

    elif action_type == "add_habit":
        h = habits.add(params.get("name", ""))
        await update.message.reply_text(f"💪 Habit #{h['id']}: {h['name']}")

    elif action_type == "habit_done":
        keyword = params.get("keyword", "")
        if keyword.isdigit():
            ok, streak = habits.log(int(keyword))
            name = f"#{keyword}"
        else:
            ok, streak, h = habits.log_by_name(keyword)
            name = h["name"] if h else keyword
        if ok:
            await update.message.reply_text(f"💪 {name} done! 🔥 {streak} day streak!")
        else:
            await update.message.reply_text("❓ Kaunsa habit?")

    elif action_type == "water":
        total = water.add(params.get("ml", 250))
        await update.message.reply_text(
            f"💧 +{params.get('ml',250)}ml! Total: {total}/{water.goal()}ml")

    else:
        prompt = build_system_prompt() + f"\n\nUser: {user_msg}\n\nShort Hindi reply (2-3 lines):"
        reply  = call_gemini(prompt)
        if not reply:
            reply = _smart_fallback(user_msg)
        await update.message.reply_text(reply, parse_mode="Markdown")

    chat_hist.add("user",      user_msg, update.effective_user.first_name or "User")
    chat_hist.add("assistant", "Reply sent", "Bot")


def _smart_fallback(user_msg):
    msg = user_msg.lower()
    n   = now_ist()
    if any(w in msg for w in ["time", "kitne baje"]):
        return f"⏰ Abhi *{n.strftime('%I:%M %p')}* IST"
    if any(w in msg for w in ["date", "aaj kya tarikh"]):
        return f"📅 *{n.strftime('%A, %d %B %Y')}*"
    if any(w in msg for w in ["hello", "hi", "assalam", "namaste"]):
        return "🕌 *Assalamualaikum!* Kya help chahiye?"
    if any(w in msg for w in ["kaise ho", "how are"]):
        return "😊 *Main badiya hoon!* Aap sunao?"
    return "🙏 *Batao kya help chahiye?*\nTasks, reminders, kharcha, diary — sab kar sakta hoon!"

# ================================================================
# MAIN
# ================================================================
def main():
    log.info("=" * 60)
    log.info("🤖 Personal AI Bot — FIXED v2")
    log.info(f"⏰ IST: {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"📊 Sheets: {'✅' if sheets_backup.connected else '❌'}")
    log.info(f"🔐 GitHub: {'✅' if repo_manager.is_connected else '⚠️'}")
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

    # All commands
    for cmd, handler in [
        ("start",     cmd_start),
        ("help",      cmd_help),
        ("status",    cmd_status),
        ("datacheck", cmd_datacheck),
        ("sheetstest",cmd_sheetstest),
        ("task",      cmd_task),
        ("done",      cmd_done),
        ("habit",     cmd_habit),
        ("hdone",     cmd_hdone),
        ("kharcha",   cmd_kharcha),
        ("remind",    cmd_remind),
        ("delremind", cmd_delremind),
        ("water",     cmd_water),
        ("briefing",  cmd_briefing),
        ("save",      cmd_save),
        ("snooze5",   cmd_snooze),
        ("snooze10",  cmd_snooze),
        ("snooze30",  cmd_snooze),
        ("snooze60",  cmd_snooze),
    ]:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(CallbackQueryHandler(handle_ok_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=10)
        log.info("⏰ Alarm job: every 60s — re-rings until OK pressed")

    log.info("✅ Bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
