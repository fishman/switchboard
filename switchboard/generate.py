"""switchboard - ZMK keymap compiler. YAML in, standalone ZMK out."""

from pathlib import Path
import json
import yaml
import sys

from jinja2 import Environment, FileSystemLoader

from switchboard import resolve as resolve_key, parse_row
from switchboard.validate import validate

ROOT = Path(__file__).parent.parent
LIBRARY = ROOT / "library"
TEMPLATES = ROOT / "templates"


def load_config(path: str = "config.yaml") -> dict:
    config_path = ROOT / path
    with open(config_path) as f:
        config = yaml.safe_load(f)
    layers = config.get("layers", {})
    for name, layer in list(layers.items()):
        layers[name] = _resolve_layer(layer, config)
    return config


def _resolve_layer(layer: dict, config: dict) -> dict:
    resolved = dict(layer)
    alpha_name = layer.get("alpha")
    if alpha_name:
        alpha_path = LIBRARY / "alphas" / f"{alpha_name}.yaml"
        if alpha_path.exists():
            with open(alpha_path) as f:
                alpha = yaml.safe_load(f)
            preset_rows = alpha.get("rows", {})
            for rk, rv in preset_rows.items():
                rk_int = int(rk) if isinstance(rk, str) and rk.isdigit() else rk
                layer_rows = resolved.setdefault("rows", {})
                if rk_int not in layer_rows and str(rk_int) not in layer_rows:
                    layer_rows[rk_int] = rv
            resolved["_source"] = f"alpha:{alpha_name}"
    import_name = layer.get("import")
    if import_name:
        import_path = LIBRARY / "layers" / f"{import_name}.yaml"
        if import_path.exists():
            with open(import_path) as f:
                imported = yaml.safe_load(f)
            for key in ("rows", "thumbs", "display"):
                if key in imported and key not in resolved:
                    val = imported[key]
                    if key == "thumbs" and isinstance(val, dict):
                        left = val.get("left", "NONE | NONE | NONE")
                        right = val.get("right", "NONE | NONE | NONE")
                        val = f"{left} | {right}"
                    resolved[key] = val
            resolved["_source"] = f"import:{import_name}"
    return resolved


def _get_full_row(rows: dict, row_idx: int, default: str = "") -> list[str]:
    val = rows.get(row_idx, rows.get(str(row_idx), default))
    return parse_row(str(val), sep="|")


def _get_full_thumbs(thumbs_str: str) -> list[str]:
    return parse_row(str(thumbs_str), sep="|")


def _extract_inner_keys(physical: dict, layer: dict) -> list[str]:
    """Extract Miryoku inner keys (36 values) for K00-K37 params."""
    inner_cfg = physical["miryoku_inner"]
    row_start, row_end = inner_cfg["row_range"]
    col_ranges = inner_cfg["col_ranges"]
    thumb_ranges = inner_cfg["thumb_ranges"]
    rows = layer.get("rows", {})
    thumbs = layer.get("thumbs", "")

    keys = []
    for row_i in range(row_start, row_end + 1):
        full = _get_full_row(rows, row_i)
        for half_i, (c_start, c_end) in enumerate(col_ranges):
            if row_i == 3 and half_i == 1 and len(full) == 14:
                inner = full[8:13]
            else:
                inner = full[c_start:c_end + 1]
            keys.extend(inner)

    full_thumbs = _get_full_thumbs(thumbs)
    n_thumbs = len(full_thumbs)
    if n_thumbs == 6:
        keys.extend(full_thumbs[:3])
        keys.extend(full_thumbs[3:6])
    else:
        for t_start, t_end in thumb_ranges:
            keys.extend(full_thumbs[t_start:t_end + 1])

    return keys


def _build_layer_context(physical: dict, layer: dict, name: str) -> dict:
    inner_cfg = physical["miryoku_inner"]
    thumb_ranges = inner_cfg["thumb_ranges"]
    outer_thumb = inner_cfg.get("outer_thumb_cols", [0, 7])
    row_start, row_end = inner_cfg["row_range"]
    rows = layer.get("rows", {})
    thumbs_str = layer.get("thumbs", "")

    ctx = {"name": name, "display": layer.get("display", name)}

    row0 = _get_full_row(rows, 0)
    n0 = len(row0)
    mid = n0 // 2
    ctx["row0_left"] = " ".join(resolve_key(k, "zmk") for k in row0[:mid])
    ctx["row0_right"] = " ".join(resolve_key(k, "zmk") for k in row0[mid:])

    for row_i in range(row_start, row_end + 1):
        full = _get_full_row(rows, row_i)
        if row_i < 3:
            ctx[f"r{row_i}_l"] = resolve_key(full[0], "zmk")
            ctx[f"r{row_i}_r"] = resolve_key(full[11], "zmk")
        else:
            ctx[f"r{row_i}_l"] = resolve_key(full[0], "zmk")
            ctx[f"r{row_i}_r"] = resolve_key(full[13], "zmk") if len(full) > 13 else "&none"
            ctx["lie_k"] = resolve_key(full[6], "zmk") if len(full) > 6 else "&none"
            ctx["rie_k"] = resolve_key(full[7], "zmk") if len(full) > 7 else "&none"

    full_thumbs = _get_full_thumbs(thumbs_str)
    ctx["th_l"] = resolve_key(full_thumbs[outer_thumb[0]], "zmk") if len(full_thumbs) > outer_thumb[0] else "&none"
    ctx["th_r"] = resolve_key(full_thumbs[outer_thumb[1]], "zmk") if len(full_thumbs) > outer_thumb[1] else "&none"

    # inner keys resolved to ZMK
    inner_keys = _extract_inner_keys(physical, layer)
    ctx["inner_keys"] = [resolve_key(k, "zmk") for k in inner_keys]

    return ctx


def generate(config: dict, output_dir: str) -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), trim_blocks=True, lstrip_blocks=True)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    physical = config["physical"]
    layers = config["layers"]
    behaviors = config.get("behaviors", {"tap_term_ms": 200, "quick_tap_ms": 0})

    layer_ctxs = []
    for name, layer in layers.items():
        layer_ctxs.append(_build_layer_context(physical, layer, name))

    # sensor layers (mirrors the layer list)
    sensor_layers = []
    for i, lc in enumerate(layer_ctxs):
        sensor_layers.append({"name": lc["name"], "index": i})

    ctx = {
        "layers": layer_ctxs,
        "sensor_layers": sensor_layers,
        "behaviors": behaviors,
    }

    shield = config["physical"]["shield"]
    config_dir = out / "config" / "boards" / "shields" / shield
    config_dir.mkdir(parents=True, exist_ok=True)

    (config_dir / f"{shield}.keymap").write_text(env.get_template("keymap.j2").render(ctx))
    (config_dir / f"{shield}.conf").write_text(env.get_template("custom.conf.j2").render(ctx))
    (config_dir / "layout.html").write_text(_generate_html(config))

    (out / "build.yaml").write_text(env.get_template("build.j2").render({"shield": shield}))
    (out / "west.yml").write_text(env.get_template("west.j2").render({}))

    conf_path = (out / "config").resolve()
    print(f"Generated -> {config_dir}/")
    print(f"  {shield}.keymap")
    print(f"  {shield}.conf")
    print(f"  layout.html")
    print(f"  build.yaml")
    print(f"\n  west build -- -DZMK_CONFIG={conf_path} -DSHIELD={shield}_left")


def _generate_html(config: dict) -> str:
    layer_data = {}
    for name, layer in config["layers"].items():
        display = layer.get("display", name)
        rows = layer.get("rows", {})
        thumbs = layer.get("thumbs", "")
        layer_data[name] = {
            "display": display,
            "rows": {str(k): parse_row(str(v), sep="|") for k, v in rows.items()},
            "thumbs": parse_row(str(thumbs), sep="|"),
        }
    data_json = json.dumps(layer_data, indent=2)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{config['meta']['name']} - switchboard</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:20px}}
h1{{font-size:1.2em;margin-bottom:16px;color:#a0a0c0}}
.tabs{{display:flex;gap:4px;margin-bottom:20px;flex-wrap:wrap}}
.tab{{padding:6px 14px;border:1px solid #333;border-radius:6px;cursor:pointer;font-size:.85em;background:#16213e;color:#888;transition:all .15s}}
.tab:hover{{background:#1a1a3e;color:#ccc}}
.tab.active{{background:#0f3460;color:#e0e0e0;border-color:#533483}}
.keyboard{{display:inline-block}}
.row{{display:flex;gap:3px;margin-bottom:3px}}
.key{{width:52px;height:48px;border:1px solid #2a2a4a;border-radius:5px;display:flex;align-items:center;justify-content:center;font-size:.68em;background:#16213e;color:#ccc;text-align:center;line-height:1.2;word-break:break-all;padding:2px}}
.key.empty{{background:#111;border-color:#1a1a2e;color:#333}}
.key.thumb{{background:#1a1a3e}}
.key.outer{{background:#1e1e3a}}
.key.mod{{color:#7eb8da}}
.key.layer{{color:#e2a76f}}
.key.sym{{color:#a0d0a0}}
.key.nav{{color:#d0a0d0}}
.gap{{width:20px}}
.legend{{margin-top:20px;font-size:.75em;color:#666;display:flex;gap:16px}}
.legend span{{display:flex;align-items:center;gap:4px}}
.legend .dot{{width:10px;height:10px;border-radius:2px;display:inline-block}}
</style>
</head>
<body>
<h1>{config['meta']['name']}</h1>
<div class="tabs" id="tabs"></div>
<div id="keyboard"></div>
<div class="legend">
<span><span class="dot" style="background:#7eb8da"></span>modifiers</span>
<span><span class="dot" style="background:#e2a76f"></span>layers</span>
<span><span class="dot" style="background:#a0d0a0"></span>symbols</span>
<span><span class="dot" style="background:#d0a0d0"></span>nav</span>
</div>
<script>
const DATA={data_json};
const LAYERS=Object.keys(DATA);
let current=LAYERS[0];
function cls(k){{
const u=(k||'').toUpperCase();
if(!u||u==='NONE')return'empty';
if(u.startsWith('MT(')||'LCTL LALT LSFT LGUI RCTL RALT RSFT RGUI'.includes(u))return'key mod';
if(u.startsWith('LT(')||u.startsWith('TO(')||u.startsWith('MO('))return'key layer';
if('LBRC RBRC LPAR RPAR LBKT RBKT AMPS ASTRK AT HASH DLLR PRCNT CARET COLON SEMI COMMA DOT SLASH SQT GRAVE TILDE UNDER PIPE PLUS EQUAL BSLH EXCL'.includes(u))return'key sym';
if('UP DOWN LEFT RIGHT HOME END PGUP PGDN INS DEL BSPC TAB RET ENT ESC SPC'.includes(u))return'key nav';
return'';
}}
function render(name){{
const l=DATA[name],r=l.rows,t=l.thumbs;
let h='<div class="keyboard">';
if(r['0']||r[0]){{h+='<div class="row">';(r['0']||r[0]).forEach((k,i)=>{{h+=`<div class="key outer ${{cls(k)}}">${{k==='NONE'?'':k}}</div>`;if(i===5)h+='<div class="gap"></div>';}});h+='</div>';}}
for(let ri=1;ri<=3;ri++){{if(!r[String(ri)]&&r[ri]===undefined)continue;h+='<div class="row">';(r[String(ri)]||r[ri]).forEach((k,i)=>{{const c=i===0||i===11||i===13?'outer':'';h+=`<div class="key ${{c}} ${{cls(k)}}">${{k==='NONE'?'':k}}</div>`;if(i===5||i===6)h+=i===5?'':'<div class="gap"></div>';}});h+='</div>';}}
if(t&&t.length){{h+='<div class="row">';t.forEach((k,i)=>{{h+=`<div class="key thumb ${{cls(k)}}">${{k==='NONE'?'':k}}</div>`;if(i===3)h+='<div class="gap"></div>';}});h+='</div>';}}
h+='</div>';document.getElementById('keyboard').innerHTML=h;
}}
(function(){{
const tabs=document.getElementById('tabs');
LAYERS.forEach(n=>{{const b=document.createElement('div');b.className='tab'+(n===current?' active':'');b.textContent=DATA[n].display||n;b.onclick=()=>{{document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));b.classList.add('active');current=n;render(n);}};tabs.appendChild(b);}});
render(current);
}})();
</script>
</body>
</html>"""
