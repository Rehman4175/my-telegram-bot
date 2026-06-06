#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HUMAN TOUCH MODULE — Rk Bot
============================
Sirf 2 features:
  1. Morning Check-in (8 AM) — Ek message + buttons
  2. Smart Nudge — Sirf genuine situations mein

Bot mein integrate karne ke liye:
  from human_touch import register_human_touch

  # main() ke andar, job_queue setup ke paas:
  register_human_touch(app, water, tasks, habits)
"""

import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════
# QUIET MODE — Agar user "Aaj chhuti" kare
# Bot din bhar quiet rahega
# ═══════════════════════════════════════════════════
_quiet_chats: set = set()   # chat_id jahan aaj chhuti hai
_quiet_date: str  = ""      # kis date ko quiet set hua


def _is_quiet(chat_id: int, today: str) -> bool:
    global _quiet_chats, _quiet_date
    if _quiet_date != today:
        _quiet_chats.clear()
        _quiet_date = today
    return chat_id in _quiet_chats


def _set_quiet(chat_id: int, today: str):
    global _quiet_chats, _quiet_date
    if _quiet_date != today:
        _quiet_chats.clear()
        _quiet_date = today
    _quiet_chats.add(chat_id)


# ═══════════════════════════════════════════════════
# HELPER — chat_ids collect karna
# ═══════════════════════════════════════════════════

def _get_chat_ids(reminders_store) -> set:
    """Registered chat IDs nikalo reminder store se"""
    ids = set()
    try:
        for r in reminders_store.get_all():
            cid = r.get("chat_id")
            if cid:
                ids.add(int(cid))
    except Exception as e:
        log.warning(f"[HumanTouch] chat_ids error: {e}")
    return ids


# ═══════════════════════════════════════════════════
# FEATURE 1 — MORNING CHECK-IN (8:00 AM)
# ═══════════════════════════════════════════════════

async def morning_checkin_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Roz subah 8 AM pe ek message — plan poochna + quick action buttons.
    Agar user 'Aaj chhuti' kare toh din bhar bot quiet rahega.
    """
    water_store   = context.bot_data.get("ht_water")
    tasks_store   = context.bot_data.get("ht_tasks")
    habits_store  = context.bot_data.get("ht_habits")
    reminders_store = context.bot_data.get("ht_reminders")

    if not all([water_store, tasks_store, habits_store, reminders_store]):
        log.warning("[HumanTouch] Stores not set, skipping morning check-in")
        return

    # Sirf 8:00 AM pe fire karo
    from secure_data_manager import now_ist
    now = now_ist()
    if now.strftime("%H:%M") != "08:00":
        return

    today = now.strftime("%Y-%m-%d")
    chat_ids = _get_chat_ids(reminders_store)
    if not chat_ids:
        return

    # Pending tasks count
    try:
        pending_count = len(tasks_store.pending())
    except Exception:
        pending_count = 0

    # Pending habits
    try:
        _, habits_pending = habits_store.today_status()
        habits_count = len(habits_pending)
    except Exception:
        habits_count = 0

    # Message build karo
    greeting = f"☀️ *Assalamualaikum! Subah Mubarak!*\n\n"

    if pending_count > 0:
        greeting += f"📋 *{pending_count} tasks* pending hain aaj\n"
    else:
        greeting += f"✅ Koi pending task nahi — Alhamdulillah!\n"

    if habits_count > 0:
        greeting += f"🏃 *{habits_count} habits* karni hain aaj\n"

    greeting += f"\n*Aaj ka plan kya hai?* Batao ya quick action lo:\n"
    greeting += f"_(Agar chhuti hai toh 'Aaj Rest' button dabao — din bhar disturb nahi karunga)_"

    # Buttons
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Tasks Dekho",   callback_data="ht_show_tasks"),
            InlineKeyboardButton("📝 Plan Batao",    callback_data="ht_plan_mode"),
        ],
        [
            InlineKeyboardButton("💧 Paani Log Karo", callback_data="ht_water_log"),
            InlineKeyboardButton("😴 Aaj Rest",       callback_data="ht_quiet_day"),
        ],
    ])

    for chat_id in chat_ids:
        if _is_quiet(chat_id, today):
            continue
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=greeting,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            log.info(f"[HumanTouch] Morning check-in sent to {chat_id}")
        except Exception as e:
            log.error(f"[HumanTouch] Morning check-in failed for {chat_id}: {e}")


# ═══════════════════════════════════════════════════
# FEATURE 2 — SMART NUDGE
# Sirf 3 genuine situations mein fire karta hai
# ═══════════════════════════════════════════════════

async def smart_nudge_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Sirf in 3 situations mein nudge karo:
      A. Paani 0 hai aur sham ho gayi (6 PM check)
      B. Koi task 3+ din se pending hai (check daily)
      C. Habit streak tootne wala hai — aaj 9 PM tak nahi ki (9 PM check)
    """
    water_store     = context.bot_data.get("ht_water")
    tasks_store     = context.bot_data.get("ht_tasks")
    habits_store    = context.bot_data.get("ht_habits")
    reminders_store = context.bot_data.get("ht_reminders")

    if not all([water_store, tasks_store, habits_store, reminders_store]):
        return

    from secure_data_manager import now_ist
    now   = now_ist()
    hm    = now.strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")

    chat_ids = _get_chat_ids(reminders_store)
    if not chat_ids:
        return

    for chat_id in chat_ids:
        if _is_quiet(chat_id, today):
            continue

        # ── A. Paani nudge — 6 PM ──────────────────────
        if hm == "18:00":
            try:
                total_water = water_store.today_total()
                goal        = water_store.goal()
                if total_water == 0:
                    msg = (
                        "💧 *Bhai, paani nahi piya aaj ek ghunt bhi!*\n\n"
                        "Sham ho gayi hai — ab toh pi lo! 😅\n"
                        "Sirf `/water 250` likho — ho jayega! ✅"
                    )
                    await context.bot.send_message(
                        chat_id=chat_id, text=msg, parse_mode="Markdown"
                    )
                    log.info(f"[HumanTouch] Water nudge sent to {chat_id}")
                elif total_water < goal * 0.4:
                    remaining = goal - total_water
                    msg = (
                        f"💧 *Paani thoda kam hai aaj!*\n\n"
                        f"Abhi tak: {total_water}ml / {goal}ml\n"
                        f"Bacha hai: {remaining}ml — chal pi le! 💪\n"
                        f"`/water 250` — quick log!"
                    )
                    await context.bot.send_message(
                        chat_id=chat_id, text=msg, parse_mode="Markdown"
                    )
                    log.info(f"[HumanTouch] Low water nudge sent to {chat_id}")
            except Exception as e:
                log.error(f"[HumanTouch] Water nudge error: {e}")

        # ── B. Old task nudge — 11 AM ──────────────────
        if hm == "11:00":
            try:
                old_tasks = []
                for t in tasks_store.pending():
                    created = t.get("created", t.get("date", ""))
                    if created:
                        try:
                            created_date = datetime.strptime(
                                created[:10], "%Y-%m-%d"
                            ).date()
                            days_old = (now.date() - created_date).days
                            if days_old >= 3:
                                old_tasks.append((t, days_old))
                        except Exception:
                            pass

                if old_tasks:
                    # Sirf sabse purana wala dikhao — spam nahi karna
                    oldest_task, days = max(old_tasks, key=lambda x: x[1])
                    msg = (
                        f"📋 *Ek task bahut time se pada hai:*\n\n"
                        f"*#{oldest_task['id']}* — {oldest_task['title'][:60]}\n"
                        f"⏳ *{days} din* se pending!\n\n"
                        f"Aaj ho jayega InshAllah? 💪\n"
                        f"`/done {oldest_task['id']}` — Complete karo"
                    )
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "✅ Abhi Complete Karo",
                            callback_data=f"ht_done_{oldest_task['id']}"
                        ),
                        InlineKeyboardButton(
                            "⏰ Kal Ke Liye",
                            callback_data=f"ht_postpone_{oldest_task['id']}"
                        ),
                    ]])
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                    log.info(
                        f"[HumanTouch] Old task nudge sent: "
                        f"#{oldest_task['id']} ({days}d old)"
                    )
            except Exception as e:
                log.error(f"[HumanTouch] Old task nudge error: {e}")

        # ── C. Habit streak nudge — 9 PM ───────────────
        if hm == "21:00":
            try:
                _, habits_pending = habits_store.today_status()
                # Sirf woh habits jo streak > 2 hain — unka zyada fark padta hai
                streak_at_risk = [
                    h for h in habits_pending
                    if h.get("streak", 0) >= 3
                ]
                if streak_at_risk:
                    names = "\n".join(
                        f"   🔥 *{h['name']}* — {h['streak']} din ka streak!"
                        for h in streak_at_risk[:3]
                    )
                    msg = (
                        f"⚠️ *Raat ho gayi — ye streaks khatam hone wali hain!*\n\n"
                        f"{names}\n\n"
                        f"10 min bacha hai InshAllah — abhi karlo! 💪\n"
                        f"`/hdone id` — log karo"
                    )
                    await context.bot.send_message(
                        chat_id=chat_id, text=msg, parse_mode="Markdown"
                    )
                    log.info(
                        f"[HumanTouch] Habit streak nudge: "
                        f"{len(streak_at_risk)} at risk"
                    )
            except Exception as e:
                log.error(f"[HumanTouch] Habit nudge error: {e}")


# ═══════════════════════════════════════════════════
# CALLBACK HANDLER — Buttons ke responses
# ═══════════════════════════════════════════════════

async def human_touch_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Morning check-in aur nudge buttons handle karo"""
    query = update.callback_query
    await query.answer()

    data     = query.data
    chat_id  = update.effective_chat.id

    water_store  = ctx.bot_data.get("ht_water")
    tasks_store  = ctx.bot_data.get("ht_tasks")
    habits_store = ctx.bot_data.get("ht_habits")

    from secure_data_manager import now_ist
    now   = now_ist()
    today = now.strftime("%Y-%m-%d")

    # ── Aaj Rest / Quiet Day ────────────────────────
    if data == "ht_quiet_day":
        _set_quiet(chat_id, today)
        await query.edit_message_text(
            "😴 *Theek hai, aaj rest karo!*\n\n"
            "Din bhar disturb nahi karunga InshAllah 🤲\n"
            "Kal subah milte hain! ☀️",
            parse_mode="Markdown"
        )

    # ── Tasks Dekho ─────────────────────────────────
    elif data == "ht_show_tasks":
        try:
            pending = tasks_store.pending() if tasks_store else []
            if pending:
                lines = "\n".join(
                    f"  #{t['id']} {t['title'][:45]}" for t in pending[:10]
                )
                await query.edit_message_text(
                    f"📋 *Pending Tasks ({len(pending)}):*\n\n{lines}\n\n"
                    f"_/done id — complete karo_",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(
                    "✅ *Alhamdulillah! Koi pending task nahi!* 🎉\n\n"
                    "_Naya task add karna ho toh batao!_",
                    parse_mode="Markdown"
                )
        except Exception as e:
            log.error(f"[HumanTouch] show_tasks callback: {e}")
            await query.edit_message_text("❌ Tasks load nahi hue!")

    # ── Plan Mode — user ko batane do ───────────────
    elif data == "ht_plan_mode":
        await query.edit_message_text(
            "📝 *Batao aaj kya karna hai!*\n\n"
            "Sirf likho — main task mein add kar dunga:\n\n"
            "_Example: 'Doctor se milna hai, grocery lani hai'_\n\n"
            "Ya `/task Naam` se direct add karo! ✅",
            parse_mode="Markdown"
        )

    # ── Paani Log (quick 250ml) ──────────────────────
    elif data == "ht_water_log":
        try:
            if water_store:
                total = water_store.add(250)
                goal  = water_store.goal()
                pct   = int(total / goal * 100) if goal else 0
                filled = min(pct // 20, 5)
                bar   = "🟦" * filled + "⬜" * (5 - filled)
                await query.edit_message_text(
                    f"💧 *+250ml logged!* ✅\n\n"
                    f"Total: {total}/{goal}ml\n"
                    f"{bar} {pct}%\n\n"
                    f"{'🎉 Goal complete! Alhamdulillah!' if total >= goal else 'Badhiya! Thoda aur piyo 💪'}",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("❌ Water store unavailable!")
        except Exception as e:
            log.error(f"[HumanTouch] water_log callback: {e}")
            await query.edit_message_text("❌ Water log nahi hua!")

    # ── Old Task — Abhi Complete Karo ───────────────
    elif data.startswith("ht_done_"):
        try:
            tid = int(data.split("_")[2])
            t   = tasks_store.complete(tid) if tasks_store else None
            if t:
                await query.edit_message_text(
                    f"✅ *Alhamdulillah! Task Complete!* 🎉\n\n"
                    f"#{t['id']} ~~{t['title']}~~\n\n"
                    f"MashAllah! 💪",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("❌ Task nahi mila!")
        except Exception as e:
            log.error(f"[HumanTouch] done callback: {e}")
            await query.edit_message_text("❌ Kuch galat hua!")

    # ── Old Task — Kal Ke Liye ──────────────────────
    elif data.startswith("ht_postpone_"):
        try:
            tid    = int(data.split("_")[2])
            target = next(
                (t for t in tasks_store.all_tasks() if t["id"] == tid),
                None
            ) if tasks_store else None
            if target:
                from secure_data_manager import reminders as rem_store
                kal = (now + timedelta(days=1)).strftime("%Y-%m-%d 09:00:00")
                rem_store.add(chat_id, f"Task: {target['title']}", kal)
                await query.edit_message_text(
                    f"⏰ *Kal 9 AM ke liye set ho gaya!*\n\n"
                    f"#{tid} {target['title'][:50]}\n\n"
                    f"_InshAllah kal ho jayega! 🤲_",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("❌ Task nahi mila!")
        except Exception as e:
            log.error(f"[HumanTouch] postpone callback: {e}")
            await query.edit_message_text("❌ Kuch galat hua!")


# ═══════════════════════════════════════════════════
# REGISTER — Bot mein integrate karne ka function
# ═══════════════════════════════════════════════════

def register_human_touch(app, water_store, tasks_store, habits_store, reminders_store):
    """
    Bot mein human touch register karo.

    bot.py ke main() mein add karo:

        from human_touch import register_human_touch
        register_human_touch(app, water, tasks, habits, reminders)

    Bas itna! Kuch aur nahi karna.
    """
    # Stores bot_data mein save karo taaki jobs access kar sakein
    app.bot_data["ht_water"]     = water_store
    app.bot_data["ht_tasks"]     = tasks_store
    app.bot_data["ht_habits"]    = habits_store
    app.bot_data["ht_reminders"] = reminders_store

    # Callback handler register karo
    app.add_handler(
        CallbackQueryHandler(
            human_touch_callback,
            pattern=r"^ht_"
        )
    )

    # Jobs schedule karo (job_queue zaroor hona chahiye)
    jq = app.job_queue
    if jq:
        # Morning check-in — har 60 sec check, 8:00 AM pe fire hoga
        jq.run_repeating(morning_checkin_job, interval=60, first=15)

        # Smart nudge — har 60 sec check, specific times pe fire hoga
        jq.run_repeating(smart_nudge_job, interval=60, first=20)

        log.info("✅ [HumanTouch] Morning check-in + Smart nudge registered!")
    else:
        log.warning("⚠️ [HumanTouch] JobQueue not available — jobs not scheduled!")
