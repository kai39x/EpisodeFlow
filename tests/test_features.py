"""New in 1.2.0: aired episodes you don't have, and season folders."""
import os

import pytest

import episodeflow as ef


def make(folder, *names):
    os.makedirs(folder, exist_ok=True)
    for n in names:
        with open(os.path.join(folder, n), "w", encoding="utf-8") as fh:
            fh.write(n)


def tree(folder):
    out = []
    for root, _, files in os.walk(folder):
        out += [os.path.relpath(os.path.join(root, f), folder).replace(os.sep, "/") for f in files]
    return sorted(out)


def label(season, part, episodes, status="FINISHED", nxt=None, at=None):
    return {"title": "Show", "episodes": episodes, "season": season, "part": part, "status": status,
            "aired": nxt - 1 if nxt else None, "next": nxt, "next_at": at, "cover": None, "keys": []}


def lookup_with(labels):
    lk = ef.AniListLookup("Show", [], use_cache=False)
    lk.labels, lk._done, lk.status_key = labels, True, "matched"
    return lk


def plan_for(tmp_path, labels, names):
    folder = tmp_path / "Show"
    make(folder, *names)
    plan = ef.analyze(str(folder), online=False)
    plan.lookup = lookup_with(labels)
    return plan


# ---------- aired episodes you don't have ----------
def test_airing_season_counts_only_what_is_out(tmp_path):
    plan = plan_for(tmp_path, [label(1, 1, 12, "RELEASING", nxt=8, at=1_800_000_000)],
                    ["Show - 01.mkv", "Show - 03.mkv", "Show - 05.mkv"])
    s = ef.missing_episodes(plan)[0]
    assert (s["total"], s["aired"], s["airing"]) == (12, 7, True)
    assert s["missing"] == [2, 4, 6, 7]          # 8 to 12 aren't out yet, so they aren't "missing"
    assert s["new"] == [6, 7]                    # out, after the last one you have
    assert s["next"] == {"episode": 8, "at": 1_800_000_000}


def test_second_part_airing_counts_from_the_first(tmp_path):
    labels = [label(1, 1, 13), label(1, 2, 12, "RELEASING", nxt=3, at=1_800_000_000)]
    plan = plan_for(tmp_path, labels, [f"Show - {n:02d}.mkv" for n in range(1, 14)])
    s = ef.missing_episodes(plan)[0]
    assert (s["total"], s["aired"]) == (25, 15)
    assert s["new"] == [14, 15]
    assert s["next"]["episode"] == 16


def test_finished_season_has_no_new_or_next(tmp_path):
    plan = plan_for(tmp_path, [label(1, 1, 12)], ["Show - 01.mkv", "Show - 12.mkv"])
    s = ef.missing_episodes(plan)[0]
    assert s["missing"] == list(range(2, 12)) and s["new"] == [] and s["next"] is None and not s["airing"]


def test_announced_part_is_not_missing(tmp_path):
    labels = [label(1, 1, 12), label(1, 2, 12, "NOT_YET_RELEASED")]
    plan = plan_for(tmp_path, labels, [f"Show - {n:02d}.mkv" for n in range(1, 13)])
    s = ef.missing_episodes(plan)[0]
    assert (s["total"], s["aired"], s["missing"], s["new"]) == (24, 12, [], [])


# ---------- season folders ----------
@pytest.fixture
def organize(monkeypatch):
    monkeypatch.setattr(ef, "ORGANIZE", True)


def test_season_folders_and_undo(tmp_path, organize):
    folder = str(tmp_path / "Frieren")
    make(folder, "Frieren - 01.mkv", "Frieren - 01.ar.srt", "Frieren S02E10.mkv", "Frieren OVA.mkv")
    plan = ef.analyze(folder, online=False)
    assert ef.apply_plan(plan) == 4
    assert tree(folder) == ["Season 01/Frieren - S01E01.ar.srt", "Season 01/Frieren - S01E01.mkv",
                            "Season 02/Frieren - S02E10.mkv", "Specials/Frieren - S00E01.mkv"]
    # opened again, each season folder is already done
    shows = ef.find_show_folders(folder)
    assert [os.path.basename(f) for f in shows] == ["Season 01", "Season 02", "Specials"]
    assert all(ef.plan_status(ef.analyze(f, online=False)) == "done" for f in shows)
    # undo puts everything back and removes the folders it made
    assert ef.undo(folder) == 4
    assert tree(folder) == ["Frieren - 01.ar.srt", "Frieren - 01.mkv", "Frieren OVA.mkv", "Frieren S02E10.mkv"]
    assert sorted(os.listdir(folder)) == tree(folder)


def test_no_extra_folder_inside_a_season_folder(tmp_path, organize):
    folder = str(tmp_path / "Frieren" / "Season 2")
    make(folder, "Frieren - 01.mkv")
    plan = ef.analyze(folder, online=False)
    assert ef.plan_pairs(plan) == [("Frieren - 01.mkv", "Frieren - S02E01.mkv")]


def test_failed_move_removes_the_folders_it_made(tmp_path, organize, monkeypatch):
    folder = str(tmp_path / "Frieren")
    make(folder, "Frieren - 01.mkv", "Frieren - 02.mkv")
    plan = ef.analyze(folder, online=False)
    real_rename = os.rename

    def rename(src, dst):
        if os.path.basename(src) == "Frieren - 02.mkv":
            raise PermissionError(32, "in use")
        real_rename(src, dst)

    monkeypatch.setattr(ef.os, "rename", rename)
    with pytest.raises(ef.EFError):
        ef.apply_plan(plan)
    assert sorted(os.listdir(folder)) == ["Frieren - 01.mkv", "Frieren - 02.mkv"]


def test_season_folder_setting_is_saved(monkeypatch):
    monkeypatch.setattr(ef, "ORGANIZE", False)
    ef.set_organize(True)
    assert ef.ORGANIZE and ef.load_settings()["folders"] == "season"
    ef.set_organize(False)
    assert not ef.ORGANIZE and ef.load_settings()["folders"] == "none"
