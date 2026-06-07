import json
import os
from datetime import datetime
from pathlib import Path
from secure_data_manager import DATA_DIR, sheets_backup, now_ist

NOTES_FILE = os.path.join(DATA_DIR, "quick_notes.json")

def _get_next_id():
    """Get next unique ID for note"""
    notes = get_all_notes()
    if not notes:
        return 1
    # Safely get max ID
    max_id = 0
    for note in notes:
        nid = note.get("id", 0)
        if isinstance(nid, int) and nid > max_id:
            max_id = nid
    return max_id + 1

def add_note(text: str) -> dict:
    """Add a new quick note with unique ID"""
    notes = get_all_notes()
    
    # Get next unique ID
    new_id = _get_next_id()
    
    note = {
        "id": new_id,
        "text": text,
        "created": now_ist().strftime("%Y-%m-%d %H:%M:%S"),
        "date": now_ist().strftime("%Y-%m-%d"),
        "time": now_ist().strftime("%H:%M:%S"),
        "pinned": False
    }
    notes.insert(0, note)  # Newest first
    _save_notes(notes)
    
    # ✅ Save to Google Sheets
    try:
        sheets_backup.quick_note(note)  # Add this method to sheets_backup
    except Exception as e:
        log.warning(f"Sheet backup failed for note: {e}")
    
    return note

def get_all_notes() -> list:
    """Get all notes"""
    if not os.path.exists(NOTES_FILE):
        return []
    try:
        with open(NOTES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def _save_notes(notes: list):
    """Save notes to file"""
    with open(NOTES_FILE, 'w', encoding='utf-8') as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)

def delete_note(note_id: int) -> bool:
    """Delete a note by ID"""
    notes = get_all_notes()
    original_len = len(notes)
    notes = [n for n in notes if n.get("id") != note_id]
    if len(notes) < original_len:
        _save_notes(notes)
        return True
    return False

def pin_note(note_id: int) -> bool:
    """Toggle pin status of a note"""
    notes = get_all_notes()
    for note in notes:
        if note.get("id") == note_id:
            note["pinned"] = not note.get("pinned", False)
            _save_notes(notes)
            return note["pinned"]
    return False

def search_notes(query: str) -> list:
    """Search notes by text"""
    notes = get_all_notes()
    query_lower = query.lower()
    return [n for n in notes if query_lower in n.get("text", "").lower()]

def get_note_by_id(note_id: int) -> dict:
    """Get a single note by ID"""
    notes = get_all_notes()
    for note in notes:
        if note.get("id") == note_id:
            return note
    return None

def clear_all_notes() -> int:
    """Delete all notes"""
    count = len(get_all_notes())
    _save_notes([])
    return count
