# Generates one self-contained 1:1 icon HTML per plugin, for the root README table.
# Rendered to PNG by render_squares.mjs. Shares the palette, background treatment and
# glyph of banners.py so the two read as one family.
#
# Only plugins that have a banner get a square. Tiles are displayed at ~100px in a
# markdown table, so they carry the glyph and a short name, nothing else.
import html

S = 400

def page(cfg):
    a1, a2 = cfg["a1"], cfg["a2"]
    ts = cfg.get("title_size", 46)
    title = "<br>".join(html.escape(part) for part in cfg["title"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html,body {{ width:{S}px; height:{S}px; }}
body {{
  font-family:-apple-system,"Segoe UI",system-ui,sans-serif; color:#ececf3; overflow:hidden; position:relative;
  background:
    radial-gradient(300px 300px at 0% -10%, {a1}55, transparent 62%),
    radial-gradient(300px 300px at 108% 112%, {a2}3d, transparent 60%),
    linear-gradient(120deg,#08090d 0%, #0c0d14 55%, #090a10 100%);
}}
body::before {{ content:""; position:absolute; inset:0;
  background-image:radial-gradient(rgba(255,255,255,.05) 1px, transparent 1px); background-size:20px 20px;
  mask-image:radial-gradient(300px 300px at 50% 44%, #000 40%, transparent 86%); }}
body::after {{ content:""; position:absolute; left:0; top:0; bottom:0; width:9px;
  background:linear-gradient(180deg,{a1},{a2}); }}
.deco {{ position:absolute; left:50%; top:44%; width:430px; height:430px; margin:-215px 0 0 -215px;
  border-radius:50%;
  background:repeating-radial-gradient(circle at 50% 50%, {a1}26 0 1.5px, transparent 1.5px 36px);
  -webkit-mask-image:radial-gradient(circle at 50% 50%, #000 30%, transparent 68%);
  mask-image:radial-gradient(circle at 50% 50%, #000 30%, transparent 68%); opacity:.6; }}
.inner {{ position:relative; z-index:2; height:100%; display:flex; flex-direction:column;
  align-items:center; justify-content:center; gap:22px; padding:0 26px 0 34px; }}
.glyph {{ font-size:152px; line-height:1; filter:drop-shadow(0 10px 26px {a1}77); }}
h1 {{ font-size:{ts}px; line-height:1.06; font-weight:800; letter-spacing:-1.1px; text-align:center;
  /* Same descender guard as banners.py: background-clip:text paints only inside the
     padding box, so a short padding-bottom cuts the tail off a 'g' or 'p'. */
  padding:4px 8px 26px 8px; margin-bottom:-26px;
  background:linear-gradient(180deg,#fff,{a2}); -webkit-background-clip:text; background-clip:text; color:transparent; }}
.fdot {{ position:absolute; border-radius:50%; z-index:3; }}
.d1 {{ width:16px; height:16px; background:{a1}; top:26px; left:36px; box-shadow:0 0 20px {a1}; }}
.d2 {{ width:12px; height:12px; background:{a2}; bottom:30px; right:28px; box-shadow:0 0 16px {a2}; }}
.ring {{ position:absolute; width:30px; height:30px; border:2px solid {a2}; border-radius:50%; opacity:.45;
  top:34px; right:34px; z-index:3; }}
</style></head><body>
  <div class="deco"></div>
  <div class="inner">
    <div class="glyph">{cfg["emoji"]}</div>
    <h1>{title}</h1>
  </div>
  <span class="fdot d1"></span><span class="fdot d2"></span><span class="ring"></span>
</body></html>"""

# Palette and glyph per plugin are copied from banners.py so the pair always matches.
# title is a list, one entry per rendered line.
squares = {
  "interface-defaults":   dict(a1="#7c6ef0", a2="#a78bfa", emoji="🎛️", title=["Interface", "Defaults"]),
  "inline-visualizer-v2": dict(a1="#14b8a6", a2="#7c6ef0", emoji="📊", title=["Inline", "Visualizer v2"], title_size=42),
  "email-composer":       dict(a1="#3b82f6", a2="#38bdf8", emoji="✉️", title=["Email", "Composer"]),
  "mcp-app-bridge":       dict(a1="#10b981", a2="#34d399", emoji="🧩", title=["MCP App", "Bridge"]),
  "vision-bridge":        dict(a1="#f59e0b", a2="#fb7185", emoji="👁️", title=["Vision", "Bridge"]),
  "prune":                dict(a1="#14b8a6", a2="#22c55e", emoji="🧹", title=["Prune"], title_size=58),
}

for key, cfg in squares.items():
    open(f"square_{key}.html", "w", encoding="utf-8").write(page(cfg))
    print("wrote square_" + key + ".html")
