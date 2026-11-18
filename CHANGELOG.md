# Changelog

## 1.1.2

Fixes:
- **Season folders.** In `Frieren/Season 1`, `Frieren/Season 2`, files were renamed to `Show - S01E01` because the season folder had no show name in it. The show's name now comes from the folder above, and `Specials` / `Extras` / `Season 0` folders go to Season 0. They're also found when you open the folder above the show. In the list they show as `Frieren · Season 2`.
- **Names that only change upper/lower case** (`frieren` folder, `Frieren - S01E01.mkv`) stopped with "A file with this name already exists". Renaming and undo now work.
- **Version tags stuck to the number** (`S01E05v2`, `E05v2`, `05v2`) weren't read at all. Now they are.
- **Double episodes** (`S01E05-E06`, `S01E05E06`) were either not read or renamed to `S01E05` only. They're now named `S01E05-E06` and both count as present.
- **Copies and quality marks.** `Frieren - 05 (1).mkv` (a Windows copy) was renamed next to the original as `S01E05 (1)` instead of being shown as a duplicate, and `[Group] Show - 01 (1080p).mkv` kept ` (1080p)` in its new name. Only copies you kept on purpose keep their mark now.
- **Subtitles** like `Ep.v2.srt` could be matched to both `Ep.mkv` and `Ep.v2.mkv`. Each subtitle now goes with one video only.
- **Undo from the "Renamed" message** undid the show you were looking at, not the one you'd just renamed, if you switched shows within those seconds.
- Opening another folder while one was still being read could mark the new one as finished too early.
- When AniList can't be reached, an older saved answer is used instead of counting from the folder. Saved answers older than 60 days are cleared.
- Japanese / Chinese episode numbers like `第05話` are read.

## 1.1.1

Safety fixes:
- **Renaming is all or nothing.** Before, if a file couldn't be renamed partway through (for example an episode open in a video player), the files before it were left with temporary names like `__epf_tmp_0__.mkv`, and the history didn't record it, so there was nothing to undo. Now every file gets its old name back and EpisodeFlow says which file was in use.
- **No permanent deletes by surprise.** USB sticks, SD cards and network drives have no Recycle Bin, so Windows would have deleted a duplicate for good. EpisodeFlow now refuses and deletes nothing there. On other drives, if Windows still can't recycle a file, it asks before deleting it for good.
- **"Remove from this PC" only removes EpisodeFlow's own files**, by name, and the data folder only when it's empty. Before, it deleted a whole folder.
- **Folder icons keep the rest of `desktop.ini`** (a folder's display name, view settings...). Removing an icon only makes the folder read-only again if EpisodeFlow made it so.
- In **Rename all ready shows**, a show that couldn't be renamed is now named in the message instead of being skipped silently.

Behind the scenes:
- Importing the engine no longer creates folders or moves files. That only happens when the program starts.
- Tests now use pytest and cover AniList seasons and parts (with a fake AniList), renaming, undo, duplicates and the file name formats, as well as episode detection.
- GitHub Actions runs the tests on every push. On a version tag it builds `EpisodeFlow.exe` and attaches it to the release with its SHA256.
- `build.bat` installs pinned build tools (`requirements-build.txt`) into its own `.venv`, and checks for Python 3.10 or newer.

## 1.1.0

- Themes: Match Windows, Light, Dark, OLED (true black) and Aurora.
- Glass buttons and panels, with five accent colours (can be turned off).
- Your theme and language are remembered between runs.

## 1.0.0

First release:
- Renames anime episodes from any naming style to clean names (`Show - S01E05`).
- Seasons and Part 2 / Cour 2 counted correctly with AniList.
- Missing episodes, specials (Season 0), and subtitles renamed with their episode.
- Anime posters as folder icons.
- Duplicate episodes, full history with undo, storage view.
- Drag and drop, Send To menu, English and Arabic.
