"""Webサーバー起動サブコマンド"""
from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stock_analyze_system.config import AppConfig


def _valid_port(value: str) -> int:
    """ポート番号が 1〜65535 の範囲内か検証する argparse 用 type 関数。"""
    port = int(value)
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError(
            f"Port must be between 1 and 65535, got {port}",
        )
    return port


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """`serve` サブコマンドの argparse parser を登録する。

    Args:
        subparsers: 親 parser の `add_subparsers()` 戻り値。
    """
    parser = subparsers.add_parser("serve", help="Webサーバー起動")
    parser.add_argument(
        "--host", type=str, default=None,
        help="バインドホスト (default: configから取得)",
    )
    parser.add_argument(
        "--port", type=_valid_port, default=None,
        help="バインドポート (default: configから取得)",
    )
    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, config: AppConfig) -> None:
    """`serve` サブコマンドのエントリポイント。uvicorn でアプリを起動する。

    Args:
        args: argparse の解析結果 (`--host` / `--port`)。
        config: アプリ設定 (host/port 未指定時のデフォルト供給源)。
    """
    import uvicorn

    host = args.host if args.host is not None else config.web.host
    port = args.port if args.port is not None else config.web.port

    print(f"Starting server on {host}:{port}...")
    # cli/app.py が asyncio ループ内で handle() を await するため、
    # 同期の uvicorn.run() ではなく Server.serve() を使う
    server_config = uvicorn.Config(
        "stock_analyze_system.web:create_app",
        host=host,
        port=port,
        factory=True,
    )
    await uvicorn.Server(server_config).serve()
