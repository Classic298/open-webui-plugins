# Shared Assets Protocol, optional build reload add-on for event functions.
# Copy everything below this header into the top of your event function, above
# the shared asset block, so FUNCTION_BUILD_ID is easy to find and bump.
# Spec and rules: https://github.com/Classic298/open-webui-plugins/tree/main/shared-assets-protocol

import asyncio
import json
import logging
import uuid
from typing import Any, Optional

# BUMP ON EVERY CODE CHANGE: peers already on this build ignore the broadcast.
FUNCTION_BUILD_ID = "2026-10-05.1"

RELOAD_KEY = "my-plugin"  # fixed, like the asset key
RELOAD_SIGNATURE = "// my-plugin:start"  # a string only your own source contains

# ===========================================================================
# Build reload broadcast
# ---------------------------------------------------------------------------
# Each load publishes FUNCTION_BUILD_ID over Redis; a peer on another build
# re-executes the source from the database. register(app) is yours and must be
# idempotent; gate each producer on reload_active(app).
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
                # Enable broadcasts arrive before is_active commits; bootstrap trusts this flag.
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
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def bootstrap():
        try:
            from open_webui.main import app

            own = await reload_find_own_row()
            # Loading a disabled function (e.g. for its valves) must not switch it on.
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
