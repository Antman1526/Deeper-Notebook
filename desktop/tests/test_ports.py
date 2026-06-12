import socket

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
