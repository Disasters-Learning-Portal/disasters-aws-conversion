#!/usr/bin/env python3
"""Create real GitHub issues from loe-poc/sample_issues.json via the `gh` CLI.

Each created issue is labeled so the whole batch is easy to find and clean up.
Use --dry-run first to preview. Requires `gh` to be authenticated.

Examples:
  python loe-poc/create_issues.py --dry-run
  python loe-poc/create_issues.py --limit 5
  python loe-poc/create_issues.py               # create all
Cleanup:
  gh issue list --label poc-loe --state open --json number -q '.[].number' \\
    | xargs -I{} gh issue close {}
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(__file__)


def gh_json(args):
    out = subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def default_repo():
    return gh_json(["repo", "view", "--json", "nameWithOwner"])["nameWithOwner"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=os.path.join(HERE, "sample_issues.json"))
    ap.add_argument("--repo", default=None, help="owner/name (default: current repo)")
    ap.add_argument("--limit", type=int, default=None, help="only create the first N")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "created_issues.json"),
                    help="write created {number,url,title} here")
    args = ap.parse_args()

    repo = args.repo or default_repo()
    with open(args.file, encoding="utf-8") as fh:
        issues = json.load(fh)
    if args.limit:
        issues = issues[:args.limit]

    print(f"Repo: {repo}  |  Issues to create: {len(issues)}  |  dry-run: {args.dry_run}")
    created = []
    for i, iss in enumerate(issues, 1):
        cmd = ["gh", "issue", "create", "--repo", repo,
               "--title", iss["title"], "--body", iss["body"]]
        for label in iss.get("labels", []):
            cmd += ["--label", label]
        if args.dry_run:
            print(f"[{i}/{len(issues)}] DRY-RUN would create: {iss['title']}")
            continue
        try:
            url = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()
        except subprocess.CalledProcessError as e:
            sys.exit(f"gh issue create failed for '{iss['title']}':\n{e.stderr}")
        num = url.rstrip("/").split("/")[-1]
        created.append({"number": int(num), "url": url, "title": iss["title"]})
        print(f"[{i}/{len(issues)}] created #{num}  {iss['title']}")

    if created:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(created, fh, indent=2)
        print(f"\nWrote {len(created)} created issues -> {os.path.relpath(args.out)}")


if __name__ == "__main__":
    main()
