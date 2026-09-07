"""Console logging configuration for the automation CLI."""

from __future__ import annotations

import logging


class AccountFilter(logging.Filter):
    def __init__(self, account_id: str) -> None:
        super().__init__()
        self.account_id = account_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.account_id = self.account_id
        return True


def configure_logging(account_id: str = "default") -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | %(account_id)s | "
            "%(name)s | %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(AccountFilter(account_id))
