# front3d-pano

*[Русская версия — README.md](README.md) (main).*

A generator of 360° panoramas with metric 3D annotation from **3D-FRONT** rooms. For
every room it places cameras, renders four equirectangular panoramas and exports the
annotation: object boxes in metres, the room contour, object relations, object meshes,
2D boxes and masks.

The generator does not depend on any particular method. It produces the annotation as
it is and, besides it, only the common COCO format. The formats of particular methods
come from separate **adapters** outside the generator: they read the ground truth, and
the core does not change for them.

## Output

| Layer | Contents | Depends on methods |
|---|---|---|
| Render | per view: colour, depth, normals, instance masks (`{0..3}.hdf5`), cameras and parameters (`render.json`) | no |
| Ground truth | object boxes in metres, room contour, relations, classes, object meshes, house-disjoint split | no |
| COCO | 2D object boxes and masks | no |

Every file is described in [docs/output_format.md](docs/output_format.md) (the documents in `docs/` are in Russian).

## Pipeline

```
GLB rooms (MIDI-3D processing)  +  original 3D-FRONT (scales, classes, architecture)
        │
        ▼  metadata → freeze → init → architecture
dataset composition: house-disjoint split and excluded rooms with reasons
        │
        ▼  render (Blender through BlenderProc) → reject
panoramas: outputs/<split>/<house>/<room>/{0..3}.hdf5 + render.json
        │
        ▼  export → validate
ground truth and COCO
        │
        ▼  images → publish
the set as it is shared
```

Step by step: [docs/pipeline.md](docs/pipeline.md); the same steps as Slurm jobs: [examples/slurm/](examples/slurm/README.md).

## Installation

Python 3.9 or newer. Annotation and checks run on the CPU:

```bash
git clone https://github.com/HoloPano-dissertation/front3d-pano.git
cd front3d-pano
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
front3d-pano --help
```

Rendering also needs BlenderProc, which downloads Blender on first use. Tested with
BlenderProc 2.8.0 and Blender 4.2.1 on Linux:

```bash
pip install -e ".[render]"
blenderproc pip install "shapely>=2,<3"
```

## One room

```bash
front3d-pano render-room /data/3D-FRONT-SCENE/<house>/<room> /data/rendered-room \
  --views 4 --samples 96 --min-clearance 0.1 --ambient 4.0 --light-temperature 2700-5000
```

The folder receives `{0..3}.hdf5` and `render.json`; how to read the HDF5 is shown in
[docs/output_format.md](docs/output_format.md).

## Commands

Every step is `front3d-pano <command>`; `front3d-pano <command> --help` lists its options.

| Command | What it does |
|---|---|
| `metadata` | exact per-room scales and object classes from the original 3D-FRONT |
| `freeze` | house-disjoint split and the excluded rooms with reasons |
| `init` | a new experiment over the frozen split |
| `architecture` | walls, floors, ceilings and their materials from the original 3D-FRONT |
| `render` | camera planning and rendering of many rooms, with shards and resumption |
| `render-room` | rendering of one room |
| `reject` | moves rooms the renderer could not make out of the split |
| `export` | all annotation: colour, metric ground truth, relations, meshes, COCO |
| `validate` | checks the exports against each other |
| `images` | colour of the whole set as PNG |
| `publish` | the set as it is shared: panoramas, COCO and README |

## Data and terms of use

No data is included; it has to be downloaded separately. The generator uses the GLB
rooms of the MIDI-3D processing ([huanngzh/3D-Front](https://huggingface.co/datasets/huanngzh/3D-Front),
CC BY-NC 4.0) and two archives of the original 3D-FRONT: scene descriptions and
textures. The original 3D-FRONT is distributed under the Alibaba license agreement for
scientific research only. What to download and which terms apply is described in
[docs/data_sources.md](docs/data_sources.md).

## Tests

```bash
pytest
```

The tests need neither Blender nor 3D-FRONT data: rooms and renders are built from
simple shapes inside the tests.
