"""Validate config.yaml and report errors."""

import sys
from switchboard.validate import validate
from switchboard.generate import load_config


def main():
    import yaml
    from pathlib import Path
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    errors = validate(config)
    if errors:
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        sys.exit(1)
    print("  ✓ config.yaml valid")


if __name__ == "__main__":
    main()
