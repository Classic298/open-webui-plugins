# Generates one self-contained banner HTML per plugin. Rendered to PNG by renderall.mjs.
import html
import math

W, H = 1600, 400

def page(cfg):
    a1, a2 = cfg["a1"], cfg["a2"]
    ts = cfg.get("title_size", 76)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html,body {{ width:{W}px; height:{H}px; }}
body {{
  font-family:-apple-system,"Segoe UI",system-ui,sans-serif; color:#ececf3; overflow:hidden; position:relative;
  background:
    radial-gradient(760px 620px at 4% -20%, {a1}44, transparent 60%),
    radial-gradient(760px 620px at 104% 130%, {a2}33, transparent 58%),
    linear-gradient(120deg,#08090d 0%, #0c0d14 55%, #090a10 100%);
}}
body::before {{ content:""; position:absolute; inset:0;
  background-image:radial-gradient(rgba(255,255,255,.05) 1px, transparent 1px); background-size:24px 24px;
  mask-image:radial-gradient(1300px 760px at 45% 42%, #000 42%, transparent 88%); }}
body::after {{ content:""; position:absolute; left:0; top:0; bottom:0; width:6px;
  background:linear-gradient(180deg,{a1},{a2}); }}
.inner {{ position:relative; z-index:2; display:flex; align-items:center; height:100%; padding:0 70px 0 92px; gap:30px; }}
.left {{ flex:1; min-width:0; }}
.badges {{ display:flex; flex-wrap:wrap; gap:9px; margin-bottom:22px; max-width:900px; }}
.pill {{ font-size:15.5px; font-weight:600; letter-spacing:.2px; padding:7px 15px; border-radius:999px;
  border:1px solid rgba(255,255,255,.14); background:rgba(255,255,255,.045); color:#c7c7d6; white-space:nowrap; }}
.pill.a {{ border-color:{a1}88; background:{a1}26; color:#fff; }}
.pill.dot::before {{ content:""; display:inline-block; width:7px; height:7px; border-radius:50%;
  background:{a2}; margin-right:8px; vertical-align:middle; }}
.titlerow {{ display:flex; align-items:center; gap:22px; }}
.glyph {{ font-size:{ts-10}px; line-height:1; filter:drop-shadow(0 6px 20px {a1}66); }}
h1 {{ font-size:{ts}px; line-height:1.0; font-weight:800; letter-spacing:-1.6px;
  padding:8px 10px 22px 0; margin-bottom:-22px;
  background:linear-gradient(180deg,#fff,{a2}); -webkit-background-clip:text; background-clip:text; color:transparent; }}
.tag {{ margin-top:18px; font-size:25px; line-height:1.4; color:#a6a6bd; max-width:840px; font-weight:400; }}
.tag b {{ color:#e7e5ff; font-weight:600; }}

/* right stage */
.right {{ width:470px; height:100%; position:relative; display:flex; align-items:center; justify-content:center; flex:none; }}
.deco {{ position:absolute; width:560px; height:560px; border-radius:50%;
  background:repeating-radial-gradient(circle at 50% 50%, {a1}22 0 1.5px, transparent 1.5px 44px);
  -webkit-mask-image:radial-gradient(circle at 50% 50%, #000 34%, transparent 70%);
  mask-image:radial-gradient(circle at 50% 50%, #000 34%, transparent 70%); opacity:.55; }}
.stage {{ position:relative; z-index:2; padding:22px 30px; border-radius:22px;
  background:linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.015));
  border:1px solid rgba(255,255,255,.09);
  box-shadow:0 34px 74px -30px rgba(0,0,0,.75), inset 0 1px 0 rgba(255,255,255,.06); }}
.fdot {{ position:absolute; border-radius:50%; z-index:3; }}
.d1 {{ width:15px; height:15px; background:{a1}; top:-7px; left:26px; box-shadow:0 0 18px {a1}; }}
.d2 {{ width:11px; height:11px; background:{a2}; bottom:14px; right:-7px; box-shadow:0 0 15px {a2}; }}
.d3 {{ width:8px; height:8px; background:#fff; top:26%; right:2px; opacity:.55; }}
.ring {{ position:absolute; width:30px; height:30px; border:2px solid {a2}; border-radius:50%; opacity:.5;
  bottom:-10px; left:8px; z-index:3; }}
</style></head><body>
  <div class="inner">
    <div class="left">
      <div class="badges">{"".join(f'<span class="pill{" a" if i==0 else " dot"}">{html.escape(b)}</span>' for i,b in enumerate(cfg["badges"]))}</div>
      <div class="titlerow"><div class="glyph">{cfg["emoji"]}</div><h1>{html.escape(cfg["title"])}</h1></div>
      <div class="tag">{cfg["tag"]}</div>
    </div>
    <div class="right">
      <div class="deco"></div>
      <div class="stage">{cfg["motif"]}
        <span class="fdot d1"></span><span class="fdot d2"></span><span class="fdot d3"></span><span class="ring"></span>
      </div>
    </div>
  </div>
</body></html>"""

# ---------- motifs ----------
def m_controls(a1,a2):  # interface-defaults: full control cluster
    return f'''<svg width="384" height="300" viewBox="0 0 384 300" fill="none" font-family="sans-serif">
      <!-- toggles -->
      <rect x="4" y="4" width="112" height="44" rx="22" fill="{a1}"/><circle cx="94" cy="26" r="16" fill="#fff"/>
      <rect x="140" y="4" width="112" height="44" rx="22" fill="#2b2c39" stroke="rgba(255,255,255,.08)"/><circle cx="162" cy="26" r="16" fill="#8a8b9e"/>
      <!-- dropdown -->
      <rect x="4" y="66" width="150" height="46" rx="12" fill="#171826" stroke="{a1}66"/>
      <text x="20" y="95" fill="#dcd9ff" font-size="18">Auto</text>
      <path d="M118 84 l9 9 l9 -9" fill="none" stroke="{a2}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      <!-- number stepper -->
      <rect x="170" y="66" width="130" height="46" rx="12" fill="#171826" stroke="rgba(255,255,255,.1)"/>
      <text x="192" y="97" fill="#9a9ab0" font-size="26" text-anchor="middle">&#8722;</text>
      <text x="235" y="94" fill="#fff" font-size="18" text-anchor="middle" font-family="monospace">1.0</text>
      <text x="278" y="96" fill="{a1}" font-size="24" text-anchor="middle">+</text>
      <!-- slider -->
      <rect x="4" y="146" width="296" height="6" rx="3" fill="#33343f"/>
      <rect x="4" y="146" width="188" height="6" rx="3" fill="{a1}"/>
      <circle cx="192" cy="149" r="14" fill="#fff"/>
      <!-- checkbox + radio + line -->
      <rect x="4" y="196" width="36" height="36" rx="9" fill="{a2}"/><path d="M13 214 l7 7 l13 -15" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="78" cy="214" r="18" fill="none" stroke="{a1}" stroke-width="4"/><circle cx="78" cy="214" r="8" fill="{a1}"/>
      <rect x="116" y="200" width="184" height="28" rx="8" fill="#22232e"/>
      <rect x="330" y="66" width="46" height="46" rx="12" fill="{a2}22" stroke="{a2}"/><path d="M341 89 h24 M353 77 v24" stroke="{a2}" stroke-width="3" stroke-linecap="round"/>
    </svg>'''

def m_charts(a1,a2):  # visualizer: bars + line + dots + donut
    cols=["#14b8a6","#7c6ef0","#d85a30","#378add","#ba7517"]
    bars="".join(f'<rect x="{16+i*50}" y="{230-h}" width="32" height="{h}" rx="6" fill="{c}"/>' for i,(h,c) in enumerate(zip([80,150,60,190,120],cols)))
    dots="".join(f'<circle cx="{16+i*50+16}" cy="{y}" r="7" fill="#fff" stroke="{a1}" stroke-width="3"/>' for i,y in enumerate([120,70,150,40,90]))
    return f'''<svg width="384" height="300" viewBox="0 0 384 300" fill="none">
      {bars}
      <path d="M32 120 L82 70 L132 150 L182 40 L232 90" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity=".92"/>
      {dots}
      <rect x="10" y="248" width="250" height="4" rx="2" fill="rgba(255,255,255,.14)"/>
      <!-- donut -->
      <g transform="translate(322,66)">
        <circle r="42" fill="none" stroke="#26283a" stroke-width="16"/>
        <circle r="42" fill="none" stroke="{a1}" stroke-width="16" stroke-dasharray="150 264" stroke-linecap="round" transform="rotate(-90)"/>
        <circle r="42" fill="none" stroke="{a2}" stroke-width="16" stroke-dasharray="70 264" stroke-dashoffset="-150" stroke-linecap="round" transform="rotate(-90)"/>
      </g>
      <g transform="translate(300,150)" stroke="{a2}" stroke-width="3"><circle cx="10" cy="6" r="5" fill="{a2}"/><circle cx="34" cy="20" r="5" fill="none"/><circle cx="52" cy="0" r="5" fill="{a1}"/></g>
    </svg>'''

def m_email(a1,a2):  # centered envelope, top-right "send" plane accent with trail
    return f'''<svg width="384" height="300" viewBox="0 0 384 300" fill="none">
      <!-- centered envelope (focal point) -->
      <rect x="42" y="78" width="234" height="156" rx="15" fill="#141520" stroke="{a1}" stroke-width="3"/>
      <path d="M48 92 L159 162 L270 92" fill="none" stroke="{a2}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="66" y="170" width="118" height="8" rx="4" fill="#2a2c3b"/>
      <rect x="66" y="185" width="172" height="8" rx="4" fill="#22232e"/>
      <g transform="translate(60,201)" font-family="sans-serif">
        <rect x="0" y="0" width="54" height="24" rx="12" fill="{a1}33" stroke="{a1}" stroke-width="1.5"/><text x="27" y="17" fill="#dfe6ff" font-size="13" text-anchor="middle">To</text>
        <rect x="62" y="0" width="58" height="24" rx="12" fill="{a2}22" stroke="{a2}" stroke-width="1.5"/><text x="91" y="17" fill="#dfe6ff" font-size="13" text-anchor="middle">CC</text>
        <rect x="130" y="0" width="66" height="24" rx="12" fill="#22232e" stroke="rgba(255,255,255,.12)"/><text x="163" y="17" fill="#c2c2d2" font-size="13" text-anchor="middle">BCC</text>
      </g>
      <!-- send: dashed trajectory from envelope corner up to the plane -->
      <path d="M268 96 C300 92 316 74 336 56" fill="none" stroke="{a2}" stroke-width="3" stroke-dasharray="2 11" stroke-linecap="round" opacity=".85"/>
      <g transform="translate(300,26) rotate(12)"><path d="M0 30 L58 6 L44 62 L31 42 Z" fill="{a1}"/><path d="M58 6 L31 42" stroke="#0b0c12" stroke-width="2"/></g>
      <g fill="{a2}"><circle cx="352" cy="86" r="3.5"/><circle cx="366" cy="64" r="2.5"/></g>
    </svg>'''

def m_bridge(a1,a2):  # server rack -> ui:// packet flow -> app window with live chart
    return f'''<svg width="384" height="300" viewBox="0 0 384 300" fill="none" font-family="monospace">
      <line x1="118" y1="104" x2="220" y2="104" stroke="{a2}" stroke-width="4" stroke-dasharray="2 12" stroke-linecap="round"/>
      <circle cx="160" cy="104" r="6" fill="{a2}"/>
      <rect x="18" y="70" width="100" height="140" rx="16" fill="#111a16" stroke="{a1}" stroke-width="3"/>
      <g>
        <rect x="32" y="86" width="72" height="30" rx="7" fill="#18241f" stroke="{a1}" stroke-width="1.5"/>
        <circle cx="44" cy="101" r="4" fill="{a1}"/>
        <line x1="56" y1="101" x2="92" y2="101" stroke="{a1}" stroke-width="3" stroke-linecap="round" opacity=".7"/>
        <rect x="32" y="124" width="72" height="30" rx="7" fill="#18241f" stroke="{a1}" stroke-width="1.5"/>
        <circle cx="44" cy="139" r="4" fill="{a2}"/>
        <line x1="56" y1="139" x2="84" y2="139" stroke="{a1}" stroke-width="3" stroke-linecap="round" opacity=".7"/>
        <rect x="32" y="162" width="72" height="30" rx="7" fill="#18241f" stroke="{a1}" stroke-width="1.5"/>
        <circle cx="44" cy="177" r="4" fill="#8fe8cf"/>
        <line x1="56" y1="177" x2="96" y2="177" stroke="{a1}" stroke-width="3" stroke-linecap="round" opacity=".7"/>
      </g>
      <rect x="220" y="54" width="146" height="172" rx="16" fill="#0f1a16" stroke="{a2}" stroke-width="3"/>
      <rect x="220" y="54" width="146" height="30" rx="16" fill="#18241f"/>
      <rect x="220" y="72" width="146" height="12" fill="#18241f"/>
      <circle cx="236" cy="69" r="4" fill="{a2}"/><circle cx="250" cy="69" r="4" fill="{a1}"/><circle cx="264" cy="69" r="4" fill="#8fe8cf"/>
      <g stroke="#8fe8cf" stroke-width="3" stroke-linecap="round" opacity=".75">
        <line x1="236" y1="102" x2="330" y2="102"/><line x1="236" y1="118" x2="306" y2="118"/>
      </g>
      <g fill="{a2}">
        <rect x="236" y="168" width="14" height="38" rx="4" opacity=".55"/>
        <rect x="256" y="150" width="14" height="56" rx="4" opacity=".8"/>
        <rect x="276" y="160" width="14" height="46" rx="4" opacity=".65"/>
        <rect x="296" y="136" width="14" height="70" rx="4"/>
      </g>
      <circle cx="338" cy="178" r="20" stroke="{a1}" stroke-width="7" fill="none" opacity=".9"
        stroke-dasharray="94 32" stroke-linecap="round" transform="rotate(-45 338 178)"/>
      <g transform="translate(134,120)"><rect x="0" y="0" width="88" height="36" rx="10" fill="#0c1512" stroke="rgba(255,255,255,.2)"/><text x="44" y="24" fill="#bdf3df" font-size="17" text-anchor="middle">ui://</text></g>
      <g transform="translate(160,168)"><rect x="0" y="0" width="62" height="26" rx="8" fill="#0c1512" stroke="{a1}" stroke-width="1.5"/><text x="31" y="18" fill="#bdf3df" font-size="13" text-anchor="middle">CSP</text></g>
      <text x="68" y="238" fill="#8fb8ab" font-size="14" text-anchor="middle" font-family="sans-serif">MCP server</text>
      <text x="293" y="252" fill="#8fb8ab" font-size="14" text-anchor="middle" font-family="sans-serif">Rich UI embed</text>
    </svg>'''

def m_vision(a1,a2):  # image + scan + arrow + text card + eye
    return f'''<svg width="384" height="300" viewBox="0 0 384 300" fill="none">
      <rect x="16" y="80" width="150" height="130" rx="14" fill="#1a160e" stroke="{a1}" stroke-width="3"/>
      <circle cx="56" cy="118" r="15" fill="{a1}"/>
      <path d="M24 196 L70 144 L104 178 L130 150 L158 196 Z" fill="{a2}" opacity=".85"/>
      <g stroke="{a2}" stroke-width="2" opacity=".5"><line x1="16" y1="120" x2="166" y2="120"/><line x1="16" y1="150" x2="166" y2="150"/><line x1="16" y1="180" x2="166" y2="180"/></g>
      <!-- eye badge -->
      <g transform="translate(120,64)"><path d="M0 14 C10 0 34 0 44 14 C34 28 10 28 0 14 Z" fill="#0b0c12" stroke="{a1}" stroke-width="2.5"/><circle cx="22" cy="14" r="7" fill="{a1}"/></g>
      <!-- arrow -->
      <path d="M182 145 h40" stroke="{a2}" stroke-width="4" stroke-linecap="round"/><path d="M214 133 l14 12 l-14 12" fill="none" stroke="{a2}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
      <!-- text card -->
      <rect x="240" y="96" width="120" height="118" rx="18" fill="#161821" stroke="{a1}" stroke-width="3"/>
      <g stroke="#cfd6ff" stroke-width="4" stroke-linecap="round"><line x1="260" y1="126" x2="340" y2="126"/><line x1="260" y1="146" x2="340" y2="146"/><line x1="260" y1="166" x2="340" y2="166"/><line x1="260" y1="186" x2="316" y2="186"/></g>
    </svg>'''

def m_prune(a1, a2):  # database, throttle gauge, metered trickle, progress bar, sparkles
    # Gauge geometry: a 248-degree dial centred at (gx, gy). Points are polar,
    # so a helper turns an angle + radius into an (x, y) on the dial.
    gx, gy, gr = 306, 70, 27
    sweep_start, sweep_end = 214.0, -34.0
    span = sweep_start - sweep_end
    needle_deg = sweep_start - 0.30 * span  # needle reads ~30%: deliberately slow

    def polar(deg, radius):
        angle = math.radians(deg)
        return gx + radius * math.cos(angle), gy - radius * math.sin(angle)

    def arc(from_deg, to_deg, radius):
        (x0, y0), (x1, y1) = polar(from_deg, radius), polar(to_deg, radius)
        long_arc = 1 if abs(from_deg - to_deg) > 180 else 0
        return f"M{x0:.1f} {y0:.1f} A{radius} {radius} 0 {long_arc} 1 {x1:.1f} {y1:.1f}"

    def tick(deg):
        (ix, iy), (ox, oy) = polar(deg, gr + 3), polar(deg, gr + 8)
        return (f'<line x1="{ix:.1f}" y1="{iy:.1f}" x2="{ox:.1f}" y2="{oy:.1f}" '
                f'stroke="#5d6d67" stroke-width="2" stroke-linecap="round"/>')

    def spark(cx, cy, radius, fill, op):
        waist = radius * 0.28  # inner waist of the four-point star
        return (f'<path transform="translate({cx},{cy})" '
                f'd="M0 {-radius} L{waist:.1f} {-waist:.1f} L{radius} 0 L{waist:.1f} {waist:.1f} '
                f'L0 {radius} L{-waist:.1f} {waist:.1f} L{-radius} 0 L{-waist:.1f} {-waist:.1f} Z" '
                f'fill="{fill}" opacity="{op}"/>')

    needle_x, needle_y = polar(needle_deg, gr - 6)
    ticks = "".join(tick(sweep_start - i * span / 6) for i in range(7))
    # Metered trickle draining from the db base: evenly spaced, fading out.
    drops = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{a2}" opacity="{op}"/>'
        for cx, cy, r, op in [(160, 184, 6, .95), (186, 204, 5.2, .7), (210, 223, 4.3, .48), (232, 240, 3.5, .3)]
    )
    return f'''<svg width="384" height="300" viewBox="0 0 384 300" fill="none">
      <defs>
        <linearGradient id="prDb" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#13231f"/><stop offset="1" stop-color="#0b1512"/></linearGradient>
        <linearGradient id="prBar" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{a1}"/><stop offset="1" stop-color="{a2}"/></linearGradient>
      </defs>
      <!-- database (hero) -->
      <g stroke="{a1}" stroke-width="3">
        <path d="M42 76 v100 a54 17 0 0 0 108 0 v-100" fill="url(#prDb)"/>
        <ellipse cx="96" cy="76" rx="54" ry="17" fill="url(#prDb)"/>
        <path d="M42 110 a54 17 0 0 0 108 0" fill="none" stroke-width="2.4" opacity=".55"/>
        <path d="M42 143 a54 17 0 0 0 108 0" fill="none" stroke-width="2.4" opacity=".55"/>
      </g>
      <path d="M55 71 a44 12 0 0 1 82 0" fill="none" stroke="#7fe6d2" stroke-width="2" stroke-linecap="round" opacity=".5"/>
      <!-- clean sparkles -->
      {spark(150,44,9,'#ffffff',.95)}{spark(128,32,5,a2,.85)}{spark(62,54,4.5,'#eafff8',.7)}
      <!-- verified-safe badge -->
      <g transform="translate(146,92)"><circle r="14" fill="{a2}"/><path d="M-6 0 l4.5 5.5 l8.5 -10.5" fill="none" stroke="#08120f" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/></g>
      <!-- metered trickle out -->
      <path d="M150 176 C 176 198, 205 210, 234 236" fill="none" stroke="{a2}" stroke-width="2" stroke-dasharray="1 11" stroke-linecap="round" opacity=".55"/>
      {drops}
      <!-- throttle gauge -->
      <circle cx="{gx}" cy="{gy}" r="{gr+13}" fill="#0d1a17" stroke="rgba(255,255,255,.08)" stroke-width="1.5"/>
      {ticks}
      <path d="{arc(sweep_start, sweep_end, gr)}" fill="none" stroke="#28352f" stroke-width="6" stroke-linecap="round"/>
      <path d="{arc(sweep_start, needle_deg, gr)}" fill="none" stroke="url(#prBar)" stroke-width="6" stroke-linecap="round"/>
      <line x1="{gx}" y1="{gy}" x2="{needle_x:.1f}" y2="{needle_y:.1f}" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
      <circle cx="{gx}" cy="{gy}" r="5" fill="{a2}" stroke="#08120f" stroke-width="1.5"/>
      <!-- progress -->
      <rect x="28" y="260" width="328" height="7" rx="3.5" fill="#233029"/>
      <rect x="28" y="260" width="206" height="7" rx="3.5" fill="url(#prBar)"/>
      <circle cx="234" cy="263.5" r="6" fill="#fff"/>
    </svg>'''

banners = {
  "interface-defaults": dict(a1="#7c6ef0", a2="#a78bfa", emoji="🎛️", title="Interface Defaults", title_size=86,
    badges=["Event function","Auto-seed","Bulk apply","Native Valves"],
    tag="Set <b>Settings &rarr; Interface</b> defaults for your whole instance from one function's Valves. New users seeded automatically on signup, OAuth and SCIM.",
    motif=m_controls("#7c6ef0","#a78bfa")),
  "inline-visualizer-v2": dict(a1="#14b8a6", a2="#7c6ef0", emoji="📊", title="Inline Visualizer", title_size=78,
    badges=["Tool + Skill","Live rendered","Chart.js · D3 · Plotly","Conversational"],
    tag="<b>Live interactive</b> HTML/SVG visualizations, dashboards and charts rendered inline in chat, with a full theme-aware design system.",
    motif=m_charts("#14b8a6","#7c6ef0")),
  "email-composer": dict(a1="#3b82f6", a2="#38bdf8", emoji="✉️", title="Email Composer", title_size=80,
    badges=["Tool","Rich UI card","To/CC/BCC",".eml export"],
    tag="AI email drafting in an <b>interactive Rich UI card</b>. Rich text, recipient chips, priority, autosave and one-click send.",
    motif=m_email("#3b82f6","#38bdf8")),
  "mcp-app-bridge": dict(a1="#10b981", a2="#34d399", emoji="🧩", title="MCP App Bridge", title_size=78,
    badges=["Tool","MCP Apps","SEP-1865","ui:// + CSP"],
    tag="Use <b>MCP Apps</b> right in your chat: tools bring their own interactive interface, rendered as an embedded panel. No middleware, no core changes.",
    motif=m_bridge("#10b981","#34d399")),
  "vision-bridge": dict(a1="#f59e0b", a2="#fb7185", emoji="👁️", title="Vision Bridge", title_size=80,
    badges=["Filter + Tool","No core changes","On-demand","Re-queryable"],
    tag="Give a <b>text-only model</b> the ability to work with images. Call <b>analyze_image()</b> on demand and re-query with new questions any time.",
    motif=m_vision("#f59e0b","#fb7185")),
  "prune": dict(a1="#14b8a6", a2="#22c55e", emoji="🧹", title="Prune", title_size=90,
    badges=["Event function","Throttled deletes","Dry-run preview","Multi-worker safe"],
    tag="Automatic, <b>throttled</b> database &amp; storage cleanup driven by system events. Purposefully slow, so a live instance <b>never even notices</b>.",
    motif=m_prune("#14b8a6","#22c55e")),
}

for key, cfg in banners.items():
    open(f"banner_{key}.html","w",encoding="utf-8").write(page(cfg))
    print("wrote banner_"+key+".html")
