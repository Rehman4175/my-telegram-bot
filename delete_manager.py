#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DELETE MANAGER — Rk Bot
========================
FIXED v3:
  - _wipe_sheet_tab() ab sahi TAB_MAP keys use karta hai (capital case)
  - Extra sheets nahi banegi — _ws() sirf existing tabs pe kaam karega
  - NukeAll: sirf in-scope sheets wipe karega (10 sheets, Goals nahi)
  - Password capture sahi kaam karta hai
  - per_user=True, per_chat=True set hai

Sheet tabs (exact):
  Tasks | Reminders | Expenses | Habits | Diary
  Memory / Important Notes | Bills & Subscriptions
  Calendar Events | Water Intake | Miscellaneous

Commands:
  /nuke      → Sirf Miscellaneous (chat history) delete
  /delsheet  → Ek sheet ki ek row delete (ID se)
  /nukesheet → Ek poori sheet wipe (header bachta hai)
  /nukeall   → SAARI sheets + saara local data
  /delete    → Full menu open

Har operation se pehle DELETE_PASSWORD maanga jata hai.
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

# Conversation states
DEL_AWAIT_PASS         = 50
DEL_AWAIT_CHOICE       = 51
DEL_AWAIT_SHEET        = 52
DEL_AWAIT_NUKE_CONFIRM = 53

# ----------------------------------------------------------------
# KEY_MAP:
#   key   = short name (hum internally use karte hain)
#   "tab" = exact TAB_MAP key jo GoogleSheetsBackup._ws() samajhta hai
#   "display" = user ko dikhne wala naam
# ----------------------------------------------------------------
SHEETS = {
    "tasks":     {"tab": "Tasks",     "display": "Tasks"},
    "reminders": {"tab": "Reminders", "display": "Reminders"},
    "expenses":  {"tab": "Expenses",  "display": "Expenses"},
    "habits":    {"tab": "Habits",    "display": "Habits"},
    "diary":     {"tab": "Diary",     "display": "Diary"},
    "memory":    {"tab": "Memory",    "display": "Memory / Important Notes"},
    "bills":     {"tab": "Bills",     "display": "Bills & Subscriptions"},
    "calendar":  {"tab": "Calendar",  "display": "Calendar Events"},
    "water":     {"tab": "Water",     "display": "Water Intake"},
    "logs":      {"tab": "Logs",      "display": "Miscellaneous"},
}

# Local store reset defaults
LOCAL_DEFAULTS = {
    "reminders": (lambda: reminders.store, {"list": [], "counter": 0}),
    "tasks":     (lambda: tasks.store,     {"list": [], "counter": 0}),
    "memory":    (lambda: memory.store,    {"facts": []}),
    "goals":     (lambda: goals.store,     {"list": [], "counter": 0}),
    "calendar":  (lambda: calendar.store,  {"events": [], "counter": 0}),
    "bills":     (lambda: bills.store,     {"list": [], "counter": 0}),
    "expenses":  (lambda: expenses.store,  {"list": [], "budget": 0}),
    "habits":    (lambda: habits.store,    {"list": [], "logs": {}, "counter": 0}),
    "water":     (lambda: water.store,     {"logs": {}, "goal_ml": 2000}),
    "logs":      (lambda: chat_hist.store, {"history": []}),
    "diary":     (lambda: diary.store,     {"entries": {}}),
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
# HELPER: Sheet wipe — FIXED
# ================================================================

def _wipe_sheet_tab(key: str):
    """
    key = SHEETS dict ka key, e.g. "logs", "tasks"
    Internally TAB_MAP key use hoga jo _ws() samajhta hai.
    IMPORTANT: Naya tab nahi banega — sirf existing tab wipe hoga.
    """
    if not sheets_backup.connected:
        return False, "⚠️ Google Sheets connected nahi hai!"

    sheet_info = SHEETS.get(key)
    if not sheet_info:
        return False, f"⚠️ Unknown sheet key: {key}"

    tab_key     = sheet_info["tab"]      # e.g. "Logs", "Tasks"
    display     = sheet_info["display"]  # e.g. "Miscellaneous", "Tasks"

    # _ws() ko TAB_MAP key do — ye internally TAB_MAP se real tab name lookup karega
    # Lekin pehle check karo tab exist karti hai ya nahi (auto-create se bachne ke liye)
    tab_real_name = sheets_backup.TAB_MAP.get(tab_key, tab_key)
    ws_cache      = sheets_backup._ws_cache

    # Tab already cached hai ya sheet mein exist karti hai — check karo
    if tab_real_name not in ws_cache:
        # Cache mein nahi — manually check karo bina auto-create ke
        try:
            ws_found = sheets_backup._book.worksheet(tab_real_name)
            sheets_backup._ws_cache[tab_real_name] = ws_found
        except Exception:
            return False, f"⚠️ Tab '{display}' Google Sheet mein nahi mili. Create mat ki — manually add karo."

    # Ab _ws() safely call kar sakte hain — tab exist karti hai
    ws = sheets_backup._ws(tab_key)
    if not ws:
        return False, f"⚠️ '{display}' tab access nahi ho saka!"

    try:
        all_values = ws.get_all_values()
        total_rows = len(all_values)
        if total_rows <= 1:
            return True, f"ℹ️ '{display}' pehle se khali hai (ya sirf header hai)."

        # Row 2 se last tak delete karo (reverse order mein)
        for row_idx in range(total_rows, 1, -1):
            ws.delete_rows(row_idx)

        return True, f"✅ '{display}' — {total_rows - 1} rows delete ho gayi. Header safe hai. ✨"

    except Exception as e:
        log.error(f"_wipe_sheet_tab [{key}]: {e}")
        return False, f"❌ Error wiping '{display}': {e}"


def _wipe_local_store(key: str) -> str:
    """Local JSON store reset karo."""
    if key not in LOCAL_DEFAULTS:
        return f"⚠️ Unknown local store: {key}"
    try:
        get_store, default_data = LOCAL_DEFAULTS[key]
        store_obj      = get_store()
        store_obj.data = default_data.copy()
        store_obj.save()
        return f"✅ Local '{key}' cleared."
    except Exception as e:
        return f"⚠️ Local '{key}' error: {e}"


# ================================================================
# KEYBOARDS
# ================================================================

def _delete_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Chat History (Miscellaneous) Delete", callback_data="dm_nuke_logs")],
        [InlineKeyboardButton("📋 Ek Sheet Entry Delete (by ID)",        callback_data="dm_delrow")],
        [InlineKeyboardButton("🧹 Ek Poori Sheet Wipe",                  callback_data="dm_nukesheet")],
        [InlineKeyboardButton("☢️ SABB KUCH DELETE (NukeAll)",           callback_data="dm_nukeall")],
        [InlineKeyboardButton("❌ Cancel",                                callback_data="dm_cancel")],
    ])


def _sheet_select_keyboard(action_prefix: str):
    keys    = list(SHEETS.keys())
    buttons = []
    row     = []
    for k in keys:
        row.append(InlineKeyboardButton(SHEETS[k]["display"], callback_data=f"{action_prefix}_{k}"))
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
    text   = update.message.text or ""
    intent = parse_delete_intent(text) or "menu"
    ctx.user_data["dm_entry_cmd"] = intent
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

    if not DELETE_PASSWORD:
        await update.effective_chat.send_message(
            "❌ *DELETE_PASSWORD set nahi hai!*\n\n"
            "Repository Secrets mein `DELETE_PASSWORD` add karo.",
            parse_mode="Markdown"
        )
        ctx.user_data.clear()
        return ConversationHandler.END

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
            "✅ *Password Sahi!*\n\n"
            "⚠️ *CHAT HISTORY NUKE*\n\n"
            "Miscellaneous sheet + local chat history delete hogi.\n\nPakka?",
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
            "In *10 sheets* ka saara data + local JSON delete hoga:\n"
            "Tasks, Reminders, Expenses, Habits, Diary,\n"
            "Memory, Bills, Calendar, Water, Miscellaneous\n\n"
            "⛔ Yeh undo NAHI hoga!\n\n"
            "Confirm karne ke liye exactly *CONFIRM* (capital mein) type karo:",
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
# STATE 53: NukeAll — CONFIRM text
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

    # Sirf SHEETS dict ke keys wipe karo — koi extra tab nahi banega
    for key in SHEETS.keys():
        local_msg = _wipe_local_store(key)
        results.append(local_msg)

        ok, sheet_msg = _wipe_sheet_tab(key)
        results.append(sheet_msg)

    # Goals local bhi clear karo (sheet tab nahi hai scope mein)
    try:
        goals.store.data = {"list": [], "counter": 0}
        goals.store.save()
        results.append("✅ Local 'goals' cleared.")
    except Exception as e:
        results.append(f"⚠️ Goals local: {e}")

    report = "\n".join(results)
    if len(report) > 3500:
        report = report[:3500] + "\n...(truncated)"

    await update.effective_chat.send_message(
        f"☢️ *NUKEALL COMPLETE!*\n\n{report}\n\n"
        f"_(Local JSON + GitHub push ho gaya)_",
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

    sheet_info   = SHEETS.get(selected_key, {})
    tab_key      = sheet_info.get("tab", selected_key)
    display      = sheet_info.get("display", selected_key)

    ok = sheets_backup.delete_row_by_value(tab_key, 1, str(row_id))

    if ok:
        await update.message.reply_text(
            f"✅ *Row Delete Ho Gayi!*\n\n"
            f"📊 Sheet: *{display}*\n🆔 ID: `{row_id}`",
            parse_mode="Markdown"
        )
        log.info(f"Row deleted: {display} ID={row_id}")
    else:
        await update.message.reply_text(
            f"⚠️ ID `{row_id}` sheet *{display}* mein nahi mila.\n"
            f"Sahi ID check karo aur dobara try karo.",
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

    # Cancel
    if data == "dm_cancel":
        await query.edit_message_text(
            "❌ *Delete operation cancel ho gaya.*\n\nData safe hai! 🛡️",
            parse_mode="Markdown"
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    # Menu actions
    if data == "dm_nuke_logs":
        await query.edit_message_text(
            "⚠️ *CHAT HISTORY NUKE*\n\n"
            "Miscellaneous sheet + local chat history delete hogi.\n\nPakka?",
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
            "🧹 *Sheet Wipe*\n\nKaunsi sheet poori saaf karni hai?\n"
            "_(Header bachega, baaki sab delete hoga)_",
            parse_mode="Markdown",
            reply_markup=_sheet_select_keyboard("dm_wipe")
        )
        return DEL_AWAIT_CHOICE

    if data == "dm_nukeall":
        await query.edit_message_text(
            "☢️ *NUCLEAR OPTION*\n\n"
            "SAARI 10 sheets + SAARA local data permanently delete hoga!\n\n"
            "⛔ Undo NAHI hoga!\n\n"
            "Confirm ke liye exactly *CONFIRM* (capital) type karo:",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_NUKE_CONFIRM

    # Sheet row select
    if data.startswith("dm_row_"):
        sheet_key = data.replace("dm_row_", "")
        ctx.user_data["dm_selected_sheet_key"] = sheet_key
        display   = SHEETS.get(sheet_key, {}).get("display", sheet_key)
        await query.edit_message_text(
            f"📋 *{display}* se delete karna hai.\n\n"
            f"Kis row ka *ID number* delete karna hai?\n\nExample: `3`",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_SHEET

    # Sheet wipe select
    if data.startswith("dm_wipe_"):
        sheet_key = data.replace("dm_wipe_", "")
        display   = SHEETS.get(sheet_key, {}).get("display", sheet_key)
        ctx.user_data["dm_pending_wipe_key"] = sheet_key
        await query.edit_message_text(
            f"🧹 *'{display}' Wipe*\n\n"
            f"Saari entries delete ho jayengi, header bachega.\n\nPakka?",
            parse_mode="Markdown",
            reply_markup=_confirm_keyboard(f"wipe_{sheet_key}")
        )
        return DEL_AWAIT_CHOICE

    # Confirm: nuke logs
    if data == "dm_confirm_nuke_logs":
        local_msg     = _wipe_local_store("logs")
        ok, sheet_msg = _wipe_sheet_tab("logs")
        status        = "✅" if ok else "⚠️"
        await query.edit_message_text(
            f"🗑️ *Chat History Nuke Complete!*\n\n"
            f"{local_msg}\n{sheet_msg}",
            parse_mode="Markdown"
        )
        log.info(f"Chat history nuked at {now_ist().isoformat()}")
        ctx.user_data.clear()
        return ConversationHandler.END

    # Confirm: wipe specific sheet
    if data.startswith("dm_confirm_wipe_"):
        sheet_key     = data.replace("dm_confirm_wipe_", "")
        display       = SHEETS.get(sheet_key, {}).get("display", sheet_key)
        local_msg     = _wipe_local_store(sheet_key)
        ok, sheet_msg = _wipe_sheet_tab(sheet_key)
        await query.edit_message_text(
            f"🧹 *'{display}' Wipe Complete!*\n\n"
            f"{local_msg}\n{sheet_msg}",
            parse_mode="Markdown"
        )
        log.info(f"Sheet wiped: {display} at {now_ist().isoformat()}")
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
# REGISTER
# ================================================================

def register_delete_handlers(app: Application):
    """
    bot.py ke main() mein SABSE PEHLE call karo:

        from delete_manager import register_delete_handlers
        register_delete_handlers(app)

    Yeh zaruri hai taaki ConversationHandler ka DEL_AWAIT_PASS state
    password message ko capture kare, handle_message() se pehle.
    """

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("nuke",      cmd_delete_entry),
            CommandHandler("delsheet",  cmd_delete_entry),
            CommandHandler("nukesheet", cmd_delete_entry),
            CommandHandler("nukeall",   cmd_delete_entry),
            CommandHandler("delete",    cmd_delete_entry),
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
        per_user=True,
        per_chat=True,
    )

    app.add_handler(conv)

    pw_status = "✅ SET" if DELETE_PASSWORD else "❌ NOT SET — Repository Secrets mein DELETE_PASSWORD add karo!"
    log.info("✅ Delete Manager v3 registered.")
    log.info("   Commands: /nuke /delsheet /nukesheet /nukeall /delete")
    log.info(f"   DELETE_PASSWORD: {pw_status}")
    log.info(f"   Sheets in scope: {list(SHEETS.keys())}")


# ================================================================
# STANDALONE TEST
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
        print("⚠️  DELETE_PASSWORD env nahi mili — Repository Secrets mein add karo.")

    from telegram.ext import Application as TGApp
    application = TGApp.builder().token(TELEGRAM_TOKEN).build()
    register_delete_handlers(application)

    log.info("🤖 Delete Manager standalone mode — polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
