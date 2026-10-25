import json

import pytest


def test_exclusions_need_no_split_label(tmp_path):
    from front3d_pano.dataset import prepare
    splits = tmp_path / "splits"
    splits.mkdir()
    for name, room_id in (("train", "h1/Bedroom-1"), ("val", "h2/Bedroom-2"),
                          ("test", "h3/Bedroom-3")):
        (splits / (name + ".txt")).write_text(room_id + "\n", encoding="utf-8")
    (splits / "excluded_rooms.json").write_text(json.dumps({
        "expected_retained_rooms": 3,
        "rooms": [{"room_id": "h4/Bedroom-4", "house_id": "h4", "split": "excluded",
                   "reason": "the contour collapsed for this room"}]}), encoding="utf-8")
    assert [row["room_id"] for row in prepare.frozen_rooms(splits)] == [
        "h3/Bedroom-3", "h1/Bedroom-1", "h2/Bedroom-2"]


def test_initialization_does_not_create_partial_experiment_with_missing_source(tmp_path):
    from front3d_pano.dataset.prepare import initialize
    root = tmp_path / "new-experiment"
    with pytest.raises((ValueError, FileNotFoundError, NotADirectoryError)):
        initialize(tmp_path / "missing-source", root, tmp_path / "splits")
    assert not root.exists()


def test_initialization_refuses_existing_directory(tmp_path):
    from front3d_pano.dataset.prepare import initialize
    with pytest.raises(FileExistsError):
        initialize(tmp_path / "source", tmp_path, tmp_path / "splits")


@pytest.fixture
def exported_dataset(tmp_path):
    from PIL import Image
    CLASSES = ["bed", "chair", "table"]

    def write(path, data, jsonl=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r)+"\n" for r in data) if jsonl else json.dumps(data))

    rooms = []
    for split in ("train", "val", "test"):
        room_id = split+"-house/room"
        rooms.append({"room_id": room_id, "house_id": split+"-house", "split": split})
        records, images, annotations = [], [], []
        for view in range(4):
            sample_id = room_id+"/"+str(view)
            rgb = tmp_path / "rgb" / split / (str(view)+".png")
            rgb.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (1024, 512), "gray").save(rgb)
            gt = tmp_path / "gt" / split / (str(view)+".json")
            write(gt, {"layout": {"min_corner": [-1, -1, -1], "max_corner": [1, 1, 1]}, "objects": []})
            records.append({"sample_id": sample_id, "input": str(rgb), "ground_truth": str(gt),
                            "metadata": {"split": split}})
            images.append({"sample_id": sample_id, "id": view+1, "file_name": str(rgb), "width": 1024, "height": 512})
            annotations.append({"id": view+1, "image_id": view+1, "category_id": 1, "bbox": [0, 0, 1, 1],
                                "area": 1, "segmentation": {"size": [512, 1024], "counts": [0, 1, 512*1024-1]}})
        for folder in ("manifests", "manifests_gt"):
            write(tmp_path / folder / (split+".jsonl"), records, True)
        write(tmp_path / "coco" / (split+".json"), {"images": images, "annotations": annotations,
              "categories": [{"id": i+1, "name": name, "supercategory": "furniture"} for i, name in enumerate(CLASSES)]})
        (tmp_path / "splits").mkdir(exist_ok=True)
        (tmp_path / "splits" / (split+".txt")).write_text(room_id+"\n")
    write(tmp_path / "state/classes.json", {"classes": CLASSES})
    write(tmp_path / "splits/rooms.jsonl", rooms, True)
    write(tmp_path / "splits/excluded_rooms.jsonl", [], True)
    return tmp_path


def test_all_exports_are_checked(exported_dataset):
    from front3d_pano.dataset.validate_dataset import validate_dataset
    report = validate_dataset(exported_dataset)
    assert report["ready"]
    assert report["sample_counts"] == {"train": 4, "val": 4, "test": 4}
    assert report["coco_annotations"] == report["sample_counts"]


def test_excluded_room_leak_invalidates_previous_success(exported_dataset):
    from front3d_pano.dataset.validate_dataset import validate_dataset
    validate_dataset(exported_dataset)
    (exported_dataset / "splits/excluded_rooms.jsonl").write_text('{"room_id":"train-house/room"}\n')
    with pytest.raises(ValueError, match="Excluded"):
        validate_dataset(exported_dataset)
    assert not json.loads((exported_dataset / "state/derived_validation.json").read_text())["ready"]


@pytest.mark.parametrize("mutation", ["rle", "category", "duplicate", "bbox"])
def test_coco_corruption_is_rejected(exported_dataset, mutation):
    from front3d_pano.dataset.validate_dataset import validate_dataset
    path = exported_dataset / "coco/train.json"
    coco = json.loads(path.read_text())
    if mutation == "rle":
        coco["annotations"][0]["segmentation"]["counts"][-1] -= 1
    elif mutation == "category":
        coco["annotations"][0]["category_id"] = 99
    elif mutation == "duplicate":
        coco["images"].append(coco["images"][0])
    else:
        coco["annotations"][0]["bbox"][0] = -1
    path.write_text(json.dumps(coco))
    with pytest.raises(ValueError):
        validate_dataset(exported_dataset)
