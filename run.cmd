@echo off
# inside ./run
echo "[run] HF_TOKEN length: ${#HF_TOKEN:-0}"
echo "[run] HUGGINGFACE_HUB_TOKEN length: ${#HUGGINGFACE_HUB_TOKEN:-0}"
echo "[run] GIT_LFS_SKIP_SMUDGE=$GIT_LFS_SKIP_SMUDGE"

REM Windows wrapper for the project CLI
python run %*
