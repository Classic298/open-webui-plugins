# 🔌 MCP App Bridge

<img width="6400" height="1600" alt="banner-mcp-app-bridge" src="https://github.com/user-attachments/assets/e90ef10e-9fb6-44de-91bf-2d4db12f0023" />

Renders [MCP Apps](https://github.com/modelcontextprotocol/ext-apps) (SEP-1865) as Rich UI embeds in Open WebUI — using the existing embed system, no middleware changes needed.

> [!IMPORTANT]
> **This is for MCP _Apps_ — MCP tools that ship their own UI (a `ui://` resource).** If your MCP server just exposes plain tools with no interface, you do not need this bridge: connect the server through Open WebUI's built-in MCP support instead. You _can_ point this tool at a plain MCP server, but that is not what it was built for.

> [!TIP]
> **🚀 [Jump to Setup Guide](#setup)** — get up and running in under 1 minute.

> [!NOTE]
> This tool follows the MCP protocol's [dynamic tool discovery pattern](#mcp-dynamic-tool-discovery) — and aligns with Anthropic's [Tool Search Tool](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/tool-search-tool) concept, where tools are discovered and loaded on demand rather than pre-registered in the model's context.

When an MCP server declares a `ui://` resource on a tool, this bridge fetches the HTML and renders it inline in the chat, acting as the MCP Apps host: the app gets the standard handshake, its tool input and result, and can call back into its own server. See [MCP Apps Spec Support](#mcp-apps-spec-support) for what is covered.

### Demo

| Bar Chart | KPI Dashboard | Donut Chart |
|---|---|---|
| ![Bar Chart](assets/demo-bar-chart.png) | ![Dashboard](assets/demo-dashboard.png) | ![Donut Chart](assets/demo-donut-chart.png) |

## How It Works

1. **Model calls `search_mcp_tools` or `list_mcp_tools`** → discovers tools on the MCP server, including which ones have UI resources. Listing is paginated and returns only names and short descriptions; search returns full parameter schemas for the top matches. Full schemas only enter context for tools that match the model's search.
2. **Model calls `call_mcp_tool`** → executes the tool, checks for `_meta.ui.resourceUri`
3. **If a UI resource exists** → fetches the HTML and returns a Rich UI embed via `HTMLResponse`: a small host frame that loads the app in a nested sandboxed iframe with the server's CSP
4. **Open WebUI renders it** in a sandboxed iframe, same as the [Inline Visualizer](../inline-visualizer/). The app talks to the host frame over `postMessage` (JSON-RPC), and the host frame forwards the app's server calls through Open WebUI

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  LLM calls  │────▶│  MCP App    │────▶│  MCP Server │
│  call_mcp_  │     │  Bridge     │     │  (tool +    │
│  tool()     │◀────│  (Tool)     │◀────│  ui:// res) │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │
       │            ┌──────┴──────┐
       │            │ Wraps app:  │
       │            │ • Host page │
       │            │ • CSP       │
       │            │ • Tool data │
       │            │ • Auto-size │
       │            └──────┬──────┘
       ▼                   ▼
┌────────────────────────────┐
│  Open WebUI renders HTML   │
│  as Rich UI embed (iframe) │
└────────────────────────────┘
```

## Security

The bridge honors the MCP Apps spec security model:

| Spec Feature | Implementation |
|---|---|
| Server-declared CSP (`_meta.ui.csp`) | Read from the `resources/read` content item, falling back to the `resources/list` entry. Placed at the very top of the app's document, so it applies before any of the server's markup |
| `connectDomains` | Maps to `connect-src` directive |
| `resourceDomains` | Maps to `script-src`, `style-src`, `img-src`, `font-src`, `media-src` |
| `frameDomains` | Maps to `frame-src` directive |
| `baseUriDomains` | Maps to `base-uri` directive |
| No CSP declared | Restrictive default: blocks all outbound, allows only inline scripts/styles |
| Iframe sandboxing | The app runs in its own nested iframe without `allow-same-origin`, so it never shares an origin with Open WebUI, whatever the same-origin toggle says |
| Tool visibility (`_meta.ui.visibility`) | App-only tools are hidden from the model and cannot be called by it. Model-only tools cannot be called by the app |
| App calls to its server | Sent through an Open WebUI route, checked against the user's access to the tool, and logged on the server. See the note below for which user they run as |

> [!NOTE]
> **Same-origin toggle:** the app stays isolated even when "iframe Sandbox Allow Same Origin" is enabled. It always runs in its own nested frame, so it cannot read Open WebUI's cookies, local storage or page, and it gets no cookies or local storage of its own either. Before 1.0.0, with the toggle on, the app ran on Open WebUI's origin and could read its cookies and local storage. Now only the bridge's own host frame runs there.

> [!NOTE]
> **Who an app's server calls run as:** with the same-origin toggle on, the logged-in user looking at the app, using their own login and their own access to the tool (Open WebUI only shows apps in chats the user owns, including their own copies of shared chats). With it off, the user who ran the tool, through a token stored in the embed that expires 15 minutes after the tool ran. Anyone who can open the chat can read that token, so it only works in chats that are not shared (share link, shared with users, or in a shared folder). Admins can read any chat, so they can use it too. After sharing stops, anyone who opened or cloned the shared chat can still use it until it expires, and copies of the chat (clone, export and import) keep the token, so sharing a copy within those 15 minutes lets its viewers use it.

## MCP Apps Spec Support

The bridge implements the host side of the MCP Apps specification, version 2026-01-26.

| Feature | Support |
|---|---|
| MCP Apps extension (`io.modelcontextprotocol/ui`) advertised on `initialize` | ✅ Servers that check for MCP Apps support register their UI tools |
| `ui/initialize` handshake | ✅ With host capabilities and host context (theme, locale, time zone, container width, platform, the tool definition) |
| `ui/notifications/tool-input` and `tool-result` | ✅ Sent after the handshake. The result is the server's `CallToolResult`; if it has no `structuredContent` and exactly one text block parses as a JSON object, that object is sent as `structuredContent` |
| App calls to its server: `tools/call`, `resources/read`, `resources/list` | ✅ See the note on who they run as. In shared chats only with the same-origin toggle on |
| `ui/message` | ✅ Submitted to the chat once the user confirms Open WebUI's "Confirm Prompt from Embed" dialog. With the same-origin toggle on, Open WebUI would skip that dialog, so the text is only placed in the chat input |
| `ui/open-link` | ✅ Opens a new tab (see below) |
| `ui/notifications/size-changed` | ✅ The embed follows the app's height |
| `ui/request-display-mode` | ✅ Answers `inline`, the only mode offered |
| Logging (`notifications/message`) | ✅ Written to the browser console |
| `prefersBorder` | ✅ Border only, no background |
| Base64 (`blob`) HTML resources | ✅ |

Servers that split their tool list into pages are fully listed. Apps that never start the handshake still get their tool input and result about one second after loading, and the older `window.__MCP_TOOL_RESULT__`, `__MCP_TOOL_ARGS__` and `__MCP_TOOL_NAME__` globals are still set.

Not supported, or only partly, in Open WebUI:

| Feature | Why |
|---|---|
| `ui/resource-teardown` | Open WebUI removes the embed without notice, and a message sent while the frame is being removed never reaches the app |
| `permissions` (camera, microphone, geolocation, clipboard) | Browsers refuse them in the app's sandboxed frame, which has no origin of its own, and Open WebUI's embed frame does not pass them on |
| `ui/update-model-context` | Open WebUI builds the next turn from each tool call's stored output, which the bridge cannot update after the call. The request returns "Method not found" |
| Dedicated app origin (`domain`) | Embeds are `srcdoc` frames with no origin of their own |
| Fullscreen and picture-in-picture | Not offered; apps are told `inline` is the only mode |
| Theme | Follows the browser or OS color preference. Open WebUI's own theme setting is not used |
| Links | Open WebUI's sandbox does not let popups leave it, so a linked page opens in a sandboxed tab. With the same-origin toggle off (the default), sites that need cookies or local storage (logins, for example) do not work there |

> [!NOTE]
> With the same-origin toggle off, an app can call its server for 15 minutes after the tool ran; after that its calls fail with "App expired. Run the tool again." App calls go through a route the bridge registers in the worker process that ran the tool. After a restart, or on a multi-worker or multi-node deployment without sticky sessions, such a call can land on a worker that has not run the tool yet and fail. With a single worker, running the tool again resolves it. With the same-origin toggle off, the app's calls carry no cookies, so cookie-based sticky sessions do not help and a cookie-based auth proxy in front of Open WebUI (oauth2-proxy, Cloudflare Access, Authelia) rejects them.

## Setup

Requires Open WebUI 0.11.4 or newer.

### 1. Install the Tool

1. Copy the contents of `tool.py`
2. In Open WebUI, go to **Workspace → Tools → + Create New**
3. Paste the code
4. Name it **MCP App Bridge** (or whatever you want) and click **Save**

### 2. Configure Valves

1. Click the **gear icon** next to the MCP App Bridge tool
2. Set **mcp_server_url** to your MCP server's streamable HTTP endpoint
3. Pick an **auth_method** (see [Authentication](#authentication)) and fill in the matching valves
4. Set **tool_blocklist** to a comma-separated list of tool names to hide from the model and block from execution (optional)
5. Save

### 3. Attach to a Model

1. Go to **Admin Panel → Settings → Models** and edit your model
2. Under **Tools**, enable the **MCP App Bridge** tool
3. Save

### 4. Use It

Ask your model to interact with the MCP server. It will call `search_mcp_tools` (or `list_mcp_tools` to browse) to discover available tools, then `call_mcp_tool` to execute them. Tools with UI resources render as interactive embeds inline in the chat.

## Authentication

The `auth_method` valve picks how the bridge authenticates against the MCP server:

| `auth_method` | What it does | Valves used |
|---|---|---|
| `bearer` (default) | Sends a single static token for every user. Leave `auth_token` empty for an unauthenticated server. | `auth_token` |
| `oauth_2.1` | Each user signs in to the MCP server themselves. The bridge registers itself at the authorization server with dynamic client registration (RFC 7591). | `oauth_server_url`, `oauth_scope`, `oauth_resource_parameter` |
| `oauth_2.1_static` | Same per-user sign-in, but with a client id and secret you registered by hand. | `oauth_client_id`, `oauth_client_secret`, `oauth_server_url`, `oauth_scope`, `oauth_resource_parameter` |

### How the OAuth 2.1 flow works

The bridge reuses Open WebUI's own MCP OAuth machinery, so the flow is the same one admin-configured MCP tool servers use:

1. On the first tool call the bridge discovers the authorization server from the MCP server (RFC 9728 protected resource metadata, then RFC 8414 / OIDC discovery), then registers an OAuth client and stores the result in its own valves. `oauth_server_url` overrides discovery when a server does not publish metadata.
2. The client is registered with Open WebUI's OAuth client manager under the key `mcp:tool:<tool_id>`, so its redirect URI is Open WebUI's existing callback route, `/oauth/clients/mcp:tool:<tool_id>/callback`.
3. Users without a session get a sign-in link back from the tool (`/oauth/clients/mcp:tool:<tool_id>/authorize`) plus a toast. Opening it runs the standard authorization code flow with PKCE (S256), and the callback stores the token per user.
4. Later calls use that user's access token, refreshed automatically when it is close to expiry. A `401` from the MCP server forces one refresh and retry before the call fails.

Tokens live in Open WebUI's `oauth_session` table, one per user, so users only ever see the tools they personally authorized. The `oauth_client_info` valve holds the encrypted client registration. Clear it to force a fresh registration.

> [!NOTE]
> The OAuth client is registered in the worker process that ran the tool. On a multi-worker or multi-node deployment without sticky sessions, the sign-in link can land on a worker that has not loaded the client yet and return a 404. Retrying the tool call, then the link, resolves it.

## Testing with the Demo Server

A minimal test server is included in `examples/test_server.py`. It exposes a `show_chart` tool with a `ui://demo/chart` resource that renders an animated bar chart.

```
python examples/test_server.py
```

Then set the valve `mcp_server_url` to `http://localhost:8765/mcp` and ask the model:

> "Use the show_chart tool to display quarterly revenue: Q1=45, Q2=62, Q3=38, Q4=71"

## Why a Tool?

The MCP Apps spec (SEP-1865) defines how MCP servers can serve interactive UIs. Some implementations require extensive middleware changes, new frontend components, and additional npm dependencies to support this.

This bridge demonstrates that Open WebUI's existing infrastructure — `HTMLResponse` for Rich UI embeds, sandboxed iframes, auto-height reporting — already provides the rendering pipeline needed. A single Tool file is sufficient to bridge the gap.

## MCP Dynamic Tool Discovery

This tool follows the MCP protocol's dynamic tool discovery pattern — and aligns with Anthropic's [Tool Search Tool](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/tool-search-tool) concept, where tools are discovered and loaded on demand rather than pre-registered in the model's context.

The flow maps directly to MCP primitives:

| Bridge Function | MCP Primitive | Purpose |
|---|---|---|
| `search_mcp_tools` | `tools/list` | Keyword search: returns full parameter schemas for the top matches only |
| `list_mcp_tools` | `tools/list` | Browsing: names and short descriptions, no schemas |
| `call_mcp_tool` | `tools/call` | On-demand execution — model invokes tools by name with arguments |

This avoids pre-loading every MCP tool definition into the model's context window, which is especially important for MCP servers that expose many tools. The model discovers relevant tools first, then loads full schemas only for the top search matches — exactly the pattern the MCP spec and Anthropic's dynamic tool loading approach advocate for.

## MCP Apps vs Open WebUI Rich UI

Open WebUI already has a native Rich UI system: tools that return `HTMLResponse` render interactive HTML inline in the chat inside a sandboxed iframe. This bridge uses that same system to render MCP Apps — no additional rendering infrastructure is needed.

> [!NOTE]
> Tools returning `HTMLResponse` always render inside an iframe, regardless of whether the "iframe Sandbox Allow Same Origin" toggle is enabled. That toggle only controls whether the iframe gets `allow-same-origin` access — the iframe isolation itself is always enforced.

| Capability | MCP Apps (via this bridge) | Open WebUI Rich UI (native) |
|---|---|---|
| Render interactive HTML inline | ✅ | ✅ |
| Sandboxed iframe isolation | ✅ Always | ✅ Always |
| Content Security Policy | ✅ Server-declared CSP | ✅ Via Tool declared CSP (e.g. Inline Visualizer's strict/balanced/none) |
| Auto-height resize | ✅ From the app's size reports, or measured by the bridge | ✅ Built into HTML or injected by tool |
| Theme awareness | ℹ️ Light or dark, from the browser or OS | ✅ Via auto-injected CSS variables |
| Dynamic content per call | ℹ️ Static resource + data injection | ✅ Fully dynamic HTML per invocation |
| Bidirectional communication | ✅ JSON-RPC: server tool calls, resource reads, chat messages, links | ✅ Via native postMessage bridge (sendPrompt, openLink) |
| External dependencies | ⚠️ Requires MCP server with ext-apps | ✅ None — tool generates HTML directly |
| Ecosystem portability | ✅ Works across MCP-Apps compatible hosts | ❌ Open WebUI only |

The key tradeoff: MCP Apps offer **ecosystem portability** — the same UI resource works in any MCP-compatible host. Open WebUI's native Rich UI offers **more flexibility, tighter integration and no additional dependencies** — fully dynamic HTML generation, theme awareness, and bidirectional communication without external dependencies.

This bridge lets you have both: MCP App UIs render in Open WebUI using the same Rich UI pipeline that native tools use.
