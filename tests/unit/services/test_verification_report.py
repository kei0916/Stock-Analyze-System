"""検証レポートサービスのテスト"""
import json
from stock_analyze_system.services.verification_report import save_verification_report

class TestSaveVerificationReport:
    def test_creates_report_file(self, tmp_path):
        tree = {"doc_name": "10-K_2024"}
        verification_log = [{
            "mode": "sampling",
            "accuracy": 0.95,
            "checked_count": 20,
            "correct_count": 19,
            "incorrect_count": 1,
            "items": [{"title": "Revenue", "page_number": 42, "answer": "correct", "thinking": "matched", "page_text_snippet": "Revenue was..."}],
        }]
        result_path = save_verification_report(
            company_id="US_AAPL", filing_id=1, tree=tree,
            verification_log=verification_log, node_count=10, output_dir=tmp_path,
        )
        assert result_path.exists()
        data = json.loads(result_path.read_text())
        assert data["company_id"] == "US_AAPL"
        assert data["node_count"] == 10
        assert len(data["phases"]) == 1
        assert data["phases"][0]["accuracy"] == 0.95

    def test_report_filename_format(self, tmp_path):
        tree = {"doc_name": "10-K"}
        result_path = save_verification_report(
            company_id="US_AAPL", filing_id=1, tree=tree,
            verification_log=[{"mode": "test", "accuracy": 1.0, "checked_count": 1, "correct_count": 1, "incorrect_count": 0, "items": []}],
            node_count=5, output_dir=tmp_path,
        )
        assert result_path.name.startswith("US_AAPL_")
        assert result_path.suffix == ".json"
