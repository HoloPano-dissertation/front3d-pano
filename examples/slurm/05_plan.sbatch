#!/bin/bash
#SBATCH --job-name=front3d-plan
#SBATCH --cpus-per-task=4
#SBATCH --time=04:00:00
#SBATCH --array=0-63
#SBATCH --output=logs/%x-%A_%a.out
set -euo pipefail
front3d-pano render "${EXP:?}/splits/rooms.jsonl" "${EXP:?}/plan" \
  --views 4 --plan-only --architecture-root "${ARCH:?}" \
  --shard-index "$SLURM_ARRAY_TASK_ID" --shard-count "$SLURM_ARRAY_TASK_COUNT"
