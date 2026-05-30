# APIMart Image Reference

## Core Endpoints

- `POST /v1/uploads/images`
  - Upload a local image and receive a URL that can be passed to image generation models.
- `POST /v1/images/generations`
  - Submit an asynchronous image generation or image editing task.
- `GET /v1/tasks/{task_id}`
  - Poll task status until the image job completes or fails.

Use bearer authentication with `Authorization: Bearer <APIMART_API_KEY>`.

## Supported Models In This Skill

This skill only supports the GPT image and Gemini image families from the APIMart image docs:

- `gpt-image-2`
- `gpt-image-2-official`
- `gpt-image-1-official`
- `gpt-image-1.5-official`
- `gemini-2.5-flash-image-preview`
- `gemini-3.1-flash-image-preview`
- `gemini-3-pro-image-preview`

Do not use this skill for Qwen, Seedream, Z-Image, Grok Imagine, Flux, or other image families outside GPT and Gemini.

## Model Capability Matrix

| Model | Text-to-image | Image edit | Mask | Notes |
| --- | --- | --- | --- | --- |
| `gpt-image-2` | yes | yes | no | Supports `official_fallback`; ignore `quality`, `style`, `response_format` |
| `gpt-image-2-official` | yes | yes | yes | Supports `quality`, `background`, `moderation`, `output_format`, `output_compression`, `n`, `mask_url` |
| `gpt-image-1-official` | yes | yes | yes | Supports OpenAI-style official image options |
| `gpt-image-1.5-official` | yes | yes | yes | Similar to `gpt-image-1-official` |
| `gemini-2.5-flash-image-preview` | yes | yes | no | Up to 14 input images, `size` uses aspect ratios such as `1:1` and `16:9` |
| `gemini-3.1-flash-image-preview` | yes | yes | no | Up to 14 input images, `n` up to 4 |
| `gemini-3-pro-image-preview` | yes | yes | no | Gemini Pro image route, same aspect-ratio style inputs |

## GPT-Image 2 vs GPT-Image 2 Official

### `gpt-image-2`

Use when the user wants GPT-Image 2 through the regular APIMart route.

Supported fields in this skill:

- `model`
- `prompt`
- `size`
- `resolution`
- `image_urls`
- `official_fallback`

Warn and ignore by default:

- `quality`
- `style`
- `response_format`

Constraints:

- `image_urls` maximum: 16
- `mask_url`: not supported

### `gpt-image-2-official`

Use when the user needs GPT-Image 2 official-channel features.

Supported fields in this skill:

- `model`
- `prompt`
- `size`
- `resolution`
- `image_urls`
- `mask_url`
- `quality`
- `background`
- `moderation`
- `output_format`
- `output_compression`
- `n`

Constraints:

- `image_urls` maximum: 16
- `n`: `1-4`
- `background=transparent` is not promised by this skill; if the provider degrades it, report that plainly

## Gemini Image Models

Gemini image models in this skill use APIMart's Gemini routes, including:

- `gemini-2.5-flash-image-preview`
- `gemini-3.1-flash-image-preview`
- `gemini-3-pro-image-preview`

Supported fields in this skill:

- `model`
- `prompt`
- `image_urls`
- `size`
- `resolution`
- `n`
- `official_fallback`

Gemini-specific constraints enforced by this skill:

- `image_urls` maximum: 14
- `n`: `1-4`
- `mask_url`: not supported
- `size` must be one of `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`, `21:9`, `5:4`, `4:5`
- `resolution` must be one of `1K`, `2K`, `4K`

Fields ignored with warnings:

- `quality`
- `background`
- `moderation`
- `output_format`
- `output_compression`

## Payload Shape Guidance

Base payload:

```json
{
  "model": "gpt-image-2",
  "prompt": "A refined editorial portrait",
  "size": "1536x1024",
  "resolution": "2K"
}
```

Edit payload:

```json
{
  "model": "gemini-3.1-flash-image-preview",
  "prompt": "Replace the background with a foggy mountain lake while preserving the person",
  "image_urls": ["https://cdn.apimart.ai/example/input.png"],
  "size": "16:9",
  "resolution": "2K",
  "n": 1
}
```

## Batch Task File Shapes

Text-to-image:

```json
[
  {
    "model": "gpt-image-2",
    "prompt": "A book cover with brutalist typography",
    "size": "1536x1024",
    "resolution": "2K",
    "output": "./outimage/apimart-image/book-cover.png"
  }
]
```

You can run batch jobs concurrently with `--workers`:

```powershell
python C:\Users\29664\.codex\skills\apimart-image\scripts\generate_apimart.py `
  --batch .\tasks.json `
  --workers 2
```

Image edit:

```json
[
  {
    "model": "gemini-3-pro-image-preview",
    "inputs": ["./portrait.png"],
    "prompt": "Swap the jacket for a charcoal wool coat while preserving the pose and face",
    "size": "3:4",
    "resolution": "2K",
    "output": "./outimage/apimart-image/coat-edit.png"
  }
]
```

## Error Handling Notes

- Missing API key: use `--setup`, `APIMART_API_KEY`, or `C:\Users\29664\.codex\skills\apimart-image\config.json`.
- Unsupported field combination: fail early with a clear message.
- Task completed without image URLs: treat as an API or payload-shape error and show the task payload.
- Download failure after a successful task: report the remote URL and the HTTP status.
