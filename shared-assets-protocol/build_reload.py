# Shared Assets Protocol, optional build reload add-on for event functions.
# Copy everything below this header into your event function, next to the
# shared asset block. It is not part of the interop surface: every name is
# scoped by RELOAD_KEY, so your copy only ever serves your own plugin.
# Spec and rules: https://github.com/Classic298/open-webui-plugins/tree/main/shared-assets-protocol

import asyncio
import json
import logging
import uuid
from typing import Any, Optional

# ===========================================================================
# BUMP THIS ON EVERY CODE CHANGE.
# It is the payload of the reload broadcast; peers that already run this build
# ignore the broadcast, so an unchanged id leaves the fleet on old code.
# ===========================================================================
FUNCTION_BUILD_ID = "2026-10-05.1"

RELOAD_KEY = "my-plugin"  # fixed, like the asset key
RELOAD_SIGNATURE = "// my-plugin:start"  # a string only your own source contains

# ===========================================================================
# Build reload broadcast (optional add-on, event functions only)
# ---------------------------------------------------------------------------
# Every container keeps its own module cache and fragment registry, so a save
# on one container leaves the others on the old code until they restart. Each
# load publishes FUNCTION_BUILD_ID over Redis; a peer on another build drops
# its cached module and re-executes the source from the database, whose fresh
# Event().__init__ registers again. Without Redis it only tracks local state.
#
# Contract:
#   * Needs FUNCTION_BUILD_ID, RELOAD_KEY and RELOAD_SIGNATURE defined above.
#   * register(app) is yours: it calls asset_register for every fragment and
#     must be idempotent. Gate each producer on reload_active(app), so a
#     disable on one container switches the fragment off on all of them.
#   * Call reload_bootstrap(register) from Event.__init__ and
#     reload_on_event(...) from event(). Nothing else is needed.
#   * A deleted function still never sees its own deletion: disable first.
# ===========================================================================
RELOAD_STATE_ATTR = "_owui_build_reload"  # {key: {active, build, function_id, listener}}
RELOAD_CHANNEL = "owui-build-reload:" + RELOAD_KEY
RELOAD_PROCESS_TOKEN = uuid.uuid4().hex

reload_log = logging.getLogger("owui-build-reload")


def reload_state(app: Any) -> dict:
    registry = getattr(app.state, RELOAD_STATE_ATTR, None)
    if not isinstance(registry, dict):
        registry = {}
        app.state.__setattr__(RELOAD_STATE_ATTR, registry)
    return registry.setdefault(RELOAD_KEY, {})


def reload_active(app: Any) -> bool:
    return bool(reload_state(app).get("active"))


def reload_mark_loaded(app: Any, register, function_id: Optional[str]) -> None:
    """Publish the fragments and mark this process active and on this build."""
    register(app)
    state = reload_state(app)
    state["active"] = True
    state["build"] = FUNCTION_BUILD_ID
    if function_id:
        state["function_id"] = function_id


async def reload_find_own_row():
    from open_webui.models.functions import Functions

    event_functions = await Functions.get_functions_by_type("event")
    return next((f for f in event_functions if RELOAD_SIGNATURE in (f.content or "")), None)


async def reload_publish(app: Any, active: bool) -> None:
    redis = getattr(app.state, "redis", None)
    if redis is None:
        return
    try:
        await redis.publish(
            RELOAD_CHANNEL,
            json.dumps({"origin": RELOAD_PROCESS_TOKEN, "build": FUNCTION_BUILD_ID, "active": active}),
        )
    except Exception as e:
        reload_log.warning("[%s] publish failed: %s", RELOAD_KEY, type(e).__name__)


async def reload_from_db(app: Any) -> None:
    """Re-exec the DB source so a peer runs the new build, not its stale copy."""
    from types import SimpleNamespace

    from open_webui.utils.plugin import (
        get_function_contents_cache,
        get_function_module_from_cache,
        get_functions_cache,
    )

    function_id = reload_state(app).get("function_id")
    if not function_id:
        own = await reload_find_own_row()
        function_id = own.id if own else None
    if not function_id:
        return
    context = SimpleNamespace(app=app)
    get_functions_cache(context).pop(function_id, None)
    get_function_contents_cache(context).pop(function_id, None)
    await get_function_module_from_cache(context, function_id)


async def reload_ensure_listener(app: Any) -> None:
    """One listener per process; a no-op without Redis."""
    state = reload_state(app)
    if state.get("listener") is not None:
        return
    redis = getattr(app.state, "redis", None)
    if redis is None:
        return
    # Mark before awaiting so a concurrent event() can't double-subscribe.
    state["listener"] = True
    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(RELOAD_CHANNEL)
    except Exception as e:
        state["listener"] = None
        reload_log.warning("[%s] subscribe failed: %s", RELOAD_KEY, type(e).__name__)
        return

    async def listen():
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                raw = message.get("data")
                if isinstance(raw, (bytes, bytearray)):
                    raw = raw.decode("utf-8", "ignore")
                try:
                    payload = json.loads(raw) if raw else {}
                except Exception:
                    payload = {}
                if payload.get("origin") == RELOAD_PROCESS_TOKEN:
                    continue
                if not payload.get("active"):
                    state["active"] = False
                    continue
                if state.get("active") and payload.get("build") == state.get("build"):
                    continue
                # Set before the re-exec: an enable broadcast arrives while the
                # row still reads is_active=False, and bootstrap trusts this flag.
                state["active"] = True
                try:
                    await reload_from_db(app)
                except Exception as e:
                    reload_log.warning("[%s] reload from db failed: %s", RELOAD_KEY, type(e).__name__)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            reload_log.warning("[%s] listener stopped: %s", RELOAD_KEY, type(e).__name__)

    state["listener"] = asyncio.create_task(listen())


def reload_bootstrap(register) -> None:
    """Register when the module is (re)loaded in a running app - right after an
    admin save, or a peer's reload_from_db - so no restart is needed."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def bootstrap():
        try:
            from open_webui.main import app

            own = await reload_find_own_row()
            # Loading a disabled function (e.g. to show its valves) must not
            # switch it on. The active flag covers a peer reloading on an
            # enable broadcast, sent before the toggle commits is_active.
            if own is None or not (own.is_active or reload_active(app)):
                return
            reload_mark_loaded(app, register, own.id)
            reload_log.info("[%s] build %s loaded", RELOAD_KEY, FUNCTION_BUILD_ID)
            await reload_ensure_listener(app)
            await reload_publish(app, True)
        except Exception as e:
            reload_log.warning("[%s] bootstrap failed: %s", RELOAD_KEY, type(e).__name__)

    loop.create_task(bootstrap())


async def reload_on_event(
    app: Any, register, event: Optional[dict], function_id: Optional[str], event_name: Optional[str]
) -> None:
    try:
        await reload_ensure_listener(app)
    except Exception as e:
        reload_log.warning("[%s] listener setup failed: %s", RELOAD_KEY, type(e).__name__)

    subject_id = ((event or {}).get("subject") or {}).get("id")
    if event_name == "function.disable_started" and subject_id == function_id:
        reload_state(app)["active"] = False
        await reload_publish(app, False)
        return

    state = reload_state(app)
    current = state.get("active") and state.get("build") == FUNCTION_BUILD_ID
    if current and event_name != "system.startup.completed":
        return
    try:
        reload_mark_loaded(app, register, function_id)
        await reload_publish(app, True)
    except Exception as e:
        reload_log.warning("[%s] registration failed (%s): %s", RELOAD_KEY, event_name, type(e).__name__)


# =========================== end build reload block ========================
