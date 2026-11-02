#!/bin/zsh
set -eu
cd "${0:A:h}"
export KIRA_PROJECT="$PWD"
export KIRA_TRAINING_WORKSPACE="${KIRA_TRAINING_WORKSPACE:-$PWD/output/kira-training-space/workspace}"
exec "${KIRA_PYTHON:-python3}" plugins/kira-training-space/runtime/server.py "$@"
