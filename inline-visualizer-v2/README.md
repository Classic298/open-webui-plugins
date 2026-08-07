# 🎨 Inline Visualizer — Streaming Edition

<img width="6400" height="1600" alt="banner-inline-visualizer-v2" src="https://github.com/user-attachments/assets/a96bc28d-ee9c-403a-a5a4-0429b6c154ce" />

**Turn any Open WebUI chat into a live canvas.** Ask for a dashboard, diagram, chart, interactive quiz, architecture map, periodic table, flowchart, data explorer, OUR SOLAR SYSTEM — anything you'd draw in a browser — and watch the model paint it straight into the conversation as it types. Clickable nodes that send follow-up prompts. Copy-buttons that do the right thing. Sliders, toggles, and tabs that remember their state across reloads. Light/dark theme out of the box. A full 9-ramp design system so every visual looks like it belongs.

Interactive. Stateful. Themed. Localized into 48 languages. Renders as the stream arrives — no waiting, no static pop-in.

> [!TIP]
> **🚀 [Jump to Setup](#setup)** — up and running in about a minute.

<video src="https://github.com/user-attachments/assets/8bb8bd13-7b23-43c5-9dd4-e2b1b2cb304a"></video>

---

## ⚡ v2 vs v1 — what's new

If you came from the original inline-visualizer plugin, **everything visible to the model stays basically the same**. Under the hood, it's been rewritten from scratch. Every row below is an actual behavior delta, not marketing copy.

Legend: 🚫 feature not in that version · ⚡ present, v2 expands it · ✅ present and working

| | **v1 — classic** | **v2 — streaming** |
|---|---|---|
| **Rendering timing** | ✅ Static. Model finishes writing → tool assembles a complete HTML payload → `HTMLResponse` comes back → iframe mounts fully formed. User waits for the whole response before seeing anything. | ✅ **Live.** Tool returns an empty wrapper; the model streams the HTML/SVG inline between markers. Iframe paints token-by-token as the model types — first elements appear within ~50 ms of the opening marker arriving. |
| **Protocol** | ✅ Model calls `render_visualization(title=…, html_code=…)` with the full HTML as a tool argument. Tool returns `HTMLResponse`, Open WebUI mounts it as an iframe via `message.embeds[]`. One-shot, server-side. | ✅ Model calls `visualize(title=…)` with no body, then emits the HTML/SVG in the chat stream between plain-text `@@@VIZ-START … @@@VIZ-END` markers. A parasitic same-origin iframe observer reads the parent chat's live DOM and paints as tokens arrive. |
| **Refresh / reload behavior** | ✅ Saved HTML lives in `message.embeds[]`; reopens render instantly. | ✅ Markers live in the saved message body; observer reconstructs iframe state and fires `finalize()` immediately on mount. No re-streaming needed. |
| **Bridges** | ⚡ `sendPrompt`, `openLink` | ✅ `sendPrompt`, `openLink`, **`copyText`** (auto-toast), **`toast(msg, kind)`** (success/info/warn/error, auto-dismiss), **`saveState(k,v)`** / **`loadState(k,fallback)`** (per-message `localStorage` scope, survives reloads) |
| **Pre-styled bare HTML** | 🚫 N/A — model styles every primitive from scratch. | ✅ Drop a vanilla `<button>`, `<input>` (every common type), `<textarea>`, `<select>`, `<label>`, `<fieldset>`, `<table>`, `<details>` / `<summary>`, `<blockquote>`, `<kbd>`, `<hr>`, `<mark>`, `<dl>` (in `data-layout="grid"` and `inline` modes too) and they come out theme-matched. Adding `class` or `style` opts out — model can still go fully custom. **Smaller payloads, faster generation, consistent look across visualizations.** |
| **Accent palette** | 🚫 N/A | ✅ `data-accent="teal"` (or `coral`, `pink`, `gray`, `blue`, `green`, `amber`, `red`) on any element recolors focus rings, checkboxes, radios, and `var(--accent)` consumers. 9 named values matching the chart ramps. Light/dark handled per-theme. |
| **Accessibility defaults** | 🚫 N/A | ✅ `aria-invalid="true"` paints a red border on inputs/textareas/selects; `:focus-visible` draws a clear accent outline on keyboard focus only (mouse focus stays subtle). |
| **CDN library catalog in skill** | ⚡ Chart.js, D3.js examples | ✅ Chart.js, D3.js, Vega-Lite, **ECharts**, **Plotly**, **vis-network** (standalone bundle), **Tone.js / Wavesurfer** — each with a vetted CDN URL and "when to reach for it" guidance. Allowlisted in strict CSP out of the box. |
| **Chart-type coverage in skill** | ⚡ Bar / line / doughnut / scatter | ✅ Adds stacked bars/areas, radar, KPI cards with sparklines, progress bars, ranking strips, KPI donuts, custom-shape charts (thermometers, batteries, fuel gauges), plus comparison cards, slider-driven explainers, tabs (with hidden-panel init guidance), step-through walkthroughs. |
| **Stream-completion feedback** | 🚫 N/A — no stream. | ✅ Localized "Visualization ready" toast in the top-right + an optional soft chime. Fires only when a real stream was seen — reopening a finished chat stays quiet. The chime is off-switchable via the `chime` valve (off → chime code isn't shipped at all). |
| **i18n surface** | ⚡ 1 string × 47 languages = 47 translations (download tooltip) | ✅ 8 strings × 48 languages = **384 translations** — download tooltip, loader label, "unavailable" notice (title + body), "Copied" toast, "Visualization ready" toast, "Export failed" toast, "Visualization script error" toast. Auto-detected from `<html data-iv-lang>`, `localStorage.locale`, and `navigator.language`. |
| **Mid-stream reconciler** | 🚫 N/A — the iframe is built once from a complete payload. | ✅ Custom safe-cut HTML parser flushes the longest valid prefix on each chunk. Incremental DOM reconciler only appends new nodes and **leaves script-populated containers alone** so `d3.select(...).append('svg')`, `new vis.Network(...)`, ECharts canvases, etc. survive the final paint pass. **Existing nodes never re-mount, animations never re-trigger, zero flicker.** |
| **Per-tick efficiency** | 🚫 N/A | ✅ `msg.textContent` cached between ticks; unchanged → full pipeline (regex extract, DOM walk, reconciler) short-circuits to a string compare. Only one tick per real DOM mutation does real work. |
| **Dynamic script injection** | 🚫 N/A — scripts come baked into the static srcdoc and are parsed by the browser normally. | ✅ External `<script src>` + inline scripts injected at finalize() are **serialized via a Promise chain**. Each link wrapped + `.catch`'d so a single bad script can't stall the rest. `Chart`, `d3`, `vega-embed` etc. are guaranteed defined before consumer code runs. |
| **Script-boundary safety** | 🚫 N/A — the browser parses the srcdoc once, no re-injection. | ✅ Safe-cut parser tracks the tokenizer state across HTML's script-data-escape and double-escape transitions. **Module-load guard** refuses to start the plugin if any embedded script body contains a literal `<!--`, `<script>`, etc. that would silently break the IIFE. |
| **Tool-result-example bleed** | 🚫 N/A — observer doesn't scan chat DOM. | ✅ TreeWalker excludes `<details type="tool_calls" \| reasoning \| code_execution \| code_interpreter>` when scanning, with a lax fallback that recovers responses from providers that wrap the visible answer inside a reasoning block (Bedrock-hosted Haiku 4.5). |
| **Bootstrap resilience** | 🚫 N/A | ✅ Initial tick, inner observer, parent observer, and poll timer each independently guarded — any one failure can't leave the iframe silently dormant. Height reporter collapses `100vh` / `100vw` descendants during measurement to break the feedback loop. |
| **Standalone HTML export** | ⚡ Save HTML → opens fine. | ✅ Imported library scripts are relocated to the end of `<body>` before serialization so charts paint correctly when the file is opened directly (head-loaded scripts otherwise run before their target divs exist). |
| **Plugin footprint** | ✅ `tool.py` + `SKILL.md` | ✅ Same two files, same install flow — **no Open WebUI core patches**. |

### The one-line summary

> **v1 builds the visualization and shows you the finished poster. v2 hands the model a brush and a canvas and lets you watch it paint.**

---

## ✨ Features

### 🎬 Streaming render
The tool returns an empty wrapper. The model then emits HTML/SVG between `@@@VIZ-START` / `@@@VIZ-END` text markers in its response. An observer tails the parent chat's live DOM, extracts the growing block, and reconciles new nodes into the iframe in real time. You see cards, SVGs, and charts appear as the model writes them — not all at once when the message completes.

### 🌍 Built-in localization
Auto-detects the user's language from `<html data-iv-lang>` (injected server-side), then from parent `localStorage.locale`, then `navigator.language`. 48 languages for:
- Download button tooltip
- "Rendering visualization…" loader label
- "Streaming visualization unavailable" notice (title and body, shown if `allow-same-origin` is off)
- "Copied" confirmation toast
- "Visualization ready" done toast
- "Export failed" toast
- "Visualization script error" toast

### 🎨 Design system
- **9 color ramps** — purple, teal, coral, pink, gray, blue, green, amber, red — each with fill / stroke / text variants that auto-swap for light/dark mode
- **SVG utility classes** — `.t` `.ts` `.th` text, `.box` `.node` `.arr` `.leader` shapes, `.c-{ramp}` color application
- **Theme CSS variables** — dozens of aliases (`--bg`, `--fg`, `--surface`, `--border`, …) so the model can hardcode without breaking light/dark parity
- **`data-accent` palette** — set `data-accent="teal"` on any element (root, container, or single tag) to recolor focus rings, checkboxes, radios, and `var(--accent)` consumers. 9 named values matching the chart ramps. Light/dark handled per-theme.
- **Pre-styled bare HTML** — drop a vanilla `<button>`, `<input>` (every common type — `text`, `email`, `number`, `range`, `date`, `checkbox`, `radio`, …), `<textarea>`, `<select>`, `<label>`, `<fieldset>`, `<legend>`, `<table>`, `<details>` / `<summary>`, `<blockquote>`, `<kbd>`, `<hr>`, `<mark>`, `<dl>` (in `data-layout="grid"` and `data-layout="inline"` modes too) and they come out themed. Add `class` or `style` to opt out. Saves tokens on simple UIs without locking the design space.
- **Accessibility defaults** — `aria-invalid="true"` paints a red border on inputs/textareas/selects; `:focus-visible` draws a clear accent outline on keyboard focus only.

### 🌉 Bridges — visualizations that talk back

| Bridge | What it does |
|---|---|
| `sendPrompt(text)` | Submits `text` as a user message in the chat. Makes any node a drill-down trigger. |
| `openLink(url)` | Opens `url` in a new tab (bypasses iframe sandbox weirdness on anchor clicks). |
| `copyText(text)` | Copies to clipboard (async API + legacy fallback) and fires a localized "Copied" toast. |
| `toast(msg, kind)` | Top-right auto-dismissing banner. `kind`: `success` / `info` / `warn` / `error`. |
| `saveState(key, value)` | Persists to `parent.localStorage` keyed by the assistant message id. |
| `loadState(key, fallback)` | Reads what `saveState` wrote. Survives reloads, scoped per-message. |

### 🔒 Configurable CSP

| Level | Outbound fetch | External images | Script CDNs | Use case |
|---|:-:|:-:|:-:|---|
| **Offline** | ❌ | ❌ | ❌ self-hosted only | Air-gapped / zero external connections. [Self-hosting tutorial ↓](#-offline-mode--self-hosting-the-cdn-libraries) |
| **Strict** (default) | ❌ | ❌ | ✅ 3 allowlisted | Maximum sandboxing, CDN charts still work. |
| **Balanced** | ❌ | ✅ | ✅ 3 allowlisted | Flags, logos, external image references. |
| **None** | ✅ | ✅ | ✅ any | Live API data pulls from inside the iframe. |

### 🎉 Done toast + chime
When a live stream finalizes, a localized "Visualization ready" toast slides in top-right and a soft three-note C-major arpeggio plays on Web Audio sine oscillators. Refreshes of completed messages are silent — the observer only celebrates when it actually witnessed the stream. Mute via `saveState('iv-sound', false)` per viz, or `localStorage['iv-sound-off']='1'` globally.

### 🧼 Efficient tick loop
- `msg.textContent` cached between ticks; unchanged → full pipeline short-circuits to a string compare
- DOM hide walker skips text nodes inside `<details type="tool_calls">` so the skill's own example markers never hijack detection
- Dynamic `<script>` insertion serialized through a promise chain — external `<script src>` tags are awaited via `onload` before any subsequent inline `<script>` executes, so `Chart` / `d3` / `vega-embed` / etc. are always defined by the time your consumer code runs
- `navigator.vibrate` is silently stubbed inside the iframe — models sometimes reach for haptic feedback on click, and Chrome logs an `[Intervention]` line every time without a user gesture; the stub keeps the console clean
- Safe-cut HTML parser lets the reconciler flush partial markup (`<svg><rect/><g>` renders during stream) without breaking on unclosed tags

---

## 📦 Components

Two parts. Same as v1. Install both.

| File | Type | Install location |
|------|------|-----------------|
| `tool.py` | Tool | Workspace → Tools |
| `SKILL.md` | Skill | Workspace → Knowledge → Create Skill (name it **`visualize`**) |

The **tool** mounts the iframe wrapper, injects the design-system CSS/JS, and tails the chat for markers. The **skill** teaches the model the protocol (markers, color ramps, SVG patterns, when to use `sendPrompt` vs local JS, CDN libraries, common failures).

---

## Setup

> [!NOTE]
> **Prerequisite.** Works best with fast + strong models that follow protocol instructions precisely. Verified on Claude Sonnet 4.5, Claude Opus 4.7, GPT-5.4, Gemini 3.1 Pro, Qwen 3.5 27B.

### 1. Install the tool

1. Copy the contents of `tool.py`
2. In Open WebUI: **Workspace → Tools → + Create New**
3. Paste. **Save**.

### 2. Install the skill

1. Copy the contents of `SKILL.md`
2. In Open WebUI: **Workspace → Knowledge → Create Skill**
3. Name it **`Visualize`** (the tool calls `view_skill("visualize")` by this name)
4. Paste. **Save**.

> [!TIP]
> Or drag `SKILL.md` straight into the import field on **Workspace → Skills** — Open WebUI reads the YAML frontmatter (`name: visualize`, `description: …`) and pre-fills the create form for you. Just click **Save**.

### 3. Attach to your model

1. **Admin Panel → Settings → Models** → edit the model you want
2. Under **Tools**, enable **Visualizer**
3. Under **Skills**, attach **Visualizer**
4. Check **Function Calling** is **not** set to `Legacy` (Advanced Params). `Default` and `Native` both work, and `Default` has been native since Open WebUI `0.10.0`
5. Save.

### 4. Enable same-origin access — **required**

> [!IMPORTANT]
> Streaming mode **does not work without this setting.** The observer's entire job is reading the parent chat's DOM to find markers as they stream in — that requires cross-frame access, which the browser blocks unless the iframe is allowed same-origin. With the setting off, every visualization renders a localized "Streaming visualization unavailable" notice instead of content.

Steps:

1. **User Settings → Interface**
2. Scroll down
3. Enable **Allow iframe same origin**

> [!NOTE]
> Enabling same-origin means JavaScript inside a visualization can reach the parent Open WebUI page. That is a platform-level permission the tool cannot narrow — it's the cost of this streaming architecture. If your threat model can't accept that, use the original v1 inline-visualizer instead (static mode doesn't need same-origin).

---

## 🎯 Usage

Ask for a visualization. The model calls `view_skill("visualize")` to load the design system, calls `visualize(title=…)` to mount the wrapper, then streams the HTML/SVG between `@@@VIZ-START` / `@@@VIZ-END` markers.

### Example prompts

- *"Visualize the architecture of a microservices system with clickable nodes."*
- *"Show me a flowchart of Git branching — let me click each stage for a drill-down."*
- *"Build an interactive study card for transformer LLMs: architecture diagram, parameter-count chart, temperature slider, SDK snippet."*
- *"Make me a periodic table where clicking an element asks you to explain it."*

### The protocol in one example

```
I'll chart the attention mechanism for you.

@@@VIZ-START
<svg viewBox="0 0 680 240">
  <!-- content streams in live -->
</svg>
@@@VIZ-END

As you can see, each query token attends to all key tokens simultaneously.
```

Everything between the markers is hidden from the chat body and piped into the iframe. Prose before and after renders normally.

---

## 🌉 Bridges — deep dive

### `sendPrompt(text)`
Turns any node into a conversational drill-down. The iframe `postMessage`s the parent with Open WebUI's native prompt-submit protocol.

```html
<g class="node c-purple" onclick="sendPrompt('Explain attention — how does softmax(QKᵀ/√d)V work and why scale by √d?')">
  <rect x="100" y="20" width="200" height="44" rx="8"/>
  <text class="th" x="200" y="42" text-anchor="middle" dominant-baseline="central">Attention</text>
</g>
```

### `openLink(url)`
Opens URLs in a new tab — safer than anchor tags inside sandboxed iframes.

```html
<button onclick="openLink('https://arxiv.org/abs/1706.03762')">View paper ↗</button>
```

### `copyText(text)` — fires a localized toast automatically

```html
<button onclick="copyText(document.getElementById('snippet').textContent)">Copy</button>
<pre id="snippet">from anthropic import Anthropic
client = Anthropic()
…</pre>
```

### `toast(msg, kind)` — standalone status banners

```html
<button onclick="recompute(); toast('Recomputed', 'info')">Recompute</button>
```

`kind` ∈ `success` (default) / `info` / `warn` / `error`.

### `saveState` / `loadState` — per-message persistence

```html
<script>
  const initial = loadState('showAdvanced', false);
  document.getElementById('adv').checked = initial;
  applyView(initial);

  function toggle(el) {
    saveState('showAdvanced', el.checked);
    applyView(el.checked);
  }
</script>
```

Keys are prefixed with the assistant message id, so a chart in Chat A and a chart in Chat B never share state. A slider value survives page reloads — the user's last setting is there when they come back.

---

## 🎨 Design system — at a glance

### Color ramps
```
purple · teal · coral · pink · gray · blue · green · amber · red
```
Apply via CSS class on any `<g>` — child `<rect>`, `<circle>`, `<ellipse>` get the ramp's fill + stroke automatically, un-classed, un-filled child `<path>` / `<polygon>` (pie wedges, areas) get the ramp's saturated stroke color (an explicit `fill` attribute always wins), and child `.th` / `.ts` get the ramp's text colors. `currentColor` anywhere inside the group resolves to the ramp color, so classed marks can opt back in with `fill="currentColor"`. Light/dark adaptation is automatic.

```html
<g class="node c-teal">
  <rect x="100" y="20" width="180" height="44" rx="8"/>
  <text class="th" x="190" y="42" text-anchor="middle" dominant-baseline="central">Compute</text>
</g>
```

### SVG utility classes

| Class | Purpose |
|---|---|
| `.t` `.ts` `.th` | 14 px primary text / 12 px secondary / 14 px bold |
| `.box` | Neutral rect (secondary bg, tertiary border) |
| `.node` | Clickable element (cursor, hover opacity) |
| `.arr` | Arrow line (1.5 px, border-secondary) |
| `.leader` | Dashed guide line (0.5 px, tertiary) |
| `.c-{ramp}` | Apply a color ramp to all descendants |

### Themed HTML elements

A wide set of bare tags ship with theme-aware default styling. The model
writes `<button>`, `<select>`, `<table>`, `<details>` etc. and gets
polished output — no class or inline style needed.

| Group | Tags |
|---|---|
| **Forms** | `<button>` · `<input>` (`text`, `email`, `number`, `search`, `password`, `tel`, `url`, `date`, `time`, `datetime-local`, `range`, `checkbox`, `radio`) · `<textarea>` · `<select>` · `<label>` · `<fieldset>` · `<legend>` |
| **Tables** | `<table>` · `<thead>` · `<tbody>` · `<th>` · `<td>` · `<caption>` (numeric cells: `align="right"` or `class="num"` → tabular-nums) |
| **Disclosure** | `<details>` / `<summary>` (rotating chevron) |
| **Inline** | `<kbd>` · `<mark>` · `<code>` · `<blockquote>` · `<hr>` |
| **Definition lists** | `<dl>` in three layouts — bare (stacked glossary), `data-layout="grid"` (two-column card), `data-layout="inline"` (pill row) |

Adding a `class` or `style` attribute to any of these opts out of the
default styling — the model can still go fully custom when the design
calls for it.

---

## 🌍 Localization

The tool bakes `<html data-iv-lang="{detected}">` on the server (reads parent `localStorage.locale` via `__event_call__`). Client-side fallbacks chain through `parent.localStorage` and `navigator.language`. 48 languages covered: en, de, cs, hu, hr, pl, fr, nl, es, pt, it, ca, gl, eu, da, sv, no, fi, is, sk, sl, sr, bs, bg, mk, uk, ru, be, lt, lv, et, ro, el, sq, tr, az, ar, he, zh, ja, ko, vi, th, id, ms, hi, bn, sw.

Eight strings translated per language. That's **384 translations shipping** in the tool.

---

## 🔒 Security

Every visualization renders in a sandboxed iframe with a configurable Content Security Policy. Open **Workspace → Tools → Inline Visualizer → gear icon** to change the valve.

| Level | Outbound requests | External images | URL param stripping | Use case |
|-------|:-:|:-:|:-:|---|
| **Offline** *(new in 2.2.0)* | ❌ | ❌ | ✅ | **Nothing leaves your instance** — even the three script CDNs are blocked. Libraries can be self-hosted on your instance ([tutorial ↓](#-offline-mode--self-hosting-the-cdn-libraries)). |
| **Strict** (default) | ❌ | ❌ | ✅ | Max safety with CDN charts. All core features work normally. |
| **Balanced** | ❌ | ✅ | — | Visualizations displaying external images (flags, logos). |
| **None** | ✅ | ✅ | — | Visualizations fetching live API data from within the iframe. |

### What works in Strict mode

Chart.js, D3.js, Vega-Lite, and any other pure-client-side library load and render normally — the three major CDN hosts (cdnjs, jsdelivr, unpkg) are on the `script-src` allowlist, and `'unsafe-eval'` is granted so runtime expression compilers (Vega's `new Function(...)`, some templating libs) work. Visualizations with **inline data** (data arrays hardcoded in the SVG/HTML source) work without limits. The SKILL tells the model to inline data by default, so this covers 99% of prompts.

**What Strict blocks:** runtime `fetch()` calls, `d3.csv('https://…')`, Vega-Lite specs with `data: { url: '…' }`, external images, form submits. If you want a live-updating weather widget or a chart that pulls a CSV at render time, switch to **None**.

**What Offline additionally blocks:** the three CDN hosts themselves. In Offline mode the iframe cannot make a single request that leaves your Open WebUI server — `script-src` drops the CDN allowlist and permits `'self'` instead, so the only scripts that load are inline ones and files served by your own instance. Pure inline SVG/HTML visualizations (the skill's default) work unchanged; library charts (Chart.js, D3, …) keep working too **if you self-host the files** — see [Offline mode](#-offline-mode--self-hosting-the-cdn-libraries) below.

> [!NOTE]
> Strict allows `'unsafe-inline'` and `'unsafe-eval'` for scripts because LLM-generated visualizations ship their own inline code and some libraries compile expressions at runtime. Those relaxations don't create exfil channels — the real outbound blockers (`connect-src 'none'`, `form-action 'none'`, `img-src` restricted, `object-src 'none'`) stay in place regardless. If you need a truly locked-down iframe, disable JavaScript entirely at the Open WebUI level; the tool can't render anything useful without `'unsafe-inline'` scripts.

### Why `script-src` allows a CDN but `connect-src` doesn't

Loading a library from a CDN is a plain `GET` of a fixed public URL — zero data leaves the browser. Allowing `fetch()` to the same CDN opens an exfiltration channel: the URL itself becomes the payload (`fetch('https://cdn.example/?data=' + userContent)` gets logged server-side even if it returns 404). Different directions, different risks — Strict grants "read known public asset", denies "write arbitrary data anywhere". This is intentional, not an oversight.

### Sourcemap warnings in DevTools

When DevTools is open, the browser attempts to fetch `.map` files for loaded libraries from the same CDN. Strict blocks those via `connect-src 'none'` — you'll see lines like `Connecting to 'https://cdn.jsdelivr.net/npm/vega.min.js.map' violates CSP…` in the console. Those are DevTools-only noise (end users with DevTools closed never see them). We intentionally don't relax `connect-src` to fix this because that would reopen the exfil surface above for all users.

> [!WARNING]
> With `allow-same-origin` enabled (required for streaming), JavaScript in a visualization has reach into the parent Open WebUI page. That is a platform-level permission — the tool cannot narrow it further. The tool's only network traffic of its own is one same-origin GET to your own instance's chats API (retried until the chat is saved): when an inline script in a rendered block fails to parse, it re-reads the raw message text via the parent frame — works at every security level and sends nothing anywhere else. If you need full isolation, disable same-origin: v2 degrades gracefully with a localized "streaming unavailable" notice, and you can fall back to the original inline-visualizer (static mode only) for that workflow.

> [!NOTE]
> Even in **None** mode, external API calls may still fail due to CORS — that's the remote server's policy, not ours.

---

## 🔌 Offline mode — self-hosting the CDN libraries

*(new in v2.2.0)* The **Offline** security level guarantees **nothing leaves your Open WebUI host**: no CDNs, no external images, fonts, or media. The only request the tool itself ever makes is the same-origin chats-API read described under [Security](#-security). It exists for air-gapped networks and privacy-hardened deployments.

Two ways to use it:

### Option A — no libraries at all (zero setup)

Just set the valve: **Workspace → Tools → Inline Visualizer → gear icon → `security_level` → `offline`**. Done.

Everything the design system ships — inline SVG diagrams, themed HTML components, interactive explainers, sparklines, KPI cards, `sendPrompt` drill-downs — is baked into the iframe itself and needs no network. Only *library* charts (Chart.js, D3, ECharts, Plotly, Vega-Lite, vis-network, Tone.js) normally come from a CDN. If you can live without those, you're finished. Optionally delete the **CDN libraries** section from `SKILL.md` before importing it, so the model doesn't try to load them in the first place.

### Option B — keep the libraries, serve them yourself

Open WebUI already serves a static folder at `https://<your-instance>/static/` — and in Offline mode the CSP allows `'self'`, so anything you drop in there loads fine inside visualizations. Small tutorial:

**1. Set the valve to `offline`** (see Option A).

**2. Download the libraries you want** (these are the exact pinned builds from `SKILL.md`):

```bash
mkdir iv-libs && cd iv-libs
curl -LO https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js
curl -LO https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js
curl -LO https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.0/echarts.min.js
curl -Lo plotly.min.js https://cdn.jsdelivr.net/npm/plotly.js-dist@2
curl -Lo vega.min.js https://cdn.jsdelivr.net/npm/vega@5
curl -Lo vega-lite.min.js https://cdn.jsdelivr.net/npm/vega-lite@5
curl -Lo vega-embed.min.js https://cdn.jsdelivr.net/npm/vega-embed@6
curl -Lo vis-network.min.js https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js
curl -Lo Tone.js https://cdnjs.cloudflare.com/ajax/libs/tone/15.0.4/Tone.js
```

(Only grab what you actually use — Chart.js alone covers most chart prompts.)

**3. Put the folder inside Open WebUI's static directory.**

*Docker (recommended — survives image updates):* bind-mount the folder into the static dir when starting the container:

```bash
docker run -d ... -v /path/on/host/iv-libs:/app/backend/open_webui/static/iv-libs ...
```

*Docker (quick test — lost on image update):*

```bash
docker exec open-webui mkdir -p /app/backend/open_webui/static/iv-libs
docker cp iv-libs/. open-webui:/app/backend/open_webui/static/iv-libs/
```

*Bare-metal / pip:* the served folder is the `static/` directory of the installed `open_webui` package (or wherever the `STATIC_DIR` environment variable points, if you set one). Create `iv-libs/` inside it and copy the files there.

**4. Verify.** Open `https://<your-instance>/static/iv-libs/chart.umd.min.js` in your browser — you should see minified JavaScript. If you get a 404, the files aren't in the folder Open WebUI is actually serving.

**5. Teach the model the local paths.** The model writes the `<script src=…>` tags, so `SKILL.md` must point it at your copies instead of the CDNs. Before importing the skill, search-replace the loader URLs in the **CDN libraries** section (and the Chart.js setup example), e.g.:

```html
<!-- before -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<!-- after -->
<script src="/static/iv-libs/chart.umd.min.js"></script>
```

Keeping the filenames identical makes this a plain search-replace. If you already imported the skill, just edit it in **Workspace → Knowledge/Skills** and save.

**6. Done.** New visualizations now load every byte from your own server. You can confirm in DevTools → Network: the only requests are same-origin.

> [!NOTE]
> **Sub-path deployments:** if Open WebUI is served under a sub-path (e.g. `https://example.com/webui/`), use the full path in the skill: `/webui/static/iv-libs/…`. The iframe inherits the parent page's origin and base URL, so absolute paths resolve against your domain root.

> [!NOTE]
> **Why not just mirror the CDN hostnames?** You can (DNS override + an internally-trusted TLS cert for the CDN hosts works with zero plugin changes), but it's operationally heavy. The `/static` route is two files and one valve.

---

## 🧰 Troubleshooting

<details>
<summary><b>The iframe shows a "Streaming visualization unavailable" notice</b></summary>

`allow-same-origin` is off. Enable it in **Settings → Interface → iframe Sandbox Allow Same Origin**.
</details>

<details>
<summary><b>The iframe is a thin empty strip</b></summary>

Usually means the model emitted an empty `@@@VIZ-START … @@@VIZ-END` block, or stopped mid-stream without closing the block and hit the idle-finalize fallback. Try regenerating. See the next entry for how the idle fallback works.
</details>

<details>
<summary><b>How does the plugin know when to stop streaming?</b></summary>

Two triggers:

1. **`@@@VIZ-END` marker arrives** — fires `finalize()` instantly. Scripts run, loader is replaced with the rendered viz, done toast + chime fire. This is the 99%+ case.
2. **Idle fallback — 30 seconds of completely stable source text.** Catches three edge cases: the user stopped generation mid-viz, the model forgot to close the block, or the network died.

The 30s window is deliberately much longer than any realistic inter-chunk stall. Gemini 3.1 Pro's 200-token chunks with 3-6s gaps, proxy buffering under poor network (10-20s silent pauses), and occasional Claude stalls all comfortably fit inside it. An earlier 5s fallback produced a thin-strip regression in ~40% of long streams; **30s is the sweet spot** between surviving real stalls and still recovering from a user-stop within half a minute.

**If a browser tab's network completely dies for more than 30s**, the fallback will finalize on whatever partial content arrived before the outage. At that point the stream is already gone, so a frozen loader-forever would be worse. Refresh the chat and the saved markdown (which has both markers) finalizes instantly on first tick.
</details>

<details>
<summary><b>A "Visualization script error" toast appears</b></summary>

An inline script in the visualization does not parse. The usual cause is not the model: Open WebUI's citation rendering can silently swallow single-line numeric array literals like `[21, 11, 4]` from the message, corrupting the source the plugin reads from the chat DOM. The plugin detects the broken script before running it and re-reads the raw message text from your instance's chats API, which fixes the corrupted case automatically. The toast only appears when that recovery also dead-ends: the model genuinely wrote invalid JavaScript, the chat is unsaved (temporary chat), or the message kept streaming past the ~90s retry window — in the last case a refresh fixes it, because the saved chat recovers on the first attempt. The exact parse error is in the browser console.
</details>

<details>
<summary><b>Chart.js / D3 renders but nothing appears</b></summary>

Chart.js needs `<div style="position: relative; height: Xpx;">` around its canvas and `maintainAspectRatio: false` in options. See **Library init** in SKILL.md.
</details>

<details>
<summary><b>I switched to Offline and Chart.js / D3 stopped loading</b></summary>

Expected — Offline blocks the CDNs by design. Either self-host the libraries under `/static/iv-libs/` and point `SKILL.md` at them (see [Offline mode](#-offline-mode--self-hosting-the-cdn-libraries)), or stay on **Strict**, which allowlists the three public CDNs while still blocking every data-exfiltration channel.
</details>

<details>
<summary><b>External images don't load</b></summary>

Strict CSP blocks external images. Switch to **Balanced** in the tool's valves.
</details>

<details>
<summary><b>fetch() fails with CORS</b></summary>

Set CSP to **None** AND the remote server must allow cross-origin requests. If it doesn't, there's nothing any client-side config can do.
</details>

<details>
<summary><b>The done chime is annoying</b></summary>

Open **Workspace → Tools → Inline Visualizer (Streaming) → gear icon**, flip the **`chime`** valve to off, save. Chime disabled globally — the function definition is stripped from the iframe entirely (not shipped as a silent no-op), saving ~1 KB per visualization.
</details>

<details>
<summary><b>I updated <code>tool.py</code> and nothing changed</b></summary>

**BEFORE Open WebUI 0.9.5**, Open WebUI didn't hot-reload tool source codes if the tool changed. You have to paste the new contents into **Workspace → Tools → Inline Visualizer (Streaming) → Save** again and then restart your Open WebUI.

Additionally, existing chats keep their old iframe baked into `message.embeds[]` — only newly-triggered tool calls pick up the update.

On **multi-worker deployments** (`UVICORN_WORKERS > 1`), each worker process has its own in-memory tool module cache. A save updates the worker that handled the save request; every other worker keeps its old compiled module until the backend restarts. If you're on a multi-worker setup and you see stale behavior even from fresh chats, restart the backend.

**Open WebUI 0.9.5 and newer is no longer affected by this. Changing the tool's source code will update it across all workers instantly now**
</details>

---

## 📐 Architecture

```
┌──────────────────── Assistant message ────────────────────┐
│                                                            │
│  <p>Here's the architecture:</p>                           │
│                                                            │
│  <p>@@@VIZ-START</p>       ← hidden by observer            │
│  <p>&lt;svg…&gt;…&lt;/svg&gt;</p>  ← hidden, piped to iframe    │
│  <p>@@@VIZ-END</p>         ← hidden by observer            │
│                                                            │
│  ┌──────────────── tool embed iframe ─────────────────┐    │
│  │ #iv-render      ← live SVG reconciles here         │    │
│  │ #iv-loader      ← dots + "Rendering visualization…"│    │
│  │ #iv-dl-wrap     ← download button                  │    │
│  │ #iv-toast-wrap  ← top-right toast stack            │    │
│  └────────────────────────────────────────────────────┘    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

The observer inside the iframe uses `parent.document` (via `allow-same-origin`) to `getSearchableText(msg)` — a TreeWalker that excludes `<details type="tool_calls">` — runs a regex for the N-th `@@@VIZ-START…@@@VIZ-END` block (N = iframe's embed index), safe-cuts the partial HTML, parses into a detached tree, and reconciles into `#iv-render`. On `@@@VIZ-END` it finalizes: injects scripts via a promise chain (external waits on `onload` before the next inline script executes), fires the done toast + chime, hides the loader.

### Finalize triggers

| Trigger | Delay | When it fires |
|---|---|---|
| `@@@VIZ-END` in source | instant | Model closed the block cleanly (the 99%+ case) |
| 30s of source stability | 30s | User stopped generation, model forgot END, or network died |
| Raw-source recovery | up to ~90s | An inline script failed to parse (chat renderer corrupted the DOM source); finalize waits on the raw message text from the chats API, instant on saved chats |

The idle fallback is deliberately much longer than any realistic inter-chunk stall — Gemini 3.1 Pro's 200-token chunks with 3-6s gaps, proxy buffering under poor network (10-20s silent pauses), and occasional stalls on other models all fit comfortably inside. If a stream genuinely dies for 30s+, the visualization is already gone — finalizing on the partial content beats a loader frozen forever, and refreshing the chat re-finalizes instantly from the saved markdown (which has both markers).

---

## 🙏 Credits

Built on top of [**Open WebUI**](https://github.com/open-webui/open-webui) and its tool / skill system.

---

<div align="center">
<sub>Built for the humans who want their models to <em>show</em>, not just tell.</sub>
</div>
