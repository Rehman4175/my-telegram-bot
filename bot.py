#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PERSONAL AI ASSISTANT BOT — FIXED v3
Changes from v2:
  - parse_user_message() completely rewritten — now catches ALL Hinglish patterns
  - "2 min baad paani pina hai" → reminder ✅
  - "chai pe 50 rupees" → expense ✅
  - "diary mein likho..." → diary ✅
  - "exercise ho gayi" → habit done ✅
  - handle_message() has debug logging so you can see what action fires
  - Alarm rings every minute until OK pressed (unchanged from v2)
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
# ALARM KEYBOARD
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
        f"Main aapka AI Dost hoon! 🤖\n\n"
        f"*Examples:*\n"
        f"• '2 min baad paani pina hai'\n"
        f"• 'Chai pe 50 rupees kharcha'\n"
        f"• 'Diary mein likho aaj accha din tha'\n"
        f"• 'Exercise ho gayi'\n\n"
        f"/help — sab commands",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *COMMANDS*\n\n"
        "🗣 *Natural Language:*\n"
        "  '2 min baad paani pina hai'\n"
        "  'Chai pe 50 rupees kharcha'\n"
        "  'Diary mein likho aaj...'\n"
        "  'Exercise habit ho gayi'\n"
        "  '250ml paani piya'\n\n"
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
        "`/datacheck` — data safety check",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    github_ok = "✅ Connected" if repo_manager.is_connected else "⚠️ Local only"
    sheets_ok = "✅ Connected" if sheets_backup.connected   else "❌ NOT connected"
    await update.message.reply_text(
        f"📊 *BOT STATUS*\n\n"
        f"🤖 Bot: ✅ Running\n"
        f"🔐 GitHub: {github_ok}\n"
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
    github_ok = repo_manager.is_connected
    sheets_ok = sheets_backup.connected
    total_diary     = sum(len(v) for v in diary.get_all_entries().values())
    total_tasks     = len(tasks.all_tasks())
    total_expenses  = len(expenses.store.data.get("list", []))
    total_habits    = len(habits.all())
    total_water     = len(water.store.data.get("logs", {}))
    total_reminders = len(reminders.get_all())
    github_status = "✅ GitHub pe safe hai" if github_ok else "⚠️ Sirf local"
    sheets_status = "✅ Sheets sync ho raha hai" if sheets_ok else "❌ Sheets sync BAND"
    sheets_live = "❓"
    if sheets_ok:
        try:
            ok = sheets_backup.log_event("DATACHECK", f"Manual check at {now_ist().strftime('%H:%M')}")
            sheets_live = "✅ Test PASS!" if ok else "❌ Test FAIL"
        except Exception as e:
            sheets_live = f"❌ Error: {e}"
    await update.message.reply_text(
        f"🔍 *DATA SAFETY CHECK*\n{'═'*25}\n\n"
        f"📦 *Saved data:*\n"
        f"  📖 Diary: {total_diary} entries\n"
        f"  📋 Tasks: {total_tasks}\n"
        f"  💰 Expenses: {total_expenses}\n"
        f"  💪 Habits: {total_habits}\n"
        f"  💧 Water: {total_water} din\n"
        f"  ⏰ Reminders: {total_reminders}\n\n"
        f"💾 *Storage:*\n  🔐 {github_status}\n  📊 {sheets_status}\n\n"
        f"🧪 *Sheets Live Test:* {sheets_live}",
        parse_mode="Markdown"
    )

async def cmd_sheetstest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Sheets test chal raha hai...")
    try:
        ok = sheets_backup.test_connection()
        if ok:
            await update.message.reply_text("✅ *Google Sheets WORKING!*", parse_mode="Markdown")
        else:
            await update.message.reply_text(
                "❌ *Sheets test FAILED!*\n\nCheck service account access.",
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
            await update.message.reply_text(f"🎉 Done! ✅ {t['title']}")
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
        await update.effective_chat.send_message("❌ *Galat Password!*", parse_mode="Markdown")
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
    await update.message.reply_text("❌ Diary cancelled.")
    return ConversationHandler.END

# ================================================================
# ALARM JOB
# ================================================================
async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now    = now_ist()
    now_hm = now.strftime("%H:%M")

    if now.hour == 0 and now.minute <= 1:
        reminders.reset_daily()
        log.info("🔄 Midnight reset done")
        return

    for r in reminders.due_now():
        log.info(f"🔔 First ring — #{r['id']} '{r['text']}' at {r['time']}")
        await _send_alarm(context, r)

    for r in reminders.all_active():
        if r.get("fired_today", False) and not r.get("acknowledged", False):
            log.info(f"🔔 Re-ring #{r['id']} (count={r.get('fire_count',0)}) '{r['text']}'")
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
            chat_id      = int(r["chat_id"]),
            text         = alert,
            reply_markup = alarm_keyboard(r["id"]),
            parse_mode   = "Markdown"
        )
        reminders.mark_fired(r["id"])
        log.info(f"✅ Alarm sent #{r['id']}: {r['text']}")
    except Exception as e:
        log.error(f"❌ Alarm send error #{r.get('id','?')}: {e}")

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
            await query.edit_message_text("✅ *Alarm band! Ab nahi bajega.* 🔕", parse_mode="Markdown")
            log.info(f"✅ Alarm #{rid} stopped by OK")
        else:
            await query.edit_message_text("⚠️ Pehle se band hai.")
    except Exception as e:
        log.error(f"OK button error: {e}")
        await query.edit_message_text("❌ Error!")

# ================================================================
# NATURAL LANGUAGE PARSER — FIXED v3
# ================================================================
def parse_user_message(user_msg):
    lower = user_msg.lower().strip()
    now   = now_ist()

    # ── 1. REMINDER ──────────────────────────────────────────────
    remind_triggers = [
        "remind", "reminder", "alarm", "set alarm",
        "yaad dilana", "yaad dilao", "yaad dila", "yaad kar",
        "bata dena", "bata do",
    ]
    # Time patterns
    m_min = _re.search(r'(\d+)\s*(min|minute|minutes)\b', lower)
    m_hr  = _re.search(r'(\d+)\s*(ghanta|ghante|hour|hours|hr)\b', lower)
    m_hm  = _re.search(r'(\d{1,2}):(\d{2})', lower)
    m_baj = _re.search(r'(\d{1,2})\s*baje\b', lower)

    has_time = bool(m_min or m_hr or m_hm or m_baj)
    has_remind_word = any(w in lower for w in remind_triggers)

    # Trigger reminder if: has reminder word + time, OR natural "X baad Y pina/karna/etc"
    baad_pattern = bool(_re.search(
        r'\d+\s*(min|minute|ghanta|ghante|hour|hr)\s*(baad|mein|me|ke baad)', lower
    ))

    if (has_remind_word and has_time) or baad_pattern or (has_time and has_remind_word):
        ts = None
        if m_min:
            ts = (now + timedelta(minutes=int(m_min.group(1)))).strftime("%H:%M")
        elif m_hr:
            ts = (now + timedelta(hours=int(m_hr.group(1)))).strftime("%H:%M")
        elif m_hm:
            ts = f"{int(m_hm.group(1)):02d}:{int(m_hm.group(2)):02d}"
        elif m_baj:
            ts = f"{int(m_baj.group(1)):02d}:00"

        if ts:
            text = user_msg
            # Strip time phrases
            text = _re.sub(r'\d+\s*(min|minute|minutes|ghanta|ghante|hour|hours|hr)\s*(baad|mein|me|ke baad)?',
                           '', text, flags=_re.IGNORECASE)
            text = _re.sub(r'\d{1,2}:\d{2}', '', text)
            text = _re.sub(r'\d+\s*baje\b', '', text, flags=_re.IGNORECASE)
            # Strip reminder keywords
            for kw in ["remind me", "reminder set karo", "reminder", "remind",
                       "alarm set karo", "alarm set kar", "alarm",
                       "yaad dilana", "yaad dilao", "yaad dila", "yaad kar",
                       "bata dena", "bata do",
                       "mujhe", "mujhko", "please", "plz", "ko", "ka", "ke"]:
                text = _re.sub(r'(?i)\b' + _re.escape(kw) + r'\b', ' ', text)
            text = " ".join(text.split()).strip(" ,-:")
            if not text or len(text) < 2:
                text = user_msg.strip()  # fallback: use original
            return ("remind", {"time": ts, "text": text})

    # ── 2. DIARY ─────────────────────────────────────────────────
    diary_triggers = [
        "diary mein likho", "diary me likho", "dairy mein likho", "dairy me likho",
        "diary mein", "dairy mein", "diary me", "dairy me",
        "journal mein", "journal me",
        "note kar lo", "note karo", "note kar",
        "diary",
    ]
    if any(w in lower for w in diary_triggers):
        text = user_msg
        for kw in sorted(diary_triggers, key=len, reverse=True):  # longest first
            text = _re.sub(r'(?i)' + _re.escape(kw), ' ', text)
        # Also remove "likho", "likh do"
        for kw in ["likho", "likh do", "likh", "save karo", "save kar"]:
            text = _re.sub(r'(?i)\b' + _re.escape(kw) + r'\b', ' ', text)
        text = " ".join(text.split()).strip(" ,-:")
        if not text or len(text) < 3:
            text = user_msg
        return ("diary", {"text": text})

    # ── 3. EXPENSE ───────────────────────────────────────────────
    expense_triggers = [
        "kharcha", "kharch", "spent", "spend", "rupees", "rupay", "rupee",
        "₹", "rs ", "rs.", "paisa", "paisay", "lagay", "laga",
        "pay kiya", "payment", "bill pay"
    ]
    has_rupee_amount = bool(
        _re.search(r'₹\s*\d+', lower) or
        _re.search(r'\d+\s*(rs\.?|rupee[s]?|rupay|paisa)', lower) or
        _re.search(r'\b\d{2,5}\b', lower)
    )
    if any(w in lower for w in expense_triggers) and has_rupee_amount:
        # Extract amount
        m = (_re.search(r'₹\s*(\d+(?:\.\d+)?)', lower) or
             _re.search(r'(\d+(?:\.\d+)?)\s*(?:rs\.?|rupee[s]?|rupay|paisa)', lower) or
             _re.search(r'\b(\d{2,6}(?:\.\d+)?)\b', lower))
        if m:
            amount = float(m.group(1))
            # Build description: remove amount + currency + trigger words
            desc = user_msg
            desc = _re.sub(r'₹\s*\d+(?:\.\d+)?', '', desc)
            desc = _re.sub(r'\d+(?:\.\d+)?\s*(?:rs\.?|rupee[s]?|rupay|paisa)?', '', desc, flags=_re.IGNORECASE)
            for kw in ["kharcha", "kharch", "spent", "spend", "rupees", "rupay",
                       "rupee", "rs", "paisa", "paisay", "lagay", "laga",
                       "pe", "par", "mein", "me", "ka", "ki", "ke", "pay kiya"]:
                desc = _re.sub(r'(?i)\b' + _re.escape(kw) + r'\b', ' ', desc)
            desc = " ".join(desc.split()).strip(" ,-:")
            if not desc or len(desc) < 2:
                desc = "Kharcha"
            return ("expense", {"amount": amount, "desc": desc})

    # ── 4. WATER ─────────────────────────────────────────────────
    water_triggers = [
        "paani piya", "pani piya", "water piya",
        "paani pi", "pani pi", "water pi",
        "water log", "water peena", "paani peena",
        "glass paani", "glass pani", "glass water",
        "bottle paani", "bottle pani",
        "ml paani", "ml pani", "ml water",
    ]
    if any(w in lower for w in water_triggers):
        m  = _re.search(r'(\d+)\s*(ml|glass|bottle)', lower)
        ml = 250
        if m:
            val, unit = int(m.group(1)), m.group(2)
            if "glass"  in unit: ml = val * 250
            elif "bottle" in unit: ml = val * 500
            else: ml = val
        return ("water", {"ml": ml})

    # ── 5. TASK ADD ──────────────────────────────────────────────
    task_add_triggers = [
        "task add", "add task", "kaam add", "new task",
        "task banao", "task bana", "task lagao", "todo add", "todo:"
    ]
    if any(w in lower for w in task_add_triggers):
        title = user_msg
        for kw in task_add_triggers:
            title = _re.sub(r'(?i)' + _re.escape(kw), '', title)
        title = title.strip(" ,-:")
        if title:
            return ("add_task", {"title": title[:80]})

    # ── 6. TASK COMPLETE ─────────────────────────────────────────
    task_done_triggers = [
        "task done", "kaam ho gaya", "kaam complete", "task complete",
        "kaam khatam", "complete kar liya", "finish kar liya",
        "done kar liya", "ho gaya task", "task ho gaya"
    ]
    if any(w in lower for w in task_done_triggers):
        m    = _re.search(r'#?(\d+)', lower)
        hint = m.group(1) if m else lower[:40]
        return ("complete_task", {"hint": hint})

    # ── 7. HABIT ADD ─────────────────────────────────────────────
    habit_add_triggers = [
        "habit add", "add habit", "new habit", "habit banao", "habit bana"
    ]
    if any(w in lower for w in habit_add_triggers):
        name = user_msg
        for kw in habit_add_triggers:
            name = _re.sub(r'(?i)' + _re.escape(kw), '', name)
        return ("add_habit", {"name": name.strip(" ,-:")[:50]})

    # ── 8. HABIT DONE ────────────────────────────────────────────
    habit_done_triggers = [
        "habit done", "habit ho gayi", "habit ho gaya", "habit complete",
        "habit kar li", "habit kar liya",
        "exercise ho gaya", "exercise ho gayi", "exercise kar liya",
        "gym ho gaya", "gym ho gayi", "gym kar liya",
        "walk ho gayi", "walk ho gaya", "walk kar liya",
        "running ho gayi", "running ho gaya",
        "yoga ho gayi", "yoga ho gaya",
        "meditation ho gayi", "meditation ho gaya",
    ]
    if any(w in lower for w in habit_done_triggers):
        m       = _re.search(r'#?(\d+)', lower)
        keyword = m.group(1) if m else lower[:40]
        # Try to extract habit name from message
        for kw in ["ho gayi", "ho gaya", "kar li", "kar liya", "done", "complete"]:
            keyword = _re.sub(r'(?i)\b' + _re.escape(kw) + r'\b', '', keyword)
        keyword = keyword.strip()
        if not keyword:
            keyword = lower[:40]
        return ("habit_done", {"keyword": keyword})

    # ── 9. FALLBACK: AI CHAT ─────────────────────────────────────
    return ("chat", {"text": user_msg})


# ================================================================
# MESSAGE HANDLER — with action debug logging
# ================================================================
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_msg = update.message.text.strip()
    if user_msg.startswith("/"):
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    action_type, params = parse_user_message(user_msg)

    # Always log what action was detected — helps debug
    log.info(f"📥 MSG: '{user_msg[:60]}'")
    log.info(f"🎯 ACTION: {action_type} | PARAMS: {params}")

    if action_type == "remind":
        r = reminders.add(
            update.effective_chat.id,
            params.get("text", "Reminder"),
            params.get("time", "")
        )
        await update.message.reply_text(
            f"✅ *Reminder Set!*\n"
            f"🕐 {params.get('time')} — {params.get('text')}\n"
            f"🆔 #{r['id']} | once",
            parse_mode="Markdown"
        )

    elif action_type == "add_task":
        t = tasks.add(params.get("title", ""))
        await update.message.reply_text(
            f"✅ *Task Added!*\n📋 #{t['id']} — {t['title']}",
            parse_mode="Markdown"
        )

    elif action_type == "complete_task":
        hint    = params.get("hint", "")
        matched = next(
            (t for t in tasks.pending()
             if str(t["id"]) == hint or (hint and hint.lower() in t["title"].lower())),
            None
        )
        if matched:
            tasks.complete(matched["id"])
            await update.message.reply_text(f"🎉 *Done!* ✅ {matched['title']}", parse_mode="Markdown")
        else:
            pending = tasks.pending()
            if pending:
                lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:10])
                await update.message.reply_text(
                    f"❓ Kaunsa task complete hua?\n\n{lines}\n\n_/done <id>_",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("📋 Koi pending task nahi!")

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
            f"📖 *Diary Saved!* ✅\n_{text[:100]}_",
            parse_mode="Markdown"
        )

    elif action_type == "add_habit":
        h = habits.add(params.get("name", ""))
        await update.message.reply_text(
            f"💪 *Habit Added!*\n#{h['id']} — {h['name']}",
            parse_mode="Markdown"
        )

    elif action_type == "habit_done":
        keyword = params.get("keyword", "")
        if keyword.strip().isdigit():
            ok, streak = habits.log(int(keyword.strip()))
            name = f"Habit #{keyword.strip()}"
        else:
            ok, streak, h = habits.log_by_name(keyword)
            name = h["name"] if h else keyword
        if ok:
            await update.message.reply_text(
                f"💪 *{name}* ho gayi! 🔥 *{streak} day streak!*",
                parse_mode="Markdown"
            )
        else:
            all_h = habits.all()
            if all_h:
                lines = "\n".join(f"#{h['id']} {h['name']}" for h in all_h)
                await update.message.reply_text(
                    f"❓ Kaunsa habit?\n\n{lines}\n\n_/hdone <id>_",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("💪 Koi habit nahi. /habit se add karo!")

    elif action_type == "water":
        ml    = params.get("ml", 250)
        total = water.add(ml)
        goal  = water.goal()
        pct   = int(total / goal * 100) if goal else 0
        bar   = "💧" * min(10, pct // 10) + "⬜" * (10 - min(10, pct // 10))
        await update.message.reply_text(
            f"💧 *+{ml}ml paani!*\n{bar}\n{total}ml / {goal}ml ({pct}%)",
            parse_mode="Markdown"
        )

    else:  # chat
        prompt = build_system_prompt() + f"\n\nUser: {user_msg}\n\nShort Hindi reply (2-3 lines):"
        reply  = call_gemini(prompt)
        if not reply:
            reply = _smart_fallback(user_msg)
        await update.message.reply_text(reply, parse_mode="Markdown")

    chat_hist.add("user",      user_msg, update.effective_user.first_name or "User")
    chat_hist.add("assistant", f"Action: {action_type}", "Bot")


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
    log.info("🤖 Personal AI Bot — FIXED v3")
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

    for cmd, handler in [
        ("start",      cmd_start),
        ("help",       cmd_help),
        ("status",     cmd_status),
        ("datacheck",  cmd_datacheck),
        ("sheetstest", cmd_sheetstest),
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

    log.info("✅ Bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
