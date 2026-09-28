import argparse
import sys


def main(argv=None):
    p = argparse.ArgumentParser(prog="textkit")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("count")
    c.add_argument("path")
    args = p.parse_args(argv)
    try:
        with open(args.path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"textkit: {e}", file=sys.stderr)
        return 2
    print(len(text.splitlines()), len(text.split()), len(text))
    return 0


sys.exit(main())
