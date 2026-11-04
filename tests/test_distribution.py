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
        "from train_operation_info.providers.saitama_railway import SaitamaRailwayProvider\n"
        "sr_tracker = Tracker(enabled_providers=('saitama_railway',))\n"
        "sr: SaitamaRailwayProvider = sr_tracker.saitama_railway\n"
        "sr_line: Line = sr.main\n"
        "from train_operation_info.providers.tfl import TflProvider\n"
        "tfl_tracker = Tracker(enabled_providers=('tfl',))\n"
        "tfl: TflProvider = tfl_tracker.tfl\n"
        "bakerloo: Line = tfl.bakerloo\n"
        "elizabeth: Line = tfl.elizabeth\n"
        "windrush: Line = tfl.windrush\n"
        "from train_operation_info.providers.yokohama_subway import YokohamaSubwayProvider\n"
        "yokohama_tracker = Tracker(enabled_providers=('yokohama_subway',))\n"
        "yokohama: YokohamaSubwayProvider = yokohama_tracker.yokohama_subway\n"
        "yokohama_blue: Line = yokohama.blue\n"
        "yokohama_green: Line = yokohama.green\n"
        "from train_operation_info.providers.taoyuan_metro import TaoyuanMetroProvider\n"
        "from train_operation_info.providers.kaohsiung_metro import KaohsiungMetroProvider\n"
        "kaohsiung_tracker = Tracker(enabled_providers=('kaohsiung_metro',))\n"
        "kaohsiung: KaohsiungMetroProvider = kaohsiung_tracker.kaohsiung_metro\n"
        "kaohsiung_mrt: Line = kaohsiung.metro\n"
        "kaohsiung_lrt: Line = kaohsiung.light_rail\n"
        "taoyuan_tracker = Tracker(enabled_providers=('taoyuan_metro',))\n"
        "taoyuan: TaoyuanMetroProvider = taoyuan_tracker.taoyuan_metro\n"
        "taoyuan_airport: Line = taoyuan.airport\n"
        "from train_operation_info.providers.tosakuro import TosaKuroshioProvider\n"
        "tosakuro_tracker = Tracker(enabled_providers=('tosakuro',))\n"
        "tosakuro: TosaKuroshioProvider = tosakuro_tracker.tosakuro\n"
        "gomen_nahari: Line = tosakuro.gomen_nahari\n"
        "nakamura_sukumo: Line = tosakuro.nakamura_sukumo\n"
        "from train_operation_info.providers.sendai_subway import SendaiSubwayProvider\n"
        "sendai_tracker = Tracker(enabled_providers=('sendai_subway',))\n"
        "sendai: SendaiSubwayProvider = sendai_tracker.sendai_subway\n"
        "sendai_namboku: Line = sendai.namboku\n"
        "sendai_tozai: Line = sendai.tozai\n"
        "from train_operation_info.providers.fukuoka_subway import FukuokaSubwayProvider\n"
        "fukuoka_tracker = Tracker(enabled_providers=('fukuoka_subway',))\n"
        "fukuoka_subway: FukuokaSubwayProvider = fukuoka_tracker.fukuoka_subway\n"
        "kuko: Line = fukuoka_subway.kuko\n"
        "hakozaki: Line = fukuoka_subway.hakozaki\n"
        "nanakuma: Line = fukuoka_subway.nanakuma\n"
        "from train_operation_info.providers.renfe import RenfeProvider\n"
        "renfe_tracker = Tracker(enabled_providers=('renfe',))\n"
        "renfe: RenfeProvider = renfe_tracker.renfe\n"
        "cercanias: Line = renfe.cercanias\n"
        "from train_operation_info.providers.metro_north import MetroNorthProvider\n"
        "mnr = MetroNorthProvider()\n"
        "mnr_tracker = Tracker(enabled_providers=('metro_north',), overrides=(mnr,))\n"
        "metro_north: MetroNorthProvider = mnr_tracker.metro_north\n"
        "assert metro_north is mnr and mnr_tracker.providers == (mnr,)\n"
        "hudson: Line = metro_north.hudson\n"
        "harlem: Line = metro_north.harlem\n"
        "new_haven: Line = metro_north.new_haven\n"
        "new_canaan: Line = metro_north.new_canaan\n"
        "danbury: Line = metro_north.danbury\n"
        "waterbury: Line = metro_north.waterbury\n"
        "pascack_valley: Line = metro_north.pascack_valley\n"
        "port_jervis: Line = metro_north.port_jervis\n"
        "wassaic: Line = metro_north.wassaic\n"
        "from train_operation_info.providers.mtr import MtrProvider\n"
        "mtr_tracker = Tracker(enabled_providers=('mtr',))\n"
        "mtr: MtrProvider = mtr_tracker.mtr\n"
        "tsuen_wan: Line = mtr.tsuen_wan\n"
        "airport_express: Line = mtr.airport_express\n"
        "from train_operation_info.providers.nishitetsu import NishitetsuProvider\n"
        "nishitetsu_tracker = Tracker(enabled_providers=('nishitetsu',))\n"
        "nishitetsu: NishitetsuProvider = nishitetsu_tracker.nishitetsu\n"
        "tenjin_omuta: Line = nishitetsu.tenjin_omuta\n"
        "dazaifu: Line = nishitetsu.dazaifu\n"
        "amagi: Line = nishitetsu.amagi\n"
        "kaizuka: Line = nishitetsu.kaizuka\n"
        "from train_operation_info.providers.jreast import JrEastProvider\n"
        "from train_operation_info.providers.jrcentral import JrCentralProvider\n"
        "from train_operation_info.providers.jrkyushu import JrKyushuProvider\n"
        "from train_operation_info.providers.nankai import NankaiProvider\n"
        "from train_operation_info.providers.sotetsu import SotetsuProvider\n"
        "sotetsu_tracker = Tracker(enabled_providers=('sotetsu',))\n"
        "sotetsu: SotetsuProvider = sotetsu_tracker.sotetsu\n"
        "sotetsu_line: Line = sotetsu.main\n"
        "from train_operation_info.providers.kyoto_subway import KyotoSubwayProvider\n"
        "kyoto_tracker = Tracker(enabled_providers=('kyoto_subway',))\n"
        "kyoto: KyotoSubwayProvider = kyoto_tracker.kyoto_subway\n"
        "karasuma: Line = kyoto.karasuma\n"
        "kyoto_tozai: Line = kyoto.tozai\n"
        "from train_operation_info.providers.hakone_tozan import HakoneTozanProvider\n"
        "from train_operation_info.providers.tokyo_metro import TokyoMetroProvider\n\n"
        "from train_operation_info.providers.tosaden import TosadenProvider\n\n"
        "from train_operation_info.providers.meitetsu import MeitetsuProvider\n"
        "from train_operation_info.providers.tra import TraProvider\n"
        "from train_operation_info.providers.db import DbProvider\n"
        "from train_operation_info.providers.transilien import TransilienProvider\n"
        "from train_operation_info.providers.obb import ObbProvider\n"
        "from train_operation_info.providers.trenitalia import TrenitaliaProvider\n"
        "from train_operation_info.providers.tgv import TgvProvider\n"
        'tgv_tracker = Tracker(enabled_providers=("tgv",))\n'
        "tgv: TgvProvider = tgv_tracker.tgv\n"
        "tgv_network: Line = tgv.network\n"
        'trenitalia_tracker = Tracker(enabled_providers=("trenitalia",))\n'
        "trenitalia: TrenitaliaProvider = trenitalia_tracker.trenitalia\n"
        "trenitalia_network: Line = trenitalia.network\n"
        'europe = Tracker(enabled_providers=("db", "transilien", "obb"))\n'
        "db: DbProvider = europe.db\n"
        "transilien: TransilienProvider = europe.transilien\n"
        "obb: ObbProvider = europe.obb\n"
        "fernverkehr: Line = db.fernverkehr\n"
        "rer_d: Line = transilien.rer_d\n"
        "metro_1: Line = transilien.metro_1\n"
        "metro_3bis: Line = transilien.metro_3bis\n"
        "metro_7bis: Line = transilien.metro_7bis\n"
        "metro_14: Line = transilien.metro_14\n"
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
