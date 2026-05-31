#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COMMAND PARSER v4.0 — FIRST WORD ALWAYS WINS
==================================================================
- First word se command decide hoti hai - ALWAYS
- Baaki text mein koi bhi word ho, first word ki command chalegi
- "reminder lagao mujhe 2 min baad paani pina" → remind (not memory)
- "dairy mein likho yaad rakhna hai" → diary (not memory)
- Date/time parsing fully working
- Smart text cleanup
"""

import re
from datetime import datetime, timedelta, date

# ══════════════════════════════════════════════════════
# FIRST WORD MAP — YEH SAB SE PEHLE CHECK HOGA
# ══════════════════════════════════════════════════════

FIRST_WORD_MAP = {
    # ── REMINDER ──
    "remind": "remind", "reminder": "remind", "remindme": "remind",
    "alarm": "remind", "alert": "remind", "yaad": "remind", "yad": "remind",
    "bata": "remind", "batao": "remind", "notify": "remind",
    "remider": "remind", "remaind": "remind", "remaindar": "remind",
    "alram": "remind", "remainders": "remind", "reminders": "remind",

    # ── DIARY ──
    "diary": "diary", "dairy": "diary", "daiari": "diary", "dairi": "diary",
    "diari": "diary", "diaryy": "diary", "note": "diary", "notes": "diary",
    "likh": "diary", "likho": "diary", "likhna": "diary", "save": "diary",
    "jot": "diary", "record": "diary",

    # ── TASK ──
    "task": "task", "tasks": "task", "todo": "task", "kaam": "task",
    "kaaam": "task", "kam": "task", "karni": "task", "krni": "task",
    "karna": "task", "krna": "task", "work": "task",
    "kaaaam": "task",

    # ── HABIT ──
    "habit": "habit", "habits": "habit", "habbit": "habit", "routine": "habit",
    "habitt": "habit", "gym": "habit", "exercise": "habit", "walk": "habit",
    "yoga": "habit", "meditation": "habit", "namaz": "habit", "quran": "habit",
    "running": "habit", "workout": "habit",

    # ── EXPENSE ──
    "kharcha": "expense", "karcha": "expense", "kharch": "expense",
    "karch": "expense", "paisa": "expense", "paise": "expense",
    "rs": "expense", "rs.": "expense", "rupees": "expense", "spent": "expense",
    "laga": "expense", "lagaya": "expense", "expense": "expense",
    "kharach": "expense", "kharca": "expense", "spend": "expense",
    "paid": "expense", "payment": "expense",

    # ── WATER ──
    "paani": "water", "pani": "water", "paanii": "water", "water": "water",
    "drink": "water", "piya": "water", "paanee": "water",

    # ── MEMORY ──
    "memory": "memory", "remember": "memory", "store": "memory",
    "yaaddasht": "memory", "memo": "memory",

    # ── CALENDAR ──
    "birthday": "calendar", "bday": "calendar", "b'day": "calendar",
    "janamdin": "calendar", "janmdin": "calendar", "event": "calendar",
    "events": "calendar", "schedule": "calendar", "cal": "calendar",
    "calendar": "calendar", "meeting": "calendar", "appointment": "calendar",
    "bithday": "calendar", "birhtday": "calendar", "birtday": "calendar",
    "anniversary": "calendar", "aniversary": "calendar", "exam": "calendar",
    "interview": "calendar", "party": "calendar",

    # ── BILL ──
    "bill": "bill", "bills": "bill", "subscription": "bill", "sub": "bill",
    "emi": "bill", "loan": "bill", "insurance": "bill", "premium": "bill",
    "netflix": "bill", "jio": "bill", "amazon": "bill",

    # ── COMPLETE ──
    "done": "complete", "complete": "complete", "completed": "complete",
    "finish": "complete", "finished": "complete",

    # ── SHOW ──
    "dikhao": "show", "dikha": "show", "dekho": "show", "dekh": "show",
    "show": "show", "list": "show", "batao": "show", "check": "show",
    "status": "show",
}

# ══════════════════════════════════════════════════════
# FIRST PHRASE MAP — 2-3 word combinations
# ══════════════════════════════════════════════════════

FIRST_PHRASE_MAP = {
    # Reminder first-phrases
    "yaad dilana": "remind", "yaad dila": "remind", "yaad dila do": "remind",
    "yaad dilao": "remind", "yaad krao": "remind", "yaad kara": "remind",
    "bata dena": "remind", "bata do": "remind", "mat bhoolo": "remind",
    "remind me": "remind", "remind karo": "remind", "remind kar": "remind",
    "alarm set": "remind", "alarm laga": "remind", "alarm lagao": "remind",
    "reminder set": "remind", "reminder lagao": "remind", "reminder add": "remind",
    "reminder laga": "remind", "set reminder": "remind", "set alarm": "remind",
    "add reminder": "remind", "add alarm": "remind",
    "bhool mat": "remind", "mat bhoolna": "remind", "bhoolna mat": "remind",

    # Diary first-phrases
    "diary mein": "diary", "diary me": "diary", "dairy mein": "diary",
    "dairy me": "diary", "note kar": "diary", "note karo": "diary",
    "likh do": "diary", "likh lo": "diary", "save kar": "diary",
    "diary add": "diary", "diary entry": "diary", "diary update": "diary",
    "aaj ka diary": "diary", "diary likhna": "diary",

    # Task first-phrases
    "task add": "task", "task likh": "task", "task lagao": "task",
    "task banana": "task", "naya task": "task", "new task": "task",
    "kaam add": "task", "kaam likh": "task", "add task": "task",
    "add kaam": "task", "todo add": "task", "add todo": "task",
    "kaam karna hai": "task", "kaam krna hai": "task",
    "mujhe karna hai": "task", "karna hai": "task", "krna hai": "task",

    # Habit first-phrases
    "habit add": "habit", "habit lagao": "habit", "habit bana": "habit",
    "new habit": "habit", "naya habit": "habit", "habit done": "habit",
    "habit complete": "habit", "habit ho": "habit",
    "gym ho": "habit", "gym kar": "habit", "gym done": "habit",
    "exercise ho": "habit", "exercise kar": "habit", "exercise done": "habit",
    "walk ho": "habit", "walk kar": "habit", "walk done": "habit",
    "namaz ho": "habit", "namaz kar": "habit", "namaz padh": "habit",
    "quran padha": "habit", "quran parha": "habit",
    "workout done": "habit", "workout kar": "habit",
    "running done": "habit", "running kar": "habit",

    # Expense first-phrases
    "kharcha hua": "expense", "kharcha kiya": "expense", "kharcha add": "expense",
    "paisa gaya": "expense", "paise gaye": "expense", "paisa diya": "expense",
    "rs laga": "expense", "rupees lage": "expense", "spent on": "expense",
    "add kharcha": "expense", "add expense": "expense", "expense add": "expense",
    "pay kiya": "expense", "payment kiya": "expense",

    # Water first-phrases
    "paani piya": "water", "pani piya": "water", "water piya": "water",
    "paani pi": "water", "pani pi": "water", "water pi": "water",
    "paani add": "water", "water add": "water", "water log": "water",
    "glass piya": "water", "bottle piya": "water",

    # Memory first-phrases
    "memory mein": "memory", "memory me": "memory", "memory add": "memory",
    "memory save": "memory", "yaad rakhna": "memory", "yaad rakh": "memory",
    "remember karo": "memory", "remember kar": "memory",
    "note down": "memory", "dimaag mein": "memory", "dimag mein": "memory",

    # Calendar first-phrases
    "birthday add": "calendar", "birthday hai": "calendar",
    "birthday save": "calendar", "ka birthday": "calendar",
    "ki birthday": "calendar", "event add": "calendar", "event hai": "calendar",
    "meeting add": "calendar", "meeting hai": "calendar",
    "appointment add": "calendar", "cal mein": "calendar",
    "calendar mein": "calendar", "schedule add": "calendar",

    # Bill first-phrases
    "bill add": "bill", "bill lagao": "bill", "bill save": "bill",
    "subscription add": "bill", "emi add": "bill", "loan add": "bill",

    # Show first-phrases
    "task dikhao": "show", "task list": "show", "task dekho": "show",
    "reminder dikhao": "show", "reminder list": "show",
    "habit dikhao": "show", "habit list": "show",
    "diary dikhao": "show", "diary dekho": "show",
    "saari diary": "show", "purani diary": "show", "all diary": "show",
    "kharcha dikhao": "show", "expense dikhao": "show",
    "paani dikhao": "show", "water status": "show",
    "memory dikhao": "show", "memory list": "show",
    "calendar dikhao": "show", "events dikhao": "show",
    "bills dikhao": "show", "bill list": "show",
    "aaj kya kiya": "show", "kya kiya aaj": "show",
}

# ══════════════════════════════════════════════════════
# MONTH MAP
# ══════════════════════════════════════════════════════

MONTH_MAP = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2,
    'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
    'may': 5, 'mei': 5, 'jun': 6, 'june': 6, 'juni': 6,
    'jul': 7, 'july': 7, 'aug': 8, 'august': 8,
    'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10, 'nov': 11, 'november': 11,
    'dec': 12, 'december': 12,
}

REMINDER_CLEANUP_WORDS = [
    'reminder', 'remind', 'alarm', 'alert', 'yaad', 'yad', 'dilana',
    'dila', 'do', 'dena', 'set', 'add', 'lagao', 'laga', 'laga do',
    'notify', 'bata', 'batao', 'mat', 'bhoolo', 'bhoolna', 'mat bhoolna',
    'mujhe', 'mujhey', 'please', 'plz', 'zara', 'jaldi', 'zaroor',
    'remider', 'remaind', 'alram', 'karwa', 'krao', 'kara',
]

# ══════════════════════════════════════════════════════
# TIME PARSER
# ══════════════════════════════════════════════════════

def parse_time_from_text(text: str):
    lower = text.lower()

    # HH:MM
    m = re.search(r'\b(\d{1,2}):(\d{2})\b', lower)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"

    # subha/morning X baje
    m = re.search(
        r'(?:subah|subha|morning|fajar|fajr)\s+(\d{1,2})\s*(?:baje|bajay|am|:00)?',
        lower
    )
    if m:
        h = int(m.group(1))
        if h == 12: h = 0
        return f"{h:02d}:00"

    # shaam/evening/raat X baje
    m = re.search(
        r'(?:shaam|sham|evening|raat|night|maghrib|isha)\s+(\d{1,2})\s*(?:baje|bajay|pm|:00)?',
        lower
    )
    if m:
        h = int(m.group(1))
        if h != 12: h += 12
        if h > 23: h = 23
        return f"{h:02d}:00"

    # dopahar X baje
    m = re.search(
        r'(?:dopahar|noon|zuhr)\s+(\d{1,2})\s*(?:baje|bajay|pm|:00)?',
        lower
    )
    if m:
        h = int(m.group(1))
        if h < 12: h += 12
        return f"{h:02d}:00"

    # X baje with context
    m = re.search(r'(\d{1,2})\s*(?:baje|bajay)\b', lower)
    if m:
        h = int(m.group(1))
        if any(x in lower for x in ['subah', 'subha', 'morning', 'am', 'fajar']):
            if h == 12: h = 0
        elif any(x in lower for x in ['shaam', 'sham', 'evening', 'raat', 'night', 'pm']):
            if h != 12: h += 12
        else:
            if 1 <= h <= 6: h += 12
        return f"{h:02d}:00"

    # X am/pm
    m = re.search(r'(\d{1,2})\s*(am|pm)\b', lower)
    if m:
        h = int(m.group(1))
        if m.group(2) == 'pm':
            if h != 12: h += 12
        else:
            if h == 12: h = 0
        return f"{h:02d}:00"

    # Default times
    if any(x in lower for x in ['subah', 'subha', 'morning', 'fajar']):
        return "09:00"
    if any(x in lower for x in ['shaam', 'sham', 'evening', 'maghrib']):
        return "18:00"
    if any(x in lower for x in ['raat', 'night', 'isha']):
        return "21:00"
    if any(x in lower for x in ['dopahar', 'noon', 'zuhr']):
        return "13:00"

    return None


def parse_specific_date(text: str, now_ist_func=None):
    from datetime import timezone
    if now_ist_func:
        now = now_ist_func()
    else:
        IST = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(IST)
    today = now.date()
    lower = text.lower()

    if re.search(r'\bparso\b', lower):
        return today + timedelta(days=2)
    if re.search(r'\bkal\b|\bkl\b|\btomorrow\b', lower):
        return today + timedelta(days=1)
    if re.search(r'\baaj\b|\btoday\b', lower):
        return today

    # YYYY-MM-DD
    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', lower)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except: pass

    # DD/MM/YYYY
    m = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', lower)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except: pass

    # DD/MM/YY
    m = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{2})\b', lower)
    if m:
        try:
            return date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except: pass

    month_keys = sorted(MONTH_MAP.keys(), key=len, reverse=True)
    month_pattern = '|'.join(re.escape(k) for k in month_keys)

    # DD Month YYYY / DD Month
    m = re.search(
        r'(\d{1,2})\s+(' + month_pattern + r')\.?\s*(?:(\d{4}))?',
        lower
    )
    if m:
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2).rstrip('.'), 0)
        year = int(m.group(3)) if m.group(3) else today.year
        if month:
            try:
                d = date(year, month, day)
                if d < today and not m.group(3):
                    d = date(year + 1, month, day)
                return d
            except: pass

    # Month DD YYYY / Month DD
    m = re.search(
        r'(' + month_pattern + r')\.?\s+(\d{1,2})(?:\s+(\d{4}))?',
        lower
    )
    if m:
        month = MONTH_MAP.get(m.group(1).rstrip('.'), 0)
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        if month:
            try:
                d = date(year, month, day)
                if d < today and not m.group(3):
                    d = date(year + 1, month, day)
                return d
            except: pass

    return None


def parse_relative_time(text: str, now_ist_func=None):
    from datetime import timezone
    if now_ist_func:
        now = now_ist_func()
    else:
        IST = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(IST)
    lower = text.lower()

    # Seconds
    m = re.search(r'(\d+)\s*(?:second|seconds|sec|secs)\s*(?:baad|mein|after)?', lower)
    if m:
        return now + timedelta(seconds=int(m.group(1)))

    # Minutes
    m = re.search(r'(\d+)\s*(?:minute|minutes|min|mins|m)\s*(?:baad|mein|main|after|ke baad)?', lower)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    # Hours
    m = re.search(r'(\d+)\s*(?:hour|hours|hr|hrs|ghanta|ghante)\s*(?:baad|mein|main|after|ke baad)?', lower)
    if m:
        return now + timedelta(hours=int(m.group(1)))

    # Days
    m = re.search(r'(\d+)\s*(?:day|days|din|dino)\s*(?:baad|mein|main|after|ke baad)?', lower)
    if m:
        return now + timedelta(days=int(m.group(1)))

    # Weeks
    m = re.search(r'(\d+)\s*(?:week|weeks|hafte|hafta)\s*(?:baad|mein|main|after|ke baad)?', lower)
    if m:
        return now + timedelta(weeks=int(m.group(1)))

    # Kal with time
    if re.search(r'\bkal\b|\bkl\b|\btomorrow\b', lower):
        result = now + timedelta(days=1)
        time_str = parse_time_from_text(text)
        h, mi = map(int, time_str.split(':')) if time_str else (9, 0)
        return result.replace(hour=h, minute=mi, second=0, microsecond=0)

    # Parso
    if re.search(r'\bparso\b', lower):
        result = now + timedelta(days=2)
        time_str = parse_time_from_text(text)
        h, mi = map(int, time_str.split(':')) if time_str else (9, 0)
        return result.replace(hour=h, minute=mi, second=0, microsecond=0)

    # Today with specific time
    time_str = parse_time_from_text(text)
    if time_str:
        h, mi = map(int, time_str.split(':'))
        result = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if result <= now:
            result += timedelta(days=1)
        return result

    return None


def parse_amount(text: str):
    m = re.search(r'(?:rs\.?\s*|rupees?\s*|₹\s*)(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if m: return float(m.group(1))
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:rs\.?|rupees?|₹)', text, re.IGNORECASE)
    if m: return float(m.group(1))
    m = re.search(r'\b(\d+(?:\.\d+)?)\b', text)
    if m: return float(m.group(1))
    return None


def parse_water_amount(text: str):
    lower = text.lower()
    m = re.search(r'(\d+)\s*ml', lower)
    if m: return int(m.group(1))
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:liter|litre|l)\b', lower)
    if m: return int(float(m.group(1)) * 1000)
    m = re.search(r'(\d+)\s*(?:glass|glasses|gilas)', lower)
    if m: return int(m.group(1)) * 250
    m = re.search(r'(\d+)\s*(?:bottle|bottles)', lower)
    if m: return int(m.group(1)) * 500
    word_map = {'ek': 1, 'do': 2, 'teen': 3, 'char': 4, 'paanch': 5,
                'chhe': 6, 'saat': 7, 'aath': 8, 'one': 1, 'two': 2,
                'three': 3, 'four': 4, 'five': 5}
    for word, num in word_map.items():
        if word in lower:
            if 'bottle' in lower: return num * 500
            if 'glass' in lower: return num * 250
    return 250


def clean_reminder_text(original: str) -> str:
    result = original
    for kw in REMINDER_CLEANUP_WORDS:
        result = re.sub(r'\b' + re.escape(kw) + r'\b', ' ', result, flags=re.IGNORECASE)

    result = re.sub(r'\d{4}-\d{1,2}-\d{1,2}', ' ', result)
    result = re.sub(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', ' ', result)
    result = re.sub(r'\d{1,2}:\d{2}', ' ', result)

    month_keys = sorted(MONTH_MAP.keys(), key=len, reverse=True)
    for mk in month_keys:
        result = re.sub(r'\b' + re.escape(mk) + r'\b', ' ', result, flags=re.IGNORECASE)

    time_words = [
        'subah', 'subha', 'shaam', 'sham', 'raat', 'dopahar',
        'morning', 'evening', 'night', 'noon', 'baje', 'bajay',
        'am', 'pm', 'kal', 'aaj', 'parso', 'tomorrow', 'today',
        'baad', 'mein', 'me', 'ko', 'pe', 'par', 'ke',
    ]
    for tw in time_words:
        result = re.sub(r'\b' + re.escape(tw) + r'\b', ' ', result, flags=re.IGNORECASE)

    result = re.sub(r'\b\d{1,2}\b', ' ', result)
    result = ' '.join(result.split()).strip()

    if len(result) < 3:
        stop = set(REMINDER_CLEANUP_WORDS + time_words +
                   ['ka', 'ki', 'ke', 'hai', 'hain', 'tha', 'thi'])
        words = original.split()
        meaningful = [w for w in words
                      if w.lower() not in stop
                      and not re.match(r'^\d+$', w)
                      and len(w) > 1]
        result = ' '.join(meaningful).strip()

    return result if result else "Reminder"


# ══════════════════════════════════════════════════════
# MAIN PARSER — FIRST WORD WINS
# ══════════════════════════════════════════════════════

def parse_command(user_msg: str, now_ist_func=None):
    if not user_msg or not user_msg.strip():
        return ("unknown", {})

    original = user_msg.strip()
    lower = original.lower().strip()
    words = lower.split()

    # ════════════════════════════════
    # STEP 1: FIRST WORD CHECK — HIGHEST PRIORITY
    # Pehla word jo bhi ho, usi se action decide hoga
    # ════════════════════════════════
    if words:
        first_word = words[0]

        # Single first word match
        if first_word in FIRST_WORD_MAP:
            action = FIRST_WORD_MAP[first_word]
            remaining = " ".join(words[1:])
            return _build_result(action, remaining, original, now_ist_func)

        # Two-word first phrase match
        if len(words) >= 2:
            two = words[0] + " " + words[1]
            if two in FIRST_PHRASE_MAP:
                action = FIRST_PHRASE_MAP[two]
                remaining = " ".join(words[2:])
                return _build_result(action, remaining, original, now_ist_func)

        # Three-word first phrase match
        if len(words) >= 3:
            three = words[0] + " " + words[1] + " " + words[2]
            if three in FIRST_PHRASE_MAP:
                action = FIRST_PHRASE_MAP[three]
                remaining = " ".join(words[3:])
                return _build_result(action, remaining, original, now_ist_func)

    # ════════════════════════════════
    # STEP 2: AMOUNT FIRST = EXPENSE
    # "200 chai", "500 petrol"
    # ════════════════════════════════
    m = re.match(r'^(\d+(?:\.\d+)?)\s+(.+)$', lower)
    if m:
        amount = float(m.group(1))
        desc = m.group(2).strip()
        # Make sure desc first word is not a command
        desc_first = desc.split()[0] if desc.split() else ""
        if desc_first not in FIRST_WORD_MAP:
            return ("expense", {
                "amount": amount,
                "desc": desc.title(),
                "raw": original
            })

    # ════════════════════════════════
    # STEP 3: QUICK REMINDER SHORTHAND
    # "r 10m medicine", "r 1h paani"
    # ════════════════════════════════
    m = re.match(r'^r\s+(\d+(?:m|min|h|hr|s|sec)?)\s+(.+)$', lower)
    if m:
        time_arg = m.group(1)
        text = m.group(2).strip()
        from datetime import timezone
        now = now_ist_func() if now_ist_func else datetime.now(
            __import__('datetime').timezone(timedelta(hours=5, minutes=30))
        )
        if re.search(r'm(?:in)?$', time_arg):
            mins = int(re.sub(r'[^0-9]', '', time_arg))
            due = now + timedelta(minutes=mins)
        elif re.search(r'h(?:r)?$', time_arg):
            hrs = int(re.sub(r'[^0-9]', '', time_arg))
            due = now + timedelta(hours=hrs)
        elif re.search(r's(?:ec)?$', time_arg):
            secs = int(re.sub(r'[^0-9]', '', time_arg))
            due = now + timedelta(seconds=secs)
        else:
            due = now + timedelta(minutes=int(re.sub(r'[^0-9]', '', time_arg)))
        return ("remind", {
            "text": text.title(),
            "due": due.strftime("%Y-%m-%d %H:%M:%S"),
            "raw": original
        })

    # ════════════════════════════════
    # STEP 4: DONE + NUMBER = COMPLETE TASK
    # ════════════════════════════════
    m = re.match(r'^done\s+(\d+)$', lower)
    if m:
        return ("complete", {"id": int(m.group(1)), "hint": original, "raw": original})

    # ════════════════════════════════
    # STEP 5: UNKNOWN
    # ════════════════════════════════
    return ("unknown", {"raw": original})


# ══════════════════════════════════════════════════════
# BUILD RESULT
# ══════════════════════════════════════════════════════

def _build_result(action: str, remaining: str, original: str, now_ist_func=None):

    if action == "diary":
        text = remaining.strip() or original
        for kw in ['diary', 'dairy', 'mein', 'me', 'likho', 'likh',
                   'add', 'save', 'daalo', 'daal', 'note', 'entry', 'update']:
            text = re.sub(r'\b' + re.escape(kw) + r'\b', ' ', text, flags=re.IGNORECASE)
        text = ' '.join(text.split()).strip() or original
        return ("diary", {"text": text, "raw": original})

    elif action == "task":
        title = remaining.strip() or original
        for kw in ["add", "karo", "kro", "lagao", "likh", "naya", "new",
                   "karna", "krna", "karna hai", "krna hai", "banana", "bana",
                   "mujhe", "hai", "he"]:
            title = re.sub(r'\b' + re.escape(kw) + r'\b', '', title, flags=re.IGNORECASE)
        title = " ".join(title.split()).strip()
        return ("task", {"title": title[:100] or "Task", "raw": original})

    elif action == "remind":
        # Try relative time first
        due_dt = parse_relative_time(original, now_ist_func)

        if not due_dt:
            due_date = parse_specific_date(original, now_ist_func)
            if due_date:
                time_str = parse_time_from_text(original)
                if time_str:
                    h, mi = map(int, time_str.split(':'))
                    due_dt = datetime(due_date.year, due_date.month, due_date.day, h, mi, 0)
                else:
                    due_dt = datetime(due_date.year, due_date.month, due_date.day, 9, 0, 0)

        if not due_dt:
            from datetime import timezone
            now = now_ist_func() if now_ist_func else datetime.now(
                timezone(timedelta(hours=5, minutes=30))
            )
            due_dt = now + timedelta(minutes=5)

        text = clean_reminder_text(original)
        return ("remind", {
            "text": text.title() or "Reminder",
            "due": due_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "raw": original
        })

    elif action == "habit":
        name = remaining.strip()
        for kw in ["add", "lagao", "bana", "new", "naya", "start",
                   "shuru", "banana", "bnao"]:
            name = re.sub(r'\b' + re.escape(kw) + r'\b', '', name, flags=re.IGNORECASE)
        name = " ".join(name.split()).strip()

        done_words = [
            "done", "complete", "ho gayi", "ho gaya", "kar li", "kar liya",
            "ho gai", "kiya", "ki", "padha", "padhi", "parha", "gaya", "gayi",
        ]
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
                   "spent", "laga", "lagaya", "expense", "add", "karo",
                   "kharach", "kharch", "spend", "paid", "payment"]:
            desc = re.sub(r'\b' + re.escape(kw) + r'\b', '', desc, flags=re.IGNORECASE)
        if amount:
            desc = desc.replace(str(int(amount)), "").replace(str(amount), "")
        desc = " ".join(desc.split()).strip()
        return ("expense", {
            "amount": amount or 0,
            "desc": desc.title() or "Expense",
            "raw": original
        })

    elif action == "water":
        ml = parse_water_amount(original)
        return ("water", {"ml": ml, "raw": original})

    elif action == "memory":
        text = remaining.strip() or original
        for kw in ["memory", "save", "karo", "rakh", "yaad", "remember",
                   "store", "mein", "me", "add", "daal", "note", "yaaddasht"]:
            text = re.sub(r'\b' + re.escape(kw) + r'\b', '', text, flags=re.IGNORECASE)
        text = " ".join(text.split()).strip()
        return ("memory", {"text": text or original, "raw": original})

    elif action == "calendar":
        due_date = parse_specific_date(original, now_ist_func)
        date_str = due_date.strftime("%Y-%m-%d") if due_date else \
            (now_ist_func() if now_ist_func else datetime.now()).strftime("%Y-%m-%d")

        title = remaining or original
        is_bday = any(w in original.lower() for w in [
            "birthday", "bday", "janamdin", "janmdin", "bithday", "b'day",
        ])
        for kw in ["birthday", "bday", "janamdin", "event", "add", "hai",
                   "calendar", "cal", "schedule", "mein", "me", "ka", "ki",
                   "meeting", "appointment"]:
            title = re.sub(r'\b' + re.escape(kw) + r'\b', '', title, flags=re.IGNORECASE)
        title = ' '.join(title.split()).strip()

        return ("calendar", {
            "title": title[:100] or "Event",
            "date": date_str,
            "type": "birthday" if is_bday else "event",
            "raw": original
        })

    elif action == "bill":
        amount = parse_amount(original)
        name = remaining or original
        for kw in ["bill", "bills", "subscription", "sub", "emi", "loan",
                   "add", "new", "naya", "lagao", "netflix", "jio", "amazon"]:
            name = re.sub(r'\b' + re.escape(kw) + r'\b', '', name, flags=re.IGNORECASE)
        if amount:
            name = name.replace(str(int(amount)), "").replace(str(amount), "")

        due_day = 0
        m = re.search(r'(\d{1,2})\s*(?:tarikh|taarikh|date|th|st|nd|rd)\b', original.lower())
        if m:
            candidate = int(m.group(1))
            if 1 <= candidate <= 31:
                due_day = candidate
                name = name.replace(m.group(0), "")
        name = " ".join(name.split()).strip()
        return ("bill", {
            "name": name or "Bill",
            "amount": amount or 0,
            "due_day": due_day,
            "raw": original
        })

    elif action == "complete":
        m = re.search(r'#?(\d+)', original)
        task_id = int(m.group(1)) if m else None
        return ("complete", {"id": task_id, "hint": original, "raw": original})

    elif action == "show":
        lower_orig = original.lower()
        if any(x in lower_orig for x in ["purani diary", "poorani diary", "saari diary",
                                           "all diary", "puraani diary", "poori diary"]):
            return ("show_all_diary", {"raw": original})
        elif any(x in lower_orig for x in ["task", "kaam", "todo", "pending"]):
            return ("show_tasks", {"raw": original})
        elif any(x in lower_orig for x in ["reminder", "alarm", "yaad"]):
            return ("show_reminders", {"raw": original})
        elif any(x in lower_orig for x in ["habit", "routine"]):
            return ("show_habits", {"raw": original})
        elif any(x in lower_orig for x in ["diary", "dairy"]):
            return ("show_diary", {"raw": original})
        elif any(x in lower_orig for x in ["memory", "yaad hai"]):
            return ("show_memory", {"raw": original})
        elif any(x in lower_orig for x in ["calendar", "event", "birthday", "schedule"]):
            return ("show_calendar", {"raw": original})
        elif any(x in lower_orig for x in ["bill", "subscription", "emi"]):
            return ("show_bills", {"raw": original})
        elif any(x in lower_orig for x in ["kharcha", "expense", "paisa"]):
            return ("show_expense", {"raw": original})
        elif any(x in lower_orig for x in ["paani", "pani", "water"]):
            return ("show_water", {"raw": original})
        else:
            return ("show_tasks", {"raw": original})

    return ("unknown", {"raw": original})


# ══════════════════════════════════════════════════════
# MAIN FUNCTION
# ══════════════════════════════════════════════════════

def get_action(user_msg: str, now_ist_func=None):
    """
    Main function - returns (action, params, needs_confirmation)
    RULE: First word ALWAYS decides the action
    """
    action, params = parse_command(user_msg, now_ist_func)

    confirm_actions = [
        "remind", "task", "diary", "expense", "habit",
        "habit_done", "calendar", "bill", "water", "memory"
    ]
    needs_confirmation = action in confirm_actions
    return action, params, needs_confirmation


def get_action_legacy(user_msg: str, now_ist_func=None):
    action, params = parse_command(user_msg, now_ist_func)
    return action, params


# ══════════════════════════════════════════════════════
# TEST
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("COMMAND PARSER v4.0 - FIRST WORD ALWAYS WINS")
    print("=" * 70)

    test_cases = [
        # ── MAIN PROBLEM CASES ──
        ("reminder lagao mujhe 2 min baad paani pina hai yaad dilana",
         "SHOULD BE: remind (not memory)"),
        ("yaad dilana 6 june subha 11 baje IGL ka bill bharna hai",
         "SHOULD BE: remind with date+time"),
        ("dairy mein likho aaj yaad aaya tha kuch important",
         "SHOULD BE: diary (not memory)"),
        ("task add karna hai doctor se milna yaad dilana",
         "SHOULD BE: task (not remind)"),
        ("paani piya yaad rakhna 2 glass",
         "SHOULD BE: water (not memory)"),

        # ── REMINDER CASES ──
        ("reminder 6 june subha 11 baje IGL ka bill",   "remind date+time"),
        ("yaad dilana kal shaam 5 baje meeting",         "remind tomorrow evening"),
        ("alarm set karo 30 min baad chai",              "remind relative"),
        ("bata dena raat 10 baje medicine leni hai",     "remind night"),
        ("r 10m paani pina",                             "quick remind"),
        ("r 2h gym jana",                                "quick remind hours"),

        # ── DIARY CASES ──
        ("diary mein likho aaj ka din acha tha",         "diary"),
        ("dairy yaad aa gaya kal ki baat",               "diary"),
        ("note kar lo meeting mein yaad dilana tha",     "diary (not remind)"),

        # ── TASK CASES ──
        ("task doctor se milna hai",                     "task"),
        ("kaam karna hai market jana reminder bhi chahiye", "task (not remind)"),
        ("done 3",                                       "complete"),

        # ── EXPENSE CASES ──
        ("kharcha 200 chai",                             "expense"),
        ("500 petrol",                                   "expense shorthand"),
        ("paisa diya 300 grocery",                       "expense"),

        # ── WATER CASES ──
        ("paani piya 2 glass yaad rakhna",               "water (not memory)"),
        ("water 500ml",                                  "water"),

        # ── HABIT CASES ──
        ("gym ho gaya",                                  "habit done"),
        ("namaz padh li",                                "habit done"),
        ("habit add morning walk",                       "habit add"),

        # ── SHOW CASES ──
        ("task dikhao",                                  "show tasks"),
        ("saari diary dikhao",                           "show all diary"),
        ("reminder list",                                "show reminders"),
    ]

    passed = 0
    failed = 0
    for msg, desc in test_cases:
        action, params, confirm = get_action(msg)
        display = {k: v for k, v in params.items() if k != 'raw'}
        status = "✅" if "SHOULD BE" not in desc or \
                 desc.split("SHOULD BE: ")[1].split(" ")[0].lower() in action else "❌"
        if status == "✅":
            passed += 1
        else:
            failed += 1
        print(f"\n{status} [{desc}]")
        print(f"   MSG: {msg[:60]}")
        print(f"   → {action} | {display}")

    print(f"\n{'='*70}")
    print(f"✅ Passed: {passed} | ❌ Failed: {failed}")
    print(f"{'='*70}")
