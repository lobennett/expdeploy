from expdeploy import __version__


def test_version_is_alpha():
    assert __version__ == "0.1.0a0"


def test_version_is_str():
    assert isinstance(__version__, str)
