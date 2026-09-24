"""
title: MCP App Bridge
author: Classic298
author_url: https://github.com/Classic298
funding_url: https://github.com/Classic298
version: 1.0.0
required_open_webui_version: 0.11.4
description: Wraps MCP server tools and renders MCP App UI resources (ui://) as Rich UI embeds using Open WebUI's existing embed system. Context-efficient discovery: paginated summary listing plus keyword search, so full schemas are only loaded for the top matching tools. Acts as an MCP Apps (2026-01-26) host: each app runs isolated in a nested sandbox with its server-declared CSP, gets the ui/initialize handshake, tool input and tool result, and can call its server's tools, read its resources, open links and send chat messages. Authenticates with a static bearer token or with per-user OAuth 2.1 (dynamic client registration or static credentials), reusing Open WebUI's own MCP OAuth machinery. No middleware changes needed.
"""

import base64
import hashlib
import json
import logging
import secrets
import time
from typing import Literal
from contextlib import AsyncExitStack

import jwt
from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.exceptions import McpError

LIST_PAGE_SIZE = 25
SEARCH_RESULT_LIMIT = 5

MCP_APPS_EXTENSION = "io.modelcontextprotocol/ui"
MCP_APPS_MIME_TYPE = "text/html;profile=mcp-app"
MCP_APPS_PROTOCOL_VERSION = "2026-01-26"

APP_RPC_PATH = "/api/v1/mcp-app-bridge/rpc"
RPC_TOKEN_TTL_SECONDS = 900

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


def _tool_visibility(tool: types.Tool) -> list:
    """Who may call the tool, per _meta.ui.visibility (default: model and app)."""
    visibility = _extract_ui_meta(tool).get("visibility")
    if visibility is None:
        return ["model", "app"]
    return visibility if isinstance(visibility, list) else []


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


def _js_json(value: object) -> str:
    """JSON for embedding in an inline <script>: no text can close the tag."""
    return json.dumps(value).replace("<", "\\u003c")


def _build_tool_result_params(call_result) -> dict:
    """Build tool-result notification params; fill structuredContent if absent."""
    params = call_result.model_dump(mode="json", by_alias=True, exclude_none=True)
    if "structuredContent" not in params:
        json_objects = []
        for block in params["content"]:
            try:
                parsed = json.loads(block.get("text", ""))
            except (ValueError, RecursionError):
                continue
            if isinstance(parsed, dict):
                json_objects.append(parsed)
        if len(json_objects) == 1:
            params["structuredContent"] = json_objects[0]
    return params


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


def _extract_ui_html(resource_result: types.ReadResourceResult) -> tuple[str, dict]:
    """HTML of a resources/read result (text or base64 blob) and its item's _meta.ui."""
    for item in resource_result.contents:
        html = getattr(item, "text", None)
        if html is None and getattr(item, "blob", None):
            html = base64.b64decode(item.blob).decode("utf-8")
        if html:
            return html, _extract_ui_meta(item)
    return "", {}


async def _list_all_tools(session: ClientSession) -> list:
    """Every tool on the server, following nextCursor across pages."""
    tools, cursor = [], None
    while True:
        result = await session.list_tools(
            params=types.PaginatedRequestParams(cursor=cursor)
        )
        tools.extend(result.tools)
        cursor = result.nextCursor
        if not cursor:
            return tools


class _AppsClientSession(ClientSession):
    """ClientSession that advertises MCP Apps support when it initializes."""

    async def send_request(self, request, *args, **kwargs):
        if isinstance(request.root, types.InitializeRequest):
            request.root.params.capabilities.extensions = {
                MCP_APPS_EXTENSION: {"mimeTypes": [MCP_APPS_MIME_TYPE]}
            }
        return await super().send_request(request, *args, **kwargs)


async def _connect_mcp(url: str, headers: dict | None) -> tuple[AsyncExitStack, ClientSession]:
    """Open a streamable-HTTP MCP connection. Caller owns the returned stack."""
    stack = AsyncExitStack()
    try:
        transport = await stack.enter_async_context(
            streamablehttp_client(url, headers=headers)
        )
        read_stream, write_stream, _ = transport
        session = await stack.enter_async_context(
            _AppsClientSession(read_stream, write_stream)
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
# MCP App host
# ---------------------------------------------------------------------------


APP_HOST_HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
html,body{margin:0;padding:0;background:transparent}
iframe{display:block;width:100%;height:150px;border:0}
iframe.bordered{width:calc(100% - 2px);border:1px solid rgba(128,128,128,.35);border-radius:12px}
</style>
</head>
<body>
<script>
(function () {
  var config = __CONFIG__;
  var openWebui = window.parent;
  var frame = document.createElement('iframe');
  frame.setAttribute('sandbox', 'allow-scripts allow-forms allow-popups allow-downloads');
  if (config.prefersBorder) frame.className = 'bordered';
  frame.srcdoc = config.appHtml;
  document.body.appendChild(frame);

  var darkScheme = window.matchMedia('(prefers-color-scheme: dark)');
  var handshakeStarted = false;
  var initialized = false;
  var appReportsSize = false;
  var appGone = false;
  var lastWidth = frame.clientWidth;

  function send(message) {
    if (appGone) return;
    message.jsonrpc = '2.0';
    frame.contentWindow.postMessage(message, '*');
  }
  function respond(id, result) { send({id: id, result: result}); }
  function fail(id, code, errorMessage) { send({id: id, error: {code: code, message: errorMessage}}); }
  function notify(method, params) { send({method: method, params: params}); }

  function hostContext() {
    return Object.assign({}, config.hostContext, {
      theme: darkScheme.matches ? 'dark' : 'light',
      containerDimensions: {width: frame.clientWidth},
      locale: navigator.language,
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      deviceCapabilities: {
        touch: window.matchMedia('(pointer: coarse)').matches,
        hover: window.matchMedia('(hover: hover)').matches
      }
    });
  }

  function sendToolData() {
    notify('ui/notifications/tool-input', config.toolInput);
    notify('ui/notifications/tool-result', config.toolResult);
  }

  function resize(height) {
    frame.style.height = Math.ceil(height) + 'px';
    openWebui.postMessage({type: 'iframe:height', height: frame.offsetHeight}, '*');
  }
  resize(frame.clientHeight);

  function viewerToken() {
    try { return localStorage.getItem('token'); } catch (error) { return null; }
  }

  function forwardToServer(message) {
    var token = viewerToken();
    fetch(config.rpc.url, {
      method: 'POST',
      headers: token ? {Authorization: 'Bearer ' + token} : {},
      body: JSON.stringify({
        token: config.rpc.token,
        tool_id: config.rpc.toolId,
        method: message.method,
        params: message.params || {}
      })
    })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (reply) {
        if (reply.error) fail(message.id, reply.error.code, reply.error.message);
        else respond(message.id, reply.result);
      })
      .catch(function (error) { fail(message.id, -32603, String(error)); });
  }

  function sameOrigin() {
    try { return !!openWebui.document; } catch (error) { return false; }
  }

  function messageText(content) {
    return [].concat(content || [])
      .filter(function (block) { return block && block.type === 'text'; })
      .map(function (block) { return block.text; })
      .join('\n');
  }

  var requestHandlers = {
    'ui/initialize': function (message) {
      handshakeStarted = true;
      respond(message.id, {
        protocolVersion: config.protocolVersion,
        hostInfo: config.hostInfo,
        hostCapabilities: config.hostCapabilities,
        hostContext: hostContext()
      });
    },
    'ping': function (message) { respond(message.id, {}); },
    'ui/open-link': function (message) {
      var url = String((message.params || {}).url || '');
      if (!/^https?:/i.test(url)) return fail(message.id, -32000, 'Invalid URL');
      window.open(url, '_blank', 'noopener,noreferrer');
      respond(message.id, {});
    },
    'ui/message': function (message) {
      var text = messageText((message.params || {}).content);
      if (!text) return fail(message.id, -32000, 'Invalid message format');
      // Same-origin prompts skip Open WebUI's confirm dialog, so only fill the input then.
      openWebui.postMessage({type: sameOrigin() ? 'input:prompt' : 'input:prompt:submit', text: text}, '*');
      respond(message.id, {});
    },
    'ui/request-display-mode': function (message) { respond(message.id, {mode: 'inline'}); },
    'tools/call': forwardToServer,
    'resources/read': forwardToServer,
    'resources/list': forwardToServer
  };

  var notificationHandlers = {
    'ui/notifications/initialized': function () {
      initialized = true;
      sendToolData();
    },
    'ui/notifications/size-changed': function (message) {
      var height = (message.params || {}).height;
      if (typeof height !== 'number') return;
      appReportsSize = true;
      resize(height);
    },
    'notifications/message': function (message) {
      console.log('[MCP App]', message.params);
    }
  };

  window.addEventListener('message', function (event) {
    var message = event.data || {};
    // Later pages in the frame are not the app; Chromium sends this from a detached source.
    if (message.type === 'mcp-app:unload' && message.key === config.unloadKey) {
      appGone = true;
      return;
    }
    if (event.source !== frame.contentWindow || appGone) return;
    if (message.type === 'iframe:height') {
      if (!appReportsSize && typeof message.height === 'number') resize(message.height);
      return;
    }
    if (message.jsonrpc !== '2.0' || typeof message.method !== 'string') return;
    var isRequest = message.id !== undefined && message.id !== null;
    var handlers = isRequest ? requestHandlers : notificationHandlers;
    if (Object.prototype.hasOwnProperty.call(handlers, message.method)) handlers[message.method](message);
    else if (isRequest) fail(message.id, -32601, 'Method not found');
  });

  frame.addEventListener('load', function () {
    setTimeout(function () { if (!handshakeStarted) sendToolData(); }, 1000);
  });

  darkScheme.addEventListener('change', function () {
    if (initialized) notify('ui/notifications/host-context-changed', {theme: darkScheme.matches ? 'dark' : 'light'});
  });
  window.addEventListener('resize', function () {
    if (window.innerHeight !== frame.offsetHeight) resize(frame.clientHeight);
    if (!initialized || frame.clientWidth === lastWidth) return;
    lastWidth = frame.clientWidth;
    notify('ui/notifications/host-context-changed', {containerDimensions: {width: lastWidth}});
  });
})();
</script>
</body>
</html>
"""


def _rpc_error(code: int, message: str) -> dict:
    """JSON-RPC error body for a rendered app."""
    return {"error": {"code": code, "message": message}}


def _rpc_response(reply: dict) -> JSONResponse:
    # The sandboxed host frame fetches with Origin: null, which CORS may not allow.
    return JSONResponse(reply, headers={"Access-Control-Allow-Origin": "*"})


def _rpc_token_key() -> bytes:
    """Signing key for app tokens, kept apart from Open WebUI's own."""
    from open_webui.env import WEBUI_SECRET_KEY

    return hashlib.sha256(f"mcp-app-bridge:{WEBUI_SECRET_KEY}".encode()).digest()


def _mint_rpc_token(user_id: str, tool_id: str, chat_id: str | None) -> str:
    """Token an app's host frame sends when it cannot send the viewer's login."""
    claims = {
        "sub": user_id,
        "tool_id": tool_id,
        "chat_id": chat_id,
        "exp": int(time.time()) + RPC_TOKEN_TTL_SECONDS,
    }
    return jwt.encode(claims, _rpc_token_key(), algorithm="HS256")


async def _can_use_tool(user, tool_id: str) -> bool:
    """The access check Open WebUI applies before it runs a tool for a user."""
    from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL
    from open_webui.models.access_grants import AccessGrants
    from open_webui.models.tools import Tools as ToolsTable

    tool = await ToolsTable.get_tool_by_id(tool_id)
    if tool is None:
        return False
    return (
        (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
        or tool.user_id == user.id
        or await AccessGrants.has_access(
            user_id=user.id, resource_type="tool", resource_id=tool_id
        )
    )


async def _is_private_chat(chat_id: str, user_id: str) -> bool:
    """Whether only this user (and admins) can open the chat."""
    from open_webui.models.access_grants import AccessGrants
    from open_webui.models.chats import Chats
    from open_webui.models.folders import Folders
    from open_webui.utils.chat_id import is_temporary_chat_id

    if not chat_id or is_temporary_chat_id(chat_id):
        return True
    chat = await Chats.get_chat_by_id(chat_id)
    if chat is None or chat.user_id != user_id or chat.share_id:
        return False
    if await AccessGrants.get_grants_by_resource("shared_chat", chat_id):
        return False
    folder_id, seen_ids = chat.folder_id, set()
    while folder_id and folder_id not in seen_ids:
        seen_ids.add(folder_id)
        folder = await Folders.get_folder_by_id(folder_id)
        if folder is None or folder.user_id != user_id:
            return False
        if await AccessGrants.get_grants_by_resource("folder", folder_id):
            return False
        folder_id = folder.parent_id
    return True


async def _app_rpc_endpoint(request) -> JSONResponse:
    """Run a rendered app's server request as the viewer or the tool's user."""
    from open_webui.models.tools import Tools as ToolsTable
    from open_webui.utils.auth import (
        get_http_authorization_cred,
        get_verified_user_by_id,
        get_verified_user_by_token,
    )
    from open_webui.utils.plugin import get_tool_module_from_cache

    body = await request.json()
    # Only the explicit header: the login cookie would let other sites trigger calls.
    if request.headers.get("Authorization"):
        credentials = get_http_authorization_cred(request.headers["Authorization"])
        redis = getattr(request.app.state, "redis", None)
        user = credentials and await get_verified_user_by_token(
            credentials.credentials, redis
        )
        tool_id = body.get("tool_id", "")
    else:
        try:
            claims = jwt.decode(
                body.get("token", ""), _rpc_token_key(), algorithms=["HS256"]
            )
        except jwt.InvalidTokenError:
            return _rpc_response(_rpc_error(-32000, "App expired. Run the tool again."))

        # Anyone who can open the chat can read the embed's token.
        private = await _is_private_chat(claims["chat_id"] or "", claims["sub"])
        user = await get_verified_user_by_id(claims["sub"]) if private else None
        tool_id = claims["tool_id"]
    if not user or not await _can_use_tool(user, tool_id):
        return _rpc_response(
            _rpc_error(-32000, "This app cannot reach its server here.")
        )

    tool_module, _ = await get_tool_module_from_cache(request, tool_id)
    tool_module.valves = tool_module.Valves(
        **(await ToolsTable.get_tool_valves_by_id(tool_id) or {})
    )
    reply = await tool_module._handle_app_request(
        body.get("method"),
        body.get("params") or {},
        request,
        user.model_dump(),
        tool_id,
    )
    return _rpc_response(reply)


def _mount_app_rpc_route(app) -> None:
    """(Re)register the app RPC route ahead of the SPA catch-all mounted at "/"."""
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) != APP_RPC_PATH
    ]
    app.router.routes.insert(
        0, Route(APP_RPC_PATH, _app_rpc_endpoint, methods=["POST"])
    )


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

    async def _list_allowed_tools(self, session, caller: str = "model") -> list:
        tools = await _list_all_tools(session)
        blocked = self._blocked_tools()
        return [
            tool
            for tool in tools
            if tool.name not in blocked and caller in _tool_visibility(tool)
        ]

    async def _handle_app_request(
        self, method: str, params: dict, request, user: dict, tool_id: str
    ) -> dict:
        """Proxy a rendered app's request to its MCP server as a JSON-RPC reply."""
        target = params.get("name") or params.get("uri") or "-"
        log.info("MCP App request %s %s from user %s", method, target, user.get("id"))

        async def operation(session):
            if method == "tools/call":
                name = params.get("name")
                tools = await self._list_allowed_tools(session, caller="app")
                if not any(tool.name == name for tool in tools):
                    return _rpc_error(-32602, f'Tool "{name}" is not available.')
                result = await session.call_tool(name, params.get("arguments") or {})
            elif method == "resources/read":
                result = await session.read_resource(params.get("uri"))
            elif method == "resources/list":
                result = await session.list_resources(
                    params=types.PaginatedRequestParams(cursor=params.get("cursor"))
                )
            else:
                return _rpc_error(-32601, "Method not found")
            payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
            return {"result": payload}

        try:
            return await self._run_with_session(operation, request, user, tool_id)
        except AuthorizationRequired:
            return _rpc_error(-32000, "Sign in to the MCP server to continue.")
        except McpError as e:
            return _rpc_error(e.error.code, e.error.message)

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
        __chat_id__=None,
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
            ui_resource_uri = None
            called_tool = None

            max_height = None
            for tool in await _list_all_tools(session):
                if tool.name == tool_name:
                    if "model" not in _tool_visibility(tool):
                        return f'Tool "{tool_name}" is not available.'
                    ui_resource_uri = _extract_ui_resource_uri(tool)
                    ui_meta = _extract_ui_meta(tool)
                    max_height = ui_meta.get("maxHeight")
                    called_tool = tool
                    break

            # --- Call the tool ---
            call_result = await session.call_tool(tool_name, args)
            result_text = _extract_tool_result_text(call_result)

            # --- If no UI resource, return plain text ---
            if not ui_resource_uri:
                return result_text or "Tool executed (no output)."

            # --- Fetch the UI resource content ---
            html_content, ui_meta = _extract_ui_html(
                await session.read_resource(ui_resource_uri)
            )
            if not html_content:
                return result_text or "Tool executed (UI resource was empty)."

            if not ui_meta:
                resources_result = await session.list_resources()
                ui_meta = _get_resource_ui_meta(
                    resources_result.resources, ui_resource_uri
                )
            if not isinstance(ui_meta, dict):
                ui_meta = {}
            csp_data = ui_meta.get("csp")

            # --- Build injection: CSP + data + auto-height ---
            # Globals for custom apps that read __MCP_TOOL_RESULT__ directly
            data_script = (
                "<script>\n"
                f"  window.__MCP_TOOL_RESULT__ = {_js_json(result_text)};\n"
                f"  window.__MCP_TOOL_ARGS__   = {_js_json(args)};\n"
                f"  window.__MCP_TOOL_NAME__   = {_js_json(tool_name)};\n"
                "</script>\n"
            )

            # Use maxHeight from tool metadata as a floor for apps that use
            # height:100% / flex layouts (their scrollHeight is tiny without it).
            max_h_js = f"var maxH={int(max_height)};" if max_height else "var maxH=0;"
            # Overflow that survives two of our resizes is vh-sized; stop chasing it.
            height_script = (
                "<script>\n"
                "(function(){\n"
                f"{max_h_js}\n"
                "function measureHeight(){\n"
                "  var h=document.documentElement.scrollHeight;\n"
                "  if(maxH && h<maxH) h=maxH;\n"
                "  return h;\n"
                "}\n"
                "var settledOverflow=0,overflowedAfterResize=false,postedHeight=0;\n"
                "var lastWidth=window.innerWidth;\n"
                "function reportHeight(){\n"
                "  var h=measureHeight();\n"
                "  if(h-window.innerHeight===settledOverflow) return;\n"
                "  postedHeight=h;\n"
                "  window.parent.postMessage({type:'iframe:height',height:h},'*');\n"
                "}\n"
                "window.addEventListener('load',function(){reportHeight();setTimeout(reportHeight,200)});\n"
                "window.addEventListener('DOMContentLoaded',function(){\n"
                "new MutationObserver(reportHeight).observe(document.body,{childList:true,subtree:true});\n"
                "});\n"
                "window.addEventListener('resize',function(){\n"
                "  if(window.innerWidth!==lastWidth){\n"
                "    lastWidth=window.innerWidth;\n"
                "    reportHeight();\n"
                "    return;\n"
                "  }\n"
                "  var h=measureHeight(),overflow=h-window.innerHeight;\n"
                "  if(!overflow){\n"
                "    settledOverflow=0;\n"
                "    overflowedAfterResize=false;\n"
                "    return;\n"
                "  }\n"
                "  if(h===postedHeight) return;\n"
                "  if(overflowedAfterResize){\n"
                "    settledOverflow=overflow;\n"
                "    return;\n"
                "  }\n"
                "  overflowedAfterResize=true;\n"
                "  reportHeight();\n"
                "});\n"
                "})();\n"
                "</script>\n"
            )

            # If maxHeight is declared, give the document a min-height so that
            # apps using height:100% / flex layouts expand properly.
            min_height_style = ""
            if max_height:
                min_height_style = (
                    f"<style>html,body{{min-height:{int(max_height)}px}}</style>\n"
                )

            unload_key = secrets.token_urlsafe(16)
            unload_message = _js_json({"type": "mcp-app:unload", "key": unload_key})
            unload_script = (
                "<script>addEventListener('pagehide',function(){"
                f"parent.postMessage({unload_message},'*')"
                "})</script>\n"
            )
            # Prepended, so the CSP applies before any of the server's markup parses.
            app_html = (
                "<!DOCTYPE html>\n"
                + _build_csp_meta_tag(csp_data)
                + min_height_style
                + data_script
                + height_script
                + unload_script
                + html_content
            )

            from open_webui.env import VERSION

            _mount_app_rpc_route(__request__.app)
            rpc_token = _mint_rpc_token(__user__["id"], __id__, __chat_id__)
            host_config = {
                "appHtml": app_html,
                "toolInput": {"arguments": args},
                "toolResult": _build_tool_result_params(call_result),
                "protocolVersion": MCP_APPS_PROTOCOL_VERSION,
                "hostInfo": {"name": "Open WebUI", "version": VERSION},
                "hostCapabilities": {
                    "openLinks": {},
                    "message": {"text": {}},
                    "logging": {},
                    "serverTools": {},
                    "serverResources": {},
                    "sandbox": {"permissions": {}, "csp": csp_data or {}},
                },
                "hostContext": {
                    "toolInfo": {
                        "tool": called_tool.model_dump(
                            mode="json", by_alias=True, exclude_none=True
                        )
                    },
                    "displayMode": "inline",
                    "availableDisplayModes": ["inline"],
                    "platform": "web",
                    "userAgent": "Open WebUI MCP App Bridge",
                },
                "rpc": {"url": APP_RPC_PATH, "token": rpc_token, "toolId": __id__},
                "unloadKey": unload_key,
                "prefersBorder": ui_meta.get("prefersBorder") is True,
            }

            # --- Return as Rich UI embed with LLM context ---
            response = HTMLResponse(
                content=APP_HOST_HTML.replace("__CONFIG__", _js_json(host_config)),
                headers={"Content-Disposition": "inline"},
            )
            result_context = (
                f'MCP tool "{tool_name}" ran and its UI is already rendered and '
                f"visible to the user. Do NOT repeat, reformat, summarize or list "
                f"the returned data - the user is already looking at it. Reply with "
                f"at most one short sentence, or say nothing if nothing needs saying."
            )
            if result_text:
                result_context += (
                    f"\n\nReference data (for answering follow-up questions only, "
                    f"never to restate):\n{result_text}"
                )
            return response, result_context

        try:
            return await self._run_with_session(
                operation, __request__, __user__, __id__
            )
        except AuthorizationRequired as e:
            return await self._authorization_message(e, __event_emitter__)
