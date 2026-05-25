# XBRL Fixtures

## Files
- `sample_sec_10k.json`: SEC Company Facts の縮小サンプル (5タグ、annual + quarterly)
- `expected_parse_result.json`: `SecXbrlParser.parse_company_facts()` のゴールデン出力

## 再生成手順

実装を意図的に変更した場合のみ実行:

```bash
uv run python scripts/generate_fixtures/gen_xbrl_golden.py
```

差分は PR レビューで必ず確認すること。
