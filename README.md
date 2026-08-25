# 🧩 Open WebUI Plugins

A curated collection of plugins for [Open WebUI](https://github.com/open-webui/open-webui): tools, skills, filters, pipes, actions and events that extend your AI chat experience.

Each plugin lives in its own folder with a README explaining what it does, what components it includes, and how to set it up.

---

## Plugins

<!-- Icons are local paths until the PNGs are uploaded to the repo; replace each src with its
     GitHub attachment URL after upload. Only plugins that have a banner get an icon. -->
| | Plugin | Description | Components |
|---|--------|-------------|------------|
| <img src="square-inline-visualizer-v2.png" width="64"> | [Inline Visualizer v2](inline-visualizer-v2/) | 🔹 **LIVE RENDERED** 🔹 Your model draws **interactive charts, dashboards, diagrams and mini-apps right in the chat**, appearing live while the answer streams. Everything matches your light/dark theme automatically, and you can click a bar or a node and ask the model about it. Works with hand-written SVG/HTML and with Chart.js, D3, Vega-Lite, ECharts, Plotly, vis-network and Tone.js. | Tool + Skill |
| <img src="square-prune.png" width="64"> | [Prune](prune/) | ⭐ **NEW** ⭐ Old chats, inactive users and orphaned files are **cleaned out automatically in the background**, so slowly that a live instance never notices. Dry-run by default, with an admin page at `/prune` to preview and run cleanups manually. Safe across replicas. | Event |
|  | [Keep reasoning_content](keep-reasoning-content/) | Feeds a reasoning model its own prior chain of thought back, so DeepSeek / Kimi / MiMo / vLLM models stay coherent across tool calls and follow-up turns. Fixes the `reasoning_content is missing` break mid-tool-call. | Filter |
| <img src="square-interface-defaults.png" width="64"> | [Interface Defaults](interface-defaults/) | Open WebUI's **Default Interface Settings** page cannot push your defaults onto **existing** users. This adds that, a full factory reset, and defaults for the settings that page cannot reach: notifications, keyboard shortcuts, memory, the personal system prompt and the speech/voice block. | Event |
| <img src="square-email-composer.png" width="64"> | [Email Composer](email-composer/) | Draft emails with your model and get a **real email card in the chat**: edit the rich text, adjust To/CC/BCC and priority, then download it as .eml or hand it to your mail app with one click. | Tool |
| <img src="square-mcp-app-bridge.png" width="64"> | [MCP App Bridge](mcp-app-bridge/) | Use **MCP Apps** (SEP-1865) inside your chat: connect an MCP server and its tools **bring their own interactive interface**, rendered as an embedded panel right where the model called them. No middleware and no core changes needed. | Tool |
| <img src="square-vision-bridge.png" width="64"> | [Vision Bridge](vision-bridge/) | Lets a **text-only model work with images**: attach a picture and the model asks a separate vision model to look at it on demand, then comes back with new questions about the same image any time. No core changes. | Filter + Tool |
|  | [Inline Visualizer](inline-visualizer/) | 🗄️ **LEGACY (v1)** 🗄️ The original version: interactive charts and visualizations in chat, rendered once the answer finishes, with the same theme-aware design system and Chart.js/D3 support. | Tool + Skill |

---

## Plugin Types

| Type | What it does | Where to install |
|------|-------------|-----------------|
| **Tools** | Give your model new capabilities it can call (web search, APIs, rendering) | Workspace → Tools |
| **Skills** | Structured instructions that teach a model how to do specified tasks or workflows | Workspace → Skills |
| **Filters** | Transform messages before they reach the model or before they're shown to you | Admin Panel → Functions |
| **Pipes** | Custom model endpoints. Proxy, merge, or create entirely new model behaviors | Admin Panel → Functions |
| **Actions** | Buttons that appear below messages for quick actions | Admin Panel → Functions |
| **Events** | React to system events as they fire (user signup, valve updates, lifecycle hooks). Can also register routes and serve standalone pages. | Admin Panel → Functions |

---

## How to Install

1. Open the plugin's folder and read its **README** for specific instructions
2. Each README lists the components (tool, skill, filter, etc.) and where to install them
3. Some plugins are a single file, others are multi-component; the README will guide you

---

Each plugin folder is self-contained with all necessary files and documentation.

---

## Contributing

Found a bug or have an idea? Open an issue.
