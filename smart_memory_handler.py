#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMART CONTEXT MEMORY HANDLER — Rk Bot Addon
=============================================
Ye file purane code se BILKUL ALAG hai — sirf import karke use karo.
Koi bhi purana code touch nahi kiya.

FEATURES:
  - Structured key-value context memory (naam, date, event, etc.)
  - Natural language se save: "doctor appointment kal tha yaad hai?"
  - Natural language se retrieve: "doctor ka kya tha?"
  - Gemini se smart search — fuzzy match
  - Google Sheets "Smart Memory" tab mein backup
  - Auto-tag: people, dates, events, tasks, info
  - /memory command: list/search/delete

SHEET TAB: "Smart Memory"
HEADERS: ID, Date, Time, Key, Value, Tags, Source

INSTALL:
  1. Is file ko bot ke folder mein daalo
  2. main.py mein niche likha add karo:
        from smart_memory_handler import register_memory_handlers
        register_memory_handlers(app)
  3. "Smart Memory" sheet tab bot khud banayega
"""

import os
import json
import logging
import time
import urllib.request
import re

from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

log = logging.getLogger(__name__)

# ── Imports from existing secure_data_manager ──────────────────
try:
    from secure_data_manager import (
        sheets_backup, now_ist, today_str, now_str, PrivateStore
    )
    _SDM_AVAILABLE = True
except ImportError:
    log.error("secure_data_manager import failed! Smart memory disabled.")
    _SDM_AVAILABLE = False

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={key}"

_last_call = 0

def _rate_limit():
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 2:
        time.sleep(2 - elapsed)
    _last_call = time.time()

def _call_gemini(prompt: str, max_tokens: int = 300) -> str | None:
    if not GEMINI_API_KEY:
        return None
    _rate_limit()
    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens}
    }).encode("utf-8")
    try:
        url = GEMINI_URL.format(key=GEMINI_API_KEY)
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        log.warning(f"Gemini smart memory error: {e}")
        return None


# ================================================================
# SMART MEMORY STORE  →  "Smart Memory" sheet tab
# ================================================================

class SmartMemoryStore:
    """
    Key-value context memory with tagging and Sheets sync.
    Tab: "Smart Memory"
    Headers: ID, Date, Time, Key, Value, Tags, Source
    """
    TAB_NAME = "Smart Memory"
    HEADERS  = ["ID", "Date", "Time", "Key", "Value", "Tags", "Source"]

    def __init__(self):
        if not _SDM_AVAILABLE:
            return
        self.store = PrivateStore("smart_memory", {"entries": [], "counter": 0})
        self._ensure_sheet_tab()

    def _ensure_sheet_tab(self):
        try:
            if not sheets_backup._book:
                return
            existing = [ws.title for ws in sheets_backup._book.worksheets()]
            if self.TAB_NAME not in existing:
                ws = sheets_backup._book.add_worksheet(
                    title=self.TAB_NAME, rows=2000, cols=len(self.HEADERS)
                )
                ws.append_row(self.HEADERS, value_input_option="USER_ENTERED")
                sheets_backup._ws_cache[self.TAB_NAME] = ws
                log.info(f"Created sheet tab: '{self.TAB_NAME}'")
            else:
                if self.TAB_NAME not in sheets_backup._ws_cache:
                    ws = sheets_backup._book.worksheet(self.TAB_NAME)
                    sheets_backup._ws_cache[self.TAB_NAME] = ws
        except Exception as e:
            log.warning(f"SmartMemory tab ensure error: {e}")

    def _append_to_sheet(self, row):
        try:
            ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if not ws:
                self._ensure_sheet_tab()
                ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if ws:
                ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
        except Exception as e:
            log.warning(f"SmartMemory sheet append: {e}")

    def save(self, key: str, value: str, tags: str = "", source: str = "user") -> dict:
        """Save a context memory entry"""
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        mid = self.store.data["counter"]
        entry = {
            "id":     mid,
            "date":   today_str(),
            "time":   now_str(),
            "key":    key.strip()[:100],
            "value":  value.strip()[:500],
            "tags":   tags.strip()[:100],
            "source": source,
        }
        self.store.data["entries"].append(entry)
        self.store.data["entries"] = self.store.data["entries"][-1000:]
        self.store.save()
        self._append_to_sheet([mid, today_str(), now_str(), key[:100], value[:500], tags, source])
        return entry

    def search(self, query: str, limit: int = 5) -> list:
        """Simple keyword search across key+value+tags"""
        query_lower = query.lower()
        keywords = query_lower.split()
        scored = []
        for entry in self.store.data.get("entries", []):
            text = f"{entry['key']} {entry['value']} {entry['tags']}".lower()
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: (-x[0], x[1]["id"] * -1))
        return [e for _, e in scored[:limit]]

    def delete(self, mid: int) -> bool:
        before = len(self.store.data["entries"])
        self.store.data["entries"] = [e for e in self.store.data["entries"] if e["id"] != mid]
        if len(self.store.data["entries"]) < before:
            self.store.save()
            return True
        return False

    def get_all(self) -> list:
        return self.store.data.get("entries", [])

    def get_recent(self, n: int = 10) -> list:
        return self.store.data.get("entries", [])[-n:]


# Singleton
if _SDM_AVAILABLE:
    smart_mem = SmartMemoryStore()
else:
    smart_mem = None


# ================================================================
# EXTRACT KEY-VALUE from natural language using Gemini
# ================================================================

def _extract_kv_from_text(text: str) -> tuple[str, str, str]:
    """
    Returns (key, value, tags) from natural language text.
    E.g. "Doctor appointment 15 May ko hai" → ("doctor appointment", "15 May", "event,date")
    """
    prompt = f"""Yeh ek personal memory note hai: "{text}"

Isse ek structured key-value mein convert karo.
Sirf JSON do, koi explanation nahi:
{{
  "key": "chhota topic/kya cheez hai (max 6 words)",
  "value": "poori detail (max 50 words)",
  "tags": "comma separated: person/event/date/task/info/health/money/reminder"
}}

Examples:
"doctor se milna tha kal" → {{"key": "doctor appointment", "value": "kal doctor se milna tha", "tags": "event,health"}}
"Simran ka number 9876543210 hai" → {{"key": "simran contact", "value": "9876543210", "tags": "person,info"}}
"password gmail Abc123 hai" → {{"key": "gmail password", "value": "Abc123", "tags": "info"}}"""

    result = _call_gemini(prompt, max_tokens=150)
    if not result:
        # Fallback: raw save
        words = text.split()[:6]
        return " ".join(words), text, "info"

    try:
        # Strip markdown fences
        clean = result.replace("```json", "").replace("```", "").strip()
        data  = json.loads(clean)
        return (
            data.get("key", text[:40]),
            data.get("value", text),
            data.get("tags", "info")
        )
    except Exception:
        words = text.split()[:6]
        return " ".join(words), text, "info"


# ================================================================
# NATURAL LANGUAGE TRIGGER DETECTION
# ================================================================

SAVE_TRIGGERS = [
    "yaad rakhna", "yaad rakho", "note karo", "note kr", "save karo",
    "remember karo", "memory mein", "context mein", "context save",
    "smart memory", "important note", "baat yaad rakhna",
    "bhoolna mat", "bhulna nahi", "note this", "remember this",
    "save this",
]

RETRIEVE_TRIGGERS = [
    "yaad hai kya", "yaad hai?", "bata", "batao", "kya tha",
    "kya thi", "kab tha", "kab thi", "kahan tha", "kaun tha",
    "mujhe yaad krao", "mujhe bata", "poochh raha hoon",
    "kya save tha", "kya note tha", "memory check",
    "context kya", "yaad dila", "recall",
]

def is_save_intent(text: str) -> bool:
    lower = text.lower()
    return any(t in lower for t in SAVE_TRIGGERS)

def is_retrieve_intent(text: str) -> bool:
    lower = text.lower()
    return any(t in lower for t in RETRIEVE_TRIGGERS)


# ================================================================
# SMART RETRIEVE with Gemini ranking
# ================================================================

def _smart_retrieve(query: str) -> list:
    """Search + optionally rerank with Gemini"""
    if not smart_mem:
        return []

    # Basic keyword search
    results = smart_mem.search(query, limit=10)
    if not results:
        return []

    if len(results) <= 3 or not GEMINI_API_KEY:
        return results[:3]

    # Gemini rerank
    entries_text = "\n".join(
        f"{i+1}. Key: {e['key']} | Value: {e['value']} | Date: {e['date']}"
        for i, e in enumerate(results[:10])
    )
    prompt = f"""User query: "{query}"

Niche memory entries hain. Sirf 1-3 most relevant entry numbers do (comma separated):
{entries_text}

Sirf numbers do, koi explanation nahi. Example: 1,3"""

    ranking = _call_gemini(prompt, max_tokens=20)
    if ranking:
        try:
            indices = [int(x.strip()) - 1 for x in ranking.split(",") if x.strip().isdigit()]
            reranked = [results[i] for i in indices if 0 <= i < len(results)]
            if reranked:
                return reranked[:3]
        except Exception:
            pass

    return results[:3]


# ================================================================
# /memory COMMAND
# ================================================================

async def cmd_memory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /memory — sab dekho
    /memory search kya doctor tha — search karo
    /memory del 5 — delete karo
    /memory save doctor appointment kal hai — save karo
    """
    if not smart_mem:
        await update.message.reply_text("❌ Smart Memory unavailable")
        return

    args = ctx.args or []

    if not args:
        recent = smart_mem.get_recent(8)
        if not recent:
            await update.message.reply_text(
                "🧠 *Smart Memory*\n\nKoi entry nahi hai abhi.\n\n"
                "*Save karo:*\n"
                "`/memory save doctor appointment kal hai`\n\n"
                "*Search karo:*\n"
                "`/memory search doctor`\n\n"
                "Ya seedha bolo: `doctor appointment yaad rakhna kal hai`",
                parse_mode="Markdown"
            )
            return

        lines = []
        for e in reversed(recent):
            lines.append(
                f"🔹 #{e['id']} *{e['key']}*\n"
                f"   {e['value'][:80]}\n"
                f"   📅 {e['date']} | 🏷 {e.get('tags','')}"
            )
        await update.message.reply_text(
            f"🧠 *Smart Memory — Recent ({len(recent)}):*\n\n" + "\n\n".join(lines) +
            "\n\n`/memory search [query]` — dhundho\n`/memory del [id]` — delete",
            parse_mode="Markdown"
        )
        return

    sub = args[0].lower()

    if sub in ("del", "delete", "hata"):
        if len(args) < 2:
            await update.message.reply_text("/memory del [id]")
            return
        try:
            mid = int(args[1])
            ok  = smart_mem.delete(mid)
            if ok:
                await update.message.reply_text(f"🗑️ Memory #{mid} delete ho gaya! ✅")
            else:
                await update.message.reply_text(f"❌ #{mid} nahi mila!")
        except Exception:
            await update.message.reply_text("❌ Invalid ID")
        return

    if sub in ("save", "add", "note"):
        text = " ".join(args[1:]).strip()
        if not text:
            await update.message.reply_text("/memory save [jo yaad rakhna hai]")
            return
        key, value, tags = _extract_kv_from_text(text)
        e = smart_mem.save(key, value, tags, source="command")
        await update.message.reply_text(
            f"🧠 *Memory Save Ho Gaya! Alhamdulillah!* ✅\n\n"
            f"🔑 *Key:* {e['key']}\n"
            f"📝 *Value:* {e['value']}\n"
            f"🏷 *Tags:* {e['tags']}\n\n"
            f"📊 Sheets mein bhi save!",
            parse_mode="Markdown"
        )
        return

    if sub in ("search", "dhundho", "find", "kya"):
        query = " ".join(args[1:]).strip()
        if not query:
            await update.message.reply_text("/memory search [kya dhundna hai]")
            return
        results = _smart_retrieve(query)
        if not results:
            await update.message.reply_text(
                f"🔍 `{query}` ke baare mein koi memory nahi mili.\n\n"
                f"Pehle save karo: `/memory save {query} — yahan likho`",
                parse_mode="Markdown"
            )
            return
        lines = []
        for e in results:
            lines.append(
                f"🔹 #{e['id']} *{e['key']}*\n"
                f"   {e['value']}\n"
                f"   📅 {e['date']}"
            )
        await update.message.reply_text(
            f"🔍 *'{query}' ke results:*\n\n" + "\n\n".join(lines),
            parse_mode="Markdown"
        )
        return

    # Default: treat all args as search query
    query = " ".join(args)
    results = _smart_retrieve(query)
    if results:
        lines = [f"🔹 #{e['id']} *{e['key']}*\n   {e['value']}\n   📅 {e['date']}" for e in results]
        await update.message.reply_text(
            f"🔍 *Memory results:*\n\n" + "\n\n".join(lines),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❓ `{query}` ke baare mein koi memory nahi.\n\nSave karo: /memory save {query} ...",
            parse_mode="Markdown"
        )


# ================================================================
# NATURAL LANGUAGE MESSAGE INTERCEPTOR
# ================================================================

async def handle_smart_memory_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    NL messages intercept karo — agar memory save/retrieve intent ho.
    Returns True if handled, False agar nahi (taaki main handler process kare).

    NOTE: Ye handler sirf tab kaam karega jab explicitly call kiya jaye.
    Main message handler mein integrate karna padega.
    """
    if not update.message or not update.message.text:
        return False
    if not smart_mem:
        return False

    text = update.message.text.strip()
    if text.startswith("/"):
        return False

    if is_save_intent(text):
        # Remove trigger words and save
        clean = text
        for trigger in SAVE_TRIGGERS:
            clean = re.sub(re.escape(trigger), "", clean, flags=re.IGNORECASE)
        clean = clean.strip(" ,-:.")
        if not clean:
            return False

        key, value, tags = _extract_kv_from_text(clean)
        e = smart_mem.save(key, value, tags, source="nl")
        await update.message.reply_text(
            f"🧠 *Yaad Rakh Liya! Alhamdulillah!* ✅\n\n"
            f"🔑 {e['key']}\n📝 {e['value']}\n\n"
            f"📊 Sheets mein save!\n`/memory search {e['key']}` — baad mein dhundho",
            parse_mode="Markdown"
        )
        return True

    if is_retrieve_intent(text):
        # Extract search query
        clean = text
        for trigger in RETRIEVE_TRIGGERS:
            clean = re.sub(re.escape(trigger), "", clean, flags=re.IGNORECASE)
        clean = re.sub(r'\b(mujhe|kya|tha|thi|ko|se|ka|ki|ke|ne|pe|par)\b', '', clean, flags=re.IGNORECASE)
        clean = " ".join(clean.split()).strip()

        if not clean or len(clean) < 2:
            return False

        results = _smart_retrieve(clean)
        if results:
            lines = [f"🔹 *{e['key']}*\n   {e['value']}\n   📅 {e['date']}" for e in results]
            await update.message.reply_text(
                f"🧠 *Memory mein mila:*\n\n" + "\n\n".join(lines) +
                "\n\nJazakAllah! 🌟",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"🧠 `{clean}` ke baare mein koi memory nahi mili.\n\n"
                f"Save karna hai? `/memory save {clean} — detail yahan`",
                parse_mode="Markdown"
            )
        return True

    return False


# ================================================================
# INTEGRATION HELPER for rk_bot.py handle_message
# ================================================================

async def check_smart_memory_intent(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Call this at the TOP of handle_message() in rk_bot.py:

        from smart_memory_handler import check_smart_memory_intent
        ...
        async def handle_message(update, ctx):
            if await check_smart_memory_intent(update, ctx):
                return   # smart memory ne handle kar liya
            ...rest of handler...

    Returns True if message was handled by smart memory.
    """
    return await handle_smart_memory_message(update, ctx)


# ================================================================
# REGISTER HANDLERS  ←  main.py mein ye call karo
# ================================================================

def register_memory_handlers(app):
    """
    Call this in main() BEFORE general message handler:
        from smart_memory_handler import register_memory_handlers
        register_memory_handlers(app)
    """
    app.add_handler(CommandHandler("memory", cmd_memory))
    log.info("✅ Smart Memory handlers registered!")
    log.info("   - /memory — list/search/save/delete")
    log.info("   - NL: 'doctor yaad rakhna' → auto-save")
    log.info("   - NL: 'doctor kya tha' → auto-retrieve")
    log.info("   - Google Sheets 'Smart Memory' tab sync")
