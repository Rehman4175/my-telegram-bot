#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — Rk Bot
FIXED v5:
  - PREFIX SYSTEM: "diary add ...", "task add ...", "reminder add ..." → strict routing
  - Fallback: keyword-based classification (improved)
  - Reminder: chat_id properly stored → alarm triggers correctly
  - Google Sheets: connection verified + retry + detailed logs
  - Expense: won't go to diary anymore
  - All categories: expense, reminder, task, habit, water, memory, bill, calendar, diary
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
        now_ist, today_str, now_str, PrivateStore
    )
    _SDM_AVAILABLE = True
    log.info("✅ secure_data_manager loaded in voice handler")
except ImportError as e:
    log.error(f"secure_data_manager import failed: {e}")
    _SDM_AVAILABLE = False

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
    HEADERS  = ["ID", "Date", "Time", "Transcript", "Saved To", "Duration", "Status", "Category"]

    def __init__(self):
        if not _SDM_AVAILABLE:
            return
        self.store = PrivateStore("voice_notes", {"list": [], "counter": 0})
        self._ensure_sheet_tab()

    def _ensure_sheet_tab(self):
        """Ensure Voice Notes tab exists in Google Sheets — with detailed logging."""
        try:
            if not sheets_backup:
                log.warning("⚠️ sheets_backup is None — Google Sheets not initialized")
                return

            # Try to connect if not already connected
            if not getattr(sheets_backup, 'connected', False):
                log.warning("⚠️ sheets_backup not connected — attempting reconnect...")
                try:
                    sheets_backup.connect()
                    log.info("✅ sheets_backup reconnected")
                except Exception as ce:
                    log.error(f"❌ sheets_backup reconnect failed: {ce}")
                    return

            if not getattr(sheets_backup, '_book', None):
                log.warning("⚠️ sheets_backup._book is None after connect")
                return

            existing = [ws.title for ws in sheets_backup._book.worksheets()]
            log.info(f"📊 Existing sheets: {existing}")

            if self.TAB_NAME not in existing:
                ws = sheets_backup._book.add_worksheet(
                    title=self.TAB_NAME, rows=2000, cols=len(self.HEADERS)
                )
                ws.append_row(self.HEADERS, value_input_option="USER_ENTERED")
                sheets_backup._ws_cache[self.TAB_NAME] = ws
                log.info(f"✅ Created '{self.TAB_NAME}' tab in Google Sheets")
            else:
                if self.TAB_NAME not in sheets_backup._ws_cache:
                    ws = sheets_backup._book.worksheet(self.TAB_NAME)
                    sheets_backup._ws_cache[self.TAB_NAME] = ws
                log.info(f"✅ '{self.TAB_NAME}' tab already exists and cached")

        except Exception as e:
            log.error(f"❌ VoiceNotes tab error: {e}", exc_info=True)

    def _append_to_sheet(self, row):
        """Append row to Google Sheets with retry and detailed error logging."""
        for attempt in range(3):
            try:
                if not sheets_backup:
                    log.warning("⚠️ sheets_backup None — cannot append")
                    return

                if not getattr(sheets_backup, 'connected', False):
                    log.warning("⚠️ Sheets not connected — trying reconnect before append")
                    sheets_backup.connect()

                ws = sheets_backup._ws_cache.get(self.TAB_NAME)
                if not ws:
                    self._ensure_sheet_tab()
                    ws = sheets_backup._ws_cache.get(self.TAB_NAME)

                if not ws:
                    log.error("❌ Could not get Voice Notes worksheet")
                    return

                ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
                log.info(f"✅ Appended to Google Sheets row: {row[:4]}")
                return

            except Exception as e:
                log.error(f"❌ Sheet append attempt {attempt+1}/3 failed: {e}")
                if attempt < 2:
                    time.sleep(2)

    def add(self, transcript: str, saved_to: str = "diary", category: str = "diary",
            duration: int = 0, status: str = "Success"):
        if not _SDM_AVAILABLE:
            return None
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        vid   = self.store.data["counter"]
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
    MODEL_URL  = "https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip"

    def __init__(self):
        self.model     = None
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
                self.model     = Model(model_path)
                self.available = True
                log.info(f"✅ Vosk model loaded from {model_path}")
            except Exception as e:
                log.error(f"Vosk model load failed: {e}")
        else:
            log.warning("⚠️ Vosk unavailable — only Gemini will be used")

    def _download_model(self) -> Optional[str]:
        zip_path  = os.path.join(os.getcwd(), f"{self.MODEL_NAME}.zip")
        dest_path = os.path.join(os.getcwd(), self.MODEL_NAME)

        if os.path.exists(dest_path) and os.path.isdir(dest_path):
            return dest_path

        try:
            log.info(f"📥 Downloading Vosk model from: {self.MODEL_URL}")
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

            rec        = KaldiRecognizer(self.model, 16000)
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
            else:
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
# GEMINI TRANSCRIPTION
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
    result     = None

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                GEMINI_URL.format(key=GEMINI_API_KEY),
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            break

        except urllib.error.HTTPError as e:
            try:
                body       = e.read().decode("utf-8", errors="ignore")
                err_json   = json.loads(body)
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
        block    = feedback.get("blockReason", "")
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
# TRANSCRIPTION WITH FALLBACK
# ================================================================

async def transcribe_audio(audio_bytes: bytes) -> Tuple[Optional[str], Optional[str], str]:
    """Returns: (text, error, source)  source = 'gemini' | 'offline' | None"""

    if GEMINI_API_KEY:
        transcript, error = await transcribe_audio_gemini(audio_bytes)
        if transcript:
            return transcript, None, "gemini"
        log.warning(f"Gemini failed: {error}")

    if offline_recognizer.available:
        log.info("Falling back to offline Vosk...")
        transcript, error = await offline_recognizer.transcribe(audio_bytes)
        if transcript:
            return transcript, None, "offline"
        return None, error or "Both methods failed", None

    return None, "No transcription method available (Gemini API missing)", None


# ================================================================
# ✅ CLASSIFICATION SYSTEM — v5
#
# STEP 1: PREFIX DETECTION (highest priority)
#   "diary add ...", "task add ...", "reminder add ...", etc.
#   → Jo bhi prefix ke baad bolo, wahi content save hoga
#
# STEP 2: KEYWORD FALLBACK (agar prefix nahi mila)
#   → Broad keyword matching with confidence scoring
# ================================================================

# --- All valid prefixes mapped to categories ---
PREFIX_MAP = {
    # Diary
    "diary":        "diary",
    "dairy":        "diary",   # common typo/mispronunciation
    # Task
    "task":         "task",
    "todo":         "task",
    "kaam":         "task",
    # Reminder
    "reminder":     "reminder",
    "remind":       "reminder",
    "alarm":        "reminder",
    "yaad dilao":   "reminder",
    "yaad":         "reminder",
    # Expense
    "expense":      "expense",
    "kharcha":      "expense",
    "karcha":       "expense",
    "kharch":       "expense",
    "paisa":        "expense",
    # Habit
    "habit":        "habit",
    "aadat":        "habit",
    # Water
    "water":        "water",
    "pani":         "water",
    "paani":        "water",
    # Memory
    "memory":       "memory",
    "yaad rakhna":  "memory",
    "remember":     "memory",
    # Bill
    "bill":         "bill",
    "payment":      "bill",
    # Calendar
    "calendar":     "calendar",
    "schedule":     "calendar",
    "meeting":      "calendar",
    "event":        "calendar",
}

# Word that separates category from content (optional)
_ADD_WORDS = {"add", "kr", "karo", "kar", "likho", "likh", "save", "set"}


def _try_prefix_match(text: str, chat_id: str = "") -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Check if transcript starts with a known category prefix.
    Returns (category, params) or None.

    Supports:
      "diary add aaj acha din tha"
      "task karo report submit"
      "reminder 5 minute baad pani peena"
      "kharcha 500 chai pe"   ← "kharcha" itself is prefix
    """
    lower   = text.lower().strip()
    matched_category = None
    content_start    = 0

    # Sort prefixes longest-first so "yaad rakhna" beats "yaad"
    for prefix in sorted(PREFIX_MAP.keys(), key=len, reverse=True):
        if lower.startswith(prefix):
            matched_category = PREFIX_MAP[prefix]
            rest = lower[len(prefix):].strip()
            # Skip optional "add / karo / ..." connector word
            words = rest.split()
            if words and words[0] in _ADD_WORDS:
                rest = " ".join(words[1:]).strip()
            content = rest or text  # fallback to full text if nothing left
            content_start = len(text) - len(content)
            break

    if not matched_category:
        return None

    # Build original-case content (preserve user's words)
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
            desc   = re.sub(r'\d+(?:\.\d+)?', '', content).strip()
            # Remove noise words
            for nw in ["rs", "rupees", "rupaye", "kharcha", "karcha", "kharch",
                       "add", "karo", "kr", "kiya", "tha", "hua", "diye", "laga", "spent"]:
                desc = re.sub(r'\b' + re.escape(nw) + r'\b', ' ', desc, flags=re.IGNORECASE)
            desc = " ".join(desc.split()).strip() or "Expense"
            return "expense", {"amount": amount, "description": desc[:100]}
        else:
            # No amount found — save to diary with note
            return "diary", {"text": f"[Expense note — no amount] {content[:500]}"}

    elif category == "reminder":
        clean, due_time, t_val, t_unit = _parse_reminder_duration(lower)
        clean = " ".join(clean.split()).strip() or content
        return "reminder", {
            "text": clean[:200],
            "due_time": due_time,
            "time_value": t_val,
            "time_unit": t_unit,
            "chat_id": chat_id,   # ← critical for alarm trigger
        }

    elif category == "task":
        return "task", {"text": content[:200]}

    elif category == "habit":
        return "habit", {"text": content[:150]}

    elif category == "water":
        amount_m = re.search(r'(\d+(?:\.\d+)?)', lower)
        unit_m   = re.search(r'(glass|bottle|liter|litre|ltr|ml)', lower, re.IGNORECASE)
        amount   = float(amount_m.group(1)) if amount_m else 1.0
        unit     = unit_m.group(1).lower() if unit_m else "glass"
        return "water", {"amount": amount, "unit": unit}

    elif category == "memory":
        return "memory", {"text": content[:200]}

    elif category == "bill":
        amount_m = re.search(r'(\d+(?:\.\d+)?)', lower)
        if amount_m:
            amount = float(amount_m.group(1))
            desc   = re.sub(r'\d+(?:\.\d+)?', '', content).strip()
            for nw in ["bill", "payment", "add", "karo", "kr", "rs"]:
                desc = re.sub(r'\b' + re.escape(nw) + r'\b', ' ', desc, flags=re.IGNORECASE)
            desc = " ".join(desc.split()).strip() or "Bill"
            return "bill", {"amount": amount, "description": desc[:100]}
        else:
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

    else:  # diary
        return "diary", {"text": content[:500]}


def _parse_reminder_duration(text: str) -> Tuple[str, str, int, str]:
    """Extract time duration. Returns (clean_text, due_time_HH:MM, value, unit)"""
    patterns = [
        (r'(\d+)\s*(minute|min|mins|m)\b',   'minute'),
        (r'(\d+)\s*(second|sec|secs)\b',      'second'),
        (r'(\d+)\s*(hour|hr|hours|ghanta)\b', 'hour'),
        (r'(\d+)\s*(day|days|din)\b',         'day'),
    ]
    for pattern, unit in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            now   = datetime.now()
            if unit == 'minute':
                due = now + timedelta(minutes=value)
            elif unit == 'second':
                due = now + timedelta(seconds=value)
            elif unit == 'hour':
                due = now + timedelta(hours=value)
            else:
                due = now + timedelta(days=value)
            due_str = due.strftime("%H:%M")
            clean   = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
            return clean, due_str, value, unit
    return text, "", 0, ""


def _classify_transcript(text: str, chat_id: str = "") -> Tuple[str, Dict[str, Any]]:
    """
    Main classifier:
    1. Try PREFIX match first
    2. Fall back to keyword scoring
    3. Default to diary
    """

    # ── STEP 1: Prefix detection ──────────────────────────────
    prefix_result = _try_prefix_match(text, chat_id)
    if prefix_result:
        return prefix_result

    # ── STEP 2: Keyword scoring fallback ─────────────────────
    lower = text.lower().strip()

    scores: Dict[str, int] = {
        "expense": 0, "reminder": 0, "task": 0, "habit": 0,
        "water": 0,   "memory": 0,   "bill": 0, "calendar": 0,
    }

    # Expense signals
    if any(kw in lower for kw in ["kharcha", "karcha", "kharch", "expense", "spent"]):
        scores["expense"] += 5
    if re.search(r'\brs\b|\brupees\b|\brupaye\b|\bpaisa\b|\bpaise\b', lower):
        scores["expense"] += 3
    if any(kw in lower for kw in ["laga", "diya", "kharche"]):
        scores["expense"] += 2
    if re.search(r'\d+', lower):
        scores["expense"] += 1

    # Reminder signals
    if any(kw in lower for kw in ["reminder", "remind", "alarm"]):
        scores["reminder"] += 5
    if any(kw in lower for kw in ["yaad dilao", "yaad dila", "bata dena"]):
        scores["reminder"] += 4
    if any(kw in lower for kw in ["baad", "minute", "ghante", "hour"]):
        scores["reminder"] += 2

    # Task signals
    if any(kw in lower for kw in ["task", "todo", "karna hai", "krna hai"]):
        scores["task"] += 5
    if any(kw in lower for kw in ["complete", "finish", "submit"]):
        scores["task"] += 2

    # Habit signals
    if any(kw in lower for kw in ["habit", "aadat", "roz", "daily"]):
        scores["habit"] += 5

    # Water signals
    if any(kw in lower for kw in ["water", "pani", "paani"]):
        scores["water"] += 5
    if any(kw in lower for kw in ["glass", "bottle", "piya", "peena"]):
        scores["water"] += 2

    # Memory signals
    if any(kw in lower for kw in ["memory", "remember", "yaad rakhna", "note karo"]):
        scores["memory"] += 5

    # Bill signals
    if any(kw in lower for kw in ["bill", "subscription"]):
        scores["bill"] += 5
    if any(kw in lower for kw in ["bijli", "internet", "mobile", "recharge"]):
        scores["bill"] += 3

    # Calendar signals
    if any(kw in lower for kw in ["calendar", "meeting", "appointment", "schedule"]):
        scores["calendar"] += 5
    if any(kw in lower for kw in ["monday", "tuesday", "wednesday", "thursday",
                                   "friday", "saturday", "sunday", "tomorrow", "kal"]):
        scores["calendar"] += 2

    # Pick highest score (minimum threshold = 3)
    best_cat = max(scores, key=lambda k: scores[k])
    if scores[best_cat] >= 3:
        log.info(f"🔍 KEYWORD matched: '{best_cat}' (score={scores[best_cat]}) | text: '{text[:60]}'")
        return _build_params(best_cat, text, chat_id)

    # ── STEP 3: Default → diary ───────────────────────────────
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

    duration  = getattr(voice, "duration", 0) or 0
    user_name = update.effective_user.first_name or "User"
    chat_id   = str(update.effective_chat.id)

    status_msg = await update.message.reply_text(
        f"🎙️ *Voice note mila!* ({duration}s)\n\n⏳ Download ho raha hai...",
        parse_mode="Markdown"
    )

    # Download audio
    try:
        file_obj    = await ctx.bot.get_file(voice.file_id)
        audio_bytes = bytes(await file_obj.download_as_bytearray())
        log.info(f"Downloaded: {len(audio_bytes)} bytes")
    except Exception as e:
        await status_msg.edit_text(f"❌ *Download fail!*\n\n`{str(e)[:150]}`", parse_mode="Markdown")
        return

    # Transcribe
    await status_msg.edit_text(
        f"🎙️ *Voice note* ({duration}s, {len(audio_bytes)//1024}KB)\n\n"
        f"🤖 Transcribe kar raha hai...\n(Pehle Gemini, phir offline)",
        parse_mode="Markdown"
    )

    transcript, error, source = await transcribe_audio(audio_bytes)

    # Transcription failed
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

    # Classify + save
    category, data = _classify_transcript(transcript, chat_id)

    saved_to   = "diary"
    extra_info = ""
    emoji_map  = {
        "expense": "💸", "reminder": "⏰", "habit": "🔥", "water": "💧",
        "task": "✅", "memory": "🧠", "bill": "🧾", "calendar": "📅", "diary": "📖"
    }
    emoji        = emoji_map.get(category, "📝")
    source_emoji = "🌐" if source == "gemini" else "📴"
    source_text  = "Gemini (Online)" if source == "gemini" else "Vosk (Offline)"

    # ── EXPENSE ──────────────────────────────────────────────
    if category == "expense":
        expenses.add(data["amount"], data["description"])
        saved_to   = "expenses"
        extra_info = f"💸 Rs.{data['amount']} add kar diya!\n📝 *{data['description'][:50]}*"

    # ── REMINDER ─────────────────────────────────────────────
    elif category == "reminder" and reminders:
        due_time = data.get("due_time", "")
        rem_text = data.get("text", "Reminder")
        # chat_id MUST be passed so alarm triggers in correct chat
        r_chat_id = data.get("chat_id") or chat_id
        r        = reminders.add(r_chat_id, rem_text, due_time, repeat="once")
        saved_to = f"reminder #{r['id']}"
        t_val    = data.get('time_value', 0)
        t_unit   = data.get('time_unit', '')
        time_info = f" — {t_val} {t_unit}" if t_val else (f" — at {due_time}" if due_time else "")
        extra_info = f"⏰ Reminder #{r['id']} set!{time_info}\n📌 *{rem_text[:60]}*"

    # ── TASK ─────────────────────────────────────────────────
    elif category == "task":
        t          = tasks.add(data["text"])
        saved_to   = f"task #{t['id']}"
        extra_info = f"✅ Task #{t['id']} add!\n📌 *{data['text'][:60]}*"

    # ── HABIT ────────────────────────────────────────────────
    elif category == "habit":
        h          = habits.add(data["text"])
        saved_to   = f"habit #{h['id']}"
        extra_info = f"🔥 Habit #{h['id']} add!\n📌 *{data['text'][:60]}*"

    # ── WATER ────────────────────────────────────────────────
    elif category == "water" and water:
        unit      = data.get("unit", "glass")
        amount    = data.get("amount", 1.0)
        unit_ml   = {
            "glass": 250, "bottle": 500,
            "liter": 1000, "litre": 1000, "ltr": 1000, "ml": 1
        }.get(unit.lower(), 250)
        ml        = int(amount * unit_ml)
        total     = water.add(ml)
        goal_ml   = water.goal()
        saved_to  = "water"
        extra_info = f"💧 {amount} {unit} ({ml}ml) logged!\n🚰 Total today: {total}ml / {goal_ml}ml"

    # ── MEMORY ───────────────────────────────────────────────
    elif category == "memory":
        memory.add(data["text"])
        saved_to   = "memory"
        extra_info = f"🧠 Memory save!\n📝 *{data['text'][:60]}*"

    # ── BILL ─────────────────────────────────────────────────
    elif category == "bill":
        b          = bills.add(data["description"], data["amount"], due_day=0)
        saved_to   = f"bill #{b['id']}"
        extra_info = f"🧾 Bill Rs.{data['amount']} add!\n📝 *{data['description'][:50]}*"

    # ── CALENDAR ─────────────────────────────────────────────
    elif category == "calendar" and calendar:
        e         = calendar.add(
            data["text"],
            data.get("event_date") or today_str(),
            data.get("event_time", "")
        )
        saved_to  = f"calendar #{e['id']}"
        extra_info = f"📅 Event #{e['id']} added!\n📌 *{data['text'][:50]}*"
        if data.get("event_date"):
            extra_info += f"\n📅 {data['event_date']}"
        if data.get("event_time"):
            extra_info += f" ⏰ {data['event_time']}"

    # ── DIARY ────────────────────────────────────────────────
    else:
        diary.add(f"[Voice] {data['text']}")
        saved_to   = "diary"
        extra_info = "📖 Diary mein save kar diya!"

    # Log to voice notes sheet
    if voice_store:
        voice_store.add(transcript, saved_to, category, duration, "Success")

    # Log to misc sheet
    try:
        if sheets_backup and hasattr(sheets_backup, 'log_event'):
            sheets_backup.log_event("voice_note", user_name, f"[{category}] {transcript[:80]}")
    except Exception as e:
        log.debug(f"Misc log error (non-critical): {e}")

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
        category     = v.get("category", "diary")
        emoji        = emoji_map.get(category, "📝")
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
        "🎙️ *Voice Note Guide — v5*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*🎯 PREFIX SYSTEM (Sabse reliable!)*\n"
        "Pehle category bolo, phir 'add', phir content:\n\n"
        "💸 `kharcha add 500 chai pe`\n"
        "⏰ `reminder add 5 minute baad pani peena`\n"
        "✅ `task add report submit karna hai`\n"
        "🔥 `habit add subah 5 baje uthna`\n"
        "💧 `water add 2 glass piya`\n"
        "🧠 `memory add passport number 1234`\n"
        "🧾 `bill add 1000 bijli ka`\n"
        "📅 `calendar add monday 3pm meeting`\n"
        "📖 `diary add aaj bahut acha din tha`\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*⚡ Short forms bhi kaam karte hain:*\n"
        "`kharcha 500 chai pe` → expense\n"
        "`pani 2 glass` → water\n"
        "`yaad dilao 10 min baad meeting` → reminder\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 Gemini (Online) → 📴 Vosk (Offline fallback)\n\n"
        "/voicenotes — Recent notes dekho",
        parse_mode="Markdown"
    )


async def cmd_sheets_debug(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Debug command to check Google Sheets connection status."""
    lines = ["📊 *Google Sheets Debug:*\n"]

    try:
        if not _SDM_AVAILABLE:
            lines.append("❌ secure_data_manager not loaded")
        else:
            lines.append("✅ secure_data_manager loaded")

        if not sheets_backup:
            lines.append("❌ sheets_backup is None")
        else:
            connected  = getattr(sheets_backup, 'connected', 'unknown')
            has_book   = getattr(sheets_backup, '_book', None) is not None
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
    app.add_handler(CommandHandler("voicenotes",   cmd_voicenotes))
    app.add_handler(CommandHandler("voicehelp",    cmd_voicehelp))
    app.add_handler(CommandHandler("sheetsdbg",    cmd_sheets_debug))   # ← new debug command

    gemini_status = "✅" if GEMINI_API_KEY else "❌"
    vosk_status   = "✅" if offline_recognizer.available else "❌"
    sheets_status = "✅" if _SDM_AVAILABLE and sheets_backup and getattr(sheets_backup, 'connected', False) else "❌"

    log.info("═" * 50)
    log.info("✅ Voice handlers registered (v5)")
    log.info(f"   🌐 Gemini API   : {gemini_status}")
    log.info(f"   📴 Vosk Offline : {vosk_status}")
    log.info(f"   📊 Google Sheets: {sheets_status}")
    log.info("═" * 50)
