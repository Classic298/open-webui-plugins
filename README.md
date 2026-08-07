# 🧩 Open WebUI Plugins

A curated collection of plugins for [Open WebUI](https://github.com/open-webui/open-webui) — tools, skills, filters, pipes, actions and events that extend your AI chat experience.

Each plugin lives in its own folder with a README explaining what it does, what components it includes, and how to set it up.

---

## Plugins

| Plugin | Description | Components |
|--------|-------------|------------|
| [Inline Visualizer v2](inline-visualizer-v2/) | 🔹 **LIVE RENDERED** 🔹 Your model draws **interactive charts, dashboards, diagrams and mini-apps right in the chat**, appearing live while the answer streams. Everything matches your light/dark theme automatically, and you can talk to what it draws: click a bar or a node and ask the model about it. Works with hand-written SVG/HTML and with Chart.js, D3, Vega-Lite, ECharts, Plotly, vis-network and Tone.js. | Tool + Skill |
| [Prune](prune/) | ⭐ **NEW** ⭐ Keeps a long-running instance from silently filling up: old chats, inactive users and orphaned files are **cleaned out automatically in the background**, so slowly that a live instance never notices. Dry-run by default so nothing is deleted until you say so, with an admin page at `/prune` to preview and run cleanups manually, and safe to use across replicas. Requires Open WebUI `0.10.0`. | Event |
| [Keep reasoning_content](keep-reasoning-content/) | Keeps your reasoning model's chain of thought intact across tool calls and follow-up turns, so it no longer "forgets" why it called a tool a moment ago or breaks mid-tool-call with a `reasoning_content is missing` error. Open WebUI normally throws away the model's prior reasoning before sending the next request; this filter feeds it back, so DeepSeek / Kimi / MiMo / vLLM and other reasoning models stay coherent across an entire conversation. | Filter |
| [Interface Defaults](interface-defaults/) | Decide what **Settings → Interface** looks like for everyone on your instance: pick the defaults once and **every new user starts with them**, whether they arrive via signup, OAuth or SCIM. One-shot buttons push your defaults to all existing users or reset the instance, all configured from the function's own settings panel. Requires Open WebUI `0.10.0`. | Event |
| [Email Composer](email-composer/) | Draft emails with your model and get a **real email card in the chat**: edit the rich text, adjust To/CC/BCC and priority, then download it as .eml or hand it to your mail app with one click. | Tool |
| [MCP App Bridge](mcp-app-bridge/) | Use **MCP Apps** (SEP-1865) inside your chat: connect an MCP server and its tools **bring their own interactive interface**, rendered as an embedded panel right where the model called them. No middleware and no core changes needed. | Tool |
| [Vision Bridge](vision-bridge/) | Lets a **text-only model work with images**: attach a picture and the model asks a separate vision model to look at it on demand, and can come back with new questions about the same image any time, all without breaking on the image itself and without core changes. Requires Open WebUI `0.11.0`. | Filter + Tool |
| [Inline Visualizer](inline-visualizer/) | 🗄️ **LEGACY (v1)** 🗄️ The original version: interactive charts and visualizations in chat, rendered once the answer finishes rather than live, with the same theme-aware design system and Chart.js/D3 support. | Tool + Skill |

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
