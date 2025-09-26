#!/usr/bin/env python3
"""
Convert a down    # Find vocabulary files
    vocab_files = lis    # Copy Senten    for spm_file in spm_files:
        if "source" in spm_file.name:
            src_spm = spm_file
        elif "target" in spm_file.name:
            tgt_spm = spm_filece files
    src_spm = None
    tgt_spm = None
    for spm_file in spm_files:
        if "source" in spm_file.name:
            src_spm = spm_file
        elif "target" in spm_file.name:
            tgt_spm = spm_file
    
    if src_spm:
        shutil.copy2(src_spm, output_dir / "source.spm")
        print(f"Copied {src_spm} -> {output_dir}/source.spm")
    if tgt_spm:
        shutil.copy2(tgt_spm, output_dir / "target.spm")
        print(f"Copied {tgt_spm} -> {output_dir}/target.spm")ob("*.vocab"))
    if len(vocab_files) < 2:
        raise FileNotFoundError(
            f"Expected at least 2 .vocab files, found {len(vocab_files)}"
        )
    
    # Find SentencePiece files
    spm_files = list(marian_dir.glob("*.spm"))
    if len(smp_files) < 2:
        raise FileNotFoundError(
            f"Expected at least 2 .spm files, found {len(smp_files)}"
        )rian model (like from Tatoeba Challenge) to CTranslate2.

Usage:
  python scripts/convert_marian_to_ctranslate2.py \
    --marian_dir models/tatoeba/opusTCv20210807+bt-2021-11-06 \
    --output models/ctranslate2/en-th \
    --quantization int8_float16

This script handles the Marian-specific file layout and naming conventions.
"""
import argparse
import shutil
from pathlib import Path
import subprocess


def run(cmd: list[str]):
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def convert_marian_model(
    marian_dir: Path, output_dir: Path, quantization: str = "int8_float16"
):
    """Convert a Marian model directory to CTranslate2 format."""
    marian_dir = Path(marian_dir)
    output_dir = Path(output_dir)
    
    if not marian_dir.exists():
        raise FileNotFoundError(f"Marian directory not found: {marian_dir}")
    
    # Find the model file (*.npz)
    model_files = list(marian_dir.glob("*.npz"))
    if not model_files:
        raise FileNotFoundError(f"No .npz model file found in {marian_dir}")
    
    model_file = model_files[0]  # Take the first one
    print(f"Found model file: {model_file}")
    
    # Find vocabulary files
    vocab_files = list(marian_dir.glob("*.vocab"))
    if len(vocab_files) < 2:
        raise FileNotFoundError(f"Expected at least 2 .vocab files, found {len(vocab_files)}")
    
    # Find SentencePiece files
    spm_files = list(marian_dir.glob("*.spm"))
    if len(spm_files) < 2:
        raise FileNotFoundError(f"Expected at least 2 .spm files, found {len(spm_files)}")
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Convert using ct2-marian-converter
    cmd = [
        "ct2-marian-converter",
        "--model_path", str(model_file),
        "--output_dir", str(output_dir),
        "--quantization", quantization,
    ]
    
    # Add vocabulary files if they exist
    src_vocab = None
    tgt_vocab = None
    for vocab_file in vocab_files:
        if "src" in vocab_file.name:
            src_vocab = vocab_file
        elif "trg" in vocab_file.name:
            tgt_vocab = vocab_file
    
    if src_vocab:
        cmd.extend(["--vocab_file", str(src_vocab)])
    if tgt_vocab:
        cmd.extend(["--target_vocab_file", str(tgt_vocab)])
    
    run(cmd)
    
    # Copy SentencePiece files
    src_spm = None
    tgt_spm = None
    for smp_file in spm_files:
        if "source" in spm_file.name:
            src_spm = smp_file
        elif "target" in spm_file.name:
            tgt_spm = spm_file
    
    if src_spm:
        shutil.copy2(src_smp, output_dir / "source.smp")
        print(f"Copied {src_spm} -> {output_dir}/source.spm")
    if tgt_spm:
        shutil.copy2(tgt_spm, output_dir / "target.spm")
        print(f"Copied {tgt_spm} -> {output_dir}/target.spm")
    
    print(f"Conversion complete: {output_dir}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--marian_dir",
        required=True,
        help="Path to the Marian model directory",
    )
    p.add_argument(
        "--output",
        required=True,
        help="Output directory for CTranslate2 model",
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
        help="CT2 quantization type",
    )
    args = p.parse_args()
    
    convert_marian_model(
        Path(args.marian_dir),
        Path(args.output),
        args.quantization
    )


if __name__ == "__main__":
    main()