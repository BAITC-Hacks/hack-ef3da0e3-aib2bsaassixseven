from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ml_pipeline.catalog import ASR_MODELS, LLM_MODELS, MODELS


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline meeting ML pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="download and pin models once")
    prepare.add_argument("--models-dir", type=Path, required=True)
    prepare.add_argument("--asr-model", choices=ASR_MODELS, required=True)
    prepare.add_argument("--llm-model", choices=LLM_MODELS, default="qwen3.5-9b")
    prepare.add_argument("--also", nargs="*", choices=tuple(MODELS), default=[])

    run = subparsers.add_parser("run", help="process one recording offline")
    run.add_argument("--audio", type=Path, required=True)
    run.add_argument("--meeting-at", help="ISO date/time, e.g. 2026-09-23T10:00")
    run.add_argument("--timezone", required=True, help="IANA timezone")
    run.add_argument("--participant", action="append", default=[])
    run.add_argument("--asr-model", choices=ASR_MODELS, required=True)
    run.add_argument("--llm-model", choices=LLM_MODELS, default="qwen3.5-9b")
    run.add_argument("--models-dir", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--chunk-chars", type=int, default=10_000)
    run.add_argument(
        "--reviewed-corrections",
        type=Path,
        help="optional audio-hash-bound, reviewed transcript fragments",
    )

    compare = subparsers.add_parser(
        "compare", help="evaluate candidates on same labeled set"
    )
    compare.add_argument("--manifest", type=Path, required=True)
    compare.add_argument("--models-dir", type=Path, required=True)
    compare.add_argument("--output-dir", type=Path, required=True)
    compare.add_argument(
        "--asr-models", nargs="+", choices=ASR_MODELS, default=list(ASR_MODELS)
    )
    compare.add_argument(
        "--llm-models", nargs="+", choices=LLM_MODELS, default=list(LLM_MODELS)
    )

    args = parser.parse_args()
    if args.command == "prepare":
        from ml_pipeline.prepare import prepare_models

        names = list(
            dict.fromkeys(["diarization", args.asr_model, args.llm_model, *args.also])
        )
        result = prepare_models(args.models_dir, names, token=os.getenv("HF_TOKEN"))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "run":
        from ml_pipeline.runtime import RunConfig, run_pipeline

        run_pipeline(
            RunConfig(
                audio=args.audio,
                meeting_at=args.meeting_at,
                timezone=args.timezone,
                participants=args.participant,
                asr_model=args.asr_model,
                llm_model=args.llm_model,
                models_dir=args.models_dir,
                output_dir=args.output_dir,
                chunk_chars=args.chunk_chars,
                reviewed_corrections=args.reviewed_corrections,
            )
        )
        print(args.output_dir.resolve())
    else:
        from ml_pipeline.compare import compare_manifest

        result = compare_manifest(
            args.manifest,
            args.output_dir,
            args.models_dir,
            args.asr_models,
            args.llm_models,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
