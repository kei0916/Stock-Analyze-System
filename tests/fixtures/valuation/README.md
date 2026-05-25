# Valuation Fixtures

## Files
- `expected_valuation.json`: `compute_valuation_from_financials()` の代表入力に対する期待出力

## 再生成手順

```bash
uv run python scripts/generate_fixtures/gen_valuation_golden.py
```

実装を意図的に変更した場合のみ。差分は PR で必ず確認する。
