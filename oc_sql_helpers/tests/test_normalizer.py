#!/usr/bin/env python3
# most of these tests are etalon-based
# it is more cheap way then write classic 'unit' tests for each case
# exclusions: tests for 'normalization wrappers' - different argument types for 'normalize_path' and so on

import os
import filecmp
import fnmatch
import tempfile
import re

import unittest
import unittest.mock
from oc_sql_helpers import normalizer

import logging
logging.getLogger().propagate = False
logging.getLogger().disabled = True


class PLSQLNormalizerTest(unittest.TestCase):
    def setUp(self):
        self._norm = normalizer.PLSQLNormalizer()
        _path = os.path.dirname(os.path.abspath(__file__))
        _path = os.path.join(_path, "samples")
        self._path = _path

    def test_normalize(self):
        _path = os.path.join(self._path, "normalize")
        _path_src = os.path.join(_path, "sources")
        _path_rslt = os.path.join(_path, "results")

        _tests = 0

        for _sample_fn_base in fnmatch.filter(os.listdir(_path_src), "*.sql"):
            _tests += 1

            for _flagdir in fnmatch.filter(os.listdir(_path_rslt), "_*"):
                _flags = _flagdir.split("_")

                _ls_flags = list()

                for _flag in _flags:
                    _flag = _flag.replace("-","_")
                    if not _flag or not hasattr(normalizer.PLSQLNormalizationFlags, _flag):
                        continue

                    _ls_flags.append(getattr(normalizer.PLSQLNormalizationFlags, _flag))

                # see etalon for our file combination
                _etalon_fn = os.path.join(_path_rslt, _flagdir, _sample_fn_base)
                _sample_fn = os.path.join(_path_src, _sample_fn_base)
                _tempfile = tempfile.NamedTemporaryFile(mode='w+b')

                if os.path.exists(_etalon_fn):
                    self._norm.normalize_path(_sample_fn, write_to=_tempfile, flags=_ls_flags)
                    _tempfile.flush()
                    self.assertTrue(filecmp.cmp(_tempfile.name, _etalon_fn))
                else:
                    # should be an exception then
                    with self.assertRaises(normalizer.PLSQLNormalizationError):
                        self._norm.normalize_path(_sample_fn, write_to=_tempfile, flags=_ls_flags)

                _tempfile.close()

                if (os.path.exists(_tempfile.name)):
                    os.remove(_tempfile.name)

        self.assertTrue(_tests > 1)

    def test_file_is_wrappable(self):
        return self.__test_file_is("is_wrappable", self._norm.is_wrappable)

    def test_file_is_sql(self):
        return self.__test_file_is("is_sql", self._norm.is_sql)

    def test_file_is_wrapped(self):
        return self.__test_file_is("is_wrapped", self._norm.is_wrapped)

    def __test_file_is(self, context, n_method):
        _path = os.path.join(self._path, context)

        for _result in [True, False]:
            _rpath = os.path.join(_path, str(_result))

            _tests = 0

            for _sample_fn in fnmatch.filter(os.listdir(_rpath), "*.sql"):
                _tests += 1
                with open(os.path.join(_rpath, _sample_fn), 'rb') as _fl:
                    self.assertEqual(n_method(_fl), _result)

            self.assertTrue(_tests > 1)

    def test_path_is_wrappable(self):
        return self.__test_path_is("is_wrappable", self._norm.is_wrappable_path)

    def test_path_is_wrapped(self):
        return self.__test_path_is("is_wrapped", self._norm.is_wrapped_path)

    def test_path_is_sql(self):
        return self.__test_path_is("is_sql", self._norm.is_sql_path)

    def __test_path_is(self, context, n_method):
        _path = os.path.join(self._path, context)

        for _result in [True, False]:
            _tests = 0
            _rpath = os.path.join(_path, str(_result))

            for _sample_fn in fnmatch.filter(os.listdir(_rpath), "*.sql"):
                _tests += 1
                self.assertEqual(n_method(os.path.join(_rpath, _sample_fn)), _result)

            self.assertTrue(_tests > 1)

    def test_str_is_wrappable(self):
        return self.__test_str_is("is_wrappable", self._norm.is_wrappable)

    def test_str_is_sql(self):
        return self.__test_str_is("is_sql", self._norm.is_sql)

    def test_str_is_wrapped(self):
        return self.__test_str_is("is_wrapped", self._norm.is_wrapped)

    def __test_str_is(self, context, n_method):
        _path = os.path.join(self._path, context)

        for _result in [True, False]:
            _rpath = os.path.join(_path, str(_result))
            _tests = 0

            for _sample_fn in fnmatch.filter(os.listdir(_rpath), "*.sql"):
                _tests += 1
                with open(os.path.join(_rpath, _sample_fn), mode='rb') as _fl:
                    _sample_content = _fl.read()

                self.assertEqual(n_method(_sample_content), _result)

            self.assertTrue(_tests > 1)
