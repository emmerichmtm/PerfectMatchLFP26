"""Add the staff files, templates and third-party notices to the PyInstaller output folder."""
from importlib import metadata
from pathlib import Path
import shutil
import sys

import scoring

ROOT = Path(__file__).resolve().parent
SHIPPED = ("PuLP", "pyinstaller")  # PuLP with its CBC solver; PyInstaller's bootloader starts the EXE


def add_files(package: Path):
    for name in ("START HERE.txt", "manual.pdf"):
        shutil.copy2(ROOT / name, package / name)
    templates = package / "templates"
    templates.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "examples" / "survey_example.csv", templates / "survey_example.csv")
    (templates / "settings.csv").write_text(scoring.settings_to_csv(scoring.default_settings()), encoding="utf-8-sig")


def add_notices(package: Path):
    destination = package / "Third-party notices"
    destination.mkdir(exist_ok=True)
    versions = []
    for name in SHIPPED:
        dist = metadata.distribution(name)
        versions.append(f"{dist.metadata['Name']} {dist.version}")
        for entry in dist.files or []:
            if any(word in entry.name.lower() for word in ("license", "copying", "notice")):
                source = Path(dist.locate_file(entry))
                if source.is_file():
                    target = destination / name / Path(*[p for p in entry.parts if p not in (".", "..")])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("The Python runtime LICENSE.txt was not found.")
    shutil.copy2(python_license, destination / "Python-LICENSE.txt")
    (destination / "VERSIONS.txt").write_text("Python " + sys.version + "\n" + "\n".join(versions) + "\n", encoding="utf-8")


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    add_files(folder)
    add_notices(folder)
