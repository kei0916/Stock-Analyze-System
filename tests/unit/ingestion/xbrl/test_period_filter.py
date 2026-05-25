"""period_filter のテスト"""
from stock_analyze_system.ingestion.xbrl.period_filter import (
    ANNUAL_MIN_DAYS,
    DURATION_UNKNOWN,
    QUARTERLY_MAX_DAYS,
    days_between,
    duration_ok,
    merge_near_dates,
)


class TestDaysBetween:
    def test_normal_dates(self):
        assert days_between("2024-01-01", "2024-12-31") == 365

    def test_same_date(self):
        assert days_between("2024-06-15", "2024-06-15") == 0

    def test_invalid_start_returns_unknown(self):
        assert days_between("bad", "2024-01-01") == DURATION_UNKNOWN

    def test_invalid_end_returns_unknown(self):
        assert days_between("2024-01-01", "bad") == DURATION_UNKNOWN

    def test_negative_days(self):
        assert days_between("2024-12-31", "2024-01-01") == -365


class TestDurationOk:
    def test_annual_above_min(self):
        assert duration_ok(365, "annual") is True

    def test_annual_below_min(self):
        assert duration_ok(200, "annual") is False

    def test_annual_boundary(self):
        assert duration_ok(ANNUAL_MIN_DAYS, "annual") is True

    def test_quarterly_below_max(self):
        assert duration_ok(90, "quarterly") is True

    def test_quarterly_above_max(self):
        assert duration_ok(200, "quarterly") is False

    def test_quarterly_boundary(self):
        assert duration_ok(QUARTERLY_MAX_DAYS, "quarterly") is True

    def test_unknown_mode_returns_true(self):
        assert duration_ok(999, "unknown_mode") is True


class TestMergeNearDates:
    def test_single_date_unchanged(self):
        dates = {"2024-01-01"}
        result = merge_near_dates(dates, {}, {})
        assert result == {"2024-01-01"}

    def test_empty_set(self):
        result = merge_near_dates(set(), {}, {})
        assert result == set()

    def test_distant_dates_not_merged(self):
        dates = {"2024-01-01", "2024-06-30"}
        result = merge_near_dates(dates, {}, {})
        assert result == {"2024-01-01", "2024-06-30"}

    def test_near_dates_merged_to_best(self):
        """+-3日以内の日付がフィールド数の多い方にマージされる"""
        dates = {"2024-01-01", "2024-01-02"}
        field_data = {
            "revenue": {"2024-01-01": 100.0},
            "net_income": {"2024-01-02": 50.0, "2024-01-01": 200.0},
        }
        mapping = {"revenue": ["tag1"], "net_income": ["tag2"]}
        result = merge_near_dates(dates, field_data, mapping)
        assert result == {"2024-01-01"}
        assert field_data["net_income"]["2024-01-01"] == 200.0

    def test_value_migration_from_other_date(self):
        """マージ先にない値は移行される"""
        dates = {"2024-03-29", "2024-03-31"}
        field_data = {
            "revenue": {"2024-03-31": 100.0},
            "net_income": {"2024-03-29": 50.0},
        }
        mapping = {"revenue": ["t1"], "net_income": ["t2"]}
        result = merge_near_dates(dates, field_data, mapping)
        assert len(result) == 1
        best = list(result)[0]
        # Both values should be accessible on the best date
        assert field_data["revenue"].get(best) is not None

    def test_conflict_keeps_best_date_value(self):
        """競合時はbest_dateの値を保持（他方の値は破棄）"""
        dates = {"2024-01-01", "2024-01-02"}
        field_data = {
            "revenue": {"2024-01-01": 100.0, "2024-01-02": 200.0},
        }
        mapping = {"revenue": ["tag1"]}
        result = merge_near_dates(dates, field_data, mapping)
        best = list(result)[0]
        assert field_data["revenue"][best] is not None
        # Other date should have been deleted
        other = "2024-01-02" if best == "2024-01-01" else "2024-01-01"
        assert other not in field_data["revenue"]

    def test_three_close_dates_form_single_cluster(self):
        """3つの近接日付が1クラスタにマージされる"""
        dates = {"2024-06-28", "2024-06-29", "2024-06-30"}
        field_data = {
            "revenue": {"2024-06-30": 100.0},
            "net_income": {"2024-06-29": 50.0},
            "eps": {"2024-06-28": 3.5},
        }
        mapping = {"revenue": ["t1"], "net_income": ["t2"], "eps": ["t3"]}
        result = merge_near_dates(dates, field_data, mapping)
        assert len(result) == 1

    def test_two_separate_clusters(self):
        """距離がある2グループはそれぞれ独立"""
        dates = {"2024-01-01", "2024-01-02", "2024-06-30", "2024-07-01"}
        result = merge_near_dates(dates, {}, {"f": ["t"]})
        assert len(result) == 2
