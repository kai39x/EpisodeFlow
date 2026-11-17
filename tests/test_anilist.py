"""Seasons and parts from AniList, with a fake AniList (nothing goes online)."""
import episodeflow as ef


def media(mid, romaji, episodes, year, month, prequel=None, sequel=None, english=None):
    edges = []
    for rel, other in (("PREQUEL", prequel), ("SEQUEL", sequel)):
        if other:
            edges.append({"relationType": rel, "node": {"id": other[0], "type": "ANIME", "format": "TV",
                                                        "startDate": {"year": other[1], "month": other[2]}}})
    return {"id": mid, "format": "TV", "episodes": episodes, "synonyms": [],
            "title": {"romaji": romaji, "english": english}, "startDate": {"year": year, "month": month},
            "nextAiringEpisode": None, "coverImage": {"extraLarge": f"https://example.invalid/{mid}.jpg"},
            "relations": {"edges": edges}}


REZERO = {
    1: media(1, "Re:Zero kara Hajimeru Isekai Seikatsu", 25, 2016, 4, sequel=(2, 2020, 7)),
    2: media(2, "Re:Zero kara Hajimeru Isekai Seikatsu 2nd Season", 13, 2020, 7,
             prequel=(1, 2016, 4), sequel=(3, 2021, 1)),
    3: media(3, "Re:Zero kara Hajimeru Isekai Seikatsu 2nd Season Part 2", 12, 2021, 1, prequel=(2, 2020, 7)),
}


def fake_anilist(calls):
    def post(query, variables):
        calls.append(variables)
        if "Page" in query:
            return {"Page": {"media": [REZERO[2]]}}      # search finds the 2nd season first
        return {"Media": REZERO[variables["id"]]}
    return post


def test_chain_is_walked_back_to_season_one_and_labelled():
    calls = []
    chain = ef.fetch_chain("Re Zero", fake_anilist(calls))
    assert [m["id"] for m in chain] == [1, 2, 3]
    labels = ef.label_chain(chain)
    assert [(e["season"], e["part"], e["episodes"]) for e in labels] == [(1, 1, 25), (2, 1, 13), (2, 2, 12)]


def test_part_two_continues_the_count():
    files = ["Re Zero S2 Part 2 - 01.mkv", "Re Zero S2 Part 2 - 02.mkv"]
    lookup = ef.AniListLookup("Re Zero", files, post=fake_anilist([]), use_cache=False)
    results = ef.resolve_batch(files, None, lookup)
    assert [(r.season, r.episode) for r in results] == [(2, 14), (2, 15)]
    assert lookup.season_parts(2) == [13, 12]
    assert lookup.cover() == "https://example.invalid/1.jpg"


def test_offline_falls_back_to_the_folder():
    def offline(query, variables):
        raise OSError("no internet")
    files = ["Re Zero S2 Part 2 - 01.mkv"]
    lookup = ef.AniListLookup("Re Zero", files, post=offline, use_cache=False)
    results = ef.resolve_batch(files, None, lookup)
    assert lookup.status_key == "offline"
    assert results[0].episode == 1 and results[0].confidence == "medium"
