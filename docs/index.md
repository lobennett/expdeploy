# expdeploy

A modern Python deploy tool for [jsPsych v8](https://www.jspsych.org/) experiments.

**Status: v0.1.0** — lab-ready.

## What it does

- Serves jsPsych v8 experiments locally with **zero Node.js dependency** for experimenters.
- Authoring in canonical ESM (`import { initJsPsych } from 'jspsych'`) with local imports working out of the box.
- **BIDS-compatible** filesystem layout for fMRI and behavioral data.
- **Batteries** of experiments with four counterbalance schemes (fixed, Latin square, seeded random, user-supplied).
- **Local-first** storage with optional Supabase mirror, replayable via `expdeploy sync`.
- **Reproducibility**: layered OCI images via `expdeploy build` — a study image freezes deploy version, jsPsych version, every experiment file, and every Python dep.

## Quick install

```bash
uv tool install expdeploy
expdeploy run ./examples/hello_world --subject 01
```

→ [Getting started](getting-started.md)
