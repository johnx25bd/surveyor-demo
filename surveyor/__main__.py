"""Entry point so ``python -m surveyor "question"`` runs the CLI."""

import sys

from surveyor.cli import main

sys.exit(main())
