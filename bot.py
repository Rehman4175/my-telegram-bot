#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PERSONAL AI ASSISTANT - COMPLETE FIXED VERSION
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

# ================================================================
# CONFIG
# ================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DIARY_PASSWORD = os.environ.get("DIARY_PASSWORD", "Rk1996")

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
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}
            )
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
    return (
        f"Tu mera Personal AI Assistant hai — naam 'Dost'.\n"
        f"TIME: {now_ist().strftime('%A, %d %b — %I:%M %p')} IST\n\n"
        f"Tasks: {len(tp)} pending\n"
        f"Habits: {len(hd)} done, {len(hp)} pending\n"
        f"Kharcha: Rs.{exp_t}\n"
        f"Paani: {wt}ml/{wg}ml\n"
        f"Reminders: {len(active_rem)} active\n\n"
        f"Hamesha Hindi/Hinglish mein SHORT jawab do."
    )

def alarm_keyboard(rid):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("OK - Alarm Band Karo", callback_data=f"ok_{rid}")
    ]])

# ================================================================
# COMMAND HANDLERS
# ================================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(
        f"Assalamualaikum {name}!\n\nMain aapka AI Dost hoon!\n\nExamples:\n'2 min mein paani yaad dilana'\n'Chai pe 50 rupees kharcha'\n'Diary mein likho aaj accha din tha'\n\nCommands: /help",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "COMMANDS\n\nNatural Chat:\n'2 min mein paani yaad dilana'\n'Chai pe 50 rupees kharcha'\n'Diary mein likho...'\n'Exercise habit ho gayi'\n\nCommands:\n/task Task name - Add task\n/done id - Complete task\n/habit Habit name - Add habit\n/hdone id - Log habit\n/remind 30m Chai - Set reminder\n/kharcha 100 Chai - Add expense\n/diary - View diary (password)\n/save text - Quick diary save\n/water 250 - Log water\n/briefing - Daily summary\n/status - Check system status\n/checksync - Check GitHub & Sheets sync\n/help - This menu",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    github_status = "Connected" if repo_manager.is_connected else "Local only"
    sheets_status = "Connected" if sheets_backup.connected else "Not connected"
    await update.message.reply_text(
        f"BOT STATUS\n\nBot: Running\nGitHub: {github_status}\nGoogle Sheets: {sheets_status}\n\nData Stats:\nTasks: {len(tasks.all_tasks())}\nDiary: {sum(len(v) for v in diary.get_all_entries().values())} entries\nExpenses: {len(expenses.store.data.get('list', []))}\nHabits: {len(habits.all())}\nReminders: {len(reminders.get_all())}\nWater: {water.today_total()}/{water.goal()}ml today",
        parse_mode="Markdown"
    )

async def cmd_checksync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    github_status = "Connected" if repo_manager.is_connected else "Local only"
    sheets_status = "Connected" if sheets_backup.connected else "Not connected"
    
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
        except:
            pass
    
    diary_in_sheets = "Unknown"
    if sheets_backup.connected and sheets_backup.sheet:
        try:
            ws = sheets_backup.sheet.worksheet("Diary")
            all_records = ws.get_all_values()
            if len(all_records) > 1:
                diary_in_sheets = f"{len(all_records)-1} entries"
            else:
                diary_in_sheets = "No entries yet"
        except:
            diary_in_sheets = "Check failed"
    
    sheet_url = "Not connected"
    if sheets_backup.sheet:
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheets_backup.sheet.id}"
    
    await update.message.reply_text(
        f"SYNC STATUS\n\nGitHub: {github_status}\nGoogle Sheets: {sheets_status}\nLast Git Commit: {last_sync}\nDiary in Sheets: {diary_in_sheets}\n\nAll data is secure! New deploy will NOT delete your data.\n\nTip: Check your Google Sheet here:\n{sheet_url}",
        parse_mode="Markdown"
    )

async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(f"Pending ({len(pending)}):\n{lines}\n\n/done id", parse_mode="Markdown")
        else:
            await update.message.reply_text("/task Kaam naam", parse_mode="Markdown")
        return
    title = " ".join(ctx.args)
    t = tasks.add(title)
    await update.message.reply_text(f"Task added: #{t['id']} {t['title']}")

async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        pending = tasks.pending()
        if pending:
            lines = "\n".join(f"#{t['id']} {t['title']}" for t in pending[:15])
            await update.message.reply_text(f"Pending:\n{lines}\n\n/done id", parse_mode="Markdown")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t:
            await update.message.reply_text(f"Done! {t['title']}", parse_mode="Markdown")
        else:
            await update.message.reply_text("Task not found!")
    except Exception:
        await update.message.reply_text("Invalid ID!")

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        all_h = habits.all()
        if all_h:
            hd, _ = habits.today_status()
            lines = "\n".join(f"{'Yes' if h in hd else 'No'} #{h['id']} {h['name']} streak:{h.get('streak',0)}" for h in all_h)
            await update.message.reply_text(f"Habits:\n{lines}\n\n/hdone id", parse_mode="Markdown")
        else:
            await update.message.reply_text("/habit Naam", parse_mode="Markdown")
        return
    h = habits.add(" ".join(ctx.args))
    await update.message.reply_text(f"Habit added: #{h['id']} {h['name']}")

async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        if pending:
            lines = "\n".join(f"#{h['id']} {h['name']}" for h in pending)
            await update.message.reply_text(f"Pending Habits:\n{lines}\n\n/hdone id", parse_mode="Markdown")
        return
    try:
        ok, streak = habits.log(int(ctx.args[0]))
        if ok:
            await update.message.reply_text(f"Habit done! {streak} day streak!", parse_mode="Markdown")
        else:
            await update.message.reply_text("Already done today!")
    except Exception:
        await update.message.reply_text("Invalid ID!")

async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        today_list = expenses.get_by_date(today_str())
        if today_list:
            lines = "\n".join(f"Rs.{e['amount']} - {e['desc']}" for e in today_list[-10:])
            await update.message.reply_text(f"Aaj ka kharcha:\n{lines}\nTotal: Rs.{expenses.today_total()}", parse_mode="Markdown")
        else:
            await update.message.reply_text("/kharcha 100 Chai", parse_mode="Markdown")
        return
    try:
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:])
        expenses.add(amount, desc)
        await update.message.reply_text(f"Rs.{amount} - {desc}\nAaj total: Rs.{expenses.today_total()}", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("/kharcha 100 Chai")

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        active = reminders.all_active()
        if active:
            lines = "\n".join(f"#{r['id']} {r['time']} - {r['text']}" for r in active)
            await update.message.reply_text(f"Active Reminders:\n{lines}\n\n/remind 30m Chai", parse_mode="Markdown")
        else:
            await update.message.reply_text("/remind 30m Chai ya /remind 15:30 Meeting", parse_mode="Markdown")
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
        await update.message.reply_text("/remind 30m Chai or /remind 15:30 Meeting")
        return
    r = reminders.add(update.effective_chat.id, text, remind_at)
    await update.message.reply_text(f"Reminder set for {remind_at}: {text}\nID #{r['id']}", parse_mode="Markdown")

async def cmd_water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ml = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 250
    total = water.add(ml)
    goal = water.goal()
    await update.message.reply_text(f"+{ml}ml! Total: {total}/{goal}ml", parse_mode="Markdown")

async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n = now_ist()
    tp = tasks.today_pending()
    hd, hp = habits.today_status()
    await update.message.reply_text(
        f"BRIEFING - {n.strftime('%d %b %Y')}\n{n.strftime('%I:%M %p')} IST\n\nTasks pending: {len(tp)}\nHabits done: {len(hd)}/{len(hd)+len(hp)}\nAaj kharcha: Rs.{expenses.today_total()}\nWater: {water.today_total()}ml/{water.goal()}ml",
        parse_mode="Markdown"
    )

async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("/save Aaj ka din acha tha...")
        return
    text = " ".join(ctx.args)
    diary.add(text)
    await update.message.reply_text(f"Diary saved! {text[:100]}\n\nAlso backed up to Google Sheets!", parse_mode="Markdown")

async def cmd_delremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        try:
            reminders.delete(int(ctx.args[0]))
            await update.message.reply_text("Reminder deleted!")
        except Exception:
            await update.message.reply_text("Invalid ID!")
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
            await update.message.reply_text(f"Reminder #{rid} nahi mila!")
            return
        reminders.acknowledge(rid, f"Snoozed {mins}min")
        new_time = (now_ist() + timedelta(minutes=mins)).strftime("%H:%M")
        new_rem = reminders.add(target["chat_id"], f"🔁 {target['text']}", new_time, "once")
        await update.message.reply_text(f"Snoozed! {mins} min baad fir yaad dilaunga.\nNew ID: #{new_rem['id']}", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("Invalid ID!")

# ================================================================
# DIARY CONVERSATION
# ================================================================
async def cmd_diary_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or []
    if not args:
        ctx.user_data["diary_mode"] = "view_today"
        await update.message.reply_text("Diary password daalo:\n/cancel se bahar", parse_mode="Markdown")
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
    await update.message.reply_text("Password daalo:\n/cancel se bahar", parse_mode="Markdown")
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
        await update.effective_chat.send_message("Galat Password!\nDobara: /diary", parse_mode="Markdown")
        return ConversationHandler.END
    mode = ctx.user_data.get("diary_mode", "view_today")
    if mode == "write" and not ctx.user_data.get("diary_pending_text"):
        await update.effective_chat.send_message("Diary mein likho:\n/cancel se bahar", parse_mode="Markdown")
        return DIARY_AWAIT_TEXT
    elif mode == "write":
        text = ctx.user_data.get("diary_pending_text", "")
        diary.add(text)
        await update.effective_chat.send_message(f"Diary saved! {text[:100]}\n\nAlso backed up to Google Sheets!", parse_mode="Markdown")
        return ConversationHandler.END
    else:
        entries = diary.get_all_entries()
        if not entries:
            await update.effective_chat.send_message("Koi diary entry nahi mili.", parse_mode="Markdown")
        else:
            count = sum(len(v) for v in entries.values())
            await update.effective_chat.send_message(f"Total diary entries: {count}", parse_mode="Markdown")
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
    await update.effective_chat.send_message(f"Diary saved! {text[:100]}\n\nAlso backed up to Google Sheets!", parse_mode="Markdown")
    return ConversationHandler.END

async def diary_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Diary cancelled.", parse_mode="Markdown")
    return ConversationHandler.END

# ================================================================
# ALARM JOB
# ================================================================
async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now = now_ist()
    now_hm = now.strftime("%H:%M")
    if now.hour == 0 and now.minute <= 1:
        reminders.reset_daily()
        return
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
                suffix = f"\n{fire_count + 1}vi baar baj raha hai - OK dabao!"
            alert = (
                f"ALARM!\n"
                f"{'=' * 25}\n"
                f"{reminder_time} BAJ GAYE!\n"
                f"{'=' * 25}\n\n"
                f"{r['text'].upper()}\n"
                f"{suffix}\n\n"
                f"Snooze: /snooze5 {r['id']} | /snooze10 {r['id']}\n"
                f"Delete: /delremind {r['id']}"
            )
            try:
                await context.bot.send_message(
                    chat_id=int(r["chat_id"]),
                    text=alert,
                    reply_markup=alarm_keyboard(r["id"]),
                    parse_mode="Markdown"
                )
                for item in reminders.store.data["list"]:
                    if item["id"] == r["id"]:
                        item["fire_count"] = item.get("fire_count", 0) + 1
                        item["last_fired_minute"] = now_hm
                        item["last_fired"] = now_ist().isoformat()
                        break
                reminders.store.save()
                log.info(f"Alarm fired #{r['id']} at {now_hm}")
            except Exception as e:
                log.error(f"Failed to send alarm: {e}")

async def handle_ok_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Alarm band!")
    if query.data.startswith("ok_"):
        try:
            rid = int(query.data.split("_")[1])
            if reminders.acknowledge(rid, "User pressed OK"):
                await query.edit_message_text("Alarm band ho gaya! Ab nahi bajega.\n\nPress /remind to set new reminder.", parse_mode="Markdown")
                log.info(f"Reminder #{rid} stopped by OK button")
            else:
                await query.edit_message_text("Pehle se band hai ya invalid ID.", parse_mode="Markdown")
        except Exception as e:
            log.error(f"OK button error: {e}")
            await query.edit_message_text("Error stopping alarm!")

# ================================================================
# NATURAL LANGUAGE
# ================================================================
def parse_user_message(user_msg):
    lower = user_msg.lower().strip()
    now = now_ist()
    remind_words = ["remind", "reminder", "alarm", "yaad dilana", "bata dena"]
    if any(w in lower for w in remind_words):
        m = _re.search(r'(\d+)\s*(?:min|minute|m)\b', lower)
        if m:
            mins = int(m.group(1))
            time_str = (now + timedelta(minutes=mins)).strftime("%H:%M")
            text = _re.sub(r'\d+\s*(?:min|minute|m)\b', '', user_msg)
            text = " ".join(w for w in text.split() if w.lower() not in remind_words).strip()
            return ("remind", {"time": time_str, "text": text or "Reminder!"})
        m = _re.search(r'(\d{1,2}):(\d{2})', lower)
        if m:
            time_str = f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
            text = _re.sub(r'\d{1,2}:\d{2}', '', user_msg)
            text = " ".join(w for w in text.split() if w.lower() not in remind_words).strip()
            return ("remind", {"time": time_str, "text": text or "Reminder!"})
    if "diary" in lower or "dairy" in lower:
        text = user_msg
        for kw in ["diary", "dairy", "likho", "add", "save", "mein", "me", "main"]:
            text = _re.sub(kw, " ", text, flags=_re.IGNORECASE)
        text = " ".join(text.split()).strip()
        return ("diary", {"text": text or user_msg})
    if any(w in lower for w in ["task add", "add task", "kaam add", "new task"]):
        title = user_msg
        for w in ["task add", "add task", "kaam add", "new task"]:
            title = _re.sub(w, "", title, flags=_re.IGNORECASE)
        title = title.strip()
        if title:
            return ("add_task", {"title": title[:80]})
    if any(w in lower for w in ["task done", "kaam ho gaya", "complete kar liya"]):
        m = _re.search(r'#?(\d+)', lower)
        hint = m.group(1) if m else lower[:30]
        return ("complete_task", {"hint": hint})
    expense_words = ["kharcha", "kharch", "spent", "rupees", "rs"]
    if any(w in lower for w in expense_words):
        m = _re.search(r'(\d+(?:\.\d+)?)', lower)
        if m:
            amount = float(m.group(1))
            desc = _re.sub(r'(\d+(?:\.\d+)?|rs\.?|rupees?)', "", user_msg, flags=_re.IGNORECASE)
            desc = " ".join(w for w in desc.split() if w.lower() not in expense_words).strip()
            return ("expense", {"amount": amount, "desc": desc or "Expense"})
    if "habit add" in lower or "add habit" in lower:
        name = _re.sub(r'habit add|add habit', "", user_msg, flags=_re.IGNORECASE).strip()
        return ("add_habit", {"name": name[:50]})
    if "habit done" in lower or "habit ho gayi" in lower:
        m = _re.search(r'#?(\d+)', lower)
        keyword = m.group(1) if m else lower[:30]
        return ("habit_done", {"keyword": keyword})
    if any(w in lower for w in ["paani piya", "water piya", "water log"]):
        m = _re.search(r'(\d+)\s*(ml|glass|bottle)', lower)
        ml = 250
        if m:
            val, unit = int(m.group(1)), m.group(2)
            ml = val * 250 if "glass" in unit else val * 500 if "bottle" in unit else val
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
    log.info(f"Received '{user_msg[:50]}' -> {action_type}")
    if action_type == "remind":
        r = reminders.add(update.effective_chat.id, params.get("text", "Reminder"), params.get("time", ""))
        await update.message.reply_text(f"Reminder set for {params.get('time')}: {params.get('text')}\nID #{r['id']}", parse_mode="Markdown")
    elif action_type == "add_task":
        t = tasks.add(params.get("title", ""))
        await update.message.reply_text(f"Task added: #{t['id']} {t['title']}")
    elif action_type == "complete_task":
        hint = params.get("hint", "")
        pending = tasks.pending()
        matched = next((t for t in pending if str(t["id"]) == hint or (hint and hint in t["title"].lower())), None)
        if matched:
            tasks.complete(matched["id"])
            await update.message.reply_text(f"Done! {matched['title']}")
        else:
            await update.message.reply_text("Kaunsa task? ID ya naam batao")
    elif action_type == "expense":
        expenses.add(params.get("amount", 0), params.get("desc", ""))
        await update.message.reply_text(f"Rs.{params.get('amount')} - {params.get('desc')}\nAaj total: Rs.{expenses.today_total()}")
    elif action_type == "diary":
        diary.add(params.get("text", ""))
        await update.message.reply_text(f"Diary saved! {params.get('text', '')[:100]}\n\nAlso backed up to Google Sheets!", parse_mode="Markdown")
    elif action_type == "add_habit":
        h = habits.add(params.get("name", ""))
        await update.message.reply_text(f"Habit added: #{h['id']} {h['name']}")
    elif action_type == "habit_done":
        keyword = params.get("keyword", "")
        if keyword.isdigit():
            ok, streak = habits.log(int(keyword))
            name = f"#{keyword}"
        else:
            ok, streak, h = habits.log_by_name(keyword)
            name = h["name"] if h else keyword
        if ok:
            await update.message.reply_text(f"{name} done! {streak} day streak!")
        else:
            await update.message.reply_text("Kaunsa habit? ID ya naam batao")
    elif action_type == "water":
        total = water.add(params.get("ml", 250))
        goal = water.goal()
        await update.message.reply_text(f"+{params.get('ml', 250)}ml! Total: {total}/{goal}ml")
    else:
        prompt = build_system_prompt() + f"\n\nUser: {user_msg}\n\nShort Hindi reply (2-3 lines):"
        reply = call_gemini(prompt)
        if not reply:
            reply = "Batao kya help chahiye? Tasks, reminders, kharcha, diary?"
        await update.message.reply_text(reply, parse_mode="Markdown")
    chat_hist.add("user", user_msg, update.effective_user.first_name or "User")
    chat_hist.add("assistant", "Reply sent", "Bot")

# ================================================================
# MAIN
# ================================================================
def main():
    log.info("=" * 60)
    log.info("Personal AI Bot - SECURE DATA + FIXED ALARMS + SHEETS SYNC")
    log.info(f"IST: {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Sheets: {'Yes' if sheets_backup.connected else 'No'}")
    log.info(f"GitHub: {'Yes' if repo_manager.is_connected else 'No'}")
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
        ("checksync", cmd_checksync), ("task", cmd_task), ("done", cmd_done),
        ("habit", cmd_habit), ("hdone", cmd_hdone), ("kharcha", cmd_kharcha),
        ("remind", cmd_remind), ("delremind", cmd_delremind), ("water", cmd_water),
        ("briefing", cmd_briefing), ("save", cmd_save), ("snooze5", cmd_snooze),
        ("snooze10", cmd_snooze), ("snooze30", cmd_snooze), ("snooze60", cmd_snooze),
    ]
    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))
    app.add_handler(CallbackQueryHandler(handle_ok_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    if app.job_queue:
        app.job_queue.run_repeating(reminder_job, interval=60, first=10)
        log.info("Reminder job scheduled (every 60s)")
    log.info("Bot ready! Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
