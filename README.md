# 🧩 Open WebUI Plugins

A curated collection of plugins for [Open WebUI](https://github.com/open-webui/open-webui) — tools, skills, filters, pipes, actions and events that extend your AI chat experience.

Each plugin lives in its own folder with a README explaining what it does, what components it includes, and how to set it up.

---

## Plugins

| Plugin | Description | Components |
|--------|-------------|------------|
| [Inline Visualizer v2](inline-visualizer-v2/) | 🔹 **LIVE RENDERED** 🔹 interactive HTML/SVG visualizations inline in chat. Full design system with theme-aware colors, SVG utilities, **pre-styled bare HTML** (forms, tables, `<details>`, `<dl>`, …), a **9-color `data-accent` palette**, and six interactive bridges for conversational drill-down - talk to your visualizations, dashboards, charts, maps etc. - First-class support for Chart.js, D3, Vega-Lite, ECharts, Plotly, vis-network, and Tone.js. | Tool + Skill |
| [Prune](prune/) | ⭐ **NEW** ⭐ Automatic, **throttled** database & storage cleanup driven by system events. Old chats, inactive users, orphaned records/uploads/vector collections are pruned in the background, purposefully slowly so a live instance never notices. Valve-configured (`0 = disabled`), dry-run by default, Redis/Valkey-coordinated across replicas, plus a session-gated admin page at `/prune` for manual preview & execute. Requires Open WebUI `0.10.0`. | Event |
| [Keep reasoning_content](keep-reasoning-content/) | Keeps your reasoning model's chain of thought intact across tool calls and follow-up turns, so it no longer "forgets" why it called a tool a moment ago or breaks mid-tool-call with a `reasoning_content is missing` error. Open WebUI normally throws away the model's prior reasoning before sending the next request; this filter feeds it back, so DeepSeek / Kimi / MiMo / vLLM and other reasoning models stay coherent across an entire conversation. | Filter |
| [Interface Defaults](interface-defaults/) | Set your whole instance's **Settings → Interface** defaults from one function's Valves. New users (signup / OAuth / SCIM) are **seeded automatically**; two one-shot buttons push the defaults to everyone or factory-reset the instance. Native Valves UI (toggles, dropdown, number), background bulk ops, no custom UI or monkey-patching. Requires Open WebUI `0.10.0`. | Event |
| [Email Composer](email-composer/) | AI-powered email drafting with an interactive Rich UI card. Rich text editing, To/CC/BCC chips, priority, download .eml, one-click send via mailto. | Tool |
| [MCP App Bridge](mcp-app-bridge/) | Renders MCP Apps (SEP-1865) as Rich UI embeds. Connects to MCP servers, calls tools with `ui://` resources, injects server-declared CSP, and renders the HTML inline — no middleware changes needed. | Tool |
| [Vision Bridge](vision-bridge/) | Give a **text-only model** the ability to work with images, no core changes. A filter strips each image from the request down to a file-id marker (so the model never 404s on it) and leaves the image in the chat; a tool lets the model call `analyze_image(file_id, query)` on demand to send it to a separate vision model, re-queryable with new questions any time. | Filter + Tool |
| [Inline Visualizer](inline-visualizer/) | 🗄️ **LEGACY (v1)** 🗄️ Interactive HTML/SVG visualizations inline in chat. Full design system with theme-aware colors, SVG utilities, Chart.js/D3 support, and a sendPrompt bridge for conversational drill-down. | Tool + Skill |

---

## Plugin Types

| Type | What it does | Where to install |
|------|-------------|-----------------|
| **Tools** | Give your model new capabilities it can call (web search, APIs, rendering) | Workspace → Tools |
| **Skills** | Structured instructions that teach a model how to do specified tasks or workflows | Workspace → Skills |
| **Filters** | Transform messages before they reach the model or before they're shown to you | Admin Panel → Functions |
| **Pipes** | Custom model endpoints — proxy, merge, or create entirely new model behaviors | Admin Panel → Functions |
| **Actions** | Buttons that appear below messages for quick actions | Admin Panel → Functions |
| **Events** | React to system events as they fire (user signup, valve updates, lifecycle hooks). Can also register routes and serve standalone pages. | Admin Panel → Functions |

---

## How to Install

1. Open the plugin's folder and read its **README** for specific instructions
2. Each README lists the components (tool, skill, filter, etc.) and where to install them
3. Some plugins are a single file, others are multi-component — the README will guide you

---

Each plugin folder is self-contained with all necessary files and documentation.

---

## Contributing

Found a bug or have an idea? Open an issue.
