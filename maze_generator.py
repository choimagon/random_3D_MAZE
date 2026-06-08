from __future__ import annotations

import argparse
import random
import re
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


CELL = 1.0
WALL_HEIGHT = 0.72
WALL_SIZE = CELL * 0.48

Coordinate = tuple[int, int]


@dataclass(frozen=True)
class BatchResult:
    output_dir: Path
    files: list[Path]


def validate_inputs(
    width: int,
    height: int,
    start: Coordinate,
    goal: Coordinate,
    count: int = 1,
) -> None:
    if width < 3 or height < 3:
        raise ValueError("width and height must be at least 3.")
    if count < 1:
        raise ValueError("count must be at least 1.")

    for name, (row, col) in {"start": start, "goal": goal}.items():
        if row < 0 or row >= height or col < 0 or col >= width:
            raise ValueError(f"{name} coordinate is outside the grid.")

    if start == goal:
        raise ValueError("start and goal must be different cells.")


def generate_maze_grid(
    width: int,
    height: int,
    start: Coordinate,
    goal: Coordinate,
    seed: int | None = None,
) -> list[str]:
    """Generate a connected 2D maze where # is a wall and spaces are floor."""
    validate_inputs(width, height, start, goal)

    rng = random.Random(seed)
    grid = [["#" for _ in range(width)] for _ in range(height)]
    anchors = [(row, col) for row in range(1, height - 1, 2) for col in range(1, width - 1, 2)]
    anchor_set = set(anchors)

    if not anchors:
        raise ValueError("grid is too small to contain a maze.")

    stack = [_nearest_anchor(start, anchors)]
    visited = {stack[0]}
    grid[stack[0][0]][stack[0][1]] = " "

    while stack:
        row, col = stack[-1]
        neighbors = []

        for drow, dcol in ((0, 2), (0, -2), (2, 0), (-2, 0)):
            next_cell = (row + drow, col + dcol)
            if next_cell in anchor_set and next_cell not in visited:
                neighbors.append(next_cell)

        if not neighbors:
            stack.pop()
            continue

        next_row, next_col = rng.choice(neighbors)
        wall_row = (row + next_row) // 2
        wall_col = (col + next_col) // 2
        grid[wall_row][wall_col] = " "
        grid[next_row][next_col] = " "
        visited.add((next_row, next_col))
        stack.append((next_row, next_col))

    _connect_point_to_maze(grid, start, anchors, rng)
    _connect_point_to_maze(grid, goal, anchors, rng)

    if not _has_path(grid, start, goal):
        raise RuntimeError("generated maze does not connect start and goal.")

    start_row, start_col = start
    goal_row, goal_col = goal
    grid[start_row][start_col] = "S"
    grid[goal_row][goal_col] = "G"

    return ["".join(row) for row in grid]


def build_mujoco_xml(
    maze: Iterable[str],
    start: Coordinate,
    goal: Coordinate,
    model_name: str = "generated_maze",
) -> str:
    rows = list(maze)
    if not rows:
        raise ValueError("maze must contain at least one row.")

    height = len(rows)
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("all maze rows must have the same width.")

    board_width = width * CELL
    board_height = height * CELL
    camera_distance = max(board_width, board_height) * 0.95
    camera_height = max(board_width, board_height) * 0.65

    wall_geoms = _wall_geoms(rows)
    marker_geoms = _marker_geoms(start, goal, height, width)
    safe_model_name = _safe_xml_name(model_name)

    return textwrap.dedent(
        f"""
        <mujoco model="{safe_model_name}">
          <compiler angle="degree"/>
          <option timestep="0.01" gravity="0 0 -9.81"/>

          <visual>
            <global azimuth="135" elevation="-38" offwidth="1280" offheight="720"/>
            <quality shadowsize="4096"/>
            <map fogstart="12" fogend="26"/>
          </visual>

          <asset>
            <texture name="sky" type="skybox" builtin="gradient" rgb1="0.65 0.78 0.95" rgb2="0.06 0.08 0.10" width="512" height="512"/>
            <texture name="floor_tex" type="2d" builtin="checker" rgb1="0.77 0.78 0.72" rgb2="0.56 0.58 0.54" width="512" height="512"/>
            <material name="floor_mat" texture="floor_tex" texrepeat="8 8" reflectance="0.18"/>
          </asset>

          <worldbody>
            <light name="key" pos="-3 -4 8" dir="0.4 0.5 -1" diffuse="0.95 0.95 0.9" specular="0.2 0.2 0.2"/>
            <light name="fill" pos="5 4 4" dir="-0.6 -0.4 -1" diffuse="0.3 0.35 0.45"/>

            <camera name="overview" pos="{camera_distance:.2f} {-camera_distance:.2f} {camera_height:.2f}" xyaxes="0.707 0.707 0 -0.408 0.408 0.816"/>
            <camera name="low_angle" pos="0 {-camera_distance:.2f} 3.2" xyaxes="1 0 0 0 0.35 0.94"/>

            <geom name="floor" type="plane" pos="0 0 0" size="{board_width / 2 + 1:.2f} {board_height / 2 + 1:.2f} 0.1" material="floor_mat"/>
            <geom name="backdrop" type="box" pos="0 0 -0.055" size="{board_width / 2 + 0.3:.2f} {board_height / 2 + 0.3:.2f} 0.05" rgba="0.10 0.11 0.12 1"/>

            {wall_geoms}
            {marker_geoms}
          </worldbody>
        </mujoco>
        """
    ).strip()


def write_maze_batch(
    width: int,
    height: int,
    start: Coordinate,
    goal: Coordinate,
    count: int,
    output_root: Path | str = "output",
    seed: int | None = None,
    timestamp: str | None = None,
) -> BatchResult:
    validate_inputs(width, height, start, goal, count)

    output_root = Path(output_root)
    timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    start_name = f"start_r{start[0]}_c{start[1]}"
    goal_name = f"goal_r{goal[0]}_c{goal[1]}"
    folder_name = f"{width}x{height}_{start_name}_{goal_name}_{timestamp}"
    output_dir = _unique_dir(output_root / folder_name)
    output_dir.mkdir(parents=True, exist_ok=False)

    batch_rng = random.Random(seed)
    files: list[Path] = []

    for index in range(1, count + 1):
        maze_seed = batch_rng.randrange(0, 2**63)
        maze = generate_maze_grid(width, height, start, goal, seed=maze_seed)
        xml = build_mujoco_xml(maze, start, goal, model_name=f"maze_{index}")
        file_path = output_dir / f"{index}.xml"
        file_path.write_text(xml + "\n", encoding="utf-8")
        files.append(file_path)

    return BatchResult(output_dir=output_dir, files=files)


def _nearest_anchor(point: Coordinate, anchors: list[Coordinate]) -> Coordinate:
    row, col = point
    return min(anchors, key=lambda anchor: abs(anchor[0] - row) + abs(anchor[1] - col))


def _connect_point_to_maze(
    grid: list[list[str]],
    point: Coordinate,
    anchors: list[Coordinate],
    rng: random.Random,
) -> None:
    target = _nearest_anchor(point, anchors)
    row, col = point
    target_row, target_col = target
    grid[row][col] = " "

    if rng.choice((True, False)):
        _carve_horizontal(grid, row, col, target_col)
        _carve_vertical(grid, col=target_col, row=row, target_row=target_row)
    else:
        _carve_vertical(grid, col, row, target_row)
        _carve_horizontal(grid, target_row, col, target_col)


def _carve_horizontal(grid: list[list[str]], row: int, col: int, target_col: int) -> None:
    step = 1 if target_col >= col else -1
    for current_col in range(col, target_col + step, step):
        grid[row][current_col] = " "


def _carve_vertical(grid: list[list[str]], col: int, row: int, target_row: int) -> None:
    step = 1 if target_row >= row else -1
    for current_row in range(row, target_row + step, step):
        grid[current_row][col] = " "


def _has_path(grid: list[list[str]], start: Coordinate, goal: Coordinate) -> bool:
    height = len(grid)
    width = len(grid[0])
    visited = {start}
    queue = [start]

    while queue:
        row, col = queue.pop(0)
        if (row, col) == goal:
            return True

        for next_row, next_col in ((row + 1, col), (row - 1, col), (row, col + 1), (row, col - 1)):
            if next_row < 0 or next_row >= height or next_col < 0 or next_col >= width:
                continue
            if (next_row, next_col) in visited or grid[next_row][next_col] == "#":
                continue
            visited.add((next_row, next_col))
            queue.append((next_row, next_col))

    return False


def _wall_geoms(maze: list[str]) -> str:
    height = len(maze)
    width = len(maze[0])
    geoms: list[str] = []

    for row, line in enumerate(maze):
        for col, tile in enumerate(line):
            if tile != "#":
                continue

            x, y = _grid_to_world(row, col, height, width)
            geoms.append(
                _box_geom(
                    f"wall_{row}_{col}",
                    (x, y, WALL_HEIGHT / 2.0),
                    (WALL_SIZE, WALL_SIZE, WALL_HEIGHT / 2.0),
                    "0.22 0.25 0.28 1",
                )
            )

    return "\n      ".join(geoms)


def _marker_geoms(start: Coordinate, goal: Coordinate, rows: int, cols: int) -> str:
    sx, sy = _grid_to_world(start[0], start[1], rows, cols)
    gx, gy = _grid_to_world(goal[0], goal[1], rows, cols)
    return "\n      ".join(
        [
            '<geom name="start_pad" type="cylinder" '
            f'pos="{sx:.3f} {sy:.3f} 0.018" size="0.32 0.018" rgba="0.09 0.62 0.36 1"/>',
            '<geom name="goal_pad" type="cylinder" '
            f'pos="{gx:.3f} {gy:.3f} 0.018" size="0.32 0.018" rgba="0.86 0.23 0.18 1"/>',
            '<body name="player_ball" '
            f'pos="{sx:.3f} {sy:.3f} 0.35">'
            '<freejoint/>'
            '<geom type="sphere" size="0.22" mass="0.3" rgba="0.15 0.39 0.92 1"/>'
            "</body>",
        ]
    )


def _box_geom(
    name: str,
    pos: tuple[float, float, float],
    size: tuple[float, float, float],
    rgba: str,
) -> str:
    px, py, pz = pos
    sx, sy, sz = size
    return (
        f'<geom name="{name}" type="box" pos="{px:.3f} {py:.3f} {pz:.3f}" '
        f'size="{sx:.3f} {sy:.3f} {sz:.3f}" rgba="{rgba}" condim="3"/>'
    )


def _grid_to_world(row: int, col: int, rows: int, cols: int) -> tuple[float, float]:
    x = (col - (cols - 1) / 2.0) * CELL
    y = ((rows - 1) / 2.0 - row) * CELL
    return x, y


def _unique_dir(path: Path) -> Path:
    if not path.exists():
        return path

    suffix = 2
    while True:
        candidate = Path(f"{path}_{suffix}")
        if not candidate.exists():
            return candidate
        suffix += 1


def _safe_xml_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return safe or "maze"


def _parse_coord(value: str) -> Coordinate:
    try:
        row_text, col_text = value.split(",", 1)
        return int(row_text), int(col_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("coordinate must use row,col format.") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate random MuJoCo maze XML files.")
    parser.add_argument("--width", type=int, required=True, help="Grid width in cells.")
    parser.add_argument("--height", type=int, required=True, help="Grid height in cells.")
    parser.add_argument("--start", type=_parse_coord, required=True, help="Start cell as row,col.")
    parser.add_argument("--goal", type=_parse_coord, required=True, help="Goal cell as row,col.")
    parser.add_argument("--count", type=int, default=1, help="Number of XML maps to generate.")
    parser.add_argument("--output", type=Path, default=Path("output"), help="Output root directory.")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed.")
    args = parser.parse_args()

    result = write_maze_batch(
        width=args.width,
        height=args.height,
        start=args.start,
        goal=args.goal,
        count=args.count,
        output_root=args.output,
        seed=args.seed,
    )

    print(f"Created {len(result.files)} XML file(s) in {result.output_dir}")


if __name__ == "__main__":
    main()
