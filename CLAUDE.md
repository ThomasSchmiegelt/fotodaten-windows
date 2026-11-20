# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"Bildermacher 1.0": a local web UI (plus GIMP 3 plugin) around Qwen-Image 2.1 for text-to-image, image editing, group shots, image sequences/videos, and a training-data pipeline (generate variants → auto bounding boxes → verify → multiply → train a detector with D-FINE or YOLO26). Image and language models can run locally or through an OpenAI-compatible cloud API. `README.md` explains the design and the measurements behind it; `ANLEITUNG.md` is the user manual.

## Commands

```bash
./einrichten.sh [training|nurcloud|lokal] [cu126] [ohnemodelle]   # set up venv qwen_bild/, packages, models (re-runnable)
./start.sh [PORT]                       # start server + open browser, default http://127.0.0.1:7860
./stop.sh                               # kill running server
./qwen_bild/bin/python webui/server.py  # run server directly (no env setup from start.sh)
./qwen_bild/bin/python webui/pruefung.py   # the only check: UI vs. running server (server on 7860 must be up)
./qwen_bild/bin/python demo/demonstration.py --ablauf reise   # run a sequence from the CLI
./gimp/install.sh                       # link GIMP plugin
```

There is no test suite, linter config or build step. `pruefung.py` checks that `app.js` only reads fields `/api/info` actually returns, that every referenced DOM element exists, that brackets balance, and that the running server uses the code on disk. Run it after changing `server.py` responses or `webui/seite/`.

Windows equivalents: `einrichten.bat`, `start.bat`, `installieren.bat` (dev venv); `portable/bauen.py` does the real work behind `einrichten.*`.

**Only one server instance at a time.** Two processes each loading ~17 GB onto the GPU evict each other.

## Environment that start.sh sets

`start.sh` sources `lokal.env` (machine-specific, not in the repo), sets `HF_HOME=./daten/hf`, `YOLO_CONFIG_DIR=./modelle/yolo/einstellungen`, `HF_HUB_DISABLE_XET=1` and `PYTHONUTF8=1`. If the marker `daten/bildmodell_lokal.txt` (written by `einrichten.sh lokal`) is missing, it sets `QWEN_NUR_CLOUD=1`, and `engine.py` never imports torch/diffusers for the image model. Code must keep working without torch in that mode. The README lists the other env vars (`QWEN_HOST`, `QWEN_PORT`, `OLLAMA_URL`, `QWEN_CHAT_MODEL`, `QWEN_BOX_*`, `QWEN_YOLO_*`, `QWEN_IMAGE_REVISION`). Cloud credentials live in `einstellungen.json` (gitignored, mode 600), never in env vars.

## Architecture

- **`webui/server.py`**: stdlib `ThreadingHTTPServer`, routes and startup only. It imports the feature modules and serves `webui/seite/` (`index.html`, `stil.css`, `app.js`; plain JS, no build).
- **`webui/auftraege.py`**: the job queue. `einreihen(art, params)` enqueues and a single worker thread runs jobs one after another under `engine.lock`. `_abarbeiten` dispatches on `art` to `run_*` functions (`run_job` is the default for plain generation). Consecutive compatible `generate` jobs are bundled (`_buendelbar`) into one series so they share a single model load. Progress and results go into the shared dict `current`, which the UI polls.
- **`webui/engine.py`**: the two-phase pipeline (the core design constraint). The model is ~33 GB in bf16 and does not fit in GPU or RAM at once, so each series first loads the text encoder and embeds all prompts, frees it, then loads transformer + VAE and denoises/decodes all images. `enable_model_cpu_offload()` is deliberately not used. The VAE decodes in one piece up to `QWEN_VOLLBILD` (1 MP) and tiles above that, because tiling leaves visible banding. The reference resolution drops as the number of references grows (`reference_resolution`). Cloud generation goes through `Engine._aus_der_cloud`.
- **`webui/kataloge/`**: preset tables (style/light/camera/colour in `anmutung.py`, environment/view/material in `motiv.py`, prompt templates/effects/groups in `vorlage.py`). The server validates language-model output against these real tables rather than with a JSON schema; a schema measurably hurt comprehension.
- **`webui/sprache/`**: everything language-model related (Ollama or cloud). The server talks only to the package `__init__`, not to the individual files.
- **`webui/variablen.py`**: `#name#` variables (values per image, drawn from seed + index) and `!Person!` reference (also a description like `!die erste Frau!`). `run_job` in `auftraege.py` masks them as `[[n]]` before translation, builds one prompt per image via `_fertige_jobs`, and passes `prompts` + `seeds` to `run_series`. Jobs with variables or a person are never bundled.
- **`webui/pibruecke.py`**: pi (`@earendil-works/pi-coding-agent`) as a child process in RPC mode with exactly one tool (`webui/pi/bildprompt.ts`). The server detects `tool_execution_start` for `bildprompt_senden`, sanitises the args, exposes events via long-poll `GET /api/pi/ereignisse`, and unloads the Ollama model afterwards. The window is `webui/seite/pi.html`, and it hands over to the main page via `BroadcastChannel("bildermacher")`.
- **Language model choice**: `sprache/ollama.py` redirects the default names `MODEL`/`GROSS` to the user's choice in `rufen()` (one choke point, stored in `sprachmodelle.json`). Don't import the chosen name by value; call `gewaehlt("klein"|"gross")`.
- **`webui/cloud.py`**: OpenAI-compatible API for both the chat and the image model.
- Feature modules: `ablauf.py` (sequences as data blocks, the bundled sequences), `geschichte.py`/`szenenbau.py` (story → scenes → staged composition), `sechsseiten.py` (six views of an object; writes to `katalog/`, not `outputs/`), `retusche.py`, `projekte.py` (separate storage under `projekte/`), `bausteine.py` (reusable people/places/objects with gaps), `torwache.py` (removes excluded terms from the final prompt; shared by jobs and stories).
- Training-data chain: `fotodaten.py` (variant plan for real photos, EXIF, box transforms) → `datensatz.py` (Qwen3-VL boxes checked by Grounding DINO, YOLO/COCO export) → `vervielfaeltigen.py` (augmentation where the box is carried along; SD1.5 + ControlNet for new environments) → `detektor.py` with `detektor_lauf.py` / `yolo_lauf.py` running **as separate subprocesses** (on Windows they are killed with `taskkill /T`).

Outputs go to `outputs/`, projects to `projekte/`, models to `daten/` and `modelle/`. All of these are gitignored and must never be committed.

## Conventions (from CONTRIBUTING.md)

- **German** identifiers, comments and commit messages. Identifiers and comments use no umlauts (`ae`/`oe`/`ue`); UI text and Markdown use real umlauts.
- Comments explain *why*. Many choices rest on measurements ("gemessen …"). If you change such a decision, re-measure and update the comment and the README.
- New dependencies need a reason and a license compatible with MIT (no AGPL or other copyleft). Version pins in `requirements*.txt` are deliberate: `diffusers` is pinned to a commit, `polars==1.31.0` and cu130 are pinned because Windows Smart App Control blocks other builds.
- Windows matters as much as Linux. Run pip as `python -m pip`, and keep the platform guards (e.g. `expandable_segments` is Linux-only).
- `server.py` wraps `do_GET`/`do_POST`: it rejects foreign `Host`/`Origin` (CSRF/DNS rebinding), reads the POST body up front (keep-alive), and turns exceptions into JSON errors. Routes live in `_get`/`_post`.
- The "open in GIMP" endpoint only accepts requests from `127.0.0.1`, even with `QWEN_HOST=0.0.0.0`.
