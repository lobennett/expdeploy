# expdeploy

A modern Python deploy tool for [jsPsych v8](https://www.jspsych.org/) experiments.
Pays homage to [expfactory](https://github.com/expfactory) and expands its scope:
canonical jsPsych ESM authoring, BIDS-compliant data layout, batteries with
counterbalancing, and reproducibility via OCI containers.

**Status:** v0.1-alpha. Under active development; not yet stable.

## Quick start

```bash
uv tool install expdeploy
expdeploy run ./examples/hello_world --subject 01 --port 8080
# opens http://localhost:8080
```

## Documentation

See `docs/superpowers/specs/2026-05-14-expdeploy-design.md` for the v0.1 design spec.

## License

MIT — see [LICENSE](LICENSE).
