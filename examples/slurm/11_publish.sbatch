#!/bin/bash
#SBATCH --job-name=front3d-publish
#SBATCH --cpus-per-task=2
#SBATCH --time=04:00:00
#SBATCH --array=0-63
#SBATCH --output=logs/%x-%A_%a.out
set -euo pipefail
front3d-pano publish "${EXP:?}" "${SHARE:?}" \
  --shard-index "$SLURM_ARRAY_TASK_ID" --shard-count "$SLURM_ARRAY_TASK_COUNT"
