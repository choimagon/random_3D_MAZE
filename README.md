# MuJoCo Maze Tool

Generate random 2D maze layouts, export them as MuJoCo XML files, preview them
in a top-down grid, and open selected maps in the native MuJoCo viewer.

## Quick Start

Install Miniconda or Anaconda first. Then run:

```bash
git clone https://github.com/choimagon/random_3D_MAZE.git
cd random_3D_MAZE
```

### macOS / Ubuntu

```bash
chmod +x run.sh
./run.sh
```

### Windows

Double-click `run.bat`, or run:

```bat
run.bat
```

You can also use the cross-platform Python launcher directly:

```bash
python run.py
```

The first run creates this local conda environment automatically:

```text
.conda_envs/mujoco-maze
```

After that, the same command opens the GUI directly.

## OS Setup

### macOS

1. Install Miniconda or Anaconda.
2. Open Terminal in this project folder.
3. Run:

```bash
chmod +x run.sh
./run.sh
```

The native MuJoCo viewer is launched with `mjpython` automatically when needed.

### Ubuntu

1. Install Miniconda or Anaconda.
2. Install common OpenGL/X11 runtime libraries if MuJoCo viewer windows do not
   open:

```bash
sudo apt update
sudo apt install -y libgl1 libegl1 libx11-6 libxrandr2 libxinerama1 libxcursor1 libxi6 libxxf86vm1
```

3. Run:

```bash
chmod +x run.sh
./run.sh
```

### Windows

1. Install Miniconda or Anaconda for Windows.
2. Open Anaconda Prompt, PowerShell, or Command Prompt in this project folder.
3. Run:

```bat
run.bat
```

If `run.bat` is blocked by policy, run:

```bat
python run.py
```

## Manual Environment Setup

The launcher does this automatically, but you can create the environment
manually:

```bash
conda env create -p .conda_envs/mujoco-maze -f environment.yml
```

Then run the GUI manually:

### macOS / Ubuntu

```bash
.conda_envs/mujoco-maze/bin/python maze_generator_gui.py
```

### Windows

```bat
.conda_envs\mujoco-maze\python.exe maze_generator_gui.py
```

## GUI Workflow

1. Open the GUI with `./run.sh`, `run.bat`, or `python run.py`.
2. In the `Generate` tab, set width, height, and map count.
3. Click `Create Grid`.
4. Click cells to set `Start` and `Goal`.
5. Click `Generate XML`.
6. The GUI switches to the `Viewer` tab and loads the generated folder.

Generated files are written under:

```text
output/<width>x<height>_start_r<row>_c<col>_goal_r<row>_c<col>_<timestamp>/
```

The XML files are named `1.xml`, `2.xml`, `3.xml`, and so on.

## Viewer

In the `Viewer` tab:

- `Choose Folder`: load an output folder.
- `View All`: show all XML files in one top-down grid preview window.
- Click a preview tile: open that XML in the native MuJoCo viewer.
- `View Selected`: open the selected XML directly in the native MuJoCo viewer.

Both preview and native viewer use a top-down orthographic camera.

## CLI Generation

You can also generate XML maps from the terminal:

```bash
.conda_envs/mujoco-maze/bin/python maze_generator.py --width 13 --height 13 --start 1,1 --goal 11,11 --count 4
```

On Windows:

```bat
.conda_envs\mujoco-maze\python.exe maze_generator.py --width 13 --height 13 --start 1,1 --goal 11,11 --count 4
```
