# 👁️ Vision Bridge

<img width="6400" height="1600" alt="banner-vision-bridge" src="https://github.com/user-attachments/assets/cbbe17c2-a529-44db-b87c-ec9ecf62f03a" />

Give a **text-only model the ability to work with images**, with no core changes. A filter takes the image out of the request (so the text-only model never 404s on an image it cannot accept) and leaves a marker in its place. A tool then lets the model send that image to a separate vision model on demand, asking whatever it wants, as many times as it wants. The image itself stays in the chat untouched.

> [!TIP]
> **🚀 [Jump to Setup](#setup)** — install both parts, set two valves, done in about a minute.

> [!NOTE]
> The filter and the tool are a pair. The filter keeps the image out of the text-only model's request; the tool lets that model look at the image on demand through a vision model you configure. Install both for the on-demand flow.

## ⚠️ The problem this fixes

Route an image to a text-only model and the request fails: the model (or the provider) rejects an `image_url` part it was never built to accept. The usual workaround is to hard-swap the image for a one-shot description, which throws the real image away and locks you into whatever that single description happened to capture.

Vision Bridge keeps the image and defers the looking. The text-only model drives its own conversation and, whenever it needs to, calls out to a vision model with a specific question. Ask again later with a different question and it looks again, at the same untouched image.

## ✅ How it works

1. **Filter (`strip_only`)** runs on the request to the text-only model. Each image part is replaced with a text marker: `[Image attached — file_id: <id>. Call analyze_image(...) to inspect it.]`, or `[Image attached. Call analyze_image(query="…") to inspect the most recent image.]` when the id is not in the request (Open WebUI inlines uploaded images before filters run). The model receives the marker, never the image. The image stays in the chat and in storage.
2. **Model calls `analyze_image(file_id, query)`** whenever it needs to see something. The tool resolves the file id to the stored image, sends it plus the question to the configured vision model, and returns the answer as text.
3. **Re-query any time.** Because the image is never consumed or deleted, the model can call the tool again with a new question and get a fresh, different answer about the same image.

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

## 🧩 Components

| File | Type | Install location |
|------|------|-----------------|
| `filter.py` | Filter | Admin Panel → Functions |
| `tool.py` | Tool | Workspace → Tools |

## Setup

### 1. Install the Filter

1. Copy the contents of `filter.py`.
2. In Open WebUI, go to **Admin Panel → Functions → + New**, paste the code, and **Save**.
3. Enable it on your text-only model (or Global), and set the valve `strip_only = true`.

### 2. Install the Tool

1. Copy the contents of `tool.py`.
2. Go to **Workspace → Tools → + Create New**, paste the code, and **Save**.
3. Open the tool's valves and set `vision_model_id` to your multimodal model (e.g. `gpt-4o`, or a vision model on OpenRouter).

### 3. Attach the Tool to your model

1. **Admin Panel → Settings → Models**, edit your text-only model.
2. Under **Tools**, enable **Vision Bridge**, and **Save**.

That is it. Send an image in a chat with that model: the filter strips it to a marker, and the model calls `analyze_image` when it wants to look.

## ⚙️ Configuration

### Filter valves (`filter.py`)

| Valve | Default | Purpose |
|-------|---------|---------|
| `strip_only` | `true` | Remove images from the request, replacing each with a text marker, and leave them in the chat. Pair with the tool for on-demand re-analysis. Set `false` for describe mode (below). |
| `vision_model_id` | `""` | Vision model used **only** in describe mode. |
| `analysis_prompt` | "Describe this image…" | Instruction sent to the vision model in describe mode. |
| `label` | "Image description" | Heading for the inlined description (describe mode). |
| `purge_from_history` | `true` | Describe mode: replace the saved image with its description. |
| `delete_file_record` | `true` | Describe mode: delete the image file after analysis. |
| `skip_if_vision_capable` | `false` | If the target model already has the `vision` capability, do nothing (useful for a Global install). |
| `max_images` | `4` | Max images per message (describe mode). |

### Tool valves (`tool.py`)

| Valve | Default | Purpose |
|-------|---------|---------|
| `vision_model_id` | `""` | **Required.** The vision-capable model that actually looks at images. |
| `default_query` | "Describe this image…" | Question used when the model calls `analyze_image` without one. |

## 🔀 Two modes

The filter has two modes, chosen by the `strip_only` valve:

- **`strip_only = true` (default, tool-driven):** the recommended pairing. The image is swapped for a marker and kept in the chat, and the **tool** does the looking on demand. Best for models that can tool-call, and the only mode that supports re-querying the same image with new questions over time.
- **`strip_only = false` (describe-and-replace):** the filter itself runs one vision pass up front and swaps the image for the resulting text (needs `vision_model_id` on the **filter**). For models that cannot tool-call. This consumes the image (optionally deleting it), so there is no later re-analysis. Any image the vision pass does not cover (an older turn whose image is still in the chat, one that can no longer be read, or anything past `max_images`) is replaced by a "not sent to this model" note, so the text-only model never receives an image.

## 🧪 Validated

Verified end-to-end against OpenRouter. A text-only `deepseek-v4-flash` received the marker (no image), then re-queried the same image twice via `minimax-m3`: "what colors?" and "any text?" returned correct, different answers. Re-analysis of one image with new questions over time works, and a vision call only happens when the model actually asks.

## ❓ FAQ

<details>
<summary><b>Do I need both the filter and the tool?</b></summary>

For the on-demand flow, yes. The filter keeps the image out of the text-only model's request (so it does not error), and the tool is what lets the model actually look at the image when it decides to. If your model cannot tool-call, use the filter alone in describe mode (`strip_only = false`), which inlines one description up front.
</details>

<details>
<summary><b>Which model does the actual looking?</b></summary>

Whatever you set as `vision_model_id` on the tool (for the on-demand flow) or on the filter (for describe mode). It can be any vision-capable model your instance can reach, for example `gpt-4o` or a multimodal model on OpenRouter. The text-only model never sees the image itself; it only ever gets text back.
</details>

<details>
<summary><b>Can the model ask more than one question about the same image?</b></summary>

Yes, that is the point of `strip_only` mode. The image is left untouched in the chat, so the model can call `analyze_image` again with a new `query` at any time and get a fresh answer. Note that uploaded images reach the filter without a file id (Open WebUI inlines them first), so the tool resolves the most recent image in the chat; an older image in a multi-image chat can only be targeted when the marker carries a `file_id`. Describe mode does not support re-analysis at all, since it consumes the image up front.
</details>

<details>
<summary><b>What happens to the original image?</b></summary>

In `strip_only` mode it stays in the chat and in storage, unchanged. In describe mode it is replaced in history by its text description, and (with the default valves) the file record is deleted after analysis.
</details>

## 📝 Changelog

- **1.0.1** — Fixed images reaching the text-only model. Describe mode only replaced the newest image message, so images from earlier turns were sent as-is (Ollama `500 image input is not supported`, or a confident description of an image the model cannot see); anything the vision pass does not cover is now replaced by a marker in both modes. Describe mode also purges the analyzed image from the chat again: Open WebUI inlines uploaded images as data URIs before filters run, so the file id is now taken from the stored chat instead of the request url, which also restores a usable `analyze_image` hint in `strip_only` mode.
- **1.0.0** — Initial release. `strip_only` tool-driven mode: the image is kept in the chat and inspected on demand via `analyze_image`, so it can be re-queried with new questions. Describe-and-replace mode is available for models that cannot tool-call.
