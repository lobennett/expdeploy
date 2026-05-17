# Storage adapters

Each completed run writes to up to three places:

1. **FSAdapter (always on)** — raw JSON + BIDS layout (if `[bids]` is set)
2. **SQLiteCatalog (always on)** — local index of runs at `data/catalog.sqlite`
3. **Remote adapters (optional)** — currently `supabase`; future: firebase, mongo, s3

## Filesystem layout

```
data/
├── catalog.sqlite
├── raw/
│   └── sub-01/
│       └── ses-01/
│           └── sub-01_ses-01_task-flanker_run-01_beh.json
└── bids/                              # only if [bids] in manifest
    ├── dataset_description.json
    ├── participants.tsv
    └── sub-01/
        └── ses-01/
            ├── func/                  # fMRI
            │   ├── ..._events.tsv
            │   └── ..._events.json    # sidecar
            └── beh/                   # behavioral
```

## Supabase adapter

Install the extra:

```bash
uv tool install 'expdeploy[supabase]'
```

Configure via env vars:

```
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=eyJ...   # never the anon key
export SUPABASE_SCHEMA=expdeploy           # optional
export SUPABASE_BUCKET=expdeploy-raw       # optional
```

Apply the schema:

```bash
expdeploy supabase migrate
```

If the project doesn't have the `exec_sql` RPC, run the SQL at `src/expdeploy/storage/supabase_schema.sql` via the Supabase SQL editor manually.

Mirror runs to Supabase:

```bash
expdeploy run ./examples/hello_world --subject 01 --remote supabase
```

Replay any failed remote writes:

```bash
expdeploy sync --adapter supabase
```

## Security note

The Supabase service role key bypasses RLS — guard it like a database password. Don't commit it; use environment variables or a secret manager. Participants don't authenticate against Supabase; the deploy server is the trusted writer.
