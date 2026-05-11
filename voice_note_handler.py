#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — HINGLISH OUTPUT FIXED
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
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
HF_API_KEY = os.environ.get("HUGGINGFACE_API_KEY", "")

GEMINI_AUDIO_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={key}"
GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

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
# HINGLISH TRANSCRIPTION - FIXED PROMPTS
# ================================================================

async def transcribe_with_groq(audio_bytes: bytes) -> Optional[str]:
    """Groq Whisper API - Hinglish output"""
    if not GROQ_API_KEY:
        return None
    
    try:
        import aiohttp
        
        data = aiohttp.FormData()
        data.add_field('file', audio_bytes, filename='audio.ogg', content_type='audio/ogg')
        data.add_field('model', 'whisper-large-v3')
        data.add_field('response_format', 'json')
        data.add_field('language', 'hi')
        # FIXED: Hinglish prompt
        data.add_field('prompt', 'Hinglish only: Hindi words written in English alphabet. Example: "mujhe aaj office jaana hai" not Devanagari. Numbers as digits.')
        
        headers = {'Authorization': f'Bearer {GROQ_API_KEY}'}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_WHISPER_URL, headers=headers, data=data, timeout=30) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    text = result.get('text', '')
                    if text:
                        # Convert any Devanagari to Hinglish approximation
                        text = _devanagari_to_hinglish(text)
                        log.info(f"Groq: {len(text)} chars")
                        return text.strip()
                else:
                    error_text = await resp.text()
                    log.error(f"Groq error {resp.status}: {error_text[:200]}")
    except ImportError:
        log.error("aiohttp not installed")
    except Exception as e:
        log.error(f"Groq error: {e}")
    return None

async def transcribe_with_gemini(audio_bytes: bytes) -> Optional[str]:
    """Gemini - Hinglish output"""
    if not GEMINI_API_KEY:
        return None
    
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    
    # FIXED: Force Hinglish output
    instruction = """CRITICAL INSTRUCTION: You MUST write the transcript in HINGLISH only.

HINGLISH = Hindi words written using English/Roman alphabet (A-Z).
DO NOT use Devanagari script (देवनागरी).
DO NOT translate to English.

Examples of CORRECT Hinglish:
- "mujhe kal meeting mein jaana hai 10 baje"
- "aaj mausam bahut accha hai"
- "500 rupees kharcha kiya movie pe"
- "yaad rakhna milk lena hai"

Examples of WRONG (DO NOT DO THIS):
- "मुझे कल मीटिंग में जाना है" (This is Devanagari - WRONG)
- "I have to go to meeting tomorrow" (This is English - WRONG)

Rules:
- Use only English alphabet letters
- Hindi words as they sound in English
- Numbers as digits
- No punctuation unless necessary
- Just write exactly what was said in Hinglish

Now transcribe this voice message in HINGLISH only:"""

    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "audio/ogg", "data": audio_b64}},
                {"text": instruction}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 500
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
            candidates = result.get("candidates", [])
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return None
            text = parts[0].get("text", "").strip()
            if text:
                text = re.sub(r'\*+', '', text)
                text = re.sub(r'\n+', ' ', text)
                # Convert any Devanagari to Hinglish
                text = _devanagari_to_hinglish(text)
                log.info(f"Gemini: {len(text)} chars")
                return text
    except Exception as e:
        log.error(f"Gemini error: {e}")
    return None

def _devanagari_to_hinglish(text: str) -> str:
    """Convert Devanagari script to Hinglish approximation"""
    # Common Devanagari to Roman mapping
    mapping = {
        'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo',
        'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au', 'अं': 'am', 'अः': 'ah',
        'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng',
        'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'ny',
        'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
        'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
        'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
        'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v', 'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h',
        'क्ष': 'ksh', 'त्र': 'tr', 'ज्ञ': 'gy',
        'ा': 'aa', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo',
        'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', '्': '',
        'ं': 'm', 'ः': 'h', '़': '', 'ॉ': 'o', 'ॅ': 'e',
        '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
        '५': '5', '६': '6', '७': '7', '८': '8', '९': '9',
    }
    
    result = []
    i = 0
    while i < len(text):
        # Check for multi-character sequences first
        if i+1 < len(text) and text[i:i+2] in mapping:
            result.append(mapping[text[i:i+2]])
            i += 2
        elif text[i] in mapping:
            result.append(mapping[text[i]])
            i += 1
        else:
            result.append(text[i])
            i += 1
    
    return ''.join(result)

# ================================================================
# CLASSIFICATION
# ================================================================

def _classify_transcript(text: str) -> str:
    """Classify transcript into task/expense/memory/diary"""
    lower = text.lower()
    
    # Expense keywords
    expense_keywords = [
        'kharcha', 'karcha', 'kharch', 'expense', 'laga', 'lagaya', 
        'diye', 'paisa', 'paise', 'rupees', 'rs', 'spent', 'uda diye',
        'movie', 'film', 'shopping', 'petrol', 'diesel', 'bill', 'chai', 'coffee', 'khana'
    ]
    
    # Task keywords
    task_keywords = [
        'karna hai', 'krna hai', 'karna he', 'todo', 'task', 'kaam',
        'meeting', 'call', 'phone', 'remind', 'yaad dilana', 'bata dena',
        'jana hai', 'jaana hai', 'aana hai', 'lana hai', 'dena hai'
    ]
    
    # Memory keywords
    memory_keywords = [
        'yaad rakhna', 'remember', 'memory', 'note karo', 'yaad karo',
        'bhoolna mat', 'important', 'zaroori'
    ]
    
    has_number = bool(re.search(r'\d+', text))
    
    expense_score = sum(1 for kw in expense_keywords if kw in lower)
    task_score = sum(1 for kw in task_keywords if kw in lower)
    memory_score = sum(1 for kw in memory_keywords if kw in lower)
    
    if has_number:
        expense_score += 2
    
    if expense_score >= 2 and has_number:
        return "expense"
    elif expense_score >= 1 and has_number:
        return "expense"
    elif task_score >= 1:
        return "task"
    elif memory_score >= 1:
        return "memory"
    else:
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

    duration = getattr(voice, "duration", 0) or 0
    
    status_msg = await update.message.reply_text(
        f"🎙️ Voice note ({duration}s)\n\n🔄 Processing...",
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

    if len(audio_bytes) < 1000:
        await status_msg.edit_text("❌ Audio too short!")
        return

    # Transcribe
    transcript = None
    method_used = "none"
    
    if GROQ_API_KEY:
        await status_msg.edit_text(f"🎙️ Transcribing with Groq...", parse_mode="Markdown")
        transcript = await transcribe_with_groq(audio_bytes)
        if transcript:
            method_used = "Groq"
    
    if not transcript and GEMINI_API_KEY:
        await status_msg.edit_text(f"🎙️ Trying Gemini...", parse_mode="Markdown")
        transcript = await transcribe_with_gemini(audio_bytes)
        if transcript:
            method_used = "Gemini"

    if not transcript:
        await status_msg.edit_text(
            "❌ Transcription failed!\n\n"
            "Add GROQ_API_KEY to secrets for best results.\n"
            "Get free key: https://console.groq.com",
            parse_mode="Markdown"
        )
        if voice_store:
            voice_store.add("[Failed]", "none", duration, "Failed", "none")
        return

    # Classify and save
    category = _classify_transcript(transcript)
    saved_to = "diary"
    extra_info = ""
    user_name = update.effective_user.first_name or "User"

    if category == "task":
        task_text = transcript[:100]
        t = tasks.add(task_text)
        saved_to = f"task #{t['id']}"
        extra_info = f"✅ Task #{t['id']} added: {task_text[:50]}"
        
    elif category == "expense":
        amount_match = re.search(r'(\d+(?:\.\d+)?)', transcript)
        if amount_match:
            amount = float(amount_match.group(1))
            desc = re.sub(r'\d+(?:\.\d+)?', '', transcript).strip()[:80] or "Expense"
            expenses.add(amount, desc)
            saved_to = "expenses"
            extra_info = f"💸 Rs.{amount} expense added: {desc[:40]}"
        else:
            diary.add(f"[Voice] {transcript}")
            saved_to = "diary"
            extra_info = f"📖 Saved to diary (no amount found)"
            
    elif category == "memory":
        memory.add(transcript[:200])
        saved_to = "memory"
        extra_info = f"🧠 Saved to memory: {transcript[:50]}"
        
    else:
        diary.add(f"[Voice] {transcript}")
        saved_to = "diary"
        extra_info = f"📖 Saved to diary: {transcript[:60]}"

    if voice_store:
        voice_store.add(transcript, saved_to, duration, "Success", method_used)

    response = f"""🎙️ *Voice Done!*

🤖 {method_used}
⏱ {duration}s

📝 *Heard:*
_{transcript[:400]}_ 

💾 {extra_info}

📋 /voicenotes - All voice notes"""

    await status_msg.edit_text(response, parse_mode="Markdown")

async def cmd_voicenotes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not voice_store:
        await update.message.reply_text("❌ Voice store unavailable")
        return

    recent = voice_store.get_recent(10)
    if not recent:
        await update.message.reply_text("🎙️ No voice notes yet!\n\nSend me a voice message!")
        return

    lines = []
    for v in reversed(recent):
        lines.append(
            f"#{v['id']} {v['date']} {v['time']}\n"
            f"   💾 {v['saved_to']} | {v.get('method', 'unknown')}\n"
            f"   _{v['transcript'][:80]}_"
        )

    await update.message.reply_text(
        f"🎙️ *Recent Voice Notes*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown"
    )

def register_voice_handlers(app):
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(CommandHandler("voicenotes", cmd_voicenotes))
    log.info("✅ Voice handlers registered (Hinglish output)")
