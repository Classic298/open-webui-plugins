"""
title: Inline Visualizer
author: Classic298
version: 1.4.0
description: Renders interactive HTML/SVG visualizations inline in chat. For design system instructions, the model should call view_skill("visualize").
"""

import re
from typing import Literal

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
  /* --- Common aliases (catch hallucinated variable names from shadcn/Tailwind) --- */
  --foreground: var(--color-text-primary);
  --background: var(--color-bg-primary);
  --muted-foreground: var(--color-text-secondary);
  --border: var(--color-border-tertiary);
  --surface-1: var(--color-bg-secondary);
  --surface-2: var(--color-bg-tertiary);
  --card: var(--color-bg-secondary);
  --card-foreground: var(--color-text-primary);
  --primary: #6c2eb9;
  --primary-foreground: #ffffff;
  --accent: var(--color-bg-tertiary);
  --accent-foreground: var(--color-text-primary);
  --muted: var(--color-bg-tertiary);
  --popover: var(--color-bg-secondary);
  --popover-foreground: var(--color-text-primary);
  --input: var(--color-border-tertiary);
  --ring: var(--color-border-secondary);
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
  --foreground: var(--color-text-primary);
  --background: var(--color-bg-primary);
  --muted-foreground: var(--color-text-secondary);
  --border: var(--color-border-tertiary);
  --surface-1: var(--color-bg-secondary);
  --surface-2: var(--color-bg-tertiary);
  --card: var(--color-bg-secondary);
  --card-foreground: var(--color-text-primary);
  --primary: #a78bfa;
  --primary-foreground: #1A1A1A;
  --accent: var(--color-bg-tertiary);
  --accent-foreground: var(--color-text-primary);
  --muted: var(--color-bg-tertiary);
  --popover: var(--color-bg-secondary);
  --popover-foreground: var(--color-text-primary);
  --input: var(--color-border-tertiary);
  --ring: var(--color-border-secondary);
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
button {
  background: transparent; border: 0.5px solid var(--color-border-secondary);
  border-radius: var(--radius-md); padding: 6px 14px; font-size: 13px;
  color: var(--color-text-primary); cursor: pointer; font-family: var(--font-sans);
}
button:hover { background: var(--color-bg-secondary); }
button.active { background: var(--color-bg-secondary); border-color: var(--color-border-primary); }
input[type="range"] {
  -webkit-appearance: none; width: 100%; height: 4px;
  background: var(--color-border-tertiary); border-radius: 2px; outline: none;
}
input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none; width: 18px; height: 18px; border-radius: 50%;
  background: var(--color-bg-primary); border: 0.5px solid var(--color-border-secondary); cursor: pointer;
}
select {
  background: var(--color-bg-secondary); border: 0.5px solid var(--color-border-tertiary);
  border-radius: var(--radius-md); padding: 6px 10px; font-size: 13px;
  color: var(--color-text-primary); font-family: var(--font-sans);
}
code {
  font-family: var(--font-mono); font-size: 13px; background: var(--color-bg-tertiary);
  padding: 2px 6px; border-radius: 4px;
}
"""

# ---------------------------------------------------------------------------
# Injected JavaScript — theme detection (head), height reporting & bridges (body)
# ---------------------------------------------------------------------------

# Runs in <head> BEFORE any user content so CSS variables resolve to the
# correct theme when model scripts read them at parse time.
# Also sets up a MutationObserver to react to live theme switches.
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
    // Re-render Chart.js instances with updated theme colors
    if (window.Chart && Chart.instances) {
      var s = getComputedStyle(document.documentElement);
      var tc = s.getPropertyValue('--color-text-secondary').trim();
      var gc = s.getPropertyValue('--color-border-tertiary').trim();
      Chart.defaults.color = tc;
      Chart.defaults.borderColor = gc;
      Object.values(Chart.instances).forEach(function(chart) {
        Object.values(chart.options.scales || {}).forEach(function(scale) {
          if (scale.ticks) scale.ticks.color = tc;
          if (scale.grid) scale.grid.color = gc;
        });
        var leg = (chart.options.plugins || {}).legend;
        if (leg && leg.labels) leg.labels.color = tc;
        chart.update();
      });
    }
  }

  try {
    var p = parent.document.documentElement;
    applyTheme(detectTheme(p));
    // Watch for live theme changes on the parent
    new MutationObserver(function() {
      applyTheme(detectTheme(p));
    }).observe(p, { attributes: true, attributeFilter: ['class', 'data-theme', 'style'] });
  } catch(e) {
    // No same-origin access — fall back to OS preference
    var mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
    if (mq) {
      applyTheme(mq.matches);
      mq.addEventListener('change', function(e) { applyTheme(e.matches); });
    }
  }
})();
</script>
"""

BODY_SCRIPTS = """
<script>

// --- Height reporting ---
var _rh_last = 0;          // last reported height
var _rh_consecutive = 0;   // consecutive small-growth reports
var _rh_raf = 0;           // rAF id for debouncing ResizeObserver

function reportHeight() {
  var b = document.body;
  // Measure SVG overflow (content beyond viewBox) before collapsing body,
  // since getBoundingClientRect needs normal layout.
  var svgOverflow = 0;
  document.querySelectorAll('svg[viewBox]').forEach(function(svg) {
    try {
      var bbox = svg.getBBox();
      var vb = svg.viewBox.baseVal;
      if (vb && vb.width > 0 && vb.height > 0) {
        var overflow = bbox.y + bbox.height - (vb.y + vb.height);
        if (overflow > 0) {
          var scale = svg.getBoundingClientRect().width / vb.width;
          svgOverflow += Math.ceil(overflow * scale);
        }
      }
    } catch(e) {}
  });
  // Temporarily collapse body so scrollHeight reflects actual content,
  // not the iframe's previously set height (fixes shrink-on-collapse).
  b.style.height = '0';
  var h = b.scrollHeight + svgOverflow;
  b.style.height = '';

  // Guard against feedback loops (e.g. content using 100vh + body padding).
  // Each cycle the iframe grows by a small fixed delta (typically body padding).
  // Detect 3+ consecutive small monotonic increases and stop reporting.
  var delta = h - _rh_last;
  if (_rh_last > 0 && delta > 0 && delta < 50) {
    _rh_consecutive++;
    if (_rh_consecutive >= 3) return;   // feedback loop — stop
  } else {
    _rh_consecutive = 0;                // large jump or shrink — legitimate change
  }

  _rh_last = h;
  parent.postMessage({ type: 'iframe:height', height: h }, '*');
}
window.addEventListener('load', reportHeight);
window.addEventListener('resize', reportHeight);
// Debounce ResizeObserver through rAF to avoid tight synchronous loops
new ResizeObserver(function() {
  cancelAnimationFrame(_rh_raf);
  _rh_raf = requestAnimationFrame(reportHeight);
}).observe(document.body);
// Explicitly handle <details> toggle — ResizeObserver misses this in some browsers
document.addEventListener('toggle', function() {
  _rh_consecutive = 0;     // user interaction — reset loop detector
  setTimeout(reportHeight, 50);
}, true);
// Reset loop detector on user interaction (clicks may change content height)
document.addEventListener('click', function() { _rh_consecutive = 0; }, true);

// --- Post-render fixes (theme defaults, overlap prevention) ---
window.addEventListener('load', function() {
  // Chart.js theme defaults + legend overflow prevention
  if (window.Chart) {
    var s = getComputedStyle(document.documentElement);
    var textColor = s.getPropertyValue('--color-text-secondary').trim();
    var gridColor = s.getPropertyValue('--color-border-tertiary').trim();
    Chart.defaults.color = textColor;
    Chart.defaults.borderColor = gridColor;
    Chart.defaults.plugins.legend.labels.color = textColor;
    Chart.defaults.plugins.legend.maxHeight = 120;
    Chart.defaults.plugins.legend.labels.boxWidth = 12;
    Chart.defaults.plugins.legend.labels.font = { size: 11 };
    // Re-render existing charts with corrected legend constraints
    Object.values(Chart.instances || {}).forEach(function(chart) {
      var leg = chart.options.plugins && chart.options.plugins.legend;
      if (leg) {
        leg.maxHeight = leg.maxHeight || 120;
        if (leg.labels) {
          leg.labels.boxWidth = leg.labels.boxWidth || 12;
        }
      }
      chart.update();
    });
  }

  // SVG axis-label overlap — stagger only labels in a tight horizontal band
  // (skips complex diagrams where text is scattered across the full canvas)
  document.querySelectorAll('svg').forEach(function(svg) {
    var texts = Array.from(svg.querySelectorAll('text'));
    if (texts.length < 4) return;
    // Collect bounding info for all visible texts
    var items = [];
    texts.forEach(function(t) {
      var r = t.getBoundingClientRect();
      if (r.width < 1) return;
      items.push({ el: t, rect: r, cx: r.left + r.width / 2, cy: r.top + r.height / 2 });
    });
    if (items.length < 4) return;
    // Only stagger texts that sit in a narrow y-band (axis labels).
    // If texts span a wide vertical range, this is a diagram — skip entirely.
    var minY = Infinity, maxY = -Infinity;
    items.forEach(function(it) {
      if (it.cy < minY) minY = it.cy;
      if (it.cy > maxY) maxY = it.cy;
    });
    var ySpan = maxY - minY;
    if (ySpan < 1) return;
    // Find the y-band with the most texts (likely the axis row)
    var bandSize = 30; // px tolerance for "same row"
    var bestBand = [], bestCount = 0;
    items.forEach(function(anchor) {
      var band = items.filter(function(it) { return Math.abs(it.cy - anchor.cy) < bandSize; });
      if (band.length > bestCount) { bestCount = band.length; bestBand = band; }
    });
    // Only proceed if the best band has 3+ labels AND doesn't cover most texts
    // (if most texts are in the band, it's likely a simple chart; otherwise a diagram)
    if (bestBand.length < 3 || bestBand.length === items.length && ySpan > 60) return;
    // Use only the best-band texts for grouping/stagger
    var groups = [];
    bestBand.forEach(function(it) {
      for (var i = 0; i < groups.length; i++) {
        if (Math.abs(groups[i].cx - it.cx) < 15) {
          groups[i].items.push(it);
          return;
        }
      }
      groups.push({ cx: it.cx, items: [it] });
    });
    if (groups.length < 3) return;
    groups.sort(function(a, b) { return a.cx - b.cx; });
    var needsStagger = false;
    for (var i = 0; i < groups.length - 1; i++) {
      var maxR = 0, minL = Infinity;
      groups[i].items.forEach(function(it) { if (it.rect.right > maxR) maxR = it.rect.right; });
      groups[i+1].items.forEach(function(it) { if (it.rect.left < minL) minL = it.rect.left; });
      if (maxR > minL - 2) { needsStagger = true; break; }
    }
    if (needsStagger) {
      for (var i = 1; i < groups.length; i += 2) {
        groups[i].items.forEach(function(it) {
          var cy = parseFloat(it.el.getAttribute('y') || 0);
          it.el.setAttribute('y', String(cy + 18));
        });
      }
    }
  });

  setTimeout(reportHeight, 100);
});

// --- sendPrompt bridge (requires iframe Sandbox Allow Same Origin) ---
function sendPrompt(text) {
  try {
    // Use Open WebUI's native postMessage protocol.
    // submitPrompt automatically queues the message if the AI is still generating.
    parent.postMessage({ type: 'input:prompt:submit', text: text }, '*');
  } catch(e) { /* iframe sandbox restriction */ }
}

// --- Open link in parent window ---
function openLink(url) {
  try { parent.window.open(url, '_blank'); }
  catch(e) { window.open(url, '_blank'); }
}
</script>
"""

# ---------------------------------------------------------------------------
# STRICT-mode script — strips query params from all navigation and links
# ---------------------------------------------------------------------------

STRICT_SECURITY_SCRIPT = """
<script>
(function() {
  function stripParams(rawUrl) {
    try { var u = new URL(rawUrl, location.href); u.search = ''; return u.toString(); }
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
    (root.querySelectorAll ? root : document).querySelectorAll('a[href]').forEach(function(a) {
      a.href = stripParams(a.href);
    });
  }
  sanitizeLinks(document);
  new MutationObserver(function(muts) {
    muts.forEach(function(m) {
      m.addedNodes.forEach(function(n) { if (n.nodeType === 1) sanitizeLinks(n); });
    });
  }).observe(document.body, { childList: true, subtree: true });
})();
</script>
"""

# Kept for backwards compatibility in case anything references the old name
INJECTED_SCRIPTS = BODY_SCRIPTS


_WRAPPER_TAG_RE = re.compile(
    r'<!DOCTYPE[^>]*>|</?html[^>]*>|</?head[^>]*>|</?body[^>]*>|<meta[^>]*/?>',
    re.IGNORECASE,
)


def _sanitize_content(content: str) -> str:
    """Strip document wrapper tags that models sometimes include."""
    content = _WRAPPER_TAG_RE.sub('', content)
    # Collapse runs of 3+ blank lines into a single blank line
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()


# ---------------------------------------------------------------------------
# CSP generation per security level
# ---------------------------------------------------------------------------

_KNOWN_CDNS = (
    "https://cdnjs.cloudflare.com"
    " https://cdn.jsdelivr.net"
    " https://unpkg.com"
)


def _build_csp_tag(level: str) -> str:
    """Return a <meta> CSP tag for the given security level, or empty string."""
    if level == "none":
        return ""

    if level == "strict":
        return (
            '<meta http-equiv="Content-Security-Policy" content="'
            f"default-src 'self'; "
            f"script-src 'unsafe-inline' {_KNOWN_CDNS}; "
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

    # balanced: block outbound connections & forms, allow external images
    return (
        '<meta http-equiv="Content-Security-Policy" content="'
        f"default-src 'self'; "
        f"script-src 'unsafe-inline' {_KNOWN_CDNS}; "
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


def _build_html(content: str, security_level: str = "strict") -> str:
    """Wrap a user-provided HTML/SVG fragment in the full Rich UI shell."""
    content = _sanitize_content(content)
    csp_tag = _build_csp_tag(security_level)
    strict_script = STRICT_SECURITY_SCRIPT if security_level == "strict" else ""
    return (
        "<!DOCTYPE html><html><head>"
        f"{csp_tag}"
        f"<style>{THEME_CSS}\n{SVG_CLASSES}\n{BASE_STYLES}</style>"
        f"{THEME_DETECTION_SCRIPT}"
        f"</head><body>\n{content}\n{BODY_SCRIPTS}{strict_script}</body></html>"
    )


# ---------------------------------------------------------------------------
# Valves (user-configurable settings)
# ---------------------------------------------------------------------------

# Developer reference for security levels:
#
#   STRICT   — Blocks all outbound requests, form submissions, external images,
#              embedded objects, and base-URI hijacking. Injects a script that
#              strips URL query parameters from all navigation. Recommended default.
#
#   BALANCED — Same as STRICT but allows external image loading (img-src *).
#              No URL parameter stripping.
#
#   NONE     — No CSP applied. Visualization can make arbitrary network requests.
#
# None of these levels can prevent parent document access when iframe
# Same-Origin is enabled — that is controlled at the platform level.


class Tools:
    """Inline Visualizer — renders interactive HTML/SVG in chat.

    Security is controlled via the ``security_level`` valve, which applies
    a Content Security Policy to the rendered iframe. Defaults to STRICT,
    blocking all silent data exfiltration vectors.
    """

    class Valves(BaseModel):
        security_level: Literal["strict", "balanced", "none"] = Field(
            default="strict",
            description="Strict (default): blocks outbound requests, images, and forms. Balanced: allows external images. None: no restrictions.",
        )

    def __init__(self):
        self.valves = self.Valves()

    def render_visualization(
        self,
        html_code: str,
        title: str = "Visualization",
    ) -> tuple:
        """
        Render an interactive HTML or SVG visualization inline in the chat.

        IMPORTANT: You MUST call view_skill("visualize") FIRST to load the design system
        before calling this tool. Never generate a visualization without reading the skill
        instructions first — they contain critical rules for colors, layout, SVG setup,
        chart patterns, and common failure points.

        After calling this tool, do NOT repeat or echo back the HTML/SVG source code in
        your text response. The visualization is already rendered and visible to the user.
        Instead, briefly describe what the visualization shows in plain language.

        The system automatically injects:
        - Theme CSS variables (auto-detected light/dark mode)
        - SVG utility classes: .t .ts .th .box .node .arr .leader
        - Color ramp classes: .c-purple .c-teal .c-coral .c-pink .c-gray .c-blue .c-green .c-amber .c-red
        - Base element styles (button, range, select, code, headings)
        - Height auto-sizing script
        - sendPrompt(text) function — sends a message to the chat (requires iframe Sandbox Allow Same Origin)
        - openLink(url) function — opens a URL in a new tab

        :param html_code: HTML or SVG content fragment. Do NOT include DOCTYPE, html, head, or body tags.
                          Structure: <style> first (prefer inline styles), visible content next, <script> last.
                          Chart.js is auto-injected by Open WebUI when same-origin is enabled. Otherwise, load via CDN:
                          <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>.
                          For complex visualizations, load D3 via <script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>.
        :param title: Short descriptive title for the visualization.
        :return: Interactive rich embed rendered in the chat, with LLM context.
        """
        response = HTMLResponse(
            content=_build_html(html_code, self.valves.security_level),
            headers={"Content-Disposition": "inline"},
        )
        result_context = (
            f'Visualization "{title}" is now rendered and visible to the user as an '
            f"interactive embed. Do NOT echo back the HTML/SVG source code. Instead, "
            f"briefly describe what the visualization shows in plain language. If the "
            f"visualization has interactive elements (clickable nodes, buttons, sliders), "
            f"mention what the user can interact with."
        )
        return response, result_context

