"""Load keycodes.yaml and provide resolve() for mapping key names → firmware keycodes."""

from pathlib import Path
import yaml

_KEYCODES_PATH = Path(__file__).parent.parent / "keycodes.yaml"

with open(_KEYCODES_PATH) as f:
    _data = yaml.safe_load(f)

# Build flat lookup: key_name → {zmk: "...", qmk: "..."}
_lookup: dict[str, dict[str, str]] = {}
for _category in ["basic", "modifiers", "f_keys", "navigation", "letters",
                   "numbers", "symbols", "media", "system"]:
    for name, mappings in _data.get(_category, {}).items():
        _lookup[name.upper()] = mappings

# Behavior templates
_behaviors = _data.get("behaviors", {})


def resolve(token: str | None, firmware: str = "zmk") -> str:
    """Resolve a key name or behavior token to a firmware keycode string.

    Simple keys:  "ESC" → "&kp ESC" (zmk) or "KC_ESC" (qmk)
    Behaviors:    "MT(LCTL,A)" → "U_MT(LCTRL, A)" or "MT(MOD_LCTL, KC_A)"
    """
    if token is None:
        return _lookup.get("NONE", {}).get(firmware, "&none")

    t = str(token).strip()
    if not t or t.upper() in ("NONE", "TRANS"):
        return _lookup.get("NONE", {}).get(firmware, "&none")

    # behavior token: MT(LCTL,A), LT(SYM,DEL), MO(NAV), etc.
    if "(" in t and t.endswith(")"):
        return _resolve_behavior(t, firmware)

    # simple key lookup
    upper = t.upper()
    if upper in _lookup:
        return _lookup[upper].get(firmware, t)

    # single lowercase letter
    if len(t) == 1 and t.isalpha():
        return _lookup.get(t.upper(), {}).get(firmware, t)

    return t


def _resolve_behavior(token: str, firmware: str) -> str:
    name, rest = token.split("(", 1)
    name = name.strip().upper()
    args = [a.strip() for a in rest.rstrip(")").split(",")]

    bt = _behaviors.get(name)
    if not bt:
        return token

    if firmware == "zmk":
        return _resolve_behavior_zmk(name, args, bt)
    elif firmware == "qmk":
        return _resolve_behavior_qmk(name, args, bt)
    return token


def _resolve_behavior_zmk(name: str, args: list, bt: dict) -> str:
    tmpl = bt.get("zmk_template", "")
    if not tmpl:
        return str(args)

    if name == "MT":
        mod = args[0].upper()
        mod = bt.get("zmk_mod_map", {}).get(mod, mod)
        key = args[1].upper()
        key_code = _lookup.get(key, {}).get("zmk", f"&kp {key}")
        key_name = key_code.replace("&kp ", "") if key_code.startswith("&kp ") else key
        return f"U_MT({mod}, {key_name})"

    elif name == "LT":
        layer = args[0].upper()
        key = args[1].upper()
        key_code = _lookup.get(key, {}).get("zmk", f"&kp {key}")
        key_name = key_code.replace("&kp ", "") if key_code.startswith("&kp ") else key
        return f"U_LT(U_{layer}, {key_name})"

    elif name in ("MO", "TO", "TOG"):
        return tmpl.format(layer=args[0].upper())

    return tmpl


def _resolve_behavior_qmk(name: str, args: list, bt: dict) -> str:
    tmpl = bt.get("qmk_template", "")
    if not tmpl:
        return str(args)

    if name == "MT":
        mod = args[0].upper()
        key = args[1].upper()
        key_code = _lookup.get(key, {}).get("qmk", f"KC_{key}")
        mod_map = {"LCTL": "MOD_LCTL", "LALT": "MOD_LALT", "LSFT": "MOD_LSFT",
                   "LGUI": "MOD_LGUI", "RCTL": "MOD_RCTL", "RALT": "MOD_RALT",
                   "RSFT": "MOD_RSFT", "RGUI": "MOD_RGUI"}
        mod = mod_map.get(mod, mod)
        return f"MT({mod}, {key_code})"

    elif name == "LT":
        layer = args[0].upper()
        key = args[1].upper()
        key_code = _lookup.get(key, {}).get("qmk", f"KC_{key}")
        return f"LT({layer}, {key_code})"

    elif name in ("MO", "TO", "TOG"):
        return tmpl.format(layer=args[0].upper())

    return tmpl


def get_lookup() -> dict:
    """Return the full lookup dict (for schema validation or debugging)."""
    return _lookup


def get_behaviors() -> dict:
    """Return the behavior template dict."""
    return _behaviors


def parse_row(row_str: str, sep: str = ",") -> list[str]:
    """Parse a separated key string into a list, stripping whitespace."""
    return [k.strip() for k in str(row_str).split(sep)]
