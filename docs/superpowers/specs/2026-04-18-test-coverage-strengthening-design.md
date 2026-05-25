# テストカバレッジ強化 設計書 (リファクタ安全網)

**Date**: 2026-04-18
**Status**: 全セクション承認済み (2026-04-18)
**Goal**: プロジェクト全体のテストカバレッジを強化し、今後の大規模リファクタリングを安全に実施できる基盤を作る。
**Scope**: テスト追加のみ。ソースコードは一切変更しない。

**重要な前提 (2026-04-18 に git log で確認)**:
`docs/superpowers/plans/2026-03-29-maintainability-refactoring.md` の 12 Task はほぼ**実行済み** (`container.py`, `enums.py`, `ingestion/xbrl/`, `services/verification_report.py`, `valuation.compute_valuation_from_financials`, `PageIndexService.count_nodes` すべて存在)。
したがって本 spec の Phase A は「計画中のリファクタを守る」ではなく「既に移動・分割された現状コードを**今後の新たなリファクタから守る** characterization テストを作る」という意味合いになる。5 領域の選定は依然有効 (責務が集中し、将来再度触られる可能性が高い箇所)。

---

## コンテキスト (AI モデル引き継ぎ用メモ)

後続のモデルや別 AI が本作業を継続できるよう、ここまでの意思決定と現状認識を記録する。

### プロジェクト現状 (2026-04-18 時点)
- Python 3.10+, SQLAlchemy 2.0 async, pytest, FastAPI, litellm, PageIndex (PDF→木構造 RAG)
- ソース 90 ファイル / テスト 65 ファイル / pytest 収集 632 テスト / 全通過
- カバレッジ **92%** (未カバー 280 / 3612 行)
- 低カバレッジ領域:
  - `services/pageindex_service.py` **77%** (外部 PageIndex lib 呼び出し部 約50行)
  - `web/routes/watchlists.py` **68%**, `api.py` **75%**, `dashboard.py` **75%**, `rag.py` **75%**, `targets.py` **77%**, `stocks.py` **82%**
  - `web/auth.py` **86%**, CLI `watchlist.py` **84%**, `valuation.py` **87%**
  - `ingestion/edinet_xbrl_parser.py` **83%**
- 結合テスト (`tests/integration/`) は `test_llamacpp_server.py` 1本のみ
- **過去のリファクタは実行済み** (`docs/superpowers/specs/2026-03-29-maintainability-refactoring-design.md` の 12 Task はほぼ完了)。本 spec は「既に移動・分割された現状コードを将来のリファクタから守る」目的の characterization テストを追加する位置付け。

### ユーザー決定事項

| 項目 | 決定 |
|------|------|
| 優先順位 | **Phase A (保護網) → Phase B (カバレッジ底上げ) → Phase C (結合テスト)** の順 |
| Phase A スコープ | **5領域すべて保護** (XBRL parser 分割 / ValuationService 統合 / CLI DI コンテナ分離 / 検証レポート移動 / Enum 置換) |
| Phase B スコープ | **数値目標なし**。未カバー行をレビューして「分岐 (エラーパス/バリデーション)」のみ潰す。達成値は結果論 |
| Phase C スコープ | **Service 組立て層のみ** (`container.setup_services()` をそのまま使用、外部 API のみモック、CLI/Web 表層は含めない) |
| 実行戦略 | **アプローチ3: ハイブリッド** — Phase A は領域単位で独立 PR (5本)、Phase B/C はまとめて PR (各1〜2本) |
| 進め方 | ソース変更せずテスト追加のみ。各セクションをこの spec に追記しながら進める |

---

## セクション1: 全体アーキテクチャ

### 基本方針
1. **ソース側は一切触らない**。テスト追加のみ。
2. **既存テストを破壊しない**。新設テストは独立フィクスチャを使用。
3. 各 PR 毎に `pytest tests/ -v` 全件通過を保証。
4. スナップショット更新は手動・意図的に実施 (CI で自動更新しない)。

### ディレクトリ構成 (新設箇所のみ)

```
tests/
├── fixtures/                           # 新設: 保護用スナップショット・入力データ
│   ├── xbrl/
│   │   ├── sample_sec_10k.json        # SEC Company Facts の縮小版
│   │   └── expected_parse_result.json # パース結果のゴールデン値
│   ├── valuation/
│   │   └── expected_valuation.json    # compute_valuation の期待値
│   └── reports/
│       └── expected_verification.json # 検証レポート JSON スキーマ
├── integration/                        # 既存: 1本のみ、拡充する
│   ├── test_llamacpp_server.py        # 既存 (触らない)
│   ├── conftest.py                    # 新設: 結合テスト用フィクスチャ
│   └── test_service_assembly.py       # 新設: Phase C 本体
└── unit/
    ├── characterization/              # 新設: Phase A 用 characterization テスト
    │   ├── test_xbrl_parse_golden.py
    │   ├── test_valuation_compute_golden.py
    │   ├── test_container_assembly.py
    │   ├── test_verification_report_schema.py
    │   └── test_enum_integration.py
    └── (既存テスト群にも Phase B の分岐テストを追記)
```

### pytest マーカー
- `@pytest.mark.characterization` を新設し、一括実行/除外可能にする。
- `pyproject.toml` の `[tool.pytest.ini_options]` の `markers` に追記:
  ```toml
  markers = [
      "rag_model(name): テストで使用するモデル名をマーク（タイミングレポート用）",
      "characterization: リファクタ保護用の振る舞い固定テスト",
      "integration: 結合テスト (実DB・サービス組立て経由)",
  ]
  ```

### コミット単位・PR 構成
| # | PR タイトル | Phase | 内容 |
|---|------------|-------|------|
| 1 | test: characterize SEC XBRL parser output | A | XBRL parse ゴールデン |
| 2 | test: characterize compute_valuation outputs | A | Valuation ゴールデン |
| 3 | test: characterize CLI DI container assembly | A | container 組立て検証 |
| 4 | test: characterize verification report schema | A | JSON スキーマ固定 |
| 5 | test: characterize FilingType/PeriodType integration | A | enum 相当の文字列の統合検証 |
| 6 | test: cover missing branches in web routes & auth | B | 未カバー分岐潰し |
| 7 | test: cover missing branches in CLI & ingestion | B | 未カバー分岐潰し |
| 8 | test: service-layer integration via container | C | 結合テストシナリオ 2〜3本 |

**Status**: 承認済み (2026-04-18)

---

## セクション2: Phase A 詳細 (リファクタ保護網 5領域)

### 2-1. XBRL パーサー分割保護

**対象**: `SecXbrlParser` が将来 `ingestion/xbrl/{parser,taxonomy,period_filter}.py` に分割されても出力が変わらないこと。

**新設ファイル**:
- `tests/fixtures/xbrl/sample_sec_10k.json` — SEC Company Facts の実データから 5〜10 タグに絞った縮小版 (Revenues, NetIncomeLoss, Assets, Liabilities, EarningsPerShareBasic 等)。annual と quarterly の両方を含む。
- `tests/fixtures/xbrl/expected_parse_result.json` — 現行実装の出力をゴールデン値として保存。
- `tests/unit/characterization/test_xbrl_parse_golden.py`

**テスト構成**:
```python
class TestSecXbrlParserGolden:
    def test_annual_parse_matches_golden(self):
        parser = SecXbrlParser(...)
        result = parser.parse(sample_sec_10k, form="10-K")
        assert result == load_json("expected_parse_result.json")["annual"]

    def test_quarterly_parse_matches_golden(self): ...
    def test_period_filter_duration_ok_boundary(self): ...  # ANNUAL_MIN_DAYS=300 の前後
    def test_merge_near_dates_tolerance(self): ...          # 近接日付マージの境界
    def test_taxonomy_detection_us_gaap_vs_ifrs(self): ...
```

**フィクスチャ生成方針**:
- サンプルデータは既存 `tests/unit/ingestion/test_sec_xbrl_parser.py` の固定値を流用・拡張
- ゴールデン JSON は現行実装の出力を一度実行して保存 → git コミット
- 意図的変更時のみ手動で再生成。再生成コマンドを `tests/fixtures/xbrl/README.md` に明記

**既存テストとの棲み分け**:
- 既存 `test_sec_xbrl_parser.py`: 単体メソッド動作確認 (変更不要)
- 新設 characterization: パーサー全体の I/O スナップショット

**Status**: 承認済み (2026-04-18)

---

### 2-2. ValuationService 計算保護

**対象**: `compute_valuation_from_financials()` (現 `services/job.py:36-102`, 将来 `services/valuation.py` へ移動, Task 6) の計算結果が完全一致すること。

**新設ファイル**:
- `tests/fixtures/valuation/expected_valuation.json` — 代表企業 (US_AAPL 想定) の FinancialData 入力と期待指標 (PER / PBR / DividendYield / EarningsYield / EV-EBITDA 等)
- `tests/unit/characterization/test_valuation_compute_golden.py`

**テスト構成**:
```python
class TestComputeValuationGolden:
    def test_full_valuation_matches_golden(self):
        """全指標の計算結果を fixture と完全一致させる"""
        financials = FinancialData(revenue=..., net_income=..., ...)
        market_price = 150.0
        shares_outstanding = 15_700_000_000
        result = compute_valuation_from_financials(
            financials, market_price, shares_outstanding
        )
        assert result == load_expected("expected_valuation.json")

    def test_zero_net_income_handling(self): ...      # PER = None の分岐
    def test_missing_dividend_handling(self): ...     # DivYield = None の分岐
    def test_negative_equity_handling(self): ...      # PBR の扱い
    def test_fiscal_year_priority(self): ...          # annual vs quarterly の優先順位
```

**方針**:
- ゴールデン値は「仕様」として扱う。Task 6 移動後も同値を返す保証
- 境界テスト (ゼロ除算・欠損値) を4パターン以上網羅
- モックは使わず純粋関数として直接呼び出す

**検証観点**:
- 現 `job.py` と Task 6 実行後の `valuation.py` で、同じ入力に同じ出力を返すか (※Task 6 は既に実行済みであり、本テストは「現在位置 (`valuation.py`) から再度動かさない」保護網となる)

**Status**: 承認済み (2026-04-18)

---

### 2-3. CLI DI コンテナ組立て保護

**対象**: `cli/container.py` の `setup_services()` が組み立てる `ServiceContainer` の構造 (サービス型・依存関係・RAG 有効/無効の分岐) が変わらないこと。

**現状**: `container.py` は既に存在し動作するが、`setup_services()` 自体の直接テストはない。

**新設ファイル**:
- `tests/unit/characterization/test_container_assembly.py`

**テスト構成**:
```python
class TestSetupServicesAssembly:
    async def test_returns_container_with_all_required_services(self, session):
        """全必須サービスが組み立てられる (非None)"""
        config = build_test_config()
        services = await setup_services(session, config)
        assert services.company_service is not None
        assert services.financial_service is not None
        assert services.valuation_service is not None
        # ... (全9必須サービス)

    async def test_rag_service_none_when_pageindex_disabled(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)
        assert services.rag_service is None

    async def test_rag_service_created_when_pageindex_enabled(self, session):
        config = build_test_config(pageindex_enabled=True)
        services = await setup_services(session, config)
        assert services.rag_service is not None
        assert hasattr(services.rag_service, "pageindex_service")

    async def test_service_types_match_expectations(self, session):
        services = await setup_services(session, build_test_config())
        assert type(services.company_service).__name__ == "CompanyService"
        # ... (全サービス型名チェック)

    async def test_screening_service_default_none(self, session):
        """screening_service は現状 None (Phase 5 未実装)"""
        services = await setup_services(session, build_test_config())
        assert services.screening_service is None
```

**方針**:
- `session` フィクスチャ (既存 `tests/conftest.py` の in-memory SQLite) を流用
- 外部クライアント (SEC/EDINET/FMP/Yahoo) は初期化のみで実通信は発生しない。モック不要
- LlmClient の初期化がネットワークを叩く場合はダミー base_url を config で渡す
- `build_test_config()` ヘルパーを `tests/integration/conftest.py` に追加し、Phase C でも流用

**検証観点**:
- DI 配線が将来 `setup_services()` 内で変わっても、契約 (`ServiceContainer` の各フィールド型・RAG 有効分岐) が維持されているか

**Status**: 承認済み (2026-04-18)

---

### 2-4. 検証レポート JSON スキーマ保護

**対象**: `services/verification_report.py` の `save_verification_report()` が生成する JSON の構造とキー構成が変わらないこと。

**現状**: 既存 `tests/unit/services/test_verification_report.py` は基本動作のみ検証。全キースキーマは未網羅。

**新設ファイル**:
- `tests/fixtures/reports/expected_verification.json`
- `tests/unit/characterization/test_verification_report_schema.py`

**テスト構成**:
```python
class TestVerificationReportSchema:
    def test_top_level_keys(self, tmp_path):
        """トップレベルキー集合と型を固定"""
        report_path = save_verification_report(...)
        data = json.loads(report_path.read_text())
        expected_keys = {
            "company_id", "filing_id", "doc_name",
            "timestamp", "node_count", "phases",
        }
        assert set(data.keys()) == expected_keys
        assert isinstance(data["company_id"], str)
        assert isinstance(data["filing_id"], int)
        assert isinstance(data["phases"], list)

    def test_phase_schema(self, tmp_path):
        """各 phase エントリの必須キーと型"""
        phase = data["phases"][0]
        expected_phase_keys = {
            "mode", "accuracy", "checked_count",
            "correct_count", "incorrect_count", "items",
        }
        assert set(phase.keys()) == expected_phase_keys

    def test_item_schema(self, tmp_path):
        """各 item エントリのキー構成"""
        item = data["phases"][0]["items"][0]
        expected_item_keys = {
            "title", "page_number", "answer",
            "thinking", "page_text_snippet",
        }
        assert set(item.keys()) == expected_item_keys

    def test_matches_golden_snapshot(self, tmp_path):
        """代表入力 → 期待JSON ファイルとの完全一致 (timestampは除外)"""
        report_path = save_verification_report(
            company_id="US_AAPL", filing_id=1,
            tree=FIXED_TREE, verification_log=FIXED_LOG,
            node_count=10, output_dir=tmp_path,
        )
        actual = json.loads(report_path.read_text())
        expected = load_fixture("expected_verification.json")
        del actual["timestamp"]; del expected["timestamp"]
        assert actual == expected

    def test_unicode_preservation(self, tmp_path):
        """日本語文字列が escape されずに出力される"""
        raw = report_path.read_text()
        assert "売上高" in raw
        assert "\\u58f2" not in raw
```

**方針**:
- 既存 `test_verification_report.py` は残し、本ファイルでスキーマ契約を別観点で担保
- `expected_verification.json` は代表入力で生成し fixtures に保存
- 日本語非エスケープ (`ensure_ascii=False`) の保護を含める

**Status**: 承認済み (2026-04-18)

---

### 2-5. Enum 文字列互換性保護

**対象**: `FilingType` / `PeriodType` / `AccountingStandard` (StrEnum) がプレーン文字列と相互運用可能であること。将来 StrEnum から別形式 (plain `Literal`, `dataclass` 等) に変更された際、既存の文字列比較・DB 保存・argparse 入出力が壊れないよう固定する。

**現状**: 既存 `tests/unit/test_enums.py` は値確認のみ。外部システム (argparse, DB, JSON) との統合は未テスト。

**新設ファイル**:
- `tests/unit/characterization/test_enum_integration.py`

**テスト構成**:
```python
class TestFilingTypeStringCompat:
    def test_equals_plain_string(self):
        assert FilingType.TEN_K == "10-K"
        assert "10-K" == FilingType.TEN_K
        assert FilingType.TEN_K in ("10-K", "20-F")

    def test_dict_key_interchange(self):
        d = {FilingType.TEN_K: "annual report"}
        assert d["10-K"] == "annual report"  # str でアクセス

    def test_in_set_with_string(self):
        filed_forms = {"10-K", "20-F"}
        assert FilingType.TEN_K in filed_forms

    def test_json_serialization(self):
        data = {"type": FilingType.TEN_K}
        assert json.dumps(data) == '{"type": "10-K"}'


class TestFilingTypeArgparseIntegration:
    def test_argparse_accepts_enum_default(self):
        parser = argparse.ArgumentParser()
        add_filing_type_argument(parser)
        args = parser.parse_args([])
        assert args.filing_type == FilingType.TEN_K
        assert args.filing_type == "10-K"

    def test_argparse_accepts_valid_strings(self):
        for s in ("10-K", "10-Q", "20-F", "6-K"):
            args = parser.parse_args(["--filing-type", s])
            assert args.filing_type == s

    def test_argparse_rejects_invalid(self):
        with pytest.raises(SystemExit):
            parser.parse_args(["--filing-type", "ANNUAL_10K"])


class TestFilingTypeDatabaseRoundtrip:
    async def test_saved_as_plain_string(self, session):
        filing = Filing(company_id="US_X", form_type=FilingType.TEN_K, ...)
        session.add(filing); await session.commit()
        loaded = await session.get(Filing, filing.id)
        assert loaded.form_type == "10-K"
        assert loaded.form_type == FilingType.TEN_K


class TestPeriodType:
    # 同様に ANNUAL / QUARTERLY の相互運用性

class TestAccountingStandard:
    # 同様に US_GAAP / IFRS / JP_GAAP
```

**方針**:
- 既存 `test_enums.py` は軽量 (値のみ)。本ファイルで統合互換性を網羅
- DB ラウンドトリップには in-memory SQLite (`session` fixture) を使う
- 将来 StrEnum から変更された場合、本テスト群が落ちる → 文字列互換レイヤの追加要否を検知できる

**検証観点**:
- argparse / JSON / DB / dict / set すべてで enum ⇄ 文字列 の交換が可能であること

**Status**: 承認済み (2026-04-18)

---

## セクション3: Phase B 詳細 (未カバー分岐潰し)

### 方針
- **数値目標なし**。未カバー行を 1 件ずつレビューし「エラー分岐・バリデーション・条件分岐」に該当するもののみテスト追加
- 「外部 lib 呼び出し」「防御的 except で握りつぶしたログ出力」など、テスト困難かつ保守性に寄与しない行は `# pragma: no cover` で除外
- PR は 2 本: (6) Web/auth、(7) CLI/ingestion

### 未カバー行の分類 (2026-04-18 時点)

| カテゴリ | ファイル | 未カバー行 | 扱い |
|---------|---------|-----------|------|
| Web 認証未ログインリダイレクト | `web/routes/watchlists.py` `targets.py` `stocks.py` `dashboard.py` `rag.py` | 各 3-6 行 | **テスト追加** (unauthenticated → 302 Location=/login) |
| Web API エラーレスポンス | `web/routes/api.py` 16 行 (83, 98, 107-112, 125-126, 139-143, 155-160) | | **テスト追加** (404/400 パス) |
| Web jobs エラーハンドリング | `web/routes/jobs.py:52-54` | | **テスト追加** (sync 失敗時の flash) |
| web/auth.py 失敗系 | 69-71 (署名検証失敗), 80-86 (セッション無効/期限切れ) | | **テスト追加** (invalid signature / expired) |
| CLI エラーパス | `cli/watchlist.py` 各行, `cli/valuation.py` 各行 | | **テスト追加** (未登録 watchlist / 計算失敗時の出力) |
| CLI financial / target バリデーション | `cli/financial.py`, `cli/target.py` 各数行 | | **テスト追加** |
| PageIndexService 外部 lib 部 | `pageindex_service.py:242-292, 312-347` | 約 75 行 | **pragma 除外** (PageIndex lib の async builder 呼び出し部、モックが過剰に侵襲的になる) |
| PageIndexService その他 | `pageindex_service.py:158,161,163,222,448` | | **pragma 除外** (ロガー・fallback) |
| ingestion edinet_xbrl_parser | 19 行 | | **テスト追加** (重要分岐) / 軽微なログは **pragma 除外** |
| ingestion sec_edgar | 57-58, 68, 93-95 | | **テスト追加** (リトライ分岐・エラー時) |
| repositories screening.py | 37-42 | | **テスト追加** (未キャッシュ時の構築) |
| models/base.py | 38-39, 42 | | **pragma 除外** (sync fallback、async アプリでは通らない) |

### pragma 除外方針
除外対象は次の条件をすべて満たすもの:
1. モックすると実装詳細に過剰に結合する
2. 落ちても発見が容易 (起動時エラー・手動実行で即わかる)
3. 振る舞い固定にカバレッジが寄与しない (ログ、fallback)

それ以外はテスト追加で潰す。

### 想定される追加テスト数
- Web + auth: 約 15 テスト
- CLI: 約 10 テスト
- ingestion + repositories: 約 8 テスト
- **合計 約 30 テスト**

### 達成後の見込みカバレッジ
現状 92% → テスト追加 + pragma 除外で **96-98%** (結果論)

**Status**: 承認済み (2026-04-18)

---

## セクション4: Phase C 詳細 (結合テスト層)

### 方針
- **Service 組立て層のみ**: `cli/container.py` の `setup_services()` で実サービスを組み立て、in-memory SQLite 上で複数サービスが協調する代表シナリオを検証
- CLI/Web 表層は含めない (TestClient / subprocess を使わない)
- 外部 API のみモック (SEC / EDINET / FMP / Yahoo / LlmClient)
- PR は 1 本に集約

### 新設ファイル
```
tests/integration/
├── conftest.py                    # build_test_config(), 外部クライアントモック factory
└── test_service_assembly.py       # 3 シナリオ
```

### シナリオ1: 企業登録 → Filing Sync → Financial Sync → Valuation 計算

```python
class TestFullSyncFlow:
    async def test_new_company_complete_pipeline(
        self, session, mock_sec_client, mock_fmp_client
    ):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)

        # 1. Company 作成
        await services.company_service.create_company(
            company_id="US_TEST", name="Test Corp", ticker="TEST",
        )

        # 2. Filings sync
        mock_sec_client.set_filings([{"form": "10-K", ...}])
        result = await services.filing_sync.sync_filings("US_TEST")
        assert result.created_count == 1

        # 3. Financial sync
        mock_sec_client.set_company_facts({...})
        result = await services.financial_sync.sync_financials("US_TEST")
        assert result.created_count >= 1

        # 4. Valuation 計算
        latest = await services.financial_service.get_latest(
            "US_TEST", period_type=PeriodType.ANNUAL,
        )
        val = compute_valuation_from_financials(
            latest, market_price=150.0, shares_outstanding=1_000_000,
        )
        assert val["per"] is not None and val["pbr"] is not None
```

### シナリオ2: Watchlist + AnalysisTarget 連動

```python
class TestWatchlistTargetFlow:
    async def test_watchlist_with_targets_persistence(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)

        await services.company_service.create_company("US_A", "A Corp", "A")
        await services.company_service.create_company("US_B", "B Corp", "B")

        wl = await services.watchlist_service.create_watchlist("Tech")
        await services.watchlist_service.add_item(wl.id, "US_A")
        await services.watchlist_service.add_item(wl.id, "US_B")
        await services.target_service.add_target("US_A", priority=1)

        reloaded_wl = await services.watchlist_service.get_watchlist(wl.id)
        assert len(reloaded_wl.items) == 2
        targets = await services.target_service.list_targets()
        assert any(t.company_id == "US_A" for t in targets)

        await services.watchlist_service.remove_item(wl.id, "US_A")
        reloaded_wl = await services.watchlist_service.get_watchlist(wl.id)
        assert len(reloaded_wl.items) == 1
```

### シナリオ3: RAG 無効時のフォールバック動作

```python
class TestRagDisabledFallback:
    async def test_non_rag_features_work_when_rag_disabled(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)
        assert services.rag_service is None
        assert services.company_service is not None
        await services.company_service.create_company("US_X", "X", "X")

    async def test_rag_service_available_when_enabled(self, session):
        config = build_test_config(pageindex_enabled=True)
        services = await setup_services(session, config)
        assert services.rag_service is not None
        assert services.rag_service.pageindex_service is not None
```

### モック戦略 (`tests/integration/conftest.py`)

```python
@pytest.fixture
def mock_sec_client(monkeypatch):
    class _MockSec:
        def __init__(self):
            self._filings = []; self._facts = {}
        def set_filings(self, data): self._filings = data
        def set_company_facts(self, data): self._facts = data
        async def fetch_filings(self, cik, form_type): return self._filings
        async def fetch_company_facts(self, cik): return self._facts
        async def fetch_cik_by_ticker(self, t): return "0000000001"
    mock = _MockSec()
    monkeypatch.setattr(
        "stock_analyze_system.cli.container.SecEdgarClient",
        lambda **kw: mock,
    )
    return mock

# 同様に mock_fmp_client, mock_edinet_client, mock_yahoo_client, mock_llm_client

def build_test_config(pageindex_enabled: bool = False) -> AppConfig:
    """結合テスト用の最小 AppConfig"""
    return AppConfig(...)
```

### 注意点
- `AppConfig` の実構造を確認し `build_test_config()` を組む (環境変数依存を避ける)
- `setup_services()` 内で外部クライアントをインスタンス化しているため、`monkeypatch.setattr` で**モジュール参照先** (`cli.container` 側) を差し替える
- 既存 `conftest.py` の `async_engine` / `session` fixture を流用するため `tests/conftest.py` は触らない

**Status**: 承認済み (2026-04-18)

---

## セクション5: 実装規律・依存関係・受け入れ基準

### 5-1. テスト実装規律

**スナップショット (ゴールデン値) 生成ルール**
- `tests/fixtures/**/expected_*.json` は**手動生成・手動更新のみ**
- 初回生成は `scripts/generate_fixtures/` 配下の専用スクリプトで実行 (Phase A 各 Task の最後に作成)
- 再生成コマンドは各 fixture 近傍の `README.md` に明記
- CI で自動更新は禁止 (差分は必ず PR で確認する)

**フィクスチャ分離原則**
- 新設テストは既存テストのフィクスチャを壊さない。`session` 等は既存を流用、専用フィクスチャは `tests/integration/conftest.py` or `tests/unit/characterization/conftest.py` に置く
- in-memory SQLite は既存同様 per-test で再作成

**pytest マーカー運用**
- `characterization`: Phase A の特性化テスト。`pytest -m characterization` で単独実行可能
- `integration`: Phase C の結合テスト。`pytest -m integration` で単独実行可能
- デフォルトでは両方とも実行される

**アサーションスタイル**
- characterization: `assert actual == expected` (ゴールデン比較)
- behavioral: 明示的条件分岐アサート (`assert result.per is None`)
- スキーマ: `assert set(d.keys()) == {...}`
- スタイルを混在させない (1 ファイル 1 スタイル)

### 5-2. 依存関係・実行順序

```
PR 1-5 (Phase A: 各独立、順不同可)
  ├─ PR 1: XBRL parser golden
  ├─ PR 2: Valuation golden
  ├─ PR 3: Container assembly
  ├─ PR 4: Verification report schema
  └─ PR 5: Enum integration
         ↓
PR 6-7 (Phase B: Aが揃った後の安定状態で実施)
  ├─ PR 6: Web + auth 分岐潰し + pragma
  └─ PR 7: CLI + ingestion 分岐潰し + pragma
         ↓
PR 8 (Phase C: B完了後、config と mock 基盤を利用)
  └─ PR 8: Service assembly integration (3シナリオ)
```

- Phase A の 5 PR は並行レビュー可能 (領域が独立)
- Phase B は Phase A の完了を待つ (pragma 追加が既存テストと干渉しないことを確認するため)
- Phase C は Phase B 完了後 (config / mock 基盤を Phase B の修正込みで整えた状態でスタート)

### 5-3. 受け入れ基準 (全 PR 共通)

1. `pytest tests/ -v` 全件通過 (既存 632 + 新規)
2. `ruff check src/ tests/` エラーなし
3. `uv run pytest --cov=stock_analyze_system --cov-report=term` で該当領域のカバレッジが下がっていない
4. 新規テストが 100% 通過している
5. 新規 fixture ファイルは再生成手順が README に記載されている

### 5-4. リスクと緩和策

| リスク | 緩和策 |
|-------|-------|
| ゴールデン値が実装仕様と乖離している可能性 | Phase A 各 PR で「これはバグ? 仕様?」をレビュー対象に明記。バグの場合は spec を更新 |
| pragma 除外が過剰になる | PR 6-7 で除外行をレビューリストに明記。理由も PR description に書く |
| `setup_services()` モック差し替えが壊れやすい | `monkeypatch.setattr` の参照パスを定数化 (`tests/integration/_mock_paths.py`) |
| 結合テストが遅くなる | 各シナリオ独立 `session` fixture (in-memory) で 1 テスト < 1 秒を維持 |
| AppConfig の必須フィールド依存 | `build_test_config()` を Phase A-3 (container assembly) 時点で先出しして共有 |

### 5-5. 完了の定義 (Definition of Done)

- [x] Phase A 5 PR すべてマージ済み (PR 1-5)
- [x] Phase B 2 PR マージ済み (PR 6-7)
- [x] Phase C 1 PR マージ済み (PR 8)
- [x] `pytest tests/ -v` 全件通過 (718 tests: unit 673 + characterization 40 + integration 5)
- [x] `uv run pytest --cov` で 96% 以上 (**97%** 達成 / 未カバー 120/3563 行)
- [x] `tests/fixtures/` 配下に再生成手順 README 完備
- [x] `docs/superpowers/plans/2026-04-18-test-coverage-strengthening.md` (実装プラン) が新設・コミット済み

**Status**: 完了 (2026-04-18)

### 5-6. 最終結果

| 指標 | Before | After |
|---|---|---|
| テスト数 | 632 | **718** (+86) |
| 全体カバレッジ | 92% | **97%** |
| characterization マーカー | — | 40 tests (5 領域) |
| integration マーカー | — | 5 tests (`setup_services` 結合) |
| ruff `tests/` | clean | clean |

Phase A (特性化): PageIndex / SEC filings / XBRL / valuation / StrEnum の 5 領域でゴールデン固定。Phase B (分岐補完): web routes / CLI / ingestion の未カバーを補完、PageIndex 外部 lib 呼び出しは pragma で除外。Phase C (結合): `container.setup_services()` 経由で DB 永続化までの経路 3 シナリオを検証。

---

## 全セクション承認完了 (2026-04-18)

次の工程: `writing-plans` スキルを起動して実装プランを `docs/superpowers/plans/2026-04-18-test-coverage-strengthening.md` に生成する。その後 `executing-plans` で PR 1 から順次実装。
