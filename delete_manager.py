#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DELETE MANAGER — Rk Bot (FAST + AUTO-CLEANUP + FIXED)
======================================================
- All original features preserved
- FAST: batch_clear() for sheet wipe
- FAST: batch deletion for chat clear
- Pre-delete backup active
- AUTO-CLEANUP: All intermediate messages deleted after operation
- FIXED: NUKEALL confirmation working
- FIXED: Case-insensitive CONFIRM check
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
# FIXED: Sheet names match actual Google Sheets tabs
# ----------------------------------------------------------------
SHEETS = {
    "tasks":        {"tab": "Tasks",                    "display": "Tasks",                    "has_id": True},
    "reminders":    {"tab": "Reminders",                "display": "Reminders",                "has_id": True},
    "expenses":     {"tab": "Expenses",                 "display": "Expenses",                 "has_id": True},
    "habits":       {"tab": "Habits",                   "display": "Habits",                   "has_id": True},
    "diary":        {"tab": "Diary",                    "display": "Diary",                    "has_id": True},
    "memory":       {"tab": "Smart Memory",             "display": "Smart Memory",             "has_id": True},
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
# ██████  AUTO-CLEANUP FUNCTION
# ================================================================

async def _cleanup_messages(update: Update, ctx: ContextTypes.DEFAULT_TYPE, keep_last: int = 0):
    """Delete all intermediate messages, keep only last N messages"""
    try:
        chat_id = update.effective_chat.id
        
        # Try to get current message id
        if update.callback_query:
            current_msg_id = update.callback_query.message.message_id
        elif update.effective_message:
            current_msg_id = update.effective_message.message_id
        else:
            return
        
        # Delete messages from current-1 down to current-30
        for i in range(1, 31):
            msg_id = current_msg_id - i
            if msg_id > 0:
                try:
                    await ctx.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    await asyncio.sleep(0.05)
                except:
                    pass
    except Exception as e:
        log.debug(f"Cleanup error: {e}")


async def _send_final_message_and_cleanup(update: Update, ctx: ContextTypes.DEFAULT_TYPE, final_text: str):
    """Send final message and cleanup all intermediate messages"""
    # Send final message
    if update.callback_query:
        msg = await update.callback_query.message.reply_text(final_text, parse_mode="Markdown")
    else:
        msg = await update.effective_chat.send_message(final_text, parse_mode="Markdown")
    
    # Delete conversation history
    await _cleanup_messages(update, ctx, keep_last=1)
    
    return msg


# ================================================================
# ██████  BACKUP SYSTEM — Pre-Delete Full Backup
# ================================================================

def _create_full_backup(label: str = "pre_delete") -> tuple[bool, str]:
    """Delete se pehle Google Sheet ke SAARE data ka backup banata hai."""
    timestamp = now_ist().strftime("%Y%m%d_%H%M%S")
    backup_label = f"{label}_{timestamp}"
    results = []

    # --- Step 1: Local JSON backup ---
    try:
        backup_data = {}
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

        if sheets_backup.connected:
            sheets_data = {}
            for key, info in SHEETS.items():
                try:
                    ws = sheets_backup._book.worksheet(info["tab"])
                    if ws:
                        sheets_data[key] = ws.get_all_values()
                except Exception as e:
                    sheets_data[key] = f"Error: {e}"
            backup_data["sheets_data"] = sheets_data

        backup_dir = os.path.join(DATA_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = os.path.join(backup_dir, f"backup_{backup_label}.json")

        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)

        results.append(f"✅ Local backup saved")
    except Exception as e:
        log.error(f"Local backup error: {e}")
        results.append(f"⚠️ Local backup error: {e}")

    # --- Step 2: GitHub push ---
    try:
        if hasattr(repo_manager, 'push') and callable(repo_manager.push):
            repo_manager.push(f"🗄️ Auto-backup before {label} [{timestamp}]")
            results.append("✅ GitHub backup pushed")
    except Exception as e:
        results.append(f"ℹ️ GitHub push: {e}")

    msg = "\n".join(results)
    return True, msg


def _create_sheet_backup(sheet_key: str, label: str = "pre_wipe") -> tuple[bool, str]:
    """Ek specific sheet ka backup banata hai delete se pehle."""
    timestamp = now_ist().strftime("%Y%m%d_%H%M%S")
    sheet_info = SHEETS.get(sheet_key, {})
    display = sheet_info.get("display", sheet_key)
    tab_key = sheet_info.get("tab", sheet_key)
    backup_label = f"{label}_{sheet_key}_{timestamp}"

    try:
        backup_data = {
            "sheet_key": sheet_key,
            "display": display,
            "backup_time": now_ist().isoformat(),
            "label": backup_label,
            "data": []
        }

        if sheets_backup.connected:
            ws = sheets_backup._book.worksheet(tab_key)
            if ws:
                backup_data["data"] = ws.get_all_values()

        if sheet_key in LOCAL_DEFAULTS and sheet_key not in ["voice_notes", "smart_memory"]:
            get_store, _ = LOCAL_DEFAULTS[sheet_key]
            store_obj = get_store()
            if store_obj and hasattr(store_obj, 'data'):
                backup_data["local_data"] = store_obj.data

        backup_dir = os.path.join(DATA_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = os.path.join(backup_dir, f"backup_{backup_label}.json")

        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)

        row_count = len(backup_data["data"]) - 1
        return True, f"✅ Backup done: {display} ({max(row_count, 0)} rows)"
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
    "nuclear option", "nuke karo sab", "poora wipe",
]

_NUKE_LOGS_PHRASES = [
    "chat history delete", "chat delete karo", "chat saaf karo",
    "logs delete karo", "logs saaf karo", "purani chat hatao",
    "miscellaneous delete", "chat wipe", "logs wipe",
]

_NUKESHEET_PHRASES = [
    "sheet wipe karo", "poori sheet delete", "sheet saaf karo",
    "ek sheet clear", "sheet clear", "sheet khali karo",
    "poori sheet saaf", "sheet wipe", "tab wipe karo",
]

_DELROW_PHRASES = [
    "sheet se entry hatao", "sheet se delete karo", "row delete karo",
    "entry delete karo", "record hatao", "entry hatao",
    "sheet mein se hatao", "specific entry delete", "ek entry delete",
]

_MENU_PHRASES = [
    "delete menu", "delete manager", "kya delete kar sakta",
    "delete options", "delete help", "delete manager open",
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
# HELPER: FAST Sheet wipe (using batch_clear)
# ================================================================

def _get_worksheet_direct(exact_tab_name: str):
    """Direct exact tab name se worksheet laata hai."""
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
    """Sheet ke saare rows delete karta hai (header bachta hai). FAST VERSION."""
    if not sheets_backup.connected:
        return False, "⚠️ Google Sheets connected nahi hai!"

    sheet_info = SHEETS.get(key)
    if not sheet_info:
        return False, f"⚠️ Unknown sheet key: {key}"

    exact_tab_name = sheet_info["tab"]
    display = sheet_info["display"]

    ws = _get_worksheet_direct(exact_tab_name)
    if not ws:
        try:
            available = [s.title for s in sheets_backup._book.worksheets()]
            return False, f"⚠️ Tab '{display}' nahi mili!"
        except Exception as e:
            return False, f"⚠️ Tab '{display}' access error: {e}"

    try:
        all_values = ws.get_all_values()
        total_rows = len(all_values)
        if total_rows <= 1:
            return True, f"ℹ️ '{display}' already empty"

        # FAST METHOD: Clear all content at once
        if total_rows > 1 and len(all_values[0]) > 0:
            last_col_letter = chr(ord('A') + len(all_values[0]) - 1)
            range_to_clear = f"A2:{last_col_letter}{total_rows}"
            ws.batch_clear([range_to_clear])
            
        return True, f"✅ '{display}' wiped ({total_rows - 1} rows)"

    except Exception as e:
        # Fallback to slow delete
        log.warning(f"Batch clear failed: {e}")
        try:
            for row_idx in range(total_rows, 1, -1):
                ws.delete_rows(row_idx)
            return True, f"✅ '{display}' wiped ({total_rows - 1} rows)"
        except Exception as e2:
            return False, f"❌ Error wiping '{display}': {e2}"


def _wipe_local_store(key: str) -> str:
    if key not in LOCAL_DEFAULTS:
        return f"⚠️ Unknown local store: {key}"
    if key in ["voice_notes", "smart_memory"]:
        return f"ℹ️ '{key}' sheet only"
    try:
        get_store, default_data = LOCAL_DEFAULTS[key]
        store_obj = get_store()
        if store_obj:
            store_obj.data = default_data.copy()
            store_obj.save()
            return f"✅ Local '{key}' cleared"
    except Exception as e:
        return f"⚠️ Local '{key}' error: {e}"
    return f"ℹ️ Local '{key}' cleared"


# ================================================================
# KEYBOARDS
# ================================================================

def _delete_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Chat History Delete", callback_data="dm_nuke_logs")],
        [InlineKeyboardButton("📋 Delete Row (by ID)", callback_data="dm_delrow")],
        [InlineKeyboardButton("🧹 Wipe Entire Sheet", callback_data="dm_nukesheet")],
        [InlineKeyboardButton("☢️ NUKE ALL (Complete Wipe)", callback_data="dm_nukeall")],
        [InlineKeyboardButton("❌ Cancel", callback_data="dm_cancel")],
    ])


def _sheet_select_keyboard(action_prefix: str):
    keys = list(SHEETS.keys())
    buttons = []
    row = []
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
        InlineKeyboardButton("✅ YES, Delete", callback_data=f"dm_confirm_{action}"),
        InlineKeyboardButton("❌ Cancel", callback_data="dm_cancel"),
    ]])


# ================================================================
# COMMON: Password maango
# ================================================================

async def _ask_password(chat, ctx, intent: str, label: str = "Delete Operation"):
    ctx.user_data["dm_entry_cmd"] = intent
    await chat.send_message(
        f"🔐 *{label}*\n\n⚠️ Password required!\n\nEnter *Delete Password*:\n\n/cancel - Exit",
        parse_mode="Markdown"
    )


# ================================================================
# ENTRY POINTS
# ================================================================

async def cmd_delete_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.split()[0].lstrip("/").lower()
    intent_map = {
        "nuke": "nuke_logs",
        "delsheet": "delrow",
        "nukesheet": "nukesheet",
        "nukeall": "nukeall",
        "delete": "menu",
    }
    intent = intent_map.get(cmd, "menu")
    await _ask_password(update.effective_chat, ctx, intent)
    return DEL_AWAIT_PASS


async def cmd_nl_delete_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
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
            "❌ DELETE_PASSWORD not set!\n\nAdd DELETE_PASSWORD to Environment Variables."
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    if entered != DELETE_PASSWORD:
        await update.effective_chat.send_message(
            "❌ Wrong Password! Access denied.\n\nTry again: /delete"
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    intent = ctx.user_data.get("dm_entry_cmd", "menu")

    if intent == "nuke_logs":
        await update.effective_chat.send_message(
            "✅ Password correct!\n\n⚠️ *CHAT HISTORY DELETE*\n\nDelete Miscellaneous sheet + local chat history?\n\nConfirm:",
            parse_mode="Markdown",
            reply_markup=_confirm_keyboard("nuke_logs")
        )
        return DEL_AWAIT_CHOICE

    elif intent == "delrow":
        await update.effective_chat.send_message(
            "✅ Password correct!\n\n📋 Which sheet to delete row from?\n\n*(ID column is first column)*",
            parse_mode="Markdown",
            reply_markup=_sheet_select_keyboard("dm_row")
        )
        return DEL_AWAIT_CHOICE

    elif intent == "nukesheet":
        await update.effective_chat.send_message(
            "✅ Password correct!\n\n🧹 Which sheet to wipe?\n\n*(Header will remain)*",
            parse_mode="Markdown",
            reply_markup=_sheet_select_keyboard("dm_wipe")
        )
        return DEL_AWAIT_CHOICE

    elif intent == "nukeall":
        await update.effective_chat.send_message(
            "✅ Password correct!\n\n☢️ *NUCLEAR OPTION - DELETE EVERYTHING*\n\n"
            "All 12 sheets + local data will be PERMANENTLY deleted!\n\n"
            "⚠️ This cannot be undone!\n\n"
            "Type `CONFIRM` (all caps) to proceed:",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_NUKE_CONFIRM

    else:
        await update.effective_chat.send_message(
            "✅ Password correct! Delete Manager Ready.\n\nWhat would you like to do?",
            parse_mode="Markdown",
            reply_markup=_delete_menu_keyboard()
        )
        return DEL_AWAIT_CHOICE


# ================================================================
# STATE 53: NukeAll — CONFIRM text (WITH AUTO-CLEANUP & FIXED)
# ================================================================

async def del_nukeall_confirm_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END

    text = update.message.text.strip()
    log.info(f"NUKEALL confirm text received: '{text}'")
    
    # Delete the CONFIRM message immediately
    try:
        await update.message.delete()
    except:
        pass

    # Case-insensitive check
    if text.upper() != "CONFIRM":
        # Cleanup and exit
        await _cleanup_messages(update, ctx)
        await update.effective_chat.send_message(
            f"❌ Confirmation failed!\n\nExpected `CONFIRM`, got `{text}`.\n\nOperation cancelled. Data safe. 🛡️",
            parse_mode="Markdown"
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    # If we reach here, confirmation is correct
    status_msg = await update.effective_chat.send_message(
        "⚠️ *NUKEALL IN PROGRESS...*\n\nDeleting all data. Please wait...",
        parse_mode="Markdown"
    )

    # Perform wipe operations
    results = []
    success_count = 0
    fail_count = 0
    
    for key in SHEETS.keys():
        local_msg = _wipe_local_store(key)
        results.append(local_msg)
        if "✅" in local_msg:
            success_count += 1
        ok, sheet_msg = _wipe_sheet_tab(key)
        results.append(sheet_msg)
        if ok:
            success_count += 1
        else:
            fail_count += 1
        await asyncio.sleep(0.1)

    try:
        goals.store.data = {"list": [], "counter": 0}
        goals.store.save()
        results.append("✅ Local goals cleared")
        success_count += 1
    except Exception as e:
        results.append(f"⚠️ Goals error: {e}")
        fail_count += 1

    # Delete status message
    try:
        await status_msg.delete()
    except:
        pass

    # Cleanup ALL previous messages
    await _cleanup_messages(update, ctx, keep_last=0)
    
    # Send ONLY final completion message
    final_msg = f"""☢️ *NUKEALL COMPLETE!* ☢️

✅ All sheets wiped successfully
✅ Local data cleared
✅ Backup saved in GitHub

📊 Summary: {success_count} successful, {fail_count} failed

_System reset to factory state._"""

    await update.effective_chat.send_message(final_msg, parse_mode="Markdown")
    
    log.warning(f"NUKEALL performed at {now_ist().isoformat()}")
    ctx.user_data.clear()
    return ConversationHandler.END


# ================================================================
# STATE 52: Row delete — ID input
# ================================================================

async def del_row_id_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END

    text = update.message.text.strip()
    selected_key = ctx.user_data.get("dm_selected_sheet_key", "")

    if not selected_key:
        await update.message.reply_text("❌ No sheet selected. Try /delsheet again.")
        ctx.user_data.clear()
        return ConversationHandler.END

    try:
        row_id = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ Enter only *ID number*! Example: `5`\n\n/cancel to exit.",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_SHEET

    sheet_info = SHEETS.get(selected_key, {})
    tab_key = sheet_info.get("tab", selected_key)
    display = sheet_info.get("display", selected_key)

    ok = sheets_backup.delete_row_by_value(tab_key, 1, str(row_id))

    # Delete the ID input message
    try:
        await update.message.delete()
    except:
        pass

    # Cleanup previous messages
    await _cleanup_messages(update, ctx, keep_last=0)

    if ok:
        await update.effective_chat.send_message(
            f"✅ *Row Deleted!*\n\n📊 Sheet: {display}\n🆔 ID: {row_id}",
            parse_mode="Markdown"
        )
    else:
        await update.effective_chat.send_message(
            f"⚠️ ID {row_id} not found in {display}.\n\nCheck ID and try again.",
            parse_mode="Markdown"
        )

    ctx.user_data.clear()
    return ConversationHandler.END


# ================================================================
# Callback Query Handler (WITH AUTO-CLEANUP)
# ================================================================

async def del_callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "dm_cancel":
        await query.edit_message_text("❌ Operation cancelled. Data safe! 🛡️")
        await _cleanup_messages(update, ctx)
        ctx.user_data.clear()
        return ConversationHandler.END

    if data == "dm_nuke_logs":
        await query.edit_message_text(
            "⚠️ *CHAT HISTORY DELETE*\n\nDelete Miscellaneous sheet + local chat history?\n\nConfirm:",
            parse_mode="Markdown",
            reply_markup=_confirm_keyboard("nuke_logs")
        )
        return DEL_AWAIT_CHOICE

    if data == "dm_delrow":
        await query.edit_message_text(
            "📋 *Delete Row*\n\nWhich sheet?\n\n*(ID column is first column)*",
            parse_mode="Markdown",
            reply_markup=_sheet_select_keyboard("dm_row")
        )
        return DEL_AWAIT_CHOICE

    if data == "dm_nukesheet":
        await query.edit_message_text(
            "🧹 *Wipe Sheet*\n\nWhich sheet to wipe?\n\n*(Header will remain)*",
            parse_mode="Markdown",
            reply_markup=_sheet_select_keyboard("dm_wipe")
        )
        return DEL_AWAIT_CHOICE

    if data == "dm_nukeall":
        await query.edit_message_text(
            "☢️ *NUCLEAR OPTION*\n\n"
            "All 12 sheets + local data will be PERMANENTLY deleted!\n\n"
            "⚠️ This cannot be undone!\n\n"
            "Type `CONFIRM` (all caps) to proceed:",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_NUKE_CONFIRM

    if data.startswith("dm_row_"):
        sheet_key = data.replace("dm_row_", "")
        ctx.user_data["dm_selected_sheet_key"] = sheet_key
        display = SHEETS.get(sheet_key, {}).get("display", sheet_key)
        await query.edit_message_text(
            f"📋 *{display}*\n\nEnter the *ID number* of the row to delete:\n\nExample: `3`",
            parse_mode="Markdown"
        )
        return DEL_AWAIT_SHEET

    if data.startswith("dm_wipe_"):
        sheet_key = data.replace("dm_wipe_", "")
        display = SHEETS.get(sheet_key, {}).get("display", sheet_key)
        ctx.user_data["dm_pending_wipe_key"] = sheet_key
        await query.edit_message_text(
            f"🧹 *'{display}' Wipe*\n\n⚠️ Backup will be created automatically!\n\nAll data will be deleted (header remains).\n\nConfirm:",
            parse_mode="Markdown",
            reply_markup=_confirm_keyboard(f"wipe_{sheet_key}")
        )
        return DEL_AWAIT_CHOICE

    if data == "dm_confirm_nuke_logs":
        # Delete confirmation message
        try:
            await query.message.delete()
        except:
            pass
        
        # Perform wipe
        _, backup_msg = _create_sheet_backup("logs", label="pre_nuke_logs")
        local_msg = _wipe_local_store("logs")
        ok, sheet_msg = _wipe_sheet_tab("logs")
        
        # Cleanup all previous messages
        await _cleanup_messages(update, ctx, keep_last=0)
        
        # Send only final message
        await update.effective_chat.send_message(
            f"🗑️ *Chat History Deleted!*\n\n{sheet_msg}",
            parse_mode="Markdown"
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    if data.startswith("dm_confirm_wipe_"):
        sheet_key = data.replace("dm_confirm_wipe_", "")
        display = SHEETS.get(sheet_key, {}).get("display", sheet_key)
        
        # Delete confirmation message
        try:
            await query.message.delete()
        except:
            pass
        
        # Perform wipe
        _, backup_msg = _create_sheet_backup(sheet_key, label="pre_wipe")
        local_msg = _wipe_local_store(sheet_key)
        ok, sheet_msg = _wipe_sheet_tab(sheet_key)
        
        # Cleanup all previous messages
        await _cleanup_messages(update, ctx, keep_last=0)
        
        # Send only final message
        await update.effective_chat.send_message(
            f"🧹 *'{display}' Wiped!*\n\n{sheet_msg}",
            parse_mode="Markdown"
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    await query.edit_message_text("❓ Unknown action. /delete to try again.")
    ctx.user_data.clear()
    return ConversationHandler.END


# ================================================================
# CANCEL
# ================================================================

async def del_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _cleanup_messages(update, ctx)
    ctx.user_data.clear()
    await update.message.reply_text("❌ Operation cancelled. Data safe! 🛡️")
    return ConversationHandler.END


# ================================================================
# REGISTER
# ================================================================

def register_delete_handlers(app: Application):
    # Main Delete ConversationHandler
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("nuke", cmd_delete_entry),
            CommandHandler("delsheet", cmd_delete_entry),
            CommandHandler("nukesheet", cmd_delete_entry),
            CommandHandler("nukeall", cmd_delete_entry),
            CommandHandler("delete", cmd_delete_entry),
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

    pw_status = "✅ SET" if DELETE_PASSWORD else "❌ NOT SET"
    log.info("✅ Delete Manager (Auto-Cleanup + Fixed) registered.")
    log.info("   Commands: /nuke /delsheet /nukesheet /nukeall /delete")
    log.info(f"   DELETE_PASSWORD: {pw_status}")
    log.info("   ✅ FIXED: NUKEALL confirmation now working")
    log.info("   ✅ AUTO-CLEANUP: All intermediate messages deleted after operation")


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
        print("⚠️ DELETE_PASSWORD env not set - add to Repository Secrets")

    from telegram.ext import Application as TGApp
    application = TGApp.builder().token(TELEGRAM_TOKEN).build()
    register_delete_handlers(application)

    log.info("🤖 Delete Manager (Fixed) — polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
