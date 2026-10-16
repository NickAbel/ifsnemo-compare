# Shared warn/error message styling (Okabe-Ito palette). Keep in sync with colors.py.
NC='\033[0m'
RED='\033[1;38;2;213;94;0m'       # vermillion
YELLOW='\033[1;38;2;230;159;0m'   # orange

# Display warning styled message with given argument.
function warn {
    echo -e "${YELLOW}[WARN]${NC} $1" 1>&2
}

# Display fatal styled message with given argument, then exit.
function fatal {
    echo -e "${RED}\u274c FATAL:${NC} $1" 1>&2
    exit 1
}
