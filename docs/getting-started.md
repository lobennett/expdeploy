# Getting started

## Install

The package will be available on PyPI after the v0.1.0 release:

```bash
uv tool install expdeploy
```

For development:

```bash
git clone https://github.com/lobennett/expdeploy.git
cd expdeploy
uv sync --extra dev
```

## Run the hello-world

```bash
expdeploy run ./examples/hello_world --subject 01 --port 8080
```

This opens `http://localhost:8080` in your browser. Press any key on the stimulus and you'll see a `Saved.` confirmation. The raw JSON lands at `./data/raw/sub-01/sub-01_task-hello_beh.json`; an entry appears in `./data/catalog.sqlite`.

## Inspect runs

```bash
expdeploy status --data-dir ./data
```

## Run a battery

```bash
expdeploy run ./examples/mini_battery/battery.toml --subject 0
```

Or inline:

```bash
expdeploy run \
  --exps ./flanker,./stroop,./nback \
  --counterbalance latin_square \
  --subject 01
```
