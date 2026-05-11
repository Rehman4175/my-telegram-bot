#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — FIXED with better classification & Hinglish support
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
# HINGLISH TRANSCRIPTION
# ================================================================

async def transcribe_with_groq(audio_bytes: bytes) -> Optional[str]:
    """Groq Whisper API - Best for Hinglish"""
    if not GROQ_API_KEY:
        return None
    
    try:
        import aiohttp
        
        data = aiohttp.FormData()
        data.add_field('file', audio_bytes, filename='audio.ogg', content_type='audio/ogg')
        data.add_field('model', 'whisper-large-v3')
        data.add_field('response_format', 'json')
        data.add_field('language', 'hi')
        data.add_field('prompt', 'Hindi, Hinglish, Urdu conversation')  # Context hint
        
        headers = {'Authorization': f'Bearer {GROQ_API_KEY}'}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_WHISPER_URL, headers=headers, data=data, timeout=30) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    text = result.get('text', '')
                    if text:
                        log.info(f"Groq transcription: {len(text)} chars")
                        return text.strip()
                else:
                    error_text = await resp.text()
                    log.error(f"Groq error {resp.status}: {error_text[:200]}")
    except ImportError:
        log.error("aiohttp not installed - install with: pip install aiohttp")
    except Exception as e:
        log.error(f"Groq error: {e}")
    return None

async def transcribe_with_huggingface(audio_bytes: bytes) -> Optional[str]:
    """HuggingFace Whisper - Fallback"""
    if not HF_API_KEY:
        return None
    
    try:
        import aiohttp
        
        headers = {"Authorization": f"Bearer {HF_API_KEY}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(HF_WHISPER_URL, headers=headers, data=audio_bytes, timeout=60) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    text = result.get('text', '')
                    if text:
                        log.info(f"HF transcription: {len(text)} chars")
                        return text.strip()
                else:
                    error_text = await resp.text()
                    log.error(f"HF error {resp.status}: {error_text[:200]}")
    except ImportError:
        log.error("aiohttp not installed")
    except Exception as e:
        log.error(f"HF error: {e}")
    return None

async def transcribe_with_gemini(audio_bytes: bytes) -> Optional[str]:
    """Gemini - Last resort with Hinglish prompt"""
    if not GEMINI_API_KEY:
        return None
    
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    
    instruction = """This is a Hindi/Urdu/Hinglish voice message from an Indian user.
Transcribe EXACTLY what is said in the SAME language (Hinglish - Hindi words written in English alphabet).

IMPORTANT RULES:
- Write in Hinglish (Hindi words using English letters)
- Example: "mujhe kal meeting mein jaana hai" NOT "I have to go to meeting tomorrow"
- Keep numbers as digits: 10, 100, 500
- Do NOT translate to English
- Do NOT add any explanations, prefixes, or extra text
- Just write the exact words spoken

Transcribe now:"""

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
                log.error(f"No candidates: {result}")
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                log.error(f"No parts: {candidates[0]}")
                return None
            text = parts[0].get("text", "").strip()
            if text:
                text = re.sub(r'\*+', '', text)
                text = re.sub(r'\n+', ' ', text)
                log.info(f"Gemini transcription: {len(text)} chars")
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
# FIXED: BETTER CLASSIFICATION (HINDI + HINGLISH SUPPORT)
# ================================================================

def _classify_transcript(text: str) -> str:
    """Classify transcript into task/expense/memory/diary with Hindi/Hinglish support"""
    lower = text.lower()
    
    # Expense keywords (Hindi + Hinglish)
    expense_keywords = [
        'kharcha', 'karcha', 'kharch', 'karch', 'expense', 'kharcha hai', 'karcha hai',
        'laga', 'lagaya', 'lagaye', 'diye', 'paisa', 'paise', 'paisa diya', 'paise diye',
        'rupees', 'rs', 'rp', 'kharcha hua', 'kharch kiye', 'kharch kiya',
        'movie', 'film', 'shopping', 'bazar', 'bazaar', 'market',
        'petrol', 'diesel', 'bill', 'bills', 'bhar', 'bhara', 'bhar diya',
        'money', 'spent', 'pay', 'paid', 'payment', 'chai', 'coffee', 'tea',
        'khana', 'food', 'lunch', 'dinner', 'breakfast', 'meal',
        'uda diye', 'uda diya', 'gaye', 'gaya'
    ]
    
    # Task keywords (Hindi + Hinglish)
    task_keywords = [
        'karna hai', 'krna hai', 'karna he', 'krna he', 'todo', 'task',
        'kaam', 'kaam hai', 'meeting', 'call', 'phone', 'phone karna',
        'remind', 'reminder', 'yaad dilana', 'bata dena', 'bata do',
        'karo', 'kar na', 'karna', 'kar do', 'kardo',
        'submit', 'send', 'email', 'message', 'text', 'buy', 'purchase', 'order',
        'jana hai', 'jaana hai', 'aana hai', 'lana hai', 'dena hai', 'lena hai',
        'pickup', 'drop', 'deliver', 'delivery',
        'bhejna hai', 'bhej do', 'laana hai', 'le aana'
    ]
    
    # Memory keywords
    memory_keywords = [
        'yaad rakhna', 'remember', 'memory', 'note karo', 'note kr', 'note kar',
        'yaad karo', 'yaad rakh', 'yaad rakho', 'yaad rakhna hai',
        'mind mein', 'dimaag mein', 'bhoolna mat', 'mat bhoolna',
        'important', 'zaroori', 'special', 'khas', 'yaad hai'
    ]
    
    # Check for numbers (expenses usually have numbers)
    has_number = bool(re.search(r'\d+', text))
    
    # Check for amount pattern (XX rupees, Rs XX, XX rupaye)
    amount_patterns = [
        r'(\d+)\s*(?:rupees|rs|rp|rupaye|रुपये)',
        r'(?:rupees|rs|rp)\s*(\d+)',
        r'(\d+)\s*(?:ka|ke|ki)\s*(?:kharcha|karcha)'
    ]
    has_amount = False
    for pattern in amount_patterns:
        if re.search(pattern, lower):
            has_amount = True
            break
    
    # Score each category
    expense_score = sum(1 for kw in expense_keywords if kw in lower)
    task_score = sum(1 for kw in task_keywords if kw in lower)
    memory_score = sum(1 for kw in memory_keywords if kw in lower)
    
    # Boost expense if amount is present
    if has_amount or has_number:
        expense_score += 3
    
    # Boost task if contains action words with "hai"
    if 'hai' in lower and task_score >= 1:
        task_score += 1
    
    log.info(f"Classification scores - Expense:{expense_score}, Task:{task_score}, Memory:{memory_score} | Has amount:{has_amount} | Text:{text[:50]}")
    
    # Decision logic
    if expense_score >= 3 and (has_number or has_amount):
        return "expense"
    elif expense_score >= 2 and has_number:
        return "expense"
    elif expense_score >= 1 and has_amount:
        return "expense"
    elif task_score >= 2:
        return "task"
    elif task_score >= 1:
        return "task"
    elif memory_score >= 2:
        return "memory"
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
        f"🎙️ *Voice note received! ({duration}s)*\n\n⏳ Processing...",
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
        await status_msg.edit_text("❌ Audio too short or empty!")
        return

    # Try transcription methods
    transcript = None
    method_used = "none"
    
    # Method 1: Groq (best for Hinglish)
    if GROQ_API_KEY:
        await status_msg.edit_text(f"🎙️ *Voice note! ({duration}s)*\n\n🤖 Transcribing with Groq Whisper...", parse_mode="Markdown")
        transcript = await transcribe_with_groq(audio_bytes)
        if transcript:
            method_used = "Groq Whisper"
            log.info(f"Groq success: {transcript[:100]}")
    
    # Method 2: HuggingFace
    if not transcript and HF_API_KEY:
        await status_msg.edit_text(f"🎙️ *Voice note! ({duration}s)*\n\n🔄 Trying HuggingFace Whisper...", parse_mode="Markdown")
        transcript = await transcribe_with_huggingface(audio_bytes)
        if transcript:
            method_used = "HuggingFace Whisper"
            log.info(f"HF success: {transcript[:100]}")
    
    # Method 3: Gemini
    if not transcript and GEMINI_API_KEY:
        await status_msg.edit_text(f"🎙️ *Voice note! ({duration}s)*\n\n🔄 Trying Gemini...", parse_mode="Markdown")
        transcript = await transcribe_with_gemini(audio_bytes)
        if transcript:
            method_used = "Gemini"
            log.info(f"Gemini success: {transcript[:100]}")

    if not transcript:
        await status_msg.edit_text(
            "❌ *Transcription failed!*\n\n"
            "Possible reasons:\n"
            "• Audio quality too poor\n"
            "• No API keys configured\n"
            "• Network issue\n\n"
            "To fix, add GROQ_API_KEY to secrets (recommended)\n"
            "Get free key: https://console.groq.com",
            parse_mode="Markdown"
        )
        if voice_store:
            voice_store.add("[Failed - No transcription]", "none", duration, "Failed", "none")
        return

    # Classify and save
    category = _classify_transcript(transcript)
    saved_to = "diary"
    extra_info = ""
    user_name = update.effective_user.first_name or "User"
    
    log.info(f"Classification result: {category} | Transcript: {transcript[:100]}")

    if category == "task":
        # Clean task text
        task_text = transcript
        remove_words = ["task", "add task", "new task", "kaam", "karna hai", "krna hai", 
                       "karna he", "krna he", "karo", "kar do", "kardo", "please", "plz"]
        for word in remove_words:
            task_text = re.sub(r'\b' + re.escape(word) + r'\b', '', task_text, flags=re.IGNORECASE)
        task_text = re.sub(r'\s+', ' ', task_text).strip()
        if not task_text or len(task_text) < 2:
            task_text = transcript[:80]
        
        t = tasks.add(task_text)
        saved_to = f"task #{t['id']}"
        extra_info = f"✅ Task #{t['id']} add ho gaya!\n📌 *{task_text[:60]}*"
        try:
            sheets_backup.log_event("voice_task", user_name, f"#{t['id']}: {task_text[:80]}")
        except Exception:
            pass

    elif category == "expense":
        # Extract amount
        amount_match = re.search(r'(\d+(?:\.\d+)?)', transcript)
        if amount_match:
            amount = float(amount_match.group(1))
            # Clean description
            desc = transcript
            desc = re.sub(r'\d+(?:\.\d+)?', '', desc)
            remove_words = ["kharcha", "karcha", "expense", "rupees", "rs", "rp", 
                           "laga", "lagaya", "diye", "paisa", "paise", "spent", "on"]
            for word in remove_words:
                desc = re.sub(r'\b' + re.escape(word) + r'\b', '', desc, flags=re.IGNORECASE)
            desc = re.sub(r'\s+', ' ', desc).strip()
            if not desc or len(desc) < 1:
                desc = "Voice expense"
            
            expenses.add(amount, desc[:100])
            saved_to = "expenses"
            extra_info = f"💸 Rs.{amount} expense add ho gaya!\n📝 *{desc[:50]}*"
            try:
                sheets_backup.log_event("voice_expense", user_name, f"Rs.{amount}: {desc[:80]}")
            except Exception:
                pass
        else:
            # No amount found - save to diary as note
            diary.add(f"[Voice Note] {transcript}")
            saved_to = "diary (no amount)"
            extra_info = f"📖 Diary mein save kiya (amount nahi mila)\n📝 *{transcript[:60]}*"

    elif category == "memory":
        # Clean memory text
        memory_text = transcript
        remove_words = ["yaad rakhna", "remember", "memory", "note karo", "note kar",
                       "save karo", "yaad karo", "yaad rakh", "please", "plz"]
        for word in remove_words:
            memory_text = re.sub(r'\b' + re.escape(word) + r'\b', '', memory_text, flags=re.IGNORECASE)
        memory_text = re.sub(r'\s+', ' ', memory_text).strip()
        if not memory_text or len(memory_text) < 2:
            memory_text = transcript[:100]
        
        memory.add(memory_text)
        saved_to = "memory"
        extra_info = f"🧠 Memory mein save ho gaya!\n📝 *{memory_text[:60]}*"
        try:
            sheets_backup.log_event("voice_memory", user_name, memory_text[:100])
        except Exception:
            pass

    else:  # diary
        diary.add(f"[Voice] {transcript}")
        saved_to = "diary"
        extra_info = f"📖 Diary mein save ho gaya!\n📝 *{transcript[:80]}*"
        try:
            sheets_backup.log_event("voice_diary", user_name, transcript[:100])
        except Exception:
            pass

    if voice_store:
        voice_store.add(transcript, saved_to, duration, "Success", method_used)

    # Send response
    response = (
        f"🎙️ *Voice Note Processed!* ✅\n"
        f"🤖 *Method:* {method_used}\n"
        f"⏱ *Duration:* {duration}s\n\n"
        f"📝 *Heard:*\n"
        f"_{transcript[:350]}_\n\n"
        f"{'─' * 30}\n"
        f"💾 {extra_info}\n\n"
        f"📋 /voicenotes — All voice notes"
    )
    
    if len(transcript) > 350:
        response += f"\n\n*(... {len(transcript)-350} more chars)*"
    
    await status_msg.edit_text(response, parse_mode="Markdown")

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
            "🎙️ *No voice notes yet!*\n\n"
            "Send me a voice message and I'll:\n"
            "• Transcribe it in Hinglish\n"
            "• Classify as Task/Expense/Memory/Diary\n"
            "• Save to the right place automatically!\n\n"
            "Examples:\n"
            "• \"500 rupees kharcha kiya movie pe\" → Goes to Expenses\n"
            "• \"Kal meeting hai 10 baje\" → Goes to Tasks\n"
            "• \"Yaad rakhna milk lena hai\" → Goes to Memory\n"
            "• \"Aaj mausam accha hai\" → Goes to Diary",
            parse_mode="Markdown"
        )
        return

    lines = []
    for v in reversed(recent[-10:]):
        status_emoji = "✅" if v.get('status') == "Success" else "❌"
        lines.append(
            f"{status_emoji} *#{v['id']}* {v['date']} {v['time']}\n"
            f"   🤖 {v.get('method', 'unknown')} | ⏱ {v.get('duration', 0)}s\n"
            f"   💾 Saved to: *{v['saved_to']}*\n"
            f"   📝 _{v['transcript'][:100]}_"
        )

    await update.message.reply_text(
        f"🎙️ *Recent Voice Notes (Last 10)*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown"
    )

# ================================================================
# REGISTER FUNCTION
# ================================================================

def register_voice_handlers(app):
    """Register voice handlers with the bot"""
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(CommandHandler("voicenotes", cmd_voicenotes))
    log.info("✅ Voice Note handlers registered (Hinglish + Multi-method transcription)")
