import logging

# ANSI color codes for use in log messages
# Usage: logger.info(f"{C.GREEN}Fetched %d issues{C.RESET}")

class C:
    RESET   = "\033[0m"

    # Text colors
    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    # Bright variants
    BRED    = "\033[91m"
    BGREEN  = "\033[92m"
    BYELLOW = "\033[93m"
    BBLUE   = "\033[94m"
    BCYAN   = "\033[96m"

    # Styles
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ULINE   = "\033[4m"


class ColorFormatter(logging.Formatter):
    """Logging formatter that applies ANSI colors by log level.
    Change the mapping here to restyle all log output in one place.
    """
    LEVEL_COLORS = {
        logging.DEBUG   : C.DIM,
        logging.INFO    : C.RESET,
        logging.WARNING : C.BYELLOW,
        logging.ERROR   : C.RED,
        logging.CRITICAL: C.BRED + C.BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, C.RESET)
        message = super().format(record)
        return f"{color}{message}{C.RESET}"
