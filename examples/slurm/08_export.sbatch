#!/bin/bash
#SBATCH --job-name=front3d-export
#SBATCH --cpus-per-task=8
#SBATCH --time=24:00:00
#SBATCH --output=logs/%x-%j.out
set -euo pipefail
for stage in rgb ground_truth relations shape coco; do
  front3d-pano export "${EXP:?}" --stage "$stage" \
    --scale-table "${METADATA:?}" --class-table "${METADATA:?}"
done
front3d-pano validate "${EXP:?}"
