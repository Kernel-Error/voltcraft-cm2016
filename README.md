# Charge Manager CM 2016

Open-source Linux GUI for the **Voltcraft Charge Manager CM 2016** battery charger.
Replaces the Windows-only CM2016 Logger V2.10 software with a native
GTK 4 / libadwaita desktop application.

## Features

- **Real-time monitoring** of all 6 charging slots (4x AA/AAA + 2x 9V block)
- **Auto-detect** CM2016 device via USB (Silicon Labs CP210x)
- **Data table** with autoscroll, slot filtering, and clipboard support
- **Voltage and current charts** with line/bar styles and time window control
- **Chart interaction** -- drag zoom, scroll wheel, keyboard navigation, data point tooltips
- **Export** to CSV and spreadsheet (.xlsx) with embedded charts
- **Print** measurement reports (DIN A4/A3 landscape)
- **Save/load** recording sessions with crash recovery
- **Sleep inhibit** prevents system suspend during recording
- **7 languages**: English, German, French, Dutch, Italian, Spanish, Polish

## Screenshots

*Coming soon*

## Requirements

- Linux with GTK 4.14+ and libadwaita 1.5+
- Python 3.10+
- System packages:
  - Debian/Ubuntu/Mint: `sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1`
  - Fedora: `sudo dnf install python3-gobject gtk4 libadwaita`
  - Arch: `sudo pacman -S python-gobject gtk4 libadwaita`

## Installation

```bash
git clone https://github.com/Kernel-Error/voltcraft-cm2016.git
cd voltcraft-cm2016
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .
```

## Usage

Connect the CM2016 via USB cable, then:

```bash
cm2016
```

The application auto-detects the device. Click **Start Logging** to begin recording.

See [docs/manual.md](docs/manual.md) for the full user manual.

## Device

The Voltcraft CM 2016 is a charger/manager for AA/AAA NiMH rechargeable batteries
with 6 independent charging slots. It connects via USB-B using a Silicon Labs CP210x
USB-to-UART bridge chip and transmits measurement data every 2 seconds.

Supported charging programs: Charge, Discharge, Check, Cycle, Alive.

## Development

```bash
source .venv/bin/activate
ruff check src/ tests/          # Lint
ruff format src/ tests/         # Format
mypy src/                       # Type check
pytest                          # Run tests (135 tests)
pytest --cov=cm2016             # Tests with coverage
```

## License

[MIT](LICENSE) -- Sebastian van de Meer aka Kernel-Error
