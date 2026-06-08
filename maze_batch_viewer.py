from __future__ import annotations

import argparse
import os
import platform
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from xml.etree import ElementTree


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
LOCAL_MJPYTHON = SCRIPT_DIR / ".conda_envs" / "mujoco-maze" / "bin" / "mjpython"
GRID_TILE_WIDTH = 880
GRID_TILE_HEIGHT = 560
GRID_TILE_MARGIN = 12
GRID_TOP_OFFSET = 48
GRID_BOTTOM_OFFSET = 80
TOP_VIEW_DISTANCE_SCALE = 1.45


class BatchViewerApp:
    def __init__(self, root: tk.Misc, set_window_title: bool = True) -> None:
        self.root = root
        if set_window_title and hasattr(self.root, "title"):
            self.root.title("MuJoCo Maze Batch Viewer")

        self.folder_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Choose a folder that contains generated XML files.")
        self.xml_files: list[Path] = []
        self.viewer_processes: list[subprocess.Popen] = []
        self.grid_windows: list[GridRenderWindow] = []
        self.last_arrange_error = ""

        self._build_layout()
        self._load_latest_output_folder()

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        folder_row = ttk.Frame(outer)
        folder_row.grid(row=0, column=0, sticky="ew")
        folder_row.columnconfigure(0, weight=1)

        self.folder_entry = ttk.Entry(folder_row, textvariable=self.folder_var, state="readonly")
        self.folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(folder_row, text="Choose Folder", command=self.choose_folder).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(folder_row, text="Refresh", command=self.refresh_current_folder).grid(row=0, column=2)

        list_frame = ttk.Frame(outer)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(list_frame, height=14, activestyle="dotbox")
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<Double-Button-1>", lambda _event: self.view_selected())

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)

        button_row = ttk.Frame(outer)
        button_row.grid(row=2, column=0, sticky="ew")
        ttk.Button(button_row, text="View Selected", command=self.view_selected).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_row, text="View All", command=self.view_all).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_row, text="Stop Viewer", command=self.stop_viewer).grid(row=0, column=2)

        ttk.Label(outer, textvariable=self.status_var).grid(row=3, column=0, sticky="w", pady=(10, 0))

    def choose_folder(self) -> None:
        initial_dir = DEFAULT_OUTPUT_DIR if DEFAULT_OUTPUT_DIR.exists() else SCRIPT_DIR
        selected = filedialog.askdirectory(
            parent=self.root,
            title="Select a generated maze XML folder",
            initialdir=str(initial_dir),
        )
        if not selected:
            return
        self.load_folder(Path(selected))

    def refresh_current_folder(self) -> None:
        folder_text = self.folder_var.get()
        if not folder_text:
            self.choose_folder()
            return
        self.load_folder(Path(folder_text))

    def load_folder(self, folder: Path) -> None:
        try:
            xml_files = find_xml_files(folder)
        except Exception as exc:
            messagebox.showerror("Folder error", str(exc), parent=self.root)
            return

        self.folder_var.set(str(folder))
        self.xml_files = xml_files
        self.listbox.delete(0, tk.END)

        for xml_file in self.xml_files:
            self.listbox.insert(tk.END, xml_file.name)

        if self.xml_files:
            self.status_var.set(f"Loaded {len(self.xml_files)} XML file(s).")
            self.listbox.selection_set(0)
        else:
            self.status_var.set("No XML files found in the selected folder.")

    def view_selected(self) -> None:
        if not self.xml_files:
            messagebox.showerror("No XML files", "Choose a folder with XML files first.", parent=self.root)
            return

        selected_indexes = self.listbox.curselection()
        if not selected_indexes:
            messagebox.showerror("No selection", "Select one XML file from the list.", parent=self.root)
            return

        xml_path = self.xml_files[selected_indexes[0]]
        if self._start_viewer(["--open-files", str(xml_path), "--viewer-index", "1", "--viewer-total", "1"]):
            self.status_var.set(f"Started viewer for {xml_path.name}.")

    def view_all(self) -> None:
        folder_text = self.folder_var.get()
        if not folder_text:
            messagebox.showerror("No folder", "Choose a folder first.", parent=self.root)
            return
        if not self.xml_files:
            messagebox.showerror("No XML files", "The selected folder has no XML files.", parent=self.root)
            return

        try:
            grid_window = GridRenderWindow(self.root, self.xml_files, on_open_xml=self.open_xml_from_grid)
        except Exception as exc:
            messagebox.showerror("Grid viewer failed", str(exc), parent=self.root)
            return

        self.grid_windows.append(grid_window)
        self.status_var.set(f"Opened grid viewer with {len(self.xml_files)} XML file(s).")

    def open_xml_from_grid(self, xml_path: Path, index: int, total: int) -> None:
        process = self._start_viewer(
            [
                "--open-files",
                str(xml_path),
                "--viewer-index",
                str(index),
                "--viewer-total",
                str(total),
            ]
        )
        if process is not None:
            self.status_var.set(f"Started MuJoCo viewer for {xml_path.name}.")

    def stop_viewer(self) -> None:
        running = [process for process in self.viewer_processes if process.poll() is None]
        open_grid_windows = [window for window in self.grid_windows if window.is_open]
        if not running and not open_grid_windows:
            self.viewer_processes = []
            self.grid_windows = []
            self.status_var.set("No viewer process is running.")
            return

        for process in running:
            process.terminate()
        self.viewer_processes = []

        for window in open_grid_windows:
            window.close()
        self.grid_windows = []
        self.status_var.set(
            f"Stopped {len(running)} viewer process(es) and {len(open_grid_windows)} grid window(s)."
        )

    def _start_viewer(self, args: list[str], poll: bool = True) -> subprocess.Popen | None:
        executable = _viewer_executable()
        if executable is None:
            messagebox.showerror(
                "mjpython not found",
                "Could not find mjpython. Activate the mujoco-maze conda environment first.",
                parent=self.root,
            )
            return None

        command = [str(executable), str(Path(__file__).resolve()), *args]
        try:
            process = subprocess.Popen(command, cwd=SCRIPT_DIR)
        except Exception as exc:
            messagebox.showerror("Viewer failed", str(exc), parent=self.root)
            return None

        self.viewer_processes.append(process)
        if poll:
            self.root.after(1000, self._poll_viewers)
        return process

    def _arrange_viewer_grid(
        self,
        targets: list[tuple[subprocess.Popen, str]],
        attempt: int = 1,
    ) -> None:
        running = [(process, title) for process, title in targets if process.poll() is None]
        if not running:
            return

        success, error = arrange_process_windows_grid(
            running,
            screen_width=self.root.winfo_screenwidth(),
            screen_height=self.root.winfo_screenheight(),
        )
        if success:
            self.status_var.set(f"Arranged {len(running)} viewer window(s) in a grid.")
            return

        if attempt < 5:
            self.root.after(900, lambda: self._arrange_viewer_grid(targets, attempt + 1))
            return

        self.last_arrange_error = error
        detail = f" {self.last_arrange_error}" if self.last_arrange_error else ""
        self.status_var.set(f"Started {len(running)} viewer window(s), but grid arrange failed.{detail}")

    def _poll_viewers(self) -> None:
        self.viewer_processes = [process for process in self.viewer_processes if process.poll() is None]
        running = len(self.viewer_processes)

        if running:
            self.status_var.set(f"{running} viewer process(es) running.")
            self.root.after(1000, self._poll_viewers)
            return

        self.status_var.set("All viewer processes finished.")

    def _load_latest_output_folder(self) -> None:
        if not DEFAULT_OUTPUT_DIR.exists():
            return

        candidates = [path for path in DEFAULT_OUTPUT_DIR.iterdir() if path.is_dir()]
        if not candidates:
            return

        latest = max(candidates, key=lambda path: path.stat().st_mtime)
        self.load_folder(latest)


class GridRenderWindow:
    def __init__(self, parent: tk.Misc, xml_files: list[Path], on_open_xml=None) -> None:
        if not xml_files:
            raise ValueError("No XML files were provided.")

        import mujoco

        self.parent = parent
        self.mujoco = mujoco
        self.xml_files = xml_files
        self.on_open_xml = on_open_xml
        self.is_open = True
        self.items: list[dict] = []

        self.cols = math.ceil(math.sqrt(len(xml_files)))
        self.rows = math.ceil(len(xml_files) / self.cols)
        self.tile_width, self.tile_height = self._tile_size()

        self.window = tk.Toplevel(parent)
        self.window.title("MuJoCo Maze Grid Viewer")
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        content = ttk.Frame(self.window, padding=GRID_TILE_MARGIN)
        content.grid(row=0, column=0, sticky="nsew")
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)

        for row in range(self.rows):
            content.rowconfigure(row, weight=1, uniform="maze_grid_rows")
        for col in range(self.cols):
            content.columnconfigure(col, weight=1, uniform="maze_grid_cols")

        for index, xml_file in enumerate(xml_files, start=1):
            row = (index - 1) // self.cols
            col = (index - 1) % self.cols
            canvas = tk.Canvas(
                content,
                width=self.tile_width,
                height=self.tile_height,
                bg="#0f172a",
                cursor="hand2",
                highlightthickness=1,
                highlightbackground="#334155",
            )
            canvas.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            canvas.bind(
                "<Button-1>",
                lambda _event, path=xml_file, tile_index=index: self._open_tile(path, tile_index),
            )

            model = mujoco.MjModel.from_xml_path(str(xml_file))
            data = mujoco.MjData(model)
            renderer = mujoco.Renderer(model, height=self.tile_height, width=self.tile_width)
            camera = self._camera_for(model)
            image_item = canvas.create_image(0, 0, anchor="nw")
            label_rect = canvas.create_rectangle(8, 8, 140, 34, fill="#111827", outline="")
            label_text = canvas.create_text(
                14,
                21,
                anchor="w",
                text=f"{index} / {len(xml_files)}   {xml_file.name}",
                fill="#f8fafc",
                font=("TkDefaultFont", 12, "bold"),
            )

            self.items.append(
                {
                    "canvas": canvas,
                    "model": model,
                    "data": data,
                    "renderer": renderer,
                    "camera": camera,
                    "image_item": image_item,
                    "photo": None,
                    "label_rect": label_rect,
                    "label_text": label_text,
                }
            )

        window_width = self.cols * (self.tile_width + 8) + GRID_TILE_MARGIN * 2
        window_height = self.rows * (self.tile_height + 8) + GRID_TILE_MARGIN * 2
        self.window.geometry(f"{window_width}x{window_height}+20+48")
        self._render_once()

    def _open_tile(self, xml_path: Path, index: int) -> None:
        if self.on_open_xml is not None:
            self.on_open_xml(xml_path, index, len(self.xml_files))

    def close(self) -> None:
        if not self.is_open:
            return

        self.is_open = False
        for item in self.items:
            item["renderer"].close()
        self.items = []
        self.window.destroy()

    def _render_once(self) -> None:
        if not self.is_open:
            return

        mujoco = self.mujoco
        for item in self.items:
            model = item["model"]
            data = item["data"]
            renderer = item["renderer"]
            camera = item["camera"]
            canvas = item["canvas"]

            mujoco.mj_forward(model, data)
            renderer.update_scene(data, camera=camera)
            image = renderer.render()
            photo = _photo_image_from_rgb(image)
            canvas.itemconfigure(item["image_item"], image=photo)
            item["photo"] = photo
            canvas.tag_raise(item["label_rect"])
            canvas.tag_raise(item["label_text"])

    def _tile_size(self) -> tuple[int, int]:
        screen_width = self.parent.winfo_screenwidth()
        screen_height = self.parent.winfo_screenheight()
        max_width = max(360, screen_width - 80)
        max_height = max(280, screen_height - 140)
        tile_width = min(720, max(280, (max_width - self.cols * 8 - GRID_TILE_MARGIN * 2) // self.cols))
        tile_height = min(460, max(220, (max_height - self.rows * 8 - GRID_TILE_MARGIN * 2) // self.rows))
        return tile_width, tile_height

    def _camera_for(self, model):
        mujoco = self.mujoco
        camera = mujoco.MjvCamera()
        camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        camera.distance = max(8.0, model.stat.extent * TOP_VIEW_DISTANCE_SCALE)
        camera.azimuth = 90.0
        camera.elevation = -90.0
        camera.orthographic = True
        camera.lookat[:] = model.stat.center
        return camera


def find_xml_files(folder: Path) -> list[Path]:
    if not folder.exists():
        raise FileNotFoundError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a folder: {folder}")

    return sorted(folder.glob("*.xml"), key=_xml_sort_key)


def _photo_image_from_rgb(image) -> tk.PhotoImage:
    height, width = image.shape[:2]
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    return tk.PhotoImage(data=header + image.tobytes(), format="PPM")


def view_xml_file(xml_path: Path, index: int, total: int) -> None:
    import mujoco
    import mujoco.viewer

    print(f"[{index}/{total}] Opening {xml_path}", flush=True)
    model = mujoco.MjModel.from_xml_path(str(xml_path))
    data = mujoco.MjData(model)

    with mujoco.viewer.launch_passive(model, data, show_left_ui=False, show_right_ui=False) as viewer:
        _configure_camera(viewer, model, mujoco)
        viewer.set_texts(
            (
                mujoco.mjtFontScale.mjFONTSCALE_150,
                mujoco.mjtGridPos.mjGRID_TOPLEFT,
                f"{index} / {total}",
                xml_path.name,
            )
        )

        while viewer.is_running():
            step_start = time.time()
            mujoco.mj_step(model, data)
            viewer.sync()

            elapsed = time.time() - step_start
            if elapsed < model.opt.timestep:
                time.sleep(model.opt.timestep - elapsed)


def view_files(xml_files: list[Path]) -> None:
    if not xml_files:
        raise FileNotFoundError("No XML files were provided.")

    for index, xml_path in enumerate(xml_files, start=1):
        view_xml_file(xml_path, index, len(xml_files))


def view_folder(folder: Path) -> None:
    xml_files = find_xml_files(folder)
    if not xml_files:
        raise FileNotFoundError(f"No XML files found in: {folder}")

    print(f"Found {len(xml_files)} XML file(s) in {folder}", flush=True)
    print("Opening XML files in order.", flush=True)
    view_files(xml_files)


def spawn_viewer_processes(
    xml_files: list[Path],
    wait: bool = False,
    arrange: bool = True,
) -> list[subprocess.Popen]:
    if not xml_files:
        raise FileNotFoundError("No XML files were provided.")

    executable = _viewer_executable()
    if executable is None:
        raise RuntimeError("Could not find mjpython. Activate the mujoco-maze conda environment first.")

    total = len(xml_files)
    processes = []
    for index, xml_file in enumerate(xml_files, start=1):
        processes.append(
            subprocess.Popen(
                [
                    str(executable),
                    str(Path(__file__).resolve()),
                    "--open-files",
                    str(xml_file),
                    "--viewer-index",
                    str(index),
                    "--viewer-total",
                    str(total),
                ],
                cwd=SCRIPT_DIR,
            )
        )

    if arrange:
        time.sleep(1.6)
        for _attempt in range(5):
            success, _error = arrange_process_windows_grid(processes)
            if success:
                break
            time.sleep(0.9)

    if wait:
        for process in processes:
            process.wait()

    return processes


def arrange_process_windows_grid(
    targets: list[subprocess.Popen] | list[tuple[subprocess.Popen, str]],
    screen_width: int | None = None,
    screen_height: int | None = None,
) -> tuple[bool, str]:
    if platform.system() != "Darwin":
        return False, "Window grid arrangement is only implemented on macOS."

    normalized_targets = _normalize_window_targets(targets)
    running = [(process, title) for process, title in normalized_targets if process.poll() is None]
    if not running:
        return False, "No viewer processes are running."

    if screen_width is None or screen_height is None:
        screen_width, screen_height = _macos_screen_size()

    bounds = _grid_bounds(len(running), screen_width, screen_height)
    commands = []
    for (process, title), (left, top, width, height) in zip(running, bounds):
        commands.append(
            textwrap_dedent_applescript(
                f"""
                set targetPid to {process.pid}
                set targetTitle to {_applescript_string(title)}
                set targetX to {left}
                set targetY to {top}
                set targetWidth to {width}
                set targetHeight to {height}
                set targetWindow to missing value

                tell application "System Events"
                  repeat 30 times
                    try
                      set targetProcess to first process whose unix id is targetPid
                      tell targetProcess
                        repeat with appWindow in windows
                          try
                            if targetTitle is "" or (name of appWindow contains targetTitle) then
                              set targetWindow to appWindow
                              exit repeat
                            end if
                          end try
                        end repeat
                        if targetWindow is missing value and targetTitle is "" and exists window 1 then
                          set targetWindow to window 1
                        end if
                      end tell
                    end try

                    if targetWindow is missing value and targetTitle is not "" then
                      repeat with appProcess in processes
                        repeat with appWindow in windows of appProcess
                          try
                            if name of appWindow contains targetTitle then
                              set targetWindow to appWindow
                              exit repeat
                            end if
                          end try
                        end repeat
                        if targetWindow is not missing value then exit repeat
                      end repeat
                    end if

                    if targetWindow is not missing value then exit repeat
                    delay 0.1
                  end repeat

                  if targetWindow is not missing value then
                    set size of targetWindow to {{targetWidth, targetHeight}}
                    delay 0.05
                    set position of targetWindow to {{targetX, targetY}}
                  else
                    error "No window for process " & targetPid & " / " & targetTitle
                  end if
                end tell
                """
            )
        )

    script = "\n".join(commands)
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            check=False,
            text=True,
            timeout=12,
        )
    except Exception as exc:
        return False, str(exc)

    if result.returncode == 0:
        return True, ""

    error = (result.stderr or result.stdout).strip()
    return False, error


def _grid_bounds(count: int, screen_width: int, screen_height: int) -> list[tuple[int, int, int, int]]:
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    usable_width = max(320, screen_width - GRID_TILE_MARGIN * (cols + 1))
    usable_height = max(
        240,
        screen_height
        - GRID_TOP_OFFSET
        - GRID_BOTTOM_OFFSET
        - GRID_TILE_MARGIN * (rows + 1),
    )
    cell_width = min(GRID_TILE_WIDTH, max(320, usable_width // cols))
    cell_height = min(GRID_TILE_HEIGHT, max(240, usable_height // rows))

    bounds: list[tuple[int, int, int, int]] = []
    for index in range(count):
        row = index // cols
        col = index % cols
        left = GRID_TILE_MARGIN + col * (cell_width + GRID_TILE_MARGIN)
        top = GRID_TOP_OFFSET + row * (cell_height + GRID_TILE_MARGIN)
        bounds.append((left, top, cell_width, cell_height))

    return bounds


def _macos_screen_size() -> tuple[int, int]:
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "Finder" to get bounds of window of desktop',
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            parts = [int(part.strip()) for part in result.stdout.strip().split(",")]
            if len(parts) == 4:
                left, top, right, bottom = parts
                return right - left, bottom - top
    except Exception:
        pass

    return 1440, 900


def _normalize_window_targets(
    targets: list[subprocess.Popen] | list[tuple[subprocess.Popen, str]],
) -> list[tuple[subprocess.Popen, str]]:
    normalized = []
    for target in targets:
        if isinstance(target, tuple):
            normalized.append(target)
        else:
            normalized.append((target, ""))
    return normalized


def _viewer_window_title(xml_path: Path) -> str:
    try:
        root = ElementTree.parse(xml_path).getroot()
        model_name = root.attrib.get("model", "").strip()
    except Exception:
        model_name = ""

    if not model_name:
        model_name = xml_path.stem
    return f"MuJoCo : {model_name}"


def _applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def textwrap_dedent_applescript(script: str) -> str:
    return "\n".join(line.strip() for line in script.strip().splitlines())


def _configure_camera(viewer, model, mujoco_module) -> None:
    viewer.cam.type = mujoco_module.mjtCamera.mjCAMERA_FREE
    viewer.cam.distance = max(8.0, model.stat.extent * TOP_VIEW_DISTANCE_SCALE)
    viewer.cam.azimuth = 90.0
    viewer.cam.elevation = -90.0
    viewer.cam.orthographic = True
    viewer.cam.lookat[:] = model.stat.center


def _xml_sort_key(path: Path) -> tuple[int, str]:
    if path.stem.isdigit():
        return int(path.stem), path.name
    return 10**9, path.name


def _viewer_executable() -> Path | None:
    if platform.system() == "Darwin":
        if LOCAL_MJPYTHON.exists():
            return LOCAL_MJPYTHON
        found = shutil.which("mjpython")
        return Path(found) if found else None

    return Path(sys.executable)


def _ensure_mjpython_for_viewer_mode() -> None:
    if platform.system() != "Darwin":
        return
    if os.environ.get("MJPYTHON_BIN"):
        return

    executable = _viewer_executable()
    if executable is None or executable == Path(sys.executable):
        return

    os.execv(str(executable), [str(executable), str(Path(__file__).resolve()), *sys.argv[1:]])


def run_gui() -> None:
    root = tk.Tk()
    app = BatchViewerApp(root)
    root.minsize(720, 480)
    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="View generated MuJoCo maze XML files.")
    parser.add_argument("folder", nargs="?", type=Path, help="Folder containing generated XML files.")
    parser.add_argument("--open-folder", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--open-files", nargs="+", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--viewer-index", type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--viewer-total", type=int, default=1, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.open_folder is not None:
        spawn_viewer_processes(find_xml_files(args.open_folder), wait=True)
        return

    if args.open_files is not None:
        _ensure_mjpython_for_viewer_mode()
        if len(args.open_files) == 1:
            view_xml_file(args.open_files[0], args.viewer_index, args.viewer_total)
        else:
            view_files(args.open_files)
        return

    if args.folder is not None:
        spawn_viewer_processes(find_xml_files(args.folder), wait=True)
        return

    run_gui()


if __name__ == "__main__":
    main()
