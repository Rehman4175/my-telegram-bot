#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COMMAND PARSER v2.0 — RK BOT with DATE PARSING & CONFIRMATION FLAG
==================================================================
- First-word based command detection
- Date parsing for reminders (6 june, 15 august 2025)
- Time parsing (9 am, 3 pm, 5 baje)
- Returns confirmation flag for sensitive actions
"""

import re
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════
# FIRST WORD MAPS
# ══════════════════════════════════════════════════════

FIRST_WORD_MAP = {
    # Diary
    "diary": "diary", "dairy": "diary", "daiari": "diary", "dairi": "diary",
    "note": "diary", "notes": "diary", "likh": "diary", "likho": "diary",
    "likhna": "diary", "likh lo": "diary", "likh do": "diary", "save": "diary",
    "jot": "diary", "record": "diary",
    
    # Task
    "task": "task", "tasks": "task", "todo": "task", "kaam": "task",
    "kaaam": "task", "kam": "task", "karni": "task", "krni": "task",
    "karna": "task", "krna": "task", "work": "task", "mujhe": "task",
    "mujhey": "task",
    
    # Reminder
    "remind": "remind", "reminder": "remind", "remindme": "remind",
    "alarm": "remind", "alert": "remind", "yaad": "remind", "yad": "remind",
    "bata": "remind", "batao": "remind", "bata do": "remind", "notify": "remind",
    
    # Habit
    "habit": "habit", "habits": "habit", "habbit": "habit", "routine": "habit",
    
    # Expense
    "kharcha": "expense", "karcha": "expense", "kharch": "expense",
    "karch": "expense", "paisa": "expense", "paise": "expense",
    "rs": "expense", "rs.": "expense", "rupees": "expense", "spent": "expense",
    "laga": "expense", "lagaya": "expense", "expense": "expense",
    "खर्चा": "expense",
    
    # Water
    "paani": "water", "pani": "water", "paanii": "water", "water": "water",
    "drink": "water", "piya": "water", "pi": "water",
    
    # Memory
    "memory": "memory", "remember": "memory", "store": "memory",
    "yaaddasht": "memory", "memo": "memory",
    
    # Calendar
    "birthday": "calendar", "bday": "calendar", "b'day": "calendar",
    "janamdin": "calendar", "janmdin": "calendar", "event": "calendar",
    "events": "calendar", "schedule": "calendar", "cal": "calendar",
    "calendar": "calendar", "meeting": "calendar", "appointment": "calendar",
    
    # Bill
    "bill": "bill", "bills": "bill", "subscription": "bill", "sub": "bill",
    "emi": "bill", "loan": "bill", "insurance": "bill", "premium": "bill",
    
    # Complete Task
    "done": "complete", "complete": "complete", "completed": "complete",
    "finish": "complete", "finished": "complete", "ho gaya": "complete",
    "hogaya": "complete", "kar liya": "complete", "karliya": "complete",
    "kar li": "complete", "karli": "complete",
    
    # Show
    "dikhao": "show", "dikha": "show", "dekho": "show", "dekh": "show",
    "show": "show", "list": "show", "batao": "show", "bata": "show",
    "check": "show", "status": "show",
}

# ══════════════════════════════════════════════════════
# PHRASE PATTERNS
# ══════════════════════════════════════════════════════

PHRASE_PATTERNS = {
    "diary": [
        "diary mein likho", "diary me likho", "diary mein likh", "diary me likh",
        "diary mein add", "diary me add", "diary mein daalo", "diary me daalo",
        "diary mein save", "diary me save", "dairy mein likho", "dairy me likho",
        "dairy mein likh", "dairy me likh", "note kar lo", "note kar do",
        "note karo", "note kr", "likh lo", "likh do", "save kar lo",
        "aaj ka diary", "kal ka diary", "diary likhna", "jot kar lo",
        "record kar lo", "likha lo", "likha do",
    ],
    "task": [
        "task add", "task add kro", "task add karo", "task lagao", "task likh",
        "task likhna", "task banana", "task bana", "task bnao", "naya task",
        "new task", "ek task", "kaam add", "kaam karna hai", "kaam krna hai",
        "kaam karna he", "kaam krna he", "kaam likh", "kaam add karo",
        "todo add", "add todo", "to do", "add task", "add kaam",
        "mujhe karna hai", "mujhe krna hai", "karna hai", "krna hai",
        "karna he", "krna he", "ek kaam hai", "ek task hai",
        "important kaam", "zaruri kaam", "pending kaam", "baaki kaam",
    ],
    "remind": [
        "yaad dilana", "yaad dila do", "yaad dila", "remind me", "remind karo",
        "reminder set", "reminder lagao", "alarm set", "alarm lagao",
        "bata dena", "mat bhoolo", "reminder laga do", "reminder lagado",
        "yaad dilao", "yaad krao", "yaad kara", "yaad karwa do", "remind kr",
        "remind kar do", "remind karna", "reminder add", "reminder daal",
        "alarm laga do", "alarm daal", "bata do", "bata dena jab",
        "bhool na jao", "bhoolna mat", "mat bhoolna", "time pe bata",
        "waqt pe bata", "baad mein bata", "baad mein yaad",
        "min mein yaad", "ghante mein yaad", "din baad bata", "kal bata",
        "subah bata", "shaam bata", "raat ko bata", "dopahar bata",
        "set reminder", "set alarm", "add reminder", "add alarm",
        "notify karo", "notify kar",
    ],
    "habit": [
        "habit add", "habit lagao", "habit bana", "habit banana", "new habit",
        "naya habit", "habit start", "habit shuru", "habit done", "habit complete",
        "habit ho gayi", "habit ho gaya", "habit kar li", "habit kar liya",
        "habit log", "habit mark", "gym ho gaya", "gym kar liya", "gym kar li",
        "gym done", "gym complete", "exercise ho gayi", "exercise kar li",
        "exercise done", "exercise complete", "walk ho gayi", "walk kar li",
        "walk done", "walk complete", "reading ho gayi", "reading kar li",
        "reading done", "reading complete", "meditation ho gayi", "meditation kar li",
        "meditation done", "yoga ho gayi", "yoga kar li", "yoga done",
        "namaz ho gayi", "namaz kar li", "namaz padh li", "namaz padha",
        "quran padha", "quran parha", "running done", "running kar li",
        "workout done", "workout kar liya",
    ],
    "expense": [
        "kharcha hua", "kharcha kiya", "kharcha ho gaya", "karcha hua",
        "karcha kiya", "paisa gaya", "paise gaye", "paisa diya", "paise diye",
        "paisa laga", "paise lage", "rupees lage", "rupees diye", "rupees gaye",
        "rs laga", "rs diya", "rs gaya", "spent on", "spend kiya", "pe laga",
        "pe lagaya", "pe diya", "mein lagaya", "mein laga", "ka kharcha",
        "ki payment", "bill pay kiya", "pay kiya", "kharida", "khareeda",
        "khareed liya", "le liya", "le aaya", "add kharcha", "add expense",
        "expense add", "kharcha add", "petrol liya", "grocery liya",
        "khana khaya", "chai piya",
    ],
    "water": [
        "paani piya", "pani piya", "paani pi liya", "pani pi liya", "paani pi",
        "pani pi", "paani liya", "pani liya", "water piya", "water pi liya",
        "water log", "water add", "paani add", "pani add", "paani track",
        "pani track", "glass piya", "glass pi liya", "bottle piya",
        "bottle pi li", "1 glass", "2 glass", "3 glass", "ek glass",
        "do glass", "teen glass", "1 bottle", "2 bottle", "250 ml", "500 ml",
        "1000 ml", "paani peena", "pani peena",
    ],
    "memory": [
        "memory mein save karo", "memory me save karo", "memory mein save",
        "memory me save", "memory mein add", "memory me add", "memory mein rakh",
        "memory me rakh", "memory mein daal", "memory me daal", "yaad rakhna",
        "yaad rakh", "yaad rakhna hai", "yaad rakhni hai", "remember karo",
        "remember kar", "remember rakhna", "note down", "dimaag mein rakh",
        "dimag mein rakh", "save kar lo yeh", "yeh save karo", "important note",
        "imp note", "memory add", "add memory", "store karo", "store kar lo",
        "fact save", "info save",
    ],
    "calendar": [
        "birthday hai", "birthday add", "birthday save", "ka birthday",
        "ki birthday", "birthday kal hai", "birthday aaj hai", "janamdin hai",
        "janamdin add", "event add", "event hai", "event save", "event kal hai",
        "event aaj hai", "calendar mein add", "cal mein add", "schedule mein add",
        "schedule hai", "meeting add", "meeting hai", "meeting kal hai",
        "meeting aaj hai", "appointment add", "appointment hai", "function hai",
        "function add", "shaadi hai", "marriage hai", "anniversary hai",
        "anniversary add", "interview hai", "interview add", "exam hai", "exam add",
    ],
    "bill": [
        "bill add", "bill lagao", "bill save", "bill aya", "bill aaya",
        "bill aa gaya", "subscription add", "sub add", "emi add", "emi lagao",
        "loan add", "loan hai", "insurance add", "insurance premium",
        "monthly bill", "yearly bill", "netflix add", "jio add", "amazon add",
        "bill pay", "bill paid", "bill dena hai", "bill dena tha",
    ],
    "show": [
        "kharcha batao", "kharcha dikhao", "kharcha dekho", "expense batao",
        "expense dikhao", "task dikhao", "tasks dikhao", "task list",
        "task dekho", "task show", "show task", "pending task", "mera kaam",
        "kya task", "task kya hai", "task batao", "saare task", "sare task",
        "sab task", "reminder dikhao", "reminders dikhao", "reminder list",
        "reminder dekho", "reminder show", "show reminder", "active reminder",
        "mera reminder", "reminder batao", "alarm dikhao", "alarm list",
        "alarm dekho", "kitne reminder", "saare reminder", "habit dikhao",
        "habits dikhao", "habit list", "habit dekho", "habit show",
        "show habit", "meri habit", "aaj ki habit", "habit batao", "kya habit",
        "diary dikhao", "diary dekho", "diary padho", "show diary",
        "diary show", "aaj ki diary", "meri diary", "diary batao",
        "dairy dikhao", "dairy dekho", "purani diary", "poorani diary",
        "saari diary", "all diary", "diary all", "sab diary", "poori diary",
        "kharcha dikhao", "expense dikhao", "kharcha dekho", "expense list",
        "aaj ka kharcha", "kitna kharcha", "total kharcha", "expense batao",
        "paani dikhao", "water dikhao", "paani kitna", "water status",
        "aaj ka paani", "water goal", "memory dikhao", "memory dekho",
        "memory show", "show memory", "meri memory", "memory list",
        "kya yaad hai", "yaad hai kya", "calendar dikhao", "events dikhao",
        "events dekho", "upcoming events", "aaj ka event", "kal ka event",
        "schedule dikhao", "cal dikhao", "bills dikhao", "bill list",
        "bill dekho", "pending bills", "unpaid bills", "bills batao",
        "aaj kya kiya", "kya kiya aaj", "progress dikhao", "status batao",
        "summary dikhao", "briefing",
    ],
}

# ══════════════════════════════════════════════════════
# MONTH MAP FOR DATE PARSING
# ══════════════════════════════════════════════════════

MONTH_MAP = {
    'jan': 1, 'january': 1, 'januari': 1, 'feb': 2, 'february': 2, 'februari': 2,
    'mar': 3, 'march': 3, 'maret': 3, 'apr': 4, 'april': 4,
    'may': 5, 'mei': 5, 'jun': 6, 'june': 6, 'juni': 6,
    'jul': 7, 'july': 7, 'juli': 7, 'aug': 8, 'august': 8, 'agustus': 8,
    'sep': 9, 'sept': 9, 'september': 9, 'oct': 10, 'october': 10, 'oktober': 10,
    'nov': 11, 'november': 11, 'dec': 12, 'december': 12, 'desember': 12,
}

# ══════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════

def _get_now():
    """Fallback now function with IST"""
    from datetime import timezone
    IST = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(IST)

def _get_today_date():
    """Get today's date"""
    return _get_now().date()

def parse_specific_date(text: str, now_ist_func=None):
    """Parse specific dates like '6 june', '15 august 2025', 'june 6'"""
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
    """Parse time like '9 baje', '3 pm', '15:30', '9 am'"""
    lower = text.lower()
    
    # HH:MM format
    m = re.search(r'(\d{1,2}):(\d{2})', lower)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    
    # X baje / X am/pm
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
    """Parse relative time like '30 min baad', '2 ghante baad', 'kal 3 baje'"""
    if now_ist_func:
        now = now_ist_func()
    else:
        now = _get_now()
    
    lower = text.lower()
    
    # X minutes baad
    m = re.search(r'(\d+)\s*(?:minute|minutes|min|mins|m)\s*(?:baad|mein|main|after)?', lower)
    if m:
        return now + timedelta(minutes=int(m.group(1)))
    
    # X hours baad
    m = re.search(r'(\d+)\s*(?:hour|hours|hr|hrs|ghanta|ghante)\s*(?:baad|mein|main|after)?', lower)
    if m:
        return now + timedelta(hours=int(m.group(1)))
    
    # X days baad
    m = re.search(r'(\d+)\s*(?:day|days|din|dino)\s*(?:baad|mein|main|after)?', lower)
    if m:
        return now + timedelta(days=int(m.group(1)))
    
    # Tomorrow
    if 'kal' in lower or 'tomorrow' in lower or 'kl' in lower:
        result = now + timedelta(days=1)
        # Check for specific time
        time_str = parse_time_from_text(text)
        if time_str:
            hour, minute = map(int, time_str.split(':'))
            result = result.replace(hour=hour, minute=minute, second=0, microsecond=0)
        else:
            result = result.replace(hour=9, minute=0, second=0, microsecond=0)
        return result
    
    # Day after tomorrow
    if 'parso' in lower:
        return now + timedelta(days=2)
    
    return None

def parse_amount(text: str):
    """Extract amount from text like '200', 'rs 500', '500 rupees'"""
    m = re.search(r'(?:rs\.?\s*|rupees?\s*|₹\s*)?(\d+(?:\.\d+)?)\s*(?:rs\.?|rupees?|₹)?', text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None

def parse_water_amount(text: str):
    """Extract water amount in ML from text"""
    lower = text.lower()
    
    # Direct ML
    m = re.search(r'(\d+)\s*ml', lower)
    if m:
        return int(m.group(1))
    
    # Glass count
    m = re.search(r'(\d+)\s*(?:glass|glasses|gilas)', lower)
    if m:
        return int(m.group(1)) * 250
    
    # Bottle count
    m = re.search(r'(\d+)\s*(?:bottle|bottles)', lower)
    if m:
        return int(m.group(1)) * 500
    
    # Word numbers
    word_map = {'ek': 1, 'do': 2, 'teen': 3, 'char': 4, 'paanch': 5, 'chhe': 6, 'saat': 7, 'aath': 8}
    for word, num in word_map.items():
        if word in lower and 'glass' in lower:
            return num * 250
    
    # Default if any water keyword present
    if any(x in lower for x in ['piya', 'pi liya', 'pi', 'liya']):
        return 250
    
    return 250

def remove_phrase(text: str, phrase: str) -> str:
    """Remove a phrase from text"""
    result = text.replace(phrase, "", 1).strip()
    clean_words = ["karo", "kro", "kr", "do", "kar", "de", "dena", "hai", "hain", 
                   "tha", "thi", "the", "mein", "me", "main", "mujhe", "mera", 
                   "meri", "please", "plz", "zara", "jaldi", "abhi"]
    for cw in clean_words:
        result = re.sub(r'\b' + re.escape(cw) + r'\b', '', result, flags=re.IGNORECASE)
    return " ".join(result.split()).strip()

def remove_date_words(text: str) -> str:
    """Remove date/time related words from text"""
    date_words = [
        'january', 'february', 'march', 'april', 'may', 'june', 'july',
        'august', 'september', 'october', 'november', 'december',
        'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
        'ko', 'mein', 'me', 'pe', 'baje', 'bajay', 'am', 'pm',
        'subah', 'shaam', 'raat', 'dopahar', 'morning', 'evening', 'night',
        'kal', 'aaj', 'parso', 'tomorrow', 'today', 'kl'
    ]
    result = text
    for dw in date_words:
        result = re.sub(r'\b' + re.escape(dw) + r'\b', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', '', result)
    result = re.sub(r'\d{4}-\d{1,2}-\d{1,2}', '', result)
    result = re.sub(r'\d{1,2}:\d{2}', '', result)
    result = re.sub(r'\d+', '', result)
    return result.strip()

# ══════════════════════════════════════════════════════
# MAIN PARSER FUNCTION
# ══════════════════════════════════════════════════════

def parse_command(user_msg: str, now_ist_func=None):
    """
    Main parser - detect action from user message
    
    Returns:
        (action_type, params_dict)
    
    Action types:
        "diary", "task", "remind", "habit", "habit_done",
        "expense", "water", "memory", "calendar", "bill",
        "complete", "show_tasks", "show_reminders", "show_habits",
        "show_diary", "show_all_diary", "show_expense", "show_water",
        "show_memory", "show_calendar", "show_bills", "unknown"
    """
    
    if not user_msg or not user_msg.strip():
        return ("unknown", {})
    
    original = user_msg.strip()
    lower = original.lower().strip()
    
    # Step 1: Phrase pattern check
    for action, phrases in PHRASE_PATTERNS.items():
        for phrase in phrases:
            if lower.startswith(phrase) or phrase in lower[:50]:
                remaining = remove_phrase(lower, phrase)
                return _build_result(action, remaining, original, now_ist_func)
    
    # Step 2: First word check
    words = lower.split()
    if words:
        first = words[0]
        if first in FIRST_WORD_MAP:
            action = FIRST_WORD_MAP[first]
            remaining = " ".join(words[1:])
            return _build_result(action, remaining, original, now_ist_func)
        
        if len(words) >= 2:
            two_words = words[0] + " " + words[1]
            if two_words in FIRST_WORD_MAP:
                action = FIRST_WORD_MAP[two_words]
                remaining = " ".join(words[2:])
                return _build_result(action, remaining, original, now_ist_func)
    
    # Step 3: Amount only (expense shorthand)
    m = re.match(r'^(\d+(?:\.\d+)?)\s+(.+)$', lower)
    if m:
        amount = float(m.group(1))
        desc = m.group(2).strip()
        action_words = list(FIRST_WORD_MAP.keys())
        if not any(aw in desc for aw in action_words):
            return ("expense", {"amount": amount, "desc": desc.title(), "raw": original})
    
    # Step 4: Quick reminder (r 10m medicine)
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
    reminder_keywords = ['remind', 'reminder', 'yaad dilana', 'yaad dila', 
                         'bata dena', 'alarm', 'reminder lagao', 'reminder laga']
    
    if any(kw in lower for kw in reminder_keywords):
        # Try specific date first
        due_date = parse_specific_date(original, now_ist_func)
        if due_date:
            time_str = parse_time_from_text(original)
            if time_str:
                hour, minute = map(int, time_str.split(':'))
                due_dt = due_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            else:
                due_dt = due_date.replace(hour=9, minute=0, second=0, microsecond=0)
            
            # Extract text
            text = original
            for w in reminder_keywords + ['ko', 'mein', 'me', 'pe', 'baje', 'bajay']:
                text = re.sub(r'\b' + re.escape(w) + r'\b', '', text, flags=re.IGNORECASE)
            text = remove_date_words(text)
            text = " ".join(text.split()).strip()
            
            return ("remind", {"text": text.title() or "Reminder", 
                              "due": due_dt.strftime("%Y-%m-%d %H:%M:%S"), 
                              "raw": original})
        
        # Try relative time
        relative_dt = parse_relative_time(original, now_ist_func)
        if relative_dt:
            text = original
            for w in reminder_keywords:
                text = re.sub(r'\b' + re.escape(w) + r'\b', '', text, flags=re.IGNORECASE)
            text = re.sub(r'\d+\s*(?:min|minute|hour|hr|din|day|ghanta)\s*(?:baad|mein)?', '', text)
            text = " ".join(text.split()).strip()
            return ("remind", {"text": text.title() or "Reminder", 
                              "due": relative_dt.strftime("%Y-%m-%d %H:%M:%S"), 
                              "raw": original})
    
    # Step 6: Default
    return ("unknown", {"raw": original})

def _build_result(action: str, remaining: str, original: str, now_ist_func=None):
    """Build result dictionary based on action"""
    
    if action == "diary":
        text = remaining.strip() or original
        return ("diary", {"text": text, "raw": original})
    
    elif action == "task":
        title = remaining.strip() or original
        for kw in ["add", "karo", "kro", "lagao", "likh", "naya", "new", "karna", "krna"]:
            title = re.sub(r'\b' + re.escape(kw) + r'\b', '', title, flags=re.IGNORECASE)
        title = " ".join(title.split()).strip()
        return ("task", {"title": title[:100] or "Task", "raw": original})
    
    elif action == "remind":
        due_dt = parse_relative_time(original, now_ist_func)
        if not due_dt:
            due_dt = parse_specific_date(original, now_ist_func)
            if due_dt:
                # Agar date object hai to datetime mein convert karo
                from datetime import datetime as dt
                if not hasattr(due_dt, 'hour'):
                    due_dt = dt(due_dt.year, due_dt.month, due_dt.day, 9, 0, 0)
                else:
                    due_dt = due_dt.replace(hour=9, minute=0, second=0, microsecond=0)
        
        if not due_dt:
            due_dt = (now_ist_func() if now_ist_func else _get_now()) + timedelta(minutes=5)
        
        text = remaining or original
        for w in ["remind", "reminder", "alarm", "yaad", "dilana", "bata", "do", "dena", "set", "add"]:
            text = re.sub(r'\b' + re.escape(w) + r'\b', '', text, flags=re.IGNORECASE)
        text = remove_date_words(text)
        text = " ".join(text.split()).strip()
        
        return ("remind", {"text": text.title() or "Reminder", 
                          "due": due_dt.strftime("%Y-%m-%d %H:%M:%S"), 
                          "raw": original})
    
    elif action == "habit":
        name = remaining.strip()
        for kw in ["add", "lagao", "bana", "new", "naya", "start", "shuru"]:
            name = re.sub(r'\b' + re.escape(kw) + r'\b', '', name, flags=re.IGNORECASE)
        name = " ".join(name.split()).strip()
        
        # Check if it's a habit done command
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
        for kw in ["kharcha", "karcha", "paisa", "paise", "rs", "rupees", 
                   "spent", "laga", "lagaya", "expense", "add", "karo"]:
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
        for kw in ["memory", "save", "karo", "rakh", "yaad", "remember", "store"]:
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
        is_bday = any(w in original.lower() for w in ["birthday", "bday", "janamdin", "janmdin"])
        return ("calendar", {"title": title[:100] or "Event", 
                            "date": date_str, 
                            "type": "birthday" if is_bday else "event", 
                            "raw": original})
    
    elif action == "bill":
        amount = parse_amount(original)
        name = remaining or original
        for kw in ["bill", "bills", "subscription", "sub", "emi", "loan", "add", "new"]:
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
                name = name.replace(m.group(0), "")
        name = " ".join(name.split()).strip()
        
        return ("bill", {"name": name or "Bill", "amount": amount or 0, "due_day": due_day, "raw": original})
    
    elif action == "complete":
        m = re.search(r'#?(\d+)', original)
        task_id = int(m.group(1)) if m else None
        return ("complete", {"id": task_id, "hint": original, "raw": original})
    
    elif action == "show":
        lower_orig = original.lower()
        
        if any(x in lower_orig for x in ["task", "kaam", "todo", "pending"]):
            return ("show_tasks", {"raw": original})
        elif any(x in lower_orig for x in ["reminder", "alarm", "yaad"]):
            return ("show_reminders", {"raw": original})
        elif any(x in lower_orig for x in ["habit", "routine"]):
            return ("show_habits", {"raw": original})
        elif any(x in lower_orig for x in ["purani diary", "poorani diary", "saari diary", "all diary"]):
            return ("show_all_diary", {"raw": original})
        elif any(x in lower_orig for x in ["diary", "dairy"]):
            return ("show_diary", {"raw": original})
        elif any(x in lower_orig for x in ["memory", "yaad hai"]):
            return ("show_memory", {"raw": original})
        elif any(x in lower_orig for x in ["calendar", "event", "birthday", "schedule"]):
            return ("show_calendar", {"raw": original})
        elif any(x in lower_orig for x in ["bill", "bills", "subscription", "emi"]):
            return ("show_bills", {"raw": original})
        elif any(x in lower_orig for x in ["kharcha", "expense", "paisa"]):
            return ("show_expense", {"raw": original})
        elif any(x in lower_orig for x in ["paani", "pani", "water"]):
            return ("show_water", {"raw": original})
        else:
            return ("show_tasks", {"raw": original})
    
    return ("unknown", {"raw": original})

# ══════════════════════════════════════════════════════
# MAIN FUNCTION FOR BOT INTEGRATION (WITH CONFIRMATION FLAG)
# ══════════════════════════════════════════════════════

def get_action(user_msg: str, now_ist_func=None):
    """
    Main function to call from bot.py
    Returns: (action, params, needs_confirmation)
    
    Usage in bot.py:
        action, params, needs_confirm = get_action(user_msg, now_ist)
        
        if needs_confirm:
            # Ask user for confirmation
        else:
            # Execute directly (show commands, etc.)
    """
    action, params = parse_command(user_msg, now_ist_func)
    
    # Actions that need confirmation before adding
    confirm_actions = ["remind", "task", "diary", "expense", "habit", 
                       "habit_done", "calendar", "bill", "water", "memory"]
    
    needs_confirmation = action in confirm_actions
    
    return action, params, needs_confirmation


# ══════════════════════════════════════════════════════
# BACKWARD COMPATIBILITY (if you need original signature)
# ══════════════════════════════════════════════════════

def get_action_legacy(user_msg: str, now_ist_func=None):
    """Legacy function - returns only (action, params) without confirmation flag"""
    action, params = parse_command(user_msg, now_ist_func)
    return action, params


# ══════════════════════════════════════════════════════
# TEST BLOCK (run with python command_parser.py)
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("COMMAND PARSER v2.0 - TESTING")
    print("=" * 70)
    
    test_messages = [
        # Reminder with dates
        ("reminder lagao mujhe 6 june ko gao ka bijli bill bharna hai", "remind with date"),
        ("yaad dilana 15 august 2025 ko party hai", "remind with date"),
        ("kal 3 baje doctor appointment", "remind with tomorrow"),
        ("30 min baad chai yaad dilana", "remind with relative time"),
        
        # Other commands
        ("task kal market jaana", "task add"),
        ("kharcha 200 chai", "expense"),
        ("diary mein likho aaj ka din acha tha", "diary"),
        ("habit gym add karo", "habit"),
        ("gym ho gaya", "habit done"),
        
        # Show commands
        ("task dikhao", "show tasks"),
        ("reminder list", "show reminders"),
        ("saari diary dikhao", "show all diary"),
        
        # Quick commands
        ("done 3", "complete task"),
        ("r 10m medicine", "quick reminder"),
    ]
    
    for msg, desc in test_messages:
        action, params, needs_confirm = get_action(msg)
        print(f"\n📩 {desc}: {msg[:50]}...")
        print(f"   → Action: {action}")
        print(f"   → Needs Confirmation: {needs_confirm}")
        if params:
            display_params = {k: v for k, v in params.items() if k != 'raw'}
            if display_params:
                print(f"   → Params: {display_params}")
    
    print("\n" + "=" * 70)
    print("✅ TEST COMPLETE! Command parser ready.")
    print("=" * 70)
