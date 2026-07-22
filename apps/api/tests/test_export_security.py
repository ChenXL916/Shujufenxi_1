from app.services.analysis_service import AnalysisService


def test_spreadsheet_formula_prefixes_are_escaped() -> None:
    assert AnalysisService._safe_cell("=HYPERLINK('bad')") == "'=HYPERLINK('bad')"
    assert AnalysisService._safe_cell("+1") == "'+1"
    assert AnalysisService._safe_cell("safe") == "safe"
