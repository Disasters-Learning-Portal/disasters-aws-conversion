#!/usr/bin/env python3
"""Add + populate the Project / Initiative / Team single-select fields on the POC board.

The POC board (kyle-lesinger/projects/1) originally carried only Program Increment +
Start/End dates. The dashboard's Capacity Matrix groups by these three fields, so this
script:

  1. Creates the three SINGLE_SELECT fields (idempotent — reuses a field if it already
     exists), with options taken from the demo assignment.
  2. Sets each demo item's value from the deterministic `project` block in
     loe-poc/sample_issues.json. Mapping is by creation order:
     sample_issues.json[i] <-> created_issues.json[i] (issue 10+i), same as setup_project.py.

Only the three board fields are touched — issue titles/bodies are left alone (so the LOE
tables / report numbers are unchanged). The grouping values are index-deterministic, so
they're stable regardless of the sample's random draws.

Re-run safe. `--dry-run` previews; `--limit N` does a batch.
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
# Board field name -> key in the sample's `project` block.
FIELD_KEYS = {"Project": "project", "Initiative": "initiative", "Team": "team"}


def gh(args, retries=4):
    """Run a gh command, retrying transient network/5xx errors with backoff."""
    for attempt in range(1, retries + 1):
        r = subprocess.run(["gh", *args], capture_output=True, text=True)
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


def field_list():
    return gh_json(["project", "field-list", str(PROJECT_NUMBER), "--owner", OWNER,
                    "--format", "json", "--limit", "100"]).get("fields", [])


def ensure_field(name, options, dry):
    """Return {id, options:{name->id}} for the single-select field, creating it if absent."""
    by_name = {f["name"]: f for f in field_list()}
    if name not in by_name:
        if dry:
            print(f"DRY create SINGLE_SELECT field {name!r} with {len(options)} options")
            return None
        gh(["project", "field-create", str(PROJECT_NUMBER), "--owner", OWNER, "--name", name,
            "--data-type", "SINGLE_SELECT", "--single-select-options", ",".join(options)])
        by_name = {f["name"]: f for f in field_list()}
    f = by_name[name]
    return {"id": f["id"], "options": {o["name"]: o["id"] for o in f.get("options", [])}}


def existing_items():
    data = gh_json(["project", "item-list", str(PROJECT_NUMBER), "--owner", OWNER,
                    "--format", "json", "--limit", "800"])
    out = {}
    for it in data.get("items", []):
        num = (it.get("content") or {}).get("number")
        if num is not None:
            out[num] = it["id"]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    samples = json.load(open(os.path.join(HERE, "sample_issues.json"), encoding="utf-8"))
    created = json.load(open(os.path.join(HERE, "created_issues.json"), encoding="utf-8"))
    if len(samples) != len(created):
        sys.exit(f"mismatch: {len(samples)} samples vs {len(created)} created issues")

    project_id = gh_json(["project", "view", str(PROJECT_NUMBER), "--owner", OWNER, "--format", "json"])["id"]

    field_defs = {}
    for name, key in FIELD_KEYS.items():
        options = sorted({s["project"][key] for s in samples})
        field_defs[name] = ensure_field(name, options, args.dry_run)
        fid = "DRY" if args.dry_run else field_defs[name]["id"]
        print(f"field {name}: {fid}  ({len(options)} options: {', '.join(options)})")

    pairs = list(zip(samples, created))
    if args.limit:
        pairs = pairs[:args.limit]

    if args.dry_run:
        for s, c in pairs[:10]:
            p = s["project"]
            print(f"DRY #{c['number']} -> Project={p['project']} | Initiative={p['initiative']} | Team={p['team']}")
        return

    on_board = existing_items()
    done = 0
    for s, c in pairs:
        num = c["number"]
        item_id = on_board.get(num)
        if not item_id:
            print(f"skip #{num}: not on board")
            continue
        p = s["project"]
        for name, key in FIELD_KEYS.items():
            fd = field_defs[name]
            opt = fd["options"].get(p[key])
            if not opt:
                print(f"  WARN #{num} {name}: no option for {p[key]!r}")
                continue
            gh(["project", "item-edit", "--project-id", project_id, "--id", item_id,
                "--field-id", fd["id"], "--single-select-option-id", opt])
        done += 1
        print(f"OK #{num} -> Project={p['project']} | Initiative={p['initiative']} | Team={p['team']}")

    print(f"\nSet grouping fields on {done} items.")


if __name__ == "__main__":
    main()
