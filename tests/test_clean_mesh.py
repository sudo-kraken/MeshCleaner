from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import clean_mesh


@pytest.fixture
def tmp_in_out(tmp_path):
    """Create input and output folders for tests."""
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    return in_dir, out_dir


@pytest.fixture
def example_stl_path():
    """
    Locate a real STL named 'test.stl' in the repository root.
    If it is not present, tests that rely on it will be skipped.
    """
    repo_root = Path(__file__).resolve().parents[1]
    stl = repo_root / "test.stl"
    if not stl.exists():
        pytest.skip("test.stl not found in repository root; skipping integration test")
    return stl


# -----------------------
# Unit tests: pure logic
# -----------------------

def test_select_main_component_first():
    """Selecting 'first' returns the first component."""
    c1, c2 = MagicMock(area=10.0, volume=5.0), MagicMock(area=1.0, volume=0.1)
    result = clean_mesh.select_main_component([c1, c2], method="first")
    assert result is c1


def test_select_main_component_ratio():
    """Selecting 'ratio' picks the lowest area/volume ratio."""
    c1, c2 = MagicMock(area=10.0, volume=5.0), MagicMock(area=1.0, volume=0.1)
    result = clean_mesh.select_main_component([c1, c2], method="ratio")
    assert result is c1


def test_select_main_component_ratio_handles_tiny_volume():
    """Guard against division by near zero volume."""
    c1 = MagicMock(area=10.0, volume=0.0)
    c2 = MagicMock(area=9.0, volume=9.0)
    result = clean_mesh.select_main_component([c1, c2], method="ratio")
    assert result is c2


# -----------------------------------
# Unit tests: process_file with mocks
# -----------------------------------

def test_process_file_single_component(tmp_path):
    """When mesh has one component, it is exported as is."""
    in_file = tmp_path / "input.stl"
    out_file = tmp_path / "output.stl"
    in_file.write_text("dummy")

    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [fake_mesh]

    with patch("clean_mesh.trimesh.load", return_value=fake_mesh):
        ok = clean_mesh.process_file(in_file, out_file, method="first")

    assert ok is True
    fake_mesh.export.assert_called_once_with(out_file)


def test_process_file_multi_component_uses_selector(tmp_path):
    """When multiple components exist, selector decides which to export."""
    in_file = tmp_path / "input.stl"
    out_file = tmp_path / "output.stl"
    in_file.write_text("dummy")

    comp1, comp2 = MagicMock(name="comp1"), MagicMock(name="comp2")
    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [comp1, comp2]

    with patch("clean_mesh.trimesh.load", return_value=fake_mesh), patch(
        "clean_mesh.select_main_component", return_value=comp2
    ) as sel:
        ok = clean_mesh.process_file(in_file, out_file, method="ratio")

    assert ok is True
    sel.assert_called_once()
    comp2.export.assert_called_once_with(out_file)


def test_process_file_catches_exception(tmp_path):
    """Errors are logged and result is False."""
    in_file = tmp_path / "bad.stl"
    out_file = tmp_path / "out.stl"
    in_file.write_text("dummy")

    with patch("clean_mesh.trimesh.load", side_effect=RuntimeError("boom")):
        ok = clean_mesh.process_file(in_file, out_file)

    assert ok is False


# ---------------------------------------
# Unit tests: process_directory and CLI
# ---------------------------------------

def test_process_directory_no_input(tmp_path):
    out_dir = tmp_path / "out"
    processed = clean_mesh.process_directory(tmp_path / "missing", out_dir, formats=["stl"])
    assert processed == 0


def test_process_directory_happy_path(tmp_in_out):
    in_dir, out_dir = tmp_in_out
    (in_dir / "a.stl").write_text("a")
    (in_dir / "b.stl").write_text("b")

    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [fake_mesh]

    def _export_writes(pathlike):
        p = Path(pathlike)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"mock")
        return True

    fake_mesh.export.side_effect = _export_writes

    with patch("clean_mesh.trimesh.load", return_value=fake_mesh):
        processed = clean_mesh.process_directory(in_dir, out_dir, formats=["stl"], method="first", verbose=True)

    assert processed == 2
    assert (out_dir / "a.stl").exists()
    assert (out_dir / "b.stl").exists()


def test_cli_main_exit_codes(tmp_in_out):
    """CLI returns 0 when at least one file is processed, else 1."""
    in_dir, out_dir = tmp_in_out
    (in_dir / "x.stl").write_text("x")

    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [fake_mesh]

    def _export_writes(pathlike):
        p = Path(pathlike)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"mock")
        return True

    fake_mesh.export.side_effect = _export_writes

    with patch("clean_mesh.trimesh.load", return_value=fake_mesh):
        code_ok = clean_mesh.main(
            [
                "--input",
                str(in_dir),
                "--output",
                str(out_dir),
                "--formats",
                "stl",
                "--method",
                "first",
            ]
        )
    assert code_ok == 0

    # Empty input dir returns 1
    empty_in = out_dir / "empty"
    empty_in.mkdir()
    code_empty = clean_mesh.main(["-i", str(empty_in), "-o", str(out_dir)])
    assert code_empty == 1


# ---------------------------------------
# Integration test using real test.stl
# ---------------------------------------

def test_integration_real_stl(example_stl_path, tmp_path):
    """
    Uses a real STL file if provided in the repo root as 'test.stl'.
    Ensures we can load, split and export without mocking.
    """
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    # Copy the STL into the temp input directory
    in_file = in_dir / example_stl_path.name
    in_file.write_bytes(example_stl_path.read_bytes())

    processed = clean_mesh.process_directory(in_dir, out_dir, formats=["stl"], method="first", verbose=True)
    assert processed == 1
    assert (out_dir / example_stl_path.name).exists()
