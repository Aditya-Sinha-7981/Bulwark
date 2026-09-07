"""
Tests for Task 14.b — XLSX artifact renderer and create_xlsx capability.

Mirrors backend/tests/test_artifacts_docx.py's structure and fixture style
exactly (once that file was adjusted to match repo conventions during 14.a
integration — see logs/artifacts-docx.md). If the 14.a integration changed
test conventions further, re-align this file the same way before merge.

Covers, per docs/testing.md "Artifact tests" and "Failure injection":
- schema validation (valid input renders; invalid input rejected before
  any file is written)
- row/header length mismatch (rendering-layer safety, not explicitly in
  the schema — see ASSUMPTION FLAG below)
- atomic-write behavior (no partial file survives a mid-render failure)
- Artifact-row persistence tying back to the correct job_id
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.domain.artifacts.xlsx_renderer import XlsxRenderError, render_xlsx
from backend.domain.capabilities.create_xlsx import (
    CapabilityValidationError,
    execute_create_xlsx,
    validate_input,
    validate_output,
)

VALID_PAYLOAD = {
    "title": "Q3 Sensor Readings",
    "sheets": [
        {
            "name": "Readings",
            "headers": ["Timestamp", "Sensor ID", "Value"],
            "rows": [
                ["2026-09-06T00:00:00Z", "S-001", "42.1"],
                ["2026-09-06T01:00:00Z", "S-001", "43.7"],
            ],
        },
        {
            "name": "Summary",
            "headers": ["Metric", "Value"],
            "rows": [["Average", "42.9"]],
        },
    ],
}


# ---------------------------------------------------------------------------
# validate_input
# ---------------------------------------------------------------------------


def test_validate_input_accepts_valid_payload():
    result = validate_input(VALID_PAYLOAD)
    assert result == VALID_PAYLOAD


def test_validate_input_rejects_missing_title():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "title"}
    with pytest.raises(CapabilityValidationError, match="title"):
        validate_input(payload)


def test_validate_input_rejects_extra_top_level_field():
    payload = {**VALID_PAYLOAD, "unexpected": "nope"}
    with pytest.raises(CapabilityValidationError, match="unexpected field"):
        validate_input(payload)


def test_validate_input_rejects_empty_sheets():
    payload = {**VALID_PAYLOAD, "sheets": []}
    with pytest.raises(CapabilityValidationError, match="sheets"):
        validate_input(payload)


def test_validate_input_rejects_sheet_missing_name():
    payload = {**VALID_PAYLOAD, "sheets": [{"headers": ["A"], "rows": []}]}
    with pytest.raises(CapabilityValidationError, match="name"):
        validate_input(payload)


def test_validate_input_rejects_extra_field_in_sheet():
    payload = {
        **VALID_PAYLOAD,
        "sheets": [{"name": "S", "headers": ["A"], "rows": [], "extra": 1}],
    }
    with pytest.raises(CapabilityValidationError, match="unexpected field"):
        validate_input(payload)


def test_validate_input_rejects_empty_headers():
    payload = {**VALID_PAYLOAD, "sheets": [{"name": "S", "headers": [], "rows": []}]}
    with pytest.raises(CapabilityValidationError, match="headers"):
        validate_input(payload)


def test_validate_input_rejects_non_string_header():
    payload = {**VALID_PAYLOAD, "sheets": [{"name": "S", "headers": ["A", 123], "rows": []}]}
    with pytest.raises(CapabilityValidationError, match="headers"):
        validate_input(payload)


def test_validate_input_accepts_empty_rows_headers_only_sheet():
    payload = {**VALID_PAYLOAD, "sheets": [{"name": "Empty", "headers": ["A", "B"], "rows": []}]}
    result = validate_input(payload)
    assert result["sheets"][0]["rows"] == []


def test_validate_input_accepts_ragged_rows():
    """Ragged rows are a rendering-layer concern (not validation), per
    finalisation decision §7/§11: short rows padded with None, long rows
    preserved. Validation only checks that rows is a list of lists."""
    payload = {
        "title": "Test",
        "sheets": [
            {
                "name": "Sheet1",
                "headers": ["A", "B", "C"],
                "rows": [
                    ["val1", "val2"],        # short row (2 of 3)
                    ["val1", "val2", "val3", "val4"],  # long row (4 of 3)
                ],
            },
        ],
    }
    result = validate_input(payload)
    assert result == payload


def test_validate_input_rejects_row_not_a_list():
    payload = {**VALID_PAYLOAD, "sheets": [{"name": "S", "headers": ["A"], "rows": ["not-a-list"]}]}
    with pytest.raises(CapabilityValidationError, match="must be a list"):
        validate_input(payload)


# ---------------------------------------------------------------------------
# validate_output
# ---------------------------------------------------------------------------


def test_validate_output_accepts_valid_shape():
    result = validate_output({"artifact_id": "abc-123", "filename": "Workbook.xlsx"})
    assert result["artifact_id"] == "abc-123"


def test_validate_output_rejects_missing_filename():
    with pytest.raises(CapabilityValidationError, match="filename"):
        validate_output({"artifact_id": "abc-123"})


def test_validate_output_rejects_extra_field():
    with pytest.raises(CapabilityValidationError, match="unexpected"):
        validate_output({"artifact_id": "a", "filename": "f.xlsx", "extra": 1})


# ---------------------------------------------------------------------------
# render_xlsx — atomic write + Artifact persistence + real content check
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_artifacts_root(tmp_path, monkeypatch):
    fake_root = tmp_path / "artifacts"
    fake_root.mkdir()
    import backend.utils.paths as paths_module
    monkeypatch.setattr(paths_module, "ARTIFACTS_ROOT", fake_root)
    monkeypatch.setattr(
        paths_module, "artifacts_path", lambda artifact_id, ext: fake_root / f"{artifact_id}{ext}"
    )
    return fake_root


def test_render_xlsx_writes_file_and_creates_artifact_row(isolated_artifacts_root):
    with patch(
        "backend.domain.artifacts.xlsx_renderer.create_artifact"
    ) as mock_create_artifact:
        mock_create_artifact.return_value = "generated-artifact-id"

        result = render_xlsx(
            artifact_id="test-artifact-id",
            job_id="test-job-id",
            payload=VALID_PAYLOAD,
        )

    assert result["artifact_id"] == "test-artifact-id"
    assert result["filename"].endswith(".xlsx")

    written_file = isolated_artifacts_root / "test-artifact-id.xlsx"
    assert written_file.exists()
    assert written_file.stat().st_size > 0

    mock_create_artifact.assert_called_once()
    call_kwargs = mock_create_artifact.call_args.kwargs
    assert call_kwargs["job_id"] == "test-job-id"
    assert call_kwargs["type"] == "xlsx"


def test_render_xlsx_produces_correct_sheet_content(isolated_artifacts_root):
    """Real end-to-end check: reopen the written file and verify actual
    sheet names, headers, and row data — not just that a file exists."""
    from openpyxl import load_workbook

    with patch("backend.domain.artifacts.xlsx_renderer.create_artifact"):
        render_xlsx(artifact_id="content-check", job_id="job-1", payload=VALID_PAYLOAD)

    workbook = load_workbook(isolated_artifacts_root / "content-check.xlsx")
    assert workbook.sheetnames == ["Readings", "Summary"]

    readings = workbook["Readings"]
    assert [cell.value for cell in readings[1]] == ["Timestamp", "Sensor ID", "Value"]
    assert readings[1][0].font.bold is True
    assert [cell.value for cell in readings[2]] == ["2026-09-06T00:00:00Z", "S-001", "42.1"]

    summary = workbook["Summary"]
    assert [cell.value for cell in summary[1]] == ["Metric", "Value"]
    assert [cell.value for cell in summary[2]] == ["Average", "42.9"]


def test_render_xlsx_removes_orphan_file_if_artifact_row_fails(isolated_artifacts_root):
    with patch(
        "backend.domain.artifacts.xlsx_renderer.create_artifact",
        side_effect=RuntimeError("db unavailable"),
    ):
        with pytest.raises(XlsxRenderError, match="Artifact row"):
            render_xlsx(
                artifact_id="orphan-test-id",
                job_id="test-job-id",
                payload=VALID_PAYLOAD,
            )

    assert not (isolated_artifacts_root / "orphan-test-id.xlsx").exists()
    assert list(isolated_artifacts_root.glob("*.tmp")) == []


def test_render_xlsx_leaves_no_temp_file_on_openpyxl_failure(isolated_artifacts_root):
    with patch(
        "backend.domain.artifacts.xlsx_renderer._build_workbook",
        side_effect=RuntimeError("simulated openpyxl crash"),
    ):
        with pytest.raises(XlsxRenderError, match="render/write"):
            render_xlsx(
                artifact_id="crash-test-id",
                job_id="test-job-id",
                payload=VALID_PAYLOAD,
            )

    assert list(isolated_artifacts_root.iterdir()) == []


def test_render_xlsx_sanitizes_unsafe_sheet_name(isolated_artifacts_root):
    """Excel forbids \ / ? * [ ] : in sheet names — confirm we sanitize
    rather than crash on a title containing them."""
    payload = {
        "title": "Report",
        "sheets": [{"name": "Q3/Q4 Report [Draft]", "headers": ["A"], "rows": []}],
    }
    from openpyxl import load_workbook

    with patch("backend.domain.artifacts.xlsx_renderer.create_artifact"):
        render_xlsx(artifact_id="sanitize-test", job_id="job-1", payload=payload)

    workbook = load_workbook(isolated_artifacts_root / "sanitize-test.xlsx")
    assert "/" not in workbook.sheetnames[0]
    assert "[" not in workbook.sheetnames[0]


def test_render_xlsx_handles_short_row_padding(isolated_artifacts_root):
    """Test that rows shorter than headers are padded with empty cells."""
    payload = {
        "title": "Test",
        "sheets": [
            {
                "name": "Sheet1",
                "headers": ["A", "B", "C"],
                "rows": [
                    ["val1", "val2"],  # Short row - missing C
                    ["val1", "val2", "val3"],  # Complete row
                ],
            },
        ],
    }

    with patch(
        "backend.domain.artifacts.xlsx_renderer.create_artifact"
    ) as mock_create_artifact:
        mock_create_artifact.return_value = "generated-artifact-id"
        result = render_xlsx(
            artifact_id="short-row-test",
            job_id="test-job-id",
            payload=payload,
        )

    # Verify the file was created and can be read back
    import openpyxl
    wb = openpyxl.load_workbook(isolated_artifacts_root / "short-row-test.xlsx")
    ws = wb["Sheet1"]
    
    # Check row 2 has 3 cells (A, B, C) with C being empty
    assert ws.cell(row=2, column=1).value == "val1"
    assert ws.cell(row=2, column=2).value == "val2"
    assert ws.cell(row=2, column=3).value is None
    
    # Check row 3 has all 3 cells
    assert ws.cell(row=3, column=1).value == "val1"
    assert ws.cell(row=3, column=2).value == "val2"
    assert ws.cell(row=3, column=3).value == "val3"


def test_render_xlsx_handles_long_row_preservation(isolated_artifacts_root):
    """Test that rows longer than headers are preserved."""
    payload = {
        "title": "Test",
        "sheets": [
            {
                "name": "Sheet1",
                "headers": ["A", "B"],
                "rows": [
                    ["val1", "val2", "val3", "val4"],  # Long row - 4 values for 2 headers
                ],
            },
        ],
    }

    with patch(
        "backend.domain.artifacts.xlsx_renderer.create_artifact"
    ) as mock_create_artifact:
        mock_create_artifact.return_value = "generated-artifact-id"
        result = render_xlsx(
            artifact_id="long-row-test",
            job_id="test-job-id",
            payload=payload,
        )

    import openpyxl
    wb = openpyxl.load_workbook(isolated_artifacts_root / "long-row-test.xlsx")
    ws = wb["Sheet1"]
    
    # Check all 4 values are preserved
    assert ws.cell(row=2, column=1).value == "val1"
    assert ws.cell(row=2, column=2).value == "val2"
    assert ws.cell(row=2, column=3).value == "val3"
    assert ws.cell(row=2, column=4).value == "val4"


def test_render_xlsx_preserves_numeric_types(isolated_artifacts_root):
    """Test that numeric cell values are written as numbers, not strings."""
    payload = {
        "title": "Test",
        "sheets": [
            {
                "name": "Sheet1",
                "headers": ["Product", "Price", "Quantity"],
                "rows": [
                    ["Widget A", 19.99, 100],
                    ["Widget B", 29.99, 50],
                ],
            },
        ],
    }

    with patch(
        "backend.domain.artifacts.xlsx_renderer.create_artifact"
    ) as mock_create_artifact:
        mock_create_artifact.return_value = "generated-artifact-id"
        result = render_xlsx(
            artifact_id="numeric-test",
            job_id="test-job-id",
            payload=payload,
        )

    import openpyxl
    wb = openpyxl.load_workbook(isolated_artifacts_root / "numeric-test.xlsx")
    ws = wb["Sheet1"]
    
    # Check numeric types are preserved
    assert ws.cell(row=2, column=2).value == 19.99
    assert isinstance(ws.cell(row=2, column=2).value, float)
    assert ws.cell(row=2, column=3).value == 100
    assert isinstance(ws.cell(row=2, column=3).value, int)
    
    assert ws.cell(row=3, column=2).value == 29.99
    assert isinstance(ws.cell(row=3, column=2).value, float)
    assert ws.cell(row=3, column=3).value == 50
    assert isinstance(ws.cell(row=3, column=3).value, int)


def test_render_xlsx_header_bold_styling(isolated_artifacts_root):
    """Test that header row has bold styling."""
    payload = {
        "title": "Test",
        "sheets": [
            {
                "name": "Sheet1",
                "headers": ["A", "B"],
                "rows": [["val1", "val2"]],
            },
        ],
    }

    with patch(
        "backend.domain.artifacts.xlsx_renderer.create_artifact"
    ) as mock_create_artifact:
        mock_create_artifact.return_value = "generated-artifact-id"
        result = render_xlsx(
            artifact_id="style-test",
            job_id="test-job-id",
            payload=payload,
        )

    import openpyxl
    wb = openpyxl.load_workbook(isolated_artifacts_root / "style-test.xlsx")
    ws = wb["Sheet1"]
    
    # Check header row is bold
    assert ws.cell(row=1, column=1).font.bold is True
    assert ws.cell(row=1, column=2).font.bold is True
    
    # Check data row is not bold
    assert ws.cell(row=2, column=1).font.bold is not True
    assert ws.cell(row=2, column=2).font.bold is not True


# ---------------------------------------------------------------------------
# execute_create_xlsx — full capability path, including audit emission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_create_xlsx_emits_artifact_created_event(isolated_artifacts_root):
    with patch(
        "backend.domain.capabilities.create_xlsx.emit", new_callable=AsyncMock
    ) as mock_emit, patch(
        "backend.domain.artifacts.xlsx_renderer.create_artifact"
    ) as mock_create_artifact:
        mock_create_artifact.return_value = "generated-id"

        result = await execute_create_xlsx(job_id="job-1", arguments=VALID_PAYLOAD)

        mock_emit.assert_awaited_once()
        call_args = mock_emit.call_args
        assert call_args.args[0] == "artifact_created"
        assert call_args.kwargs["job_id"] == "job-1"

    assert result["filename"].endswith(".xlsx")


@pytest.mark.asyncio
async def test_execute_create_xlsx_never_renders_on_invalid_input(isolated_artifacts_root):
    invalid_payload = {"title": ""}  # missing sheets entirely

    with patch(
        "backend.domain.artifacts.xlsx_renderer.create_artifact"
    ) as mock_create_artifact:
        with pytest.raises(CapabilityValidationError):
            await execute_create_xlsx(job_id="job-1", arguments=invalid_payload)

        mock_create_artifact.assert_not_called()

    assert list(isolated_artifacts_root.iterdir()) == []


# Need to import patch for tests that use it
from unittest.mock import patch