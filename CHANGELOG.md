# Changelog

## [0.1.2] - 2026-03-22

### Fixed

- Connection-lost path now properly closes the serial port and cleans up
  state by delegating to `_stop_logging()` with signal blocking (#6)
- `locale.setlocale()` crash on misconfigured systems caught gracefully
  with fallback to English (#7)
- Trickle vs charging misclassification when status_byte is 0x07: step
  value now takes priority over status byte (#9)
- Disconnect timeout raised from 2s to 5s to prevent false disconnects
  caused by USB/OS timing jitter (#10)

### Added

- Test coverage for printer, data_table, chart_widget, i18n, and
  disconnect timeout modules (#13)

## [0.1.1] - 2026-03-22

### Fixed

- Thread-safety: protect Session data store with RLock, return copies from
  `get_slot_data()` and `get_all_data()` to prevent data races (#1)
- Chart zoom viewport treated `0.0` as unset due to falsy or-pattern,
  breaking zoom when a boundary was legitimately at zero (#2)
- Division by zero crash in chart drawing with a single data point,
  constant values, or degenerate zoom viewport (#3)
- Excel export passed two separate user_data arguments to the GTK async
  callback instead of a tuple, causing the sheet name to be lost (#5)

## [0.1.0] - 2026-03-21

Initial release with full feature parity to the Windows CM2016 Logger V2.10.
