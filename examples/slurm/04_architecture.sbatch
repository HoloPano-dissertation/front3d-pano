#!/bin/bash
#SBATCH --job-name=front3d-architecture
#SBATCH --cpus-per-task=2
#SBATCH --time=04:00:00
#SBATCH --array=0-31
#SBATCH --output=logs/%x-%A_%a.out
set -euo pipefail
front3d-pano architecture "${RAW:?}/3D-FRONT.zip" "${RAW:?}/3D-FRONT-texture.zip" \
  "${SCENES:?}" - "${ARCH:?}" \
  --rooms "${EXP:?}/state/rooms-all.txt" --metadata "${METADATA:?}" \
  --shard-index "$SLURM_ARRAY_TASK_ID" --shard-count "$SLURM_ARRAY_TASK_COUNT"
