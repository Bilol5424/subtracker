"""CLI entry point:  python -m subtracker [--host H] [--port P] [--db PATH]"""

import argparse

from .server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Self-hosted subscription tracker")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=None, help="path to SQLite file")
    args = parser.parse_args()
    serve(host=args.host, port=args.port, db=args.db)


if __name__ == "__main__":
    main()
