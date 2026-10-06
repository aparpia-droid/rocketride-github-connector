import argparse
import json
import os
import sys

import connector


def main(argv=None):
    parser = argparse.ArgumentParser(description="GitHub open-issue snapshot connector")
    parser.add_argument("command", choices=["import", "read"])
    parser.add_argument("repo", help="owner/name, for example facebook/react")
    parser.add_argument("--db", help="SQLite file (default: $RR_DB_PATH, then ./issues.db)")
    args = parser.parse_args(argv)

    db_path = args.db or os.environ.get("RR_DB_PATH") or "./issues.db"
    if args.command == "import":
        result = connector.import_issues(args.repo, db_path)
    else:
        result = connector.read_issues(args.repo, db_path)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
