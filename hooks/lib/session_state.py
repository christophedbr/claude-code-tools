#!/usr/bin/env python3
"""
Session state management for CLAUDE.md auto-update hooks.
Tracks projects touched, prompt count, and triggers saves.
"""
import json
import os
import fcntl
from pathlib import Path
from datetime import datetime

STATE_FILE = Path.home() / '.claude' / 'session-state.json'
PROMPT_SAVE_INTERVAL = 15  # Save every N prompts

def get_default_state():
    """Return default state structure"""
    return {
        "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "started": datetime.now().isoformat(),
        "projects": {},  # path -> {last_touched, commits: [], files_edited: []}
        "prompt_count": 0,
        "last_save": None
    }

def load_state():
    """Load state with file locking"""
    if not STATE_FILE.exists():
        return get_default_state()

    try:
        with open(STATE_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            state = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return state
    except (json.JSONDecodeError, IOError):
        return get_default_state()

def save_state(state):
    """Save state with file locking"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(STATE_FILE, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(state, f, indent=2)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except IOError:
        pass

def clear_state():
    """Clear state file (call on session end)"""
    if STATE_FILE.exists():
        STATE_FILE.unlink()

def track_project(file_path: str, event_type: str = "edit", commit_info: dict = None):
    """
    Track a project being worked on.

    Args:
        file_path: Absolute path to file being edited
        event_type: "edit" or "commit"
        commit_info: {hash, message} if event_type is "commit"
    """
    state = load_state()
    project_root = find_project_root(file_path)

    if not project_root:
        return state

    project_key = str(project_root)
    now = datetime.now().isoformat()

    if project_key not in state["projects"]:
        state["projects"][project_key] = {
            "last_touched": now,
            "commits": [],
            "files_edited": []
        }

    proj = state["projects"][project_key]
    proj["last_touched"] = now

    if event_type == "edit":
        rel_path = str(Path(file_path).relative_to(project_root))
        if rel_path not in proj["files_edited"]:
            proj["files_edited"].append(rel_path)
            # Keep only last 20 files
            proj["files_edited"] = proj["files_edited"][-20:]

    elif event_type == "commit" and commit_info:
        proj["commits"].append({
            "hash": commit_info.get("hash", ""),
            "message": commit_info.get("message", ""),
            "time": now
        })
        # Keep only last 10 commits
        proj["commits"] = proj["commits"][-10:]

    save_state(state)
    return state

def increment_prompt_count():
    """Increment prompt count and return whether to trigger save"""
    state = load_state()
    state["prompt_count"] += 1
    save_state(state)

    should_save = (state["prompt_count"] % PROMPT_SAVE_INTERVAL == 0)
    return should_save, state

def find_project_root(file_path: str) -> Path:
    """Find git root for a given file path"""
    path = Path(file_path).resolve()
    home = Path.home()

    # Walk up looking for .git
    for parent in [path] + list(path.parents):
        if parent == home:
            return None
        if (parent / '.git').exists():
            return parent

    return None

def get_all_tracked_projects():
    """Get list of all projects tracked this session"""
    state = load_state()
    return list(state.get("projects", {}).keys())
