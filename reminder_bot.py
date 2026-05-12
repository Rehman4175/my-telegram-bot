#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REMINDER BOT — With working alarms
- Stores reminders with full timestamp
- Background loop checks every 30 seconds
- Sends message when reminder time arrives
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

log = logging.getLogger(__name__)


class ReminderManager:
    def __init__(self, private_store_class):
        """
        Initialize reminder manager
        
        Args:
            private_store_class: PrivateStore class from secure_data_manager
        """
        self.PrivateStore = private_store_class
        self.store = private_store_class("reminders", {"list": [], "counter": 0})
        
    def _next_id(self) -> int:
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        return self.store.data["counter"]
    
    def _get_now_ist(self):
        """Get current time in IST - import here to avoid circular import"""
        try:
            from secure_data_manager import now_ist
            return now_ist()
        except ImportError:
            # Fallback - IST is UTC+5:30
            return datetime.utcnow() + timedelta(hours=5, minutes=30)
    
    def add(self, chat_id: int, text: str, due_timestamp: str, repeat: str = "once") -> Dict[str, Any]:
        """
        Add a reminder
        
        Args:
            chat_id: Telegram chat ID (int)
            text: Reminder message
            due_timestamp: Format "YYYY-MM-DD HH:MM:SS" or "HH:MM" (will use today's date)
            repeat: "once", "daily", "hourly"
        """
        now = self._get_now_ist()
        
        # If only time provided, assume today or tomorrow
        if len(due_timestamp.strip()) <= 5:  # "HH:MM" format
            due_time = datetime.strptime(due_timestamp, "%H:%M")
            due = datetime(now.year, now.month, now.day, due_time.hour, due_time.minute)
            
            # If time passed today, schedule for tomorrow
            if due < now:
                due += timedelta(days=1)
            due_timestamp = due.strftime("%Y-%m-%d %H:%M:%S")
        
        reminder = {
            "id": self._next_id(),
            "chat_id": chat_id,
            "text": text,
            "due": due_timestamp,
            "repeat": repeat,
            "triggered": False,
            "acknowledged": False,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.store.data["list"].append(reminder)
        self.store.save()
        log.info(f"✅ Reminder #{reminder['id']} added: '{text[:50]}' at {due_timestamp}")
        return reminder
    
    def get_all(self) -> List[Dict[str, Any]]:
        return self.store.data.get("list", [])
    
    def get_by_id(self, reminder_id: int) -> Optional[Dict[str, Any]]:
        """Get reminder by ID"""
        for r in self.store.data.get("list", []):
            if r["id"] == reminder_id:
                return r
        return None
    
    def get_pending(self) -> List[Dict[str, Any]]:
        """Get reminders that are due and not triggered/acknowledged"""
        now = self._get_now_ist().strftime("%Y-%m-%d %H:%M:%S")
        return [r for r in self.store.data.get("list", []) 
                if not r.get("triggered", False) 
                and not r.get("acknowledged", False)
                and r.get("due", "") <= now]
    
    def all_active(self) -> List[Dict[str, Any]]:
        """Get all active (not triggered/acknowledged) reminders"""
        return [r for r in self.store.data.get("list", []) 
                if not r.get("triggered", False) 
                and not r.get("acknowledged", False)]
    
    def mark_triggered(self, reminder_id: int):
        """Mark reminder as triggered (alarm sent)"""
        for r in self.store.data.get("list", []):
            if r["id"] == reminder_id:
                r["triggered"] = True
                
                # Handle repeat reminders
                if r.get("repeat") == "daily":
                    due_time = datetime.strptime(r["due"], "%Y-%m-%d %H:%M:%S")
                    new_due = due_time + timedelta(days=1)
                    self.add(
                        r["chat_id"],
                        r["text"],
                        new_due.strftime("%Y-%m-%d %H:%M:%S"),
                        "daily"
                    )
                elif r.get("repeat") == "hourly":
                    due_time = datetime.strptime(r["due"], "%Y-%m-%d %H:%M:%S")
                    new_due = due_time + timedelta(hours=1)
                    self.add(
                        r["chat_id"],
                        r["text"],
                        new_due.strftime("%Y-%m-%d %H:%M:%S"),
                        "hourly"
                    )
                
                self.store.save()
                break
    
    def acknowledge(self, reminder_id: int, reason: str = "User pressed OK"):
        """Acknowledge a reminder (stop it from firing again)"""
        for r in self.store.data.get("list", []):
            if r["id"] == reminder_id:
                r["acknowledged"] = True
                r["acknowledged_at"] = self._get_now_ist().strftime("%Y-%m-%d %H:%M:%S")
                r["acknowledge_reason"] = reason
                self.store.save()
                log.info(f"✅ Reminder #{reminder_id} acknowledged: {reason}")
                return True
        return False
    
    def acknowledge_all_by_text(self, text: str) -> int:
        """Acknowledge all reminders with matching text"""
        count = 0
        for r in self.store.data.get("list", []):
            if not r.get("acknowledged", False) and r.get("text", "") == text:
                r["acknowledged"] = True
                r["acknowledged_at"] = self._get_now_ist().strftime("%Y-%m-%d %H:%M:%S")
                r["acknowledge_reason"] = "OK button (batch)"
                count += 1
        if count > 0:
            self.store.save()
            log.info(f"✅ Acknowledged {count} reminders with text: {text}")
        return count
    
    def reset_daily(self):
        """Reset daily flags - called at midnight"""
        for r in self.store.data.get("list", []):
            r["triggered"] = False
            r["acknowledged"] = False
        self.store.save()
        log.info("🔄 Daily reset - all reminders reactivated")
    
    def delete(self, reminder_id: int) -> bool:
        """Delete a reminder"""
        reminders = self.store.data.get("list", [])
        for i, r in enumerate(reminders):
            if r["id"] == reminder_id:
                del reminders[i]
                self.store.save()
                log.info(f"🗑️ Reminder #{reminder_id} deleted")
                return True
        return False
    
    def clear_triggered(self):
        """Remove all triggered reminders (cleanup)"""
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
            # Import here to avoid circular import issues
            from secure_data_manager import reminders
            
            # Get all pending reminders
            pending = reminders.get_pending()
            
            for reminder in pending:
                try:
                    # Format the due time nicely
                    due_dt = datetime.strptime(reminder["due"], "%Y-%m-%d %H:%M:%S")
                    due_time_display = due_dt.strftime("%I:%M %p")
                    due_date_display = due_dt.strftime("%d %b %Y")
                    
                    # Create inline keyboard for OK button
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ OK — Alarm Band Karo", callback_data=f"ok_{reminder['id']}")
                    ]])
                    
                    # Send reminder message
                    await application.bot.send_message(
                        chat_id=reminder["chat_id"],
                        text=f"🚨 *ALARM!*\n{'━' * 20}\n⏰ *{due_time_display}* ({due_date_display})\n{'━' * 20}\n\n"
                             f"🔔 *{reminder['text'].upper()}*\n\n"
                             f"😴 Snooze: /snooze5 {reminder['id']} | /snooze10 {reminder['id']}\n"
                             f"🗑️ Delete: /delremind {reminder['id']}",
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                    
                    # Mark as triggered
                    reminders.mark_triggered(reminder["id"])
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
