#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — Rk Bot Addon
====================================
Ye file purane code se BILKUL ALAG hai — sirf import karke use karo.
Koi bhi purana code touch nahi kiya.

FEATURES:
  - Voice message receive karo Telegram se
  - Gemini API se transcribe karo (free, no Whisper needed)
  - Auto detect: diary save karna hai ya task banana hai
  - Google Sheets "Voice Notes" tab mein backup
  - /voicenotes command se sab dekho

SHEET TAB: "Voice Notes"
HEADERS: ID, Date, Time, Transcript, Saved To, Duration, Status

INSTALL:
  1. Is file ko bot ke folder mein daalo
  2. main.py / rk_bot.py mein niche likha import add karo:
        from voice_note_handler import register_voice_handlers
        register_voice_handlers(app)
  3. Google Sheet mein "Voice Notes" tab manually banana (ya bot khud banayega)
"""

import os
import json
import logging
import time
import urllib.request
import urllib.error
import tempfile
import re

from datetime import datetime, timezone, timedelta
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, CommandHandler, filters

log = logging.getLogger(__name__)

# ── Imports from existing secure_data_manager ──────────────────
try:
    from secure_data_manager import (
        diary, tasks, memory, sheets_backup, repo_manager,
        now_ist, today_str, now_str, PrivateStore
    )
    _SDM_AVAILABLE = True
except ImportError:
    log.error("secure_data_manager import failed! Voice handler disabled.")
    _SDM_AVAILABLE = False

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_VISION_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"

_last_call = 0

def _rate_limit():
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 2:
        time.sleep(2 - elapsed)
    _last_call = time.time()


# ================================================================
# VOICE NOTE STORE  →  "Voice Notes" sheet tab
# ================================================================

class VoiceNoteStore:
    """
    Stores voice note transcripts locally + syncs to Google Sheets.
    Tab: "Voice Notes"
    Headers: ID, Date, Time, Transcript, Saved To, Duration (sec), Status
    """
    TAB_KEY     = "VoiceNotes"
    TAB_NAME    = "Voice Notes"
    HEADERS     = ["ID", "Date", "Time", "Transcript", "Saved To", "Duration (sec)", "Status"]

    def __init__(self):
        if not _SDM_AVAILABLE:
            return
        self.store = PrivateStore("voice_notes", {"list": [], "counter": 0})
        self._ensure_sheet_tab()

    def _ensure_sheet_tab(self):
        """Create sheet tab if not exists"""
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
                # Cache it
                if self.TAB_NAME not in sheets_backup._ws_cache:
                    ws = sheets_backup._book.worksheet(self.TAB_NAME)
                    sheets_backup._ws_cache[self.TAB_NAME] = ws
        except Exception as e:
            log.warning(f"VoiceNotes tab ensure error: {e}")

    def _append_to_sheet(self, row):
        try:
            if not sheets_backup._book:
                return
            ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if not ws:
                self._ensure_sheet_tab()
                ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if ws:
                ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
                log.info(f"[Voice Notes] row appended to sheet")
        except Exception as e:
            log.warning(f"VoiceNotes sheet append error: {e}")

    def add(self, transcript: str, saved_to: str = "diary", duration: int = 0, status: str = "Success"):
        if not _SDM_AVAILABLE:
            return None
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        vid = self.store.data["counter"]
        entry = {
            "id":         vid,
            "date":       today_str(),
            "time":       now_str(),
            "transcript": transcript,
            "saved_to":   saved_to,
            "duration":   duration,
            "status":     status,
        }
        self.store.data["list"].append(entry)
        self.store.data["list"] = self.store.data["list"][-500:]
        self.store.save()

        # Sync to sheet
        self._append_to_sheet([
            vid, today_str(), now_str(),
            transcript[:500],   # truncate very long transcripts
            saved_to,
            duration,
            status,
        ])
        return entry

    def get_recent(self, n=10):
        return self.store.data.get("list", [])[-n:]

    def get_all(self):
        return self.store.data.get("list", [])


# Singleton
if _SDM_AVAILABLE:
    voice_store = VoiceNoteStore()
else:
    voice_store = None


# ================================================================
# TRANSCRIPTION via Gemini (audio → text)
# ================================================================

async def _transcribe_with_gemini(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str | None:
    """
    Gemini 2.5 Flash can handle audio inline (base64).
    Returns transcript string or None on failure.
    """
    if not GEMINI_API_KEY:
        log.error("GEMINI_API_KEY not set — cannot transcribe")
        return None

    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    payload = json.dumps({
        "contents": [{
            "role": "user",
            "parts": [
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": audio_b64
                    }
                },
                {
                    "text": (
                        "Yeh ek voice message hai. Isko exactly transcribe karo — "
                        "jo bola gaya hai woh word-for-word likho. "
                        "Sirf transcription do, koi explanation nahi, koi prefix nahi. "
                        "Hinglish ya Hindi ya English jo bhi bola ho woh likho."
                    )
                }
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1000
        }
    }).encode("utf-8")

    _rate_limit()
    url = GEMINI_VISION_URL.format(key=GEMINI_API_KEY)
    try:
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            log.info(f"Transcription done: {text[:80]}")
            return text
    except Exception as e:
        log.error(f"Gemini transcribe error: {e}")
        return None


# ================================================================
# SMART CLASSIFY: Transcript se decide karo kahan save karna hai
# ================================================================

def _classify_transcript(text: str) -> str:
    """
    Returns: 'task', 'diary', 'memory', 'reminder', 'expense', 'general'
    """
    lower = text.lower()

    task_words = ["karna hai", "krna hai", "karna he", "todo", "task", "kaam karna",
                  "bhoolna mat", "yaad rakhna", "reminder", "remind", "alarm",
                  "meeting", "call karna", "buy", "kharidna"]
    expense_words = ["kharcha", "karcha", "kharch", "rupees", "rs ", "spent", "lagaye",
                     "diye", "paisa", "paise", "expense"]
    diary_words   = ["aaj", "kal", "din", "feel", "hua", "thi", "tha", "gaya", "gayi",
                     "diary", "likho", "save", "note", "sochi", "socha", "mood"]
    memory_words  = ["yaad", "remember", "note karo", "save karo", "important",
                     "password", "number", "address", "naam", "dob"]

    task_score    = sum(1 for w in task_words    if w in lower)
    expense_score = sum(1 for w in expense_words if w in lower)
    diary_score   = sum(1 for w in diary_words   if w in lower)
    memory_score  = sum(1 for w in memory_words  if w in lower)

    # Number present → likely expense
    if re.search(r'\d+', lower) and expense_score >= 1:
        return "expense"

    best = max(
        [("task", task_score), ("diary", diary_score),
         ("memory", memory_score), ("expense", expense_score)],
        key=lambda x: x[1]
    )
    return best[0] if best[1] > 0 else "diary"


# ================================================================
# MAIN VOICE HANDLER
# ================================================================

async def handle_voice_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Telegram voice message receive karo → transcribe → classify → save
    """
    if not _SDM_AVAILABLE:
        await update.message.reply_text("❌ Voice feature unavailable (secure_data_manager missing)")
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    user_name = update.effective_user.first_name or "User"
    duration  = getattr(voice, "duration", 0)

    # Status message
    status_msg = await update.message.reply_text(
        f"🎙️ *Voice note mila! ({duration}s)*\n\n⏳ Transcribe ho raha hai... InshAllah!",
        parse_mode="Markdown"
    )

    # Download audio
    try:
        file_obj = await ctx.bot.get_file(voice.file_id)
        audio_bytes = await file_obj.download_as_bytearray()
        audio_bytes = bytes(audio_bytes)
    except Exception as e:
        log.error(f"Voice download error: {e}")
        await status_msg.edit_text("❌ Voice download fail ho gaya!")
        return

    # Detect mime type
    mime_type = getattr(voice, "mime_type", "audio/ogg") or "audio/ogg"
    if "mp4" in mime_type or "m4a" in mime_type:
        mime_type = "audio/mp4"
    elif "webm" in mime_type:
        mime_type = "audio/webm"
    else:
        mime_type = "audio/ogg"

    # Transcribe
    transcript = await _transcribe_with_gemini(audio_bytes, mime_type)

    if not transcript:
        await status_msg.edit_text(
            "❌ *Transcription fail ho gaya!*\n\nNetwork ya Gemini API issue.\nDobara try karo.",
            parse_mode="Markdown"
        )
        if voice_store:
            voice_store.add("[Transcription Failed]", "none", duration, "Failed")
        return

    # Classify
    category = _classify_transcript(transcript)

    # Save based on category
    saved_to = "diary"
    extra_info = ""

    if category == "task":
        t = tasks.add(transcript[:80])
        saved_to  = f"task #{t['id']}"
        extra_info = f"✅ Task #{t['id']} bana diya!"

    elif category == "expense":
        # Extract amount
        m = re.search(r'(\d+(?:\.\d+)?)', transcript)
        if m:
            amount = float(m.group(1))
            desc   = re.sub(r'\d+(?:\.\d+)?', "", transcript).strip() or "Voice note expense"
            from secure_data_manager import expenses
            expenses.add(amount, desc[:60])
            saved_to  = "expenses"
            extra_info = f"💸 Rs.{amount} expense add ho gaya!"
        else:
            diary.add(f"[Voice] {transcript}")
            saved_to  = "diary"
            extra_info = "📖 Diary mein save kiya (amount nahi mila)"

    elif category == "memory":
        memory.add(transcript)
        saved_to  = "memory"
        extra_info = "🧠 Memory mein save ho gaya!"

    else:  # diary (default)
        diary.add(f"[Voice] {transcript}")
        saved_to  = "diary"
        extra_info = "📖 Diary mein save ho gaya!"

    # Store in VoiceNotes
    if voice_store:
        voice_store.add(transcript, saved_to, duration, "Success")

    # Reply
    await status_msg.edit_text(
        f"🎙️ *Voice Note Transcribed! Alhamdulillah!* ✅\n\n"
        f"📝 *Transcript:*\n_{transcript[:300]}_\n\n"
        f"{'─' * 20}\n"
        f"💾 *{extra_info}*\n\n"
        f"📊 Sheets mein bhi save!\n"
        f"🔁 /voicenotes — Purane dekho",
        parse_mode="Markdown"
    )

    # Log
    try:
        sheets_backup.log_event("voice_note", user_name, f"[{saved_to}] {transcript[:80]}")
    except Exception:
        pass


# ================================================================
# /voicenotes COMMAND
# ================================================================

async def cmd_voicenotes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show recent voice note transcripts"""
    if not voice_store:
        await update.message.reply_text("❌ Voice store unavailable")
        return

    recent = voice_store.get_recent(10)
    if not recent:
        await update.message.reply_text(
            "🎙️ Koi voice note nahi hai abhi.\n\nVoice message bhejo — main transcribe kar dunga!",
            parse_mode="Markdown"
        )
        return

    lines = []
    for v in reversed(recent):
        lines.append(
            f"🎙️ #{v['id']} *{v['date']}* {v['time']}\n"
            f"   💾 {v['saved_to']} | ⏱ {v.get('duration', 0)}s\n"
            f"   _{v['transcript'][:100]}_"
        )

    await update.message.reply_text(
        f"🎙️ *Recent Voice Notes ({len(recent)}):*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown"
    )


# ================================================================
# REGISTER HANDLERS  ←  main.py mein ye call karo
# ================================================================

def register_voice_handlers(app):
    """
    Call this in main() AFTER all other handlers:
        from voice_note_handler import register_voice_handlers
        register_voice_handlers(app)
    """
    # Voice message handler
    app.add_handler(MessageHandler(
        filters.VOICE | filters.AUDIO,
        handle_voice_message
    ))
    # Command
    app.add_handler(CommandHandler("voicenotes", cmd_voicenotes))

    log.info("✅ Voice Note handlers registered!")
    log.info("   - VOICE/AUDIO messages → transcribe + save")
    log.info("   - /voicenotes → recent list")
