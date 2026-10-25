#!/bin/bash
#SBATCH --job-name=front3d-render
#SBATCH --cpus-per-task=4
#SBATCH --time=12:00:00
#SBATCH --array=0-63
#SBATCH --output=logs/%x-%A_%a.out
set -euo pipefail
front3d-pano render "${EXP:?}/splits/rooms.jsonl" "${EXP:?}/outputs" \
  --views 4 --samples 96 --architecture-root "${ARCH:?}" \
  --ambient 4.0 --light-temperature 2700-5000 \
  --shard-index "$SLURM_ARRAY_TASK_ID" --shard-count "$SLURM_ARRAY_TASK_COUNT"
