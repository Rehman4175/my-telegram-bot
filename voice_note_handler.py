#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — Rk Bot Addon with MULTIPLE APPROACHES
============================================================
Multiple transcription methods:
1. Google Speech-to-Text (via google-cloud-speech)
2. Faster Whisper (via Hugging Face API)
3. Gemini 1.5 Pro Audio (fixed)
4. Groq Whisper API (fastest)
"""

import os
import json
import logging
import time
import urllib.request
import urllib.error
import re
import base64
import asyncio
from typing import Optional
import io

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, CommandHandler, filters

log = logging.getLogger(__name__)

# Import existing modules
try:
    from secure_data_manager import (
        diary, tasks, memory, expenses, sheets_backup, repo_manager,
        now_ist, today_str, now_str, PrivateStore
    )
    _SDM_AVAILABLE = True
except ImportError:
    log.error("secure_data_manager import failed!")
    _SDM_AVAILABLE = False

# API Keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")  # Add this to your secrets
HF_API_KEY = os.environ.get("HUGGINGFACE_API_KEY", "")

# URLs
GEMINI_AUDIO_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={key}"
GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
HF_WHISPER_URL = "https://api-inference.huggingface.co/models/openai/whisper-large-v3"

_last_call = 0

def _rate_limit():
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 1:
        time.sleep(1 - elapsed)
    _last_call = time.time()

# ================================================================
# VOICE NOTE STORE
# ================================================================

class VoiceNoteStore:
    TAB_KEY = "VoiceNotes"
    TAB_NAME = "Voice Notes"
    HEADERS = ["ID", "Date", "Time", "Transcript", "Saved To", "Duration", "Status", "Method"]

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

    def add(self, transcript: str, saved_to: str = "diary", duration: int = 0, status: str = "Success", method: str = "unknown"):
        if not _SDM_AVAILABLE:
            return None
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        vid = self.store.data["counter"]
        entry = {
            "id": vid,
            "date": today_str(),
            "time": now_str(),
            "transcript": transcript,
            "saved_to": saved_to,
            "duration": duration,
            "status": status,
            "method": method,
        }
        self.store.data["list"].append(entry)
        self.store.data["list"] = self.store.data["list"][-500:]
        self.store.save()
        self._append_to_sheet([vid, today_str(), now_str(), transcript[:500], saved_to, duration, status, method])
        return entry

    def get_recent(self, n: int = 10):
        return self.store.data.get("list", [])[-n:]

if _SDM_AVAILABLE:
    voice_store = VoiceNoteStore()
else:
    voice_store = None

# ================================================================
# APPROACH 1: GROQ WHISPER API (Fastest & Most Reliable)
# ================================================================

async def transcribe_with_groq(audio_bytes: bytes) -> Optional[str]:
    """Use Groq's Whisper API - fastest and most accurate"""
    if not GROQ_API_KEY:
        log.warning("GROQ_API_KEY not set")
        return None
    
    try:
        import aiohttp
        import mimetypes
        
        # Prepare multipart form data
        data = aiohttp.FormData()
        data.add_field('file', 
                      audio_bytes, 
                      filename='audio.ogg',
                      content_type='audio/ogg')
        data.add_field('model', 'whisper-large-v3')
        data.add_field('language', 'hi')  # Hindi focus
        data.add_field('response_format', 'json')
        
        headers = {
            'Authorization': f'Bearer {GROQ_API_KEY}'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_WHISPER_URL, 
                                  headers=headers, 
                                  data=data,
                                  timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    text = result.get('text', '')
                    if text:
                        log.info(f"Groq transcription successful: {len(text)} chars")
                        return text.strip()
                else:
                    error_text = await resp.text()
                    log.error(f"Groq API error {resp.status}: {error_text[:200]}")
                    return None
    except ImportError:
        log.error("aiohttp not installed - install with: pip install aiohttp")
        return None
    except Exception as e:
        log.error(f"Groq transcription error: {e}")
        return None

# ================================================================
# APPROACH 2: HUGGING FACE WHISPER API
# ================================================================

async def transcribe_with_huggingface(audio_bytes: bytes) -> Optional[str]:
    """Use Hugging Face's Whisper API"""
    if not HF_API_KEY:
        log.warning("HUGGINGFACE_API_KEY not set")
        return None
    
    try:
        import aiohttp
        
        headers = {
            "Authorization": f"Bearer {HF_API_KEY}"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(HF_WHISPER_URL,
                                  headers=headers,
                                  data=audio_bytes,
                                  timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    text = result.get('text', '')
                    if text:
                        log.info(f"HuggingFace transcription successful: {len(text)} chars")
                        return text.strip()
                else:
                    error_text = await resp.text()
                    log.error(f"HF API error {resp.status}: {error_text[:200]}")
                    return None
    except ImportError:
        log.error("aiohttp not installed")
        return None
    except Exception as e:
        log.error(f"HuggingFace transcription error: {e}")
        return None

# ================================================================
# APPROACH 3: FIXED GEMINI IMPLEMENTATION
# ================================================================

async def transcribe_with_gemini(audio_bytes: bytes) -> Optional[str]:
    """Fixed Gemini 1.5 Pro implementation"""
    if not GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY not set")
        return None
    
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    
    # Better prompt for transcription
    instruction = """Transcribe the voice message exactly as spoken. 
The speaker uses Hinglish (Hindi+English mixed), Hindi, or English.
Rules:
- Write exactly what is said
- Use lowercase
- Keep numbers as digits
- No explanations, no prefixes
- If unclear, write [unclear]"""

    payload = {
        "contents": [{
            "parts": [
                {
                    "inline_data": {
                        "mime_type": "audio/ogg",
                        "data": audio_b64
                    }
                },
                {"text": instruction}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1000
        }
    }
    
    _rate_limit()
    url = GEMINI_AUDIO_URL.format(key=GEMINI_API_KEY)
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read().decode())
            
            # Parse response
            candidates = result.get("candidates", [])
            if not candidates:
                log.error(f"No candidates: {result}")
                return None
            
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                log.error(f"No parts: {candidates[0]}")
                return None
            
            text = parts[0].get("text", "").strip()
            if text:
                log.info(f"Gemini transcription: {len(text)} chars")
                # Remove markdown if any
                text = re.sub(r'\*+', '', text)
                return text
            else:
                log.error("Empty text from Gemini")
                return None
                
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if hasattr(e, 'read') else ''
        log.error(f"Gemini HTTP {e.code}: {error_body[:300]}")
        return None
    except Exception as e:
        log.error(f"Gemini error: {e}")
        return None

# ================================================================
# MAIN HANDLER WITH MULTIPLE APPROACHES
# ================================================================

async def handle_voice_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _SDM_AVAILABLE:
        await update.message.reply_text("❌ Voice feature unavailable")
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    duration = getattr(voice, "duration", 0) or 0
    
    # Send initial response
    status_msg = await update.message.reply_text(
        f"🎙️ *Voice note! ({duration}s)*\n\n🔄 Downloading & processing...",
        parse_mode="Markdown"
    )

    # Download audio
    try:
        file_obj = await ctx.bot.get_file(voice.file_id)
        audio_bytes = await file_obj.download_as_bytearray()
        audio_bytes = bytes(audio_bytes)
        log.info(f"Downloaded: {len(audio_bytes)} bytes")
    except Exception as e:
        log.error(f"Download error: {e}")
        await status_msg.edit_text(f"❌ Download failed: {str(e)[:100]}")
        return

    if len(audio_bytes) < 1000:  # Too small
        await status_msg.edit_text("❌ Audio too short or empty!")
        return

    # Try multiple transcription methods in order
    transcript = None
    method_used = "none"
    
    # Method 1: Groq Whisper (if key available)
    if GROQ_API_KEY:
        await status_msg.edit_text(f"🎙️ *Voice note! ({duration}s)*\n\n🤖 Using Groq Whisper API...", parse_mode="Markdown")
        transcript = await transcribe_with_groq(audio_bytes)
        if transcript:
            method_used = "Groq Whisper"
            log.info(f"Groq succeeded: {len(transcript)} chars")
    
    # Method 2: Hugging Face Whisper (fallback)
    if not transcript and HF_API_KEY:
        await status_msg.edit_text(f"🎙️ *Voice note! ({duration}s)*\n\n🔄 Trying Hugging Face Whisper...", parse_mode="Markdown")
        transcript = await transcribe_with_huggingface(audio_bytes)
        if transcript:
            method_used = "HuggingFace Whisper"
            log.info(f"HF succeeded: {len(transcript)} chars")
    
    # Method 3: Gemini (last resort)
    if not transcript and GEMINI_API_KEY:
        await status_msg.edit_text(f"🎙️ *Voice note! ({duration}s)*\n\n🔄 Trying Gemini...", parse_mode="Markdown")
        transcript = await transcribe_with_gemini(audio_bytes)
        if transcript:
            method_used = "Gemini"
            log.info(f"Gemini succeeded: {len(transcript)} chars")

    if not transcript:
        await status_msg.edit_text(
            "❌ *Transcription failed with ALL methods!*\n\n"
            "Possible issues:\n"
            "• Audio quality too poor\n"
            "• No API keys configured\n"
            "• Network problems\n\n"
            "Required API keys (add to secrets):\n"
            "• GROQ_API_KEY (recommended - FREE)\n"
            "• HUGGINGFACE_API_KEY\n"
            "• GEMINI_API_KEY (fallback)\n\n"
            "Get Groq key: https://console.groq.com",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        if voice_store:
            voice_store.add("[Failed - All methods]", "none", duration, "Failed", "none")
        return

    # Process the transcript
    category = _classify_transcript(transcript)
    saved_to = "diary"
    extra_info = ""

    if category == "task":
        t = tasks.add(transcript[:200])
        saved_to = f"task #{t['id']}"
        extra_info = f"✅ Added to Tasks (ID: {t['id']})"
    elif category == "expense":
        m = re.search(r'(\d+(?:\.\d+)?)', transcript)
        if m:
            amount = float(m.group(1))
            desc = re.sub(r'\d+(?:\.\d+)?', "", transcript).strip() or "Voice expense"
            expenses.add(amount, desc[:100])
            saved_to = "expenses"
            extra_info = f"💸 Added expense: ₹{amount}"
        else:
            diary.add(f"[Voice] {transcript}")
            saved_to = "diary"
            extra_info = "📖 Saved to diary (no amount found)"
    elif category == "memory":
        memory.add(transcript)
        saved_to = "memory"
        extra_info = "🧠 Saved to memory"
    else:
        diary.add(f"[Voice] {transcript}")
        saved_to = "diary"
        extra_info = "📖 Saved to diary"

    if voice_store:
        voice_store.add(transcript, saved_to, duration, "Success", method_used)

    # Format response
    response_text = (
        f"🎙️ *Voice Note Processed!*\n"
        f"🤖 *Method:* {method_used}\n"
        f"⏱ *Duration:* {duration}s\n\n"
        f"📝 *Transcript:*\n"
        f"_{transcript[:400]}_\n\n"
        f"{'─' * 25}\n"
        f"💾 {extra_info}\n\n"
        f"📋 /voicenotes - View all voice notes"
    )
    
    if len(transcript) > 400:
        response_text += f"\n\n*(... {len(transcript)-400} more characters)*"
    
    await status_msg.edit_text(response_text, parse_mode="Markdown")

    try:
        sheets_backup.log_event("voice_note", update.effective_user.first_name, f"[{method_used}] {transcript[:80]}")
    except Exception:
        pass

def _classify_transcript(text: str) -> str:
    """Simple classification logic"""
    lower = text.lower()
    
    task_keywords = ['karna hai', 'krna hai', 'todo', 'task', 'kaam', 'meeting', 'call']
    expense_keywords = ['kharcha', 'kharch', 'rupees', 'rs', 'spent', 'paisa', 'laga']
    memory_keywords = ['yaad rakhna', 'remember', 'note karo', 'save karo', 'important']
    
    if any(kw in lower for kw in expense_keywords) and re.search(r'\d+', lower):
        return "expense"
    elif any(kw in lower for kw in task_keywords):
        return "task"
    elif any(kw in lower for kw in memory_keywords):
        return "memory"
    else:
        return "diary"

async def cmd_voicenotes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show recent voice notes"""
    if not voice_store:
        await update.message.reply_text("❌ Voice store unavailable")
        return

    recent = voice_store.get_recent(10)
    if not recent:
        await update.message.reply_text(
            "🎙️ No voice notes yet.\n\n"
            "Send me a voice message and I'll transcribe it!"
        )
        return

    lines = []
    for v in reversed(recent):
        status_emoji = "✅" if v['status'] == "Success" else "❌"
        lines.append(
            f"{status_emoji} *#{v['id']}* {v['date']} {v['time']}\n"
            f"   🤖 {v.get('method', 'unknown')} | ⏱ {v.get('duration', 0)}s\n"
            f"   💾 {v['saved_to']}\n"
            f"   📝 _{v['transcript'][:80]}_"
        )

    await update.message.reply_text(
        f"🎙️ *Recent Voice Notes (Last 10)*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

def register_voice_handlers(app):
    """Register handlers with the bot"""
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(CommandHandler("voicenotes", cmd_voicenotes))
    log.info("✅ Voice handlers registered with multiple transcription methods!")
