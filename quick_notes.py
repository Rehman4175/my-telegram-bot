#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QUICK NOTE (CLIPBOARD) MANAGER
Jaldi koi bhi cheez save karo — number, address, link, text
"""

import json, os
from datetime import datetime, timezone, timedelta

DATA_DIR = os.environ.get("DATA_DIR", "data")
NOTES_FILE = os.path.join(DATA_DIR, "quick_notes.json")

IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST)

def _load():
    try:
        if os.path.exists(NOTES_FILE):
            with open(NOTES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {"notes": [], "counter": 0}

def _save(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(NOTES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_note(text: str) -> dict:
    """Naya note save karo"""
    data = _load()
    data["counter"] = data.get("counter", 0) + 1
    note = {
        "id": data["counter"],
        "text": text.strip(),
        "created": now_ist().strftime("%Y-%m-%d %H:%M"),
        "pinned": False
    }
    data["notes"].append(note)
    _save(data)
    return note

def get_all_notes() -> list:
    """Saare notes list karo — pinned pehle"""
    data = _load()
    notes = data.get("notes", [])
    pinned = [n for n in notes if n.get("pinned")]
    normal = [n for n in notes if not n.get("pinned")]
    return pinned + normal

def delete_note(note_id: int) -> bool:
    """Note delete karo"""
    data = _load()
    before = len(data["notes"])
    data["notes"] = [n for n in data["notes"] if n["id"] != note_id]
    if len(data["notes"]) < before:
        _save(data)
        return True
    return False

def pin_note(note_id: int) -> bool:
    """Note pin/unpin karo"""
    data = _load()
    for n in data["notes"]:
        if n["id"] == note_id:
            n["pinned"] = not n.get("pinned", False)
            _save(data)
            return n["pinned"]
    return False

def search_notes(query: str) -> list:
    """Notes mein search karo"""
    query = query.lower()
    return [n for n in get_all_notes() if query in n["text"].lower()]

def clear_all_notes() -> int:
    """Saare notes delete karo"""
    data = _load()
    count = len(data["notes"])
    data["notes"] = []
    _save(data)
    return count

def get_note_by_id(note_id: int) -> dict:
    data = _load()
    for n in data["notes"]:
        if n["id"] == note_id:
            return n
    return None
