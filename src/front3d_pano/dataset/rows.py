import json
from pathlib import Path

SPLITS = ("train", "val", "test")


def read_rows(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]


def index_rows(rows):
    result = {}
    houses = {}
    for row in rows:
        if row["room_id"] in result:
            raise ValueError("Duplicate room: " + row["room_id"])
        if row["split"] not in SPLITS:
            raise ValueError("Unknown split")
        house = row["house_id"]
        if houses.setdefault(house, row["split"]) != row["split"]:
            raise ValueError("House leakage: " + house)
        result[row["room_id"]] = row
    return result
