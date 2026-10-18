"""Tests for zone display name mapping."""

import pytest

from titrack.data.zones import get_zone_display_name


def _path(folder: str, name: str) -> str:
    return f"/Game/Art/Maps/{folder}/{name}/{name}"


class TestGetZoneDisplayName:
    """Tests for get_zone_display_name."""

    def test_mundane_palace_not_matched_as_hideout(self):
        path = _path("04DD", "DD_ShengTingZhuangYuan000")
        assert get_zone_display_name(path, 4657) == "Voidlands - Mundane Palace"

    def test_sacred_court_manor_hideout(self):
        path = _path("04DD", "DD_ShengTingZhuangYuan")
        assert get_zone_display_name(path) == "Hideout - Sacred Court Manor"

    @pytest.mark.parametrize("level_id", [4207, 4307, 4606])
    def test_grimwind_woods_glacial_suffixes(self, level_id):
        path = _path("03YL", "YL_BeiFengLinDi201")
        assert get_zone_display_name(path, level_id) == "Glacial Abyss - Grimwind Woods"

    def test_tartarus_in_riot(self):
        path = "/Game/Art/Season/S16/Maps/ZhongZuiDiYu/ZhongZuiDiYu"
        assert get_zone_display_name(path, 235501) == "Tartarus in Riot"

    @pytest.mark.parametrize(
        "variant,expected",
        [
            ("00001", "Voidlands - Yesterday Chamber"),
            ("00002", "Voidlands - Road of Purgation"),
            ("00003", "Thunder Wastes - Chamber of Confusion"),
            ("00004", "Thunder Wastes - Place of Repentance"),
            ("00005", "Thunder Wastes - Ascetic Gallery"),
            ("00006", "Voidlands - Corridor of Disorder"),
            ("00007", "Thunder Wastes - Ascension Testing Ground"),
        ],
    )
    def test_ss14_ywmd_zones(self, variant, expected):
        path = _path("05JH", f"JH_YWMD_{variant}")
        assert get_zone_display_name(path, 4600) == expected

    def test_unknown_zone_falls_back_to_cleaned_path(self):
        path = _path("05JH", "JH_SomethingNew00009")
        assert get_zone_display_name(path) == "JH_SomethingNew"
