"""
title: Interface Defaults
author: Classic298
author_url: https://github.com/Classic298
funding_url: https://github.com/Classic298
version: 1.1.2
required_open_webui_version: 0.10.2
description: Manage Settings > Interface defaults instance-wide from this function's Valves. Only settings you switch to Custom are managed; anything left on Default is never written, so users keep their own choice for it. New users are seeded automatically (subscribes to user.created, which fires for signup, OAuth, LDAP, SCIM and admin-created accounts). Two trigger toggles act as one-shot buttons: "Apply to all existing users" pushes your Custom settings to everyone (normally only needed once, right after install), and "Reset all users to factory" clears the interface settings this function manages from every user AND puts this config back to Default. Both only touch those interface settings; a user's system prompt, default model, audio and other preferences are preserved unchanged. Tick a trigger and Save; it unticks itself and runs in the background over the users in chunks. Booleans render as toggles, direction as a dropdown, text scale as a number. No custom UI, no monkey-patching, no startup hooks. Defaults below match Open WebUI's factory values.
"""

import asyncio
import json
import logging
from copy import deepcopy
from typing import Literal, Optional

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# Valve fields that are NOT interface settings (excluded when building ui).
_TRIGGERS = ("apply_to_all_existing_users", "reset_all_users_to_factory")
_NON_UI = _TRIGGERS + ("bulk_users_per_second",)

# Users are read in chunks so a bulk pass never loads a whole large instance.
_USER_CHUNK = 100

# Hold references to background bulk tasks so the loop cannot garbage-collect one
# mid-run (per asyncio.create_task's documented caveat).
_BG_TASKS: set = set()


def _spawn(coro):
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task


def _pixels_or_blank(value) -> str:
    """A compression side is a positive pixel count or blank (no limit). '0' is
    truthy in JS and would resize to a 0px canvas; junk yields NaN dimensions.
    isdecimal (not isdigit) so superscripts don't crash int(); str(int()) folds
    non-ASCII decimals like Arabic-Indic to plain ASCII the frontend can parse."""
    text = str(value or "").strip()
    return str(int(text)) if text.isdecimal() and int(text) > 0 else ""


def _action_buttons_or_none(raw):
    """Validate the floating-action-buttons JSON. Returns a clean list of
    {id, label, input, prompt} buttons, or None to mean 'do not manage' when the
    valve is blank or malformed (all-or-nothing, so a typo never pushes a broken
    set). Canonicalises to exactly the four keys Open WebUI reads."""
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            raw = json.loads(raw)
        except ValueError:
            log.warning(
                "interface-defaults: floating_action_buttons is not valid JSON, ignoring"
            )
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


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base and return a new dict, recursing into nested
    dicts so sub-keys the override omits survive. Neither input is mutated, and
    the result shares no dict with override: one ui snapshot is reused for every
    user, so handing out references would let one user's write reach the others.
    """
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = deepcopy(value)
    return merged


class Event:
    class Valves(BaseModel):
        # ── UI ──────────────────────────────────────────────────────────────
        textScale: float = Field(
            title="Text Scale", default=1.0, description="UI scale (1.0 - 1.5)"
        )
        highContrastMode: bool = Field(
            title="High Contrast Mode", default=False, description="High contrast mode"
        )
        showChatTitleInTab: bool = Field(
            title="Chat Title in Browser Tab",
            default=True,
            description="Display chat title in browser tab",
        )
        notificationSound: bool = Field(
            title="Notification Sound", default=True, description="Notification sound"
        )
        notificationSoundAlways: bool = Field(
            title="Always Play Notification Sound",
            default=False,
            description="Always play notification sound",
        )
        userLocation: bool = Field(
            title="Allow User Location",
            default=False,
            description="Allow access to user location",
        )
        hapticFeedback: bool = Field(
            title="Haptic Feedback",
            default=False,
            description="Haptic feedback (Android)",
        )
        copyFormatted: bool = Field(
            title="Copy Formatted Text",
            default=False,
            description="Copy formatted text",
        )
        showUpdateToast: bool = Field(
            title="Update Available Toast",
            default=True,
            description="Toast notifications for new updates (admin)",
        )
        showChangelog: bool = Field(
            title="What's New on Login",
            default=True,
            description='Show "What\'s New" modal on login (admin)\n\n---\n\n#### 💬 Chat Behavior',
        )

        # ── Chat ────────────────────────────────────────────────────────────
        enableMessageQueue: bool = Field(
            title="Message Queue", default=True, description="Enable message queue"
        )
        chatDirection: Literal["auto", "LTR", "RTL"] = Field(
            title="Chat Direction",
            default="auto",
            description="Chat text direction",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "auto", "label": "Auto (follow the interface language)"},
                        {"value": "LTR", "label": "Left to Right"},
                        {"value": "RTL", "label": "Right to Left"},
                    ],
                }
            },
        )
        landingPageMode: Literal["", "chat"] = Field(
            title="Landing Page Mode",
            default="",
            description="Which view users land on after opening Open WebUI",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "", "label": "Default (home screen)"},
                        {"value": "chat", "label": "Chat"},
                    ],
                }
            },
        )
        chatBubble: bool = Field(
            title="Chat Bubble UI", default=True, description="Chat bubble UI"
        )
        showUsername: bool = Field(
            title="Show Username Instead of You",
            default=False,
            description="Display username instead of You (bubble UI off)",
        )
        widescreenMode: bool = Field(
            title="Widescreen Mode", default=False, description="Widescreen mode"
        )
        temporaryChatByDefault: bool = Field(
            title="Temporary Chats by Default",
            default=False,
            description="New chats are temporary by default",
        )
        chatFadeStreamingText: bool = Field(
            title="Fade Streaming Text",
            default=True,
            description="Fade effect for streaming text",
        )
        renderMarkdownInUserMessages: bool = Field(
            title="Markdown in User Messages",
            default=True,
            description="Render markdown in user messages",
        )
        renderMarkdownInAssistantMessages: bool = Field(
            title="Markdown in Assistant Messages",
            default=True,
            description="Render markdown in assistant messages",
        )
        titleAutoGenerate: bool = Field(
            title="Auto-Generate Titles",
            default=True,
            description="Title auto-generation",
        )
        autoFollowUps: bool = Field(
            title="Auto-Generate Follow-Ups",
            default=True,
            description="Follow-up auto-generation",
        )
        autoTags: bool = Field(
            title="Auto-Generate Tags",
            default=True,
            description="Chat tags auto-generation",
        )
        responseAutoCopy: bool = Field(
            title="Auto-Copy Responses",
            default=False,
            description="Auto-copy response to clipboard",
        )
        insertSuggestionPrompt: bool = Field(
            title="Insert Suggestion Prompts",
            default=False,
            description="Insert suggestion prompt to input",
        )
        keepFollowUpPrompts: bool = Field(
            title="Keep Follow-Up Prompts",
            default=False,
            description="Keep follow-up prompts in chat",
        )
        insertFollowUpPrompt: bool = Field(
            title="Insert Follow-Up Prompts",
            default=False,
            description="Insert follow-up prompt to input",
        )
        regenerateMenu: bool = Field(
            title="Regenerate Menu", default=True, description="Regenerate menu"
        )
        collapseCodeBlocks: bool = Field(
            title="Collapse Code Blocks",
            default=False,
            description="Always collapse code blocks",
        )
        expandDetails: bool = Field(
            title="Expand Details", default=False, description="Always expand details"
        )
        renderMarkdownInPreviews: bool = Field(
            title="Markdown in Previews",
            default=True,
            description="Render markdown in previews",
        )
        displayMultiModelResponsesInTabs: bool = Field(
            title="Multi-Model Responses in Tabs",
            default=False,
            description="Display multi-model responses in tabs",
        )
        scrollOnBranchChange: bool = Field(
            title="Scroll on Branch Change",
            default=True,
            description="Scroll on branch change",
        )
        scrollOnResponseGeneration: bool = Field(
            title="Scroll on Response Generation",
            default=True,
            description="Scroll along while a response is generated (0.11.0+)",
        )
        showFilesOnTerminalSelect: bool = Field(
            title="Files on Terminal Select",
            default=True,
            description="Show files on terminal select",
        )
        stylizedPdfExport: bool = Field(
            title="Stylized PDF Export", default=True, description="Stylized PDF export"
        )
        showFloatingActionButtons: bool = Field(
            title="Floating Quick Actions",
            default=True,
            description="Floating quick actions",
        )
        floatingActionButtons: str = Field(
            title="Floating Quick Action Buttons (JSON)",
            default="",
            description='The actual quick-action buttons shown when text is selected, as a JSON array (leave Default to keep Open WebUI\'s built-in Ask/Explain). Each button is {"id","label","input","prompt"}; prompt supports {{SELECTED_CONTENT}}, {{CONTENT}} and {{INPUT_CONTENT}}. See the plugin README for a copy-paste tutorial and admin ideas. Invalid JSON is ignored.\n\n---\n\n#### ⌨️ Input',
        )

        # ── Input ───────────────────────────────────────────────────────────
        ctrlEnterToSend: bool = Field(
            title="Ctrl+Enter to Send",
            default=False,
            description="Ctrl+Enter to send (off = Enter to send)",
        )
        richTextInput: bool = Field(
            title="Rich Text Input",
            default=True,
            description="Rich text input for chat",
        )
        promptAutocomplete: bool = Field(
            title="Prompt Autocomplete",
            default=False,
            description="Prompt autocompletion",
        )
        showFormattingToolbar: bool = Field(
            title="Formatting Toolbar",
            default=False,
            description="Show formatting toolbar (rich text on)",
        )
        insertPromptAsRichText: bool = Field(
            title="Insert Prompts as Rich Text",
            default=False,
            description="Insert prompt as rich text (rich text on)",
        )
        largeTextAsFile: bool = Field(
            title="Paste Large Text as File",
            default=False,
            description="Paste large text as a file\n\n---\n\n#### 🧩 Artifacts",
        )

        # ── Artifacts ───────────────────────────────────────────────────────
        detectArtifacts: bool = Field(
            title="Detect Artifacts",
            default=True,
            description="Detect artifacts automatically",
        )
        iframeSandboxAllowSameOrigin: bool = Field(
            title="iframe Sandbox Allow Same Origin",
            default=False,
            description="Let sandboxed iframes (rendered HTML: artifacts, previews, embeds) access the same origin as Open WebUI",
        )
        iframeSandboxAllowForms: bool = Field(
            title="iframe Sandbox Allow Forms",
            default=False,
            description="Let sandboxed iframes (rendered HTML: artifacts, previews, embeds) submit forms\n\n---\n\n#### 🎙️ Voice & Calls",
        )

        # ── Voice ───────────────────────────────────────────────────────────
        voiceInterruption: bool = Field(
            title="Voice Interruption in Call",
            default=False,
            description="Allow voice interruption in call",
        )
        showEmojiInCall: bool = Field(
            title="Emoji in Call",
            default=False,
            description="Display emoji in call\n\n---\n\n#### 📎 Files & Search",
        )

        # ── File ────────────────────────────────────────────────────────────
        defaultUploadContext: Literal["focused", "full"] = Field(
            title="Default File Upload Context",
            default="focused",
            description="How attached files are sent to the model by default (0.11.0+)",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "focused", "label": "Using Focused Retrieval"},
                        {"value": "full", "label": "Using Entire Document"},
                    ],
                }
            },
        )
        imageCompression: bool = Field(
            title="Image Compression",
            default=False,
            description="Compress images before upload",
        )
        imageCompressionInChannels: bool = Field(
            title="Image Compression in Channels",
            default=True,
            description="Compress images in channels (compression on)",
        )
        imageCompressionWidth: str = Field(
            title="Max Image Width (px)",
            default="",
            description="Max image width in px (blank = no limit)",
        )
        imageCompressionHeight: str = Field(
            title="Max Image Height (px)",
            default="",
            description="Max image height in px (blank = no limit)",
        )

        # Reassembled into their real ui shape on apply:
        webSearchAlways: bool = Field(
            title="Web Search by Default",
            default=False,
            description="Enable web search by default (maps to webSearch='always')\n\n---\n\n#### ⚡ One-Shot Actions",
        )

        bulk_users_per_second: int = Field(
            title="Bulk Speed (Users per Second)",
            default=20,
            description="Speed limit for the two bulk actions below, in users per second, so applying to thousands of users never freezes the instance (0 = no limit).",
        )

        # --- one-shot trigger "buttons" (tick + Save; they untick themselves) ---
        apply_to_all_existing_users: bool = Field(
            title="Apply to All Existing Users",
            default=False,
            description="▶️ **Button, one-time, post-install.** Tick + Save to push the settings you switched to **Custom** above to **all existing users**. Settings left on **Default** are not touched, so every user keeps their own choice for those. **New users are always seeded automatically** on signup while this function is enabled, with or without this button; it only exists to catch up the users who were created before installation. Runs slowly in the background at the rate set above, so the instance stays responsive, and unticks itself.",
        )
        reset_all_users_to_factory: bool = Field(
            title="Reset All Users to Factory",
            default=False,
            description="⚠️ **Button, full factory reset.** Tick + Save to clear **every interface setting this function manages** for **every user** (reverting everyone to Open WebUI's built-in defaults for those, even ones you never pushed) **and** put every setting above back to **Default**, so nothing is managed any more. Other preferences (system prompt, default model, audio, notifications) are left untouched. Unticks itself.",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _ui_from_valves(self) -> dict:
        """The interface ui keys to write into a user.

        Only settings switched to Custom in the Valves UI are stored (Open WebUI
        persists valves with exclude_unset), so those are exactly the ones this
        function manages. Fields left on Default are never written, and every
        user keeps whatever they chose for them.
        """
        ui = self.valves.model_dump(exclude_unset=True)
        for key in _NON_UI:
            ui.pop(key, None)
        if "textScale" in ui:
            ui["textScale"] = min(
                1.5, max(1.0, ui["textScale"])
            )  # slider range; 15 would be 15x text
        if "floatingActionButtons" in ui:
            # str valve holding JSON -> the array the frontend reads, or drop it
            buttons = _action_buttons_or_none(ui.pop("floatingActionButtons"))
            if buttons is not None:
                ui["floatingActionButtons"] = buttons
        if "titleAutoGenerate" in ui:
            ui["title"] = {"auto": ui.pop("titleAutoGenerate")}
        if "webSearchAlways" in ui:
            ui["webSearch"] = "always" if ui.pop("webSearchAlways") else None
        # Nested key: emit only the customized sides, _deep_merge keeps the rest.
        compression_size = {
            side: _pixels_or_blank(ui.pop(valve))
            for side, valve in (
                ("width", "imageCompressionWidth"),
                ("height", "imageCompressionHeight"),
            )
            if valve in ui
        }
        if compression_size:
            ui["imageCompressionSize"] = compression_size
        return ui

    async def _iter_user_ids(self, chunk: int = _USER_CHUNK):
        """Yield user ids a chunk at a time. Users.get_users() would load every
        user, each carrying their whole settings blob, and re-run a COUNT per
        page; we only need ids because _seed_user re-reads the user anyway.
        Keyset paginated on the primary key: a bulk pass runs for minutes, and
        an OFFSET would skip users when accounts are created or deleted mid-run.
        The session is closed before each pause so nothing is held while paced."""
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

    async def _seed_user(self, user_id: str, ui: dict) -> bool:
        from open_webui.models.users import Users

        if not ui:
            return False
        user = await Users.get_user_by_id(user_id)
        if not user:
            return False
        settings = user.settings.model_dump() if user.settings else {}
        current_ui = settings.get("ui") or {}
        merged = _deep_merge(current_ui, ui)
        if merged == current_ui:
            return False  # already conformant: skip the write and its race window
        await Users.update_user_settings_by_id(user_id, {"ui": merged})
        return True

    async def _apply_to_all(self, ui: dict, rate: int = 20):
        if not ui:
            log.info(
                "interface-defaults: nothing to apply, no setting is set to Custom"
            )
            return
        applied = 0
        try:
            async for user_id in self._iter_user_ids():
                try:
                    if await self._seed_user(user_id, ui):
                        applied += 1
                except Exception:
                    log.exception("interface-defaults: apply failed for %s", user_id)
                if rate > 0:
                    # Trickle instead of hammering the single database writer:
                    # 4000+ users in one tight loop freezes a live instance.
                    await asyncio.sleep(1 / rate)
        except Exception:
            # A chunk-read error escapes the per-user guard; log it rather than
            # dying silently and leaving the pass half-applied with no trace.
            log.exception("interface-defaults: apply pass aborted early")
        log.info("interface-defaults: applied defaults to %d existing user(s)", applied)

    def _managed_ui_keys(self) -> set:
        """Top-level settings.ui keys this function owns. `title` is excluded: we
        only own its `auto` sub-key, the rest of that dict belongs to Open WebUI."""
        sources = {
            "titleAutoGenerate",
            "webSearchAlways",
            "imageCompressionWidth",
            "imageCompressionHeight",
        }
        plain = set(self.Valves.model_fields) - set(_NON_UI) - sources
        return plain | {"webSearch", "imageCompressionSize"}

    async def _reset_user(self, user_id: str, managed: set) -> bool:
        from open_webui.models.users import Users

        user = await Users.get_user_by_id(user_id)
        if not user:
            return False
        settings = user.settings.model_dump() if user.settings else {}
        ui = settings.get("ui") or {}
        new_ui = {k: v for k, v in ui.items() if k not in managed}
        title = new_ui.get("title")
        if isinstance(title, dict):
            siblings = {k: v for k, v in title.items() if k != "auto"}
            if siblings:
                new_ui["title"] = siblings
            else:
                new_ui.pop("title", None)
        if new_ui == ui:
            return False  # no managed key present: nothing to clear, skip the write
        await Users.update_user_settings_by_id(user_id, {"ui": new_ui})
        return True

    async def _reset_all(self, rate: int = 20):
        # settings.ui holds the user's WHOLE settings store (system prompt, default
        # model, audio, notification webhook, pinned models), not just the Interface
        # tab, so clear the interface keys instead of wiping ui.
        managed = self._managed_ui_keys()
        reset = 0
        try:
            async for user_id in self._iter_user_ids():
                try:
                    if await self._reset_user(user_id, managed):
                        reset += 1
                except Exception:
                    log.exception("interface-defaults: reset failed for %s", user_id)
                if rate > 0:
                    await asyncio.sleep(1 / rate)
        except Exception:
            log.exception("interface-defaults: reset pass aborted early")
        log.info("interface-defaults: reset %d user(s) to factory defaults", reset)

    async def _clear_triggers(self, function_id: str):
        """Untick the trigger toggles in the DB (keeps the configured settings).
        The model write does not publish the event, so there is no re-fire loop."""
        from open_webui.models.functions import Functions

        valves = await Functions.get_function_valves_by_id(function_id)
        if not valves:
            # The model layer swallows read errors and returns None; writing the
            # `or {}` fallback would silently erase the admin's whole config.
            return
        if not any(key in valves for key in _TRIGGERS):
            return  # nothing ticked: no write (keeps the startup sweep cheap)
        for key in _TRIGGERS:
            valves.pop(key, None)
        await Functions.update_function_valves_by_id(function_id, valves)

    async def _reset_valves(self, function_id: str):
        """Restore this function's config to factory: every field back to Default,
        i.e. nothing is managed. Storing the dumped defaults instead would mark
        all of them as explicitly set, so the next apply would push all of them."""
        from open_webui.models.functions import Functions

        await Functions.update_function_valves_by_id(function_id, {})

    # ── event entry point ────────────────────────────────────────────────────

    async def event(
        self,
        event: Optional[dict] = None,
        __event_name__: str = "",
        __id__: str = "",
        **kwargs
    ):
        payload = event or {}

        # 1) Seed every brand-new user (signup, oauth, ldap, scim, admin-created).
        if __event_name__ == "user.created":
            user_id = (payload.get("subject") or {}).get("id")
            if user_id:
                await self._seed_user(user_id, self._ui_from_valves())
            return

        # 2) Drop a trigger that never ran: ticked while disabled (valves save
        # without dispatch), or persisted by a crash between the valves save and
        # the untick. Either way it must not fire late on some later save.
        if __event_name__ in ("function.enabled", "system.startup.completed"):
            if (
                __event_name__ == "system.startup.completed"
                or (payload.get("subject") or {}).get("id") == __id__
            ):
                await self._clear_triggers(__id__)
            return

        # 3) Trigger buttons: fire when THIS function's admin valves are saved.
        if __event_name__ == "function.valves_updated":
            if (payload.get("subject") or {}).get("id") != __id__:
                return
            if (payload.get("data") or {}).get("scope") == "user":
                return  # per-user valves, not the admin config (no UserValves today)
            do_reset = bool(self.valves.reset_all_users_to_factory)
            do_apply = bool(self.valves.apply_to_all_existing_users)
            rate = max(0, int(self.valves.bulk_users_per_second or 0))
            if not (do_reset or do_apply):
                return
            # Bulk op runs in the background so the admin's Save returns immediately.
            if do_reset:
                # Full factory reset: restore this config to defaults AND clear every user.
                await self._reset_valves(__id__)
                _spawn(self._reset_all(rate))
            elif do_apply:
                # Snapshot the configured ui first, then untick only the trigger so the
                # configured settings are kept (new users keep getting seeded with them).
                ui = self._ui_from_valves()
                await self._clear_triggers(__id__)
                _spawn(self._apply_to_all(ui, rate))
