#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COMMAND PARSER v2.0 — RK BOT with DATE PARSING
"""

import re
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════
# FIRST WORD MAPS
# ══════════════════════════════════════════════════════

FIRST_WORD_MAP = {
    "diary": "diary", "daiari": "diary", "dairy": "diary", "dairi": "diary",
    "note": "diary", "notes": "diary", "likh": "diary", "likho": "diary",
    "likhna": "diary", "likh lo": "diary", "likh do": "diary", "save": "diary",
    "jot": "diary", "record": "diary",
    
    "task": "task", "tasks": "task", "todo": "task", "kaam": "task",
    "kaaam": "task", "kam": "task", "karni": "task", "krni": "task",
    "karna": "task", "krna": "task", "work": "task", "mujhe": "task",
    
    "remind": "remind", "reminder": "remind", "remindme": "remind",
    "alarm": "remind", "alert": "remind", "yaad": "remind", "yad": "remind",
    "bata": "remind", "batao": "remind", "bata do": "remind", "notify": "remind",
    
    "habit": "habit", "habits": "habit", "habbit": "habit", "routine": "habit",
    
    "kharcha": "expense", "karcha": "expense", "kharch": "expense",
    "karch": "expense", "paisa": "expense", "paise": "expense",
    "rs": "expense", "rs.": "expense", "rupees": "expense", "spent": "expense",
    "laga": "expense", "lagaya": "expense", "expense": "expense",
    
    "paani": "water", "pani": "water", "water": "water", "drink": "water",
    "piya": "water", "pi": "water",
    
    "memory": "memory", "remember": "memory", "store": "memory",
    
    "birthday": "calendar", "bday": "calendar", "event": "calendar",
    "schedule": "calendar", "cal": "calendar", "calendar": "calendar",
    "meeting": "calendar", "appointment": "calendar",
    
    "bill": "bill", "bills": "bill", "subscription": "bill", "emi": "bill",
    
    "done": "complete", "complete": "complete", "finish": "complete",
    "ho gaya": "complete", "hogaya": "complete", "kar liya": "complete",
    
    "dikhao": "show", "dekho": "show", "show": "show", "list": "show",
    "batao": "show", "status": "show",
}

# ══════════════════════════════════════════════════════
# PHRASE PATTERNS
# ══════════════════════════════════════════════════════

PHRASE_PATTERNS = {
    "diary": [
        "diary mein likho", "diary me likho", "diary mein likh", "diary me likh",
        "diary mein add", "diary me add", "diary mein daalo", "diary me daalo",
        "diary mein save", "diary me save", "dairy mein likho", "dairy me likho",
        "note kar lo", "note karo", "likh lo", "save kar lo",
    ],
    "task": [
        "task add", "task lagao", "task likh", "naya task", "new task",
        "kaam add", "kaam karna hai", "kaam krna hai", "todo add",
        "mujhe karna hai", "ek kaam hai",
    ],
    "remind": [
        "yaad dilana", "yaad dila do", "yaad dila", "remind me", "remind karo",
        "reminder set", "reminder lagao", "alarm set", "alarm lagao",
        "bata dena", "mat bhoolo", "reminder laga do",
    ],
    "habit": [
        "habit add", "habit lagao", "habit bana", "new habit", "naya habit",
        "habit done", "habit complete", "habit ho gayi", "habit kar li",
        "gym ho gaya", "exercise ho gayi", "namaz ho gayi",
    ],
    "expense": [
        "kharcha hua", "kharcha kiya", "paisa gaya", "paisa laga",
        "rupees lage", "rs laga", "spent on", "bill pay kiya",
    ],
    "water": [
        "paani piya", "pani piya", "paani pi liya", "water piya",
        "paani add", "water log", "glass piya",
    ],
    "memory": [
        "memory mein save", "memory me save", "yaad rakhna", "remember karo",
        "memory mein rakh", "note down",
    ],
    "calendar": [
        "birthday hai", "birthday add", "ka birthday", "ki birthday",
        "event add", "event hai", "calendar mein add", "cal mein add",
        "meeting add", "appointment add",
    ],
    "bill": [
        "bill add", "bill lagao", "subscription add", "emi add",
        "netflix add", "bill dena hai",
    ],
    "show": [
        "kharcha batao", "task dikhao", "reminder list", "habit dekho",
        "diary dikhao", "saari diary", "memory dikhao", "events dikhao",
        "bills dikhao", "aaj ka kharcha", "paani kitna",
    ],
}

# ══════════════════════════════════════════════════════
# DATE & TIME PARSERS
# ══════════════════════════════════════════════════════

MONTH_MAP = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2,
    'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
    'may': 5, 'mei': 5, 'jun': 6, 'june': 6,
    'jul': 7, 'july': 7, 'aug': 8, 'august': 8,
    'sep': 9, 'september': 9, 'oct': 10, 'october': 10,
    'nov': 11, 'november': 11, 'dec': 12, 'december': 12
}

def _get_now():
    from datetime import datetime, timezone
    IST = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(IST)

def parse_specific_date(text: str, now_ist_func=None):
    """Parse specific dates like '6 june', '15 august 2025'"""
    if now_ist_func:
        now = now_ist_func()
    else:
        now = _get_now()
    
    today = now.date()
    lower = text.lower()
    
    # Pattern: "6 june" or "6 june 2025"
    m = re.search(r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(?:(\d{4}))?', lower)
    if m:
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2)[:3], 0)
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            from datetime import date
            d = date(year, month, day)
            if d < today:
                d = date(year + 1, month, day)
            return d
        except:
            pass
    
    # Pattern: "june 6"
    m = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:\s+(\d{4}))?', lower)
    if m:
        month = MONTH_MAP.get(m.group(1)[:3], 0)
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            from datetime import date
            d = date(year, month, day)
            if d < today:
                d = date(year + 1, month, day)
            return d
        except:
            pass
    
    # Pattern: "DD-MM-YYYY" or "DD/MM/YYYY"
    m = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', lower)
    if m:
        try:
            from datetime import date
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except:
            pass
    
    # Pattern: "YYYY-MM-DD"
    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', lower)
    if m:
        try:
            from datetime import date
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except:
            pass
    
    return None

def parse_time_from_text(text: str):
    """Parse time like '9 baje', '3 pm', '15:30'"""
    lower = text.lower()
    
    m = re.search(r'(\d{1,2}):(\d{2})', lower)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    
    m = re.search(r'(\d{1,2})\s*(?:baje|bajay|am|pm|subah|shaam|raat|morning|evening|night)', lower)
    if m:
        hour = int(m.group(1))
        if any(x in lower for x in ['pm', 'shaam', 'raat', 'evening', 'night']):
            if hour != 12:
                hour += 12
        elif any(x in lower for x in ['am', 'subah', 'morning']):
            if hour == 12:
                hour = 0
        return f"{hour:02d}:00"
    
    return None

def parse_relative_time(text: str, now_ist_func=None):
    """Parse relative time like '30 min baad', '2 ghante baad'"""
    if now_ist_func:
        now = now_ist_func()
    else:
        now = _get_now()
    
    lower = text.lower()
    
    m = re.search(r'(\d+)\s*(?:minute|minutes|min|mins|m)\s*(?:baad|mein|main|after)?', lower)
    if m:
        return now + timedelta(minutes=int(m.group(1)))
    
    m = re.search(r'(\d+)\s*(?:hour|hours|hr|hrs|ghanta|ghante)\s*(?:baad|mein|main|after)?', lower)
    if m:
        return now + timedelta(hours=int(m.group(1)))
    
    m = re.search(r'(\d+)\s*(?:day|days|din|dino)\s*(?:baad|mein|main|after)?', lower)
    if m:
        return now + timedelta(days=int(m.group(1)))
    
    if 'kal' in lower or 'tomorrow' in lower or 'kl' in lower:
        return now + timedelta(days=1)
    
    if 'parso' in lower:
        return now + timedelta(days=2)
    
    return None

def parse_amount(text: str):
    """Extract amount from text"""
    m = re.search(r'(?:rs\.?\s*|rupees?\s*|₹\s*)?(\d+(?:\.\d+)?)\s*(?:rs\.?|rupees?|₹)?', text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None

def parse_water_amount(text: str):
    """Extract water amount in ML"""
    lower = text.lower()
    m = re.search(r'(\d+)\s*ml', lower)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)\s*(?:glass|glasses|gilas)', lower)
    if m:
        return int(m.group(1)) * 250
    m = re.search(r'(\d+)\s*(?:bottle|bottles)', lower)
    if m:
        return int(m.group(1)) * 500
    if any(x in lower for x in ['piya', 'pi liya', 'pi']):
        return 250
    return 250

def remove_date_words(text: str) -> str:
    """Remove date/time related words"""
    date_words = [
        'january', 'february', 'march', 'april', 'may', 'june', 'july',
        'august', 'september', 'october', 'november', 'december',
        'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
        'ko', 'mein', 'me', 'pe', 'baje', 'bajay', 'am', 'pm',
        'subah', 'shaam', 'raat', 'dopahar', 'morning', 'evening', 'night',
        'kal', 'aaj', 'parso', 'tomorrow', 'today'
    ]
    result = text
    for dw in date_words:
        result = re.sub(r'\b' + re.escape(dw) + r'\b', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', '', result)
    result = re.sub(r'\d{4}-\d{1,2}-\d{1,2}', '', result)
    result = re.sub(r'\d{1,2}:\d{2}', '', result)
    result = re.sub(r'\d+', '', result)
    return result.strip()

def remove_phrase(text: str, phrase: str) -> str:
    """Remove phrase from text"""
    result = text.replace(phrase, "", 1).strip()
    clean_words = ["karo", "kro", "kr", "do", "kar", "de", "dena", "hai", "mein", "me", "please", "plz"]
    for cw in clean_words:
        result = re.sub(r'\b' + re.escape(cw) + r'\b', '', result, flags=re.IGNORECASE)
    return " ".join(result.split()).strip()

# ══════════════════════════════════════════════════════
# MAIN PARSER FUNCTION
# ══════════════════════════════════════════════════════

def parse_command(user_msg: str, now_ist_func=None):
    """Main parser - detect action from user message"""
    
    if not user_msg or not user_msg.strip():
        return ("unknown", {})
    
    original = user_msg.strip()
    lower = original.lower().strip()
    
    # Step 1: Phrase pattern check
    for action, phrases in PHRASE_PATTERNS.items():
        for phrase in phrases:
            if lower.startswith(phrase) or phrase in lower[:50]:
                remaining = remove_phrase(lower, phrase)
                return build_result(action, remaining, original, now_ist_func)
    
    # Step 2: First word check
    words = lower.split()
    if words:
        first = words[0]
        if first in FIRST_WORD_MAP:
            action = FIRST_WORD_MAP[first]
            remaining = " ".join(words[1:])
            return build_result(action, remaining, original, now_ist_func)
        
        if len(words) >= 2:
            two_words = words[0] + " " + words[1]
            if two_words in FIRST_WORD_MAP:
                action = FIRST_WORD_MAP[two_words]
                remaining = " ".join(words[2:])
                return build_result(action, remaining, original, now_ist_func)
    
    # Step 3: Amount only (expense shorthand)
    m = re.match(r'^(\d+(?:\.\d+)?)\s+(.+)$', lower)
    if m:
        amount = float(m.group(1))
        desc = m.group(2).strip()
        action_words = list(FIRST_WORD_MAP.keys())
        if not any(aw in desc for aw in action_words):
            return ("expense", {"amount": amount, "desc": desc.title(), "raw": original})
    
    # Step 4: Quick reminder (r 10m)
    m = re.match(r'^r\s+(\d+(?:m|min|h|hr)?)\s+(.+)$', lower)
    if m:
        time_arg = m.group(1)
        text = m.group(2).strip()
        now = now_ist_func() if now_ist_func else _get_now()
        if time_arg.endswith(('m', 'min')):
            mins = int(re.sub(r'[^0-9]', '', time_arg))
            due = now + timedelta(minutes=mins)
        elif time_arg.endswith(('h', 'hr')):
            hrs = int(re.sub(r'[^0-9]', '', time_arg))
            due = now + timedelta(hours=hrs)
        else:
            due = now + timedelta(minutes=int(time_arg))
        return ("remind", {"text": text.title(), "due": due.strftime("%Y-%m-%d %H:%M:%S"), "raw": original})
    
    # Step 5: Reminder with specific date
    reminder_keywords = ['remind', 'reminder', 'yaad dilana', 'yaad dila', 'bata dena', 'alarm', 'reminder lagao', 'reminder laga']
    
    if any(kw in lower for kw in reminder_keywords):
        due_date = parse_specific_date(original, now_ist_func)
        if due_date:
            time_str = parse_time_from_text(original)
            if time_str:
                hour, minute = map(int, time_str.split(':'))
                due_dt = due_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            else:
                due_dt = due_date.replace(hour=9, minute=0, second=0, microsecond=0)
            
            text = original
            for w in reminder_keywords + ['ko', 'mein', 'me', 'pe', 'baje', 'bajay']:
                text = re.sub(r'\b' + re.escape(w) + r'\b', '', text, flags=re.IGNORECASE)
            text = remove_date_words(text)
            text = " ".join(text.split()).strip()
            
            return ("remind", {"text": text.title() or "Reminder", "due": due_dt.strftime("%Y-%m-%d %H:%M:%S"), "raw": original})
        
        # Try relative time
        relative_dt = parse_relative_time(original, now_ist_func)
        if relative_dt:
            text = original
            for w in reminder_keywords:
                text = re.sub(r'\b' + re.escape(w) + r'\b', '', text, flags=re.IGNORECASE)
            text = re.sub(r'\d+\s*(?:min|minute|hour|hr|din|day|ghanta)\s*(?:baad|mein)?', '', text)
            text = " ".join(text.split()).strip()
            return ("remind", {"text": text.title() or "Reminder", "due": relative_dt.strftime("%Y-%m-%d %H:%M:%S"), "raw": original})
    
    # Step 6: Default
    return ("unknown", {"raw": original})

def build_result(action: str, remaining: str, original: str, now_ist_func=None):
    """Build result dictionary based on action"""
    
    if action == "diary":
        text = remaining.strip() or original
        return ("diary", {"text": text, "raw": original})
    
    elif action == "task":
        title = remaining.strip() or original
        for kw in ["add", "karo", "kro", "lagao", "likh", "naya", "new", "karna"]:
            title = re.sub(r'\b' + re.escape(kw) + r'\b', '', title, flags=re.IGNORECASE)
        title = " ".join(title.split()).strip()
        return ("task", {"title": title[:100] or "Task", "raw": original})
    
    elif action == "remind":
        due_dt = parse_relative_time(original, now_ist_func)
        if not due_dt:
            due_dt = parse_specific_date(original, now_ist_func)
            if due_dt:
                due_dt = due_dt.replace(hour=9, minute=0, second=0, microsecond=0)
            else:
                due_dt = (now_ist_func() if now_ist_func else _get_now()) + timedelta(minutes=5)
        
        text = remaining or original
        for w in ["remind", "reminder", "alarm", "yaad", "dilana", "bata", "do", "dena"]:
            text = re.sub(r'\b' + re.escape(w) + r'\b', '', text, flags=re.IGNORECASE)
        text = remove_date_words(text)
        text = " ".join(text.split()).strip()
        
        return ("remind", {"text": text.title() or "Reminder", "due": due_dt.strftime("%Y-%m-%d %H:%M:%S"), "raw": original})
    
    elif action == "habit":
        name = remaining.strip()
        for kw in ["add", "lagao", "bana", "new", "naya", "start"]:
            name = re.sub(r'\b' + re.escape(kw) + r'\b', '', name, flags=re.IGNORECASE)
        name = " ".join(name.split()).strip()
        
        done_words = ["done", "complete", "ho gayi", "ho gaya", "kar li", "kar liya"]
        is_done = any(dw in original.lower() for dw in done_words)
        
        if is_done:
            habit_name = name
            if not habit_name or len(habit_name) < 2:
                habit_name = original.lower()
                for dr in done_words:
                    habit_name = habit_name.replace(dr, "").strip()
            return ("habit_done", {"keyword": habit_name or original, "raw": original})
        else:
            return ("habit", {"name": name[:80] or "Habit", "raw": original})
    
    elif action == "expense":
        amount = parse_amount(original)
        desc = remaining or original
        for kw in ["kharcha", "paisa", "rs", "rupees", "spent", "laga", "expense"]:
            desc = re.sub(r'\b' + re.escape(kw) + r'\b', '', desc, flags=re.IGNORECASE)
        if amount:
            desc = desc.replace(str(int(amount)), "").replace(str(amount), "")
        desc = " ".join(desc.split()).strip()
        return ("expense", {"amount": amount or 0, "desc": desc.title() or "Expense", "raw": original})
    
    elif action == "water":
        ml = parse_water_amount(original)
        return ("water", {"ml": ml, "raw": original})
    
    elif action == "memory":
        text = remaining.strip() or original
        for kw in ["memory", "save", "karo", "rakh", "yaad", "remember"]:
            text = re.sub(r'\b' + re.escape(kw) + r'\b', '', text, flags=re.IGNORECASE)
        text = " ".join(text.split()).strip()
        return ("memory", {"text": text or original, "raw": original})
    
    elif action == "calendar":
        date_found = parse_specific_date(original, now_ist_func)
        if date_found:
            date_str = date_found.strftime("%Y-%m-%d")
        else:
            date_str = (now_ist_func() if now_ist_func else _get_now()).strftime("%Y-%m-%d")
        
        title = remaining or original
        is_bday = any(w in original.lower() for w in ["birthday", "bday", "janamdin"])
        return ("calendar", {"title": title[:100] or "Event", "date": date_str, "type": "birthday" if is_bday else "event", "raw": original})
    
    elif action == "bill":
        amount = parse_amount(original)
        name = remaining or original
        for kw in ["bill", "subscription", "emi", "add", "new"]:
            name = re.sub(r'\b' + re.escape(kw) + r'\b', '', name, flags=re.IGNORECASE)
        if amount:
            name = name.replace(str(int(amount)), "").replace(str(amount), "")
        name = " ".join(name.split()).strip()
        
        due_day = 0
        m = re.search(r'(\d{1,2})\s*(?:tarikh|taarikh|date|th|st|nd|rd)', original.lower())
        if m:
            candidate = int(m.group(1))
            if 1 <= candidate <= 31:
                due_day = candidate
        return ("bill", {"name": name or "Bill", "amount": amount or 0, "due_day": due_day, "raw": original})
    
    elif action == "complete":
        m = re.search(r'#?(\d+)', original)
        task_id = int(m.group(1)) if m else None
        return ("complete", {"id": task_id, "hint": original, "raw": original})
    
    elif action == "show":
        lower_orig = original.lower()
        if any(x in lower_orig for x in ["task", "kaam", "todo"]):
            return ("show_tasks", {"raw": original})
        elif any(x in lower_orig for x in ["reminder", "alarm", "yaad"]):
            return ("show_reminders", {"raw": original})
        elif any(x in lower_orig for x in ["habit", "routine"]):
            return ("show_habits", {"raw": original})
        elif any(x in lower_orig for x in ["purani diary", "saari diary", "all diary"]):
            return ("show_all_diary", {"raw": original})
        elif any(x in lower_orig for x in ["diary", "dairy"]):
            return ("show_diary", {"raw": original})
        elif any(x in lower_orig for x in ["memory", "yaad hai"]):
            return ("show_memory", {"raw": original})
        elif any(x in lower_orig for x in ["calendar", "event", "birthday"]):
            return ("show_calendar", {"raw": original})
        elif any(x in lower_orig for x in ["bill", "subscription"]):
            return ("show_bills", {"raw": original})
        elif any(x in lower_orig for x in ["kharcha", "expense"]):
            return ("show_expense", {"raw": original})
        elif any(x in lower_orig for x in ["paani", "water"]):
            return ("show_water", {"raw": original})
        else:
            return ("show_tasks", {"raw": original})
    
    return ("unknown", {"raw": original})

# ══════════════════════════════════════════════════════
# MAIN FUNCTION FOR BOT INTEGRATION
# ══════════════════════════════════════════════════════

def get_action(user_msg: str, now_ist_func=None):
    """Main function to call from bot.py"""
    return parse_command(user_msg, now_ist_func)


if __name__ == "__main__":
    test_msgs = [
        "reminder lagao mujhe 6 june ko gao ka bijli bill bharna hai",
        "yaad dilana 15 august 2025 ko party hai",
        "kal 3 baje doctor appointment",
        "6 june 9 am ko bijli bill",
        "30 min baad chai yaad dilana",
        "task kal market jaana",
        "kharcha 200 chai",
    ]
    print("Testing command parser...")
    for msg in test_msgs:
        action, params = get_action(msg)
        print(f"\n📩 {msg}")
        print(f"   → {action}: { {k:v for k,v in params.items() if k != 'raw'} }")
