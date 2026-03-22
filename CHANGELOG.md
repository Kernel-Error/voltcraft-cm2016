# Changelog

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
