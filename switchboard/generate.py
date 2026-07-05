"""Generate ZMK keymap files + HTML viewer from config.yaml.

Architecture: full keyboard grid is the source of truth.
The 'miryoku_inner' subset is extracted for K parameters;
remaining positions are hardcoded per layer in the mapping macro.
"""

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

    # Resolve alpha preset: merge preset rows into layer rows
    alpha_name = layer.get("alpha")
    if alpha_name:
        alpha_path = LIBRARY / "alphas" / f"{alpha_name}.yaml"
        if alpha_path.exists():
            with open(alpha_path) as f:
                alpha = yaml.safe_load(f)
            preset_rows = alpha.get("rows", {})
            for rk, rv in preset_rows.items():
                # YAML may parse keys as int
                rk_int = int(rk) if isinstance(rk, str) and rk.isdigit() else rk
                rk_str = str(rk)
                layer_rows = resolved.setdefault("rows", {})
                if rk_int not in layer_rows and rk_str not in layer_rows:
                    layer_rows[rk_int] = rv
            resolved["_source"] = f"alpha:{alpha_name}"

    # Resolve import: merge imported keys
    import_name = layer.get("import")
    if import_name:
        import_path = LIBRARY / "layers" / f"{import_name}.yaml"
        if import_path.exists():
            with open(import_path) as f:
                imported = yaml.safe_load(f)
            for key in ("rows", "thumbs", "display"):
                if key in imported and key not in resolved:
                    val = imported[key]
                    # Convert old dict thumbs format to pipe-separated string
                    if key == "thumbs" and isinstance(val, dict):
                        left = val.get("left", "NONE | NONE | NONE")
                        right = val.get("right", "NONE | NONE | NONE")
                        val = f"{left} | {right}"
                    resolved[key] = val
            resolved["_source"] = f"import:{import_name}"

    return resolved


def _get_full_row(rows: dict, row_idx: int, default: str = "") -> list[str]:
    """Get a parsed row from the layer's rows dict (keys may be int or str)."""
    val = rows.get(row_idx, rows.get(str(row_idx), default))
    return parse_row(str(val), sep="|")


def _get_full_thumbs(thumbs_str: str) -> list[str]:
    return parse_row(str(thumbs_str), sep="|")


def _extract_inner(physical: dict, layer: dict) -> dict:
    """Extract Miryoku inner subset (K params) from full layer rows."""
    inner_cfg = physical["miryoku_inner"]
    row_start, row_end = inner_cfg["row_range"]
    col_ranges = inner_cfg["col_ranges"]      # [[1,5], [6,10]]
    thumb_ranges = inner_cfg["thumb_ranges"]  # [[1,3], [4,6]]

    rows = layer.get("rows", {})
    thumbs = layer.get("thumbs", "")

    inner = {}

    # Extract inner columns from each alpha row
    for row_i in range(row_start, row_end + 1):
        full = _get_full_row(rows, row_i)
        n = len(full)
        if n == 10:
            # Library-style row: 5 left + 5 right inner, no outer cols
            for half_i in range(2):
                start = half_i * 5
                inner[f"row{row_i}_half{half_i}"] = full[start:start + 5]
        elif n >= 12:
            # Full row with outer columns
            for half_i, (c_start, c_end) in enumerate(col_ranges):
                if row_i == 3 and half_i == 1 and n == 14:
                    inner[f"row{row_i}_half{half_i}"] = full[8:13]
                else:
                    inner[f"row{row_i}_half{half_i}"] = full[c_start:c_end + 1]
        else:
            # Unknown format, pad with NONE
            for half_i in range(2):
                inner[f"row{row_i}_half{half_i}"] = ["NONE"] * 5

    # Extract inner thumbs
    full_thumbs = _get_full_thumbs(thumbs)
    n_thumbs = len(full_thumbs)
    if n_thumbs == 6:
        # Library format: 3+3 inner only
        for half_i in range(2):
            start = half_i * 3
            inner[f"thumbs_half{half_i}"] = full_thumbs[start:start + 3]
    else:
        # Full format: outer + 3+3 inner + outer
        for half_i, (t_start, t_end) in enumerate(thumb_ranges):
            inner[f"thumbs_half{half_i}"] = full_thumbs[t_start:t_end + 1]

    return inner


def _build_layer_context(physical: dict, layer: dict, name: str) -> dict:
    """Build template context for a single layer."""
    inner_cfg = physical["miryoku_inner"]
    col_ranges = inner_cfg["col_ranges"]
    thumb_ranges = inner_cfg["thumb_ranges"]
    outer_thumb = inner_cfg.get("outer_thumb_cols", [0, 7])
    row_start, row_end = inner_cfg["row_range"]

    rows = layer.get("rows", {})
    thumbs_str = layer.get("thumbs", "")

    ctx = {"name": name}
    full_thumbs = _get_full_thumbs(thumbs_str)

    # Row 0: fully hardcoded (no K params)
    row0 = _get_full_row(rows, 0)
    n0 = len(row0)
    mid = n0 // 2
    ctx["row0_left"] = " ".join(resolve_key(k, "zmk") for k in row0[:mid])
    ctx["row0_right"] = " ".join(resolve_key(k, "zmk") for k in row0[mid:])

    # Rows 1-3: outer cols hardcoded, inner cols passed as K params
    for row_i in range(row_start, row_end + 1):
        full = _get_full_row(rows, row_i)
        if row_i < 3:
            # Rows 1-2: 12 positions, col 0 and 11 are outer
            ctx[f"r{row_i}_l"] = resolve_key(full[0], "zmk")
            ctx[f"r{row_i}_r"] = resolve_key(full[11], "zmk")
        else:
            # Row 3: 14 positions
            # 0=outer-left, 1-5=K20-K24, 6=inner-extra-L, 7=inner-extra-R, 8-12=K25-K29, 13=outer-right
            ctx[f"r{row_i}_l"] = resolve_key(full[0], "zmk")
            ctx[f"r{row_i}_r"] = resolve_key(full[13], "zmk") if len(full) > 13 else "&none"
            ctx["lie_k"] = resolve_key(full[6], "zmk") if len(full) > 6 else "&none"
            ctx["rie_k"] = resolve_key(full[7], "zmk") if len(full) > 7 else "&none"

    # Thumbs: outer hardcoded, inner passed as K params
    ctx["th_l"] = resolve_key(full_thumbs[outer_thumb[0]], "zmk") if len(full_thumbs) > outer_thumb[0] else "&none"
    ctx["th_r"] = resolve_key(full_thumbs[outer_thumb[1]], "zmk") if len(full_thumbs) > outer_thumb[1] else "&none"

    return ctx


def generate(config: dict, output_dir: str) -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), trim_blocks=True, lstrip_blocks=True)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    physical = config["physical"]
    layers = config["layers"]
    behaviors = config.get("behaviors", {"tap_term_ms": 200, "quick_tap_ms": 0})

    # ── layer contexts for keymap template ──────────────────────────
    layer_ctxs = []
    for name, layer in layers.items():
        layer_ctxs.append(_build_layer_context(physical, layer, name))

    # ── library layer defines for custom_config.h ────────────────────
    library_layers = []
    col_ranges = physical["miryoku_inner"]["col_ranges"]
    thumb_ranges = physical["miryoku_inner"]["thumb_ranges"]

    for name, layer in layers.items():
        if not layer.get("_source", "").startswith("import:"):
            continue
        inner = _extract_inner(physical, layer)
        lib = {"name": name.upper()}
        row_start, row_end = physical["miryoku_inner"]["row_range"]
        for row_i in range(row_start, row_end + 1):
            for half_i in range(2):
                keys = inner.get(f"row{row_i}_half{half_i}", [])
                lib[f"row{row_i}_h{half_i}"] = [resolve_key(k, "zmk") for k in keys]
        for half_i in range(2):
            keys = inner.get(f"thumbs_half{half_i}", [])
            lib[f"thumb_h{half_i}"] = [resolve_key(k, "zmk") for k in keys]
        library_layers.append(lib)

    ctx = {
        "layers": layer_ctxs,
        "library_layers": library_layers,
        "behaviors": behaviors,
        "flip": config.get("meta", {}).get("flavor") == "flip",
    }

    # ── render templates ────────────────────────────────────────────
    (out / "lily58.keymap").write_text(env.get_template("keymap.j2").render(ctx))
    (out / "custom_config.h").write_text(env.get_template("custom_config.j2").render(ctx))
    (out / "custom.conf").write_text(env.get_template("custom.conf.j2").render(ctx))

    # ── HTML viewer ─────────────────────────────────────────────────
    html = _generate_html(config)
    (out / "layout.html").write_text(html)

    print(f"Generated → {out}/")
    for f in sorted(out.iterdir()):
        print(f"  {f.name}")


def _generate_html(config: dict) -> str:
    """Generate a standalone HTML layer viewer."""
    # Build a JSON representation of all layers with resolved display labels
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
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{config['meta']['name']} - Layer Viewer</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; }}
h1 {{ font-size: 1.2em; margin-bottom: 16px; color: #a0a0c0; }}
.tabs {{ display: flex; gap: 4px; margin-bottom: 20px; flex-wrap: wrap; }}
.tab {{ padding: 6px 14px; border: 1px solid #333; border-radius: 6px; cursor: pointer; font-size: 0.85em; background: #16213e; color: #888; transition: all 0.15s; }}
.tab:hover {{ background: #1a1a3e; color: #ccc; }}
.tab.active {{ background: #0f3460; color: #e0e0e0; border-color: #533483; }}
.keyboard {{ display: inline-block; }}
.row {{ display: flex; gap: 3px; margin-bottom: 3px; }}
.key {{ width: 52px; height: 48px; border: 1px solid #2a2a4a; border-radius: 5px; display: flex; align-items: center; justify-content: center; font-size: 0.72em; background: #16213e; color: #ccc; text-align: center; line-height: 1.2; word-break: break-all; padding: 2px; }}
.key.empty {{ background: #111; border-color: #1a1a2e; color: #333; }}
.key.thumb {{ background: #1a1a3e; }}
.key.outer {{ background: #1e1e3a; }}
.key.mod {{ color: #7eb8da; }}
.key.layer {{ color: #e2a76f; }}
.key.sym {{ color: #a0d0a0; }}
.key.nav {{ color: #d0a0d0; }}
.gap {{ width: 20px; }}
.legend {{ margin-top: 20px; font-size: 0.75em; color: #666; display: flex; gap: 16px; }}
.legend span {{ display: flex; align-items: center; gap: 4px; }}
.legend .dot {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
</style>
</head>
<body>
<h1>{config['meta']['name']}</h1>
<div class="tabs" id="tabs"></div>
<div id="keyboard"></div>
<div class="legend">
  <span><span class="dot" style="background:#7eb8da"></span> modifiers</span>
  <span><span class="dot" style="background:#e2a76f"></span> layers</span>
  <span><span class="dot" style="background:#a0d0a0"></span> symbols</span>
  <span><span class="dot" style="background:#d0a0d0"></span> navigation</span>
</div>
<script>
const DATA = {data_json};
const LAYERS = Object.keys(DATA);
let current = LAYERS[0];

function classForKey(k) {{
  const u = (k||'').toUpperCase();
  if (!u || u === 'NONE') return 'empty';
  if (u.startsWith('MT(') || u === 'LCTL' || u === 'LALT' || u === 'LSFT' || u === 'LGUI' || u === 'RCTL' || u === 'RALT' || u === 'RSFT' || u === 'RGUI') return 'key mod';
  if (u.startsWith('LT(') || u.startsWith('TO(') || u.startsWith('MO(') || u.startsWith('TOG(')) return 'key layer';
  if ('LBRC RBRC LPAR RPAR LBKT RBKT AMPS ASTRK AT HASH DLLR PRCNT CARET COLON SEMI COMMA DOT SLASH SQT GRAVE TILDE UNDER PIPE PLUS EQUAL BSLH EXCL'.includes(u)) return 'key sym';
  if ('UP DOWN LEFT RIGHT HOME END PGUP PGDN INS DEL BSPC TAB RET ENT ESC SPC'.includes(u)) return 'key nav';
  return '';
}}

function renderLayer(name) {{
  const layer = DATA[name];
  const rows = layer.rows;
  const thumbs = layer.thumbs;
  let html = '<div class="keyboard">';

  // Row 0
  if (rows['0']) {{
    html += '<div class="row">';
    rows['0'].forEach((k, i) => {{
      const cls = i < 6 ? 'outer' : (i > 5 && i < 11 ? '' : 'outer');
      html += `<div class="key ${{cls}} ${{classForKey(k)}}">${{k === 'NONE' ? '' : k}}</div>`;
      if (i === 5) html += '<div class="gap"></div>';
    }});
    html += '</div>';
  }}

  // Rows 1-3
  for (let r = 1; r <= 3; r++) {{
    if (!rows[String(r)]) continue;
    html += '<div class="row">';
    rows[String(r)].forEach((k, i) => {{
      const cls = i === 0 || i === 11 ? 'outer' : '';
      html += `<div class="key ${{cls}} ${{classForKey(k)}}">${{k === 'NONE' ? '' : k}}</div>`;
      if (i === 5) html += '<div class="gap"></div>';
    }});
    html += '</div>';
  }}

  // Thumb row
  if (thumbs.length) {{
    html += '<div class="row">';
    thumbs.forEach((k, i) => {{
      html += `<div class="key thumb ${{classForKey(k)}}">${{k === 'NONE' ? '' : k}}</div>`;
      if (i === 3) html += '<div class="gap"></div>';
    }});
    html += '</div>';
  }}

  html += '</div>';
  document.getElementById('keyboard').innerHTML = html;
}}

function buildUI() {{
  const tabs = document.getElementById('tabs');
  LAYERS.forEach(name => {{
    const btn = document.createElement('div');
    btn.className = 'tab' + (name === current ? ' active' : '');
    btn.textContent = DATA[name].display || name;
    btn.onclick = () => {{
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      current = name;
      renderLayer(name);
    }};
    tabs.appendChild(btn);
  }});
  renderLayer(current);
}}

buildUI();
</script>
</body>
</html>"""


if __name__ == "__main__":
    config_path = ROOT / "config.yaml"
    with open(config_path) as f:
        raw_config = yaml.safe_load(f)
    errors = validate(raw_config)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)
    print("Config valid.")

    config = load_config()
    generate(config, sys.argv[1] if len(sys.argv) > 1 else "output")
