# Voltcraft Charge Manager CM 2016 - Linux GTK GUI Project

## Device Overview

The Voltcraft CM 2016 is a battery charger/manager for AA/AAA NiMH/NiCd rechargeable batteries with 6 independent charging slots (S1-S4, S5A, S5B). It connects to a PC via USB (USB-B port) using a Silicon Labs CP210x USB-to-UART bridge chip, appearing as a serial COM port.

## Communication

- **Interface:** USB serial (Silicon Labs CP210x USB-UART bridge)
- **Linux driver:** `cp210x` kernel module (typically built-in on modern kernels)
- **Device path:** `/dev/ttyUSB0` (default), currently `/dev/ttyUSB1` on dev machine (ttyUSB0 is a ch341 device)

## Serial Protocol

**Sources:** [tarator/cm2016 (Java)](https://gitlab.projecttac.com/tarator/cm2016), [michael-wahler/CM2016 (Python)](https://github.com/michael-wahler/CM2016), [Leisenfels protocol docs](https://www.leisenfels.com/howto-charge-manager-2016-data-format)

### Connection Settings

| Parameter  | Value  |
|------------|--------|
| Baud rate  | 19200  |
| Data bits  | 8      |
| Stop bits  | 1      |
| Parity     | None   |
| Flow ctrl  | None   |

### Protocol Characteristics

- **Unidirectional / read-only** - the charger pushes data, no commands are sent to it
- Device transmits a **127-byte frame every ~2 seconds**
- Host simply opens the serial port and reads

### Frame Format (127 bytes)

| Offset   | Length | Content                          |
|----------|--------|----------------------------------|
| 0-6      | 7 B    | Device ID: ASCII `"CM2016 "`     |
| 7-16     | 10 B   | Header (see below)                 |
| 17-34    | 18 B   | Slot 1 data                      |
| 35-52    | 18 B   | Slot 2 data                      |
| 53-70    | 18 B   | Slot 3 data                      |
| 71-88    | 18 B   | Slot 4 data                      |
| 89-106   | 18 B   | Slot A data (9V block)           |
| 107-124  | 18 B   | Slot B data (9V block)           |
| 125-126  | 2 B    | Checksum (algorithm unknown, not validated) |

### Slot Data Structure (18 bytes per slot)

All multi-byte integers are **little-endian**.

| Byte | Field     | Encoding |
|------|-----------|----------|
| 0    | Active    | `0x01` = running, `0x00` = finished |
| 1    | Program   | `1`=CHA, `2`=DIS, `3`=CHK, `4`=CYC, `5`=ALV, `6`/`9`=ERR |
| 2    | Step      | Odd (1,3,5,7) = charging; Even (2,4,6) = discharging; 0 = idle |
| 3    | Status    | `0x20`=empty, `0x07`/`0x02` (inactive)=RDY, `0x21`=ERR, `0x07` (active)=TRI (trickle) |
| 4-5  | Runtime   | Elapsed minutes, 16-bit LE |
| 6-7  | Voltage   | Millivolts, 16-bit LE (divide by 1000 for V) |
| 8-9  | Current   | mA 16-bit LE. Slots 1-4: /1000 for A. Slots A/B: /10000 for A |
| 10-13| C-CAP     | 32-bit LE charge capacity. Slots 1-4: /100 for mAh. Slots A/B: /1000 for mAh |
| 14-17| D-CAP     | 32-bit LE discharge capacity. Same scaling as C-CAP |

### Header Bytes (offsets 7-16, 10 bytes)

Discovered from [sarnau/cm2016](https://github.com/sarnau/cm2016) reference implementation:

| Offset | Length | Content                                         |
|--------|--------|-------------------------------------------------|
| 7      | 1 B    | Firmware version major                          |
| 8      | 1 B    | Firmware version minor                          |
| 9      | 1 B    | Chemistry setting (0=NiMH, 1=NiZn)             |
| 10     | 1 B    | Overtemperature flag                            |
| 11-12  | 2 B    | Start temperature (signed 16-bit, **big-endian**) |
| 13-14  | 2 B    | Actual temperature (signed 16-bit, **big-endian**) |
| 15-16  | 2 B    | Action counter (signed 16-bit, **big-endian**)  |

**Note:** Header uses big-endian while slot data uses little-endian.

### Important Notes

- **D-CAP byte order:** Normal LE like C-CAP (verified with real device — the byte-swap documented by Leisenfels was not confirmed)
- **Capacity fields are 32-bit LE** (not 24-bit as originally documented). C-CAP at bytes [10-13], D-CAP at bytes [14-17]. No unknown bytes in the slot structure.
- **Slots A/B current scaling** differs from slots 1-4: /10000 vs /1000 for A (finer granularity for 9V block batteries)
- Checksum exists but algorithm is unknown and neither existing project validates it

## Feature Specification (full parity with CM2016 Logger V2.10)

All features from the original Windows software are implemented. Reference: bundled PDF manual.

### Connection & Control
- **Auto-detect CM2016** - on startup, auto-selects port if a single Silicon Labs CP210x (VID `10C4`, PID `EA60`) is found
- **Serial port selection** - dialog with dropdown listing `/dev/ttyUSB*` devices and refresh button
- **Start/Stop Logging** - button to start/stop data recording
- **Auto-disconnect detection** - stops recording if no data received for >2 seconds, shows warning dialog ("Recording stopped: CM2016 switched off or disconnected")
- **"Waiting For Data"** indicator in status bar while connected

### Main View - 6 Slot Panels (left sidebar)
Each slot displays live parameters. Clicking a slot selects it for table/chart view:
- **Program** (Charge, Discharge, Cycle, Check, Alive)
- **Actual** (Ready, Charge, Discharge, Error, Trickle)
- **Chemistry** (NiMH, NiZn — from frame header byte 9)
- **Time** (elapsed runtime)
- **C-CAP** (charge capacity in mAh)
- **D-CAP** (discharge capacity in mAh)
- **Voltage** (V)
- **Current** (A)
- Background color changes gray -> green when recording is active
- Auto-clear slot data when battery is removed during recording

### Data Table (center)
- Columns: Slot, Time, Program, Actual, Voltage(V), Current(A), CCAP(mAh), DCAP(mAh), Chemistry
- **Autoscroll** toggle button - auto-scrolls to latest value when enabled
- **Copy to Clipboard** - right-click context menu: "Copy To Clipboard" (selection) / "Copy All To Clipboard" (entire table)
- **Ctrl+C** support for copying selected rows to spreadsheet applications

### Charts (right panel)
- **Voltage chart** (Voltage [V] vs Time [days:hours:minutes]) - upper graph
- **Current chart** (Current [A] vs Time [days:hours:minutes]) - lower graph
- **3 chart styles** selectable via radio buttons: Lines, Bar graph, 3D-Lines
- **3D-Lines** with adjustable Tilt and Rotation controls
- **Color coding:** Green/dark-green = charging, Red/dark-red = discharging, Gray dots = missing data points (recording pauses)
- **Final voltage** annotation displayed at program end
- **Zoom:** Mouse drag selection (draw rectangle), right-click context menu "Zoom In" (2x magnification), "Reset Zoom" (full view), mouse scroll wheel
- **Navigation:** Cursor keys for panning, scrollbars on charts
- **Keyboard shortcuts:** Home = reset zoom, Del = jump to start, End = jump to end, Backspace = undo one zoom step, PageUp/PageDown = large X-axis steps
- **Data point tooltip:** Right-click on curve shows popup with Actual Mode, Voltage, Current, Time

### Display Style (toolbar dropdown with checkboxes)
- **Table** only
- **Charts** only
- **Both** simultaneously (table + charts side by side)

### File Operations
- **File > Save Logged Data** - save all slot data to file
- **File > Load Logged Data** - load saved data (overwrites temporary files)
- **Temporary files** - data is buffered to temp files in parallel during recording
- **Resume Recording** - on startup, if temp data exists, prompt "Continue last recording?" (Yes loads data and resumes, No deletes temp data)
- **File > COM-Port** - change serial port without restarting
- **File > Quit** - exit application

### Export (applies to currently selected slot only)
- **CSV** export
- **Excel** export (including voltage and current chart images embedded in spreadsheet)

### Print
- **Print measurement report** - disabled during active recording
- Charts printed as currently displayed (respects zoom level)
- Auto-generated title line: slot number, time, charge and discharge capacity
- Recommended format: DIN A4/A3, landscape orientation

### Miscellaneous
- **About** dialog (version info)
- **Clear Data** button - delete all recorded data across all slots
- **Inhibit system sleep** during active recording (prevents data loss)

## Data Points per Slot

| Field     | Description                        |
|-----------|------------------------------------|
| Program   | Selected charging program          |
| Actual    | Current operation (Charge/Discharge/Ready/etc.) |
| Chemistry | Battery type (NiMH, NiZn)         |
| Time      | Elapsed time                       |
| C-CAP     | Charge capacity in mAh            |
| D-CAP     | Discharge capacity in mAh         |
| Voltage   | Current voltage in V              |
| Current   | Current amperage in A             |

## Project Goal

Build a native Linux GTK GUI application that fully replicates the Windows-only CM2016 Logger V2.10 software as the first free and open-source GUI for this device. Feature parity with the original is the target - all features listed above must be implemented.

## Tech Stack

- **Language:** Python 3.12
- **GUI toolkit:** GTK 4.14.5 + libadwaita 1.5.0
- **GUI bindings:** PyGObject (gi)
- **Serial communication:** pyserial 3.5
- **Charting:** Cairo (native to GTK, direct drawing via `Gtk.DrawingArea`)
- **Linting/Formatting:** ruff 0.15.7
- **Type checking:** mypy 1.19.1
- **i18n:** gettext (English source, German translation)
- **Testing:** pytest + pytest-cov
- **Git hooks:** pre-commit (ruff, ruff-format, mypy, trailing-whitespace, etc.)
- **System packages:** `gir1.2-gtk-4.0 gir1.2-adw-1`

## Project Structure

```
Voltcraft CM 2016/
├── src/cm2016/
│   ├── __init__.py
│   ├── app.py                  # Adw.Application, main window, entry point
│   ├── protocol.py             # Frame parser, enums, data classes
│   ├── serial_reader.py        # Serial I/O, frame sync, background thread
│   ├── session.py              # In-memory data store, per-slot time series
│   ├── i18n.py                 # gettext setup, _() export
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── slot_panel.py       # Single slot info panel
│   │   ├── slot_sidebar.py     # Sidebar with 6 slot panels
│   │   ├── data_table.py       # ColumnView data table
│   │   ├── chart_widget.py     # Cairo chart drawing area
│   │   ├── chart_toolbar.py    # Chart style selector, zoom controls
│   │   └── port_dialog.py      # Serial port selection dialog
│   ├── export/
│   │   ├── __init__.py
│   │   ├── csv_export.py
│   │   ├── excel_export.py
│   │   └── printer.py
│   └── persistence/
│       ├── __init__.py
│       ├── file_io.py          # Save/load session files
│       └── temp_buffer.py      # Crash recovery temp files
├── po/
│   ├── POTFILES.in
│   ├── cm2016.pot              # Generated template
│   └── de.po                   # German translation
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Sample frames, mock serial, fixtures
│   ├── test_protocol.py
│   ├── test_serial_reader.py
│   ├── test_session.py
│   ├── test_data_table.py
│   ├── test_chart_widget.py
│   ├── test_csv_export.py
│   ├── test_excel_export.py
│   ├── test_file_io.py
│   ├── test_temp_buffer.py
│   └── test_printer.py
├── CLAUDE.md
├── LICENSE
├── pyproject.toml
├── .pre-commit-config.yaml
├── .gitignore
└── manual-*.pdf                # Device manual (not committed)
```

## Development Setup

```bash
python3 -m venv --system-site-packages .venv   # Reuse system PyGObject/cairo
source .venv/bin/activate.fish                  # Or activate / activate.csh
pip install -e .                                # Install in dev mode
```

**Note:** `--system-site-packages` is required because PyGObject/pycairo need
system-installed GObject introspection libraries (`python3-gi`, `python3-gi-cairo`,
`gir1.2-gtk-4.0`, `gir1.2-adw-1`). Building them from source in a venv requires
dev headers that are not worth the trouble.

## Development Commands

```bash
ruff check src/ tests/           # Lint (E402 ignored for gi.require_version)
ruff format src/ tests/          # Format
mypy src/                        # Type check
pytest                           # Run tests
pytest --cov=cm2016              # Tests with coverage
cm2016                           # Run app (venv must be active)
```

## Existing Projects / References

- **[tarator/cm2016](https://gitlab.projecttac.com/tarator/cm2016)** - Java CLI, RXTX library, detailed protocol parser
- **[michael-wahler/CM2016](https://github.com/michael-wahler/CM2016)** - Python CLI, pyserial, optional MySQL logging
- **[sarnau/cm2016](https://github.com/sarnau/cm2016)** - Python CLI, matplotlib live-plot, CSV logging
- **[Leisenfels BattMan](https://www.leisenfels.com/products/battman)** - Commercial Java GUI (only existing Linux GUI, 30-day trial)
- **[Leisenfels protocol docs](https://www.leisenfels.com/howto-charge-manager-2016-data-format)** - Original protocol reverse engineering

## Open Questions

- [ ] Checksum algorithm (last 2 bytes) - unknown, not validated by any existing project
- [x] ~~D-CAP byte order~~ — verified: normal LE, no swap needed (2026-03-21)
- [x] ~~C-CAP/D-CAP size~~ — 32-bit LE (not 24-bit), bytes [10-13] and [14-17]. No unknown bytes in slot structure (2026-03-21)
