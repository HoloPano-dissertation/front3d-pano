#!/bin/bash
#SBATCH --job-name=front3d-metadata
#SBATCH --cpus-per-task=4
#SBATCH --time=12:00:00
#SBATCH --output=logs/%x-%j.out
set -euo pipefail
front3d-pano metadata "${RAW:?}/3D-FRONT.zip" "${SCENES:?}" "${METADATA:?}" \
  --rooms "${ROOMS:?}"
