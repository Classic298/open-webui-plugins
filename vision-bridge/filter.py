"""
title: Vision Bridge
author: Classic298
author_url: https://github.com/Classic298
funding_url: https://github.com/Classic298
version: 1.0.2
description: Let a text-only model handle images without core changes: strips each image in the request to a file-id marker (pair with the analyze_image tool), or in describe mode swaps it for a text description.
"""

import re
import asyncio
import logging
from typing import Optional, Callable, Any

from pydantic import BaseModel, Field

from open_webui.models.users import Users
from open_webui.models.files import Files
from open_webui.models.chats import Chats
from open_webui.storage.provider import Storage
from open_webui.socket.main import get_event_emitter
from open_webui.utils.misc import get_message_list, add_or_update_system_message
from open_webui.utils.chat_id import is_saved_chat_id
from open_webui.utils.chat import generate_chat_completion
from open_webui.utils.files import get_image_base64_from_file_id

log = logging.getLogger(__name__)

_FILE_ID_RE = re.compile(r"/files/([^/]+)/content")


def _file_id_of(url: str) -> Optional[str]:
    m = _FILE_ID_RE.search(url or "")
    return m.group(1) if m else None


def _has_image(content: Any) -> bool:
    return isinstance(content, list) and any(isinstance(part, dict) and part.get("type") == "image_url" for part in content)


def _is_image(file: dict) -> bool:
    return file.get("type") == "image" or (file.get("content_type") or "").startswith("image/")


async def _stored_image_message(chat_id: str, user) -> Optional[dict]:
    """Newest message on the chat's current branch that still carries images."""
    chat = await Chats.get_chat_by_id_and_user_id(chat_id, user.id)
    if not chat:
        return None
    history = chat.chat.get("history", {})
    for msg in reversed(get_message_list(history.get("messages", {}), history.get("currentId")) or []):
        if msg.get("role") == "user" and any(isinstance(f, dict) and _is_image(f) for f in msg.get("files") or []):
            return msg
    return None


def _strip_images(content: list, strip_only: bool) -> str:
    """Keep the text parts, replace each image with a marker the text-only model can read."""
    texts, markers = [], []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            texts.append(part.get("text", ""))
        elif part.get("type") == "image_url":
            if not strip_only:
                markers.append("[Image attached — not sent to this model.]")
                continue
            # Only images still referenced by url have a file id: uploads are inlined by then.
            fid = _file_id_of((part.get("image_url") or {}).get("url", ""))
            markers.append(
                f'[Image attached — file_id: {fid}. Call analyze_image(file_id="{fid}", query="…") to inspect it.]'
                if fid else '[Image attached. Call analyze_image(query="…") to inspect the most recent image.]'
            )
    return "\n\n".join([*(t for t in texts if t), *markers]).strip()


class Filter:
    class Valves(BaseModel):
        strip_only: bool = Field(
            default=True,
            description="Just remove images from the request (replaced by a file-id marker), leaving them in the chat. Pair with the analyze_image tool for on-demand re-analysis. When false, the filter instead analyzes and swaps the image for text (needs vision_model_id).",
        )
        vision_model_id: str = Field(
            default="",
            description="Vision model used in describe mode (strip_only = false).",
        )
        analysis_prompt: str = Field(
            default="Describe this image in full detail. Transcribe any text verbatim.",
            description="Instruction sent to the vision model (describe mode).",
        )
        label: str = Field(default="Image description", description="Heading for the description (describe mode).")
        purge_from_history: bool = Field(default=True, description="Describe mode: replace the saved image with its description.")
        delete_file_record: bool = Field(default=True, description="Describe mode: delete the image file after analysis.")
        max_images: int = Field(default=4, description="Max images per message (describe mode).")

    def __init__(self):
        self.valves = self.Valves()

    async def inlet(
        self,
        body: dict,
        __request__: Any = None,
        __user__: Optional[dict] = None,
        __chat_id__: Optional[str] = None,
        __event_emitter__: Optional[Callable[[dict], Any]] = None,
    ) -> dict:
        messages = body.get("messages") or []
        vision_bridge_note = """
        [VISION BRIDGE TOOL POLICY]
        You are a text-only primary model with access to a separate vision model through Vision Bridge.
        Use the correct vision workflow depending on where the image is located.
        1. IMAGES ATTACHED TO THE CONVERSATION
        If an image is attached to the conversation or represented by a marker such as:
        [Image attached — file_id: ...]
        or:
        [Image attached. Call analyze_image(...) ...]
        use `analyze_image`.
        If a file_id is available, pass that exact file_id to `analyze_image`.
        Do not attempt to inspect such images yourself.
        2. IMAGES STORED IN THE OPEN TERMINAL
        If an image exists as a file inside the currently connected Open Terminal, use:
        `analyze_terminal_image(path="...", query="...")`
        to inspect it.
        Examples include PNG, JPG, JPEG and WebP files created by Python, Pillow, ImageMagick, ffmpeg, rendering scripts, or other terminal commands.
        IMPORTANT:
        Do NOT call `read_file` before `analyze_terminal_image`.
        Do NOT use `read_file` for visual inspection of terminal image files.
        `analyze_terminal_image` reads the image from the terminal internally and sends it directly to the separate vision model.
        Use `read_file` normally for text files, source code, JSON, logs, configuration files, and other non-image content.
        3. VISUAL VERIFICATION
        When a task requires understanding, describing, evaluating, comparing, or verifying the actual appearance of an image, you MUST use the appropriate vision tool before completing the task.
        Do not infer what an image looks like solely from:
        - the code that generated it,
        - the prompt used to create it,
        - file metadata,
        - filenames,
        - image dimensions,
        - or successful command execution.
        A message such as:
        "Image file read successfully"
        is NOT visual analysis.
        4. GENERATED IMAGES
        When you generate or modify an image in the terminal and visual verification is relevant:
        1. Create or modify the image.
        2. Call `analyze_terminal_image` on the resulting image file.
        3. Evaluate the vision model's response.
        4. If necessary, modify the image again.
        5. Re-analyze the new result.
        6. Continue until the requested visual result is achieved or further iteration is unnecessary.
        Do not stop after merely generating the file if the task requires checking its appearance.
        5. ANIMATIONS AND GIFS
        If reliable visual inspection of an animation or GIF is required and direct inspection is unsuitable, use the terminal to extract one or more representative frames as PNG files and inspect those frames using `analyze_terminal_image`.
        Use the vision model's actual observations as visual evidence.
        """.strip()

        system_content = next(
            (
                str(msg.get("content", ""))
                for msg in messages
                if msg.get("role") == "system"
            ),
            "",
        )

        if "[VISION BRIDGE TOOL POLICY]" not in system_content:
            messages = add_or_update_system_message(
                vision_bridge_note,
                messages,
                append=True,
            )
            body["messages"] = messages        

        # Describe mode covers the newest image message; the strip below catches every other image.
        if not self.valves.strip_only and self.valves.vision_model_id and (__user__ or {}).get("id"):
            target = next(
                (msg for msg in reversed(messages) if msg.get("role") == "user" and _has_image(msg.get("content"))),
                None,
            )
            if target:
                user = await Users.get_user_by_id(__user__["id"])
                if user:
                    await self._describe(target, user, __request__, __chat_id__, __event_emitter__)
        user = None
        if self.valves.strip_only and __request__ and (__user__ or {}).get("id"):
            user = await Users.get_user_by_id(__user__["id"])

        for msg in messages:
            if _has_image(msg.get("content")):
                if self.valves.strip_only and user and msg.get("role") == "user":
                    content = msg.get("content") or []

                    text = " ".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    )

                    if "images from the tool results above" in text:
                        for part in content:
                            if (
                                not isinstance(part, dict)
                                or part.get("type") != "image_url"
                            ):
                                continue

                            url = (part.get("image_url") or {}).get("url", "")

                            if url.startswith("data:image/"):
                                try:
                                    stored_url = await get_image_url_from_base64(
                                        __request__,
                                        url,
                                        {},
                                        user,
                                    )

                                    if stored_url:
                                        part["image_url"]["url"] = stored_url

                                except Exception:
                                    log.exception(
                                        "Vision Bridge: failed to persist tool-result image"
                                    )

                msg["content"] = _strip_images(
                    msg["content"],
                    self.valves.strip_only,
                )

        return body

    async def _describe(self, target, user, request, chat_id, event_emitter):
        async def status(text, done=False):
            if event_emitter:
                await event_emitter({"type": "status", "data": {"description": text, "done": done}})

        texts, data_urls, image_count = [], [], 0
        for part in target["content"]:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                texts.append(part.get("text", ""))
            elif part.get("type") == "image_url":
                image_count += 1
                url = (part.get("image_url") or {}).get("url", "")
                if url.startswith("data:"):
                    data_urls.append(url)
                else:
                    fid = _file_id_of(url)
                    du = await get_image_base64_from_file_id(fid, user=user) if fid else None
                    if du:
                        data_urls.append(du)

        data_urls = data_urls[: self.valves.max_images]
        if not data_urls:
            return

        user_text = "\n\n".join(t for t in texts if t).strip()
        await status(f"Analyzing {len(data_urls)} image(s) with {self.valves.vision_model_id}…")
        try:
            parts = [{"type": "text", "text": self.valves.analysis_prompt}]
            parts += [{"type": "image_url", "image_url": {"url": du}} for du in data_urls]
            resp = await generate_chat_completion(
                request,
                {"model": self.valves.vision_model_id, "messages": [{"role": "user", "content": parts}], "stream": False},
                user=user, bypass_filter=True,
            )
            description = resp["choices"][0]["message"]["content"]
        except Exception as e:
            log.exception("Vision Bridge analysis failed")
            # Keep the image: a failed analysis must not consume it.
            target["content"] = f"{user_text}\n\n[image analysis failed: {e}]".strip()
            await status("Image analysis failed", done=True)
            return

        merged = f"{user_text}\n\n[{self.valves.label}]\n{description}".strip()
        skipped = image_count - len(data_urls)
        if skipped:
            merged += f"\n\n[{skipped} further image(s) attached — not sent to this model.]"
        target["content"] = merged
        await status("Done", done=True)

        # Purge only when every image was described (_persist drops all of the message's images).
        if not skipped and is_saved_chat_id(chat_id):
            stored = await _stored_image_message(chat_id, user)
            if stored:
                await self._persist(chat_id, user, stored, merged)

    async def _persist(self, chat_id, user, message, new_content):
        files = message.get("files") or []
        images = [f for f in files if isinstance(f, dict) and _is_image(f)]
        if self.valves.purge_from_history:
            kept = [f for f in files if not (isinstance(f, dict) and _is_image(f))]
            mid = message["id"]
            await Chats.upsert_message_to_chat_by_id_and_message_id(chat_id, mid, {"files": kept, "content": new_content})
            try:
                emit = await get_event_emitter({"chat_id": chat_id, "message_id": mid, "user_id": user.id}, update_db=False)
                await emit({"type": "files", "data": {"files": kept}})
                await emit({"type": "replace", "data": {"content": new_content}})
            except Exception:
                log.exception("Vision Bridge: client sync failed for %s", mid)
        if self.valves.delete_file_record:
            for image in images:
                fid = image.get("id") or _file_id_of(image.get("url", ""))
                try:
                    f = await Files.get_file_by_id(fid) if fid else None
                    if f and (f.user_id == user.id or user.role == "admin"):
                        if await Files.delete_file_by_id(fid) and f.path:
                            await asyncio.to_thread(Storage.delete_file, f.path)
                except Exception:
                    log.exception("Vision Bridge: delete failed for %s", fid)
