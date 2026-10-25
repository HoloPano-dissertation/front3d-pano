import json


def experiment_classes(root):
    path = root / "state" / "classes.json"
    if not path.is_file():
        raise FileNotFoundError("%s is written by the ground_truth stage; run it first" % path)
    return list(json.loads(path.read_text(encoding="utf-8"))["classes"])
