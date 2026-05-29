"""パッケージエントリポイント: python -m stock_analyze_system / stock-analyze CLI"""
import asyncio

from stock_analyze_system.cli.app import main


def main_entry() -> int:
    """setuptools entry_points 用 同期エントリ。pyproject.toml [project.scripts] から参照される。"""
    asyncio.run(main())
    return 0


if __name__ == "__main__":
    main_entry()
