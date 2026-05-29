#!/usr/bin/env python3
"""Edit images with APIMart image models."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _apimart_common import (
    ApimartClient,
    ApimartImageError,
    build_generation_payload,
    choose_output_path,
    coerce_base_url,
    extract_result_image_urls,
    get_model_spec,
    guess_extension_from_url,
    is_remote_url,
    load_batch_tasks,
    print_error,
    print_info,
    print_warning,
    resolve_api_key,
    resolve_model_name,
    run_setup,
    validate_model_inputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Edit images via APIMart.")
    parser.add_argument("--setup", action="store_true", help="Interactively save APIMART API key.")
    parser.add_argument("--model", help="APIMART image model name.")
    parser.add_argument("--prompt", help="Editing prompt.")
    parser.add_argument("--input", action="append", dest="inputs", help="Input image path or URL. Repeatable.")
    parser.add_argument("--mask", help="Optional mask image path or URL.")
    parser.add_argument("--size", help="Model-specific size or aspect ratio.")
    parser.add_argument("--resolution", help="Model-specific resolution.")
    parser.add_argument("--output", help="Output file path for a single image.")
    parser.add_argument("--output-dir", help="Output directory for generated files.")
    parser.add_argument("--retry", type=int, default=3, help="Retry count for task creation.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Task poll interval in seconds.")
    parser.add_argument("--timeout", type=int, default=600, help="Task timeout in seconds.")
    parser.add_argument("--api-key", help="APIMART API key override.")
    parser.add_argument("--base-url", help="APIMART API base URL override.")
    parser.add_argument("--extra-json", help="JSON object merged into the generation payload.")
    parser.add_argument("--official-fallback", action="store_true", help="Only applies to gpt-image-2.")
    parser.add_argument("--quality", help="Model-specific quality option.")
    parser.add_argument("--background", help="Model-specific background option.")
    parser.add_argument("--moderation", help="Model-specific moderation option.")
    parser.add_argument("--output-format", help="Model-specific output format.")
    parser.add_argument("--output-compression", type=int, help="Model-specific output compression.")
    parser.add_argument("--n", type=int, help="Number of requested images for supported models.")
    parser.add_argument("--batch", help="JSON array of edit tasks.")
    return parser


def upload_if_needed(client: ApimartClient, value: str) -> str:
    if is_remote_url(value):
        return value
    return client.upload_image(value)


def task_to_options(task: dict, args: argparse.Namespace, mask_url: str | None) -> dict:
    return {
        "size": task.get("size", args.size),
        "resolution": task.get("resolution", args.resolution),
        "official_fallback": task.get("official_fallback", args.official_fallback),
        "quality": task.get("quality", args.quality),
        "background": task.get("background", args.background),
        "moderation": task.get("moderation", args.moderation),
        "output_format": task.get("output_format", args.output_format),
        "output_compression": task.get("output_compression", args.output_compression),
        "n": task.get("n", args.n),
        "mask_url": mask_url,
    }


def run_single_task(client: ApimartClient, args: argparse.Namespace, task: dict, index: int = 0) -> list[Path]:
    model_name = task.get("model") or resolve_model_name(args.model)
    prompt = task.get("prompt") or args.prompt
    if not prompt:
        raise ApimartImageError("A prompt is required.")

    inputs = task.get("inputs")
    if inputs is None:
        inputs = args.inputs or []
    if not inputs:
        raise ApimartImageError("At least one --input image is required for edit mode.")

    image_urls = [upload_if_needed(client, value) for value in inputs]
    mask_value = task.get("mask", args.mask)
    mask_url = upload_if_needed(client, mask_value) if mask_value else None
    validate_model_inputs(model_name, image_count=len(image_urls), has_mask=bool(mask_url))

    options = task_to_options(task, args, mask_url)
    payload, warnings = build_generation_payload(
        model_name=model_name,
        prompt=prompt,
        image_urls=image_urls,
        options=options,
        extra_json=task.get("extra_json") or args.extra_json,
    )
    for warning in warnings:
        print_warning(warning)

    task_id, _ = client.create_generation_task(payload, retries=max(args.retry, 0))
    print_info(f"Created task: {task_id}")
    status_payload = client.poll_task(task_id, poll_interval=args.poll_interval, timeout_seconds=args.timeout)
    result_urls = extract_result_image_urls(status_payload)
    if not result_urls:
        raise ApimartImageError(f"Task '{task_id}' completed without image URLs: {status_payload}")

    output_dir = Path(task.get("output_dir") or args.output_dir) if task.get("output_dir") or args.output_dir else None
    output_override = task.get("output") or args.output
    saved_paths: list[Path] = []
    for image_index, image_url in enumerate(result_urls):
        extension = guess_extension_from_url(image_url)
        output_path = choose_output_path(
            output=output_override if len(result_urls) == 1 else None,
            output_dir=output_dir,
            prompt=prompt,
            index=index + image_index,
            extension=extension,
        )
        saved = client.download_image(image_url, output_path)
        saved_paths.append(saved)
        print_info(f"task_id={task_id}")
        print_info(f"image_url={image_url}")
        print_info(f"saved={saved}")
    return saved_paths


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.setup:
        try:
            run_setup()
        except ApimartImageError as exc:
            print_error(str(exc))
            return 1
        return 0
    try:
        model_name = resolve_model_name(args.model)
        _ = get_model_spec(model_name)
        api_key = resolve_api_key(args.api_key)
        base_url = coerce_base_url(args.base_url)
        with ApimartClient(base_url=base_url, api_key=api_key, timeout=args.timeout) as client:
            if args.batch:
                tasks = load_batch_tasks(args.batch)
                for idx, task in enumerate(tasks):
                    task.setdefault("model", model_name)
                    run_single_task(client, args, task, index=idx)
            else:
                run_single_task(client, args, {"model": model_name}, index=0)
        return 0
    except ApimartImageError as exc:
        print_error(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
