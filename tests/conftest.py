"""
Shared setup for the tests (run them with:  python -m pytest).
Settings, history and the AniList cache go to a throwaway folder, never your real
%LOCALAPPDATA%\\EpisodeFlow, and nothing goes online.
"""
import os
import sys
import tempfile

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="episodeflow-tests-")
sys.path.insert(0, os.path.abspath(SRC))
