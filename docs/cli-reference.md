# CLI reference

!!! note "Auto-generation not available"
    `mkdocs-typer` is installed but did not expand the directive with the current Typer version.
    Run `expdeploy --help` (or `expdeploy <cmd> --help`) to see full command documentation.

## Global options

```
expdeploy [OPTIONS] COMMAND [ARGS]...
```

## Commands

### `run`

Serve a single experiment or battery.

```bash
expdeploy run PATH [OPTIONS]
  --subject TEXT          Subject ID (required)
  --session TEXT          Session number
  --run TEXT              Run number
  --port INTEGER          Port to listen on [default: 8080]
  --data-dir PATH         Data output directory [default: ./data]
  --no-browser            Don't open browser automatically
  --remote TEXT           Remote adapter names to mirror writes to (e.g. supabase)
  --vars TEXT             JSON string of extra variables injected into window.expdeploy.vars
```

### `validate`

Validate a manifest.toml or battery.toml without running.

```bash
expdeploy validate PATH
```

### `status`

List runs recorded in the local catalog.

```bash
expdeploy status [OPTIONS]
  --data-dir PATH         Data directory [default: ./data]
```

### `sync`

Replay failed remote-storage writes against the configured adapter.

```bash
expdeploy sync [OPTIONS]
  --adapter TEXT          Remote adapter name [default: supabase]
  --dry-run               List pending writes without executing
  --data-dir PATH         Data directory [default: ./data]
```

### `build`

Build a study-specific OCI image with experiments baked in.

```bash
expdeploy build TARGET [OPTIONS]
  --tag TEXT              OCI image tag (required)
  --base-tag TEXT         Base image tag to FROM [default: ghcr.io/lobennett/expdeploy:latest]
  --engine TEXT           docker | podman [default: docker]
  --push / --no-push      Push after build [default: no-push]
  --output PATH           Where to write study.Dockerfile
```

### `supabase migrate`

Apply idempotent DDL to the configured Supabase Postgres.

```bash
expdeploy supabase migrate
```

### `supabase test-connection`

Verify the configured Supabase credentials and bucket access.

```bash
expdeploy supabase test-connection
```

### `supabase drop`

DROP the expdeploy schema. Test environments only.

```bash
expdeploy supabase drop --confirm
```
