# Changelog

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
