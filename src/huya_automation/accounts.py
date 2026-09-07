"""Account configuration for isolated parallel automation workers."""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_FILE = Path("config.toml")
ACCOUNT_KEYS = {"username", "password", "enabled"}


class AccountConfigError(RuntimeError):
    """Raised when multi-account configuration is missing or invalid."""


@dataclass(frozen=True)
class AccountConfig:
    username: str
    enabled: bool = True
    password: str | None = None

    @property
    def account_id(self) -> str:
        return self.username

    @property
    def storage_id(self) -> str:
        digest = hashlib.sha256(self.username.encode("utf-8")).hexdigest()
        return f"account-{digest[:16]}"


def load_payload(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as file:
            payload = tomllib.load(file)
    except FileNotFoundError as error:
        raise AccountConfigError(
            f"未找到配置文件：{path}。请复制 config.example.toml。"
        ) from error
    except tomllib.TOMLDecodeError as error:
        raise AccountConfigError(f"账号配置文件格式错误：{error}") from error
    except OSError as error:
        raise AccountConfigError(f"无法读取账号配置文件 {path}：{error}") from error
    return payload


def parse_account_credentials(
    payload: dict[str, object],
    label: str,
) -> tuple[str, str | None]:
    username = payload.get("username")
    password = payload.get("password")
    if not isinstance(username, str) or not username.strip():
        raise AccountConfigError(f"{label} 的 username 必须是字符串。")
    if password is not None and not isinstance(password, str):
        raise AccountConfigError(f"{label} 的 password 必须是字符串。")
    return username.strip(), password or None


def load_accounts(path: Path = DEFAULT_CONFIG_FILE) -> list[AccountConfig]:
    payload = load_payload(path)

    raw_accounts = payload.get("accounts")
    if not isinstance(raw_accounts, list) or not raw_accounts:
        raise AccountConfigError("账号配置必须包含至少一个 [[accounts]]。")

    accounts: list[AccountConfig] = []
    usernames: set[str] = set()
    for index, raw_account in enumerate(raw_accounts):
        if not isinstance(raw_account, dict):
            raise AccountConfigError(f"第 {index + 1} 个账号配置不是对象。")
        unknown_keys = set(raw_account) - ACCOUNT_KEYS
        if unknown_keys:
            raise AccountConfigError(
                f"第 {index + 1} 个账号包含未知配置项："
                f"{', '.join(sorted(unknown_keys))}"
            )
        username, password = parse_account_credentials(
            raw_account,
            f"第 {index + 1} 个账号",
        )
        if username in usernames:
            raise AccountConfigError(f"账号 username 重复：{username}")

        enabled = raw_account.get("enabled", True)
        if not isinstance(enabled, bool):
            raise AccountConfigError(
                f"账号 {username} 的 enabled 必须是布尔值。"
            )

        usernames.add(username)
        accounts.append(
            AccountConfig(
                username=username,
                enabled=enabled,
                password=password,
            )
        )
    return accounts


def find_account(
    accounts: list[AccountConfig],
    username: str,
) -> AccountConfig:
    for account in accounts:
        if account.username == username:
            return account
    raise AccountConfigError(f"账号配置中不存在 username：{username}")
