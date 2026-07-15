"""Gateway test configuration."""

pytest_plugins = []


def pytest_configure(config):
    config.option.asyncio_mode = "auto"
