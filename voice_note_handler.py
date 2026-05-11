#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — Rk Bot
FIX: gemini-1.5-pro → gemini-1.5-flash (Pro audio support nahi karta!)
     Exact Gemini error Telegram mein dikhega
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

try:
    from secure_data_manager import (
        diary, tasks, memory, expenses, sheets_backup, repo_manager,
        now_ist, today_str, now_str, PrivateStore
    )
    _SDM_AVAILABLE = True
except ImportError:
    log.error("secure_data_manager import failed!")
    _SDM_AVAILABLE = False

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ✅ FLASH use karo — PRO audio transcription support NAHI karta!
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"

_last_call = 0

def _rate_limit():
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 2:
        time.sleep(2 - elapsed)
    _last_call = time.time()

# ================================================================
# VOICE NOTE STORE
# ================================================================

class VoiceNoteStore:
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
            else:
                if self.TAB_NAME not in sheets_backup._ws_cache:
                    ws = sheets_backup._book.worksheet(self.TAB_NAME)
                    sheets_backup._ws_cache[self.TAB_NAME] = ws
        except Exception as e:
            log.warning(f"VoiceNotes tab error: {e}")

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
            log.warning(f"Sheet append error: {e}")

    def add(self, transcript: str, saved_to: str = "diary",
            duration: int = 0, status: str = "Success"):
        if not _SDM_AVAILABLE:
            return None
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        vid = self.store.data["counter"]
        entry = {
            "id": vid, "date": today_str(), "time": now_str(),
            "transcript": transcript, "saved_to": saved_to,
            "duration": duration, "status": status,
        }
        self.store.data["list"].append(entry)
        self.store.data["list"] = self.store.data["list"][-500:]
        self.store.save()
        self._append_to_sheet([vid, today_str(), now_str(),
                                transcript[:500], saved_to, duration, status])
        return entry

    def get_recent(self, n: int = 10):
        return self.store.data.get("list", [])[-n:]

if _SDM_AVAILABLE:
    voice_store = VoiceNoteStore()
else:
    voice_store = None

# ================================================================
# GEMINI TRANSCRIPTION
# ================================================================

async def transcribe_audio(audio_bytes: bytes) -> tuple:
    """
    Returns: (transcript_text, error_message)
    Success: ("text...", None)
    Failure: (None, "exact error detail")
    """
    # ── Check 1: API Key ─────────────────────────────────────────
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY GitHub Secret mein set nahi hai!"

    # ── Check 2: Audio size ──────────────────────────────────────
    if not audio_bytes or len(audio_bytes) < 1000:
        return None, f"Audio too small: {len(audio_bytes) if audio_bytes else 0} bytes"

    log.info(f"Sending to Gemini Flash: {len(audio_bytes)} bytes")

    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    instruction = """Transcribe this voice message exactly as spoken.
Speaker uses Hinglish (Hindi words written in English letters).
Write ONLY what was said. No explanation, no prefix.
Use English alphabet only (no Devanagari/Hindi script).
Numbers in digits: 10, 100, 500."""

    payload = json.dumps({
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "audio/ogg", "data": audio_b64}},
                {"text": instruction}
            ]
        }],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 500}
    }).encode("utf-8")

    _rate_limit()

    try:
        req = urllib.request.Request(
            GEMINI_URL.format(key=GEMINI_API_KEY),
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

    except urllib.error.HTTPError as e:
        # ── Exact Gemini error nikalo ────────────────────────────
        try:
            body = e.read().decode("utf-8", errors="ignore")
            err_json = json.loads(body)
            gemini_msg = err_json.get("error", {}).get("message", body[:200])
        except Exception:
            gemini_msg = f"HTTP {e.code}"
        return None, f"Gemini HTTP {e.code}: {gemini_msg}"

    except urllib.error.URLError as e:
        return None, f"Network error: {e.reason}"

    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

    # ── Parse response ───────────────────────────────────────────
    candidates = result.get("candidates", [])
    if not candidates:
        feedback   = result.get("promptFeedback", {})
        block      = feedback.get("blockReason", "")
        return None, f"No candidates. Block reason: '{block}'. Response: {str(result)[:200]}"

    finish = candidates[0].get("finishReason", "")
    if finish in ("SAFETY", "RECITATION", "OTHER"):
        return None, f"Gemini blocked: finishReason={finish}"

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        return None, f"Empty parts in response: {str(candidates[0])[:200]}"

    text = parts[0].get("text", "").strip()
    if not text:
        return None, "Gemini returned empty text (silent/unclear audio?)"

    # Cleanup
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'\n+', ' ', text).strip()
    text = re.sub(r'^(transcription|hinglish|text|output)[:\s]*', '', text, flags=re.IGNORECASE)

    log.info(f"✅ Transcribed: {text[:80]}")
    return text.strip(), None

# ================================================================
# CLASSIFICATION
# ================================================================

def _classify_transcript(text: str) -> str:
    lower = text.lower()

    expense_kw = [
        'kharcha', 'karcha', 'kharch', 'laga', 'lagaya', 'diye', 'paisa', 'paise',
        'rupees', 'rs', 'spent', 'khareeda', 'kharida', 'shopping',
        'petrol', 'diesel', 'bill', 'chai', 'coffee', 'khana', 'food', 'lunch', 'dinner'
    ]
    task_kw = [
        'karna hai', 'krna hai', 'karna he', 'kaam', 'task', 'meeting', 'call',
        'remind', 'yaad dilana', 'jana hai', 'jaana hai', 'lana hai', 'dena hai',
        'submit', 'send', 'buy', 'order', 'phone karna'
    ]
    memory_kw = [
        'yaad rakhna', 'remember', 'memory', 'note karo', 'yaad karo',
        'bhoolna mat', 'important', 'zaroori', 'yaad rakh'
    ]

    has_number  = bool(re.search(r'\d+', text))
    e_score = sum(1 for w in expense_kw if w in lower)
    t_score = sum(1 for w in task_kw    if w in lower)
    m_score = sum(1 for w in memory_kw  if w in lower)

    if has_number and e_score > 0:
        return "expense"
    if e_score >= 2:
        return "expense"
    if t_score >= 1:
        return "task"
    if m_score >= 1:
        return "memory"
    return "diary"

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

    duration  = getattr(voice, "duration", 0) or 0
    user_name = update.effective_user.first_name or "User"

    status_msg = await update.message.reply_text(
        f"🎙️ *Voice note mila!* ({duration}s)\n\n⏳ Download ho raha hai...",
        parse_mode="Markdown"
    )

    # Download
    try:
        file_obj    = await ctx.bot.get_file(voice.file_id)
        audio_bytes = bytes(await file_obj.download_as_bytearray())
        log.info(f"Downloaded: {len(audio_bytes)} bytes")
    except Exception as e:
        await status_msg.edit_text(f"❌ *Download fail!*\n\n`{str(e)[:150]}`", parse_mode="Markdown")
        return

    # Transcribe
    await status_msg.edit_text(
        f"🎙️ *Voice note* ({duration}s, {len(audio_bytes)//1024}KB)\n\n🤖 Gemini Flash transcribe kar raha hai...",
        parse_mode="Markdown"
    )

    transcript, error = await transcribe_audio(audio_bytes)

    # ── FAILURE: exact error dikhao ──────────────────────────────
    if not transcript:
        await status_msg.edit_text(
            f"❌ *Transcription fail!*\n\n"
            f"*Error:*\n`{error}`\n\n"
            f"*Debug:*\n"
            f"• API key: `{'SET ✅' if GEMINI_API_KEY else 'MISSING ❌'}`\n"
            f"• Model: `gemini-1.5-flash`\n"
            f"• Audio: `{len(audio_bytes)} bytes`\n"
            f"• Duration: `{duration}s`",
            parse_mode="Markdown"
        )
        if voice_store:
            voice_store.add(f"[FAIL: {str(error)[:60]}]", "none", duration, "Failed")
        return

    # ── Classify & Save ──────────────────────────────────────────
    category   = _classify_transcript(transcript)
    saved_to   = "diary"
    extra_info = ""

    if category == "task":
        task_text = transcript
        for w in ['karna hai', 'krna hai', 'task', 'kaam', 'karo', 'add']:
            task_text = re.sub(r'\b' + re.escape(w) + r'\b', '', task_text, flags=re.IGNORECASE)
        task_text = re.sub(r'\s+', ' ', task_text).strip() or transcript[:80]
        t          = tasks.add(task_text)
        saved_to   = f"task #{t['id']}"
        extra_info = f"✅ Task #{t['id']} add kar diya!\n📌 *{task_text[:60]}*"

    elif category == "expense":
        m = re.search(r'(\d+(?:\.\d+)?)', transcript)
        if m:
            amount = float(m.group(1))
            desc   = re.sub(r'\d+(?:\.\d+)?', '', transcript)
            for w in ['kharcha', 'karcha', 'laga', 'lagaya', 'diye', 'paisa', 'rupees', 'rs']:
                desc = re.sub(r'\b' + re.escape(w) + r'\b', '', desc, flags=re.IGNORECASE)
            desc = re.sub(r'\s+', ' ', desc).strip() or "Expense"
            expenses.add(amount, desc[:100])
            saved_to   = "expenses"
            extra_info = f"💸 Rs.{amount} add kar diya!\n📝 *{desc[:50]}*"
        else:
            diary.add(f"[Voice] {transcript}")
            saved_to   = "diary"
            extra_info = "📖 Diary mein save kiya (amount nahi mila)"

    elif category == "memory":
        mem_text = transcript
        for w in ['yaad rakhna', 'remember', 'memory', 'note karo', 'yaad karo']:
            mem_text = re.sub(r'\b' + re.escape(w) + r'\b', '', mem_text, flags=re.IGNORECASE)
        mem_text = re.sub(r'\s+', ' ', mem_text).strip() or transcript[:100]
        memory.add(mem_text)
        saved_to   = "memory"
        extra_info = f"🧠 Memory mein save kar liya!\n📝 *{mem_text[:60]}*"

    else:
        diary.add(f"[Voice] {transcript}")
        saved_to   = "diary"
        extra_info = f"📖 Diary mein save kar diya!"

    if voice_store:
        voice_store.add(transcript, saved_to, duration, "Success")

    await status_msg.edit_text(
        f"🎙️ *Ho gaya!* ✅\n\n"
        f"📝 *Tumne kaha:*\n_{transcript[:400]}_\n\n"
        f"{'─'*20}\n"
        f"💾 {extra_info}\n\n"
        f"/voicenotes — Purane notes dekho",
        parse_mode="Markdown"
    )

    try:
        sheets_backup.log_event("voice_note", user_name, f"[{saved_to}] {transcript[:80]}")
    except Exception:
        pass

# ================================================================
# /voicenotes COMMAND
# ================================================================

async def cmd_voicenotes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not voice_store:
        await update.message.reply_text("❌ Voice store unavailable")
        return
    recent = voice_store.get_recent(10)
    if not recent:
        await update.message.reply_text(
            "🎙️ Abhi koi voice note nahi hai.\n\nVoice message bhejo — main transcribe kar dunga!"
        )
        return
    lines = []
    for v in reversed(recent):
        emoji = "✅" if v.get("status") == "Success" else "❌"
        lines.append(
            f"{emoji} *#{v['id']}* {v['date']} {v['time']}\n"
            f"   💾 *{v['saved_to']}* | ⏱ {v.get('duration', 0)}s\n"
            f"   📝 _{v['transcript'][:100]}_"
        )
    await update.message.reply_text(
        "🎙️ *Recent Voice Notes:*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown"
    )

# ================================================================
# REGISTER
# ================================================================

def register_voice_handlers(app):
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(CommandHandler("voicenotes", cmd_voicenotes))
    log.info("✅ Voice handlers registered — model: gemini-1.5-flash")
