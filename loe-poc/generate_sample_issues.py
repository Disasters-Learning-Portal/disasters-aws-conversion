#!/usr/bin/env python3
"""Deterministically generate N varied "Objective" issues for the LOE POC.

PI and the objective window (Start/End) live on the PROJECT BOARD, not in the
issue body. So each generated record has:
  - body: Context + LOE/FTE table only (no PI / no timeline text)
  - project: {pi, pi_start, pi_end, start, end}  -> used to set project fields
             and to drive offline report testing

Writes loe-poc/sample_issues.json (schema: number,title,url,state,body,labels,
project). Seeded for reproducibility so reports diff cleanly across runs.

Variety: 2 real PIs (26.4 current, 27.2 next), 1-5 people/ticket, mixed roles &
FTE, ~30% partial-window objectives, a few empty LOE tables, a few edge rows
(invalid role / non-numeric FTE).
"""
import argparse
import datetime
import json
import os
import random

# Real Program Increments from the Disasters Learning Portal board.
PIS = [
    ("PI 26.4", datetime.date(2026, 7, 12), datetime.date(2026, 10, 17)),
    ("PI 27.2", datetime.date(2026, 10, 18), datetime.date(2027, 1, 16)),
]

ROSTER = [
    ("Alice Nguyen", "PM"), ("Sofia Rossi", "PM"),
    ("Bob Martinez", "Backend"), ("Nadia Hassan", "Backend"),
    ("Carla Diaz", "Geospatial"), ("Owen Clark", "Geospatial"),
    ("Devon Lee", "Frontend"), ("Rae Thompson", "Frontend"),
    ("Priya Patel", "Data Curator"), ("Liam Walsh", "Data Curator"),
    ("Sam Okoro", "ML"), ("Yuki Tanaka", "ML"),
    ("Jordan Kim", "Designer"), ("Elena Petrova", "Designer"),
    ("Taylor Brooks", "Comms"),
    ("Morgan Reyes", "Jupyterhub"),
]

TEAM_TAGS = ["PM", "Frontend", "Backend", "Geospatial", "Data Curator", "Comms", "ML", "Designer", "Jupyterhub"]

TOPICS = [
    "COG pipeline hardening", "S3 ingestion API v2", "Disaster dashboard redesign",
    "Flood extent model", "CSDA catalog automation", "Stakeholder reporting portal",
    "Notebook environment upgrade", "Reprojection service scaling", "Auth & access control",
    "Data QA automation", "Tile server migration", "Metadata schema v3",
    "Alerting pipeline", "Cloud cost monitoring", "Wildfire severity model",
    "Public API documentation", "Onboarding revamp", "STAC catalog buildout",
    "Imagery mosaicking", "Latency profiling", "Nodata standardization",
    "Hurricane track ingestion", "Access log analytics", "Model retraining harness",
    "Colormap library", "Region-of-interest tooling", "Backfill orchestration",
    "Vector tile support", "Search relevance tuning", "Incident runbook automation",
]

FTES = [0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.75, 0.8, 1.0]
BAD_ROWS = [("Chris DevOps", "DevOps", "0.3"), ("Pat Analyst", "Analyst", "0.2"),
            ("Jamie Ops", "Backend", "TBD")]


def body_for(topic, rows):
    parts = [
        "## Context", "",
        "### Motivation",
        f"Deliver **{topic}** to support the Disasters program during this PI.", "",
        "### Description",
        f"Scope, milestones, and dependencies for {topic.lower()}.", "",
        "### Examples & Concept Diagrams (If applicable)", "",
        "## Success Criteria",
        "- [ ] Design reviewed and approved",
        "- [ ] Implementation merged and deployed", "",
        "## Risks",
        "- Dependency slippage; mitigate with early integration checkpoints.", "",
        "## LOE/FTE",
        "<!-- PI and Start/End dates live on the project board, not here. -->",
        "| Person | Role | FTE | Notes |",
        "| ------ | ---- | --- | ----- |",
    ]
    return "\n".join(parts + rows)


def make_rows(rng, kind):
    if kind == "empty":
        return ["|  |  |  |  |"]
    n = rng.randint(1, 5)
    rows = [f"| {name} | {role} | {rng.choice(FTES)} | — |" for name, role in rng.sample(ROSTER, n)]
    if kind == "edge":
        bad = rng.choice(BAD_ROWS)
        rows.append(f"| {bad[0]} | {bad[1]} | {bad[2]} | — |")
    return rows


def partial_window(rng, pi_start, pi_end):
    total = (pi_end - pi_start).days
    offset = rng.randint(0, max(1, total // 2))
    length = rng.randint(max(7, total // 4), max(8, total * 3 // 4))
    start = pi_start + datetime.timedelta(days=offset)
    end = min(pi_end, start + datetime.timedelta(days=length))
    return start, end


def generate(count, seed):
    rng = random.Random(seed)
    empties = {8, 21, 37, 46}
    edges = {13, 29, 44}
    assignments = sorted(rng.choices(range(len(PIS)), weights=[0.6, 0.4], k=count))

    issues = []
    for i in range(1, count + 1):
        pi_title, pi_start, pi_end = PIS[assignments[i - 1]]
        topic = TOPICS[(i - 1) % len(TOPICS)]
        team = rng.choice(TEAM_TAGS)
        title = f"[{team}]-[Objective {i}]: {topic}"

        if (i not in empties) and (rng.random() < 0.30):
            obj_start, obj_end = partial_window(rng, pi_start, pi_end)
        else:
            obj_start, obj_end = pi_start, pi_end

        kind = "empty" if i in empties else ("edge" if i in edges else "normal")
        body = body_for(topic, make_rows(rng, kind))
        issues.append({
            "number": i, "title": title, "url": "", "state": "open",
            "body": body, "labels": ["Objective", "poc-loe"],
            "project": {
                "pi": pi_title,
                "pi_start": pi_start.isoformat(), "pi_end": pi_end.isoformat(),
                "start": obj_start.isoformat(), "end": obj_end.isoformat(),
            },
        })
    return issues


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "sample_issues.json"))
    args = ap.parse_args()
    issues = generate(args.count, args.seed)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(issues, fh, indent=2, ensure_ascii=False)
    print(f"Wrote {len(issues)} sample issues -> {os.path.relpath(args.out)}")


if __name__ == "__main__":
    main()
