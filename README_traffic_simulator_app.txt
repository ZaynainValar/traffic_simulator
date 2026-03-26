Traffic Simulator Desktop App
============================

How to run the Python app directly
----------------------------------
1. Install Python 3.11+ if needed. Make sure to add Python to PATH.
2. Install the required packages:
      py -m pip install numpy matplotlib pillow imageio imageio-ffmpeg
   or:
      python -m pip install numpy matplotlib pillow imageio imageio-ffmpeg
3. Run:
      py traffic_simulator_app.py
   or:
      python traffic_simulator_app.py

How to build the Windows .exe
-----------------------------
Option A: easiest
- Put the Python file and the matching batch file in the same folder.
- Double-click the batch file.

Option B: command line
- Install build tools:
      py -m pip install pyinstaller numpy matplotlib pillow imageio imageio-ffmpeg
- Build:
      py -m PyInstaller --noconfirm --clean --onefile --windowed --name TrafficSimulatorUI traffic_simulator_app.py

Where the executable appears
----------------------------
- It should appear in the same folder/directory where you placed build_windows_exe and traffic_simulator_app inside dist\TrafficSimulatorUI.exe

How uninstall works
-------------------
If you are sharing the raw PyInstaller build:
- delete the .exe file if you used the one-file build
- delete any exported files the user created manually

Included files
--------------
1. traffic_simulator_app.py
   Desktop UI version of the traffic simulator with notebook-style precompute, separate progress stages,
   display-aware sizing, and preview caching for smoother playback.

2. build_windows_exe.bat
   Windows build script for creating a single-file executable with PyInstaller.

3. README_traffic_simulator_app_.txt
   This guide.

What this version does
----------------------
This version is built around the same design philosophy as the notebook:
- the simulation is computed first
- the display frames are rendered after that
- playback happens only after those stages finish

That means the app intentionally trades startup time and memory usage for more reliable playback.
The goal is to make the simulation itself fully settled before the user watches it.

In addition to that notebook-style workflow, this version includes:
- separate progress stages in the UI
  1) Precomputing traffic states
  2) Rendering display frames
- ETA based on rendered units per second
- optional random seed input
- display-fit preview logic
- preview-cache playback, so the app can build viewer-sized frames in advance instead of resizing every
  image live during playback
- export options for GIF, MP4, and a playable HTML player

How the app works
-----------------
1. Open the app.
2. Adjust the settings.
3. Click Generate / Apply.
4. The app computes the full simulation state history.
5. The app then renders the display frames.
6. The app builds a display-ready preview cache for the current viewer size.
7. Playback uses that cached preview instead of live Matplotlib drawing.

This is slower up front than a live-draw app, but it keeps the simulation logic separate from playback.
So if playback looks different on two machines, that does not mean the underlying traffic simulation changed.

Using the app
-------------
Generate / Apply
  Reads the current settings and rebuilds the simulation from scratch.

Reset Defaults
  Restores the default parameter values in the UI.

Play
  Starts or pauses playback of the already-prepared preview.

Step
  Advances one display frame.

Restart
  Returns playback to the beginning of the current prepared simulation.

Export GIF / MP4 / HTML Player
  Saves the prepared animation in one of the supported output formats.

Parameter guide
---------------
Below is a full explanation of each setting shown in the app.

Layout
------

Lanes
  The number of travel lanes on the freeway segment.

  Increasing this:
  - creates a wider road
  - gives vehicles more passing options
  - usually reduces congestion because cars have more space to spread out
  - tends to create more interesting overtaking patterns

  Decreasing this:
  - makes the road narrower
  - forces more vehicles to compete for the same openings
  - usually increases blocking, pressure to pass, and local congestion

Base road length
  The baseline horizontal length of the simulated freeway segment before zoom-related scaling is applied.

  Increasing this:
  - gives vehicles more left-to-right room to occupy
  - lets more vehicles remain visible at the same time
  - makes the simulated road feel longer and more spread out
  - can reduce how quickly cars enter and leave the visible scene

  Decreasing this:
  - shortens the visible segment
  - causes vehicles to appear and disappear more quickly
  - can make traffic feel denser because the same inflow is squeezed into less visible road

Zoom
  The main scene zoom factor. In this project, zoom affects more than appearance.
  It changes the effective scene scale used to frame the road and surrounding space.

  Increasing this:
  - expands the visible world extent used by the viewer
  - changes how much space appears around the roadway
  - affects how large the road segment feels in the final render
  - can make the scene feel less cramped

  Decreasing this:
  - tightens the framing
  - reduces the visible world extent
  - makes the road fill more of the view

Horizontal zoom
  Additional horizontal scaling applied to the road length.

  Increasing this:
  - stretches the road horizontally
  - gives more visual room for spacing between vehicles
  - can make the road feel longer without increasing the number of lanes

  Decreasing this:
  - compresses the road horizontally
  - makes vehicles cycle through the visible segment faster
  - can make traffic look busier because the same cars occupy less visual width

Traffic
-------

Spawn probability
  The base probability that each lane attempts to spawn a vehicle during a simulation step.
  This is one of the strongest controls over traffic density.

  Increasing this:
  - creates heavier traffic
  - raises the chance of backups and slowdowns
  - increases lane-change demand because drivers encounter leaders more often
  - tends to make congestion emerge sooner

  Decreasing this:
  - creates lighter traffic
  - leaves larger average gaps between vehicles
  - reduces blocking and passing pressure
  - produces a calmer, more open-flow simulation

Spawn clearance
  The minimum open space near the road entrance required before a new vehicle is allowed to appear.

  Increasing this:
  - makes spawning more conservative
  - reduces crowding right at the entrance
  - lowers effective inflow when traffic is already dense
  - helps prevent very tight initial spacing

  Decreasing this:
  - allows vehicles to appear closer to existing traffic
  - makes the entrance fill more aggressively
  - can increase local bunching near the spawn side of the road

Min desired speed
  The lower bound of the random desired-speed range before vehicle-type and driver-style adjustments are applied.

  Increasing this:
  - raises the floor on how slow vehicles want to drive
  - reduces the very slow tail of traffic
  - can make the entire system move faster overall
  - may reduce the number of rolling bottlenecks caused by especially slow drivers

  Decreasing this:
  - allows slower target speeds
  - increases speed diversity across the traffic population
  - can create more interactions where faster cars catch slower ones
  - usually increases the chance of passing behavior and backups

Max desired speed
  The upper bound of the random desired-speed range before vehicle-type and driver-style adjustments are applied.

  Increasing this:
  - allows more aggressive target speeds
  - increases the gap between fast and slow traffic
  - usually creates more overtaking and lane changes
  - can make assertive drivers feel much more aggressive

  Decreasing this:
  - compresses the fast end of the speed distribution
  - reduces extreme speed differences
  - often makes traffic flow look more uniform
  - can reduce the amount of passing pressure in the left lanes

Behavior
--------

Safe gap
  The forward spacing threshold that strongly influences when a driver starts to feel blocked by the vehicle ahead.
  This is one of the main controls over following conservatism.

  Increasing this:
  - makes drivers respond earlier to slower vehicles ahead
  - makes following behavior more cautious
  - tends to increase lane-change attempts because drivers feel blocked sooner
  - can produce smoother but more conservative traffic flow

  Decreasing this:
  - makes drivers tolerate tighter spacing
  - reduces the chance that a driver feels blocked at moderate distances
  - can make traffic look more aggressive and compact
  - may reduce lane changes if drivers are willing to sit closer behind leaders

Lane change threshold
  The minimum score improvement required before a vehicle will commit to switching lanes.
  In other words, it controls how much better another lane must be before a driver decides it is worth moving.

  Increasing this:
  - makes drivers harder to convince
  - reduces lane-change frequency
  - produces more lane stability
  - keeps drivers in their current lane unless the benefit is clearly meaningful

  Decreasing this:
  - makes drivers willing to move for smaller advantages
  - increases lane-change activity
  - can make traffic look more dynamic or more chaotic, depending on the other settings

Yield rear gap
  The rear-distance threshold used when deciding whether a slower vehicle is holding up faster traffic behind it.
  This feeds into the courtesy-yield behavior.

  Increasing this:
  - makes drivers more aware of vehicles behind them from farther away
  - increases the chance that slower drivers try to move right to let others pass
  - can create more polite-looking traffic behavior

  Decreasing this:
  - makes drivers less sensitive to faster followers behind them
  - reduces courtesy-yield triggers
  - can make slow leaders stay in the way longer

Weaver probability
  The fraction of vehicles that become special aggressive “weaver” drivers.
  Weavers are more likely to move around actively and are less bound by the ordinary lane-discipline logic.

  Increasing this:
  - creates more chaotic and aggressive lane movement
  - increases the number of vehicles that drift toward better speed lanes even without classic blocking
  - makes the traffic stream look more restless

  Decreasing this:
  - makes traffic more orderly
  - keeps behavior closer to the ordinary driver profiles
  - reduces sudden or repeated lane shifts

Timing
------

Simulation FPS
  The number of traffic-logic updates per simulated second.
  This affects how finely the simulator resolves changes in speed, spacing, and lane decisions.

  Increasing this:
  - gives the simulator more logic updates per second
  - can make motion and behavioral transitions more finely resolved
  - may increase total compute time because more simulation steps are required
  - can improve temporal smoothness of the underlying traffic logic

  Decreasing this:
  - reduces the number of logic updates
  - can make the simulation cheaper to compute
  - may make motion and decisions look coarser if set too low

Display FPS
  The number of display frames targeted for playback and export.
  This affects how smooth the final animation looks, but it is separate from the underlying simulation logic.

  Increasing this:
  - creates more display frames
  - makes playback and exported animations appear smoother
  - significantly increases frame-render time, memory use, and export size
  - does not change the core simulated traffic decisions, only how finely they are displayed

  Decreasing this:
  - reduces the number of rendered display frames
  - lowers generation cost and output size
  - can make playback look less smooth
  - is often one of the best ways to reduce total render time

Run time (s)
  The duration of each simulation run in seconds.

  Increasing this:
  - simulates traffic for longer
  - increases the number of simulation steps and display frames
  - raises generation time, memory usage, and export size
  - lets longer traffic patterns develop

  Decreasing this:
  - shortens the simulation
  - reduces total compute and render cost
  - produces smaller exports and faster turnaround

Random seed (optional)
  Controls repeatability of the random generation.
  If you enter a number, the same settings should produce the same random traffic pattern each time.
  If you leave it blank, the app uses a fresh random seed and the run changes from build to build.

  Entering a seed:
  - is useful for debugging, comparison, and reproducible demos
  - lets you rerun the same traffic scenario after changing only one other parameter

  Leaving it blank:
  - gives a fresh random run each time
  - is useful when you want variety instead of exact reproducibility

Display and performance notes
-----------------------------
- Larger monitors and larger viewer sizes usually require more work for preview playback.
- This version reduces that problem by building a preview cache for the current viewer size after rendering.
- If you resize the viewer substantially, the app may need to rebuild that preview cache.
- Display FPS and Run time are two of the strongest controls over total render time.
- Spawn probability is one of the strongest controls over how busy the simulation becomes.

Export formats
--------------
Animated GIF
  Good for easy sharing and wide compatibility.
  File sizes can become large for long or high-FPS runs.

MP4 Video
  Usually the best balance of smooth playback and file size.
  Requires the ffmpeg support installed with imageio-ffmpeg.

HTML Player
  Saves a standalone playable HTML file rather than a static page of individual frames.
  This is useful if you want to share an interactive playback file without requiring a video player.

Practical tuning tips
---------------------
If you want denser traffic:
- raise Spawn probability
- lower Lanes
- lower Safe gap only if you want more aggressive-looking close traffic

If you want smoother exports with less waiting:
- lower Display FPS
- shorten Run time

If you want more passing behavior:
- raise Max desired speed
- lower Lane change threshold
- keep enough lane count for vehicles to maneuver

If you want more orderly traffic:
- lower Weaver probability
- raise Lane change threshold
- raise Safe gap

If you want reproducible comparisons:
- set a specific Random seed
- change one parameter at a time
