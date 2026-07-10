"""Microsoft Outlook Desktop COM Automation wrapper.

Uses ``pywin32`` to drive the already-installed, already-configured
Outlook desktop client. Deliberately does NOT use Microsoft Graph or
Azure, and does not require administrator permissions -- it simply
automates the same Outlook application a user would use interactively.

Import of ``win32com.client`` is done lazily inside the class so this
module can still be imported (and partially unit-tested with mocks) on
non-Windows machines / CI systems that don't have pywin32's COM support.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Iterator, Optional

from src.config_loader import Settings

logger = logging.getLogger(__name__)

# Outlook constants (avoids a hard dependency on win32com.client.constants
# at import time).
OL_MAIL_ITEM = 0
OL_FOLDER_INBOX = 6


class OutlookClientError(Exception):
    """Raised for any unrecoverable Outlook automation failure."""


@dataclass(frozen=True)
class OutlookMessage:
    """A read-only view of an Outlook MailItem, with just the fields this
    project needs."""

    entry_id: str
    conversation_id: Optional[str]
    conversation_index: Optional[str]
    subject: str
    sender_email: str
    received_time: Optional[datetime]
    body: str
    html_body: str


class OutlookClient:
    """Wraps Outlook COM automation for sending and reading mail.

    The underlying Outlook Application object is created lazily on first
    use and cached for the lifetime of this client.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._app: Any = None
        self._namespace: Any = None

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------
    def _connect(self) -> None:
        if self._app is not None:
            return
        try:
            import win32com.client  # type: ignore
        except ImportError as exc:
            raise OutlookClientError(
                "pywin32 is not installed or not available on this platform. "
                "This application must run on Windows with Outlook Desktop installed."
            ) from exc

        try:
            self._app = win32com.client.Dispatch("Outlook.Application")
            self._namespace = self._app.GetNamespace("MAPI")
        except Exception as exc:  # pragma: no cover - COM error surface is broad
            raise OutlookClientError(
                "Could not connect to Outlook. Make sure Outlook Desktop is "
                "installed and has been opened at least once on this machine."
            ) from exc

    def _get_inbox(self) -> Any:
        self._connect()
        try:
            if self._settings.outlook.send_from_account:
                for account in self._namespace.Folders:
                    if account.Name == self._settings.outlook.send_from_account:
                        return account.Folders(self._settings.outlook.inbox_folder_name)
                raise OutlookClientError(
                    f"Account '{self._settings.outlook.send_from_account}' not found in Outlook profile"
                )
            return self._namespace.GetDefaultFolder(OL_FOLDER_INBOX)
        except OutlookClientError:
            raise
        except Exception as exc:  # pragma: no cover
            raise OutlookClientError("Could not access the Outlook Inbox folder") from exc

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def send_html_email(
        self, to_email: str, subject: str, html_body: str
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Send an HTML email and return (entry_id, conversation_id,
        conversation_index) for the sent item, when available.

        Note: Outlook does not always expose ConversationID for an item
        immediately after ``Send()``; callers should treat these as
        best-effort and rely on ConversationID/Subject/ReminderID matching
        when scanning replies later.
        """
        self._connect()
        try:
            mail = self._app.CreateItem(OL_MAIL_ITEM)
            mail.To = to_email
            mail.Subject = subject
            mail.HTMLBody = html_body
            if self._settings.outlook.send_from_account:
                mail.SentOnBehalfOfName = self._settings.outlook.send_from_account
            mail.Send()
        except Exception as exc:  # pragma: no cover
            raise OutlookClientError(f"Failed to send email to {to_email}") from exc

        entry_id = getattr(mail, "EntryID", None)
        conversation_id = getattr(mail, "ConversationID", None)
        conversation_index = getattr(mail, "ConversationIndex", None)

        time.sleep(self._settings.outlook.send_delay_seconds)
        return entry_id, conversation_id, conversation_index

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    def iter_recent_inbox_messages(self) -> Iterator[OutlookMessage]:
        """Yield inbox messages received within the configured lookback
        window, most recent first.
        """
        inbox = self._get_inbox()
        cutoff = datetime.now() - timedelta(days=self._settings.outlook.reply_lookback_days)

        try:
            items = inbox.Items
            items.Sort("[ReceivedTime]", True)  # descending
        except Exception as exc:  # pragma: no cover
            raise OutlookClientError("Could not read items from the Inbox") from exc

        for item in items:
            try:
                # MailItem.Class == 43 in Outlook's object model; skip
                # meeting requests, receipts, etc.
                if getattr(item, "Class", 43) != 43:
                    continue
                received_time = self._to_datetime(getattr(item, "ReceivedTime", None))
                if received_time and received_time < cutoff:
                    break  # sorted descending, so we can stop early

                yield OutlookMessage(
                    entry_id=item.EntryID,
                    conversation_id=getattr(item, "ConversationID", None),
                    conversation_index=getattr(item, "ConversationIndex", None),
                    subject=getattr(item, "Subject", "") or "",
                    sender_email=self._resolve_sender_email(item),
                    received_time=received_time,
                    body=getattr(item, "Body", "") or "",
                    html_body=getattr(item, "HTMLBody", "") or "",
                )
            except Exception:  # pragma: no cover
                logger.exception("Skipping an inbox item that could not be read")
                continue

    @staticmethod
    def _resolve_sender_email(item: Any) -> str:
        """Best-effort resolution of the sender's SMTP address, falling
        back gracefully for Exchange-cached addresses."""
        try:
            sender = item.Sender
            exchange_user = sender.GetExchangeUser() if sender is not None else None
            if exchange_user is not None:
                return exchange_user.PrimarySmtpAddress
        except Exception:  # pragma: no cover
            pass
        return getattr(item, "SenderEmailAddress", "") or ""

    @staticmethod
    def _to_datetime(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:  # pragma: no cover
            return None
