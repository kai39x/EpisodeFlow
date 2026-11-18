"""Folder layouts and names that used to go wrong (fixed in 1.1.2)."""
import os

import pytest

import episodeflow as ef


def make(folder, *names):
    os.makedirs(folder, exist_ok=True)
    for n in names:
        with open(os.path.join(folder, n), "w", encoding="utf-8") as fh:
            fh.write(n)


def pairs(folder):
    return ef.plan_pairs(ef.analyze(folder, online=False))


@pytest.fixture
def frieren(tmp_path):
    root = tmp_path / "Anime" / "Sousou no Frieren"
    make(root / "Season 1", "Frieren - 01.mkv")
    make(root / "Season 2", "Frieren - 01.mkv")
    make(root / "Specials", "Frieren - 01.mkv")
    return str(root)


def test_season_folders_take_the_show_name_from_above(frieren):
    folders = ef.find_show_folders(frieren)
    assert [os.path.basename(f) for f in folders] == ["Season 1", "Season 2", "Specials"]
    assert [pairs(f)[0][1] for f in folders] == ["Sousou no Frieren - S01E01.mkv",
                                                 "Sousou no Frieren - S02E01.mkv",
                                                 "Sousou no Frieren - S00E01.mkv"]


def test_season_folders_are_found_from_the_folder_above(frieren):
    folders = ef.find_show_folders(os.path.dirname(frieren))
    assert [os.path.basename(f) for f in folders] == ["Season 1", "Season 2", "Specials"]


def test_show_folder_with_a_specials_folder_inside(tmp_path):
    show = tmp_path / "Dandadan"
    make(show, "Dandadan - 01.mkv")
    make(show / "Specials", "Dandadan - OVA.mkv")
    assert [os.path.basename(f) for f in ef.find_show_folders(str(show))] == ["Dandadan", "Specials"]


@pytest.mark.skipif(os.name != "nt", reason="only Windows ignores upper/lower case in file names")
def test_changing_only_upper_and_lower_case(tmp_path):
    folder = tmp_path / "frieren"
    make(folder, "Frieren - S01E01.mkv", "Frieren - S01E01.srt")
    plan = ef.analyze(str(folder), online=False)
    assert ef.apply_plan(plan) == 2
    assert sorted(os.listdir(folder)) == ["frieren - S01E01.mkv", "frieren - S01E01.srt"]
    assert ef.undo(str(folder)) == 2
    assert sorted(os.listdir(folder)) == ["Frieren - S01E01.mkv", "Frieren - S01E01.srt"]


def test_quality_or_copy_marker_from_a_download_is_not_kept(tmp_path):
    folder = tmp_path / "Frieren"
    make(folder, "Frieren - 05.mkv", "Frieren - 05 (1).mkv", "[SubsPlease] Frieren - 06 (1080p).mkv",
         "Frieren - S01E07.mkv", "Frieren - S01E07 (720p).mkv")
    plan = ef.analyze(str(folder), online=False)
    targets = {r.original: ef.target_name(plan, r) for r in plan.ordered}
    assert targets["[SubsPlease] Frieren - 06 (1080p).mkv"] == "Frieren - S01E06.mkv"
    # a Windows "(1)" copy is a duplicate of episode 5, not a second file to rename
    assert [g["episode"] for g in ef.duplicate_groups(plan)] == [5]
    # a copy kept on purpose earlier keeps its marker
    assert targets["Frieren - S01E07 (720p).mkv"] == "Frieren - S01E07 (720p).mkv"


@pytest.mark.parametrize("name, season, episode, end", [
    ("Show S01E05v2.mkv", 1, 5, None),
    ("Show E05v2.mkv", None, 5, None),
    ("Show 05v2.mkv", None, 5, None),
    ("Show S01E05-E06.mkv", 1, 5, 6),
    ("Show S01E05E06.mkv", 1, 5, 6),
    ("Show S01E05-06.mkv", 1, 5, 6),
    ("Show S01E05-E12.mkv", 1, 5, None),        # too far apart to be one file: just episode 5
    ("[Group] 葬送のフリーレン 第05話.mkv", None, 5, None),
])
def test_more_name_styles(name, season, episode, end):
    r = ef.detect(name)
    assert (r.season, r.episode, r.episode_end) == (season, episode, end)


def test_double_episode_file(tmp_path):
    folder = tmp_path / "Dbl"
    make(folder, "Dbl S01E01-E02.mkv", "Dbl S01E03.mkv", "Dbl S01E05.mkv")
    plan = ef.analyze(str(folder), online=False)
    assert ("Dbl S01E01-E02.mkv", "Dbl - S01E01-E02.mkv") in ef.plan_pairs(plan)
    assert ef.missing_episodes(plan)[0]["missing"] == [4]
    assert ef.render_template("{show} - {s}x{e}", "Dbl", 1, 1, 2) == "Dbl - 1x1-2"


def test_subtitle_goes_with_the_longest_matching_video(tmp_path):
    folder = tmp_path / "Show"
    make(folder, "Show - 01.mkv", "Show - 01.v2.mkv", "Show - 01.v2.srt")
    plan = ef.analyze(str(folder), online=False)
    subs = {r.original: [s for s, _ in ef.matching_subs(str(folder), r.original, plan.all_files)] for r in plan.ordered}
    assert subs == {"Show - 01.mkv": [], "Show - 01.v2.mkv": ["Show - 01.v2.srt"]}


def test_saved_anilist_answer_is_used_when_offline(monkeypatch, tmp_path):
    labels = [{"title": "Frieren", "episodes": 28, "season": 1, "part": 1, "aired": None, "cover": None, "keys": []}]
    old = {"frieren": {"time": 0, "labels": labels, "v": ef.CACHE_VERSION}}   # far too old to trust online

    def offline(query, variables):
        raise OSError("no internet")

    monkeypatch.setattr(ef, "_load_cache", lambda: old)
    lookup = ef.AniListLookup("Frieren", ["Frieren - 01.mkv"], post=offline)
    assert lookup.season_parts(1) == [28]
    assert lookup.status_key == "saved"
