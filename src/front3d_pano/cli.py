import runpy
import subprocess
import sys
from pathlib import Path

PACKAGE = __package__ or "front3d_pano"

COMMANDS = {
    "metadata": ("dataset.source_metadata",
                 "exact per-room scales and object classes from the original 3D-FRONT"),
    "freeze": ("dataset.prepare", "house-disjoint split and the rooms excluded from it"),
    "init": ("dataset.prepare", "new experiment over the frozen split"),
    "architecture": ("dataset.scene_architecture",
                     "walls, floors, ceilings and their materials from the original 3D-FRONT"),
    "render": ("render.run_batch", "plan cameras and render panoramas for many rooms"),
    "render-room": (None, "render one room (Blender through BlenderProc)"),
    "reject": ("dataset.prepare", "move rooms the renderer could not make out of the split"),
    "export": ("dataset.prepare", "annotation: RGB, metric ground truth, relations, meshes and COCO"),
    "validate": ("dataset.prepare", "check the exports against each other"),
    "images": ("render.export_images", "colour of every view as PNG beside its HDF5"),
    "publish": ("dataset.publish_annotations", "the set as it is shared: panoramas, COCO and README"),
}
PREPARE = {"freeze", "init", "reject", "export", "validate"}


def usage():
    width = max(map(len, COMMANDS))
    lines = ["usage: front3d-pano <command> [arguments]", "",
             "Commands, in the order a dataset is built:"]
    lines += ["  %-*s  %s" % (width, name, text) for name, (_, text) in COMMANDS.items()]
    lines += ["", "front3d-pano <command> --help lists the options of a command."]
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(usage())
        return
    if argv[0] in ("-V", "--version"):
        from . import __version__
        print(__version__)
        return
    command, arguments = argv[0], argv[1:]
    if command not in COMMANDS:
        sys.exit("front3d-pano: unknown command %r\n\n%s" % (command, usage()))
    if command == "render-room":
        script = Path(__file__).resolve().parent / "render" / "run_room.sh"
        sys.exit(subprocess.call(["bash", str(script), *arguments]))
    module = COMMANDS[command][0]
    if command in PREPARE:
        arguments = [command, *arguments]
    sys.argv = ["front3d-pano" if command in PREPARE else "front3d-pano " + command, *arguments]
    runpy.run_module("%s.%s" % (PACKAGE, module), run_name="__main__")


if __name__ == "__main__":
    main()
