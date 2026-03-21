# Charge Manager CM 2016 -- User Manual

Version 0.1.0

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [System Requirements](#2-system-requirements)
3. [Installation](#3-installation)
4. [Quick Start](#4-quick-start)
5. [Main Window Overview](#5-main-window-overview)
6. [Connecting to the Device](#6-connecting-to-the-device)
7. [Recording Data](#7-recording-data)
8. [Slot Panels](#8-slot-panels)
9. [Data Table](#9-data-table)
10. [Charts](#10-charts)
11. [Chart Interaction](#11-chart-interaction)
12. [Exporting Data](#12-exporting-data)
13. [Printing](#13-printing)
14. [Saving and Loading Sessions](#14-saving-and-loading-sessions)
15. [Crash Recovery](#15-crash-recovery)
16. [Clear Data](#16-clear-data)
17. [Sleep Inhibit](#17-sleep-inhibit)
18. [Languages](#18-languages)
19. [Keyboard Shortcuts Reference](#19-keyboard-shortcuts-reference)
20. [Troubleshooting](#20-troubleshooting)

---

## 1. Introduction

Charge Manager CM 2016 is a free, open-source Linux desktop application for
monitoring and logging data from the **Voltcraft Charge Manager CM 2016**
battery charger. It replaces the Windows-only CM2016 Logger V2.10 software with
a native GTK 4 / libadwaita interface that follows modern GNOME design
guidelines.

The Voltcraft CM 2016 is a charger/manager for AA and AAA NiMH and NiCd
rechargeable batteries. It has **six independent charging slots**: four standard
slots (Slot 1 through Slot 4) and two 9 V block battery slots (Slot A and
Slot B). The device connects to a computer over USB using a Silicon Labs CP210x
USB-to-UART bridge and transmits live measurement data every two seconds.

**Key features of this application:**

- Real-time display of all six charging slots with live parameters
- Data logging with a filterable, scrollable table view
- Voltage and current charts with charge/discharge color coding
- CSV and Excel (.xlsx) export with embedded charts
- Print measurement reports
- Save and load recording sessions (.cm2016 files)
- Automatic crash recovery from temporary files
- Seven supported interface languages
- System sleep inhibit during active recording

---

## 2. System Requirements

### Operating System

- Linux with GTK 4.14+ and libadwaita 1.5+
- Tested on Ubuntu 24.04+, Fedora 40+, and Arch Linux

### System Packages

The following system packages must be installed before the application can run:

**Debian / Ubuntu:**

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
```

**Fedora:**

```bash
sudo dnf install python3-gobject gtk4 libadwaita
```

**Arch Linux:**

```bash
sudo pacman -S python-gobject gtk4 libadwaita
```

### Python

- Python 3.10 or newer

### Hardware

- Voltcraft Charge Manager CM 2016 connected via USB
- The `cp210x` kernel module (included in the default kernel on all major
  distributions)

---

## 3. Installation

### Step 1: Create a Virtual Environment

Because the application uses PyGObject (GTK bindings), the virtual environment
must have access to system-installed packages:

```bash
python3 -m venv --system-site-packages .venv
```

### Step 2: Activate the Environment

```bash
# Bash / Zsh
source .venv/bin/activate

# Fish
source .venv/bin/activate.fish
```

### Step 3: Install the Application

```bash
pip install -e .
```

This installs the `cm2016` command and all Python dependencies (pyserial,
openpyxl).

### Step 4: Run

```bash
cm2016
```

The application window opens. If a CM 2016 device is connected, it will be
auto-detected.

---

## 4. Quick Start

1. **Connect the Voltcraft CM 2016** to your computer using the USB cable.
2. **Launch the application** by running `cm2016` in your terminal.
3. The application auto-detects the CM 2016 if it is the only Silicon Labs
   CP210x device on the system. If not, click **Port** in the header bar to
   select the correct serial port manually.
4. Click **Start Logging** in the header bar. The button changes to
   **Stop Logging** and the slot panels turn green to indicate active recording.
5. Insert batteries into the charger and start a charging program on the device.
   Data appears in the slot panels, table, and charts within seconds.
6. When finished, click **Stop Logging**. Use **Export** to save your data as
   CSV or Excel, or use **File > Save Logged Data** to save the full session.

---

## 5. Main Window Overview

The main window is divided into the following areas:

```
+--------------------------------------------------------------+
|  Header Bar: File | Port | Start Logging | Export | Print    |
|                              Display [v] | About | Clear Data|
+----------+-----------------------------------------------+---+
|          |                                                |
|  Slot    |  Content Area                                  |
|  Sidebar |  (Table view or Charts view, selected via      |
|          |   the Display dropdown)                        |
|  Slot 1  |                                                |
|  Slot 2  |                                                |
|  Slot 3  |                                                |
|  Slot 4  |                                                |
|  Slot A  |                                                |
|  Slot B  |                                                |
|          |                                                |
+----------+------------------------------------------------+
|  Status Bar: "Select a port and click Start Logging"       |
+------------------------------------------------------------+
```

### Header Bar (left to right)

| Element            | Description                                          |
|--------------------|------------------------------------------------------|
| **File**           | Menu with Save Logged Data and Load Logged Data      |
| **Port**           | Opens the serial port selection dialog                |
| **Start Logging**  | Starts/stops data recording (toggles to Stop Logging)|
| **Export**          | Menu with CSV and Spreadsheet (.xlsx) options         |
| **Print**          | Print a measurement report for the selected slot     |

### Header Bar (right side)

| Element            | Description                                          |
|--------------------|------------------------------------------------------|
| **Display**        | Dropdown to switch between Table and Charts view     |
| **About**          | Shows version and license information                |
| **Clear Data**     | Deletes all recorded data (with confirmation)        |

### Sidebar

Six slot panels showing live data for each charging slot. Click a panel to
select that slot for the table filter and chart display.

### Content Area

Shows either the data table or the charts, depending on the Display dropdown
selection.

### Status Bar

Displays the current application state:
- "Select a port and click Start Logging" -- initial state
- "Waiting For Data" -- connected but no frames received yet
- "Recording -- N data points" -- actively recording
- "Logging stopped" -- recording stopped by the user

---

## 6. Connecting to the Device

### Automatic Detection

When the application starts, it scans for Silicon Labs CP210x USB-to-UART
devices (vendor ID `10C4`, product ID `EA60`). If exactly one such device is
found, it is automatically selected as the serial port. The **Port** button in
the header bar updates to show the device name (e.g., `ttyUSB0`).

### Manual Port Selection

If auto-detection does not find the device (for example, if you have multiple
USB-serial adapters), click the **Port** button to open the port selection
dialog:

1. The dialog shows a dropdown listing all available `/dev/ttyUSB*` devices with
   their descriptions.
2. If you plugged in the device after opening the dialog, click **Refresh** to
   rescan.
3. Select the correct port and click **OK**.

If you click **Start Logging** without having selected a port, the port
selection dialog opens automatically.

### Changing the Port

You can change the serial port at any time by clicking the **Port** button.
There is no need to restart the application.

### Permissions

Your user account must have read access to the serial device. On most
distributions, this means being a member of the `dialout` group:

```bash
sudo usermod -aG dialout $USER
```

Log out and back in for the group change to take effect.

---

## 7. Recording Data

### Starting a Recording

Click the **Start Logging** button in the header bar. The application:

1. Opens the serial port connection to the CM 2016.
2. Changes the button label to **Stop Logging** (with a red background).
3. Turns all slot panel backgrounds from gray to green.
4. Begins listening for data frames from the device.
5. Inhibits system sleep to prevent data loss (see
   [Sleep Inhibit](#17-sleep-inhibit)).
6. Creates temporary recovery files in the background (see
   [Crash Recovery](#15-crash-recovery)).

The status bar shows "Waiting For Data" until the first frame arrives, then
switches to "Recording -- N data points" with a running count.

### Stopping a Recording

Click **Stop Logging**. The button reverts to **Start Logging** (blue), slot
panels return to gray, the Print button becomes available again, and system
sleep inhibit is released.

### Auto-Disconnect Detection

If the CM 2016 is switched off or the USB cable is disconnected during
recording, the application automatically stops logging and shows a notification:

> Recording stopped: CM2016 switched off or disconnected

### Auto-Clear on Battery Removal

When a battery is removed from a slot during an active recording, the data for
that slot is automatically cleared. This prevents stale data from mixing with a
new battery's measurements.

---

## 8. Slot Panels

The left sidebar contains six panels, one for each charging slot. Each panel
displays eight live parameters:

| Parameter     | Description                                              |
|---------------|----------------------------------------------------------|
| **Program**   | The charging program selected on the device: Charge, Discharge, Cycle, Check, or Alive |
| **Actual**    | The current operation status: Ready, Charge, Discharge, Error, or Trickle |
| **Chemistry** | Battery chemistry type: NiMH or NiZn                     |
| **Time**      | Elapsed runtime in HH:MM format                          |
| **C-CAP**     | Charge capacity accumulated so far, in mAh               |
| **D-CAP**     | Discharge capacity accumulated so far, in mAh            |
| **Voltage**   | Current battery voltage in volts (e.g., 1.425 V)         |
| **Current**   | Current charge or discharge current in amperes (e.g., 0.500 A) |

### Visual Indicators

- **Gray background**: Idle (not recording)
- **Green background**: Recording is active

### Slot Selection

Click any slot panel to select it. The selected slot determines:

- Which slot's data is shown in the data table (filtered view)
- Which slot's data is plotted in the charts

---

## 9. Data Table

The data table displays logged measurement records in a scrollable column view.
Switch to the table view using the **Display** dropdown (select "Table").

### Columns

| Column         | Description                          |
|----------------|--------------------------------------|
| Slot           | Slot number (1--4, A, B)             |
| Time           | Elapsed runtime                      |
| Program        | Charging program                     |
| Actual         | Current status                       |
| Voltage (V)    | Voltage reading                      |
| Current (A)    | Current reading                      |
| CCAP (mAh)     | Charge capacity                      |
| DCAP (mAh)     | Discharge capacity                   |
| Chemistry      | Battery type                         |

### Slot Filtering

When you click a slot in the sidebar, the table filters to show only records
from that slot. The filter label at the top-left of the table updates to show
the selected slot name (e.g., "Slot 1") or "All Slots" if no filter is active.

### Autoscroll

The **Autoscroll** toggle button (top-right of the table toolbar) keeps the
table scrolled to the latest row as new data arrives. Click it to disable
autoscroll if you want to examine older data without the view jumping.

### Clipboard Operations

**Right-click context menu:**

| Menu Item              | Action                                      |
|------------------------|---------------------------------------------|
| Copy Selected Rows     | Copies selected rows as tab-separated values|
| Copy All Rows          | Copies all visible (filtered) rows as TSV   |

**Keyboard shortcut:**

- **Ctrl+C** copies the currently selected rows to the clipboard in
  tab-separated format, ready to paste into spreadsheet applications like
  LibreOffice Calc.

Rows can be selected using standard multi-selection (click, Shift+click,
Ctrl+click).

---

## 10. Charts

The charts view shows two graphs stacked vertically. Switch to the chart view
using the **Display** dropdown (select "Charts").

### Voltage Chart (upper)

Plots **Voltage [V]** on the Y-axis against **Time** on the X-axis.

### Current Chart (lower)

Plots **Current [A]** on the Y-axis against **Time** on the X-axis.

### Color Coding

| Color   | Meaning                                                    |
|---------|------------------------------------------------------------|
| Green   | Charging or trickle charging                               |
| Red     | Discharging                                                |
| Gray    | Gap in data (recording pause or missing data points)       |
| Yellow  | Final voltage annotation (shown when a program completes)  |

### Chart Styles

Above the charts, the **Style** toolbar provides two rendering modes:

| Style    | Description                                              |
|----------|----------------------------------------------------------|
| **Lines**| Data points connected by line segments (default)         |
| **Bar**  | Vertical bar chart; bar height represents absolute value |

Click the **Lines** or **Bar** toggle button to switch styles. Both charts
update simultaneously.

### Time Window Control

At the top of the charts view, a time window toolbar controls how much data is
visible:

| Button | Tooltip         | Action                                       |
|--------|-----------------|----------------------------------------------|
| **+**  | Show more time  | Widens the time window to the next preset    |
| **-**  | Show less time  | Narrows the time window to the previous preset|

The current window size is shown between the buttons (e.g., "Time window:
5 min"). Available presets are: 1 min, 2 min, 5 min (default), 10 min, 20 min,
30 min, 1h, 2h, and All.

When set to a specific duration, only the most recent data within that window is
displayed. Setting the window to "All" shows the entire recording.

### Final Voltage Annotation

When a charging program completes (the slot becomes idle after being active), a
yellow annotation appears at the last data point showing the final voltage
value. This makes it easy to see the end-of-charge voltage at a glance.

---

## 11. Chart Interaction

The charts support several methods of interactive navigation and inspection.

### Mouse Drag Zoom

Click and drag on a chart to draw a selection rectangle. When you release the
mouse button, the chart zooms into the selected area. The rectangle must be at
least 5 pixels wide and tall to register as a zoom action.

### Scroll Wheel Zoom

- **Scroll up** zooms in (narrows the view)
- **Scroll down** zooms out (widens the view)

Zooming is centered on the current viewport center.

### Right-Click Context Menu

Right-click on an empty area of the chart to open the context menu:

| Menu Item       | Action                                     |
|-----------------|--------------------------------------------|
| **Zoom In**     | Zooms in 2x centered on the viewport       |
| **Reset Zoom**  | Returns to the default auto-fit view        |

### Data Point Tooltip

Right-click near a data point on the curve (within 20 pixels) to see a tooltip
popup showing:

| Field         | Example          |
|---------------|------------------|
| Actual Mode   | Charge           |
| Voltage       | 1.425 V          |
| Current       | 0.500 A          |
| Time          | 01:23            |

### Keyboard Shortcuts (Charts)

When a chart has keyboard focus (click on it first):

| Key            | Action                                        |
|----------------|-----------------------------------------------|
| Left Arrow     | Pan left (10% of visible range)               |
| Right Arrow    | Pan right (10% of visible range)              |
| Up Arrow       | Pan up (10% of visible range)                 |
| Down Arrow     | Pan down (10% of visible range)               |
| Page Up        | Pan right by 50% of visible range             |
| Page Down      | Pan left by 50% of visible range              |
| Home           | Reset zoom (fit all data)                     |
| Delete         | Jump to the start of the data                 |
| End            | Jump to the end of the data                   |
| Backspace      | Undo the last zoom step                       |

The zoom history is maintained as a stack. Each zoom action (drag, scroll, or
menu) pushes the previous viewport onto the stack. Pressing Backspace pops the
stack and returns to the previous view. Pressing Home clears the stack entirely.

---

## 12. Exporting Data

Exports always apply to the **currently selected slot** (the one highlighted in
the sidebar). If no data exists for the selected slot, a notification appears:
"No data to export."

### CSV Export

1. Click **Export** in the header bar.
2. Select **CSV** from the dropdown menu.
3. A file save dialog opens with a suggested filename
   (e.g., `CM2016_Slot1_2026-03-21.csv`).
4. Choose a location and click Save.

The CSV file contains one header row and one data row per measurement point,
with columns: Slot, Time, Program, Actual, Voltage (V), Current (A),
CCAP (mAh), DCAP (mAh), Chemistry.

### Spreadsheet (.xlsx) Export

1. Click **Export** in the header bar.
2. Select **Spreadsheet (.xlsx)** from the dropdown menu.
3. A file save dialog opens with a suggested filename
   (e.g., `CM2016_Slot1_2026-03-21.xlsx`).
4. Choose a location and click Save.

The Excel file includes the same data columns as the CSV export, plus embedded
voltage and current chart images within the spreadsheet.

---

## 13. Printing

Click the **Print** button in the header bar to print a measurement report for
the currently selected slot.

- The print dialog uses the standard GTK print dialog, allowing you to choose a
  printer, set page size, and configure other print options.
- **Recommended format:** DIN A4 or A3, landscape orientation.
- The report includes an auto-generated title line with the slot number, elapsed
  time, and charge/discharge capacity values.
- Charts are printed as currently displayed, respecting the current zoom level
  and chart style.

**Note:** The Print button is **disabled during active recording**. Stop
recording first, then print.

---

## 14. Saving and Loading Sessions

### Saving

To save all recorded data across all slots:

1. Go to **File > Save Logged Data** (or press **Ctrl+S**).
2. A file save dialog opens with a suggested filename `recording.cm2016`.
3. Choose a location and click Save.

The `.cm2016` file format preserves all slot data and can be loaded again later.
If there is no data to save, a notification appears: "No data to save."

### Loading

To load a previously saved session:

1. Go to **File > Load Logged Data** (or press **Ctrl+O**).
2. Select a `.cm2016` file and click Open.

Loading a file **replaces** the current session data. The status bar shows the
number of records loaded (e.g., "42 data points loaded"). All slot panels,
table, and charts update to reflect the loaded data.

---

## 15. Crash Recovery

The application automatically buffers recorded data to temporary files in the
background during every recording session. If the application or system crashes
unexpectedly, this data is preserved.

### Recovery on Startup

When the application starts and detects recovery data from a previous session,
a dialog appears:

> **Continue last recording?**
>
> Recovery data from a previous session was found.
>
> [No] [Yes]

- Click **Yes** to restore the recovered data. The session is loaded and you can
  continue recording or export the data.
- Click **No** to discard the recovery data and start fresh.

Recovery data is automatically deleted after the dialog is dismissed, regardless
of your choice.

---

## 16. Clear Data

To delete all recorded data across all slots:

1. Click the **Clear Data** button (red, right side of the header bar).
2. A confirmation dialog appears:

   > **Clear Data**
   >
   > Delete all recorded data for all slots?
   >
   > [Cancel] [Clear]

3. Click **Clear** to confirm. All slot panels, the data table, and the charts
   are reset. The status bar shows "All data cleared."
4. Click **Cancel** to keep your data.

---

## 17. Sleep Inhibit

When recording is active, the application prevents the system from entering
sleep or suspend mode. This ensures that long-running charging sessions
(which can last many hours) are not interrupted by power management.

Sleep inhibit is automatically released when you stop recording or when the
connection is lost.

---

## 18. Languages

The application interface is available in seven languages:

| Language | Locale Code |
|----------|-------------|
| English  | `en`        |
| German   | `de`        |
| French   | `fr`        |
| Dutch    | `nl`        |
| Italian  | `it`        |
| Spanish  | `es`        |
| Polish   | `pl`        |

The language is determined by your system locale. The application reads the
`LANG` environment variable at startup.

### Changing the Language

To run the application in a specific language, set the `LANG` environment
variable before launching:

```bash
# German
LANG=de_DE.UTF-8 cm2016

# French
LANG=fr_FR.UTF-8 cm2016

# Dutch
LANG=nl_NL.UTF-8 cm2016

# Italian
LANG=it_IT.UTF-8 cm2016

# Spanish
LANG=es_ES.UTF-8 cm2016

# Polish
LANG=pl_PL.UTF-8 cm2016

# English (default)
LANG=en_US.UTF-8 cm2016
```

If no translation is available for the active locale, the interface defaults to
English.

---

## 19. Keyboard Shortcuts Reference

### Application-Wide

| Shortcut   | Action                             |
|------------|------------------------------------|
| Ctrl+S     | Save Logged Data                   |
| Ctrl+O     | Load Logged Data                   |
| Ctrl+C     | Copy selected table rows to clipboard |

### Chart Navigation (when chart is focused)

| Shortcut   | Action                             |
|------------|------------------------------------|
| Left        | Pan left (10% of view)            |
| Right       | Pan right (10% of view)           |
| Up          | Pan up (10% of view)              |
| Down        | Pan down (10% of view)            |
| Page Up     | Pan right (50% of view)           |
| Page Down   | Pan left (50% of view)            |
| Home        | Reset zoom (fit all data)         |
| End         | Jump to end of data               |
| Delete      | Jump to start of data             |
| Backspace   | Undo last zoom step               |

### Chart Mouse Controls

| Action              | Effect                            |
|---------------------|-----------------------------------|
| Left-click drag     | Draw zoom rectangle               |
| Scroll wheel up     | Zoom in                           |
| Scroll wheel down   | Zoom out                          |
| Right-click (curve) | Show data point tooltip           |
| Right-click (empty) | Open context menu (Zoom In / Reset Zoom) |

---

## 20. Troubleshooting

### The device is not detected on startup

- Ensure the CM 2016 is connected via USB and powered on.
- Check that the `cp210x` kernel module is loaded:
  ```bash
  lsmod | grep cp210x
  ```
- Verify the device appears as a serial port:
  ```bash
  ls /dev/ttyUSB*
  ```
- If you have multiple USB-serial adapters, auto-detection only works when
  exactly one CP210x device is present. Use the **Port** button to select
  manually.

### "Failed to connect to port" error

- Check that your user has permission to access the serial device:
  ```bash
  ls -l /dev/ttyUSB0
  ```
  You should be a member of the `dialout` group (or `uucp` on Arch Linux):
  ```bash
  sudo usermod -aG dialout $USER
  ```
  Log out and back in for the change to take effect.
- Make sure no other application (such as a serial terminal) is using the same
  port.

### No data appears after clicking Start Logging

- The status bar should show "Waiting For Data." The CM 2016 only transmits data
  when batteries are inserted and a program is running. Insert a battery and
  start a charging program on the device.
- If the status bar stays on "Waiting For Data" indefinitely, verify you
  selected the correct port. Open the **Port** dialog and try a different
  device.

### Recording stops unexpectedly

- If you see "Recording stopped: CM2016 switched off or disconnected," the USB
  connection was interrupted. Check the cable and reconnect.
- If the charger was intentionally turned off, this is expected behavior.

### Charts show no data

- Make sure the **Display** dropdown is set to "Charts."
- Click on a slot panel in the sidebar to select the slot you want to view.
- If the slot has no recorded data, the chart displays "No data."

### Application does not start

- Ensure system packages are installed (see [System Requirements](#2-system-requirements)).
- Check that the virtual environment was created with `--system-site-packages`:
  ```bash
  python3 -m venv --system-site-packages .venv
  source .venv/bin/activate
  pip install -e .
  cm2016
  ```
- Look for error messages in the terminal output.

### Export produces an empty file

- Exports apply to the **selected slot only**. Make sure the selected slot has
  recorded data. Click a slot in the sidebar to select it.

### Print button is grayed out

- The Print button is disabled during active recording. Click **Stop Logging**
  first, then print.

---

*Charge Manager CM 2016 is licensed under the MIT License.*
*Copyright 2026 Sebastian van de Meer aka Kernel-Error.*
