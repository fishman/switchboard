"""switchboard CLI - YAML in, ZMK/QMK out."""

import shutil
import subprocess
import sys
from pathlib import Path

import typer
import yaml

from switchboard.generate import load_config, generate, ROOT
from switchboard.validate import validate

app = typer.Typer(help="Keyboard firmware config compiler.")


@app.command()
def check():
    """Validate config.yaml."""
    config_path = ROOT / "config.yaml"
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    errors = validate(raw)
    if errors:
        for e in errors:
            typer.echo(f"  ✗ {e}", err=True)
        raise typer.Exit(1)
    typer.echo("  ✓ config.yaml valid")


@app.command()
def gen(
    output: Path = typer.Option("output", "--output", "-o", help="Output directory"),
):
    """Generate ZMK keymap, config, build.yaml, west.yml, and HTML viewer."""
    config_path = ROOT / "config.yaml"
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    errors = validate(raw)
    if errors:
        for e in errors:
            typer.echo(f"  ✗ {e}", err=True)
        raise typer.Exit(1)
    config = load_config()
    generate(config, str(output))


@app.command()
def init_workspace():
    """Initialize a ZMK workspace in output/ for local builds."""
    out = ROOT / "output"
    if not (out / "west.yml").exists():
        typer.echo("Run 'switchboard generate' first.", err=True)
        raise typer.Exit(1)
    subprocess.run(["west", "init", "-l", str(out)], check=True)
    subprocess.run(["west", "update"], cwd=str(out), check=True)
    typer.echo("Workspace ready. cd output && west build -- -DSHIELD=<shield>_left")


@app.command()
def deploy(
    target: Path = typer.Option(None, "--target", "-t", help="Target config directory"),
):
    """Copy generated output into a zmk-config repo's config/ dir."""
    out = ROOT / "output"
    if target is None:
        target = ROOT.parent / "config"
    src = out / "config" / "boards" / "shields"
    if not src.exists():
        typer.echo("Run 'switchboard generate' first.", err=True)
        raise typer.Exit(1)
    dst = target / "boards" / "shields"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    typer.echo(f"  Deployed -> {dst}")


@app.command()
def clean():
    """Remove build and output directories."""
    for d in ["build", "output"]:
        path = ROOT / d
        if path.exists():
            shutil.rmtree(path)
    typer.echo("  Cleaned build/ and output/")


if __name__ == "__main__":
    app()
