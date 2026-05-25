.PHONY: docs docs-serve docs-full docs-clean

# Living Docs (ADR-005) — P1
# gen_docs.py が docs/generated と docs-site/docs を clean 再生成する

docs:
	uv run python -m scripts.gen_docs --repo-root .
	cd docs-site && npm run build

# spec §8 に合わせ、docs-serve はビルド済みサイトの serve とする
# (dev server の npm run start ではなく、build → serve の順)
docs-serve: docs
	cd docs-site && npm run serve

# P1/P2 の間は docs-full は docs と同等。test-coverage-map は P3 で追加
docs-full: docs
	@echo "[make] NOTE: test-coverage-map is not implemented yet (planned for P3)"

docs-clean:
	rm -rf docs/generated docs-site/docs docs-site/build docs-site/.docusaurus
