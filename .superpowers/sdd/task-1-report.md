# Task 1 Report: Shared Spatial Metadata Helper

## What I implemented
- Added `scripts/lib/spatial_metadata.py` with the shared helper functions:
  - `parse_floor_orientation`
  - `parse_cell_spatial`
  - `is_outdoor_like`
  - `window_issue_level`
  - `nearest_declared_side`
- Added `tests/conftest.py` so `scripts/` is importable during pytest runs.
- Added `tests/test_spatial_metadata.py` covering orientation parsing, spatial parsing, outdoor detection, window issue classification, and nearest-side inference.
- Added `requirements-dev.txt` with `pytest>=8.0,<9.0`.

## What I tested and test results
- Installed dev dependencies:
  - `python -m pip install -r requirements-dev.txt`
- Ran the focused test file:
  - `python -m pytest tests/test_spatial_metadata.py -v`
- Result: 9 tests passed.

## TDD evidence

### RED
Command:
```powershell
python -m pytest tests/test_spatial_metadata.py -v
```

Output:
```text
============================= test session starts ==============================
platform win32 -- Python 3.14.0, pytest-8.4.2, pluggy-1.6.0 -- C:\Python314\python.exe
cachedir: .pytest_cache
rootdir: D:\I29786\workspace\houseDesignPrepare\.worktrees\workflow-optimization
plugins: anyio-4.13.0
collecting ... collected 0 items / 1 error

==================================== ERRORS ====================================
_______________ ERROR collecting tests/test_spatial_metadata.py _______________
ImportError while importing test module 'D:\I29786\workspace\houseDesignPrepare\.worktrees\workflow-optimization\tests\test_spatial_metadata.py'.
Traceback:
tests\test_spatial_metadata.py:3: in <module>
    from lib.spatial_metadata import (
E   ModuleNotFoundError: No module named 'lib.spatial_metadata'
=========================== short test summary info ============================
ERROR tests/test_spatial_metadata.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
============================== 1 error in 0.33s ===============================
```

### GREEN
Command:
```powershell
python -m pytest tests/test_spatial_metadata.py -v
```

Output:
```text
============================= test session starts ==============================
platform win32 -- Python 3.14.0, pytest-8.4.2, pluggy-1.6.0 -- C:\Python314\python.exe
cachedir: .pytest_cache
rootdir: D:\I29786\workspace\houseDesignPrepare\.worktrees\workflow-optimization
plugins: anyio-4.13.0
collecting ... collected 9 items

tests/test_spatial_metadata.py::test_parse_floor_orientation_normalizes_known_sides PASSED
tests/test_spatial_metadata.py::test_parse_floor_orientation_defaults_unknown_sides PASSED
tests/test_spatial_metadata.py::test_parse_cell_spatial_prefers_explicit_values_and_outdoor_role PASSED
tests/test_spatial_metadata.py::test_outdoor_window_zero_is_not_a_warning PASSED
tests/test_spatial_metadata.py::test_indoor_window_zero_is_warning PASSED
tests/test_spatial_metadata.py::test_indoor_missing_window_is_warning PASSED
tests/test_spatial_metadata.py::test_outdoor_missing_window_is_not_a_warning PASSED
tests/test_spatial_metadata.py::test_nearest_declared_side_detects_front_and_rear PASSED
tests/test_spatial_metadata.py::test_nearest_declared_side_marks_large_spanning_cells_ambiguous PASSED

============================== 9 passed in 0.11s ==============================
```

## Files changed
- `requirements-dev.txt`
- `scripts/lib/spatial_metadata.py`
- `tests/conftest.py`
- `tests/test_spatial_metadata.py`
- `.superpowers/sdd/task-1-report.md`

## Self-review findings
- The helper is intentionally small and matches the brief’s interfaces exactly.
- The test coverage exercises the behavior the task brief called out, including the RED/GREEN path.
- No unrelated files were modified.

## Issues or concerns
- None.
