#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DELETE MANAGER — Rk Bot
========================
FIXED v2:
  - per_user=True, per_chat=True explicitly set — ConversationHandler state properly maintained
  - Password ab sahi capture hoga
  - bot.py mein sabse pehle register karo (register_delete_handlers call)

Natural Hinglish se kaam karta hai, e.g.:
  "chat history delete karo"
  "saari chat saaf karo"
  "sheet se entry hatao"
  "sab kuch delete karo"
  "logs clear karo"
  "tasks sheet wipe karo"

Commands bhi kaam karti hain:
  /nuke          → Sirf chat history (Miscellaneous) delete
  /delsheet      → Kisi ek sheet ki ek row delete (ID se)
  /nukesheet     → Ek poori sheet wipe (header bachta hai)
  /nukeall       → SAARI sheets + saara local data (nuclear option)
  /delete        → Full menu open

Har operation se pehle DELETE_PASSWORD maanga jata hai.
Repository Secrets mein "DELETE_PASSWORD" set karo. ✅
"""

import os
import re as _re
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

from secure_data_manager import (
    memory, tasks, diary, habits, expenses, goals, reminders,
    water, bills, calendar, chat_hist,
    sheets_backup, now_ist, today_str, now_str,
    repo_manager, DATA_DIR
)

log = logging.getLogger(__name__)

# ================================================================
# CONFIG
# ================================================================
DELETE_PASSWORD = os.environ.get("DELETE_PASSWORD", "")

# Conversation states — high numbers taaki bot.py se clash na ho
DEL_AWAIT_PASS         = 50
DEL_AWAIT_CHOICE       = 51
DEL_AWAIT_SHEET        = 52
DEL_AWAIT_NUKE_CONFIRM = 53

# Sheet display names
SHEET_KEY_MAP = {
    "reminders": "Reminders",
    "tasks":     "Tasks",
    "memory":    "Memory / Important Notes",
    "goals":     "Goals",
    "calendar":  "Calendar Events",
    "bills":     "Bills & Subscriptions",
    "expenses":  "Expenses",
    "habits":    "Habits",
    "water":     "Water Intake",
    "logs":      "Miscellaneous",
    "diary":     "Diary",
}

INTERNAL_KEY_MAP = {
    "reminders": "Reminders",
    "tasks":     "Tasks",
    "memory":    "Memory",
    "goals":     "Goals",
    "calendar":  "Calendar",
    "bills":     "Bills",
    "expenses":  "Expenses",
    "habits":    "Habits",
    "water":     "Water",
    "logs":      "Logs",
    "diary":     "Diary",
}


# ================================================================
# NATURAL LANGUAGE INTENT DETECTOR
# ================================================================

_NUKEALL_PHRASES = [
    "sab kuch delete", "saara data delete", "sab data hatao",
    "poora data wipe", "nuke all", "nukeall", "sab saaf karo",
    "saari sheets delete", "everything delete", "total wipe",
    "factory reset", "sab kuch hatao", "saara kuch delete",
    "poora kuch delete", "sab kuch saaf", "nuclear option",
    "nuke karo sab", "poora wipe", "saari data saaf",
    "sab data delete", "saari cheezein delete",
]

_NUKE_LOGS_PHRASES = [
    "chat history delete", "chat delete karo", "chat saaf karo",
    "logs delete karo", "logs saaf karo", "purani chat hatao",
    "miscellaneous delete", "miscellaneous saaf", "chat history saaf",
    "chat history hatao", "purani baatein delete", "history saaf karo",
    "chat wipe", "logs wipe", "history delete", "chat clear karo",
    "chat clear", "logs clear", "history clear", "chat history clear",
    "purani history", "history hatao", "chat hatao",
]

_NUKESHEET_PHRASES = [
    "sheet wipe karo", "poori sheet delete", "sheet saaf karo",
    "ek sheet clear", "sheet clear", "sheet khali karo",
    "poori sheet saaf", "sheet wipe", "tab wipe karo",
    "tab saaf karo", "sheet ka data delete", "ek tab delete",
    "puri sheet", "sheet poori saaf", "sheet ka saara data",
]

_DELROW_PHRASES = [
    "sheet se entry hatao", "sheet se delete karo", "row delete karo",
    "entry delete karo", "record hatao", "entry hatao",
    "sheet mein se hatao", "sheet se row hatao", "specific entry delete",
    "ek entry delete", "ek row delete", "sheet row delete",
    "row hatao", "entry hata do", "sheet se ek",
    "specific row", "koi entry delete", "ek record hatao",
]

_MENU_PHRASES = [
    "delete menu", "delete manager", "kya delete kar sakta",
    "delete options", "delete help", "delete kya kya",
    "delete manager open", "delete manager kholna",
]


def parse_delete_intent(text: str):
    """
    Natural language se delete intent detect karo.
    Returns: "nuke_logs" | "delrow" | "nukesheet" | "nukeall" | "menu" | None
    """
    lower = text.lower().strip()

    if any(p in lower for p in _NUKEALL_PHRASES):
        return "nukeall"
    if any(p in lower for p in _NUKE_LOGS_PHRASES):
        return "nuke_logs"
    if any(p in lower for p in _NUKESHEET_PHRASES):
        return "nukesheet"
    if any(p in lower for p in _DELROW_PHRASES):
        return "delrow"
    if any(p in lower for p in _MENU_PHRASES):
        return "menu"

    return None


# ================================================================
# HELPER FUNCTIONS
# ================================================================

def _wipe_sheet_tab(internal_key: str):
    """Ek sheet ke saare data rows delete karo, header row 1 rakho."""
    if not sheets_backup.connected:
        return False, "⚠️ Google Sheets connected nahi hai!"

    ws = sheets_backup._ws(internal_key)
    if not ws:
        tab_name = SHEET_KEY_MAP.get(internal_key, internal_key)
        return False, f"⚠️ Tab '{tab_name}' nahi mili!"

    try:
        all_values = ws.get_all_values()
        total_rows = len(all_values)
        if total_rows <= 1:
            tab_name = SHEET_KEY_MAP.get(internal_key, internal_key)
            return True, f"ℹ️ '{tab_name}' pehle se khali hai."

        for row_idx in range(total_rows, 1, -1):
            ws.delete_rows(row_idx)

        tab_name = SHEET_KEY_MAP.get(internal_key, internal_key)
        return True, f"✅ '{tab_name}' — {total_rows - 1} rows delete. Header safe."
    except Exception as e:
        log.error(f"_wipe_sheet_tab [{internal_key}]: {e}")
        return False, f"❌ Error: {e}"


def _wipe_local_store(store_name: str) -> str:
    """Local JSON store reset karo."""
    defaults = {
        "reminders": (reminders.store, {"list": [], "counter": 0}),
        "tasks":     (tasks.store,     {"list": [], "counter": 0}),
        "memory":    (memory.store,    {"facts": []}),
        "goals":     (goals.store,     {"list": [], "counter": 0}),
        "calendar":  (calendar.store,  {"events": [], "counter": 0}),
        "bills":     (bills.store,     {"list": [], "counter": 0}),
        "expenses":  (expenses.store,  {"list": [], "budget": 0}),
        "habits":    (habits.store,    {"list": [], "logs": {}, "counter": 0}),
        "water":     (water.store,     {"logs": {}, "goal_ml": 2000}),
        "logs":      (chat_hist.store, {"history": []}),
        "diary":     (diary.store,     {"entries": {}}),
    }
    if store_name not in defaults:
        return f"⚠️ Unknown store: {store_name}"
    try:
        store_obj, default_data = defaults[store_name]
        store_obj.data = default_data
        store_obj.save()
        return f"✅ Local '{store_name}' cleared."
    except Exception as e:
        return f"⚠️ Local '{store_name}' error: {e}"


# ================================================================
# KEYBOARDS
# ================================================================

def _delete_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Chat History (Logs) Delete",    callback_data="dm_nuke_logs")],
        [InlineKeyboardButton("📋 Ek Sheet Entry Delete (by ID)", callback_data="dm_delrow")],
        [InlineKeyboardButton("🧹 Ek Poori Sheet Wipe",           callback_data="dm_nukesheet")],
        [InlineKeyboardButton("☢️ SABB KUCH DELETE (NukeAll)",    callback_data="dm_nukeall")],
        [InlineKeyboardButton("❌ Cancel",                         callback_data="dm_cancel")],
    ])

def _sheet_select_keyboard(action_prefix: str):
    keys    = list(SHEET_KEY_MAP.keys())
    buttons = []
    row     = []
    for k in keys:
        row.append(InlineKeyboardButton(SHEET_KEY_MAP[k], callback_data=f"{action_prefix}_{k}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="dm_cancel")])
    return InlineKeyboardMarkup(buttons)

def _confirm_keyboard(action: str):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Haan, Delete Karo", callback_data=f"dm_confirm_{action}"),
        InlineKeyboardButton("❌ Nahi, Ruko",        callback_data="dm_cancel"),
    ]])


# ================================================================
# COMMON: Password maango
# ================================================================

async def _ask_password(chat, ctx, intent: str, label: str = "Delete Operation"):
    ctx.user_data["dm_entry_cmd"] = intent
    await chat.send_message(
        f"🔐 *{label}*\n\n"
        f"⚠️ Sensitive operation — password chahiye!\n\n"
        f"*Delete Password* daalo:\n\n"
        f"_(Galat password = cancel)_\n/cancel — Bahar niklo",
        parse_mode="Markdown"
    )


# ================================================================
# ENTRY POINTS
# ================================================================

async def cmd_delete_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Commands: /nuke /delsheet /nukesheet /nukeall /delete"""
    cmd = update.message.text.split()[0].lstrip("/").lower()
    intent_map = {
        "nuke":      "nuke_logs",
        "delsheet":  "delrow",
        "nukesheet": "nukesheet",
        "nukeall":   "nukeall",
        "delete":    "menu",
    }
    intent = intent_map.get(cmd, "menu")
    await _ask_password(update.effective_chat, ctx, intent)
    return DEL_AWAIT_PASS


async def cmd_nl_delete_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Natural language entry — ConversationHandler regex se trigger hoga."""
    intent = ctx.user_data.get("dm_entry_cmd", "menu")
    await _ask_password(update.effective_chat, ctx, intent)
    return DEL_AWAIT_PASS


# ================================================================
# STATE 50: Password check
# ================================================================

async def del_password_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END

    entered = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    # Env check
    if not DELETE_PASSWORD:
        await update.effective_chat.send_message(
            "❌ *DELETE_PASSWORD set nahi hai!*\n\n"
            "Repository Secrets mein `DELETE_PASSWORD` add karo.",
            parse_mode="Markdown"
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    # Password check
    if entered != DELETE_PASSWORD:
        await update.effective_chat.send_message(
            "❌ *Galat Password! Access denied.*\n\nDobara try: /delete",
            parse_mode="Markdown"
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    # ✅ Sahi password
    intent = ctx.user_data.get("dm_entry_cmd", "menu")

    if intent == "nuke_logs":
        await update.effective_chat.send_message(
            "✅ *Password Sahi! MashAllah!*\n\n"
            "⚠️ *CHAT HISTORY NUKE*\n\n"
            "Miscellaneous sheet + local logs saab delete ho jayenge.\n\nPakka?",
            parse_mode="Markdown",
            reply_markup=_confirm_keyboard("nuke_logs")
        )
        return DEL_AWAIT_CHOICE

    elif intent == "delrow":
        await update.effective_chat.send_message(
            "✅ *Password Sahi!*\n\n"
            "📋 Kaunsi sheet se ek entry (row) delete karni hai?",
            parse_mode="Markdown",
            reply_markup=_sheet_select_keyboard("dm_row")
        )
        return DEL_AWAIT_CHOICE

    elif intent == "nukesheet":
        await update.effective_chat.send_message(
            "✅ *Password Sahi!*\n\n"
            "🧹 Kaunsi sheet poori wipe karni hai?\n"
            "_(Header bachega, baaki sab delete hoga)_",
            parse_mode="Markdown",
            reply_markup=_sheet_select_keyboard("dm_wipe")
        )
        return DEL_AWAIT_CHOICE

    elif intent == "nukeall":
        await update.effective_chat.send_message(
            "✅ *Password Sahi!*\n\n"
            "☢️ *NUCLEAR OPTION — SAAB KUCH DELETE*\n\n"
            "*SAARI SHEETS* aur *SAARA LOCAL DATA* permanent delete hoga!\n\n"
            "⛔ Yeh undo NAHI hoga!\n\n"
            "Confirm karne ke liye *CONFIRM* (bilkul capital mein) type karo:",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_NUKE_CONFIRM

    else:  # menu
        await update.effective_chat.send_message(
            "✅ *Password Sahi! Delete Manager Ready.*\n\nKya karna chahte ho?",
            parse_mode="Markdown",
            reply_markup=_delete_menu_keyboard()
        )
        return DEL_AWAIT_CHOICE


# ================================================================
# STATE 53: NukeAll confirmation
# ================================================================

async def del_nukeall_confirm_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END

    text = update.message.text.strip()
    if text != "CONFIRM":
        await update.message.reply_text(
            "❌ *Confirm nahi mila!*\n\n"
            "Exactly `CONFIRM` (capital letters) type karna tha.\n\n"
            "Operation cancel. Data safe hai. 🛡️",
            parse_mode="Markdown"
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text(
        "☢️ *NukeAll shuru ho raha hai...*\n\nThoda wait karo...",
        parse_mode="Markdown"
    )

    results = []
    for key in INTERNAL_KEY_MAP.keys():
        results.append(_wipe_local_store(key))
        ok, msg = _wipe_sheet_tab(key)
        results.append(msg)

    report = "\n".join(results)
    if len(report) > 3500:
        report = report[:3500] + "\n...(aur bhi the)"

    await update.effective_chat.send_message(
        f"☢️ *NUKEALL COMPLETE! Alhamdulillah fresh start!*\n\n{report}\n\n"
        f"_(Local JSON + GitHub bhi update ho gaye)_",
        parse_mode="Markdown"
    )
    log.warning(f"NUKEALL performed at {now_ist().isoformat()}")
    ctx.user_data.clear()
    return ConversationHandler.END


# ================================================================
# STATE 52: Row delete — ID input
# ================================================================

async def del_row_id_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END

    text         = update.message.text.strip()
    selected_key = ctx.user_data.get("dm_selected_sheet_key", "")

    if not selected_key:
        await update.message.reply_text(
            "❌ Sheet select nahi hui. /delsheet se dobara try karo."
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    try:
        row_id = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ Sirf *ID number* daalo! Example: `5`\n/cancel — Bahar jao.",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_SHEET

    tab_name     = SHEET_KEY_MAP.get(selected_key, selected_key)
    internal_key = INTERNAL_KEY_MAP.get(selected_key, selected_key)

    ok = sheets_backup.delete_row_by_value(internal_key, 1, str(row_id))

    if ok:
        await update.message.reply_text(
            f"✅ *Row Delete Ho Gayi! JazakAllah!*\n\n"
            f"📊 Sheet: *{tab_name}*\n🆔 ID: `{row_id}`\n\n"
            f"Sheet se hata diya gaya.",
            parse_mode="Markdown"
        )
        log.info(f"Row deleted: {tab_name} ID={row_id}")
    else:
        await update.message.reply_text(
            f"⚠️ ID `{row_id}` sheet *{tab_name}* mein nahi mila.\n"
            f"Sheet mein sahi ID check karo aur dobara try karo.",
            parse_mode="Markdown"
        )

    ctx.user_data.clear()
    return ConversationHandler.END


# ================================================================
# Callback Query Handler
# ================================================================

async def del_callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if data == "dm_cancel":
        await query.edit_message_text(
            "❌ *Delete operation cancel ho gaya.*\n\nData safe hai! 🛡️",
            parse_mode="Markdown"
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    # Menu → sub actions
    if data == "dm_nuke_logs":
        await query.edit_message_text(
            "⚠️ *CHAT HISTORY NUKE*\n\n"
            "Miscellaneous sheet + local logs delete honge.\n\nPakka?",
            parse_mode="Markdown",
            reply_markup=_confirm_keyboard("nuke_logs")
        )
        return DEL_AWAIT_CHOICE

    if data == "dm_delrow":
        await query.edit_message_text(
            "📋 *Ek Row Delete*\n\nKaunsi sheet se?",
            parse_mode="Markdown",
            reply_markup=_sheet_select_keyboard("dm_row")
        )
        return DEL_AWAIT_CHOICE

    if data == "dm_nukesheet":
        await query.edit_message_text(
            "🧹 *Sheet Wipe*\n\nKaunsi sheet poori saaf karni hai?",
            parse_mode="Markdown",
            reply_markup=_sheet_select_keyboard("dm_wipe")
        )
        return DEL_AWAIT_CHOICE

    if data == "dm_nukeall":
        await query.edit_message_text(
            "☢️ *NUCLEAR OPTION*\n\n"
            "SAARI sheets + SAARA local data permanently delete hoga!\n\n"
            "⛔ Undo NAHI hoga!\n\n"
            "Confirm ke liye *CONFIRM* (capital) type karo:",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_NUKE_CONFIRM

    # Sheet row select
    if data.startswith("dm_row_"):
        sheet_key = data.replace("dm_row_", "")
        ctx.user_data["dm_selected_sheet_key"] = sheet_key
        tab_name = SHEET_KEY_MAP.get(sheet_key, sheet_key)
        await query.edit_message_text(
            f"📋 *{tab_name}* se delete karna hai.\n\n"
            f"Kis row ka *ID number* delete karna hai?\n\n"
            f"Example: `3`",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_SHEET

    # Sheet wipe select
    if data.startswith("dm_wipe_"):
        sheet_key = data.replace("dm_wipe_", "")
        tab_name  = SHEET_KEY_MAP.get(sheet_key, sheet_key)
        ctx.user_data["dm_pending_wipe_key"] = sheet_key
        await query.edit_message_text(
            f"🧹 *'{tab_name}' Wipe*\n\n"
            f"Saari entries delete ho jayengi, header bachega.\n\nPakka?",
            parse_mode="Markdown",
            reply_markup=_confirm_keyboard(f"wipe_{sheet_key}")
        )
        return DEL_AWAIT_CHOICE

    # Confirm: nuke logs
    if data == "dm_confirm_nuke_logs":
        local_msg      = _wipe_local_store("logs")
        ok, sheet_msg  = _wipe_sheet_tab("logs")
        await query.edit_message_text(
            f"🗑️ *Chat History Nuke Complete! Alhamdulillah!*\n\n"
            f"{local_msg}\n{sheet_msg}\n\nSab saaf ho gaya! 🌟",
            parse_mode="Markdown"
        )
        log.info(f"Chat history nuked at {now_ist().isoformat()}")
        ctx.user_data.clear()
        return ConversationHandler.END

    # Confirm: wipe specific sheet
    if data.startswith("dm_confirm_wipe_"):
        sheet_key     = data.replace("dm_confirm_wipe_", "")
        tab_name      = SHEET_KEY_MAP.get(sheet_key, sheet_key)
        local_msg     = _wipe_local_store(sheet_key)
        ok, sheet_msg = _wipe_sheet_tab(sheet_key)
        await query.edit_message_text(
            f"🧹 *'{tab_name}' Wipe Complete! JazakAllah!*\n\n"
            f"{local_msg}\n{sheet_msg}\n\nSheet saaf ho gayi.",
            parse_mode="Markdown"
        )
        log.info(f"Sheet wiped: {tab_name} at {now_ist().isoformat()}")
        ctx.user_data.clear()
        return ConversationHandler.END

    # Unknown
    await query.edit_message_text("❓ Unknown action. /delete se dobara try karo.")
    ctx.user_data.clear()
    return ConversationHandler.END


# ================================================================
# CANCEL
# ================================================================

async def del_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "❌ *Delete operation cancel.*\n\nData safe hai! 🛡️",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


# ================================================================
# REGISTER — FIXED VERSION
# ================================================================

def register_delete_handlers(app: Application):
    """
    bot.py ke main() mein SABSE PEHLE call karo:

        from delete_manager import register_delete_handlers
        register_delete_handlers(app)   # ← app.add_handler se pehle

    Yeh zaruri hai taaki ConversationHandler ka DEL_AWAIT_PASS state
    password message ko capture kare, handle_message() se pehle.
    """

    conv = ConversationHandler(
        entry_points=[
            # Slash commands
            CommandHandler("nuke",      cmd_delete_entry),
            CommandHandler("delsheet",  cmd_delete_entry),
            CommandHandler("nukesheet", cmd_delete_entry),
            CommandHandler("nukeall",   cmd_delete_entry),
            CommandHandler("delete",    cmd_delete_entry),
            # Natural language
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.Regex(
                    _re.compile(
                        r'\b(delete|saaf karo|wipe|nuke|hatao|clear karo|'
                        r'history delete|chat delete|sheet delete|data delete|'
                        r'sab kuch delete|saara data|chat saaf|logs saaf|'
                        r'history saaf|entry hatao|row hatao)\b',
                        _re.IGNORECASE
                    )
                ),
                cmd_nl_delete_entry,
            ),
        ],
        states={
            DEL_AWAIT_PASS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, del_password_check)
            ],
            DEL_AWAIT_CHOICE: [
                CallbackQueryHandler(del_callback_handler, pattern=r"^dm_"),
            ],
            DEL_AWAIT_SHEET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, del_row_id_input),
                CallbackQueryHandler(del_callback_handler, pattern=r"^dm_cancel$"),
            ],
            DEL_AWAIT_NUKE_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, del_nukeall_confirm_text),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", del_cancel),
            CallbackQueryHandler(del_callback_handler, pattern=r"^dm_cancel$"),
        ],
        allow_reentry=True,
        per_message=False,
        per_user=True,   # ✅ FIX: explicitly set
        per_chat=True,   # ✅ FIX: explicitly set
    )

    app.add_handler(conv)

    pw_status = "✅ SET" if DELETE_PASSWORD else "❌ NOT SET — Repository Secrets mein DELETE_PASSWORD add karo!"
    log.info("✅ Delete Manager registered.")
    log.info("   Commands: /nuke /delsheet /nukesheet /nukeall /delete")
    log.info("   NL phrases: 'chat delete karo', 'sab kuch delete', 'sheet se entry hatao', etc.")
    log.info(f"   DELETE_PASSWORD: {pw_status}")


# ================================================================
# STANDALONE
# ================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN env set karo!")
        exit(1)

    if not DELETE_PASSWORD:
        print("⚠️  DELETE_PASSWORD env nahi mili.")
        print("   Repository Secrets mein 'DELETE_PASSWORD' add karo.")

    from telegram.ext import Application as TGApp
    application = TGApp.builder().token(TELEGRAM_TOKEN).build()
    register_delete_handlers(application)

    log.info("🤖 Delete Manager standalone mode — polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
