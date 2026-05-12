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
from secure_data_manager import PrivateStore, now_ist

log = logging.getLogger(__name__)

class ReminderManager:
    def __init__(self):
        self.store = PrivateStore("reminders", {"list": [], "counter": 0})
        self._running_task = None
        
    def _next_id(self) -> int:
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        return self.store.data["counter"]
    
    def add(self, chat_id: int, text: str, due_timestamp: str, repeat: str = "once") -> Dict[str, Any]:
        """
        Add a reminder
        
        Args:
            chat_id: Telegram chat ID (int)
            text: Reminder message
            due_timestamp: Format "YYYY-MM-DD HH:MM:SS" or "HH:MM" (will use today's date)
            repeat: "once", "daily", "hourly"
        """
        # If only time provided, assume today
        if len(due_timestamp.strip()) <= 5:  # "HH:MM" format
            now = now_ist()
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
            "created_at": now_ist().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.store.data["list"].append(reminder)
        self.store.save()
        log.info(f"✅ Reminder #{reminder['id']} added: '{text[:50]}' at {due_timestamp}")
        return reminder
    
    def get_all(self) -> List[Dict[str, Any]]:
        return self.store.data.get("list", [])
    
    def get_pending(self) -> List[Dict[str, Any]]:
        """Get reminders that are due and not triggered"""
        now = now_ist().strftime("%Y-%m-%d %H:%M:%S")
        return [r for r in self.store.data.get("list", []) 
                if not r.get("triggered", False) and r.get("due", "") <= now]
    
    def mark_triggered(self, reminder_id: int):
        """Mark reminder as triggered"""
        for r in self.store.data.get("list", []):
            if r["id"] == reminder_id:
                r["triggered"] = True
                
                # Handle repeat reminders
                if r.get("repeat") == "daily":
                    # Create new reminder for tomorrow
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
    
    def delete(self, reminder_id: int) -> bool:
        """Delete a reminder"""
        reminders = self.store.data.get("list", [])
        for i, r in enumerate(reminders):
            if r["id"] == reminder_id:
                del reminders[i]
                self.store.save()
                return True
        return False
    
    def clear_triggered(self):
        """Remove all triggered reminders (cleanup)"""
        before = len(self.store.data.get("list", []))
        self.store.data["list"] = [r for r in self.store.data.get("list", []) 
                                   if not r.get("triggered", False)]
        after = len(self.store.data["list"])
        self.store.save()
        log.info(f"🧹 Cleaned {before - after} triggered reminders")


async def reminder_checker(application):
    """
    Background task that checks for due reminders every 30 seconds
    This runs in the main bot event loop
    """
    # Import here to avoid circular imports
    from secure_data_manager import reminders
    
    log.info("🕐 Reminder checker started - checking every 30 seconds")
    
    while True:
        try:
            # Get all pending reminders
            pending = reminders.get_pending()
            
            for reminder in pending:
                try:
                    # Send the reminder message
                    await application.bot.send_message(
                        chat_id=reminder["chat_id"],
                        text=f"⏰ *REMINDER!*\n\n{reminder['text']}\n\n_Set at: {reminder.get('created_at', 'unknown')}_",
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


# Global instance
reminders = ReminderManager()
