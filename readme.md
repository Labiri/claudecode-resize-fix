# Claude Code Terminal Resize Fix

Claude Code and terminal resizing have a complicated relationship, especially after version 2.0.60-ish.
It uses Ink (React for terminals) to render its TUI. Ink is great, but it gets confused when the terminal dimensions change mid-render. The `SIGWINCH` signal fires, Ink tries to redraw, but the PTY dimensions are out of sync, and you end up with text from three different layouts fighting for screen real estate.

The fix is embarrassingly simple: run Claude inside a PTY wrapper that actually keeps the dimensions in sync.

## How it works

```
Your Terminal ←→ This Wrapper ←→ PTY ←→ Claude Code
                      ↓
              "oh, resize? let me
               sync that for you"
```

When you resize:
1. Terminal sends `SIGWINCH` to the wrapper
2. Wrapper updates PTY size via `TIOCSWINSZ` ioctl
3. Wrapper forwards `SIGWINCH` to Claude
4. Ink redraws with correct dimensions
5. You don't want to throw your laptop out the window

That's it. No magic, just plumbing that should have been there.

# Installation

Just point the repo to Claude Code. We are in 2026.


## Installation for the brave

```bash
# Grab it
curl -o ~/.local/bin/claude-resize-fix https://raw.githubusercontent.com/Labiri/claudecode-resize-fix/main/claude-resize-fix.py
chmod +x ~/.local/bin/claude-resize-fix
```

## Usage

```bash
# Instead of 'claude', run:
claude-resize-fix

# All args pass through
claude-resize-fix --resume abc123
claude-resize-fix -p "explain this code"
```

### Make it permanent

Add to your shell rc:

```bash
alias claude='~/.local/bin/claude-resize-fix'
```

Or if you want a fallback (you don't need one, but some people like safety nets):

```bash
claude() {
    local wrapper="$HOME/.local/bin/claude-resize-fix"
    if [[ -x "$wrapper" ]]; then
        python3 "$wrapper" "$@"
    else
        command claude "$@"
    fi
}
```

## Requirements

- Python 3.8+ (uses `pty`, `fcntl`, `termios` - all stdlib)
- macOS or Linux
- Claude Code CLI in your PATH

## FAQ

**Does this add latency?**
No. It's a thin proxy shuffling bytes between two file descriptors.

**Why Python and not a shell script?**
Try doing proper PTY management and signal handling in bash. I'll wait.

**Does it work in tmux?**
Yes.

## License

MIT. Do whatever you want with it.

---

*Born from watching Claude's output turn into modern art one too many times.*
