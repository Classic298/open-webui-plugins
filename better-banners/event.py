"""
title: Better Banners
author: Classic298
author_url: https://github.com/Classic298
funding_url: https://github.com/Classic298
version: 1.0.0
required_open_webui_version: 0.11.4
description: Shows the banners from Admin Panel → Settings → General → Banners in every chat, at the top of the page or right above the message input. Users can collapse the banners into a small pill and dismiss the dismissible ones, and both choices are remembered. Banner edits reach open tabs live, in each user's language. Inspired by Broadcast Toasts by G30.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ===========================================================================
# Shared static-asset registry
# --- KEEP BYTE-IDENTICAL IN EVERY PLUGIN THAT USES IT ----------------------
# ---------------------------------------------------------------------------
# Each plugin publishes a fragment into one app.state registry and the route
# composes them per request, so load order is irrelevant. Per-process: each
# container serves what it has loaded.
#
# Contract:
#   * ASSET_REGISTRY_ATTR, ASSET_ROUTE_ATTR, the entry shape and the paths are
#     the interop surface. The route owner's copy serves everyone.
#   * `key` must be a module-level constant, or a re-exec adds a second entry.
#   * Lower `order` composes first (default 0). Never encode priority in the key.
#   * Producers run on the event loop for every request, 304s included: return
#     a prebuilt string, no I/O, no locks.
#   * Return "" to withdraw. A deleted plugin never sees its own deletion, so
#     disable it first.
#   * Inline fragments only: <script src> / @import lands after hydration.
# ===========================================================================
LOADER_PATH = "/static/loader.js"
CUSTOM_CSS_PATH = "/static/custom.css"
SHARED_ASSET_TYPES = {
    LOADER_PATH: "application/javascript; charset=utf-8",
    CUSTOM_CSS_PATH: "text/css; charset=utf-8",
}
ASSET_REGISTRY_ATTR = "_owui_static_fragments"  # {path: {key: entry}}
ASSET_ROUTE_ATTR = "_owui_shared_asset"  # set to the path the route serves
ASSET_IMPL_ATTR = "_owui_shared_asset_impl"  # implementation version of the route
# Bump on any behaviour change: the newest copy takes over the route.
ASSET_IMPL_VERSION = 4

# Warn once per (path, key, exception type): compose runs on every page load.
_ASSET_WARNED: set = set()


def asset_fragments(app: Any, path: str) -> dict:
    registry = getattr(app.state, ASSET_REGISTRY_ATTR, None)
    if not isinstance(registry, dict):
        registry = {}
        app.state.__setattr__(ASSET_REGISTRY_ATTR, registry)
    bucket = registry.get(path)
    if not isinstance(bucket, dict):
        bucket = {}
        registry[path] = bucket
    return bucket


def asset_sort_key(item):
    """(order, key); a non-int order falls back to 0 so it cannot break sorted()."""
    key, entry = item
    try:
        order = int(entry.get("order", 0))
    except (TypeError, ValueError):
        order = 0
    return (order, key)


def asset_strip_block(content: str, start_marker: str, end_marker: str) -> str:
    """Remove every marker-wrapped block, leaving other content untouched."""
    while start_marker in content:
        start = content.find(start_marker)
        end = content.find(end_marker, start)
        if end == -1:
            # No end marker: the block was appended last, so drop to EOF.
            content = content[:start]
            break
        end += len(end_marker)
        if content[end : end + 1] == "\n":
            end += 1
        content = content[:start] + content[end:]
    return content


def asset_compose(app: Any, path: str) -> str:
    """Disk file plus every registered fragment, in (order, key) order."""
    import logging

    try:
        from open_webui.env import STATIC_DIR

        target = Path(STATIC_DIR) / path.rsplit("/", 1)[-1]
        body = (
            ""
            if (target.is_symlink() or not target.is_file())
            else target.read_text(encoding="utf-8")
        )
    except Exception:
        body = ""

    ordered = sorted(asset_fragments(app, path).items(), key=asset_sort_key)
    # Strip first: an older file-writing build may have left a block on disk.
    for _key, entry in ordered:
        body = asset_strip_block(body, entry["start"], entry["end"])
    body = body.rstrip()

    for key, entry in ordered:
        try:
            block = (entry["js"]() or "").strip()
        except Exception as exc:
            mark = (path, key, type(exc).__name__)
            if mark not in _ASSET_WARNED:
                if len(_ASSET_WARNED) > 256:
                    _ASSET_WARNED.clear()
                _ASSET_WARNED.add(mark)
                logging.getLogger("owui-shared-assets").warning(
                    "fragment %r failed for %s - it will be omitted",
                    key,
                    path,
                    exc_info=True,
                )
            continue
        if block:
            body = (body + "\n\n" if body else "") + block
    return body + "\n" if body else ""


def asset_register(
    app: Any, path: str, key: str, start: str, end: str, producer, order: int = 0
) -> None:
    """Publish a fragment and ensure the route exists. Idempotent."""
    from starlette.responses import Response
    from starlette.routing import Mount, Route

    asset_fragments(app, path)[key] = {
        "start": start,
        "end": end,
        "js": producer,
        "order": order,
    }

    for existing in app.routes:
        if getattr(existing, ASSET_ROUTE_ATTR, None) != path:
            continue
        if getattr(existing, ASSET_IMPL_ATTR, 0) >= ASSET_IMPL_VERSION:
            return  # an equal or newer implementation already owns the route
        break  # ours is newer - fall through and replace it

    # Fragments live on app.state, so replacing the route loses nothing.
    app.routes[:] = [r for r in app.routes if getattr(r, "path", "") != path]
    media_type = SHARED_ASSET_TYPES.get(path, "text/plain; charset=utf-8")

    async def serve_asset(request):
        content = asset_compose(app, path)
        etag = (
            '"owui-'
            # Cache validator only; a bare md5() raises on FIPS hosts.
            + hashlib.md5(
                (path + "\x00" + content).encode("utf-8"), usedforsecurity=False
            ).hexdigest()
            + '"'
        )
        # no-cache, not no-store: no-store would disable the 304 below.
        headers = {
            "Cache-Control": "no-cache, must-revalidate, private",
            "ETag": etag,
        }
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        # Starlette only adds charset for text/*.
        return Response(content, media_type=media_type, headers=headers)

    insert_at = len(app.routes)
    for position, existing in enumerate(app.routes):
        if isinstance(existing, Mount) and getattr(existing, "name", "") == "static":
            insert_at = position
            break
    shared = Route(path, serve_asset, methods=["GET"])
    setattr(shared, ASSET_ROUTE_ATTR, path)
    setattr(shared, ASSET_IMPL_ATTR, ASSET_IMPL_VERSION)
    app.routes.insert(insert_at, shared)


# =========================== end shared asset block ========================


SOCKET_EVENT = "owui:better-banners"
BANNERS_UPDATED_EVENT = "config.banners.updated"
DISABLED_CHECK_SECONDS = 1.0
LOADER_BLOCK_START = "// owui-better-banners:start"
LOADER_BLOCK_END = "// owui-better-banners:end"
ASSET_KEY = "better-banners"

BANNER_CSS = r"""
#owui-better-banners{--obb-enter-y:-10px;--obb-collapse-y:-14px;--obb-surface:rgba(255,255,255,.78);--obb-text:#1f2937;--obb-muted:#6b7280;--obb-hover:rgba(0,0,0,.06);display:flex;flex-direction:column;gap:6px;box-sizing:border-box;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin}
html.dark #owui-better-banners{--obb-surface:rgba(23,23,23,.72);--obb-text:#f3f4f6;--obb-muted:#9ca3af;--obb-hover:rgba(255,255,255,.08)}
#owui-better-banners[data-position="top"]{flex:none;width:100%;max-width:58rem;max-height:40vh;margin:calc(3rem - 4px) auto 0;padding:4px 8px}
#owui-better-banners[data-position="bottom"]{--obb-enter-y:10px;--obb-collapse-y:14px;width:100%;max-height:40vh;margin:-4px 0 4px;padding:4px 0}
.obb-banner,.obb-pill{pointer-events:auto;background:linear-gradient(color-mix(in srgb,var(--obb-accent) 10%,transparent),color-mix(in srgb,var(--obb-accent) 10%,transparent)),var(--obb-surface);-webkit-backdrop-filter:blur(18px) saturate(1.4);backdrop-filter:blur(18px) saturate(1.4);box-shadow:0 6px 20px -12px rgba(0,0,0,.25);color:var(--obb-text);font-size:.8125rem}
.obb-banner{box-sizing:border-box;flex:none;position:relative;display:flex;align-items:flex-start;gap:10px;padding:8px 6px 8px 12px;border-radius:16px;border:1px solid color-mix(in srgb,var(--obb-accent) 24%,transparent);line-height:1.5;text-align:left}
.obb-banner:not(:has(.obb-actions)){padding-right:12px}
.obb-info{--obb-accent:#3b82f6}.obb-success{--obb-accent:#22c55e}.obb-warning{--obb-accent:#f59e0b}.obb-error{--obb-accent:#ef4444}
.obb-icon{flex:none;width:16px;height:16px;margin-top:2px;color:var(--obb-accent)}
.obb-body{flex:1;min-width:0;cursor:default}
.obb-title{font-weight:600}
.obb-content{max-height:var(--obb-max-height,160px);overflow-y:auto;overflow-wrap:anywhere;scrollbar-width:thin}
.obb-content ul,.obb-content ol{margin:2px 0;padding-left:20px}
.obb-content ul{list-style:disc}.obb-content ol{list-style:decimal}
.obb-content a{color:inherit;text-decoration:underline;text-underline-offset:2px}
.obb-content code{font-size:.75rem;padding:1px 5px;border-radius:6px;background:var(--obb-hover)}
.obb-actions{flex:none;display:flex;gap:2px;margin:-2px 0}
.obb-button{display:flex;align-items:center;justify-content:center;width:24px;height:24px;padding:0;border:0;border-radius:8px;background:transparent;color:var(--obb-muted);cursor:pointer}
.obb-button:hover{background:var(--obb-hover);color:var(--obb-text)}
.obb-button:focus-visible{outline:2px solid var(--obb-accent);outline-offset:1px}
.obb-button svg{width:14px;height:14px}
.obb-pill{position:sticky;z-index:1;flex:none;align-self:center;display:inline-flex;align-items:center;gap:8px;height:30px;padding:0 10px 0 12px;border-radius:999px;border:1px solid color-mix(in srgb,var(--obb-accent) 30%,transparent);font:inherit;line-height:1;cursor:pointer}
.obb-pill:hover{border-color:color-mix(in srgb,var(--obb-accent) 60%,transparent)}
.obb-pill:focus-visible{outline:2px solid var(--obb-accent);outline-offset:2px}
.obb-dot{width:8px;height:8px;border-radius:50%;background:var(--obb-accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--obb-accent) 25%,transparent)}
.obb-count{min-width:18px;padding:2px 6px;border-radius:999px;background:color-mix(in srgb,var(--obb-accent) 18%,transparent);font-size:.75rem;font-weight:600;font-variant-numeric:tabular-nums;text-align:center}
.obb-pill svg{width:14px;height:14px;color:var(--obb-muted)}
.obb-chevron{display:flex;transition:transform .32s cubic-bezier(.34,1.56,.64,1)}
#owui-better-banners[data-position="top"] .obb-pill[aria-expanded="true"] .obb-chevron,#owui-better-banners[data-position="bottom"] .obb-pill[aria-expanded="false"] .obb-chevron{transform:rotate(180deg)}
#owui-better-banners[data-position="top"] .obb-pill{top:0}
#owui-better-banners[data-position="bottom"] .obb-pill{bottom:0}
.obb-pill.obb-absorb{animation:obb-absorb .46s cubic-bezier(.34,1.56,.64,1)}
.obb-pill.obb-release{animation:obb-release .3s cubic-bezier(.34,1.56,.64,1)}
.obb-banner.obb-enter{animation:obb-in .26s cubic-bezier(.22,1,.36,1) backwards;animation-delay:var(--obb-delay,0ms)}
.obb-pill.obb-enter{animation:obb-pop .28s cubic-bezier(.34,1.56,.64,1)}
.obb-banner.obb-leave{animation:obb-out .16s ease-in forwards}
.obb-collapsing{overflow:hidden;transition:height .24s cubic-bezier(.4,0,.2,1),padding .24s cubic-bezier(.4,0,.2,1),margin .24s cubic-bezier(.4,0,.2,1),border-width .24s,opacity .18s ease,transform .24s cubic-bezier(.4,0,.2,1);transition-delay:var(--obb-delay,0ms)}
.obb-collapsed{height:0!important;padding-top:0;padding-bottom:0;border-width:0;opacity:0;transform:translateY(var(--obb-collapse-y)) scale(.88);margin-top:-6px}
@keyframes obb-in{from{opacity:0;transform:translateY(var(--obb-enter-y)) scale(.94)}to{opacity:1;transform:none}}
@keyframes obb-out{to{opacity:0;transform:scale(.92)}}
@keyframes obb-pop{from{opacity:0;transform:scale(.8)}to{opacity:1;transform:none}}
@keyframes obb-absorb{0%{transform:scale(1)}30%{transform:scale(1.16)}60%{transform:scale(.94)}100%{transform:scale(1)}}
@keyframes obb-release{0%{transform:scale(1)}35%{transform:scale(.9)}100%{transform:scale(1)}}
@media (prefers-reduced-motion:reduce){.obb-banner.obb-enter,.obb-pill.obb-enter,.obb-banner.obb-leave,.obb-pill.obb-absorb,.obb-pill.obb-release{animation-duration:.01ms;animation-delay:0s}.obb-collapsing,.obb-chevron{transition-duration:.01ms;transition-delay:0s}}
"""

LOADER_SCRIPT = r"""
(function () {
  'use strict';
  if (window.__owuiBetterBanners) return;
  window.__owuiBetterBanners = true;

  var CFG = __CONFIG__;
  var CSS = __CSS__;
  var COLLAPSED_KEY = 'owui-better-banners:collapsed';
  // Open WebUI's own key, so dismissals carry over in both directions.
  var DISMISSED_KEY = 'dismissedBannerIds';
  var FRAME = '42["' + CFG.event + '"';
  var SYNC_SPREAD_MS = 2000;
  var COLLAPSE_MS = 240;
  var LEAVE_MS = 200;
  var STAGGER_MS = 45;
  var LEVEL_ORDER = ['success', 'info', 'warning', 'error'];
  var ICONS = {
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>',
    success: '<circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 4.5-5"/>',
    warning: '<path d="M10.3 4.2 2.6 17.6a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z"/><path d="M12 10v4"/><path d="M12 17h.01"/>',
    error: '<circle cx="12" cy="12" r="9"/><path d="m9.5 9.5 5 5"/><path d="m14.5 9.5-5 5"/>'
  };
  var CHEVRON = '<path d="m6 9 6 6 6-6"/>';
  var CLOSE = '<path d="M6 6l12 12"/><path d="M18 6 6 18"/>';
  var MEGAPHONE = '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>';

  var banners = [];
  var root = null;
  var placeQueued = false;
  var lastRenderKey = '';
  var collapseTimer = null;
  var anchored = false;
  var inflight = false;
  var syncAgain = false;
  var syncTimer = null;
  var lastToken = null;

  function token() {
    try { return localStorage.getItem('token') || ''; } catch (e) { return ''; }
  }

  function readJson(key, fallback) {
    try {
      var value = JSON.parse(localStorage.getItem(key) || 'null');
      return value && typeof value === 'object' ? value : fallback;
    } catch (e) {
      return fallback;
    }
  }

  function writeJson(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }

  function svg(paths) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + paths + '</svg>';
  }

  // Same lookup as Open WebUI's resolveLocalizedString: exact locale, then its base language.
  function localized(banner, field) {
    var lang = (document.documentElement.getAttribute('lang') || '').trim();
    var base = lang.split('-')[0];
    var candidates = base && base !== lang ? [lang, base] : lang ? [lang] : [];
    for (var i = 0; i < candidates.length; i++) {
      var entry = banner.i18n && banner.i18n[candidates[i]];
      var value = entry && entry[field];
      if (typeof value === 'string' && value.trim()) return value;
    }
    return typeof banner[field] === 'string' ? banner[field] : '';
  }

  function fingerprint(banner) {
    var text = JSON.stringify([banner.type, banner.title || '', banner.content, banner.i18n || null]);
    var hash = 5381;
    for (var i = 0; i < text.length; i++) hash = ((hash << 5) + hash + text.charCodeAt(i)) | 0;
    return (hash >>> 0).toString(36);
  }

  function isSafeUrl(url) {
    return /^(https?:\/\/|mailto:|\/(?!\/))/i.test(url);
  }

  function appendLink(target, href, label) {
    var link = document.createElement('a');
    link.href = href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = label;
    target.appendChild(link);
  }

  function appendInline(target, text) {
    var pattern = /\*\*([^*]+)\*\*|\*([^*\s][^*]*)\*|`([^`]+)`|\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)|https?:\/\/[^\s<>"']+/g;
    var last = 0;
    var match;
    while ((match = pattern.exec(text))) {
      var raw = match[0];
      var isBareUrl = /^https?:/.test(raw);
      if (isBareUrl) {
        raw = raw.replace(/[.,;:!?]+$/, '');
        while (raw.slice(-1) === ')' && raw.split('(').length < raw.split(')').length) raw = raw.slice(0, -1);
        pattern.lastIndex = match.index + raw.length;
      }
      if (match.index > last) target.appendChild(document.createTextNode(text.slice(last, match.index)));
      var bold = match[1];
      var italic = match[2];
      if (bold || italic) {
        var emphasis = document.createElement(bold ? 'strong' : 'em');
        appendInline(emphasis, bold || italic);
        target.appendChild(emphasis);
      } else if (match[3]) {
        var code = document.createElement('code');
        code.textContent = match[3];
        target.appendChild(code);
      } else if (match[4]) {
        if (isSafeUrl(match[5])) appendLink(target, match[5], match[4]);
        else target.appendChild(document.createTextNode(match[4]));
      } else {
        appendLink(target, raw, raw);
      }
      last = match.index + raw.length;
    }
    if (last < text.length) target.appendChild(document.createTextNode(text.slice(last)));
  }

  var HTML_TAGS = /^(A|ABBR|B|BLOCKQUOTE|BR|CODE|DEL|DETAILS|DIV|EM|H[1-6]|HR|I|IMG|LI|MARK|OL|P|PRE|S|SMALL|SPAN|STRONG|SUB|SUMMARY|SUP|TABLE|TBODY|TD|TH|THEAD|TR|U|UL)$/;
  var HTML_DROPPED = /^(SCRIPT|STYLE|IFRAME|OBJECT|EMBED|TEMPLATE|NOSCRIPT|SVG|MATH|FORM|INPUT|BUTTON|TEXTAREA|SELECT|LINK|META|BASE)$/;

  // Same idea as Open WebUI's DOMPurify pass: keep formatting and inline styles, drop anything that can run or load code.
  function appendSafeHtml(target, source) {
    Array.prototype.forEach.call(source.childNodes, function (node) {
      if (node.nodeType === 3) {
        target.appendChild(document.createTextNode(node.nodeValue));
        return;
      }
      if (node.nodeType !== 1 || HTML_DROPPED.test(node.tagName)) return;
      if (!HTML_TAGS.test(node.tagName)) {
        appendSafeHtml(target, node);
        return;
      }
      var clean = document.createElement(node.tagName.toLowerCase());
      var style = node.getAttribute('style');
      if (style && !/url\s*\(|expression|javascript:/i.test(style)) clean.setAttribute('style', style);
      ['title', 'class', 'colspan', 'rowspan', 'alt', 'width', 'height'].forEach(function (name) {
        if (node.hasAttribute(name)) clean.setAttribute(name, node.getAttribute(name));
      });
      if (node.tagName === 'A') {
        var href = node.getAttribute('href') || '';
        if (isSafeUrl(href)) {
          clean.href = href;
          clean.target = '_blank';
          clean.rel = 'noopener noreferrer';
        }
      }
      if (node.tagName === 'IMG') {
        var src = node.getAttribute('src') || '';
        if (!/^https?:\/\//i.test(src)) return;
        clean.src = src;
      }
      appendSafeHtml(clean, node);
      target.appendChild(clean);
    });
  }

  function renderContent(target, text) {
    // Like Open WebUI, banners written in HTML render as HTML, with line breaks kept.
    if (/<[a-z][^>]*>/i.test(text)) {
      var parsed = new DOMParser().parseFromString(String(text).replace(/\r?\n/g, '<br>'), 'text/html');
      appendSafeHtml(target, parsed.body);
    } else {
      renderMarkdown(target, text);
    }
  }

  function renderMarkdown(target, text) {
    var list = null;
    var needsBreak = false;
    String(text).replace(/\r\n/g, '\n').split('\n').forEach(function (line) {
      var item = /^\s*(?:[-*+]|(\d+)[.)])\s+(.*)$/.exec(line);
      if (item) {
        var listTag = item[1] ? 'OL' : 'UL';
        if (!list || list.tagName !== listTag) {
          list = document.createElement(listTag);
          target.appendChild(list);
        }
        var li = document.createElement('li');
        appendInline(li, item[2]);
        list.appendChild(li);
        needsBreak = false;
        return;
      }
      list = null;
      if (needsBreak) target.appendChild(document.createElement('br'));
      var heading = /^\s*#{1,6}\s+(.*)$/.exec(line);
      if (heading) {
        var strong = document.createElement('strong');
        appendInline(strong, heading[1]);
        target.appendChild(strong);
      } else {
        appendInline(target, line);
      }
      needsBreak = true;
    });
  }

  function dismissedIds() {
    var ids = readJson(DISMISSED_KEY, []);
    return Array.isArray(ids) ? ids : [];
  }

  function collapsedMap() {
    return readJson(COLLAPSED_KEY, {});
  }

  function visibleBanners() {
    var dismissed = dismissedIds();
    return banners.filter(function (banner) {
      return dismissed.indexOf(banner.id) === -1;
    });
  }

  function anchor() {
    var chatNav = document.querySelector('#new-chat-button ~ nav');
    if (!chatNav) return null;
    var pane = document.getElementById('chat-pane');
    var inChat = pane && (pane.querySelector('#chat-conversation') || location.pathname.lastIndexOf('/c/', 0) === 0);
    if (!inChat) return null;
    if (CFG.position === 'top') {
      // In the page flow, so the chat moves down instead of hiding under the banners.
      return { parent: pane, before: pane.firstChild === root ? root.nextSibling : pane.firstChild };
    }
    var input = document.getElementById('message-input-container');
    var form = input && input.closest('form');
    return form && form.parentNode ? { parent: form.parentNode, before: form } : null;
  }

  function ensureRoot() {
    if (root) return;
    root = document.createElement('div');
    root.id = 'owui-better-banners';
    root.setAttribute('role', 'region');
    root.setAttribute('aria-label', 'Announcements');
    root.dataset.position = CFG.position;
    root.style.setProperty('--obb-max-height', CFG.maxHeight + 'px');
  }

  function place() {
    placeQueued = false;
    var current = token();
    if (current !== lastToken) {
      lastToken = current;
      sync();
    }
    var target = root && root.childNodes.length ? anchor() : null;
    // Pick up dismissals made in Open WebUI's own banners in this tab.
    if (target && !anchored) render();
    anchored = Boolean(target);
    if (!target || !root.childNodes.length) {
      if (root && root.parentNode) {
        root.parentNode.removeChild(root);
        root.querySelectorAll('.obb-enter').forEach(function (element) { element.classList.remove('obb-enter'); });
      }
      return;
    }
    var misplaced = root.parentNode !== target.parent || (target.before && root.nextSibling !== target.before);
    if (misplaced) target.parent.insertBefore(root, target.before);
  }

  function schedulePlace() {
    if (placeQueued) return;
    placeQueued = true;
    requestAnimationFrame(place);
  }

  function isCollapsed(visible) {
    var map = collapsedMap();
    return visible.length > 0 && visible.every(function (banner) {
      return map[banner.id] === fingerprint(banner);
    });
  }

  function staggerFromPill(elements) {
    elements.forEach(function (element, index) {
      var distance = CFG.position === 'top' ? index : elements.length - 1 - index;
      element.style.setProperty('--obb-delay', distance * STAGGER_MS + 'ms');
    });
  }

  function replayAnimation(element, className) {
    element.classList.remove('obb-enter', 'obb-absorb', 'obb-release');
    void element.offsetHeight;
    element.classList.add(className);
    element.addEventListener('animationend', function () { element.classList.remove(className); }, { once: true });
  }

  function collapseAll() {
    var visible = visibleBanners();
    if (!visible.length) return;
    var pill = root.querySelector('.obb-pill');
    clearTimeout(collapseTimer);
    var map = {};
    visible.forEach(function (banner) { map[banner.id] = fingerprint(banner); });
    writeJson(COLLAPSED_KEY, map);
    lastRenderKey = renderKey(visible, true);
    updatePill(pill, visible, true);
    var elements = root.querySelectorAll('.obb-banner');
    staggerFromPill(elements);
    // Keep the target height of an expand still running, so reversing it again opens fully.
    var heights = Array.prototype.map.call(elements, function (element) {
      return element.style.height || element.offsetHeight + 'px';
    });
    elements.forEach(function (element, index) {
      element.classList.remove('obb-enter');
      element.style.height = heights[index];
      element.classList.add('obb-collapsing');
    });
    void root.offsetHeight;
    elements.forEach(function (element) { element.classList.add('obb-collapsed'); });
    collapseTimer = setTimeout(function () {
      elements.forEach(function (element) { element.remove(); });
      replayAnimation(pill, 'obb-absorb');
    }, COLLAPSE_MS + (elements.length - 1) * STAGGER_MS);
  }

  function expandAll() {
    var visible = visibleBanners();
    if (!visible.length) return;
    var pill = root.querySelector('.obb-pill');
    clearTimeout(collapseTimer);
    writeJson(COLLAPSED_KEY, {});
    lastRenderKey = renderKey(visible, false);
    updatePill(pill, visible, false);
    replayAnimation(pill, 'obb-release');
    var elements = root.querySelectorAll('.obb-banner');
    if (!elements.length) {
      elements = visible.map(bannerElement);
      if (CFG.position === 'top') pill.after.apply(pill, elements);
      else pill.before.apply(pill, elements);
      var heights = elements.map(function (element) { return element.offsetHeight + 'px'; });
      elements.forEach(function (element, index) {
        element.style.height = heights[index];
        element.classList.add('obb-collapsed');
      });
      void root.offsetHeight;
    }
    staggerFromPill(elements);
    elements.forEach(function (element) {
      element.classList.add('obb-collapsing');
      element.classList.remove('obb-collapsed');
    });
    collapseTimer = setTimeout(function () {
      elements.forEach(function (element) {
        element.classList.remove('obb-collapsing');
        element.style.height = '';
      });
    }, COLLAPSE_MS + (elements.length - 1) * STAGGER_MS);
  }

  function dismiss(banner, element) {
    var remaining = banners.map(function (b) { return b.id; });
    var ids = [banner.id].concat(dismissedIds()).filter(function (id) {
      return remaining.indexOf(id) !== -1;
    });
    writeJson(DISMISSED_KEY, ids);
    // Start the fade from wherever a running entrance left it.
    element.style.opacity = getComputedStyle(element).opacity;
    element.classList.remove('obb-enter');
    element.classList.add('obb-leave');
    setTimeout(function () {
      element.remove();
      var visible = visibleBanners();
      if (visible.length) {
        var pill = root.querySelector('.obb-pill');
        var collapsed = pill.getAttribute('aria-expanded') !== 'true';
        lastRenderKey = renderKey(visible, collapsed);
        updatePill(pill, visible, collapsed);
      } else if (!root.querySelector('.obb-banner')) {
        // Wait for any other banner still fading out before clearing the stack.
        render();
      }
      schedulePlace();
    }, LEAVE_MS);
  }

  function button(className, paths, label) {
    var el = document.createElement('button');
    el.type = 'button';
    el.className = 'obb-button ' + className;
    el.setAttribute('aria-label', label);
    el.title = label;
    el.innerHTML = svg(paths);
    return el;
  }

  function bannerLevel(banner) {
    return ICONS[banner.type] ? banner.type : 'info';
  }

  function bannerElement(banner) {
    var level = bannerLevel(banner);
    var element = document.createElement('div');
    element.className = 'obb-banner obb-' + level;
    element.dataset.id = banner.id;

    var icon = document.createElement('span');
    icon.className = 'obb-icon';
    icon.innerHTML = svg(ICONS[level]);
    element.appendChild(icon);

    var body = document.createElement('div');
    body.className = 'obb-body';
    var title = localized(banner, 'title').trim();
    if (title) {
      var heading = document.createElement('div');
      heading.className = 'obb-title';
      heading.textContent = title;
      body.appendChild(heading);
    }
    var content = document.createElement('div');
    content.className = 'obb-content';
    renderContent(content, localized(banner, 'content'));
    body.appendChild(content);
    element.appendChild(body);

    if (banner.dismissible) {
      var actions = document.createElement('div');
      actions.className = 'obb-actions';
      var close = button('obb-close', CLOSE, 'Dismiss');
      close.addEventListener('click', function () { dismiss(banner, element); });
      actions.appendChild(close);
      element.appendChild(actions);
    }
    return element;
  }

  function updatePill(pill, visible, collapsed) {
    var pillLevel = visible.map(bannerLevel).reduce(function (highest, level) {
      return LEVEL_ORDER.indexOf(level) > LEVEL_ORDER.indexOf(highest) ? level : highest;
    });
    var label = (collapsed ? 'Expand all (' : 'Collapse all (') + visible.length + ')';
    LEVEL_ORDER.forEach(function (level) { pill.classList.remove('obb-' + level); });
    pill.classList.add('obb-' + pillLevel);
    pill.setAttribute('aria-label', label);
    pill.setAttribute('aria-expanded', String(!collapsed));
    pill.title = label;
    pill.querySelector('.obb-count').textContent = visible.length;
  }

  function pillElement(visible, collapsed) {
    var pill = document.createElement('button');
    pill.type = 'button';
    pill.className = 'obb-pill';
    pill.innerHTML = '<span class="obb-dot"></span>' + svg(MEGAPHONE) + '<span class="obb-count"></span>' +
      '<span class="obb-chevron">' + svg(CHEVRON) + '</span>';
    updatePill(pill, visible, collapsed);
    pill.addEventListener('click', function () {
      if (pill.getAttribute('aria-expanded') === 'true') collapseAll();
      else expandAll();
    });
    return pill;
  }

  function renderKey(visible, collapsed) {
    return JSON.stringify([collapsed, document.documentElement.getAttribute('lang'), visible]);
  }

  function render() {
    ensureRoot();
    var visible = visibleBanners();
    var collapsed = isCollapsed(visible);
    // Skip identical re-renders so a routine sync does not replay the entrance animation.
    var key = renderKey(visible, collapsed);
    if (key === lastRenderKey) return;
    lastRenderKey = key;
    // Forget an old collapse once the stack is open, or dismissing the banner that reopened it re-collapses it.
    if (visible.length && !collapsed) writeJson(COLLAPSED_KEY, {});
    var elements = collapsed ? [] : visible.map(bannerElement);
    staggerFromPill(elements);
    if (visible.length) {
      var pill = pillElement(visible, collapsed);
      if (CFG.position === 'top') elements.unshift(pill);
      else elements.push(pill);
    }
    elements.forEach(function (element) {
      element.classList.add('obb-enter');
      element.addEventListener('animationend', function () { element.classList.remove('obb-enter'); });
    });
    root.replaceChildren.apply(root, elements);
    schedulePlace();
  }

  function sync() {
    if (syncTimer) {
      clearTimeout(syncTimer);
      syncTimer = null;
    }
    var auth = token();
    if (!auth) {
      banners = [];
      render();
      return;
    }
    if (inflight) {
      syncAgain = true;
      return;
    }
    inflight = true;
    fetch('/api/v1/configs/banners', {
      headers: { Authorization: 'Bearer ' + auth },
      cache: 'no-store'
    })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (!Array.isArray(data)) return;
        banners = data;
        render();
      })
      .catch(function () {})
      .then(function () {
        inflight = false;
        if (syncAgain) {
          syncAgain = false;
          sync();
        }
      });
  }

  // Spread over a short window so an edit does not hit the server with every tab at once.
  function scheduleSync() {
    if (syncTimer) return;
    syncTimer = setTimeout(function () {
      syncTimer = null;
      sync();
    }, Math.floor(Math.random() * SYNC_SPREAD_MS));
  }

  function onFrame(evt) {
    var raw = evt.data;
    if (typeof raw === 'string' && raw.lastIndexOf(FRAME, 0) === 0) scheduleSync();
  }

  // Plugins get no handle on the app's socket, so hook WebSocket to hear the change signal.
  function hookSocket() {
    var proto = window.WebSocket.prototype;
    var listen = proto.addEventListener;
    var connectedBefore = false;

    function watch(ws) {
      if (String(ws.url).indexOf('socket.io') === -1) return;
      listen.call(ws, 'message', onFrame);
      // The first connection comes with the page load, which already fetched.
      listen.call(ws, 'open', function () {
        if (connectedBefore) scheduleSync();
        connectedBefore = true;
      });
    }

    // engine.io sets onmessage right after onopen, before the socket connects.
    var desc = Object.getOwnPropertyDescriptor(proto, 'onmessage');
    Object.defineProperty(proto, 'onmessage', {
      configurable: true,
      enumerable: desc.enumerable,
      get: desc.get,
      set: function (fn) {
        watch(this);
        desc.set.call(this, fn);
      }
    });
  }

  function start() {
    lastToken = token();
    sync();
    new MutationObserver(schedulePlace).observe(document.body, { childList: true, subtree: true });
    new MutationObserver(function () { if (banners.length) render(); })
      .observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) scheduleSync();
    });
    window.addEventListener('storage', function (evt) {
      if (evt.key === DISMISSED_KEY || evt.key === COLLAPSED_KEY) render();
    });
    if (CFG.resync > 0) {
      setInterval(function () { if (!document.hidden) sync(); }, CFG.resync * 1000);
    }
  }

  var style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);
  hookSocket();
  start();
})();
"""


class Event:
    class Valves(BaseModel):
        position: Literal["top", "bottom"] = Field(
            default="top",
            description="Where banners appear: at the top of the chat, or right above the message input.",
        )
        max_height_px: int = Field(
            default=160,
            ge=60,
            le=600,
            description="Tallest a single expanded banner gets before its text scrolls.",
        )
        resync_interval_seconds: int = Field(
            default=300,
            ge=0,
            le=3600,
            description="How often each open tab re-reads the banners on its own, as a backstop for a live update it missed. 0 turns it off.",
        )

    _fragment_cache: Optional[tuple[tuple, str]] = None
    _disabled_cache: Optional[tuple[float, bool]] = None

    def __init__(self):
        self.valves = self.Valves()

    def _loader_fragment(self) -> str:
        if Event._is_disabled():
            return ""
        valves = self.valves
        cache_key = (
            valves.position,
            valves.max_height_px,
            valves.resync_interval_seconds,
        )
        if Event._fragment_cache and Event._fragment_cache[0] == cache_key:
            return Event._fragment_cache[1]
        config = json.dumps(
            {
                "event": SOCKET_EVENT,
                "position": valves.position,
                "maxHeight": valves.max_height_px,
                "resync": valves.resync_interval_seconds,
            }
        )
        script = (
            LOADER_SCRIPT.strip()
            .replace("__CONFIG__", config)
            .replace("__CSS__", json.dumps(BANNER_CSS.strip()))
        )
        fragment = f"{LOADER_BLOCK_START}\n{script}\n{LOADER_BLOCK_END}"
        Event._fragment_cache = (cache_key, fragment)
        return fragment

    # Other workers never get this function's disable event, so the state lives on disk.
    @staticmethod
    def _disabled_marker() -> Path:
        from open_webui.config import CACHE_DIR

        return Path(CACHE_DIR) / "better_banners" / "disabled"

    @classmethod
    def _set_disabled(cls, disabled: bool) -> None:
        cls._disabled_cache = (time.monotonic(), disabled)
        marker = cls._disabled_marker()
        if disabled:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
        else:
            marker.unlink(missing_ok=True)

    @classmethod
    def _is_disabled(cls) -> bool:
        now = time.monotonic()
        if (
            cls._disabled_cache
            and now - cls._disabled_cache[0] < DISABLED_CHECK_SECONDS
        ):
            return cls._disabled_cache[1]
        disabled = cls._disabled_marker().exists()
        cls._disabled_cache = (now, disabled)
        return disabled

    async def event(
        self,
        event: Optional[dict] = None,
        __event_name__: str = "",
        __id__: str = "",
        __app__: Any = None,
        **kwargs,
    ) -> None:
        is_own = ((event or {}).get("subject") or {}).get("id") == __id__
        if is_own and __event_name__ == "function.disable_started":
            Event._set_disabled(True)
            return

        if is_own and __event_name__ == "function.enable_started":
            Event._set_disabled(False)

        asset_register(
            __app__,
            LOADER_PATH,
            ASSET_KEY,
            LOADER_BLOCK_START,
            LOADER_BLOCK_END,
            self._loader_fragment,
        )

        if __event_name__ == BANNERS_UPDATED_EVENT:
            from open_webui.socket.main import sio

            await sio.emit(SOCKET_EVENT, {})
