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


def test_select_main_component_largest():
    """Selecting 'largest' returns the component with the greatest surface area."""
    c1, c2 = MagicMock(area=10.0, volume=5.0), MagicMock(area=20.0, volume=1.0)
    result = clean_mesh.select_main_component([c1, c2], method="largest")
    assert result is c2


def test_select_main_component_ratio():
    """Selecting 'ratio' picks the lowest area/volume ratio."""
    c1, c2 = MagicMock(area=10.0, volume=5.0), MagicMock(area=1.0, volume=0.1)
    result = clean_mesh.select_main_component([c1, c2], method="ratio")
    assert result is c1


def test_select_main_component_ratio_handles_negative_volume():
    """Reversed winding does not change a component's ratio."""
    c1, c2 = MagicMock(area=10.0, volume=-5.0), MagicMock(area=9.0, volume=1.0)
    result = clean_mesh.select_main_component([c1, c2], method="ratio")
    assert result is c1


def test_select_main_component_ratio_handles_tiny_volume():
    """Guard against division by near zero volume."""
    c1 = MagicMock(area=10.0, volume=0.0)
    c2 = MagicMock(area=9.0, volume=9.0)
    result = clean_mesh.select_main_component([c1, c2], method="ratio")
    assert result is c2


def test_select_main_component_ratio_falls_back_to_largest():
    """Undefined ratios fall back to the deterministic largest strategy."""
    c1 = MagicMock(area=10.0, volume=0.0)
    c2 = MagicMock(area=20.0, volume=float("nan"))
    result = clean_mesh.select_main_component([c1, c2], method="ratio")
    assert result is c2


def test_select_main_component_rejects_empty_components():
    with pytest.raises(ValueError, match="No components"):
        clean_mesh.select_main_component([])


def test_select_main_component_rejects_unknown_method():
    component = MagicMock(area=10.0, volume=5.0)
    with pytest.raises(ValueError, match="Unknown component selection method"):
        clean_mesh.select_main_component([component], method="unknown")


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
    fake_mesh.export.side_effect = lambda path: Path(path).write_bytes(b"mesh")

    with patch("clean_mesh.trimesh.load", return_value=fake_mesh):
        ok = clean_mesh.process_file(in_file, out_file, method="first")

    assert ok is True
    exported_path = Path(fake_mesh.export.call_args.args[0])
    assert exported_path != out_file
    assert exported_path.suffix == out_file.suffix
    assert out_file.read_bytes() == b"mesh"


def test_process_file_multi_component_uses_selector(tmp_path):
    """When multiple components exist, selector decides which to export."""
    in_file = tmp_path / "input.stl"
    out_file = tmp_path / "output.stl"
    in_file.write_text("dummy")

    comp1, comp2 = MagicMock(name="comp1"), MagicMock(name="comp2")
    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [comp1, comp2]
    comp2.export.side_effect = lambda path: Path(path).write_bytes(b"selected")

    with (
        patch("clean_mesh.trimesh.load", return_value=fake_mesh),
        patch("clean_mesh.select_main_component", return_value=comp2) as sel,
    ):
        ok = clean_mesh.process_file(in_file, out_file, method="ratio")

    assert ok is True
    sel.assert_called_once()
    assert comp2.export.call_count == 1
    assert out_file.read_bytes() == b"selected"


def test_process_file_catches_exception(tmp_path):
    """Errors are logged and result is False."""
    in_file = tmp_path / "bad.stl"
    out_file = tmp_path / "out.stl"
    in_file.write_text("dummy")

    with patch("clean_mesh.trimesh.load", side_effect=RuntimeError("boom")):
        ok = clean_mesh.process_file(in_file, out_file)

    assert ok is False


def test_process_file_rejects_unknown_method(tmp_path):
    in_file = tmp_path / "input.stl"
    out_file = tmp_path / "output.stl"
    in_file.write_text("dummy")

    with patch("clean_mesh.trimesh.load") as load:
        ok = clean_mesh.process_file(in_file, out_file, method="unknown")

    assert ok is False
    load.assert_not_called()


def test_process_file_rejects_same_input_and_output(tmp_path):
    mesh_file = tmp_path / "model.stl"
    mesh_file.write_bytes(b"original")

    with patch("clean_mesh.trimesh.load") as load:
        ok = clean_mesh.process_file(mesh_file, mesh_file)

    assert ok is False
    assert mesh_file.read_bytes() == b"original"
    load.assert_not_called()


def test_process_file_rejects_empty_mesh(tmp_path):
    in_file = tmp_path / "empty.stl"
    out_file = tmp_path / "output.stl"
    in_file.write_text("dummy")

    with patch("clean_mesh.trimesh.load", return_value=clean_mesh.trimesh.Trimesh()):
        ok = clean_mesh.process_file(in_file, out_file)

    assert ok is False
    assert not out_file.exists()


def test_process_file_rejects_non_finite_vertices(tmp_path):
    in_file = tmp_path / "invalid.stl"
    out_file = tmp_path / "output.stl"
    in_file.write_text("dummy")
    mesh = clean_mesh.trimesh.Trimesh(
        vertices=[[float("nan"), 0, 0], [1, 0, 0], [0, 1, 0]],
        faces=[[0, 1, 2]],
        process=False,
    )

    with patch("clean_mesh.trimesh.load", return_value=mesh):
        ok = clean_mesh.process_file(in_file, out_file)

    assert ok is False
    assert not out_file.exists()


def test_process_file_preserves_existing_output_when_export_fails(tmp_path):
    """A failed export does not replace the last good output."""
    in_file = tmp_path / "input.stl"
    out_file = tmp_path / "output.stl"
    sidecar_file = tmp_path / "output.mtl"
    in_file.write_text("dummy")
    out_file.write_bytes(b"original")
    sidecar_file.write_bytes(b"original sidecar")

    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [fake_mesh]

    def _failed_export(pathlike):
        Path(pathlike).with_suffix(".mtl").write_bytes(b"incomplete sidecar")
        raise RuntimeError("export failed")

    fake_mesh.export.side_effect = _failed_export

    with patch("clean_mesh.trimesh.load", return_value=fake_mesh):
        ok = clean_mesh.process_file(in_file, out_file)

    assert ok is False
    assert out_file.read_bytes() == b"original"
    assert sidecar_file.read_bytes() == b"original sidecar"
    assert not list(tmp_path.glob(".output-*"))


def test_process_file_moves_export_sidecars(tmp_path):
    in_file = tmp_path / "input.obj"
    out_file = tmp_path / "output.obj"
    in_file.write_text("dummy")

    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [fake_mesh]

    def _export_with_sidecars(*, mtl_name, **_kwargs):
        return (
            f"mtllib {mtl_name}\nv 0 0 0\n",
            {
                mtl_name: b"newmtl material\nmap_Kd texture.png\n",
                "texture.png": b"texture",
            },
        )

    fake_mesh.export.side_effect = _export_with_sidecars

    with patch("clean_mesh.trimesh.load", return_value=fake_mesh):
        ok = clean_mesh.process_file(in_file, out_file)

    assert ok is True
    assert out_file.read_text() == "mtllib output.obj_assets/output.mtl\nv 0 0 0\n"
    assert (tmp_path / "output.obj_assets" / "output.mtl").read_bytes().startswith(b"newmtl material")
    assert (tmp_path / "output.obj_assets" / "texture.png").read_bytes() == b"texture"


def test_process_file_obj_without_materials(tmp_path):
    in_file = tmp_path / "input.obj"
    out_file = tmp_path / "output.obj"
    in_file.write_text("dummy")

    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [fake_mesh]
    fake_mesh.export.return_value = ("v 0 0 0\n", {})

    with patch("clean_mesh.trimesh.load", return_value=fake_mesh):
        ok = clean_mesh.process_file(in_file, out_file)

    assert ok is True
    assert out_file.read_text() == "v 0 0 0\n"
    assert not (tmp_path / "output.obj_assets").exists()


@pytest.mark.parametrize(
    "exported",
    [
        b"not a tuple",
        ("v 0 0 0\n", []),
        ("v 0 0 0\n", {"texture.png": b"texture"}),
        ("v 0 0 0\n", {"output.mtl": b"material"}),
        (
            "mtllib output.mtl\nv 0 0 0\n",
            {"output.mtl": b"material", "../texture.png": b"texture"},
        ),
    ],
)
def test_process_file_rejects_invalid_obj_export_data(tmp_path, exported):
    in_file = tmp_path / "input.obj"
    out_file = tmp_path / "output.obj"
    in_file.write_text("dummy")

    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [fake_mesh]
    fake_mesh.export.return_value = exported

    with patch("clean_mesh.trimesh.load", return_value=fake_mesh):
        ok = clean_mesh.process_file(in_file, out_file)

    assert ok is False
    assert not out_file.exists()
    assert not list(tmp_path.glob(".output-*"))


def test_process_file_rejects_obj_assets_that_would_replace_input_parent(
    tmp_path,
):
    input_dir = tmp_path / "model.obj_assets"
    input_dir.mkdir()
    in_file = input_dir / "input.obj"
    out_file = tmp_path / "model.obj"
    in_file.write_text("original input")

    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [fake_mesh]
    fake_mesh.export.return_value = (
        "mtllib model.mtl\nv 0 0 0\n",
        {"model.mtl": b"material"},
    )

    with patch("clean_mesh.trimesh.load", return_value=fake_mesh):
        ok = clean_mesh.process_file(in_file, out_file)

    assert ok is False
    assert in_file.read_text() == "original input"
    assert not out_file.exists()


def test_process_file_namespaces_assets_for_multiple_objs(tmp_path):
    first_input = tmp_path / "first-input.obj"
    second_input = tmp_path / "second-input.obj"
    first_output = tmp_path / "first.obj"
    second_output = tmp_path / "second.obj"
    first_input.write_text("dummy")
    second_input.write_text("dummy")

    def _mesh_with_texture(texture):
        mesh = MagicMock()
        mesh.split.return_value = [mesh]

        def _export(*, mtl_name, **_kwargs):
            return (
                f"mtllib {mtl_name}\nv 0 0 0\n",
                {
                    mtl_name: b"newmtl material\nmap_Kd texture.png\n",
                    "texture.png": texture,
                },
            )

        mesh.export.side_effect = _export
        return mesh

    with patch(
        "clean_mesh.trimesh.load",
        side_effect=[_mesh_with_texture(b"first"), _mesh_with_texture(b"second")],
    ):
        first_ok = clean_mesh.process_file(first_input, first_output)
        second_ok = clean_mesh.process_file(second_input, second_output)

    assert first_ok is True
    assert second_ok is True
    assert first_output.read_text().startswith("mtllib first.obj_assets/first.mtl")
    assert second_output.read_text().startswith("mtllib second.obj_assets/second.mtl")
    assert (tmp_path / "first.obj_assets" / "texture.png").read_bytes() == b"first"
    assert (tmp_path / "second.obj_assets" / "texture.png").read_bytes() == b"second"


def test_process_file_namespaces_real_trimesh_obj_materials(tmp_path):
    first_input = tmp_path / "first-input.obj"
    second_input = tmp_path / "second-input.obj"
    first_output = tmp_path / "first.obj"
    second_output = tmp_path / "second.obj"
    first_input.write_text("dummy")
    second_input.write_text("dummy")

    def _textured_box(diffuse):
        mesh = clean_mesh.trimesh.creation.box()
        mesh.visual = clean_mesh.trimesh.visual.TextureVisuals(
            uv=clean_mesh.np.zeros((len(mesh.vertices), 2)),
            material=clean_mesh.trimesh.visual.material.SimpleMaterial(diffuse=diffuse),
        )
        return mesh

    with patch(
        "clean_mesh.trimesh.load",
        side_effect=[
            _textured_box([255, 0, 0, 255]),
            _textured_box([0, 0, 255, 255]),
        ],
    ):
        first_ok = clean_mesh.process_file(first_input, first_output)
        second_ok = clean_mesh.process_file(second_input, second_output)

    assert first_ok is True
    assert second_ok is True
    assert "mtllib first.obj_assets/first.mtl" in first_output.read_text()
    assert "mtllib second.obj_assets/second.mtl" in second_output.read_text()
    assert (tmp_path / "first.obj_assets" / "first.mtl").is_file()
    assert (tmp_path / "second.obj_assets" / "second.mtl").is_file()


def test_process_file_rolls_back_if_publishing_obj_fails(tmp_path):
    in_file = tmp_path / "input.obj"
    out_file = tmp_path / "output.obj"
    assets_dir = tmp_path / "output.obj_assets"
    in_file.write_text("dummy")
    out_file.write_bytes(b"original mesh")
    assets_dir.mkdir()
    (assets_dir / "output.mtl").write_bytes(b"original material")
    (assets_dir / "texture.png").write_bytes(b"original texture")

    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [fake_mesh]

    def _export(*, mtl_name, **_kwargs):
        return (
            f"mtllib {mtl_name}\nv 0 0 0\n",
            {
                mtl_name: b"replacement material",
                "texture.png": b"replacement texture",
            },
        )

    fake_mesh.export.side_effect = _export
    real_replace = clean_mesh.os.replace
    failed = False

    def _fail_main_publication(source, destination):
        nonlocal failed
        source_path = Path(source)
        destination_path = Path(destination)
        if not failed and destination_path == out_file and source_path.parent.name.startswith(".output-"):
            failed = True
            raise OSError("simulated publication failure")
        return real_replace(source, destination)

    with (
        patch("clean_mesh.trimesh.load", return_value=fake_mesh),
        patch("clean_mesh.os.replace", side_effect=_fail_main_publication),
    ):
        ok = clean_mesh.process_file(in_file, out_file)

    assert ok is False
    assert out_file.read_bytes() == b"original mesh"
    assert (assets_dir / "output.mtl").read_bytes() == b"original material"
    assert (assets_dir / "texture.png").read_bytes() == b"original texture"
    assert not list(tmp_path.glob(".output-*"))


def test_process_file_rolls_back_before_propagating_keyboard_interrupt(
    tmp_path,
):
    in_file = tmp_path / "input.obj"
    out_file = tmp_path / "output.obj"
    assets_dir = tmp_path / "output.obj_assets"
    in_file.write_text("dummy")
    out_file.write_bytes(b"original mesh")
    assets_dir.mkdir()
    (assets_dir / "output.mtl").write_bytes(b"original material")

    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [fake_mesh]
    fake_mesh.export.return_value = (
        "mtllib output.mtl\nv 0 0 0\n",
        {"output.mtl": b"replacement material"},
    )
    real_replace = clean_mesh.os.replace
    interrupted = False

    def _interrupt_main_publication(source, destination):
        nonlocal interrupted
        source_path = Path(source)
        destination_path = Path(destination)
        if not interrupted and destination_path == out_file and source_path.parent.name.startswith(".output-"):
            interrupted = True
            real_replace(source, destination)
            raise KeyboardInterrupt
        return real_replace(source, destination)

    with (
        patch("clean_mesh.trimesh.load", return_value=fake_mesh),
        patch(
            "clean_mesh.os.replace",
            side_effect=_interrupt_main_publication,
        ),
        pytest.raises(KeyboardInterrupt),
    ):
        clean_mesh.process_file(in_file, out_file)

    assert out_file.read_bytes() == b"original mesh"
    assert (assets_dir / "output.mtl").read_bytes() == b"original material"
    assert not list(tmp_path.glob(".output-*"))


def test_process_file_preserves_backup_if_rollback_fails(tmp_path):
    in_file = tmp_path / "input.obj"
    out_file = tmp_path / "output.obj"
    assets_dir = tmp_path / "output.obj_assets"
    in_file.write_text("dummy")
    out_file.write_bytes(b"original mesh")
    assets_dir.mkdir()
    (assets_dir / "output.mtl").write_bytes(b"original material")

    fake_mesh = MagicMock()
    fake_mesh.split.return_value = [fake_mesh]
    fake_mesh.export.return_value = (
        "mtllib output.mtl\nv 0 0 0\n",
        {"output.mtl": b"replacement material"},
    )
    real_replace = clean_mesh.os.replace
    publication_failed = False
    restoration_failed = False

    def _fail_publication_and_restoration(source, destination):
        nonlocal publication_failed, restoration_failed
        source_path = Path(source)
        destination_path = Path(destination)
        if not publication_failed and destination_path == out_file and source_path.parent.name.startswith(".output-"):
            publication_failed = True
            raise OSError("simulated publication failure")
        if (
            publication_failed
            and not restoration_failed
            and destination_path == out_file
            and source_path.parent.name == ".rollback"
        ):
            restoration_failed = True
            raise OSError("simulated restoration failure")
        return real_replace(source, destination)

    with (
        patch("clean_mesh.trimesh.load", return_value=fake_mesh),
        patch(
            "clean_mesh.os.replace",
            side_effect=_fail_publication_and_restoration,
        ),
    ):
        ok = clean_mesh.process_file(in_file, out_file)

    assert ok is False
    assert not out_file.exists()
    assert (assets_dir / "output.mtl").read_bytes() == b"original material"
    recovery_dirs = list(tmp_path.glob(".meshcleaner-recovery-*"))
    assert len(recovery_dirs) == 1
    recovery_dir = recovery_dirs[0]
    assert str(out_file) in (recovery_dir / "RECOVERY.txt").read_text()
    assert (recovery_dir / "backups" / "1").read_bytes() == b"original mesh"


# ---------------------------------------
# Unit tests: process_directory and CLI
# ---------------------------------------


def test_process_directory_no_input(tmp_path):
    out_dir = tmp_path / "out"
    processed = clean_mesh.process_directory(tmp_path / "missing", out_dir, formats=["stl"])
    assert processed == 0


def test_process_directory_rejects_non_directory_paths(tmp_path):
    in_file = tmp_path / "input"
    in_file.write_text("not a directory")
    out_file = tmp_path / "output"
    out_file.write_text("not a directory")

    assert clean_mesh.process_directory(in_file, tmp_path / "out") == 0
    assert clean_mesh.process_directory(tmp_path, out_file) == 0


def test_process_directory_rejects_in_place_output(tmp_path):
    (tmp_path / "model.stl").write_text("mesh")

    with patch("clean_mesh.process_file") as process:
        processed = clean_mesh.process_directory(tmp_path, tmp_path, formats=["stl"])

    assert processed == 0
    process.assert_not_called()


def test_process_directory_rejects_overlapping_directories(tmp_path):
    in_dir = tmp_path / "models"
    in_dir.mkdir()
    (in_dir / "model.stl").write_text("mesh")

    with patch("clean_mesh.process_file") as process:
        nested_processed = clean_mesh.process_directory(
            in_dir,
            in_dir / "cleaned",
            formats=["stl"],
        )
        parent_processed = clean_mesh.process_directory(
            in_dir,
            tmp_path,
            formats=["stl"],
        )

    assert nested_processed == 0
    assert parent_processed == 0
    process.assert_not_called()


def test_process_directory_handles_unreadable_input(tmp_in_out):
    in_dir, out_dir = tmp_in_out

    with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
        processed = clean_mesh.process_directory(in_dir, out_dir)

    assert processed == 0


def test_process_directory_normalizes_formats_and_order(tmp_in_out):
    in_dir, out_dir = tmp_in_out
    (in_dir / "B.STL").write_text("b")
    (in_dir / "a.stl").write_text("a")
    (in_dir / "ignored.obj").write_text("obj")

    with patch("clean_mesh.process_file", return_value=True) as process:
        processed = clean_mesh.process_directory(
            in_dir,
            out_dir,
            formats=["stl", ".STL", "stl"],
        )

    assert processed == 2
    assert [call.args[0].name for call in process.call_args_list] == ["a.stl", "B.STL"]


def test_process_directory_separates_case_variant_obj_assets(tmp_in_out):
    in_dir, out_dir = tmp_in_out
    (in_dir / "part.obj").write_text("lower")
    (in_dir / "part.OBJ").write_text("upper")
    if len(list(in_dir.iterdir())) != 2:
        pytest.skip("Case-variant filenames require a case-sensitive filesystem")

    def _mesh():
        mesh = MagicMock()
        mesh.split.return_value = [mesh]

        def _export(*, mtl_name, **_kwargs):
            return (
                f"mtllib {mtl_name}\nv 0 0 0\n",
                {mtl_name: b"material"},
            )

        mesh.export.side_effect = _export
        return mesh

    with patch(
        "clean_mesh.trimesh.load",
        side_effect=[_mesh(), _mesh()],
    ):
        processed = clean_mesh.process_directory(
            in_dir,
            out_dir,
            formats=["obj"],
        )

    assert processed == 2
    assert (out_dir / "part.obj_assets" / "part.mtl").is_file()
    assert (out_dir / "part.OBJ_assets" / "part.mtl").is_file()


def test_process_directory_accepts_a_single_format_string(tmp_in_out):
    in_dir, out_dir = tmp_in_out
    (in_dir / "model.stl").write_text("mesh")

    with patch("clean_mesh.process_file", return_value=True) as process:
        processed = clean_mesh.process_directory(in_dir, out_dir, formats="stl")

    assert processed == 1
    process.assert_called_once()


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


def test_cli_defaults_to_largest(tmp_in_out):
    in_dir, out_dir = tmp_in_out
    (in_dir / "x.stl").write_text("x")

    with patch("clean_mesh.process_file", return_value=True) as process:
        code = clean_mesh.main(["--input", str(in_dir), "--output", str(out_dir)])

    assert code == 0
    assert process.call_args.kwargs["method"] == "largest"


def test_cli_reports_partial_failure(tmp_in_out):
    in_dir, out_dir = tmp_in_out
    (in_dir / "a.stl").write_text("a")
    (in_dir / "b.stl").write_text("b")

    with patch("clean_mesh.process_file", side_effect=[True, False]):
        code = clean_mesh.main(["--input", str(in_dir), "--output", str(out_dir)])

    assert code == 1


def test_cli_main_exit_codes(tmp_in_out):
    """CLI returns 0 only when every discovered file is processed."""
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
