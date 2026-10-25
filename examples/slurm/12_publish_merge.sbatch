#!/bin/bash
#SBATCH --job-name=front3d-publish-merge
#SBATCH --cpus-per-task=2
#SBATCH --time=01:00:00
#SBATCH --output=logs/%x-%j.out
set -euo pipefail
front3d-pano publish "${EXP:?}" "${SHARE:?}" --merge
