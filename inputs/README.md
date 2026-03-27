# inputs/

This folder is the **drop-folder** for the agent in dev mode (`CAMERA_MODE=folder`).

## How it works:
1. Start the full Docker stack: `docker compose --env-file .env.dev up -d`
2. Copy any invoice/label JPEG or PNG into this folder
3. The agent auto-detects it, processes it within seconds, and moves it to `inputs/processed/`

## Supported file formats:
- `.jpg` / `.jpeg`
- `.png`
- `.bmp`
- `.tiff`

## After processing:
Files are moved to `inputs/processed/` automatically.
