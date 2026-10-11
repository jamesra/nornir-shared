"""Characterization tests for ``files._scan_one_directory``, the per-directory unit of
``RecurseSubdirectoriesGenerator``.

The property test builds a real directory from generated file and subdirectory names and
filter criteria, then compares the scan against a short reference written straight from
the documented rules:

* any file matching ``ExcludedFiles`` vetoes the directory and its whole subtree;
* the directory is reported with the files matching ``RequiredFiles``, or with an empty
  list when neither ``RequiredFiles`` nor ``MatchNames`` is set;
* subdirectories with a ``.`` in their own name, or named in ``ExcludeNames_set``, are
  skipped; ones matching ``MatchNames`` are reported and not descended; the rest are
  children to visit.

Criteria are normalised the way ``_RecurseSubdirectoriesGeneratorTask`` normalises them.
"""
from __future__ import annotations

import os
import re
import tempfile
import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from nornir_shared import files

_FILE_NAMES = ['a.idoc', 'B.idoc', 'c.png', 'D.PNG', 'e.txt', 'stos.mosaic']
_DIR_NAMES = ['abc', 'ABD', 'tem', 'TEMP', 'x.y', 'leaf', '001', '002']

# Raw criteria as callers pass them: None, a '*' glob string, or a list of names.
_FILE_CRITERIA = st.one_of(
    st.none(),
    st.sampled_from(['*.idoc', '*.PNG', '*.mosaic', 'zzz']),
    st.lists(st.sampled_from(_FILE_NAMES + ['missing.txt']), max_size=3),
)
_DIR_CRITERIA = st.one_of(
    st.none(),
    st.sampled_from(['ab.*', 'LEAF']),
    st.lists(st.sampled_from(_DIR_NAMES + ['missing']), max_size=3),
)
_EXCLUDE_NAMES = st.one_of(st.none(), st.lists(st.sampled_from(_DIR_NAMES), max_size=3))

# Runners such as mutmut call one test method from several TestCase instances in a single
# process; each example builds its own temp directory, so that is safe here.
_SETTINGS = settings(max_examples=150, deadline=None,
                     suppress_health_check=[HealthCheck.differing_executors])


def _hit(name: str, criteria, caseInsensitive: bool = True) -> bool:
    """True when *name* matches normalised *criteria* (a pattern, a set, or None)."""
    if criteria is None:
        return False
    key = name.lower() if caseInsensitive else name
    if isinstance(criteria, re.Pattern):
        return criteria.match(key) is not None
    return key in criteria


def _reference_scan(path, required, excluded, match, exclude_names, caseInsensitive):
    """Expected ``(results, children)`` for *path*, as plain tuples and paths."""
    with os.scandir(path) as it:
        entries = list(it)
    file_names = [e.name for e in entries if e.is_file()]
    dirs = [e for e in entries if not e.is_file() and e.is_dir()]

    if any(_hit(n, excluded) for n in file_names):
        return [], []

    results = []
    required_hits = [n for n in file_names if _hit(n, required)]
    if required_hits:
        results.append((path, required_hits))
    elif not required and not match:
        results.append((path, []))

    children = []
    for d in dirs:
        if '.' in d.name:
            continue
        if exclude_names is not None and (d.name.lower() if caseInsensitive else d.name) in exclude_names:
            continue
        if _hit(d.name, match, caseInsensitive):
            results.append((d.path, []))
            continue
        children.append(d.path)
    return results, children


def _make_entries(root: str, file_names: list[str], dir_names: list[str]) -> None:
    """Create the named empty files and subdirectories under *root*."""
    for name in dir_names:
        os.makedirs(os.path.join(root, name))
    for name in file_names:
        with open(os.path.join(root, name), 'w'):
            pass


class ScanOneDirectoryTests(unittest.TestCase):
    """``_scan_one_directory`` applies the file and directory rules to one listing."""

    def _scan(self, root, required=None, excluded=None, match=None, exclude_names=None,
              caseInsensitive=True):
        """Normalise raw criteria like the generator does, then scan *root*."""
        scan = files._scan_one_directory(
            root,
            files.ensure_regex_or_set(required, caseInsensitive=caseInsensitive),
            files.ensure_regex_or_set(excluded, caseInsensitive=caseInsensitive),
            files.ensure_regex_or_set(match, caseInsensitive=caseInsensitive),
            files.ensure_string_set(exclude_names, caseInsensitive=caseInsensitive),
            caseInsensitive)
        return [(r.path, r.matched_files) for r in scan.results], scan.children

    @_SETTINGS
    @given(file_names=st.lists(st.sampled_from(_FILE_NAMES), unique=True),
           dir_names=st.lists(st.sampled_from(_DIR_NAMES), unique=True),
           required=_FILE_CRITERIA, excluded=_FILE_CRITERIA,
           match=_DIR_CRITERIA, exclude_names=_EXCLUDE_NAMES,
           caseInsensitive=st.booleans())
    def test_property_matches_reference(self, file_names, dir_names, required, excluded,
                                        match, exclude_names, caseInsensitive) -> None:
        """Results and children agree with the reference on generated listings."""
        with tempfile.TemporaryDirectory() as root:
            _make_entries(root, file_names, dir_names)
            ci = caseInsensitive
            expected = _reference_scan(
                root,
                files.ensure_regex_or_set(required, caseInsensitive=ci),
                files.ensure_regex_or_set(excluded, caseInsensitive=ci),
                files.ensure_regex_or_set(match, caseInsensitive=ci),
                files.ensure_string_set(exclude_names, caseInsensitive=ci),
                ci)
            self.assertEqual(self._scan(root, required, excluded, match, exclude_names, ci),
                             expected)

    def test_an_excluded_file_prunes_the_directory_and_subtree(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            _make_entries(root, ['a.idoc', 'stos.mosaic'], ['leaf'])
            self.assertEqual(self._scan(root, required='*.idoc', excluded='*.mosaic'), ([], []))

    def test_required_files_are_reported_in_listing_order_with_original_case(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            _make_entries(root, ['a.idoc', 'B.idoc', 'c.png'], [])
            self.assertEqual(self._scan(root, required='*.idoc'), ([(root, ['a.idoc', 'B.idoc'])], []))

    def test_no_criteria_reports_the_directory_with_no_files(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            _make_entries(root, ['a.idoc'], ['leaf'])
            self.assertEqual(self._scan(root), ([(root, [])], [os.path.join(root, 'leaf')]))

    def test_unmatched_required_files_report_nothing_but_still_descend(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            _make_entries(root, ['c.png'], ['leaf'])
            self.assertEqual(self._scan(root, required='*.idoc'), ([], [os.path.join(root, 'leaf')]))

    def test_dotted_excluded_and_matched_subdirectories(self) -> None:
        """Dotted and excluded names are skipped; MatchNames are reported, not descended."""
        with tempfile.TemporaryDirectory() as root:
            _make_entries(root, [], ['x.y', 'tem', 'abc', 'leaf'])
            results, children = self._scan(root, match=['ABC'], exclude_names=['TEM'])
            self.assertEqual(results, [(os.path.join(root, 'abc'), [])])
            self.assertEqual(children, [os.path.join(root, 'leaf')])

    def test_a_missing_directory_scans_empty(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(self._scan(os.path.join(root, 'absent')), ([], []))


class MatchRequiredFilesTests(unittest.TestCase):
    """``_match_required_files`` decides a directory's file criteria from names alone."""

    @staticmethod
    def _match(names, required=None, excluded=None):
        return files._match_required_files(names,
                                           files.ensure_regex_or_set(required, caseInsensitive=True),
                                           files.ensure_regex_or_set(excluded, caseInsensitive=True))

    def test_examples(self) -> None:
        names = ['a.idoc', 'B.IDOC', 'c.png']
        self.assertEqual(self._match(names, required='*.idoc'), ['a.idoc', 'B.IDOC'])
        self.assertEqual(self._match(names, required=['C.PNG']), ['c.png'])
        self.assertIsNone(self._match(names, required='*.idoc', excluded=['c.png']))
        self.assertIsNone(self._match(names, excluded='*.PNG'))
        self.assertEqual(self._match(names, excluded=['missing']), [])
        self.assertEqual(self._match(names), [])
        self.assertEqual(self._match(names, required=[], excluded=[]), [])

    def test_no_criteria_does_not_read_the_listing(self) -> None:
        def listing():
            raise AssertionError('listing consumed with no criteria')
            yield  # pragma: no cover

        self.assertEqual(files._match_required_files(listing(), None, frozenset()), [])

    @_SETTINGS
    @given(names=st.lists(st.sampled_from(_FILE_NAMES), unique=True),
           required=_FILE_CRITERIA, excluded=_FILE_CRITERIA)
    def test_property_exclusion_vetoes_otherwise_filters(self, names, required, excluded) -> None:
        req = files.ensure_regex_or_set(required, caseInsensitive=True)
        exc = files.ensure_regex_or_set(excluded, caseInsensitive=True)
        result = files._match_required_files(names, req, exc)
        if any(_hit(n, exc) for n in names):
            self.assertIsNone(result)
        else:
            self.assertEqual(result, [n for n in names if _hit(n, req)])


if __name__ == '__main__':
    unittest.main()
