"""Check the installed wheel's public API outside the source checkout."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv
import zipfile


def test_installed_wheel_preserves_types_and_readonly_providers(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "source"
    source.mkdir()
    for name in ("setup.py", "pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(root / name, source / name)
    shutil.copytree(
        root / "src" / "train_operation_info",
        source / "src" / "train_operation_info",
        ignore=shutil.ignore_patterns("__pycache__"),
    )

    # Keep the checkout and any user PYTHONPATH out of the consumer's imports.
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("MYPYPATH", None)
    # Messages are matched as plain text; FORCE_COLOR would insert ANSI codes.
    env.pop("FORCE_COLOR", None)
    env.pop("MYPY_FORCE_COLOR", None)

    def run(*command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command, cwd=tmp_path, env=env, capture_output=True, text=True,
            encoding="utf-8", timeout=120,
        )

    wheels = tmp_path / "wheels"
    build = run(
        sys.executable, "-m", "pip", "wheel", "--no-index", "--no-deps",
        "--no-build-isolation", str(source), "--wheel-dir", str(wheels),
    )
    assert build.returncode == 0, build.stdout + build.stderr
    wheel, = wheels.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        assert "train_operation_info/py.typed" in archive.namelist()

    environment = tmp_path / "venv"
    # Reuse existing dependencies and tooling; never fetch packages from the web.
    venv.EnvBuilder(system_site_packages=True, with_pip=False).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    install = run(
        str(python), "-m", "pip", "install", "--no-index", "--no-deps",
        "--ignore-installed", str(wheel),
    )
    assert install.returncode == 0, install.stdout + install.stderr
    location = run(
        str(python), "-c",
        "import sys; from pathlib import Path; import train_operation_info as package; "
        "assert Path(package.__file__).resolve().is_relative_to(sys.prefix)",
    )
    assert location.returncode == 0, location.stdout + location.stderr

    consumer = tmp_path / "consumer.py"
    consumer.write_text(
        "from train_operation_info import Tracker\n"
        "from train_operation_info.models import Line\n"
        "from train_operation_info.providers.jreast import JrEastProvider\n"
        "from train_operation_info.providers.jrcentral import JrCentralProvider\n"
        "from train_operation_info.providers.jrkyushu import JrKyushuProvider\n"
        "from train_operation_info.providers.nankai import NankaiProvider\n"
        "from train_operation_info.providers.hakone_tozan import HakoneTozanProvider\n"
        "from train_operation_info.providers.tokyo_metro import TokyoMetroProvider\n\n"
        "from train_operation_info.providers.tosaden import TosadenProvider\n\n"
        "from train_operation_info.providers.meitetsu import MeitetsuProvider\n"
        "from train_operation_info.providers.tra import TraProvider\n"
        "from train_operation_info.providers.db import DbProvider\n"
        "from train_operation_info.providers.transilien import TransilienProvider\n"
        "from train_operation_info.providers.obb import ObbProvider\n"
        'europe = Tracker(enabled_providers=("db", "transilien", "obb"))\n'
        "db: DbProvider = europe.db\n"
        "transilien: TransilienProvider = europe.transilien\n"
        "obb: ObbProvider = europe.obb\n"
        "fernverkehr: Line = db.fernverkehr\n"
        "rer_d: Line = transilien.rer_d\n"
        "obb_network: Line = obb.network\n"
        "tra = TraProvider()\n"
        'tra_tracker = Tracker(enabled_providers=("tra",), overrides=(tra,))\n'
        "assert tra_tracker.tra is tra\n"
        "assert tra_tracker.providers == (tra,)\n"
        "tra_eastern: Line = tra_tracker.tra.eastern\n"
        "tra_pingxi: Line = tra_tracker.tra.pingxi\n"
        "provider = NankaiProvider()\n"
        'tracker = Tracker(enabled_providers=("nankai",), overrides=(provider,))\n'
        "assert tracker.nankai is provider\n"
        "assert tracker.providers == (provider,)\n"
        "line: Line = tracker.nankai.main\n"
        "hakone = HakoneTozanProvider()\n"
        'hakone_tracker = Tracker(enabled_providers=("hakone_tozan",), overrides=(hakone,))\n'
        "assert hakone_tracker.hakone_tozan is hakone\n"
        "assert hakone_tracker.providers == (hakone,)\n"
        "hakone_line: Line = hakone_tracker.hakone_tozan.main\n"
        "central = JrCentralProvider()\n"
        'central_tracker = Tracker(enabled_providers=("jrcentral",), overrides=(central,))\n'
        "assert central_tracker.jrcentral is central\n"
        "assert central_tracker.providers == (central,)\n"
        "tokaido: Line = central_tracker.jrcentral.tokaido_atami_toyohashi\n"
        "chuo: Line = central_tracker.jrcentral.chuo\n"
        "kyushu = JrKyushuProvider()\n"
        'kyushu_tracker = Tracker(enabled_providers=("jrkyushu",), overrides=(kyushu,))\n'
        "assert kyushu_tracker.jrkyushu is kyushu\n"
        "assert kyushu_tracker.providers == (kyushu,)\n"
        "fukuoka: Line = kyushu_tracker.jrkyushu.fukuoka_kitakyushu\n"
        "kyushu_shin: Line = kyushu_tracker.jrkyushu.kyushu_shinkansen\n"
        "nishi_shin: Line = kyushu_tracker.jrkyushu.nishi_kyushu_shinkansen\n"
        "east = JrEastProvider()\n"
        'east_tracker = Tracker(enabled_providers=("jreast",), overrides=(east,))\n'
        "assert east_tracker.jreast is east\n"
        "assert east_tracker.providers == (east,)\n"
        "yamanote: Line = east_tracker.jreast.yamanote\n"
        "shinkansen: Line = east_tracker.jreast.tohoku_shinkansen\n"
        "metro = TokyoMetroProvider()\n"
        'metro_tracker = Tracker(enabled_providers=("tokyo_metro",), overrides=(metro,))\n'
        "assert metro_tracker.tokyo_metro is metro\n"
        "assert metro_tracker.providers == (metro,)\n"
        "ginza: Line = metro_tracker.tokyo_metro.ginza\n"
        "tozai: Line = metro_tracker.tokyo_metro.tozai\n"
        "tosaden = TosadenProvider()\n"
        'tosaden_tracker = Tracker(enabled_providers=("tosaden",), overrides=(tosaden,))\n'
        "assert tosaden_tracker.tosaden is tosaden\n"
        "assert tosaden_tracker.providers == (tosaden,)\n"
        "streetcar: Line = tosaden_tracker.tosaden.main\n"
        "meitetsu = MeitetsuProvider()\n"
        'meitetsu_tracker = Tracker(enabled_providers=("meitetsu",), overrides=(meitetsu,))\n'
        "assert meitetsu_tracker.meitetsu is meitetsu\n"
        "assert meitetsu_tracker.providers == (meitetsu,)\n"
        "nagoya_main: Line = meitetsu_tracker.meitetsu.nagoya_main\n"
        "airport: Line = meitetsu_tracker.meitetsu.tokoname_airport\n",
        encoding="utf-8",
    )
    runtime = run(str(python), str(consumer))
    assert runtime.returncode == 0, runtime.stdout + runtime.stderr
    mypy = (
        str(python), "-m", "mypy", "--strict", "--no-incremental",
        "--python-executable", str(python), "--cache-dir", str(tmp_path / "mypy-cache"),
        "--show-error-codes", str(consumer),
    )
    valid = run(*mypy)
    assert valid.returncode == 0, valid.stdout + valid.stderr

    with consumer.open("a", encoding="utf-8") as handle:
        handle.write(
            "tracker.nankai = NankaiProvider()\n"
            "tracker.nankai.nonexistent\n"
            "wrong: str = tracker.nankai.main\n"
            "east_tracker.jreast = JrEastProvider()\n"
            "east_tracker.jreast.nonexistent\n"
            "wrong_east: str = east_tracker.jreast.yamanote\n"
            "metro_tracker.tokyo_metro = TokyoMetroProvider()\n"
            "metro_tracker.tokyo_metro.nonexistent\n"
            "wrong_metro: str = metro_tracker.tokyo_metro.ginza\n"
            "tosaden_tracker.tosaden = TosadenProvider()\n"
            "tosaden_tracker.tosaden.nonexistent\n"
            "wrong_tosaden: str = tosaden_tracker.tosaden.main\n"
            "meitetsu_tracker.meitetsu = MeitetsuProvider()\n"
            "meitetsu_tracker.meitetsu.nonexistent\n"
            "wrong_meitetsu: str = meitetsu_tracker.meitetsu.nagoya_main\n"
            "kyushu_tracker.jrkyushu = JrKyushuProvider()\n"
            "kyushu_tracker.jrkyushu.nonexistent\n"
            "wrong_kyushu: str = kyushu_tracker.jrkyushu.fukuoka_kitakyushu\n"
            "tra_tracker.tra = TraProvider()\n"
            "tra_tracker.tra.nonexistent\n"
            "wrong_tra: str = tra_tracker.tra.pingxi\n"
        )
    invalid = run(*mypy)
    assert invalid.returncode == 1, invalid.stdout + invalid.stderr
    # Slots accept no assignment: mypy reports the target type as Never.
    assert 'variable has type "Never"' in invalid.stdout, invalid.stdout
    assert 'has no attribute "nonexistent"' in invalid.stdout, invalid.stdout
    assert "[assignment]" in invalid.stdout, invalid.stdout
    assert "Found 21 errors" in invalid.stdout, invalid.stdout
