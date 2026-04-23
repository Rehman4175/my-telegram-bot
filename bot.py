"""
╔══════════════════════════════════════════════════════╗
║       PERSONAL AI ASSISTANT — MERGED BEST v4.0       ║
║  100% FREE | Gemini Multi-Model | News | Smart Memory ║
║  Auto-Fallback | 24/7 Ready | Chat Clear + Remember  ║
╚══════════════════════════════════════════════════════╝
"""

import os, json, logging, time, urllib.request, urllib.error
from datetime import datetime, date, timedelta
from xml.etree import ElementTree as ET

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ══════════════════════════════════════════════
# LOGGING — File + Console dono mein
# ══════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# CONFIG — Environment variables se keys lo
# ══════════════════════════════════════════════
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "APNA_TOKEN_YAHAN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "APNI_KEY_YAHAN")

# 🔥 MULTI-MODEL FALLBACK — agar ek busy ho toh doosra try karo
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-8b",
]

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

# ══════════════════════════════════════════════
# FILE PATHS
# ══════════════════════════════════════════════
DATA = "data"
os.makedirs(DATA, exist_ok=True)

F_MEMORY   = f"{DATA}/memory.json"
F_TASKS    = f"{DATA}/tasks.json"
F_DIARY    = f"{DATA}/diary.json"
F_HABITS   = f"{DATA}/habits.json"
F_NOTES    = f"{DATA}/notes.json"
F_EXPENSES = f"{DATA}/expenses.json"
F_GOALS    = f"{DATA}/goals.json"
F_CHAT     = f"{DATA}/chat_history.json"   # Chat alag — clear ho sakti hai
F_NEWS     = f"{DATA}/news_cache.json"
F_REMINDERS = f"{DATA}/reminders.json"

# ══════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════
def load(path, default=None):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"Load error {path}: {e}")
    return default if default is not None else {}

def save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Save error {path}: {e}")

def today_str():     return date.today().isoformat()
def now_str():       return datetime.now().strftime("%H:%M")
def yesterday_str(): return (date.today() - timedelta(days=1)).isoformat()

# ══════════════════════════════════════════════
# 🔥 GEMINI MULTI-MODEL CALLER (503 proof!)
# ══════════════════════════════════════════════
def call_gemini(system_prompt: str, messages: list, retries=2) -> str:
    """
    Multiple models try karta hai automatically.
    503/429 pe next model pe switch karta hai.
    """
    contents = [
        {"role": "user",  "parts": [{"text": f"[SYSTEM]\n{system_prompt}\n[/SYSTEM]\n\nReady ho?"}]},
        {"role": "model", "parts": [{"text": "Haan ready hoon! Batao."}]},
    ]
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    payload = json.dumps({
        "contents": contents,
        "generationConfig": {"temperature": 0.75, "maxOutputTokens": 700}
    }).encode("utf-8")

    errors = []
    for model in GEMINI_MODELS:
        for attempt in range(retries):
            try:
                url = BASE_URL.format(model=model, key=GEMINI_API_KEY)
                req = urllib.request.Request(
                    url, data=payload,
                    headers={"Content-Type": "application/json"}, method="POST"
                )
                with urllib.request.urlopen(req, timeout=25) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    text = result["candidates"][0]["content"]["parts"][0]["text"]
                    log.info(f"✅ Model used: {model}")
                    return text

            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8")
                log.warning(f"Model {model} attempt {attempt+1}: HTTP {e.code}")
                if e.code in (503, 429, 500):
                    errors.append(f"{model}: overloaded")
                    time.sleep(1.5)
                    continue
                elif e.code == 404:
                    errors.append(f"{model}: not found")
                    break
                elif "API_KEY_INVALID" in body:
                    return "❌ Gemini key galat hai! aistudio.google.com se sahi key lo."
                elif "QUOTA_EXCEEDED" in body:
                    return "⚠️ Aaj ki limit ho gayi. Kal phir try karo (free mein 1000 requests/day)."
                else:
                    return f"❌ API Error {e.code}: {body[:150]}"
            except Exception as e:
                log.warning(f"Model {model}: {e}")
                errors.append(str(e))
                break

    return ("⚠️ Abhi sab Gemini models busy hain (high demand).\n"
            "30 second mein dobara try karo! Main theek hoon, bas Google server thoda busy hai. 😅\n\n"
            f"_Tried: {', '.join(GEMINI_MODELS)}_")

# ══════════════════════════════════════════════
# FREE NEWS via RSS (No API key needed!)
# ══════════════════════════════════════════════
NEWS_FEEDS = {
    "India":      "https://feeds.bbci.co.uk/hindi/rss.xml",
    "Technology": "https://feeds.feedburner.com/ndtvnews-tech-news",
    "Business":   "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "World":      "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Sports":     "https://feeds.bbci.co.uk/sport/rss.xml",
}

def fetch_news(category="India", max_items=5) -> list:
    """RSS se free news — koi API key nahi chahiye"""
    cache = load(F_NEWS, {"cache": {}, "updated": {}})
    now_ts = time.time()

    # Cache check — 30 min se purana ho toh fresh fetch
    if (category in cache["cache"] and
        now_ts - cache["updated"].get(category, 0) < 1800):
        return cache["cache"][category][:max_items]

    url = NEWS_FEEDS.get(category, NEWS_FEEDS["India"])
    items = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            tree = ET.parse(resp)
            root = tree.getroot()
            channel = root.find("channel")
            if channel is None: channel = root
            for item in channel.findall("item")[:max_items]:
                title = item.findtext("title", "").strip()
                desc  = item.findtext("description", "").strip()
                link  = item.findtext("link", "").strip()
                pub   = item.findtext("pubDate", "").strip()
                if title:
                    items.append({"title": title, "desc": desc[:120], "link": link, "pub": pub})
    except Exception as e:
        log.warning(f"News fetch error: {e}")
        return [{"title": "News abhi available nahi", "desc": str(e), "link": "", "pub": ""}]

    cache["cache"][category] = items
    cache["updated"][category] = now_ts
    save(F_NEWS, cache)
    return items

# ══════════════════════════════════════════════
# CHAT HISTORY (separately managed — /clear se sirf yahi hategi)
# ══════════════════════════════════════════════
class ChatHistory:
    def __init__(self):
        self.data = load(F_CHAT, {"history": [], "cleared_at": None})

    def add(self, role: str, content: str):
        self.data["history"].append({
            "role": role, "content": content,
            "time": datetime.now().isoformat()
        })
        self.data["history"] = self.data["history"][-80:]
        save(F_CHAT, self.data)

    def get_recent(self, n=20) -> list:
        return [{"role": m["role"], "content": m["content"]}
                for m in self.data["history"][-n:]]

    def clear(self):
        count = len(self.data["history"])
        self.data["history"] = []
        self.data["cleared_at"] = datetime.now().isoformat()
        save(F_CHAT, self.data)
        return count

    def count(self):
        return len(self.data["history"])

# ══════════════════════════════════════════════
# MEMORY (permanent — chat clear se safe!)
# ══════════════════════════════════════════════
class Memory:
    def __init__(self):
        self.data = load(F_MEMORY, {"facts": [], "prefs": {}, "dates": {}})

    def save_data(self): save(F_MEMORY, self.data)

    def add_fact(self, fact):
        self.data["facts"].append({"f": fact, "d": today_str()})
        self.data["facts"] = self.data["facts"][-300:]
        self.save_data()

    def set_pref(self, k, v):
        self.data["prefs"][k] = v; self.save_data()

    def context(self):
        facts = "\n".join(f"• {x['f']}" for x in self.data["facts"][-25:]) or "Kuch nahi"
        prefs = "\n".join(f"• {k}: {v}" for k, v in self.data["prefs"].items()) or "Kuch nahi"
        dates = "\n".join(f"• {k}: {v}" for k, v in self.data["dates"].items()) or "Kuch nahi"
        return f"FACTS:\n{facts}\n\nPREFERENCES:\n{prefs}\n\nIMPORTANT DATES:\n{dates}"

# ══════════════════════════════════════════════
# TASKS
# ══════════════════════════════════════════════
class Tasks:
    def __init__(self):
        self.data = load(F_TASKS, {"list": [], "counter": 0})

    def save_data(self): save(F_TASKS, self.data)

    def add(self, title, priority="medium", due=None):
        self.data["counter"] += 1
        t = {"id": self.data["counter"], "title": title,
             "priority": priority, "due": due or today_str(),
             "done": False, "done_at": None,
             "created": datetime.now().isoformat()}
        self.data["list"].append(t); self.save_data(); return t

    def complete(self, tid):
        for t in self.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True; t["done_at"] = datetime.now().isoformat()
                self.save_data(); return t
        return None

    def delete(self, tid):
        self.data["list"] = [t for t in self.data["list"] if t["id"] != tid]
        self.save_data()

    def clear_done(self):
        before = len(self.data["list"])
        self.data["list"] = [t for t in self.data["list"] if not t["done"]]
        self.save_data()
        return before - len(self.data["list"])

    def pending(self):    return [t for t in self.data["list"] if not t["done"]]
    def done_on(self, d): return [t for t in self.data["list"] if t["done"] and (t.get("done_at","") or "")[:10] == d]
    def today_pending(self):
        td = today_str()
        return [t for t in self.data["list"] if not t["done"] and t.get("due","") <= td]

# ══════════════════════════════════════════════
# DIARY
# ══════════════════════════════════════════════
class Diary:
    def __init__(self):
        self.data = load(F_DIARY, {"entries": {}})

    def save_data(self): save(F_DIARY, self.data)

    def add(self, content, mood="😊"):
        td = today_str()
        self.data["entries"].setdefault(td, [])
        self.data["entries"][td].append({"text": content, "mood": mood, "time": now_str()})
        self.save_data()

    def get(self, d): return self.data["entries"].get(d, [])

# ══════════════════════════════════════════════
# HABITS
# ══════════════════════════════════════════════
class Habits:
    def __init__(self):
        self.data = load(F_HABITS, {"list": [], "logs": {}, "counter": 0})

    def save_data(self): save(F_HABITS, self.data)

    def add(self, name, emoji="✅"):
        self.data["counter"] += 1
        h = {"id": self.data["counter"], "name": name, "emoji": emoji, "streak": 0}
        self.data["list"].append(h); self.save_data(); return h

    def delete(self, hid):
        self.data["list"] = [h for h in self.data["list"] if h["id"] != hid]
        self.save_data()

    def log(self, hid):
        td = today_str()
        self.data["logs"].setdefault(td, [])
        if hid in self.data["logs"][td]: return False, 0
        self.data["logs"][td].append(hid)
        yd = yesterday_str()
        streak = 0
        for h in self.data["list"]:
            if h["id"] == hid:
                h["streak"] = h["streak"] + 1 if hid in self.data["logs"].get(yd, []) else 1
                streak = h["streak"]
        self.save_data(); return True, streak

    def today_status(self):
        done_ids = self.data["logs"].get(today_str(), [])
        return ([h for h in self.data["list"] if h["id"] in done_ids],
                [h for h in self.data["list"] if h["id"] not in done_ids])

    def all(self): return self.data["list"]

# ══════════════════════════════════════════════
# NOTES
# ══════════════════════════════════════════════
class Notes:
    def __init__(self):
        self.data = load(F_NOTES, {"list": [], "counter": 0})

    def save_data(self): save(F_NOTES, self.data)

    def add(self, content, tag="general"):
        self.data["counter"] += 1
        n = {"id": self.data["counter"], "text": content, "tag": tag,
             "created": datetime.now().isoformat()}
        self.data["list"].append(n); self.save_data(); return n

    def recent(self, n=15): return self.data["list"][-n:]

    def delete(self, nid):
        self.data["list"] = [n for n in self.data["list"] if n["id"] != nid]
        self.save_data()

# ══════════════════════════════════════════════
# EXPENSES
# ══════════════════════════════════════════════
class Expenses:
    def __init__(self):
        self.data = load(F_EXPENSES, {"list": [], "counter": 0, "budget": None})

    def save_data(self): save(F_EXPENSES, self.data)

    def add(self, amount, desc, category="general"):
        self.data["counter"] += 1
        e = {"id": self.data["counter"], "amount": amount,
             "desc": desc, "category": category,
             "date": today_str(), "time": now_str()}
        self.data["list"].append(e); self.save_data(); return e

    def set_budget(self, amount):
        self.data["budget"] = amount; self.save_data()

    def budget_left(self):
        if self.data["budget"] is None: return None
        return self.data["budget"] - self.month_total()

    def today_total(self): return sum(e["amount"] for e in self.data["list"] if e["date"] == today_str())
    def month_total(self):
        m = today_str()[:7]
        return sum(e["amount"] for e in self.data["list"] if e["date"][:7] == m)
    def today_list(self): return [e for e in self.data["list"] if e["date"] == today_str()]

# ══════════════════════════════════════════════
# GOALS
# ══════════════════════════════════════════════
class Goals:
    def __init__(self):
        self.data = load(F_GOALS, {"list": [], "counter": 0})

    def save_data(self): save(F_GOALS, self.data)

    def add(self, title, deadline=None):
        self.data["counter"] += 1
        g = {"id": self.data["counter"], "title": title,
             "deadline": deadline or "", "progress": 0,
             "done": False, "created": today_str()}
        self.data["list"].append(g); self.save_data(); return g

    def update_progress(self, gid, pct):
        for g in self.data["list"]:
            if g["id"] == gid:
                g["progress"] = min(100, max(0, pct))
                if g["progress"] == 100: g["done"] = True
                self.save_data(); return g
        return None

    def active(self): return [g for g in self.data["list"] if not g["done"]]

# ══════════════════════════════════════════════
# 🔔 REMINDERS & ALARMS
# ══════════════════════════════════════════════
class Reminders:
    def __init__(self):
        self.data = load(F_REMINDERS, {"list": [], "counter": 0, "daily_alarms": []})

    def save_data(self): save(F_REMINDERS, self.data)

    def add(self, text, remind_at_iso, chat_id, job_id=None):
        self.data["counter"] += 1
        r = {
            "id": self.data["counter"],
            "text": text,
            "remind_at": remind_at_iso,
            "chat_id": chat_id,
            "done": False,
            "job_id": job_id or f"remind_{self.data['counter']}",
            "created": datetime.now().isoformat()
        }
        self.data["list"].append(r)
        self.save_data()
        return r

    def add_alarm(self, time_str, text, chat_id):
        """Daily repeating alarm — HH:MM format"""
        self.data["counter"] += 1
        a = {
            "id": self.data["counter"],
            "time": time_str,
            "text": text,
            "chat_id": chat_id,
            "active": True,
            "job_id": f"alarm_{self.data['counter']}",
            "created": datetime.now().isoformat()
        }
        self.data["daily_alarms"].append(a)
        self.save_data()
        return a

    def mark_done(self, rid):
        for r in self.data["list"]:
            if r["id"] == rid:
                r["done"] = True
                self.save_data()
                return True
        return False

    def delete(self, rid):
        before = len(self.data["list"]) + len(self.data["daily_alarms"])
        self.data["list"] = [r for r in self.data["list"] if r["id"] != rid]
        self.data["daily_alarms"] = [a for a in self.data["daily_alarms"] if a["id"] != rid]
        self.save_data()
        return before > len(self.data["list"]) + len(self.data["daily_alarms"])

    def stop_alarm(self, aid):
        for a in self.data["daily_alarms"]:
            if a["id"] == aid:
                a["active"] = False
                self.save_data()
                return True
        return False

    def pending(self):
        return [r for r in self.data["list"] if not r["done"]]

    def active_alarms(self):
        return [a for a in self.data["daily_alarms"] if a["active"]]

    def all_upcoming(self):
        result = []
        for r in self.data["list"]:
            if not r["done"]:
                result.append({"type": "remind", **r})
        for a in self.data["daily_alarms"]:
            if a["active"]:
                result.append({"type": "alarm", **a})
        return result


# ══════════════════════════════════════════════
# INIT — Sab objects bana lo
# ══════════════════════════════════════════════
chat_hist = ChatHistory()
mem      = Memory()
tasks    = Tasks()
diary    = Diary()
habits   = Habits()
notes    = Notes()
expenses = Expenses()
goals    = Goals()
reminders = Reminders()

# ══════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════
def build_system_prompt():
    now_label = datetime.now().strftime("%A, %d %B %Y — %I:%M %p")
    tp = tasks.today_pending()
    tasks_txt = "\n".join(f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}" for t in tp[:8]) or "  Koi nahi"
    yd_done = tasks.done_on(yesterday_str())
    yd_txt = "\n".join(f"  ✓ {t['title']}" for t in yd_done[:6]) or "  Koi nahi"
    hd, hp = habits.today_status()
    exp_today = expenses.today_total()
    exp_month = expenses.month_total()
    ag = goals.active()
    goals_txt = "\n".join(f"  🎯 {g['title']} ({g['progress']}%)" for g in ag[:4]) or "  Koi nahi"
    td_diary = diary.get(today_str())
    diary_txt = "\n".join(f"  {e['time']} {e['text']}" for e in td_diary[-3:]) or "  Kuch nahi"

    return f"""Tu mera Personal AI Assistant hai. Naam: "Dost".
Hamesha Hindi ya Hinglish mein baat kar. Bilkul close dost ki tarah — warm, helpful, casual.

ABHI: {now_label}

AAJ KE PENDING TASKS:
{tasks_txt}

KAL KYA KIYA:
{yd_txt}

HABITS AAJ:
  Done: {', '.join(h['name'] for h in hd) or 'Koi nahi'}
  Baaki: {', '.join(h['name'] for h in hp) or 'Sab ho gaye!'}

AAJ KI DIARY:
{diary_txt}

KHARCHA: Aaj ₹{exp_today} | Mahina ₹{exp_month}

GOALS:
{goals_txt}

YAADDASHT:
{mem.context()}

RULES:
- Hamesha Hindi/Hinglish mein jawab de
- Dost ki tarah baat kar, "As an AI" kabhi mat bol
- Jo yaad hai use naturally use kar
- Short, clear, helpful reh
- Emojis freely use kar
- Kabhi bhi payment ya upgrade suggest mat kar — sab free hai
"""

# ══════════════════════════════════════════════
# AI CHAT FUNCTION
# ══════════════════════════════════════════════
async def ai_chat(user_msg: str) -> str:
    lower = user_msg.lower()
    if any(kw in lower for kw in ["yaad rakh", "remember", "mera naam", "meri", "main rehta", "mujhe pasand"]):
        mem.add_fact(user_msg[:200])

    chat_hist.add("user", user_msg)
    messages = chat_hist.get_recent(20)

    reply = call_gemini(build_system_prompt(), messages)
    chat_hist.add("assistant", reply)
    return reply

# ══════════════════════════════════════════════
# KEYBOARDS
# ══════════════════════════════════════════════
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 Daily Briefing", callback_data="briefing"),
         InlineKeyboardButton("📋 Tasks",           callback_data="tasks")],
        [InlineKeyboardButton("💪 Habits",          callback_data="habits"),
         InlineKeyboardButton("📖 Diary",            callback_data="diary")],
        [InlineKeyboardButton("🎯 Goals",            callback_data="goals"),
         InlineKeyboardButton("💰 Kharcha",          callback_data="expenses")],
        [InlineKeyboardButton("📝 Notes",            callback_data="notes"),
         InlineKeyboardButton("🧠 Yaaddasht",        callback_data="memory")],
        [InlineKeyboardButton("📰 News",             callback_data="news_menu"),
         InlineKeyboardButton("💡 Motivate",         callback_data="motivate")],
        [InlineKeyboardButton("🔔 Reminders",        callback_data="reminders"),
         InlineKeyboardButton("📊 Kal Ka Summary",   callback_data="yesterday")],
        [InlineKeyboardButton("🧹 Chat Clear",       callback_data="clear_chat")],
    ])

def news_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇳 India",        callback_data="news_India"),
         InlineKeyboardButton("💻 Tech",           callback_data="news_Technology")],
        [InlineKeyboardButton("📈 Business",       callback_data="news_Business"),
         InlineKeyboardButton("🌍 World",          callback_data="news_World")],
        [InlineKeyboardButton("⚽ Sports",         callback_data="news_Sports"),
         InlineKeyboardButton("🏠 Menu",           callback_data="menu")],
    ])

# ══════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Dost"
    await update.message.reply_text(
        f"🤖 *Namaste {name}! Main Aapka Personal AI Dost Hoon!*\n\n"
        "Main aapki madad karunga:\n"
        "🧠 Sab kuch yaad rakhna\n"
        "📋 Tasks & Goals track karna\n"
        "📖 Roz diary likhna\n"
        "💪 Habits & Streaks\n"
        "💰 Kharcha track karna\n"
        "📰 Free news (India, Tech, World)\n"
        "💬 Kisi bhi topic par baat karna\n\n"
        "✅ *100% FREE — Powered by Google Gemini*\n"
        "_4 models — auto-fallback on 503!_ 🔥\n\n"
        "_Seedha kuch bhi type karo, ya neeche buttons use karo!_ 👇",
        parse_mode="Markdown", reply_markup=main_kb())

async def send_briefing(msg_obj):
    tp = tasks.today_pending()
    yd = tasks.done_on(yesterday_str())
    hd, hp = habits.today_status()
    exp_today = expenses.today_total()
    exp_month = expenses.month_total()
    ag = goals.active()
    td_diary = diary.get(today_str())
    today_label = datetime.now().strftime("%A, %d %B %Y")

    txt = f"🌅 *DAILY BRIEFING*\n📅 {today_label}\n\n"
    if yd:
        txt += f"✅ *Kal {len(yd)} kaam kiye:*\n"
        for t in yd[:5]: txt += f"  • {t['title']}\n"
        txt += "\n"
    if tp:
        txt += f"📋 *Aaj {len(tp)} kaam baaki:*\n"
        for t in tp[:6]:
            e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
            txt += f"  {e} {t['title']}\n"
        txt += "\n"
    else:
        txt += "🎉 *Koi pending task nahi!*\n\n"
    if hp:
        txt += f"💪 *{len(hp)} Habits baaki:*\n"
        for h in hp[:4]: txt += f"  ○ {h['emoji']} {h['name']}\n"
        txt += "\n"
    if ag:
        txt += f"🎯 *Goals ({len(ag)}):*\n"
        for g in ag[:3]: txt += f"  • {g['title']} — {g['progress']}%\n"
        txt += "\n"
    bl = expenses.budget_left()
    txt += f"💰 Aaj ₹{exp_today:.0f} | Mahina ₹{exp_month:.0f}"
    if bl is not None: txt += f" | Budget baaki: ₹{bl:.0f}"
    txt += "\n\n"
    if td_diary: txt += f"📖 Aaj {len(td_diary)} diary entries\n\n"
    txt += "💪 *Aaj ka din badiya banao!* 🚀"
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_briefing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_briefing(update.message)

async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "📋 Task add karo:\n`/task Kaam ka naam`\n`/task Important meeting high`\n\n"
            "_Priority: high / low (default: medium)_", parse_mode="Markdown"); return
    args = " ".join(ctx.args)
    priority = "medium"
    if args.endswith(" high"): priority="high"; args=args[:-5].strip()
    elif args.endswith(" low"): priority="low"; args=args[:-4].strip()
    t = tasks.add(args, priority=priority)
    e = "🔴" if priority=="high" else "🟡" if priority=="medium" else "🟢"
    await update.message.reply_text(
        f"✅ *Task Add!*\n\n{e} {t['title']}\nPriority: *{priority.upper()}*", parse_mode="Markdown")

async def show_tasks(msg_obj):
    pending = tasks.pending()
    if not pending:
        await msg_obj.reply_text("🎉 Koi pending task nahi!\n\n`/task Kaam ka naam` se naya add karo", parse_mode="Markdown"); return
    txt = f"📋 *TASKS ({len(pending)} pending)*\n\n"
    kb = []
    for t in pending[:10]:
        e = "🔴" if t["priority"]=="high" else "🟡" if t["priority"]=="medium" else "🟢"
        txt += f"{e} *#{t['id']}* {t['title']}\n"
        kb.append([InlineKeyboardButton(f"✅ #{t['id']}: {t['title'][:35]}", callback_data=f"done_{t['id']}")])
    kb.append([InlineKeyboardButton("🗑 Done Tasks Hata Do", callback_data="clear_done_tasks"),
               InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Kaun sa task? `/done 3`", parse_mode="Markdown"); return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t: await update.message.reply_text(f"🎉 *Complete!*\n\n✅ {t['title']}\n\nWah bhai! 💪", parse_mode="Markdown")
        else: await update.message.reply_text("❌ Task nahi mila ya pehle done hai.")
    except: await update.message.reply_text("❌ `/done 3` format use karo", parse_mode="Markdown")

async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🗑 `/deltask 3` — Task #3 delete karega", parse_mode="Markdown"); return
    try:
        tasks.delete(int(ctx.args[0]))
        await update.message.reply_text(f"🗑 *Task #{ctx.args[0]} Delete Ho Gaya!*", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/deltask 3` format", parse_mode="Markdown")

async def cmd_diary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📖 `/diary Aaj bahut productive tha!`", parse_mode="Markdown"); return
    content = " ".join(ctx.args)
    diary.add(content)
    mem.add_fact(f"Diary {today_str()}: {content[:100]}")
    await update.message.reply_text(
        f"📖 *Diary Mein Likh Diya!*\n\n_{content}_\n\n🕐 {now_str()}", parse_mode="Markdown")

async def show_diary(msg_obj):
    td = diary.get(today_str())
    yd = diary.get(yesterday_str())
    txt = "📖 *DIARY*\n\n"
    if td:
        txt += "📅 *Aaj:*\n"
        for e in td: txt += f"  {e['time']} {e['mood']} {e['text']}\n"
        txt += "\n"
    if yd:
        txt += "📅 *Kal:*\n"
        for e in yd[-3:]: txt += f"  {e['time']} {e['mood']} {e['text']}\n"
    if not td and not yd: txt += "_Koi entry nahi_\n\n`/diary Aaj kya hua...`"
    await msg_obj.reply_text(txt, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("💪 `/habit Morning walk 🏃`", parse_mode="Markdown"); return
    name = " ".join(ctx.args)
    emoji = "✅"
    for em in ["💪","🏃","📚","💧","🧘","🌅","🏋","✍️","🎯","🙏"]:
        if em in name: emoji = em; break
    h = habits.add(name, emoji)
    await update.message.reply_text(
        f"💪 *Habit Add!*\n\n{h['emoji']} {h['name']}\n\nRoz `/hdone {h['id']}` se mark karo!", parse_mode="Markdown")

async def cmd_hdone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        _, pending = habits.today_status()
        txt = "💪 Kaunsi habit complete ki?\n\n"
        for h in pending: txt += f"`/hdone {h['id']}` — {h['emoji']} {h['name']}\n"
        await update.message.reply_text(txt or "Koi pending habit nahi!", parse_mode="Markdown"); return
    try:
        hid = int(ctx.args[0])
        ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"]==hid), None)
        if ok and h:
            st = f"🔥 {streak} din ka streak!" if streak > 1 else "Pehli baar! 🌟"
            await update.message.reply_text(f"💪 *Done!*\n\n{h['emoji']} {h['name']}\n{st}", parse_mode="Markdown")
        else: await update.message.reply_text("✅ Aaj pehle hi mark hai!")
    except: await update.message.reply_text("❌ `/hdone 1` format", parse_mode="Markdown")

async def cmd_delhabit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🗑 `/delhabit 1` — Habit #1 delete karega", parse_mode="Markdown"); return
    try:
        habits.delete(int(ctx.args[0]))
        await update.message.reply_text(f"🗑 *Habit #{ctx.args[0]} Delete Ho Gayi!*", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/delhabit 1` format", parse_mode="Markdown")

async def show_habits(msg_obj):
    done, pending = habits.today_status()
    all_h = habits.all()
    if not all_h:
        await msg_obj.reply_text("💪 Koi habit nahi!\n\n`/habit Morning walk` se shuru karo!", parse_mode="Markdown"); return
    txt = "💪 *HABITS — AAJ*\n\n"
    if done:
        txt += "✅ *Ho Gaye:*\n"
        for h in done: txt += f"  {h['emoji']} {h['name']} 🔥{h['streak']}\n"
        txt += "\n"
    kb = []
    if pending:
        txt += "⏳ *Baaki:*\n"
        for h in pending:
            txt += f"  ○ {h['emoji']} {h['name']}\n"
            kb.append([InlineKeyboardButton(f"✅ {h['emoji']} {h['name']}", callback_data=f"habit_{h['id']}")])
    else: txt += "🎉 *Sab complete!*"
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def cmd_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📝 `/note Grocery: Doodh, Bread`", parse_mode="Markdown"); return
    n = notes.add(" ".join(ctx.args))
    await update.message.reply_text(f"📝 *Note #{n['id']} Save!*\n\n_{n['text']}_", parse_mode="Markdown")

async def cmd_delnote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🗑 `/delnote 3` — Note #3 delete karega", parse_mode="Markdown"); return
    try:
        notes.delete(int(ctx.args[0]))
        await update.message.reply_text(f"🗑 *Note #{ctx.args[0]} Delete Ho Gaya!*", parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/delnote 3` format", parse_mode="Markdown")

async def show_notes(msg_obj):
    ns = notes.recent(12)
    if not ns:
        await msg_obj.reply_text("📝 Koi notes nahi.\n\n`/note Kuch important`", parse_mode="Markdown"); return
    txt = f"📝 *NOTES ({len(ns)})*\n\n"
    for n in ns: txt += f"*#{n['id']}* {n['text']}\n_{n['created'][:10]}_\n\n"
    await msg_obj.reply_text(txt, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

async def cmd_kharcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "💰 `/kharcha 50 Chai`\n`/kharcha 500 Grocery`\n\n"
            "Aaj ka hisaab: `/kharcha_aaj`\nBudget set: `/budget 5000`", parse_mode="Markdown"); return
    try:
        amount = float(ctx.args[0])
        desc = " ".join(ctx.args[1:]) or "Kharcha"
        expenses.add(amount, desc)
        bl = expenses.budget_left()
        txt = f"💰 *₹{amount:.0f} — {desc}*\n\nAaj ka total: *₹{expenses.today_total():.0f}*"
        if bl is not None: txt += f"\nBudget baaki: ₹{bl:.0f}"
        await update.message.reply_text(txt, parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/kharcha 100 Khana` format", parse_mode="Markdown")

async def cmd_kharcha_aaj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    items = expenses.today_list()
    if not items:
        await update.message.reply_text("💰 Aaj koi kharcha nahi.\n\n`/kharcha 50 Chai` se shuru karo!", parse_mode="Markdown"); return
    txt = "💰 *AAJ KA KHARCHA*\n\n"
    for e in items: txt += f"  ₹{e['amount']:.0f} — {e['desc']} ({e['time']})\n"
    txt += f"\n💵 *Aaj: ₹{expenses.today_total():.0f}*\n📅 *Mahina: ₹{expenses.month_total():.0f}*"
    bl = expenses.budget_left()
    if bl is not None: txt += f"\n🎯 Budget baaki: ₹{bl:.0f}"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("💰 `/budget 5000` — Monthly budget set karo", parse_mode="Markdown"); return
    try:
        b = float(ctx.args[0])
        expenses.set_budget(b)
        await update.message.reply_text(
            f"💰 *Monthly Budget Set: ₹{b:.0f}*\n\nAbhi tak kharch: ₹{expenses.month_total():.0f}\nBaaki: ₹{expenses.budget_left():.0f}",
            parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/budget 5000` format", parse_mode="Markdown")

async def cmd_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🎯 `/goal Weight lose 10kg`\n`/goal Job change 2025-12-31`", parse_mode="Markdown"); return
    title = " ".join(ctx.args)
    deadline = None
    parts = title.rsplit(" ", 1)
    if len(parts) == 2 and len(parts[1]) == 10 and parts[1].count("-") == 2:
        deadline = parts[1]; title = parts[0]
    g = goals.add(title, deadline)
    await update.message.reply_text(
        f"🎯 *Goal Add!*\n\n✨ {g['title']}" + (f"\n📅 Deadline: {deadline}" if deadline else ""), parse_mode="Markdown")

async def cmd_gprogress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        gid = int(ctx.args[0]); pct = int(ctx.args[1])
        g = goals.update_progress(gid, pct)
        if g:
            bar = "█"*(pct//10) + "░"*(10-pct//10)
            msg = f"🎯 *Progress Update!*\n\n{g['title']}\n{bar} *{pct}%*"
            if pct == 100: msg += "\n\n🏆 *GOAL COMPLETE!* 🎉"
            await update.message.reply_text(msg, parse_mode="Markdown")
    except: await update.message.reply_text("❌ `/gprogress 1 75` format", parse_mode="Markdown")

async def show_goals(msg_obj):
    ag = goals.active()
    if not ag:
        await msg_obj.reply_text("🎯 Koi goals nahi!\n\n`/goal Kuch achieve karna hai`", parse_mode="Markdown"); return
    txt = f"🎯 *GOALS ({len(ag)})*\n\n"
    kb = []
    for g in ag:
        bar = "█"*(g["progress"]//10) + "░"*(10-g["progress"]//10)
        txt += f"*{g['title']}*\n{bar} {g['progress']}%"
        if g["deadline"]: txt += f" | 📅 {g['deadline']}"
        txt += "\n\n"
        kb.append([InlineKeyboardButton(f"📊 Update: {g['title'][:28]}", callback_data=f"goal_{g['id']}")])
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def cmd_remember(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("🧠 `/remember Mera birthday 15 August hai`", parse_mode="Markdown"); return
    fact = " ".join(ctx.args)
    mem.add_fact(fact)
    await update.message.reply_text(f"🧠 *Yaad Kar Liya!* ✅\n\n_{fact}_", parse_mode="Markdown")

async def cmd_recall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    facts = mem.data["facts"]
    if not facts:
        await update.message.reply_text("🧠 Kuch yaad nahi kiya abhi tak.\n\n`/remember Koi baat`", parse_mode="Markdown"); return
    txt = f"🧠 *YAADDASHT ({len(facts)})*\n_(Chat clear se SAFE hai)_ 🔒\n\n"
    for f in facts[-12:]: txt += f"  📌 {f['f']}\n  _{f['d']}_\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Haan Clear Karo", callback_data="confirm_clear_chat"),
         InlineKeyboardButton("❌ Nahi", callback_data="menu")]
    ])
    await update.message.reply_text(
        f"🧹 *Chat clear karna chahte ho?*\n\n"
        f"📊 {chat_hist.count()} messages abhi hain\n"
        f"✅ Memory, Tasks, Diary — sab safe rahega!\n"
        f"_Sirf conversation history hategi_",
        parse_mode="Markdown", reply_markup=kb)

async def show_news(msg_obj, category):
    await msg_obj.reply_text(f"📰 *{category} news fetch ho rahi hai...*", parse_mode="Markdown")
    news_items = fetch_news(category)
    txt = f"📰 *{category.upper()} NEWS*\n\n"
    for i, item in enumerate(news_items, 1):
        txt += f"*{i}.* {item['title']}\n"
        if item['desc']: txt += f"_{item['desc'][:100]}..._\n"
        if item['link']: txt += f"[Padhne ke liye click karo]({item['link']})\n"
        txt += "\n"
    txt += "_Free RSS news — No API key!_ ✅"
    try:
        await msg_obj.reply_text(txt, parse_mode="Markdown", reply_markup=news_kb())
    except Exception:
        await msg_obj.reply_text(txt[:3000], reply_markup=news_kb())

# ══════════════════════════════════════════════
# 🔔 REMINDER & ALARM HANDLERS
# ══════════════════════════════════════════════

def parse_remind_time(arg: str):
    """
    Parse time string and return datetime when to fire.
    Supports:
      30m  → 30 minutes baad
      2h   → 2 ghante baad
      09:30 → aaj 09:30 (agar beet gaya toh kal)
    Returns (datetime, label) or (None, error_msg)
    """
    now = datetime.now()
    arg = arg.strip().lower()

    # Minutes: 30m, 5m
    if arg.endswith("m") and arg[:-1].isdigit():
        mins = int(arg[:-1])
        return now + timedelta(minutes=mins), f"{mins} minute"

    # Hours: 2h, 1h
    if arg.endswith("h") and arg[:-1].isdigit():
        hrs = int(arg[:-1])
        return now + timedelta(hours=hrs), f"{hrs} ghante"

    # Time HH:MM
    if ":" in arg:
        try:
            parts = arg.split(":")
            h, m = int(parts[0]), int(parts[1])
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
                label = f"kal {h:02d}:{m:02d}"
            else:
                label = f"aaj {h:02d}:{m:02d}"
            return target, label
        except:
            pass

    return None, "❌ Time format galat!\nUse: `30m`, `2h`, `09:30`"


async def fire_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    """Job queue callback — reminder fire hoga"""
    job = ctx.job
    data = job.data
    chat_id = data["chat_id"]
    text    = data["text"]
    rid     = data.get("rid")

    msg = f"🔔 *REMINDER!*\n\n⏰ {text}\n\n_Time: {now_str()}_"
    try:
        await ctx.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
        if rid:
            reminders.mark_done(rid)
    except Exception as e:
        log.warning(f"Reminder fire error: {e}")


async def fire_alarm(ctx: ContextTypes.DEFAULT_TYPE):
    """Daily alarm callback"""
    job = ctx.job
    data = job.data
    chat_id = data["chat_id"]
    text    = data.get("text", "⏰ Alarm!")

    msg = f"⏰ *ALARM!*\n\n🔔 {text}\n\n_Time: {now_str()}_"
    try:
        await ctx.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
    except Exception as e:
        log.warning(f"Alarm fire error: {e}")


async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /remind 30m Paani peena
    /remind 2h Meeting check karo
    /remind 09:30 Gym jaana
    """
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text(
            "🔔 *Reminder kaise set karein:*\n\n"
            "`/remind 30m Paani peena`\n"
            "`/remind 2h Meeting hai`\n"
            "`/remind 09:30 Gym jaana`\n\n"
            "_Formats: Xm (minutes), Xh (hours), HH:MM (specific time)_",
            parse_mode="Markdown")
        return

    time_arg = ctx.args[0]
    text = " ".join(ctx.args[1:])
    chat_id = update.effective_chat.id

    fire_at, label = parse_remind_time(time_arg)
    if fire_at is None:
        await update.message.reply_text(label, parse_mode="Markdown")
        return

    delay = (fire_at - datetime.now()).total_seconds()
    if delay < 5:
        await update.message.reply_text("❌ Time pehle hi beet chuka hai! Dobara try karo.", parse_mode="Markdown")
        return

    r = reminders.add(text, fire_at.isoformat(), chat_id)
    job_id = r["job_id"]

    ctx.job_queue.run_once(
        fire_reminder,
        when=delay,
        data={"chat_id": chat_id, "text": text, "rid": r["id"]},
        name=job_id
    )

    await update.message.reply_text(
        f"✅ *Reminder Set!*\n\n"
        f"🔔 {text}\n"
        f"⏰ {label} baad notification milega\n"
        f"📅 {fire_at.strftime('%d %b %Y, %I:%M %p')}\n\n"
        f"_ID #{r['id']} | Cancel: `/cancelremind {r['id']}`_",
        parse_mode="Markdown")


async def cmd_alarm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /alarm 07:00 Uthne ka time!
    /alarm 22:00 Sone se pehle review karo
    """
    if not ctx.args:
        await update.message.reply_text(
            "⏰ *Daily Alarm kaise set karein:*\n\n"
            "`/alarm 07:00 Good morning!`\n"
            "`/alarm 22:00 Kal ki planning karo`\n\n"
            "_Roz usi time pe notification milega!_\n"
            "Sabhi alarms dekho: `/reminders`\n"
            "Band karo: `/stopalarm 1`",
            parse_mode="Markdown")
        return

    time_str = ctx.args[0]
    text = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else "⏰ Alarm!"
    chat_id = update.effective_chat.id

    # Validate HH:MM
    try:
        parts = time_str.split(":")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
        time_str = f"{h:02d}:{m:02d}"
    except:
        await update.message.reply_text(
            "❌ Time format: `HH:MM` (jaise `07:30`)", parse_mode="Markdown")
        return

    a = reminders.add_alarm(time_str, text, chat_id)

    # Schedule daily job
    fire_time = datetime.now().replace(
        hour=h, minute=m, second=0, microsecond=0)
    if fire_time <= datetime.now():
        fire_time += timedelta(days=1)

    delay = (fire_time - datetime.now()).total_seconds()

    ctx.job_queue.run_repeating(
        fire_alarm,
        interval=86400,       # 24 ghante
        first=delay,
        data={"chat_id": chat_id, "text": text, "aid": a["id"]},
        name=a["job_id"]
    )

    await update.message.reply_text(
        f"⏰ *Daily Alarm Set!*\n\n"
        f"🔔 {text}\n"
        f"🕐 Roz {time_str} baje ring karega\n\n"
        f"_ID #{a['id']} | Band karo: `/stopalarm {a['id']}`_",
        parse_mode="Markdown")


async def cmd_reminders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Sab upcoming reminders aur alarms dikhao"""
    all_items = reminders.all_upcoming()

    if not all_items:
        await update.message.reply_text(
            "🔔 *Koi active reminder/alarm nahi!*\n\n"
            "Set karo:\n"
            "`/remind 30m Paani peena`\n"
            "`/alarm 07:00 Good morning`",
            parse_mode="Markdown")
        return

    txt = f"🔔 *ACTIVE REMINDERS & ALARMS ({len(all_items)})*\n\n"

    one_time = [x for x in all_items if x["type"] == "remind"]
    daily    = [x for x in all_items if x["type"] == "alarm"]

    if one_time:
        txt += "⏰ *One-Time Reminders:*\n"
        for r in one_time:
            try:
                dt = datetime.fromisoformat(r["remind_at"])
                time_label = dt.strftime("%d %b, %I:%M %p")
            except:
                time_label = r.get("remind_at", "?")
            txt += f"  #{r['id']} 📌 {r['text']}\n  ⏰ {time_label}\n"
            txt += f"  ❌ Cancel: `/cancelremind {r['id']}`\n\n"

    if daily:
        txt += "🔁 *Daily Alarms:*\n"
        for a in daily:
            txt += f"  #{a['id']} 🔔 {a['text']}\n  🕐 Roz {a['time']} baje\n"
            txt += f"  ❌ Band karo: `/stopalarm {a['id']}`\n\n"

    await update.message.reply_text(txt, parse_mode="Markdown")


async def cmd_cancelremind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """One-time reminder cancel karo"""
    if not ctx.args:
        await update.message.reply_text(
            "❌ `/cancelremind 3` — Reminder #3 cancel karega", parse_mode="Markdown")
        return
    try:
        rid = int(ctx.args[0])
        # Job queue se bhi cancel karo
        job_name = f"remind_{rid}"
        current_jobs = ctx.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()

        if reminders.delete(rid):
            await update.message.reply_text(
                f"✅ *Reminder #{rid} Cancel Ho Gaya!*", parse_mode="Markdown")
        else:
            await update.message.reply_text(
                f"❌ Reminder #{rid} nahi mila.", parse_mode="Markdown")
    except:
        await update.message.reply_text(
            "❌ `/cancelremind 3` format use karo", parse_mode="Markdown")


async def cmd_stopalarm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Daily alarm band karo"""
    if not ctx.args:
        await update.message.reply_text(
            "⏰ `/stopalarm 2` — Alarm #2 band karega", parse_mode="Markdown")
        return
    try:
        aid = int(ctx.args[0])
        job_name = f"alarm_{aid}"
        current_jobs = ctx.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()

        if reminders.stop_alarm(aid):
            await update.message.reply_text(
                f"⏰ *Alarm #{aid} Band Ho Gaya!*\n\nDobara set karo: `/alarm 07:00 text`",
                parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Alarm #{aid} nahi mila.", parse_mode="Markdown")
    except:
        await update.message.reply_text(
            "❌ `/stopalarm 2` format use karo", parse_mode="Markdown")


async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📰 *Kaunsi category ki news chahiye?*", parse_mode="Markdown", reply_markup=news_kb())

async def show_yesterday(msg_obj):
    yd_label = (date.today()-timedelta(days=1)).strftime("%A, %d %B")
    done = tasks.done_on(yesterday_str())
    yd_d = diary.get(yesterday_str())
    txt = f"📅 *KAL KA SUMMARY ({yd_label})*\n\n"
    if done:
        txt += f"✅ *{len(done)} Tasks Kiye:*\n"
        for t in done: txt += f"  • {t['title']}\n"
        txt += "\n"
    if yd_d:
        txt += "📖 *Diary:*\n"
        for e in yd_d: txt += f"  {e['time']} {e['mood']} {e['text']}\n"
    if not done and not yd_d: txt += "_Kal ka koi data nahi mila_"
    await msg_obj.reply_text(txt, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = """🤖 *COMMANDS — v4.0*

*🔔 REMINDERS & ALARMS:*
`/remind 30m Paani peena` — 30 min baad
`/remind 2h Meeting` — 2 ghante baad
`/remind 09:30 Gym` — specific time
`/alarm 07:00 Uthna hai` — Daily alarm (roz!)
`/reminders` — Sab dekho
`/cancelremind 3` — Cancel #3
`/stopalarm 2` — Daily alarm band

*📋 TASKS:*
`/task Kaam [high/low]` — Add
`/done 3` — Complete
`/deltask 3` — Delete

*📖 DIARY:*
`/diary Aaj yeh hua` — Entry likho

*🧠 MEMORY:*
`/remember Koi baat` — Permanently save
`/recall` — Sab dekho

*📝 NOTES:*
`/note Kuch important`
`/delnote 3` — Delete

*💪 HABITS:*
`/habit Habit naam emoji`
`/hdone 1` — Complete
`/delhabit 1` — Delete

*💰 KHARCHA:*
`/kharcha 100 Khana`
`/kharcha_aaj` — Aaj ka hisaab
`/budget 5000` — Monthly budget

*🎯 GOALS:*
`/goal Goal naam`
`/gprogress 1 50` — 50% done

*📰 NEWS (FREE):*
`/news` — India, Tech, Business, World, Sports

*🧹 CLEAR:*
`/clear` — Chat clear (memory safe!)

*🌅 DAILY:*
`/briefing` — Poora update
`/yesterday` — Kal kya hua

*💬 Seedha kuch bhi type karo!* 😊
_503 error pe auto fallback — 4 models try karta hoon!_"""
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

# ══════════════════════════════════════════════
# CALLBACK HANDLER
# ══════════════════════════════════════════════
async def callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); d = q.data

    if   d == "menu":      await q.message.reply_text("🏠 *Main Menu*", parse_mode="Markdown", reply_markup=main_kb())
    elif d == "briefing":  await send_briefing(q.message)
    elif d == "tasks":     await show_tasks(q.message)
    elif d == "habits":    await show_habits(q.message)
    elif d == "diary":     await show_diary(q.message)
    elif d == "goals":     await show_goals(q.message)
    elif d == "notes":     await show_notes(q.message)
    elif d == "yesterday": await show_yesterday(q.message)
    elif d == "news_menu": await q.message.reply_text("📰 *Kaunsi news?*", parse_mode="Markdown", reply_markup=news_kb())

    elif d.startswith("news_"):
        cat = d.split("_", 1)[1]
        await show_news(q.message, cat)

    elif d == "reminders":
        all_items = reminders.all_upcoming()
        if not all_items:
            await q.message.reply_text(
                "🔔 *Koi active reminder nahi!*\n\n"
                "`/remind 30m Kuch karna hai`\n"
                "`/alarm 07:00 Good morning`",
                parse_mode="Markdown")
        else:
            txt = f"🔔 *REMINDERS ({len(all_items)})*\n\n"
            for item in all_items:
                if item["type"] == "remind":
                    try:
                        dt = datetime.fromisoformat(item["remind_at"])
                        tl = dt.strftime("%d %b, %I:%M %p")
                    except:
                        tl = "?"
                    txt += f"  #{item['id']} ⏰ {item['text']} — {tl}\n"
                else:
                    txt += f"  #{item['id']} 🔁 {item['text']} — Roz {item['time']}\n"
            await q.message.reply_text(txt, parse_mode="Markdown")

    elif d == "memory":
        facts = mem.data["facts"]
        txt = f"🧠 *YAADDASHT ({len(facts)})*\n_(Chat clear se safe hai)_ 🔒\n\n"
        txt += "\n".join(f"  📌 {f['f']}" for f in facts[-12:]) if facts else "_Kuch nahi_"
        await q.message.reply_text(txt, parse_mode="Markdown")

    elif d == "expenses":
        items = expenses.today_list()
        txt = f"💰 *KHARCHA*\nAaj: ₹{expenses.today_total():.0f} | Mahina: ₹{expenses.month_total():.0f}\n"
        bl = expenses.budget_left()
        if bl is not None: txt += f"Budget baaki: ₹{bl:.0f}\n"
        txt += "\n"
        for e in items[-8:]: txt += f"  ₹{e['amount']:.0f} {e['desc']}\n"
        if not items: txt += "_Aaj koi kharcha nahi_"
        await q.message.reply_text(txt, parse_mode="Markdown")

    elif d == "clear_chat":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Haan Clear Karo", callback_data="confirm_clear_chat"),
             InlineKeyboardButton("❌ Nahi", callback_data="menu")]
        ])
        await q.message.reply_text(
            f"🧹 *Chat clear karna chahte ho?*\n\n"
            f"📊 {chat_hist.count()} messages abhi hain\n"
            f"✅ Memory, Tasks, Diary — sab safe rahega!\n"
            f"_Sirf conversation history hategi_",
            parse_mode="Markdown", reply_markup=kb)

    elif d == "confirm_clear_chat":
        count = chat_hist.clear()
        await q.message.reply_text(
            f"🧹 *Chat Clear Ho Gayi!*\n\n"
            f"🗑 {count} messages hata diye\n"
            f"🔒 Memory, Tasks, Habits — sab safe hai!\n\n"
            f"_Ab fresh start karo!_ 🚀",
            parse_mode="Markdown", reply_markup=main_kb())

    elif d == "clear_done_tasks":
        count = tasks.clear_done()
        await q.message.reply_text(f"🗑 *{count} Done Tasks Delete Ho Gayi!*", parse_mode="Markdown")

    elif d == "motivate":
        reply = await ai_chat("Mujhe ek powerful 3-4 line motivation de Hindi mein. Real, raw, energetic. Generic mat dena.")
        await q.message.reply_text(f"💡 *Motivation:*\n\n{reply}", parse_mode="Markdown")

    elif d.startswith("done_"):
        t = tasks.complete(int(d.split("_")[1]))
        await q.message.reply_text(
            f"🎉 *Complete!*\n\n✅ {t['title']}\n💪 Wah bhai!" if t else "❌ Nahi mila",
            parse_mode="Markdown")

    elif d.startswith("habit_"):
        hid = int(d.split("_")[1])
        ok, streak = habits.log(hid)
        h = next((x for x in habits.all() if x["id"]==hid), None)
        if ok and h:
            st = f"🔥 {streak} din ka streak!" if streak > 1 else "Pehli baar! 🌟"
            await q.message.reply_text(f"💪 *Done!*\n{h['emoji']} {h['name']}\n{st}", parse_mode="Markdown")
        else:
            await q.message.reply_text("✅ Aaj pehle hi mark hai!")

    elif d.startswith("goal_"):
        gid = d.split("_")[1]
        await q.message.reply_text(f"📊 Progress:\n`/gprogress {gid} 50` (0-100)", parse_mode="Markdown")

# ══════════════════════════════════════════════
# MESSAGE HANDLER
# ══════════════════════════════════════════════
async def handle_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ai_chat(update.message.text)
    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(reply)

# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
def main():
    log.info("🤖 Personal AI Bot v4.0 — Merged Best — Starting...")
    log.info(f"📡 Models (fallback order): {', '.join(GEMINI_MODELS)}")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    handlers = [
        ("start",       cmd_start),
        ("help",        cmd_help),
        ("briefing",    cmd_briefing),
        ("task",        cmd_task),
        ("done",        cmd_done),
        ("deltask",     cmd_deltask),
        ("diary",       cmd_diary),
        ("remember",    cmd_remember),
        ("recall",      cmd_recall),
        ("note",        cmd_note),
        ("delnote",     cmd_delnote),
        ("habit",       cmd_habit),
        ("hdone",       cmd_hdone),
        ("delhabit",    cmd_delhabit),
        ("kharcha",     cmd_kharcha),
        ("kharcha_aaj", cmd_kharcha_aaj),
        ("budget",      cmd_budget),
        ("goal",        cmd_goal),
        ("gprogress",   cmd_gprogress),
        ("remind",      cmd_remind),
        ("alarm",       cmd_alarm),
        ("reminders",   cmd_reminders),
        ("cancelremind",cmd_cancelremind),
        ("stopalarm",   cmd_stopalarm),
        ("news",        cmd_news),
        ("clear",       cmd_clear),
        ("yesterday",   lambda u,c: show_yesterday(u.message)),
    ]
    for cmd, handler in handlers:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    log.info("✅ Bot ready! Telegram pe /start karo.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
