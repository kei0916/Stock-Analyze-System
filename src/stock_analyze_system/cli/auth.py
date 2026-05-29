"""CLI: 認証関連のヘルパ (パスワードハッシュ生成)"""
from __future__ import annotations

import getpass
import sys


def register_parser(subparsers) -> None:
    parser = subparsers.add_parser("auth", help="認証関連コマンド")
    auth_sub = parser.add_subparsers(dest="auth_command", required=True)

    hash_parser = auth_sub.add_parser(
        "hash-password",
        help="WEB_PASSWORD_HASH 用の bcrypt ハッシュを生成する",
    )
    hash_parser.set_defaults(handler=_hash_password_handler)


async def _hash_password_handler(args, _services_or_config) -> int:
    from stock_analyze_system.web.auth import hash_password

    plaintext = getpass.getpass("Password: ")
    if not plaintext:
        sys.stderr.write("Password must not be empty.\n")
        return 1
    confirm = getpass.getpass("Confirm: ")
    if plaintext != confirm:
        sys.stderr.write("Passwords do not match.\n")
        return 1
    sys.stdout.write(hash_password(plaintext) + "\n")
    return 0
