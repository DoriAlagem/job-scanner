import pytest
from unittest.mock import MagicMock, patch
from src.email_sender import send


def _make_smtp_cls():
    """Return a mock SMTP class whose instances are also mocks (context manager ready)."""
    mock_instance = MagicMock()
    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)
    mock_cls = MagicMock(return_value=mock_instance)
    return mock_cls, mock_instance


def test_send_connects_to_correct_host_and_sends_to_recipient():
    mock_cls, mock_smtp = _make_smtp_cls()
    env = {"GMAIL_FROM": "from@gmail.com", "GMAIL_APP_PASSWORD": "secret"}

    with patch.dict("os.environ", env):
        send("Subject", "Body", "to@example.com", _smtp_cls=mock_cls)

    mock_cls.assert_called_once_with("smtp.gmail.com", 587)
    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with("from@gmail.com", "secret")
    mock_smtp.sendmail.assert_called_once()
    _, call_args, _ = mock_smtp.sendmail.mock_calls[0]
    assert call_args[1] == ["to@example.com"]


def test_send_raises_when_env_vars_missing():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(KeyError):
            send("Subject", "Body", "to@example.com")
