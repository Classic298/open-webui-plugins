"""
title: Vision Bridge
author: Classic298
author_url: https://github.com/Classic298
funding_url: https://github.com/Classic298
version: 1.0.1
description: Let a text-only model inspect images on demand via analyze_image(file_id, query), sending them to a configured vision model; pair with the Vision Bridge filter so the image never reaches the text-only model.
"""

import re
import logging
from typing import Optional, Callable, Any

from pydantic import BaseModel, Field

from open_webui.models.users import Users
from open_webui.models.chats import Chats
from open_webui.utils.misc import get_message_list
from open_webui.utils.chat_id import is_saved_chat_id
from open_webui.utils.chat import generate_chat_completion
from open_webui.utils.files import get_image_base64_from_file_id

log = logging.getLogger(__name__)

_FILE_ID_RE = re.compile(r"/files/([^/]+)/content")


def _file_id_of(url: str) -> Optional[str]:
    m = _FILE_ID_RE.search(url or "")
    return m.group(1) if m else None


def _is_image(file: dict) -> bool:
    return file.get("type") == "image" or (file.get("content_type") or "").startswith("image/")


class Tools:
    class Valves(BaseModel):
        vision_model_id: str = Field(
            default="",
            description="Model id of a vision-capable model used to analyze images (e.g. gpt-4o, a multimodal OpenRouter model).",
        )
        default_query: str = Field(
            default="Describe this image in full detail. Transcribe any text verbatim.",
            description="Question used when the model calls the tool without one.",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def analyze_image(
        self,
        query: str = "",
        file_id: str = "",
        __request__: Any = None,
        __user__: Optional[dict] = None,
        __chat_id__: Optional[str] = None,
        __messages__: Optional[list] = None,
        __event_emitter__: Optional[Callable[[dict], Any]] = None,
    ) -> str:
        """
        Inspect an image attached to this chat and answer a question about it.

        You cannot see images yourself. When the conversation references an attached image
        (you will see a marker like "[Image attached — file_id: ...]"), call this tool with
        that file_id and your question. You can call it again with a different question about
        the same image at any time.

        :param query: The specific question to answer about the image (e.g. "what are the dimensions of the table?", "read the serial number"). Leave empty for a full description.
        :param file_id: The file id of the image to inspect, taken from the "[Image attached — file_id: ...]" marker. Omit to use the most recent image in the chat.
        :return: The vision model's answer as text.
        """

        async def status(d, done=False):
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": d, "done": done}})

        if not self.valves.vision_model_id:
            return "Vision Bridge is not configured: set a vision_model_id in the tool valves."

        if not __user__ or not __user__.get("id"):
            return "No user context available."
        user = await Users.get_user_by_id(__user__["id"])
        if not user:
            return "User not found."

        data_url = await self._resolve(file_id.strip(), user, __chat_id__, __messages__)
        if not data_url:
            return "No matching image found (it may have been deleted, or the file id is wrong)."

        await status(f"Looking at the image with {self.valves.vision_model_id}…")
        prompt = query.strip() or self.valves.default_query
        try:
            response = await generate_chat_completion(
                __request__,
                {
                    "model": self.valves.vision_model_id,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ]}],
                    "stream": False,
                },
                user=user, bypass_filter=True,
            )
            answer = response["choices"][0]["message"]["content"]
        except Exception as e:
            log.exception("Vision Bridge analysis failed")
            return f"Vision analysis failed: {e}"

        await status("Done", done=True)
        return answer

    async def _resolve(self, file_id, user, chat_id, messages):
        if file_id:
            return await get_image_base64_from_file_id(file_id, user=user)
        if is_saved_chat_id(chat_id):
            chat = await Chats.get_chat_by_id_and_user_id(chat_id, user.id)
            if chat:
                history = chat.chat.get("history", {})
                chain = get_message_list(history.get("messages", {}), history.get("currentId"))
                for msg in reversed(chain or []):
                    if msg.get("role") != "user":
                        continue
                    for f in msg.get("files") or []:
                        if isinstance(f, dict) and _is_image(f):
                            fid = f.get("id") or _file_id_of(f.get("url", ""))
                            if fid:
                                return await get_image_base64_from_file_id(fid, user=user)
        for msg in reversed(messages or []):
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for part in msg["content"]:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        url = (part.get("image_url") or {}).get("url", "")
                        if url.startswith("data:"):
                            return url
        return None
