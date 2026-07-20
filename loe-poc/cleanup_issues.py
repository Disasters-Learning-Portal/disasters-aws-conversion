#!/usr/bin/env python3
"""Close or DELETE the POC demo issues created by create_issues.py.

Tracks the exact issues via loe-poc/created_issues.json (written at creation
time); can also target every issue carrying the `poc-loe` label as a fallback.
Safe by default: prints what it would do unless --close or --delete is given.

Examples:
  python loe-poc/cleanup_issues.py                 # dry-run: list tracked issues
  python loe-poc/cleanup_issues.py --by-label      # dry-run against poc-loe label
  python loe-poc/cleanup_issues.py --close         # close the tracked issues
  python loe-poc/cleanup_issues.py --delete        # permanently delete them
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(__file__)


def gh_json(args):
    return json.loads(subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout)


def default_repo():
    return gh_json(["repo", "view", "--json", "nameWithOwner"])["nameWithOwner"]


def tracked_numbers(path):
    with open(path, encoding="utf-8") as fh:
        return [i["number"] for i in json.load(fh)]


def label_numbers(repo):
    data = gh_json(["issue", "list", "--repo", repo, "--label", "poc-loe",
                    "--state", "all", "--json", "number", "--limit", "500"])
    return [i["number"] for i in data]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=os.path.join(HERE, "created_issues.json"))
    ap.add_argument("--repo", default=None)
    ap.add_argument("--by-label", action="store_true", help="target the poc-loe label instead of the tracking file")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--close", action="store_true", help="close the issues")
    g.add_argument("--delete", action="store_true", help="permanently delete the issues")
    args = ap.parse_args()

    repo = args.repo or default_repo()
    if args.by_label:
        numbers = label_numbers(repo)
    elif os.path.exists(args.file):
        numbers = tracked_numbers(args.file)
    else:
        sys.exit(f"no tracking file at {args.file}; use --by-label")

    numbers = sorted(set(numbers))
    action = "delete" if args.delete else "close" if args.close else "dry-run"
    print(f"Repo: {repo}  |  Issues: {len(numbers)}  |  action: {action}")
    print("Numbers:", ", ".join(f"#{n}" for n in numbers))
    if action == "dry-run":
        print("\n(dry-run) pass --close or --delete to act.")
        return

    for n in numbers:
        cmd = ["gh", "issue", action, str(n), "--repo", repo]
        if args.delete:
            cmd.append("--yes")
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"{action}d #{n}")
        except subprocess.CalledProcessError as e:
            print(f"WARN could not {action} #{n}: {e.stderr.strip()}")


if __name__ == "__main__":
    main()
