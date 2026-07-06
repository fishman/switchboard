# switchboard

YAML in, ZMK/QMK out.

Define your keyboard layers on the full physical grid. Import from a library of reusable presets. Generates a self-contained ZMK keymap, config, and an interactive HTML layer viewer. No Miryoku dependency in the output.

## Quick start

```bash
pdm install
pdm run check      # validate config.yaml
pdm run generate   # write output/
```

Build with ZMK:
```bash
west build -- -DZMK_CONFIG=$(pwd)/output -DSHIELD=lily58_left
```

## Structure

```
switchboard/
  config.yaml          <- your keyboard layout (edit this)
  keycodes.yaml        <- firmware-agnostic key -> ZMK/QMK mappings
  library/
    alphas/            <- reusable alpha presets
    layers/            <- reusable layer definitions
    keyboards/         <- per-keyboard position labels
  templates/           <- Jinja2 output templates
  switchboard/         <- compiler (Python)
```

## Config

Layers define keys for every physical position using `|`-separated rows:

```yaml
layers:
  base:
    alpha: dvorak
    rows:
      0: "ESC | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 0 | BSPC"
      1: "TAB | SQT | COMMA | DOT | P | Y | F | G | C | R | L | LBKT"
    thumbs: "LGUI | LT(FUN,DEL) | LT(NUM,BSPC) | LT(SYM,RET) | LT(MOUSE,TAB) | LT(NAV,SPC) | LT(MEDIA,ESC) | RALT"

  sym:
    import: sym   # from library/layers/sym.yaml
    rows:
      0: "GRAVE | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 | F10 | DEL"
```

Behavior tokens: `MT(LCTL,A)` (mod-tap), `LT(FUN,DEL)` (layer-tap), `TO(BASE)` (toggle layer).

Keys use `|` separator to avoid collision with commas inside behavior tokens.

## Output

- `lily58.keymap` - self-contained ZMK keymap (zero external includes)
- `lily58.conf` - debounce, BLE power
- `layout.html` - standalone interactive layer viewer
