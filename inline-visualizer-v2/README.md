# 🎨 Inline Visualizer

<img width="6400" height="1600" alt="banner-inline-visualizer-v2" src="https://github.com/user-attachments/assets/a96bc28d-ee9c-403a-a5a4-0429b6c154ce" />

**Turn any Open WebUI chat into a live canvas.** Ask for a dashboard, diagram, chart, quiz, architecture map, periodic table or a model of the solar system, and watch the model draw it straight into the conversation while the answer streams. Nodes you can click to ask follow-up questions, sliders and tabs that remember their state, light/dark theme out of the box, localized into 48 languages.

> [!TIP]
> **🚀 [Jump to Setup](#setup)**, up and running in about a minute.

<video src="https://github.com/user-attachments/assets/8bb8bd13-7b23-43c5-9dd4-e2b1b2cb304a"></video>

---

## ✨ Features

| Feature | What you get |
|---|---|
| 🎬 **Live rendering** | The visualization paints piece by piece while the model writes it. Nothing re-mounts or flickers along the way. |
| 🌉 **Interactive bridges** | Clicks can send a follow-up prompt, open a link, copy text, show a toast or save state that survives reloads. |
| 🎨 **Design system** | 9 color ramps, SVG utility classes and theme variables. Everything matches light and dark mode automatically. |
| 🧩 **Pre-styled HTML** | Plain `<button>`, `<input>`, `<select>`, `<table>`, `<details>` and friends come out themed with no styling needed. Add `class` or `style` to go custom. |
| 📊 **Chart libraries** | Chart.js, D3, Vega-Lite, ECharts, Plotly, vis-network and Tone.js, each with a pinned CDN URL and guidance in the skill. |
| 🔒 **Configurable security** | Four CSP levels from fully offline to unrestricted. The default blocks every outbound data channel. |
| 🔌 **Offline mode** | Zero external connections. Libraries can be self-hosted on your own instance. |
| 🌍 **48 languages** | All user-facing text (loader, toasts, notices, tooltips) follows the user's language. |
| 🎉 **Done toast + chime** | A "Visualization ready" toast and an optional soft chime when a live stream finishes. Reopening old chats stays quiet. |
| 💾 **Standalone export** | Download any visualization as an HTML file that works on its own. |
| ♿ **Accessibility defaults** | Clear keyboard focus outlines and red borders on invalid inputs. |
| 🧱 **No core changes** | Two files, a tool and a skill. Nothing to patch in Open WebUI. |

---

## 📦 Components

| File | Type | Install location |
|------|------|-----------------|
| `tool.py` | Tool | Workspace → Tools |
| `SKILL.md` | Skill | Workspace → Knowledge → Create Skill (name it **`visualize`**) |

The **tool** mounts the visualization frame and renders what the model writes. The **skill** teaches the model how to write it: the protocol, colors, patterns and libraries.

---

## Setup

> [!NOTE]
> Works best with fast, strong models that follow instructions precisely. Verified on Claude Sonnet 4.5, Claude Opus 4.7, GPT-5.4, Gemini 3.1 Pro and Qwen 3.5 27B.

### 1. Install the tool

1. Copy the contents of `tool.py`
2. In Open WebUI: **Workspace → Tools → + Create New**
3. Paste and **Save**

### 2. Install the skill

1. Copy the contents of `SKILL.md`
2. In Open WebUI: **Workspace → Knowledge → Create Skill**
3. Name it **`visualize`** (the tool loads the skill by this name)
4. Paste and **Save**

> [!TIP]
> You can also drag `SKILL.md` into the import field on **Workspace → Skills**. The name and description are filled in for you, just click **Save**.

### 3. Attach to your model

1. **Admin Panel → Settings → Models** → edit the model you want
2. Under **Tools**, enable **Inline Visualizer**
3. Under **Skills**, attach **visualize**
4. Check **Function Calling** is **not** set to `Legacy` (Advanced Params). `Default` and `Native` both work, and `Default` has been native since Open WebUI `0.10.0`
5. Save

### 4. Enable same-origin access (required)

1. **User Settings → Interface**
2. Enable **iframe Sandbox Allow Same Origin**

> [!IMPORTANT]
> Live rendering needs this. The visualization reads the chat as it streams, which the browser only allows with same-origin access. Without it, every visualization shows a "Streaming visualization unavailable" notice.

> [!NOTE]
> With same-origin enabled, JavaScript inside a visualization can reach the Open WebUI page. This is an Open WebUI permission the tool cannot narrow.

---

## 🎯 Usage

Just ask for a visualization. Some ideas:

- *"Visualize the architecture of a microservices system with clickable nodes."*
- *"Show me a flowchart of Git branching, let me click each stage for details."*
- *"Build an interactive study card for transformer LLMs: architecture diagram, parameter-count chart, temperature slider."*
- *"Make me a periodic table where clicking an element asks you to explain it."*

Under the hood the model calls `visualize(title=…)` and then writes the HTML/SVG between two markers in its answer:

```
I'll chart the attention mechanism for you.

@@@VIZ-START
<svg viewBox="0 0 680 240">
  <!-- content streams in live -->
</svg>
@@@VIZ-END

As you can see, each query token attends to all key tokens simultaneously.
```

Everything between the markers is hidden from the chat and drawn in the visualization. Text before and after shows normally.

---

## 🌉 Bridges

Functions available to scripts inside a visualization:

| Bridge | What it does |
|---|---|
| `sendPrompt(text)` | Sends `text` as a user message. Turns any element into a follow-up question. |
| `openLink(url)` | Opens `url` in a new tab. |
| `copyText(text)` | Copies to the clipboard and shows a "Copied" toast. |
| `toast(msg, kind)` | Shows a short banner. `kind`: `success` (default), `info`, `warn`, `error`. |
| `saveState(key, value)` | Saves a value for this message. Survives page reloads. |
| `loadState(key, fallback)` | Reads what `saveState` wrote. |

```html
<g class="node c-purple" onclick="sendPrompt('Explain how attention works')">
  <rect x="100" y="20" width="200" height="44" rx="8"/>
  <text class="th" x="200" y="42" text-anchor="middle" dominant-baseline="central">Attention</text>
</g>
```

State is stored per message, so charts in different chats never share values.

---

## 🎨 Design system

**Color ramps:** `purple` · `teal` · `coral` · `pink` · `gray` · `blue` · `green` · `amber` · `red`. Put `class="c-teal"` on an SVG `<g>` and its shapes and text pick up matching colors for light and dark mode. Put `data-accent="teal"` on any HTML element to recolor focus rings, checkboxes and radios.

| SVG class | Purpose |
|---|---|
| `.t` `.ts` `.th` | Primary text, secondary text, heading text |
| `.box` | Neutral box |
| `.node` | Clickable element with hover effect |
| `.arr` | Arrow line |
| `.leader` | Dashed guide line |
| `.c-{ramp}` | Apply a color ramp |

| Themed HTML | Tags |
|---|---|
| **Forms** | `<button>`, `<input>` (all common types), `<textarea>`, `<select>`, `<label>`, `<fieldset>`, `<legend>` |
| **Tables** | `<table>` and its parts. `align="right"` or `class="num"` aligns numbers. |
| **Disclosure** | `<details>` / `<summary>` |
| **Inline** | `<kbd>`, `<mark>`, `<code>`, `<blockquote>`, `<hr>` |
| **Definition lists** | `<dl>`, plain or with `data-layout="grid"` / `data-layout="inline"` |

---

## 🔒 Security

Every visualization runs in a sandboxed frame with a Content Security Policy. Change the level in **Workspace → Tools → Inline Visualizer → gear icon → `security_level`**.

| Level | Outbound requests | External images | CDN libraries | Use case |
|-------|:-:|:-:|:-:|---|
| **Offline** | ❌ | ❌ | ❌ (self-hosted only) | Nothing leaves your instance. See [Offline mode](#-offline-mode). |
| **Strict** (default) | ❌ | ❌ | ✅ | Maximum safety, library charts still work. |
| **Balanced** | ❌ | ✅ | ✅ | Visualizations that show external images (flags, logos). |
| **None** | ✅ | ✅ | ✅ | Visualizations that fetch live data from APIs. |

**Strict** covers almost every prompt: the skill tells the model to put data directly into the visualization, and the three big CDNs (cdnjs, jsdelivr, unpkg) are allowed for loading libraries. It blocks `fetch()`, remote data files, external images and form submits. Loading a library is a plain download of a public file, while allowing `fetch()` would let a visualization send chat content anywhere, which is why one is allowed and the other is not.

The tool's only request of its own goes to your own instance: if a script in a visualization fails to parse, it re-reads the raw message from the chats API to repair it.

> [!NOTE]
> With DevTools open you may see CSP errors for `.map` files. Those are DevTools fetching sourcemaps, and regular users never trigger them.

> [!NOTE]
> Even on **None**, API calls can still fail because of CORS. That is decided by the remote server.

---

## 🔌 Offline mode

The **Offline** level guarantees that no request leaves your Open WebUI host.

**Without libraries (no setup):** set `security_level` to `offline`. Diagrams, themed HTML, KPI cards and clickable drill-downs all keep working. Only library charts (Chart.js, D3, ECharts, Plotly, Vega-Lite, vis-network, Tone.js) need a CDN. Optionally remove the **CDN libraries** section from `SKILL.md` so the model does not try to use them.

**With libraries (self-hosted):**

1. Set `security_level` to `offline`
2. Download the libraries you need (the same pinned builds as in `SKILL.md`):

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

3. Put the folder in Open WebUI's static directory. With Docker, mount it so it survives updates:

```bash
docker run -d ... -v /path/on/host/iv-libs:/app/backend/open_webui/static/iv-libs ...
```

   For a bare-metal/pip install, copy it into the `static/` folder of the installed `open_webui` package (or wherever `STATIC_DIR` points).

4. Check that `https://<your-instance>/static/iv-libs/chart.umd.min.js` shows JavaScript in your browser
5. In `SKILL.md`, replace the CDN URLs with your local paths before importing it:

```html
<!-- before -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<!-- after -->
<script src="/static/iv-libs/chart.umd.min.js"></script>
```

If Open WebUI runs under a sub-path (e.g. `https://example.com/webui/`), use `/webui/static/iv-libs/…` instead.

---

## 🧰 Troubleshooting

<details>
<summary><b>"Streaming visualization unavailable" notice</b></summary>

Same-origin access is off. Enable **User Settings → Interface → iframe Sandbox Allow Same Origin**.
</details>

<details>
<summary><b>The visualization is a thin empty strip</b></summary>

The model wrote an empty block, or stopped without closing it. If the closing marker never arrives, the visualization finishes on its own after 30 seconds without new content. Regenerating usually fixes it.
</details>

<details>
<summary><b>A "Visualization script error" toast appears</b></summary>

A script in the visualization does not parse. Most of the time Open WebUI's chat rendering garbled it, and the tool repairs this automatically by re-reading the saved message. The toast only shows when that also fails: the model wrote invalid JavaScript, the chat is temporary (unsaved), or the answer kept streaming for more than about 90 seconds (a refresh fixes that case). The exact error is in the browser console.
</details>

<details>
<summary><b>A Chart.js chart renders empty</b></summary>

Chart.js needs a wrapper like `<div style="position: relative; height: 300px;">` around the canvas and `maintainAspectRatio: false`. The skill covers this under **Library init**.
</details>

<details>
<summary><b>Libraries stopped loading after switching to Offline</b></summary>

Offline blocks the CDNs by design. Self-host the libraries (see [Offline mode](#-offline-mode)) or switch back to **Strict**.
</details>

<details>
<summary><b>External images don't load</b></summary>

Strict blocks external images. Switch to **Balanced**.
</details>

<details>
<summary><b>The done chime is annoying</b></summary>

Open **Workspace → Tools → Inline Visualizer → gear icon** and turn off the **`chime`** valve.
</details>

<details>
<summary><b>I updated <code>tool.py</code> and nothing changed</b></summary>

Existing chats keep the version they were created with. Only new visualizations use the update.
</details>
