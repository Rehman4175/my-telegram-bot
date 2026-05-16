#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REMINDER BOT — With working alarms + Google Sheets Sync
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

log = logging.getLogger(__name__)

# Global references
_sheets_backup = None
_channel_logger = None

def set_sheets_backup(sheets):
    global _sheets_backup
    _sheets_backup = sheets
    log.info("✅ Sheets backup reference set in reminder_bot")

def set_channel_logger(logger):
    global _channel_logger
    _channel_logger = logger
    log.info("✅ Channel logger reference set in reminder_bot")


class ReminderManager:
    def __init__(self, private_store_class, sheets_backup=None):
        self.PrivateStore = private_store_class
        self.sheets_backup = sheets_backup or _sheets_backup
        self.store = private_store_class("reminders", {"list": [], "counter": 0})
        
    def _next_id(self) -> int:
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        return self.store.data["counter"]
    
    def _get_now_ist(self):
        try:
            from secure_data_manager import now_ist
            return now_ist()
        except ImportError:
            return datetime.utcnow() + timedelta(hours=5, minutes=30)
    
    def _sync_to_sheets(self, reminder: Dict[str, Any], action: str = "created"):
        sheets = self.sheets_backup or _sheets_backup
        if not sheets:
            return
        
        try:
            row = [
                reminder.get("id", ""),
                reminder.get("due", reminder.get("time", "")),
                reminder.get("text", ""),
                reminder.get("repeat", "once"),
                "Active" if not reminder.get("triggered") else "Triggered",
                reminder.get("created_at", reminder.get("date", "")),
                reminder.get("chat_id", ""),
                reminder.get("last_fired", ""),
                str(reminder.get("acknowledged", False)),
                reminder.get("remarks", ""),
            ]
            
            if action == "created":
                if hasattr(sheets, '_append'):
                    sheets._append("Reminders", row)
                    log.info(f"📊 Synced reminder #{reminder['id']} to sheets")
            else:
                if hasattr(sheets, 'update_row_by_value'):
                    sheets.update_row_by_value("Reminders", 1, str(reminder["id"]), row)
        except Exception as e:
            log.error(f"Failed to sync reminder to sheets: {e}")
    
    async def _log_to_channel(self, reminder: Dict[str, Any], action: str = "created"):
        if _channel_logger:
            if action == "created":
                await _channel_logger.log(
                    f"⏰ *Reminder #{reminder['id']} Created*\n"
                    f"📌 {reminder['text']}\n"
                    f"🕐 Due: {reminder['due']}\n"
                    f"👤 Chat: `{reminder['chat_id']}`",
                    "reminder"
                )
            elif action == "triggered":
                await _channel_logger.log(
                    f"🚨 *Alarm Fired!*\n"
                    f"⏰ Reminder #{reminder['id']}\n"
                    f"🔔 {reminder['text']}\n"
                    f"👤 Chat: `{reminder['chat_id']}`",
                    "alarm"
                )
    
    def add(self, chat_id: int, text: str, due_timestamp: str, repeat: str = "once") -> Dict[str, Any]:
        now = self._get_now_ist()
        
        if len(str(due_timestamp).strip()) <= 5:
            due_time = datetime.strptime(due_timestamp, "%H:%M")
            due = datetime(now.year, now.month, now.day, due_time.hour, due_time.minute)
            if due < now:
                due += timedelta(days=1)
            due_timestamp = due.strftime("%Y-%m-%d %H:%M:%S")
        
        reminder = {
            "id": self._next_id(),
            "chat_id": chat_id,
            "text": text[:200],
            "due": due_timestamp,
            "repeat": repeat,
            "triggered": False,
            "acknowledged": False,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.store.data["list"].append(reminder)
        self.store.save()
        log.info(f"✅ Reminder #{reminder['id']} added: '{text[:50]}' at {due_timestamp}")
        
        self._sync_to_sheets(reminder, action="created")
        asyncio.create_task(self._log_to_channel(reminder, "created"))
        
        return reminder
    
    def get_all(self) -> List[Dict[str, Any]]:
        return self.store.data.get("list", [])
    
    def get_by_id(self, reminder_id: int) -> Optional[Dict[str, Any]]:
        for r in self.store.data.get("list", []):
            if r["id"] == reminder_id:
                return r
        return None
    
    def get_pending(self) -> List[Dict[str, Any]]:
        now = self._get_now_ist().strftime("%Y-%m-%d %H:%M:%S")
        return [r for r in self.store.data.get("list", []) 
                if not r.get("triggered", False) 
                and not r.get("acknowledged", False)
                and r.get("due", "") <= now]
    
    def all_active(self) -> List[Dict[str, Any]]:
        return [r for r in self.store.data.get("list", []) 
                if not r.get("triggered", False) 
                and not r.get("acknowledged", False)]
    
    def mark_triggered(self, reminder_id: int):
        for r in self.store.data.get("list", []):
            if r["id"] == reminder_id:
                r["triggered"] = True
                r["last_fired"] = self._get_now_ist().strftime("%Y-%m-%d %H:%M:%S")
                self.store.save()
                self._sync_to_sheets(r, action="update")
                asyncio.create_task(self._log_to_channel(r, "triggered"))
                break
    
    def acknowledge(self, reminder_id: int, reason: str = "User pressed OK"):
        for r in self.store.data.get("list", []):
            if r["id"] == reminder_id:
                r["acknowledged"] = True
                r["acknowledged_at"] = self._get_now_ist().strftime("%Y-%m-%d %H:%M:%S")
                r["acknowledge_reason"] = reason
                self.store.save()
                self._sync_to_sheets(r, action="update")
                log.info(f"✅ Reminder #{reminder_id} acknowledged: {reason}")
                return True
        return False
    
    def acknowledge_all_by_text(self, text: str) -> int:
        count = 0
        for r in self.store.data.get("list", []):
            if not r.get("acknowledged", False) and r.get("text", "") == text:
                r["acknowledged"] = True
                r["acknowledged_at"] = self._get_now_ist().strftime("%Y-%m-%d %H:%M:%S")
                r["acknowledge_reason"] = "OK button (batch)"
                self._sync_to_sheets(r, action="update")
                count += 1
        if count > 0:
            self.store.save()
        return count
    
    def reset_daily(self):
        for r in self.store.data.get("list", []):
            if r.get("repeat") in ("daily", "weekly"):
                r["triggered"] = False
                r["acknowledged"] = False
                self._sync_to_sheets(r, action="update")
        self.store.save()
        log.info("🔄 Daily reset")
    
    def delete(self, reminder_id: int) -> bool:
        reminders = self.store.data.get("list", [])
        for i, r in enumerate(reminders):
            if r["id"] == reminder_id:
                del reminders[i]
                self.store.save()
                sheets = self.sheets_backup or _sheets_backup
                if sheets and hasattr(sheets, 'delete_row_by_value'):
                    try:
                        sheets.delete_row_by_value("Reminders", 1, str(reminder_id))
                    except Exception as e:
                        log.error(f"Failed to delete from sheets: {e}")
                return True
        return False
    
    def clear_triggered(self):
        before = len(self.store.data.get("list", []))
        self.store.data["list"] = [r for r in self.store.data.get("list", []) 
                                   if not r.get("triggered", False)]
        after = len(self.store.data["list"])
        self.store.save()
        if before - after > 0:
            log.info(f"🧹 Cleaned {before - after} triggered reminders")


async def reminder_checker(application):
    """
    Background task that checks for due reminders every 30 seconds
    This runs in the main bot event loop
    """
    log.info("🕐 Reminder checker started - checking every 30 seconds")
    
    while True:
        try:
            from secure_data_manager import reminders
            from smart_reminder import smart_reminder
            
            # Get regular pending reminders
            pending = reminders.get_pending()
            
            # Get smart pending reminders
            smart_pending = smart_reminder.get_pending_smart()
            
            # Combine both
            all_pending = pending + smart_pending
            
            for reminder in all_pending:
                try:
                    # Format the due time nicely
                    due_dt = datetime.strptime(reminder["due"], "%Y-%m-%d %H:%M:%S")
                    due_time_display = due_dt.strftime("%I:%M %p")
                    due_date_display = due_dt.strftime("%d %b %Y")
                    
                    # Get priority prefix for message
                    priority = reminder.get("priority", "MEDIUM")
                    priority_config = {
                        "HIGH": "🔴 *URGENT!* ",
                        "MEDIUM": "🟠 *Reminder!* ",
                        "LOW": "🔵 "
                    }
                    priority_prefix = priority_config.get(priority, "⏰ ")
                    
                    # Create inline keyboard with extra options for smart reminders
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    
                    if reminder.get("repeat") in ["smart", "smart_followup"]:
                        buttons = [
                            InlineKeyboardButton("✅ Complete - Stop Reminding", callback_data=f"smart_complete_{reminder['id']}"),
                            InlineKeyboardButton("⏰ Snooze 5min", callback_data=f"smart_snooze5_{reminder['id']}"),
                            InlineKeyboardButton("🔁 Remind Again", callback_data=f"smart_again_{reminder['id']}"),
                        ]
                        keyboard = InlineKeyboardMarkup([buttons])
                        
                        # Add progress info
                        current_repeat = reminder.get("current_repeat", 0)
                        max_repeats = reminder.get("max_repeats", 6)
                        progress = f"\n\n📊 *Progress:* Attempt {current_repeat + 1}/{max_repeats}"
                    else:
                        keyboard = InlineKeyboardMarkup([[
                            InlineKeyboardButton("✅ OK — Alarm Band Karo", callback_data=f"ok_{reminder['id']}")
                        ]])
                        progress = ""
                    
                    # Send reminder message
                    await application.bot.send_message(
                        chat_id=reminder["chat_id"],
                        text=f"{priority_prefix}🚨 *ALARM!*\n{'━' * 20}\n⏰ *{due_time_display}* ({due_date_display})\n{'━' * 20}\n\n"
                             f"🔔 *{reminder['text'].upper()}*\n{progress}\n\n"
                             f"😴 Snooze: /snooze5 {reminder['id']} | /snooze10 {reminder['id']}\n"
                             f"🗑️ Delete: /delremind {reminder['id']}",
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                    
                    # Mark as triggered
                    reminders.mark_triggered(reminder["id"])
                    
                    # For smart reminders, schedule follow-up
                    if reminder.get("repeat") in ["smart", "smart_followup"]:
                        smart_reminder.process_smart_reminder(reminder)
                    
                    log.info(f"🔔 Reminder #{reminder['id']} sent to {reminder['chat_id']}")
                    
                except Exception as e:
                    log.error(f"Failed to send reminder #{reminder['id']}: {e}")
            
            # Clean old triggered reminders every hour
            if datetime.now().minute == 0:
                reminders.clear_triggered()
                
        except Exception as e:
            log.error(f"Reminder checker error: {e}")
        
        # Wait 30 seconds before next check
        await asyncio.sleep(30)
