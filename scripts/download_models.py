#!/usr/bin/env python3
"""Download dependencies for offline ASR/MT providers."""

from __future__ import annotations

import argparse
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Optional

import requests
from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
WHISPER_DIR = MODELS_DIR / "whisper.cpp"
VOSK_DIR = MODELS_DIR / "vosk"
MARIAN_DIR = MODELS_DIR / "marian"

VOSK_ZIP = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
WHISPER_BIN = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin"


def download_file(url: str, destination: Path, *, chunk_size: int = 1 << 20) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        written = 0
        with destination.open("wb") as fp:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    fp.write(chunk)
                    written += len(chunk)
        if total and written != total:
            raise IOError(f"Downloaded size mismatch for {url}")


def extract_zip(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "r") as zf:
        zf.extractall(dest)
    return dest


def ensure_vosk_model(force: bool) -> Path:
    target_dir = VOSK_DIR / "vosk-model-small-en-us-0.15"
    if target_dir.exists() and not force:
        print(f"Vosk model already present at {target_dir}")
        return target_dir
    tmp_zip = VOSK_DIR / "vosk.zip"
    print("Downloading Vosk model…")
    download_file(VOSK_ZIP, tmp_zip)
    print("Extracting Vosk model…")
    extract_zip(tmp_zip, VOSK_DIR)
    tmp_zip.unlink(missing_ok=True)
    return target_dir


def ensure_whisper_model(force: bool) -> Path:
    target = WHISPER_DIR / "ggml-small.en.bin"
    if target.exists() and not force:
        print(f"Whisper.cpp model already present at {target}")
        return target
    print("Downloading Whisper.cpp model…")
    download_file(WHISPER_BIN, target)
    return target


def ensure_marian_model(force: bool) -> Path:
    target = MARIAN_DIR
    if any(target.glob("*")) and not force:
        print(f"MarianMT model already present at {target}")
        return target
    print("Downloading MarianMT model (Helsinki-NLP/opus-mt-en-th)…")
    snapshot_download(
        repo_id="Helsinki-NLP/opus-mt-en-th",
        local_dir=str(target),
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    return target


def main(force: bool = False, skip_vosk: bool = False, skip_whisper: bool = False, skip_marian: bool = False) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if not skip_vosk:
        ensure_vosk_model(force)
    if not skip_whisper:
        ensure_whisper_model(force)
    if not skip_marian:
        ensure_marian_model(force)
    print("All models downloaded.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download offline ASR/MT models.")
    parser.add_argument("--force", action="store_true", help="Re-download even if files exist")
    parser.add_argument("--skip-vosk", action="store_true", help="Skip Vosk model")
    parser.add_argument("--skip-whisper", action="store_true", help="Skip Whisper.cpp model")
    parser.add_argument("--skip-marian", action="store_true", help="Skip MarianMT model")
    args = parser.parse_args()
    main(force=args.force, skip_vosk=args.skip_vosk, skip_whisper=args.skip_whisper, skip_marian=args.skip_marian)
