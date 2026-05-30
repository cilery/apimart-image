# APIMart Image

APIMart Image is a local Codex skill for generating and editing images through APIMart GPT-image and Gemini image models.

It provides a script-first workflow for:

- text-to-image generation
- image-to-image editing
- mask-based editing on supported official GPT-image routes
- batch jobs with configurable worker concurrency
- common aspect ratios including `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`, `21:9`, `5:4`, `4:5`
- output quality tiers such as `1K`, `2K`, and `4K` on supported Gemini routes

## Included Scripts

- `scripts/generate_apimart.py`
  - text-to-image generation
  - batch generation via `--batch`
- `scripts/generate_apimart_edit.py`
  - image editing
  - mask-based editing where the selected model supports it
  - batch editing via `--batch`
- `scripts/_apimart_common.py`
  - shared payload building, validation, retries, downloads, and batch helpers

## Supported Model Families

- `gpt-image-2`
- `gpt-image-2-official`
- `gpt-image-1-official`
- `gpt-image-1.5-official`
- `gemini-2.5-flash-image-preview`
- `gemini-3.1-flash-image-preview`
- `gemini-3-pro-image-preview`

## Setup

Configure your APIMart API key locally before use:

```powershell
python .\scripts\generate_apimart.py --setup
```

Or create a local `config.json` file that is not committed:

```json
{
  "api_key": "sk-your-key"
}
```

You can also use:

```powershell
$env:APIMART_API_KEY="sk-your-key"
```

## Examples

Text-to-image:

```powershell
python .\scripts\generate_apimart.py `
  --model gemini-3.1-flash-image-preview `
  --prompt "A refined editorial portrait of a watchmaker in a bright workshop, realistic lighting" `
  --size 4:5 `
  --resolution 2K `
  --output .\outimage\apimart-image\watchmaker.png
```

Image edit:

```powershell
python .\scripts\generate_apimart_edit.py `
  --model gpt-image-2-official `
  --input .\photo.png `
  --prompt "Replace the background with a snowy harbor while preserving the subject" `
  --quality high `
  --output-format png `
  --output .\outimage\apimart-image\harbor-edit.png
```

Batch generation:

```powershell
python .\scripts\generate_apimart.py `
  --batch .\tasks.json `
  --workers 2
```

## Notes

- API keys are intentionally kept out of version control.
- Generated output is ignored by git by default.
- This repository publishes the usable skill and scripts only, without local tests or private configuration.
