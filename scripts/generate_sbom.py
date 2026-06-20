from __future__ import annotations

import json
import platform
import sys
from importlib import metadata
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--version", default=None)
    args = parser.parse_args()

    sys.path.insert(0, str(Path("src").resolve()))
    from employeurd_megagest.version import __version__

    if args.version and args.version != __version__:
        raise SystemExit(f"La version de mise en ligne {args.version} ne correspond pas à la version de l'application {__version__}.")

    output = Path("dist") / f"EmployeurD-MegaGest-v{__version__}.sbom.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    components = [
        {
            "type": "framework",
            "name": "Python",
            "version": platform.python_version(),
        }
    ]
    for package_name in ("cx_Freeze", "freeze-core", "lief", "filelock", "cabarchive", "striprtf"):
        try:
            package_version = metadata.version(package_name)
        except metadata.PackageNotFoundError:
            continue
        components.append({"type": "library", "name": package_name, "version": package_version})

    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": [{"vendor": "local", "name": "scripts/generate_sbom.py"}],
            "component": {
                "type": "application",
                "name": "EmployeurD-MegaGest",
                "version": __version__,
            },
        },
        "components": components,
    }
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
