#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from .freeze import DEFAULT_TEST, DEFAULT_VAL
from .rows import SPLITS, index_rows, read_rows

STAGES = ("rgb", "ground_truth", "relations", "shape", "coco")

VIEWS_PER_ROOM = 4
RENDER_EVIDENCE = ("The panorama renderer could not place the required cameras "
                   "or finish the views for this room.")


def exclusion_policy(splits_dir):
    return json.loads((Path(splits_dir) / "excluded_rooms.json").read_text(encoding="utf-8"))


def split_rows(splits_dir):
    rows = []
    for split in SPLITS:
        for room_id in (Path(splits_dir) / (split+".txt")).read_text().splitlines():
            if Path(room_id).is_absolute() or ".." in Path(room_id).parts or len(Path(room_id).parts) != 2:
                raise ValueError("Invalid frozen room ID")
            rows.append({"room_id": room_id, "house_id": room_id.split("/")[0], "split": split})
    index_rows(rows)
    return sorted(rows, key=lambda r: (r["split"], r["room_id"]))


def frozen_rooms(splits_dir):
    rows = split_rows(splits_dir)
    policy = exclusion_policy(splits_dir)
    excluded = {row["room_id"] for row in policy["rooms"]}
    if len(excluded) != len(policy["rooms"]):
        raise ValueError("The reviewed exclusions name a room twice")
    if len(rows) != policy["expected_retained_rooms"] or set(index_rows(rows)) & excluded:
        raise ValueError("Frozen split is inconsistent with the reviewed exclusions")
    return rows


def write_experiment_split(root, splits_dir, rows):
    for split in SPLITS:
        shutil.copyfile(Path(splits_dir) / (split+".txt"), root / "splits" / (split+".txt"))
    (root / "splits/rooms.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
    policy = exclusion_policy(splits_dir)
    (root / "splits/excluded_rooms.jsonl").write_text(
        "".join(json.dumps(r)+"\n" for r in policy["rooms"]))
    return policy


def initialize(scene_root, root, splits_dir):
    if root.exists():
        raise FileExistsError("Use a new experiment directory")
    scene_root = scene_root.resolve()
    rows = frozen_rooms(splits_dir)
    from ..render.room_layout import recover_layout
    for row in rows:
        room = scene_root / row["room_id"]
        layout = recover_layout(room)
        height = layout["ceiling_z"]-layout["floor_z"]
        row.update(room_dir=str(room), min_clearance=min(0.1, 0.04*height))
    for name in ("splits", "source", "outputs", "state"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "source/rooms").symlink_to(scene_root, target_is_directory=True)
    policy = write_experiment_split(root, splits_dir, rows)
    (root / "splits/summary.json").write_text(json.dumps({
        "room_counts": {s: sum(r["split"] == s for r in rows) for s in SPLITS},
        "house_disjoint": True, "excluded_rooms": len(policy["rooms"]),
        "expected_panoramas": len(rows)*VIEWS_PER_ROOM,
        "source_root": str(scene_root), "policy_id": policy["policy_id"]}, indent=2)+"\n")
    print("Initialized %d rooms with frozen house-disjoint splits; source GLBs unchanged"
          % len(rows))


def refresh_experiment(root, splits_dir):
    rows = frozen_rooms(splits_dir)
    known = {row["room_id"]: row for row in read_rows(root / "splits/rooms.jsonl")}
    for row in rows:
        before = known.get(row["room_id"])
        if before is None:
            raise ValueError("The split names a room the experiment never had: " + row["room_id"])
        row.update(room_dir=before["room_dir"], min_clearance=before["min_clearance"])
    policy = write_experiment_split(root, splits_dir, rows)
    summary = json.loads((root / "splits/summary.json").read_text())
    summary.update({
        "room_counts": {s: sum(r["split"] == s for r in rows) for s in SPLITS},
        "excluded_rooms": len(policy["rooms"]),
        "expected_panoramas": len(rows)*VIEWS_PER_ROOM,
        "policy_id": policy["policy_id"]})
    (root / "splits/summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    return len(rows)


def check_experiment_rooms(root):
    actual = index_rows(read_rows(root / "splits/rooms.jsonl"))
    expected = index_rows(split_rows(root / "splits"))
    if set(actual) != set(expected) or any(actual[k]["split"] != expected[k]["split"] for k in expected):
        raise ValueError(
            "The rooms of this experiment differ from its split of %d rooms; "
            "exports and metrics from the two are not comparable" % len(expected))


MODULES = {"export_rgb": "dataset", "export_ground_truth": "dataset",
           "export_relations": "dataset", "export_shape": "dataset",
           "export_coco": "adapters"}


def run_module(name, root, extra=()):
    module = "%s.%s.%s" % (__package__.rpartition(".")[0], MODULES[name], name)
    subprocess.run([sys.executable, "-m", module, str(root), *extra], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    splits_help = "Directory of the frozen split: train/val/test.txt and excluded_rooms.json"
    init = commands.add_parser("init", help="Create a new experiment from source GLB rooms")
    init.add_argument("scene_root", type=Path)
    init.add_argument("experiment_root", type=Path)
    init.add_argument("--splits", type=Path, required=True, help=splits_help)
    export = commands.add_parser("export", help="Build RGB, metric ground truth, relations, meshes and COCO")
    export.add_argument("experiment_root", type=Path)
    export.add_argument("--stage", choices=("all", *STAGES), default="all")
    export.add_argument("--scale-table", help="Exact per-room metric scales from the original 3D-FRONT")
    export.add_argument("--class-table", help="Object classes from the original 3D-FRONT")
    export.add_argument("--reference-height", help="Ceiling height in metres assumed by the scale anchor")
    export.add_argument("--allow-unscalable", action="store_true",
                        help="Record rooms failing a scale check instead of stopping")
    export.add_argument("--expand-distance", help="Slack in metres for a touching relation")
    reject = commands.add_parser(
        "reject", help="Move rooms the renderer could not make out of the frozen split")
    reject.add_argument("experiment_root", type=Path)
    reject.add_argument("--splits", type=Path, required=True, help=splits_help)
    reject.add_argument("--rendered", type=Path,
                        help="Root of the finished renders, holding <house>/<room>/")
    reject.add_argument("--reasons", type=Path,
                        help="JSON object: room id -> what the renderer said about it")
    reject.add_argument("--rooms",
                        help="Exclude exactly the rooms of this list, whatever their render: "
                             "a JSON array of <house>/<room>, or one id per line")
    reject.add_argument("--reason", help="Why the rooms of --rooms leave the set")
    reject.add_argument("--evidence")
    reject.add_argument("--views", type=int, default=VIEWS_PER_ROOM)
    validate = commands.add_parser("validate", help="Validate the exported annotation")
    validate.add_argument("experiment_root", type=Path)
    freeze = commands.add_parser(
        "freeze", help="Build the frozen house-disjoint split from a source of GLB rooms")
    freeze.add_argument("scene_root", type=Path)
    freeze.add_argument("--splits", type=Path, required=True,
                        help="Directory to write the frozen split into")
    freeze.add_argument("--metadata", help="Scale and class report of the original 3D-FRONT")
    freeze.add_argument("--rooms",
                        help="Take only the rooms of this list: a JSON array of <house>/<room>, "
                             "or one id per line. Without it the whole source is taken")
    freeze.add_argument("--val", type=float, default=DEFAULT_VAL)
    freeze.add_argument("--test", type=float, default=DEFAULT_TEST)
    freeze.add_argument("--seed", type=int, default=0)
    freeze.add_argument("--reference-height", type=float,
                        help="Ceiling height in metres assumed when no exact scale is given")
    freeze.add_argument("--force", action="store_true",
                        help="Replace an existing split; earlier results then describe another set")
    args = parser.parse_args()
    if args.command == "freeze":
        from .freeze import freeze as build_split
        print(json.dumps(build_split(
            args.scene_root, args.splits, args.metadata, args.val, args.test,
            args.seed, args.reference_height, args.force, room_list=args.rooms),
            indent=2, ensure_ascii=False))
        return
    root = args.experiment_root.resolve()
    if args.command == "reject":
        from .reject import (apply_to_splits, name_exclusions, plan_exclusions,
                             read_reasons)
        if args.rooms:
            if not args.reason:
                parser.error("--rooms needs --reason: a room leaves the set only with one")
            from .room_list import read_room_list
            exclusions = name_exclusions(frozen_rooms(args.splits), read_room_list(args.rooms),
                                         args.reason, args.evidence or args.reason)
        elif args.rendered and args.reasons:
            exclusions = plan_exclusions(frozen_rooms(args.splits), args.rendered, args.views,
                                         read_reasons(args.reasons),
                                         args.evidence or RENDER_EVIDENCE)
        else:
            parser.error("reject takes either --rooms with --reason, "
                         "or --rendered with --reasons")
        if not exclusions:
            print(json.dumps({"excluded_now": 0, "rooms": len(frozen_rooms(args.splits))}, indent=2))
            return
        report = apply_to_splits(args.splits, exclusions)
        report["rooms_in_experiment"] = refresh_experiment(root, args.splits)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    if args.command == "init":
        initialize(args.scene_root, root, args.splits)
        return
    check_experiment_rooms(root)
    if args.command == "export":
        (root / "state").mkdir(exist_ok=True)
        scale_options = []
        for name in ("scale_table", "reference_height", "class_table"):
            value = getattr(args, name)
            if value:
                scale_options += ["--"+name.replace("_", "-"), str(value)]
        if args.allow_unscalable:
            scale_options.append("--allow-unscalable")
        relation_options = ["--expand-distance", str(args.expand_distance)] \
            if args.expand_distance else []
        for stage in STAGES if args.stage == "all" else (args.stage,):
            extra = {"ground_truth": scale_options, "relations": relation_options}
            run_module("export_"+stage, root, extra.get(stage, ()))
    else:
        from .validate_dataset import validate_dataset
        print(json.dumps(validate_dataset(root), indent=2))


if __name__ == "__main__":
    main()
