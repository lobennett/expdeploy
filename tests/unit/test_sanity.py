from expdeploy import __version__


def test_version_is_stable():
    assert __version__ == "0.1.0"


def test_version_is_str():
    assert isinstance(__version__, str)
