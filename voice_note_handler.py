#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICE NOTE HANDLER — Rk Bot
WITH OFFLINE VOSK SUPPORT (Fallback when Gemini busy)
FIXED: Auto-download Vosk model if not found
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

try:
    from secure_data_manager import (
        diary, tasks, memory, expenses, sheets_backup, repo_manager,
        now_ist, today_str, now_str, PrivateStore
    )
    _SDM_AVAILABLE = True
    log.info("✅ secure_data_manager loaded successfully")
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
# OFFLINE VOICE RECOGNITION (VOSK) - AUTO DOWNLOAD + FIXED PATH
# ================================================================

VOSK_AVAILABLE = False
try:
    from vosk import Model, KaldiRecognizer
    from pydub import AudioSegment
    VOSK_AVAILABLE = True
    log.info("✅ Vosk imported successfully")
except ImportError as e:
    log.warning(f"⚠️ Vosk not available: {e}")


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
            "/home/runner/work/my-telegram-bot/my-telegram-bot/vosk-model-small-hi-0.22",
            "/github/workspace/vosk-model-small-hi-0.22",
            "/opt/hostedtoolcache/vosk-model-small-hi-0.22",
        ]

        model_path = None
        for path in possible_paths:
            if path and os.path.exists(path) and os.path.isdir(path):
                model_path = path
                log.info(f"✅ Found Vosk model at: {path}")
                break

        # ── AUTO-DOWNLOAD if model not found anywhere ─────────────────
        if VOSK_AVAILABLE and not model_path:
            log.info("⬇️  Vosk model nahi mila — auto-download ho raha hai...")
            model_path = self._download_model()
        # ─────────────────────────────────────────────────────────────

        if VOSK_AVAILABLE and model_path:
            try:
                self.model     = Model(model_path)
                self.available = True
                log.info(f"✅ Offline Vosk model loaded successfully from {model_path}")
            except Exception as e:
                log.error(f"❌ Failed to load Vosk model: {e}")
        else:
            log.warning("⚠️ Vosk offline recognition unavailable — Gemini fallback use hoga")

    def _download_model(self) -> Optional[str]:
        """Download + unzip Vosk Hindi model. Returns extracted path or None."""
        zip_path  = os.path.join(os.getcwd(), f"{self.MODEL_NAME}.zip")
        dest_path = os.path.join(os.getcwd(), self.MODEL_NAME)

        # Already extracted? (race-condition guard)
        if os.path.exists(dest_path) and os.path.isdir(dest_path):
            log.info(f"✅ Model already extracted at: {dest_path}")
            return dest_path

        try:
            log.info(f"📥 Downloading Vosk model from: {self.MODEL_URL}")
            urllib.request.urlretrieve(self.MODEL_URL, zip_path)
            size_mb = os.path.getsize(zip_path) // 1024 // 1024
            log.info(f"✅ Download complete ({size_mb} MB) — extracting...")

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(os.getcwd())

            # Cleanup zip
            try:
                os.remove(zip_path)
            except Exception:
                pass

            if os.path.exists(dest_path) and os.path.isdir(dest_path):
                log.info(f"✅ Vosk model extracted to: {dest_path}")
                return dest_path
            else:
                log.error(f"❌ Extracted but folder not found: {dest_path}")
                return None

        except Exception as e:
            log.error(f"❌ Vosk model download/extract fail: {e}")
            # Cleanup partial zip
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except Exception:
                    pass
            return None

    async def transcribe(self, audio_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
        """Convert audio bytes to text using local Vosk model."""
        if not self.available:
            return None, "Offline model not available - using Gemini only"

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
                    except Exception:
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
                    except Exception:
                        pass
            return None, str(e)


# Initialize offline transcriber (auto-downloads model if missing)
offline_recognizer = OfflineTranscriber()


# ================================================================
# ENHANCED STORES (Reminders, Habits, Water, Bills, Calendar)
# ================================================================

class ReminderStore:
    TAB_NAME = "Reminders"
    HEADERS  = ["ID", "Created Date", "Created Time", "Text", "Due Time", "Status", "Completed At"]

    def __init__(self):
        if not _SDM_AVAILABLE:
            return
        self.store = PrivateStore("reminders", {"list": [], "counter": 0})
        self._ensure_sheet_tab()

    def _ensure_sheet_tab(self):
        try:
            if not sheets_backup or not sheets_backup._book:
                return
            existing = [ws.title for ws in sheets_backup._book.worksheets()]
            if self.TAB_NAME not in existing:
                ws = sheets_backup._book.add_worksheet(title=self.TAB_NAME, rows=2000, cols=len(self.HEADERS))
                ws.append_row(self.HEADERS, value_input_option="USER_ENTERED")
                sheets_backup._ws_cache[self.TAB_NAME] = ws
            else:
                if self.TAB_NAME not in sheets_backup._ws_cache:
                    ws = sheets_backup._book.worksheet(self.TAB_NAME)
                    sheets_backup._ws_cache[self.TAB_NAME] = ws
        except Exception as e:
            log.debug(f"Reminders tab error (non-critical): {e}")

    def _append_to_sheet(self, row):
        try:
            if not sheets_backup or not sheets_backup._book:
                return
            ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if not ws:
                self._ensure_sheet_tab()
                ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if ws:
                ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
        except Exception as e:
            log.debug(f"Sheet append error: {e}")

    def add(self, text: str, due_time: str = "") -> Dict[str, Any]:
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        rid   = self.store.data["counter"]
        entry = {
            "id": rid, "created_date": today_str(), "created_time": now_str(),
            "text": text, "due_time": due_time, "status": "pending", "completed_at": ""
        }
        self.store.data["list"].append(entry)
        self.store.data["list"] = self.store.data["list"][-500:]
        self.store.save()
        self._append_to_sheet([rid, today_str(), now_str(), text, due_time, "pending", ""])
        return entry

    def get_recent(self, n: int = 20):
        return self.store.data.get("list", [])[-n:]


class HabitStore:
    TAB_NAME = "Habits"
    HEADERS  = ["ID", "Created Date", "Habit Name", "Streak", "Last Done", "Status"]

    def __init__(self):
        if not _SDM_AVAILABLE:
            return
        self.store = PrivateStore("habits", {"list": [], "counter": 0})
        self._ensure_sheet_tab()

    def _ensure_sheet_tab(self):
        try:
            if not sheets_backup or not sheets_backup._book:
                return
            existing = [ws.title for ws in sheets_backup._book.worksheets()]
            if self.TAB_NAME not in existing:
                ws = sheets_backup._book.add_worksheet(title=self.TAB_NAME, rows=2000, cols=len(self.HEADERS))
                ws.append_row(self.HEADERS, value_input_option="USER_ENTERED")
                sheets_backup._ws_cache[self.TAB_NAME] = ws
            else:
                if self.TAB_NAME not in sheets_backup._ws_cache:
                    ws = sheets_backup._book.worksheet(self.TAB_NAME)
                    sheets_backup._ws_cache[self.TAB_NAME] = ws
        except Exception as e:
            log.debug(f"Habits tab error: {e}")

    def _append_to_sheet(self, row):
        try:
            if not sheets_backup or not sheets_backup._book:
                return
            ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if not ws:
                self._ensure_sheet_tab()
                ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if ws:
                ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
        except Exception as e:
            log.debug(f"Sheet append error: {e}")

    def add(self, name: str) -> Dict[str, Any]:
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        hid   = self.store.data["counter"]
        entry = {
            "id": hid, "created_date": today_str(), "name": name,
            "streak": 0, "last_done": "", "status": "active"
        }
        self.store.data["list"].append(entry)
        self.store.data["list"] = self.store.data["list"][-500:]
        self.store.save()
        self._append_to_sheet([hid, today_str(), name, 0, "", "active"])
        return entry

    def get_recent(self, n: int = 20):
        return self.store.data.get("list", [])[-n:]


class WaterStore:
    TAB_NAME = "Water Intake"
    HEADERS  = ["ID", "Date", "Time", "Amount", "Unit", "Cumulative Today"]

    def __init__(self):
        if not _SDM_AVAILABLE:
            return
        self.store = PrivateStore("water", {"logs": [], "counter": 0})
        self._ensure_sheet_tab()

    def _ensure_sheet_tab(self):
        try:
            if not sheets_backup or not sheets_backup._book:
                return
            existing = [ws.title for ws in sheets_backup._book.worksheets()]
            if self.TAB_NAME not in existing:
                ws = sheets_backup._book.add_worksheet(title=self.TAB_NAME, rows=2000, cols=len(self.HEADERS))
                ws.append_row(self.HEADERS, value_input_option="USER_ENTERED")
                sheets_backup._ws_cache[self.TAB_NAME] = ws
            else:
                if self.TAB_NAME not in sheets_backup._ws_cache:
                    ws = sheets_backup._book.worksheet(self.TAB_NAME)
                    sheets_backup._ws_cache[self.TAB_NAME] = ws
        except Exception as e:
            log.debug(f"Water tab error: {e}")

    def _append_to_sheet(self, row):
        try:
            if not sheets_backup or not sheets_backup._book:
                return
            ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if not ws:
                self._ensure_sheet_tab()
                ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if ws:
                ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
        except Exception as e:
            log.debug(f"Sheet append error: {e}")

    def add(self, amount: float, unit: str = "glass") -> Dict[str, Any]:
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        wid         = self.store.data["counter"]
        today_total = self.today_total()
        new_total   = today_total + amount
        entry = {
            "id": wid, "date": today_str(), "time": now_str(),
            "amount": amount, "unit": unit, "cumulative": new_total
        }
        self.store.data["logs"].append(entry)
        self.store.data["logs"] = self.store.data["logs"][-1000:]
        self.store.save()
        self._append_to_sheet([wid, today_str(), now_str(), amount, unit, new_total])
        return entry

    def today_total(self) -> float:
        today = today_str()
        total = 0.0
        for entry in self.store.data.get("logs", []):
            if entry.get("date") == today:
                total += entry.get("amount", 0)
        return total


class BillStore:
    TAB_NAME = "Bills"
    HEADERS  = ["ID", "Created Date", "Amount", "Description", "Due Date", "Paid Status"]

    def __init__(self):
        if not _SDM_AVAILABLE:
            return
        self.store = PrivateStore("bills", {"list": [], "counter": 0})
        self._ensure_sheet_tab()

    def _ensure_sheet_tab(self):
        try:
            if not sheets_backup or not sheets_backup._book:
                return
            existing = [ws.title for ws in sheets_backup._book.worksheets()]
            if self.TAB_NAME not in existing:
                ws = sheets_backup._book.add_worksheet(title=self.TAB_NAME, rows=2000, cols=len(self.HEADERS))
                ws.append_row(self.HEADERS, value_input_option="USER_ENTERED")
                sheets_backup._ws_cache[self.TAB_NAME] = ws
            else:
                if self.TAB_NAME not in sheets_backup._ws_cache:
                    ws = sheets_backup._book.worksheet(self.TAB_NAME)
                    sheets_backup._ws_cache[self.TAB_NAME] = ws
        except Exception as e:
            log.debug(f"Bills tab error: {e}")

    def _append_to_sheet(self, row):
        try:
            if not sheets_backup or not sheets_backup._book:
                return
            ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if not ws:
                self._ensure_sheet_tab()
                ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if ws:
                ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
        except Exception as e:
            log.debug(f"Sheet append error: {e}")

    def add(self, amount: float, description: str = "", due_date: str = "") -> Dict[str, Any]:
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        bid   = self.store.data["counter"]
        entry = {
            "id": bid, "created_date": today_str(), "amount": amount,
            "description": description, "due_date": due_date or today_str(), "paid": False
        }
        self.store.data["list"].append(entry)
        self.store.data["list"] = self.store.data["list"][-500:]
        self.store.save()
        self._append_to_sheet([bid, today_str(), amount, description, due_date or today_str(), "Pending"])
        return entry


class CalendarStore:
    TAB_NAME = "Calendar Events"
    HEADERS  = ["ID", "Created Date", "Event", "Event Date", "Event Time", "Reminder Sent"]

    def __init__(self):
        if not _SDM_AVAILABLE:
            return
        self.store = PrivateStore("calendar", {"list": [], "counter": 0})
        self._ensure_sheet_tab()

    def _ensure_sheet_tab(self):
        try:
            if not sheets_backup or not sheets_backup._book:
                return
            existing = [ws.title for ws in sheets_backup._book.worksheets()]
            if self.TAB_NAME not in existing:
                ws = sheets_backup._book.add_worksheet(title=self.TAB_NAME, rows=2000, cols=len(self.HEADERS))
                ws.append_row(self.HEADERS, value_input_option="USER_ENTERED")
                sheets_backup._ws_cache[self.TAB_NAME] = ws
            else:
                if self.TAB_NAME not in sheets_backup._ws_cache:
                    ws = sheets_backup._book.worksheet(self.TAB_NAME)
                    sheets_backup._ws_cache[self.TAB_NAME] = ws
        except Exception as e:
            log.debug(f"Calendar tab error: {e}")

    def _append_to_sheet(self, row):
        try:
            if not sheets_backup or not sheets_backup._book:
                return
            ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if not ws:
                self._ensure_sheet_tab()
                ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if ws:
                ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
        except Exception as e:
            log.debug(f"Sheet append error: {e}")

    def add(self, event: str, event_date: str = "", event_time: str = "") -> Dict[str, Any]:
        self.store.data["counter"] = self.store.data.get("counter", 0) + 1
        cid   = self.store.data["counter"]
        entry = {
            "id": cid, "created_date": today_str(), "event": event,
            "event_date": event_date or today_str(),
            "event_time": event_time, "reminder_sent": False
        }
        self.store.data["list"].append(entry)
        self.store.data["list"] = self.store.data["list"][-500:]
        self.store.save()
        self._append_to_sheet([cid, today_str(), event, event_date or today_str(), event_time, "No"])
        return entry


# Initialize stores if available
if _SDM_AVAILABLE:
    reminders      = ReminderStore()
    habits         = HabitStore()
    water_intake   = WaterStore()
    bills          = BillStore()
    calendar_events = CalendarStore()
    log.info("✅ All voice stores initialized")
else:
    reminders = habits = water_intake = bills = calendar_events = None
    log.warning("⚠️ Voice stores not available (SDM missing)")


# ================================================================
# VOICE NOTE STORE
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
        try:
            if not sheets_backup or not sheets_backup._book:
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
            log.debug(f"VoiceNotes tab error: {e}")

    def _append_to_sheet(self, row):
        try:
            if not sheets_backup or not sheets_backup._book:
                return
            ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if not ws:
                self._ensure_sheet_tab()
                ws = sheets_backup._ws_cache.get(self.TAB_NAME)
            if ws:
                ws.append_row([str(x) for x in row], value_input_option="USER_ENTERED")
        except Exception as e:
            log.debug(f"Sheet append error: {e}")

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
# GEMINI TRANSCRIPTION (ONLINE)
# ================================================================

async def transcribe_audio_gemini(audio_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY GitHub Secret mein set nahi hai!"

    if not audio_bytes or len(audio_bytes) < 1000:
        return None, f"Audio too small: {len(audio_bytes) if audio_bytes else 0} bytes"

    log.info(f"Sending to Gemini 2.5 Flash: {len(audio_bytes)} bytes")

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
                body     = e.read().decode("utf-8", errors="ignore")
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
        block    = feedback.get("blockReason", "")
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

    text = re.sub(r'\*+', '', text)
    text = re.sub(r'\n+', ' ', text).strip()
    text = re.sub(r'^(transcription|hinglish|text|output)[:\s]*', '', text, flags=re.IGNORECASE)

    log.info(f"✅ Gemini transcribed: {text[:80]}")
    return text.strip(), None


# ================================================================
# TRANSCRIPTION WITH FALLBACK (Online -> Offline)
# ================================================================

async def transcribe_audio(audio_bytes: bytes) -> Tuple[Optional[str], Optional[str], str]:
    """
    Returns: (transcript_text, error_message, source)
    source: 'gemini', 'offline', or None
    """
    # Try Gemini first (if API key exists)
    if GEMINI_API_KEY:
        transcript, error = await transcribe_audio_gemini(audio_bytes)
        if transcript:
            return transcript, None, "gemini"
        log.warning(f"Gemini failed: {error}")

    # Fallback to offline Vosk (if available)
    if offline_recognizer.available:
        log.info("Falling back to offline Vosk transcription...")
        transcript, error = await offline_recognizer.transcribe(audio_bytes)
        if transcript:
            return transcript, None, "offline"
        else:
            return None, error or "Both online and offline transcription failed", None
    else:
        return None, "No transcription method available (Gemini API missing and Vosk model not found)", None


# ================================================================
# ENHANCED CLASSIFICATION WITH KEYWORD ROUTING
# ================================================================

def parse_reminder_time(text: str) -> Tuple[str, str, int, str]:
    time_value = 0
    time_unit  = ""
    time_str   = ""

    patterns = [
        (r'(\d+)\s*(minute|min|m)', 'minute'),
        (r'(\d+)\s*(second|sec|s)', 'second'),
        (r'(\d+)\s*(hour|hr|ghanta)', 'hour'),
        (r'(\d+)\s*(day|din)', 'day'),
    ]

    for pattern, unit in patterns:
        match = re.search(pattern, text.lower())
        if match:
            time_value = int(match.group(1))
            time_unit  = unit
            now = datetime.now()
            if unit == 'minute':
                due = now + timedelta(minutes=time_value)
            elif unit == 'second':
                due = now + timedelta(seconds=time_value)
            elif unit == 'hour':
                due = now + timedelta(hours=time_value)
            elif unit == 'day':
                due = now + timedelta(days=time_value)
            else:
                due = now
            time_str = due.strftime("%Y-%m-%d %H:%M:%S")
            text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
            break

    return text, time_str, time_value, time_unit


def _classify_transcript(text: str) -> Tuple[str, Dict[str, Any]]:
    lower = text.lower().strip()

    # 1. EXPENSE
    expense_patterns = [
        r'^(expense|kharcha|karcha|exp)\s+(\d+(?:\.\d+)?)(?:\s+(.+))?$',
        r'^(\d+(?:\.\d+)?)\s+(?:rs|rupees|rupaye)?\s+(?:kharch|expense|kharcha).+$'
    ]
    for pattern in expense_patterns:
        match = re.match(pattern, lower, re.IGNORECASE)
        if match:
            if 'expense' in pattern or 'kharcha' in pattern:
                amount      = float(match.group(2))
                description = match.group(3) or ""
            else:
                amount      = float(match.group(1))
                description = re.sub(
                    r'^\d+(?:\.\d+)?\s*(?:rs|rupees|rupaye)?\s*(?:kharch|expense|kharcha)?\s*',
                    '', text, flags=re.IGNORECASE
                )
            if not description:
                description = "Expense"
            return "expense", {"amount": amount, "description": description[:100]}

    # 2. REMINDER
    reminder_match = re.match(r'^(reminder|remind|yaad dilana|rem)\s+(.+)$', lower, re.IGNORECASE)
    if reminder_match:
        reminder_text = reminder_match.group(2)
        clean_text, due_time, time_value, time_unit = parse_reminder_time(reminder_text)
        return "reminder", {
            "text": clean_text[:200], "due_time": due_time,
            "time_value": time_value, "time_unit": time_unit
        }

    # 3. HABIT
    habit_match = re.match(r'^(habit|aadat|hab)\s+(.+)$', lower, re.IGNORECASE)
    if habit_match:
        return "habit", {"text": habit_match.group(2)[:150]}

    # 4. WATER
    water_patterns = [
        r'^(water|pani|paani|water intake)\s+(\d+(?:\.\d+)?)\s*(glass|bottle|liter|ltr|ml)?',
        r'^(\d+(?:\.\d+)?)\s*(glass|bottle|liter|ltr|ml)?\s+(water|pani|paani)',
    ]
    for pattern in water_patterns:
        match = re.match(pattern, lower, re.IGNORECASE)
        if match:
            if 'water' in pattern and match.group(1):
                amount = float(match.group(2))
                unit   = match.group(3) or "glass"
            elif match.group(1):
                amount = float(match.group(1))
                unit   = match.group(2) or "glass"
            else:
                amount = 1.0
                unit   = "glass"
            return "water", {"amount": amount, "unit": unit}

    # 5. TASK
    task_match = re.match(r'^(task|kaam|tk)\s+(.+)$', lower, re.IGNORECASE)
    if task_match:
        return "task", {"text": task_match.group(2)[:200]}

    # 6. MEMORY
    memory_match = re.match(r'^(memory|yaad rakhna|remember|mem)\s+(.+)$', lower, re.IGNORECASE)
    if memory_match:
        return "memory", {"text": memory_match.group(2)[:200]}

    # 7. BILL
    bill_match = re.match(r'^(bill|payment|bil)\s+(\d+(?:\.\d+)?)(?:\s+(.+))?$', lower, re.IGNORECASE)
    if bill_match:
        return "bill", {
            "amount": float(bill_match.group(2)),
            "description": (bill_match.group(3) or "")[:100]
        }

    # 8. CALENDAR
    calendar_match = re.match(r'^(calendar|meeting|appointment|cal|mtg)\s+(.+)$', lower, re.IGNORECASE)
    if calendar_match:
        event_text  = calendar_match.group(2)
        date_match  = re.search(
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
            event_text, re.IGNORECASE
        )
        time_match  = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm))', event_text, re.IGNORECASE)
        event_date  = date_match.group(1) if date_match else ""
        event_time  = time_match.group(1) if time_match else ""
        if date_match:
            event_text = event_text.replace(date_match.group(1), "").strip()
        if time_match:
            event_text = event_text.replace(time_match.group(1), "").strip()
        return "calendar", {
            "text": event_text[:200],
            "event_date": event_date,
            "event_time": event_time
        }

    # 9. DEFAULT: DIARY
    return "diary", {"text": text[:500]}


# ================================================================
# MAIN HANDLER
# ================================================================

async def handle_voice_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _SDM_AVAILABLE:
        await update.message.reply_text("❌ Voice feature unavailable - secure_data_manager not loaded")
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
        f"🎙️ *Voice note* ({duration}s, {len(audio_bytes)//1024}KB)\n\n"
        f"🤖 Transcribe kar raha hai...\n(Pehle Gemini try karega, fir offline)",
        parse_mode="Markdown"
    )

    transcript, error, source = await transcribe_audio(audio_bytes)

    # Failure
    if not transcript:
        vosk_status = "✅" if offline_recognizer.available else "❌"
        await status_msg.edit_text(
            f"❌ *Transcription fail!*\n\n"
            f"*Error:*\n`{error}`\n\n"
            f"*Debug:*\n"
            f"• Gemini API: `{'SET ✅' if GEMINI_API_KEY else 'MISSING ❌'}`\n"
            f"• Offline Vosk: `{vosk_status}`\n"
            f"• Audio: `{len(audio_bytes)} bytes`\n"
            f"• Duration: `{duration}s`",
            parse_mode="Markdown"
        )
        if voice_store:
            voice_store.add(f"[FAIL: {str(error)[:60]}]", "none", "failed", duration, "Failed")
        return

    # Classify and Save
    category, data = _classify_transcript(transcript)
    saved_to   = "diary"
    extra_info = ""
    emoji_map  = {
        "expense": "💸", "reminder": "⏰", "habit": "🔥", "water": "💧",
        "task": "✅", "memory": "🧠", "bill": "🧾", "calendar": "📅", "diary": "📖"
    }
    emoji        = emoji_map.get(category, "📝")
    source_emoji = "🌐" if source == "gemini" else "📴"
    source_text  = "Gemini (Online)" if source == "gemini" else "Vosk (Offline)"

    if category == "expense":
        expenses.add(data["amount"], data["description"])
        saved_to   = "expenses"
        extra_info = f"Rs.{data['amount']} add kar diya!\n📝 *{data['description'][:50]}*"

    elif category == "reminder" and reminders:
        r          = reminders.add(data["text"], data["due_time"])
        saved_to   = f"reminder #{r['id']}"
        time_info  = f" ⏰ {data['time_value']}{data['time_unit']}" if data['time_value'] else ""
        extra_info = f"Reminder #{r['id']} set!{time_info}\n📌 *{data['text'][:50]}*"

    elif category == "habit" and habits:
        h          = habits.add(data["text"])
        saved_to   = f"habit #{h['id']}"
        extra_info = f"Habit #{h['id']} add kar diya!\n📌 *{data['text'][:50]}*"

    elif category == "water" and water_intake:
        w          = water_intake.add(data["amount"], data["unit"])
        saved_to   = "water"
        total      = water_intake.today_total()
        extra_info = f"{data['amount']} {data['unit']} water logged!\n🚰 Total today: {total} {data['unit']}"

    elif category == "task":
        t          = tasks.add(data["text"])
        saved_to   = f"task #{t['id']}"
        extra_info = f"Task #{t['id']} add kar diya!\n📌 *{data['text'][:60]}*"

    elif category == "memory":
        memory.add(data["text"])
        saved_to   = "memory"
        extra_info = f"Smart memory mein save kar liya!\n📝 *{data['text'][:60]}*"

    elif category == "bill" and bills:
        b          = bills.add(data["amount"], data["description"])
        saved_to   = f"bill #{b['id']}"
        extra_info = f"Bill Rs.{data['amount']} add!\n📝 *{data['description'][:50]}*"

    elif category == "calendar" and calendar_events:
        e          = calendar_events.add(data["text"], data["event_date"], data["event_time"])
        saved_to   = f"calendar #{e['id']}"
        extra_info = f"Event #{e['id']} added!\n📌 *{data['text'][:50]}*"
        if data['event_date']:
            extra_info += f"\n📅 Date: {data['event_date']}"
        if data['event_time']:
            extra_info += f" ⏰ {data['event_time']}"

    else:
        diary.add(f"[Voice] {data['text']}")
        saved_to   = "diary"
        extra_info = "Diary mein save kar diya!"

    if voice_store:
        voice_store.add(transcript, saved_to, category, duration, "Success")

    response_text = (
        f"{emoji} *Ho gaya!* ✅\n\n"
        f"📝 *Tumne kaha:*\n_{transcript[:400]}_\n\n"
        f"{'─'*20}\n"
        f"💾 {extra_info}\n\n"
        f"🎤 Category: *{category.upper()}*\n"
        f"{source_emoji} Source: *{source_text}*\n"
        f"/voicenotes — Purane notes dekho"
    )
    await status_msg.edit_text(response_text, parse_mode="Markdown")

    try:
        if sheets_backup:
            sheets_backup.log_event("voice_note", user_name, f"[{category}] {transcript[:80]}")
    except Exception:
        pass


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
            "💸 expense 500 movie ticket\n"
            "⏰ reminder 5 minute baad pani peena\n"
            "🔥 habit subah 5 baje uthna\n"
            "💧 water 2 glass\n"
            "✅ task report submit karna\n"
            "🧠 memory passport number 1234\n"
            "🧾 bill 1000 bijli ka\n"
            "📅 calendar monday 3pm meeting\n"
            "📖 (default) aaj acha din tha",
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
    help_text = """🎙️ *Voice Note Commands & Categories*

*How to use:*
Just send a voice message starting with a keyword!

*Available Categories:*

💸 *EXPENSE* — `expense 500 movie ticket`
⏰ *REMINDER* — `reminder 5 minute baad pani peena`
🔥 *HABIT* — `habit subah 5 baje uthna`
💧 *WATER* — `water 2 glass` or `pani 1 liter`
✅ *TASK* — `task report submit karna hai`
🧠 *MEMORY* — `memory passport number 1234`
🧾 *BILL* — `bill 1000 bijli ka`
📅 *CALENDAR* — `calendar monday 3pm meeting`
📖 *DIARY* — (default) `aaj acha din tha`

*Transcription Source:*
• 🌐 Gemini (Online) - High accuracy
• 📴 Vosk (Offline) - Fallback when Gemini busy

*Commands:*
/voicenotes — Recent voice notes
/voicehelp — This help
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")


# ================================================================
# REGISTER
# ================================================================

def register_voice_handlers(app):
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(CommandHandler("voicenotes", cmd_voicenotes))
    app.add_handler(CommandHandler("voicehelp", cmd_voicehelp))

    gemini_status = "✅" if GEMINI_API_KEY else "❌"
    vosk_status   = "✅" if offline_recognizer.available else "❌"
    sheets_status = "✅" if _SDM_AVAILABLE and sheets_backup and sheets_backup.connected else "❌"

    log.info("═" * 50)
    log.info("✅ Voice handlers registered")
    log.info(f"   🌐 Gemini API: {gemini_status}")
    log.info(f"   📴 Vosk Offline: {vosk_status}")
    log.info(f"   📊 Google Sheets: {sheets_status}")
    log.info("═" * 50)
