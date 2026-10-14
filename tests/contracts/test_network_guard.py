"""A planted connect proves the no-network gate can reject real call sites."""

import socket

import pytest


def test_connect_is_denied_before_socket_or_provider_dispatch():
    with pytest.raises(AssertionError, match="Network is disabled"):
        socket.create_connection(("127.0.0.1", 9))
