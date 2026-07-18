import socket

import desktop.ports as ports_mod
from desktop.ports import find_free_port, find_free_ports


def test_find_free_port_returns_open_port():
    port = find_free_port()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", port))
    s.close()


def test_find_free_ports_returns_distinct():
    ports = find_free_ports(4)
    assert len(set(ports)) == 4
    for p in ports:
        assert 1024 < p < 65536


def test_find_free_ports_zero_returns_empty():
    assert find_free_ports(0) == []


def test_find_free_ports_listens_while_reserving_candidates(monkeypatch):
    created = []

    class FakeSocket:
        def __init__(self, port):
            self.port = port
            self.listened = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def bind(self, _address):
            return None

        def listen(self, _backlog):
            self.listened = True

        def getsockname(self):
            return ("127.0.0.1", self.port)

    def make_socket():
        sock = FakeSocket(51000 + len(created))
        created.append(sock)
        return sock

    monkeypatch.setattr(ports_mod, "_make_probe_socket", make_socket)

    assert find_free_ports(3) == [51000, 51001, 51002]
    assert all(sock.listened for sock in created)
