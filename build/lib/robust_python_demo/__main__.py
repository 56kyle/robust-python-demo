"""Command-line interface."""

import typer


app: typer.Typer = typer.Typer()


@app.command(name="robust-python-demo")
def main() -> None:
    """Robust Python Demo."""


if __name__ == "__main__":
    app()  # pragma: no cover
