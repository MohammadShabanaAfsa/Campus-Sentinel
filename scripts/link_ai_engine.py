"""Create ignored Python import aliases without replacing existing files."""
import os
from pathlib import Path
import subprocess


def link_source(root, source_name, alias_name):
    source = root / source_name
    alias = root / "backend" / alias_name
    if not source.is_dir():
        raise SystemExit(f"Canonical {source_name} source directory is missing.")
    if os.path.lexists(alias):
        if alias.resolve() == source.resolve():
            print(f"{alias_name} import alias already points to canonical source.")
            return
        raise SystemExit(f"backend/{alias_name} already exists; left untouched. Review it manually.")
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(source)],
            check=True, capture_output=True,
        )
    else:
        alias.symlink_to(Path("..") / source_name, target_is_directory=True)
    print(f"Created local {alias_name} import alias; no source files copied or removed.")


def main():
    root = Path(__file__).resolve().parents[1]
    link_source(root, "ai-engine", "ai_engine")
    link_source(root, "agents", "agents")


if __name__ == "__main__":
    main()
