#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PERSONAL AI ASSISTANT v5.0 - FRESH"""

import os, json, logging, time, asyncio, urllib.request, urllib.error, ssl
from datetime import datetime, date, timedelta
import hashlib, threading, re as _re

ssl._create_default_https_context = ssl._create_unverified_context
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()])
log = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    log.error("Set TELEGRAM_TOKEN and GEMINI_API_KEY")
    exit(1)

SECRET_CODE = "Rk1996"
SECRET_CODE_HASH = hashlib.sha256(SECRET_CODE.encode()).hexdigest()
GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

DATA = os.path.join(os.getcwd(), "data")
os.makedirs(DATA, exist_ok=True)

def load_json(path, default=None):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return default if default is not None else {}

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def today_str():
    return date.today().isoformat()

def now_str():
    return datetime.now().strftime("%H:%M")

def verify_secret(code):
    return hashlib.sha256(code.encode()).hexdigest() == SECRET_CODE_HASH

# ═══════════════ GEMINI API ═══════════════
def call_gemini(system_prompt, messages):
    contents = [
        {"role": "user", "parts": [{"text": f"[SYSTEM]\n{system_prompt}\n[/SYSTEM]"}]},
        {"role": "model", "parts": [{"text": "Ready"}]}
    ]
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    
    payload = json.dumps({
        "contents": contents,
        "generationConfig": {"temperature": 0.75, "maxOutputTokens": 600}
    }).encode("utf-8")
    
    for model in GEMINI_MODELS:
        try:
            url = BASE_URL.format(model=model, key=GEMINI_API_KEY)
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=45) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                log.info(f"Model: {model}")
                return result["candidates"][0]["content"]["parts"][0]["text"]
        except:
            continue
    return None

# ═══════════════ CLASSES ═══════════════
class ChatHistory:
    def __init__(self):
        path = os.path.join(DATA, "chat_history.json")
        self.data = load_json(path, {"history": [], "msg_ids": []})
        self.path = path
    
    def add(self, role, content):
        self.data["history"].append({
            "role": role,
            "content": content,
            "time": datetime.now().isoformat()
        })
        self.data["history"] = self.data["history"][-80:]
        save_json(self.path, self.data)
    
    def track_msg(self, chat_id, msg_id):
        self.data["msg_ids"].append({"chat_id": chat_id, "msg_id": msg_id})
        self.data["msg_ids"] = self.data["msg_ids"][-500:]
        save_json(self.path, self.data)
    
    def get_recent(self, n=20):
        return [{"role": m["role"], "content": m["content"]} for m in self.data["history"][-n:]]
    
    def get_tracked_ids(self):
        return self.data.get("msg_ids", [])
    
    def clear(self):
        count = len(self.data["history"])
        self.data["history"] = []
        save_json(self.path, self.data)
        return count
    
    def clear_msg_ids(self):
        self.data["msg_ids"] = []
        save_json(self.path, self.data)
    
    def count(self):
        return len(self.data["history"])

class Memory:
    def __init__(self):
        path = os.path.join(DATA, "memory.json")
        self.data = load_json(path, {"facts": [], "important_notes": []})
        self.path = path
    
    def save(self):
        save_json(self.path, self.data)
    
    def add_fact(self, fact):
        self.data["facts"].append({"f": fact, "d": today_str()})
        self.data["facts"] = self.data["facts"][-400:]
        self.save()
    
    def context(self):
        facts = "\n".join(f"• {x['f']}" for x in self.data["facts"][-30:]) or "Kuch nahi"
        return f"FACTS:\n{facts}"

class Tasks:
    def __init__(self):
        path = os.path.join(DATA, "tasks.json")
        self.data = load_json(path, {"list": [], "counter": 0, "completed_history": []})
        self.path = path
    
    def save(self):
        save_json(self.path, self.data)
    
    def add(self, title, priority="medium"):
        self.data["counter"] += 1
        t = {
            "id": self.data["counter"],
            "title": title,
            "priority": priority,
            "done": False,
            "done_at": None,
            "completed_date": None,
            "created": datetime.now().isoformat()
        }
        self.data["list"].append(t)
        self.save()
        return t
    
    def complete(self, tid):
        for t in self.data["list"]:
            if t["id"] == tid and not t["done"]:
                t["done"] = True
                t["done_at"] = datetime.now().isoformat()
                t["completed_date"] = today_str()
                self.data["completed_history"].append(t.copy())
                self.save()
                return t
        return None
    
    def pending(self):
        return [t for t in self.data["list"] if not t["done"]]
    
    def all_tasks(self):
        return self.data["list"]
    
    def completed_tasks(self):
        return [t for t in self.data["list"] if t["done"]]
    
    def delete(self, tid):
        before = len(self.data["list"])
        self.data["list"] = [t for t in self.data["list"] if t["id"] != tid]
        self.save()
        return before != len(self.data["list"])
    
    def get_history(self):
        return self.data.get("completed_history", [])

class OfflineQueue:
    def __init__(self):
        path = os.path.join(DATA, "offline_queue.json")
        self.queue = load_json(path, {"pending": []})
        self.path = path
        self.lock = threading.Lock()
    
    def add(self, uid, cid, uname, msg):
        with self.lock:
            self.queue["pending"].append({
                "uid": uid, "cid": cid, "uname": uname, "msg": msg, "done": False
            })
            save_json(self.path, self.queue)
    
    def get_pending(self):
        return [m for m in self.queue["pending"] if not m["done"]]
    
    def mark_done(self, idx):
        with self.lock:
            if 0 <= idx < len(self.queue["pending"]):
                self.queue["pending"][idx]["done"] = True
                save_json(self.path, self.queue)

# ═══════════════ INIT OBJECTS ═══════════════
chat_hist = ChatHistory()
mem = Memory()
tasks = Tasks()
offline_queue = OfflineQueue()
log.info("All objects initialized!")

# ═══════════════ FUNCTIONS ═══════════════
def build_system_prompt():
    nl = datetime.now().strftime("%A, %d %B %Y — %I:%M %p")
    tp = tasks.pending()
    ts = "\n".join(
        f"  {'🔴' if t['priority']=='high' else '🟡' if t['priority']=='medium' else '🟢'} {t['title']}"
        for t in tp[:6]
    ) or "Koi nahi"
    return f"""Tu mera AI Assistant 'Dost' hai. Hindi/Hinglish mein baat kar.
⏰ {nl} | 💬 {chat_hist.count()} msgs
📋 TASKS:\n{ts}
━━ YAADDASHT ━━\n{mem.context()}
RULES: Dost ki tarah baat kar, Hinglish mein jawab de, short aur helpful reh."""

async def ai_chat(user_msg, chat_id=None):
    chat_hist.add("user", user_msg)
    reply = call_gemini(build_system_prompt(), chat_hist.get_recent(20))
    if reply is None:
        return "OFFLINE"
    chat_hist.add("assistant", reply)
    return reply

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Tasks", callback_data="tasks"),
         InlineKeyboardButton("🧠 Yaaddasht", callback_data="memory")],
        [InlineKeyboardButton("🧹 Clear Chat", callback_data="clear_chat"),
         InlineKeyboardButton("💡 Motivate", callback_data="motivate")],
    ])

# ═══════════════ COMMAND HANDLERS ═══════════════
async def cmd_start(update, ctx):
    name = update.effective_user.first_name or "Dost"
    txt = f"""🕌 *Assalamualaikum {name}!*

🧠 Smart Memory | 📋 Tasks
💰 Kharcha | ⏰ Reminders
📥 Offline Queue | 🔐 Code: `Rk1996`

✅ Seedha type karo! 👇"""
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_help(update, ctx):
    txt = """🤖 *COMMANDS*
📋 /task | /done 3 | /alltasks | /completed | /pending
🔐 /verify Rk1996 | /taskhistory Rk1996
🧠 /remember | /recall | ⏰ /remind 30m Chai
🧹 /clear"""
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def cmd_task(update, ctx):
    if not ctx.args:
        await update.message.reply_text("📋 `/task Kaam` | `/task Important high`", parse_mode="Markdown")
        return
    args = " ".join(ctx.args)
    priority = "medium"
    if args.endswith(" high"):
        priority = "high"
        args = args[:-5].strip()
    elif args.endswith(" low"):
        priority = "low"
        args = args[:-4].strip()
    t = tasks.add(args, priority)
    emoji = "🔴" if priority == "high" else "🟡" if priority == "medium" else "🟢"
    await update.message.reply_text(f"✅ *Task Add!* {emoji} {t['title']}\n🆔 `#{t['id']}`", parse_mode="Markdown")

async def cmd_done(update, ctx):
    if not ctx.args:
        await update.message.reply_text("`/done 3` - Task ID do", parse_mode="Markdown")
        return
    try:
        t = tasks.complete(int(ctx.args[0]))
        if t:
            await update.message.reply_text(f"🎉 *Complete!* ✅ {t['title']}\n💪 Wah bhai!", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Task nahi mila ya pehle hi done hai.")
    except:
        pass

async def cmd_deltask(update, ctx):
    if not ctx.args:
        return
    try:
        ok = tasks.delete(int(ctx.args[0]))
        await update.message.reply_text("🗑 *Task Delete!*" if ok else "❌ Nahi mila", parse_mode="Markdown")
    except:
        pass

async def cmd_all_tasks(update, ctx):
    all_t = tasks.all_tasks()
    if not all_t:
        await update.message.reply_text("📋 Koi task nahi! `/task Kaam` se add karo")
        return
    txt = f"📋 *SAARE TASKS ({len(all_t)})*\n━━━━━━━━━━━━━━━━\n\n"
    pending = [t for t in all_t if not t["done"]]
    completed = [t for t in all_t if t["done"]]
    if pending:
        txt += "*⏳ PENDING:*\n"
        for t in pending:
            e = "🔴" if t["priority"] == "high" else "🟡" if t["priority"] == "medium" else "🟢"
            txt += f"{e} *#{t['id']}* {t['title']}\n"
        txt += "\n"
    if completed:
        txt += "*✅ COMPLETED:*\n"
        for t in completed[-10:]:
            txt += f"✓ *#{t['id']}* {t['title']} _{t.get('completed_date', '')}_\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_completed_tasks(update, ctx):
    comp = tasks.completed_tasks()
    if not comp:
        await update.message.reply_text("✅ Koi completed task nahi! `/done 3` se complete karo")
        return
    txt = f"✅ *COMPLETED TASKS ({len(comp)})*\n━━━━━━━━━━━━━━━━\n\n"
    for t in comp[-15:]:
        txt += f"✓ *#{t['id']}* {t['title']}\n  📅 {t.get('completed_date', '')}\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_pending_tasks(update, ctx):
    pend = tasks.pending()
    if not pend:
        await update.message.reply_text("🎉 Koi pending task nahi! Sab clear!")
        return
    txt = f"⏳ *PENDING TASKS ({len(pend)})*\n━━━━━━━━━━━━━━━━\n\n"
    for t in pend:
        e = "🔴" if t["priority"] == "high" else "🟡" if t["priority"] == "medium" else "🟢"
        txt += f"{e} *#{t['id']}* {t['title']}\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_verify(update, ctx):
    if not ctx.args or not verify_secret(ctx.args[0]):
        await update.message.reply_text("❌ Galat code! `/verify Rk1996`")
        return
    await update.message.reply_text("✅ *Verified!*\n\nAb `/taskhistory` use karo.", parse_mode="Markdown")

async def cmd_task_history(update, ctx):
    if not ctx.args or not verify_secret(ctx.args[0]):
        await update.message.reply_text("❌ Galat code! `/taskhistory Rk1996`")
        return
    history = tasks.get_history()
    if not history:
        await update.message.reply_text("📋 Koi task history nahi!")
        return
    txt = f"🔓 *TASK HISTORY ({len(history)})*\n━━━━━━━━━━━━━━━━\n\n"
    for t in history[-20:]:
        txt += f"✓ {t.get('title', '')}\n  📅 {t.get('completed_date', '')}\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_remember(update, ctx):
    if not ctx.args:
        return
    fact = " ".join(ctx.args)
    mem.add_fact(fact)
    await update.message.reply_text(f"🧠 *Yaad Kar Liya!* ✅\n\n_{fact}_\n\n🔒 Chat clear ke baad bhi safe!", parse_mode="Markdown")

async def cmd_recall(update, ctx):
    facts = mem.data["facts"]
    if not facts:
        await update.message.reply_text("🧠 Kuch yaad nahi! `/remember Koi baat`")
        return
    txt = f"🧠 *YAADDASHT ({len(facts)} facts)*\n\n"
    for f in facts[-15:]:
        txt += f"  📌 {f['f']}\n  _{f['d']}_\n\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def cmd_remind(update, ctx):
    await update.message.reply_text("⏰ *Reminder System*\n\n`/remind 30m Chai peeni hai`\n`/remind 15:30 Doctor appointment`\n`/remind 8:00 Uthna daily`", parse_mode="Markdown")

async def cmd_clear(update, ctx):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Haan Clear Karo", callback_data="confirm_clear_chat"),
         InlineKeyboardButton("❌ Nahi", callback_data="menu")]
    ])
    await update.message.reply_text(
        f"🧹 *Chat Clear Karna Hai?*\n\n📊 {chat_hist.count()} messages abhi hain\n\n"
        "⚠️ Sirf chat history clear hogi\n"
        "✅ Memory, Tasks — sab safe rahega!",
        parse_mode="Markdown", reply_markup=kb
    )

# ═══════════════ CALLBACK ═══════════════
async def callback(update, ctx):
    q = update.callback_query
    await q.answer()
    d = q.data
    
    if d == "menu":
        await q.message.reply_text("🏠 *Main Menu*", parse_mode="Markdown", reply_markup=main_kb())
    
    elif d == "tasks":
        pending = tasks.pending()
        if not pending:
            await q.message.reply_text("🎉 Koi pending task nahi! `/task Kaam` se add karo")
            return
        txt = f"📋 *PENDING TASKS ({len(pending)})*\n\n"
        kb = []
        for t in pending[:12]:
            e = "🔴" if t["priority"] == "high" else "🟡" if t["priority"] == "medium" else "🟢"
            txt += f"{e} *#{t['id']}* {t['title']}\n"
            kb.append([InlineKeyboardButton(f"✅ #{t['id']}: {t['title'][:32]}", callback_data=f"done_{t['id']}")])
        kb.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
        await q.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    
    elif d == "memory":
        facts = mem.data["facts"]
        if facts:
            txt = f"🧠 *YAADDASHT ({len(facts)} facts)*\n🔒 Chat clear ke baad bhi safe\n\n"
            txt += "\n".join(f"  📌 {f['f']}" for f in facts[-12:])
        else:
            txt = "🧠 Kuch yaad nahi!"
        await q.message.reply_text(txt, parse_mode="Markdown")
    
    elif d == "clear_chat":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Haan", callback_data="confirm_clear_chat"),
             InlineKeyboardButton("❌ Nahi", callback_data="menu")]
        ])
        await q.message.reply_text(
            f"🧹 *Clear?* {chat_hist.count()} msgs\n✅ Data safe!",
            parse_mode="Markdown", reply_markup=kb
        )
    
    elif d == "confirm_clear_chat":
        count = chat_hist.clear()
        await q.message.reply_text(
            f"🧹 *Chat Clear!* 🗑 {count} messages\n\n🔒 Memory, Tasks — sab safe!\n_Fresh start!_ 🚀",
            parse_mode="Markdown", reply_markup=main_kb()
        )
    
    elif d == "motivate":
        reply = await ai_chat("Mujhe powerful motivation de Hindi mein. 3-4 line. Real, raw.")
        if reply == "OFFLINE":
            await q.message.reply_text("💡 AI abhi offline hai. Thodi der baad try karo.")
        else:
            await q.message.reply_text(f"💡 *Motivation:*\n\n{reply}", parse_mode="Markdown")
    
    elif d.startswith("done_"):
        tid = int(d.split("_")[1])
        t = tasks.complete(tid)
        if t:
            await q.message.reply_text(f"🎉 *Complete!* ✅ {t['title']}\n💪 Wah bhai!", parse_mode="Markdown")
        else:
            await q.message.reply_text("❌ Task nahi mila ya pehle hi done hai.")

# ═══════════════ MESSAGE HANDLER ═══════════════
async def handle_msg(update, ctx):
    user = update.effective_user
    chat_id = update.effective_chat.id
    msg = update.message.text
    
    chat_hist.track_msg(chat_id, update.message.message_id)
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    reply = await ai_chat(msg, chat_id=chat_id)
    
    if reply == "OFFLINE":
        offline_queue.add(user.id, chat_id, user.first_name, msg)
        sent = await update.message.reply_text(
            "⚠️ *AI Abhi Offline Hai!*\n\n"
            "📥 Aapka message save kar liya hai!\n"
            "Jab AI online hoga, automatically process hoga.",
            parse_mode="Markdown"
        )
    else:
        try:
            sent = await update.message.reply_text(reply, parse_mode="Markdown")
        except:
            sent = await update.message.reply_text(reply)
    
    chat_hist.track_msg(chat_id, sent.message_id)

# ═══════════════ MAIN ═══════════════
def main():
    log.info("Bot Starting...")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    handlers = [
        ("start", cmd_start),
        ("help", cmd_help),
        ("task", cmd_task),
        ("done", cmd_done),
        ("deltask", cmd_deltask),
        ("alltasks", cmd_all_tasks),
        ("completed", cmd_completed_tasks),
        ("pending", cmd_pending_tasks),
        ("verify", cmd_verify),
        ("taskhistory", cmd_task_history),
        ("remember", cmd_remember),
        ("recall", cmd_recall),
        ("remind", cmd_remind),
        ("clear", cmd_clear),
    ]
    
    for cmd, handler in handlers:
        app.add_handler(CommandHandler(cmd, handler))
    
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    
    log.info("Bot ready!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()