#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — Rk Bot Addon
====================================
Gemini API based transcription — NO ffmpeg, NO speech_recognition needed!
Works on GitHub Actions out of the box.

FIXES:
  - Python 3.9 compatible: str | None → Optional[str]
  - Better mime_type detection for Telegram voice messages
  - Improved error logging for easier debugging
  - Rate limit handling improved
"""

import os
import json
import logging
import time
import urllib.request
import urllib.error
import re
import base64
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, CommandHandler, filters

log = logging.getLogger(__name__)

# ── Imports from existing secure_data_manager ──────────────────
try:
    from secure_data_manager import (
        diary, tasks, memory, expenses, sheets_backup, repo_manager,
        now_ist, today_str, now_str, PrivateStore
    )
    _SDM_AVAILABLE = True
except ImportError:
    log.error("secure_data_manager import failed! Voice handler disabled.")
    _SDM_AVAILABLE = False

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Gemini 1.5 Flash — audio transcription ke liye best
GEMINI_VISION_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"

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
    TAB_KEY  = "VoiceNotes"
    TAB_NAME = "Voice Notes"
    HEADERS  = ["ID", "Date", "Time", "Transcript", "Saved To", "Duration", "Status"]

    def __init__(self):
        if not _SDM_AVAILABLE:
            return
        self.store = PrivateStore("voice_notes", {"list": [], "counter": 0})
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
        self._append_to_sheet([vid, today_str(), now_str(), transcript[:500], saved_to, duration, status])
        return entry

    def get_recent(self, n: int = 10):
        return self.store.data.get("list", [])[-n:]

    def get_all(self):
        return self.store.data.get("list", [])


if _SDM_AVAILABLE:
    voice_store = VoiceNoteStore()
else:
    voice_store = None


# ================================================================
# MIME TYPE HELPER
# ================================================================

def _get_mime_type(voice) -> str:
    """
    Telegram voice messages → usually audio/ogg (opus codec)
    Telegram audio files   → can be audio/mp3, audio/mp4, audio/mpeg etc.
    Gemini supports: audio/wav, audio/mp3, audio/aiff, audio/aac,
                     audio/ogg, audio/flac, audio/webm
    """
    raw = getattr(voice, "mime_type", None) or ""
    raw = raw.lower()

    log.info(f"Original mime_type from Telegram: '{raw}'")

    if "ogg" in raw:
        return "audio/ogg"
    elif "webm" in raw:
        return "audio/webm"
    elif "mp4" in raw or "m4a" in raw or "aac" in raw:
        return "audio/aac"
    elif "mp3" in raw or "mpeg" in raw:
        return "audio/mp3"
    elif "wav" in raw:
        return "audio/wav"
    elif "flac" in raw:
        return "audio/flac"
    else:
        # Telegram voice messages are almost always OGG/Opus
        log.info("mime_type unclear, defaulting to audio/ogg")
        return "audio/ogg"


# ================================================================
# TRANSCRIPTION via Gemini (audio → text) — NO ffmpeg needed!
# ================================================================

async def _transcribe_with_gemini(audio_bytes: bytes, mime_type: str = "audio/ogg") -> Optional[str]:
    if not GEMINI_API_KEY:
        log.error("GEMINI_API_KEY not set — cannot transcribe")
        return None

    if not audio_bytes:
        log.error("Empty audio bytes received!")
        return None

    log.info(f"Transcribing {len(audio_bytes)} bytes, mime: {mime_type}")

    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    # Clean instruction
    instruction = (
        "Transcribe this voice message exactly as spoken. "
        "The speaker may use Hindi, Urdu, Hinglish (Hindi + English mix), or English. "
        "Write only what was said. No explanation, no prefix, no extra text."
    )

    payload = json.dumps({
        "contents": [{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": audio_b64}},
                {"text": instruction}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 500
        }
    }).encode("utf-8")

    _rate_limit()
    url = GEMINI_VISION_URL.format(key=GEMINI_API_KEY)

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

            # Check for safety blocks or empty candidates
            candidates = result.get("candidates", [])
            if not candidates:
                log.error(f"No candidates in Gemini response: {result}")
                return None

            candidate = candidates[0]

            # Check finish reason
            finish_reason = candidate.get("finishReason", "")
            if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
                log.error(f"Gemini blocked response: finishReason={finish_reason}")
                return None

            parts = candidate.get("content", {}).get("parts", [])
            if not parts:
                log.error(f"Empty parts in Gemini response: {candidate}")
                return None

            text = parts[0].get("text", "").strip()
            if not text:
                log.error("Empty text in Gemini response")
                return None

            log.info(f"Transcription done ({len(text)} chars): {text[:80]}")
            return text

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        log.error(f"Gemini HTTP error {e.code}: {body[:200]}")
        return None
    except urllib.error.URLError as e:
        log.error(f"Gemini URL error: {e}")
        return None
    except Exception as e:
        log.error(f"Gemini transcribe unexpected error: {e}")
        return None


# ================================================================
# CLASSIFICATION
# ================================================================

def _classify_transcript(text: str) -> str:
    lower = text.lower()

    task_words    = ["karna hai", "krna hai", "karna he", "todo", "task", "kaam",
                     "yaad dilana", "remind", "meeting", "call karna", "buy"]
    expense_words = ["kharcha", "karcha", "kharch", "rupees", "rs", "spent", "paisa",
                     "laga", "lagaya", "diye"]
    memory_words  = ["yaad rakhna", "remember", "note karo", "save karo", "important",
                     "memory mein", "yaad rakh"]

    task_score    = sum(1 for w in task_words    if w in lower)
    expense_score = sum(1 for w in expense_words if w in lower)
    memory_score  = sum(1 for w in memory_words  if w in lower)

    # Agar number hai aur expense word hai → expense
    if re.search(r'\d+', lower) and expense_score >= 1:
        return "expense"

    scores = [
        ("task",    task_score),
        ("memory",  memory_score),
        ("expense", expense_score),
        ("diary",   1),  # default
    ]
    best = max(scores, key=lambda x: x[1])
    return best[0]


# ================================================================
# MAIN HANDLER
# ================================================================

async def handle_voice_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _SDM_AVAILABLE:
        await update.message.reply_text("❌ Voice feature unavailable")
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    user_name = update.effective_user.first_name or "User"
    duration  = getattr(voice, "duration", 0) or 0

    # Step 1: Ack karo
    status_msg = await update.message.reply_text(
        f"🎙️ *Voice note mila! ({duration}s)*\n\n⏳ Transcribe ho raha hai...",
        parse_mode="Markdown"
    )

    # Step 2: Download
    try:
        file_obj    = await ctx.bot.get_file(voice.file_id)
        audio_bytes = await file_obj.download_as_bytearray()
        audio_bytes = bytes(audio_bytes)
        log.info(f"Voice downloaded: {len(audio_bytes)} bytes, file_id={voice.file_id}")
    except Exception as e:
        log.error(f"Voice download error: {e}")
        await status_msg.edit_text(
            f"❌ *Voice download fail ho gaya!*\n\nError: `{str(e)[:100]}`",
            parse_mode="Markdown"
        )
        return

    if not audio_bytes or len(audio_bytes) < 100:
        await status_msg.edit_text("❌ Audio file empty ya corrupt hai!")
        return

    # Step 3: Mime type
    mime_type = _get_mime_type(voice)
    log.info(f"Using mime_type: {mime_type} for transcription")

    # Step 4: Transcribe
    await status_msg.edit_text(
        f"🎙️ *Voice note mila! ({duration}s)*\n\n🤖 Gemini transcribe kar raha hai...",
        parse_mode="Markdown"
    )

    transcript = await _transcribe_with_gemini(audio_bytes, mime_type)

    if not transcript:
        await status_msg.edit_text(
            "❌ *Transcription fail ho gaya!*\n\n"
            "Possible reasons:\n"
            "• GEMINI_API_KEY sahi nahi\n"
            "• Audio too short/silent\n"
            "• Network issue\n\n"
            "Dobara try karo.",
            parse_mode="Markdown"
        )
        if voice_store:
            voice_store.add("[Transcription Failed]", "none", duration, "Failed")
        return

    # Step 5: Classify & Save
    category = _classify_transcript(transcript)
    saved_to  = "diary"
    extra_info = ""

    if category == "task":
        t = tasks.add(transcript[:100])
        saved_to   = f"task #{t['id']}"
        extra_info = f"✅ Task #{t['id']} bana diya!"

    elif category == "expense":
        m = re.search(r'(\d+(?:\.\d+)?)', transcript)
        if m:
            amount = float(m.group(1))
            desc   = re.sub(r'\d+(?:\.\d+)?', "", transcript).strip() or "Voice expense"
            expenses.add(amount, desc[:60])
            saved_to   = "expenses"
            extra_info = f"💸 Rs.{amount} expense add ho gaya!"
        else:
            diary.add(f"[Voice] {transcript}")
            saved_to   = "diary"
            extra_info = "📖 Diary mein save kiya (amount nahi mila)"

    elif category == "memory":
        memory.add(transcript)
        saved_to   = "memory"
        extra_info = "🧠 Memory mein save ho gaya!"

    else:  # diary
        diary.add(f"[Voice] {transcript}")
        saved_to   = "diary"
        extra_info = "📖 Diary mein save ho gaya!"

    if voice_store:
        voice_store.add(transcript, saved_to, duration, "Success")

    await status_msg.edit_text(
        f"🎙️ *Voice Note Transcribed!* ✅\n\n"
        f"📝 *Transcript:*\n_{transcript[:300]}_\n\n"
        f"{'─' * 20}\n"
        f"💾 {extra_info}\n\n"
        f"/voicenotes — Purani notes dekho",
        parse_mode="Markdown"
    )

    try:
        sheets_backup.log_event("voice_note", user_name, f"[{saved_to}] {transcript[:80]}")
    except Exception:
        pass


# ================================================================
# COMMAND: /voicenotes
# ================================================================

async def cmd_voicenotes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not voice_store:
        await update.message.reply_text("❌ Voice store unavailable")
        return

    recent = voice_store.get_recent(10)
    if not recent:
        await update.message.reply_text(
            "🎙️ Koi voice note nahi hai abhi.\n\nVoice message bhejo — main transcribe kar dunga!"
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
        f"🎙️ *Recent Voice Notes:*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown"
    )


# ================================================================
# REGISTER
# ================================================================

def register_voice_handlers(app):
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(CommandHandler("voicenotes", cmd_voicenotes))
    log.info("✅ Voice Note handlers registered (Gemini-based, no ffmpeg needed!)")
