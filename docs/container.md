# Container

The OCI image lives at `ghcr.io/lobennett/expdeploy:<version>` (multi-arch: linux/amd64 + linux/arm64).

## Day-to-day dev (bind-mount)

```bash
podman run --rm -p 8080:8080 \
  -v $PWD/experiments:/experiments:ro \
  -v $PWD/data:/data \
  ghcr.io/lobennett/expdeploy:latest \
  run /experiments/flanker --subject 01 --data-dir /data
```

## Study image (reproducible scientific artifact)

`expdeploy build` produces an image with experiments baked in. This is the image you cite in your paper.

```bash
expdeploy build ./battery.toml \
  --tag ghcr.io/your-lab/study-2026:2026-05-17 \
  --engine podman \
  --push
```

The generated `study.Dockerfile` is written next to the battery file and is gitable for transparency. The image carries OCI labels:

- `org.expdeploy.manifest_hash` — content hash of every experiment file + battery.toml
- `org.expdeploy.deploy_version` — `expdeploy` version that built the image

## Apptainer / Singularity

```bash
apptainer pull docker://ghcr.io/lobennett/expdeploy:latest
apptainer run --bind ./experiments:/experiments --bind ./data:/data \
  expdeploy.sif run /experiments/battery.toml --subject 01
```
