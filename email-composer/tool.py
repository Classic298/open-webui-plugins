"""
title: Email Composer
author: Classic298
author_url: https://github.com/Classic298
funding_url: https://github.com/Classic298
version: 1.1.0
description: Renders composed emails as interactive Rich UI cards with rich text editing, markdown auto-conversion, To/CC/BCC chips, priority badges, copy, download .eml, mailto, autosave, and word count. Requires 'Allow Iframe Same-Origin Access' in Settings > Interface for autosave (all other features work without it). Note: mailto is plain text only and may truncate long emails; use Download .eml for formatted or long emails.
"""

import json
import uuid
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse


class Tools:
    class Valves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()
        self.citation = False

    async def compose_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        bcc: str = "",
        priority: str = "normal",
        __event_emitter__=None,
    ):
        """
        Composes and displays an email as an interactive card embedded in the chat.
        Use this tool whenever the user asks to write, draft, or compose an email.
        The card lets the user edit all fields with rich text formatting, copy the body, download as .eml, or open in their mail app.

        :param to: Recipient email address(es), separated by semicolons for multiple
        :param subject: Email subject line
        :param body: Plain text email body
        :param cc: CC recipient(s), separated by semicolons (optional)
        :param bcc: BCC recipient(s), separated by semicolons (optional)
        :param priority: Email priority: high, normal, or low (optional)
        :return: Confirmation that the interactive email card is displayed
        """
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": "Composing email...", "done": False}})

        storage_key = "email-composer-" + str(uuid.uuid4())
        # Escaped so "</script>" in the email text cannot end the inline script.
        args_json = json.dumps({
            "to": to,
            "subject": subject,
            "body": body,
            "cc": cc,
            "bcc": bcc,
            "priority": priority,
        }).replace("<", "\\u003c")
        inject = "var ARGS = " + args_json + ";\nvar STORAGE_KEY = " + json.dumps(storage_key) + ";"
        html = EMAIL_CARD_HTML.replace("/*__ARGS__*/", inject)

        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": "Email ready", "done": True}})
            # Deliver the card on the message-level "embeds" channel so it renders
            # inline under BOTH native (Open WebUI >= 0.10) and legacy tool calling.
            # Returning an HTMLResponse attaches the embed to the tool-call result
            # instead, which 0.10's native path does not paint inline, so the card
            # only showed up inside the collapsed tool-call details.
            await __event_emitter__({"type": "embeds", "data": {"embeds": [html]}})
            return (
                "The interactive email card is now displayed in the chat. "
                "Do not repeat the email body, subject or recipients in your reply. "
                "Reply with one short sentence confirming the draft is ready to review, "
                "edit and send from the card."
            )

        # No event emitter (older Open WebUI): fall back to the Rich UI return.
        return HTMLResponse(content=html, headers={"Content-Disposition": "inline"})


EMAIL_CARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {
  --bg: transparent;
  --card: #ffffff;
  --border: #e5e7eb;
  --border-light: #f0f0f0;
  --text: #111827;
  --text2: #6b7280;
  --text3: #9ca3af;
  --chip-bg: #f3f4f6;
  --chip-text: #374151;
  --chip-x: #9ca3af;
  --chip-x-hover: #ef4444;
  --hover: rgba(0,0,0,0.06);
  --accent1: #6366f1;
  --accent2: #8b5cf6;
  --accent3: #a78bfa;
  --badge-high-bg: #fef2f2;
  --badge-high-text: #dc2626;
  --badge-high-border: #fecaca;
  --badge-low-bg: #f9fafb;
  --badge-low-text: #9ca3af;
  --badge-low-border: #e5e7eb;
  --success: #22c55e;
  --toolbar-active: rgba(99,102,241,0.12);
}
@media(prefers-color-scheme:dark){
:root {
  --card: #1a1b26;
  --border: #2a2b3d;
  --border-light: #252636;
  --text: #e5e7eb;
  --text2: #9ca3af;
  --text3: #6b7280;
  --chip-bg: #2a2b3d;
  --chip-text: #d1d5db;
  --chip-x: #6b7280;
  --chip-x-hover: #f87171;
  --hover: rgba(255,255,255,0.08);
  --accent1: #818cf8;
  --accent2: #a78bfa;
  --accent3: #c4b5fd;
  --badge-high-bg: #2d1519;
  --badge-high-text: #f87171;
  --badge-high-border: #4c1d25;
  --badge-low-bg: #1f2028;
  --badge-low-text: #6b7280;
  --badge-low-border: #2a2b3d;
  --success: #4ade80;
  --toolbar-active: rgba(129,140,248,0.15);
}}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',sans-serif;color:var(--text);line-height:1.5;padding:2px}

.card{position:relative;background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--accent1),var(--accent2),var(--accent3));z-index:1}

.header{display:flex;align-items:center;justify-content:space-between;padding:10px 14px 8px;border-bottom:1px solid var(--border-light)}
.header-left{display:flex;align-items:center;gap:8px;min-width:0}
.header-left svg{flex-shrink:0;color:var(--text2);animation:iconPop .35s ease-out}
.header-title{font-weight:600;font-size:13px;color:var(--text2);white-space:nowrap}
.badge{font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px;white-space:nowrap}
.badge-high{background:var(--badge-high-bg);color:var(--badge-high-text);border:1px solid var(--badge-high-border)}
.badge-low{background:var(--badge-low-bg);color:var(--badge-low-text);border:1px solid var(--badge-low-border)}
.header-actions{display:flex;align-items:center;gap:2px;flex-shrink:0}

.btn{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border:none;background:none;color:var(--text2);border-radius:8px;cursor:pointer;transition:background .15s,color .15s;text-decoration:none}
.btn:hover{background:var(--hover);color:var(--text)}
.btn svg{width:16px;height:16px}
.btn-success svg{color:var(--success)}

.fields{padding:0 14px}
.field-row{display:flex;align-items:flex-start;gap:8px;padding:8px 0;font-size:13px}
.field-row+.field-row{border-top:1px solid var(--border-light)}
.field-label{font-weight:500;color:var(--text2);flex-shrink:0;padding-top:3px;user-select:none;min-width:48px}
.field-value{flex:1;min-width:0}

.chips{display:flex;flex-wrap:wrap;align-items:center;gap:4px;min-height:26px}
.chip{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:12px;font-size:12px;background:var(--chip-bg);color:var(--chip-text);animation:chipIn .15s ease-out;max-width:100%;overflow:hidden}
.chip span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chip-x{display:inline-flex;align-items:center;justify-content:center;background:none;border:none;cursor:pointer;color:var(--chip-x);padding:0;width:14px;height:14px;border-radius:50%;transition:color .15s,background .15s;flex-shrink:0}
.chip-x:hover{color:var(--chip-x-hover);background:rgba(239,68,68,.1)}
.chip-x svg{width:10px;height:10px}

.chip-input{flex:1;min-width:80px;border:none;outline:none;background:transparent;font-size:12px;color:var(--text);padding:2px 0;font-family:inherit}
.chip-input::placeholder{color:var(--text3)}

.cc-toggle{padding:4px 0 0 56px}
.cc-toggle button{font-size:12px;color:var(--text3);background:none;border:none;cursor:pointer;padding:2px 4px;border-radius:4px;transition:color .15s}
.cc-toggle button:hover{color:var(--text2)}

.subject-row{border-top:1px solid var(--border-light) !important}
.subject-input{flex:1;border:none;outline:none;background:transparent;font-size:13px;font-weight:600;color:var(--text);font-family:inherit;padding:2px 0}
.subject-input::placeholder{color:var(--text3);font-weight:400}

.toolbar{display:flex;align-items:center;gap:2px;padding:6px 14px;border-top:1px solid var(--border-light);flex-wrap:wrap}
.tbtn{display:inline-flex;align-items:center;justify-content:center;min-width:26px;height:24px;border:none;background:none;color:var(--text2);border-radius:5px;cursor:pointer;font-size:12px;font-family:inherit;padding:0 5px;transition:background .12s,color .12s;user-select:none}
.tbtn:hover{background:var(--hover);color:var(--text)}
.tbtn.active{background:var(--toolbar-active);color:var(--accent1)}
.tsep{width:1px;height:16px;background:var(--border-light);margin:0 3px}

.body-area{padding:10px 14px 4px}
.body-editable{min-height:60px;outline:none;font-size:13px;color:var(--text);font-family:inherit;line-height:1.6;white-space:pre-wrap;word-wrap:break-word}
.body-editable:empty::before{content:attr(data-placeholder);color:var(--text3);pointer-events:none;font-style:italic}
.body-editable h1{font-size:1.35em;font-weight:700;margin:0.4em 0 0.2em;line-height:1.3}
.body-editable h2{font-size:1.15em;font-weight:600;margin:0.3em 0 0.15em;line-height:1.3}
.body-editable h3{font-size:1.05em;font-weight:600;margin:0.25em 0 0.1em;line-height:1.3}
.body-editable ul,.body-editable ol{padding-left:1.4em;margin:0.3em 0}
.body-editable li{margin:0.1em 0}
.body-editable p{margin:0}
.body-editable code{background:var(--chip-bg);padding:1px 5px;border-radius:3px;font-size:0.9em;font-family:'SF Mono',Monaco,Consolas,monospace}
.body-editable a{color:var(--accent1);text-decoration:underline;text-underline-offset:2px}

.footer{display:flex;align-items:center;justify-content:space-between;padding:6px 14px 10px;font-size:11px;color:var(--text3)}
.footer-counts{display:flex;gap:12px}
.footer-hint{opacity:.7}

.save-indicator{font-size:11px;color:var(--text3);padding:0 6px;opacity:0;transition:opacity .3s}
.save-indicator.visible{opacity:1}

@keyframes iconPop{0%{transform:scale(0);opacity:0}60%{transform:scale(1.15)}100%{transform:scale(1);opacity:1}}
@keyframes chipIn{from{transform:scale(.85);opacity:0}to{transform:scale(1);opacity:1}}

.hidden{display:none !important}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <div class="header-left">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16"><path stroke-linecap="round" stroke-linejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75"/></svg>
      <span class="header-title">Email</span>
      <span class="badge hidden" id="priorityBadge"></span>
      <span class="save-indicator" id="saveIndicator"></span>
    </div>
    <div class="header-actions">
      <button class="btn" id="btnCopy" title="Copy body (rich text)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9.75a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184"/></svg></button>
      <button class="btn" id="btnDownload" title="Download .eml"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3"/></svg></button>
      <a class="btn" id="btnMailto" title="Open in mail app (plain text only — use Download .eml for formatting)" href="mailto:"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5"/></svg></a>
    </div>
  </div>

  <div class="fields">
    <div class="field-row" id="toRow">
      <span class="field-label">To:</span>
      <div class="field-value"><div class="chips" id="toChips"><input class="chip-input" id="toInput" placeholder="recipient@example.com"></div></div>
    </div>
    <div class="cc-toggle" id="ccToggle"><button id="btnCcBcc">Cc / Bcc</button></div>
    <div class="field-row hidden" id="ccRow">
      <span class="field-label">Cc:</span>
      <div class="field-value"><div class="chips" id="ccChips"><input class="chip-input" id="ccInput" placeholder="cc@example.com"></div></div>
    </div>
    <div class="field-row hidden" id="bccRow">
      <span class="field-label">Bcc:</span>
      <div class="field-value"><div class="chips" id="bccChips"><input class="chip-input" id="bccInput" placeholder="bcc@example.com"></div></div>
    </div>
    <div class="field-row subject-row">
      <span class="field-label">Subject:</span>
      <div class="field-value"><input class="subject-input" id="subjectInput" placeholder="Subject"></div>
    </div>
  </div>

  <div class="toolbar" id="toolbar">
    <button class="tbtn" data-cmd="bold" title="Bold (Ctrl+B)"><b>B</b></button>
    <button class="tbtn" data-cmd="italic" title="Italic (Ctrl+I)"><i>I</i></button>
    <button class="tbtn" data-cmd="underline" title="Underline (Ctrl+U)"><u>U</u></button>
    <button class="tbtn" data-cmd="strikeThrough" title="Strikethrough"><s>S</s></button>
    <div class="tsep"></div>
    <button class="tbtn" data-cmd="formatBlock" data-val="H1" title="Heading 1" style="font-weight:700">H1</button>
    <button class="tbtn" data-cmd="formatBlock" data-val="H2" title="Heading 2" style="font-weight:600">H2</button>
    <button class="tbtn" data-cmd="formatBlock" data-val="P" title="Normal text">¶</button>
    <div class="tsep"></div>
    <button class="tbtn" data-cmd="insertUnorderedList" title="Bullet list">•&thinsp;List</button>
    <button class="tbtn" data-cmd="insertOrderedList" title="Numbered list">1. List</button>
  </div>

  <div class="body-area">
    <div class="body-editable" id="bodyEditable" contenteditable="true" data-placeholder="Email body..."></div>
  </div>

  <div class="footer">
    <div class="footer-counts">
      <span id="wordCount">0 words</span>
      <span id="charCount">0 chars</span>
    </div>
    <span class="footer-hint" title="Ctrl+Enter to open in mail app">Ctrl+Enter to send</span>
  </div>
</div>

<script>
(function(){
  // Data injected directly by the Python tool
  /*__ARGS__*/

  var checkSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5"/></svg>';
  var clipSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9.75a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184"/></svg>';
  var xSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>';

  function reportHeight(){parent.postMessage({type:'iframe:height',height:document.documentElement.scrollHeight},'*')}
  window.addEventListener('load',reportHeight);
  new ResizeObserver(reportHeight).observe(document.body);

  function $(id){return document.getElementById(id)}
  var bodyEl=$('bodyEditable'), subjectIn=$('subjectInput'), copyBtn=$('btnCopy'),
      dlBtn=$('btnDownload'), mailtoA=$('btnMailto'), ccToggleBtn=$('btnCcBcc'),
      ccRow=$('ccRow'), bccRow=$('bccRow'), ccToggleWrap=$('ccToggle'), badge=$('priorityBadge'),
      saveIndicator=$('saveIndicator');

  // Autosave
  var saveTimer=null;
  function getState(){return{to:chips.to,cc:chips.cc,bcc:chips.bcc,subject:subjectIn.value,bodyHtml:bodyEl.innerHTML}}
  function persistState(){
    try{localStorage.setItem(STORAGE_KEY,JSON.stringify(getState()))}catch(e){}
    saveIndicator.textContent='Saved';saveIndicator.classList.add('visible');
    setTimeout(function(){saveIndicator.classList.remove('visible')},1500);
  }
  function scheduleSave(){if(saveTimer)clearTimeout(saveTimer);saveTimer=setTimeout(persistState,600)}
  function loadSaved(){try{var s=localStorage.getItem(STORAGE_KEY);return s?JSON.parse(s):null}catch(e){return null}}

  var chips={to:[],cc:[],bcc:[]};

  function parseAddrs(s){return s.split(/[;,]\s*/).map(function(x){return x.trim()}).filter(Boolean)}
  function escHtml(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML}

  function renderChips(field){
    var container=$(field+'Chips'), input=$(field+'Input');
    container.querySelectorAll('.chip').forEach(function(el){el.remove()});
    chips[field].forEach(function(addr,idx){
      var el=document.createElement('span');el.className='chip';
      el.innerHTML='<span>'+escHtml(addr)+'</span><button class="chip-x" data-field="'+field+'" data-idx="'+idx+'">'+xSvg+'</button>';
      container.insertBefore(el,input);
    });
    reportHeight();
  }

  function addChips(field,text){
    var addrs=text.split(/[;,\s]+/).map(function(s){return s.trim()}).filter(Boolean);
    if(addrs.length){chips[field]=chips[field].concat(addrs);renderChips(field);updateMailto();scheduleSave()}
  }
  function removeChip(field,idx){chips[field].splice(idx,1);renderChips(field);updateMailto();scheduleSave()}

  function setupChipInput(field){
    var input=$(field+'Input');
    input.addEventListener('keydown',function(e){
      if(e.key==='Enter'||e.key===','||e.key===';'||e.key==='Tab'){
        if(input.value.trim()){e.preventDefault();addChips(field,input.value);input.value=''}
      }else if(e.key==='Backspace'&&!input.value&&chips[field].length){removeChip(field,chips[field].length-1)}
    });
    input.addEventListener('blur',function(){if(input.value.trim()){addChips(field,input.value);input.value=''}});
    input.addEventListener('paste',function(e){e.preventDefault();addChips(field,(e.clipboardData||window.clipboardData).getData('text'))});
  }

  document.addEventListener('click',function(e){var b=e.target.closest('.chip-x');if(b)removeChip(b.dataset.field,parseInt(b.dataset.idx))});

  function getBodyText(){return bodyEl.innerText||bodyEl.textContent||''}

  // Reliable HTML-to-plain-text for mailto and copy (innerText can lose newlines in contenteditable)
  function getPlainText(){
    var h=bodyEl.innerHTML;
    h=h.replace(/<br\s*\/?>/gi,'\n');
    h=h.replace(/<\/(h[1-6]|p|div|li|blockquote)>/gi,'\n');
    h=h.replace(/<li[^>]*>/gi,'- ');
    h=h.replace(/<[^>]+>/g,'');
    h=h.replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&nbsp;/g,' ');
    h=h.replace(/\n{3,}/g,'\n\n');
    return h.trim();
  }

  function updateCounts(){
    var t=getBodyText(),w=t.trim()?t.trim().split(/\s+/).length:0;
    $('wordCount').textContent=w+(w===1?' word':' words');
    $('charCount').textContent=t.length+(t.length===1?' char':' chars');
  }

  function updateMailto(){
    var to=chips.to.join(','),cc=chips.cc.join(','),bcc=chips.bcc.join(','),sub=subjectIn.value,body=getPlainText(),p=[];
    if(sub)p.push('subject='+encodeURIComponent(sub));
    if(body)p.push('body='+encodeURIComponent(body));
    if(cc)p.push('cc='+encodeURIComponent(cc));
    if(bcc)p.push('bcc='+encodeURIComponent(bcc));
    mailtoA.href='mailto:'+to+(p.length?'?'+p.join('&'):'');
  }

  function showCcBcc(){ccRow.classList.remove('hidden');bccRow.classList.remove('hidden');ccToggleWrap.classList.add('hidden');reportHeight()}

  function setPriority(p){
    if(p==='high'){badge.textContent='High Priority';badge.className='badge badge-high'}
    else if(p==='low'){badge.textContent='Low Priority';badge.className='badge badge-low'}
    else{badge.classList.add('hidden')}
  }

  function fallbackCopy(t){var a=document.createElement('textarea');a.value=t;a.style.cssText='position:fixed;left:-9999px';document.body.appendChild(a);a.select();try{document.execCommand('copy')}catch(e){}a.remove()}

  function copyBody(){
    var html=bodyEl.innerHTML,t=getPlainText();
    if(navigator.clipboard&&navigator.clipboard.write){
      navigator.clipboard.write([new ClipboardItem({
        'text/html':new Blob([html],{type:'text/html'}),
        'text/plain':new Blob([t],{type:'text/plain'})
      })]).catch(function(){fallbackCopy(t)});
    }else{fallbackCopy(t)}
    copyBtn.innerHTML=checkSvg;copyBtn.classList.add('btn-success');
    setTimeout(function(){copyBtn.innerHTML=clipSvg;copyBtn.classList.remove('btn-success')},2000);
  }

  function downloadEml(){
    var to=chips.to.join(', '),cc=chips.cc.join(', '),bcc=chips.bcc.join(', ');
    var sub=subjectIn.value,htmlBody=bodyEl.innerHTML;
    var boundary='----=_Part_'+Date.now();
    var eml='MIME-Version: 1.0\r\nDate: '+new Date().toUTCString()+'\r\nTo: '+to+'\r\n';
    if(cc)eml+='Cc: '+cc+'\r\n';
    if(bcc)eml+='Bcc: '+bcc+'\r\n';
    eml+='Subject: '+sub+'\r\n';
    eml+='Content-Type: text/html; charset=utf-8\r\n\r\n';
    eml+='<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;font-size:14px;line-height:1.6;color:#222">'+htmlBody+'</body></html>';
    var blob=new Blob([eml],{type:'message/rfc822'}),url=URL.createObjectURL(blob);
    var a=document.createElement('a');a.href=url;a.download=(sub||'email').replace(/[^a-zA-Z0-9 _-]/g,'_')+'.eml';
    document.body.appendChild(a);a.click();URL.revokeObjectURL(url);a.remove();
  }

  // Toolbar: formatting commands
  document.querySelectorAll('.tbtn').forEach(function(btn){
    btn.addEventListener('mousedown',function(e){
      e.preventDefault(); // keep focus in contenteditable
      var cmd=btn.dataset.cmd,val=btn.dataset.val||null;
      if(cmd==='formatBlock'&&val) document.execCommand(cmd,false,'<'+val+'>');
      else document.execCommand(cmd,false,val);
      scheduleSave();updateCounts();reportHeight();
    });
  });

  // Track active formatting state for toolbar highlights
  bodyEl.addEventListener('keyup',updateToolbarState);
  bodyEl.addEventListener('mouseup',updateToolbarState);
  function updateToolbarState(){
    document.querySelectorAll('.tbtn[data-cmd]').forEach(function(btn){
      var cmd=btn.dataset.cmd;
      if(cmd==='formatBlock') return;
      try{btn.classList.toggle('active',document.queryCommandState(cmd))}catch(e){}
    });
  }

  copyBtn.addEventListener('click',copyBody);
  dlBtn.addEventListener('click',downloadEml);
  ccToggleBtn.addEventListener('click',showCcBcc);
  bodyEl.addEventListener('input',function(){updateCounts();updateMailto();scheduleSave();reportHeight()});
  subjectIn.addEventListener('input',function(){updateMailto();scheduleSave()});
  setupChipInput('to');setupChipInput('cc');setupChipInput('bcc');
  document.addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();mailtoA.click()}});

  // Lightweight markdown-to-HTML converter for AI body text
  function mdToHtml(md){
    var lines=md.split('\n'),out='',inUl=false,inOl=false;
    function cl(){if(inUl){out+='</ul>';inUl=false}if(inOl){out+='</ol>';inOl=false}}
    function il(t){
      t=escHtml(t);
      t=t.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
      t=t.replace(/\*(.+?)\*/g,'<em>$1</em>');
      t=t.replace(/~~(.+?)~~/g,'<del>$1</del>');
      t=t.replace(/`(.+?)`/g,'<code>$1</code>');
      t=t.replace(/\[([^\]]+)\]\(([^)]+)\)/g,function(match,text,url){
        if(!/^(https?|mailto):/i.test(url))return match;
        return '<a href="'+url.replace(/"/g,'&quot;')+'">'+text+'</a>';
      });
      return t;
    }
    for(var i=0;i<lines.length;i++){
      var L=lines[i],m;
      if((m=L.match(/^(#{1,3})\s+(.+)/))){cl();var n=m[1].length;out+='<h'+n+'>'+il(m[2])+'</h'+n+'>'}
      else if((m=L.match(/^[\-\*]\s+(.+)/))){if(!inUl){cl();out+='<ul>';inUl=true}out+='<li>'+il(m[1])+'</li>'}
      else if((m=L.match(/^\d+\.\s+(.+)/))){if(!inOl){cl();out+='<ol>';inOl=true}out+='<li>'+il(m[1])+'</li>'}
      else if(!L.trim()){cl();out+='<br>'}
      else{cl();out+=il(L)+'<br>'}
    }
    cl();
    return out.replace(/(<br>)+$/,'');
  }

  // Initialize: restore saved edits or use baked-in data
  var saved=loadSaved();
  if(saved){
    subjectIn.value=saved.subject||'';
    bodyEl.innerHTML=saved.bodyHtml||'';
    if(saved.to&&saved.to.length){chips.to=saved.to;renderChips('to')}
    else if(ARGS.to){chips.to=parseAddrs(ARGS.to);renderChips('to')}
    if(saved.cc&&saved.cc.length){chips.cc=saved.cc;renderChips('cc');showCcBcc()}
    else if(ARGS.cc){chips.cc=parseAddrs(ARGS.cc);renderChips('cc');showCcBcc()}
    if(saved.bcc&&saved.bcc.length){chips.bcc=saved.bcc;renderChips('bcc');showCcBcc()}
    else if(ARGS.bcc){chips.bcc=parseAddrs(ARGS.bcc);renderChips('bcc');showCcBcc()}
  }else{
    subjectIn.value=ARGS.subject||'';
    bodyEl.innerHTML=mdToHtml(ARGS.body||'');
    if(ARGS.to){chips.to=parseAddrs(ARGS.to);renderChips('to')}
    if(ARGS.cc){chips.cc=parseAddrs(ARGS.cc);renderChips('cc');showCcBcc()}
    if(ARGS.bcc){chips.bcc=parseAddrs(ARGS.bcc);renderChips('bcc');showCcBcc()}
  }
  setPriority(ARGS.priority||'normal');
  updateCounts();updateMailto();reportHeight();
})();
</script>
</body>
</html>"""

