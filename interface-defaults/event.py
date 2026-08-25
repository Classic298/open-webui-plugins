"""
title: Interface Defaults
author: Classic298
author_url: https://github.com/Classic298
funding_url: https://github.com/Classic298
version: 1.4.0
required_open_webui_version: 0.11.1
description: Companion to Admin Panel → Settings → General → Default Interface Settings. Adds the two things that page has no button for - force every existing user onto the configured defaults, and factory-reset the whole instance - plus defaults for the user settings that page does not reach (notifications, keyboard shortcuts, memory, personal system prompt, speech/voice).
"""

import asyncio
import json
import logging
import os
import sys
from copy import deepcopy
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def _get_logger() -> logging.Logger:
    # Named, not getLogger(__name__): a DB-loaded plugin is "function_<uuid>".
    logger = logging.getLogger("interface_defaults")
    if getattr(logger, "_id_configured", False):
        return logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger._id_configured = True  # type: ignore[attr-defined]
    return logger


log = _get_logger()

# The config row Open WebUI 0.11.1+ overlays onto every user's settings.ui.
DEFAULTS_CONFIG_KEY = "ui.default_interface_settings"
# Our own row: the paths this function last wrote into that overlay, so a valve
# switched back to Default can be withdrawn again. Kept separate because
# anything inside DEFAULTS_CONFIG_KEY is merged into real user settings.
OWNED_CONFIG_KEY = "ui.interface_defaults_managed_paths"

# Valve descriptions are rendered as markdown, so this becomes a real link.
# Absolute when WEBUI_URL is set, so it still points somewhere useful when Open
# WebUI is served under a reverse-proxy sub-path.
ADMIN_PAGE = (os.environ.get("WEBUI_URL") or "").rstrip("/") + "/admin/settings/general"
ADMIN_LINK = (
    f"[Admin Panel → Settings → General → Default Interface Settings]({ADMIN_PAGE})"
)

TRIGGERS = ("apply_defaults_to_all_users", "reset_all_users_to_factory")
NON_UI = TRIGGERS + ("bulk_users_per_second",)

# Every settings.ui path the native Default Interface Settings editor renders.
# A factory reset clears exactly these (plus EXTRA_PATHS below). settings.ui also
# holds a user's direct connections, tool servers, pinned models and default
# model, which are not interface options and are never touched.
NATIVE_INTERFACE_PATHS = (
    ("autoFollowUps",),
    ("autoTags",),
    ("backgroundImageUrl",),
    ("chatBubble",),
    ("chatDirection",),
    ("chatFadeStreamingText",),
    ("chatHoverPreview",),
    ("collapseCodeBlocks",),
    ("copyFormatted",),
    ("ctrlEnterToSend",),
    ("defaultUploadContext",),
    ("detectArtifacts",),
    ("displayMultiModelResponsesInTabs",),
    ("enableMessageQueue",),
    ("expandDetails",),
    ("floatingActionButtons",),
    ("hapticFeedback",),
    ("highContrastMode",),
    ("iframeSandboxAllowDownloads",),
    ("iframeSandboxAllowForms",),
    ("iframeSandboxAllowSameOrigin",),
    ("iframeSandboxAllowScripts",),
    ("imageCompression",),
    ("imageCompressionInChannels",),
    ("imageCompressionSize",),
    ("insertFollowUpPrompt",),
    ("insertPromptAsRichText",),
    ("insertSuggestionPrompt",),
    ("keepFollowUpPrompts",),
    ("landingPageMode",),
    ("largeTextAsFile",),
    ("promptAutocomplete",),
    ("regenerateMenu",),
    ("renderMarkdownInAssistantMessages",),
    ("renderMarkdownInPreviews",),
    ("renderMarkdownInUserMessages",),
    ("responseAutoCopy",),
    ("richTextInput",),
    ("scrollOnBranchChange",),
    ("scrollOnResponseGeneration",),
    ("showChangelog",),
    ("showChatTitleInTab",),
    ("showEmojiInCall",),
    ("showFilesOnTerminalSelect",),
    ("showFloatingActionButtons",),
    ("showFormattingToolbar",),
    ("showUpdateToast",),
    ("showUsername",),
    ("splitLargeChunks",),
    ("stylizedPdfExport",),
    ("temporaryChatByDefault",),
    ("terminalFileDisplay",),
    ("terminalPreviewAllowSameOrigin",),
    ("textScale",),
    # Only the auto sub-key: the rest of `title` is not an interface option.
    ("title", "auto"),
    ("userLocation",),
    ("voiceInterruption",),
    ("webSearch",),
    ("widescreenMode",),
)

# The extra valves, and where each one lands in settings.ui. These are the user
# settings the native editor does not cover.
EXTRA_PATHS = {
    "desktop_notifications": ("notificationEnabled",),
    "notification_sound": ("notificationSound",),
    "notification_sound_when_focused": ("notificationSoundAlways",),
    "keyboard_shortcuts": ("keyboardShortcuts",),
    "memory": ("memory",),
    "system_prompt": ("system",),
    "hands_free_voice_calls": ("conversationMode",),
    "auto_send_after_transcription": ("speechAutoSend",),
    "auto_read_responses_aloud": ("responseAutoPlayback",),
    "speech_to_text_engine": ("audio", "stt", "engine"),
    "speech_to_text_language": ("audio", "stt", "language"),
    "text_to_speech_voice": ("audio", "tts", "voice"),
    "speech_playback_speed": ("audio", "tts", "playbackRate"),
    "allow_non_local_voices": ("audio", "tts", "nonLocalVoices"),
}

USER_CHUNK = 100

# Keeps a background bulk pass from being garbage-collected mid-run.
_BG_TASKS: set = set()


def _spawn(coro):
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task


def _mask_from_paths(paths) -> dict:
    """Build a nested dict shaped like the paths, so _subtract can walk it."""
    mask: dict = {}
    for path in paths:
        current = mask
        for part in path[:-1]:
            current = current.setdefault(part, {})
        current[path[-1]] = True
    return mask


def _assign(target: dict, path, value) -> None:
    current = target
    for part in path[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[path[-1]] = value


def _remove(target: dict, path) -> None:
    """Remove one path and any dict it leaves empty behind it."""
    if len(path) == 1:
        target.pop(path[0], None)
        return
    nested = target.get(path[0])
    if isinstance(nested, dict):
        _remove(nested, path[1:])
        if not nested:
            target.pop(path[0], None)


def _subtract(settings: dict, mask: dict) -> dict:
    """Return settings without the paths the mask names. Sub-keys the mask does
    not name survive, so clearing `title.auto` leaves the rest of `title` alone.
    """
    result = {}
    for key, value in settings.items():
        if key not in mask:
            result[key] = value
            continue
        masked = mask[key]
        if isinstance(masked, dict) and isinstance(value, dict):
            nested = _subtract(value, masked)
            if nested:
                result[key] = nested
    return result


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base and return a new dict, recursing into nested dicts
    so sub-keys the override omits survive. Neither input is mutated and the result
    shares no dict with override: one defaults snapshot is reused for every user,
    so handing out references would let one user's later write reach the others."""
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _action_buttons_or_none(raw):
    """Validate the floating-action-buttons JSON. Returns a clean button list, or
    None to mean 'do not manage', so a typo never pushes a broken set."""
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            raw = json.loads(raw)
        except ValueError:
            log.warning("interface-defaults: quick action JSON is invalid, ignoring")
            return None
    if not isinstance(raw, list) or not raw:
        return None
    buttons, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            return None
        button_id = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        prompt = item.get("prompt")
        if not button_id or not label or not isinstance(prompt, str) or not prompt:
            return None
        if button_id in seen:  # the frontend matches actions by id; dupes are ambiguous
            return None
        seen.add(button_id)
        buttons.append(
            {
                "id": button_id,
                "label": label,
                "input": bool(item.get("input", False)),
                "prompt": prompt,
            }
        )
    return buttons


class Event:
    class Valves(BaseModel):
        # ── actions ──────────────────────────────────────────────────────────
        apply_defaults_to_all_users: bool = Field(
            default=False,
            title="Apply Defaults to All Users",
            description=(
                f"**Overwrites.** Every setting configured in {ADMIN_LINK} is written "
                "into every existing user, replacing the choice they made for it. "
                "Settings you have not configured are left alone.\n\n"
                "One-shot: unticks itself on save and runs in the background."
            ),
        )
        reset_all_users_to_factory: bool = Field(
            default=False,
            title="Reset All Users to Factory",
            description=(
                "**Destructive, and it ignores your configuration.** Clears *every* "
                "interface setting from *every* user, including options you never "
                "configured, so the whole instance falls back to Open WebUI's built-ins "
                f"and to whatever you set in {ADMIN_LINK}.\n\n"
                "Chats, direct connections, tool servers, pinned models and the "
                "default model are **not** touched.\n\n"
                "One-shot: unticks itself on save and runs in the background."
            ),
        )
        bulk_users_per_second: int = Field(
            default=20,
            title="Bulk Write Rate",
            description=(
                "Users per second for either one-shot pass. Lower is gentler on the "
                "database, `0` runs flat out.\n\n"
                "---\n\n"
                "#### 🔔 Notifications"
            ),
        )

        # ── notifications ────────────────────────────────────────────────────
        desktop_notifications: bool = Field(
            default=False,
            title="Desktop Notifications",
            description="`Settings → Notifications`. Browser notifications for finished responses. Users still grant the browser permission themselves.",
        )
        notification_sound: bool = Field(
            default=True,
            title="Notification Sound",
            description="`Settings → Notifications`. Play a sound with in-app toast notifications.",
        )
        notification_sound_when_focused: bool = Field(
            default=False,
            title="Notification Sound While Tab Focused",
            description=(
                "Play the notification sound even while the tab is in the foreground. "
                "Open WebUI reads this setting but ships **no toggle for it anywhere**, "
                "so this valve is the only way to set it.\n\n"
                "---\n\n"
                "#### 💬 Interaction"
            ),
        )

        # ── interaction ──────────────────────────────────────────────────────
        keyboard_shortcuts: bool = Field(
            default=True,
            title="Keyboard Shortcuts",
            description="`Settings → Keyboard shortcuts`. Enable shortcuts and the hotkey hints shown in the UI.",
        )
        memory: bool = Field(
            default=False,
            title="Memory",
            description="`Settings → Personalization`. Enable the memory feature.",
        )
        system_prompt: str = Field(
            default="",
            title="System Prompt",
            description=(
                "`Settings → General`. The personal system prompt every user starts "
                "with. This is the *user-level* prompt, so a model's own system prompt "
                "still applies on top of it.\n\n"
                "---\n\n"
                "#### 🔊 Speech & Voice"
            ),
        )

        # ── speech and voice ─────────────────────────────────────────────────
        hands_free_voice_calls: bool = Field(
            default=False,
            title="Hands-Free Voice Calls",
            description="`Settings → Audio`. Start voice calls in hands-free conversation mode.",
        )
        auto_send_after_transcription: bool = Field(
            default=False,
            title="Auto-Send After Transcription",
            description="`Settings → Audio`. Send transcribed voice input as soon as speech recognition finishes.",
        )
        auto_read_responses_aloud: bool = Field(
            default=False,
            title="Auto-Read Responses Aloud",
            description="`Settings → Audio`. Read every response out loud automatically.",
        )
        speech_to_text_engine: Literal["", "web"] = Field(
            default="",
            title="Speech-to-Text Engine",
            description="`Settings → Audio`. Blank uses the engine configured in `Admin Panel → Settings → Audio`. `web` uses the browser's own recognition.",
        )
        speech_to_text_language: str = Field(
            default="",
            title="Speech-to-Text Language",
            description="`Settings → Audio`. Recognition language as ISO-639-1, for example `en`. Blank auto-detects.",
        )
        text_to_speech_voice: str = Field(
            default="",
            title="Text-to-Speech Voice",
            description="`Settings → Audio`. A browser voice name when no TTS engine is configured, otherwise a voice id from your configured engine.",
        )
        speech_playback_speed: float = Field(
            default=1.0,
            title="Speech Playback Speed",
            description="`Settings → Audio`. Speech playback rate. `1` is normal speed.",
        )
        allow_non_local_voices: bool = Field(
            default=False,
            title="Allow Non-Local Voices",
            description=(
                "`Settings → Audio`. Offer browser voices that are not provided by a "
                "local speech service.\n\n"
                "---\n\n"
                "#### ✨ Quick Actions"
            ),
        )

        # ── quick actions ────────────────────────────────────────────────────
        quick_action_buttons: str = Field(
            default="",
            title="Quick Action Buttons (JSON)",
            description=(
                "The buttons Open WebUI offers when a user selects text in a message. "
                f"There is a visual editor for these in {ADMIN_LINK}; this valve exists "
                "so a whole set can be pasted at once. Invalid JSON is ignored.\n\n"
                "```json\n"
                '[{"id": "summarize", "label": "Summarize", "input": false, '
                '"prompt": "Summarize this: {{SELECTED_CONTENT}}"}]'
                "\n"
                "```"
            ),
        )

    def __init__(self):
        self.valves = self.Valves()

    # ── config overlay ───────────────────────────────────────────────────────

    def _extras_from_valves(self) -> dict:
        """The settings.ui paths this function currently manages, as {path: value}.

        Open WebUI persists a function's valves with exclude_unset, so this is
        exactly the set the admin switched from Default to Custom.
        """
        chosen = self.valves.model_dump(exclude_unset=True)
        for key in NON_UI:
            chosen.pop(key, None)
        extras = {}
        for valve, value in chosen.items():
            if valve == "quick_action_buttons":
                buttons = _action_buttons_or_none(value)
                if buttons is None:
                    continue
                extras[("floatingActionButtons",)] = buttons
                continue
            path = EXTRA_PATHS.get(valve)
            if path:
                extras[path] = value
        return extras

    async def _sync_overlay(self) -> int:
        """Write our valves into the config row Open WebUI overlays onto users,
        and withdraw anything we wrote before that is back on Default."""
        from open_webui.models.config import Config

        defaults = await Config.get(DEFAULTS_CONFIG_KEY)
        defaults = dict(defaults) if isinstance(defaults, dict) else {}
        previous = await Config.get(OWNED_CONFIG_KEY)
        previous = (
            [tuple(path) for path in previous] if isinstance(previous, list) else []
        )

        extras = self._extras_from_valves()
        for path in previous:
            if path not in extras:
                _remove(defaults, path)
        for path, value in extras.items():
            _assign(defaults, path, value)

        await Config.upsert(
            {
                DEFAULTS_CONFIG_KEY: defaults,
                OWNED_CONFIG_KEY: [list(path) for path in extras],
            }
        )
        return len(extras)

    # ── bulk passes ──────────────────────────────────────────────────────────

    async def _iter_user_ids(self, chunk: int = USER_CHUNK):
        """Yield user ids a chunk at a time, keyset paginated on the primary key.
        A bulk pass runs for minutes, and an OFFSET would skip users when accounts
        are created or deleted mid-run. The session is closed before each pause."""
        from open_webui.internal.db import get_async_db_context
        from open_webui.models.users import User
        from sqlalchemy import select

        after = None
        while True:
            async with get_async_db_context() as db:
                stmt = select(User.id).order_by(User.id).limit(chunk)
                if after is not None:
                    stmt = stmt.where(User.id > after)
                ids = (await db.execute(stmt)).scalars().all()
            for user_id in ids:
                yield user_id
            if len(ids) < chunk:
                return
            after = ids[-1]

    async def _clear_user(self, user_id: str, mask: dict) -> bool:
        from open_webui.models.users import Users

        user = await Users.get_user_by_id(user_id)
        if not user:
            return False
        settings = user.settings.model_dump() if user.settings else {}
        ui = settings.get("ui") or {}
        stripped = _subtract(ui, mask)
        if stripped == ui:
            return False  # nothing of ours present: skip the write and its race window
        await Users.update_user_settings_by_id(user_id, {"ui": stripped})
        return True

    async def _write_user(self, user_id: str, defaults: dict) -> bool:
        from open_webui.models.users import Users

        user = await Users.get_user_by_id(user_id)
        if not user:
            return False
        settings = user.settings.model_dump() if user.settings else {}
        ui = settings.get("ui") or {}
        merged = _deep_merge(ui, defaults)
        if merged == ui:
            return False  # already conformant: skip the write and its race window
        await Users.update_user_settings_by_id(user_id, {"ui": merged})
        return True

    async def _bulk(self, payload: dict, rate: int, label: str, write: bool) -> None:
        if not payload:
            log.info("interface-defaults: %s found nothing configured to apply", label)
            return
        touch = self._write_user if write else self._clear_user
        cleared = 0
        try:
            async for user_id in self._iter_user_ids():
                try:
                    if await touch(user_id, payload):
                        cleared += 1
                except Exception:
                    log.exception(
                        "interface-defaults: %s failed for %s", label, user_id
                    )
                if rate > 0:
                    # Trickle instead of hammering the single database writer:
                    # thousands of users in one tight loop freezes a live instance.
                    await asyncio.sleep(1 / rate)
        except Exception:
            log.exception("interface-defaults: %s aborted early", label)
        log.info("interface-defaults: %s updated %d user(s)", label, cleared)

    async def _clear_triggers(self, function_id: str) -> None:
        """Untick the buttons in the DB, keeping the configured settings. The
        model write publishes nothing, so there is no re-fire loop."""
        from open_webui.models.functions import Functions

        valves = await Functions.get_function_valves_by_id(function_id)
        if not valves:
            # The model layer returns None on a read error; writing an `or {}`
            # fallback would silently erase the admin's whole config.
            return
        if not any(key in valves for key in TRIGGERS):
            return
        for key in TRIGGERS:
            valves.pop(key, None)
        await Functions.update_function_valves_by_id(function_id, valves)

    # ── event entry point ────────────────────────────────────────────────────

    async def event(
        self,
        event: Optional[dict] = None,
        __event_name__: str = "",
        __id__: str = "",
        __app__: Any = None,
        **kwargs,
    ):
        payload = event or {}

        # Drop a button ticked while the function was disabled, or left ticked by
        # a crash before the pass started, so it cannot fire late on a later save.
        if __event_name__ in ("function.enabled", "system.startup.completed"):
            if __event_name__ == "system.startup.completed" or (
                (payload.get("subject") or {}).get("id") == __id__
            ):
                await self._clear_triggers(__id__)
            return

        if __event_name__ != "function.valves_updated":
            return
        if (payload.get("subject") or {}).get("id") != __id__:
            return
        if (payload.get("data") or {}).get("scope") == "user":
            return  # per-user valves, not the admin config

        managed = await self._sync_overlay()
        log.info("interface-defaults: managing %d extra setting(s)", managed)

        do_reset = bool(self.valves.reset_all_users_to_factory)
        do_apply = bool(self.valves.apply_defaults_to_all_users)
        if not (do_reset or do_apply):
            return

        rate = max(0, int(self.valves.bulk_users_per_second or 0))
        await self._clear_triggers(__id__)

        if do_reset:
            mask = _mask_from_paths(
                list(NATIVE_INTERFACE_PATHS) + list(EXTRA_PATHS.values())
            )
            _spawn(self._bulk(mask, rate, "factory reset", write=False))
            return

        # Apply overwrites: the configured defaults are written into every user,
        # so a personal choice that disagrees with one of them is replaced.
        from open_webui.models.config import Config

        defaults = await Config.get(DEFAULTS_CONFIG_KEY)
        _spawn(
            self._bulk(
                defaults if isinstance(defaults, dict) else {},
                rate,
                "apply to all users",
                write=True,
            )
        )
