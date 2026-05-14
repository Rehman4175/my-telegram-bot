#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — Rk Bot
FIXED v9 (FINAL - TIME PARSING FIXED):
  - VOSK FIRST: Offline transcription priority (more reliable for Hinglish)
  - Gemini fallback only if Vosk fails
  - FIXED: Better Hinglish time parsing ("2 minute baad", "5 min mein", etc.)
  - FIXED: Hindi number support (do=2, teen=3, etc.)
  - FIXED: Proper timestamp calculation
  - All categories working: expense, reminder, task, habit, water, memory, bill, calendar, diary
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

# ── Import from secure_data_manager (single source of truth) ──
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
# OFFLINE VOICE RECOGNITION (VOSK) — AUTO DOWNLOAD
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
    """
    Returns: (text, error, source)
    Priority: VOSK (Offline) first → Gemini (Online) fallback
    """
    if offline_recognizer.available:
        log.info("🎯 Using OFFLINE Vosk first (more reliable for Hinglish)")
        transcript, error = await offline_recognizer.transcribe(audio_bytes)
        if transcript and len(transcript) > 3:
            log.info(f"✅ Offline transcribed: {transcript[:80]}")
            return transcript, None, "offline"
        log.warning(f"Offline failed: {error}, falling back to Gemini")
    if GEMINI_API_KEY:
        log.info("🌐 Falling back to Gemini Online")
        transcript, error = await transcribe_audio_gemini(audio_bytes)
        if transcript:
            return transcript, None, "gemini"
        log.warning(f"Gemini failed: {error}")
    return None, "No transcription method available (Vosk offline + Gemini API both failed)", None


# ================================================================
# ✅ TIME PARSING - FIXED FOR HINGLISH
# ================================================================

def _parse_reminder_full_timestamp(text: str) -> Tuple[str, str, int, str]:
    """
    Extract time duration and return FULL TIMESTAMP.
    Better parsing for Hinglish voice commands like:
    - "2 minute baad pani piyo"
    - "5 min mein chai"
    - "do minute baad" (Hindi number)
    """
    import re
    
    text_lower = text.lower().strip()
    now = now_ist() if 'now_ist' in dir() else datetime.now()
    
    log.info(f"🔍 Parsing time from: '{text}'")
    
    # Hindi numbers to digits
    hindi_numbers = {
        'do': '2', 'teen': '3', 'chaar': '4', 'paanch': '5',
        'chhe': '6', 'saat': '7', 'aath': '8', 'nau': '9', 'das': '10',
        'gyarah': '11', 'barah': '12', 'terah': '13', 'chaudah': '14',
        'pandrah': '15', 'solah': '16', 'satrah': '17', 'atharah': '18',
        'unnis': '19', 'bees': '20'
    }
    
    for hindi, digit in hindi_numbers.items():
        text_lower = text_lower.replace(hindi, digit)
    
    # Patterns for Hinglish
    patterns = [
        (r'(\d+)\s*(?:minute|min|minutes|mins)\s*(?:baad|mein|main|after|ke baad|bad mein|me)', 'minute'),
        (r'(\d+)\s*(?:minute|min|minutes|mins)\b', 'minute'),
        (r'(\d+)\s*(?:second|sec|seconds|secs)\s*(?:baad|mein|main|after)', 'second'),
        (r'(\d+)\s*(?:hour|hr|hours|hrs|ghanta|ghante)\s*(?:baad|mein|main|after)', 'hour'),
        (r'(\d+)\s*(?:day|days|din)\s*(?:baad|mein|main|after)', 'day'),
        (r'(\d+)\s*m\b', 'minute'),
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
            
            log.info(f"✅ Parsed: {value} {unit}(s) from now → {full_timestamp}")
            
            # Clean the text
            clean = text
            clean = re.sub(pattern, '', clean, flags=re.IGNORECASE)
            noise_words = ['reminder', 'lagao', 'laga', 'karo', 'kar', 'kr', 'set', 'add', 
                           'baad', 'mein', 'main', 'after', 'please', 'plz', 'bata', 'dena', 'mujhe']
            for word in noise_words:
                clean = re.sub(r'\b' + re.escape(word) + r'\b', '', clean, flags=re.IGNORECASE)
            clean = re.sub(r'\s+', ' ', clean).strip()
            clean = clean or "Reminder"
            
            return clean, full_timestamp, value, unit
    
    # If no pattern found, try to extract just the number
    number_match = re.search(r'(\d+)', text_lower)
    if number_match:
        value = int(number_match.group(1))
        due = now + timedelta(minutes=value)
        full_timestamp = due.strftime("%Y-%m-%d %H:%M:%S")
        log.info(f"✅ Using number {value} as minutes → {full_timestamp}")
        
        clean = re.sub(r'\d+', '', text)
        noise_words = ['reminder', 'lagao', 'laga', 'karo', 'kar', 'kr', 'set', 'add', 
                       'baad', 'mein', 'main', 'after', 'please', 'plz']
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
    noise_words = ['reminder', 'lagao', 'laga', 'karo', 'kar', 'kr', 'set', 'add', 'please', 'plz']
    for word in noise_words:
        clean = re.sub(r'\b' + re.escape(word) + r'\b', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\s+', ' ', clean).strip()
    clean = clean or "Reminder"
    
    return clean, full_timestamp, 5, "minute"


# ================================================================
# CLASSIFICATION SYSTEM
# ================================================================

PREFIX_MAP = {
    "diary": "diary", "dairy": "diary",
    "task": "task", "todo": "task", "kaam": "task",
    "reminder": "reminder", "remind": "reminder", "alarm": "reminder",
    "yaad dilao": "reminder", "yaad": "reminder",
    "expense": "expense", "kharcha": "expense", "karcha": "expense", "kharch": "expense", "paisa": "expense",
    "habit": "habit", "aadat": "habit",
    "water": "water", "pani": "water", "paani": "water",
    "memory": "memory", "yaad rakhna": "memory", "remember": "memory",
    "bill": "bill", "payment": "bill",
    "calendar": "calendar", "schedule": "calendar", "meeting": "calendar", "event": "calendar",
}

_ADD_WORDS = {"add", "kr", "karo", "kar", "likho", "likh", "save", "set", "lagao", "laga"}


def _try_prefix_match(text: str, chat_id: str = "") -> Optional[Tuple[str, Dict[str, Any]]]:
    """Check if transcript starts with a known category prefix."""
    lower = text.lower().strip()
    matched_category = None
    content_start = 0

    for prefix in sorted(PREFIX_MAP.keys(), key=len, reverse=True):
        if lower.startswith(prefix):
            matched_category = PREFIX_MAP[prefix]
            rest = lower[len(prefix):].strip()
            words = rest.split()
            if words and words[0] in _ADD_WORDS:
                rest = " ".join(words[1:]).strip()
            content = rest or text
            content_start = len(text) - len(content)
            break

    if not matched_category:
        return None

    original_content = text[content_start:].strip() if content_start < len(text) else text
    log.info(f"🎯 PREFIX matched: '{matched_category}' | content: '{original_content[:60]}'")
    return _build_params(matched_category, original_content, chat_id)


def _build_params(category: str, content: str, chat_id: str) -> Tuple[str, Dict[str, Any]]:
    """Convert category + raw content string into (category, params dict)."""
    lower = content.lower().strip()

    if category == "expense":
        amount_m = re.search(r'(\d+(?:\.\d+)?)', lower)
        if amount_m:
            amount = float(amount_m.group(1))
            desc = re.sub(r'\d+(?:\.\d+)?', '', content).strip()
            for nw in ["rs", "rupees", "rupaye", "kharcha", "karcha", "kharch",
                       "add", "karo", "kr", "kiya", "tha", "hua", "diye", "laga", "spent"]:
                desc = re.sub(r'\b' + re.escape(nw) + r'\b', ' ', desc, flags=re.IGNORECASE)
            desc = " ".join(desc.split()).strip() or "Expense"
            return "expense", {"amount": amount, "description": desc[:100]}
        return "diary", {"text": f"[Expense note — no amount] {content[:500]}"}

    elif category == "reminder":
        content_clean = content
        content_clean = content_clean.replace('laga0', '')
        content_clean = content_clean.replace('laga 0', '')
        content_clean = content_clean.replace('lagao', '')
        content_clean = re.sub(r'\breminder\b', '', content_clean, flags=re.IGNORECASE)
        
        log.info(f"📝 Reminder raw content: '{content_clean}'")
        
        clean, full_timestamp, t_val, t_unit = _parse_reminder_full_timestamp(content_clean)
        
        clean = clean.strip()
        if not clean or len(clean) < 2:
            clean = "Reminder"
        
        log.info(f"⏰ Reminder result: '{clean}' at {full_timestamp} ({t_val} {t_unit})")
        
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
            for nw in ["bill", "payment", "add", "karo", "kr", "rs"]:
                desc = re.sub(r'\b' + re.escape(nw) + r'\b', ' ', desc, flags=re.IGNORECASE)
            desc = " ".join(desc.split()).strip() or "Bill"
            return "bill", {"amount": amount, "description": desc[:100]}
        return "diary", {"text": f"[Bill note — no amount] {content[:500]}"}

    elif category == "calendar":
        date_match = re.search(
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|'
            r'today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
            lower, re.IGNORECASE
        )
        time_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm))', lower, re.IGNORECASE)
        event_date = date_match.group(1) if date_match else ""
        event_time = time_match.group(1) if time_match else ""
        clean = content
        for nw in ["calendar", "meeting", "appointment", "event", "schedule",
                   "add", "karo", "kr", "mein", "me", "hai"]:
            clean = re.sub(r'\b' + re.escape(nw) + r'\b', ' ', clean, flags=re.IGNORECASE)
        if date_match:
            clean = clean.replace(date_match.group(1), '')
        if time_match:
            clean = clean.replace(time_match.group(1), '')
        clean = " ".join(clean.split()).strip() or content
        return "calendar", {
            "text": clean[:200],
            "event_date": event_date,
            "event_time": event_time,
        }

    else:
        return "diary", {"text": content[:500]}


def _classify_transcript(text: str, chat_id: str = "") -> Tuple[str, Dict[str, Any]]:
    """Main classifier with prefix and keyword fallback."""
    
    # Step 1: Try prefix match
    prefix_result = _try_prefix_match(text, chat_id)
    if prefix_result:
        return prefix_result

    # Step 2: Keyword scoring
    lower = text.lower().strip()
    scores = {
        "expense": 0, "reminder": 0, "task": 0, "habit": 0,
        "water": 0, "memory": 0, "bill": 0, "calendar": 0,
    }

    if any(kw in lower for kw in ["kharcha", "karcha", "kharch", "expense", "spent"]):
        scores["expense"] += 5
    if re.search(r'\brs\b|\brupees\b|\brupaye\b|\bpaisa\b|\bpaise\b', lower):
        scores["expense"] += 3
    if re.search(r'\d+', lower):
        scores["expense"] += 1

    if any(kw in lower for kw in ["reminder", "remind", "alarm"]):
        scores["reminder"] += 5
    if any(kw in lower for kw in ["yaad dilao", "yaad dila", "bata dena"]):
        scores["reminder"] += 4
    if any(kw in lower for kw in ["baad", "minute", "ghante", "hour", "mein", "main"]):
        scores["reminder"] += 3

    if any(kw in lower for kw in ["task", "todo", "karna hai", "krna hai"]):
        scores["task"] += 5

    if any(kw in lower for kw in ["habit", "aadat", "roz", "daily"]):
        scores["habit"] += 5

    if any(kw in lower for kw in ["water", "pani", "paani"]):
        scores["water"] += 5

    if any(kw in lower for kw in ["memory", "remember", "yaad rakhna"]):
        scores["memory"] += 5

    if any(kw in lower for kw in ["bill", "subscription"]):
        scores["bill"] += 5

    if any(kw in lower for kw in ["calendar", "meeting", "appointment", "schedule"]):
        scores["calendar"] += 5

    best_cat = max(scores, key=lambda k: scores[k])
    if scores[best_cat] >= 3:
        log.info(f"🔍 KEYWORD matched: '{best_cat}' (score={scores[best_cat]})")
        return _build_params(best_cat, text, chat_id)

    log.info(f"📖 DIARY default | text: '{text[:60]}'")
    return "diary", {"text": text[:500]}


# ================================================================
# MAIN VOICE MESSAGE HANDLER
# ================================================================

async def handle_voice_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _SDM_AVAILABLE:
        await update.message.reply_text("❌ Voice feature unavailable - SDM not loaded")
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    duration = getattr(voice, "duration", 0) or 0
    user_name = update.effective_user.first_name or "User"
    chat_id = str(update.effective_chat.id)

    status_msg = await update.message.reply_text(
        f"🎙️ *Voice note mila!* ({duration}s)\n\n⏳ Download ho raha hai...",
        parse_mode="Markdown"
    )

    try:
        file_obj = await ctx.bot.get_file(voice.file_id)
        audio_bytes = bytes(await file_obj.download_as_bytearray())
        log.info(f"Downloaded: {len(audio_bytes)} bytes")
    except Exception as e:
        await status_msg.edit_text(f"❌ *Download fail!*\n\n`{str(e)[:150]}`", parse_mode="Markdown")
        return

    await status_msg.edit_text(
        f"🎙️ *Voice note* ({duration}s, {len(audio_bytes)//1024}KB)\n\n"
        f"🤖 Transcribe kar raha hai...\n(Pehle Vosk offline, phir Gemini)",
        parse_mode="Markdown"
    )

    transcript, error, source = await transcribe_audio(audio_bytes)

    if not transcript:
        vosk_status = "✅" if offline_recognizer.available else "❌"
        await status_msg.edit_text(
            f"❌ *Transcription fail!*\n\n"
            f"*Error:*\n`{error}`\n\n"
            f"*Debug:*\n"
            f"• Gemini API: `{'SET ✅' if GEMINI_API_KEY else 'MISSING ❌'}`\n"
            f"• Offline Vosk: `{vosk_status}`\n"
            f"• Audio: `{len(audio_bytes)} bytes` | Duration: `{duration}s`",
            parse_mode="Markdown"
        )
        if voice_store:
            voice_store.add(f"[FAIL: {str(error)[:60]}]", "none", "failed", duration, "Failed")
        return

    log.info(f"📝 RAW TRANSCRIPT: '{transcript}'")
    log.info(f"📝 SOURCE: {source}")

    transcript = transcript.replace('laga0', '')
    transcript = transcript.replace('laga 0', '')
    transcript = transcript.replace('lagao', '')
    transcript = re.sub(r'\b(\d+)\s*baad\b', r'\1 minute baad', transcript)
    transcript = re.sub(r'\s+', ' ', transcript).strip()

    category, data = _classify_transcript(transcript, chat_id)

    saved_to = "diary"
    extra_info = ""
    emoji_map = {
        "expense": "💸", "reminder": "⏰", "habit": "🔥", "water": "💧",
        "task": "✅", "memory": "🧠", "bill": "🧾", "calendar": "📅", "diary": "📖"
    }
    emoji = emoji_map.get(category, "📝")
    source_emoji = "📴" if source == "offline" else "🌐"
    source_text = "Vosk (Offline)" if source == "offline" else "Gemini (Online)"

    if category == "expense":
        expenses.add(data["amount"], data["description"])
        saved_to = "expenses"
        extra_info = f"💸 Rs.{data['amount']} add kar diya!\n📝 *{data['description'][:50]}*"

    elif category == "reminder" and reminders:
        due_timestamp = data.get("due_timestamp", "")
        rem_text = data.get("text", "Reminder")
        r_chat_id = int(data.get("chat_id") or chat_id)
        
        r = reminders.add(
            chat_id=r_chat_id,
            text=rem_text,
            due_timestamp=due_timestamp,
            repeat="once"
        )
        saved_to = f"reminder #{r['id']}"
        t_val = data.get('time_value', 0)
        t_unit = data.get('time_unit', '')
        time_info = f" — {t_val} {t_unit}" if t_val else ""
        
        try:
            dt = datetime.strptime(due_timestamp, "%Y-%m-%d %H:%M:%S")
            display_time = dt.strftime("%I:%M %p, %d %b")
        except:
            display_time = due_timestamp
        
        extra_info = f"⏰ Reminder #{r['id']} set!{time_info}\n📌 *{rem_text[:60]}*\n🕐 Will trigger at: *{display_time}*"

    elif category == "task":
        t = tasks.add(data["text"])
        saved_to = f"task #{t['id']}"
        extra_info = f"✅ Task #{t['id']} add!\n📌 *{data['text'][:60]}*"

    elif category == "habit":
        h = habits.add(data["text"])
        saved_to = f"habit #{h['id']}"
        extra_info = f"🔥 Habit #{h['id']} add!\n📌 *{data['text'][:60]}*"

    elif category == "water" and water:
        unit = data.get("unit", "glass")
        amount = data.get("amount", 1.0)
        unit_ml = {
            "glass": 250, "bottle": 500,
            "liter": 1000, "litre": 1000, "ltr": 1000, "ml": 1
        }.get(unit.lower(), 250)
        ml = int(amount * unit_ml)
        total = water.add(ml)
        goal_ml = water.goal()
        saved_to = "water"
        extra_info = f"💧 {amount} {unit} ({ml}ml) logged!\n🚰 Total today: {total}ml / {goal_ml}ml"

    elif category == "memory":
        memory.add(data["text"])
        saved_to = "memory"
        extra_info = f"🧠 Memory save!\n📝 *{data['text'][:60]}*"

    elif category == "bill":
        b = bills.add(data["description"], data["amount"], due_day=0)
        saved_to = f"bill #{b['id']}"
        extra_info = f"🧾 Bill Rs.{data['amount']} add!\n📝 *{data['description'][:50]}*"

    elif category == "calendar" and calendar:
        e = calendar.add(
            data["text"],
            data.get("event_date") or today_str(),
            data.get("event_time", "")
        )
        saved_to = f"calendar #{e['id']}"
        extra_info = f"📅 Event #{e['id']} added!\n📌 *{data['text'][:50]}*"
        if data.get("event_date"):
            extra_info += f"\n📅 {data['event_date']}"
        if data.get("event_time"):
            extra_info += f" ⏰ {data['event_time']}"

    else:
        diary.add(f"[Voice] {data['text']}")
        saved_to = "diary"
        extra_info = "📖 Diary mein save kar diya!"

    if voice_store:
        voice_store.add(transcript, saved_to, category, duration, "Success")

    try:
        if sheets_backup and hasattr(sheets_backup, 'log_event'):
            sheets_backup.log_event("voice_note", user_name, f"[{category}] {transcript[:80]}")
    except Exception as e:
        log.debug(f"Misc log error (non-critical): {e}")

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
            "🎙️ *Abhi koi voice note nahi hai*\n\n"
            "Voice message bhejo — main transcribe kar dunga!\n\n"
            "*Available categories:*\n"
            "💸 `kharcha 500 chai pe`\n"
            "⏰ `reminder 5 minute baad pani peena`\n"
            "✅ `task add report submit karna hai`\n"
            "🔥 `habit add subah uthna`\n"
            "💧 `water 2 glass`\n"
            "🧠 `memory passport number 1234`\n"
            "🧾 `bill 1000 bijli ka`\n"
            "📅 `calendar monday 3pm meeting`\n"
            "📖 `diary aaj acha din tha`",
            parse_mode="Markdown"
        )
        return

    emoji_map = {
        "expense": "💸", "reminder": "⏰", "habit": "🔥", "water": "💧",
        "task": "✅", "memory": "🧠", "bill": "🧾", "calendar": "📅", "diary": "📖"
    }
    lines = []
    for v in reversed(recent):
        category = v.get("category", "diary")
        emoji = emoji_map.get(category, "📝")
        status_emoji = "✅" if v.get("status") == "Success" else "❌"
        lines.append(
            f"{status_emoji} {emoji} *#{v['id']}* {v['date']} {v['time']}\n"
            f"   💾 *{v['saved_to']}* | ⏱ {v.get('duration', 0)}s | 🏷 {category}\n"
            f"   📝 _{v['transcript'][:100]}_"
        )

    await update.message.reply_text(
        "🎙️ *Recent Voice Notes:*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown"
    )


async def cmd_voicehelp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎙️ *Voice Note Guide — v9 (Time Parsing Fixed!)*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*🎯 Examples:*\n\n"
        "💸 `kharcha 500 chai pe`\n"
        "⏰ `reminder 2 minute baad pani peena`\n"
        "⏰ `reminder do minute baad pani` (Hindi numbers)\n"
        "✅ `task report submit karna hai`\n"
        "💧 `water 2 glass`\n"
        "📖 `diary aaj acha din tha`\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📴 Vosk (Offline) → 🌐 Gemini (Online fallback)\n\n"
        "/voicenotes — Recent notes dekho",
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
            has_book = getattr(sheets_backup, '_book', None) is not None
            lines.append(f"{'✅' if connected else '❌'} connected: `{connected}`")
            lines.append(f"{'✅' if has_book else '❌'} _book present: `{has_book}`")

            if has_book:
                try:
                    titles = [ws.title for ws in sheets_backup._book.worksheets()]
                    lines.append(f"📋 Sheets: `{', '.join(titles)}`")
                except Exception as e:
                    lines.append(f"❌ Could not list sheets: `{e}`")

        if voice_store:
            lines.append("✅ voice_store initialized")
            lines.append(f"📝 Total voice notes: `{len(voice_store.store.data.get('list', []))}`")
        else:
            lines.append("❌ voice_store is None")

    except Exception as e:
        lines.append(f"❌ Debug error: `{e}`")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ================================================================
# REGISTER HANDLERS
# ================================================================

def register_voice_handlers(app):
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(CommandHandler("voicenotes", cmd_voicenotes))
    app.add_handler(CommandHandler("voicehelp", cmd_voicehelp))
    app.add_handler(CommandHandler("sheetsdbg", cmd_sheets_debug))

    gemini_status = "✅" if GEMINI_API_KEY else "❌"
    vosk_status = "✅" if offline_recognizer.available else "❌"
    sheets_status = "✅" if _SDM_AVAILABLE and sheets_backup and getattr(sheets_backup, 'connected', False) else "❌"

    log.info("═" * 50)
    log.info("✅ Voice handlers registered (v9 - Time Parsing Fixed!)")
    log.info(f"   📴 Vosk Offline : {vosk_status} (Priority)")
    log.info(f"   🌐 Gemini API   : {gemini_status} (Fallback)")
    log.info(f"   📊 Google Sheets: {sheets_status}")
    log.info("═" * 50)
