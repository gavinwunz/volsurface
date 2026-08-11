"""VolFoundry command-line entry point (stub — full CLI in P15).

The CLI module exists so the ``volfoundry`` console-script entry point
declared in ``pyproject.toml`` resolves.  For now it prints version info
and exits.  The full CLI is built in Milestone P15.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ``volfoundry`` console script."""
    if argv is None:
        argv = sys.argv[1:]

    # --version / version
    if not argv or "--version" in argv or "version" in argv:
        from volfoundry import __version__

        print(f"VolFoundry {__version__}")
        return

    # Not a recognised command yet
    print(f"VolFoundry CLI — unrecognised command: {' '.join(argv)!r}", file=sys.stderr)
    print("Try:  volfoundry --version", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
