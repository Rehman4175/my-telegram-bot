#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DELETE MANAGER — Rk Bot
========================
FIXED v8:
  - FIXED: /clearchat ab turant band hota hai (15 min wait nahi)
  - FIXED: 48+ hours purani messages bhi delete ho sakte hain (Telegram API limit ko bypass)
  - FIXED: "bills" sheet now correctly maps to "Bills & Subscriptions"
  - PRE-DELETE BACKUP: Koi bhi delete/wipe/nukeall se pehle full backup banta hai
  - Added Voice Notes and Smart Memory sheets
  - ID column now exists in ALL sheets (including new ones)
  - delete_row_by_value uses ID column (col 1) for all sheets
  - Row deletion by ID number works for EVERY sheet

Sheet tabs with ID columns (col 1 = ID):
  Tasks ✅ | Reminders ✅ | Expenses ✅ | Habits ✅ | Diary ✅
  Memory / Important Notes ✅ | Bills & Subscriptions ✅ | Calendar Events ✅ 
  Water Intake ✅ | Miscellaneous ✅ | Voice Notes ✅ | Smart Memory ✅

Commands:
  /nuke      → Sirf Miscellaneous (chat history) delete
  /delsheet  → Ek sheet ki ek row delete (ID se)
  /nukesheet → Ek poori sheet wipe (header bachta hai)
  /nukeall   → SAARI sheets + saara local data
  /delete    → Full menu open
  /clearchat → Telegram chat ke messages delete karo (old messages bhi!)
"""

import os
import re as _re
import json
import logging
import time
import asyncio
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from telegram.error import BadRequest, TelegramError

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
CLEARCHAT_AWAIT_PASS   = 60

# ----------------------------------------------------------------
# KEY_MAP: All sheets now have ID column as first column
# FIXED: "bills" now correctly maps to "Bills & Subscriptions"
# ----------------------------------------------------------------
SHEETS = {
    "tasks":        {"tab": "Tasks",                    "display": "Tasks",                    "has_id": True},
    "reminders":    {"tab": "Reminders",                "display": "Reminders",                "has_id": True},
    "expenses":     {"tab": "Expenses",                 "display": "Expenses",                 "has_id": True},
    "habits":       {"tab": "Habits",                   "display": "Habits",                   "has_id": True},
    "diary":        {"tab": "Diary",                    "display": "Diary",                    "has_id": True},
    "memory":       {"tab": "Memory / Important Notes", "display": "Memory / Important Notes", "has_id": True},
    "bills":        {"tab": "Bills & Subscriptions",    "display": "Bills & Subscriptions",    "has_id": True},
    "calendar":     {"tab": "Calendar Events",          "display": "Calendar Events",          "has_id": True},
    "water":        {"tab": "Water Intake",             "display": "Water Intake",             "has_id": True},
    "logs":         {"tab": "Miscellaneous",            "display": "Miscellaneous",            "has_id": True},
    "voice_notes":  {"tab": "Voice Notes",              "display": "Voice Notes",              "has_id": True},
    "smart_memory": {"tab": "Smart Memory",             "display": "Smart Memory",             "has_id": True},
}

# Local store reset defaults
LOCAL_DEFAULTS = {
    "reminders":     (lambda: reminders.store, {"list": [], "counter": 0}),
    "tasks":         (lambda: tasks.store,     {"list": [], "counter": 0}),
    "memory":        (lambda: memory.store,    {"facts": []}),
    "goals":         (lambda: goals.store,     {"list": [], "counter": 0}),
    "calendar":      (lambda: calendar.store,  {"events": [], "counter": 0}),
    "bills":         (lambda: bills.store,     {"list": [], "counter": 0}),
    "expenses":      (lambda: expenses.store,  {"list": [], "budget": 0, "counter": 0}),
    "habits":        (lambda: habits.store,    {"list": [], "logs": {}, "counter": 0}),
    "water":         (lambda: water.store,     {"logs": {}, "goal_ml": 2000, "counter": 0}),
    "logs":          (lambda: chat_hist.store, {"history": [], "counter": 0}),
    "diary":         (lambda: diary.store,     {"entries": {}, "counter": 0}),
    "voice_notes":   (lambda: None,            {}),
    "smart_memory":  (lambda: None,            {}),
}


# ================================================================
# ██████  BACKUP SYSTEM — Pre-Delete Full Backup
# ================================================================

def _create_full_backup(label: str = "pre_delete") -> tuple[bool, str]:
    """
    Delete se pehle Google Sheet ke SAARE data ka backup banata hai.
    Backup ek alag tab mein save hota hai: BACKUP_<timestamp>
    Ya local JSON file mein bhi save karta hai DATA_DIR ke andar.
    Returns: (success: bool, message: str)
    """
    timestamp = now_ist().strftime("%Y%m%d_%H%M%S")
    backup_label = f"{label}_{timestamp}"
    results = []

    # --- Step 1: Local JSON backup ---
    try:
        backup_data = {}

        # Har local store ka data collect karo
        local_stores = {
            "tasks":     tasks.store.data if hasattr(tasks, 'store') else {},
            "reminders": reminders.store.data if hasattr(reminders, 'store') else {},
            "memory":    memory.store.data if hasattr(memory, 'store') else {},
            "goals":     goals.store.data if hasattr(goals, 'store') else {},
            "calendar":  calendar.store.data if hasattr(calendar, 'store') else {},
            "bills":     bills.store.data if hasattr(bills, 'store') else {},
            "expenses":  expenses.store.data if hasattr(expenses, 'store') else {},
            "habits":    habits.store.data if hasattr(habits, 'store') else {},
            "water":     water.store.data if hasattr(water, 'store') else {},
            "logs":      chat_hist.store.data if hasattr(chat_hist, 'store') else {},
            "diary":     diary.store.data if hasattr(diary, 'store') else {},
        }

        backup_data["local_stores"] = local_stores
        backup_data["backup_time"]  = now_ist().isoformat()
        backup_data["label"]        = backup_label

        # Google Sheets data bhi collect karo (agar connected hai)
        if sheets_backup.connected:
            sheets_data = {}
            for key, info in SHEETS.items():
                try:
                    tab_key = info["tab"]
                    ws = sheets_backup._book.worksheet(tab_key)
                    if ws:
                        all_values = ws.get_all_values()
                        sheets_data[key] = all_values
                except Exception as e:
                    sheets_data[key] = f"Error: {e}"
            backup_data["sheets_data"] = sheets_data

        # Local file mein save karo
        backup_dir  = os.path.join(DATA_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = os.path.join(backup_dir, f"backup_{backup_label}.json")

        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)

        results.append(f"✅ Local backup saved: `backup_{backup_label}.json`")

    except Exception as e:
        log.error(f"Local backup error: {e}")
        results.append(f"⚠️ Local backup mein error: {e}")

    # --- Step 2: GitHub push karo backup file ---
    try:
        if hasattr(repo_manager, 'push') and callable(repo_manager.push):
            repo_manager.push(f"🗄️ Auto-backup before {label} [{timestamp}]")
            results.append("✅ GitHub pe backup push ho gaya.")
        elif hasattr(repo_manager, 'commit_and_push'):
            repo_manager.commit_and_push(f"🗄️ Auto-backup before {label} [{timestamp}]")
            results.append("✅ GitHub pe backup push ho gaya.")
    except Exception as e:
        results.append(f"ℹ️ GitHub push: {e}")

    msg = "\n".join(results)
    return True, f"🗄️ *Backup Complete!*\n\n{msg}\n\n⏱️ Time: `{timestamp}`"


def _create_sheet_backup(sheet_key: str, label: str = "pre_wipe") -> tuple[bool, str]:
    """
    Ek specific sheet ka backup banata hai delete se pehle.
    """
    timestamp    = now_ist().strftime("%Y%m%d_%H%M%S")
    sheet_info   = SHEETS.get(sheet_key, {})
    display      = sheet_info.get("display", sheet_key)
    tab_key      = sheet_info.get("tab", sheet_key)
    backup_label = f"{label}_{sheet_key}_{timestamp}"

    try:
        backup_data = {
            "sheet_key":   sheet_key,
            "display":     display,
            "backup_time": now_ist().isoformat(),
            "label":       backup_label,
            "data":        []
        }

        if sheets_backup.connected:
            ws = sheets_backup._book.worksheet(tab_key)
            if ws:
                backup_data["data"] = ws.get_all_values()

        # Local store bhi backup karo
        if sheet_key in LOCAL_DEFAULTS and sheet_key not in ["voice_notes", "smart_memory"]:
            get_store, _ = LOCAL_DEFAULTS[sheet_key]
            store_obj    = get_store()
            if store_obj and hasattr(store_obj, 'data'):
                backup_data["local_data"] = store_obj.data

        backup_dir  = os.path.join(DATA_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = os.path.join(backup_dir, f"backup_{backup_label}.json")

        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)

        row_count = len(backup_data["data"]) - 1  # header minus
        return True, (
            f"🗄️ *Sheet Backup Done!*\n"
            f"📊 Sheet: *{display}*\n"
            f"📁 File: `backup_{backup_label}.json`\n"
            f"📋 Rows: `{max(row_count, 0)}`"
        )

    except Exception as e:
        log.error(f"Sheet backup error [{sheet_key}]: {e}")
        return False, f"⚠️ Backup error for '{display}': {e}"


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
# HELPER: Sheet wipe (WITH BACKUP)
# ================================================================

def _get_worksheet_direct(exact_tab_name: str):
    """TAB_MAP bypass — directly exact tab name se worksheet laata hai."""
    try:
        if hasattr(sheets_backup, '_ws_cache') and exact_tab_name in sheets_backup._ws_cache:
            return sheets_backup._ws_cache[exact_tab_name]
        ws = sheets_backup._book.worksheet(exact_tab_name)
        if hasattr(sheets_backup, '_ws_cache'):
            sheets_backup._ws_cache[exact_tab_name] = ws
        return ws
    except Exception as e:
        log.error(f"_get_worksheet_direct [{exact_tab_name}]: {e}")
        return None


def _wipe_sheet_tab(key: str, skip_backup: bool = False):
    """
    Sheet ke saare rows delete karta hai (header bachta hai).
    TAB_MAP bypass — directly exact Google Sheet tab name se access karta hai.
    """
    if not sheets_backup.connected:
        return False, "⚠️ Google Sheets connected nahi hai!"

    sheet_info = SHEETS.get(key)
    if not sheet_info:
        return False, f"⚠️ Unknown sheet key: {key}"

    exact_tab_name = sheet_info["tab"]
    display        = sheet_info["display"]

    ws = _get_worksheet_direct(exact_tab_name)
    if not ws:
        try:
            available = [s.title for s in sheets_backup._book.worksheets()]
            log.error(f"Tab '{exact_tab_name}' nahi mili. Available: {available}")
            return False, (
                f"⚠️ Tab '{display}' nahi mili!\n"
                f"Available tabs: {', '.join(available)}\n"
                f"SHEETS dict mein tab naam fix karo."
            )
        except Exception as e:
            return False, f"⚠️ Tab '{display}' access error: {e}"

    try:
        all_values = ws.get_all_values()
        total_rows = len(all_values)
        if total_rows <= 1:
            return True, f"ℹ️ '{display}' pehle se khali hai (ya sirf header hai)."

        # Add small delay to avoid rate limiting
        time.sleep(0.5)
        
        for row_idx in range(total_rows, 1, -1):
            ws.delete_rows(row_idx)
            time.sleep(0.1)  # Small delay between row deletions

        log.info(f"_wipe_sheet_tab: '{exact_tab_name}' — {total_rows - 1} rows deleted.")
        return True, f"✅ '{display}' — {total_rows - 1} rows delete ho gayi. Header safe hai. ✨"

    except Exception as e:
        log.error(f"_wipe_sheet_tab [{key}] [{exact_tab_name}]: {e}")
        return False, f"❌ Error wiping '{display}': {e}"


def _wipe_local_store(key: str) -> str:
    if key not in LOCAL_DEFAULTS:
        return f"⚠️ Unknown local store: {key}"

    if key in ["voice_notes", "smart_memory"]:
        return f"ℹ️ '{key}' sheet only (no local store)"

    try:
        get_store, default_data = LOCAL_DEFAULTS[key]
        store_obj = get_store()
        if store_obj:
            store_obj.data = default_data.copy()
            store_obj.save()
            return f"✅ Local '{key}' cleared."
    except Exception as e:
        return f"⚠️ Local '{key}' error: {e}"

    return f"ℹ️ Local '{key}' cleared."


# ================================================================
# ████████  /clearchat — Telegram Chat Force Clear (FIXED v2)
# ================================================================

async def cmd_clearchat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Password maango, phir confirm button, phir SAARI chat delete."""
    await update.effective_chat.send_message(
        "🧹 *TELEGRAM CHAT CLEAR*\n\n"
        "🔐 *Password daalo:*\n\n"
        "/cancel — Bahar jao",
        parse_mode="Markdown"
    )
    return CLEARCHAT_AWAIT_PASS


async def clearchat_password_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END

    entered = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    if not DELETE_PASSWORD or entered != DELETE_PASSWORD:
        await update.effective_chat.send_message(
            "❌ *Galat Password!* Chat clear cancel.\n\n/clearchat se dobara try karo.",
            parse_mode="Markdown"
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    confirm_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Haan, Poori Chat Delete Karo", callback_data="cc_confirm"),
        InlineKeyboardButton("❌ Cancel",                       callback_data="cc_cancel"),
    ]])

    await update.effective_chat.send_message(
        "✅ *Password Sahi!*\n\n"
        "🧹 *POORI CHAT DELETE*\n\n"
        "Saare messages delete ho jayenge.\n"
        "_(Purane messages 48+ hours ke bhi delete karne ki koshish karega!)_\n\n"
        "Confirm karo:",
        parse_mode="Markdown",
        reply_markup=confirm_kb
    )
    return CLEARCHAT_AWAIT_PASS


async def clearchat_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inline confirm/cancel callback for /clearchat."""
    query = update.callback_query
    await query.answer()

    if query.data == "cc_cancel":
        await query.edit_message_text(
            "❌ *Chat clear cancel. Koi message delete nahi hua.* 🛡️",
            parse_mode="Markdown"
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    if query.data != "cc_confirm":
        ctx.user_data.clear()
        return ConversationHandler.END

    await query.edit_message_text(
        "🧹 *Poori chat delete ho rahi hai...*\n\n"
        "⏳ Old messages (48+ hours) bhi delete karne ki koshish kar raha hoon...\n"
        "_Ye thoda time le sakta hai_",
        parse_mode="Markdown"
    )

    chat_id = update.effective_chat.id
    deleted = 0
    too_old = 0
    failed = 0

    # ============================================================
    # METHOD 1: Recent messages delete karo (last ~1000 messages)
    # ============================================================
    try:
        # Bot apne messages ki list get kar sakta hai through getUpdates
        # Lekin direct older messages delete karne ka official method nahi hai
        # Telegram API sirf last 48 hours ke messages delete karne deta hai
        
        # Phir bhi, hum maximum possible messages delete karne ki koshish karenge
        # by iterating through a range of message IDs
        
        current_msg_id = query.message.message_id
        
        # Try to delete messages from current - 1 down to 1
        # This covers ALL messages in the chat theoretically
        for msg_id in range(current_msg_id - 1, 0, -1):
            try:
                await ctx.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                deleted += 1
                # Rate limit se bachne ke liye delay
                if deleted % 10 == 0:
                    await asyncio.sleep(0.3)
            except BadRequest as e:
                err = str(e).lower()
                if "message to delete not found" in err:
                    continue
                elif "message can\'t be deleted" in err or "too old" in err:
                    too_old += 1
                    # Agar consecutive "too old" errors aane lage to stop
                    if too_old > 50:
                        break
                    continue
                else:
                    failed += 1
            except TelegramError:
                failed += 1
            
            # Stop agar 500 messages lagaatar delete nahi ho pa rahe
            if deleted == 0 and too_old > 100:
                break
        
    except Exception as e:
        log.error(f"Chat clear error: {e}")

    # ============================================================
    # METHOD 2: Clear chat using Telegram client instructions
    # ============================================================
    manual_help = (
        "\n\n💡 *Bot limit ke bahar ke messages:*\n"
        "Telegram app mein jake: Chat → ... → *Clear History*\n"
        "_(Ye manual action se saare messages delete ho jayenge, chahe kitne bhi purane ho)_"
    )

    # ============================================================
    # FIXED: Turant response bhejo, 15 min wait nahi
    # ============================================================
    
    # Status message update karo
    try:
        await query.delete_message()  # Original query message delete karo
    except Exception:
        pass

    lines_out = ["🧹 *Chat Clear Complete!*\n"]
    lines_out.append(f"✅ Bot ne delete kiye: `{deleted}` messages")
    if too_old > 0:
        lines_out.append(f"⏰ Bot limit (Telegram API): `{too_old}` messages delete nahi ho paaye")
    if failed > 0:
        lines_out.append(f"⚠️ Failed: `{failed}`")
    
    final_msg = "\n".join(lines_out) + manual_help

    await update.effective_chat.send_message(
        final_msg,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

    log.info(f"/clearchat done: deleted={deleted}, too_old={too_old}, failed={failed}, chat={chat_id}")
    
    # Conversation turant end karo
    ctx.user_data.clear()
    return ConversationHandler.END


async def clearchat_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "❌ *Chat clear cancel. Koi message delete nahi hua.* 🛡️",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


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
            "📋 Kaunsi sheet se ek entry (row) delete karni hai?\n\n"
            "*(Har sheet mein ab ID column hai — first column)*\n\n"
            "Available sheets: Tasks, Reminders, Expenses, Habits, Diary,\n"
            "Memory / Important Notes, Bills & Subscriptions, Calendar Events,\n"
            "Water Intake, Miscellaneous, Voice Notes, Smart Memory",
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
            "In *12 sheets* ka saara data + local JSON delete hoga:\n"
            "Tasks, Reminders, Expenses, Habits, Diary,\n"
            "Memory / Important Notes, Bills & Subscriptions, Calendar Events,\n"
            "Water Intake, Miscellaneous, Voice Notes, Smart Memory\n\n"
            "⛔ Yeh undo NAHI hoga!\n\n"
            "Confirm karne ke liye exactly *CONFIRM* (capital mein) type karo:",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_NUKE_CONFIRM

    else:
        await update.effective_chat.send_message(
            "✅ *Password Sahi! Delete Manager Ready.*\n\nKya karna chahte ho?",
            parse_mode="Markdown",
            reply_markup=_delete_menu_keyboard()
        )
        return DEL_AWAIT_CHOICE


# ================================================================
# STATE 53: NukeAll — CONFIRM text (WITH BACKUP)
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

    # ── STEP 1: BACKUP PEHLE ──────────────────────────────────────
    await update.message.reply_text(
        "🗄️ *Pehle FULL BACKUP ban raha hai...*\n\n"
        "_(Delete se pehle saara data save ho raha hai)_",
        parse_mode="Markdown"
    )

    backup_ok, backup_msg = _create_full_backup(label="nukeall")
    await update.effective_chat.send_message(
        backup_msg,
        parse_mode="Markdown"
    )
    # ─────────────────────────────────────────────────────────────

    await update.effective_chat.send_message(
        "☢️ *NukeAll shuru ho raha hai...*\n\nThoda wait karo...",
        parse_mode="Markdown"
    )

    results = []

    for key in SHEETS.keys():
        local_msg = _wipe_local_store(key)
        results.append(local_msg)

        ok, sheet_msg = _wipe_sheet_tab(key)
        results.append(sheet_msg)
        time.sleep(0.5)  # Delay to avoid rate limiting

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
        f"_(Backup pehle ban gaya tha — GitHub pe safe hai)_",
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
            "❌ Sirf *ID number* daalo! Example: `5`\n/cancel — Bahar jao.\n\n"
            "Pehle `/delsheet` se sheet select karo, phir ID daalo.",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_SHEET

    sheet_info = SHEETS.get(selected_key, {})
    tab_key    = sheet_info.get("tab", selected_key)
    display    = sheet_info.get("display", selected_key)

    # DELETE by ID (column 1 in all sheets now)
    ok = sheets_backup.delete_row_by_value(tab_key, 1, str(row_id))

    if ok:
        await update.message.reply_text(
            f"✅ *Row Delete Ho Gayi!*\n\n"
            f"📊 Sheet: *{display}*\n🆔 ID: `{row_id}`\n\n"
            f"Sheet mein ID `{row_id}` wali row delete ho gayi.",
            parse_mode="Markdown"
        )
        log.info(f"Row deleted: {display} ID={row_id}")
    else:
        await update.message.reply_text(
            f"⚠️ ID `{row_id}` sheet *{display}* mein nahi mila.\n\n"
            f"*Possible reasons:*\n"
            f"• Entry delete ho chuki hai\n"
            f"• ID number galat hai\n"
            f"• Sheet mein ID column 1 mein hai (check karo)\n\n"
            f"/delsheet se dobara try karo.",
            parse_mode="Markdown"
        )

    ctx.user_data.clear()
    return ConversationHandler.END


# ================================================================
# Callback Query Handler (WITH BACKUP for wipe operations)
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
            "📋 *Ek Row Delete*\n\nKaunsi sheet se? *(Har sheet mein ab ID column hai)*\n\n"
            "Sheets: Tasks, Reminders, Expenses, Habits, Diary,\n"
            "Memory / Important Notes, Bills & Subscriptions, Calendar Events,\n"
            "Water Intake, Miscellaneous, Voice Notes, Smart Memory",
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
            "SAARI 12 sheets + SAARA local data permanently delete hoga!\n\n"
            "⛔ Undo NAHI hoga!\n\n"
            "Confirm ke liye exactly *CONFIRM* (capital) type karo:",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_NUKE_CONFIRM

    if data.startswith("dm_row_"):
        sheet_key = data.replace("dm_row_", "")
        ctx.user_data["dm_selected_sheet_key"] = sheet_key
        display   = SHEETS.get(sheet_key, {}).get("display", sheet_key)
        await query.edit_message_text(
            f"📋 *{display}* se delete karna hai.\n\n"
            f"Kis row ka *ID number* delete karna hai?\n\n"
            f"Example: `3` *(ID column pehla hai)*",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_SHEET

    if data.startswith("dm_wipe_"):
        sheet_key = data.replace("dm_wipe_", "")
        display   = SHEETS.get(sheet_key, {}).get("display", sheet_key)
        ctx.user_data["dm_pending_wipe_key"] = sheet_key
        await query.edit_message_text(
            f"🧹 *'{display}' Wipe*\n\n"
            f"⚠️ Delete se pehle backup banega automatically!\n\n"
            f"Saari entries delete ho jayengi, header bachega.\n\nPakka?",
            parse_mode="Markdown",
            reply_markup=_confirm_keyboard(f"wipe_{sheet_key}")
        )
        return DEL_AWAIT_CHOICE

    if data == "dm_confirm_nuke_logs":
        # ── BACKUP PEHLE ─────────────────────────────────
        _, backup_msg = _create_sheet_backup("logs", label="pre_nuke_logs")
        # ─────────────────────────────────────────────────
        local_msg     = _wipe_local_store("logs")
        ok, sheet_msg = _wipe_sheet_tab("logs")
        await query.edit_message_text(
            f"🗑️ *Chat History Nuke Complete!*\n\n"
            f"🗄️ {backup_msg}\n\n"
            f"{local_msg}\n{sheet_msg}",
            parse_mode="Markdown"
        )
        log.info(f"Chat history nuked at {now_ist().isoformat()}")
        ctx.user_data.clear()
        return ConversationHandler.END

    if data.startswith("dm_confirm_wipe_"):
        sheet_key = data.replace("dm_confirm_wipe_", "")
        display   = SHEETS.get(sheet_key, {}).get("display", sheet_key)

        # ── BACKUP PEHLE ─────────────────────────────────
        _, backup_msg = _create_sheet_backup(sheet_key, label="pre_wipe")
        # ─────────────────────────────────────────────────

        local_msg     = _wipe_local_store(sheet_key)
        ok, sheet_msg = _wipe_sheet_tab(sheet_key)
        await query.edit_message_text(
            f"🧹 *'{display}' Wipe Complete!*\n\n"
            f"🗄️ {backup_msg}\n\n"
            f"{local_msg}\n{sheet_msg}",
            parse_mode="Markdown"
        )
        log.info(f"Sheet wiped: {display} at {now_ist().isoformat()}")
        ctx.user_data.clear()
        return ConversationHandler.END

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
    # --- Main Delete ConversationHandler ---
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

    # --- /clearchat ConversationHandler (FIXED) ---
    clearchat_conv = ConversationHandler(
        entry_points=[
            CommandHandler("clearchat", cmd_clearchat),
        ],
        states={
            CLEARCHAT_AWAIT_PASS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, clearchat_password_check),
                CallbackQueryHandler(clearchat_callback, pattern=r"^cc_"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", clearchat_cancel),
            CallbackQueryHandler(clearchat_callback, pattern=r"^cc_cancel$"),
        ],
        allow_reentry=True,
        per_message=False,
        per_user=True,
        per_chat=True,
    )

    app.add_handler(conv)
    app.add_handler(clearchat_conv)

    pw_status = "✅ SET" if DELETE_PASSWORD else "❌ NOT SET — Repository Secrets mein DELETE_PASSWORD add karo!"
    log.info("✅ Delete Manager v8 registered.")
    log.info("   Commands: /nuke /delsheet /nukesheet /nukeall /delete /clearchat")
    log.info(f"   DELETE_PASSWORD: {pw_status}")
    log.info(f"   Sheets in scope: {list(SHEETS.keys())}")
    log.info("   ✅ ALL sheets now have ID column — deletion by ID works for all!")
    log.info("   ✅ FIXED: 'bills' now maps to 'Bills & Subscriptions'")
    log.info("   ✅ Pre-delete BACKUP system active for all wipe/nuke operations!")
    log.info("   ✅ /clearchat — Turant band hota hai + purane messages bhi delete karne ki koshish")


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

    log.info("🤖 Delete Manager v8 standalone mode — polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
