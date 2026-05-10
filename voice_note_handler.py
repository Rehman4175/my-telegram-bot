#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Memory Handler for RK Bot
- /memory commands
- Auto-detect memory intents in natural language
- Search and manage memories
"""

import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from secure_data_manager import memory, today_str, now_str, sheets_backup

log = logging.getLogger(__name__)

async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main memory command handler with subcommands"""
    args = context.args
    
    if not args:
        # Show all memories
        await _show_memories(update)
        return    
    subcmd = args[0].lower()
    
    if subcmd == "add":
        if len(args) < 2:
            await update.message.reply_text(
                "🧠 *Usage:* `/memory add Your memory text here`\n\n"
                "Example: `/memory add My birthday is on 28th December`",
                parse_mode="Markdown"
            )
            return
        text = " ".join(args[1:])
        memory.add(text)
        _log_memory_action(update.effective_user.first_name or "User", "add", text)
        await update.message.reply_text(
            f"🧠 *Memory Saved!* ✅\n\n_{text[:150]}_\n\nInshAllah yaad rakhunga! 💡",
            parse_mode="Markdown"
        )
    
    elif subcmd == "search":
        if len(args) < 2:
            await update.message.reply_text(
                "🧠 *Usage:* `/memory search keyword`\n\n"
                "Example: `/memory search birthday`",
                parse_mode="Markdown"
            )
            return
        keyword = " ".join(args[1:]).lower()
        await _search_memories(update, keyword)
    
    elif subcmd == "clear":
        # Confirm before clearing
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes, Clear All", callback_data="memory_clear_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="memory_clear_cancel")
        ]])
        await update.message.reply_text(
            "⚠️ *Warning!*\n\nAre you sure you want to delete ALL memories?\n\nThis action cannot be undone!",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    elif subcmd == "delete":
        if len(args) < 2:
            await update.message.reply_text(
                "🧠 *Usage:* `/memory delete memory_number`\n\n"
                "Use `/memory` to see memory numbers.",
                parse_mode="Markdown"
            )
            return
        try:
            idx = int(args[1]) - 1
            facts = memory.get_all_facts()
            if 0 <= idx < len(facts):
                deleted = facts.pop(idx)
                # Save back
                memory.store.data["facts"] = facts
                memory.store.save()
                _log_memory_action(update.effective_user.first_name or "User", "delete", deleted.get("f", "")[:50])
                await update.message.reply_text(
                    f"🗑️ *Memory Deleted!*\n\nWas: \"{deleted.get('f', '')[:100]}\"",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Invalid memory number!", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ Please provide a valid number!", parse_mode="Markdown")
    
    else:
        await update.message.reply_text(
            "🧠 *Memory Commands:*\n\n"
            "`/memory` — Show all memories\n"
            "`/memory add text` — Save new memory\n"
            "`/memory search word` — Search memories\n"
            "`/memory delete number` — Delete specific memory\n"
            "`/memory clear` — Delete ALL memories\n\n"
            "*Natural language:*\n"
            "• `yaad rakhna ...`\n"
            "• `memory mein save karo ...`\n"
            "• `remember that ...`",
            parse_mode="Markdown"
        )

async def _show_memories(update: Update):
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text(
            "🧠 *No memories saved yet!*\n\n"
            "Use `/memory add Your text here` to save important things.\n"
            "Or simply say: *yaad rakhna ...*",
            parse_mode="Markdown"
        )
        return
    
    lines = []
    for i, fact in enumerate(facts[-20:], 1):
        date_str = fact.get("d", "unknown")
        text = fact.get("f", str(fact))
        lines.append(f"📌 *{i}.* _{date_str}_\n   {text[:120]}")
    
    total = len(facts)
    msg = f"🧠 *Saved Memories ({total} total):*\n\n" + "\n\n".join(lines)
    if total > 20:
        msg += f"\n\n*+{total - 20} more memories.* Use /memory search to find them."
    
    await update.message.reply_text(msg[:4000], parse_mode="Markdown")

async def _search_memories(update: Update, keyword: str):
    facts = memory.get_all_facts()
    matches = []
    
    for i, fact in enumerate(facts, 1):
        text = fact.get("f", str(fact)).lower()
        if keyword in text:
            date_str = fact.get("d", "unknown")
            matches.append(f"📌 *{i}.* _{date_str}_\n   {fact.get('f', str(fact))[:120]}")
    
    if not matches:
        await update.message.reply_text(
            f"🔍 *No memories found containing:* \"{keyword}\"\n\n"
            f"Try a different word or use `/memory` to see all.",
            parse_mode="Markdown"
        )
        return
    
    msg = f"🔍 *Search Results for \"{keyword}\":*\n\n" + "\n\n".join(matches[:10])
    if len(matches) > 10:
        msg += f"\n\n*+{len(matches) - 10} more matches.*"
    
    await update.message.reply_text(msg[:4000], parse_mode="Markdown")

async def _clear_memories(update: Update):
    count = len(memory.get_all_facts())
    memory.store.data["facts"] = []
    memory.store.save()
    _log_memory_action(update.effective_user.first_name or "User", "clear_all", f"{count} memories")
    await update.message.reply_text(
        f"🗑️ *All {count} memories have been cleared!* ✅",
        parse_mode="Markdown"
    )

async def handle_memory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks for memory commands"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "memory_clear_confirm":
        count = len(memory.get_all_facts())
        memory.store.data["facts"] = []
        memory.store.save()
        _log_memory_action(query.from_user.first_name or "User", "clear_all", f"{count} memories")
        await query.edit_message_text(
            f"🗑️ *All {count} memories have been cleared!* ✅",
            parse_mode="Markdown"
        )
    elif query.data == "memory_clear_cancel":
        await query.edit_message_text(
            "✅ *Memory clear cancelled!*",
            parse_mode="Markdown"
        )

async def check_smart_memory_intent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user message is about saving memory and handle it"""
    if not update.message or not update.message.text:
        return False
    
    text = update.message.text.lower().strip()
    
    # Memory intent patterns
    patterns = [
        r'yaad rakhna?\s+(.+)$',
        r'yaad rakhoge?\s+(.+)$',
        r'memory mein save karo?\s+(.+)$',
        r'memory me save karo?\s+(.+)$',
        r'remember\s+(.+)$',
        r'note karlo?\s+(.+)$',
        r'yaad karo?\s+(.+)$',
        r'dimaag mein rakhna?\s+(.+)$',
        r'important baat\s+(.+)$',
        r'yaad rakhena?\s+(.+)$',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            memory_text = match.group(1).strip()
            if memory_text:
                memory.add(memory_text)
                _log_memory_action(update.effective_user.first_name or "User", "smart_save", memory_text[:80])
                await update.message.reply_text(
                    f"🧠 *Yaad rakha!* ✅\n\n> {memory_text[:150]}\n\nInshAllah bhoolunga nahi! 💡",
                    parse_mode="Markdown"
                )
                return True
    
    return False

def _log_memory_action(user_name: str, action: str, detail: str):
    """Log memory actions to sheets"""
    try:
        sheets_backup.log_event("memory", user_name, f"[{action}] {detail}")
        log.info(f"[Memory] {action} | {user_name} | {detail[:60]}")
    except Exception as e:
        log.warning(f"Memory log failed: {e}")

def register_memory_handlers(app):
    """Register memory command handlers"""
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CallbackQueryHandler(handle_memory_callback, pattern=r"^memory_clear_"))
    log.info("Smart memory handlers registered")
