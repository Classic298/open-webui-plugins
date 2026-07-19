"""
title: Inline Visualizer
author: Classic298
author_url: https://github.com/Classic298
funding_url: https://github.com/Classic298
version: 2.2.0
required_open_webui_version: 0.10.2
description: Renders interactive HTML/SVG visualizations inline in chat. Requires "iframe Sandbox Allow Same Origin" to be enabled in Open WebUI Settings -> Interface. For design instructions, the model should call view_skill("visualize").
"""

import re
from typing import Literal

# Build marker embedded into the rendered iframe so the running
# version can be verified at runtime (search DevTools for
# `data-iv-build` on <html>).  Bump on every protocol-level change
# so stale cached iframes can be spotted immediately.
_IV_BUILD = "2.2.0"

from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Injected CSS — Theme variables (light default, dark via data-theme)
# ---------------------------------------------------------------------------

THEME_CSS = """
:root {
  --color-text-primary: #1F2937;
  --color-text-secondary: #6B7280;
  --color-text-tertiary: #9CA3AF;
  --color-text-info: #2563EB;
  --color-text-success: #059669;
  --color-text-warning: #D97706;
  --color-text-danger: #DC2626;
  --color-bg-primary: #FFFFFF;
  --color-bg-secondary: #F9FAFB;
  --color-bg-tertiary: #F3F4F6;
  --color-border-tertiary: rgba(0,0,0,0.15);
  --color-border-secondary: rgba(0,0,0,0.3);
  --color-border-primary: rgba(0,0,0,0.4);
  --font-sans: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'SF Mono', Menlo, Consolas, monospace;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  /* --- Color ramp variables (light) --- */
  --ramp-purple-fill:#EEEDFE; --ramp-purple-stroke:#534AB7; --ramp-purple-th:#3C3489; --ramp-purple-ts:#534AB7;
  --ramp-teal-fill:#E1F5EE;   --ramp-teal-stroke:#0F6E56;   --ramp-teal-th:#085041;   --ramp-teal-ts:#0F6E56;
  --ramp-coral-fill:#FAECE7;  --ramp-coral-stroke:#993C1D;  --ramp-coral-th:#712B13;  --ramp-coral-ts:#993C1D;
  --ramp-pink-fill:#FBEAF0;   --ramp-pink-stroke:#993556;   --ramp-pink-th:#72243E;   --ramp-pink-ts:#993556;
  --ramp-gray-fill:#F1EFE8;   --ramp-gray-stroke:#5F5E5A;   --ramp-gray-th:#444441;   --ramp-gray-ts:#5F5E5A;
  --ramp-blue-fill:#E6F1FB;   --ramp-blue-stroke:#185FA5;   --ramp-blue-th:#0C447C;   --ramp-blue-ts:#185FA5;
  --ramp-green-fill:#EAF3DE;  --ramp-green-stroke:#3B6D11;  --ramp-green-th:#27500A;  --ramp-green-ts:#3B6D11;
  --ramp-amber-fill:#FAEEDA;  --ramp-amber-stroke:#854F0B;  --ramp-amber-th:#633806;  --ramp-amber-ts:#854F0B;
  --ramp-red-fill:#FCEBEB;    --ramp-red-stroke:#A32D2D;    --ramp-red-th:#791F1F;    --ramp-red-ts:#A32D2D;
  /* --- Common aliases (catch hallucinated variable names) --- */
  /* Text */
  --fg: var(--color-text-primary);
  --text: var(--color-text-primary);
  --foreground: var(--color-text-primary);
  --text-primary: var(--color-text-primary);
  --text-color: var(--color-text-primary);
  --color-text: var(--color-text-primary);
  --color-foreground: var(--color-text-primary);
  --body-color: var(--color-text-primary);
  --muted: var(--color-text-secondary);
  --muted-foreground: var(--color-text-secondary);
  --text-muted: var(--color-text-secondary);
  --text-secondary: var(--color-text-secondary);
  --secondary: var(--color-text-secondary);
  --subtle: var(--color-text-tertiary);
  --text-tertiary: var(--color-text-tertiary);
  /* Backgrounds */
  --bg: var(--color-bg-primary);
  --background: var(--color-bg-primary);
  --bg-primary: var(--color-bg-primary);
  --body-bg: var(--color-bg-primary);
  --color-bg: var(--color-bg-primary);
  --surface: var(--color-bg-secondary);
  --surface-1: var(--color-bg-secondary);
  --surface-2: var(--color-bg-tertiary);
  --card: var(--color-bg-secondary);
  --card-bg: var(--color-bg-secondary);
  --card-foreground: var(--color-text-primary);
  --card-background: var(--color-bg-secondary);
  --popover: var(--color-bg-secondary);
  --popover-foreground: var(--color-text-primary);
  --hover: rgba(0,0,0,0.04);
  /* Borders */
  --border: var(--color-border-tertiary);
  --border-color: var(--color-border-tertiary);
  --divider: var(--color-border-tertiary);
  --separator: var(--color-border-tertiary);
  --input: var(--color-border-tertiary);
  --ring: var(--color-border-secondary);
  /* Accent / Primary (AI uses --accent as brand color, not surface) */
  --primary: #6c2eb9;
  --primary-foreground: #ffffff;
  --accent: #6c2eb9;
  --accent-foreground: #ffffff;
  /* Themed select chevron (light) — used by the pre-styled <select> */
  --select-arrow: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path d='M3 4.5l3 3 3-3' fill='none' stroke='%236B7280' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>");
}
:root[data-theme="dark"] {
  --color-text-primary: #E5E7EB;
  --color-text-secondary: #9CA3AF;
  --color-text-tertiary: #6B7280;
  --color-text-info: #60A5FA;
  --color-text-success: #34D399;
  --color-text-warning: #FBBF24;
  --color-text-danger: #F87171;
  --color-bg-primary: #1A1A1A;
  --color-bg-secondary: #262626;
  --color-bg-tertiary: #111111;
  --color-border-tertiary: rgba(255,255,255,0.15);
  --color-border-secondary: rgba(255,255,255,0.3);
  --color-border-primary: rgba(255,255,255,0.4);
  --ramp-purple-fill:#3C3489; --ramp-purple-stroke:#AFA9EC; --ramp-purple-th:#CECBF6; --ramp-purple-ts:#AFA9EC;
  --ramp-teal-fill:#085041;   --ramp-teal-stroke:#5DCAA5;   --ramp-teal-th:#9FE1CB;   --ramp-teal-ts:#5DCAA5;
  --ramp-coral-fill:#712B13;  --ramp-coral-stroke:#F0997B;  --ramp-coral-th:#F5C4B3;  --ramp-coral-ts:#F0997B;
  --ramp-pink-fill:#72243E;   --ramp-pink-stroke:#ED93B1;   --ramp-pink-th:#F4C0D1;   --ramp-pink-ts:#ED93B1;
  --ramp-gray-fill:#444441;   --ramp-gray-stroke:#B4B2A9;   --ramp-gray-th:#D3D1C7;   --ramp-gray-ts:#B4B2A9;
  --ramp-blue-fill:#0C447C;   --ramp-blue-stroke:#85B7EB;   --ramp-blue-th:#B5D4F4;   --ramp-blue-ts:#85B7EB;
  --ramp-green-fill:#27500A;  --ramp-green-stroke:#97C459;  --ramp-green-th:#C0DD97;  --ramp-green-ts:#97C459;
  --ramp-amber-fill:#633806;  --ramp-amber-stroke:#EF9F27;  --ramp-amber-th:#FAC775;  --ramp-amber-ts:#EF9F27;
  --ramp-red-fill:#791F1F;    --ramp-red-stroke:#F09595;    --ramp-red-th:#F7C1C1;    --ramp-red-ts:#F09595;
  /* --- Common aliases (dark overrides) --- */
  --text: var(--color-text-primary);
  --foreground: var(--color-text-primary);
  --text-primary: var(--color-text-primary);
  --text-color: var(--color-text-primary);
  --color-text: var(--color-text-primary);
  --body-color: var(--color-text-primary);
  --muted: var(--color-text-secondary);
  --muted-foreground: var(--color-text-secondary);
  --text-muted: var(--color-text-secondary);
  --text-secondary: var(--color-text-secondary);
  --secondary: var(--color-text-secondary);
  --subtle: var(--color-text-tertiary);
  --text-tertiary: var(--color-text-tertiary);
  --bg: var(--color-bg-primary);
  --background: var(--color-bg-primary);
  --bg-primary: var(--color-bg-primary);
  --body-bg: var(--color-bg-primary);
  --color-bg: var(--color-bg-primary);
  --surface: var(--color-bg-secondary);
  --surface-1: var(--color-bg-secondary);
  --surface-2: var(--color-bg-tertiary);
  --card: var(--color-bg-secondary);
  --card-bg: var(--color-bg-secondary);
  --card-foreground: var(--color-text-primary);
  --card-background: var(--color-bg-secondary);
  --popover: var(--color-bg-secondary);
  --popover-foreground: var(--color-text-primary);
  --hover: rgba(255,255,255,0.06);
  --border: var(--color-border-tertiary);
  --border-color: var(--color-border-tertiary);
  --divider: var(--color-border-tertiary);
  --separator: var(--color-border-tertiary);
  --input: var(--color-border-tertiary);
  --ring: var(--color-border-secondary);
  --primary: #a78bfa;
  --primary-foreground: #1A1A1A;
  --accent: #a78bfa;
  --accent-foreground: #ffffff;
  --select-arrow: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path d='M3 4.5l3 3 3-3' fill='none' stroke='%239CA3AF' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>");
}

/* --- Named accent palette ---
 * Apply data-accent="<name>" on <html> for global, on any element
 * for local override. The variants reuse the existing color-ramp
 * stroke colors so charts and forms share visual vocabulary
 * (teal here = teal in a chart). Each variant works in both
 * light and dark themes — --accent picks up the ramp's per-theme
 * stroke automatically; --accent-foreground flips dark in dark
 * mode so text stays legible on pastel accents.
 */
[data-accent="purple"] { --accent: var(--ramp-purple-stroke); --accent-foreground: #ffffff; }
[data-accent="teal"]   { --accent: var(--ramp-teal-stroke);   --accent-foreground: #ffffff; }
[data-accent="coral"]  { --accent: var(--ramp-coral-stroke);  --accent-foreground: #ffffff; }
[data-accent="pink"]   { --accent: var(--ramp-pink-stroke);   --accent-foreground: #ffffff; }
[data-accent="gray"]   { --accent: var(--ramp-gray-stroke);   --accent-foreground: #ffffff; }
[data-accent="blue"]   { --accent: var(--ramp-blue-stroke);   --accent-foreground: #ffffff; }
[data-accent="green"]  { --accent: var(--ramp-green-stroke);  --accent-foreground: #ffffff; }
[data-accent="amber"]  { --accent: var(--ramp-amber-stroke);  --accent-foreground: #ffffff; }
[data-accent="red"]    { --accent: var(--ramp-red-stroke);    --accent-foreground: #ffffff; }

[data-theme="dark"] [data-accent],
[data-theme="dark"][data-accent] {
  --accent-foreground: #1A1A1A;
}
"""

# ---------------------------------------------------------------------------
# Injected CSS — SVG utility classes + color ramp selectors
# ---------------------------------------------------------------------------

SVG_CLASSES = """
/* --- Text --- */
.t  { font: 400 14px/1.4 var(--font-sans); fill: var(--color-text-primary); }
.ts { font: 400 12px/1.4 var(--font-sans); fill: var(--color-text-secondary); }
.th { font: 500 14px/1.4 var(--font-sans); fill: var(--color-text-primary); }

/* --- Shapes --- */
.box    { fill: var(--color-bg-secondary); stroke: var(--color-border-tertiary); stroke-width: 0.5; }
.node   { cursor: pointer; }
.node:hover { opacity: 0.85; }
.arr    { stroke: var(--color-border-secondary); stroke-width: 1.5; fill: none; }
.leader { stroke: var(--color-text-tertiary); stroke-width: 0.5; stroke-dasharray: 3 2; fill: none; }

/* --- Color ramp selectors (fill/stroke adapt via CSS vars) --- */
.c-purple>rect,.c-purple>circle,.c-purple>ellipse{fill:var(--ramp-purple-fill);stroke:var(--ramp-purple-stroke);stroke-width:.5}
.c-purple>.th{fill:var(--ramp-purple-th)!important} .c-purple>.ts{fill:var(--ramp-purple-ts)!important}
.c-teal>rect,.c-teal>circle,.c-teal>ellipse{fill:var(--ramp-teal-fill);stroke:var(--ramp-teal-stroke);stroke-width:.5}
.c-teal>.th{fill:var(--ramp-teal-th)!important} .c-teal>.ts{fill:var(--ramp-teal-ts)!important}
.c-coral>rect,.c-coral>circle,.c-coral>ellipse{fill:var(--ramp-coral-fill);stroke:var(--ramp-coral-stroke);stroke-width:.5}
.c-coral>.th{fill:var(--ramp-coral-th)!important} .c-coral>.ts{fill:var(--ramp-coral-ts)!important}
.c-pink>rect,.c-pink>circle,.c-pink>ellipse{fill:var(--ramp-pink-fill);stroke:var(--ramp-pink-stroke);stroke-width:.5}
.c-pink>.th{fill:var(--ramp-pink-th)!important} .c-pink>.ts{fill:var(--ramp-pink-ts)!important}
.c-gray>rect,.c-gray>circle,.c-gray>ellipse{fill:var(--ramp-gray-fill);stroke:var(--ramp-gray-stroke);stroke-width:.5}
.c-gray>.th{fill:var(--ramp-gray-th)!important} .c-gray>.ts{fill:var(--ramp-gray-ts)!important}
.c-blue>rect,.c-blue>circle,.c-blue>ellipse{fill:var(--ramp-blue-fill);stroke:var(--ramp-blue-stroke);stroke-width:.5}
.c-blue>.th{fill:var(--ramp-blue-th)!important} .c-blue>.ts{fill:var(--ramp-blue-ts)!important}
.c-green>rect,.c-green>circle,.c-green>ellipse{fill:var(--ramp-green-fill);stroke:var(--ramp-green-stroke);stroke-width:.5}
.c-green>.th{fill:var(--ramp-green-th)!important} .c-green>.ts{fill:var(--ramp-green-ts)!important}
.c-amber>rect,.c-amber>circle,.c-amber>ellipse{fill:var(--ramp-amber-fill);stroke:var(--ramp-amber-stroke);stroke-width:.5}
.c-amber>.th{fill:var(--ramp-amber-th)!important} .c-amber>.ts{fill:var(--ramp-amber-ts)!important}
.c-red>rect,.c-red>circle,.c-red>ellipse{fill:var(--ramp-red-fill);stroke:var(--ramp-red-stroke);stroke-width:.5}
.c-red>.th{fill:var(--ramp-red-th)!important} .c-red>.ts{fill:var(--ramp-red-ts)!important}
"""

# ---------------------------------------------------------------------------
# Injected CSS — Base resets & interactive element styles
# ---------------------------------------------------------------------------

BASE_STYLES = """
* { box-sizing: border-box; margin: 0; font-family: var(--font-sans); }
html, body { overflow: hidden; }
body { background: transparent; color: var(--color-text-primary); line-height: 1.5; padding: 8px; }
svg { overflow: visible; }
svg text { fill: var(--color-text-primary); }
h1 { font-size: 22px; font-weight: 500; color: var(--color-text-primary); margin-bottom: 12px; }
h2 { font-size: 18px; font-weight: 500; color: var(--color-text-primary); margin-bottom: 8px; }
h3 { font-size: 16px; font-weight: 500; color: var(--color-text-primary); margin-bottom: 6px; }
p  { font-size: 14px; color: var(--color-text-secondary); margin-bottom: 8px; }
/* --- Pre-styled form elements ---
 * Each rule is gated with :not([class]):not([style]) so the model
 * opts in by emitting bare HTML. Adding either attribute is treated
 * as opting out — the default suppresses and the model styles from
 * scratch. Keeps token cost low for vanilla cases without locking
 * the design space.
 */
button:not([class]):not([style]) {
  background: transparent; border: 0.5px solid var(--color-border-secondary);
  border-radius: var(--radius-md); padding: 6px 14px; font-size: 13px;
  color: var(--color-text-primary); cursor: pointer; font-family: var(--font-sans);
}
button:not([class]):not([style]):hover { background: var(--color-bg-secondary); }

input[type="text"]:not([class]):not([style]),
input[type="number"]:not([class]):not([style]),
input[type="email"]:not([class]):not([style]),
input[type="search"]:not([class]):not([style]),
input[type="password"]:not([class]):not([style]),
input[type="tel"]:not([class]):not([style]),
input[type="url"]:not([class]):not([style]),
input[type="date"]:not([class]):not([style]),
input[type="time"]:not([class]):not([style]),
input[type="datetime-local"]:not([class]):not([style]) {
  background: var(--color-bg-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: var(--radius-md); padding: 6px 10px; font-size: 13px;
  color: var(--color-text-primary); font-family: var(--font-sans);
  outline: none; transition: border-color 0.15s ease;
}
input[type="text"]:not([class]):not([style]):focus,
input[type="number"]:not([class]):not([style]):focus,
input[type="email"]:not([class]):not([style]):focus,
input[type="search"]:not([class]):not([style]):focus,
input[type="password"]:not([class]):not([style]):focus,
input[type="tel"]:not([class]):not([style]):focus,
input[type="url"]:not([class]):not([style]):focus,
input[type="date"]:not([class]):not([style]):focus,
input[type="time"]:not([class]):not([style]):focus,
input[type="datetime-local"]:not([class]):not([style]):focus {
  border-color: var(--color-border-primary);
}

/* Drop the type=number spinner — clashes with the field's borders. */
input[type="number"]:not([class]):not([style]) {
  -moz-appearance: textfield; appearance: textfield;
}
input[type="number"]:not([class]):not([style])::-webkit-outer-spin-button,
input[type="number"]:not([class]):not([style])::-webkit-inner-spin-button {
  -webkit-appearance: none; margin: 0;
}

textarea:not([class]) {
  background: var(--color-bg-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: var(--radius-md); padding: 8px 10px; font-size: 13px;
  color: var(--color-text-primary); font-family: var(--font-sans);
  outline: none; resize: vertical; min-height: 60px;
  transition: border-color 0.15s ease;
}
textarea:not([class]):focus { border-color: var(--color-border-primary); }

/* accent-color always applies, regardless of class/style — it's a
 * tint property the model is highly unlikely to set themselves, and
 * letting it ride keeps palette switches consistent even when the
 * model adds inline width/max-width styling to the slider. */
input[type="range"], input[type="checkbox"], input[type="radio"] {
  accent-color: var(--accent);
}
input[type="range"]:not([class]):not([style]) { width: 100%; }

input[type="checkbox"]:not([class]):not([style]),
input[type="radio"]:not([class]):not([style]) {
  /* accent-color comes from the always-on rule above. */
  cursor: pointer;
}

select:not([class]):not([style]) {
  appearance: none; -webkit-appearance: none; -moz-appearance: none;
  background-color: var(--color-bg-secondary);
  background-image: var(--select-arrow);
  background-repeat: no-repeat;
  background-position: right 10px center;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: var(--radius-md); padding: 6px 28px 6px 10px;
  font-size: 13px; color: var(--color-text-primary); font-family: var(--font-sans);
  outline: none; cursor: pointer;
}
select:not([class]):not([style]):focus { border-color: var(--color-border-primary); }

label:not([class]):not([style]) {
  font-size: 13px; color: var(--color-text-primary); cursor: pointer;
}
fieldset:not([class]):not([style]) {
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: var(--radius-md); padding: 12px;
}
legend:not([class]):not([style]) {
  font-size: 12px; color: var(--color-text-secondary); padding: 0 6px;
}

/* Validation error border — standard a11y attribute, no class needed. */
input[aria-invalid="true"]:not([class]):not([style]),
textarea[aria-invalid="true"]:not([class]),
select[aria-invalid="true"]:not([class]):not([style]) {
  border-color: var(--color-text-danger);
}

/* Keyboard-only focus rings (accent outline). Mouse focus stays subtle. */
button:not([class]):not([style]):focus-visible,
input:not([class]):not([style]):focus-visible,
textarea:not([class]):focus-visible,
select:not([class]):not([style]):focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

code {
  font-family: var(--font-mono); font-size: 13px; background: var(--color-bg-tertiary);
  padding: 2px 6px; border-radius: 4px;
}

/* <kbd> — keyboard-key pill (cmd/ctrl/k style). */
kbd:not([class]):not([style]) {
  font-family: var(--font-mono); font-size: 12px;
  background: var(--color-bg-secondary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 4px; padding: 1px 6px;
  color: var(--color-text-primary);
}

/* <hr> — flat divider matching the rest of the borders. */
hr:not([class]):not([style]) {
  border: none;
  border-top: 0.5px solid var(--color-border-tertiary);
  margin: 1.5rem 0;
}

/* <details> / <summary> — themed disclosure with a bigger chevron.
 * Container is an invisible rounded "wrapper" — the visible card-
 * shape is the summary header itself. This way if a model adds its
 * own summary background/border, the result is still single-card,
 * not nested. Chevron is sized to be clearly visible. */
details:not([class]):not([style]) {
  margin: 12px 0;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: var(--radius-md);
  overflow: hidden;
}
details:not([class]):not([style]) > summary {
  cursor: pointer; list-style: none; user-select: none;
  font-weight: 500; color: var(--color-text-primary);
  background: var(--color-bg-secondary);
  padding: 10px 14px 10px 34px;
  position: relative;
  transition: background-color 0.15s ease;
}
details:not([class]):not([style]) > summary:hover {
  background: var(--color-bg-tertiary);
}
details:not([class]):not([style]) > summary::-webkit-details-marker { display: none; }
details:not([class]):not([style]) > summary::marker { content: ''; }
details:not([class]):not([style]) > summary::before {
  content: '\\25B8'; /* ▸ */
  position: absolute; left: 12px; top: 50%;
  transform: translateY(-50%);
  transition: transform 0.15s ease;
  color: var(--color-text-secondary);
  font-size: 18px;
  line-height: 1;
}
details[open]:not([class]):not([style]) > summary::before {
  transform: translateY(-50%) rotate(90deg);
}
details[open]:not([class]):not([style]) > summary {
  border-bottom: 0.5px solid var(--color-border-tertiary);
}
/* Margin (not padding) so children with their own bg inset properly. */
details:not([class]):not([style]) > *:not(summary) {
  margin: 12px 14px;
}

blockquote:not([class]):not([style]) {
  border-left: 4px solid var(--accent);
  background: var(--color-bg-secondary);
  padding: 12px 18px;
  margin: 16px 0;
  color: var(--color-text-secondary);
  border-radius: var(--radius-md);
}
blockquote:not([class]):not([style]) > :last-child { margin-bottom: 0; }
blockquote:not([class]):not([style]) > :first-child { margin-top: 0; }

/* <table> — flat data table, theme-matched borders, header pill,
 * row hover, last-row borderless, no zebra (kept calm). For numeric
 * columns, add align="right" or class="num" to <th>/<td>. */
table:not([class]):not([style]) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
  color: var(--color-text-primary);
  font-family: var(--font-sans);
}
table:not([class]):not([style]) caption {
  text-align: left;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
  padding: 0 0 8px;
  caption-side: top;
}
table:not([class]):not([style]) th {
  text-align: left;
  padding: 8px 12px;
  /* Reset all sides so a model's `border:` shorthand can't leak through. */
  border: none;
  border-bottom: 0.5px solid var(--color-border-secondary);
  font-weight: 500;
  font-size: 11px;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: var(--color-bg-secondary);
  white-space: nowrap;
}
table:not([class]):not([style]) td {
  padding: 10px 12px;
  border: none;
  border-bottom: 0.5px solid var(--color-border-tertiary);
  vertical-align: top;
}
table:not([class]):not([style]) tr:last-child > td {
  border-bottom: none;
}
table:not([class]):not([style]) tbody tr {
  transition: background-color 0.1s ease;
}
table:not([class]):not([style]) tbody tr:hover {
  background: var(--color-bg-secondary);
}
/* Numeric columns: opt-in via align="right" or class="num" on cells. */
table:not([class]):not([style]) td[align="right"],
table:not([class]):not([style]) th[align="right"],
table:not([class]):not([style]) td.num,
table:not([class]):not([style]) th.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

mark:not([class]):not([style]) {
  background: var(--ramp-amber-fill);
  color: var(--ramp-amber-th);
  padding: 0 4px;
  border-radius: 3px;
}

/* <dl> three modes — default stacked, data-layout="grid", data-layout="inline".
 * data-layout is the explicit opt-in, so [data-layout] rules skip the class/style gate. */
dl:not([class]):not([style]) { margin: 12px 0; }
dl:not([class]):not([style]) > dt {
  font-weight: 500;
  color: var(--color-text-primary);
  font-size: 14px;
  margin-top: 12px;
}
dl:not([class]):not([style]) > dt:first-child { margin-top: 0; }
dl:not([class]):not([style]) > dd {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* `display: contents` on the optional wrapping div + dual selectors below
 * tolerates both flat <dt><dd>… and <div><dt><dd></div>… markup. */
dl[data-layout="grid"] {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 8px 16px;
  align-items: baseline;
  padding: 12px 16px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  margin: 12px 0;
}
dl[data-layout="grid"] > div { display: contents; }
dl[data-layout="grid"] > dt,
dl[data-layout="grid"] > div > dt {
  font-weight: 400;
  color: var(--color-text-secondary);
  font-size: 13px;
  margin: 0;
}
dl[data-layout="grid"] > dd,
dl[data-layout="grid"] > div > dd {
  margin: 0;
  text-align: right;
  color: var(--color-text-primary);
  font-weight: 500;
  font-size: 13px;
}

/* data-layout="inline" — pill row. Each <dt>/<dd> pair wrapped in <div>.
 * Same opt-in-via-attribute logic as grid above — no :not() gate. */
dl[data-layout="inline"] {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 12px 0;
}
dl[data-layout="inline"] > div {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  padding: 4px 10px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 999px;
  font-size: 12px;
  background: var(--color-bg-secondary);
}
dl[data-layout="inline"] > div > dt {
  margin: 0;
  font-weight: 400;
  color: var(--color-text-secondary);
  font-size: 12px;
}
dl[data-layout="inline"] > div > dt::after {
  content: ":";
  margin-right: 2px;
}
dl[data-layout="inline"] > div > dd {
  margin: 0;
  font-weight: 500;
  color: var(--color-text-primary);
  font-size: 12px;
}

#iv-dl-wrap{position:fixed;top:4px;right:4px;z-index:9999}
#iv-dl-btn{width:26px;height:26px;padding:0;display:flex;align-items:center;justify-content:center;
  opacity:0.3;border-color:var(--color-border-tertiary);background:var(--color-bg-primary)}
#iv-dl-btn:hover{opacity:0.9;background:var(--color-bg-secondary)}
#iv-dl-btn svg{width:14px;height:14px;stroke:var(--color-text-secondary);fill:none;
  stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
/* --- Print ---
 * overflow:hidden on html/body clips content in print (needed on screen
 * for iframe sizing). Chart.js canvas scaling is handled by JS beforeprint
 * handler in BODY_SCRIPTS — it directly mutates inline styles that CSS
 * cannot reliably override in Chrome's print engine.
 */
@media print {
  @page { margin: 12mm; }
  html, body { overflow: visible !important; height: auto !important;
    background: #fff !important; }
  body { padding: 4px !important; }
  #iv-dl-wrap { display: none !important; }
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
"""

# ---------------------------------------------------------------------------
# Injected JavaScript — theme detection (head), height reporting & bridges (body)
# ---------------------------------------------------------------------------
# Theme script runs in <head> before user content so CSS vars are resolved
# when model scripts read them at parse time.
#
# !! SRCDOC SAFETY !!  Do NOT write the literal tokens <!-- , --> ,
# <![CDATA[ , ]]> , <script> or </script> ANYWHERE in this body —
# not even inside JS comments. The iframe srcdoc's HTML5 tokenizer
# treats them as parser state changes regardless of JS context, and
# silently breaks the IIFE (see _assert_srcdoc_safe near the bottom
# of this file for the runtime guard).
THEME_DETECTION_SCRIPT = """
<script>
(function() {
  function detectTheme(root) {
    return root.classList.contains('dark')
      || root.getAttribute('data-theme') === 'dark'
      || getComputedStyle(root).colorScheme === 'dark';
  }

  function applyTheme(isDark) {
    var theme = isDark ? 'dark' : 'light';
    if (document.documentElement.getAttribute('data-theme') === theme) return;
    document.documentElement.setAttribute('data-theme', theme);
    if (window.Chart && Chart.instances) {
      var styles = getComputedStyle(document.documentElement);
      var textColor = styles.getPropertyValue('--color-text-secondary').trim();
      var gridColor = styles.getPropertyValue('--color-border-tertiary').trim();
      Chart.defaults.color = textColor;
      Chart.defaults.borderColor = gridColor;
      Object.values(Chart.instances).forEach(function(chart) {
        Object.values(chart.options.scales || {}).forEach(function(scale) {
          if (scale.ticks) scale.ticks.color = textColor;
          if (scale.grid) scale.grid.color = gridColor;
        });
        var legend = (chart.options.plugins || {}).legend;
        if (legend && legend.labels) legend.labels.color = textColor;
        chart.update();
      });
    }
  }

  try {
    var parentRoot = parent.document.documentElement;
    applyTheme(detectTheme(parentRoot));
    new MutationObserver(function() {
      applyTheme(detectTheme(parentRoot));
    }).observe(parentRoot, { attributes: true, attributeFilter: ['class', 'data-theme', 'style'] });
  } catch(e) {
    // No same-origin access — fall back to OS preference.
    var mediaQuery = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
    if (mediaQuery) {
      applyTheme(mediaQuery.matches);
      mediaQuery.addEventListener('change', function(e) { applyTheme(e.matches); });
    }
  }
})();
</script>
"""

# !! SRCDOC SAFETY !!  Do NOT write the literal tokens <!-- , --> ,
# <![CDATA[ , ]]> , <script> or </script> ANYWHERE in this body —
# not even inside JS comments. See THEME_DETECTION_SCRIPT for full rationale.
BODY_SCRIPTS = """
<script>
// --- Height reporting ---
var _rh_last = 0;          // last reported height
var _rh_consecutive = 0;   // consecutive small-growth reports
var _rh_raf = 0;           // rAF id for debouncing ResizeObserver

function reportHeight() {
  var body = document.body;
  // Measure SVG overflow before the body collapse below — getBBox
  // needs normal layout.
  var svgOverflow = 0;
  document.querySelectorAll('svg[viewBox]').forEach(function(svg) {
    try {
      var bbox = svg.getBBox();
      var viewBox = svg.viewBox.baseVal;
      if (viewBox && viewBox.width > 0 && viewBox.height > 0) {
        var overflow = bbox.y + bbox.height - (viewBox.y + viewBox.height);
        if (overflow > 0) {
          var scale = svg.getBoundingClientRect().width / viewBox.width;
          svgOverflow += Math.ceil(overflow * scale);
        }
      }
    } catch(e) {}
  });

  // Force height:auto on body + direct children — vh in an auto-sized
  // iframe tracks iframe height, creating a feedback loop.
  var savedBodyCss = body.style.cssText;
  body.style.setProperty('height', 'auto', 'important');
  body.style.setProperty('overflow', 'visible', 'important');
  body.style.setProperty('display', 'block', 'important');
  var savedChildren = [];
  Array.from(body.children).forEach(function(child) {
    if (child.nodeType !== 1) return;
    savedChildren.push({ el: child, css: child.style.cssText });
    child.style.setProperty('height', 'auto', 'important');
    child.style.setProperty('max-height', 'none', 'important');
    child.style.setProperty('min-height', '0', 'important');
    child.style.setProperty('overflow', 'visible', 'important');
  });

  // Collapse any descendant with viewport-unit dimensions — 100vh
  // resolves to our own reported height, so leaving it intact
  // creates a feedback loop where body grows each cycle.
  var savedVhUsers = [];
  try {
    var vhUsers = body.querySelectorAll(
      '[style*="vh"], [style*="vw"], [style*="vmin"], [style*="vmax"]'
    );
    for (var k = 0; k < vhUsers.length; k++) {
      var vhEl = vhUsers[k];
      savedVhUsers.push({ el: vhEl, css: vhEl.style.cssText });
      vhEl.style.setProperty('min-height', '0', 'important');
      vhEl.style.setProperty('max-height', 'none', 'important');
      vhEl.style.setProperty('height', 'auto', 'important');
    }
  } catch(e) {}

  var pageHeight = body.scrollHeight + svgOverflow;
  body.style.cssText = savedBodyCss;
  savedChildren.forEach(function(entry) { entry.el.style.cssText = entry.css; });
  for (var v = 0; v < savedVhUsers.length; v++) {
    savedVhUsers[v].el.style.cssText = savedVhUsers[v].css;
  }

  // Loop guard: 3+ consecutive small monotonic increases → stop.
  var delta = pageHeight - _rh_last;
  if (_rh_last > 0 && delta > 0 && delta < 50) {
    _rh_consecutive++;
    if (_rh_consecutive >= 3) return;
  } else {
    _rh_consecutive = 0;
  }

  _rh_last = pageHeight;
  parent.postMessage({ type: 'iframe:height', height: pageHeight }, '*');
}
window.addEventListener('load', reportHeight);
window.addEventListener('resize', reportHeight);
// rAF-debounced ResizeObserver avoids tight synchronous loops.
new ResizeObserver(function() {
  cancelAnimationFrame(_rh_raf);
  _rh_raf = requestAnimationFrame(reportHeight);
}).observe(document.body);
// <details> toggle — ResizeObserver misses this in some browsers.
document.addEventListener('toggle', function() {
  _rh_consecutive = 0;
  setTimeout(reportHeight, 50);
}, true);
// Dynamic content swaps (innerHTML assignments, SPA-style updates).
var _rh_mutRaf = 0;
new MutationObserver(function() {
  _rh_consecutive = 0;
  cancelAnimationFrame(_rh_mutRaf);
  _rh_mutRaf = requestAnimationFrame(reportHeight);
}).observe(document.body, { childList: true, subtree: true });
// Click covers custom expand/collapse via style.display / class swaps.
document.addEventListener('click', function() {
  _rh_consecutive = 0;
  cancelAnimationFrame(_rh_mutRaf);
  _rh_mutRaf = requestAnimationFrame(reportHeight);
}, true);

// --- Post-render fixes (theme defaults, overlap prevention) ---
window.addEventListener('load', function() {
  // Chart.js theme defaults + legend overflow prevention
  if (window.Chart) {
    var styles = getComputedStyle(document.documentElement);
    var textColor = styles.getPropertyValue('--color-text-secondary').trim();
    var gridColor = styles.getPropertyValue('--color-border-tertiary').trim();
    Chart.defaults.color = textColor;
    Chart.defaults.borderColor = gridColor;
    Chart.defaults.plugins.legend.labels.color = textColor;
    Chart.defaults.plugins.legend.maxHeight = 120;
    Chart.defaults.plugins.legend.labels.boxWidth = 12;
    Chart.defaults.plugins.legend.labels.font = { size: 11 };
    Object.values(Chart.instances || {}).forEach(function(chart) {
      var legend = chart.options.plugins && chart.options.plugins.legend;
      if (legend) {
        legend.maxHeight = legend.maxHeight || 120;
        if (legend.labels) {
          legend.labels.boxWidth = legend.labels.boxWidth || 12;
        }
      }
      chart.update();
    });
  }

  // De-overlap SVG axis labels only — add data-no-stagger on a <svg>
  // to opt out.
  document.querySelectorAll('svg').forEach(function(svg) {
    if (svg.hasAttribute('data-no-stagger')) return;
    var texts = Array.from(svg.querySelectorAll('text'));
    if (texts.length < 4) return;
    var items = [];
    texts.forEach(function(textEl) {
      var rect = textEl.getBoundingClientRect();
      if (rect.width < 1) return;
      items.push({ el: textEl, rect: rect, cx: rect.left + rect.width / 2, cy: rect.top + rect.height / 2 });
    });
    if (items.length < 4) return;
    // Only touch texts in a narrow y-band (axis labels). Diagrams with
    // texts spread across the canvas are left alone.
    var minY = Infinity, maxY = -Infinity;
    items.forEach(function(item) {
      if (item.cy < minY) minY = item.cy;
      if (item.cy > maxY) maxY = item.cy;
    });
    var ySpan = maxY - minY;
    if (ySpan < 1) return;
    // Pick the densest y-band (likely the axis row).
    var bandSize = 30;
    var bestBand = [], bestCount = 0;
    items.forEach(function(anchor) {
      var band = items.filter(function(item) { return Math.abs(item.cy - anchor.cy) < bandSize; });
      if (band.length > bestCount) { bestCount = band.length; bestBand = band; }
    });
    if (bestBand.length < 3 || bestBand.length === items.length && ySpan > 60) return;
    var groups = [];
    bestBand.forEach(function(item) {
      for (var i = 0; i < groups.length; i++) {
        if (Math.abs(groups[i].cx - item.cx) < 15) {
          groups[i].items.push(item);
          return;
        }
      }
      groups.push({ cx: item.cx, items: [item] });
    });
    if (groups.length < 3) return;
    groups.sort(function(a, b) { return a.cx - b.cx; });
    var needsStagger = false;
    for (var i = 0; i < groups.length - 1; i++) {
      var maxRight = 0, minLeft = Infinity;
      groups[i].items.forEach(function(item) { if (item.rect.right > maxRight) maxRight = item.rect.right; });
      groups[i+1].items.forEach(function(item) { if (item.rect.left < minLeft) minLeft = item.rect.left; });
      if (maxRight > minLeft - 2) { needsStagger = true; break; }
    }
    if (needsStagger) {
      for (var i = 1; i < groups.length; i += 2) {
        groups[i].items.forEach(function(item) {
          var y = parseFloat(item.el.getAttribute('y') || 0);
          item.el.setAttribute('y', String(y + 18));
        });
      }
    }
  });

  setTimeout(reportHeight, 100);
});

// --- sendPrompt bridge (requires iframe Sandbox Allow Same Origin) ---
function sendPrompt(text) {
  try {
    // Open WebUI's native prompt-submit postMessage — queues if the
    // model is mid-generation.
    parent.postMessage({ type: 'input:prompt:submit', text: text }, '*');
  } catch(e) { /* iframe sandbox restriction */ }
}

// --- Open link in parent window ---
function openLink(url) {
  try { parent.window.open(url, '_blank'); }
  catch(e) { window.open(url, '_blank'); }
}

// --- navigator.vibrate silencer ---
// Chrome spams `[Intervention] Blocked call to navigator.vibrate…` on
// every call without a prior user gesture. Replace with a no-op so the
// block path never runs.
try {
  if (typeof navigator !== 'undefined' && navigator.vibrate) {
    navigator.vibrate = function() { return false; };
  }
} catch(e) {}

// --- Toast bridge ---
// Floating auto-dismissing top-right banner. kind = success/info/warn/error.
function toast(msg, kind) {
  kind = kind || 'success';
  var color = kind === 'error' ? 'var(--color-text-danger)'
           : kind === 'info'  ? 'var(--color-text-info)'
           : kind === 'warn'  ? 'var(--color-text-warning)'
           : 'var(--color-text-success)';
  var wrap = document.getElementById('iv-toast-wrap');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.id = 'iv-toast-wrap';
    wrap.style.cssText =
      'position:fixed;top:4px;right:38px;z-index:9998;' +
      'display:flex;flex-direction:column;gap:4px;pointer-events:none;' +
      'max-width:280px;';
    document.body.appendChild(wrap);
  }
  var banner = document.createElement('div');
  banner.style.cssText =
    'padding:6px 12px;border-radius:var(--radius-md);' +
    'background:var(--color-bg-secondary);' +
    'border:0.5px solid var(--color-border-tertiary);' +
    'color:' + color + ';font-size:12px;line-height:1.4;' +
    'font-family:var(--font-sans);font-weight:500;' +
    'opacity:0;transform:translateY(-4px);transition:all 0.2s ease;' +
    'pointer-events:auto;white-space:nowrap;' +
    'overflow:hidden;text-overflow:ellipsis;';
  banner.textContent = String(msg == null ? '' : msg);
  wrap.appendChild(banner);
  requestAnimationFrame(function() {
    banner.style.opacity = '1';
    banner.style.transform = 'none';
  });
  setTimeout(function() {
    banner.style.opacity = '0';
    banner.style.transform = 'translateY(-4px)';
    setTimeout(function() { if (banner.parentNode) banner.parentNode.removeChild(banner); }, 220);
  }, 2200);
}

// --- copyText bridge ---
// Async Clipboard API with execCommand fallback (Open WebUI's iframe
// sandbox lacks allow-clipboard-write). Toast fires unconditionally —
// execCommand can silently fail and swallowing feedback leaves the user
// confused. silent=true suppresses the toast.
function copyText(text, silent) {
  var value = String(text == null ? '' : text);
  var label = (typeof _ivCopiedStr !== 'undefined' &&
               (_ivCopiedStr[_ivLang] || _ivCopiedStr.en)) || 'Copied';
  function fire() { if (!silent) try { toast(label, 'success'); } catch(e) {} }

  function legacy() {
    try {
      var textarea = document.createElement('textarea');
      textarea.value = value;
      textarea.setAttribute('readonly', '');
      textarea.style.cssText =
        'position:fixed;left:-9999px;top:-9999px;opacity:0;';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      try { textarea.setSelectionRange(0, value.length); } catch(e) {}
      try { document.execCommand('copy'); } catch(e) {}
      textarea.remove();
    } catch(e) {}
    fire();
  }

  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(fire, legacy);
      return;
    }
  } catch(e) {}
  legacy();
}

// --- saveState / loadState bridges ---
// parent.localStorage proxy scoped to the assistant message id — state
// persists across reloads but never leaks between chats / messages.
// Silent no-op if localStorage / parent is unreachable.
function _ivStatePrefix() {
  try {
    var frame = window.frameElement;
    var msgEl = frame && frame.closest && frame.closest('[id^="message-"]');
    return 'iv-state:' + ((msgEl && msgEl.id) || 'global') + ':';
  } catch(e) { return 'iv-state:global:'; }
}
function saveState(key, value) {
  try {
    parent.localStorage.setItem(
      _ivStatePrefix() + String(key),
      JSON.stringify(value === undefined ? null : value)
    );
  } catch(e) {}
}
function loadState(key, fallback) {
  try {
    var stored = parent.localStorage.getItem(_ivStatePrefix() + String(key));
    if (stored == null) return fallback === undefined ? null : fallback;
    return JSON.parse(stored);
  } catch(e) { return fallback === undefined ? null : fallback; }
}

/*__CHIME_BLOCK__*/

// --- Print fix for Chart.js canvases ---
// Chart.js writes explicit pixel widths as inline styles that CSS
// max-width can't override in Chrome's print engine. Mutate inline
// styles before print, restore after.
(function() {
  window.addEventListener('beforeprint', function() {
    document.querySelectorAll('canvas').forEach(function(canvas) {
      canvas.setAttribute('data-print-style', canvas.style.cssText);
      canvas.style.setProperty('width', '100%', 'important');
      canvas.style.setProperty('max-width', '100%', 'important');
      canvas.style.setProperty('height', 'auto', 'important');
      var parentEl = canvas.parentElement;
      if (parentEl) {
        parentEl.setAttribute('data-print-style', parentEl.style.cssText);
        parentEl.style.setProperty('width', '100%', 'important');
        parentEl.style.setProperty('max-width', '100%', 'important');
      }
    });
  });
  window.addEventListener('afterprint', function() {
    document.querySelectorAll('[data-print-style]').forEach(function(el) {
      el.style.cssText = el.getAttribute('data-print-style');
      el.removeAttribute('data-print-style');
    });
  });
})();

// --- Download visualization as self-contained HTML ---
var _ivLang = 'en';
var _ivStr = {
  // Required languages
  en: 'Download as HTML',
  de: 'Als HTML herunterladen',
  cs: 'Stáhnout jako HTML',
  hu: 'Letöltés HTML-ként',
  hr: 'Preuzmi kao HTML',
  pl: 'Pobierz jako HTML',
  fr: 'Télécharger en HTML',
  nl: 'Downloaden als HTML',
  // Western & Southern European
  es: 'Descargar como HTML',
  pt: 'Baixar como HTML',
  it: 'Scarica come HTML',
  ca: 'Baixa com a HTML',
  gl: 'Descargar como HTML',
  eu: 'Deskargatu HTML gisa',
  // Northern European
  da: 'Download som HTML',
  sv: 'Ladda ner som HTML',
  no: 'Last ned som HTML',
  fi: 'Lataa HTML-tiedostona',
  is: 'Hlaða niður sem HTML',
  // Eastern European & Slavic
  sk: 'Stiahnuť ako HTML',
  sl: 'Prenesi kot HTML',
  sr: 'Преузми као HTML',
  bs: 'Preuzmi kao HTML',
  bg: 'Изтегли като HTML',
  mk: 'Преземи како HTML',
  uk: 'Завантажити як HTML',
  ru: 'Скачать как HTML',
  be: 'Спампаваць як HTML',
  // Baltic
  lt: 'Atsisiųsti kaip HTML',
  lv: 'Lejupielādēt kā HTML',
  et: 'Laadi alla HTML-ina',
  // Other European
  ro: 'Descarcă ca HTML',
  el: 'Λήψη ως HTML',
  sq: 'Shkarko si HTML',
  // Middle Eastern
  tr: 'HTML olarak indir',
  az: 'HTML olaraq yüklə',
  ar: 'تحميل كـ HTML',

  he: 'הורד כ-HTML',
  // East & South Asian
  zh: '下载为HTML',
  ja: 'HTMLでダウンロード',
  ko: 'HTML로 다운로드',
  vi: 'Tải xuống dạng HTML',
  th: 'ดาวน์โหลดเป็น HTML',
  id: 'Unduh sebagai HTML',
  ms: 'Muat turun sebagai HTML',
  hi: 'HTML के रूप में डाउनलोड करें',
  bn: 'HTML হিসেবে ডাউনলোড করুন',
  // African
  sw: 'Pakua kama HTML'
};

// Loader label (shown while waiting for the first content chunk).
var _ivLoadStr = {
  en: 'Rendering visualization\u2026',
  de: 'Visualisierung wird erstellt\u2026',
  cs: 'Vykresluje se vizualizace\u2026',
  hu: 'Vizualizáció renderelése\u2026',
  hr: 'Iscrtavanje vizualizacije\u2026',
  pl: 'Renderowanie wizualizacji\u2026',
  fr: 'Rendu de la visualisation\u2026',
  nl: 'Visualisatie renderen\u2026',
  es: 'Renderizando visualización\u2026',
  pt: 'Renderizando visualização\u2026',
  it: 'Rendering della visualizzazione\u2026',
  ca: 'Renderitzant visualització\u2026',
  gl: 'Renderizando visualización\u2026',
  eu: 'Bistaratzea errendatzen\u2026',
  da: 'Gengiver visualisering\u2026',
  sv: 'Renderar visualisering\u2026',
  no: 'Gjengir visualisering\u2026',
  fi: 'Renderöidään visualisointia\u2026',
  is: 'Teiknar sjónræna framsetningu\u2026',
  sk: 'Vykresľuje sa vizualizácia\u2026',
  sl: 'Upodabljanje vizualizacije\u2026',
  sr: 'Исцртавање визуализације\u2026',
  bs: 'Iscrtavanje vizualizacije\u2026',
  bg: 'Изчертаване на визуализацията\u2026',
  mk: 'Исцртување на визуализацијата\u2026',
  uk: 'Відображення візуалізації\u2026',
  ru: 'Отрисовка визуализации\u2026',
  be: 'Адмалёўка візуалізацыі\u2026',
  lt: 'Atvaizduojama vizualizacija\u2026',
  lv: 'Vizualizācijas renderēšana\u2026',
  et: 'Visualiseeringu renderdamine\u2026',
  ro: 'Randare vizualizare\u2026',
  el: 'Απόδοση οπτικοποίησης\u2026',
  sq: 'Duke renderuar vizualizimin\u2026',
  tr: 'Görselleştirme oluşturuluyor\u2026',
  az: 'Vizuallaşdırma hazırlanır\u2026',
  ar: 'جارٍ عرض التصور\u2026',
  he: 'מציג הדמיה\u2026',
  zh: '正在渲染可视化\u2026',
  ja: 'ビジュアライゼーションを描画中\u2026',
  ko: '시각화 렌더링 중\u2026',
  vi: 'Đang kết xuất hình ảnh\u2026',
  th: 'กำลังแสดงผลการแสดงภาพ\u2026',
  id: 'Merender visualisasi\u2026',
  ms: 'Memaparkan visualisasi\u2026',
  hi: 'विज़ुअलाइज़ेशन रेंडर हो रहा है\u2026',
  bn: 'ভিজ্যুয়ালাইজেশন রেন্ডার হচ্ছে\u2026',
  sw: 'Inarendi taswira\u2026'
};

// "Streaming visualization unavailable" title + body, shown only when
// the iframe cannot reach parent.document (Allow Same Origin disabled).
var _ivErrTitleStr = {
  en: 'Streaming visualization unavailable',
  de: 'Streaming-Visualisierung nicht verfügbar',
  cs: 'Streamovaná vizualizace není dostupná',
  hu: 'A streamelt vizualizáció nem érhető el',
  hr: 'Streaming vizualizacija nije dostupna',
  pl: 'Strumieniowa wizualizacja niedostępna',
  fr: 'Visualisation en streaming indisponible',
  nl: 'Streaming visualisatie niet beschikbaar',
  es: 'Visualización en streaming no disponible',
  pt: 'Visualização em streaming indisponível',
  it: 'Visualizzazione in streaming non disponibile',
  ca: 'Visualització en streaming no disponible',
  gl: 'Visualización en streaming non dispoñíbel',
  eu: 'Streaming bistaratzea ez dago erabilgarri',
  da: 'Streaming-visualisering utilgængelig',
  sv: 'Strömmande visualisering otillgänglig',
  no: 'Streaming-visualisering utilgjengelig',
  fi: 'Suoratoistettu visualisointi ei käytettävissä',
  is: 'Streymandi sjónræn framsetning ekki tiltæk',
  sk: 'Streamovaná vizualizácia nie je dostupná',
  sl: 'Pretočna vizualizacija ni na voljo',
  sr: 'Стриминг визуализација није доступна',
  bs: 'Streaming vizualizacija nije dostupna',
  bg: 'Поточната визуализация е недостъпна',
  mk: 'Стриминг визуализација недостапна',
  uk: 'Потокова візуалізація недоступна',
  ru: 'Потоковая визуализация недоступна',
  be: 'Струменевая візуалізацыя недаступная',
  lt: 'Srautinė vizualizacija nepasiekiama',
  lv: 'Straumētā vizualizācija nav pieejama',
  et: 'Voogedastuse visualiseering pole saadaval',
  ro: 'Vizualizarea în streaming indisponibilă',
  el: 'Η ροή οπτικοποίησης δεν είναι διαθέσιμη',
  sq: 'Vizualizimi i transmetimit i padisponueshëm',
  tr: 'Akış görselleştirmesi kullanılamıyor',
  az: 'Streaming vizualizasiyası mövcud deyil',
  ar: 'التصور المتدفق غير متاح',
  he: 'הדמיה בסטרימינג אינה זמינה',
  zh: '流式可视化不可用',
  ja: 'ストリーミングビジュアライゼーションは利用できません',
  ko: '스트리밍 시각화를 사용할 수 없습니다',
  vi: 'Hình ảnh trực quan phát trực tuyến không khả dụng',
  th: 'การแสดงผลแบบสตรีมไม่พร้อมใช้งาน',
  id: 'Visualisasi streaming tidak tersedia',
  ms: 'Visualisasi strim tidak tersedia',
  hi: 'स्ट्रीमिंग विज़ुअलाइज़ेशन अनुपलब्ध',
  bn: 'স্ট্রিমিং ভিজ্যুয়ালাইজেশন অনুপলব্ধ',
  sw: 'Taswira ya utiririshaji haipatikani'
};

// Confirmation toast shown after copyText() succeeds.
var _ivCopiedStr = {
  en: 'Copied', de: 'Kopiert', cs: 'Zkopírováno', hu: 'Másolva',
  hr: 'Kopirano', pl: 'Skopiowano', fr: 'Copié', nl: 'Gekopieerd',
  es: 'Copiado', pt: 'Copiado', it: 'Copiato', ca: 'Copiat',
  gl: 'Copiado', eu: 'Kopiatuta',
  da: 'Kopieret', sv: 'Kopierat', no: 'Kopiert', fi: 'Kopioitu',
  is: 'Afritað',
  sk: 'Skopírované', sl: 'Kopirano', sr: 'Копирано', bs: 'Kopirano',
  bg: 'Копирано', mk: 'Копирано', uk: 'Скопійовано', ru: 'Скопировано',
  be: 'Скапіявана',
  lt: 'Nukopijuota', lv: 'Nokopēts', et: 'Kopeeritud',
  ro: 'Copiat', el: 'Αντιγράφηκε', sq: 'U kopjua',
  tr: 'Kopyalandı', az: 'Kopyalandı', ar: 'تم النسخ', he: 'הועתק',
  zh: '已复制', ja: 'コピーしました', ko: '복사됨',
  vi: 'Đã sao chép', th: 'คัดลอกแล้ว', id: 'Disalin', ms: 'Disalin',
  hi: 'कॉपी किया गया', bn: 'অনুলিপি করা হয়েছে',
  sw: 'Imenakiliwa'
};

// Shown as a top-right toast when streaming completes and the
// visualization has finished rendering. Only appears if we actually
// witnessed live streaming — refreshes of completed messages stay silent.
var _ivDoneStr = {
  en: 'Visualization ready',
  de: 'Visualisierung bereit',
  cs: 'Vizualizace připravena',
  hu: 'Vizualizáció kész',
  hr: 'Vizualizacija spremna',
  pl: 'Wizualizacja gotowa',
  fr: 'Visualisation prête',
  nl: 'Visualisatie klaar',
  es: 'Visualización lista',
  pt: 'Visualização pronta',
  it: 'Visualizzazione pronta',
  ca: 'Visualització llesta',
  gl: 'Visualización lista',
  eu: 'Bistaratzea prest',
  da: 'Visualisering klar',
  sv: 'Visualisering klar',
  no: 'Visualisering klar',
  fi: 'Visualisointi valmis',
  is: 'Sjónræn framsetning tilbúin',
  sk: 'Vizualizácia pripravená',
  sl: 'Vizualizacija pripravljena',
  sr: 'Визуализација спремна',
  bs: 'Vizualizacija spremna',
  bg: 'Визуализацията е готова',
  mk: 'Визуализацијата е подготвена',
  uk: 'Візуалізація готова',
  ru: 'Визуализация готова',
  be: 'Візуалізацыя гатовая',
  lt: 'Vizualizacija paruošta',
  lv: 'Vizualizācija gatava',
  et: 'Visualiseering valmis',
  ro: 'Vizualizare gata',
  el: 'Η οπτικοποίηση είναι έτοιμη',
  sq: 'Vizualizimi gati',
  tr: 'Görselleştirme hazır',
  az: 'Vizuallaşdırma hazırdır',
  ar: 'التصور جاهز',
  he: 'ההדמיה מוכנה',
  zh: '可视化已完成',
  ja: 'ビジュアライゼーション完成',
  ko: '시각화 완료',
  vi: 'Hình ảnh đã sẵn sàng',
  th: 'การแสดงภาพพร้อมแล้ว',
  id: 'Visualisasi siap',
  ms: 'Visualisasi sedia',
  hi: 'विज़ुअलाइज़ेशन तैयार',
  bn: 'ভিজ্যুয়ালাইজেশন প্রস্তুত',
  sw: 'Taswira tayari'
};

// Export failure toast (PNG/SVG download dead-ended).
var _ivExportErrStr = {
  en: 'Export failed',
  de: 'Export fehlgeschlagen',
  cs: 'Export se nezdařil',
  hu: 'Az exportálás sikertelen',
  hr: 'Izvoz nije uspio',
  pl: 'Eksport nie powiódł się',
  fr: 'Échec de l’exportation',
  nl: 'Exporteren mislukt',
  es: 'Error al exportar',
  pt: 'Falha na exportação',
  it: 'Esportazione non riuscita',
  ca: 'Ha fallat l’exportació',
  gl: 'Fallou a exportación',
  eu: 'Esportazioak huts egin du',
  da: 'Eksport mislykkedes',
  sv: 'Exporten misslyckades',
  no: 'Eksporten mislyktes',
  fi: 'Vienti epäonnistui',
  is: 'Útflutningur mistókst',
  sk: 'Export zlyhal',
  sl: 'Izvoz ni uspel',
  sr: 'Извоз није успео',
  bs: 'Izvoz nije uspio',
  bg: 'Експортирането е неуспешно',
  mk: 'Извезувањето не успеа',
  uk: 'Не вдалося експортувати',
  ru: 'Не удалось экспортировать',
  be: 'Не ўдалося экспартаваць',
  lt: 'Nepavyko eksportuoti',
  lv: 'Neizdevās eksportēt',
  et: 'Eksportimine ebaõnnestus',
  ro: 'Exportul a eșuat',
  el: 'Η εξαγωγή απέτυχε',
  sq: 'Eksportimi dështoi',
  tr: 'Dışa aktarma başarısız oldu',
  az: 'İxrac uğursuz oldu',
  ar: 'فشل التصدير',
  he: 'הייצוא נכשל',
  zh: '导出失败',
  ja: 'エクスポートに失敗しました',
  ko: '내보내기 실패',
  vi: 'Xuất không thành công',
  th: 'การส่งออกล้มเหลว',
  id: 'Ekspor gagal',
  ms: 'Eksport gagal',
  hi: 'निर्यात विफल',
  bn: 'এক্সপোর্ট ব্যর্থ হয়েছে',
  sw: 'Imeshindwa kuhamisha'
};

var _ivErrBodyStr = {
  en: 'Open User Settings \u2192 Interface, scroll down, and enable "Allow iframe same origin" to use streaming mode.',
  de: 'Öffne Benutzereinstellungen \u2192 Oberfläche, scrolle nach unten und aktiviere „Allow iframe same origin" für den Streaming-Modus.',
  cs: 'Otevřete Uživatelská nastavení \u2192 Rozhraní, sjeďte dolů a zapněte „Allow iframe same origin" pro režim streamování.',
  hu: 'Nyissa meg a Felhasználói beállítások \u2192 Felület menüt, görgessen le, és kapcsolja be az „Allow iframe same origin" opciót a streamelési módhoz.',
  hr: 'Otvorite Korisničke postavke \u2192 Sučelje, pomaknite se prema dolje i uključite „Allow iframe same origin" za streaming način.',
  pl: 'Otwórz Ustawienia użytkownika \u2192 Interfejs, przewiń w dół i włącz „Allow iframe same origin" dla trybu strumieniowego.',
  fr: 'Ouvrez Paramètres utilisateur \u2192 Interface, faites défiler vers le bas et activez « Allow iframe same origin » pour le mode streaming.',
  nl: 'Open Gebruikersinstellingen \u2192 Interface, scrol omlaag en schakel "Allow iframe same origin" in voor streamingmodus.',
  es: 'Abre Configuración de usuario \u2192 Interfaz, desplázate hacia abajo y activa "Allow iframe same origin" para el modo streaming.',
  pt: 'Abra Configurações do usuário \u2192 Interface, role para baixo e ative "Allow iframe same origin" para o modo streaming.',
  it: 'Apri Impostazioni utente \u2192 Interfaccia, scorri in basso e attiva "Allow iframe same origin" per la modalità streaming.',
  ca: 'Obre Configuració d\u2019usuari \u2192 Interfície, desplaça\u2019t avall i activa "Allow iframe same origin" per al mode streaming.',
  gl: 'Abre Configuración de usuario \u2192 Interface, desprázate cara abaixo e activa "Allow iframe same origin" para o modo streaming.',
  eu: 'Ireki Erabiltzaile-ezarpenak \u2192 Interfazea, egin behera eta gaitu "Allow iframe same origin" streaming modua erabiltzeko.',
  da: 'Åbn Brugerindstillinger \u2192 Grænseflade, rul ned, og aktivér "Allow iframe same origin" for streamingtilstand.',
  sv: 'Öppna Användarinställningar \u2192 Gränssnitt, rulla ner och aktivera "Allow iframe same origin" för strömningsläge.',
  no: 'Åpne Brukerinnstillinger \u2192 Grensesnitt, rull ned og aktiver "Allow iframe same origin" for streamingmodus.',
  fi: 'Avaa Käyttäjäasetukset \u2192 Käyttöliittymä, vieritä alas ja ota "Allow iframe same origin" käyttöön suoratoistotilaa varten.',
  is: 'Opnaðu Notandastillingar \u2192 Viðmót, skrunaðu niður og kveiktu á "Allow iframe same origin" fyrir streymisstillingu.',
  sk: 'Otvorte Používateľské nastavenia \u2192 Rozhranie, posuňte sa nadol a zapnite „Allow iframe same origin" pre režim streamovania.',
  sl: 'Odprite Uporabniške nastavitve \u2192 Vmesnik, pomaknite se navzdol in omogočite "Allow iframe same origin" za pretočni način.',
  sr: 'Отворите Корисничка подешавања \u2192 Интерфејс, померите надоле и омогућите „Allow iframe same origin" за стриминг режим.',
  bs: 'Otvorite Korisničke postavke \u2192 Sučelje, skrolajte prema dolje i uključite "Allow iframe same origin" za streaming mod.',
  bg: 'Отворете Потребителски настройки \u2192 Интерфейс, превъртете надолу и активирайте „Allow iframe same origin" за поточен режим.',
  mk: 'Отворете Кориснички поставки \u2192 Интерфејс, листајте надолу и овозможете „Allow iframe same origin" за стриминг режим.',
  uk: 'Відкрийте Налаштування користувача \u2192 Інтерфейс, прокрутіть униз і ввімкніть «Allow iframe same origin» для потокового режиму.',
  ru: 'Откройте Настройки пользователя \u2192 Интерфейс, прокрутите вниз и включите «Allow iframe same origin» для режима потоковой передачи.',
  be: 'Адкрыйце Налады карыстальніка \u2192 Інтэрфейс, прагартайце ўніз і ўключыце «Allow iframe same origin» для струменевага рэжыму.',
  lt: 'Atidarykite Naudotojo nustatymai \u2192 Sąsaja, slinkite žemyn ir įjunkite „Allow iframe same origin" srautiniam režimui.',
  lv: 'Atveriet Lietotāja iestatījumi \u2192 Saskarne, ritiniet lejup un iespējojiet "Allow iframe same origin" straumēšanas režīmam.',
  et: 'Ava Kasutaja seaded \u2192 Liides, keri alla ja luba „Allow iframe same origin" voogedastusrežiimi jaoks.',
  ro: 'Deschide Setări utilizator \u2192 Interfață, derulează în jos și activează "Allow iframe same origin" pentru modul streaming.',
  el: 'Ανοίξτε Ρυθμίσεις χρήστη \u2192 Διεπαφή, κυλήστε προς τα κάτω και ενεργοποιήστε το «Allow iframe same origin» για λειτουργία ροής.',
  sq: 'Hapni Cilësimet e përdoruesit \u2192 Ndërfaqja, rrëshqitni poshtë dhe aktivizoni "Allow iframe same origin" për modalitetin e transmetimit.',
  tr: 'Kullanıcı Ayarları \u2192 Arayüz\u2019ü açın, aşağı kaydırın ve akış modu için "Allow iframe same origin" seçeneğini etkinleştirin.',
  az: 'İstifadəçi Ayarları \u2192 İnterfeys\u2019i açın, aşağı sürüşdürün və streaming rejimi üçün "Allow iframe same origin" seçimini aktivləşdirin.',
  ar: 'افتح إعدادات المستخدم \u2190 الواجهة، مرر لأسفل وفعّل "Allow iframe same origin" لاستخدام وضع التدفق.',
  he: 'פתח הגדרות משתמש \u2190 ממשק, גלול מטה והפעל את "Allow iframe same origin" למצב סטרימינג.',
  zh: '打开 用户设置 \u2192 界面，向下滚动并启用"Allow iframe same origin"以使用流式模式。',
  ja: 'ユーザー設定 \u2192 インターフェースを開き、下にスクロールして「Allow iframe same origin」を有効にするとストリーミングモードを使用できます。',
  ko: '사용자 설정 \u2192 인터페이스를 열고 아래로 스크롤하여 "Allow iframe same origin"을 활성화하면 스트리밍 모드를 사용할 수 있습니다.',
  vi: 'Mở Cài đặt người dùng \u2192 Giao diện, cuộn xuống và bật "Allow iframe same origin" để sử dụng chế độ phát trực tiếp.',
  th: 'เปิดการตั้งค่าผู้ใช้ \u2192 อินเทอร์เฟซ เลื่อนลงและเปิดใช้งาน "Allow iframe same origin" เพื่อใช้โหมดสตรีม',
  id: 'Buka Pengaturan Pengguna \u2192 Antarmuka, gulir ke bawah dan aktifkan "Allow iframe same origin" untuk mode streaming.',
  ms: 'Buka Tetapan Pengguna \u2192 Antara Muka, tatal ke bawah dan dayakan "Allow iframe same origin" untuk mod strim.',
  hi: 'उपयोगकर्ता सेटिंग्स \u2192 इंटरफ़ेस खोलें, नीचे स्क्रॉल करें और स्ट्रीमिंग मोड के लिए "Allow iframe same origin" सक्षम करें।',
  bn: 'ব্যবহারকারী সেটিংস \u2192 ইন্টারফেস খুলুন, নিচে স্ক্রোল করুন এবং স্ট্রিমিং মোডের জন্য "Allow iframe same origin" সক্ষম করুন।',
  sw: 'Fungua Mipangilio ya Mtumiaji \u2192 Kiolesura, sogeza chini na washa "Allow iframe same origin" kwa hali ya utiririshaji.'
};

(function() {
  function detectLang() {
    // 1. Pre-detected via __event_call__ (baked into HTML by the tool)
    var pre = document.documentElement.getAttribute('data-iv-lang');
    if (pre && _ivStr[pre]) return pre;
    // 2. Fallback: parent localStorage (needs same-origin)
    try {
      var stored = parent.localStorage.getItem('locale')
           || parent.localStorage.getItem('language')
           || parent.localStorage.getItem('i18nextLng');
      if (stored) { var primary = stored.split('-')[0].toLowerCase(); if (_ivStr[primary]) return primary; }
    } catch(e) {}
    // 3. Fallback: browser language (standalone HTML / no same-origin)
    try {
      var browserLang = (navigator.language || navigator.userLanguage || 'en').split('-')[0].toLowerCase();
      if (_ivStr[browserLang]) return browserLang;
    } catch(e) {}
    return 'en';
  }
  _ivLang = detectLang();
  var downloadBtn = document.getElementById('iv-dl-btn');
  if (downloadBtn) downloadBtn.title = _ivStr[_ivLang] || _ivStr.en;
  // Swap the server-baked English loader label for the detected locale.
  var loadLabel = document.querySelector('.iv-loading-label');
  if (loadLabel) loadLabel.textContent = _ivLoadStr[_ivLang] || _ivLoadStr.en;
})();

// ---------------------------------------------------------------------------
// Download as self-contained HTML
// ---------------------------------------------------------------------------
// Desktop / Android: blob + <a download> + target="_blank" safety net
// (gracefully opens in a new tab if the iframe sandbox blocks downloads).
// iOS: NO target="_blank" (would strand PWA users on a blob page with no
// back button), setTimeout(0) deferral avoids a synchronous WebKit
// "Load failed" throw, and error listeners suppress the residual toast
// for 60s. iOS detection also catches iPadOS via MacIntel+touchpoints.
// ---------------------------------------------------------------------------

var _ivIsIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
  || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

// ---------------------------------------------------------------------------
// Download format menu (HTML / SVG / PNG)
// ---------------------------------------------------------------------------

function _ivFirstSvg() {
  var svgs = document.querySelectorAll('svg');
  for (var i = 0; i < svgs.length; i++) {
    var svg = svgs[i];
    if (svg.ownerSVGElement) continue;            // skip nested svg
    var ancestor = svg.parentNode, inWrap = false; // skip the download icon itself
    while (ancestor) { if (ancestor.id === 'iv-dl-wrap') { inWrap = true; break; } ancestor = ancestor.parentNode; }
    if (inWrap) continue;
    return svg;
  }
  return null;
}

function _ivDlMenu(ev) {
  if (ev) ev.stopPropagation();
  var menu = document.getElementById('iv-dl-menu');
  if (!menu) { _ivDownload(); return; }
  if (menu.style.display !== 'none') { menu.style.display = 'none'; return; }
  // SVG export only makes sense when the visualization contains an SVG.
  // PNG is always available (vector rasterization or html2canvas screenshot).
  var hasSvg = !!_ivFirstSvg();
  var items = menu.querySelectorAll('.iv-dl-item');
  for (var i = 0; i < items.length; i++) {
    var label = items[i].textContent;
    if (label === 'SVG') items[i].style.display = hasSvg ? 'block' : 'none';
  }
  menu.style.display = 'block';
  var closer = function() {
    menu.style.display = 'none';
    document.removeEventListener('click', closer, true);
  };
  setTimeout(function() { document.addEventListener('click', closer, true); }, 0);
}

function _ivBaseName() {
  var name = (document.title || 'visualization').replace(/[<>:"\\/|?*]+/g, '-').replace(/\s+/g, ' ').trim();
  if (!name) name = 'visualization';
  if (name.length > 200) name = name.substring(0, 200).trim();
  return name;
}

function _ivSaveBlob(blob, fileName) {
  var url = URL.createObjectURL(blob);
  var triggerDownload = function() {
    var link = document.createElement('a');
    link.style.display = 'none';
    link.href = url;
    link.download = fileName;
    if (!_ivIsIOS) link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    setTimeout(function() { link.remove(); URL.revokeObjectURL(url); }, 60000);
  };
  if (_ivIsIOS) { setTimeout(triggerDownload, 0); } else { triggerDownload(); }
}

function _ivResolvedBg() {
  // Effective page background for exports: body, then html, then the
  // detected theme (data-theme) so dark-mode exports stay dark.
  var bg = '';
  try {
    var bodyBg = window.getComputedStyle(document.body).backgroundColor;
    if (bodyBg && bodyBg !== 'rgba(0, 0, 0, 0)' && bodyBg !== 'transparent') bg = bodyBg;
    if (!bg) {
      var htmlBg = window.getComputedStyle(document.documentElement).backgroundColor;
      if (htmlBg && htmlBg !== 'rgba(0, 0, 0, 0)' && htmlBg !== 'transparent') bg = htmlBg;
    }
  } catch (e) {}
  if (!bg) {
    try {
      var varBg = window.getComputedStyle(document.documentElement).getPropertyValue('--color-bg');
      if (varBg && varBg.trim()) bg = varBg.trim();
    } catch (e) {}
  }
  if (!bg) {
    var isDark = (document.documentElement.getAttribute('data-theme') || '') === 'dark';
    bg = isDark ? '#1A1A1A' : '#ffffff';
  }
  return bg;
}

function _ivSerializedSvg(svg) {
  // Inline computed styles so CSS-class based fills/strokes/fonts
  // survive outside the document stylesheet.
  var clone = svg.cloneNode(true);
  var props = ['fill', 'fill-opacity', 'stroke', 'stroke-width',
    'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'opacity',
    'font-family', 'font-size', 'font-weight', 'font-style',
    'text-anchor', 'dominant-baseline', 'letter-spacing'];
  var liveNodes = svg.querySelectorAll('*');
  var cloneNodes = clone.querySelectorAll('*');
  for (var i = 0; i < liveNodes.length && i < cloneNodes.length; i++) {
    var computed;
    try { computed = window.getComputedStyle(liveNodes[i]); } catch (e) { continue; }
    var styleStr = '';
    for (var j = 0; j < props.length; j++) {
      var value = computed.getPropertyValue(props[j]);
      if (value && value !== 'normal' && value !== 'auto') styleStr += props[j] + ':' + value + ';';
    }
    if (styleStr) cloneNodes[i].setAttribute('style', styleStr);
  }
  if (!clone.getAttribute('xmlns')) clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  // Theme-matching background rect so dark-mode exports stay readable.
  try {
    var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    var viewBox = (svg.viewBox && svg.viewBox.baseVal) || null;
    rect.setAttribute('x', viewBox ? viewBox.x : 0);
    rect.setAttribute('y', viewBox ? viewBox.y : 0);
    rect.setAttribute('width', viewBox && viewBox.width ? viewBox.width : '100%');
    rect.setAttribute('height', viewBox && viewBox.height ? viewBox.height : '100%');
    rect.setAttribute('fill', _ivResolvedBg());
    rect.setAttribute('data-iv-bg', '1');
    clone.insertBefore(rect, clone.firstChild);
  } catch (e) {}
  return new XMLSerializer().serializeToString(clone);
}

function _ivSvgSize(svg) {
  var width = 0, height = 0;
  var viewBox = svg.viewBox && svg.viewBox.baseVal;
  if (viewBox && viewBox.width > 0) { width = viewBox.width; height = viewBox.height; }
  if (!width || !height) {
    var rect = svg.getBoundingClientRect();
    width = width || rect.width || 1200;
    height = height || rect.height || 800;
  }
  return { w: Math.ceil(width), h: Math.ceil(height) };
}

// Terminal failure reporter — the fallback chain bottoms out here so a
// dead-end never leaves the user with a silent no-op.
function _ivExportError() {
  try {
    if (typeof toast !== 'function') return;
    var msg = (typeof _ivExportErrStr !== 'undefined' &&
               (_ivExportErrStr[_ivLang] || _ivExportErrStr.en)) || 'Export failed';
    toast(msg, 'error');
  } catch (e) {}
}

function _ivDownloadSVG() {
  try {
    var svg = _ivFirstSvg();
    if (!svg) { _ivExportError(); return; }
    var xml = _ivSerializedSvg(svg);
    _ivSaveBlob(new Blob([xml], {type: 'image/svg+xml;charset=utf-8'}), _ivBaseName() + '.svg');
  } catch (e) { _ivExportError(); }
}

// onFail defaults to the terminal error toast so _ivSvgToPng is loop-free
// when used as the last link of the PNG chain; callers that still have a
// path left (e.g. the crisp-vector shortcut) pass _ivDomToPng instead.
function _ivSvgToPng(onFail) {
  var fail = onFail || _ivExportError;
  var svg = _ivFirstSvg();
  if (!svg) { fail(); return; }
  var size = _ivSvgSize(svg);
  var xml = _ivSerializedSvg(svg);
  var img = new Image();
  img.onload = function() {
    try {
      var canvas = document.createElement('canvas');
      canvas.width = size.w * 2;   // 2x for crisp rendering
      canvas.height = size.h * 2;
      var ctx = canvas.getContext('2d');
      ctx.fillStyle = _ivResolvedBg();
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      if (!canvas.toBlob) { fail(); return; }
      canvas.toBlob(function(blob) {
        if (blob) _ivSaveBlob(blob, _ivBaseName() + '.png');
        else fail();
      }, 'image/png');
    } catch (e) { fail(); }   // tainted canvas / toBlob SecurityError
  };
  img.onerror = function() { fail(); };   // malformed serialized SVG
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
}

function _ivHtml2Png() {
  // Screenshot the full visualization via html2canvas.
  // The CDN is permitted by the iframe CSP (script-src includes jsdelivr);
  // no data leaves the iframe (connect-src stays 'none').
  var run = function() {
    var dlWrap = document.getElementById('iv-dl-wrap');
    if (dlWrap) dlWrap.style.visibility = 'hidden';
    window.html2canvas(document.body, {backgroundColor: _ivResolvedBg(), scale: 2, logging: false})
      .then(function(canvas) {
        if (dlWrap) dlWrap.style.visibility = '';
        if (!canvas.toBlob) { _ivSvgToPng(); return; }
        canvas.toBlob(function(blob) {
          if (blob) _ivSaveBlob(blob, _ivBaseName() + '.png');
          else _ivSvgToPng();
        }, 'image/png');
      })
      .catch(function() {
        if (dlWrap) dlWrap.style.visibility = '';
        _ivSvgToPng();
      });
  };
  if (window.html2canvas) { run(); return; }
  var scriptEl = document.createElement('script');
  scriptEl.src = 'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js';
  scriptEl.onload = run;
  scriptEl.onerror = function() { _ivSvgToPng(); };
  document.head.appendChild(scriptEl);
}

function _ivDomToPng() {
  // Native-engine screenshot via SVG foreignObject. Unlike html2canvas this
  // resolves CSS variables and modern color functions, so dark/light themes
  // export exactly as rendered. Live canvases (Chart.js) are swapped for
  // images; current input states (sliders) are frozen into the clone.
  try {
    var pageWidth = Math.max(document.documentElement.scrollWidth, document.body.scrollWidth, document.body.offsetWidth);
    var pageHeight = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight, document.body.offsetHeight);
    var clone = document.documentElement.cloneNode(true);
    // Freeze live computed colors/opacity/transforms into the clone:
    // SVG-as-image restarts CSS animations at frame 0 (fade-ins would
    // export as opacity 0) and re-evaluates media queries (dark layouts
    // would export light). Inlining the live values prevents both.
    var PROPS = ['color', 'background-color', 'border-top-color',
      'border-right-color', 'border-bottom-color', 'border-left-color',
      'fill', 'stroke', 'box-shadow'];
    var liveNodes = document.documentElement.querySelectorAll('*');
    var cloneNodes = clone.querySelectorAll('*');
    for (var n = 0; n < liveNodes.length && n < cloneNodes.length; n++) {
      try {
        var computed = window.getComputedStyle(liveNodes[n]);
        cloneNodes[n].style.opacity = computed.opacity;
        if (computed.visibility !== 'visible') cloneNodes[n].style.visibility = computed.visibility;
        if (computed.transform && computed.transform !== 'none') cloneNodes[n].style.transform = computed.transform;
        for (var pi = 0; pi < PROPS.length; pi++) {
          var propValue = computed.getPropertyValue(PROPS[pi]);
          if (propValue) cloneNodes[n].style.setProperty(PROPS[pi], propValue);
        }
      } catch (e) {}
    }
    var noAnimStyle = document.createElement('style');
    noAnimStyle.textContent = '* { animation: none !important; transition: none !important; }';
    var headEl = clone.querySelector('head');
    if (headEl) { headEl.appendChild(noAnimStyle); } else { clone.appendChild(noAnimStyle); }
    var junkNodes = clone.querySelectorAll('#iv-dl-wrap, script');
    for (var i = 0; i < junkNodes.length; i++) {
      if (junkNodes[i].parentNode) junkNodes[i].parentNode.removeChild(junkNodes[i]);
    }
    var liveCanvases = document.querySelectorAll('canvas');
    var cloneCanvases = clone.querySelectorAll('canvas');
    for (var j = 0; j < liveCanvases.length && j < cloneCanvases.length; j++) {
      try {
        var imgEl = document.createElement('img');
        imgEl.src = liveCanvases[j].toDataURL('image/png');
        var rect = liveCanvases[j].getBoundingClientRect();
        var styleStr = (cloneCanvases[j].getAttribute('style') || '') + ';width:' + rect.width + 'px;height:' + rect.height + 'px;';
        imgEl.setAttribute('style', styleStr);
        if (cloneCanvases[j].getAttribute('class')) imgEl.setAttribute('class', cloneCanvases[j].getAttribute('class'));
        cloneCanvases[j].parentNode.replaceChild(imgEl, cloneCanvases[j]);
      } catch (e) {}
    }
    var liveInputs = document.querySelectorAll('input');
    var cloneInputs = clone.querySelectorAll('input');
    for (var k = 0; k < liveInputs.length && k < cloneInputs.length; k++) {
      try {
        cloneInputs[k].setAttribute('value', liveInputs[k].value);
        if (liveInputs[k].checked) cloneInputs[k].setAttribute('checked', 'checked');
      } catch (e) {}
    }
    var bg = _ivResolvedBg();
    clone.style.background = bg;
    var xml = new XMLSerializer().serializeToString(clone);
    var svgWrapper = '<svg xmlns="http://www.w3.org/2000/svg" width="' + pageWidth + '" height="' + pageHeight + '">'
      + '<foreignObject width="100%" height="100%">' + xml + '</foreignObject></svg>';
    var img = new Image();
    img.onload = function() {
      var canvas = document.createElement('canvas');
      canvas.width = pageWidth * 2;
      canvas.height = pageHeight * 2;
      var ctx = canvas.getContext('2d');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      try {
        canvas.toBlob(function(blob) {
          if (blob) { _ivSaveBlob(blob, _ivBaseName() + '.png'); } else { _ivHtml2Png(); }
        }, 'image/png');
      } catch (e) { _ivHtml2Png(); }
    };
    img.onerror = function() { _ivHtml2Png(); };
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgWrapper);
  } catch (e) { _ivHtml2Png(); }
}

function _ivDownloadPNG() {
  // Pure/dominant SVG: crisp vector rasterization.
  // HTML or mixed layouts: native foreignObject screenshot (theme-faithful);
  // html2canvas remains as a fallback (e.g. Safari foreignObject taint).
  var svg = _ivFirstSvg();
  if (svg) {
    try {
      var rect = svg.getBoundingClientRect();
      var bodyWidth = document.body.scrollWidth || 1;
      var bodyHeight = document.body.scrollHeight || 1;
      // Crisp vector shortcut; if it fails, fall back to the DOM screenshot
      // rather than dead-ending.
      if ((rect.width * rect.height) / (bodyWidth * bodyHeight) >= 0.5) { _ivSvgToPng(_ivDomToPng); return; }
    } catch (e) { _ivSvgToPng(_ivDomToPng); return; }
  }
  _ivDomToPng();
}

function _ivDownload() {
  // Strip download button + overflow:hidden for standalone use.
  var dlWrap = document.getElementById('iv-dl-wrap');
  if (dlWrap) dlWrap.remove();

  // Serialize from a clone so we can relocate model-imported scripts
  // without mutating the live iframe. enqueueScript appended each
  // imported script tags to head for sequenced execution during streaming
  // — but in a fresh standalone load, head scripts run BEFORE the body
  // is parsed, so any getElementById('chart-canvas') etc. returns null.
  // Move tagged scripts to the end of <body> so they execute after the
  // canvases / DOM nodes they reference.
  var docClone = document.documentElement.cloneNode(true);
  var headClone = docClone.querySelector('head');
  var bodyClone = docClone.querySelector('body');
  if (headClone && bodyClone) {
    var imported = headClone.querySelectorAll('script[data-iv-imported="1"]');
    for (var i = 0; i < imported.length; i++) {
      bodyClone.appendChild(imported[i]);
    }
  }
  var html = '<!DOCTYPE html>\\n' + docClone.outerHTML;

  if (dlWrap) document.body.appendChild(dlWrap);
  html = html.replace('html, body { overflow: hidden; }', '');

  var fileName = (document.title || 'visualization').replace(/[<>:"\\/|?*]+/g, '-').replace(/\s+/g, ' ').trim();
  if (!fileName) fileName = 'visualization';
  // Cap at 200 chars to stay under the Windows 255-char filename limit.
  if (fileName.length > 200) fileName = fileName.substring(0, 200).trim();
  fileName += '.html';

  var blob = new Blob([html], {type: 'text/html;charset=utf-8'});
  var url = URL.createObjectURL(blob);

  if (_ivIsIOS) {
    // iOS — deferred click + "Load failed" error suppression.
    setTimeout(function() {
      var _origOnerror = window.onerror;
      window.onerror = function(msg) {
        if (typeof msg === 'string' && msg.indexOf('Load failed') !== -1) return true;
        if (_origOnerror) return _origOnerror.apply(this, arguments);
      };
      var suppressLoadError = function(ev) {
        var message = ev && (ev.message || (ev.reason && ev.reason.message) || '');
        if (message.indexOf('Load failed') !== -1) { ev.preventDefault(); ev.stopImmediatePropagation(); return true; }
      };
      window.addEventListener('error', suppressLoadError, true);
      window.addEventListener('unhandledrejection', suppressLoadError, true);

      var link = document.createElement('a');
      link.style.display = 'none';
      link.href = url;
      link.download = fileName;
      // No target="_blank" on iOS — strands PWA users on a blob page.
      document.body.appendChild(link);
      link.click();

      // Restore original handlers after 60s.
      setTimeout(function() {
        window.onerror = _origOnerror;
        window.removeEventListener('error', suppressLoadError, true);
        window.removeEventListener('unhandledrejection', suppressLoadError, true);
        URL.revokeObjectURL(url);
        link.remove();
      }, 60000);
    }, 0);
  } else {
    // Desktop / Android — straightforward blob download.
    var link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    // Safety net: new tab if the iframe sandbox blocks downloads.
    link.target = '_blank';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    setTimeout(function() { link.remove(); URL.revokeObjectURL(url); }, 60000);
  }
}
</script>
"""


# ---------------------------------------------------------------------------
# Happy chime on live-stream completion
# ---------------------------------------------------------------------------
# Injected into BODY_SCRIPTS via a /*__CHIME_BLOCK__*/ placeholder so the
# ``chime`` valve can strip it out entirely when disabled — no bytes
# shipped, not just a silent no-op. finalize() calls playDoneSound() inside
# a ``typeof playDoneSound === 'function'`` guard, so omission is safe.
# ---------------------------------------------------------------------------

# !! SRCDOC SAFETY !!  Do NOT write the literal tokens <!-- , --> ,
# <![CDATA[ , ]]> , <script> or </script> ANYWHERE in this body —
# not even inside JS comments. See THEME_DETECTION_SCRIPT for full rationale.
CHIME_SCRIPT = """
// --- Happy chime ---
// C-major arpeggio (C5 → E5 → G5) on sine oscillators with exponential
// decay. ~300 ms, gentle volume. Silent no-op if AudioContext is still
// suspended (no prior user gesture).
var _ivAudioCtx = null;
function playDoneSound() {
  try {
    var AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    if (!_ivAudioCtx) _ivAudioCtx = new AudioCtx();
    var ctx = _ivAudioCtx;
    if (ctx.state === 'suspended') { try { ctx.resume(); } catch(e) {} }
    var now = ctx.currentTime;
    var notes = [523.25, 659.25, 783.99]; // C5, E5, G5
    notes.forEach(function(freq, i) {
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = freq;
      var start = now + i * 0.09;
      var duration = 0.35;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.16, start + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
      osc.connect(gain).connect(ctx.destination);
      osc.start(start);
      osc.stop(start + duration + 0.02);
    });
  } catch(e) {}
}
"""

# ---------------------------------------------------------------------------
# STRICT-mode script — strip query params from openLink / window.open /
# <a href>. Supplementary hygiene only; the real exfil blocker is the
# CSP connect-src directive. Paths, fragments, and location.assign are
# not intercepted.
# ---------------------------------------------------------------------------

# !! SRCDOC SAFETY !!  Do NOT write the literal tokens <!-- , --> ,
# <![CDATA[ , ]]> , <script> or </script> ANYWHERE in this body —
# not even inside JS comments. See THEME_DETECTION_SCRIPT for full rationale.
STRICT_SECURITY_SCRIPT = """
<script>
(function() {
  function stripParams(rawUrl) {
    try { var parsed = new URL(rawUrl, location.href); parsed.search = ''; return parsed.toString(); }
    catch(e) { return rawUrl; }
  }

  // Override openLink to strip query/hash parameters
  var _origOpenLink = window.openLink;
  window.openLink = function(url) {
    _origOpenLink(stripParams(url));
  };

  // Override window.open to strip query parameters
  var _origOpen = window.open;
  window.open = function(url) {
    arguments[0] = stripParams(url);
    return _origOpen.apply(this, arguments);
  };

  // Strip params from all existing and future <a> tags
  function sanitizeLinks(root) {
    (root.querySelectorAll ? root : document).querySelectorAll('a[href]').forEach(function(anchor) {
      anchor.href = stripParams(anchor.href);
    });
  }
  sanitizeLinks(document);
  new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
      mutation.addedNodes.forEach(function(node) { if (node.nodeType === 1) sanitizeLinks(node); });
    });
  }).observe(document.body, { childList: true, subtree: true });
})();
</script>
"""

# ---------------------------------------------------------------------------
# STREAMING mode — text-marker observer (CodeBlock-free)
# ---------------------------------------------------------------------------
# Model emits plain-text @@@VIZ-START … @@@VIZ-END markers (NOT a code
# fence — that path routed through CodeMirror's virtualizer and lost
# content on scroll / refresh). Markdown renders them as ordinary
# paragraph/html tokens, so nothing we scan goes through CodeBlock.
#
# Observer loop:
#   1. Find enclosing message via frame.closest('[id^="message-"]').
#   2. Read msg.textContent (skipping <details type="tool_calls"> etc).
#   3. Regex-extract the idx-th @@@VIZ-START … @@@VIZ-END block.
#   4. Safe-cut partial HTML, reconcile into #iv-render.
#   5. Walk the message DOM to hide the raw markers + between-marker
#      content inline (display:none !important).
#
# idx comes from the embed container id "{messageId}-embeds-{N}", so
# multiple visualizations in the same message claim in order.
#
# Requires iframe Sandbox Allow Same Origin.
# ---------------------------------------------------------------------------

# !! SRCDOC SAFETY !!  Do NOT write the literal tokens <!-- , --> ,
# <![CDATA[ , ]]> , <script> or </script> ANYWHERE in this body —
# not even inside JS comments. See THEME_DETECTION_SCRIPT for full rationale.
# This is the script that broke in 2.1.0–2.1.2 when a comment cleanup
# accidentally introduced literal <!-- and <script> inside JS comments.
STREAMING_OBSERVER_SCRIPT = """
<script>
(function() {
  'use strict';
  // Markers must match SKILL.md. Chosen so markdown never treats them
  // as a code fence (would put CodeMirror in the loop).
  var START_MARK = '@@@VIZ-START';
  var END_MARK = '@@@VIZ-END';

  // Stash the original text when we blank a node in place — wrapping
  // breaks Svelte's tracked refs, but blanked nodes still need to
  // surface the marker substring to the state machine.
  //
  // The store lives on the PARENT window so every visualizer iframe in
  // the page shares it: on a multi-visualization message, a sibling
  // embed must still see the original text of nodes we blanked (the
  // END marker included), or its marker state machine desyncs and it
  // mis-hides prose. Keys are parent-document text nodes, so entries
  // die with the DOM (WeakMap). Falls back to a local store when the
  // parent is unreachable (no same-origin — observer bails anyway).
  var _ivOriginalText = null;
  try {
    var _sharedMap = parent.__ivChatOriginalText;
    if (!_sharedMap || typeof _sharedMap.get !== 'function' ||
        typeof _sharedMap.set !== 'function' || typeof _sharedMap.has !== 'function') {
      parent.__ivChatOriginalText = new parent.WeakMap();
    }
    _ivOriginalText = parent.__ivChatOriginalText;
  } catch(e) {
    _ivOriginalText = (typeof WeakMap !== 'undefined') ? new WeakMap() : null;
  }
  // Blanked/trimmed-node registry (shared for the same reason) so the
  // restore pass in hideMarkerRange can revive nodes that stop being
  // marked. Companion WeakSet dedupes pushes across re-blank cycles.
  var _ivBlankedNodes = null;
  try {
    var _sharedList = parent.__ivChatBlankedNodes;
    if (!_sharedList || typeof _sharedList.push !== 'function' ||
        typeof _sharedList.splice !== 'function') {
      parent.__ivChatBlankedNodes = new parent.Array();
    }
    _ivBlankedNodes = parent.__ivChatBlankedNodes;
  } catch(e) { _ivBlankedNodes = []; }
  var _ivBlankedSet = null;
  try {
    var _sharedSet = parent.__ivChatBlankedSet;
    if (!_sharedSet || typeof _sharedSet.has !== 'function' ||
        typeof _sharedSet.add !== 'function') {
      parent.__ivChatBlankedSet = new parent.WeakSet();
    }
    _ivBlankedSet = parent.__ivChatBlankedSet;
  } catch(e) {
    _ivBlankedSet = (typeof WeakSet !== 'undefined') ? new WeakSet() : null;
  }
  // Store entries are { orig, written }: `orig` is the model's text,
  // `written` is what WE last wrote (empty string for a blank, the
  // prose-only remainder for a trim). Legacy plain-string entries from
  // older builds are read as { orig: entry, written: '' }.
  function getEffectiveText(textNode) {
    if (!textNode) return '';
    var value = textNode.nodeValue || '';
    if (!_ivOriginalText) return value;
    var entry = null;
    try { entry = _ivOriginalText.get(textNode); } catch(e) {}
    if (entry == null) return value;
    var orig = (typeof entry === 'object') ? entry.orig : entry;
    var written = (typeof entry === 'object') ? (entry.written || '') : '';
    // Surface the original ONLY while the node still holds what we
    // wrote — if Svelte overwrote it with fresh text, that text wins.
    if (value === written || value === '') return orig || '';
    return value;
  }
  function _ivStash(textNode, current, written) {
    if (!_ivOriginalText) return;
    try {
      var entry = _ivOriginalText.get(textNode);
      if (entry && typeof entry === 'object') {
        var prevWritten = entry.written || '';
        // Svelte handed the node new content since our last write —
        // that becomes the new original (streaming growth on the node).
        if (current !== prevWritten && current !== '') entry.orig = current;
        entry.written = written;
      } else if (typeof entry === 'string') {
        _ivOriginalText.set(textNode, { orig: (current !== '' ? current : entry), written: written });
      } else {
        _ivOriginalText.set(textNode, { orig: current, written: written });
      }
    } catch(e) {}
  }
  function _ivRegisterBlanked(textNode) {
    if (!_ivBlankedNodes) return;
    if (_ivBlankedSet) {
      try {
        if (_ivBlankedSet.has(textNode)) return;
        _ivBlankedSet.add(textNode);
      } catch(e) {}
    }
    _ivBlankedNodes.push(textNode);
  }
  function blankPreserving(textNode) {
    var current = textNode.nodeValue || '';
    if (current === '') return;  // already blanked, idempotent no-op
    _ivStash(textNode, current, '');
    try { textNode.nodeValue = ''; } catch(e) {}
    _ivRegisterBlanked(textNode);
  }
  // Trim a node that MIXES prose and marker content down to its
  // prose-only remainder ('Here is the chart: @@@VIZ-START' keeps
  // 'Here is the chart: '). Blanking such a node would destroy the
  // prose; hiding its block even more so.
  function trimPreserving(textNode, kept) {
    var current = textNode.nodeValue || '';
    if (current === kept) return;  // already trimmed, idempotent
    _ivStash(textNode, current, kept);
    try { textNode.nodeValue = kept; } catch(e) {}
    _ivRegisterBlanked(textNode);
  }
  // `+?` (not `*?`): require ≥1 body char so a freshly emitted
  // @@@VIZ-START with no content yet doesn't match an empty capture
  // and trip finalize("") via the idle timer.
  var BLOCK_RE = /@@@VIZ-START\\n?([\\s\\S]+?)(?:\\n?@@@VIZ-END|$)/g;

  // The DOM walker only skips tool/code (and reasoning, strict) detail
  // blocks once Open WebUI has tokenised them, which needs the closing
  // detail tag. While one is still streaming it is plain text, so its
  // body (tool args/results, and the render_visualization embeds
  // payload, a full copy of this script) leaks into the searchable
  // text and the matcher can lock onto a decoy marker. Strip those
  // ranges from the string too, mirroring the DOM filter: always
  // tool/code, reasoning only on the strict pass.
  function _ivStripDetailRanges(text, skipReasoning) {
    if (!text || text.indexOf('<details') === -1) return text || '';
    var stripRe = skipReasoning
      ? /type\\s*=\\s*"(?:tool_calls|code_execution|code_interpreter|reasoning)"/
      : /type\\s*=\\s*"(?:tool_calls|code_execution|code_interpreter)"/;
    var out = '', i = 0;
    while (i < text.length) {
      var open = text.indexOf('<details', i);
      if (open === -1) { out += text.slice(i); break; }
      var tagEnd = text.indexOf('>', open);
      if (tagEnd === -1) {
        // Opening tag still streaming (large embeds payload). Drop the
        // remainder if it is already a stripped type, else keep it.
        out += stripRe.test(text.slice(open)) ? text.slice(i, open) : text.slice(i);
        break;
      }
      if (!stripRe.test(text.slice(open, tagEnd + 1))) {
        out += text.slice(i, tagEnd + 1);  // kept type (reasoning, lax pass)
        i = tagEnd + 1;
        continue;
      }
      out += text.slice(i, open);  // text before the stripped block
      var depth = 1, j = tagEnd + 1;
      while (j < text.length && depth > 0) {
        var nextOpen = text.indexOf('<details', j);
        var nextClose = text.indexOf('</details>', j);
        if (nextClose === -1) { j = text.length; break; }  // not closed, strip to end
        if (nextOpen !== -1 && nextOpen < nextClose) { depth++; j = nextOpen + 8; }
        else { depth--; j = nextClose + 10; }
      }
      i = j;
    }
    return out;
  }

  // A real visualisation body always has at least one HTML element
  // open tag. Text-only decoys (this script's regex source, or the
  // skill example whose brackets are entity-escaped) do not, so we
  // refuse to finalise on them and keep scanning for the real block.
  function _ivLooksRenderable(html) {
    return /<[a-zA-Z]/.test(html || '');
  }

  var renderArea = document.getElementById('iv-render');
  if (!renderArea) return;

  // Require same-origin access to parent — otherwise show a helpful notice.
  var hasParentAccess = false;
  try { void parent.document.body; hasParentAccess = true; } catch(e) {}
  if (!hasParentAccess) {
    // _ivLang / _ivErrTitleStr / _ivErrBodyStr come from BODY_SCRIPTS
    // which runs before this observer script.
    var _lang = (typeof _ivLang !== 'undefined' && _ivLang) || 'en';
    var errTitle = (typeof _ivErrTitleStr !== 'undefined' &&
              (_ivErrTitleStr[_lang] || _ivErrTitleStr.en)) ||
             'Streaming visualization unavailable';
    var errBody = (typeof _ivErrBodyStr !== 'undefined' &&
              (_ivErrBodyStr[_lang] || _ivErrBodyStr.en)) ||
             'Open User Settings \u2192 Interface, scroll down, and enable ' +
             '"Allow iframe same origin" to use streaming mode.';
    function _esc(str) {
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    renderArea.innerHTML =
      '<div style="padding:16px 18px;border:0.5px solid var(--color-border-tertiary);' +
      'border-radius:var(--radius-md);background:var(--color-bg-secondary);' +
      'color:var(--color-text-primary);font-size:13px;line-height:1.5;">' +
      '<div style="font-weight:500;margin-bottom:6px;">' + _esc(errTitle) + '</div>' +
      '<div style="color:var(--color-text-secondary);">' + _esc(errBody) + '</div></div>';
    return;
  }

  // Claim: each tool call renders an embed at "{messageId}-embeds-{N}".
  // The N-th embed owns the N-th @@@VIZ-START/END pair in the message.

  var myMessage = null;
  var myIndex = null;        // this wrapper's position among embed siblings
  var lastRawText = '';
  var lastSafeRendered = '';
  var finalizeTimer = null;
  var finalized = false;

  function findMyMessage() {
    if (myMessage && parent.document.contains(myMessage)) return myMessage;
    try {
      var frame = window.frameElement;
      if (!frame) return null;
      // chat-assistant wrapper holds both streaming-time buffer and
      // settled content; response-content-container only populates on
      // rehydrate. Toolbar / suggestions row are siblings, not
      // descendants, so we won't scoop them up.
      myMessage = (frame.closest && frame.closest('.chat-assistant'))
        || (frame.closest && frame.closest('#response-content-container'))
        || (frame.closest && frame.closest('[id^="message-"]'))
        || null;
      return myMessage;
    } catch(e) { return null; }
  }

  function determineIndex() {
    if (myIndex !== null) return myIndex;
    try {
      var frame = window.frameElement;
      if (!frame) return null;
      var embedContainer = frame.closest && frame.closest('[id*="-embeds-"]');
      if (embedContainer) {
        var match = embedContainer.id.match(/-embeds-(\\d+)$/);
        if (match) { myIndex = parseInt(match[1], 10); return myIndex; }
      }
      // Fallback: count preceding sibling iframes within the same message.
      var msg = findMyMessage();
      if (msg) {
        var iframes = msg.querySelectorAll('iframe');
        for (var i = 0, count = 0; i < iframes.length; i++) {
          if (iframes[i] === frame) { myIndex = count; return myIndex; }
          count++;
        }
      }
    } catch(e) {}
    return null;
  }

  // Concatenate searchable text, skipping reasoning / tool-result
  // subtrees so our own result_context example markers (and any
  // @@@VIZ markers the model wrote in chain-of-thought) don't trip
  // the state machine.
  // skipReasoning=true (strict): rejects reasoning subtrees too —
  // this is the preferred pass, since it ignores planning markers
  // a model may have written in chain-of-thought.
  // skipReasoning=false (lax): scans reasoning. Used as fallback for
  // providers that wrap the actual visible response inside
  // <details type="reasoning"> (Bedrock-hosted Haiku 4.5).
  function getSearchableText(msg, skipReasoning) {
    var out = '';
    try {
      var walker = parent.document.createTreeWalker(
        msg, NodeFilter.SHOW_TEXT, {
          acceptNode: function(node) {
            var ancestor = node.parentNode;
            while (ancestor && ancestor !== msg) {
              if (ancestor.nodeType === 1) {
                // Markers inside code are documentation, not protocol:
                // a fenced example must neither become the rendered
                // block nor trip the hide state machine. cm-editor is
                // Open WebUI's CodeMirror-rendered fence container.
                if (ancestor.tagName === 'CODE' || ancestor.tagName === 'PRE') {
                  return NodeFilter.FILTER_REJECT;
                }
                try {
                  if (ancestor.classList && ancestor.classList.contains('cm-editor')) {
                    return NodeFilter.FILTER_REJECT;
                  }
                } catch(e) {}
                if (ancestor.tagName === 'DETAILS') {
                  var detailsType = ancestor.getAttribute && ancestor.getAttribute('type');
                  if (detailsType === 'tool_calls' ||
                      detailsType === 'code_execution' || detailsType === 'code_interpreter') {
                    return NodeFilter.FILTER_REJECT;
                  }
                  if (skipReasoning && detailsType === 'reasoning') {
                    return NodeFilter.FILTER_REJECT;
                  }
                }
                var ancestorId = ancestor.id || '';
                if (ancestorId && ancestorId.indexOf('-detail-group') !== -1) {
                  if (ancestorId.indexOf('tool') !== -1 || ancestorId.indexOf('code') !== -1) {
                    return NodeFilter.FILTER_REJECT;
                  }
                  if (skipReasoning) {
                    return NodeFilter.FILTER_REJECT;
                  }
                }
              }
              ancestor = ancestor.parentNode;
            }
            return NodeFilter.FILTER_ACCEPT;
          }
        }
      );
      var textNode;
      while ((textNode = walker.nextNode())) out += getEffectiveText(textNode);
    } catch(e) { return _ivStripDetailRanges(msg.textContent || '', skipReasoning); }
    return _ivStripDetailRanges(out, skipReasoning);
  }

  // Returns the regex match object for the idx-th block in `text`, or null.
  function _ivMatchBlock(text, idx) {
    BLOCK_RE.lastIndex = 0;
    var match, count = 0;
    while ((match = BLOCK_RE.exec(text)) !== null) {
      if (count === idx) return match;
      count++;
      if (match.index === BLOCK_RE.lastIndex) BLOCK_RE.lastIndex++;
    }
    return null;
  }

  // Strict pass first (skips reasoning); fall back to lax (scans
  // reasoning) only when strict yields no match. This way planning
  // markers a model wrote in chain-of-thought never win over a real
  // response — but providers that wrap the entire visible response
  // inside <details type="reasoning"> (Bedrock-routed Haiku 4.5) still
  // surface their content via the lax fallback.
  function _ivResolveBlock(idx) {
    var msg = findMyMessage();
    if (!msg) return null;
    var strict = _ivMatchBlock(getSearchableText(msg, true), idx);
    if (strict !== null) return strict;
    return _ivMatchBlock(getSearchableText(msg, false), idx);
  }

  function readSource() {
    var idx = determineIndex();
    if (idx === null) idx = 0;
    var match = _ivResolveBlock(idx);
    return match ? match[1] : null;
  }

  // Hide markers + between-marker content. Multi-pass walker, run
  // every tick, idempotent and self-correcting.
  //
  // Pass 1 marks candidate text nodes with an OUTSIDE/INSIDE state
  // machine (full markers, in-range nodes, and speculative partial
  // marker tails still streaming in).
  //
  // Pass 2 hides a block ancestor ONLY when every non-whitespace
  // text node inside it is marked. A container that also holds prose
  // must never be display:none'd — Open WebUI 0.10+ renders raw html
  // tokens as bare text nodes directly under the single div that
  // wraps the whole message content, and unconditionally hiding that
  // div nuked the entire response, prose included (issue #60). Marked
  // nodes whose block fails the check are blanked in place instead
  // (preserves Svelte's node refs). Text-free elements between the
  // first and last marked nodes (markdown 'space' tokens render as
  // empty margin divs) are swept too so the hidden source leaves no
  // gap. Inline `display:none !important` survives Svelte re-renders.
  //
  // Pass 3 un-hides / un-blanks anything no longer marked, so a
  // speculative partial hit (prose that transiently ends in '@@@')
  // self-corrects on a later tick instead of staying hidden forever.

  function hideEl(el) {
    if (!el || el.nodeType !== 1) return;
    if (el.getAttribute('data-iv-chat-hidden') !== '1') {
      el.setAttribute('data-iv-chat-hidden', '1');
    }
    try { el.style.setProperty('display', 'none', 'important'); } catch(e) {}
  }

  function wrapAndHideText(textNode) {
    var parentEl = textNode.parentNode;
    if (!parentEl) return;
    if (parentEl.nodeType === 1 &&
        parentEl.getAttribute &&
        parentEl.getAttribute('data-iv-chat-wrap') === '1') return;
    try {
      var ownerDoc = parentEl.ownerDocument || document;
      var wrapper = ownerDoc.createElement('span');
      wrapper.setAttribute('data-iv-chat-wrap', '1');
      wrapper.setAttribute('data-iv-chat-hidden', '1');
      wrapper.style.setProperty('display', 'none', 'important');
      parentEl.insertBefore(wrapper, textNode);
      wrapper.appendChild(textNode);
    } catch(e) {}
  }

  // Nearest ancestor that's a block-ish container — we prefer hiding
  // block elements over inline ones so we don't leave empty block
  // boxes visible. Stops at `stopAt` (the message root) — never hides
  // the message itself.
  function nearestBlockAncestor(el, stopAt) {
    var BLOCK = { P:1, DIV:1, SECTION:1, ARTICLE:1, BLOCKQUOTE:1,
                  PRE:1, H1:1, H2:1, H3:1, H4:1, H5:1, H6:1,
                  UL:1, OL:1, LI:1, TABLE:1 };
    var cur = el;
    while (cur && cur !== stopAt) {
      if (cur.nodeType === 1 && BLOCK[cur.tagName]) return cur;
      cur = cur.parentNode;
    }
    return null;
  }

  // Length of the longest non-empty prefix of START_MARK (>= '@@@')
  // that `text` ends with, or 0. Lets us hide a marker still streaming
  // in char-by-char (e.g. "@@@V") before the full token matches —
  // '@@@…' prefixes shared with a partial END_MARK are covered too.
  function partialStartSuffixLength(text) {
    for (var k = Math.min(text.length, START_MARK.length); k >= 3; k--) {
      if (START_MARK.substr(0, k) === text.substr(text.length - k)) return k;
    }
    return 0;
  }

  // Order-aware scan of ONE text node. Walks marker occurrences in
  // position order starting from `insideAtEntry`; returns the exit
  // state plus the text lying OUTSIDE all marker ranges (the marker
  // tokens themselves count as inside). Position order matters: a
  // node reading '…@@@VIZ-END @@@VIZ-START…' must exit INSIDE, or the
  // next visualization's body leaks into the chat as raw source. A
  // stray END with no open range swallows just the marker token and
  // stays OUTSIDE.
  function scanNodeText(text, insideAtEntry) {
    var kept = '';
    var pos = 0;
    var inside = insideAtEntry;
    while (pos < text.length) {
      if (inside) {
        var endIdx = text.indexOf(END_MARK, pos);
        if (endIdx === -1) { pos = text.length; break; }
        pos = endIdx + END_MARK.length;
        inside = false;
      } else {
        var startIdx = text.indexOf(START_MARK, pos);
        var strayEnd = text.indexOf(END_MARK, pos);
        if (strayEnd !== -1 && (startIdx === -1 || strayEnd < startIdx)) {
          kept += text.slice(pos, strayEnd);
          pos = strayEnd + END_MARK.length;
          continue;
        }
        if (startIdx === -1) { kept += text.slice(pos); break; }
        kept += text.slice(pos, startIdx);
        pos = startIdx + START_MARK.length;
        inside = true;
      }
    }
    return { inside: inside, kept: kept };
  }

  // allowWrap=false during streaming (wrapping a text node breaks
  // Svelte's tracked refs and stalls post-VIZ chunks), true on finalize.
  function hideMarkerRange(allowWrap) {
    var msg = findMyMessage();
    if (!msg) return;
    var myFrame = window.frameElement;

    // Never hide our own iframe's container.
    var myEmbedContainer = null;
    try { myEmbedContainer = myFrame && myFrame.closest('[id*="-embeds-"]'); }
    catch(e) {}
    var embedsRoot = null;
    try { embedsRoot = myFrame && myFrame.closest('[id$="-embeds-container"]'); }
    catch(e) {}

    // Skip reasoning / tool-result subtrees (same rationale as
    // getSearchableText).
    var walker;
    try {
      walker = parent.document.createTreeWalker(
        msg, NodeFilter.SHOW_TEXT, {
          acceptNode: function(node) {
            var ancestor = node.parentNode;
            while (ancestor && ancestor !== msg) {
              if (ancestor.nodeType === 1) {
                // Same code-skip as getSearchableText: markers inside
                // code/fences are documentation — never hide them or
                // let them drive the state machine.
                if (ancestor.tagName === 'CODE' || ancestor.tagName === 'PRE') {
                  return NodeFilter.FILTER_REJECT;
                }
                try {
                  if (ancestor.classList && ancestor.classList.contains('cm-editor')) {
                    return NodeFilter.FILTER_REJECT;
                  }
                } catch(e) {}
                if (ancestor.tagName === 'DETAILS') {
                  var detailsType = ancestor.getAttribute && ancestor.getAttribute('type');
                  if (detailsType === 'tool_calls' ||
                      detailsType === 'code_execution' || detailsType === 'code_interpreter') {
                    return NodeFilter.FILTER_REJECT;
                  }
                }
                var ancestorId = ancestor.id || '';
                if (ancestorId && ancestorId.indexOf('-detail-group') !== -1 &&
                    (ancestorId.indexOf('tool') !== -1 ||
                     ancestorId.indexOf('code') !== -1)) {
                  return NodeFilter.FILTER_REJECT;
                }
              }
              ancestor = ancestor.parentNode;
            }
            return NodeFilter.FILTER_ACCEPT;
          }
        }
      );
    } catch(e) { return; }

    // ---- Pass 1: mark nodes via the OUTSIDE/INSIDE state machine ----
    // `segments` tracks runs of consecutively marked nodes (broken by
    // any node with visible prose) so the element sweep below stays
    // scoped to actual marker ranges and never reaches across the
    // prose between two visualization pairs.
    var inside = false;
    var textNode;
    var walked = [];
    var hideNodes = [];
    var hideNodeSet = (typeof WeakSet !== 'undefined') ? new WeakSet() : null;
    // Nodes that MIX prose and marker content in one text node — they
    // get trimmed to the prose remainder instead of blanked/hidden.
    var partialTrims = [];
    var partialSet = (typeof WeakSet !== 'undefined') ? new WeakSet() : null;
    var segments = [];
    var currentSegment = null;
    function isMarked(node) {
      if (hideNodeSet) return hideNodeSet.has(node);
      return hideNodes.indexOf(node) !== -1;
    }
    function isTrimmed(node) {
      if (partialSet) return partialSet.has(node);
      for (var q = 0; q < partialTrims.length; q++) {
        if (partialTrims[q].node === node) return true;
      }
      return false;
    }
    function markNode(node) {
      hideNodes.push(node);
      if (hideNodeSet) hideNodeSet.add(node);
      if (!currentSegment) {
        currentSegment = { first: node, last: node };
        segments.push(currentSegment);
      } else {
        currentSegment.last = node;
      }
    }
    function trimNodeTo(node, kept) {
      partialTrims.push({ node: node, kept: kept });
      if (partialSet) partialSet.add(node);
      currentSegment = null;  // visible prose breaks the sweep segment
    }

    while ((textNode = walker.nextNode())) {
      if (embedsRoot && embedsRoot.contains(textNode)) continue;
      if (myEmbedContainer && myEmbedContainer.contains(textNode)) continue;
      walked.push(textNode);
    }

    for (var w = 0; w < walked.length; w++) {
      var node = walked[w];
      // getEffectiveText surfaces the original (pre-blank/pre-trim)
      // text so already-processed nodes still match.
      var text = getEffectiveText(node);
      var scan = scanNodeText(text, inside);
      inside = scan.inside;

      if (scan.kept !== text) {
        // Node overlaps a marker range. Fully consumed -> hide it;
        // mixed with prose -> trim to the prose-only remainder.
        if (scan.kept.trim() === '') markNode(node);
        else trimNodeTo(node, scan.kept);
        continue;
      }

      // Speculative partial marker tail: only the LAST streamed text
      // node can be a marker still arriving char-by-char, and once
      // this embed finalized nothing is left to stream. Without these
      // gates, settled prose that legitimately ends in '@@@' would be
      // re-hidden on every tick, unrecoverably.
      if (!finalized && !inside && w === walked.length - 1) {
        var partialLen = partialStartSuffixLength(text);
        if (partialLen > 0) {
          var keptHead = text.slice(0, text.length - partialLen);
          if (keptHead.trim() === '') markNode(node);
          else trimNodeTo(node, keptHead);
          continue;
        }
      }

      if (text.trim() !== '') currentSegment = null;
    }

    // ---- Pass 2: pick hideable elements ----
    var toHideEls = [];
    var toHideSet = (typeof WeakSet !== 'undefined') ? new WeakSet() : null;
    function noteHidden(el) {
      toHideEls.push(el);
      if (toHideSet) toHideSet.add(el);
    }
    function isNotedHidden(el) {
      if (toHideSet) return toHideSet.has(el);
      return toHideEls.indexOf(el) !== -1;
    }
    var failedEls = [];
    var failedSet = (typeof WeakSet !== 'undefined') ? new WeakSet() : null;
    function noteFailed(el) {
      failedEls.push(el);
      if (failedSet) failedSet.add(el);
    }
    function isNotedFailed(el) {
      if (failedSet) return failedSet.has(el);
      return failedEls.indexOf(el) !== -1;
    }

    // Structural safety: never collapse the message root, anything
    // that owns an iframe (ours or a sibling embed's), or the embeds
    // containers themselves.
    function safeToHide(el) {
      if (!el || el === msg) return false;
      try { if (myFrame && el.contains(myFrame)) return false; } catch(e) {}
      try {
        if (el.tagName === 'IFRAME' || el.querySelector('iframe') !== null) return false;
      } catch(e) { return false; }
      if (el.id && String(el.id).indexOf('-embeds') !== -1) return false;
      try {
        if (embedsRoot && (el.contains(embedsRoot) || embedsRoot.contains(el))) return false;
      } catch(e) {}
      return true;
    }

    // Content safety: every non-whitespace text node under `el` must
    // be marked — a block holding ANY prose is never hidden wholesale.
    function fullyMarked(el) {
      try {
        var check = parent.document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
        var node;
        while ((node = check.nextNode())) {
          var value = getEffectiveText(node);
          if (value === '' || value.trim() === '') continue;
          if (!isMarked(node)) return false;
        }
        return true;
      } catch(e) { return false; }
    }

    var toBlankText = [];
    for (var i = 0; i < hideNodes.length; i++) {
      var block = nearestBlockAncestor(hideNodes[i].parentNode, msg);
      if (block && isNotedHidden(block)) continue;
      if (block && !isNotedFailed(block) && safeToHide(block) && fullyMarked(block)) {
        noteHidden(block);
      } else {
        if (block && !isNotedFailed(block)) noteFailed(block);
        // Block also holds prose (or an iframe) — can't hide it.
        // Blank in place: nodeValue = '' preserves Svelte's refs.
        toBlankText.push(hideNodes[i]);
      }
    }

    // Sweep text-free elements strictly inside each marked segment —
    // markdown 'space' tokens render as empty margin divs that would
    // otherwise leave a gap where the source was. Segment-scoped so an
    // <hr>/<img> in the prose between two visualization pairs is never
    // touched. (compareDocumentPosition bitmasks: 4 = FOLLOWING,
    // 2 = PRECEDING.)
    // Text-free is NOT content-free: images, rules, form controls and
    // friends carry meaning without text nodes. Never sweep them (or
    // anything containing them) — segments can legitimately span such
    // an element when two pairs are separated only by, say, an image.
    var CONTENT_EL = { IMG:1, SVG:1, HR:1, CANVAS:1, VIDEO:1, AUDIO:1,
                       PICTURE:1, OBJECT:1, EMBED:1, INPUT:1, BUTTON:1,
                       SELECT:1, TEXTAREA:1, IFRAME:1, MATH:1 };
    var CONTENT_EL_SELECTOR = 'img,svg,hr,canvas,video,audio,picture,' +
                              'object,embed,input,button,select,textarea,iframe,math';
    if (segments.length > 0) {
      var allEls;
      try { allEls = msg.getElementsByTagName('*'); } catch(e) { allEls = []; }
      for (var s = 0; s < allEls.length; s++) {
        var candidate = allEls[s];
        if (isNotedHidden(candidate)) continue;
        if ((candidate.textContent || '').trim() !== '') continue;
        if (CONTENT_EL[String(candidate.tagName).toUpperCase()]) continue;
        try { if (candidate.querySelector(CONTENT_EL_SELECTOR) !== null) continue; }
        catch(e) { continue; }
        if (!safeToHide(candidate)) continue;
        for (var g = 0; g < segments.length; g++) {
          var seg = segments[g];
          var within = false;
          try {
            within = !candidate.contains(seg.first) &&
                     !candidate.contains(seg.last) &&
                     (seg.first.compareDocumentPosition(candidate) & 4) !== 0 &&
                     (seg.last.compareDocumentPosition(candidate) & 2) !== 0;
          } catch(e) {}
          if (within) { noteHidden(candidate); break; }
        }
      }
    }

    // ---- Pass 3: apply, then self-correct stale hides / blanks ----
    // Un-hide first: elements we hid on an earlier tick that are no
    // longer justified (partial-marker false positive, message edit,
    // Svelte re-render shuffling content).
    var previouslyHidden = [];
    try { previouslyHidden = msg.querySelectorAll('[data-iv-chat-hidden="1"]'); }
    catch(e) {}
    for (var p = 0; p < previouslyHidden.length; p++) {
      var hiddenEl = previouslyHidden[p];
      if (isNotedHidden(hiddenEl)) continue;
      if (hiddenEl.getAttribute('data-iv-chat-wrap') === '1') continue;
      try {
        hiddenEl.style.removeProperty('display');
        hiddenEl.removeAttribute('data-iv-chat-hidden');
      } catch(e) {}
    }

    for (var h = 0; h < toHideEls.length; h++) hideEl(toHideEls[h]);
    if (allowWrap) {
      // Finalize: wrap for tighter visual collapse (safe — Svelte
      // has stopped streaming chunks).
      for (var j = 0; j < toBlankText.length; j++) wrapAndHideText(toBlankText[j]);
    } else {
      for (var k = 0; k < toBlankText.length; k++) blankPreserving(toBlankText[k]);
    }
    for (var t = 0; t < partialTrims.length; t++) {
      trimPreserving(partialTrims[t].node, partialTrims[t].kept);
    }

    // Restore nodes that are no longer marked or trimmed (speculative
    // partials that turned out to be prose, message edits). Registry
    // is shared across sibling iframes — only judge nodes inside OUR
    // message; drop detached entries outright.
    if (_ivBlankedNodes) {
      for (var r = _ivBlankedNodes.length - 1; r >= 0; r--) {
        var blanked = _ivBlankedNodes[r];
        var connected = false;
        try {
          if (!blanked) connected = false;
          else if (typeof blanked.isConnected === 'boolean') {
            connected = blanked.isConnected;
          } else {
            var ownerDoc = blanked.ownerDocument;
            connected = !!(ownerDoc && ownerDoc.documentElement &&
                           ownerDoc.documentElement.contains(blanked));
          }
        } catch(e) {}
        if (!connected) {
          try { if (_ivBlankedSet) _ivBlankedSet.delete(blanked); } catch(e) {}
          _ivBlankedNodes.splice(r, 1);
          continue;
        }
        var inMyMsg = false;
        try { inMyMsg = msg.contains(blanked); } catch(e) {}
        if (!inMyMsg) continue;
        if (isMarked(blanked) || isTrimmed(blanked)) continue;
        // No longer ours to suppress: put the original back if the
        // node still holds our write; if Svelte already overwrote it
        // with fresh text, the fresh text wins — just drop the stash.
        try {
          var entry = _ivOriginalText ? _ivOriginalText.get(blanked) : null;
          if (entry != null) {
            var orig = (typeof entry === 'object') ? entry.orig : entry;
            var written = (typeof entry === 'object') ? (entry.written || '') : '';
            var currentValue = blanked.nodeValue || '';
            if (typeof orig === 'string' &&
                (currentValue === written || currentValue === '')) {
              blanked.nodeValue = orig;
            }
          }
        } catch(e) {}
        try { if (_ivOriginalText) _ivOriginalText.delete(blanked); } catch(e) {}
        try { if (_ivBlankedSet) _ivBlankedSet.delete(blanked); } catch(e) {}
        _ivBlankedNodes.splice(r, 1);
      }
    }
  }

  // Returns the last index where the parser is in TEXT state (not
  // mid-tag / mid-attr / mid-script / mid-CDATA). Browser auto-closes
  // open tags on innerHTML assignment — depth doesn't matter.
  var VOID_TAGS = {area:1,base:1,br:1,col:1,embed:1,hr:1,img:1,input:1,
                   link:1,meta:1,param:1,source:1,track:1,wbr:1};
  var RAW_TAGS = {script:1, style:1};

  function findSafeCut(text) {
    var i = 0, len = text.length;
    var state = 'TEXT';
    var quote = 0;
    var safeCut = 0;
    var tagNameBuf = '';
    var tagNameEnd = false;
    var inClosingTag = false;
    var selfClosing = false;
    var rawTag = '';  // active raw-text tag close-tag name

    while (i < len) {
      var ch = text.charCodeAt(i);

      if (state === 'RAW') {
        // Inside a raw-text element. Contents are NOT a safe cut — we
        // have to wait for the full close tag before flushing, otherwise
        // innerHTML would include partial JS/CSS.
        var marker = '</' + rawTag;
        if (text.substr(i, marker.length).toLowerCase() === marker) {
          var end = text.indexOf('>', i + marker.length);
          if (end === -1) break;
          rawTag = '';
          state = 'TEXT';
          i = end + 1;
          safeCut = i;
          continue;
        }
        i++; continue;
      }

      if (state === 'TEXT') {
        if (ch === 60 /* < */) {
          // The HTML-comment / CDATA opener tokens are built via
          // string concatenation. Embedding the raw forms in source
          // (even inside a JS comment) puts the enclosing srcdoc
          // parser into script-data-escape mode and breaks the IIFE.
          var CMT_OPEN = '<' + '!--';
          var CMT_CLOSE = '--' + '>';
          var CDATA_OPEN = '<' + '![CDATA[';
          if (text.substr(i, 4) === CMT_OPEN) {
            var ce = text.indexOf(CMT_CLOSE, i + 4);
            if (ce === -1) break;
            i = ce + 3;
            safeCut = i;
            continue;
          }
          if (text.substr(i, 9) === CDATA_OPEN) {
            // CDATA close — literal would put srcdoc parser into
            // script-data-escape mode; concatenate at runtime.
            var ke = text.indexOf(']]' + '>', i + 9);
            if (ke === -1) break;
            i = ke + 3;
            safeCut = i;
            continue;
          }
          state = 'TAG';
          tagNameBuf = ''; tagNameEnd = false;
          inClosingTag = false; selfClosing = false;
          i++; continue;
        }
        i++;
        safeCut = i;
        continue;
      }

      if (state === 'TAG') {
        if (ch === 47 /* / */) {
          if (tagNameBuf === '' && !tagNameEnd) { inClosingTag = true; i++; continue; }
          selfClosing = true; i++; continue;
        }
        if (ch === 62 /* > */) {
          var tagName = tagNameBuf.toLowerCase();
          if (!inClosingTag && !selfClosing && RAW_TAGS[tagName]) {
            state = 'RAW'; rawTag = tagName; i++; continue;
          }
          state = 'TEXT'; i++;
          safeCut = i;
          continue;
        }
        if (ch === 32 || ch === 9 || ch === 10 || ch === 13) {
          tagNameEnd = true; i++; state = 'ATTR_NAME'; continue;
        }
        if (!tagNameEnd) tagNameBuf += text.charAt(i);
        i++; continue;
      }

      if (state === 'ATTR_NAME') {
        if (ch === 62) {
          var tagName = tagNameBuf.toLowerCase();
          if (!inClosingTag && !selfClosing && RAW_TAGS[tagName]) {
            state = 'RAW'; rawTag = tagName; i++; continue;
          }
          state = 'TEXT'; i++;
          safeCut = i;
          continue;
        }
        if (ch === 47) { selfClosing = true; i++; continue; }
        if (ch === 61 /* = */) { state = 'ATTR_VAL_START'; i++; continue; }
        i++; continue;
      }

      if (state === 'ATTR_VAL_START') {
        if (ch === 32 || ch === 9 || ch === 10 || ch === 13) { i++; continue; }
        if (ch === 34) { quote = 34; state = 'ATTR_VAL_Q'; i++; continue; }
        if (ch === 39) { quote = 39; state = 'ATTR_VAL_Q'; i++; continue; }
        if (ch === 62) { state = 'ATTR_NAME'; continue; }
        state = 'ATTR_VAL_U'; i++; continue;
      }

      if (state === 'ATTR_VAL_Q') {
        if (ch === quote) { state = 'ATTR_NAME'; i++; continue; }
        i++; continue;
      }

      if (state === 'ATTR_VAL_U') {
        if (ch === 32 || ch === 9 || ch === 10 || ch === 13) { state = 'ATTR_NAME'; i++; continue; }
        if (ch === 62) { state = 'ATTR_NAME'; continue; }
        i++; continue;
      }
    }
    return safeCut;
  }

  // Incremental DOM reconciler — append-only, so existing elements
  // stay put (no reflow, no animation re-trigger). Attributes are
  // immutable between cuts (parser can't cut mid-tag).

  // Serializes script execution across the visualization — external
  // scripts load async while inline scripts run sync on insertion,
  // so we chain the insertions to enforce source order.
  var _ivScriptChain = Promise.resolve();
  var _ivEnqueuedScripts = Object.create(null);

  // FNV-1a content hash, used to dedupe script bodies across
  // reconciler branches that may re-encounter the same node.
  function _ivHashScript(str) {
    var hash = 2166136261;
    for (var i = 0; i < str.length; i++) {
      hash = (hash ^ str.charCodeAt(i)) >>> 0;
      hash = Math.imul(hash, 16777619) >>> 0;
    }
    return hash.toString(36);
  }

  function enqueueScript(incoming) {
    var src = incoming.getAttribute && incoming.getAttribute('src');
    var code = incoming.textContent || '';

    // Dedupe by src or content hash — reconciler may hit the same
    // script twice across streaming/finalize branches. Re-execution
    // would redeclare consts and double-wire listeners.
    var key = src ? ('src:' + src) : ('code:' + code.length + ':' + _ivHashScript(code));
    if (_ivEnqueuedScripts[key]) return;
    _ivEnqueuedScripts[key] = true;

    var attrs = [];
    for (var a = 0; a < incoming.attributes.length; a++) {
      attrs.push([incoming.attributes[a].name, incoming.attributes[a].value]);
    }
    // Each link in the chain is wrapped + .catch'd so a single bad
    // script (model wrote invalid JS, attribute name has weird chars,
    // appendChild's synchronous parse throws, etc.) can't kill the
    // chain and stall every script that follows.
    if (src) {
      _ivScriptChain = _ivScriptChain.then(function() {
        return new Promise(function(resolve) {
          try {
            var scriptEl = document.createElement('script');
            attrs.forEach(function(pair) {
              try { scriptEl.setAttribute(pair[0], pair[1]); } catch(_){}
            });
            // Tag for HTML export: _ivDownload moves these to end of body
            // so they execute after the model's canvases / DOM nodes exist.
            scriptEl.setAttribute('data-iv-imported', '1');
            scriptEl.onload = scriptEl.onerror = function() { resolve(); };
            document.head.appendChild(scriptEl);
          } catch(e) { resolve(); }
        });
      }).catch(function() {});
    } else {
      _ivScriptChain = _ivScriptChain.then(function() {
        try {
          var scriptEl = document.createElement('script');
          attrs.forEach(function(pair) {
            try { scriptEl.setAttribute(pair[0], pair[1]); } catch(_){}
          });
          scriptEl.setAttribute('data-iv-imported', '1');
          scriptEl.textContent = code;
          document.head.appendChild(scriptEl);
        } catch(e) {}
      }).catch(function() {});
    }
  }

  // importNode preserves SVG namespaces. Scripts go through
  // enqueueScript for source-order execution.
  function importAndAppend(parent, incoming) {
    var nodeType = incoming.nodeType;
    if (nodeType === 3) {
      parent.appendChild(document.createTextNode(incoming.textContent));
      return;
    }
    if (nodeType === 8) {
      parent.appendChild(document.createComment(incoming.textContent));
      return;
    }
    if (nodeType !== 1) return;
    var tagName = incoming.nodeName;
    var el;
    if (tagName === 'SCRIPT' || tagName === 'script') {
      enqueueScript(incoming);
      return;
    }
    // Shallow import preserves HTML/SVG namespace.
    el = document.importNode(incoming, false);
    parent.appendChild(el);
    for (var i = 0; i < incoming.childNodes.length; i++) {
      importAndAppend(el, incoming.childNodes[i]);
    }
  }

  function reconcile(existing, incoming) {
    var existingChildren = existing.childNodes;
    var incomingChildren = incoming.childNodes;
    // Source declares this element as a leaf (no children); any children
    // in the live DOM came from user scripts that target this element by
    // id (d3.select(...).append('svg'), new vis.Network(container, ...),
    // ECharts/Plotly/Vega painting into their target div, etc.). Trimming
    // them would erase the chart, so leave the leaf alone.
    if (incomingChildren.length === 0) return;
    var i;
    for (i = 0; i < incomingChildren.length; i++) {
      var incomingChild = incomingChildren[i];
      var existingChild = existingChildren[i];
      if (!existingChild) {
        importAndAppend(existing, incomingChild);
        continue;
      }
      // Position mismatch — rare with append-only, but guard.
      if (existingChild.nodeType !== incomingChild.nodeType ||
          (existingChild.nodeType === 1 && existingChild.nodeName !== incomingChild.nodeName)) {
        existing.removeChild(existingChild);
        var next = existingChildren[i] || null;
        var holder = document.createDocumentFragment();
        importAndAppend(holder, incomingChild);
        if (next) existing.insertBefore(holder, next);
        else existing.appendChild(holder);
        continue;
      }
      if (existingChild.nodeType === 3) {
        if (existingChild.nodeValue !== incomingChild.nodeValue) existingChild.nodeValue = incomingChild.nodeValue;
        continue;
      }
      if (existingChild.nodeType === 1) reconcile(existingChild, incomingChild);
    }
    // No outer trim — streaming source is append-only, so existing
    // children beyond incomingChildren.length are script-added (D3 SVG, vis-network
    // canvas/SVG, ECharts canvas, etc.). Removing them erases the chart
    // mid-render even when the script targeted a non-leaf container.
  }

  // withScripts=true materializes scripts (finalize path); false strips
  // them during streaming. Regex source is concatenated so the raw
  // open / close tokens never appear literally in this file.
  var _ivOpen = '<' + 'script';
  var _ivClose = '<' + '\\/script>';
  var _ivStripPaired = new RegExp(_ivOpen + '[\\\\s\\\\S]*?' + _ivClose, 'gi');
  var _ivStripOpen = new RegExp(_ivOpen + '[\\\\s\\\\S]*$', 'i');
  // Strip doc-level tags that models sometimes wrap VIZ content in.
  var _ivStripDocTags = new RegExp('<' + '!DOCTYPE[^>]*>|<' + '/?(?:html|head|body)[^>]*>', 'gi');

  // Open WebUI's chat sanitizer strips <style> but keeps the inner CSS
  // as text. Re-inflate consecutive bare CSS rules so the iframe can
  // apply them. Strict pattern + ≥2 adjacent rules guards against
  // accidental matches on JSON / object literals.
  var _ivCssRule = /[A-Za-z@.#:*\[\]>+\-,\s_~()='"&]+\{\s*(?:[A-Za-z-]+\s*:\s*[^;{}<>]+;\s*)+\}/g;
  function reinflateBareCSS(text) {
    if (/<style[\\s>]/i.test(text)) return text;
    _ivCssRule.lastIndex = 0;
    var matches = [], match;
    while ((match = _ivCssRule.exec(text)) !== null) {
      matches.push({ start: match.index, end: _ivCssRule.lastIndex });
      if (match.index === _ivCssRule.lastIndex) _ivCssRule.lastIndex++;
    }
    if (matches.length < 2) return text;
    // Group consecutive rules (separated by < 50 chars of whitespace)
    var groups = [], current = null;
    for (var i = 0; i < matches.length; i++) {
      if (current && matches[i].start - current.end < 50) current.end = matches[i].end;
      else { current = { start: matches[i].start, end: matches[i].end, count: 1 }; groups.push(current); }
      if (current.start !== matches[i].start) current.count = (current.count || 1) + 1;
    }
    // Process from last to first to preserve indices
    for (var g = groups.length - 1; g >= 0; g--) {
      var group = groups[g];
      var slice = text.substring(group.start, group.end);
      // Require multiple rules in the group
      var braces = slice.match(/\{/g);
      if (!braces || braces.length < 2) continue;
      text = text.substring(0, group.start) + '<style>' + slice + '</style>' + text.substring(group.end);
    }
    return text;
  }

  function renderSafeInto(text, withScripts) {
    var html = withScripts
      ? text
      : text.replace(_ivStripPaired, '').replace(_ivStripOpen, '');
    html = html.replace(_ivStripDocTags, '');
    html = reinflateBareCSS(html);
    var temp = document.createElement('div');
    try {
      temp.innerHTML = html;
    } catch(e) {
      // Fallback to full replace on any parse oddity.
      renderArea.innerHTML = html;
      return;
    }
    reconcile(renderArea, temp);
  }

  // ---- Fade-in animation for newly-complete elements ------------------
  function markAndAnimate(root) {
    var toAnimate = [];
    function visit(node, top) {
      if (!node || node.nodeType !== 1) return;
      var isSvgChild = node.ownerSVGElement != null;
      if ((top || isSvgChild || node.tagName === 'svg') && !node.hasAttribute('data-iv-faded')) {
        node.setAttribute('data-iv-faded', '1');
        toAnimate.push(node);
      }
      if (node.tagName === 'svg') {
        for (var child = node.firstElementChild; child; child = child.nextElementSibling) visit(child, false);
      }
    }
    for (var child = root.firstElementChild; child; child = child.nextElementSibling) visit(child, true);
    if (toAnimate.length === 0) return;
    requestAnimationFrame(function() {
      toAnimate.forEach(function(el) { el.classList.add('iv-fade-in'); });
    });
  }

  // ---- Height handling during streaming -------------------------------
  var heightRaf = 0;
  function scheduleHeight() {
    cancelAnimationFrame(heightRaf);
    heightRaf = requestAnimationFrame(function() {
      try { if (typeof reportHeight === 'function') reportHeight(); } catch(e) {}
    });
  }

  // ---- Finalize: run scripts, final height nudge ----------------------

  // Defensive post-finalize stripper. Catches marker leftovers and
  // orphan close-tags from unbalanced model HTML that ended up in
  // DOM regions the streaming-time hide skipped. Anchored on marker
  // substrings (no false positives on prose) and skips <code>/<pre>.
  function stripFinalizeArtifacts() {
    var msg = findMyMessage();
    if (!msg) return;
    var nodes = [];
    try {
      var walker = parent.document.createTreeWalker(
        msg, NodeFilter.SHOW_TEXT, null
      );
      var walkerNode;
      while ((walkerNode = walker.nextNode())) nodes.push(walkerNode);
    } catch(e) { return; }

    for (var i = 0; i < nodes.length; i++) {
      var textNode = nodes[i];
      var value = textNode.nodeValue || '';
      if (!value) continue;
      if (value.indexOf(START_MARK) === -1 && value.indexOf(END_MARK) === -1) continue;
      // Skip code/pre AND anything hideMarkerRange already hid: the
      // hide pass needs the marker text intact inside hidden blocks —
      // stripping it there would make a later pass consider the block
      // unjustified and un-hide the raw source.
      var ancestor = textNode.parentNode, isProtected = false;
      while (ancestor && ancestor !== msg) {
        if (ancestor.nodeType === 1) {
          if (ancestor.tagName === 'CODE' || ancestor.tagName === 'PRE') {
            isProtected = true; break;
          }
          if (ancestor.getAttribute &&
              ancestor.getAttribute('data-iv-chat-hidden') === '1') {
            isProtected = true; break;
          }
        }
        ancestor = ancestor.parentNode;
      }
      if (isProtected) continue;
      var cleaned = value
        .split(START_MARK).join('')
        .split(END_MARK).join('')
        .replace(/<\/[a-z][a-z0-9]*\s*>/gi, '');
      try { textNode.nodeValue = cleaned.replace(/^\s+|\s+$/g, '') ? cleaned : ''; }
      catch(e) {}
    }
  }

  function finalize(fullText) {
    if (finalized) return;
    if (!_ivLooksRenderable(fullText)) return;  // never latch on a non-HTML decoy
    finalized = true;
    // withScripts=true so the reconciler materializes script tags.
    renderSafeInto(fullText, true);
    // Multi-shot self-heal — Svelte may flush chunks several seconds
    // after finalize fires (slow networks, large messages, post-render
    // re-hydrations), restoring text nodes we hid. Run once
    // immediately, then every 1s for 30s; each run is idempotent and
    // cheap. ORDER MATTERS: re-assert hiding BEFORE stripping — the
    // stripper deletes marker text from visible nodes, and if it ran
    // first on a freshly restored flush the hide pass would no longer
    // find the markers and the raw source would stay visible.
    try { hideMarkerRange(false); } catch(e) {}
    try { stripFinalizeArtifacts(); } catch(e) {}
    var stripInterval = setInterval(function() {
      try { hideMarkerRange(false); } catch(e) {}
      try { stripFinalizeArtifacts(); } catch(e) {}
      _ivHealDirty = false;
    }, 1000);
    setTimeout(function() { clearInterval(stripInterval); }, 30000);
    hideLoader();
    markAndAnimate(renderArea);
    // Nudge the height reporter across layout settle.
    scheduleHeight();
    setTimeout(scheduleHeight, 120);
    setTimeout(scheduleHeight, 400);
    // Done announcement — only on live streams, not on rehydration.
    if (wasStreaming) {
      try {
        var label = (typeof _ivDoneStr !== 'undefined' &&
                     (_ivDoneStr[_ivLang] || _ivDoneStr.en)) || 'Visualization ready';
        if (typeof toast === 'function') toast(label, 'success');
      } catch(e) {}
      try { if (typeof playDoneSound === 'function') playDoneSound(); } catch(e) {}
    }
  }

  function isBlockClosed() {
    var idx = determineIndex();
    if (idx === null) idx = 0;
    var match = _ivResolveBlock(idx);
    return !!match && match[0].indexOf(END_MARK) !== -1;
  }

  // Tick skips its whole pipeline when the searchable text is
  // unchanged. A childList mutation sets forceHide=true so Svelte
  // rebuilds that preserve the text string still get re-hidden.
  var lastMsgText = null;
  var wasStreaming = false;
  var firstSeenLen = null;
  // Set by the mutation observers whenever the message subtree (or the
  // chat body's child list) changes; gates the post-finalize self-heal
  // so idle 400ms polls stay free.
  var _ivHealDirty = false;

  function tick(forceHide) {
    var msg = findMyMessage();
    if (!msg) return;

    if (finalized) {
      // Post-finalize self-heal: the observers and the 400ms poll stay
      // alive, and Svelte can flush restored text nodes long after
      // finalize (late chunks, rehydration, branch switches). Only act
      // when the message subtree actually mutated (cheap gate — no
      // text walk on idle polls), and hide BEFORE stripping so the
      // stripper never erases markers the hide pass still needs.
      if (_ivHealDirty) {
        try { hideMarkerRange(false); } catch(e) {}
        try { stripFinalizeArtifacts(); } catch(e) {}
        _ivHealDirty = false;
      }
      return;
    }

    // Lax: tick on any text change, including reasoning-block edits
    // (Bedrock-routed Haiku 4.5 streams the response inside reasoning).
    var currentText = getSearchableText(msg, false);
    var textChanged = currentText !== lastMsgText;
    lastMsgText = currentText;

    // Live-stream detection by GROWTH — the first-seen searchable
    // length never grows on refreshes of completed messages, so
    // wasStreaming stays false and we don't fire the done toast/chime.
    if (firstSeenLen === null) firstSeenLen = currentText.length;
    else if (!wasStreaming && currentText.length > firstSeenLen) {
      wasStreaming = true;
    }

    // allowWrap=false: streaming-safe (no text-node wrapping — would
    // break Svelte's diff and stall post-VIZ chunks).
    if (textChanged || forceHide) hideMarkerRange(false);

    // Source-dependent work only runs on actual changes.
    if (!textChanged) return;

    var raw = readSource();
    if (raw === null) return;
    if (raw === lastRawText) {
      scheduleFinalize(raw);
      return;
    }
    lastRawText = raw;

    var cut = findSafeCut(raw);
    var safe = raw.substring(0, cut);

    if (safe !== lastSafeRendered && safe.length > 0) {
      lastSafeRendered = safe;
      renderSafeInto(safe, false);
      markAndAnimate(renderArea);
      scheduleHeight();
    }

    scheduleFinalize(raw);
  }

  // Forces hideMarkerRange to re-run even when textContent is unchanged
  // — Svelte can rebuild a text node without altering its string value.
  function _ivHasChildListMutation(records) {
    if (!records) return false;
    for (var i = 0; i < records.length; i++) {
      if (records[i] && records[i].type === 'childList') return true;
    }
    return false;
  }

  // True when any mutation record touches OUR message subtree (or an
  // ancestor of it — a wholesale rebuild mutates the parent's child
  // list). Errs on true when the message can't be resolved.
  function _ivRecordsTouchMyMessage(records) {
    var msg = null;
    try { msg = findMyMessage(); } catch(e) {}
    if (!msg || !records) return true;
    for (var i = 0; i < records.length; i++) {
      var target = records[i] && records[i].target;
      if (!target) continue;
      try {
        if (msg.contains(target) || target.contains(msg)) return true;
      } catch(e) { return true; }
    }
    return false;
  }

  function scheduleFinalize(raw) {
    // Primary signal: @@@VIZ-END present → finalize instantly.
    // Fallback: 30s of completely stable source (user stopped
    // generation / model forgot END / network died). 30s is longer
    // than any realistic inter-chunk stall (Gemini 3.1 Pro 200-token
    // chunks, proxy buffering, etc) so we can't trip it mid-stream.
    clearTimeout(finalizeTimer);
    if (isBlockClosed() && _ivLooksRenderable(raw)) { finalize(raw); return; }
    finalizeTimer = setTimeout(function() {
      if (finalized) return;
      var latest = readSource();
      if (latest === null) return;
      if (!_ivLooksRenderable(latest)) return;
      if (isBlockClosed() || latest === raw) {
        finalize(latest);
      }
    }, 30000);
  }

  // ---- Inject fade-in + loader CSS into our OWN document -------------
  (function injectFadeCss() {
    var styleEl = document.createElement('style');
    styleEl.textContent =
      '@keyframes iv-fade-in-kf {' +
      '  from { opacity: 0; transform: translateY(2px); }' +
      '  to   { opacity: 1; transform: none; }' +
      '}' +
      '@keyframes iv-fade-in-svg-kf {' +
      '  from { opacity: 0; } to { opacity: 1; }' +
      '}' +
      '#iv-render .iv-fade-in { animation: iv-fade-in-kf 500ms ease-out both; }' +
      '#iv-render svg .iv-fade-in { animation: iv-fade-in-svg-kf 500ms ease-out both; }' +
      // Three pulsing dots + label shown while waiting for content.
      '@keyframes iv-pulse-kf {' +
      '  0%, 80%, 100% { opacity: 0.25; transform: scale(0.85); }' +
      '  40%           { opacity: 1;    transform: scale(1); }' +
      '}' +
      '.iv-loading {' +
      '  display: flex; flex-direction: column; align-items: center;' +
      '  justify-content: center; gap: 12px;' +
      '  padding: 48px 20px; min-height: 120px;' +
      '  color: var(--color-text-tertiary);' +
      '  font-size: 12px; letter-spacing: 0.02em;' +
      '}' +
      '.iv-loading-dots { display: inline-flex; gap: 8px; }' +
      '.iv-loading-dots span {' +
      '  width: 8px; height: 8px; border-radius: 50%;' +
      '  background: var(--color-text-tertiary);' +
      '  animation: iv-pulse-kf 1.4s infinite ease-in-out both;' +
      '}' +
      '.iv-loading-dots span:nth-child(1) { animation-delay: -0.32s; }' +
      '.iv-loading-dots span:nth-child(2) { animation-delay: -0.16s; }' +
      '.iv-loading-label { opacity: 0.6; }';
    document.head.appendChild(styleEl);
  })();

  // #iv-loader is rendered server-side as a sibling below #iv-render;
  // we only need to remove it on finalize.
  function hideLoader() {
    try {
      var loader = document.getElementById('iv-loader');
      if (loader && loader.parentNode) loader.parentNode.removeChild(loader);
    } catch(e) {}
  }

  // Defense in depth: outer observer on parent.document.body sees new
  // messages as chat scrolls / navigates; inner observer on our own
  // message catches every streaming text mutation; 400ms poll is a
  // safety net in case the observers miss anything.
  var innerObserver = null;
  function attachInnerObserver() {
    if (innerObserver) return;
    var msg = findMyMessage();
    if (!msg) return;
    try {
      innerObserver = new MutationObserver(function(records) {
        _ivHealDirty = true;
        try { tick(_ivHasChildListMutation(records)); } catch(e) {}
      });
      innerObserver.observe(msg, {
        childList: true, subtree: true, characterData: true
      });
    } catch(e) {}
  }

  function pollTick() {
    try { tick(false); } catch(e) {}
    try { attachInnerObserver(); } catch(e) {}
  }

  // Each bootstrap step is independently guarded — any one of them
  // failing must not prevent the polling timer from being installed.
  // Without the timer the iframe goes silently dormant.
  try { tick(false); } catch(e) {}
  try { attachInnerObserver(); } catch(e) {}
  try {
    new MutationObserver(function(records) {
      // childList touching OUR message can mean it was rebuilt
      // wholesale — flag the self-heal for that case too. Scoped so a
      // busy chat (other messages streaming) doesn't make every
      // settled viz iframe re-walk its message on each flush.
      var hasChildList = _ivHasChildListMutation(records);
      if (hasChildList && _ivRecordsTouchMyMessage(records)) _ivHealDirty = true;
      try { tick(hasChildList); } catch(e) {}
      try { attachInnerObserver(); } catch(e) {}
    }).observe(parent.document.body, {
      childList: true, subtree: true, characterData: true
    });
  } catch(e) {}
  setInterval(pollTick, 400);
})();
</script>
"""


# Kept for backwards compatibility in case anything references the old name
INJECTED_SCRIPTS = BODY_SCRIPTS


# ---------------------------------------------------------------------------
# srcdoc safety guard
#
# Every constant listed in _IFRAME_EMBEDDED_SCRIPTS below is concatenated
# into an iframe's srcdoc. Once that srcdoc is parsed by the browser's
# HTML5 tokenizer, the script-data state machine is sensitive to the
# following literal byte sequences appearing ANYWHERE inside a script
# body (including inside JS comments and string literals):
#
#   <!--           triggers "script data escape start"
#   -->            exits  "script data escaped"
#   <![CDATA[      same family of escape transitions
#   ]]>            same
#   <script        in escaped state, triggers "script data double escape start"
#   </script>      in double-escaped state, exits back to escaped — does
#                  NOT terminate the outer script
#
# When any of these appears inside a script body — even commented out —
# the outer script's actual `</script>` tag stops terminating the
# script. The IIFE then either never executes or executes incompletely,
# producing the silent failure mode we hit in 2.1.0–2.1.2 (every
# debugging path looks normal in isolation, but tick never runs).
#
# Always build these tokens via string concatenation in JS — never
# write them as literals, not even inside comments. The guard below
# raises at module load time so the plugin refuses to import if anyone
# ever reintroduces one.
_FORBIDDEN_SRCDOC_LITERALS = (
    "<!--",
    "-->",
    "<![CDATA[",
    "]]>",
    "<script",
    "</script",
)


def _assert_srcdoc_safe(name: str, body: str) -> None:
    """Refuse to load if `body` contains any HTML token that would
    confuse the iframe srcdoc's script-data state machine.

    Each script body is allowed exactly ONE legitimate `<script>` and
    one `</script>` — the wrapping tags themselves. Anything beyond
    that count is a reintroduction of the bug fixed in 2.1.3.
    """
    open_count = body.count("<script")
    close_count = body.count("</script")
    if open_count > 1 or close_count > 1:
        raise RuntimeError(
            f"Inline Visualizer: {name} contains an extra <script> or "
            f"</script> literal (open={open_count}, close={close_count}). "
            "These break HTML5 srcdoc parsing — build them via string "
            "concatenation in JS instead."
        )
    for tok in ("<!--", "-->", "<![CDATA[", "]]>"):
        if tok in body:
            raise RuntimeError(
                f"Inline Visualizer: {name} contains a literal {tok!r}. "
                "This puts the iframe srcdoc parser into script-data-escape "
                "mode and silently breaks the IIFE. Concatenate it in JS "
                "instead, even inside comments."
            )


_IFRAME_EMBEDDED_SCRIPTS = {
    "THEME_DETECTION_SCRIPT": THEME_DETECTION_SCRIPT,
    "BODY_SCRIPTS": BODY_SCRIPTS,
    "CHIME_SCRIPT": CHIME_SCRIPT,
    "STRICT_SECURITY_SCRIPT": STRICT_SECURITY_SCRIPT,
    "STREAMING_OBSERVER_SCRIPT": STREAMING_OBSERVER_SCRIPT,
}
for _name, _body in _IFRAME_EMBEDDED_SCRIPTS.items():
    _assert_srcdoc_safe(_name, _body)


DOWNLOAD_BUTTON = (
    '<div id="iv-dl-wrap">'
    '<button id="iv-dl-btn" onclick="_ivDlMenu(event)" title="Download">'
    '<svg viewBox="0 0 16 16"><path d="M8 2v8M5 7l3 3 3-3"/><path d="M3 12h10"/></svg>'
    "</button>"
    '<div id="iv-dl-menu" style="display:none;position:absolute;right:0;top:30px;z-index:60;'
    "background:rgba(28,30,34,.97);color:#fff;border:1px solid rgba(128,128,128,.35);"
    "border-radius:8px;box-shadow:0 4px 14px rgba(0,0,0,.3);min-width:104px;"
    'overflow:hidden;font-size:12px;font-family:system-ui,sans-serif;">'
    '<button class="iv-dl-item" onclick="_ivDownload()" style="display:block;width:100%;'
    "padding:7px 14px;background:transparent;border:none;cursor:pointer;"
    'text-align:left;color:inherit;font:inherit;">HTML</button>'
    '<button class="iv-dl-item" onclick="_ivDownloadSVG()" style="display:block;width:100%;'
    "padding:7px 14px;background:transparent;border:none;cursor:pointer;"
    'text-align:left;color:inherit;font:inherit;">SVG</button>'
    '<button class="iv-dl-item" onclick="_ivDownloadPNG()" style="display:block;width:100%;'
    "padding:7px 14px;background:transparent;border:none;cursor:pointer;"
    'text-align:left;color:inherit;font:inherit;">PNG</button>'
    "</div></div>"
)


# ---------------------------------------------------------------------------
# CSP generation per security level
# ---------------------------------------------------------------------------

_KNOWN_CDNS = (
    "https://cdnjs.cloudflare.com" " https://cdn.jsdelivr.net" " https://unpkg.com"
)

# The strict and balanced tags interpolate the (constant) CDN allowlist, so
# assemble them once at import instead of rebuilding the string on every render.
_CSP_STRICT = (
    '<meta http-equiv="Content-Security-Policy" content="'
    f"default-src 'self'; "
    f"script-src 'unsafe-inline' 'unsafe-eval' {_KNOWN_CDNS}; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'none'; "
    "form-action 'none'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "media-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    '">'
)
_CSP_BALANCED = (
    '<meta http-equiv="Content-Security-Policy" content="'
    f"default-src 'self'; "
    f"script-src 'unsafe-inline' 'unsafe-eval' {_KNOWN_CDNS}; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'none'; "
    "form-action 'none'; "
    "img-src * data: blob:; "
    "font-src 'self' data:; "
    "media-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    '">'
)


def _build_csp_tag(level: str) -> str:
    """Return a <meta> CSP tag for the given security level, or empty string.

    'unsafe-eval' is included because runtime expression compilers like
    Vega / Vega-Lite use new Function() internally and fail under
    strict CSP. 'unsafe-inline' is already present (inline scripts can
    execute arbitrary code), so adding 'unsafe-eval' does not
    meaningfully widen the attack surface — the real exfil blockers
    (connect-src, form-action, img-src, object-src) remain intact.
    """
    if level == "none":
        return ""

    if level == "offline":
        # STRICT minus the public CDN allowlist: nothing loads from
        # outside the Open WebUI origin. 'self' replaces the CDN hosts
        # so admins can serve pinned libraries from the instance's own
        # /static directory (srcdoc iframes inherit the parent page's
        # origin and base URL, so 'self' == the Open WebUI host and
        # paths like /static/iv-libs/chart.umd.min.js resolve locally).
        return (
            '<meta http-equiv="Content-Security-Policy" content="'
            "default-src 'self'; "
            "script-src 'unsafe-inline' 'unsafe-eval' 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'none'; "
            "form-action 'none'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "media-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            '">'
        )

    if level == "strict":
        return _CSP_STRICT

    # balanced: block outbound connections & forms, allow external images
    return _CSP_BALANCED


def _build_html(
    security_level: str = "strict",
    title: str = "Visualization",
    lang: str = "en",
    chime: bool = True,
) -> str:
    """Wrap the streaming visualization shell: empty render area + observer.

    The observer tails the parent chat DOM for an ``@@@VIZ-START`` …
    ``@@@VIZ-END`` plain-text block in the assistant message and renders
    its contents live into #iv-render.
    """
    csp_tag = _build_csp_tag(security_level)
    strict_script = (
        STRICT_SECURITY_SCRIPT if security_level in ("strict", "offline") else ""
    )
    safe_title = (
        title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    # Sanitize lang to a simple lowercase BCP-47 primary subtag.
    # Split on '-' first so "zh-CN" → "zh", not "zhcn".
    safe_lang = re.sub(r"[^a-z]", "", lang.split("-")[0].lower()[:5]) or "en"

    # Strip the chime script entirely when the valve is off — no bytes
    # shipped, no defined playDoneSound in the iframe. finalize()'s
    # typeof-function guard turns the missing definition into a no-op.
    body_scripts = BODY_SCRIPTS.replace(
        "/*__CHIME_BLOCK__*/", CHIME_SCRIPT if chime else ""
    )

    # Loader sits *below* the render area so content appears to flow
    # downward toward the pulsing dots — like a cursor following a pen.
    # The observer removes #iv-loader entirely on finalize().
    body_inner = (
        '<div id="iv-render"></div>\n'
        '<div id="iv-loader" class="iv-loading" aria-live="polite">'
        '<div class="iv-loading-dots"><span></span><span></span><span></span></div>'
        '<div class="iv-loading-label">Rendering visualization\u2026</div>'
        "</div>\n"
        f"{DOWNLOAD_BUTTON}\n"
        f"{body_scripts}"
        f"{STREAMING_OBSERVER_SCRIPT}"
        f"{strict_script}"
    )

    return (
        f'<!DOCTYPE html><html data-iv-lang="{safe_lang}" data-iv-build="{_IV_BUILD}"><head>'
        f"<title>{safe_title}</title>"
        f"{csp_tag}"
        f"<style>{THEME_CSS}\n{SVG_CLASSES}\n{BASE_STYLES}</style>"
        f'<script>try{{console.info("iv[build]","{_IV_BUILD}");}}catch(e){{}}</script>'
        f"{THEME_DETECTION_SCRIPT}"
        f"</head><body>\n{body_inner}\n</body></html>"
    )


# ---------------------------------------------------------------------------
# Valves (user-configurable settings)
# ---------------------------------------------------------------------------

# Developer reference for security levels:
#
#   STRICT   — Containment-oriented default. Blocks outbound fetch/XHR
#              (connect-src 'none'), form submissions, external images,
#              embedded objects, and base-URI hijacking. Injects a script
#              that strips URL query parameters from link navigation as
#              additional hygiene (query-only; does not cover path or
#              fragment, and does not intercept location.assign/replace).
#              Script execution within the visualization is intentionally
#              allowed ('unsafe-inline' + CDN allowlist) — this is
#              required for Chart.js, D3, and interactive visualizations.
#
#   BALANCED — Same as STRICT but allows external image loading (img-src *).
#              No URL parameter stripping. Note: img-src * permits
#              tracking pixels — this is an accepted privacy tradeoff
#              for visualizations that need external images.
#
#   NONE     — No CSP applied. Visualization can make arbitrary network
#              requests. Use only for visualizations that fetch live API
#              data (CORS restrictions still apply).
#
#   OFFLINE  — Zero outgoing connections of any kind. Same as STRICT but
#              the public CDN hosts are dropped from script-src and
#              'self' is allowed instead, so chart libraries must be
#              served by the Open WebUI instance itself (drop the pinned
#              files under its /static directory — see the README
#              section "Offline mode"). External scripts, images, fonts
#              and media are all blocked; only same-origin, data: and
#              blob: sources load. For air-gapped / privacy-hardened
#              deployments. URL parameter stripping is applied like in
#              STRICT.
#
# Limitations that apply to ALL levels:
# - Script execution is always permitted (required for core features).
# - When iframe Same-Origin is enabled at the platform level, JS inside
#   the visualization can access the parent Open WebUI page. No CSP
#   level can prevent this — it is controlled by the platform setting.


class Tools:
    """Inline Visualizer — renders interactive HTML/SVG in chat.

    Security is controlled via the ``security_level`` valve, which applies
    a Content Security Policy to the rendered iframe.  Defaults to STRICT,
    which blocks outbound network requests (fetch/XHR) and form submissions
    while allowlisting three public script CDNs.  OFFLINE additionally
    drops the CDN allowlist for zero external connections (self-hosted
    libraries under the instance's /static directory still load).
    Script execution is always permitted — it is required for interactive
    visualizations, Chart.js, and D3.  See the developer reference above
    for the full security model and its limitations.
    """

    class Valves(BaseModel):
        security_level: Literal["strict", "balanced", "none", "offline"] = Field(
            default="strict",
            description="Strict (default): blocks outbound fetch/XHR, images, and forms; scripts always allowed (3 public CDNs allowlisted). Offline: like Strict but with ZERO external connections — even the CDNs are blocked; libraries self-hosted under Open WebUI's /static folder still load (see README). Balanced: like Strict but also allows external images. None: no restrictions.",
        )
        chime: bool = Field(
            default=True,
            description="Play a soft three-note chime when a live-streamed visualization finishes. When off, the chime script is omitted from the iframe entirely (not shipped as a no-op).",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def visualize(
        self,
        title: str = "Visualization",
        __event_call__=None,
        __event_emitter__=None,
    ):
        """
        You need to call this tool before EVERY visualization you want to render.
        What this tool does: visualize() mounts an iframe sandbox directly in the chat.
        After this tool is called, the assistant must stream exactly one HTML/SVG visualization fragment between the plain-text delimiters @@@VIZ-START and @@@VIZ-END.
        The sandbox renders that fragment live for the user.

        Use this tool ONLY for EXPLICIT visualization requests.
        Do NOT use this tool proactively. Do NOT infer that a visualization would be helpful.
        **If the user did not explicitly ask for a visual artifact, do not call visualize().**
        Never use visualize() for ordinary assistant output.
        The chat you are responding in has a full Markdown, LaTeX, KaTeX and Mermaid rendering engine.
        Call visualize() ONLY when the user clearly and UNAMBIGUOUSLY, DIRECTLY, EXPLICITLY asked for a visual artifact (e.g. diagrams, charts, graphs, dashboards, illustrations, interactive explainers, etc.).

        IMPORTANT:
        BEFORE CALLING THIS TOOL, YOU MUST: Call view_skill("visualize") FIRST.
        You MUST call view_skill("visualize") first.
        The visualize skill contains a mandatory handbook/tutorial with important rules for rendering, layout, SVG setup, chart patterns, colors, interactivity, and common failure points.
        Never generate a visualization without reading the skill first.

        After calling this tool:
        In the assistant message that follows, emit exactly one visualization block:

        @@@VIZ-START
        <!-- HTML/SVG fragment only -->
        @@@VIZ-END

        Hard output rules:
        - Use the delimiters exactly: @@@VIZ-START and @@@VIZ-END.
        - Put each delimiter on its own line.
        - Emit exactly one @@@VIZ-START / @@@VIZ-END pair per tool call.
        - Do not wrap the visualization in Markdown code fences.
        - Do not use ```html, ```svg, ~~~, :::, or any other fenced block.
        - Emit a fragment only: no <!DOCTYPE>, no <html>, no <head>, no <body>.
        - Structure the fragment as: <style> first, visible content next, <script> last.
        - Do not describe the HTML/SVG source to the user. Describe what the visualization shows.

        :param title: Short descriptive title for the visualization.
        :return: Interactive rich embed rendered in the chat, with LLM context.
        """
        # Detect UI language via parent page JS (same pattern as PDF/Gamma actions)
        lang = "en"
        if __event_call__:
            try:
                lang_result = await __event_call__(
                    {
                        "type": "execute",
                        "data": {"code": """
return (() => {
  try {
    const stored = localStorage.getItem('locale')
                || localStorage.getItem('language')
                || localStorage.getItem('i18nextLng');
    if (stored) {
      const l = stored.split('-')[0].toLowerCase();
      if (l) return l;
    }
  } catch (e) {}
  try {
    return (navigator.language || navigator.userLanguage || 'en').split('-')[0].toLowerCase();
  } catch (e) {}
  return 'en';
})();
"""},
                    }
                )
                if isinstance(lang_result, str) and lang_result.strip():
                    lang = lang_result.strip()
            except Exception:
                pass

        html = _build_html(
            self.valves.security_level,
            title,
            lang,
            chime=self.valves.chime,
        )
        response = HTMLResponse(
            content=html,
            headers={"Content-Disposition": "inline"},
        )
        result_context = (
            f'Visualization wrapper "{title}" is mounted and waiting for content. '
            f"Now emit the HTML/SVG in your NEXT text response wrapped in the "
            f"TEXT delimiters @@@VIZ-START and @@@VIZ-END, each on their own line. "
            f"The wrapper will tail your stream and render live. These are PLAIN "
            f"TEXT markers — NOT a ``` code fence, NOT HTML tags, NOT a ::: fence. "
            f"Example:\n\n"
            f"    @@@VIZ-START\n"
            f'    <svg viewBox="0 0 680 240">…</svg>\n'
            f"    @@@VIZ-END\n\n"
            f"Write explanatory prose BEFORE and AFTER the block — do not describe "
            f"the HTML source itself. Emit exactly ONE @@@VIZ-START/@@@VIZ-END pair "
            f"for this tool call."
        )
        # Under native tool calling the embeds attached to the per-tool-call result item are not painted by the frontend,
        # whereas the message-level "embeds" channel is path-independent and always renders (it is the same channel legacy already uses).
        # Fall back to the original HTMLResponse return when no event emitter is available to preserve prior behavior.
        if __event_emitter__:
            await __event_emitter__({"type": "embeds", "data": {"embeds": [html]}})
            return result_context
        return response, result_context
