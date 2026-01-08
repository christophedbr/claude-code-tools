# CLAUDE.md Auto-Update Hooks

> Auto-maintains project context files across all your git repositories.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                     Trigger Points                              │
├─────────────────────────────────────────────────────────────────┤
│  1. ON FILE EDIT     → Track project in session state           │
│  2. ON GIT COMMIT    → Immediate CLAUDE.md update               │
│  3. EVERY 15 PROMPTS → Periodic save (pre-compression safety)   │
│  4. ON SESSION END   → Final update + macOS notification        │
└─────────────────────────────────────────────────────────────────┘
```

## Files

| File                   | Purpose                                |
| ---------------------- | -------------------------------------- |
| `on-file-edit.py`      | PostToolUse hook - tracks edited files |
| `on-bash.py`           | PostToolUse hook - detects git commits |
| `on-prompt.py`         | UserPromptSubmit hook - counts prompts |
| `on-stop.py`           | Stop hook - final update + cleanup     |
| `update-claude-md.py`  | Core logic - generates CLAUDE.md       |
| `lib/session_state.py` | Session tracking (projects, counters)  |

## CLAUDE.md Structure

Each project's CLAUDE.md contains:

```markdown
# Project: [name]

## Quick Context

<!-- Manual: Brief description for Claude -->

## Current Tech Stack

| Layer | Technology | Since | Notes |

<!-- Auto-detected from package.json, requirements.txt, etc. -->

## Archived Tech

| Technology | Used | Retired | Reason |

<!-- Manual: Track transitioned technologies -->

## Architecture Decisions (Active)

| Date | Decision | Rationale | Status |

<!-- Auto-populated from feat:, fix:, refactor: commits -->

## Architecture Decisions (Archived)

| Date | Decision | Outcome |

<!-- Manual: Historical decisions -->

## Task Progress

- [ ] Task items
<!-- Manual: Persistent across sessions -->

## Recent Sessions (Last 5)

| Date | Branch | Summary |

<!-- Auto: FIFO queue of recent work -->

## Notes

<!-- Manual: Preserved across updates -->
```

## Configuration

Hooks are configured in `~/.claude/settings.local.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "command": "python3 /path/to/on-file-edit.py" }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 /path/to/on-bash.py" }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": ".*",
        "hooks": [
          { "type": "command", "command": "python3 /path/to/on-prompt.py" }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": ".*",
        "hooks": [
          { "type": "command", "command": "python3 /path/to/on-stop.py" }
        ]
      }
    ]
  }
}
```

## Manual Commands

Update a single project:

```bash
python3 ~/.claude/hooks/update-claude-md.py --project /path/to/project --trigger manual
```

Update all git projects:

```bash
for dir in ~/Documents/GitHub/*/; do
  [ -d "$dir/.git" ] && python3 ~/.claude/hooks/update-claude-md.py --project "$dir" --trigger manual
done
```

## Customization

### Change save interval

Edit `lib/session_state.py`:

```python
PROMPT_SAVE_INTERVAL = 15  # Change to desired number
```

### Change session history limit

Edit `update-claude-md.py`:

```python
MAX_SESSION_HISTORY = 5  # Change to desired number
```

### Add tech stack detection

Edit `update-claude-md.py` in `detect_tech_stack()` function.

## Troubleshooting

### Hooks not triggering

- Restart Claude Code (hooks load at session start)
- Check paths are absolute in settings.local.json
- Check `~/.claude/hooks-debug.log` for errors

### Wrong project updated

- Hooks track files by absolute path
- Project root = nearest parent with `.git` directory

### Debug mode

The `on-file-edit.py` has debug logging enabled. Check:

```bash
cat ~/.claude/hooks-debug.log
```

## Session State

Tracked in `~/.claude/session-state.json`:

```json
{
  "session_id": "20260108_001234",
  "started": "2026-01-08T00:12:34",
  "projects": {
    "/path/to/project": {
      "last_touched": "...",
      "commits": [...],
      "files_edited": [...]
    }
  },
  "prompt_count": 42,
  "last_save": "..."
}
```

Cleared automatically on session end.

---

_Created: 2026-01-08_
