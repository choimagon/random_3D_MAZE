from __future__ import annotations

import math
from pathlib import Path
import textwrap
import time

import mujoco
import mujoco.viewer


CELL = 1.0
WALL_THICKNESS = 0.12
WALL_HEIGHT = 0.72

# '#' cells become raised blocks. Spaces are navigable floor.
MAZE = [
    "#############",
    "#S  #       #",
    "### # ##### #",
    "#   #   #   #",
    "# ##### # ###",
    "# #     #   #",
    "# # ####### #",
    "# #       # #",
    "# ####### # #",
    "#       #   #",
    "# ##### ### #",
    "#     #    E#",
    "#############",
]


def _box_geom(name: str, pos: tuple[float, float, float], size: tuple[float, float, float], rgba: str) -> str:
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


def _wall_geoms() -> str:
    rows = len(MAZE)
    cols = len(MAZE[0])
    geoms: list[str] = []

    for row, line in enumerate(MAZE):
        for col, tile in enumerate(line):
            if tile != "#":
                continue

            x, y = _grid_to_world(row, col, rows, cols)
            name = f"wall_{row}_{col}"
            geoms.append(
                _box_geom(
                    name,
                    (x, y, WALL_HEIGHT / 2.0),
                    (CELL * 0.48, CELL * 0.48, WALL_HEIGHT / 2.0),
                    "0.22 0.25 0.28 1",
                )
            )

    return "\n      ".join(geoms)


def _marker_geoms() -> str:
    rows = len(MAZE)
    cols = len(MAZE[0])
    start = end = None

    for row, line in enumerate(MAZE):
        for col, tile in enumerate(line):
            if tile == "S":
                start = _grid_to_world(row, col, rows, cols)
            elif tile == "E":
                end = _grid_to_world(row, col, rows, cols)

    if start is None or end is None:
        raise ValueError("MAZE must contain one S tile and one E tile.")

    sx, sy = start
    ex, ey = end
    return "\n      ".join(
        [
            '<geom name="start_pad" type="cylinder" '
            f'pos="{sx:.3f} {sy:.3f} 0.018" size="0.32 0.018" rgba="0.09 0.62 0.36 1"/>',
            '<geom name="end_pad" type="cylinder" '
            f'pos="{ex:.3f} {ey:.3f} 0.018" size="0.32 0.018" rgba="0.86 0.23 0.18 1"/>',
            '<body name="player_ball" '
            f'pos="{sx:.3f} {sy:.3f} 0.35">'
            '<freejoint/>'
            '<geom type="sphere" size="0.22" mass="0.3" rgba="0.15 0.39 0.92 1"/>'
            "</body>",
        ]
    )


def build_xml() -> str:
    rows = len(MAZE)
    cols = len(MAZE[0])
    width = cols * CELL
    height = rows * CELL
    camera_distance = max(width, height) * 0.95
    camera_height = max(width, height) * 0.65

    wall_geoms = _wall_geoms()
    marker_geoms = _marker_geoms()

    return textwrap.dedent(
        f"""
        <mujoco model="interactive_maze">
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

            <geom name="floor" type="plane" pos="0 0 0" size="{width / 2 + 1:.2f} {height / 2 + 1:.2f} 0.1" material="floor_mat"/>
            <geom name="backdrop" type="box" pos="0 0 -0.055" size="{width / 2 + 0.3:.2f} {height / 2 + 0.3:.2f} 0.05" rgba="0.10 0.11 0.12 1"/>

            {wall_geoms}
            {marker_geoms}
          </worldbody>
        </mujoco>
        """
    ).strip()


def main() -> None:
    scene_path = Path(__file__).with_name("maze_scene.xml")
    scene_path.write_text(build_xml(), encoding="utf-8")

    model = mujoco.MjModel.from_xml_path(str(scene_path))
    data = mujoco.MjData(model)

    # Keep a visible physics tick so the free ball settles if moved in the viewer.
    with mujoco.viewer.launch_passive(model, data) as viewer:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        viewer.cam.distance = 14.0
        viewer.cam.azimuth = 135.0
        viewer.cam.elevation = -42.0
        viewer.cam.lookat[:] = [0.0, 0.0, 0.0]

        while viewer.is_running():
            step_start = time.time()
            mujoco.mj_step(model, data)
            viewer.sync()

            elapsed = time.time() - step_start
            if elapsed < model.opt.timestep:
                time.sleep(model.opt.timestep - elapsed)


if __name__ == "__main__":
    main()
