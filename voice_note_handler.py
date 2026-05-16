#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — Rk Bot
FIXED v12 (IST TIMEZONE + ALL BUG FIXES):
  - FIXED: IST timezone (UTC+5:30) for reminders
  - FIXED: "Reminder" first word priority
  - FIXED: Time parsing for "2 min baad"
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
from zoneinfo import ZoneInfo  # Python 3.9+

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, CommandHandler, filters

log = logging.getLogger(__name__)

# ================================================================
# IST TIMEZONE HELPERS (FIXED!)
# ================================================================

IST = ZoneInfo("Asia/Kolkata")

def now_ist() -> datetime:
    """Return current time in IST (Asia/Kolkata)"""
    return datetime.now(IST)

def today_str() -> str:
    """Return today's date string in IST"""
    return now_ist().strftime("%Y-%m-%d")

def now_str() -> str:
    """Return current time string in IST"""
    return now_ist().strftime("%H:%M:%S")

def now_full_str() -> str:
    """Return full timestamp in IST"""
    return now_ist().strftime("%Y-%m-%d %H:%M:%S")

# ================================================================
# IMPORTS FROM SECURE DATA MANAGER
# ================================================================

try:
    from secure_data_manager import (
        diary, tasks, memory, expenses, habits, reminders,
        water, bills, calendar,
        sheets_backup, repo_manager,
        now_ist as sdm_now_ist, today_str as sdm_today_str, now_str as sdm_now_str, 
        PrivateStore,
        channel_logger
    )
    _SDM_AVAILABLE = True
    log.info("✅ secure_data_manager loaded in voice handler")
except ImportError as e:
    log.error(f"secure_data_manager import failed: {e}")
    _SDM_AVAILABLE = False
    channel_logger = None
    # Use our own IST functions when SDM is not available

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
# TIME PARSING (FIXED WITH PROPER IST!)
# ================================================================

def _parse_reminder_full_timestamp(text: str) -> Tuple[str, str, int, str]:
    """Extract time duration and return FULL TIMESTAMP in IST."""
    import re
    
    # Clean the text first - remove "remind", "reminder", etc.
    clean_text = text
    clean_text = re.sub(r'^(remind|reminder|alarm)\s+', '', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\s+(remind|reminder|alarm)\s+', ' ', clean_text, flags=re.IGNORECASE)
    
    text_lower = clean_text.lower().strip()
    
    # FIXED: Always use IST now!
    now = now_ist()
    
    log.info(f"🔍 Parsing time from: '{text}' (cleaned: '{clean_text}') | Now IST: {now}")
    
    # Hindi numbers to digits
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
        clean_text = clean_text.replace(hindi, digit)
    
    # FIXED: Better regex patterns with word boundaries
    patterns = [
        (r'(\d+)\s*(?:minute|min|minutes|mins)\s*(?:baad|mein|main|after|ke\s*baad|bad\s*mein|me)', 'minute'),
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
        
        # FIXED: Ensure timezone-aware IST timestamp
        full_timestamp = due.strftime("%Y-%m-%d %H:%M:%S")
        log.info(f"✅ Parsed: {value} {unit}(s) from now → {full_timestamp} IST")
        
        result_text = clean_text
        if matched_pattern:
            result_text = re.sub(matched_pattern, '', result_text, flags=re.IGNORECASE)
        
        # Remove noise words
        noise_words = ['reminder', 'remind', 'lagao', 'laga', 'karo', 'kar', 'kr', 'set', 'add', 
                       'baad', 'mein', 'main', 'after', 'please', 'plz', 'bata', 'dena', 'mujhe', 
                       'yad', 'yaad', 'dila', 'dilao', 'krao', 'krna', 'me', 'ko']
        for word in noise_words:
            result_text = re.sub(r'\b' + re.escape(word) + r'\b', '', result_text, flags=re.IGNORECASE)
        result_text = re.sub(r'\s+', ' ', result_text).strip()
        result_text = result_text or "Reminder"
        
        return result_text, full_timestamp, value, unit
    
    # Default: 5 minutes
    default_time = now + timedelta(minutes=5)
    full_timestamp = default_time.strftime("%Y-%m-%d %H:%M:%S")
    log.info(f"⚠️ No time pattern found, defaulting to 5 minutes → {full_timestamp} IST")
    
    result_text = clean_text
    noise_words = ['reminder', 'remind', 'lagao', 'laga', 'karo', 'kar', 'kr', 'set', 'add', 'please', 'plz']
    for word in noise_words:
        result_text = re.sub(r'\b' + re.escape(word) + r'\b', '', result_text, flags=re.IGNORECASE)
    result_text = re.sub(r'\s+', ' ', result_text).strip()
    result_text = result_text or "Reminder"
    
    return result_text, full_timestamp, 5, "minute"


# ================================================================
# CLASSIFICATION SYSTEM - FIRST WORD PRIORITY
# ================================================================

def _classify_transcript(text: str, chat_id: str = "") -> Tuple[str, Dict[str, Any]]:
    """
    Main classifier - FIRST WORD decides the category!
    """
    text = text.strip()
    lower = text.lower().strip()
    words = lower.split()
    
    if not words:
        return "diary", {"text": text[:500]}
    
    first_word = words[0]
    
    # Log for debugging
    log.info(f"🔍 CLASSIFY: first_word='{first_word}', full text='{text[:100]}'")
    
    # ============================================================
    # STEP 1: Check if first word is "reminder" or "remind" - FORCE REMINDER
    # ============================================================
    if first_word in ['reminder', 'remind', 'remindme', 'alarm']:
        # Extract everything after first word
        content = ' '.join(words[1:]) if len(words) > 1 else ""
        
        # Remove any "yaad dilana" or similar noise from content
        noise_phrases = ['yaad dilana', 'yaad dila', 'yaad kara', 'mujhe yaad dilana', 'yaad dilao']
        for phrase in noise_phrases:
            content = content.replace(phrase, '')
        
        content = content.strip()
        if not content:
            content = "Reminder"
        
        clean, full_timestamp, t_val, t_unit = _parse_reminder_full_timestamp(content)
        clean = clean.strip() or "Reminder"
        
        log.info(f"🎯 FIRST WORD '{first_word}' → REMINDER | clean text: '{clean}' | at: {full_timestamp} IST")
        
        return "reminder", {
            "text": clean[:200],
            "due_timestamp": full_timestamp,
            "time_value": t_val,
            "time_unit": t_unit,
            "chat_id": chat_id,
        }
    
    # ============================================================
    # STEP 2: Check if text starts with "remind" (case insensitive)
    # ============================================================
    if lower.startswith('remind'):
        # Extract everything after "remind"
        content = text[len('remind'):].strip()
        
        # Remove noise phrases
        noise_phrases = ['yaad dilana', 'yaad dila', 'yaad kara', 'mujhe yaad dilana', 'yaad dilao']
        for phrase in noise_phrases:
            content = content.replace(phrase, '')
        
        content = content.strip()
        if not content:
            content = "Reminder"
        
        clean, full_timestamp, t_val, t_unit = _parse_reminder_full_timestamp(content)
        clean = clean.strip() or "Reminder"
        
        log.info(f"🎯 TEXT STARTS WITH 'remind' → REMINDER | clean text: '{clean}' | at: {full_timestamp} IST")
        
        return "reminder", {
            "text": clean[:200],
            "due_timestamp": full_timestamp,
            "time_value": t_val,
            "time_unit": t_unit,
            "chat_id": chat_id,
        }
    
    # ============================================================
    # STEP 3: Other categories based on first word
    # ============================================================
    
    # Expense words
    if first_word in ['kharcha', 'expense', 'karcha']:
        content = ' '.join(words[1:]) if len(words) > 1 else ""
        amount_m = re.search(r'(\d+(?:\.\d+)?)', content)
        if amount_m:
            amount = float(amount_m.group(1))
            desc = re.sub(r'\d+(?:\.\d+)?', '', content).strip()
            desc = " ".join(desc.split()).strip() or "Expense"
            log.info(f"🎯 FIRST WORD '{first_word}' → EXPENSE | Rs.{amount}")
            return "expense", {"amount": amount, "description": desc[:100]}
        return "diary", {"text": f"[Expense note] {content[:500]}"}
    
    # Task words
    if first_word in ['task', 'todo', 'kaam']:
        content = ' '.join(words[1:]) if len(words) > 1 else ""
        log.info(f"🎯 FIRST WORD '{first_word}' → TASK | '{content}'")
        return "task", {"text": content[:200] or "Task"}
    
    # Habit words
    if first_word in ['habit', 'aadat']:
        content = ' '.join(words[1:]) if len(words) > 1 else ""
        log.info(f"🎯 FIRST WORD '{first_word}' → HABIT | '{content}'")
        return "habit", {"text": content[:150] or "Habit"}
    
    # Water words
    if first_word in ['water', 'pani', 'paani']:
        content = ' '.join(words[1:]) if len(words) > 1 else ""
        amount_m = re.search(r'(\d+(?:\.\d+)?)', content)
        unit_m = re.search(r'(glass|bottle|liter|litre|ltr|ml)', content.lower(), re.IGNORECASE)
        amount = float(amount_m.group(1)) if amount_m else 1.0
        unit = unit_m.group(1).lower() if unit_m else "glass"
        log.info(f"🎯 FIRST WORD '{first_word}' → WATER | {amount} {unit}")
        return "water", {"amount": amount, "unit": unit}
    
    # Memory words (but NOT if it's a reminder - already checked above)
    if first_word in ['memory', 'remember']:
        content = ' '.join(words[1:]) if len(words) > 1 else ""
        log.info(f"🎯 FIRST WORD '{first_word}' → MEMORY | '{content}'")
        return "memory", {"text": content[:200] or "Memory"}
    
    # Bill words
    if first_word in ['bill', 'payment']:
        content = ' '.join(words[1:]) if len(words) > 1 else ""
        amount_m = re.search(r'(\d+(?:\.\d+)?)', content)
        if amount_m:
            amount = float(amount_m.group(1))
            desc = re.sub(r'\d+(?:\.\d+)?', '', content).strip()
            desc = " ".join(desc.split()).strip() or "Bill"
            log.info(f"🎯 FIRST WORD '{first_word}' → BILL | Rs.{amount}")
            return "bill", {"amount": amount, "description": desc[:100]}
        return "diary", {"text": f"[Bill note] {content[:500]}"}
    
    # Calendar words
    if first_word in ['calendar', 'meeting', 'schedule', 'event']:
        content = ' '.join(words[1:]) if len(words) > 1 else ""
        log.info(f"🎯 FIRST WORD '{first_word}' → CALENDAR | '{content}'")
        return "calendar", {"text": content[:200] or "Event"}
    
    # Diary words
    if first_word in ['diary', 'dairy']:
        content = ' '.join(words[1:]) if len(words) > 1 else ""
        log.info(f"🎯 FIRST WORD '{first_word}' → DIARY | '{content}'")
        return "diary", {"text": content[:500] or "Diary entry"}
    
    # ============================================================
    # STEP 4: Check if text contains time indicators (reminder fallback)
    # ============================================================
    time_indicators = ['minute', 'min', 'second', 'sec', 'hour', 'ghanta', 'day', 'din', 'baad', 'mein', 'after']
    has_time = any(ti in lower for ti in time_indicators)
    has_number = re.search(r'\d+', lower)
    contains_remind = 'remind' in lower or 'reminder' in lower
    
    if contains_remind or (has_time and has_number):
        log.info(f"🎯 CONTAINS REMINDER KEYWORD or TIME → REMINDER (fallback)")
        clean, full_timestamp, t_val, t_unit = _parse_reminder_full_timestamp(text)
        clean = clean.strip() or "Reminder"
        return "reminder", {
            "text": clean[:200],
            "due_timestamp": full_timestamp,
            "time_value": t_val,
            "time_unit": t_unit,
            "chat_id": chat_id,
        }
    
    # ============================================================
    # STEP 5: Default to diary
    # ============================================================
    log.info(f"📖 DIARY default | text: '{text[:60]}'")
    return "diary", {"text": text[:500]}


# ================================================================
# MAIN VOICE MESSAGE HANDLER
# ================================================================

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
        log.info(f"Downloaded: {len(audio_bytes)} bytes")
    except Exception as e:
        await status_msg.edit_text(f"❌ Download failed: {e}")
        return

    await status_msg.edit_text(
        f"🎙️ *Voice note* ({duration}s, {len(audio_bytes)//1024}KB)\n\n🤖 Transcribing...",
        parse_mode="Markdown"
    )

    transcript, error, source = await transcribe_audio(audio_bytes)

    if not transcript:
        vosk_status = "✅" if offline_recognizer.available else "❌"
        await status_msg.edit_text(
            f"❌ *Transcription failed!*\n\nError: {error}\n\n"
            f"Gemini: {'✅' if GEMINI_API_KEY else '❌'} | Vosk: {vosk_status}",
            parse_mode="Markdown"
        )
        if voice_store:
            voice_store.add(f"[FAIL] {error[:60]}", "none", "failed", duration, "Failed")
        return

    log.info(f"📝 RAW TRANSCRIPT: '{transcript}' | SOURCE: {source}")

    # Fix common transcription issues
    transcript = transcript.replace('laga0', '')
    transcript = transcript.replace('laga 0', '')
    transcript = transcript.replace('lagao', '')
    transcript = re.sub(r'\b(\d+)\s*baad\b', r'\1 minute baad', transcript, flags=re.IGNORECASE)
    transcript = re.sub(r'\s+', ' ', transcript).strip()

    # Classify based on first word
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

    log.info(f"🎯 Category: {category} | Data: {data}")

    if category == "expense":
        expenses.add(data["amount"], data["description"])
        saved_to = "expenses"
        extra_info = f"💸 Rs.{data['amount']} added!\n📝 {data['description'][:50]}"

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
            # FIXED: Display in 12-hour format with IST indicator
            display_time = dt.strftime("%I:%M %p, %d %b")
        except:
            display_time = due_timestamp
        
        extra_info = f"⏰ Reminder #{r['id']} set!{time_info}\n📌 *{rem_text[:60]}*\n🕐 Will trigger at: *{display_time}*"

    elif category == "task":
        t = tasks.add(data["text"])
        saved_to = f"task #{t['id']}"
        extra_info = f"✅ Task #{t['id']} added!\n📌 {data['text'][:60]}"

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
        goal_ml = water.goal()
        saved_to = "water"
        extra_info = f"💧 {amount} {unit} ({ml}ml) logged!\n🚰 Total today: {total}ml / {goal_ml}ml"

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

    if voice_store:
        voice_store.add(transcript, saved_to, category, duration, "Success")

    try:
        if sheets_backup and hasattr(sheets_backup, 'log_event'):
            sheets_backup.log_event("voice_note", user_name, f"[{category}] {transcript[:80]}")
    except Exception as e:
        log.debug(f"Misc log error: {e}")

    if channel_logger:
        try:
            await channel_logger.log_voice(transcript, category, saved_to, user_name)
        except Exception as e:
            log.debug(f"Channel log error: {e}")

    await status_msg.edit_text(
        f"{emoji} *Ho gaya!* ✅\n\n"
        f"📝 *Tumne kaha:*\n_{transcript[:400]}_\n\n"
        f"{'─' * 20}\n"
        f"💾 {extra_info}\n\n"
        f"🎤 Category: *{category.upper()}*\n"
        f"{source_emoji} Source: *{source_text}*\n"
        f"/voicenotes — Purane notes dekho",
        parse_mode="Markdown"
    )


# ================================================================
# COMMANDS
# ================================================================

async def cmd_voicenotes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not voice_store:
        await update.message.reply_text("❌ Voice store unavailable")
        return

    recent = voice_store.get_recent(10)
    if not recent:
        await update.message.reply_text(
            "🎙️ *No voice notes yet*\n\nSend a voice message!",
            parse_mode="Markdown"
        )
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
        "⏰ *Reminder:* `remind 2 minute baad pani piyo`\n"
        "💸 *Expense:* `kharcha 500 chai pe`\n"
        "✅ *Task:* `task report submit karna hai`\n"
        "💧 *Water:* `pani 2 glass`\n"
        "📖 *Diary:* `diary aaj acha din tha`\n"
        "🧠 *Memory:* `memory passport number 1234`\n\n"
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
        # FIXED: Show current IST time for debugging
        lines.append(f"🕐 Current IST: `{now_ist().strftime('%I:%M %p, %d %b')}`")
    except Exception as e:
        lines.append(f"❌ Debug error: `{e}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def register_voice_handlers(app):
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(CommandHandler("voicenotes", cmd_voicenotes))
    app.add_handler(CommandHandler("voicehelp", cmd_voicehelp))
    app.add_handler(CommandHandler("sheetsdbg", cmd_sheets_debug))

    log.info("✅ Voice handlers registered (v12 - IST Timezone Fixed!)")
