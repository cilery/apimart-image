---
name: apimart-image
description: Use when the user explicitly wants to generate or edit images through APIMart, mentions APIMart image models or APIMart image keys, asks for GPT-Image or Gemini image generation models on APIMart, or wants batch image generation/editing with the local `generate_apimart.py` or `generate_apimart_edit.py` scripts.
---

# APIMart Image

Use this skill when the user wants to call APIMart image models from a local script workflow. This skill only supports the GPT image and Gemini image series shown in the APIMart image docs. Do not route requests for Qwen, Seedream, Z-Image, Grok Imagine, Flux, or other non-target families through this skill.

## What This Skill Does

This skill uses the local scripts below:

- `C:\Users\29664\.codex\skills\apimart-image\scripts\generate_apimart.py`
- `C:\Users\29664\.codex\skills\apimart-image\scripts\generate_apimart_edit.py`

Supported tasks:

- text-to-image
- image-to-image editing
- mask-based editing for models that support it
- batch generation
- batch editing

Supported model families:

- `gpt-image-2`
- `gpt-image-2-official`
- `gpt-image-1-official`
- `gpt-image-1.5-official`
- `gemini-2.5-flash-image-preview`
- `gemini-3.1-flash-image-preview`
- `gemini-3-pro-image-preview`

Read `references/apimart-images.md` when model-specific payload details matter.

## Behavior Rules

- Respect the user's requested style and constraints. Do not silently add Chinese-style assumptions.
- Default to Chinese prompts when the user is speaking Chinese, and English prompts when the user is speaking English, unless the user asks otherwise.
- Preserve the subject during image edits unless the user explicitly asks for stronger transformation.
- Save outputs under the current workspace when possible. Prefer `.\outimage\apimart-image\`.
- Do not claim an image was generated until the script completes successfully and the output file exists.
- Gemini models in this skill use APIMart's Gemini image generation route with aspect-ratio-like `--size` values such as `1:1` or `16:9`.

## First-Time Setup

The scripts need an APIMart API key.

Preferred setup command on this Windows machine:

```powershell
python C:\Users\29664\.codex\skills\apimart-image\scripts\generate_apimart.py --setup
```

Alternative environment variable:

```powershell
$env:APIMART_API_KEY="sk-your-key"
```

Alternative config file:

- Path: `C:\Users\29664\.apimart-image\config.json`
- Content:

```json
{
  "api_key": "sk-your-key"
}
```

API key resolution order:

1. `--api-key`
2. `APIMART_API_KEY`
3. `C:\Users\29664\.apimart-image\config.json`

Optional base URL override:

```powershell
$env:APIMART_BASE_URL="https://api.apimart.ai"
```

## Standard Workflow

1. Decide whether the task is text-to-image, image edit, or batch work.
2. Pick a supported model. Prefer:
   - `gpt-image-2` for general APIMart GPT image generation
   - `gpt-image-2-official` when the user needs mask editing or official-only options like `quality` and `output_format`
   - `gemini-3.1-flash-image-preview` for Gemini image generation with multiple reference images
   - `gemini-3-pro-image-preview` for higher-end Gemini image generation
   - `gemini-2.5-flash-image-preview` for Gemini image generation on the 2.5 flash family
3. Extract or refine:
   - prompt
   - model
   - size or aspect-ratio-like size value
   - resolution
   - output path
4. Run the appropriate local script.
5. Return the saved file path, task id, and source image URL(s).

## Text-To-Image

Use `generate_apimart.py`.

Example with `gpt-image-2`:

```powershell
python C:\Users\29664\.codex\skills\apimart-image\scripts\generate_apimart.py `
  --model gpt-image-2 `
  --prompt "A cinematic lighthouse poster at sunset, dramatic clouds, crisp typography space, high contrast composition" `
  --size 1536x1024 `
  --resolution 2K `
  --output .\outimage\apimart-image\20260529_1900_lighthouse.png
```

Example with `gemini-3.1-flash-image-preview`:

```powershell
python C:\Users\29664\.codex\skills\apimart-image\scripts\generate_apimart.py `
  --model gemini-3.1-flash-image-preview `
  --prompt "A clean editorial portrait of a watchmaker in a bright workshop, realistic lighting, shallow depth of field" `
  --size 1:1 `
  --resolution 2K `
  --output .\outimage\apimart-image\20260529_1905_watchmaker.png
```

## Image Editing

Use `generate_apimart_edit.py`.

The script uploads local input images to APIMart first, then submits `/v1/images/generations`, then polls `/v1/tasks/{task_id}`.

Example with `gpt-image-2-official` and mask:

```powershell
python C:\Users\29664\.codex\skills\apimart-image\scripts\generate_apimart_edit.py `
  --model gpt-image-2-official `
  --input .\photo.png `
  --mask .\mask.png `
  --prompt "Replace the masked background with a snowy harbor at blue hour while keeping the subject identity unchanged" `
  --quality high `
  --output-format png `
  --output .\outimage\apimart-image\20260529_1910_harbor-edit.png
```

Example with `gemini-3-pro-image-preview`:

```powershell
python C:\Users\29664\.codex\skills\apimart-image\scripts\generate_apimart_edit.py `
  --model gemini-3-pro-image-preview `
  --input .\room.jpg `
  --prompt "Turn this room into a quiet Nordic reading corner, preserve layout and camera angle" `
  --size 16:9 `
  --resolution 2K `
  --output .\outimage\apimart-image\20260529_1915_room-edit.png
```

## Batch Generation

Use `generate_apimart.py --batch` or `generate_apimart_edit.py --batch`.

Text-to-image batch example:

```json
[
  {
    "model": "gpt-image-2",
    "prompt": "A moody subway poster, stark lighting, wide composition",
    "size": "1536x1024",
    "resolution": "2K",
    "output": "./outimage/apimart-image/subway-poster.png"
  },
  {
    "model": "gemini-2.5-flash-image-preview",
    "prompt": "A refined skincare product shot on wet stone, soft studio light",
    "size": "1:1",
    "resolution": "2K",
    "output": "./outimage/apimart-image/skincare-shot.png"
  }
]
```

Edit batch example:

```json
[
  {
    "model": "gpt-image-2-official",
    "inputs": ["./photo.png"],
    "mask": "./mask.png",
    "prompt": "Replace only the masked sky with a dramatic aurora scene",
    "output": "./outimage/apimart-image/aurora-edit.png"
  }
]
```

## Failure Handling

- If the API key is missing, tell the user to run the setup command or configure `APIMART_API_KEY`.
- If the task times out, retry with a lower resolution or a simpler prompt.
- If the model rejects a parameter combination, remove unsupported options instead of forcing them through.
- If the output misses a required detail, refine the prompt and rerun instead of claiming success.
- If the user asks for Qwen, Seedream, Z-Image, Grok Imagine, Flux, or another non-target family, say this skill does not support it and ask for a supported GPT or Gemini image model instead.

## Notes For Codex

- This is a local user-installed skill, not a built-in image tool.
- Prefer `gpt-image-2` and `gpt-image-2-official` when the user explicitly asks for GPT-Image 2.
- Prefer `gpt-image-2-official` over `gpt-image-2` when the user needs `mask`, `quality`, `output_format`, `output_compression`, or `n`.
- Prefer Gemini models when the user explicitly asks for Gemini image generation or wants APIMart's Nano banana routes.
- For detailed payload differences, read `references/apimart-images.md`.
