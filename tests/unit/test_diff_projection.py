"""Unit tests for diff hunk projection — PatchSet → line ranges, overlap detection."""

from __future__ import annotations

import pytest

from rca.indexing.differential_indexer import (
    STATUS_ADDED,
    STATUS_DELETED,
    STATUS_MODIFIED,
    STATUS_UNCHANGED,
    _is_file_added,
    _is_file_deleted,
    _overlaps,
    _parse_hunks,
)

# ---------------------------------------------------------------------------
# Fixture diffs
# ---------------------------------------------------------------------------

MODIFY_DIFF = """\
--- a/src/HttpClient.cs
+++ b/src/HttpClient.cs
@@ -10,5 +10,5 @@
 public class HttpClient
 {
-    private readonly int _timeout = 30;
+    private readonly int _timeout = 15;
     public async Task SendAsync() {}
 }
"""

ADD_FILE_DIFF = """\
--- /dev/null
+++ b/src/NewService.cs
@@ -0,0 +1,4 @@
+public class NewService
+{
+    public void Run() {}
+}
"""

DELETE_FILE_DIFF = """\
--- a/src/LegacyAuth.cs
+++ /dev/null
@@ -1,4 +0,0 @@
-public class LegacyAuth
-{
-    public void Authenticate() {}
-}
"""

EMPTY_DIFF = ""


class TestParseHunks:
    def test_modify_diff_returns_correct_range(self):
        ranges = _parse_hunks(MODIFY_DIFF)
        assert len(ranges) == 1
        start, end = ranges[0]
        assert start == 10
        assert end >= 10

    def test_empty_diff_returns_no_ranges(self):
        assert _parse_hunks(EMPTY_DIFF) == []

    def test_add_file_diff_parses_without_error(self):
        ranges = _parse_hunks(ADD_FILE_DIFF)
        # Added file hunks: source_start=0
        assert isinstance(ranges, list)

    def test_malformed_diff_returns_empty(self):
        assert _parse_hunks("not a valid diff at all") == []


class TestOverlaps:
    def test_node_inside_hunk(self):
        assert _overlaps(11, 12, [(10, 16)]) is True

    def test_node_contains_hunk(self):
        assert _overlaps(8, 20, [(10, 16)]) is True

    def test_node_before_hunk(self):
        assert _overlaps(1, 5, [(10, 16)]) is False

    def test_node_after_hunk(self):
        assert _overlaps(20, 30, [(10, 16)]) is False

    def test_node_touching_hunk_edge(self):
        # boundary inclusive: node ends exactly where hunk starts
        assert _overlaps(8, 10, [(10, 16)]) is True

    def test_multiple_hunks_one_matches(self):
        hunks = [(1, 5), (20, 30), (50, 60)]
        assert _overlaps(25, 27, hunks) is True

    def test_multiple_hunks_none_match(self):
        hunks = [(1, 5), (20, 30)]
        assert _overlaps(10, 15, hunks) is False

    def test_empty_hunk_list(self):
        assert _overlaps(10, 20, []) is False


class TestFileFlags:
    def test_delete_flag_true_for_deletion(self):
        assert _is_file_deleted(DELETE_FILE_DIFF) is True

    def test_delete_flag_false_for_modify(self):
        assert _is_file_deleted(MODIFY_DIFF) is False

    def test_add_flag_true_for_new_file(self):
        assert _is_file_added(ADD_FILE_DIFF) is True

    def test_add_flag_false_for_modify(self):
        assert _is_file_added(MODIFY_DIFF) is False
