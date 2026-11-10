from pathlib import Path

import pytest

from anschlussradar.ingest.hubs import load_hubs
from anschlussradar.ml.features import TransferInput, min_transfer_minutes

ROOT = Path(__file__).resolve().parents[1]


def test_real_hub_list_loads_and_groups_frankfurt_levels() -> None:
    hubs = {h.eva: h for h in load_hubs(ROOT / "config" / "hubs.csv")}
    assert hubs[8098105].group_eva == 8000105  # Frankfurt Hbf (tief), S-Bahn level
    assert hubs[8000105].group_eva == 8000105
    assert hubs[8000207].group_eva == 8000207  # no group given: its own


def test_group_must_exist(tmp_path: Path) -> None:
    f = tmp_path / "hubs.csv"
    f.write_text("eva,name,state,priority,group\n8098105,Tief,HE,1,8000105\n", encoding="utf-8")
    with pytest.raises(ValueError, match="group 8000105"):
        load_hubs(f)


def test_cross_level_transfer_takes_longer() -> None:
    assert min_transfer_minutes("S", "ICE", cross_level=True) == min_transfer_minutes("S", "ICE") + 2
