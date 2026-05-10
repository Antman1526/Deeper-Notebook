import desktop


def test_package_importable():
    assert desktop.__version__ == "0.1.0"
