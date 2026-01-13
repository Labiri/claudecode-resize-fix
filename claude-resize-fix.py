#!/usr/bin/env python3
"""
Claude Code PTY Wrapper - Fixes terminal resize artifacts

Usage:
  ./claude-resize-fix.py [claude args...]
  ./claude-resize-fix.py --resume abc123
  ./claude-resize-fix.py -p "hello"

Works with: iTerm2, Terminal.app, tmux, plain terminals

"""

import os
import sys
import pty
import signal
import select
import termios
import tty
import struct
import fcntl
import time
import shutil
from contextlib import suppress
from typing import Optional


class ClaudeWrapper:
    def __init__(self, claude_args: list[str]):
        self.claude_args = claude_args
        self.master_fd: Optional[int] = None
        self.child_pid: Optional[int] = None
        self.original_termios = None
        self.resize_pending = False
        self.last_resize_time = 0
        self.resize_debounce_ms = 100

    def get_terminal_size(self) -> tuple[int, int]:
        """Get current terminal size (rows, cols)."""
        try:
            buf = fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, b'\x00' * 8)
            rows, cols, _, _ = struct.unpack('HHHH', buf)
            return rows, cols
        except (OSError, termios.error, struct.error):
            return 24, 80

    def set_pty_size(self, rows: int, cols: int):
        """Set the PTY size to match terminal."""
        if self.master_fd is not None:
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def handle_resize(self, signum, frame):
        """Handle SIGWINCH - debounce and mark for processing."""
        current_time = time.time() * 1000
        if current_time - self.last_resize_time > self.resize_debounce_ms:
            self.resize_pending = True
            self.last_resize_time = current_time

    def force_redraw(self):
        """Force Claude Code to redraw on resize."""
        if self.child_pid is None:
            return

        rows, cols = self.get_terminal_size()
        self.set_pty_size(rows, cols)

        try:
            os.kill(self.child_pid, signal.SIGWINCH)
        except ProcessLookupError:
            return

        self.resize_pending = False

    def run(self) -> int:
        """Run Claude Code in a PTY with resize handling."""
        claude_path = shutil.which('claude')
        if not claude_path:
            print("Error: 'claude' command not found in PATH", file=sys.stderr)
            return 1

        try:
            self.original_termios = termios.tcgetattr(sys.stdin.fileno())
        except termios.error:
            self.original_termios = None

        self.child_pid, self.master_fd = pty.fork()

        if self.child_pid == 0:
            os.execvp(claude_path, ['claude'] + self.claude_args)
            sys.exit(1)

        try:
            signal.signal(signal.SIGWINCH, self.handle_resize)
            rows, cols = self.get_terminal_size()
            self.set_pty_size(rows, cols)

            if self.original_termios:
                tty.setraw(sys.stdin.fileno())

            return self._io_loop()
        finally:
            self._cleanup()

    def _io_loop(self) -> int:
        """Main I/O loop - proxy between terminal and PTY."""
        stdin_fd = sys.stdin.fileno()
        stdout_fd = sys.stdout.fileno()

        while True:
            if self.resize_pending:
                self.force_redraw()

            try:
                readable, _, _ = select.select(
                    [stdin_fd, self.master_fd], [], [], 0.1
                )
            except select.error:
                continue

            pid, status = os.waitpid(self.child_pid, os.WNOHANG)
            if pid != 0:
                if os.WIFEXITED(status):
                    return os.WEXITSTATUS(status)
                return 1

            for fd in readable:
                if fd == stdin_fd:
                    try:
                        data = os.read(stdin_fd, 1024)
                        if data:
                            os.write(self.master_fd, data)
                    except OSError:
                        continue

                elif fd == self.master_fd:
                    try:
                        data = os.read(self.master_fd, 4096)
                        if data:
                            os.write(stdout_fd, data)
                    except OSError:
                        continue

    def _cleanup(self):
        """Restore terminal state."""
        if self.original_termios:
            with suppress(termios.error, OSError):
                termios.tcsetattr(
                    sys.stdin.fileno(),
                    termios.TCSAFLUSH,
                    self.original_termios
                )

        if self.master_fd is not None:
            with suppress(OSError):
                os.close(self.master_fd)


def main():
    wrapper = ClaudeWrapper(sys.argv[1:])
    sys.exit(wrapper.run())


if __name__ == '__main__':
    main()
