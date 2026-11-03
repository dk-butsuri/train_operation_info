"""Parser tests refresh the same provider repeatedly; tests/test_rate_limit.py covers the limit.

Captured third-party pages in tests/fixtures are not committed (see CONTRIBUTING.md, section 6).
Tests that need a missing capture are skipped instead of failing; other errors still fail.
"""

from collections.abc import Generator, Iterable
from pathlib import Path

import pytest

from train_operation_info.providers import base

_FIXTURES = (Path(__file__).parent / "fixtures").resolve()


def _skip_if_missing_fixture(exc: FileNotFoundError, *, module_level: bool = False) -> None:
    if exc.filename is None or not Path(exc.filename).resolve().is_relative_to(_FIXTURES):
        return
    pytest.skip(
        f"captured fixture not available locally: {Path(exc.filename).name}",
        allow_module_level=module_level,
    )


class _FixtureAwareModule(pytest.Module):
    def collect(self) -> Iterable[pytest.Item | pytest.Collector]:
        try:
            return super().collect()  # Imports the test module.
        except FileNotFoundError as exc:
            _skip_if_missing_fixture(exc, module_level=True)
            raise


def pytest_pycollect_makemodule(module_path: Path, parent: pytest.Collector) -> pytest.Module:
    return _FixtureAwareModule.from_parent(parent, path=module_path)


@pytest.hookimpl(wrapper=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> Generator[None, object, object]:
    try:
        return (yield)
    except FileNotFoundError as exc:
        _skip_if_missing_fixture(exc)
        raise


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(
    fixturedef: pytest.FixtureDef[object], request: pytest.FixtureRequest
) -> Generator[None, object, object]:
    try:
        return (yield)
    except FileNotFoundError as exc:
        _skip_if_missing_fixture(exc)
        raise


@pytest.fixture(autouse=True)
def _no_default_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base, "DEFAULT_RATE_LIMIT", 0.0)
    # Mock transports only; the shipped floor is checked in tests/test_rate_limit.py.
    monkeypatch.setattr(base, "MIN_RATE_LIMIT", 0.0)
