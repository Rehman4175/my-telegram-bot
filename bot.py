#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PERSONAL AI ASSISTANT — RK BOT
FIXED VERSION:
  - Calendar natural language properly detected BEFORE task
  - Habit natural language properly detected BEFORE task
  - "Saare task dikhao / show task / task list" → list dikhata hai, add nahi karta
  - Memory command added
  - Priority order: reminder > show_tasks > habit_done > habit_add > calendar > bill > diary > water > expense > task_complete > task_add > chat
  
FIXES v2:
  - Daily_Logs → Miscellaneous tab
  - Diary SHOW commands fixed: "diary dikhao / show diary / diary dekho" → shows, does NOT add
  - Goals add working
  - Habits sheet sync fixed

FIXES v3 (DELETE PASSWORD FIX):
  - register_delete_handlers() ko sabse PEHLE register kiya
  - ConversationHandler order fix — delete password ab properly capture hoga
  - handle_message SABSE AAKHIR mein register hoga
"""

import os, json, logging, time, asyncio, random
import urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta, timezone
import re as _re

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

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DIARY_PASSWORD = os.environ.get("DIARY_PASSWORD", "Rk1996")

DIARY_AWAIT_PASS = 0
DIARY_AWAIT_TEXT = 1
CAL_AWAIT_PASS  = 10
CAL_AWAIT_DATA  = 11

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
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            log.warning(f"Gemini error ({model}): {e}")
    return None

def build_system_prompt():
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    exp_t = expenses.today_total()
    wt = water.today_total()
    wg = water.goal()
    active_rem = reminders.all_active()
    today_events = calendar.today_events()
    return (f"Tu mera Personal AI Assistant hai — naam Rk.\n"
            f"Main ek Muslim hoon, isliye Muslim greetings aur phrases use karo jaise:\n"
            f"Assalamualaikum, Alhamdulillah, InshAllah, MashAllah, SubhanAllah, JazakAllah Khair.\n"
            f"TIME: {now_ist().strftime('%A, %d %b — %I:%M %p')} IST\n\n"
            f"Tasks: {len(tp)} pending\n"
            f"Habits: {len(hd)} done, {len(hp)} pending\n"
            f"Kharcha: Rs.{exp_t}\n"
            f"Paani: {wt}ml/{wg}ml\n"
            f"Reminders: {len(active_rem)} active\n"
            f"Aaj ke events: {len(today_events)}\n\n"
            f"Hamesha Hinglish mein SHORT jawab do. Muslim phrases zaroor use karo.")

def alarm_keyboard(rid):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ OK — Alarm Band Karo", callback_data=f"ok_{rid}")
    ]])

# ================================================================
# BASIC COMMANDS
# ================================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Bhai"
    await update.message.reply_text(
        f"☪️ Assalamualaikum {name}! 🤝\n\n"
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
        "• `netflix bill add karo 499 15 tarikh`\n"
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
        "/remind 30m Chai — Reminder set karo\n"
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
        "/delsheet — Sheet se ek row delete\n"
        "/nukesheet — Ek poori sheet wipe\n"
        "/nukeall — Sab kuch delete (nuclear option)\n\n"
        "📊 *Other:*\n"
        "/briefing — Daily summary\n"
        "/status — System status\n"
        "/checksync — GitHub & Sheets check\n"
        "/help — Yeh menu",
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
            result = subprocess.run(["git", "-C", DATA_DIR, "log", "-1", "--format=%cd"], capture_output=True, text=True)
            if result.returncode == 0:
                last_sync = result.stdout.strip()
        except:
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
            await update.message.reply_text(
                f"✅ *Alhamdulillah! Task Complete!* 🎉\n\n#{t['id']} ~~{t['title']}~~\n\nMashAllah, kaam kar diya! 💪",
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
        all_t = tasks.all_tasks()
        target = next((t for t in all_t if t["id"] == tid), None)
        if not target:
            await update.message.reply_text(f"❌ Task #{tid} nahi mila!")
            return
        tasks.delete(tid)
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
            await update.message.reply_text(
                f"🔥 *Habit Done! MashAllah!* 🎉\n\n{streak} din ka streak! Aage badhte raho! 💪",
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
    pct = int(total / goal * 100)
    filled = min(pct // 20, 5)
    bar = "🟦" * filled + "⬜" * (5 - filled)
    await update.message.reply_text(
        f"💧 *+{ml}ml Paani!*\n\nTotal: {total}/{goal}ml\n{bar} {pct}%\n\n"
        f"{'Alhamdulillah! Goal complete! 🎉' if total >= goal else 'InshAllah goal poora hoga! 💪'}",
        parse_mode="Markdown"
    )

# ================================================================
# REMINDER COMMANDS
# ================================================================

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        active = reminders.all_active()
        if active:
            lines = "\n".join(f"  ⏰ #{r['id']} {r['time']} — {r['text']}" for r in active)
            await update.message.reply_text(
                f"⏰ *Active Reminders ({len(active)}):*\n\n{lines}\n\n/remind 30m Chai — Naya set karo",
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
        remind_at = (now + timedelta(minutes=int(time_arg[:-1]))).strftime("%H:%M")
    elif ":" in time_arg:
        parts = time_arg.split(":")
        remind_at = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    else:
        await update.message.reply_text("/remind 30m Chai ya /remind 15:30 Meeting")
        return
    r = reminders.add(update.effective_chat.id, text, remind_at)
    await update.message.reply_text(
        f"⏰ *Reminder Set! InshAllah yaad dilaaunga!*\n\n🕐 {remind_at} baje: {text}\n📌 ID #{r['id']}",
        parse_mode="Markdown"
    )

async def cmd_delremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        try:
            rid = int(ctx.args[0])
            target = reminders.get_by_id(rid)
            if not target:
                await update.message.reply_text(f"❌ Reminder #{rid} nahi mila!")
                return
            reminders.delete(rid)
            await update.message.reply_text(
                f"🗑️ *Reminder Delete Ho Gaya!*\n\n#{rid} '{target['text']}'\n\nSheets se bhi hata diya. ✅",
                parse_mode="Markdown"
            )
        except Exception:
            await update.message.reply_text("❌ Invalid ID!")
    else:
        await update.message.reply_text("/delremind id")

async def cmd_snooze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.split()[0].lstrip("/").lower()
    snooze_map = {"snooze5": 5, "snooze10": 10, "snooze30": 30, "snooze60": 60}
    mins = snooze_map.get(cmd, 10)
    if not ctx.args:
        await update.message.reply_text(f"/{cmd} reminder_id", parse_mode="Markdown")
        return
    try:
        rid = int(ctx.args[0])
        target = reminders.get_by_id(rid)
        if not target:
            await update.message.reply_text(f"❌ Reminder #{rid} nahi mila!")
            return
        reminders.acknowledge(rid, f"Snoozed {mins}min")
        new_time = (now_ist() + timedelta(minutes=mins)).strftime("%H:%M")
        new_rem = reminders.add(target["chat_id"], f"🔁 {target['text']}", new_time, "once")
        await update.message.reply_text(
            f"😴 *Snooze Ho Gaya!*\n\n{mins} min baad fir yaad dilaaunga.\nNew ID: #{new_rem['id']}",
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

    if mode == "write":
        pending_text = ctx.user_data.get("diary_pending_text", "")
        if pending_text:
            diary.add(pending_text)
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
        if not week_entries:
            await update.effective_chat.send_message("📖 Is hafte koi entry nahi.", parse_mode="Markdown")
        else:
            msg = "\n\n".join(week_entries[:10])
            await update.effective_chat.send_message(
                f"📖 *Is hafte ki Diary:*\n\n{msg[:3000]}",
                parse_mode="Markdown"
            )

    elif mode == "view_all":
        all_entries = diary.get_all_entries()
        count = sum(len(v) for v in all_entries.values())
        dates = sorted(all_entries.keys(), reverse=True)
        preview = []
        for d in dates[:5]:
            for e in all_entries[d][:2]:
                preview.append(f"📅 {d}\n{e['text'][:100]}")
        msg = "\n\n".join(preview)
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
    await update.message.reply_text(
        f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n_{text[:200]}_\n\nSheets mein bhi backup ho gaya!",
        parse_mode="Markdown"
    )

# ================================================================
# CALENDAR COMMANDS
# ================================================================

async def cmd_cal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    events = calendar.upcoming(days=30)
    if not events:
        await update.message.reply_text(
            "📅 Koi upcoming event nahi hai.\n\n/caladd — Event ya birthday add karo",
            parse_mode="Markdown"
        )
        return
    lines = []
    for e in events[:15]:
        type_emoji = "🎂" if e.get("type") == "birthday" else "📅"
        time_str = f" ⏰{e['time']}" if e.get("time") else ""
        loc_str  = f" 📍{e['location']}" if e.get("location") else ""
        lines.append(f"{type_emoji} *{e['date']}*{time_str} — #{e['id']}\n   {e['title']}{loc_str}")
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
        type_emoji = "🎂" if e.get("type") == "birthday" else "📅"
        time_str = f" ⏰{e['time']}" if e.get("time") else ""
        loc_str  = f"\n   📍{e['location']}" if e.get("location") else ""
        notes_str = f"\n   📝{e['notes']}" if e.get("notes") else ""
        lines.append(f"{type_emoji} #{e['id']} *{e['title']}*{time_str}{loc_str}{notes_str}")
    await update.message.reply_text(
        f"📅 *Aaj ke Events ({today_str()}):*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown"
    )

async def cmd_calweek(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    events = calendar.upcoming(days=7)
    if not events:
        await update.message.reply_text("📅 Is hafte koi event nahi.", parse_mode="Markdown")
        return
    lines = []
    for e in events:
        type_emoji = "🎂" if e.get("type") == "birthday" else "📅"
        time_str = f" ⏰{e['time']}" if e.get("time") else ""
        loc_str  = f" 📍{e['location']}" if e.get("location") else ""
        lines.append(f"{type_emoji} *{e['date']}*{time_str} — #{e['id']}\n   {e['title']}{loc_str}")
    await update.message.reply_text(
        f"📅 *Is hafte ke Events:*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown"
    )

async def cmd_caladd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "📅 *Event ya Birthday Add Karo:*\n\n"
            "*Normal Event:*\n"
            "`/caladd 2026-05-20 Doctor 10:30 Apollo Hospital`\n\n"
            "*Birthday:*\n"
            "`/caladd 2000-09-09 Simran birthday`\n\n"
            "Format: `/caladd YYYY-MM-DD Title [HH:MM] [Location]`\n\n"
            "⚠️ Birthday mein year woh hoga jab paida hua — bot automatically next birthday calculate karega!",
            parse_mode="Markdown"
        )
        return

    args = ctx.args
    event_date = args[0]
    if not _re.match(r'\d{4}-\d{2}-\d{2}', event_date):
        await update.message.reply_text(
            "❌ Pehle date likhna padega: YYYY-MM-DD\n\nExample: /caladd 2026-05-20 Meeting",
            parse_mode="Markdown"
        )
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
    is_birthday = "birthday" in title.lower() or "bday" in title.lower() or "janamdin" in title.lower()
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
    time_str  = f"\n⏰ Time: {event_time}" if event_time else ""
    loc_str   = f"\n📍 Location: {location}" if location else ""
    type_emoji = "🎂" if is_birthday else "📅"

    if is_birthday:
        msg = (f"{type_emoji} *Birthday Add Ho Gaya! MashAllah!* 🎉\n\n"
               f"#{e['id']} 🎂 *{actual_date}*\n👤 {title}{loc_str}\n\n"
               f"✅ Ek din pehle remind karunga InshAllah!\n📊 Sheets mein bhi save ho gaya!")
    else:
        msg = (f"{type_emoji} *Calendar Event Add Ho Gaya!* ✅\n\n"
               f"#{e['id']} 📅 *{actual_date}*{time_str}\n📌 {title}{loc_str}\n\n"
               f"✅ Ek din pehle remind karunga InshAllah!\n📊 Sheets mein bhi save ho gaya!")
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_caldel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        events = calendar.upcoming(days=30)
        if events:
            lines = "\n".join(
                f"  {'🎂' if e.get('type')=='birthday' else '📅'} #{e['id']} {e['date']} {e['title']}"
                for e in events[:10]
            )
            await update.message.reply_text(
                f"Kaunsa event delete karna hai?\n\n{lines}\n\n/caldel id",
                parse_mode="Markdown"
            )
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
        await update.message.reply_text("💳 Koi active bill nahi hai.\n\n/billadd — Naya bill add karo", parse_mode="Markdown")
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
        except:
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
            "💳 *Bill Add Karo:*\n\nFormat: `/billadd Name Amount DueDay`\n\n"
            "Examples:\n`/billadd Netflix 499 15`\n`/billadd LIC 3500 5`\n`/billadd Electricity 1200 20`\n`/billadd Jio 299 1 Yes UPI`\n\n"
            "DueDay = Kitni tarikh ko bill aata hai",
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
        await update.message.reply_text(
            f"💳 *Bill Add Ho Gaya! Alhamdulillah!* ✅\n\n#{b['id']} *{name}*\n"
            f"💰 Rs.{amount}\n📅 Due: Har mahine {due_day} tarikh\n"
            f"🔄 Auto Pay: {auto_pay}\n💳 Payment: {payment_method if payment_method else 'Not set'}\n\n"
            f"📊 'Bills & Subscriptions' sheet mein save ho gaya!",
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
            await update.message.reply_text("✅ Alhamdulillah! Is mahine ke sab bills paid hain!", parse_mode="Markdown")
        return
    try:
        bid = int(ctx.args[0])
        target = bills.get_by_id(bid)
        if not target:
            await update.message.reply_text(f"❌ Bill #{bid} nahi mila!")
            return
        ok = bills.mark_paid(bid)
        if ok:
            await update.message.reply_text(
                f"✅ *Bill Paid! Alhamdulillah!* 🎉\n\n#{bid} *{target['name']}* — Rs.{target['amount']}\n\nIs mahine ka bill mark ho gaya! 📊",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"ℹ️ #{bid} {target['name']} is mahine pehle hi paid mark hai!", parse_mode="Markdown")
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
        next_ev = week_ev[0]
        events_str = f"\n\n📅 *Agla Event:*\n  {'🎂' if next_ev.get('type')=='birthday' else '📅'} {next_ev['date']} {next_ev['title']}"

    bills_str = ""
    if due_bills:
        bills_str = "\n\n💳 *Bills Due Soon:*\n" + "\n".join(
            f"  ⚠️ {b['name']} — Rs.{b['amount']} ({b['due_day']} tarikh)"
            for b in due_bills
        )

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
# REMINDER JOB
# ================================================================

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now = now_ist()
    now_hm = now.strftime("%H:%M")

    if now.hour == 0 and now.minute <= 1:
        reminders.reset_daily()

    if now_hm == "21:00":
        tomorrow_events = calendar.events_needing_reminder()
        for e in tomorrow_events:
            type_emoji = "🎂" if e.get("type") == "birthday" else "📅"
            chat_ids = set()
            for r in reminders.get_all():
                cid = r.get("chat_id", "")
                if cid:
                    chat_ids.add(cid)
            if not chat_ids:
                log.warning("No chat IDs found for day-before reminder")
                continue
            for cid in chat_ids:
                try:
                    msg = (f"{type_emoji} *Kal ka Event! InshAllah tayaar raho!*\n\n"
                           f"📅 Kal: {e['date']}\n📌 {e['title']}\n")
                    if e.get("time"):
                        msg += f"⏰ Time: {e['time']}\n"
                    if e.get("location"):
                        msg += f"📍 {e['location']}\n"
                    if e.get("type") == "birthday":
                        msg += f"\n🎂 Birthday hai! Mubarak dena mat bhoolo! 🎉"
                    await context.bot.send_message(chat_id=int(cid), text=msg, parse_mode="Markdown")
                    log.info(f"Day-before reminder sent for event #{e['id']} to {cid}")
                except Exception as ex:
                    log.error(f"Day-before reminder failed: {ex}")

    if now_hm == "09:00":
        due_bills = bills.due_soon(days=3)
        if due_bills:
            chat_ids = set()
            for r in reminders.get_all():
                cid = r.get("chat_id", "")
                if cid:
                    chat_ids.add(cid)
            for cid in chat_ids:
                try:
                    lines = "\n".join(f"  💳 {b['name']} — Rs.{b['amount']} (due {b['due_day']} tarikh)" for b in due_bills)
                    await context.bot.send_message(
                        chat_id=int(cid),
                        text=f"⚠️ *Bill Due Soon! Dhyan rakhna!*\n\n{lines}\n\n/billpaid id — Paid mark karo",
                        parse_mode="Markdown"
                    )
                except Exception as ex:
                    log.error(f"Bills reminder failed: {ex}")

    for r in reminders.all_active():
        if r.get("acknowledged", False):
            continue
        reminder_time = r.get("time", "")
        if reminder_time == now_hm:
            last_fired_minute = r.get("last_fired_minute", "")
            if last_fired_minute == now_hm:
                continue
            fire_count = r.get("fire_count", 0)
            suffix = ""
            if fire_count > 0:
                suffix = f"\n⚠️ {fire_count + 1}vi baar baj raha hai — OK dabao!"
            alert = (f"🚨 *ALARM!*\n{'━' * 20}\n⏰ *{reminder_time} BAJ GAYE!*\n{'━' * 20}\n\n"
                     f"🔔 *{r['text'].upper()}*\n{suffix}\n\n"
                     f"😴 Snooze: /snooze5 {r['id']} | /snooze10 {r['id']}\n"
                     f"🗑️ Delete: /delremind {r['id']}")
            try:
                await context.bot.send_message(
                    chat_id=int(r["chat_id"]),
                    text=alert,
                    reply_markup=alarm_keyboard(r["id"]),
                    parse_mode="Markdown"
                )
                for item in reminders.store.data["list"]:
                    if item["id"] == r["id"]:
                        item["fire_count"]        = item.get("fire_count", 0) + 1
                        item["last_fired_minute"] = now_hm
                        item["last_fired"]        = now_ist().isoformat()
                        break
                reminders.store.save()
                log.info(f"Alarm fired #{r['id']} at {now_hm}")
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
            log.info(f"OK pressed for #{rid} — {count} reminders dismissed")
        except Exception as e:
            log.error(f"OK button error: {e}")
            await query.edit_message_text("❌ Error stopping alarm!")

# ================================================================
# NATURAL LANGUAGE PARSER
# ================================================================

MONTH_MAP = {
    "jan": 1, "january": 1, "janvary": 1,
    "feb": 2, "february": 2, "febrvary": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5, "mei": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
    "januari": 1, "februari": 2, "maret": 3,
    "juni": 6, "juli": 7, "agustus": 8,
    "oktober": 10, "desember": 12
}

def _parse_date_from_text(text):
    lower = text.lower()
    now = now_ist()
    today_d = now.date()

    m = _re.search(r'(\d{1,4})[-/](\d{1,2})[-/](\d{2,4})', lower)
    if m:
        a, b, c = m.group(1), m.group(2), m.group(3)
        try:
            if len(a) == 4:
                yr, mo, dy = int(a), int(b), int(c)
            elif len(c) == 4:
                dy, mo, yr = int(a), int(b), int(c)
            else:
                dy, mo, yr = int(a), int(b), int(c) + 2000
            d = date(yr, mo, dy)
            remaining = _re.sub(r'\d{1,4}[-/]\d{1,2}[-/]\d{2,4}', '', text).strip()
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
            if date(yr, mon, day) < today_d:
                yr += 1
        try:
            d = date(yr, mon, day)
            remaining = _re.sub(r'\d{1,2}\s+(?:' + month_pattern + r')(?:\s+\d{2,4})?', '', text, flags=_re.IGNORECASE).strip()
            return d.strftime("%Y-%m-%d"), remaining
        except Exception:
            pass

    if "parso" in lower:
        d = today_d + timedelta(days=2)
        return d.strftime("%Y-%m-%d"), _re.sub(r'\bparso\b', '', text, flags=_re.IGNORECASE).strip()
    if _re.search(r'\bkal\b|\bkl\b', lower):
        d = today_d + timedelta(days=1)
        remaining = _re.sub(r'\bkal\b|\bkl\b', '', text, flags=_re.IGNORECASE).strip()
        return d.strftime("%Y-%m-%d"), remaining
    if "aaj" in lower:
        return today_d.strftime("%Y-%m-%d"), _re.sub(r'\baaj\b', '', text, flags=_re.IGNORECASE).strip()

    return None, text


def parse_user_message(user_msg: str):
    lower = user_msg.lower().strip()
    now = now_ist()

    # 1. SHOW REMINDERS
    show_reminder_phrases = [
        "reminder dikhao", "reminder dekho", "reminder list", "reminders dikhao",
        "active reminder", "reminder show", "show reminder", "mera reminder",
        "reminder batao", "reminder kya hai", "alarm dikhao", "alarm list",
        "alarm show", "show alarm", "kitne reminder", "saare reminder",
        "sare reminder", "reminder check",
    ]
    if any(p in lower for p in show_reminder_phrases):
        return ("show_reminders", {})

    # 2. SHOW TASKS
    show_task_phrases = [
        "saare task", "sare task", "task list", "task dikhao", "task dekho",
        "task show", "show task", "pending task", "meri task", "tasks dikhao",
        "tasks dekho", "kya task", "task kya hai", "task batao",
    ]
    if any(p in lower for p in show_task_phrases):
        return ("show_tasks", {})

    # 3. SHOW HABITS
    show_habit_phrases = [
        "saari habit", "sari habit", "habit list", "habit dikhao", "habit dekho",
        "habit show", "show habit", "meri habit", "habits dikhao", "habits dekho",
        "kya habit", "habit batao", "aaj ki habit",
    ]
    if any(p in lower for p in show_habit_phrases):
        return ("show_habits", {})

    # 4. SHOW DIARY
    show_diary_phrases = [
        "diary dikhao", "diary dekho", "diary padho", "show diary",
        "diary show", "diary dekhao", "aaj ki diary", "meri diary",
        "diary kya hai", "diary batao", "dairy dikhao", "dairy dekho",
        "dairy show", "show dairy",
    ]
    if any(p in lower for p in show_diary_phrases):
        return ("show_diary", {})

    # 5. SHOW CALENDAR
    show_cal_phrases = [
        "calendar dikhao", "events dikhao", "events dekho", "upcoming events",
        "aaj ka event", "cal dikhao", "schedule dikhao", "kya event",
    ]
    if any(p in lower for p in show_cal_phrases):
        return ("show_calendar", {})

    # 6. REMINDER
    remind_words = [
        "remind", "reminder", "alarm", "yaad dilana", "bata dena",
        "yaad dila", "yaad dila do", "yaad kara", "add reminder",
        "set reminder", "set alarm", "reminder set", "alarm set",
        "yaad dilao", "yaad krao", "yaad kara do",
    ]
    if any(w in lower for w in remind_words):

        def _parse_reminder_time(lwr):
            now_t = now_ist()
            mm = _re.search(r'(\d+)\s*(?:min(?:ute)?s?)\b', lwr)
            if mm:
                mins = int(mm.group(1))
                t = now_t + timedelta(minutes=mins)
                return t.strftime("%H:%M"), False

            mm = _re.search(r'(\d{1,2}):(\d{2})', lwr)
            if mm:
                h, mi = int(mm.group(1)), int(mm.group(2))
                is_tom = "kal" in lwr or "kl" in lwr or "tomorrow" in lwr
                return f"{h:02d}:{mi:02d}", is_tom

            mm = _re.search(r'(\d{1,2})\s*(?:baj[ae]?(?:y)?|am\b|pm\b|a\.m|p\.m)', lwr)
            if mm:
                h = int(mm.group(1))
                if _re.search(r'\b(?:pm|sham|shaam|raat|evening|night)\b', lwr):
                    if h != 12:
                        h += 12
                    if h >= 24:
                        h = h - 12
                elif _re.search(r'\b(?:am|subha|subah|morning|dopahar)\b', lwr) and h == 12:
                    h = 0
                elif h < 6:
                    h += 12
                is_tom = "kal" in lwr or "kl" in lwr or "tomorrow" in lwr
                return f"{h:02d}:00", is_tom

            time_word_map = {
                "subha": "08:00", "subah": "08:00", "morning": "08:00",
                "dopahar": "13:00", "lunch": "13:00",
                "shaam": "18:00", "sham": "18:00", "evening": "18:00",
                "raat": "21:00", "night": "21:00",
                "midnight": "00:00", "aadhi raat": "00:00",
            }
            for word, tstr in time_word_map.items():
                if word in lwr:
                    is_tom = "kal" in lwr or "kl" in lwr or "tomorrow" in lwr
                    return tstr, is_tom

            return None, False

        time_str, is_tomorrow = _parse_reminder_time(lower)

        if time_str:
            stop_words = remind_words + [
                "kal", "kl", "aaj", "tomorrow", "subha", "subah", "morning",
                "shaam", "sham", "raat", "night", "evening", "dopahar",
                "baje", "bajay", "baj", "pe", "par", "ko", "mein", "me",
                "mujhe", "mujhko", "please", "plz", "zara", "jara",
            ]
            text_clean = lower
            text_clean = _re.sub(r'\d+\s*(?:min(?:ute)?s?)\b', '', text_clean)
            text_clean = _re.sub(r'\d{1,2}:\d{2}', '', text_clean)
            text_clean = _re.sub(r'\d{1,2}\s*(?:baj[ae]?(?:y)?|am\b|pm\b)', '', text_clean)
            for sw in stop_words:
                text_clean = _re.sub(r'\b' + _re.escape(sw) + r'\b', ' ', text_clean)
            text_clean = " ".join(text_clean.split()).strip().title() or "Kaam"
            prefix = "🗓️ Kal: " if is_tomorrow else ""
            return ("remind", {"time": time_str, "text": f"{prefix}{text_clean}", "tomorrow": is_tomorrow})

        return ("chat", {"text": user_msg})

    # 7. HABIT DONE
    habit_done_phrases = [
        "habit ho gayi", "habit ho gaya", "habit complete", "habit kar li",
        "habit kar liya", "habit done", "gym ho gaya", "gym kar liya",
        "exercise ho gayi", "exercise kar li", "walk ho gayi", "walk kar li",
        "reading ho gayi", "meditation ho gayi", "yoga ho gayi",
    ]
    if any(p in lower for p in habit_done_phrases):
        m = _re.search(r'#?(\d+)', lower)
        keyword = m.group(1) if m else lower[:40]
        return ("habit_done", {"keyword": keyword})

    # 8. HABIT ADD
    habit_add_phrases = [
        "habit add", "add habit", "naya habit", "habit lagao", "habit bana",
        "habit start", "new habit", "habit banana",
    ]
    if any(p in lower for p in habit_add_phrases):
        name = user_msg
        for kw in habit_add_phrases + ["habit", "add", "naya", "new", "karo", "kr", "lagao", "bana", "start", "banana"]:
            name = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", name, flags=_re.IGNORECASE)
        name = " ".join(name.split()).strip()
        return ("add_habit", {"name": name[:50] or "Habit"})

    # 9. CALENDAR ADD
    cal_add_triggers = [
        "birthday", "bday", "b'day", "janamdin", "janmdin",
        "calendar add", "cal add", "event add", "add event",
        "calendar mein", "cal mein", "event hai", "ka birthday",
        "ki birthday", "ki janamdin", "ka janamdin",
    ]
    if any(t in lower for t in cal_add_triggers):
        date_str, remaining = _parse_date_from_text(user_msg)
        if date_str:
            title = remaining
            for kw in ["calendar", "cal", "event", "add", "karo", "kr", "mein", "me", "hai", "ka", "ki"]:
                title = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", title, flags=_re.IGNORECASE)
            title = " ".join(title.split()).strip()
            is_bday = any(w in lower for w in ["birthday", "bday", "janamdin", "janmdin", "b'day"])
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

    # 10. BILL ADD
    bill_add_triggers = [
        "bill add", "bill kro", "bill daal", "subscription add",
        "bill lagao", "bill likh", "add bill", "naya bill",
    ]
    if any(w in lower for w in bill_add_triggers):
        title = user_msg
        for kw in bill_add_triggers + ["bill", "add", "kro", "karo", "kr", "daal", "likh", "lagao", "naya", "subscription"]:
            title = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", title, flags=_re.IGNORECASE)
        title = " ".join(title.split()).strip()
        amount = 0
        amount_m = _re.search(r'(?:rs\.?|rupees?)?\s*(\d+(?:\.\d+)?)', title, _re.IGNORECASE)
        if amount_m:
            amount = float(amount_m.group(1))
        due_day = 0
        due_m = _re.search(r'(\d{1,2})\s*(?:tarikh|taarikh|date|th|st|nd|rd)?', title)
        if due_m:
            candidate = int(due_m.group(1))
            if 1 <= candidate <= 31 and candidate != amount:
                due_day = candidate
        name = _re.sub(r'\d+(?:\.\d+)?', '', title).strip()
        name = " ".join(name.split()).strip() or "Bill"
        return ("add_bill", {"name": name, "amount": amount, "due_day": due_day})

    # 11. DIARY ADD
    diary_add_phrases = [
        "diary mein likho", "diary me likho", "diary mein likh",
        "diary me likh", "diary add", "diary mein add", "diary me add",
        "diary mein daalo", "diary me daalo", "diary save",
        "dairy mein likho", "dairy me likho", "dairy add",
        "diary mein note", "diary me note",
    ]
    if any(p in lower for p in diary_add_phrases):
        text = user_msg
        for kw in ["diary", "dairy", "likho", "likh", "add", "save", "mein", "me",
                   "main", "daalo", "daal", "note", "karo"]:
            text = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", text, flags=_re.IGNORECASE)
        text = " ".join(text.split()).strip()
        return ("diary", {"text": text or user_msg})

    # 12. WATER
    water_triggers = ["paani piya", "water piya", "water log", "paani liya", "water pi", "paani pi"]
    if any(w in lower for w in water_triggers):
        m = _re.search(r'(\d+)\s*(ml|glass|bottle)', lower)
        ml = 250
        if m:
            val, unit = int(m.group(1)), m.group(2)
            ml = val * 250 if "glass" in unit else val * 500 if "bottle" in unit else val
        return ("water", {"ml": ml})

    # 13. EXPENSE
    expense_words = [
        "kharcha", "kharch", "spent", "rupees", "rs", "kharch kiya",
        "laga diye", "lagaya", "laga", "khaya", "piya", "liya", "diye",
        "pe lagaya", "mein lagaya", "ka kharcha", "pe laga",
    ]
    if any(w in lower for w in expense_words):
        m = _re.search(r'(\d+(?:\.\d+)?)', lower)
        if m:
            amount = float(m.group(1))
            desc = _re.sub(r'(\d+(?:\.\d+)?|rs\.?|rupees?)', "", user_msg, flags=_re.IGNORECASE)
            desc = " ".join(w for w in desc.split() if w.lower() not in expense_words).strip()
            return ("expense", {"amount": amount, "desc": desc or "Expense"})

    # 14. TASK COMPLETE
    task_done_phrases = [
        "task done", "kaam ho gaya", "kaam kar liya", "complete kar liya",
        "task complete", "ho gaya task", "kar liya task",
    ]
    if any(p in lower for p in task_done_phrases):
        m = _re.search(r'#?(\d+)', lower)
        hint = m.group(1) if m else lower[:30]
        return ("complete_task", {"hint": hint})

    # 15. TASK ADD
    task_add_words = [
        "task add", "add task", "naya task", "task lagao", "task likh",
        "task banana", "task karo", "new task",
        "kaam add", "kaam likh", "todo add", "add todo",
    ]
    kaam_soft = ["kaam karna hai", "kaam krna hai", "kaam karna he", "kaam krna he"]

    if any(p in lower for p in task_add_words):
        title = user_msg
        for kw in task_add_words + ["task", "kaam", "todo", "add", "karo", "kro", "kr",
                                     "lagao", "likh", "naya", "new", "banana", "karna"]:
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

    # 16. MEMORY SAVE
    memory_triggers = ["memory mein", "memory me", "yaad rakhna", "note karo", "note kr",
                       "save karo", "save kr", "remember karo"]
    if any(t in lower for t in memory_triggers):
        text = user_msg
        for kw in memory_triggers + ["memory", "mein", "me", "save", "karo", "kr", "note", "yaad", "rakhna", "remember"]:
            text = _re.sub(r'\b' + _re.escape(kw) + r'\b', " ", text, flags=_re.IGNORECASE)
        text = " ".join(text.split()).strip()
        return ("memory_save", {"text": text or user_msg})

    # 17. AI CHAT FALLBACK
    return ("chat", {"text": user_msg})


# ================================================================
# SHOW HELPERS
# ================================================================

async def _send_reminder_list(update: Update):
    active = reminders.all_active()
    if active:
        lines = "\n".join(f"  ⏰ #{r['id']} {r['time']} — {r['text']}" for r in active)
        await update.message.reply_text(
            f"⏰ *Active Reminders ({len(active)}):*\n\n{lines}\n\n"
            f"/delremind id — Delete karo\n/snooze5 id — Snooze 5 min\n/remind 30m Chai — Naya set karo",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "⏰ Koi active reminder nahi hai.\n\nInshAllah sab kaam ho gaye! 🌟\n\n"
            "/remind 30m Chai — Naya set karo",
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
            "✅ Alhamdulillah! Koi pending task nahi hai.\n\n/task Naam — Naya task add karo",
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
        await update.message.reply_text(
            f"🏃 *Aaj ke Habits:*\n\n{lines}\n\n/hdone id — Log karo",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🏃 Koi habit nahi hai.\n\n/habit Naam — Naya habit add karo",
            parse_mode="Markdown"
        )

async def _send_diary_today(update: Update):
    entries = diary.get(today_str())
    if not entries:
        await update.message.reply_text(
            "📖 Aaj ki koi diary entry nahi hai.\n\n"
            "/diary write — Likhna shuru karo!\n"
            "Ya bolo: *diary mein likho [text]*",
            parse_mode="Markdown"
        )
    else:
        lines = "\n\n".join(f"🕐 {e['time']}\n{e['text']}" for e in entries)
        await update.message.reply_text(
            f"📖 *Aaj ki Diary ({today_str()}):*\n\n{lines}",
            parse_mode="Markdown"
        )

async def _send_calendar_list(update: Update):
    events = calendar.upcoming(days=30)
    if events:
        lines = []
        for e in events[:10]:
            emoji = "🎂" if e.get("type") == "birthday" else "📅"
            lines.append(f"{emoji} *{e['date']}* — #{e['id']}\n   {e['title']}")
        await update.message.reply_text(
            f"📅 *Upcoming Events ({len(events)}):*\n\n" + "\n\n".join(lines),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "📅 Koi upcoming event nahi.\n\n/caladd — Add karo",
            parse_mode="Markdown"
        )

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
    log.info(f"MSG: '{user_msg[:60]}' → {action_type} | {params}")

    if action_type == "show_reminders":
        await _send_reminder_list(update)

    elif action_type == "show_tasks":
        await _send_task_list(update)

    elif action_type == "show_habits":
        await _send_habit_list(update)

    elif action_type == "show_diary":
        await _send_diary_today(update)

    elif action_type == "show_calendar":
        await _send_calendar_list(update)

    elif action_type == "remind":
        r = reminders.add(update.effective_chat.id, params.get("text", "Reminder"), params.get("time", ""))
        is_tom = params.get("tomorrow", False)
        when_str = "Kal" if is_tom else "Aaj"
        await update.message.reply_text(
            f"⏰ *Reminder Set! InshAllah yaad dilaaunga!*\n\n"
            f"🕐 {when_str} {params.get('time')} baje: {params.get('text')}\n"
            f"📌 ID #{r['id']}",
            parse_mode="Markdown"
        )

    elif action_type == "add_task":
        t = tasks.add(params.get("title", ""))
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
            await update.message.reply_text(
                f"✅ *Alhamdulillah! Task Complete!* 🎉\n\n#{matched['id']} {matched['title']}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❓ Kaunsa task? ID ya naam batao")

    elif action_type == "expense":
        expenses.add(params.get("amount", 0), params.get("desc", ""))
        await update.message.reply_text(
            f"💸 Rs.{params.get('amount')} — {params.get('desc')}\n💰 Aaj total: Rs.{expenses.today_total()}",
            parse_mode="Markdown"
        )

    elif action_type == "diary":
        diary.add(params.get("text", ""))
        await update.message.reply_text(
            f"📖 *Diary Save Ho Gayi! Alhamdulillah!* ✅\n\n_{params.get('text', '')[:100]}_\n\nSheets mein bhi!",
            parse_mode="Markdown"
        )

    elif action_type == "add_habit":
        h = habits.add(params.get("name", ""))
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
            await update.message.reply_text(
                f"🔥 *{name} done! MashAllah!* 🎉\n\n{streak} din ka streak! 💪",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "❓ Kaunsa habit? /habit se list dekho aur /hdone id se log karo"
            )

    elif action_type == "add_calendar":
        title   = params.get("title", "Event")
        ev_date = params.get("date", today_str())
        ev_type = params.get("type", "event")
        e = calendar.add(title, ev_date, "", "", "", ev_type)
        type_emoji = "🎂" if ev_type == "birthday" else "📅"
        if ev_type == "birthday":
            msg = (f"{type_emoji} *Birthday Add Ho Gaya! MashAllah!* 🎉\n\n"
                   f"#{e['id']} 🎂 *{ev_date}*\n👤 {title}\n\n"
                   f"✅ Ek din pehle remind karunga InshAllah!\n📊 Sheets mein save!")
        else:
            msg = (f"{type_emoji} *Event Add Ho Gaya!* ✅\n\n"
                   f"#{e['id']} 📅 *{ev_date}*\n📌 {title}\n\n"
                   f"✅ Ek din pehle remind karunga InshAllah!\n📊 Sheets mein save!")
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif action_type == "add_bill":
        name    = params.get("name", "Bill")
        amount  = params.get("amount", 0)
        due_day = params.get("due_day", 0)
        b = bills.add(name, amount, due_day)
        await update.message.reply_text(
            f"💳 *Bill Add Ho Gaya! Alhamdulillah!* ✅\n\n#{b['id']} *{name}*\n"
            f"💰 Rs.{amount}\n📅 Due: {due_day} tarikh (0 = not set)\n\n"
            f"📊 Sheets mein save!\n💡 Edit: /billadd",
            parse_mode="Markdown"
        )

    elif action_type == "water":
        total = water.add(params.get("ml", 250))
        goal = water.goal()
        await update.message.reply_text(
            f"💧 *+{params.get('ml', 250)}ml Paani!*\n\nTotal: {total}/{goal}ml\n\n"
            f"{'Alhamdulillah! Goal complete! 🎉' if total >= goal else 'InshAllah goal poora hoga! 💪'}",
            parse_mode="Markdown"
        )

    elif action_type == "memory_save":
        text = params.get("text", "")
        try:
            memory.add(text)
            await update.message.reply_text(
                f"🧠 *Memory Mein Save Ho Gaya!* ✅\n\n_{text[:150]}_\n\nInshAllah yaad rakhunga! 💡",
                parse_mode="Markdown"
            )
        except Exception:
            diary.add(f"[Memory] {text}")
            await update.message.reply_text(
                f"🧠 *Note Save Ho Gaya!* ✅\n\n_{text[:150]}_",
                parse_mode="Markdown"
            )

    else:
        prompt = build_system_prompt() + f"\n\nUser: {user_msg}\n\nShort Hinglish reply (2-3 lines), Muslim phrases zaroor use karo:"
        reply = call_gemini(prompt)
        if not reply:
            reply = "☪️ Assalamualaikum! Batao kya help chahiye?\nTasks, reminders, kharcha, diary, calendar, bills?"
        await update.message.reply_text(reply, parse_mode="Markdown")

    chat_hist.add("user", user_msg, update.effective_user.first_name or "User")
    chat_hist.add("assistant", "Reply sent", "Rk")

# ================================================================
# MAIN — FIXED HANDLER REGISTRATION ORDER
# ================================================================

def main():
    log.info("=" * 60)
    log.info("Personal AI Bot — Rk | FIXED v3 | Delete Password Fix")
    log.info(f"IST: {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Sheets: {'Yes' if sheets_backup.connected else 'No'}")
    log.info(f"GitHub: {'Yes' if repo_manager.is_connected else 'No'}")
    log.info("=" * 60)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # ✅ FIX: Delete Manager SABSE PEHLE register karo
    # Yeh ConversationHandler hai — iska state machine pehle active hona chahiye
    # taaki password message capture ho sake, handle_message() mein na jaye
    from delete_manager import register_delete_handlers
    register_delete_handlers(app)

    # Diary ConversationHandler — delete ke baad
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("diary", cmd_diary_entry)],
        states={
            DIARY_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_password_check)],
            DIARY_AWAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_text_input)],
        },
        fallbacks=[CommandHandler("cancel", diary_cancel)],
        per_user=True,
        per_chat=True,
        per_message=False,
    ))

    # Regular commands
    commands = [
        ("start",      cmd_start),
        ("help",       cmd_help),
        ("status",     cmd_status),
        ("checksync",  cmd_checksync),
        ("task",       cmd_task),
        ("done",       cmd_done),
        ("deltask",    cmd_deltask),
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
        ("cal",        cmd_cal),
        ("caltoday",   cmd_caltoday),
        ("calweek",    cmd_calweek),
        ("caladd",     cmd_caladd),
        ("caldel",     cmd_caldel),
        ("bills",      cmd_bills),
        ("billadd",    cmd_billadd),
        ("billpaid",   cmd_billpaid),
        ("billdel",    cmd_billdel),
    ]
    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))

    # Callback query handler (OK button for alarms)
    app.add_handler(CallbackQueryHandler(handle_ok_button, pattern=r"^ok_"))

    # ✅ FIX: General message handler SABSE AAKHIR MEIN
    # Agar pehle register hoga toh ConversationHandler ka password
    # message intercept kar lega
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=10)
        log.info("Reminder job scheduled (every 60s)")

    log.info("Bot ready! Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
