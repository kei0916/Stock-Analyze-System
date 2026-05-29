"""shared/financial のユニットテスト (derive_fcf 移管元のテスト補完)"""
from stock_analyze_system.shared.financial import derive_fcf


class TestDeriveFcf:
    def test_basic_derivation(self):
        rec = {"operating_cf": 100.0, "capex": -30.0, "fcf": None}
        derive_fcf(rec)
        assert rec["fcf"] == 70.0

    def test_positive_capex_uses_abs(self):
        rec = {"operating_cf": 100.0, "capex": 30.0, "fcf": None}
        derive_fcf(rec)
        assert rec["fcf"] == 70.0

    def test_existing_fcf_not_overwritten(self):
        rec = {"operating_cf": 100.0, "capex": -30.0, "fcf": 80.0}
        derive_fcf(rec)
        assert rec["fcf"] == 80.0

    def test_missing_operating_cf(self):
        rec = {"capex": -30.0, "fcf": None}
        derive_fcf(rec)
        assert rec["fcf"] is None

    def test_missing_capex(self):
        rec = {"operating_cf": 100.0, "fcf": None}
        derive_fcf(rec)
        assert rec["fcf"] is None

    def test_no_fcf_key(self):
        rec = {"operating_cf": 100.0, "capex": -20.0}
        derive_fcf(rec)
        assert rec["fcf"] == 80.0

    def test_zero_values(self):
        rec = {"operating_cf": 0.0, "capex": 0.0, "fcf": None}
        derive_fcf(rec)
        assert rec["fcf"] == 0.0
