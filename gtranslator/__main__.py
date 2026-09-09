"""Allow running as: python3 -m gtranslator …"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
