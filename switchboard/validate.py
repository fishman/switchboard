"""Validate config.yaml against schema rules."""

from switchboard import parse_row


def validate(config: dict) -> list[str]:
    errors = []

    if "layers" not in config:
        errors.append("missing 'layers' key")
        return errors

    layers = config["layers"]
    if not isinstance(layers, dict):
        errors.append("'layers' must be a dict")
        return errors

    for name, layer in layers.items():
        errors.extend(_validate_layer(name, layer, config))

    return errors


def _validate_layer(name: str, layer: dict, config: dict) -> list[str]:
    errors = []

    valid_keys = {"display", "alpha", "import", "rows", "thumbs"}
    for k in layer:
        if k not in valid_keys:
            errors.append(f"layer '{name}': unknown key '{k}'")

    rows = layer.get("rows", {})
    if not isinstance(rows, dict):
        errors.append(f"layer '{name}': 'rows' must be a dict")
    else:
        row_cols = config.get("physical", {}).get("row_cols", {0: 12, 1: 12, 2: 12, 3: 12})
        for rk in (0, 1, 2, 3):
            if rk not in rows:
                errors.append(f"layer '{name}': rows missing row {rk}")
            else:
                parsed = parse_row(str(rows[rk]), sep="|")
                expected = row_cols.get(rk, 12)
                if len(parsed) != expected:
                    errors.append(f"layer '{name}': row {rk} has {len(parsed)} keys, expected {expected}")

    # thumbs is a | -separated string of 8 values
    # Skip check for layers with import: (thumbs come from library)
    if not layer.get("import"):
        thumbs = layer.get("thumbs", "")
        if isinstance(thumbs, str):
            parsed = parse_row(thumbs, sep="|")
            exp_thumbs = config.get("physical", {}).get("thumbs", 8)
            if len(parsed) != exp_thumbs:
                errors.append(f"layer '{name}': thumbs has {len(parsed)} keys, expected {exp_thumbs}")
        elif isinstance(thumbs, dict):
            errors.append(f"layer '{name}': 'thumbs' must be a string, got dict")

    # alpha must reference a valid preset
    alpha_name = layer.get("alpha")
    if alpha_name:
        presets = config.get("alpha_presets", {})
        if presets and alpha_name not in presets:
            errors.append(f"layer '{name}': alpha preset '{alpha_name}' not found")

    return errors
