#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — Rk Bot
FIXED v9 - Complete Working
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
import zipfile
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, CommandHandler, filters

log = logging.getLogger(__name__)

# Import from secure_data_manager
try:
    from secure_data_manager import (
        diary, tasks, memory, expenses, habits, reminders,
        water, bills, calendar,
        sheets_backup, repo_manager,
        now_ist, today_str, now_str, PrivateStore,
        channel_logger
    )
    _SDM_AVAILABLE = True
    log.info("✅ secure_data_manager loaded in voice handler")
except ImportError as e:
    log.error(f"secure_data_manager import failed: {e}")
    _SDM_AVAILABLE = False
    channel_logger = None

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"

_last_call = 0

def _rate_limit():
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 2:
        time.sleep(2 - elapsed)
    _last_call = time.time()


# Voice Note Store
class VoiceNoteStore:
    TAB_NAME = "Voice Notes"
    HEADERS = ["ID", "Date", "Time", "Transcript", "Saved To", "Duration", "Status", "Category"]

    def __init__(self):
        if not _SDM_AVAILABLE:
            return
        self.store = PrivateStore("voice_notes", {"list": [], "counter": 0})
        self._ensure_sheet_tab()

    def _ensure_sheet_tab(self):
        try:
            if not sheets_backup or not sheets_backup.connected:
                return
            existing = [ws.title for ws in sheets_backup._book.worksheets()]
            if self.TAB_NAME not in existing:
                ws = sheets_backup._book.add_worksheet(title=self.TAB_NAME, rows=2000, cols=len(self.HEADERS))
                ws.append_row(self.HEADERS, value_input_option="USER_ENTERED")
                sheets_backup._ws_cache[self.TAB_NAME] = ws
                log.info(f"✅ Created '{self.TAB_NAME}' tab")
            else:
                if self.TAB_NAME not in sheets_backup._ws_cache:
                    ws = sheets_backup._book.worksheet(self.TAB_NAME)
                    sheets_backup._ws_cache[self.TAB_NAME] = ws
        except Exception as e:
            log.error(f"VoiceNotes tab error: {e}")

    def _append_to_sheet(self, row):
        try:
            if not sheets_backup or not sheets_backup.connected:
                return
            ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if ws:
                ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
        except Exception as e:
            log.error(f"Sheet append failed: {e}")

    def add(self, transcript: str, saved_to: str = "diary", category: str = "diary",
            duration: int = 0, status: str = "Success"):
        if not _SDM_AVAILABLE:
            return None
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        vid = self.store.data["counter"]
        entry = {
            "id": vid, "date": today_str(), "time": now_str(),
            "transcript": transcript, "saved_to": saved_to,
            "category": category, "duration": duration, "status": status,
        }
        self.store.data["list"].append(entry)
        self.store.data["list"] = self.store.data["list"][-500:]
        self.store.save()
        self._append_to_sheet([vid, today_str(), now_str(),
                                transcript[:500], saved_to, duration, status, category])
        return entry

    def get_recent(self, n: int = 10):
        return self.store.data.get("list", [])[-n:]


if _SDM_AVAILABLE:
    voice_store = VoiceNoteStore()
    log.info("✅ VoiceNoteStore initialized")
else:
    voice_store = None


# Offline Vosk Transcriber
VOSK_AVAILABLE = False
try:
    from vosk import Model, KaldiRecognizer
    from pydub import AudioSegment
    VOSK_AVAILABLE = True
    log.info("✅ Vosk imported")
except ImportError as e:
    log.warning(f"Vosk not available: {e}")


class OfflineTranscriber:
    MODEL_NAME = "vosk-model-small-hi-0.22"
    MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip"

    def __init__(self):
        self.model = None
        self.available = False
        possible_paths = [
            os.environ.get("VOSK_MODEL_PATH", ""),
            self.MODEL_NAME,
            os.path.join(os.getcwd(), self.MODEL_NAME),
            os.path.join(os.path.dirname(__file__), self.MODEL_NAME),
        ]
        model_path = None
        for path in possible_paths:
            if path and os.path.exists(path) and os.path.isdir(path):
                model_path = path
                log.info(f"✅ Found Vosk model at: {path}")
                break
        if VOSK_AVAILABLE and not model_path:
            log.info("Downloading Vosk model...")
            model_path = self._download_model()
        if VOSK_AVAILABLE and model_path and os.path.exists(model_path):
            try:
                self.model = Model(model_path)
                self.available = True
                log.info(f"✅ Vosk model loaded")
            except Exception as e:
                log.error(f"Vosk model load failed: {e}")

    def _download_model(self) -> Optional[str]:
        zip_path = os.path.join(os.getcwd(), f"{self.MODEL_NAME}.zip")
        dest_path = os.path.join(os.getcwd(), self.MODEL_NAME)
        if os.path.exists(dest_path) and os.path.isdir(dest_path):
            return dest_path
        try:
            log.info(f"📥 Downloading Vosk model...")
            urllib.request.urlretrieve(self.MODEL_URL, zip_path)
            if os.path.exists(zip_path):
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(os.getcwd())
                os.remove(zip_path)
                if os.path.exists(dest_path):
                    return dest_path
            return None
        except Exception as e:
            log.error(f"Download failed: {e}")
            return None

    async def transcribe(self, audio_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
        if not self.available:
            return None, "Offline model not available"
        temp_ogg = "temp_voice.ogg"
        temp_wav = "temp_voice.wav"
        try:
            with open(temp_ogg, "wb") as f:
                f.write(audio_bytes)
            def convert_audio():
                audio = AudioSegment.from_ogg(temp_ogg)
                audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
                audio.export(temp_wav, format="wav")
            await asyncio.to_thread(convert_audio)
            rec = KaldiRecognizer(self.model, 16000)
            text_parts = []
            with open(temp_wav, "rb") as f:
                while True:
                    data = f.read(4000)
                    if not data:
                        break
                    if rec.AcceptWaveform(data):
                        result = json.loads(rec.Result())
                        if result.get("text"):
                            text_parts.append(result["text"])
                final = json.loads(rec.FinalResult())
                if final.get("text"):
                    text_parts.append(final["text"])
            text = " ".join(text_parts).strip()
            for fp in [temp_ogg, temp_wav]:
                if os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except:
                        pass
            if text:
                return text, None
            return None, "No speech detected"
        except Exception as e:
            log.error(f"Offline error: {e}")
            return None, str(e)


offline_recognizer = OfflineTranscriber()


# Gemini Transcription
async def transcribe_audio_gemini(audio_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY not set"
    if not audio_bytes or len(audio_bytes) < 1000:
        return None, f"Audio too small"
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    instruction = """Transcribe this voice message exactly as spoken.
Speaker uses Hinglish (Hindi words written in English letters).
Write ONLY what was said. No explanation, no prefix.
Use English alphabet only.
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
    for attempt in range(3):
        try:
            req = urllib.request.Request(GEMINI_URL.format(key=GEMINI_API_KEY), data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                break
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
                continue
            return None, str(e)
    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        text = re.sub(r'\*+', '', text)
        text = re.sub(r'\n+', ' ', text).strip()
        return text, None
    except Exception as e:
        return None, f"Parse error: {e}"


async def transcribe_audio(audio_bytes: bytes) -> Tuple[Optional[str], Optional[str], str]:
    if offline_recognizer.available:
        transcript, error = await offline_recognizer.transcribe(audio_bytes)
        if transcript:
            return transcript, None, "offline"
    if GEMINI_API_KEY:
        transcript, error = await transcribe_audio_gemini(audio_bytes)
        if transcript:
            return transcript, None, "gemini"
    return None, "No transcription available", None


# Parse Reminder Time with Hindi number support
def _parse_reminder_full_timestamp(text: str) -> Tuple[str, str, int, str]:
    text_lower = text.lower().strip()
    now = now_ist() if 'now_ist' in dir() else datetime.now()
    
    # Hindi numbers
    hindi_numbers = {'do': 2, 'teen': 3, 'chaar': 4, 'paanch': 5, 'chhe': 6, 'saat': 7, 'aath': 8, 'nau': 9, 'das': 10}
    for hindi, digit in hindi_numbers.items():
        text_lower = text_lower.replace(hindi, str(digit))
        text = text.replace(hindi, str(digit))
    
    patterns = [
        (r'(\d+)\s*(?:minute|min|minutes|mins)\s*(?:baad|mein|main|after)', 'minute'),
        (r'(\d+)\s*(?:minute|min|minutes|mins)\b', 'minute'),
        (r'(\d+)\s*(?:second|sec|seconds|secs)\s*(?:baad|mein|main|after)', 'second'),
        (r'(\d+)\s*(?:hour|hr|hours|hrs|ghanta|ghante)\s*(?:baad|mein|main|after)', 'hour'),
        (r'(\d+)\s*(?:day|days|din)\s*(?:baad|mein|main|after)', 'day'),
    ]
    
    for pattern, unit in patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            if unit == 'minute':
                due = now + timedelta(minutes=value)
            elif unit == 'second':
                due = now + timedelta(seconds=value)
            elif unit == 'hour':
                due = now + timedelta(hours=value)
            else:
                due = now + timedelta(days=value)
            full_timestamp = due.strftime("%Y-%m-%d %H:%M:%S")
            clean = re.sub(pattern, '', text, flags=re.IGNORECASE)
            for word in ['reminder', 'lagao', 'laga', 'karo', 'kar', 'kr', 'set', 'add', 'baad', 'mein', 'main', 'after', 'please', 'plz', 'mujhe']:
                clean = re.sub(r'\b' + re.escape(word) + r'\b', '', clean, flags=re.IGNORECASE)
            clean = re.sub(r'\s+', ' ', clean).strip()
            clean = clean or "Reminder"
            return clean, full_timestamp, value, unit
    
    # Default 5 minutes
    default_time = now + timedelta(minutes=5)
    full_timestamp = default_time.strftime("%Y-%m-%d %H:%M:%S")
    return text, full_timestamp, 5, "minute"


# Classification
PREFIX_MAP = {
    "diary": "diary", "dairy": "diary",
    "task": "task", "todo": "task", "kaam": "task",
    "reminder": "reminder", "remind": "reminder", "alarm": "reminder",
    "yaad dilao": "reminder", "yaad": "reminder",
    "expense": "expense", "kharcha": "expense", "karcha": "expense",
    "habit": "habit", "aadat": "habit",
    "water": "water", "pani": "water", "paani": "water",
    "memory": "memory", "yaad rakhna": "memory", "remember": "memory",
    "bill": "bill", "payment": "bill",
    "calendar": "calendar", "schedule": "calendar", "meeting": "calendar"
}
_ADD_WORDS = {"add", "kr", "karo", "kar", "likho", "likh", "save", "set", "lagao", "laga"}


def _build_params(category: str, content: str, chat_id: str) -> Tuple[str, Dict[str, Any]]:
    lower = content.lower().strip()
    if category == "expense":
        amount_m = re.search(r'(\d+(?:\.\d+)?)', lower)
        if amount_m:
            amount = float(amount_m.group(1))
            desc = re.sub(r'\d+(?:\.\d+)?', '', content).strip()
            desc = " ".join(desc.split()).strip() or "Expense"
            return "expense", {"amount": amount, "description": desc[:100]}
        return "diary", {"text": f"[Expense note] {content[:500]}"}
    elif category == "reminder":
        clean, full_timestamp, t_val, t_unit = _parse_reminder_full_timestamp(content)
        clean = clean.strip() or "Reminder"
        return "reminder", {
            "text": clean[:200],
            "due_timestamp": full_timestamp,
            "time_value": t_val,
            "time_unit": t_unit,
            "chat_id": chat_id,
        }
    elif category == "task":
        return "task", {"text": content[:200]}
    elif category == "habit":
        return "habit", {"text": content[:150]}
    elif category == "water":
        amount_m = re.search(r'(\d+(?:\.\d+)?)', lower)
        unit_m = re.search(r'(glass|bottle|liter|litre|ltr|ml)', lower, re.IGNORECASE)
        amount = float(amount_m.group(1)) if amount_m else 1.0
        unit = unit_m.group(1).lower() if unit_m else "glass"
        return "water", {"amount": amount, "unit": unit}
    elif category == "memory":
        return "memory", {"text": content[:200]}
    elif category == "bill":
        amount_m = re.search(r'(\d+(?:\.\d+)?)', lower)
        if amount_m:
            amount = float(amount_m.group(1))
            desc = re.sub(r'\d+(?:\.\d+)?', '', content).strip()
            desc = " ".join(desc.split()).strip() or "Bill"
            return "bill", {"amount": amount, "description": desc[:100]}
        return "diary", {"text": f"[Bill note] {content[:500]}"}
    elif category == "calendar":
        clean = content
        for nw in ["calendar", "meeting", "appointment", "add", "karo"]:
            clean = re.sub(r'\b' + re.escape(nw) + r'\b', ' ', clean, flags=re.IGNORECASE)
        clean = " ".join(clean.split()).strip() or content
        return "calendar", {"text": clean[:200]}
    else:
        return "diary", {"text": content[:500]}


def _classify_transcript(text: str, chat_id: str = ""):
    lower = text.lower().strip()
    for prefix in sorted(PREFIX_MAP.keys(), key=len, reverse=True):
        if lower.startswith(prefix):
            category = PREFIX_MAP[prefix]
            rest = lower[len(prefix):].strip()
            words = rest.split()
            if words and words[0] in _ADD_WORDS:
                rest = " ".join(words[1:]).strip()
            content = rest or text
            return _build_params(category, content, chat_id)
    
    # Default to diary
    return "diary", {"text": text[:500]}


# Main Voice Handler
async def handle_voice_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _SDM_AVAILABLE:
        await update.message.reply_text("❌ Voice feature unavailable")
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    duration = getattr(voice, "duration", 0)
    user_name = update.effective_user.first_name or "User"
    chat_id = str(update.effective_chat.id)

    status_msg = await update.message.reply_text(
        f"🎙️ *Voice note mila!* ({duration}s)\n\n⏳ Processing...",
        parse_mode="Markdown"
    )

    try:
        file_obj = await ctx.bot.get_file(voice.file_id)
        audio_bytes = bytes(await file_obj.download_as_bytearray())
    except Exception as e:
        await status_msg.edit_text(f"❌ Download failed: {e}")
        return

    await status_msg.edit_text("🤖 Transcribing...")
    transcript, error, source = await transcribe_audio(audio_bytes)

    if not transcript:
        await status_msg.edit_text(f"❌ Transcription failed: {error}")
        if voice_store:
            voice_store.add(f"[FAIL] {error[:60]}", "none", "failed", duration, "Failed")
        return

    # Log to channel
    if channel_logger:
        try:
            await channel_logger.log_voice(transcript, "processing", "pending", user_name)
        except Exception as e:
            log.debug(f"Channel log error: {e}")

    category, data = _classify_transcript(transcript, chat_id)
    
    saved_to = "diary"
    extra_info = ""
    emoji_map = {
        "expense": "💸", "reminder": "⏰", "habit": "🔥", "water": "💧",
        "task": "✅", "memory": "🧠", "bill": "🧾", "calendar": "📅", "diary": "📖"
    }
    emoji = emoji_map.get(category, "📝")
    source_emoji = "📴" if source == "offline" else "🌐"
    source_text = "Vosk (Offline)" if source == "offline" else "Gemini"

    if category == "expense":
        expenses.add(data["amount"], data["description"])
        saved_to = "expenses"
        extra_info = f"💸 Rs.{data['amount']} added!\n📝 {data['description'][:50]}"
        if channel_logger:
            await channel_logger.log_expense(data["amount"], data["description"])

    elif category == "reminder" and reminders:
        due_timestamp = data.get("due_timestamp", "")
        rem_text = data.get("text", "Reminder")
        r_chat_id = int(data.get("chat_id") or chat_id)
        r = reminders.add(r_chat_id, rem_text, due_timestamp, "once")
        saved_to = f"reminder #{r['id']}"
        t_val = data.get('time_value', 0)
        t_unit = data.get('time_unit', '')
        time_info = f" — {t_val} {t_unit}" if t_val else ""
        try:
            dt = datetime.strptime(due_timestamp, "%Y-%m-%d %H:%M:%S")
            display_time = dt.strftime("%I:%M %p, %d %b")
        except:
            display_time = due_timestamp
        extra_info = f"⏰ Reminder #{r['id']} set!{time_info}\n📌 {rem_text[:60]}\n🕐 Will trigger at: {display_time}"

    elif category == "task":
        t = tasks.add(data["text"])
        saved_to = f"task #{t['id']}"
        extra_info = f"✅ Task #{t['id']} added!\n📌 {data['text'][:60]}"
        if channel_logger:
            await channel_logger.log_task(t['id'], data['text'])

    elif category == "habit":
        h = habits.add(data["text"])
        saved_to = f"habit #{h['id']}"
        extra_info = f"🔥 Habit #{h['id']} added!\n📌 {data['text'][:60]}"

    elif category == "water" and water:
        unit = data.get("unit", "glass")
        amount = data.get("amount", 1.0)
        unit_ml = {"glass": 250, "bottle": 500, "liter": 1000, "ltr": 1000}.get(unit.lower(), 250)
        ml = int(amount * unit_ml)
        total = water.add(ml)
        saved_to = "water"
        extra_info = f"💧 {amount} {unit} ({ml}ml) logged!\nTotal: {total}ml"

    elif category == "memory":
        memory.add(data["text"])
        saved_to = "memory"
        extra_info = f"🧠 Memory saved!\n📝 {data['text'][:60]}"

    elif category == "bill":
        b = bills.add(data["description"], data["amount"], 0)
        saved_to = f"bill #{b['id']}"
        extra_info = f"🧾 Bill Rs.{data['amount']} added!\n📝 {data['description'][:50]}"

    elif category == "calendar" and calendar:
        e = calendar.add(data["text"], today_str(), "")
        saved_to = f"calendar #{e['id']}"
        extra_info = f"📅 Event #{e['id']} added!\n📌 {data['text'][:50]}"

    else:
        diary.add(f"[Voice] {data['text']}")
        saved_to = "diary"
        extra_info = "📖 Saved to diary!"
        if channel_logger:
            await channel_logger.log_diary(data['text'])

    if voice_store:
        voice_store.add(transcript, saved_to, category, duration, "Success")

    await status_msg.edit_text(
        f"{emoji} *Done!* ✅\n\n"
        f"📝 *You said:*\n_{transcript[:300]}_\n\n"
        f"{'─' * 20}\n"
        f"💾 {extra_info}\n\n"
        f"🏷 Category: *{category.upper()}*\n"
        f"{source_emoji} Source: *{source_text}*\n"
        f"/voicenotes — View all",
        parse_mode="Markdown"
    )


# Commands
async def cmd_voicenotes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not voice_store:
        await update.message.reply_text("❌ Voice store unavailable")
        return
    recent = voice_store.get_recent(10)
    if not recent:
        await update.message.reply_text("🎙️ *No voice notes yet*\n\nSend a voice message!", parse_mode="Markdown")
        return
    emoji_map = {"expense": "💸", "reminder": "⏰", "habit": "🔥", "water": "💧", "task": "✅", "memory": "🧠", "bill": "🧾", "calendar": "📅", "diary": "📖"}
    lines = []
    for v in reversed(recent):
        category = v.get("category", "diary")
        emoji = emoji_map.get(category, "📝")
        status = "✅" if v.get("status") == "Success" else "❌"
        lines.append(f"{status} {emoji} *#{v['id']}* {v['date']} {v['time']}\n   💾 *{v['saved_to']}* | ⏱ {v.get('duration', 0)}s\n   📝 _{v['transcript'][:100]}_")
    await update.message.reply_text("🎙️ *Recent Voice Notes:*\n\n" + "\n\n".join(lines), parse_mode="Markdown")


async def cmd_voicehelp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎙️ *Voice Commands Guide*\n\n"
        "💸 `kharcha 500 chai pe`\n"
        "⏰ `reminder 2 minute baad pani peena`\n"
        "✅ `task report submit karna hai`\n"
        "💧 `water 2 glass`\n"
        "📖 `diary aaj acha din tha`\n\n"
        "/voicenotes — View recent notes",
        parse_mode="Markdown"
    )


async def cmd_sheets_debug(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["📊 *Google Sheets Debug:*\n"]
    try:
        if not _SDM_AVAILABLE:
            lines.append("❌ secure_data_manager not loaded")
        else:
            lines.append("✅ secure_data_manager loaded")
        if not sheets_backup:
            lines.append("❌ sheets_backup is None")
        else:
            connected = getattr(sheets_backup, 'connected', 'unknown')
            lines.append(f"{'✅' if connected else '❌'} connected: `{connected}`")
        if voice_store:
            lines.append("✅ voice_store initialized")
            lines.append(f"📝 Total voice notes: `{len(voice_store.store.data.get('list', []))}`")
        else:
            lines.append("❌ voice_store is None")
    except Exception as e:
        lines.append(f"❌ Debug error: `{e}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def register_voice_handlers(app):
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(CommandHandler("voicenotes", cmd_voicenotes))
    app.add_handler(CommandHandler("voicehelp", cmd_voicehelp))
    app.add_handler(CommandHandler("sheetsdbg", cmd_sheets_debug))
    log.info("✅ Voice handlers registered (v9)")
