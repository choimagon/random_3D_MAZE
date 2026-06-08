from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from maze_batch_viewer import BatchViewerApp
from maze_generator import Coordinate, write_maze_batch


DEFAULT_WIDTH = 13
DEFAULT_HEIGHT = 13
DEFAULT_COUNT = 4
MAX_VISIBLE_CANVAS_WIDTH = 900
MAX_VISIBLE_CANVAS_HEIGHT = 700


class MazeGeneratorApp:
    def __init__(
        self,
        root: tk.Misc,
        on_generated=None,
        set_window_title: bool = True,
    ) -> None:
        self.root = root
        self.on_generated = on_generated
        if set_window_title and hasattr(self.root, "title"):
            self.root.title("MuJoCo Maze XML Generator")

        self.width_var = tk.StringVar(value=str(DEFAULT_WIDTH))
        self.height_var = tk.StringVar(value=str(DEFAULT_HEIGHT))
        self.count_var = tk.StringVar(value=str(DEFAULT_COUNT))
        self.mode_var = tk.StringVar(value="start")
        self.status_var = tk.StringVar(value="Set a grid size, then create the grid.")

        self.width = DEFAULT_WIDTH
        self.height = DEFAULT_HEIGHT
        self.cell_size = 28
        self.start: Coordinate | None = None
        self.goal: Coordinate | None = None
        self.canvas: tk.Canvas | None = None
        self.grid_frame: ttk.Frame | None = None

        self._build_layout()

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        controls = ttk.Frame(outer)
        controls.grid(row=0, column=0, sticky="ew")

        ttk.Label(controls, text="Width").grid(row=0, column=0, padx=(0, 6), sticky="w")
        ttk.Entry(controls, width=7, textvariable=self.width_var).grid(row=0, column=1, padx=(0, 12))

        ttk.Label(controls, text="Height").grid(row=0, column=2, padx=(0, 6), sticky="w")
        ttk.Entry(controls, width=7, textvariable=self.height_var).grid(row=0, column=3, padx=(0, 12))

        ttk.Label(controls, text="Maps").grid(row=0, column=4, padx=(0, 6), sticky="w")
        ttk.Entry(controls, width=7, textvariable=self.count_var).grid(row=0, column=5, padx=(0, 12))

        ttk.Button(controls, text="Create Grid", command=self.create_grid).grid(row=0, column=6)

        self.status = ttk.Label(outer, textvariable=self.status_var)
        self.status.grid(row=1, column=0, pady=(10, 0), sticky="w")

        self.grid_holder = ttk.Frame(outer)
        self.grid_holder.grid(row=2, column=0, pady=(10, 0), sticky="nsew")
        outer.rowconfigure(2, weight=1)

    def create_grid(self) -> None:
        try:
            width = int(self.width_var.get())
            height = int(self.height_var.get())
            count = int(self.count_var.get())
        except ValueError:
            messagebox.showerror("Invalid input", "Width, height, and map count must be integers.")
            return

        if width < 3 or height < 3:
            messagebox.showerror("Invalid input", "Width and height must be at least 3.")
            return
        if count < 1:
            messagebox.showerror("Invalid input", "Map count must be at least 1.")
            return

        self.width = width
        self.height = height
        self.start = None
        self.goal = None
        self.cell_size = self._choose_cell_size(width, height)

        if self.grid_frame is not None:
            self.grid_frame.destroy()

        self.grid_frame = ttk.Frame(self.grid_holder)
        self.grid_frame.grid(row=0, column=0, sticky="nsew")
        self.grid_holder.columnconfigure(0, weight=1)
        self.grid_holder.rowconfigure(0, weight=1)

        toolbar = ttk.Frame(self.grid_frame)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")

        ttk.Radiobutton(toolbar, text="Start", variable=self.mode_var, value="start").grid(row=0, column=0, padx=(0, 8))
        ttk.Radiobutton(toolbar, text="Goal", variable=self.mode_var, value="goal").grid(row=0, column=1, padx=(0, 16))
        ttk.Button(toolbar, text="Generate XML", command=self.generate_xml).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(toolbar, text="Clear Points", command=self.clear_points).grid(row=0, column=3)

        canvas_width = min(width * self.cell_size, MAX_VISIBLE_CANVAS_WIDTH)
        canvas_height = min(height * self.cell_size, MAX_VISIBLE_CANVAS_HEIGHT)

        self.canvas = tk.Canvas(
            self.grid_frame,
            width=canvas_width,
            height=canvas_height,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#cbd5e1",
            scrollregion=(0, 0, width * self.cell_size, height * self.cell_size),
        )
        self.canvas.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        y_scroll = ttk.Scrollbar(self.grid_frame, orient="vertical", command=self.canvas.yview)
        x_scroll = ttk.Scrollbar(self.grid_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        y_scroll.grid(row=1, column=1, sticky="ns", pady=(8, 0))
        x_scroll.grid(row=2, column=0, sticky="ew")

        self.grid_frame.columnconfigure(0, weight=1)
        self.grid_frame.rowconfigure(1, weight=1)
        self.draw_grid()
        self.update_status()

    def on_canvas_click(self, event: tk.Event) -> None:
        if self.canvas is None:
            return

        col = int(self.canvas.canvasx(event.x) // self.cell_size)
        row = int(self.canvas.canvasy(event.y) // self.cell_size)
        if row < 0 or row >= self.height or col < 0 or col >= self.width:
            return

        point = (row, col)
        if self.mode_var.get() == "start":
            self.start = point
            if self.goal == point:
                self.goal = None
            self.mode_var.set("goal")
        else:
            self.goal = point
            if self.start == point:
                self.start = None
            self.mode_var.set("start")

        self.draw_grid()
        self.update_status()

    def clear_points(self) -> None:
        self.start = None
        self.goal = None
        self.draw_grid()
        self.update_status()

    def generate_xml(self) -> None:
        if self.start is None or self.goal is None:
            messagebox.showerror("Missing points", "Select both start and goal cells.")
            return

        try:
            count = int(self.count_var.get())
        except ValueError:
            messagebox.showerror("Invalid input", "Map count must be an integer.")
            return

        output_root = Path(__file__).resolve().parent / "output"
        try:
            result = write_maze_batch(
                width=self.width,
                height=self.height,
                start=self.start,
                goal=self.goal,
                count=count,
                output_root=output_root,
            )
        except Exception as exc:
            messagebox.showerror("Generation failed", str(exc))
            return

        self.status_var.set(f"Created {len(result.files)} XML files in {result.output_dir}")
        if self.on_generated is not None:
            self.on_generated(result.output_dir)
        messagebox.showinfo("Done", f"Created {len(result.files)} XML files:\n{result.output_dir}")

    def draw_grid(self) -> None:
        if self.canvas is None:
            return

        self.canvas.delete("all")
        for row in range(self.height):
            for col in range(self.width):
                x0 = col * self.cell_size
                y0 = row * self.cell_size
                x1 = x0 + self.cell_size
                y1 = y0 + self.cell_size
                fill = "#f8fafc"
                outline = "#cbd5e1"

                if (row, col) == self.start:
                    fill = "#22c55e"
                elif (row, col) == self.goal:
                    fill = "#ef4444"

                self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline)

                if self.cell_size >= 18:
                    label = ""
                    color = "#0f172a"
                    if (row, col) == self.start:
                        label = "S"
                    elif (row, col) == self.goal:
                        label = "G"
                    if label:
                        self.canvas.create_text(
                            x0 + self.cell_size / 2,
                            y0 + self.cell_size / 2,
                            text=label,
                            fill=color,
                            font=("TkDefaultFont", max(8, self.cell_size // 2), "bold"),
                        )

    def update_status(self) -> None:
        start_text = self._coord_text(self.start)
        goal_text = self._coord_text(self.goal)
        self.status_var.set(
            f"Grid {self.width}x{self.height} | Start {start_text} | Goal {goal_text}"
        )

    def _choose_cell_size(self, width: int, height: int) -> int:
        largest = max(width, height)
        if largest <= 20:
            return 30
        if largest <= 40:
            return 22
        if largest <= 80:
            return 14
        return 9

    def _coord_text(self, coord: Coordinate | None) -> str:
        if coord is None:
            return "-"
        return f"(row={coord[0]}, col={coord[1]})"


class MazeToolApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MuJoCo Maze Tool")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.generator_frame = ttk.Frame(self.notebook)
        self.viewer_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.generator_frame, text="Generate")
        self.notebook.add(self.viewer_frame, text="Viewer")

        self.viewer = BatchViewerApp(self.viewer_frame, set_window_title=False)
        self.generator = MazeGeneratorApp(
            self.generator_frame,
            on_generated=self.on_generated,
            set_window_title=False,
        )

    def on_generated(self, output_dir: Path) -> None:
        self.viewer.load_folder(output_dir)
        self.notebook.select(self.viewer_frame)


def main() -> None:
    root = tk.Tk()
    app = MazeToolApp(root)
    root.minsize(900, 640)
    root.mainloop()


if __name__ == "__main__":
    main()
