# Claude Code Tools

Custom hooks and utilities for [Claude Code](https://claude.ai/code).

## Features

### CLAUDE.md Auto-Update Hooks

Automatically maintains project context files (`CLAUDE.md`) across all your git repositories.

**Triggers:**

- On every file edit → tracks project
- On git commit → immediate update
- Every 15 prompts → periodic save (pre-compression safety)
- On session end → final update + notification

**Auto-detected:**

- Tech stack (Next.js, React, Tailwind, Prisma, Supabase, etc.)
- Architecture decisions from conventional commits
- Session history (FIFO, last 5)

**Preserved across updates:**

- Quick context description
- Archived tech with transition reasons
- Archived architecture decisions
- Task progress
- Notes

See [`hooks/README.md`](hooks/README.md) for detailed documentation.

## Installation

1. Clone this repo:

   ```bash
   git clone https://github.com/YOUR_USERNAME/claude-code-tools.git ~/Documents/GitHub/claude-code-tools
   ```

2. Symlink hooks to Claude's config:

   ```bash
   ln -sf ~/Documents/GitHub/claude-code-tools/hooks ~/.claude/hooks
   ```

3. Add to `~/.claude/settings.local.json`:

   ```json
   {
     "hooks": {
       "PostToolUse": [
         {
           "matcher": "Edit|Write",
           "hooks": [
             {
               "type": "command",
               "command": "python3 ~/.claude/hooks/on-file-edit.py"
             }
           ]
         },
         {
           "matcher": "Bash",
           "hooks": [
             {
               "type": "command",
               "command": "python3 ~/.claude/hooks/on-bash.py"
             }
           ]
         }
       ],
       "UserPromptSubmit": [
         {
           "matcher": ".*",
           "hooks": [
             {
               "type": "command",
               "command": "python3 ~/.claude/hooks/on-prompt.py"
             }
           ]
         }
       ],
       "Stop": [
         {
           "matcher": ".*",
           "hooks": [
             {
               "type": "command",
               "command": "python3 ~/.claude/hooks/on-stop.py"
             }
           ]
         }
       ]
     }
   }
   ```

4. Restart Claude Code to load the hooks.

## Structure

```
claude-code-tools/
├── README.md              # This file
├── hooks/
│   ├── README.md          # Detailed hook documentation
│   ├── on-file-edit.py    # PostToolUse: track edited files
│   ├── on-bash.py         # PostToolUse: detect git commits
│   ├── on-prompt.py       # UserPromptSubmit: periodic saves
│   ├── on-stop.py         # Stop: final update + cleanup
│   ├── update-claude-md.py # Core CLAUDE.md generator
│   └── lib/
│       └── session_state.py # Session tracking
```

## License

MIT

---

_Built for personal use with Claude Code_
