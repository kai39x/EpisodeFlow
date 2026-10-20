"""
Episode detection on real, messy file names (60 files from 10 shows).
Run:  python tests/test_detection.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from episodeflow import resolve_batch  # noqa: E402

B = {
"Grand Blue S3": [
("[Ember] Grand Blue Season 3 - 10 [4K].mkv","S03E10"),
("[Ember] Grand Blue Season 3 - 11 [4K].mkv","S03E11"),
("[Erai-raws] Grand Blue Season 3 - 12 [1080p CR WEBRip HEVC AAC][MultiSub][4DAE75B6] (1).mkv","S03E12"),
("Grand Blue S3 - Episode 09 [4K].mkv","S03E09"),
("[Ember] Grand.Blue.Season.3.Ep.08.4K.mkv","S03E08"),
("GB S03E07 [4K].mkv","S03E07")],
"JJK": [
("[iExplosiveRage] Jujutsu Kaisen! The Culling Game Part 1 - 09.mp4","S02E09"),
("[iExplosiveRage] Jujutsu Kaisen! The Culling Game Part 1 - 10.mp4","S02E10"),
("Jujutsu Kaisen! The Culling Game Part 1 - 11 .mp4","S02E11"),
("Jujutsu Kaisen! The Culling Game Part 1 - 12.mp4","S02E12"),
("JJK Culling Game Part1 - 08 [1080p].mp4","S02E08"),
("[iExplosiveRage] Jujutsu.Kaisen.S02E07.The.Culling.Game.mkv","S02E07"),
("jjk s2 ep06 final.mp4","S02E06")],
"Dr Stone": [
("Dr.STONE.S04E24 [4K].mkv","S04E24"),
("[iHx] Dr.STONE S04E25 - 4K.mkv","S04E25"),
("Dr Stone Season 4 Episode 23 4K.mkv","S04E23"),
("[SomeGroup] Dr.STONE - 4x22 [4K].mkv","S04E22"),
("DrSTONE_S4_E21_4K.mkv","S04E21")],
"Frieren": [
("[SAB11] Sousou no Frieren 4K FLAC E22.mkv","S01E22"),
("[Sqero] Sousou no Frieren 2nd Season - 01 [4K].mp4","S02E01"),
("Sousou no Frieren S2 - 02 [4K].mkv","S02E02"),
("[Frieren] Sousou.no.Frieren.S02E03.4K.mkv","S02E03"),
("Frieren 2nd Season Episode 04.mkv","S02E04"),
("[SAB11] Frieren - S2E05 [FLAC][4K].mkv","S02E05")],
"Yuusha": [
("Yuusha-kei ni Shosu Choubatsu 12 END [4K].mkv","S01E12"),
("Yuusha-kei ni Shosu Choubatsu Yuusha 9004-tai Keimu Kiroku - 05 [4K] .mkv","S01E05"),
("Yuusha-kei ni Shosu - 11 [4K].mkv","S01E11"),
("[Group] Yuusha kei ni Shosu Choubatsu - Episode 10.mkv","S01E10"),
("YKN S1E09 4K.mkv","S01E09")],
"Dandadan": [
("[iExplosiveRage] Dandadan - 16 [4K].mp4","S01E16"),
("[Sunless] Dandadan - 11 4K.mp4","S01E11"),
("Dandadan Episode 15 [4K].mp4","S01E15"),
("[iExplosiveRage] DanDaDan S01E14.mkv","S01E14"),
("dandadan - 13 final version.mp4","S01E13"),
("[Sunless] Dandadan.Ep.12.4K.mp4","S01E12")],
"Yofukashi": [
("[E M B E R] Yofukashi no Uta S2 - 04-[4K] .mkv","S02E04"),
("[EMBER] Yofukashi no Uta S2 - 05- [4K] .mkv","S02E05"),
("Yofukashi no Uta S2 - 11 [4K].mkv","S02E11"),
("[EMBER] Call of the Night S2E03 [4K].mkv","S02E03"),
("Yofukashi.no.Uta.Season.2.Episode.02.mkv","S02E02"),
("[E M B E R] Yofukashi no Uta - S2 - 01 [4K].mkv","S02E01")],
"Link Click": [
("[Sylor] Link Click - 11 - 4K.mp4","S01E11"),
("[Sylor] Link Click S01E01 4K.mp4","S01E01"),
("[Sylor] Shiguang Dailiren II - 01-4K.mp4","S02E01"),
("[Sylor] Shiguang Dailiren II - 02-4K.mp4","S02E02"),
("Link Click Season 1 Episode 10.mp4","S01E10"),
("[Sylor] Link.Click.S01E09.4K.mp4","S01E09"),
("Shiguang Dailiren II Episode 03 [4K].mp4","S02E03")],
"Vinland": [
("[Sunless] Vinland Saga - S01E02-4K .mkv","S01E02"),
("[Sunless] Vinland Saga - S01E06-4K .mkv","S01E06"),
("[Sqero] Vinland Saga S2 - 05 [4K].mp4","S02E05"),
("[Sqero] Vinland Saga S2 - 11 [4K].mp4","S02E11"),
("Vinland Saga Season 2 Episode 04.mkv","S02E04"),
("[Sunless] Vinland.Saga.S02E03.4K.mkv","S02E03"),
("Vinland Saga S1 - 05 [4K].mkv","S01E05")],
"Grand Blue S1": [
("[Sunless]Grand_Blue_S01E04[4K].mp4","S01E04"),
("[Sunless]Grand_Blue_S01E10[4K].mp4","S01E10"),
("Grand Blue S1E08 4K.mp4","S01E08"),
("[Sunless] Grand Blue - Season 1 - Episode 07.mkv","S01E07"),
("GB_S01_E09_4K.mp4","S01E09")],
}


def main():
    ok = total = 0
    for show, items in B.items():
        results = resolve_batch([name for name, _ in items])
        for (name, expected), r in zip(items, results):
            got = f"S{r.season:02d}E{r.episode:02d}"
            total += 1
            if got == expected:
                ok += 1
            else:
                print(f"FAIL  {show}: {name} -> {got}, expected {expected}")
    print(f"{ok}/{total} detected correctly")
    return ok == total


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
