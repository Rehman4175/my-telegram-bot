#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — Only Gemini (Best for Hinglish)
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
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={key}"

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
    TAB_KEY = "VoiceNotes"
    TAB_NAME = "Voice Notes"
    HEADERS = ["ID", "Date", "Time", "Transcript", "Saved To", "Duration", "Status"]

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

    def add(self, transcript: str, saved_to: str = "diary", duration: int = 0, status: str = "Success"):
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
        }
        self.store.data["list"].append(entry)
        self.store.data["list"] = self.store.data["list"][-500:]
        self.store.save()
        self._append_to_sheet([vid, today_str(), now_str(), transcript[:500], saved_to, duration, status])
        return entry

    def get_recent(self, n: int = 10):
        return self.store.data.get("list", [])[-n:]

if _SDM_AVAILABLE:
    voice_store = VoiceNoteStore()
else:
    voice_store = None

# ================================================================
# GEMINI TRANSCRIPTION - BEST FOR HINGLISH
# ================================================================

async def transcribe_audio(audio_bytes: bytes) -> Optional[str]:
    """Transcribe audio using Gemini 1.5 Pro - Best for Hinglish"""
    if not GEMINI_API_KEY:
        log.error("GEMINI_API_KEY not set")
        return None

    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    
    # Detailed Hinglish instruction
    instruction = """Tu ek Hinglish transcription expert hai. Jo bole maine woh Hinglish mein likh.

Hinglish kya hai? Hindi words ko English alphabet mein likhna. Jaise main abhi type kar raha hoon.

Examples of Hinglish (EXACTLY aise likhna):
- "mujhe kal subah 10 baje office jaana hai"
- "aaj mausam bahut accha hai"
- "500 rupees kharcha kiya movie dekhne mein"
- "yaad rakhna milk lena hai"
- "kal meeting hai 3 baje"

Rules:
1. JO BOLA WOHI LIKH - translate mat karo English mein
2. Devanagari script (हिन्दी) mat likhna - sirf English alphabet use karo
3. Numbers digits mein likho: 10, 100, 500
4. Hinglish mein likho jaisa main bol raha hoon
5. Koi extra word mat likhna - sirf transcript

Ab jo voice message bola hai woh Hinglish mein likh:"""

    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "audio/ogg", "data": audio_b64}},
                {"text": instruction}
            ]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 500
        }
    }
    
    _rate_limit()
    url = GEMINI_URL.format(key=GEMINI_API_KEY)
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            
            candidates = result.get("candidates", [])
            if not candidates:
                log.error(f"No candidates: {result}")
                return None
            
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                log.error(f"No parts in response")
                return None
            
            text = parts[0].get("text", "").strip()
            if not text:
                log.error("Empty text from Gemini")
                return None
            
            # Cleanup
            text = re.sub(r'\*+', '', text)
            text = re.sub(r'\n+', ' ', text)
            text = re.sub(r'\[.*?\]', '', text)
            text = re.sub(r'\(.*?\)', '', text)
            
            # Remove any "Transcription:" prefix
            text = re.sub(r'^(transcription|hinglish|text|output)[:\s]*', '', text, flags=re.IGNORECASE)
            
            log.info(f"Transcription: {text[:100]}...")
            return text.strip()
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if hasattr(e, 'read') else ''
        log.error(f"Gemini HTTP {e.code}: {error_body[:300]}")
        return None
    except Exception as e:
        log.error(f"Gemini error: {e}")
        return None

# ================================================================
# BETTER CLASSIFICATION
# ================================================================

def _classify_transcript(text: str) -> str:
    """Classify transcript into task/expense/memory/diary with Hinglish support"""
    lower = text.lower()
    
    # Expense indicators
    expense_indicators = [
        'kharcha', 'karcha', 'kharch', 'laga', 'lagaya', 'diye', 'paisa', 'paise',
        'rupees', 'rs', 'spent', 'khareeda', 'kharida', 'movie', 'film', 'shopping',
        'petrol', 'diesel', 'bill', 'chai', 'coffee', 'khana', 'food', 'lunch', 'dinner'
    ]
    
    # Task indicators  
    task_indicators = [
        'karna hai', 'krna hai', 'karna he', 'kaam', 'task', 'meeting', 'call',
        'phone', 'remind', 'yaad dilana', 'bata dena', 'jana hai', 'jaana hai',
        'aana hai', 'lana hai', 'dena hai', 'submit', 'send', 'buy', 'order'
    ]
    
    # Memory indicators
    memory_indicators = [
        'yaad rakhna', 'remember', 'memory', 'note karo', 'yaad karo',
        'bhoolna mat', 'important', 'zaroori', 'yaad rakh'
    ]
    
    has_number = bool(re.search(r'\d+', text))
    
    expense_score = sum(1 for w in expense_indicators if w in lower)
    task_score = sum(1 for w in task_indicators if w in lower)
    memory_score = sum(1 for w in memory_indicators if w in lower)
    
    # Boost expense if number present
    if has_number and expense_score > 0:
        expense_score += 2
    
    log.info(f"Scores - E:{expense_score} T:{task_score} M:{memory_score} | Text: {text[:50]}")
    
    if expense_score >= 1 and has_number:
        return "expense"
    elif expense_score >= 2:
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
        f"🎙️ *Voice note sun raha hoon...* ({duration}s)\n\n⏳ Processing...",
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

    if len(audio_bytes) < 5000:
        await status_msg.edit_text("❌ Audio bahut chhota hai! Thoda der bolo.")
        return

    # Transcribe with Gemini
    await status_msg.edit_text(f"🎙️ *Voice note ({duration}s)*\n\n🤖 Hinglish mein likh raha hoon...", parse_mode="Markdown")
    
    transcript = await transcribe_audio(audio_bytes)

    if not transcript:
        await status_msg.edit_text(
            "❌ *Smajh nahi aaya!* 😅\n\n"
            "Possible reasons:\n"
            "• Thoda clear bolo\n"
            "• Background noise hai\n"
            "• Bahut short hai\n\n"
            "Dobara try karo! 🎙️",
            parse_mode="Markdown"
        )
        if voice_store:
            voice_store.add("[Failed]", "none", duration, "Failed")
        return

    # Classify and save
    category = _classify_transcript(transcript)
    saved_to = "diary"
    extra_info = ""
    user_name = update.effective_user.first_name or "User"

    log.info(f"Category: {category} | Transcript: {transcript[:100]}")

    if category == "task":
        # Clean task text
        task_text = transcript
        remove = ['karna hai', 'krna hai', 'task', 'kaam', 'karo', 'add']
        for r in remove:
            task_text = re.sub(r'\b' + re.escape(r) + r'\b', '', task_text, flags=re.IGNORECASE)
        task_text = re.sub(r'\s+', ' ', task_text).strip()
        if not task_text or len(task_text) < 3:
            task_text = transcript[:80]
        
        t = tasks.add(task_text)
        saved_to = f"task #{t['id']}"
        extra_info = f"✅ Task #{t['id']} add kar diya!\n📌 *{task_text[:60]}*"

    elif category == "expense":
        amount_match = re.search(r'(\d+(?:\.\d+)?)', transcript)
        if amount_match:
            amount = float(amount_match.group(1))
            desc = transcript
            desc = re.sub(r'\d+(?:\.\d+)?', '', desc)
            remove = ['kharcha', 'karcha', 'laga', 'lagaya', 'diye', 'paisa', 'rupees', 'rs']
            for r in remove:
                desc = re.sub(r'\b' + re.escape(r) + r'\b', '', desc, flags=re.IGNORECASE)
            desc = re.sub(r'\s+', ' ', desc).strip()
            if not desc:
                desc = "Expense"
            
            expenses.add(amount, desc[:100])
            saved_to = "expenses"
            extra_info = f"💸 Rs.{amount} kharcha add kar diya!\n📝 *{desc[:50]}*"
        else:
            diary.add(f"[Voice] {transcript}")
            saved_to = "diary"
            extra_info = f"📖 Diary mein save kiya (amount nahi mila)"

    elif category == "memory":
        memory_text = transcript
        remove = ['yaad rakhna', 'remember', 'memory', 'note karo', 'yaad karo']
        for r in remove:
            memory_text = re.sub(r'\b' + re.escape(r) + r'\b', '', memory_text, flags=re.IGNORECASE)
        memory_text = re.sub(r'\s+', ' ', memory_text).strip()
        if not memory_text:
            memory_text = transcript[:100]
        
        memory.add(memory_text)
        saved_to = "memory"
        extra_info = f"🧠 Memory mein save kar liya!\n📝 *{memory_text[:60]}*"

    else:  # diary
        diary.add(f"[Voice] {transcript}")
        saved_to = "diary"
        extra_info = f"📖 Diary mein save kar diya!\n📝 *{transcript[:70]}*"

    if voice_store:
        voice_store.add(transcript, saved_to, duration, "Success")

    # Send response
    response = f"""🎙️ *Ho gaya!* ✅

⏱ *Duration:* {duration}s
📝 *Tumne kaha:*
_{transcript[:400]}_ 

💾 {extra_info}

📋 /voicenotes - Purane voice notes"""
    
    if len(transcript) > 400:
        response += f"\n\n*(... {len(transcript)-400} aur words)*"
    
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
            "🎙️ *Abhi tak koi voice note nahi hai!*\n\n"
            "Mujhe voice message bhejo - main sununga aur Hinglish mein likhunga!\n\n"
            "Example:\n"
            "• \"500 rupees kharcha kiya movie pe\" → Expenses mein jayega\n"
            "• \"Kal meeting hai 10 baje\" → Tasks mein jayega\n"
            "• \"Yaad rakhna milk lena hai\" → Memory mein jayega",
            parse_mode="Markdown"
        )
        return

    lines = []
    for v in reversed(recent[-10:]):
        emoji = "✅" if v.get('status') == "Success" else "❌"
        lines.append(
            f"{emoji} *#{v['id']}* {v['date']} {v['time']}\n"
            f"   💾 *{v['saved_to']}* | ⏱ {v.get('duration', 0)}s\n"
            f"   📝 _{v['transcript'][:100]}_"
        )

    await update.message.reply_text(
        f"🎙️ *Recent Voice Notes*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown"
    )

# ================================================================
# REGISTER
# ================================================================

def register_voice_handlers(app):
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(CommandHandler("voicenotes", cmd_voicenotes))
    log.info("✅ Voice Note handlers registered (Gemini 1.5 Pro - Hinglish mode)")
