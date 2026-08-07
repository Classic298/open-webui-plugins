---
name: visualize
description: Render rich interactive visuals — SVG diagrams, HTML widgets, Chart.js charts, and interactive explainers — directly inline in chat using visualize(). Use only when the user explicitly asks for a visualization, diagram, chart, graph, drawing, map, dashboard, or similar visual artifact. Do not use for ordinary markdown, code blocks, file previews, or answer formatting
---

# Inline Visualizer

This is the handbook/tutorial on how to use the visualizer tool.
The visualizer tool can render rich interactive visuals directly inline in chat using visualize.

## How to use

you called the view_skill() tool to read the tutorial/handbook about this tool.
Read the entire handbook carefully and follow the rules closely, otherwise the visualizations might end up not rendering properly or being entirely broken.
This tutorial/handbook shows you how to actually use the tool and build beautiful visualizations.

1. Call visualize(title="…") - YOU MUST CALL THE TOOL, otherwise the visualization you output will not be rendered in the chat.
2. Calling the tool, an iFrame wrapper sandbox will immediately appear inside the chat (visible only to the user). This iFrame sandbox will AUTOMATICALLY paint/render everything you output within the tags after you called the tool.
3. After calling the tool, start with the opening tag @@@VIZ-START on its own line
4. Next, after the opening tag, emit the HTML/SVG content (no <!DOCTYPE>, <html>, <head>, <body>)
5. Once you are done writing the code for the visualization, immediately close with @@@VIZ-END on its own line
6. Done! The visualization is complete. Continue with any follow-up text to the user.

The raw markers + SVG source are auto-hidden from the chat — users see only the rendered iframe filling in live.

**Example response structure:**

"""
I'll visualize the attention mechanism for you.

@@@VIZ-START
<svg viewBox="0 0 680 240">
  <!-- content streams here, renders live -->
</svg>
@@@VIZ-END

As you can see, each query token attends to all key tokens simultaneously.
"""

**Streaming rules:**
- Use the delimiters EXACTLY @@@VIZ-START and @@@VIZ-END — case-sensitive, on their own lines. Do NOT put the content inside  ```, ~~~, or ::: fences or any codeblock or other markdown.
- Do NOT wrap in HTML tags like <viz> or <svg data-iv> — only the text markers are detected.
- Emit **exactly ONE** @@@VIZ-START … @@@VIZ-END pair per tool call. For multiple visualizations, call the tool multiple times.
- Structure the content as always: <style> first → visible content → <script> last.
- Do NOT describe the HTML source in prose — users don't see it. Describe what the visualization **shows**.
- Requires **iframe Sandbox Allow Same Origin** in Open WebUI Settings → Interface. If disabled, the wrapper shows a notice — and the user won't see the visualization itself, just the notice.
- Any <script> you include runs **once**, **after** the full block has streamed in.

## What's auto-injected

- Theme CSS, SVG classes, color ramps, height reporting, sendPrompt() bridge, and openLink() bridge
- Pre-styled bare-tag form elements (see below) — saves tokens on simple forms
- Consider making diagrams **conversational** with sendPrompt() — see the "sendPrompt bridge" section further below for patterns and examples

### Pre-styled form elements

These tags get theme-aware default styling **when emitted without a class or inline style attribute**.
Other attributes (placeholder, value, id, aria-*, min/max, etc.) are fine — they don't disable the defaults.
Adding class or style is treated as an opt-out: the default is suppressed and you can style it from scratch.
Useful for short forms or quick UIs where the design doesn't need to deviate.

Pre-styled elements included in the tool:

- <button> — themed button. Use it for actions.
- <input type="text|number|email|search|password|tel|url|date|time|datetime-local"> — themed text input. Use it where a user types or picks a value.
- <input type="range"> — slider. Use it for "from–to" picks, intensity dials, or any continuous value where exact precision doesn't matter.
- <input type="checkbox">, <input type="radio"> — multi-pick / single-pick. Self-explanatory.
- <textarea> — multi-line text input.
- <select> — dropdown. Use it when a list of choices is too long for radios.
- <label>, <fieldset>, <legend> — form structure. Group related inputs and label them.
- <kbd> — keyboard-key cap. Use it whenever you mention a shortcut, so the key visually pops as a key.
  - Mac: <kbd>⌘</kbd><kbd>K</kbd>
  - Windows / Linux: <kbd>Ctrl</kbd><kbd>K</kbd>
- <hr> — horizontal divider. Separate sections inside a card or between groups of content.
- <details> / <summary> — collapsible disclosure. Use it for progressive disclosure: hide secondary detail behind a clickable summary so the surface stays clean.
- <blockquote> — pull-quote / callout. Use it to set apart a quote, an aside, or a piece of context the reader should pause on.
- <table> (with <thead> / <tbody> / <th> / <td> / <caption>) — tabular data with multiple columns and rows. Use it when the relationship between rows and columns matters. For numeric columns add align="right" or class="num" to the cells (right-aligns + tabular-nums).
- <mark> — highlighter. Use it sparingly to draw attention to a key word or number inside a sentence.
- <dl> / <dt> / <dd> — definition lists. **Far cheaper than tables for label/value layouts**. Three modes:
  - Bare <dl> → **stacked glossary**. Best when each term needs a sentence or two: definitions, FAQs, term-explained-below.
  - <dl data-layout="grid"> → **two-column card**. The lightweight alternative to a table when you have key/value pairs and don't need row separators or hover: contact cards, metadata blocks, summary panels, settings rows.
  - <dl data-layout="inline"> → **pill row** of label: value pairs (wrap each <dt>/<dd> in a <div>). Best for a tight strip of facts at the top of a card or near a chart: small numbers, status flags, tags. Colon separator is added automatically via CSS.

Bonus on bare elements:

- aria-invalid="true" paints a danger-colored border on input/textarea/select
- :focus-visible keyboard focus draws a clear --accent outline (mouse focus stays subtle)

### Accent color palette

The default accent is **purple**. Switch to one of the other ramps via the data-accent attribute.
The chosen color drives --accent and --accent-foreground, which in turn power focus rings, checkbox/radio fills, and any var(--accent) reference you write yourself.
The same nine names match the chart color ramps, so a teal-accented form sits naturally next to a teal-accented chart.

Available values: purple (default), teal, coral, pink, gray, blue, green, amber, red

**To apply an accent color globally to the whole visualization**: wrap the entire content in a single root <div data-accent="…">.
Every supported element inside inherits the chosen accent.

<div data-accent="teal">
  <style>/* CSS */</style>
  …all focus rings, checkboxes, and var(--accent) consumers go teal…
</div>

**To apply an accent color to a specific section**: set data-accent on any inner container to recolor just its subtree:

<div data-accent="teal">
  <button>Save</button>            <!-- teal focus ring -->
  <input type="checkbox" checked>  <!-- teal accent -->
</div>
<button>Cancel</button>            <!-- still default purple -->

**To apply an accent color to a single element**: set directly on an element to recolor just it:

<button data-accent="green">Approve</button>
<button data-accent="red">Reject</button>

Both light and dark themes are handled — accent values track per-theme ramp stops automatically, and foreground text color flips for legibility in dark mode.
No manual override needed.

Pick an accent that matches the topic: green for finance/positive, red for warnings/critical actions, blue for informational dashboards, amber for attention/caution, etc.
Default to purple for neutral or multi-purpose visualizations.

## Output rules

These rules keep visuals clean, accessible, and consistent with the host UI:

- **Flat design** — no gradients, drop shadows, blur, glow, or noise textures (the host UI is flat; matching it prevents visual jarring)
- **Prefer no emojis**, instead use CSS shapes or SVG paths for icons (emoji render inconsistently across platforms)
- **Sentence case** — all labels and headings
- **Round displayed numbers** — use Math.round, toLocaleString, or Intl.NumberFormat
- **Min font size 11px** — smaller becomes unreadable on most screens
- **Text weights** — 400 regular, 500 for emphasis only
- Keep long-form explanation in the prose response. Use concise labels, captions, legends, helper text, and short annotations inside the visual when they improve comprehension.
- **Build ambitiously when the topic supports it.** Treat each visualization like a small product surface, not a single static graphic. Combine multiple elements: a chart paired with a metric strip, a diagram with collapsible deep-dives, a comparison card with sliders that let the user explore tradeoffs. Use animation, hover, and click interactions where they help the reader notice or explore something — not for decoration. If the user asked for "a chart" and the topic naturally extends into a small dashboard, build the dashboard. Restraint is for cases where extra structure would distract; default to richness, not minimalism.

---

## Design system

### CSS variables (auto-injected — prefer these so light/dark mode just works)

The tool injects theme-aware CSS variables that adapt to light/dark mode automatically. Use them by default for text, surface, and border colors; reach for a specific hex only when the design genuinely calls for a fixed color (a brand mark, a deliberate accent that shouldn't track the theme).

| Token | Purpose |
|-------|---------|
| --color-text-primary | Main text |
| --color-text-secondary | Labels, muted text |
| --color-text-tertiary | Hints, placeholders |
| --color-text-info/success/warning/danger | Semantic text |
| --color-bg-primary | Main background |
| --color-bg-secondary | Cards, surfaces |
| --color-bg-tertiary | Page background |
| --color-border-tertiary | Default borders (0.15 alpha) |
| --color-border-secondary | Hover borders (0.3 alpha) |
| --font-sans | Default font |
| --font-mono | Code font |
| --radius-md / --radius-lg / --radius-xl | 8px / 12px / 16px |

### Color ramps (9 ramps, auto light/dark)

Each ramp provides fill, stroke, and text variants that adapt to the theme automatically via CSS classes.

| Ramp | 50 (light fill) | 200 | 400 | 600 (light stroke) | 800 (light title) |
|------|------|------|------|------|------|
| purple | #EEEDFE | #AFA9EC | #7F77DD | #534AB7 | #3C3489 |
| teal | #E1F5EE | #5DCAA5 | #1D9E75 | #0F6E56 | #085041 |
| coral | #FAECE7 | #F0997B | #D85A30 | #993C1D | #712B13 |
| pink | #FBEAF0 | #ED93B1 | #D4537E | #993556 | #72243E |
| gray | #F1EFE8 | #B4B2A9 | #888780 | #5F5E5A | #444441 |
| blue | #E6F1FB | #85B7EB | #378ADD | #185FA5 | #0C447C |
| green | #EAF3DE | #97C459 | #639922 | #3B6D11 | #27500A |
| amber | #FAEEDA | #EF9F27 | #BA7517 | #854F0B | #633806 |
| red | #FCEBEB | #F09595 | #E24B4A | #A32D2D | #791F1F |

### Chart dataset colors (use 400 stops)

| Series | Color | Hex |
|--------|-------|-----|
| 1 | teal-400 | #1D9E75 |
| 2 | purple-400 | #7F77DD |
| 3 | coral-400 | #D85A30 |
| 4 | blue-400 | #378ADD |
| 5 | amber-400 | #BA7517 |

For area/line fills, use same color at 20% opacity.

---

## SVG setup

If you want to build a beautiful SVG to be rendered inside the chat, follow these rules too:
Always use this SVG boilerplate:

<svg width="100%" viewBox="0 0 680 H">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
      markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke"
        stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </marker>
  </defs>
</svg>

- viewBox width **always 680** — set H to **tightly fit** content (last element bottom + 40px). **Never oversize** — calculate the actual bottom of your last SVG element and add 40px. An SVG with content ending at y=180 must use H=220, not 500
- Safe area: x=40 to x=640
- Background transparent — host provides container

### SVG classes (auto-injected)

Drop these on SVG elements instead of writing inline fill, stroke, or
font-size. They track the theme automatically.

| Class | What it is | When to use |
|-------|------------|-------------|
| .t | 14px primary-color text | Default for any visible label inside a node, axis tick, or callout. |
| .ts | 12px secondary-color text | Subtitles, captions, units (e.g. "users", "ms"), supporting text under a .t label. |
| .th | 14px primary text, 500 weight | Node titles, KPI numbers, anything that needs to read as "the headline" of a small region. |
| .box | Neutral rect — secondary bg, tertiary border | Default container for a labeled region. Use whenever you need a neutral chip / panel and don't have a semantic color. |
| .node | Cursor-pointer + hover opacity on a <g> | Mark a <g> as clickable. Pair with onclick="sendPrompt(...)" so a user can drill into the topic. |
| .arr | 1.5px stroke matching theme borders | Arrow lines and connectors. Combine with marker-end="url(#arrow)". |
| .leader | 0.5px dashed guide line | Pulling a label to a part of an illustration when the label can't sit on top of it. |
| .c-{ramp} | Sets fill/stroke + text colors on a whole <g> from one of the 9 color ramps | Color a node by category — apply .c-teal (etc.) to a <g> and every shape and text inside picks up the matching ramp. Un-classed, un-filled <path>/<polygon> children (pie wedges, areas) take the ramp's series color; on a classed or filled mark, fill="currentColor" opts back in. |

### Sizing text inside boxes

Browsers don't auto-size SVG boxes to text. To pick a width, estimate
the rendered glyph width per character and size the box from the
longest line.

- 14px text (.t, .th) → ~8 px / character
- 12px text (.ts) → ~7 px / character
- box_width = max(title_chars × 8, subtitle_chars × 7) + 24 (12 px padding each side)

### Centering text in boxes

<text> defaults to dominant-baseline="alphabetic" — y is the text's
baseline, not its center, so a label placed at the vertical midpoint of
a box actually sits ~4 px too high. For text inside a node, callout, or
any rounded rect, add dominant-baseline="central" and put y at the
box midpoint.

Keep the default (no dominant-baseline) for text that's *meant* to sit
on a baseline: axis tick labels (resting on the axis line), legend labels
(aligned to the swatch baseline), and anything where the bottom edge of
the glyphs is the visual anchor. Setting central on those will make
them look ~4 px low instead.

---

## Diagram types

### Flowchart — sequential steps, decisions

- Max **4–5 nodes** per diagram — 6+ → decompose into overview + sub-flows
- Box spacing: 60px between boxes, 24px padding inside
- Single-line node: height 44px, two-line: 56px
- Arrows must not cross any box — use L-bends if needed
- Use marker-end="url(#arrow)" on arrow paths

Single-line node:

<g class="node c-teal" onclick="sendPrompt('Tell me about X')">
  <rect x="100" y="20" width="180" height="44" rx="8"/>
  <text class="th" x="190" y="42" text-anchor="middle" dominant-baseline="central">Label</text>
</g>

Two-line node:

<g class="node c-teal">
  <rect x="100" y="20" width="200" height="56" rx="8"/>
  <text class="th" x="200" y="38" text-anchor="middle" dominant-baseline="central">Title</text>
  <text class="ts" x="200" y="56" text-anchor="middle" dominant-baseline="central">Subtitle</text>
</g>

### Architecture — nested regions, layered systems

For diagrams that show **what contains what**: services inside zones,
modules inside layers, components inside subsystems. The nesting itself
is the information — outer regions are the system, inner regions are
the parts.

- Outermost container: rx=20–24, lightest ramp fill (the 50 stop), 0.5px stroke
- Inner regions: rx=8–12, a darker stop of the same ramp — or a different ramp when the inner region is semantically distinct (e.g. external service inside an internal cluster)
- 20px minimum padding between an inner region's bounds and its parent's edge
- Max 2–3 nesting levels — beyond that, decompose into a top-level overview plus sub-diagrams

### Illustrative — explain a mechanism by drawing it

For "how does this actually work" topics where the answer is spatial:
how light refracts through a prism, how a transformer attention head
weighs tokens, how a heat pump moves heat against a gradient. **Draw
the thing itself**, not a labeled diagram about it.

- Shapes are freeform — paths, ellipses, polygons, curves — not just rounded rects
- Color encodes intensity or state, not category: warm ramps for active / hot / energized, cool ramps for calm / cold / passive, gray for neutral / inert
- Labels live outside the object connected via .leader lines — reserve a ~140px gutter on the side you'll label from
- Strongly prefer **interactive** illustrative diagrams: if the real system has a knob, a slider, or a phase, expose it. A prism with a draggable angle slider teaches refraction better than five static frames.

---

## Charts (Chart.js)

Load Chart.js in your HTML fragment:

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>

Setup pattern:

<div style="position: relative; height: 300px;">
  <canvas id="chart"></canvas>
</div>
<script>
const ctx = document.getElementById('chart').getContext('2d');
const s = getComputedStyle(document.documentElement);
const textColor = s.getPropertyValue('--color-text-secondary').trim();
const gridColor = s.getPropertyValue('--color-border-tertiary').trim();

new Chart(ctx, {
  type: 'bar',
  data: {
    labels: ['Q1','Q2','Q3','Q4'],
    datasets: [{ label: 'Revenue', data: [12,19,8,15],
      backgroundColor: '#1D9E75', borderRadius: 4, borderSkipped: false }]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { labels: { color: textColor, font: { size: 12 } } } },
    scales: {
      x: { grid: { display: false }, ticks: { color: textColor, font: { size: 12 } }, border: { color: gridColor } },
      y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 12 } }, border: { display: false } }
    }
  }
});
</script>

**Chart rules:**
- Wrap canvas in container with position: relative and explicit height — without it, maintainAspectRatio: false collapses the canvas to zero
- Always pass responsive: true, maintainAspectRatio: false in options — without maintainAspectRatio: false, Chart.js locks the canvas to a 2:1 aspect and ignores the container height; without responsive: true, it won't redraw when the iframe re-measures. You have to set them explicitly on every new Chart(...) call (Chart.js reads options at construction time, so there's no global default we could pre-set for you).
- Read CSS variables for text/border colors so the chart tracks the theme
- borderRadius: 4 on bars
- Line charts: tension: 0.3 for smooth curves
- Doughnut: cutout: '60%' — never use pie

**Chart type selection:**

| Data shape | Type | Notes |
|-----------|------|-------|
| Categories + values (a few items, comparable magnitudes) | **Bar** | Default for "compare values across labels". Switch to a horizontal bar (indexAxis: 'y') when labels are long, when there are 8+ categories, or when ranking is the point. |
| Time series, anything sampled at regular intervals | **Line** | tension: 0.3 for a natural curve. Stack multiple datasets when you're comparing trends, not when each line wanders independently — overlap gets unreadable past 4 lines. |
| Parts of a whole, ≤5 slices | **Doughnut** | Use cutout: '60%' so the empty middle can hold a total or label. Skip if the segments are very uneven (one slice >70%) — the small slices vanish; show a stacked bar instead. |
| Two continuous variables, looking for correlation | **Scatter** | Add a trend line if the relationship is the takeaway. For dense clouds, drop point opacity to 0.3–0.5 so density reads. |
| Stacked / cumulative composition over time | **Stacked bar / stacked area** | Bar when the buckets are discrete (months, segments); area when the underlying signal is continuous. |
| Single-value vs target / threshold | **Bar with reference line** or KPI card | A whole chart is overkill for one number — consider a metric card with a sparkline instead. |
| Multi-dimensional comparison (3–6 axes) | **Radar** | Only when the axes are genuinely commensurate — otherwise a small-multiples bar grid is clearer. |

### Inline SVG charts (no library)

Reach for inline SVG when the data is small, the shape is simple, or
you want the chart to share design with surrounding diagrams (matching
corner radii, palette, type). No script, no CDN — just shapes and text.
Reach for Chart.js when you need axes, tooltips, hover, animation, or
many series.

**Good fits for inline SVG:**
- **Progress / completion bar** — a value rendered against a fixed track, often paired with a percentage label to its right
- **Ranking strip** — a small number of horizontal bars stacked vertically, each bar a different category color, sized by value
- **Sparkline** — a terse trend line with no axes that sits next to a number to give the number context
- **KPI donut / ring** — a single percentage rendered as a circle arc, with the number in the middle of the ring
- **Stacked composition row** — one horizontal bar split into colored segments to show parts of a whole, when a doughnut would feel heavy
- **Custom-shape charts** — anything where the chart shape is part of the metaphor (a thermometer for temperature, a battery for charge, a fuel gauge, a tide-line)

**Theme consistency for inline SVG:**
- Use the .t / .ts / .th classes on <text> for labels, captions, and headlines.
  They pick up the theme's text colors and typography scale automatically.
  Never set font-size or fill on label text manually unless you need a specific deviation.
- For neutral backgrounds (track behind a progress bar, empty slot in a ring), use fill="var(--color-bg-secondary)" so it blends into the surrounding card.
- For data colors, prefer the chart-dataset 400-stop hexes from the table above — they're calibrated to read on both light and dark backgrounds.
  If you need a *whole group* recolored (rect + label + stroke together), wrap it in a <g class="c-teal"> (or any of the 9 ramp classes) and let the SVG class system handle fill + stroke + text in one shot.
- Keep stroke-widths to 0.5 px for chrome (axis lines, grid) and 1.5 px for data (lines, sparklines) — matches the 0.5 px borders the rest of the host UI uses, so the chart doesn't feel chunkier than its neighbors.
- Add opacity="0.85" on data fills — softens the color slightly so it sits comfortably next to text without overwhelming it.

**Math hints for the less obvious shapes:**
- Donut arc length: circumference = 2 × π × r. To draw v% of the ring, set stroke-dasharray="{v×circumference/100} {circumference}" on the foreground circle, and transform="rotate(-90 cx cy)" so the arc starts at 12 o'clock instead of 3 o'clock.
- Bar widths in a viewBox="0 0 680 …": leave 40 px of margin on each side, giving a 600 px usable plot width.

---

## Component patterns

### Metric cards — KPI strip

<div style="display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px;">
  <div style="background:var(--color-bg-secondary); border:0.5px solid var(--color-border-tertiary);
    border-radius:var(--radius-lg); padding:16px;">
    <div style="font-size:12px; color:var(--color-text-secondary);">Revenue</div>
    <div style="font-size:28px; font-weight:500; color:var(--color-text-primary); margin-top:4px;">$3,870</div>
    <div style="font-size:12px; color:var(--color-text-success); margin-top:2px;">▲ 12.4%</div>
  </div>
  <!-- repeat for other metrics -->
</div>

Pair with a chart below for a compact dashboard. Add a tiny inline-SVG
sparkline under each value if the trend matters.

### Comparison layout — two paths side by side

<div style="display:grid; grid-template-columns:1fr 1fr; gap:16px;">
  <div style="background:var(--color-bg-secondary); border:0.5px solid var(--color-border-tertiary);
    border-radius:var(--radius-lg); padding:18px;">
    <div style="font-size:14px; font-weight:500;">Monolith</div>
    <dl data-layout="grid" style="margin-top:12px;">
      <dt>Deploy unit</dt><dd>1 service</dd>
      <dt>Latency</dt><dd>Low (in-process)</dd>
      <dt>Scaling</dt><dd>Vertical</dd>
    </dl>
  </div>
  <div style="background:var(--color-bg-secondary); border:0.5px solid var(--color-border-tertiary);
    border-radius:var(--radius-lg); padding:18px;">
    <div style="font-size:14px; font-weight:500;">Microservices</div>
    <dl data-layout="grid" style="margin-top:12px;">
      <dt>Deploy unit</dt><dd>N services</dd>
      <dt>Latency</dt><dd>Higher (network)</dd>
      <dt>Scaling</dt><dd>Horizontal per service</dd>
    </dl>
  </div>
</div>

### Interactive explainer — slider drives output

<label style="display:flex; gap:12px; align-items:center;">
  <span style="min-width:80px;">Interest</span>
  <input type="range" id="rate" min="0" max="20" step="0.1" value="5" style="flex:1;">
  <span id="rate-out" style="min-width:48px; font-variant-numeric:tabular-nums;">5.0%</span>
</label>
<div id="result" style="margin-top:12px; font-size:24px; font-weight:500;"></div>

<script>
var rate = document.getElementById('rate');
var out = document.getElementById('rate-out');
var result = document.getElementById('result');
function recalc() {
  var r = parseFloat(rate.value);
  out.textContent = r.toFixed(1) + '%';
  result.textContent = '$' + (10000 * Math.pow(1 + r/100, 10)).toFixed(0);
}
rate.addEventListener('input', recalc);
recalc();
</script>

The pattern generalises: every interactive element binds an input listener, recomputes a value, and writes it to a result node.
Pair with an inline SVG that re-draws on every input change for a "live diagram".

### Tabs — a piece of UI users already know


<div style="display:flex; gap:4px; border-bottom:0.5px solid var(--color-border-tertiary);">
  <button class="tab active" onclick="showTab('a', this)">Overview</button>
  <button class="tab" onclick="showTab('b', this)">Details</button>
  <button class="tab" onclick="showTab('c', this)">Source</button>
</div>
<div id="tab-a" class="tab-panel">…</div>
<div id="tab-b" class="tab-panel" hidden>…</div>
<div id="tab-c" class="tab-panel" hidden>…</div>

<style>
  .tab { background:none; border:none; padding:8px 12px; cursor:pointer;
         border-bottom:2px solid transparent; }
  .tab.active { border-bottom-color: var(--accent); color: var(--color-text-primary); }
  .tab-panel { padding:12px 0; }
</style>

<script>
function showTab(id, btn) {
  document.querySelectorAll('.tab-panel').forEach(p => p.hidden = true);
  document.getElementById('tab-' + id).hidden = false;
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}
</script>

Persist the active tab with saveState/loadState so it survives reloads.

**Charts in inactive tabs render at 0×0.** Plotly, ECharts, and vis-network all measure their container at init time.
If that container is inside a hidden / display:none panel, they paint into a zero-size canvas and stay blank even after the tab becomes visible.
Two workarounds, pick one:

1. **Lazy-init**: only call Plotly.newPlot / echarts.init / new vis.Network the first time its tab is shown (track a tabInit[id] flag in the handler).
2. **Resize on show**: init everything up front (so data is ready), then in showTab call the right resize hook for whichever lib is in that tab.
   Note the API differs per library — c.resize() does not work for all of them:

   // ECharts: instance.resize()
   echartsInstance.resize();
   // Plotly: pass the container element, no .resize() on the chart
   Plotly.Plots.resize(document.getElementById('plotly-container'));
   // vis-network: redraw + fit — the instance has no .resize()
   networkInstance.redraw();
   networkInstance.fit();
   // Chart.js: instance.resize() — but Chart.js auto-resizes on
   // container size change so usually nothing needed.

   Skip the resize call for D3 / Vega-Lite / inline SVG — they paint declaratively into the SVG namespace and aren't bothered by hidden parents.

### Step-through walkthrough — guided narrative
A "Next ▶" button advances through a sequence of stages, each with its own caption and (optionally) a different highlighted region of the same diagram.
Useful for explaining algorithms, processes, or any topic where the order matters more than the totals.


<div id="stage" style="font-size:14px;">Click Next to begin.</div>
<button onclick="step()">Next ▶</button>

<script>
var steps = [
  'Step 1: request lands at the load balancer',
  'Step 2: routed to a healthy backend',
  'Step 3: backend writes to primary DB',
  'Step 4: replica catches up async',
];
var i = 0;
function step() {
  document.getElementById('stage').textContent = steps[i % steps.length];
  i++;
}
</script>

---

## sendPrompt bridge — conversational diagrams

sendPrompt(text) is the function that makes visualizations conversational. When called, it injects the given text into the chat input field and submits it — exactly as if the user had typed and sent it themselves. The model then receives that message and responds normally, creating a feedback loop between the visual and the conversation.

This is what separates a static diagram from an **exploration interface**. A user sees a system architecture diagram, clicks on the "Load Balancer" node, and the model receives "Tell me more about the load balancer — how does it distribute traffic across the backend services?" as a user message. The model then responds with details, and could even generate a *new* sub-diagram showing the load balancer internals. The user never had to type anything — they just clicked.

### Why this matters

Without sendPrompt, interactive elements inside the iframe are isolated — they can toggle visibility, animate, or filter data, but they can never talk back to the model. The user sees a cool diagram but has to manually type follow-up questions. With sendPrompt, every clickable element becomes a conversation starter. The diagram itself becomes a navigation interface for the topic.

### Writing good sendPrompt text

The text you pass to sendPrompt becomes the user's message to the model. Write it as a natural follow-up question — conversational, specific, and referencing the context of the diagram:

**Good prompt text** (specific, contextual, references the diagram):
- "Explain the attention mechanism — how does it decide which tokens to focus on?"
- "Break down the CI/CD pipeline stage. What tools are typically used here?"
- "Show me a more detailed diagram of the data processing layer"
- "What happens when the load balancer detects a failed backend node?"
- "Compare the pros and cons of the monolith vs microservices approach shown here"

### Usage patterns

Simple patterns — single-click sendPrompt on a node or button:
- **Drill-down**: onclick="sendPrompt('Explain the API gateway — what does it handle?')" on a diagram node
- **Quiz answer**: onclick="sendPrompt('I chose B: O(n log n). Am I right? Explain why.')" on answer buttons
- **Guided exploration**: onclick="sendPrompt('Show me a more advanced example with edge cases.')" on a "Go deeper →" button
- **Comparison**: onclick="sendPrompt('Compare REST vs GraphQL — when should I use each?')" on one of two nodes

**Form / preference collector** — gather multiple user selections, then send them all at once. Use local JS to track choices (button highlights, state object) and a submit button that composes a sendPrompt from the collected answers:

<script>
var choices = {};
function pick(category, value, btn) {
  choices[category] = value;
  // Highlight selected button, dim siblings
  btn.parentElement.querySelectorAll('button').forEach(function(b) {
    b.classList.toggle('active', b === btn);
  });
}
function submitChoices() {
  var parts = [];
  for (var k in choices) parts.push(k + ': ' + choices[k]);
  sendPrompt('Here are my preferences:\n' + parts.join('\n') + '\nGive me a personalized recommendation based on these choices.');
}
</script>

<h3>What's your style?</h3>
<p style="margin:8px 0 4px;">Pace</p>
<button onclick="pick('pace','relaxed',this)">Relaxed</button>
<button onclick="pick('pace','moderate',this)">Moderate</button>
<button onclick="pick('pace','intensive',this)">Intensive</button>

<p style="margin:8px 0 4px;">Focus</p>
<button onclick="pick('focus','culture',this)">Culture</button>
<button onclick="pick('focus','nature',this)">Nature</button>
<button onclick="pick('focus','food',this)">Food</button>

<button onclick="submitChoices()" style="margin-top:12px; font-weight:500;">Get my recommendation →</button>

This pattern is powerful because the model receives a structured summary of all user preferences in one message. Use local JS for the selection UI (instant feedback), then sendPrompt only on final submit.

### When to use sendPrompt vs local JS:
| User action | Use | Why |
|------------|-----|-----|
| Learn more about a component | sendPrompt | Model gives a contextual explanation |
| Explore a stage / drill down | sendPrompt | Model can generate a sub-diagram |
| Submit answers or preferences | sendPrompt | Model evaluates or personalizes |
| Toggle views, adjust sliders | Local JS | Instant feedback, no reasoning needed |
| Filter/sort data | Local JS | Instant response, no model needed |

---

## Interactivity by default

Build dashboards, charts, graphs, interactive functions, animated sections, moving objects, expandable detail sections, cards, copyable text elements and more. If the topic allows and it makes sense for the topic, build complex and visually stunning elements.

Visualizations should feel alive and polished — not static images dumped into chat. Build interfaces that invite interaction:

- **Expandable sections** — use collapsible <details> elements or JS-toggled sections so users can explore at their own pace without overwhelming them upfront
- **Hover effects** — nodes, buttons, and cards should respond to hover (the .node class adds this for SVG elements; for HTML, use :hover styles)
- **Smooth transitions** — add transition: all 0.2s ease to interactive elements for a polished feel
- **Active states** — when a user selects an option or clicks a tab, make the selection visually clear with the .active class or distinct styling
- **Progressive disclosure** — show a clean overview first, let the user click to reveal detail (tabs, accordions, or sendPrompt for model-powered drill-down)

**The goal is to build something that feels like a real app component embedded in chat with reactivity, sections and extra elements** — not a screenshot. If the visualization has multiple facets, give the user controls to explore them. If it has hierarchical information, let them expand and collapse. If it has data, let them sort or filter.

---

## openLink bridge — opening URLs from visualizations

openLink(url) opens a URL in a new browser tab from within the visualization iframe. Normal <a href="..."> links inside an iframe can behave unpredictably (opening inside the iframe, being blocked by sandbox restrictions, etc.). This function handles that by opening the link in the parent window instead.

<button onclick="openLink('https://docs.example.com/api-reference')">
  Open API docs ↗
</button>

Or in SVG:

<g class="node c-blue" onclick="openLink('https://github.com/org/repo')">
  <rect x="100" y="20" width="200" height="44" rx="8"/>
  <text class="th" x="200" y="42" text-anchor="middle" dominant-baseline="central">View source ↗</text>
</g>

Use openLink for external references, documentation links, or source code links. Unlike sendPrompt, this navigates away from the chat — use it when the user needs to access an external resource, not when they need the model to explain something.

---

## copyText + toast bridges — feedback on user actions

copyText(text) copies text to the system clipboard and automatically shows a localized "Copied" toast in the top-right corner of the iframe. Works from HTTPS and HTTP origins (falls back to execCommand('copy') if the async Clipboard API is blocked). Use this on "Copy" buttons inside interactive visualizations — data tables, code snippets, shareable values.

<button onclick="copyText(JSON.stringify(data, null, 2))">Copy JSON</button>

toast(message, kind) shows a small auto-dismissing banner inside the iframe. kind is optional and controls the text color: 'success' (green, default), 'info' (blue), 'warn' (amber), 'error' (red). Use it for status notifications inside long-running interactive tools — "Calculation done", "Invalid input", etc.

<button onclick="recompute(); toast('Recomputed', 'info')">Recompute</button>

Toasts auto-dismiss after ~2.2 s and stack vertically if fired in quick succession.

---

## saveState + loadState bridges — persistent interactive state

saveState(key, value) and loadState(key, fallback) proxy parent.localStorage with a key prefix scoped to **this assistant message**. State survives page reloads and tab switches, but two different chats (or different messages in the same chat) each get their own independent state — no cross-contamination.

<script>
  // Restore toggle state on load
  var showRaw = loadState('showRaw', false);
  document.getElementById('raw-toggle').checked = showRaw;
  applyView(showRaw);

  function onToggleChange(el) {
    saveState('showRaw', el.checked);
    applyView(el.checked);
  }
</script>

Use it for: selected tabs, picked chart range, hidden/shown layers, theme overrides, collapsed sections — anything the user would expect to be remembered when they re-open the chat.

Values are JSON-serialized. If localStorage is blocked (private browsing, sandboxed), both functions silently no-op and loadState returns fallback.

---

## CDN libraries

Strict-mode CSP allowlists three CDN hosts. Anything served from them
loads — no plugin tweaking needed, even in strict security mode.

Allowed hosts:
- cdnjs.cloudflare.com — widest coverage
- cdn.jsdelivr.net — npm / GitHub backed, supports minor-version pinning
- unpkg.com — npm mirror

Common picks:

| Library | Why reach for it | Example loader |
|---------|------------------|----------------|
| **Chart.js** | Bar / line / doughnut / scatter with animation out of the box | <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script> |
| **D3.js** | Custom data-driven SVG (force graphs, arcs, maps, non-standard charts) | <script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script> |
| **Vega-Lite** | Declarative grammar of graphics — feed it a JSON spec, it draws the chart | <script src="https://cdn.jsdelivr.net/npm/vega@5"></script><script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script><script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script> |
| **ECharts** | Rich interactive dashboards, advanced chart types | <script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.0/echarts.min.js"></script> |
| **Plotly** | Scientific / 3D plots, statistical charts | <script src="https://cdn.jsdelivr.net/npm/plotly.js-dist@2"></script> |
| **vis-network** | Force-directed network / node-link graphs | <script src="https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script> (the **standalone** UMD bundle — exposes vis.Network *and* vis.DataSet. The bare vis-network.min.js on cdnjs is the *peer* build and requires vis-data loaded separately, otherwise new vis.DataSet(...) throws vis is not defined.) |
| **Tone.js / Wavesurfer** | Audio synthesis, waveform visualisation | <script src="https://cdnjs.cloudflare.com/ajax/libs/tone/15.0.4/Tone.js"></script> |

Anything else on those three CDNs is fair game — apexcharts, d3-force,
konva, flatpickr, etc. Pick whatever fits the topic.

---

## Library init

Two patterns to follow when using a CDN library:

### 1 · Wrap a Chart.js canvas in a fixed-height container

maintainAspectRatio: false makes Chart.js use the container's height.
If the canvas has no intrinsic height (e.g. inside a flex column without a height set), it collapses to zero and nothing draws:

<div style="position: relative; height: 260px;">
  <canvas id="chart"></canvas>
</div>
<script>
  new Chart(document.getElementById('chart').getContext('2d'), {
    type: 'bar',
    data: { /* … */ },
    options: { responsive: true, maintainAspectRatio: false, /* … */ }
  });
</script>

### 2 · Source order matters

Put external <script src="…"> tags **before** the inline <script> that
uses them. They execute in order, so a consumer that runs before its
library is loaded will fail with Chart is not defined.

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script>/* uses Chart and d3 */</script>
