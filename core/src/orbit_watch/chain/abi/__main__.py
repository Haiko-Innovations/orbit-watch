"""``python -m orbit_watch.chain.abi <contracts/out>``: regenerate the ABI files."""

import sys

from orbit_watch.chain.abi import main

raise SystemExit(main(sys.argv[1:]))
