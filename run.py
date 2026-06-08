from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


PROJECT_DIR = Path(__file__).resolve().parent
ENV_DIR = PROJECT_DIR / ".conda_envs" / "mujoco-maze"
ENV_FILE = PROJECT_DIR / "environment.yml"
APP_SCRIPT = PROJECT_DIR / "maze_generator_gui.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up and run the MuJoCo maze GUI.")
    parser.add_argument("--setup-only", action="store_true", help="Create/check the conda environment and exit.")
    args, app_args = parser.parse_known_args()

    env_python = _env_python()
    if not env_python.exists():
        _create_env()

    if args.setup_only:
        print(f"Environment ready: {ENV_DIR}")
        return 0

    if not env_python.exists():
        print(f"Environment Python not found after setup: {env_python}", file=sys.stderr)
        return 1

    command = [str(env_python), str(APP_SCRIPT), *app_args]
    return subprocess.call(command, cwd=PROJECT_DIR)


def _env_python() -> Path:
    if os.name == "nt":
        return ENV_DIR / "python.exe"
    return ENV_DIR / "bin" / "python"


def _create_env() -> None:
    if not ENV_FILE.exists():
        raise FileNotFoundError(f"Missing environment file: {ENV_FILE}")

    conda = _find_conda()
    if conda is None:
        print(
            "Conda was not found. Install Miniconda/Anaconda, then run this again.",
            file=sys.stderr,
        )
        print("Environment file:", ENV_FILE, file=sys.stderr)
        raise SystemExit(1)

    ENV_DIR.parent.mkdir(parents=True, exist_ok=True)
    command = [str(conda), "env", "create", "-p", str(ENV_DIR), "-f", str(ENV_FILE)]
    print("Creating conda environment:")
    print(" ".join(command))
    result = _run_command(command)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _find_conda() -> Path | None:
    env_conda = os.environ.get("CONDA_EXE")
    candidates = []
    if env_conda:
        candidates.append(Path(env_conda))

    found = shutil.which("conda")
    if found:
        candidates.append(Path(found))

    home = Path.home()
    if os.name == "nt":
        candidates.extend(
            [
                home / "miniconda3" / "Scripts" / "conda.exe",
                home / "anaconda3" / "Scripts" / "conda.exe",
                home / "miniforge3" / "Scripts" / "conda.exe",
                Path("C:/ProgramData/miniconda3/Scripts/conda.exe"),
                Path("C:/ProgramData/Anaconda3/Scripts/conda.exe"),
            ]
        )
    else:
        candidates.extend(
            [
                home / "miniconda3" / "bin" / "conda",
                home / "anaconda3" / "bin" / "conda",
                home / "miniforge3" / "bin" / "conda",
                Path("/opt/anaconda3/bin/conda"),
                Path("/opt/miniconda3/bin/conda"),
            ]
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def _run_command(command: list[str]) -> subprocess.CompletedProcess:
    executable = command[0].lower()
    if os.name == "nt" and executable.endswith((".bat", ".cmd")):
        return subprocess.run(subprocess.list2cmdline(command), cwd=PROJECT_DIR, shell=True)
    return subprocess.run(command, cwd=PROJECT_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
