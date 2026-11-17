"""File name formats, missing-episode ranges and the folder-icon desktop.ini."""
import pytest

import episodeflow as ef
import episodeflow_gui as gui


@pytest.mark.parametrize("tpl, error", [
    ("{show} - S{season}E{episode}", ""),
    ("{show} - {s}x{e}", ""),
    ("", "err_tpl_empty"),
    ("{show} - S{season}", "err_tpl_episode"),
    ("{show}: {episode}", "err_tpl_chars"),
    ("{show} {name} {episode}", "err_tpl_chars"),
    ("x" * 120 + "{episode}", "err_tpl_long"),
])
def test_validate_template(tpl, error):
    assert ef.validate_template(tpl) == error


def test_render_template():
    assert ef.render_template("{show} - S{season}E{episode}", "Re:Zero", 2, 15) == "Re Zero - S02E15"
    assert ef.render_template("{show} - {s}x{e}", "Frieren", 1, 5) == "Frieren - 1x5"


def test_ranges():
    assert ef.ranges([1, 2, 3, 5, 7, 8]) == "E01-03, E05, E07-08"
    assert ef.ranges([]) == ""


def test_folder_icon_keeps_the_rest_of_desktop_ini():
    text = ("[.ShellClassInfo]\r\nLocalizedResourceName=My Anime\r\n"
            "IconResource=EpisodeFlow-1.ico,0\r\nIconFile=EpisodeFlow-1.ico\r\nIconIndex=0\r\n"
            "EpisodeFlowReadOnly=kept\r\n[ViewState]\r\nMode=\r\nFolderType=Videos\r\n")
    lines, marker = gui._split_ini(text)
    assert marker == "kept"
    assert not any(line.startswith(("IconResource", "IconFile", "IconIndex", "EpisodeFlow")) for line in lines)
    assert "LocalizedResourceName=My Anime" in lines and "FolderType=Videos" in lines
    assert not gui._ini_is_empty(lines)
    rebuilt = gui._join_ini(lines, ["IconResource=EpisodeFlow-2.ico,0"])
    assert rebuilt.startswith("[.ShellClassInfo]\r\nIconResource=EpisodeFlow-2.ico,0\r\nLocalizedResourceName")
    assert "[ViewState]" in rebuilt


def test_desktop_ini_with_only_our_icon_is_empty_after_removal():
    lines, marker = gui._split_ini("[.ShellClassInfo]\r\nIconResource=EpisodeFlow-1.ico,0\r\nIconIndex=0\r\n")
    assert marker is None          # made by 1.1.0 or older
    assert gui._ini_is_empty(lines)
