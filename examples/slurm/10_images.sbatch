#!/bin/bash
#SBATCH --job-name=front3d-images
#SBATCH --cpus-per-task=2
#SBATCH --time=04:00:00
#SBATCH --array=0-31
#SBATCH --output=logs/%x-%A_%a.out
set -euo pipefail
for split in train val test; do
  front3d-pano images "${EXP:?}/outputs/$split" "${SHARE:?}/panoramas/png" \
    --shard-index "$SLURM_ARRAY_TASK_ID" --shard-count "$SLURM_ARRAY_TASK_COUNT"
done
