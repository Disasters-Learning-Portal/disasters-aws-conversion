#!/usr/bin/env python3
"""Generate an LOE/FTE capacity report from "Objective" issues on a project board.

The Program Increment (PI) and each objective's Start/End dates live on the
GitHub **project board**, not in the issue body. The LOE/FTE staffing table lives
in the issue body. This script joins the two.

Capacity rule: raw FTE is summed **per person, per PI**; > 1.0 in a PI =
over-allocated. Objectives may cover only part of a PI (their Start/End inside the
PI window), so a duration-**weighted FTE** = fte x (objective days in PI / PI days)
is reported alongside. Over-allocation is flagged on the RAW sum (the stated rule).

Inputs (pick one):
  --project-json FILE   `gh project item-list <n> --format json` output (CI/live)
  --issues-json  FILE   sample_issues.json (offline; PI/dates from its `project`
                        block, else parsed from the body as a fallback)
  --from-dir     DIR    markdown fixtures (PI/dates parsed from the body)

Options:
  --pi "PI 26.4"        only report this PI ("calculate by PI"); default = all
  --out-dir, --now

Writes reports/loe_allocations.csv, loe_by_person.csv, loe_by_role.csv,
loe_summary.md. Standard library only; deterministic ordering for clean diffs.
"""
import argparse
import csv
import datetime
import glob
import json
import os
import re
import sys
from collections import defaultdict

ALLOWED_ROLES = [
    "PM", "Frontend", "Backend", "Geospatial", "Data Curator",
    "Comms", "ML", "Designer", "Jupyterhub",
]
ROLE_LOOKUP = {r.lower().replace(" ", ""): r for r in ALLOWED_ROLES}
ROLE_ORDER = {r: i for i, r in enumerate(ALLOWED_ROLES)}

OVER_ALLOCATION_THRESHOLD = 1.0
UNSPECIFIED_PI = "Unspecified"
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# PI calendar for single-select PI fields (the POC board). The live board uses a
# real iteration field whose window travels with the value, so this is only a
# fallback for boards that model PI as a single-select. Source: Disasters
# Learning Portal iteration config.
PI_WINDOWS = {
    "PI 26.4": (datetime.date(2026, 7, 12), datetime.date(2026, 10, 17)),
    "PI 27.2": (datetime.date(2026, 10, 18), datetime.date(2027, 1, 16)),
}


def parse_date(s):
    m = DATE_RE.search(s or "")
    if not m:
        return None
    try:
        return datetime.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def norm_pi(s):
    return re.sub(r"^pi\s*", "", (s or "").strip().lower()).replace(" ", "")


def is_objective(title):
    return "objective" in (title or "").lower()


def is_open(state):
    return (state or "open").lower() == "open"


# ---- body parsing (LOE table always; PI/dates only as a fallback) ----

def find_field(body, key):
    m = re.search(rf"^\s*[-*]?\s*{key}\s*:\s*(.+?)\s*$", body or "", re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else ""


def enrich_from_body(iss):
    """Fill pi_*/obj_* from `PI:`/`Window:`/`Start:`/`End:` lines if not already set."""
    if iss.get("pi_title"):
        return
    raw = find_field(iss["body"], "PI")
    iss["pi_title"] = ("PI " + re.sub(r"^PI\s*", "", raw, flags=re.IGNORECASE).strip()) if raw else UNSPECIFIED_PI
    dates = DATE_RE.findall(find_field(iss["body"], "Window"))
    iss["pi_start"] = parse_date(dates[0]) if dates else None
    iss["pi_end"] = parse_date(dates[1]) if len(dates) > 1 else None
    iss["obj_start"] = parse_date(find_field(iss["body"], "Start"))
    iss["obj_end"] = parse_date(find_field(iss["body"], "End"))


def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_separator_row(cells):
    return any(cells) and all(re.fullmatch(r":?-{1,}:?", c or "") for c in cells)


def extract_loe_rows(body):
    lines = (body or "").splitlines()
    start = next((i + 1 for i, ln in enumerate(lines)
                  if re.match(r"^\s*#{1,6}\s*LOE\b", ln, re.IGNORECASE)), None)
    if start is None:
        return None
    rows = []
    for line in lines[start:]:
        stripped = line.strip()
        if re.match(r"^\s*#{1,6}\s+", line):
            break
        if not stripped:
            if rows:
                break
            continue
        if stripped.startswith("|"):
            rows.append(split_row(line))
    return rows


def parse_table(rows):
    allocations, warnings = [], []
    if not rows:
        return allocations, warnings
    header, body_rows = None, rows
    joined = " ".join(c.lower() for c in rows[0])
    if "person" in joined and "role" in joined:
        header = [c.lower() for c in rows[0]]
        body_rows = rows[1:]

    def col(name, default):
        return header.index(name) if header and name in header else default

    ci_person, ci_role, ci_fte, ci_notes = col("person", 0), col("role", 1), col("fte", 2), col("notes", 3)
    for cells in body_rows:
        if is_separator_row(cells):
            continue
        get = lambda i: cells[i] if i < len(cells) else ""
        person, role_raw, fte_raw, notes = get(ci_person), get(ci_role), get(ci_fte), get(ci_notes)
        if not person and not role_raw and not fte_raw:
            continue
        if not person:
            warnings.append(f"row missing person: {cells}")
            continue
        role = ROLE_LOOKUP.get(role_raw.lower().replace(" ", ""))
        if role is None:
            warnings.append(f"invalid role '{role_raw}' for '{person}' (row skipped)")
            continue
        try:
            fte = float(fte_raw)
        except (ValueError, TypeError):
            warnings.append(f"non-numeric FTE '{fte_raw}' for '{person}' (row skipped)")
            continue
        allocations.append({"person": person, "role": role, "fte": fte, "notes": notes})
    return allocations, warnings


# ---- input loaders (all return the normalized issue schema) ----

def _pi_from_value(value):
    """Normalize a project 'Program Increment' value (iteration dict or select str)."""
    if isinstance(value, dict):  # iteration field
        title = value.get("title") or UNSPECIFIED_PI
        start = parse_date(value.get("startDate"))
        dur = value.get("duration")
        end = start + datetime.timedelta(days=int(dur) - 1) if (start and dur) else None
        if not end:
            _, end = PI_WINDOWS.get(title, (None, None))
        return title, start, end
    title = (value or "").strip() or UNSPECIFIED_PI  # single-select string
    start, end = PI_WINDOWS.get(title, (None, None))
    return title, start, end


def _item_field(item, name):
    target = name.lower().replace(" ", "")
    for k, v in item.items():
        if k.lower().replace(" ", "") == target:
            return v
    return None


def load_project_items(path):
    data = json.load(open(path, encoding="utf-8"))
    items = data.get("items", data if isinstance(data, list) else [])
    issues = []
    for it in items:
        content = it.get("content") or {}
        if content.get("type") not in (None, "Issue"):
            continue
        pi_title, pi_start, pi_end = _pi_from_value(_item_field(it, "program increment"))
        issues.append({
            "number": content.get("number"),
            "title": content.get("title", ""),
            "url": content.get("url", ""),
            "state": "open",
            "body": content.get("body", "") or "",
            "pi_title": pi_title, "pi_start": pi_start, "pi_end": pi_end,
            "obj_start": parse_date(_item_field(it, "start date")),
            "obj_end": parse_date(_item_field(it, "end date")),
        })
    return issues


def load_issues_json(path):
    issues = []
    for it in json.load(open(path, encoding="utf-8")):
        rec = {"number": it.get("number"), "title": it.get("title", ""),
               "url": it.get("url", ""), "state": it.get("state", "open"),
               "body": it.get("body", "") or ""}
        proj = it.get("project")
        if proj:
            rec.update({"pi_title": proj.get("pi", UNSPECIFIED_PI),
                        "pi_start": parse_date(proj.get("pi_start")),
                        "pi_end": parse_date(proj.get("pi_end")),
                        "obj_start": parse_date(proj.get("start")),
                        "obj_end": parse_date(proj.get("end"))})
        issues.append(rec)
    return issues


def load_from_dir(path):
    issues = []
    for p in sorted(glob.glob(os.path.join(path, "*.md"))):
        text = open(p, encoding="utf-8").read()
        meta = {}
        if text.startswith("---"):
            lines = text.splitlines()
            end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
            if end is not None:
                for line in lines[1:end]:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip().strip('"').strip("'")
                text = "\n".join(lines[end + 1:])
        m = re.search(r"(\d+)", os.path.basename(p))
        issues.append({"number": int(m.group(1)) if m else None,
                       "title": meta.get("title", os.path.basename(p)),
                       "url": f"(local) {os.path.relpath(p)}", "state": "open", "body": text})
    return issues


def load_issues(args):
    if args.project_json:
        return load_project_items(args.project_json)
    if args.issues_json:
        return load_issues_json(args.issues_json)
    if args.from_dir:
        return load_from_dir(args.from_dir)
    sys.exit("error: provide --project-json, --issues-json, or --from-dir")


# ---- aggregation ----

def pi_fraction(obj_start, obj_end, pi_start, pi_end):
    if not (pi_start and pi_end) or pi_end < pi_start or not (obj_start and obj_end):
        return 1.0
    lo, hi = max(obj_start, pi_start), min(obj_end, pi_end)
    overlap = (hi - lo).days + 1
    return max(0.0, min(1.0, overlap / ((pi_end - pi_start).days + 1)))


def new_pi_bucket():
    return {"window": "", "objectives": [], "allocations": [], "missing_loe": [], "partial": [],
            "by_person": defaultdict(lambda: {"fte": 0.0, "wfte": 0.0, "issues": set(), "roles": set()}),
            "by_role": defaultdict(lambda: {"fte": 0.0, "wfte": 0.0, "people": set(), "count": 0})}


def build_report(issues, pi_filter=None):
    objectives = [i for i in issues if is_objective(i["title"]) and is_open(i["state"])]
    for iss in objectives:
        enrich_from_body(iss)
    if pi_filter:
        objectives = [i for i in objectives if norm_pi(i.get("pi_title")) == norm_pi(pi_filter)]

    pis = defaultdict(new_pi_bucket)
    warnings = []
    for iss in objectives:
        pi_id = iss.get("pi_title") or UNSPECIFIED_PI
        b = pis[pi_id]
        if iss.get("pi_start") and iss.get("pi_end") and not b["window"]:
            b["window"] = f"{iss['pi_start'].isoformat()} to {iss['pi_end'].isoformat()}"
        b["objectives"].append(iss)
        frac = pi_fraction(iss.get("obj_start"), iss.get("obj_end"), iss.get("pi_start"), iss.get("pi_end"))
        if frac < 1.0:
            b["partial"].append(iss)

        rows = extract_loe_rows(iss["body"])
        allocs, warns = parse_table(rows) if rows is not None else ([], [])
        for w in warns:
            warnings.append(f"#{iss['number']} ({pi_id}): {w}")
        if not allocs:
            b["missing_loe"].append(iss)
            continue
        for a in allocs:
            wfte = r2(a["fte"] * frac)
            b["allocations"].append({**a, "issue": iss, "obj_start": iss.get("obj_start"),
                                     "obj_end": iss.get("obj_end"), "fraction": frac, "wfte": wfte})
            p = b["by_person"][a["person"]]
            p["fte"] += a["fte"]; p["wfte"] += wfte; p["issues"].add(iss["number"]); p["roles"].add(a["role"])
            r = b["by_role"][a["role"]]
            r["fte"] += a["fte"]; r["wfte"] += wfte; r["people"].add(a["person"]); r["count"] += 1

    ordered = sorted(pis.items(), key=lambda kv: (kv[0] == UNSPECIFIED_PI, kv[0]))
    return {"objectives": objectives, "warnings": warnings, "pis": ordered, "pi_filter": pi_filter}


def r2(x):
    return round(x + 0.0, 2)


def over(bucket):
    xs = [(p, d["fte"]) for p, d in bucket["by_person"].items() if d["fte"] > OVER_ALLOCATION_THRESHOLD]
    return sorted(xs, key=lambda t: (-t[1], t[0]))


def d2s(d):
    return d.isoformat() if d else ""


def write_csvs(rep, out_dir):
    with open(os.path.join(out_dir, "loe_allocations.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["pi", "pi_window", "issue_number", "issue_title", "issue_url",
                    "person", "role", "fte", "obj_start", "obj_end", "pi_fraction", "weighted_fte"])
        for pi_id, b in rep["pis"]:
            for a in sorted(b["allocations"], key=lambda a: (a["issue"]["number"] or 0, a["person"])):
                w.writerow([pi_id, b["window"], a["issue"]["number"], a["issue"]["title"],
                            a["issue"]["url"], a["person"], a["role"], r2(a["fte"]),
                            d2s(a["obj_start"]), d2s(a["obj_end"]), r2(a["fraction"]), r2(a["wfte"])])

    with open(os.path.join(out_dir, "loe_by_person.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["pi", "person", "total_fte", "weighted_fte", "num_objectives", "roles", "over_allocated"])
        for pi_id, b in rep["pis"]:
            for person in sorted(b["by_person"]):
                d = b["by_person"][person]
                roles = ";".join(sorted(d["roles"], key=lambda r: ROLE_ORDER.get(r, 99)))
                w.writerow([pi_id, person, r2(d["fte"]), r2(d["wfte"]), len(d["issues"]), roles,
                            str(d["fte"] > OVER_ALLOCATION_THRESHOLD).lower()])

    with open(os.path.join(out_dir, "loe_by_role.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["pi", "role", "total_fte", "weighted_fte", "num_people", "num_allocations"])
        for pi_id, b in rep["pis"]:
            for role in sorted(b["by_role"], key=lambda r: ROLE_ORDER.get(r, 99)):
                d = b["by_role"][role]
                w.writerow([pi_id, role, r2(d["fte"]), r2(d["wfte"]), len(d["people"]), d["count"]])


def render_summary(rep, now):
    total_fte = sum(a["fte"] for _, b in rep["pis"] for a in b["allocations"])
    missing = sum(len(b["missing_loe"]) for _, b in rep["pis"])
    partial = sum(len(b["partial"]) for _, b in rep["pis"])
    over_pairs = sum(len(over(b)) for _, b in rep["pis"])

    scope = f" — PI filter: {rep['pi_filter']}" if rep.get("pi_filter") else ""
    L = ["# LOE / FTE Capacity Report" + scope, "", f"_Generated: {now}_",
         "_Raw FTE summed per person **per PI**; > 1.0 = over-allocated. "
         "Weighted FTE adjusts for objectives that cover only part of the PI._", ""]
    L += ["## Headline",
          f"- **Open Objective tickets:** {len(rep['objectives'])}",
          f"- **Program Increments (PIs):** {len(rep['pis'])}",
          f"- **Partial-window objectives:** {partial}",
          f"- **Missing / empty LOE:** {missing}",
          f"- **Total allocated FTE (raw):** {r2(total_fte)}",
          f"- **Over-allocated (person, PI) pairs:** {over_pairs}", ""]

    for pi_id, b in rep["pis"]:
        window = f" — {b['window']}" if b["window"] else ""
        pi_raw = sum(a["fte"] for a in b["allocations"])
        pi_w = sum(a["wfte"] for a in b["allocations"])
        L += [f"## {pi_id}{window}",
              f"- Objectives: {len(b['objectives'])} | People: {len(b['by_person'])} "
              f"| Raw FTE: {r2(pi_raw)} | Weighted FTE: {r2(pi_w)} "
              f"| Partial: {len(b['partial'])} | Missing LOE: {len(b['missing_loe'])}", ""]
        ov = over(b)
        L.append("**Over-allocated this PI:** " +
                 (", ".join(f"{p} ({r2(f)})" for p, f in ov) if ov else "_none_"))
        L.append("")
        L += ["| Person | Raw FTE | Weighted FTE | Objectives | Roles | Over-allocated |",
              "| --- | --- | --- | --- | --- | --- |"]
        for person in sorted(b["by_person"]):
            d = b["by_person"][person]
            roles = ";".join(sorted(d["roles"], key=lambda r: ROLE_ORDER.get(r, 99)))
            flag = "⚠️ yes" if d["fte"] > OVER_ALLOCATION_THRESHOLD else "no"
            L.append(f"| {person} | {r2(d['fte'])} | {r2(d['wfte'])} | {len(d['issues'])} | {roles} | {flag} |")
        L.append("")
        L += ["| Role | Raw FTE | Weighted FTE | People | Allocations |", "| --- | --- | --- | --- | --- |"]
        for role in sorted(b["by_role"], key=lambda r: ROLE_ORDER.get(r, 99)):
            d = b["by_role"][role]
            L.append(f"| {role} | {r2(d['fte'])} | {r2(d['wfte'])} | {len(d['people'])} | {d['count']} |")
        L.append("")

        # Clickable objective list — jump straight back to each ticket. Link only
        # the "#N" so brackets in the title can't break the markdown link.
        per_obj = defaultdict(lambda: {"fte": 0.0, "people": set()})
        for a in b["allocations"]:
            e = per_obj[a["issue"]["number"]]
            e["fte"] += a["fte"]; e["people"].add(a["person"])
        L.append("### Objectives (click to open)")
        for iss in sorted(b["objectives"], key=lambda i: (i["number"] or 0)):
            n = iss["number"]
            link = f"[#{n}]({iss['url']})" if iss.get("url") else f"#{n}"
            e = per_obj.get(n)
            extra = f"{len(e['people'])} ppl · {r2(e['fte'])} FTE" if e else "⚠️ no LOE table"
            L.append(f"- {link} — {iss['title']} — {extra}")
        L.append("")

    if rep["warnings"]:
        L.append("## Warnings")
        L += [f"- {w}" for w in rep["warnings"]]
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-json", help="`gh project item-list --format json` output")
    ap.add_argument("--issues-json", help="sample_issues.json (offline)")
    ap.add_argument("--from-dir", help="Directory of markdown fixtures")
    ap.add_argument("--pi", default=None, help="Only report this PI (e.g. 'PI 26.4')")
    ap.add_argument("--out-dir", default="reports")
    ap.add_argument("--now", default="unknown")
    args = ap.parse_args()

    issues = load_issues(args)
    rep = build_report(issues, pi_filter=args.pi)
    os.makedirs(args.out_dir, exist_ok=True)
    write_csvs(rep, args.out_dir)
    summary = render_summary(rep, args.now)
    with open(os.path.join(args.out_dir, "loe_summary.md"), "w", encoding="utf-8") as fh:
        fh.write(summary + "\n")
    print(summary)


if __name__ == "__main__":
    main()
