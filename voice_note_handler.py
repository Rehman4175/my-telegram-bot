#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — Rk Bot
FIXED v10 (CRITICAL FIXES):
  - FIXED: Time parsing for "do minute", "2 minute", "do min"
  - FIXED: Category classification priority (reminder pehle check hoga)
  - FIXED: Hindi numbers (do=2, teen=3, etc.)
  - Vosk offline first, Gemini fallback
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


# ================================================================
# VOICE NOTE LOG STORE
# ================================================================

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


# ================================================================
# OFFLINE VOICE RECOGNITION (VOSK)
# ================================================================

VOSK_AVAILABLE = False
try:
    from vosk import Model, KaldiRecognizer
    from pydub import AudioSegment
    VOSK_AVAILABLE = True
    log.info("✅ Vosk imported successfully")
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
            "/home/runner/work/vosk-model-small-hi-0.22",
            "/github/workspace/vosk-model-small-hi-0.22",
            "/opt/hostedtoolcache/vosk-model-small-hi-0.22",
        ]
        model_path = None
        for path in possible_paths:
            if path and os.path.exists(path) and os.path.isdir(path):
                model_path = path
                log.info(f"✅ Found Vosk model at: {path}")
                break
        if VOSK_AVAILABLE and not model_path:
            log.info("Vosk model nahi mila — auto-download ho raha hai...")
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
                size_mb = os.path.getsize(zip_path) // 1024 // 1024
                log.info(f"Download complete ({size_mb} MB) — extracting...")
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(os.getcwd())
                os.remove(zip_path)
                if os.path.exists(dest_path) and os.path.isdir(dest_path):
                    log.info(f"✅ Extracted to: {dest_path}")
                    return dest_path
                else:
                    log.error(f"Folder not found after extract: {dest_path}")
                    return None
            else:
                log.error("Zip file not downloaded")
                return None
        except Exception as e:
            log.error(f"Download/extract failed: {e}")
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except:
                    pass
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
                log.info(f"✅ Offline transcribed: {text[:80]}")
                return text, None
            return None, "No speech detected"
        except Exception as e:
            log.error(f"Offline transcription error: {e}")
            for fp in [temp_ogg, temp_wav]:
                if os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except:
                        pass
            return None, str(e)


offline_recognizer = OfflineTranscriber()


# ================================================================
# GEMINI TRANSCRIPTION (FALLBACK)
# ================================================================

async def transcribe_audio_gemini(audio_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY set nahi hai!"
    if not audio_bytes or len(audio_bytes) < 1000:
        return None, f"Audio too small: {len(audio_bytes) if audio_bytes else 0} bytes"
    log.info(f"Sending to Gemini: {len(audio_bytes)} bytes")
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
    last_error = None
    result = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(GEMINI_URL.format(key=GEMINI_API_KEY), data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="ignore")
                err_json = json.loads(body)
                gemini_msg = err_json.get("error", {}).get("message", body[:200])
            except Exception:
                gemini_msg = f"HTTP {e.code}"
            last_error = f"Gemini HTTP {e.code}: {gemini_msg}"
            if e.code == 503 and attempt < 2:
                wait = 4 * (attempt + 1)
                log.warning(f"503 overloaded, retry {attempt+1}/3 after {wait}s...")
                time.sleep(wait)
                continue
            return None, last_error
        except urllib.error.URLError as e:
            return None, f"Network error: {e.reason}"
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"
    if result is None:
        return None, last_error
    candidates = result.get("candidates", [])
    if not candidates:
        feedback = result.get("promptFeedback", {})
        block = feedback.get("blockReason", "")
        return None, f"No candidates. Block: '{block}'"
    finish = candidates[0].get("finishReason", "")
    if finish in ("SAFETY", "RECITATION", "OTHER"):
        return None, f"Gemini blocked: {finish}"
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        return None, "Empty parts in response"
    text = parts[0].get("text", "").strip()
    if not text:
        return None, "Empty text (silent audio?)"
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'\n+', ' ', text).strip()
    text = re.sub(r'^(transcription|hinglish|text|output)[:\s]*', '', text, flags=re.IGNORECASE)
    log.info(f"✅ Gemini: {text[:80]}")
    return text.strip(), None


# ================================================================
# TRANSCRIPTION WITH FALLBACK — VOSK FIRST
# ================================================================

async def transcribe_audio(audio_bytes: bytes) -> Tuple[Optional[str], Optional[str], str]:
    if offline_recognizer.available:
        log.info("🎯 Using OFFLINE Vosk first")
        transcript, error = await offline_recognizer.transcribe(audio_bytes)
        if transcript and len(transcript) > 3:
            log.info(f"✅ Offline transcribed: {transcript[:80]}")
            return transcript, None, "offline"
        log.warning(f"Offline failed: {error}")
    if GEMINI_API_KEY:
        log.info("🌐 Falling back to Gemini")
        transcript, error = await transcribe_audio_gemini(audio_bytes)
        if transcript:
            return transcript, None, "gemini"
    return None, "No transcription available", None


# ================================================================
# TIME PARSING - COMPLETELY FIXED
# ================================================================

def _parse_reminder_full_timestamp(text: str) -> Tuple[str, str, int, str]:
    """
    Extract time duration and return FULL TIMESTAMP.
    Supports: "2 minute baad", "do minute baad", "2 min", "2m", etc.
    """
    import re
    
    text_lower = text.lower().strip()
    now = now_ist() if 'now_ist' in dir() else datetime.now()
    
    log.info(f"🔍 Parsing time from: '{text}'")
    
    # Hindi numbers to digits (extended)
    hindi_numbers = {
        'do': '2', 'don': '2', 'doo': '2',
        'teen': '3', 'tin': '3', 'tiin': '3',
        'chaar': '4', 'char': '4',
        'paanch': '5', 'panch': '5',
        'chhe': '6', 'che': '6',
        'saat': '7', 'sat': '7',
        'aath': '8', 'ath': '8',
        'nau': '9', 'naw': '9',
        'das': '10', 'dus': '10', 'dass': '10'
    }
    
    for hindi, digit in hindi_numbers.items():
        text_lower = text_lower.replace(hindi, digit)
        text = text.replace(hindi, digit)
    
    # Patterns for time extraction - ORDER MATTERS (longest first)
    patterns = [
        (r'(\d+)\s*(?:minute|min|minutes|mins)\s*(?:baad|mein|main|after|ke baad|bad mein|me)', 'minute'),
        (r'(\d+)\s*(?:minute|min|minutes|mins)\b', 'minute'),
        (r'(\d+)\s*m\b', 'minute'),
        (r'(\d+)\s*(?:second|sec|seconds|secs)\s*(?:baad|mein|main|after)', 'second'),
        (r'(\d+)\s*(?:hour|hr|hours|hrs|ghanta|ghante)\s*(?:baad|mein|main|after)', 'hour'),
        (r'(\d+)\s*(?:day|days|din)\s*(?:baad|mein|main|after)', 'day'),
    ]
    
    value = None
    unit = None
    matched_pattern = None
    
    for pattern, u in patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            unit = u
            matched_pattern = pattern
            break
    
    if value is not None and unit is not None:
        if unit == 'minute':
            due = now + timedelta(minutes=value)
        elif unit == 'second':
            due = now + timedelta(seconds=value)
        elif unit == 'hour':
            due = now + timedelta(hours=value)
        else:
            due = now + timedelta(days=value)
        
        full_timestamp = due.strftime("%Y-%m-%d %H:%M:%S")
        log.info(f"✅ Parsed: {value} {unit}(s) from now → {full_timestamp}")
        
        clean = text
        if matched_pattern:
            clean = re.sub(matched_pattern, '', clean, flags=re.IGNORECASE)
        
        noise_words = ['reminder', 'remind', 'lagao', 'laga', 'karo', 'kar', 'kr', 'set', 'add', 
                       'baad', 'mein', 'main', 'after', 'please', 'plz', 'bata', 'dena', 'mujhe', 
                       'yad', 'yaad', 'dila', 'dilao', 'krao', 'krna']
        for word in noise_words:
            clean = re.sub(r'\b' + re.escape(word) + r'\b', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s+', ' ', clean).strip()
        clean = clean or "Reminder"
        
        return clean, full_timestamp, value, unit
    
    # If no pattern but text contains number and "minute"
    number_match = re.search(r'(\d+)', text_lower)
    if number_match and ('minute' in text_lower or 'min' in text_lower):
        value = int(number_match.group(1))
        due = now + timedelta(minutes=value)
        full_timestamp = due.strftime("%Y-%m-%d %H:%M:%S")
        log.info(f"✅ Using number {value} as minutes → {full_timestamp}")
        
        clean = re.sub(r'\d+', '', text)
        noise_words = ['reminder', 'remind', 'lagao', 'laga', 'karo', 'kar', 'kr', 'set', 'add', 
                       'baad', 'mein', 'main', 'after', 'please', 'plz', 'minute', 'min']
        for word in noise_words:
            clean = re.sub(r'\b' + re.escape(word) + r'\b', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s+', ' ', clean).strip()
        clean = clean or "Reminder"
        
        return clean, full_timestamp, value, "minute"
    
    # Default: 5 minutes
    default_time = now + timedelta(minutes=5)
    full_timestamp = default_time.strftime("%Y-%m-%d %H:%M:%S")
    log.info(f"⚠️ No time pattern found, defaulting to 5 minutes → {full_timestamp}")
    
    clean = text
    noise_words = ['reminder', 'remind', 'lagao', 'laga', 'karo', 'kar', 'kr', 'set', 'add', 'please', 'plz']
    for word in noise_words:
        clean = re.sub(r'\b' + re.escape(word) + r'\b', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\s+', ' ', clean).strip()
    clean = clean or "Reminder"
    
    return clean, full_timestamp, 5, "minute"


# ================================================================
# CLASSIFICATION SYSTEM - PRIORITY FIXED
# ================================================================

PREFIX_MAP = {
    "reminder": "reminder", "remind": "reminder", "alarm": "reminder",
    "yaad dilao": "reminder", "yaad": "reminder",
    "task": "task", "todo": "task", "kaam": "task",
    "kharcha": "expense", "expense": "expense", "karcha": "expense",
    "habit": "habit", "aadat": "habit",
    "water": "water", "pani": "water", "paani": "water",
    "memory": "memory", "yaad rakhna": "memory",
    "bill": "bill", "payment": "bill",
    "calendar": "calendar", "meeting": "calendar",
    "diary": "diary", "dairy": "diary"
}

_ADD_WORDS = {"add", "kr", "karo", "kar", "likho", "likh", "save", "set", "lagao", "laga", "krao"}


def _classify_transcript(text: str, chat_id: str = "") -> Tuple[str, Dict[str, Any]]:
    """
    Main classifier with PRIORITY for reminder keywords.
    """
    lower = text.lower().strip()
    
    # STEP 1: Check if this is a reminder (HIGHEST PRIORITY)
    reminder_keywords = ['reminder', 'remind', 'alarm', 'yaad dilao', 'yaad dila', 'bata dena']
    time_indicators = ['minute', 'min', 'second', 'sec', 'hour', 'ghanta', 'day', 'din', 'baad', 'mein']
    
    # If has reminder keyword OR (has time indicator AND has a number)
    is_reminder = any(kw in lower for kw in reminder_keywords)
    has_time = any(ti in lower for ti in time_indica
