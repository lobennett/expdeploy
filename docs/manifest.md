# Experiment manifest

Each experiment is a folder containing `manifest.toml`, `index.js` (the ESM entry point), and optionally `style.css`, `assets/`, `lib/`.

## Minimal manifest.toml

```toml
[experiment]
exp_id = "flanker"
name = "Flanker"
version = "1.0.0"
entry = "index.js"

[jspsych]
version = "8.2.3"
plugins = ["@jspsych/plugin-html-keyboard-response@2.1.0"]
```

## BIDS-aware manifest

```toml
[bids]
type = "fmri"        # or "behavioral"
task = "flanker"     # BIDS task label: alphanumeric only

[bids.columns.trial_type]
Description = "Congruency of flanker."
Levels = { congruent = "Congruent", incongruent = "Incongruent" }
```

When the `[bids]` block is present, expdeploy writes a BIDS-compliant `events.tsv` (or `_beh.tsv`) under `data/bids/sub-XX/[ses-Y/]{func,beh}/`, plus a `_events.json` sidecar describing each column.

## `index.js`

```javascript
import { initJsPsych } from 'jspsych';
import htmlKeyboardResponse from '@jspsych/plugin-html-keyboard-response';

export default function build() {
  const startedAt = new Date().toISOString();
  const jsPsych = initJsPsych({
    on_finish: () => {
      window.expdeploy.submit({
        exp_id: window.expdeploy.expId,
        subject_id: window.expdeploy.subjectId,
        started_at: startedAt,
        ended_at: new Date().toISOString(),
        trials: jsPsych.data.get().values(),
        status: "finished",
      });
    },
  });
  jsPsych.run([
    { type: htmlKeyboardResponse, stimulus: "<p>Press any key.</p>" },
  ]);
}
```

## `window.expdeploy` runtime globals

- `expId` / `subjectId` / `sessionNum` / `runNum` / `groupIndex` / `deployVersion` — injected by the server
- `vars` — values passed via `--vars '{"...": ...}'` on the CLI
- `submit(payload)` — POSTs trial data to `/api/data`; returns a Promise that resolves with `{ok, path}` or rejects on error
