# 🧹 Prune

Automatic, **throttled** database and storage cleanup for your entire instance, driven by one Event function. Old chats, inactive users, orphaned records, orphaned uploads and orphaned vector collections are cleaned up in the background, slowly on purpose, so a live instance never notices. A built-in admin page (default `/prune`) lets you preview and run cleanups manually.

> [!IMPORTANT]
> **Requires Open WebUI `0.10.2` or newer.** This is an `Event` function and depends on the native events system (`system.startup.completed`, `chat.created`, `user.deleted`, …). It will not load on older versions.

> [!TIP]
> **🚀 [Jump to Setup](#setup)** — paste, enable, configure Valves. Deletion stays off until you flip the master switch, and the **Preview** button in the manual UI shows you exactly what any configuration would delete before you commit to anything.

## ✨ Features

- **Fully automatic, event-driven pruning** — no cron box, no external scripts. The instance cleans itself in reaction to its own activity (see the event table below).
- **Everything configurable from Valves** — numeric settings use `0 = disabled`; enable exactly the retention rules you want. The valve panel is organized into titled sections (general, age rules, inactive users, orphaned data, channels, retention).
- **Purposefully slow deletion** — a `deletion_rows_per_second` throttle (default 50) trickles deletions out instead of hammering the database: 20,000 old chats delete over minutes with the write path free between rows, every batch commits before sleeping, and all vector/filesystem work runs off the event loop. The throttle applies live, even to a pass already running.
- **Fast, resource-bounded scans** — previews and orphan detection scan JSON columns as raw text with a single compiled regex instead of json-decoding every chat (an order of magnitude faster on large databases), and every row scan yields the event loop between batches so the instance stays responsive while a preview runs. An optional `scan_rows_per_second` valve additionally rate-limits the read side; both limits can also be overridden per run from the manual page.
- **Live progress** — preview and execute both run in the background and report a live progress bar in the manual page: the current stage ("Scanning chats for file references", "Sweeping orphaned files", …) plus an item counter with a percentage where the total is known. Automatic passes report the same progress through the status endpoint, so an admin can always see that a pass is working and what it is doing.
- **Multi-worker safe** — every pass is claimed atomically via Redis (`SET NX EX`), so exactly one worker prunes while the rest stay idle. A token-guarded global run lock (heartbeat-renewed for long passes) additionally guarantees no two replicas ever prune concurrently.
- **Shared data of departed users survives** — orphaned knowledge bases, models, prompts, tools, notes and skills are **kept** when a living user, an existing group or a public grant can still access them (each with its own `↳ exempt shared` toggle, all on by default). Offboarding an employee no longer guts the team knowledge base they happened to create; kept ownerless KBs are logged each sweep as inventory.
- **Reference-based file safety** — a file is deleted only when *nothing* references it (no chat, knowledge base, note, folder, channel or model); who uploaded it is irrelevant. Files younger than `orphan_file_grace_hours` (default 24) are never treated as orphaned, so a sweep can't delete an upload the user hasn't attached yet.
- **Manual admin page** — a session-gated page at `/prune` (admins only, anyone else is redirected to `/`) mirroring the valve sections, with a hoverable ⓘ explanation on every option, a **Preview** that shows exactly what would be deleted, and an **Execute** with typed confirmation, a progress bar and a live run log. Both run in the background: the page can be closed and reopened mid-run and picks the run back up. VACUUM lives here as an explicit per-run maintenance checkbox.
- **Complete account cleanup** — inactive-user deletion removes the account *and* its login credentials through the same path as Open WebUI's own admin delete, plus automations and stored memories; the user's files follow the reference-based rule above.

## ✅ How it works

### Events that trigger automatic pruning

Automatic pruning only runs while the **`enable_automatic_deletion`** master switch is on. Four groups of events trigger three kinds of passes:

| Events | Pass | What it does | Gated by |
|--------|------|--------------|----------|
| `system.startup.completed` | **Full sweep** | Everything configured: age rules, all orphan cleanup, storage + vector GC | A 10-minute boot claim (dedupes simultaneous replica boots) **and**, when `full_sweep_interval_hours > 0`, the interval claim — so a restart inside the interval does not re-sweep. `full_sweep_interval_hours = 0` means sweep on **every** startup, and only at startup. |
| `chat.created`, `chat.deleted`, `chat.deleted_all`, `message.created` | **Targeted chats pass** (cheap, no full-database scans) | Age-based chat deletion and age-based channel-message deletion only | `chat_max_age_days` or `channel_message_max_age_days` configured, `event_recheck_minutes > 0`, and the `chats` claim (cooldown = that valve) |
| `auth.login`, `user.created` | **Targeted users pass** | Inactive-user deletion (account + credentials; files are left to the reference-based orphan sweep) | `inactive_user_days` configured, `event_recheck_minutes > 0`, and the `users` claim |
| `user.deleted`, `knowledge.deleted`, `file.deleted_all` | **Full sweep** | Same as startup — these events mean orphans were just created, so a full reconciliation is warranted | `full_sweep_interval_hours > 0` and the interval claim (at most one full sweep per interval, fleet-wide) |

The intuition: chat activity is the heartbeat for "did any chats age out", logins and signups are the heartbeat for "are there dead accounts", and destruction events (a user, knowledge base or file batch being deleted) signal that orphans now exist. Anything that slips between events converges at the next startup or interval-gated sweep.

Every trigger is guarded the same way: the claim is an atomic Redis `SET NX EX` (in-process fallback without Redis) whose TTL doubles as the cooldown, so exactly one worker fleet-wide wins each trigger; a pass already running on the worker skips **without** burning the claim; and every pass executes under the global run lock, so no two passes — automatic or manual — ever overlap.

Targeted passes never scan the whole database; only full sweeps rebuild the preservation set (active files/KBs/users, shared-grant exemptions) before removing orphans from the database, upload storage (local/S3/GCS/Azure) and the vector database (ChromaDB, PGVector, Milvus, Qdrant, including both multitenancy modes).

The manual page and the automatic passes share the exact same deletion engine — the UI just adds a preview table and a live log on top.

> [!WARNING]
> **Multiple replicas require Redis.** The per-node lock file cannot coordinate across pods (each pod has its own local `CACHE_DIR`, even on S3-storage deployments). With `REDIS_URL` set, claims and the global run lock make pruning exactly-once across the fleet; without it, every replica prunes independently. Single-node deployments (any number of `UVICORN_WORKERS`) are fine without Redis.

> [!NOTE]
> **Valkey works too.** Open WebUI talks to the coordination layer via the Redis protocol, so a Valkey server behind the same `REDIS_URL` (`redis://` scheme) is a drop-in replacement — no configuration difference for this plugin. Redis Sentinel and Cluster configurations are honored. (Valkey as a *vector database*, `VECTOR_DB=valkey`, is unrelated; see Limitations.)

## Components

| File | Type | Install location |
|------|------|-----------------|
| `event.py` | Event | Admin Panel → Functions |

## Setup

1. Copy the contents of `event.py`.
2. In Open WebUI, go to **Admin Panel → Functions → +** (Import/Create).
3. Paste the code and click **Save**.
4. **Enable** the function.
5. Open **`/prune`** in your browser and use **Preview** to rehearse: configure the rules you're considering and see the exact per-category counts of what they would delete. Preview is always safe.
6. Open the function's **Valves**, set the retention rules you settled on (`0` = disabled), and flip **`enable_automatic_deletion`** on. From that moment automatic passes **delete for real** on the events above.

## Usage

- **Automatic** — nothing to do. Passes run on the events in the table, throttled and coordinated. All activity is visible in the server logs (`prune …` lines), including which ownerless shared knowledge bases were kept.
- **Manual** — open `https://your-instance/prune` as an admin. Configure options (every row has a hoverable ⓘ explanation), hit **Preview** for a per-category count, then **Execute** (type `DELETE` to confirm) and watch the progress bar and live run log. Both run in the background with a stage-by-stage progress bar, so neither blocks the browser and a reopened page resumes watching the current run. The **Speed limits** section caps scan and deletion rates for that run only (empty = valve settings). Manual runs and automatic passes share one lock, so they can never overlap.
- **VACUUM** — tick **Run VACUUM afterwards** in the manual page's Maintenance section before an Execute. It runs at the end of that run, under the prune lock. There is deliberately no automatic or valve-triggered VACUUM: a database-locking maintenance operation only ever runs when an admin explicitly asks for it.

> [!WARNING]
> Some options are **destructive by design** and act on live data: `inactive_user_days` deletes the account **and all its private data**; `knowledge_base_max_age_days` is a retention policy that deletes knowledge bases **even when they are shared and actively in use**. Admins and pending users are exempt from inactivity deletion by default — keep it that way unless you know why you're changing it. VACUUM locks the database while it runs; use it in a maintenance window.

## Limitations

- Vector-database cleanup covers **ChromaDB, PGVector, Milvus and Qdrant** (plus Milvus/Qdrant multitenancy). Other vector stores (Elasticsearch, OpenSearch, Pinecone, Weaviate, Valkey, …) are skipped safely — database and storage cleanup still run, only the vector GC no-ops.
- PGVector with `PGVECTOR_PGCRYPTO`: the orphaned-chunk reconciliation inside active KB collections is skipped (the metadata column is encrypted); per-file chunk cleanup is unaffected.
- The dry-run preview reflects the database's current state: when age-based or inactive-user options are enabled, the execute run frees additional orphans mid-run (attachments of the chats it deletes), so it can reclaim more than the preview itemized.
- Changing `route_prefix` requires a server restart.

## Credits

Started as a single-file port of the standalone [prune-open-webui](https://github.com/Classic298/prune-open-webui) CLI tool (now legacy); the plugin is the actively developed successor.
