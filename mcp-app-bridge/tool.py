"""
title: MCP App Bridge
author: Classic298
author_url: https://github.com/Classic298
funding_url: https://github.com/Classic298
version: 0.7.0
description: Wraps MCP server tools and renders MCP App UI resources (ui://) as Rich UI embeds using Open WebUI's existing embed system. Context-efficient discovery: paginated summary listing plus keyword search, so full schemas are only loaded for the top matching tools. Spec-compliant: honors server-declared CSP, dispatches ui/notifications/tool-result for AppBridge SDK compatibility. Authenticates with a static bearer token or with per-user OAuth 2.1 (dynamic client registration or static credentials), reusing Open WebUI's own MCP OAuth machinery. No middleware changes needed.
"""

import json
import logging
from typing import Literal
from contextlib import AsyncExitStack

from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

LIST_PAGE_SIZE = 25
SEARCH_RESULT_LIMIT = 5

# Prefix for the OAuth client this tool registers with Open WebUI's client
# manager. Kept distinct from the "mcp:<server_id>" keys used by admin-configured
# MCP tool servers so the two never collide.
OAUTH_CLIENT_PREFIX = "mcp:tool"

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_dict(obj) -> dict:
    """Convert an MCP SDK model or dict to a plain dict."""
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return obj
    return {}


def _extract_ui_meta(tool) -> dict:
    """Extract the _meta.ui dict from a tool definition."""
    meta_dict = _to_dict(getattr(tool, "meta", None))
    if not meta_dict:
        return {}

    # Nested format: _meta.ui
    ui_meta = meta_dict.get("ui", {})
    if isinstance(ui_meta, dict):
        return ui_meta

    return {}


def _extract_ui_resource_uri(tool) -> str | None:
    """Extract ui:// resource URI from tool metadata, if present."""
    ui_meta = _extract_ui_meta(tool)

    # Nested format: _meta.ui.resourceUri
    uri = ui_meta.get("resourceUri", "")
    if isinstance(uri, str) and uri.startswith("ui://"):
        return uri

    # Flat format: _meta["ui/resourceUri"]
    meta_dict = _to_dict(getattr(tool, "meta", None)) or {}
    flat_uri = meta_dict.get("ui/resourceUri", "")
    if isinstance(flat_uri, str) and flat_uri.startswith("ui://"):
        return flat_uri

    return None


def _tool_summary(tool) -> dict:
    """Compact listing entry: name, first description line, UI flag."""
    first_line = (tool.description or "").strip().split("\n", 1)[0].rstrip()
    if len(first_line) > 200:
        first_line = first_line[:200] + "..."
    return {
        "name": tool.name,
        "description": first_line,
        "has_ui": _extract_ui_resource_uri(tool) is not None,
    }


def _extract_tool_result_text(call_result) -> str:
    """Extract text content from an MCP call_tool result."""
    if not call_result or not getattr(call_result, "content", None):
        return ""
    parts = []
    for item in call_result.content:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _build_csp_meta_tag(csp: dict) -> str:
    """Build a <meta> CSP tag from a server-declared _meta.ui.csp object.

    Per the MCP Apps spec (SEP-1865), the csp object has:
      connectDomains   -> connect-src
      resourceDomains  -> script-src, style-src, img-src, font-src, media-src
      frameDomains     -> frame-src
      baseUriDomains   -> base-uri
    """
    if not csp:
        # Restrictive default per spec: block all outbound, allow inline scripts/styles
        return (
            '<meta http-equiv="Content-Security-Policy" content="'
            "default-src 'none'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "media-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'none'; "
            "frame-src 'none'; "
            "object-src 'none'; "
            "base-uri 'self'"
            '">\n'
        )

    resource_domains = " ".join(csp.get("resourceDomains") or [])
    connect_domains = " ".join(csp.get("connectDomains") or [])
    frame_domains = " ".join(csp.get("frameDomains") or [])
    base_uri_domains = " ".join(csp.get("baseUriDomains") or [])

    rd = f" {resource_domains}" if resource_domains else ""
    cd = f" {connect_domains}" if connect_domains else " 'none'"
    fd = f" {frame_domains}" if frame_domains else " 'none'"
    bd = f" {base_uri_domains}" if base_uri_domains else " 'self'"

    policy = (
        f"default-src 'none'; "
        f"script-src 'self' 'unsafe-inline'{rd}; "
        f"style-src 'self' 'unsafe-inline'{rd}; "
        f"img-src 'self' data:{rd}; "
        f"font-src 'self'{rd}; "
        f"media-src 'self' data:{rd}; "
        f"connect-src{cd}; "
        f"frame-src{fd}; "
        f"object-src 'none'; "
        f"base-uri{bd}"
    )
    return f'<meta http-equiv="Content-Security-Policy" content="{policy}">\n'


def _get_resource_ui_meta(resources_list, uri: str) -> dict:
    """Find a resource in the listing by URI and return its _meta.ui dict."""
    for res in resources_list:
        res_dict = _to_dict(res)
        res_uri = str(res_dict.get("uri", ""))
        if res_uri == uri:
            meta = _to_dict(res_dict.get("meta"))
            return meta.get("ui", {}) if isinstance(meta, dict) else {}
    return {}


async def _connect_mcp(url: str, headers: dict | None) -> tuple[AsyncExitStack, ClientSession]:
    """Open a streamable-HTTP MCP connection. Caller owns the returned stack."""
    stack = AsyncExitStack()
    try:
        transport = await stack.enter_async_context(
            streamablehttp_client(url, headers=headers)
        )
        read_stream, write_stream, _ = transport
        session = await stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        return stack, session
    except Exception:
        await stack.aclose()
        raise


# ---------------------------------------------------------------------------
# OAuth 2.1
# ---------------------------------------------------------------------------


class AuthorizationRequired(Exception):
    """No usable OAuth session for this user yet; they must sign in first."""

    def __init__(self, authorize_url: str):
        super().__init__(authorize_url)
        self.authorize_url = authorize_url


def _is_unauthorized(exc: Exception) -> bool:
    """Whether an MCP transport error was an HTTP 401."""
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code == 401:
        return True
    message = str(exc).lower()
    return "401" in message or "unauthorized" in message


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------


class Tools:
    """MCP App Bridge — extends your abilities with additional tools.

    Three tool-calling functions that work together:
      1. ``search_mcp_tools``: find tools by keyword and get their
         parameter schemas.
      2. ``list_mcp_tools``: browse all tools (paginated summaries).
      3. ``call_mcp_tool``: use one of those tools. Works exactly like
         any other tool call you make.

    Workflow: ``search_mcp_tools`` with a keyword (or ``list_mcp_tools``
    to browse), read the tool's parameters from the result, then
    ``call_mcp_tool`` with the tool name and arguments.

    NEVER say "I cannot execute/run/use this tool" — you CAN, by
    calling ``call_mcp_tool``. It is the same as any other tool call.
    If a user asks for something and you found a matching tool, your
    next step is ALWAYS ``call_mcp_tool``.
    """

    class Valves(BaseModel):
        mcp_server_url: str = Field(
            default="",
            description="Streamable-HTTP URL of the MCP server.",
        )
        auth_method: Literal["bearer", "oauth_2.1", "oauth_2.1_static"] = Field(
            default="bearer",
            description="How to authenticate: 'bearer' uses auth_token, 'oauth_2.1' signs each user in via dynamic client registration, 'oauth_2.1_static' uses the client id/secret below.",
        )
        auth_token: str = Field(
            default="",
            description="Bearer token for MCP server authentication (auth_method 'bearer'; leave empty for an unauthenticated server).",
        )
        oauth_server_url: str = Field(
            default="",
            description="OAuth authorization server URL. Leave empty to discover it from the MCP server (RFC 9728).",
        )
        oauth_scope: str = Field(
            default="",
            description="Space or comma separated OAuth scopes. Leave empty to use the scopes the server advertises.",
        )
        oauth_client_id: str = Field(
            default="",
            description="OAuth client id (auth_method 'oauth_2.1_static' only).",
        )
        oauth_client_secret: str = Field(
            default="",
            description="OAuth client secret (auth_method 'oauth_2.1_static' only).",
        )
        oauth_resource_parameter: Literal["auto", "include", "omit"] = Field(
            default="auto",
            description="Whether to send the RFC 8707 'resource' parameter. 'auto' sends it unless the scopes already carry a resource indicator.",
        )
        oauth_client_info: str = Field(
            default="",
            description="Managed automatically: encrypted OAuth client registration. Clear this to force re-registration.",
        )
        tool_blocklist: str = Field(
            default="",
            description="Comma-separated tool names to hide from the model and block from execution.",
        )

    def __init__(self):
        self.valves = self.Valves()

    # --- auth ---------------------------------------------------------------

    def _oauth_enabled(self) -> bool:
        return self.valves.auth_method in ("oauth_2.1", "oauth_2.1_static")

    def _oauth_client_key(self, tool_id: str) -> str:
        return f"{OAUTH_CLIENT_PREFIX}:{tool_id}"

    def _oauth_connection(self) -> dict:
        """Connection-shaped dict so Open WebUI's OAuth option helpers apply."""
        return {
            "url": self.valves.mcp_server_url,
            "type": "mcp",
            "auth_type": self.valves.auth_method,
            "info": {
                "oauth_scope": self.valves.oauth_scope,
                "oauth_resource_parameter": self.valves.oauth_resource_parameter,
            },
        }

    def _stored_client_info(self) -> dict | None:
        blob = (self.valves.oauth_client_info or "").strip()
        if not blob:
            return None

        from open_webui.utils.oauth import decrypt_data

        try:
            return decrypt_data(blob)
        except Exception as e:
            log.warning("Stored OAuth client info is unreadable, re-registering: %s", e)
            return None

    async def _persist_client_info(self, tool_id: str, blob: str) -> None:
        from open_webui.models.tools import Tools as ToolsTable

        valves = await ToolsTable.get_tool_valves_by_id(tool_id) or {}
        valves["oauth_client_info"] = blob
        await ToolsTable.update_tool_valves_by_id(tool_id, valves)
        self.valves.oauth_client_info = blob

    async def _register_oauth_client(self, request, tool_id: str) -> str:
        """Ensure an OAuth client for this tool exists in Open WebUI's manager.

        Registers once (dynamic client registration or static credentials) and
        keeps the result in this tool's valves, so a restart does not force the
        user through registration again.
        """
        from open_webui.utils.oauth import (
            OAuthClientInformationFull,
            apply_connection_oauth_options,
            encrypt_data,
            get_oauth_client_info_with_dynamic_client_registration,
            get_oauth_client_info_with_static_credentials,
        )

        manager = request.app.state.oauth_client_manager
        client_key = self._oauth_client_key(tool_id)
        if await manager.get_client(client_key) is not None:
            return client_key

        client_info = self._stored_client_info()
        if client_info is None:
            oauth_server_url = self.valves.oauth_server_url or self.valves.mcp_server_url
            oauth_scope = self.valves.oauth_scope or None

            if self.valves.auth_method == "oauth_2.1_static":
                if not (self.valves.oauth_client_id and self.valves.oauth_client_secret):
                    raise RuntimeError(
                        "auth_method 'oauth_2.1_static' needs oauth_client_id and oauth_client_secret."
                    )
                registration = await get_oauth_client_info_with_static_credentials(
                    request,
                    client_key,
                    oauth_server_url,
                    oauth_client_id=self.valves.oauth_client_id,
                    oauth_client_secret=self.valves.oauth_client_secret,
                    oauth_scope=oauth_scope,
                )
            else:
                registration = await get_oauth_client_info_with_dynamic_client_registration(
                    request,
                    client_key,
                    oauth_server_url,
                    oauth_scope=oauth_scope,
                )

            client_info = registration.model_dump(mode="json")
            await self._persist_client_info(tool_id, encrypt_data(client_info))

        if self.valves.auth_method == "oauth_2.1_static" and self.valves.oauth_client_id:
            client_info["client_id"] = self.valves.oauth_client_id
            client_info["client_secret"] = self.valves.oauth_client_secret or None

        client_info = apply_connection_oauth_options(self._oauth_connection(), client_info)
        manager.add_client(client_key, OAuthClientInformationFull(**client_info))
        return client_key

    async def _authorize_url(self, request, client_key: str) -> str:
        from open_webui.models.config import Config

        webui_url = await Config.get("webui.url")
        base_url = str(webui_url or request.base_url).rstrip("/")
        return f"{base_url}/oauth/clients/{client_key}/authorize"

    async def _build_headers(
        self,
        request=None,
        user: dict | None = None,
        tool_id: str | None = None,
        force_refresh: bool = False,
    ) -> dict | None:
        if not self._oauth_enabled():
            if not self.valves.auth_token:
                return None
            return {"Authorization": f"Bearer {self.valves.auth_token}"}

        user_id = (user or {}).get("id")
        if request is None or not user_id or not tool_id:
            raise RuntimeError(
                "OAuth 2.1 authentication requires this tool to run inside a user chat request."
            )

        client_key = await self._register_oauth_client(request, tool_id)
        token = await request.app.state.oauth_client_manager.get_oauth_token(
            user_id, client_key, force_refresh=force_refresh
        )
        if not token or not token.get("access_token"):
            raise AuthorizationRequired(await self._authorize_url(request, client_key))
        return {"Authorization": f"Bearer {token['access_token']}"}

    async def _run_with_session(self, operation, request, user, tool_id):
        """Run ``operation(session)`` against the MCP server, retrying once on 401."""
        last_error = None
        for attempt in (0, 1):
            headers = await self._build_headers(
                request=request, user=user, tool_id=tool_id, force_refresh=attempt == 1
            )
            retry_on_401 = attempt == 0 and self._oauth_enabled()

            try:
                stack, session = await _connect_mcp(self.valves.mcp_server_url, headers)
            except Exception as e:
                if retry_on_401 and _is_unauthorized(e):
                    last_error = e
                    continue
                raise

            try:
                return await operation(session)
            except Exception as e:
                if retry_on_401 and _is_unauthorized(e):
                    last_error = e
                    continue
                raise
            finally:
                await stack.aclose()

        raise last_error if last_error else RuntimeError("MCP request failed.")

    async def _authorization_message(self, error: AuthorizationRequired, event_emitter) -> str:
        if event_emitter:
            try:
                await event_emitter(
                    {
                        "type": "notification",
                        "data": {
                            "type": "info",
                            "content": "Sign in to the MCP server to continue.",
                        },
                    }
                )
            except Exception:
                pass
        return (
            "Authorization required: this user has not signed in to the MCP server yet. "
            "Show the user this sign-in link exactly as it is and ask them to open it, "
            "then run the same call again:\n"
            f"{error.authorize_url}"
        )

    def _blocked_tools(self) -> set[str]:
        names = (name.strip() for name in self.valves.tool_blocklist.split(","))
        return {name for name in names if name}

    async def _list_allowed_tools(self, session) -> list:
        result = await session.list_tools()
        blocked = self._blocked_tools()
        return [tool for tool in result.tools if tool.name not in blocked]

    async def list_mcp_tools(
        self,
        offset: int = 0,
        __request__=None,
        __user__=None,
        __id__=None,
        __event_emitter__=None,
    ) -> str:
        """
        Browse the extra tools available via ``call_mcp_tool``, as a
        paginated list of names and short descriptions. Parameter
        schemas are NOT included; before calling a tool, get its
        parameters via ``search_mcp_tools`` (searching its exact name
        works). If the result has ``next_offset``, more tools exist.

        :param offset: Pagination offset; pass the previous page's ``next_offset``.
        :return: JSON page of tool summaries.
        """
        page_offset = max(offset, 0)

        async def operation(session):
            tools = await self._list_allowed_tools(session)
            payload = {
                "total": len(tools),
                "offset": page_offset,
                "tools": [
                    _tool_summary(tool)
                    for tool in tools[page_offset : page_offset + LIST_PAGE_SIZE]
                ],
                "hint": "Call search_mcp_tools with a keyword or tool name to get a tool's parameters before calling it.",
            }
            if page_offset + LIST_PAGE_SIZE < len(tools):
                payload["next_offset"] = page_offset + LIST_PAGE_SIZE
            return json.dumps(payload, ensure_ascii=False)

        try:
            return await self._run_with_session(
                operation, __request__, __user__, __id__
            )
        except AuthorizationRequired as e:
            return await self._authorization_message(e, __event_emitter__)

    async def search_mcp_tools(
        self,
        query: str,
        __request__=None,
        __user__=None,
        __id__=None,
        __event_emitter__=None,
    ) -> str:
        """
        Find extra tools matching a keyword or name, returning their
        full parameter schemas. Use this before ``call_mcp_tool``:
        search, read the matching tool's parameters, then call it.

        :param query: Keyword(s) or a tool name to search for.
        :return: JSON list of matching tools with parameters.
        """
        async def operation(session):
            tools = await self._list_allowed_tools(session)
            normalized_query = query.lower().strip()
            terms = normalized_query.split()
            scored = []
            for tool in tools:
                name = tool.name.lower()
                description = (tool.description or "").lower()
                hits = sum(1 for term in terms if term in name or term in description)
                if not hits:
                    continue
                rank = (
                    name != normalized_query,
                    not any(term in name for term in terms),
                    -hits,
                )
                scored.append((rank, tool))
            scored.sort(key=lambda entry: entry[0])

            matches = [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "has_ui": _extract_ui_resource_uri(tool) is not None,
                    "parameters": tool.inputSchema,
                }
                for _, tool in scored[:SEARCH_RESULT_LIMIT]
            ]
            payload = {"matches": matches}
            if not scored:
                payload["note"] = (
                    "No matching tools. Use list_mcp_tools to browse what is available."
                )
            elif len(scored) > SEARCH_RESULT_LIMIT:
                payload["note"] = (
                    f"Showing top {SEARCH_RESULT_LIMIT} of {len(scored)} matches. "
                    "Refine the query or use list_mcp_tools to browse."
                )
            return json.dumps(payload, ensure_ascii=False)

        try:
            return await self._run_with_session(
                operation, __request__, __user__, __id__
            )
        except AuthorizationRequired as e:
            return await self._authorization_message(e, __event_emitter__)

    async def call_mcp_tool(
        self,
        tool_name: str,
        arguments: str = "{}",
        __request__=None,
        __user__=None,
        __id__=None,
        __event_emitter__=None,
    ) -> str | tuple:
        """
        Use a tool discovered via ``search_mcp_tools`` or
        ``list_mcp_tools``. This is a normal tool call — you provide the
        name and arguments, it returns a result (text or a visual
        display shown directly to the user). This works exactly like any
        other tool call you make.

        NEVER say "I cannot run/use/execute this tool". You CAN use it
        by calling this function. When you know the tool name, call this
        immediately.

        :param tool_name: Tool name from search_mcp_tools or list_mcp_tools output.
        :param arguments: JSON string of tool arguments (default "{}").
        :return: Tool result — text or visual embed shown to the user.
        """
        if tool_name in self._blocked_tools():
            return f'Tool "{tool_name}" is not available.'

        args = json.loads(arguments) if isinstance(arguments, str) else arguments

        async def operation(session):
            # --- Find the tool and check for UI resource ---
            tools_result = await session.list_tools()
            ui_resource_uri = None

            max_height = None
            for tool in tools_result.tools:
                if tool.name == tool_name:
                    ui_resource_uri = _extract_ui_resource_uri(tool)
                    ui_meta = _extract_ui_meta(tool)
                    max_height = ui_meta.get("maxHeight")
                    break

            # --- Call the tool ---
            call_result = await session.call_tool(tool_name, args)
            result_text = _extract_tool_result_text(call_result)

            # --- If no UI resource, return plain text ---
            if not ui_resource_uri:
                return result_text or "Tool executed (no output)."

            # --- Fetch resource listing for CSP/permissions metadata ---
            resources_result = await session.list_resources()
            resources_list = (
                resources_result.resources
                if resources_result and hasattr(resources_result, "resources")
                else []
            )
            ui_meta = _get_resource_ui_meta(resources_list, ui_resource_uri)
            csp_data = ui_meta.get("csp") if isinstance(ui_meta, dict) else None

            # --- Fetch the UI resource content ---
            resource_result = await session.read_resource(ui_resource_uri)
            html_content = ""
            if resource_result and getattr(resource_result, "contents", None):
                for item in resource_result.contents:
                    text = getattr(item, "text", None)
                    if text:
                        html_content = text
                        break

            if not html_content:
                return result_text or "Tool executed (UI resource was empty)."

            # --- Build injection: CSP + data + AppBridge shim + auto-height ---
            csp_tag = _build_csp_meta_tag(csp_data)

            # Globals for custom apps that read __MCP_TOOL_RESULT__ directly
            data_script = (
                "<script>\n"
                f"  window.__MCP_TOOL_RESULT__ = {json.dumps(result_text)};\n"
                f"  window.__MCP_TOOL_ARGS__   = {json.dumps(args, ensure_ascii=False)};\n"
                f"  window.__MCP_TOOL_NAME__   = {json.dumps(tool_name)};\n"
                "</script>\n"
            )

            # Spec-compliant AppBridge shim: dispatches ui/notifications/tool-result
            # as a synthetic MessageEvent so apps using the official AppBridge SDK
            # receive the tool result via the standard protocol.
            # Works without iframe same-origin — no parent access needed.
            appbridge_shim = (
                "<script>\n"
                "(function(){\n"
                f"  var _result = {json.dumps(result_text)};\n"
                "  var _notification = {\n"
                "    jsonrpc: '2.0',\n"
                "    method: 'ui/notifications/tool-result',\n"
                "    params: { content: [{ type: 'text', text: _result }] }\n"
                "  };\n"
                "  try {\n"
                "    var _parsed = JSON.parse(_result);\n"
                "    if (_parsed && typeof _parsed === 'object')\n"
                "      _notification.params.structuredContent = _parsed;\n"
                "  } catch(e) {}\n"
                "  function _dispatch() {\n"
                "    window.dispatchEvent(new MessageEvent('message', {\n"
                "      data: _notification,\n"
                "      origin: window.location.origin,\n"
                "      source: window.parent\n"
                "    }));\n"
                "  }\n"
                "  if (document.readyState === 'complete' || document.readyState === 'interactive')\n"
                "    setTimeout(_dispatch, 50);\n"
                "  else\n"
                "    window.addEventListener('DOMContentLoaded', function(){ setTimeout(_dispatch, 50); });\n"
                "})();\n"
                "</script>\n"
            )

            # Use maxHeight from tool metadata as a floor for apps that use
            # height:100% / flex layouts (their scrollHeight is tiny without it).
            max_h_js = f"var maxH={int(max_height)};" if max_height else "var maxH=0;"
            height_script = (
                "<script>\n"
                f"{max_h_js}\n"
                "function reportHeight(){\n"
                "  var h=document.documentElement.scrollHeight;\n"
                "  if(maxH && h<maxH) h=maxH;\n"
                "  window.parent.postMessage({type:'iframe:height',height:h},'*');\n"
                "}\n"
                "window.addEventListener('load',function(){reportHeight();setTimeout(reportHeight,200)});\n"
                "new MutationObserver(reportHeight).observe(document.body,{childList:true,subtree:true});\n"
                "window.addEventListener('resize',reportHeight);\n"
                "</script>\n"
            )

            # If maxHeight is declared, give the document a min-height so that
            # apps using height:100% / flex layouts expand properly.
            min_height_style = ""
            if max_height:
                min_height_style = (
                    f"<style>html,body{{min-height:{int(max_height)}px}}</style>\n"
                )

            injection = csp_tag + min_height_style + data_script + appbridge_shim + height_script

            if "<head>" in html_content:
                html_content = html_content.replace("<head>", "<head>\n" + injection, 1)
            elif "<html>" in html_content:
                html_content = html_content.replace(
                    "<html>", "<html>\n<head>" + injection + "</head>", 1
                )
            else:
                html_content = "<head>" + injection + "</head>\n" + html_content

            # --- Return as Rich UI embed with LLM context ---
            response = HTMLResponse(
                content=html_content,
                headers={"Content-Disposition": "inline"},
            )
            result_context = (
                f'MCP tool "{tool_name}" executed successfully and its UI is now '
                f"rendered and visible to the user. Briefly describe what the tool "
                f"did or what the user can see."
            )
            if result_text:
                result_context += (
                    f" The tool returned the following data:\n{result_text}"
                )
            return response, result_context

        try:
            return await self._run_with_session(
                operation, __request__, __user__, __id__
            )
        except AuthorizationRequired as e:
            return await self._authorization_message(e, __event_emitter__)
