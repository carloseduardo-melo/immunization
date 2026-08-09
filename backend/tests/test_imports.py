import importlib


def test_app_imports():
    module = importlib.import_module("app.main")
    assert module.app is not None
