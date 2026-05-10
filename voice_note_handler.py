#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Voice Note Handler for RK Bot
Transcribes voice messages and processes them as text commands
- FIXED: Better error handling for ffmpeg missing
- FIXED: Voice notes now go to proper sheets (not diary)
- FIXED: Removed transcription prompt instructions
"""

import logging
import tempfile
import os
import re
import subprocess
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

log = logging.getLogger(__name__)

# Try to import speech recognition
try:
    import speech_recognition as sr
    HAS_SPEECH_RECOGNITION = True
except ImportError:
    HAS_SPEECH_RECOGNITION = False
    log.warning("speech_recognition not installed! Voice notes won't work.")

# Check if ffmpeg is available
def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

HAS_FFMPEG = check_ffmpeg()
if not HAS_FFMPEG:
    log.warning("ffmpeg not installed! Voice notes won't work. Install with: sudo apt install ffmpeg")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages - transcribe and process"""
    if not HAS_SPEECH_RECOGNITION:
        await update.message.reply_text(
            "🎤 Voice note feature is not available. Please send text messages.\n\n"
            "_(SpeechRecognition library not installed)_",
            parse_mode="Markdown"
        )
        return
    
    if not HAS_FFMPEG:
        await update.message.reply_text(
            "🎤 Voice note feature is not available. Please send text messages.\n\n"
            "_(ffmpeg not installed on server)_",
            parse_mode="Markdown"
        )
        return
    
    if not update.message.voice:
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Send initial response
    processing_msg = await update.message.reply_text(
        "🎤 *Voice note received!* Transcribing... ⏳",
        parse_mode="Markdown"
    )
    
    try:
        # Download voice file
        file = await context.bot.get_file(update.message.voice.file_id)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_file:
            await file.download_to_drive(tmp_file.name)
            tmp_path = tmp_file.name
        
        # Convert and transcribe
        recognizer = sr.Recognizer()
        
        # Convert ogg to wav for processing
        wav_path = tmp_path.replace('.ogg', '.wav')
        try:
            result = subprocess.run(
                ['ffmpeg', '-i', tmp_path, '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', wav_path, '-y'], 
                capture_output=True, check=True
            )
        except subprocess.CalledProcessError as e:
            log.error(f"FFmpeg conversion failed: {e.stderr}")
            await processing_msg.edit_text(
                "❌ *Voice note conversion failed!*\n\n"
                "Please send text message instead.",
                parse_mode="Markdown"
            )
            os.unlink(tmp_path)
            return
        except FileNotFoundError:
            log.error("FFmpeg not found in PATH")
            await processing_msg.edit_text(
                "❌ *ffmpeg not installed!*\n\n"
                "Please send text message instead.",
                parse_mode="Markdown"
            )
            os.unlink(tmp_path)
            return
        
        # Transcribe
        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)
            try:
                # Try using Google Speech Recognition (free, no API key required)
                text = recognizer.recognize_google(audio, language="hi-IN")
            except sr.UnknownValueError:
                text = None
            except sr.RequestError as e:
                log.error(f"Speech recognition request error: {e}")
                text = None
        
        # Clean up temp files
        os.unlink(tmp_path)
        if os.path.exists(wav_path):
            os.unlink(wav_path)
        
        if not text:
            await processing_msg.edit_text(
                "❌ *Could not transcribe voice note!*\n\n"
                "Please speak clearly or send text message instead.",
                parse_mode="Markdown"
            )
            return
        
        # Clean the transcribed text - remove any prompt instructions if present
        text = text.strip()
        
        # Remove common prompt patterns if accidentally transcribed
        prompt_patterns = [
            r'jo bola gaya hai woh word-for-word likho',
            r'sirf transcription do',
            r'koi explanation nahi',
            r'koi prefix nahi',
            r'hinglish ya hindi ya english jo bhi bola ho woh likho',
            r'isk[oO] exactly transcribe karo',
            r'is voice message ko exactly transcribe karo',
        ]
        for pattern in prompt_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        text = text.strip()
        
        if not text or len(text) < 2:
            await processing_msg.edit_text(
                "🎤 *I couldn't hear clearly!*\n\n"
                "Please speak again more clearly or send text message.",
                parse_mode="Markdown"
            )
            return
        
        # Send transcribed text
        await processing_msg.edit_text(
            f"🎤 *You said:*\n\n\"{text}\"\n\n📝 *Processing...*",
            parse_mode="Markdown"
        )
        
        # Process the transcribed text through the NLP parser
        await _process_voice_command(update, context, text)
        
    except Exception as e:
        log.error(f"Voice handling error: {e}")
        await processing_msg.edit_text(
            "❌ *Error processing voice note!*\n\nPlease send text message.",
            parse_mode="Markdown"
        )

async def _process_voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Process voice transcribed text through the appropriate handlers"""
    
    # Import here to avoid circular import
    from main import parse_user_message, _log_action, tasks, reminders, expenses, diary, habits, bills, calendar, water, memory, chat_hist, today_str
    
    user_name = update.effective_user.first_name or "User"
    
    # Parse the message to determine intent
    action_type, params = parse_user_message(text)
    log.info(f"[Voice] '{text[:60]}' → {action_type}")
    
    # Log to chat history
    chat_hist.add("user", f"[Voice] {text}", user_name)
    
    # Handle based on action type - SAME AS TEXT MESSAGES
    if action_type == "expense":
        amount = params.get("amount", 0)
        desc = params.get("desc", "")
        expenses.add(amount, desc)
        _log_action(user_name, "expense_add", f"Rs.{amount} on {desc}")
        await update.message.reply_text(
            f"💸 *Kharcha Add Ho Gaya!*\n\nRs.{amount} — {desc}\n💰 Aaj total: Rs.{expenses.today_total()}",
            parse_mode="Markdown"
        )
    
    elif action_type == "add_task":
        title = params.get("title", "")
        t = tasks.add(title)
        _log_action(user_name, "task_add", f"#{t['id']}: {title}")
        await update.message.reply_text(
            f"✅ *Task Add Ho Gaya!*\n\n📌 #{t['id']} {title}\n\nInshAllah ho jayega! 💪",
            parse_mode="Markdown"
        )
    
    elif action_type == "remind":
        r = reminders.add(update.effective_chat.id, params.get("text", "Reminder"), params.get("time", ""))
        when_str = "Kal" if params.get("tomorrow") else "Aaj"
        _log_action(user_name, "reminder_set", f"#{r['id']} at {params.get('time')}: {params.get('text')}")
        await update.message.reply_text(
            f"⏰ *Reminder Set!*\n\n🕐 {when_str} {params.get('time')} baje: {params.get('text')}\n📌 ID #{r['id']}",
            parse_mode="Markdown"
        )
    
    elif action_type == "diary":
        diary_text = params.get("text", "")
        diary.add(diary_text)
        _log_action(user_name, "diary_write", f"Entry: {diary_text[:80]}")
        await update.message.reply_text(
            f"📖 *Diary Save Ho Gayi!* ✅\n\n_{diary_text[:200]}_",
            parse_mode="Markdown"
        )
    
    elif action_type == "add_habit":
        h = habits.add(params.get("name", ""))
        _log_action(user_name, "habit_add", f"#{h['id']}: {h['name']}")
        await update.message.reply_text(
            f"🏃 *Habit Add Ho Gaya!*\n\n#{h['id']} {h['name']}\n\nInshAllah roz karoge! 💪",
            parse_mode="Markdown"
        )
    
    elif action_type == "habit_done":
        keyword = params.get("keyword", "")
        if keyword.isdigit():
            ok, streak = habits.log(int(keyword))
            name = f"#{keyword}"
        else:
            ok, streak, h = habits.log_by_name(keyword)
            name = h["name"] if h else keyword
        if ok:
            _log_action(user_name, "habit_done", f"'{name}' done | streak: {streak}")
            await update.message.reply_text(
                f"🔥 *{name} done! MashAllah!* 🎉\n\n{streak} din ka streak! 💪",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❓ Kaunsa habit? Text mein batao", parse_mode="Markdown")
    
    elif action_type == "add_calendar":
        title = params.get("title", "Event")
        ev_date = params.get("date", today_str())
        ev_type = params.get("type", "event")
        e = calendar.add(title, ev_date, "", "", "", ev_type)
        _log_action(user_name, "calendar_add", f"{'Birthday' if ev_type=='birthday' else 'Event'} #{e['id']}: {title}")
        emoji = "🎂" if ev_type == "birthday" else "📅"
        msg = f"{emoji} *Event Add Ho Gaya!* ✅\n\n📅 *{ev_date}*\n📌 {title}"
        await update.message.reply_text(msg, parse_mode="Markdown")
    
    elif action_type == "add_bill":
        name = params.get("name", "Bill")
        amount = params.get("amount", 0)
        due_day = params.get("due_day", 0)
        b = bills.add(name, amount, due_day)
        _log_action(user_name, "bill_add", f"#{b['id']}: {name} Rs.{amount}")
        await update.message.reply_text(
            f"💳 *Bill Add Ho Gaya!* ✅\n\n#{b['id']} *{name}*\n💰 Rs.{amount}",
            parse_mode="Markdown"
        )
    
    elif action_type == "water":
        ml = params.get("ml", 250)
        total = water.add(ml)
        goal_ml = water.goal()
        pct = int(total / goal_ml * 100) if goal_ml else 0
        _log_action(user_name, "water_log", f"Added {ml}ml")
        await update.message.reply_text(
            f"💧 *{ml}ml Paani Log Ho Gaya!*\n\nTotal: {total}/{goal_ml}ml ({pct}%)\n\n"
            f"{'Alhamdulillah! Goal complete! 🎉' if total >= goal_ml else 'InshAllah goal poora hoga! 💪'}",
            parse_mode="Markdown"
        )
    
    elif action_type == "memory_save":
        mem_text = params.get("text", "")
        memory.add(mem_text)
        _log_action(user_name, "memory_save", f"Saved: {mem_text[:80]}")
        await update.message.reply_text(
            f"🧠 *Memory Save Ho Gaya!* ✅\n\n_{mem_text[:150]}_",
            parse_mode="Markdown"
        )
    
    elif action_type in ["show_reminders", "show_tasks", "show_habits", "show_diary", "show_memory", "show_calendar"]:
        # For show commands, call the appropriate helper
        from main import _send_reminder_list, _send_task_list, _send_habit_list, _send_diary_today, _send_memory_list, _send_calendar_list
        
        if action_type == "show_reminders":
            await _send_reminder_list(update)
        elif action_type == "show_tasks":
            await _send_task_list(update)
        elif action_type == "show_habits":
            await _send_habit_list(update)
        elif action_type == "show_diary":
            await _send_diary_today(update)
        elif action_type == "show_memory":
            await _send_memory_list(update)
        elif action_type == "show_calendar":
            await _send_calendar_list(update)
        
        _log_action(user_name, action_type, text[:60])
    
    elif action_type == "complete_task":
        hint = params.get("hint", "")
        pending = tasks.pending()
        matched = next((t for t in pending if str(t["id"]) == hint or (hint and hint in t["title"].lower())), None)
        if matched:
            tasks.complete(matched["id"])
            _log_action(user_name, "task_done", f"#{matched['id']}: {matched['title']}")
            await update.message.reply_text(
                f"✅ *Task Complete!* 🎉\n\n#{matched['id']} {matched['title']}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❓ Kaunsa task? Text mein batao", parse_mode="Markdown")
    
    else:
        # Fallback to AI chat
        from main import build_system_prompt, call_gemini
        prompt = build_system_prompt() + f"\n\nUser (voice): {text}\n\nShort Hinglish reply (2-3 lines), Muslim phrases zaroor use karo:"
        reply = call_gemini(prompt)
        if not reply:
            reply = "☪️ Assalamualaikum! Kya help chahiye? Tasks, reminders, kharcha, diary, calendar, bills?"
        _log_action(user_name, "voice_chat", f"Q: {text[:60]} | A: {reply[:60]}")
        await update.message.reply_text(reply, parse_mode="Markdown")
    
    chat_hist.add("assistant", "Voice command processed", "Rk")

def register_voice_handlers(app):
    """Register voice message handlers"""
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    if HAS_SPEECH_RECOGNITION and HAS_FFMPEG:
        log.info("✅ Voice note handlers registered (with ffmpeg support)")
    else:
        log.warning("⚠️ Voice note handlers registered but missing dependencies")
