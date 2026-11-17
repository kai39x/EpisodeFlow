"""Renaming on disk: all or nothing, subtitles, history and undo."""
import os
import subprocess
import sys

import pytest

import episodeflow as ef


def make(folder, *names):
    for n in names:
        with open(os.path.join(folder, n), "w", encoding="utf-8") as fh:
            fh.write(n)


def listing(folder):
    return sorted(os.listdir(folder))


@pytest.fixture
def show(tmp_path):
    folder = tmp_path / "Frieren"
    folder.mkdir()
    return str(folder)


def test_rename_and_undo(show):
    make(show, "[SubsPlease] Frieren - 01 (1080p) [A1B2C3D4].mkv", "[SubsPlease] Frieren - 01 (1080p) [A1B2C3D4].ar.srt",
         "[SubsPlease] Frieren - 02 (1080p) [A1B2C3D4].mkv")
    plan = ef.analyze(show, online=False)
    assert ef.plan_status(plan) == "ready"
    assert ef.apply_plan(plan) == 3
    assert listing(show) == ["Frieren - S01E01.ar.srt", "Frieren - S01E01.mkv", "Frieren - S01E02.mkv"]
    assert ef.can_undo(show)
    assert ef.undo(show) == 3
    assert listing(show) == ["[SubsPlease] Frieren - 01 (1080p) [A1B2C3D4].ar.srt", "[SubsPlease] Frieren - 01 (1080p) [A1B2C3D4].mkv",
                             "[SubsPlease] Frieren - 02 (1080p) [A1B2C3D4].mkv"]


def test_failed_rename_changes_nothing(show, monkeypatch):
    """A file that can't be renamed (open in a player) must not leave others with temporary names."""
    names = ["Frieren - 01.mkv", "Frieren - 02.mkv", "Frieren - 03.mkv"]
    make(show, *names)
    plan = ef.analyze(show, online=False)
    real_rename = os.rename

    def rename(src, dst):
        if os.path.basename(src) == "Frieren - 02.mkv":
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        real_rename(src, dst)

    monkeypatch.setattr(ef.os, "rename", rename)
    history_before = len(ef.load_history())
    with pytest.raises(ef.EFError) as err:
        ef.apply_plan(plan)
    assert err.value.key == "err_rename_failed"
    assert err.value.values["name"] == "Frieren - 02.mkv"
    assert listing(show) == names
    assert len(ef.load_history()) == history_before


def test_failure_in_second_phase_is_rolled_back(show, monkeypatch):
    names = ["Frieren - 01.mkv", "Frieren - 02.mkv"]
    make(show, *names)
    plan = ef.analyze(show, online=False)
    real_rename = os.rename

    def rename(src, dst):
        if os.path.basename(dst) == "Frieren - S01E02.mkv":
            raise PermissionError(5, "Access is denied")
        real_rename(src, dst)

    monkeypatch.setattr(ef.os, "rename", rename)
    with pytest.raises(ef.EFError):
        ef.apply_plan(plan)
    assert listing(show) == names


def test_swapped_names(show):
    """A -> B and B -> A at the same time."""
    make(show, "Frieren - S01E01.mkv", "Frieren - S01E02.mkv")
    plan = ef.analyze(show, online=False)
    ef.edit_result(plan.ordered[0], 1, 2)
    ef.edit_result(plan.ordered[1], 1, 1)
    ef.apply_plan(plan)
    with open(os.path.join(show, "Frieren - S01E02.mkv"), encoding="utf-8") as fh:
        assert fh.read() == "Frieren - S01E01.mkv"


def test_conflicts_and_existing_names_are_refused(show):
    make(show, "Frieren - 01 [720p].mkv", "Frieren - 01 [1080p].mkv")
    plan = ef.analyze(show, online=False)
    assert ef.plan_status(plan) == "conflict"
    with pytest.raises(ef.EFError) as err:
        ef.apply_plan(plan)
    assert err.value.key == "err_conflicts"
    groups = ef.duplicate_groups(plan)
    assert len(groups) == 1
    best = [f for f in groups[0]["files"] if f["best"]]
    assert best[0]["res"] == "1080p"
    ef.keep_both(plan, [f["row"] for f in groups[0]["files"]])
    assert ef.plan_status(plan) == "ready"
    ef.apply_plan(plan)
    assert listing(show) == ["Frieren - S01E01 (720p).mkv", "Frieren - S01E01.mkv"]


def test_existing_file_is_not_overwritten(show):
    make(show, "Frieren - 01.mkv")
    plan = ef.analyze(show, online=False)
    make(show, "Frieren - S01E01.mkv")        # appears after the preview
    with pytest.raises(ef.EFError) as err:
        ef.apply_plan(plan)
    assert err.value.key == "err_exists"
    with open(os.path.join(show, "Frieren - S01E01.mkv"), encoding="utf-8") as fh:
        assert fh.read() == "Frieren - S01E01.mkv"


def test_import_changes_nothing_on_disk(tmp_path):
    """Only starting the program creates the data folder, not importing the engine."""
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path)}
    src = os.path.dirname(ef.__file__)
    subprocess.run([sys.executable, "-c", "import episodeflow"], cwd=src, env=env, check=True)
    assert not os.path.exists(os.path.join(tmp_path, "EpisodeFlow"))


def test_data_folder_is_never_the_program_folder():
    assert os.path.basename(ef.DATA_DIR) == "EpisodeFlow"
    assert os.path.normcase(ef.DATA_DIR) != os.path.normcase(ef.APP_DIR)
