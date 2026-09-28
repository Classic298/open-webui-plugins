# Shared Assets Protocol, reference implementation.
# Copy everything below this header into your plugin byte for byte.
# Spec and rules: https://github.com/Classic298/open-webui-plugins/tree/main/shared-assets-protocol

import hashlib
from pathlib import Path
from typing import Any

# ===========================================================================
# Shared static-asset registry
# --- KEEP BYTE-IDENTICAL IN EVERY PLUGIN THAT USES IT ----------------------
# ---------------------------------------------------------------------------
# app.html loads /static/loader.js and /static/custom.css on every page, and
# loader.js is the only hook running before the SvelteKit bundle hydrates. Two
# URLs, many plugins - so none may own either. Each publishes a fragment into
# one app.state registry and the route composes them PER REQUEST, so load order
# is irrelevant, a late plugin needs no cooperation, and a re-exec'd one
# replaces its own key. Per-process: each container serves what it has loaded.
#
# Fragments are inlined, never <script src> / @import - a second request would
# land after hydration, defeating the point.
#
# Contract:
#   * ASSET_REGISTRY_ATTR, ASSET_ROUTE_ATTR, the entry shape and the paths are
#     the interop surface. Everything else is implementation owned by whichever
#     plugin created the route - a stale copy silently serves everyone, hence
#     ASSET_IMPL_VERSION and byte-identity.
#   * `key` must be a module-level constant. Derive it from a build id or a
#     function id and a re-exec registers a SECOND entry - duplicated output,
#     not just a leaked closure.
#   * `order` breaks ties: lower composes first, so on custom.css it loses the
#     cascade and on loader.js it wraps innermost. Default 0. Use it instead of
#     encoding priority in the key, which would only work if every plugin
#     renamed at once.
#   * Producers run SYNCHRONOUSLY on the event loop, on every request, and
#     BEFORE the ETag is compared - so a 304 costs exactly what a 200 costs.
#     "Cheap" is per-call work, not payload size: memoise anything that
#     parses, formats or regexes and return a prebuilt string. No I/O, no
#     locks, no sleeps. Budget tens of microseconds, not milliseconds.
#   * To withdraw, return "" - there is no unregister. A disabled plugin still
#     gets function.disable_started (it fires before is_active flips), but a
#     DELETED one never sees its own deletion, so disable before deleting or
#     the fragment serves until that process restarts.
#   * Reach is the SPA only. A plugin serving its own HTML page loads neither
#     asset and must inject its own.
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
# Bump when this block changes behaviour: newer evicts older, so the fleet
# converges on one implementation instead of whichever plugin booted first.
ASSET_IMPL_VERSION = 4

# Producer failures are reported once per (path, key, exception type) - compose
# runs on every page load, so an unconditional warning would be a firehose.
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
    """(order, key). Coerced defensively: a non-int order from a third-party
    plugin would raise inside sorted(), outside the per-fragment guard, and
    take down the whole asset."""
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
    """Publish a fragment and ensure the route exists. Idempotent, and safe
    from any plugin in any order."""
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

    # Replaces a single-owner route from an older build, or an older impl of
    # this block. Fragments live on app.state, so nothing is lost.
    app.routes[:] = [r for r in app.routes if getattr(r, "path", "") != path]
    media_type = SHARED_ASSET_TYPES.get(path, "text/plain; charset=utf-8")

    async def serve_asset(request):
        content = asset_compose(app, path)
        etag = (
            '"owui-'
            # usedforsecurity=False: this is a cache validator, not a security
            # primitive, and a bare md5() raises ValueError on a FIPS host -
            # which would 500 the asset for every visitor.
            + hashlib.md5(
                (path + "\x00" + content).encode("utf-8"), usedforsecurity=False
            ).hexdigest()
            + '"'
        )
        # no-cache, NOT no-store: a response the browser may not store has no
        # validator, so If-None-Match is never sent and the 304 below is dead
        # code. no-cache still forbids reuse without revalidation, so a stale
        # body is impossible either way. Note a proxy may re-add no-store for
        # these paths, which puts the 304 back to sleep - that is deployment
        # policy, not this block's business.
        headers = {
            "Cache-Control": "no-cache, must-revalidate, private",
            "ETag": etag,
        }
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        # Starlette only auto-appends charset for text/*, so JS would ship
        # undeclared and readers guessing latin-1 get mojibake.
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
