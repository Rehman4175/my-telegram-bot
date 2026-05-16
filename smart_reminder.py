#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMART REMINDER INTELLIGENCE - Rk Bot
Features:
- Follow-up reminders (agar aapne OK nahi dabaya to dubara remind karega)
- Repeat until completed (jab tak complete nahi hota, repeat hota rahega)
- Priority-based reminders (HIGH/MEDIUM/LOW)
- Smart escalation (HIGH priority baar baar remind karega)
"""

import logging
from datetime import datetime, timedelta
from secure_data_manager import reminders, now_ist

log = logging.getLogger(__name__)

# Priority levels and their repeat intervals (in minutes)
PRIORITY_CONFIG = {
    "HIGH": {
        "repeat_interval": 5,      # Har 5 minute mein remind karega
        "max_repeats": 12,          # Maximum 12 baar (1 hour)
        "escalation": True,          # Frequency badhayega agar ignore kiya
        "message_prefix": "🔴 *URGENT!* "
    },
    "MEDIUM": {
        "repeat_interval": 15,      # Har 15 minute mein remind karega
        "max_repeats": 8,           # Maximum 8 baar (2 hours)
        "escalation": False,
        "message_prefix": "🟠 *Reminder!* "
    },
    "LOW": {
        "repeat_interval": 30,      # Har 30 minute mein remind karega
        "max_repeats": 4,           # Maximum 4 baar (2 hours)
        "escalation": False,
        "message_prefix": "🔵 "
    },
    "DEFAULT": {
        "repeat_interval": 10,
        "max_repeats": 6,
        "escalation": False,
        "message_prefix": "⏰ "
    }
}

class SmartReminder:
    def __init__(self):
        self.store = reminders  # Use existing reminder store
        
    def add_smart_reminder(self, chat_id: int, text: str, due_timestamp: str, 
                           priority: str = "MEDIUM", repeat_until_done: bool = False,
                           followup_count: int = 3, smart_escalation: bool = True) -> dict:
        """
        Add a smart reminder with advanced features
        
        Args:
            chat_id: Telegram chat ID
            text: Reminder message
            due_timestamp: When to first trigger (YYYY-MM-DD HH:MM:SS)
            priority: HIGH, MEDIUM, LOW
            repeat_until_done: If True, keeps repeating until acknowledged
            followup_count: Number of follow-up reminders if not acknowledged
            smart_escalation: If True, increases frequency for ignored HIGH priority reminders
        """
        priority = priority.upper()
        if priority not in PRIORITY_CONFIG:
            priority = "MEDIUM"
        
        config = PRIORITY_CONFIG.get(priority, PRIORITY_CONFIG["DEFAULT"])
        
        reminder = {
            "id": self._get_next_id(),
            "chat_id": chat_id,
            "text": text,
            "due": due_timestamp,
            "repeat": "smart",
            "priority": priority,
            "repeat_until_done": repeat_until_done,
            "followup_count": followup_count,
            "smart_escalation": smart_escalation,
            "repeat_interval": config["repeat_interval"],
            "max_repeats": config["max_repeats"],
            "current_repeat": 0,
            "triggered": False,
            "acknowledged": False,
            "created_at": now_ist().strftime("%Y-%m-%d %H:%M:%S"),
            "last_fired": "",
            "escalation_level": 0
        }
        
        self.store.store.data["list"].append(reminder)
        self.store.store.save()
        self._sync_to_sheets(reminder)
        
        log.info(f"✅ Smart reminder #{reminder['id']} added with priority {priority}")
        return reminder
    
    def _get_next_id(self):
        self.store.store.data["counter"] = self.store.store.data.get("counter", 0) + 1
        return self.store.store.data["counter"]
    
    def _sync_to_sheets(self, reminder):
        try:
            from secure_data_manager import sheets_backup
            row = [
                reminder.get("id", ""),
                reminder.get("due", ""),
                reminder.get("text", ""),
                f"Smart-{reminder.get('priority', 'MEDIUM')}",
                "Active",
                reminder.get("created_at", ""),
                reminder.get("chat_id", ""),
                reminder.get("last_fired", ""),
                str(reminder.get("acknowledged", False)),
                f"Repeat:{reminder.get('current_repeat',0)}/{reminder.get('max_repeats',0)}"
            ]
            sheets_backup._append("Reminders", row)
        except Exception as e:
            log.debug(f"Sheet sync error: {e}")
    
    def process_smart_reminder(self, reminder):
        """Process a triggered smart reminder - reschedule if needed"""
        if reminder.get("acknowledged", False):
            return False
        
        priority = reminder.get("priority", "MEDIUM")
        config = PRIORITY_CONFIG.get(priority, PRIORITY_CONFIG["DEFAULT"])
        
        current_repeat = reminder.get("current_repeat", 0)
        max_repeats = reminder.get("max_repeats", config["max_repeats"])
        repeat_until_done = reminder.get("repeat_until_done", False)
        
        # Calculate next reminder time
        base_interval = reminder.get("repeat_interval", config["repeat_interval"])
        
        # Smart escalation: agar HIGH priority hai aur ignore ho raha hai
        if reminder.get("smart_escalation", False) and priority == "HIGH":
            escalation_level = reminder.get("escalation_level", 0)
            if current_repeat >= 2:  # 2 baar ignore kar diya
                new_interval = max(2, base_interval // 2)  # Frequency double
                reminder["repeat_interval"] = new_interval
                reminder["escalation_level"] = escalation_level + 1
                log.info(f"⚠️ Escalating reminder #{reminder['id']} to {new_interval}min interval")
        
        # Check if we should stop repeating
        if not repeat_until_done and current_repeat >= max_repeats:
            log.info(f"📌 Smart reminder #{reminder['id']} reached max repeats ({max_repeats})")
            return False
        
        # Schedule next reminder
        next_interval = reminder.get("repeat_interval", config["repeat_interval"])
        next_due = now_ist() + timedelta(minutes=next_interval)
        next_timestamp = next_due.strftime("%Y-%m-%d %H:%M:%S")
        
        # Create follow-up reminder
        followup_text = f"🔁 {reminder['text']}"
        if current_repeat >= 1:
            followup_text = f"⚠️ Reminder #{reminder['id']} (Attempt {current_repeat + 1}/{max_repeats}): {reminder['text']}"
        
        new_reminder = {
            "id": self._get_next_id(),
            "chat_id": reminder["chat_id"],
            "text": followup_text,
            "due": next_timestamp,
            "repeat": "smart_followup",
            "priority": priority,
            "repeat_until_done": repeat_until_done,
            "followup_count": reminder.get("followup_count", 3),
            "smart_escalation": reminder.get("smart_escalation", False),
            "repeat_interval": reminder.get("repeat_interval", config["repeat_interval"]),
            "max_repeats": max_repeats,
            "current_repeat": current_repeat + 1,
            "triggered": False,
            "acknowledged": False,
            "created_at": now_ist().strftime("%Y-%m-%d %H:%M:%S"),
            "parent_id": reminder["id"],
            "escalation_level": reminder.get("escalation_level", 0)
        }
        
        self.store.store.data["list"].append(new_reminder)
        self.store.store.save()
        self._sync_to_sheets(new_reminder)
        
        log.info(f"🔄 Follow-up reminder #{new_reminder['id']} scheduled for {next_timestamp}")
        return True
    
    def get_smart_reminders(self, chat_id: int = None):
        """Get all smart reminders"""
        all_rem = self.store.get_all()
        if chat_id:
            return [r for r in all_rem if r.get("repeat") in ["smart", "smart_followup"] and r.get("chat_id") == chat_id]
        return [r for r in all_rem if r.get("repeat") in ["smart", "smart_followup"]]
    
    def get_pending_smart(self):
        """Get pending smart reminders that are due"""
        now = now_ist().strftime("%Y-%m-%d %H:%M:%S")
        all_rem = self.store.get_all()
        return [r for r in all_rem 
                if r.get("repeat") in ["smart", "smart_followup"]
                and not r.get("triggered", False)
                and not r.get("acknowledged", False)
                and r.get("due", "") <= now]
    
    def acknowledge_smart(self, reminder_id: int, reason: str = "Completed"):
        """Acknowledge and stop all follow-ups for a smart reminder"""
        # Find the original reminder and all its follow-ups
        parent_id = reminder_id
        original = self.store.get_by_id(reminder_id)
        if original and original.get("parent_id"):
            parent_id = original.get("parent_id")
        
        # Acknowledge all reminders in this chain
        count = 0
        for r in self.store.store.data.get("list", []):
            if r.get("id") == parent_id or r.get("parent_id") == parent_id or r.get("id") == reminder_id:
                if not r.get("acknowledged", False):
                    r["acknowledged"] = True
                    r["acknowledged_at"] = now_ist().strftime("%Y-%m-%d %H:%M:%S")
                    r["acknowledge_reason"] = reason
                    count += 1
        
        if count > 0:
            self.store.store.save()
            log.info(f"✅ Acknowledged {count} smart reminders (parent: {parent_id})")
        
        return count

# Create global instance
smart_reminder = SmartReminder()
