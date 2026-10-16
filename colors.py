"""Shared ok/warn/error message styling (Okabe-Ito palette, colour-blind safe).

colors.sh holds the same colours for the bash scripts; keep the two in sync.
"""
import sys

BOLD = '\033[1m'
GREEN = '\033[38;2;0;158;115m'    # Okabe-Ito bluish green
YELLOW = '\033[38;2;230;159;0m'   # Okabe-Ito orange
RED = '\033[38;2;213;94;0m'       # Okabe-Ito vermillion
RESET = '\033[0m'


def ok(msg):
    print(f"{GREEN}✓{RESET} {msg}")


def warn(msg):
    print(f"{YELLOW}[WARN]{RESET} {msg}")


def error(msg):
    print(f"{RED}[ERROR]{RESET} {msg}", file=sys.stderr)
