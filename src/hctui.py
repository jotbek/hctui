"""Compatibility launcher; prefer the installed ``hctui`` command."""

from hctui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
