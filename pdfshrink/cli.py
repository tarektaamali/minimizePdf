"""Command-line entry point. The web layer uses core.shrink directly."""

import argparse
import json
import os
import sys

from .core import shrink
from .sizes import format_size, parse_size


def _use_utf8():
    """Sizes are printed with U+202F, which cp1252 cannot encode.

    A French Windows console is cp1252 by default, so without this any
    printed size raises UnicodeEncodeError. Streams that cannot be
    reconfigured, such as pytest's capture, are left alone.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _payload(result, output):
    return {
        "ok": result.ok,
        "before": result.before,
        "size": result.size,
        "dpi": result.dpi,
        "check": list(result.check) if result.check else None,
        "best_safe_size": result.best_safe_size,
        "reason": result.reason,
        "output": output,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fit a PDF under a size budget.")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--target", default="200 Ko", help="e.g. 200 Ko, 1,5 Mo")
    parser.add_argument("--min-dpi", type=int, default=100,
                        help="refuse to go below this resolution (default 100)")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output")
    args = parser.parse_args(argv)

    _use_utf8()

    if not os.path.isfile(args.input):
        print("no such file: %s" % args.input, file=sys.stderr)
        return 2
    if os.path.abspath(args.input) == os.path.abspath(args.output):
        print("refusing to overwrite the original", file=sys.stderr)
        return 2
    try:
        target = parse_size(args.target)
    except ValueError:
        print("cannot read --target %r; try 200 Ko or 1,5 Mo" % args.target,
              file=sys.stderr)
        return 2

    result = shrink(args.input, args.output, target, args.min_dpi)

    if args.json:
        print(json.dumps(_payload(result, args.output)))
        return 0 if result.ok else 1

    print(os.path.basename(args.input))
    if result.ok:
        pct = 100 - result.size * 100 // result.before
        line = "  %s -> %s  (-%d%%)" % (
            format_size(result.before), format_size(result.size), pct)
        if result.dpi:
            line += "  at %d dpi" % result.dpi
        print(line)
        if result.check:
            print("  verified: no character altered (largest change %dpx)"
                  % result.check[0])
        print("  written: %s" % args.output)
        return 0

    print("  COULD NOT reach %s." % format_size(target))
    if result.reason == "digital_floor":
        print("  This is a digital text PDF; it is already near its floor.")
    elif result.reason == "already_minimal":
        print("  This file is already about as small as it can safely get;")
        print("  nothing on the ladder is meaningfully smaller than it.")
    elif result.best_safe_size:
        print("  Smallest safe size: %s (already written to %s)"
              % (format_size(result.best_safe_size), args.output))
    else:
        print("  Every setting that fits risks altering a character.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
