#!/usr/bin/env python3
"""
Convert a HuggingFace translation model (e.g. Helsinki-NLP/opus-mt-en-th)
into a local CTranslate2 model directory for fast offline inference.

Usage:
  python scripts/convert_to_ctranslate2.py \
    --model Helsinki-NLP/opus-mt-en-th \
    --output models/ctranslate2/en-th \
    --copy-spm

Requirements:
  pip install -r backend/requirements.txt  # includes ctranslate2[cli]

Notes:
- You can choose a compute type like int8 or float16 to reduce size/speed up.
- After conversion, set env vars:
    MT_PROVIDER=ctranslate2
    CT2_MODEL_DIR=models/ctranslate2/en-th
    CT2_COMPUTE_TYPE=int8_float16  # or auto/float16/int8
- If SentencePiece models are not present as source.spm/target.spm, this script
  will try to copy common files as a fallback.
"""
import argparse
import shutil
from pathlib import Path
import subprocess


def run(cmd: list[str]):
    subprocess.run(cmd, check=True)


def maybe_copy_spm(src_dir: Path):
    # Prefer source.spm / target.spm; otherwise copy spm.model if present
    spm_candidates = [
        (src_dir / "source.spm", src_dir / "source.spm"),
        (src_dir / "target.spm", src_dir / "target.spm"),
    ]
    # If neither exists, fall back to copying spm.model twice
    spm_model = src_dir / "spm.model"
    if not (spm_candidates[0][0].exists() and spm_candidates[1][0].exists()):
        if spm_model.exists():
            for out_name in ("source.spm", "target.spm"):
                dst = src_dir / out_name
                if not dst.exists():
                    shutil.copyfile(spm_model, dst)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--model",
        required=True,
        help=("HF model id/path e.g. Helsinki-NLP/opus-mt-en-th"),
    )
    p.add_argument(
        "--output",
        required=True,
        help=("Output dir for CTranslate2 model"),
    )
    p.add_argument(
        "--quantization",
        default="int8_float16",
        choices=[
            "int8",
            "int8_float32",
            "int8_float16",
            "int8_bfloat16",
            "int16",
            "float16",
            "bfloat16",
            "float32",
        ],
        help=("CT2 quantization type for converted weights"),
    )
    p.add_argument(
        "--copy-spm",
        action="store_true",
        help=("Attempt to copy SPM files if missing"),
    )
    p.add_argument(
        "--force",
        action="store_true",
        help=("Overwrite output directory if it exists"),
    )
    args = p.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ct2-transformers-converter",
        "--model",
        args.model,
        "--output_dir",
        str(out_dir),
        "--quantization",
        args.quantization,
    ]
    if args.force:
        cmd.append("--force")

    run(cmd)

    if args.copy_spm:
        maybe_copy_spm(out_dir)

    print(f"Converted model to {out_dir}")


if __name__ == "__main__":
    main()
