# Vision Bridge

<img width="6400" height="1600" alt="banner-vision-bridge" src="https://github.com/user-attachments/assets/cbbe17c2-a529-44db-b87c-ec9ecf62f03a" />

Give a **text-only model the ability to work with images**, with no core changes. A filter takes the image out of the request (so the text-only model never breaks on an image it cannot accept) and leaves a marker in its place. The tools then let the model send either a chat attachment or an image file in the connected Open Terminal to a separate vision model on demand. Chat attachments stay untouched and can be inspected as many times as needed.

> [!IMPORTANT]
> **Requires Open WebUI `0.11.0` or newer.** Both parts resolve chat ids through the core helper added in that release. They will not load on older versions.

> [!TIP]
> **🚀 [Jump to Setup](#setup)** — five steps, about a minute. Do them **all**, in order. Skipping one is the cause of almost every "it doesn't work" report.

---

## The five rules (read this first)

Nearly every failure comes from breaking one of these. If something does not work, check them in order before anything else.

| # | Rule | Why |
|---|------|-----|
| 1 | **Turn on the `Vision` capability on your text-only model.** | Without it Open WebUI refuses the upload with *"Selected model(s) do not support image inputs"* — you would not even get as far as the filter. You are lying to the UI on purpose here: Vision Bridge is what makes the lie true. |
| 2 | **Enable the filter on exactly the models that need it** (Admin Panel → Settings → Models → your model → Filters), **not globally.** | The filter's entire job is to remove images. Every model it runs on loses its images, so put it only on the text-only models that need rescuing — never on a real vision model. |
| 3 | **The `vision_model_id` you care about lives in the TOOL valves**, not in the filter — unless you use describe mode. | Two different files each have a valve with that name. See [Which valve goes where](#which-valve-goes-where). Filling in the wrong one is the single most common mistake. |
| 4 | **Copy the model id exactly as Open WebUI shows it**, including any connection prefix (e.g. `Ionos .Qwen/Qwen3.5-397B-A17B`, not `Qwen3.5-397B`). | The id is matched 1:1. Anything else gives `Vision analysis failed: Model not found`. The provider's marketing name, the display name and the id are often three different strings. |
| 5 | **The vision model must be usable by the person chatting**, not just by you. | A `Private` vision model is the classic "works on my admin account, broken for everyone else" report. Give it the same access as the text-only model (public, or the same group), and test once with a normal user account. |

> [!NOTE]
> The filter and the tool are a pair. The filter keeps the image out of the text-only model's request; the tool lets that model look at the image on demand through a vision model you configure. **Install both.** The only exception is describe mode, which is filter-only — see [Two modes](#two-modes).

## The problem this fixes

Route an image to a text-only model and the request fails: the model (or the provider) rejects an `image_url` part it was never built to accept. What you see in the chat is usually a generic upstream error, for example:

```
Received an unhandled error from the upstream service
```
```
ERROR | Upstream openai-compatible request failed: HTTP 500 (server_failed) …
        code=upstream-service-error message=Received an unhandled error from the upstream service
```

The usual workaround is to hard-swap the image for a one-shot description, which throws the real image away and locks you into whatever that single description happened to capture.

Vision Bridge keeps the image and defers the looking. The text-only model drives its own conversation and, whenever it needs to, calls out to a vision model with a specific question. Ask again later with a different question and it looks again, at the same untouched image.

## How it works

1. **Filter** runs on the request to the text-only model. Each image part is replaced with a text marker: `[Image attached — file_id: <id>. Call analyze_image(...) to inspect it.]`, or `[Image attached. Call analyze_image(query="…") to inspect the most recent image.]` when the id is not in the request (Open WebUI inlines uploaded images before filters run). The model receives the marker, never the image. The image stays in the chat and in storage.
2. **For chat attachments, the model calls `analyze_image(file_id, query)`.** The tool resolves the file id to the stored image, sends it plus the question to the configured vision model, and returns the answer as text.
3. **For files in Open Terminal, the model calls `analyze_terminal_image(path, query)`.** The tool reads the image from the currently connected terminal and sends it directly to the configured vision model.
4. **The filter adds tool-selection instructions.** They tell the model which vision tool to use, require real visual verification after generating or modifying an image, and reserve `read_file` for non-image content. Inline images returned by tools are also persisted before they are replaced with markers when possible.
5. **Re-query any time.** Because an image is not consumed by analysis, the model can call the appropriate tool again with a new question.

### Images generated in Open Terminal

The additional `analyze_terminal_image` tool is required for the **Open WebUI → Open Terminal** workflow. A terminal-generated image exists at a terminal path, not as a chat attachment with a file id, so `analyze_image` could not find it. Previously this made the workflow stall: the bridge returned a missing-image error and the model could not continue with visual verification.

Use `analyze_image` for images attached to the conversation and `analyze_terminal_image(path="...", query="...")` for PNG, JPEG, WebP, or other image files created or stored in the connected terminal. Do not call `read_file` first for a terminal image—the new tool performs that read internally and forwards the image to the vision model. For animations or GIFs, extract representative frames and inspect them with `analyze_terminal_image` when reliable visual verification is needed.

```
┌──────────────┐   image stripped    ┌──────────────┐
│ Text-only    │◀───to a marker──────│  Vision      │
│ model        │                     │  Bridge      │
│ (deepseek…)  │──analyze_image()───▶│  Filter+Tool │
└──────────────┘◀──answer as text────└──────┬───────┘
                                            │ file_id -> image
                                            ▼
                                     ┌──────────────┐
                                     │ Vision model │
                                     │ (gpt-4o,     │
                                     │  minimax…)   │
                                     └──────────────┘
```

## Components

| File | Type | Install location |
|------|------|-----------------|
| `filter.py` | Filter | Admin Panel → Functions |
| `tool.py` | Tool | Workspace → Tools |

## Setup

### 1. Install the Filter

1. Copy the **entire** contents of `filter.py`.
2. **Admin Panel → Functions → ➕** , paste, give it a name, **Save**.
3. Make sure the function's toggle is **on** in the Functions list.

> [!WARNING]
> Toggling the function **on** in the Functions list only means "this filter exists and may be used". It does **not** attach it to any model — that is step 4.

### 2. Install the Tool

1. Copy the **entire** contents of `tool.py`.
2. **Workspace → Tools → ➕**, paste, give it a name, **Save**.

### 3. Set the vision model on the Tool

1. In **Workspace → Tools**, open the tool's **⚙️ valves**.
2. Set `vision_model_id` to your **vision-capable** model's id.
3. Get that id from **Admin Panel → Settings → Models**: find the model, and copy the id **character for character**, including any connection prefix. Nothing else — not the provider's page title, not the pretty display name.
4. Make sure that model is **not restricted** to you (rule 5).

### 4. Turn everything on for your text-only model

**Admin Panel → Settings → Models → edit your text-only model**, then:

| Section | What to do |
|---------|-----------|
| **Capabilities** | Tick **Vision** ✅ — otherwise Open WebUI blocks the image upload entirely. |
| **Filters** | Enable **Vision Bridge** ✅ — this is what strips the image. |
| **Tools** | Enable **Vision Bridge** ✅ — this is what lets the model look. |

**Save.**

### 5. Verify it actually works

Open a **normal (non-temporary) chat** with that model, attach an image, and ask *"what is in this image?"*.

You should see:
- a status line like **"Looking at the image with `<your-vision-model>`…"**, and
- an answer describing the image.

If you see an upstream error instead, the filter is not attached (step 4). If you see `Model not found`, the id is wrong (step 3). See [Troubleshooting](#troubleshooting).

## Which valve goes where

Both files have a valve called `vision_model_id`. They are **not** the same thing, and you almost never need both.

| Your setup | Filter `strip_only` | Filter `vision_model_id` | Tool `vision_model_id` |
|------------|--------------------|--------------------------|------------------------|
| **Recommended** — model can call tools | `true` (on) | leave **empty** | **required** ✅ |
| Model **cannot** call tools (describe mode) | `false` (off) | **required** ✅ | not used (tool not needed) |
| ❌ Broken configuration | `true` (on) | filled in | empty |

> [!CAUTION]
> Filling in the filter's `vision_model_id` while `strip_only` is **on** does nothing at all — that valve is only read in describe mode. If the tool's valve is then still empty, every image request ends with *"Vision Bridge is not configured"*. Read the description under `strip_only` in the valve panel: *"When false, the filter instead analyzes and swaps the image for text (needs vision_model_id)."* — **when false**.

## Configuration

### Filter valves (`filter.py`)

| Valve | Default | Purpose |
|-------|---------|---------|
| `strip_only` | `true` | **On:** remove images from the request, replacing each with a text marker, and leave them in the chat — pair with the tool for on-demand re-analysis. **Off:** describe mode (below). |
| `vision_model_id` | `""` | Vision model used **only** in describe mode (`strip_only = false`). Ignored otherwise. |
| `analysis_prompt` | "Describe this image…" | Instruction sent to the vision model in describe mode. |
| `label` | "Image description" | Heading for the inlined description (describe mode). |
| `purge_from_history` | `true` | Describe mode: replace the saved image with its description. |
| `delete_file_record` | `true` | Describe mode: delete the image file after analysis. |
| `max_images` | `4` | Max images per message (describe mode). |

### Tool valves (`tool.py`)

| Valve | Default | Purpose |
|-------|---------|---------|
| `vision_model_id` | `""` | **Required.** The vision-capable model that actually looks at images. Must match the model id in Admin Panel → Settings → Models exactly. |
| `default_query` | "Describe this image…" | Question used when the model calls `analyze_image` without one. |

## Two modes

The filter has two modes, chosen by the `strip_only` valve:

- **`strip_only = true` (default, tool-driven):** the recommended pairing. The image is swapped for a marker and kept in the chat, and the **tool** does the looking on demand. Best for models that can tool-call, and the only mode that supports re-querying the same image with new questions over time.
- **`strip_only = false` (describe-and-replace):** the filter itself runs one vision pass up front and swaps the image for the resulting text (needs `vision_model_id` on the **filter**). For models that cannot tool-call. This consumes the image (optionally deleting it), so there is no later re-analysis. Any image the vision pass does not cover (an older turn whose image is still in the chat, one that can no longer be read, or anything past `max_images`) is replaced by a "not sent to this model" note, so the text-only model never receives an image.

## Troubleshooting

Find your exact message in the left column.

| What you see | What it means | Fix |
|--------------|---------------|-----|
| `Received an unhandled error from the upstream service` / `HTTP 500` in the logs | The image reached the text-only model. The filter did **not** run on this request. | The filter is not enabled **on that model** (Admin Panel → Settings → Models → your model → Filters). Enabling the function in the Functions list is not enough. Also check you edited the model you are actually chatting with — a workspace model and its base model are two different entries. |
| `Selected model(s) do not support image inputs` (upload is blocked) | Open WebUI thinks the model cannot take images. | Tick **Vision** under the model's **Capabilities**. |
| `Vision analysis failed: Model not found` | The id in the tool's `vision_model_id` does not match any model id on your instance. | Copy the id from Admin Panel → Settings → Models exactly, including any connection prefix (`Ionos .Qwen/…`). No trailing spaces, no display name, no provider docs name. |
| `Vision Bridge is not configured: set a vision_model_id in the tool valves.` | The **tool's** valve is empty. | You probably put the model id in the **filter's** valve instead. See [Which valve goes where](#which-valve-goes-where). |
| The model replies *"I cannot analyze images / I have no image recognition function"* | The tool is not available to the model, or the tool call returned an error the model then paraphrased. | Enable **Vision Bridge** under the model's **Tools**. Then re-check the tool's `vision_model_id`, and expand the tool call in the chat to read the real error. |
| Works for you (admin), fails for your users | Something in the chain is not reachable for that user — most often a `Private` vision model. | Give the vision model the same access as the text-only model (public, or the same group), and confirm the user can select it themselves. Always re-test with a normal user account. |
| `No matching image found (it may have been deleted, or the file id is wrong)` | The tool could not resolve an image. | Use a **normal chat, not a temporary chat** — temporary chats are not stored, so there is nothing for the tool to look up. Also check the image was not deleted by a previous describe-mode run. |
| The answer describes the **wrong** image | Multi-image chat: uploaded images arrive without a file id, so the tool falls back to the **most recent** image. | Ask about one image at a time, or re-attach the image you mean in the current turn. |
| Nothing happens at all in describe mode | `strip_only` is still on, or the **filter's** `vision_model_id` is empty. | Describe mode needs `strip_only = false` **and** a model id on the filter. |
| The vision model answers, but about nothing useful | The default query is generic. | The model can pass its own `query`; you can also change `default_query` on the tool. |

## FAQ

<details>
<summary><b>Do I need both the filter and the tool?</b></summary>

For the on-demand flow, yes. The filter keeps the image out of the text-only model's request (so it does not error), and the tool is what lets the model actually look at the image when it decides to. If your model cannot tool-call, use the filter alone in describe mode (`strip_only = false`), which inlines one description up front.
</details>

<details>
<summary><b>Should I enable the filter globally?</b></summary>

No. The filter removes images from every request it touches, which is exactly what you want for a text-only model and exactly what you do not want for a real vision model. Enable it per model, on the text-only models that need it (Admin Panel → Settings → Models → your model → Filters). That is also why there is no "skip if the model is vision-capable" valve: it would have to be off in the one setup that matters — you have to mark your text-only model as vision-capable to let images in at all — so it only ever silently disabled the filter.
</details>

<details>
<summary><b>Which model does the actual looking?</b></summary>

Whatever you set as `vision_model_id` on the tool (for the on-demand flow) or on the filter (for describe mode). It can be any vision-capable model your instance can reach, for example `gpt-4o` or a multimodal model on OpenRouter. The text-only model never sees the image itself; it only ever gets text back.
</details>

<details>
<summary><b>Where exactly do I find the model id?</b></summary>

**Admin Panel → Settings → Models**, then search for your vision model. The id is what the list and the model's edit page show — and if the connection has a prefix configured, that prefix is part of the id (`Ionos .Qwen/Qwen3.5-397B-A17B`). It is matched exactly, so copy and paste it rather than typing it.
</details>

<details>
<summary><b>Can the model ask more than one question about the same image?</b></summary>

Yes, that is the point of `strip_only` mode. The image is left untouched in the chat, so the model can call `analyze_image` again with a new `query` at any time and get a fresh answer. Note that uploaded images reach the filter without a file id (Open WebUI inlines them first), so the tool resolves the most recent image in the chat; an older image in a multi-image chat can only be targeted when the marker carries a `file_id`. Describe mode does not support re-analysis at all, since it consumes the image up front.
</details>

<details>
<summary><b>Does it work in temporary chats?</b></summary>

Describe mode does. The on-demand tool needs the stored chat to find the image, and a temporary chat is never stored — so use a normal chat for the tool-driven flow.
</details>

<details>
<summary><b>What happens to the original image?</b></summary>

In `strip_only` mode it stays in the chat and in storage, unchanged. In describe mode it is replaced in history by its text description, and (with the default valves) the file record is deleted after analysis.
</details>

## Validated

Verified end-to-end against OpenRouter. A text-only `deepseek-v4-flash` received the marker (no image), then re-queried the same image twice via `minimax-m3`: "what colors?" and "any text?" returned correct, different answers. Re-analysis of one image with new questions over time works, and a vision call only happens when the model actually asks.

## Changelog

- **1.0.2** — Removed the `skip_if_vision_capable` valve. It was a trap: a text-only model has to be marked vision-capable for Open WebUI to accept an image upload at all, so the valve turned the filter off in precisely the setup it exists for — the image then went straight to the text-only model and came back as an upstream 500. Enable the filter per model instead of globally. README rewritten around the configuration mistakes people actually hit: which of the two `vision_model_id` valves to fill in, exact model ids including connection prefixes, vision model access for non-admin users, and an error-message-to-fix table.
- **1.0.1** — Fixed images reaching the text-only model. Describe mode only replaced the newest image message, so images from earlier turns were sent as-is (Ollama `500 image input is not supported`, or a confident description of an image the model cannot see); anything the vision pass does not cover is now replaced by a marker in both modes. Describe mode also purges the analyzed image from the chat again: Open WebUI inlines uploaded images as data URIs before filters run, so the file id is now taken from the stored chat instead of the request url, which also restores a usable `analyze_image` hint in `strip_only` mode. The tool now recognises the `temporary:` chat id prefix added in 0.11.0, so it no longer looks a temporary chat up in the database.
- **1.0.0** — Initial release. `strip_only` tool-driven mode: the image is kept in the chat and inspected on demand via `analyze_image`, so it can be re-queried with new questions. Describe-and-replace mode is available for models that cannot tool-call.
