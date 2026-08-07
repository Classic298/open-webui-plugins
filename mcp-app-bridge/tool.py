"""
title: MCP App Bridge
author: Classic298
author_url: https://github.com/Classic298
funding_url: https://github.com/Classic298
version: 0.6.0
description: Wraps MCP server tools and renders MCP App UI resources (ui://) as Rich UI embeds using Open WebUI's existing embed system. Context-efficient discovery: paginated summary listing plus keyword search, so full schemas are only loaded for the top matching tools. Spec-compliant: honors server-declared CSP, dispatches ui/notifications/tool-result for AppBridge SDK compatibility. No middleware changes needed.
"""

import json
from typing import Literal
from contextlib import AsyncExitStack

from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

LIST_PAGE_SIZE = 25
SEARCH_RESULT_LIMIT = 5


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
        auth_token: str = Field(
            default="",
            description="Bearer token for MCP server authentication (optional).",
        )
        tool_blocklist: str = Field(
            default="",
            description="Comma-separated tool names to hide from the model and block from execution.",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _build_headers(self) -> dict | None:
        if not self.valves.auth_token:
            return None
        return {"Authorization": f"Bearer {self.valves.auth_token}"}

    def _blocked_tools(self) -> set[str]:
        names = (name.strip() for name in self.valves.tool_blocklist.split(","))
        return {name for name in names if name}

    async def _list_allowed_tools(self, session) -> list:
        result = await session.list_tools()
        blocked = self._blocked_tools()
        return [tool for tool in result.tools if tool.name not in blocked]

    async def list_mcp_tools(self, offset: int = 0) -> str:
        """
        Browse the extra tools available via ``call_mcp_tool``, as a
        paginated list of names and short descriptions. Parameter
        schemas are NOT included; before calling a tool, get its
        parameters via ``search_mcp_tools`` (searching its exact name
        works). If the result has ``next_offset``, more tools exist.

        :param offset: Pagination offset; pass the previous page's ``next_offset``.
        :return: JSON page of tool summaries.
        """
        stack, session = await _connect_mcp(
            self.valves.mcp_server_url, self._build_headers()
        )
        try:
            tools = await self._list_allowed_tools(session)
            offset = max(offset, 0)
            payload = {
                "total": len(tools),
                "offset": offset,
                "tools": [
                    _tool_summary(tool)
                    for tool in tools[offset : offset + LIST_PAGE_SIZE]
                ],
                "hint": "Call search_mcp_tools with a keyword or tool name to get a tool's parameters before calling it.",
            }
            if offset + LIST_PAGE_SIZE < len(tools):
                payload["next_offset"] = offset + LIST_PAGE_SIZE
            return json.dumps(payload, ensure_ascii=False)
        finally:
            await stack.aclose()

    async def search_mcp_tools(self, query: str) -> str:
        """
        Find extra tools matching a keyword or name, returning their
        full parameter schemas. Use this before ``call_mcp_tool``:
        search, read the matching tool's parameters, then call it.

        :param query: Keyword(s) or a tool name to search for.
        :return: JSON list of matching tools with parameters.
        """
        stack, session = await _connect_mcp(
            self.valves.mcp_server_url, self._build_headers()
        )
        try:
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
        finally:
            await stack.aclose()

    async def call_mcp_tool(
        self,
        tool_name: str,
        arguments: str = "{}",
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

        stack, session = await _connect_mcp(
            self.valves.mcp_server_url, self._build_headers()
        )
        try:
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
        finally:
            await stack.aclose()
