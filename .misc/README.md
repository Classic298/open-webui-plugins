# 🎨 Banner kit

Generates the art for this repo: the wide banner at the top of each plugin README and the square icon in the root README table. Both come from the same palette per plugin, so every plugin gets a matching pair.

| Output | Size | Used in |
|---|---|---|
| `banner-<key>.png` | 1600x400 layout, saved as 6400x1600 | Top of the plugin's README |
| `square-<key>.png` | 400x400 layout, saved as 1600x1600 | Root README plugin table |

## Files

| File | What it does |
|------|------|
| `banners.py` | The banner template, one config entry per plugin, and the drawing (motif) for each plugin. Writes `banner_<key>.html`. |
| `squares.py` | The icon template and one entry per plugin, reusing the banner's colors and emoji. Writes `square_<key>.html`. |
| `render.mjs` | Turns every `banner_*.html` into `banner-<key>.png` with headless Chrome. |
| `render_squares.mjs` | Same for every `square_*.html`. |
| `promo.example.html` | A taller 16:10 hero layout (a mock Valves panel on a designed background). Render at 1600x1000. |

## Run

```bash
python banners.py && node render.mjs
python squares.py && node render_squares.mjs
```

Needs Python 3 and Node 22 (for the built-in `WebSocket`). Point `CHROME` at a Chrome or Chromium binary when it is not at the Windows default:

```bash
CHROME=/usr/bin/chromium node render.mjs
```

The HTML and PNG files are gitignored. The final PNGs get uploaded to GitHub (drop them into any GitHub text box to get a `user-attachments` link) and linked from the READMEs.

> [!NOTE]
> The published art was rendered on Windows, which draws the text in **Segoe UI** and the emoji as **Fluent 3D**. Other systems fall back to their own fonts and emoji, so a render there looks slightly different. For the emoji, swap it for the matching PNG from [microsoft/fluentui-emoji](https://github.com/microsoft/fluentui-emoji) (`assets/<Name>/3D/<name>_3d.png`) before rendering.

## Add a plugin

1. In `banners.py`, write a motif function `m_<name>(a1, a2)` that returns an inline `<svg width="384" height="300" viewBox="0 0 384 300">…</svg>`, drawn with the two accent colors. Keep it iconic (5 to 10 shapes), and keep every shape inside its container with about 8px to spare.
2. Add `banners["<key>"] = dict(a1=..., a2=..., emoji=..., title=..., title_size=..., badges=[...], tag="...", motif=m_<name>(a1, a2))`.
3. In `squares.py`, add `"<key>": dict(a1=..., a2=..., emoji=..., title=["First", "Second"])` with the same colors and emoji. Each list entry is one line of the title.
4. Run both commands above and check the PNGs.

## Design rules

- **Canvas:** banner 1600x400 (4:1), icon 400x400. Both saved at 4x.
- **Background:** flat near-black (`#08090d` to `#0c0d14`), two accent glows (`a1` top-left, `a2` bottom-right), a faded dot grid and an accent strip on the left edge.
- **Colors:** each plugin gets a primary `a1` and a secondary `a2`. Taken so far: Interface Defaults indigo/violet, Inline Visualizer teal/purple, Email Composer blue/sky, MCP App Bridge emerald, Vision Bridge amber/coral, Prune teal/green, Better Banners orange/yellow.
- **Title:** 78 to 90px, weight 800, fading from white into `a2`, with the plugin's emoji next to it.
- **Layout:** text on the left (badges, then emoji and title, then a tagline of at most two lines), the motif in a framed glass panel on the right.
- **Badges:** 2 or 3 words each and never a version number, because those go stale. The first badge is filled with the accent color, the others get an accent dot. Longer explanations belong in the tagline.
- **Flat:** no drop shadows except on the motif panel, no gradient text except the title, nothing smaller than 15px.
