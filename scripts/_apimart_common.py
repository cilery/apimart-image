#!/usr/bin/env python3
"""Shared helpers for the apimart-image skill."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar
from urllib.parse import urlparse

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: httpx. Install it with `pip install httpx`.") from exc


DEFAULT_BASE_URL = "https://api.apimart.ai"
DEFAULT_OUTPUT_DIR = Path("./outimage/apimart-image")
SKILL_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = SKILL_ROOT
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_MODEL = "gpt-image-2"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
POLL_DONE_STATUSES = {"completed", "succeeded", "success"}
POLL_FAILED_STATUSES = {"failed", "error", "cancelled", "canceled", "expired"}
MAX_UPLOAD_IMAGE_COUNT = 16
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
VALID_GEMINI_ASPECT_RATIOS = {
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
}
VALID_GEMINI_RESOLUTIONS = {"1K", "2K", "4K"}
MAX_NETWORK_RETRIES = 3
DEFAULT_BATCH_WORKERS = 2
BatchResultT = TypeVar("BatchResultT")


class ApimartImageError(RuntimeError):
    """Domain error for apimart-image scripts."""


@dataclass(frozen=True)
class ModelSpec:
    name: str
    allow_input_images: bool
    allow_mask: bool
    max_input_images: int
    supports_official_fallback: bool = False
    supports_n: bool = False
    min_n: int = 1
    max_n: int = 1
    warned_ignored_fields: tuple[str, ...] = ()
    default_size: str | None = None
    family: str = "generic"


MODELS: dict[str, ModelSpec] = {
    "gpt-image-2": ModelSpec(
        name="gpt-image-2",
        allow_input_images=True,
        allow_mask=False,
        max_input_images=16,
        supports_official_fallback=True,
        supports_n=True,
        min_n=1,
        max_n=10,
        warned_ignored_fields=("quality", "style", "response_format"),
        default_size="1536x1024",
        family="gpt-image-2",
    ),
    "gpt-image-2-official": ModelSpec(
        name="gpt-image-2-official",
        allow_input_images=True,
        allow_mask=True,
        max_input_images=16,
        supports_n=True,
        min_n=1,
        max_n=4,
        default_size="1024x1024",
        family="gpt-image-2-official",
    ),
    "gpt-image-1-official": ModelSpec(
        name="gpt-image-1-official",
        allow_input_images=True,
        allow_mask=True,
        max_input_images=16,
        supports_n=True,
        min_n=1,
        max_n=10,
        default_size="1024x1024",
        family="gpt-image-1",
    ),
    "gpt-image-1.5-official": ModelSpec(
        name="gpt-image-1.5-official",
        allow_input_images=True,
        allow_mask=True,
        max_input_images=16,
        supports_n=True,
        min_n=1,
        max_n=10,
        default_size="1024x1024",
        family="gpt-image-1",
    ),
    "gemini-3.1-flash-image-preview": ModelSpec(
        name="gemini-3.1-flash-image-preview",
        allow_input_images=True,
        allow_mask=False,
        max_input_images=14,
        supports_n=True,
        min_n=1,
        max_n=4,
        default_size="1:1",
        family="gemini",
    ),
    "gemini-3-pro-image-preview": ModelSpec(
        name="gemini-3-pro-image-preview",
        allow_input_images=True,
        allow_mask=False,
        max_input_images=14,
        supports_n=True,
        min_n=1,
        max_n=4,
        default_size="1:1",
        family="gemini",
    ),
    "gemini-2.5-flash-image-preview": ModelSpec(
        name="gemini-2.5-flash-image-preview",
        allow_input_images=True,
        allow_mask=False,
        max_input_images=14,
        supports_n=True,
        min_n=1,
        max_n=4,
        default_size="1:1",
        family="gemini",
    ),
}


def print_info(message: str) -> None:
    print(message, flush=True)


def print_warning(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr, flush=True)


def print_error(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr, flush=True)


def load_config(config_path: Path = CONFIG_FILE) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict[str, Any], config_path: Path = CONFIG_FILE) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def resolve_api_key(
    cli_key: str | None,
    env_key: str | None = None,
    config_path: Path = CONFIG_FILE,
) -> str:
    if cli_key:
        return cli_key.strip()
    if env_key is None:
        env_key = os.environ.get("APIMART_API_KEY", "")
    if env_key and env_key.strip():
        return env_key.strip()
    config = load_config(config_path)
    file_key = str(config.get("api_key", "")).strip()
    if file_key:
        return file_key
    raise ApimartImageError(
        "APIMART API key not found. Run --setup, set APIMART_API_KEY, or pass --api-key."
    )


def resolve_model_name(cli_model: str | None) -> str:
    if cli_model and cli_model.strip():
        return cli_model.strip()
    env_model = os.environ.get("APIMART_IMAGE_MODEL", "").strip()
    if env_model:
        return env_model
    return DEFAULT_MODEL


def get_model_spec(model_name: str) -> ModelSpec:
    if model_name in MODELS:
        return MODELS[model_name]
    raise ApimartImageError(
        f"Unsupported model '{model_name}'. Supported models: {', '.join(sorted(MODELS))}"
    )


def validate_model_inputs(model_name: str, image_count: int, has_mask: bool) -> None:
    spec = get_model_spec(model_name)
    if image_count and not spec.allow_input_images:
        raise ApimartImageError(f"Model '{model_name}' does not support input images.")
    if image_count > spec.max_input_images:
        raise ApimartImageError(
            f"Model '{model_name}' supports at most {spec.max_input_images} input image(s)."
        )
    if has_mask and not spec.allow_mask:
        raise ApimartImageError(f"Model '{model_name}' does not support mask-based editing.")


def parse_extra_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApimartImageError(f"Invalid --extra-json: {exc}") from exc
    if not isinstance(value, dict):
        raise ApimartImageError("--extra-json must decode to a JSON object.")
    return value


def merge_nested(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_nested(result[key], value)
        else:
            result[key] = value
    return result


def build_generation_payload(
    model_name: str,
    prompt: str,
    image_urls: list[str],
    options: dict[str, Any],
    extra_json: str | None,
) -> tuple[dict[str, Any], list[str]]:
    spec = get_model_spec(model_name)
    validate_model_inputs(model_name, image_count=len(image_urls), has_mask=bool(options.get("mask_url")))

    payload: dict[str, Any] = {"model": model_name, "prompt": prompt}
    warnings: list[str] = []

    for key in ("size", "resolution"):
        value = options.get(key)
        if value:
            payload[key] = value

    if image_urls:
        payload["image_urls"] = image_urls

    if spec.supports_official_fallback and options.get("official_fallback") is not None:
        payload["official_fallback"] = bool(options["official_fallback"])
    elif bool(options.get("official_fallback")):
        warnings.append(f"official_fallback is ignored by model '{model_name}'.")

    if spec.family == "gemini":
        if options.get("quality") not in (None, ""):
            warnings.append(f"quality is ignored by model '{model_name}'.")
        if options.get("background") not in (None, ""):
            warnings.append(f"background is ignored by model '{model_name}'.")
        if options.get("moderation") not in (None, ""):
            warnings.append(f"moderation is ignored by model '{model_name}'.")
        if options.get("output_format") not in (None, ""):
            warnings.append(f"output_format is ignored by model '{model_name}'.")
        if options.get("output_compression") not in (None, ""):
            warnings.append(f"output_compression is ignored by model '{model_name}'.")
        if payload.get("size") and payload["size"] not in VALID_GEMINI_ASPECT_RATIOS:
            raise ApimartImageError(
                f"Model '{model_name}' requires --size to be one of {', '.join(sorted(VALID_GEMINI_ASPECT_RATIOS))}."
            )
        if payload.get("resolution"):
            normalized_resolution = str(payload["resolution"]).upper()
            if normalized_resolution not in VALID_GEMINI_RESOLUTIONS:
                raise ApimartImageError(
                    f"Model '{model_name}' requires --resolution to be one of {', '.join(sorted(VALID_GEMINI_RESOLUTIONS))}."
                )
            payload["resolution"] = normalized_resolution

    for field in spec.warned_ignored_fields:
        if options.get(field) not in (None, ""):
            warnings.append(f"{field} is not formally supported by model '{model_name}' and will be ignored.")

    passthrough_fields = (
        "quality",
        "background",
        "moderation",
        "output_format",
        "output_compression",
        "mask_url",
    )
    for field in passthrough_fields:
        value = options.get(field)
        if value in (None, ""):
            continue
        if field == "mask_url" and not spec.allow_mask:
            raise ApimartImageError(f"Model '{model_name}' does not support --mask.")
        payload[field] = value

    n_value = options.get("n")
    if n_value is not None:
        if not spec.supports_n:
            warnings.append(f"n is ignored by model '{model_name}'.")
        else:
            try:
                n_int = int(n_value)
            except (TypeError, ValueError) as exc:
                raise ApimartImageError("--n must be an integer.") from exc
            if not spec.min_n <= n_int <= spec.max_n:
                raise ApimartImageError(
                    f"Model '{model_name}' requires --n between {spec.min_n} and {spec.max_n}."
                )
            payload["n"] = n_int

    merged = merge_nested(payload, parse_extra_json(extra_json))
    return merged, warnings


def slugify(text: str, fallback: str = "image") -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value[:48] or fallback


def choose_output_path(
    output: str | None,
    output_dir: Path | None,
    prompt: str,
    index: int,
    extension: str,
) -> Path:
    if output:
        return Path(output)
    base_dir = output_dir or DEFAULT_OUTPUT_DIR
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    slug = slugify(prompt)
    suffix = f"_{index + 1:02d}" if index else ""
    return base_dir / f"{timestamp}_{slug}{suffix}{extension}"


def ensure_output_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def resolve_worker_count(num_tasks: int, workers: int, default_workers: int = DEFAULT_BATCH_WORKERS) -> int:
    if num_tasks <= 0:
        return 0
    if workers <= 0:
        workers = min(num_tasks, default_workers)
    return max(1, min(workers, num_tasks))


def run_batched_tasks(
    tasks: list[dict[str, Any]],
    workers: int,
    runner: Callable[[int, dict[str, Any]], BatchResultT],
    label: str,
) -> list[BatchResultT]:
    task_count = len(tasks)
    if task_count == 0:
        return []

    worker_count = resolve_worker_count(task_count, workers)
    print_info(f"[{label}] tasks={task_count} workers={worker_count}")
    results: list[BatchResultT | None] = [None] * task_count

    def invoke(index: int, task: dict[str, Any]) -> tuple[int, BatchResultT]:
        return index, runner(index, task)

    if worker_count == 1:
        for index, task in enumerate(tasks):
            _, result = invoke(index, task)
            results[index] = result
        return [result for result in results if result is not None]

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [pool.submit(invoke, index, task) for index, task in enumerate(tasks)]
        for future in as_completed(futures):
            index, result = future.result()
            results[index] = result

    return [result for result in results if result is not None]


def load_batch_tasks(batch_path: str | Path) -> list[dict[str, Any]]:
    path = Path(batch_path)
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ApimartImageError(f"Batch file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ApimartImageError(f"Batch file is not valid JSON: {exc}") from exc
    if not isinstance(content, list):
        raise ApimartImageError("Batch file must contain a JSON array.")
    for idx, item in enumerate(content):
        if not isinstance(item, dict):
            raise ApimartImageError(f"Batch item {idx} must be a JSON object.")
    return content


def is_remote_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def guess_extension_from_url(url: str, default: str = ".png") -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    return suffix or default


def read_local_image(path: str | Path) -> tuple[bytes, str]:
    image_path = Path(path)
    if not image_path.exists():
        raise ApimartImageError(f"Input image not found: {image_path}")
    suffix = image_path.suffix.lower()
    if suffix not in SUPPORTED_IMAGE_SUFFIXES:
        raise ApimartImageError(
            f"Unsupported input image format '{suffix}'. Supported: {', '.join(sorted(SUPPORTED_IMAGE_SUFFIXES))}"
        )
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = "application/octet-stream"
    return image_path.read_bytes(), mime_type


def extract_upload_url(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("url"),
        payload.get("image_url"),
        payload.get("data", {}).get("url") if isinstance(payload.get("data"), dict) else None,
        payload.get("data", {}).get("image_url") if isinstance(payload.get("data"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    raise ApimartImageError(f"Could not find uploaded image URL in response: {payload}")


def extract_result_image_urls(payload: dict[str, Any]) -> list[str]:
    if not isinstance(payload, dict):
        raise ApimartImageError(f"Unexpected task status payload: {payload!r}")

    image_urls = payload.get("image_urls")
    if isinstance(image_urls, list):
        return [item for item in image_urls if isinstance(item, str) and item]

    data = payload.get("data")
    if isinstance(data, dict):
        nested_urls = data.get("image_urls")
        if isinstance(nested_urls, list):
            return [item for item in nested_urls if isinstance(item, str) and item]
        url = data.get("image_url") or data.get("url")
        if isinstance(url, str) and url:
            return [url]
        result = data.get("result")
        if isinstance(result, dict):
            nested_urls = result.get("image_urls")
            if isinstance(nested_urls, list):
                return [item for item in nested_urls if isinstance(item, str) and item]
            images = result.get("images")
            if isinstance(images, list):
                collected: list[str] = []
                for image in images:
                    if not isinstance(image, dict):
                        continue
                    url_value = image.get("url")
                    if isinstance(url_value, str) and url_value:
                        collected.append(url_value)
                    elif isinstance(url_value, list):
                        collected.extend(
                            [entry for entry in url_value if isinstance(entry, str) and entry]
                        )
                if collected:
                    return collected

    single = payload.get("image_url") or payload.get("url")
    if isinstance(single, str) and single:
        return [single]

    return []


def normalize_status(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("status", "state"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value.lower()
    for key in ("status", "state"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value.lower()
    return ""


class ApimartClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 180):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ApimartClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = self.base_url + path
        headers = dict(kwargs.pop("headers", {}) or {})
        if "json" in kwargs and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        if headers:
            kwargs["headers"] = headers
        response = self._client.request(method, url, **kwargs)
        return response

    def _sleep_before_retry(self, attempt: int) -> None:
        time.sleep(min(2**attempt, 8))

    def _should_retry_transport_error(self, attempt: int, retries: int, exc: httpx.TransportError) -> bool:
        if attempt >= retries:
            return False
        print_warning(f"Transient network error: {exc}. Retrying...")
        self._sleep_before_retry(attempt)
        return True

    def upload_image(self, image_path: str | Path, retries: int = MAX_NETWORK_RETRIES) -> str:
        raw, mime_type = read_local_image(image_path)
        for attempt in range(retries + 1):
            try:
                response = self._client.post(
                    self.base_url + "/v1/uploads/images",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (Path(image_path).name, raw, mime_type)},
                )
            except httpx.TransportError as exc:
                if self._should_retry_transport_error(attempt, retries, exc):
                    continue
                raise ApimartImageError(f"Upload failed after retries: {exc}") from exc
            if response.status_code >= 400:
                raise ApimartImageError(f"Upload failed: HTTP {response.status_code} {response.text[:400]}")
            return extract_upload_url(response.json())
        raise ApimartImageError("Upload failed after retries: unknown error")

    def create_generation_task(self, payload: dict[str, Any], retries: int = 3) -> tuple[str, dict[str, Any]]:
        last_error: str | None = None
        for attempt in range(retries + 1):
            try:
                response = self._request("POST", "/v1/images/generations", json=payload)
            except httpx.TransportError as exc:
                if self._should_retry_transport_error(attempt, retries, exc):
                    last_error = str(exc)
                    continue
                raise ApimartImageError(f"Task creation failed after retries: {exc}") from exc
            if response.status_code < 400:
                body = response.json()
                task_id = extract_task_id(body)
                if not task_id:
                    raise ApimartImageError(f"Task creation response missing task_id: {body}")
                return str(task_id), body
            if response.status_code not in RETRYABLE_STATUS_CODES or attempt >= retries:
                raise ApimartImageError(
                    f"Task creation failed: HTTP {response.status_code} {response.text[:400]}"
                )
            last_error = response.text[:400]
            self._sleep_before_retry(attempt)
        raise ApimartImageError(f"Task creation failed after retries: {last_error or 'unknown error'}")

    def poll_task(
        self,
        task_id: str,
        poll_interval: float = 2.0,
        timeout_seconds: int = 600,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        last_transport_error: httpx.TransportError | None = None
        while time.time() < deadline:
            try:
                response = self._request("GET", f"/v1/tasks/{task_id}")
            except httpx.TransportError as exc:
                last_transport_error = exc
                print_warning(f"Transient polling error for task '{task_id}': {exc}. Retrying...")
                time.sleep(poll_interval)
                continue
            if response.status_code >= 400:
                raise ApimartImageError(
                    f"Task status check failed: HTTP {response.status_code} {response.text[:400]}"
                )
            payload = response.json()
            status = normalize_status(payload)
            if status in POLL_DONE_STATUSES:
                return payload
            if status in POLL_FAILED_STATUSES:
                raise ApimartImageError(f"Task '{task_id}' failed with payload: {payload}")
            time.sleep(poll_interval)
        if last_transport_error is not None:
            raise ApimartImageError(
                f"Timed out waiting for task '{task_id}' after transient polling errors: {last_transport_error}"
            ) from last_transport_error
        raise ApimartImageError(f"Timed out waiting for task '{task_id}'.")

    def download_image(self, url: str, output_path: Path, retries: int = MAX_NETWORK_RETRIES) -> Path:
        ensure_output_parent(output_path)
        for attempt in range(retries + 1):
            try:
                response = self._client.get(url, headers={"Authorization": f"Bearer {self.api_key}"})
            except httpx.TransportError as exc:
                if self._should_retry_transport_error(attempt, retries, exc):
                    continue
                raise ApimartImageError(f"Image download failed after retries: {exc}") from exc
            if response.status_code >= 400:
                raise ApimartImageError(
                    f"Image download failed: HTTP {response.status_code} {response.text[:400]}"
                )
            output_path.write_bytes(response.content)
            return output_path
        raise ApimartImageError("Image download failed after retries: unknown error")


def coerce_base_url(cli_value: str | None) -> str:
    if cli_value and cli_value.strip():
        return cli_value.strip().rstrip("/")
    env_value = os.environ.get("APIMART_BASE_URL", "").strip()
    if env_value:
        return env_value.rstrip("/")
    return DEFAULT_BASE_URL


def extract_task_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        direct = payload.get("task_id") or payload.get("id")
        if isinstance(direct, str) and direct:
            return direct
        data = payload.get("data")
        if isinstance(data, dict):
            nested = data.get("task_id") or data.get("id")
            if isinstance(nested, str) and nested:
                return nested
        if isinstance(data, list):
            for item in data:
                found = extract_task_id(item)
                if found:
                    return found
    if isinstance(payload, list):
        for item in payload:
            found = extract_task_id(item)
            if found:
                return found
    return None


def run_setup(config_path: Path = CONFIG_FILE) -> None:
    print_info(f"Config file: {config_path}")
    current = load_config(config_path)
    existing = str(current.get("api_key", "")).strip()
    if existing:
        masked = existing[:6] + "..." + existing[-4:]
        print_info(f"Existing API key: {masked}")
    api_key = input("Enter APIMART API key: ").strip()
    if not api_key:
        raise ApimartImageError("API key cannot be empty.")
    current["api_key"] = api_key
    save_config(current, config_path)
    print_info(f"Saved config to {config_path}")
