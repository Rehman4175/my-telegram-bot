#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COMMAND PARSER v1.0 — RK BOT
==============================
Strict first-word based command detection.
Pehla word = Action — Zero confusion.

CATEGORIES:
  1. DIARY      — diary, note, likh, likho, save
  2. TASK       — task, kaam, todo, add, karni, krni
  3. REMINDER   — remind, yaad, alarm, set, bata
  4. HABIT      — habit, done, complete, kar li, ho gaya
  5. EXPENSE    — kharcha, paisa, rs, rupees, spent, laga
  6. WATER      — paani, water, pani
  7. MEMORY     — memory, yaad rakh, note down, remember
  8. CALENDAR   — birthday, event, cal, schedule
  9. BILL       — bill, subscription, emi, loan
  10. SHOW      — dikhao, dekho, list, show, batao
"""

import re
from datetime import datetime, timedelta


# ══════════════════════════════════════════════════════
# FIRST WORD MAPS — Pehla word se action decide hoga
# ══════════════════════════════════════════════════════

# Har action ke liye pehle words
FIRST_WORD_MAP = {

    # ── DIARY ──────────────────────────────────────────
    "diary":    "diary",
    "daiari":   "diary",
    "dairy":    "diary",   # common misspelling
    "dairi":    "diary",
    "note":     "diary",
    "notes":    "diary",
    "likh":     "diary",
    "likho":    "diary",
    "likhna":   "diary",
    "likh lo":  "diary",
    "likh do":  "diary",
    "save":     "diary",
    "jot":      "diary",
    "record":   "diary",

    # ── TASK ───────────────────────────────────────────
    "task":     "task",
    "tasks":    "task",
    "todo":     "task",
    "kaam":     "task",
    "kaaam":    "task",
    "kam":      "task",
    "karni":    "task",
    "krni":     "task",
    "karna":    "task",
    "krna":     "task",
    "work":     "task",
    "mujhe":    "task",
    "mujhey":   "task",

    # ── REMINDER ───────────────────────────────────────
    "remind":   "remind",
    "reminder": "remind",
    "remindme": "remind",
    "alarm":    "remind",
    "alert":    "remind",
    "yaad":     "remind",
    "yad":      "remind",
    "bata":     "remind",
    "batao":    "remind",
    "bata do":  "remind",
    "bhool":    "remind",   # "bhoolna mat" reminder
    "notify":   "remind",

    # ── HABIT ──────────────────────────────────────────
    "habit":    "habit",
    "habits":   "habit",
    "habbit":   "habit",   # misspelling
    "routine":  "habit",
    "streak":   "habit",

    # ── EXPENSE ────────────────────────────────────────
    "kharcha":  "expense",
    "karcha":   "expense",
    "kharch":   "expense",
    "karch":    "expense",
    "kharach":  "expense",
    "paisa":    "expense",
    "paise":    "expense",
    "paisaa":   "expense",
    "rs":       "expense",
    "rs.":      "expense",
    "rupees":   "expense",
    "rupaye":   "expense",
    "rupaya":   "expense",
    "rupaiye":  "expense",
    "spent":    "expense",
    "spend":    "expense",
    "laga":     "expense",
    "lagaya":   "expense",
    "diya":     "expense",
    "expense":  "expense",
    "expenses": "expense",
    "खर्चा":    "expense",

    # ── WATER ──────────────────────────────────────────
    "paani":    "water",
    "pani":     "water",
    "paanii":   "water",
    "water":    "water",
    "drink":    "water",
    "piya":     "water",   # "piya paani"
    "pi":       "water",

    # ── MEMORY ─────────────────────────────────────────
    "memory":   "memory",
    "yaaddasht": "memory",
    "memo":     "memory",
    "remember": "memory",
    "yaaddasht":"memory",
    "store":    "memory",

    # ── CALENDAR / BIRTHDAY / EVENT ────────────────────
    "birthday": "calendar",
    "bday":     "calendar",
    "b'day":    "calendar",
    "janamdin": "calendar",
    "janmdin":  "calendar",
    "event":    "calendar",
    "events":   "calendar",
    "schedule": "calendar",
    "cal":      "calendar",
    "calendar": "calendar",
    "meeting":  "calendar",   # "meeting add karo kal"
    "appointment": "calendar",

    # ── BILL ───────────────────────────────────────────
    "bill":     "bill",
    "bills":    "bill",
    "subscription": "bill",
    "sub":      "bill",
    "emi":      "bill",
    "loan":     "bill",
    "insurance": "bill",
    "premium":  "bill",

    # ── COMPLETE TASK ───────────────────────────────────
    "done":     "complete",
    "complete": "complete",
    "completed":"complete",
    "finish":   "complete",
    "finished": "complete",
    "ho gaya":  "complete",
    "hogaya":   "complete",
    "kar liya": "complete",
    "karliya":  "complete",
    "kar li":   "complete",
    "karli":    "complete",

    # ── SHOW / LIST ─────────────────────────────────────
    "dikhao":   "show",
    "dikha":    "show",
    "dekho":    "show",
    "dekh":     "show",
    "show":     "show",
    "list":     "show",
    "batao":    "show",
    "bata":     "show",
    "check":    "show",
    "status":   "show",
}


# ══════════════════════════════════════════════════════
# PHRASE PATTERNS — Poori phrase se detect karna
# Ye first-word map se pehle check hoga
# ══════════════════════════════════════════════════════

PHRASE_PATTERNS = {

    # ── DIARY PHRASES ──────────────────────────────────
    "diary": [
        "diary mein likho", "diary me likho",
        "diary mein likh", "diary me likh",
        "diary mein add", "diary me add",
        "diary mein daalo", "diary me daalo",
        "diary mein save", "diary me save",
        "diary mein note", "diary me note",
        "diary add", "dairy add",
        "dairy mein likho", "dairy me likho",
        "dairy mein likh", "dairy me likh",
        "note kar lo", "note kar do",
        "note karo", "note kr",
        "likh lo", "likh do", "likh kar",
        "save kar lo", "save kar do",
        "aaj ka diary", "kal ka diary",
        "diary likhna", "diary likhni",
        "jot kar lo", "jot down",
        "record kar lo", "record karo",
        "likha lo", "likha do",
    ],

    # ── TASK PHRASES ───────────────────────────────────
    "task": [
        "task add", "task add kro", "task add karo",
        "task lagao", "task likh", "task likhna",
        "task banana", "task bana", "task bnao",
        "naya task", "new task", "ek task",
        "kaam add", "kaam karna hai", "kaam krna hai",
        "kaam karna he", "kaam krna he",
        "kaam likh", "kaam add karo",
        "todo add", "add todo", "to do",
        "add task", "add kaam",
        "mujhe karna hai", "mujhe krna hai",
        "karna hai", "krna hai",
        "karna he", "krna he",
        "mujhe yaad dilana", # ye reminder bhi ho sakta hai — context dekhna
        "ek kaam hai", "ek task hai",
        "important kaam", "zaruri kaam",
        "pending kaam", "baaki kaam",
    ],

    # ── REMINDER PHRASES ───────────────────────────────
    "remind": [
        "yaad dilana", "yaad dila do", "yaad dila",
        "yaad dilao", "yaad krao", "yaad kara",
        "yaad karwa do", "yaad karwa",
        "remind me", "remind karo", "remind kr",
        "remind kar do", "remind karna",
        "reminder set", "reminder lagao",
        "reminder add", "reminder daal",
        "alarm set", "alarm lagao",
        "alarm laga do", "alarm daal",
        "bata dena", "bata do", "bata dena jab",
        "bhool na jao", "bhoolna mat",
        "mat bhoolo", "mat bhoolna",
        "time pe bata", "waqt pe bata",
        "baad mein bata", "baad mein yaad",
        "min mein yaad", "ghante mein yaad",
        "din baad bata", "kal bata",
        "subah bata", "shaam bata",
        "raat ko bata", "dopahar bata",
        "set reminder", "set alarm",
        "add reminder", "add alarm",
        "notify karo", "notify kar",
    ],

    # ── HABIT PHRASES ──────────────────────────────────
    "habit": [
        "habit add", "habit lagao", "habit bana",
        "habit banana", "new habit", "naya habit",
        "habit start", "habit shuru",
        "habit done", "habit complete",
        "habit ho gayi", "habit ho gaya",
        "habit kar li", "habit kar liya",
        "habit log", "habit mark",
        "gym ho gaya", "gym kar liya", "gym kar li",
        "gym done", "gym complete",
        "exercise ho gayi", "exercise kar li",
        "exercise done", "exercise complete",
        "walk ho gayi", "walk kar li",
        "walk done", "walk complete",
        "reading ho gayi", "reading kar li",
        "reading done", "reading complete",
        "meditation ho gayi", "meditation kar li",
        "meditation done",
        "yoga ho gayi", "yoga kar li",
        "yoga done",
        "namaz ho gayi", "namaz kar li",
        "namaz padh li", "namaz padha",
        "quran padha", "quran parha",
        "running done", "running kar li",
        "workout done", "workout kar liya",
    ],

    # ── EXPENSE PHRASES ────────────────────────────────
    "expense": [
        "kharcha hua", "kharcha kiya", "kharcha ho gaya",
        "karcha hua", "karcha kiya",
        "paisa gaya", "paise gaye", "paisa diya",
        "paise diye", "paisa laga", "paise lage",
        "rupees lage", "rupees diye", "rupees gaye",
        "rs laga", "rs diya", "rs gaya",
        "spent on", "spend kiya",
        "pe laga", "pe lagaya", "pe diya",
        "mein lagaya", "mein laga",
        "ka kharcha", "ki payment",
        "bill pay kiya", "pay kiya",
        "kharida", "khareeda", "khareed liya",
        "le liya", "le aaya",
        "add kharcha", "add expense",
        "expense add", "kharcha add",
        "petrol liya", "grocery liya",
        "khana khaya", "chai piya",   # common expenses
    ],

    # ── WATER PHRASES ──────────────────────────────────
    "water": [
        "paani piya", "pani piya",
        "paani pi liya", "pani pi liya",
        "paani pi", "pani pi",
        "paani liya", "pani liya",
        "water piya", "water pi liya",
        "water log", "water add",
        "paani add", "pani add",
        "paani track", "pani track",
        "glass piya", "glass pi liya",
        "bottle piya", "bottle pi li",
        "1 glass", "2 glass", "3 glass",
        "ek glass", "do glass", "teen glass",
        "1 bottle", "2 bottle",
        "250 ml", "500 ml", "1000 ml",
        "paani peena", "pani peena",
    ],

    # ── MEMORY PHRASES ─────────────────────────────────
    "memory": [
        "memory mein save karo", "memory me save karo",
        "memory mein save karo doctor", "memory me save karo",
        "memory mein save", "memory me save",
        "memory mein add", "memory me add",
        "memory mein rakh", "memory me rakh",
        "memory mein daal", "memory me daal",
        "yaad rakhna", "yaad rakh",
        "yaad rakhna hai", "yaad rakhni hai",
        "remember karo", "remember kar",
        "remember rakhna", "note down",
        "dimaag mein rakh", "dimag mein rakh",
        "save kar lo yeh", "yeh save karo",
        "important note", "imp note",
        "memory add", "add memory",
        "store karo", "store kar lo",
        "fact save", "info save",
    ],

    # ── CALENDAR / BIRTHDAY PHRASES ────────────────────
    "calendar": [
        "birthday hai", "birthday add", "birthday save",
        "ka birthday", "ki birthday",
        "birthday kal hai", "birthday aaj hai",
        "janamdin hai", "janamdin add",
        "event add", "event hai", "event save",
        "event kal hai", "event aaj hai",
        "calendar mein add", "cal mein add",
        "schedule mein add", "schedule hai",
        "meeting add", "meeting hai",
        "meeting kal hai", "meeting aaj hai",
        "appointment add", "appointment hai",
        "function hai", "function add",
        "shaadi hai", "marriage hai",
        "anniversary hai", "anniversary add",
        "interview hai", "interview add",
        "exam hai", "exam add",
    ],

    # ── BILL PHRASES ───────────────────────────────────
    "bill": [
        "bill add", "bill lagao", "bill save",
        "bill aya", "bill aaya", "bill aa gaya",
        "subscription add", "sub add",
        "emi add", "emi lagao",
        "loan add", "loan hai",
        "insurance add", "insurance premium",
        "monthly bill", "yearly bill",
        "netflix add", "jio add", "amazon add",
        "bill pay", "bill paid",
        "bill dena hai", "bill dena tha",
    ],

    # ── SHOW / LIST PHRASES ────────────────────────────
    "show": [
        # Expenses show
        "kharcha batao", "kharcha dikhao", "kharcha dekho",
        "expense batao", "expense dikhao",

        # Tasks
        "task dikhao", "tasks dikhao", "task list",
        "task dekho", "task show", "show task",
        "pending task", "pending tasks",
        "meri task", "mera kaam",
        "kya task", "task kya hai", "task batao",
        "saare task", "sare task", "sab task",

        # Reminders
        "reminder dikhao", "reminders dikhao",
        "reminder list", "reminder dekho",
        "reminder show", "show reminder",
        "active reminder", "mera reminder",
        "reminder batao", "alarm dikhao",
        "alarm list", "alarm dekho",
        "kitne reminder", "saare reminder",

        # Habits
        "habit dikhao", "habits dikhao",
        "habit list", "habit dekho",
        "habit show", "show habit",
        "meri habit", "aaj ki habit",
        "habit batao", "kya habit",

        # Diary
        "diary dikhao", "diary dekho",
        "diary padho", "show diary",
        "diary show", "aaj ki diary",
        "meri diary", "diary batao",
        "dairy dikhao", "dairy dekho",
        "purani diary", "poorani diary",
        "saari diary", "all diary",

        # Expenses
        "kharcha dikhao", "expense dikhao",
        "kharcha dekho", "expense list",
        "aaj ka kharcha", "kitna kharcha",
        "total kharcha", "expense batao",

        # Water
        "paani dikhao", "water dikhao",
        "paani kitna", "water status",
        "aaj ka paani", "water goal",

        # Memory
        "memory dikhao", "memory dekho",
        "memory show", "show memory",
        "meri memory", "memory list",
        "kya yaad hai", "yaad hai kya",

        # Calendar
        "calendar dikhao", "events dikhao",
        "events dekho", "upcoming events",
        "aaj ka event", "kal ka event",
        "schedule dikhao", "cal dikhao",

        # Bills
        "bills dikhao", "bill list",
        "bill dekho", "pending bills",
        "unpaid bills", "bills batao",

        # Habits Status
        "aaj kya kiya", "kya kiya aaj",
        "progress dikhao", "status batao",
        "summary dikhao", "briefing",
    ],
}


# ══════════════════════════════════════════════════════
# TIME PARSER — Reminder ke liye time nikalna
# ══════════════════════════════════════════════════════

def parse_time(text: str, now_ist_func=None):
    """
    Text se time/date parse karo.
    Returns: datetime object ya None
    """
    from datetime import datetime, timedelta
    
    if now_ist_func:
        now = now_ist_func()
    else:
        from datetime import timezone
        IST = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(IST)

    lower = text.lower()

    # ── RELATIVE TIME ──
    # X minutes baad
    m = re.search(r'(\d+)\s*(?:minute|minutes|min|mins|m)\s*(?:baad|mein|main|after|ke baad)?', lower)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    # X ghante / hours baad
    m = re.search(r'(\d+)\s*(?:hour|hours|hr|hrs|ghanta|ghante)\s*(?:baad|mein|main|after|ke baad)?', lower)
    if m:
        return now + timedelta(hours=int(m.group(1)))

    # X seconds baad
    m = re.search(r'(\d+)\s*(?:second|seconds|sec|secs)\s*(?:baad|mein|main|after|ke baad)?', lower)
    if m:
        return now + timedelta(seconds=int(m.group(1)))

    # X din baad
    m = re.search(r'(\d+)\s*(?:day|days|din|dino)\s*(?:baad|mein|main|after|ke baad)?', lower)
    if m:
        return now + timedelta(days=int(m.group(1)))

    # ── SPECIFIC TIME ──
    # HH:MM format
    m = re.search(r'(\d{1,2}):(\d{2})', lower)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        dt = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if dt < now:
            dt += timedelta(days=1)
        return dt

    # X baje / AM / PM
    m = re.search(r'(\d{1,2})\s*(?:baje|bajay|am|pm|subah|shaam|raat|morning|evening|night)', lower)
    if m:
        h = int(m.group(1))
        is_pm = any(x in lower for x in ['pm', 'shaam', 'raat', 'evening', 'night'])
        is_am = any(x in lower for x in ['am', 'subah', 'morning'])
        if is_pm and h != 12:
            h += 12
        elif is_am and h == 12:
            h = 0
        dt = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if dt < now:
            dt += timedelta(days=1)
        return dt

    # ── RELATIVE DAYS ──
    if any(x in lower for x in ['kal', 'tomorrow', 'kl']):
        dt = now + timedelta(days=1)
        # Time bhi check karo
        m = re.search(r'(\d{1,2})\s*(?:baje|am|pm)', lower)
        if m:
            h = int(m.group(1))
            if 'pm' in lower and h != 12:
                h += 12
            return dt.replace(hour=h, minute=0, second=0, microsecond=0)
        return dt.replace(hour=9, minute=0, second=0, microsecond=0)

    if any(x in lower for x in ['aaj', 'today', 'abhi']):
        m = re.search(r'(\d{1,2})\s*(?:baje|am|pm)', lower)
        if m:
            h = int(m.group(1))
            if 'pm' in lower and h != 12:
                h += 12
            dt = now.replace(hour=h, minute=0, second=0, microsecond=0)
            if dt < now:
                dt += timedelta(days=1)
            return dt

    if 'parso' in lower:
        return now + timedelta(days=2)

    # ── DEFAULT ── 5 minutes baad
    return None


# ══════════════════════════════════════════════════════
# AMOUNT PARSER — Expense ke liye amount nikalna
# ══════════════════════════════════════════════════════

def parse_amount(text: str):
    """Text se amount nikalo"""
    # Rs. 500 ya 500 rs ya just 500
    m = re.search(r'(?:rs\.?\s*|rupees?\s*|₹\s*)?(\d+(?:\.\d+)?)\s*(?:rs\.?|rupees?|₹)?', text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


# ══════════════════════════════════════════════════════
# WATER AMOUNT PARSER
# ══════════════════════════════════════════════════════

def parse_water_amount(text: str):
    """Text se water amount ML mein nikalo"""
    lower = text.lower()

    # Direct ML
    m = re.search(r'(\d+)\s*ml', lower)
    if m:
        return int(m.group(1))

    # Glass
    m = re.search(r'(\d+)\s*(?:glass|glasses|gilas)', lower)
    if m:
        return int(m.group(1)) * 250

    # Bottle
    m = re.search(r'(\d+)\s*(?:bottle|bottles)', lower)
    if m:
        return int(m.group(1)) * 500

    # Words
    word_map = {
        'ek': 1, 'do': 2, 'teen': 3, 'char': 4,
        'paanch': 5, 'chhe': 6, 'saat': 7, 'aath': 8
    }
    for word, num in word_map.items():
        if word in lower and 'glass' in lower:
            return num * 250

    # Default
    if any(x in lower for x in ['piya', 'pi liya', 'pi', 'liya']):
        return 250

    return 250  # Default 1 glass


# ══════════════════════════════════════════════════════
# MAIN PARSER FUNCTION
# ══════════════════════════════════════════════════════

def parse_command(user_msg: str, now_ist_func=None):
    """
    Main parser — user message se action detect karo.
    
    Returns:
        (action_type, params_dict)
    
    Action types:
        "diary", "task", "remind", "habit", "habit_done",
        "expense", "water", "memory", "calendar", "bill",
        "complete", "show_tasks", "show_reminders", 
        "show_habits", "show_diary", "show_all_diary",
        "show_expense", "show_water", "show_memory",
        "show_calendar", "show_bills", "unknown"
    """

    if not user_msg or not user_msg.strip():
        return ("unknown", {})

    original = user_msg.strip()
    lower = original.lower().strip()

    # ── STEP 1: PHRASE PATTERN CHECK (highest priority) ──
    for action, phrases in PHRASE_PATTERNS.items():
        for phrase in phrases:
            if lower.startswith(phrase) or phrase in lower[:50]:
                # Match mila — ab action specific parsing
                remaining = _remove_phrase(lower, phrase)
                return _build_result(action, remaining, original, now_ist_func)

    # ── STEP 2: FIRST WORD CHECK ──
    words = lower.split()
    if words:
        first = words[0]

        # Direct match
        if first in FIRST_WORD_MAP:
            action = FIRST_WORD_MAP[first]
            remaining = " ".join(words[1:])
            return _build_result(action, remaining, original, now_ist_func)

        # Two word first check
        if len(words) >= 2:
            two_words = words[0] + " " + words[1]
            if two_words in FIRST_WORD_MAP:
                action = FIRST_WORD_MAP[two_words]
                remaining = " ".join(words[2:])
                return _build_result(action, remaining, original, now_ist_func)

    # ── STEP 3: AMOUNT ONLY (expense shorthand) ──
    # "200 chai", "500 petrol" — sirf number + description
    m = re.match(r'^(\d+(?:\.\d+)?)\s+(.+)$', lower)
    if m:
        amount = float(m.group(1))
        desc = m.group(2).strip()
        # Check karo koi action word toh nahi
        action_words = list(FIRST_WORD_MAP.keys())
        if not any(aw in desc for aw in action_words):
            return ("expense", {
                "amount": amount,
                "desc": desc.title(),
                "raw": original
            })

    # ── STEP 4: SPECIAL PATTERNS ──

    # "done X" — task complete
    m = re.match(r'^done\s+(\d+)$', lower)
    if m:
        return ("complete", {"id": int(m.group(1)), "raw": original})

    # "r 10m medicine" — quick reminder
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
        return ("remind", {
            "text": text.title(),
            "due": due.strftime("%Y-%m-%d %H:%M:%S"),
            "raw": original
        })

    return ("unknown", {"raw": original})


# ══════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════

def _remove_phrase(text: str, phrase: str) -> str:
    """Text se phrase remove karo aur remaining return karo"""
    result = text.replace(phrase, "", 1).strip()
    # Clean up extra words
    clean_words = [
        "karo", "kro", "kr", "do", "kar", "de", "dena",
        "hai", "hain", "tha", "thi", "the",
        "mein", "me", "main", "mujhe", "mera", "meri",
        "please", "plz", "zara", "jaldi", "abhi"
    ]
    for cw in clean_words:
        result = re.sub(r'\b' + re.escape(cw) + r'\b', '', result, flags=re.IGNORECASE)
    return " ".join(result.split()).strip()


def _get_now():
    """Fallback now function"""
    from datetime import datetime, timedelta, timezone
    IST = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(IST)


def _build_result(action: str, remaining: str, original: str, now_ist_func=None):
    """Action aur remaining text se result build karo"""

    now_func = now_ist_func or _get_now

    # ── DIARY ──
    if action == "diary":
        text = remaining.strip() or original
        return ("diary", {
            "text": text,
            "raw": original
        })

    # ── TASK ──
    elif action == "task":
        title = remaining.strip() or original
        # Remove action words
        for kw in ["add", "karo", "kro", "lagao", "likh", "banana",
                   "bana", "naya", "new", "karna", "krna"]:
            title = re.sub(r'\b' + re.escape(kw) + r'\b', '', title, flags=re.IGNORECASE)
        title = " ".join(title.split()).strip()
        return ("task", {
            "title": title[:100] or "Task",
            "raw": original
        })

    # ── REMINDER ──
    elif action == "remind":
        due_dt = parse_time(original, now_func)
        if not due_dt:
            # Default 5 min
            due_dt = now_func() + timedelta(minutes=5)

        # Text nikalo — time words hata ke
        text = remaining or original
        time_words = [
            "remind", "reminder", "alarm", "yaad", "dilana", "dila",
            "bata", "do", "dena", "set", "lagao", "add",
            "kal", "aaj", "parso", "subah", "shaam", "raat",
            "baje", "bajay", "am", "pm", "mein", "me", "ko", "pe",
            "min", "minute", "ghante", "ghanta", "hour", "din", "baad"
        ]
        for tw in time_words:
            text = re.sub(r'\b' + re.escape(tw) + r'\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\d+', '', text)
        text = " ".join(text.split()).strip()

        return ("remind", {
            "text": text.title() or "Reminder",
            "due": due_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "raw": original
        })

    # ── HABIT (add) ──
    elif action == "habit":
        name = remaining.strip()
        for kw in ["add", "lagao", "bana", "banana", "start", "shuru",
                   "naya", "new", "karo", "kro", "done", "complete",
                   "ho gaya", "ho gayi", "kar liya", "kar li"]:
            name = re.sub(r'\b' + re.escape(kw) + r'\b', '', name, flags=re.IGNORECASE)
        name = " ".join(name.split()).strip()

        # Done check
        done_words = ["done", "complete", "ho gayi", "ho gaya", "kar li",
                      "kar liya", "ho gyi", "ho gya", "karli", "karliya"]
        is_done = any(dw in original.lower() for dw in done_words)

        if is_done:
            # Habit complete log - name properly set karo
            habit_name = name
            if not habit_name or len(habit_name) < 2:
                # Original se nikalo
                done_remove = ["done", "complete", "ho gayi", "ho gaya", "kar li",
                               "kar liya", "ho gyi", "ho gya", "karli", "karliya",
                               "aaj", "kal", "abhi"]
                habit_name = original.lower()
                for dr in done_remove:
                    habit_name = habit_name.replace(dr, "").strip()
                habit_name = " ".join(habit_name.split()).strip()
            return ("habit_done", {
                "keyword": habit_name or original,
                "raw": original
            })
        else:
            # Habit add
            return ("habit", {
                "name": name[:80] or "Habit",
                "raw": original
            })

    # ── EXPENSE ──
    elif action == "expense":
        amount = parse_amount(original)
        if not amount:
            amount = parse_amount(remaining)

        # Description nikalo
        desc = remaining or original
        for kw in ["kharcha", "karcha", "kharch", "karch", "paisa", "paise",
                   "rs", "rs.", "rupees", "rupaye", "rupaya", "spent", "laga",
                   "lagaya", "diya", "expense", "add", "karo", "kr"]:
            desc = re.sub(r'\b' + re.escape(kw) + r'\b', '', desc, flags=re.IGNORECASE)
        if amount:
            desc = desc.replace(str(int(amount)), "").replace(str(amount), "")
        desc = " ".join(desc.split()).strip()

        return ("expense", {
            "amount": amount or 0,
            "desc": desc.title() or "Expense",
            "raw": original
        })

    # ── WATER ──
    elif action == "water":
        ml = parse_water_amount(original)
        return ("water", {
            "ml": ml,
            "raw": original
        })

    # ── MEMORY ──
    elif action == "memory":
        text = remaining.strip() or original
        for kw in ["memory", "save", "karo", "kr", "rakh", "add",
                   "mein", "me", "yaad", "rakhna", "remember"]:
            text = re.sub(r'\b' + re.escape(kw) + r'\b', '', text, flags=re.IGNORECASE)
        text = " ".join(text.split()).strip()
        return ("memory", {
            "text": text or original,
            "raw": original
        })

    # ── CALENDAR ──
    elif action == "calendar":
        # Date parse karo
        date_found = _parse_date_simple(original)
        title = remaining or original
        for kw in ["birthday", "bday", "event", "calendar", "cal",
                   "add", "save", "hai", "ka", "ki", "ke", "mein",
                   "schedule", "meeting", "appointment"]:
            title = re.sub(r'\b' + re.escape(kw) + r'\b', '', title, flags=re.IGNORECASE)
        title = " ".join(title.split()).strip()

        is_bday = any(w in original.lower() for w in
                      ["birthday", "bday", "janamdin", "janmdin"])

        return ("calendar", {
            "title": title or "Event",
            "date": date_found,
            "type": "birthday" if is_bday else "event",
            "raw": original
        })

    # ── BILL ──
    elif action == "bill":
        amount = parse_amount(original)
        name = remaining or original
        for kw in ["bill", "bills", "subscription", "emi", "loan",
                   "add", "lagao", "save", "naya", "new"]:
            name = re.sub(r'\b' + re.escape(kw) + r'\b', '', name, flags=re.IGNORECASE)
        if amount:
            name = name.replace(str(int(amount)), "").replace(str(amount), "")
        name = " ".join(name.split()).strip()

        # Due day check
        due_day = 0
        m = re.search(r'(\d{1,2})\s*(?:tarikh|taarikh|date|th|st|nd|rd)', original.lower())
        if m:
            candidate = int(m.group(1))
            if 1 <= candidate <= 31:
                due_day = candidate

        return ("bill", {
            "name": name or "Bill",
            "amount": amount or 0,
            "due_day": due_day,
            "raw": original
        })

    # ── COMPLETE (task done) ──
    elif action == "complete":
        m = re.search(r'#?(\d+)', original)
        task_id = int(m.group(1)) if m else None
        return ("complete", {
            "id": task_id,
            "hint": original,
            "raw": original
        })

    # ── SHOW ──
    elif action == "show":
        lower_orig = original.lower()

        # Kya dikhana hai detect karo
        if any(x in lower_orig for x in ["task", "kaam", "todo", "pending"]):
            return ("show_tasks", {"raw": original})

        elif any(x in lower_orig for x in ["reminder", "alarm", "yaad"]):
            return ("show_reminders", {"raw": original})

        elif any(x in lower_orig for x in ["habit", "routine"]):
            return ("show_habits", {"raw": original})

        elif any(x in lower_orig for x in
                 ["purani diary", "poorani diary", "saari diary", "all diary",
                  "purani dairy", "saari dairy"]):
            return ("show_all_diary", {"raw": original})

        elif any(x in lower_orig for x in ["diary", "dairy", "note"]):
            return ("show_diary", {"raw": original})

        elif any(x in lower_orig for x in ["memory", "yaad hai"]):
            return ("show_memory", {"raw": original})

        elif any(x in lower_orig for x in ["calendar", "event", "schedule", "birthday"]):
            return ("show_calendar", {"raw": original})

        elif any(x in lower_orig for x in ["bill", "subscription", "emi"]):
            return ("show_bills", {"raw": original})

        elif any(x in lower_orig for x in ["kharcha", "expense", "paisa"]):
            return ("show_expense", {"raw": original})

        elif any(x in lower_orig for x in ["paani", "pani", "water"]):
            return ("show_water", {"raw": original})

        else:
            return ("show_tasks", {"raw": original})  # Default

    return ("unknown", {"raw": original})


def _parse_date_simple(text: str):
    """Simple date parser for calendar"""
    lower = text.lower()
    today_d = _get_now().date()

    MONTH_MAP = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
        "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4,
        "june": 6, "july": 7, "august": 8, "september": 9,
        "october": 10, "november": 11, "december": 12,
    }

    # YYYY-MM-DD
    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', lower)
    if m:
        try:
            from datetime import date
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
        except:
            pass

    # DD Month YYYY
    month_pattern = "|".join(MONTH_MAP.keys())
    m = re.search(r'(\d{1,2})\s+(' + month_pattern + r')(?:\s+(\d{4}))?', lower)
    if m:
        try:
            from datetime import date
            day = int(m.group(1))
            mon = MONTH_MAP.get(m.group(2)[:3], 0)
            yr = int(m.group(3)) if m.group(3) else today_d.year
            if mon:
                return date(yr, mon, day).strftime("%Y-%m-%d")
        except:
            pass

    # Relative
    if "kal" in lower:
        return (today_d + timedelta(days=1)).strftime("%Y-%m-%d")
    if "aaj" in lower:
        return today_d.strftime("%Y-%m-%d")

    return today_d.strftime("%Y-%m-%d")


# ══════════════════════════════════════════════════════
# BOT.PY INTEGRATION — Yahan se call karo
# ══════════════════════════════════════════════════════

def get_action(user_msg: str, now_ist_func=None):
    """
    Bot.py mein use karne ke liye main function.
    
    Usage in bot.py:
        from command_parser import get_action
        
        action, params = get_action(user_msg, now_ist)
        
        if action == "diary":
            diary.add(params["text"])
        elif action == "task":
            tasks.add(params["title"])
        elif action == "remind":
            reminders.add(chat_id, params["text"], params["due"])
        # ... etc
    """
    return parse_command(user_msg, now_ist_func)


# ══════════════════════════════════════════════════════
# TEST — Directly run karke check karo
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    test_messages = [
        # DIARY
        "diary aaj mausam bahut acha tha",
        "dairy mein likho aaj office mein meeting hui",
        "note karo kal doctor ne kaha dawai leni hai",
        "likh lo petrol pump band tha",
        "save karo important document ready hai",

        # TASK
        "task doctor appointment kal",
        "kaam karna hai market jaana",
        "todo add grocery lana hai",
        "karna hai ghar ki safai",
        "mujhe kal bank jaana hai",

        # REMINDER
        "yaad dilana kal 9 baje meeting hai",
        "remind me 30 min mein chai",
        "alarm set karo kal subah 6 baje",
        "bata dena shaam 5 baje doctor appointment",
        "30 min baad yaad dilana medicine",
        "kal 9 am ko yaad dilana",

        # HABIT
        "habit gym add karo",
        "gym ho gaya aaj",
        "exercise kar li",
        "namaz ho gayi",
        "habit yoga done",

        # EXPENSE
        "kharcha 200 petrol",
        "paisa 500 grocery mein laga",
        "rs 150 chai aur samosa",
        "200 chai",
        "spent 1000 on shoes",

        # WATER
        "paani 2 glass piya",
        "water 500ml",
        "pani pi liya ek bottle",
        "paani piya",

        # MEMORY
        "memory mein save karo doctor ka number 9876543210",
        "yaad rakhna kal interview hai",
        "remember karo password abc123",

        # CALENDAR
        "birthday add simran ki 9 sep 2000",
        "meeting add kal 3 baje",
        "event add shaadi 15 june",

        # BILL
        "bill add netflix 499 15 tarikh",
        "emi add 5000 home loan",

        # SHOW
        "task dikhao",
        "reminder list",
        "saari diary dikhao",
        "kharcha batao aaj ka",
        "habit dekho",
        "memory dikhao",

        # COMPLETE
        "done 3",
        "task complete kar liya 5",

        # QUICK
        "r 10m medicine lena",
    ]

    print("=" * 60)
    print("COMMAND PARSER TEST")
    print("=" * 60)

    for msg in test_messages:
        action, params = parse_command(msg)
        print(f"\n📩 Input : {msg}")
        print(f"   Action: {action}")
        key_params = {k: v for k, v in params.items() if k != 'raw'}
        print(f"   Params: {key_params}")

    print("\n" + "=" * 60)
    print("✅ Test Complete!")
