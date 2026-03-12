---
name: skill-img-upscale-fix
description: Execute Runninghub SeedVR2 image upscale quickly. Use for "图像修复放大" and "图像无损放大". Route repair requests to repair mode, route lossless requests to workflowId 2031989838488014849, and only pass resolution when the user explicitly asks for target pixels.
metadata: {"openclaw":{"requires":{"bins":["python"],"env":["RUNNINGHUB_API_KEY"]}}}
---

# SeedVR2 Upscale

Run fast, script-first, and return only final output URLs plus task status.

Use this script path:
- `{baseDir}/scripts/run_seedvr2_upscale.py`

## Route

- User says "图像修复放大": use `--mode repair`.
- User says "图像无损放大": use `--mode lossless` (built-in workflowId `2031989838488014849`).
- Do not pass `--resolution` unless user explicitly gives target pixel size.

## Command

Repair:

```powershell
python "{baseDir}/scripts/run_seedvr2_upscale.py" --image "<image_path>" --mode repair
```

Lossless:

```powershell
python "{baseDir}/scripts/run_seedvr2_upscale.py" --image "<image_path>" --mode lossless
```

Lossless with explicit target resolution:

```powershell
python "{baseDir}/scripts/run_seedvr2_upscale.py" --image "<image_path>" --mode lossless --resolution 4000
```

Return:
- `taskId`
- final `status`
- output image URLs from `outputs`
