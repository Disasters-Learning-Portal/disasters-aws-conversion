#!/usr/bin/env python3
"""Wire the POC demo issues into the POC project board.

For each issue (zipped by creation order: sample_issues.json[i] <-> created_issues.json[i]):
  1. gh issue edit  -> replace title/body with the PI-less version (PI/dates move to the board)
  2. gh project item-add -> add the issue to the POC project
  3. gh project item-edit -> set Program Increment (single-select), Start Date, End Date

Field IDs/options are discovered at runtime. Progress is persisted to
loe-poc/project_items.json so the script is resumable/idempotent (already-wired
issues are skipped). Use --dry-run to preview and --limit N to do a batch.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(__file__)
OWNER = "kyle-lesinger"
PROJECT_NUMBER = 1


def gh(args, capture=True, retries=4):
    """Run a gh command, retrying transient network/5xx errors with backoff."""
    for attempt in range(1, retries + 1):
        r = subprocess.run(["gh", *args], capture_output=capture, text=True)
        if r.returncode == 0:
            return r.stdout
        err = r.stderr or ""
        transient = any(s in err.lower() for s in
                        ("timed out", "timeout", "connection reset", "eof",
                         "502", "503", "temporarily", "i/o timeout"))
        if transient and attempt < retries:
            time.sleep(2 * attempt)
            continue
        raise RuntimeError(f"gh {' '.join(args)}\n{err}")
    raise RuntimeError(f"gh {' '.join(args)}: exhausted retries")


def gh_json(args):
    return json.loads(gh(args))


def existing_items():
    """Map issue number -> project item id for items already on the board."""
    data = gh_json(["project", "item-list", str(PROJECT_NUMBER), "--owner", OWNER,
                    "--format", "json", "--limit", "800"])
    out = {}
    for it in data.get("items", []):
        num = (it.get("content") or {}).get("number")
        if num is not None:
            out[num] = it["id"]
    return out


def discover_fields():
    proj = gh_json(["project", "view", str(PROJECT_NUMBER), "--owner", OWNER, "--format", "json"])
    fields = gh_json(["project", "field-list", str(PROJECT_NUMBER), "--owner", OWNER,
                      "--format", "json"]).get("fields", [])
    by_name = {f["name"]: f for f in fields}
    pi = by_name["Program Increment"]
    return {
        "project_id": proj["id"],
        "pi_field": pi["id"],
        "pi_options": {o["name"]: o["id"] for o in pi.get("options", [])},
        "start_field": by_name["Start Date"]["id"],
        "end_field": by_name["End Date"]["id"],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--state", default=os.path.join(HERE, "project_items.json"))
    args = ap.parse_args()

    repo = args.repo or gh_json(["repo", "view", "--json", "nameWithOwner"])["nameWithOwner"]
    samples = json.load(open(os.path.join(HERE, "sample_issues.json"), encoding="utf-8"))
    created = json.load(open(os.path.join(HERE, "created_issues.json"), encoding="utf-8"))
    if len(samples) != len(created):
        sys.exit(f"mismatch: {len(samples)} samples vs {len(created)} created issues")

    done = json.load(open(args.state, encoding="utf-8")) if os.path.exists(args.state) else {}
    fields = None if args.dry_run else discover_fields()
    # reuse items already on the board so a resume never creates duplicates
    on_board = {} if args.dry_run else existing_items()
    if fields:
        print(f"project_id={fields['project_id']}  pi_options={fields['pi_options']}  on_board={len(on_board)}")

    todo = [(s, c) for s, c in zip(samples, created) if str(c["number"]) not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"Repo: {repo} | to wire: {len(todo)} | already done: {len(done)} | dry-run: {args.dry_run}\n")

    for i, (s, c) in enumerate(todo, 1):
        num, url, proj = c["number"], c["url"], s["project"]
        tag = f"[{i}/{len(todo)}] #{num} {s['title'][:48]}"
        if args.dry_run:
            print(f"DRY {tag}  -> PI {proj['pi']} {proj['start']}..{proj['end']}")
            continue

        gh(["issue", "edit", str(num), "--repo", repo, "--title", s["title"], "--body", s["body"]])
        item_id = on_board.get(num)
        if not item_id:
            item = gh_json(["project", "item-add", str(PROJECT_NUMBER), "--owner", OWNER,
                            "--url", url, "--format", "json"])
            item_id = item["id"]
        opt = fields["pi_options"].get(proj["pi"])
        if opt:
            gh(["project", "item-edit", "--project-id", fields["project_id"], "--id", item_id,
                "--field-id", fields["pi_field"], "--single-select-option-id", opt])
        gh(["project", "item-edit", "--project-id", fields["project_id"], "--id", item_id,
            "--field-id", fields["start_field"], "--date", proj["start"]])
        gh(["project", "item-edit", "--project-id", fields["project_id"], "--id", item_id,
            "--field-id", fields["end_field"], "--date", proj["end"]])

        done[str(num)] = {"item_id": item_id, "pi": proj["pi"],
                          "start": proj["start"], "end": proj["end"]}
        json.dump(done, open(args.state, "w"), indent=2)
        print(f"OK  {tag}  -> PI {proj['pi']}")

    print(f"\nWired total: {len(done)}  (state: {os.path.relpath(args.state)})")


if __name__ == "__main__":
    main()
