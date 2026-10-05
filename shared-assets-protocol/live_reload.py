# Shared Assets Protocol, optional live reload add-on for event functions.
# Copy everything below this header into your event function, above the shared
# asset block.
# Spec and rules: https://github.com/Classic298/open-webui-plugins/tree/main/shared-assets-protocol

import asyncio
import json
import logging
import uuid
from typing import Any, Optional

# --- fast JSON helpers: use orjson when available, fall back to stdlib json ---
try:
    import orjson as _orjson

    def _json_dumps(obj, *, default=str):
        return _orjson.dumps(obj, default=default).decode("utf-8")

    def _json_loads(payload):
        return _orjson.loads(payload)

except ImportError:

    def _json_dumps(obj, *, default=str):
        return json.dumps(obj, ensure_ascii=False, default=default)

    def _json_loads(payload):
        return json.loads(payload)


ASSET_KEY = "my-plugin"  # fixed, used for asset_register too

# ===========================================================================
# Live reload broadcast
# ---------------------------------------------------------------------------
# Each load publishes over Redis; a peer whose cached code differs from the
# database re-executes it. register(app) is yours and must be idempotent; gate
# each producer on reload_active(app).
# ===========================================================================
RELOAD_STATE_ATTR = "_owui_live_reload"  # {key: {active, exec_id, listener}}
RELOAD_EXEC_ID = uuid.uuid4().hex  # new on every exec of this source
# Open WebUI executes each function as module "function_<id>".
RELOAD_FUNCTION_ID = __name__.removeprefix("function_")

reload_log = logging.getLogger("owui-live-reload")


def reload_state(app: Any) -> dict:
    registry = getattr(app.state, RELOAD_STATE_ATTR, None)
    if not isinstance(registry, dict):
        registry = {}
        app.state.__setattr__(RELOAD_STATE_ATTR, registry)
    return registry.setdefault(ASSET_KEY, {})


def reload_active(app: Any) -> bool:
    return bool(reload_state(app).get("active"))


def reload_channel() -> str:
    from open_webui.env import REDIS_KEY_PREFIX

    return f"{REDIS_KEY_PREFIX}:live-reload:{ASSET_KEY}"


def reload_mark_loaded(app: Any) -> None:
    register(app)
    state = reload_state(app)
    state["active"] = True
    state["exec_id"] = RELOAD_EXEC_ID


async def reload_publish(app: Any, active: bool) -> None:
    redis = getattr(app.state, "redis", None)
    if redis is None:
        return
    try:
        await redis.publish(reload_channel(), _json_dumps({"active": active}))
    except Exception as e:
        reload_log.warning("[%s] publish failed: %s", ASSET_KEY, type(e).__name__)


async def reload_ensure_listener(app: Any) -> None:
    from types import SimpleNamespace

    from open_webui.utils.plugin import (
        get_function_module_from_cache,
        get_functions_cache,
    )

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
        await pubsub.subscribe(reload_channel())
    except Exception as e:
        state["listener"] = None
        reload_log.warning("[%s] subscribe failed: %s", ASSET_KEY, type(e).__name__)
        return

    async def listen():
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                if not _json_loads(message["data"])["active"]:
                    state["active"] = False
                    continue
                was_active = state.get("active")
                # Enable broadcasts arrive before is_active commits; bootstrap trusts this flag.
                state["active"] = True
                context = SimpleNamespace(app=app)
                if not was_active:
                    # Force a fresh exec so its bootstrap registers again.
                    get_functions_cache(context).pop(RELOAD_FUNCTION_ID, None)
                try:
                    await get_function_module_from_cache(context, RELOAD_FUNCTION_ID)
                except Exception as e:
                    reload_log.warning(
                        "[%s] reload from db failed: %s", ASSET_KEY, type(e).__name__
                    )
        except Exception as e:
            reload_log.warning("[%s] listener stopped: %s", ASSET_KEY, type(e).__name__)

    state["listener"] = asyncio.create_task(listen())


def reload_bootstrap() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def bootstrap():
        try:
            from open_webui.main import app
            from open_webui.models.functions import Functions

            own = await Functions.get_function_by_id(RELOAD_FUNCTION_ID)
            # Loading a disabled function (e.g. for its valves) must not switch it on.
            if own is None or not (own.is_active or reload_active(app)):
                return
            reload_mark_loaded(app)
            await reload_ensure_listener(app)
            await reload_publish(app, True)
        except Exception as e:
            reload_log.warning("[%s] bootstrap failed: %s", ASSET_KEY, type(e).__name__)

    loop.create_task(bootstrap())


async def reload_on_event(
    app: Any, event: Optional[dict], event_name: Optional[str]
) -> None:
    await reload_ensure_listener(app)
    state = reload_state(app)

    subject_id = ((event or {}).get("subject") or {}).get("id")
    if event_name == "function.disable_started" and subject_id == RELOAD_FUNCTION_ID:
        state["active"] = False
        await reload_publish(app, False)
        return

    current = state.get("active") and state.get("exec_id") == RELOAD_EXEC_ID
    if current and event_name != "system.startup.completed":
        return
    reload_mark_loaded(app)
    await reload_publish(app, True)


# =========================== end live reload block =========================
