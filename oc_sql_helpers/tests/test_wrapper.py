# Unit-tests for wrap-unwrap class

import os
import filecmp
import fnmatch
import tempfile
import re

import unittest
import unittest.mock
from oc_sql_helpers import wrapper
from copy import copy

# to get rid of garbage output
import logging
logging.getLogger().propagate = False
logging.getLogger().disabled = True

class PLSQLWrapperTest(unittest.TestCase):

    def setUp(self):
        self._wrapper = wrapper.PLSQLWrapper()

    def test_check_wrapped__not_exist(self):
        # case 1: file does not exist
        _t = tempfile.NamedTemporaryFile()
        with unittest.mock.patch("os.path.exists", return_value=False):
            self.assertEqual("Output file '%s' was not created" % _t.name, 
                    self._wrapper._check_file_really_wrapped(_t))

        _t.close()

    def test_check_wrapped__zero_len(self):
        # case 2: file has zero length
        _t = tempfile.NamedTemporaryFile()

        class _x():
            def __init__(self):
                self.st_size = 0

        with unittest.mock.patch("os.path.exists", return_value=True):
            with unittest.mock.patch("os.stat", return_value=_x()):
                self.assertEqual("Output file '%s' has zero length" % _t.name, 
                        self._wrapper._check_file_really_wrapped(_t))

        _t.close()

    def test_check_wrapped__wrong_content(self):
        # case 3: file content is wrong
        _t = tempfile.NamedTemporaryFile()

        class _x():
            def __init__(self):
                self.st_size = 1

        class _norm():
            def __init__(self):
                pass

            def is_wrapped(self, fl):
                return False


        with unittest.mock.patch("os.path.exists", return_value=True):
            with unittest.mock.patch("os.stat", return_value=_x()):
                with unittest.mock.patch("oc_sql_helpers.wrapper.PLSQLNormalizer", return_value=_norm()):
                    self.assertEqual("Output file '%s' is not actually wrapped" % _t.name, 
                            self._wrapper._check_file_really_wrapped(_t))

        _t.close()

    def test_check_wrapped__ok(self):
        # case 4: everything fine
        _t = tempfile.NamedTemporaryFile()

        class _x():
            def __init__(self):
                self.st_size = 1

        class _norm():
            def __init__(self):
                pass

            def is_wrapped(self, fl):
                return True


        with unittest.mock.patch("os.path.exists", return_value=True):
            with unittest.mock.patch("os.stat", return_value=_x()):
                with unittest.mock.patch("oc_sql_helpers.wrapper.PLSQLNormalizer", return_value=_norm()):
                    self.assertEqual("", self._wrapper._check_file_really_wrapped(_t))

        _t.close()

    def test_wrap_path__no_env(self):
        # case 1: no 'ORACLE_HOME'
        with self.assertRaises(ValueError):
            self._wrapper.wrap_path('/path/to/something.sql')

    def test_wrap_path__no_input_ext(self):
        # case 2: no extension for input file
        _t = tempfile.NamedTemporaryFile()
        _orahome = os.path.join("/", "something", "orahome")
        _wrappth = os.path.join(_orahome, "bin", "wrap")
        self._wrapper._check_file_really_wrapped = unittest.mock.MagicMock(return_value="")

        def _exist(pth):
            return pth==_wrappth

        with unittest.mock.patch.dict(os.environ, {"ORACLE_HOME": _orahome}):
            with unittest.mock.patch("os.path.exists", side_effect=_exist) as _pospth:
                with unittest.mock.patch("subprocess.check_output") as _spco:
                    self._wrapper.wrap_path(_t.name)

        self.assertEqual(1, _spco.call_count)
        self.assertEqual(3, _pospth.call_count)
        _pospth.assert_any_call(_wrappth)

        _wrap_args = list(list(_spco.call_args).pop(0)).pop(0)
        self.assertEqual(_wrappth, _wrap_args.pop(0))
        self.assertFalse("iname=%s" % _t.name in _wrap_args)
        _lb = list(filter(lambda x: x.startswith("iname="), _wrap_args))
        self.assertEqual(1, len(_lb))
        _lb = _lb.pop()
        self.assertTrue(_lb.endswith(".sql"))
        _t.close()

    def test_wrap_path__no_output_ext(self):
        # case 3: no extension for output file
        _t = tempfile.NamedTemporaryFile(suffix='.sql')
        _o = tempfile.NamedTemporaryFile()
        _orahome = os.path.join("/", "something", "orahome")
        _wrappth = os.path.join(_orahome, "bin", "wrap")
        self._wrapper._check_file_really_wrapped = unittest.mock.MagicMock(return_value="")

        def _exist(pth):
            return pth==_wrappth

        with unittest.mock.patch.dict(os.environ, {"ORACLE_HOME": _orahome}):
            with unittest.mock.patch("os.path.exists", side_effect=_exist) as _pospth:
                with unittest.mock.patch("subprocess.check_output") as _spco:
                    with self.assertRaises(wrapper.PLSQLWrapError):
                        self._wrapper.wrap_path(_t.name, write_to=_o.name)

        _t.close()
        _o.close()


    def test_wrap_path__input_does_not_exist(self):
        # case 4: input file does not exist
        _orahome = os.path.join("/", "something", "orahome")
        _wrappth = os.path.join(_orahome, "bin", "wrap")
        self._wrapper._check_file_really_wrapped = unittest.mock.MagicMock(return_value="")

        with unittest.mock.patch.dict(os.environ, {"ORACLE_HOME": _orahome}):
            with unittest.mock.patch("os.path.exists", return_value=False) as _pospth:
                with unittest.mock.patch("subprocess.check_output") as _spco:
                    with self.assertRaises(FileNotFoundError):
                        self._wrapper.wrap_path("any.sql", write_to="any.plb")

    def test_wrap_path__ok_out_file(self):
        # case 5: output to file object
        _t = tempfile.NamedTemporaryFile(suffix='.sql')
        _o = tempfile.NamedTemporaryFile(suffix=".plb")
        _orahome = os.path.join("/", "something", "orahome")
        _wrappth = os.path.join(_orahome, "bin", "wrap")
        self._wrapper._check_file_really_wrapped = unittest.mock.MagicMock(return_value="")

        def _exist(pth):
            return pth==_wrappth

        _wrap_content = "test_wrap_content"

        def _wrap(lsargs):
            _lsargs = copy(lsargs)
            _wt = _lsargs.pop()

            if not _wt.startswith("oname="):
                raise ValueError("Output file name was not defined")

            _tf = _lsargs.pop()

            if not _tf.startswith("iname="):
                raise ValueError("Input file is not defined")

            _wp = _lsargs.pop()

            if _wp != _wrappth:
                raise ValueError("Wrap binary path wrong")

            _wt = _wt[len("oname="):]

            with open(_wt, mode="wt") as _f:
                _f.write(_wrap_content)
                _f.flush()

        with unittest.mock.patch.dict(os.environ, {"ORACLE_HOME": _orahome}):
            with unittest.mock.patch("os.path.exists", side_effect=_exist) as _pospth:
                with unittest.mock.patch("subprocess.check_output", side_effect=_wrap) as _spco:
                    self._wrapper.wrap_path(_t.name, write_to=_o.name)

        self.assertEqual(1, _spco.call_count)
        self.assertEqual(2, _pospth.call_count)
        _pospth.assert_any_call(_wrappth)

        _wrap_args = list(list(_spco.call_args).pop(0)).pop(0)
        self.assertEqual(_wrappth, _wrap_args.pop(0))
        self.assertTrue("iname=%s" % _t.name in _wrap_args)
        _lb = list(filter(lambda x: x.startswith("iname="), _wrap_args))
        self.assertEqual(1, len(_lb))
        _lb = _lb.pop()
        self.assertTrue(_lb.endswith(_t.name))
        
        _lo = list(filter(lambda x: x.startswith("oname="), _wrap_args))
        self.assertEqual(len(_lo), 1)
        _lo = _lo.pop()
        self.assertTrue(_lo.endswith(_o.name))
        self.assertTrue(_lo.endswith(".plb"))

        _t.close()
        _o.seek(0, os.SEEK_SET)
        self.assertEqual(_o.read(), _wrap_content.encode('ascii'))
        _o.close()

    def test_wrap_path__ok_out_str(self):
        # case 6: output to string
        _t = tempfile.NamedTemporaryFile(suffix='.sql')
        _orahome = os.path.join("/", "something", "orahome")
        _wrappth = os.path.join(_orahome, "bin", "wrap")
        self._wrapper._check_file_really_wrapped = unittest.mock.MagicMock(return_value="")

        def _exist(pth):
            return pth==_wrappth

        _wrap_content = "test_wrap_content"

        def _wrap(lsargs):
            _lsargs = copy(lsargs)
            _wt = _lsargs.pop()

            if not _wt.startswith("oname="):
                raise ValueError("Output file name was not defined")

            _tf = _lsargs.pop()

            if not _tf.startswith("iname="):
                raise ValueError("Input file is not defined")

            _wp = _lsargs.pop()

            if _wp != _wrappth:
                raise ValueError("Wrap binary path wrong")

            _wt = _wt[len("oname="):]

            with open(_wt, mode="wt") as _f:
                _f.write(_wrap_content)
                _f.flush()

        with unittest.mock.patch.dict(os.environ, {"ORACLE_HOME": _orahome}):
            with unittest.mock.patch("os.path.exists", side_effect=_exist) as _pospth:
                with unittest.mock.patch("subprocess.check_output", side_effect=_wrap) as _spco:
                    _result = self._wrapper.wrap_path(_t.name)

        self.assertEqual(1, _spco.call_count)
        self.assertEqual(3, _pospth.call_count)
        _pospth.assert_any_call(_wrappth)

        _wrap_args = list(list(_spco.call_args).pop(0)).pop(0)
        self.assertEqual(_wrappth, _wrap_args.pop(0))
        self.assertTrue("iname=%s" % _t.name in _wrap_args)
        _lb = list(filter(lambda x: x.startswith("iname="), _wrap_args))
        self.assertEqual(1, len(_lb))
        _lb = _lb.pop()
        self.assertTrue(_lb.endswith(_t.name))
        
        _lo = list(filter(lambda x: x.startswith("oname="), _wrap_args))
        self.assertEqual(len(_lo), 1)
        _lo = _lo.pop()
        self.assertTrue(_lo.endswith(".plb"))

        _t.close()
        self.assertEqual(_result, _wrap_content.encode('ascii'))

    def test_wrap_buf(self):
        # it is wrapper for 'wrap_path'
        self._wrapper.wrap_path = unittest.mock.MagicMock(return_value="wrapped_val")
        _t = tempfile.NamedTemporaryFile()
        self.assertEqual(self._wrapper.wrap_buf(_t, write_to="/path/to/anything"), "wrapped_val")
        self._wrapper.wrap_path.assert_called_once_with(_t.name, "/path/to/anything")


class PLSQLUnWrapperTest(unittest.TestCase):
    # test unwrapping
    def setUp(self):
        _path = os.path.dirname(os.path.abspath(__file__))
        _path = os.path.join(_path, "samples")
        self.samples = _path
        self._wrapper = wrapper.PLSQLWrapper()

    def test_unwrap_path(self):
        # it is wrapper for 'unwrap_buf'
        with self.assertRaises(TypeError):
            self._wrapper.unwrap_path(1)

        _x = tempfile.NamedTemporaryFile(suffix=".sql", mode="w+t")
        _test_content = "Test content for unwrap\npath"
        _x.write(_test_content)
        _x.flush()
        self._wrapper.unwrap_buf = unittest.mock.MagicMock(return_value=_test_content)
        self.assertEqual(_test_content, self._wrapper.unwrap_path(_x.name))
        _x.close()
        self._wrapper.unwrap_buf.assert_called_once()

    def test_unwrap_buf__write_to(self):
        # this case it is more efficient to test by classic way:
        # source file -> unwrap -> compare to etalon 
        _path = os.path.join(self.samples, "unwrap")
        _path_sources = os.path.join(_path, "sources")
        _path_results = os.path.join(_path, "results")

        for _sample_fn in fnmatch.filter(os.listdir(_path_sources), '*.plb'):
            _etalon_fn = ".".join([list(os.path.splitext(_sample_fn)).pop(0), "sql"])
            _etalon_fn = os.path.join(_path_results, _etalon_fn)
            _sample_fn = os.path.join(_path_sources, _sample_fn)

            if not (os.path.exists(_etalon_fn)):
                # this case file is not wrapped correctly
                # so exception should be raised
                with open(_sample_fn, mode='rb') as _fl_in:
                    with self.assertRaises(Exception):
                        self._wrapper.unwrap_buf(_fl_in)
                continue

            _tempfile = tempfile.NamedTemporaryFile(mode="w+b")
            _temp_fn = _tempfile.name
            _fl_in = open(_sample_fn, 'rb')
            _tempfile.seek(0, os.SEEK_SET)
            self._wrapper.unwrap_buf(_fl_in, write_to=_tempfile)
            _tempfile.flush()
            _fl_in.close()
            self.assertTrue(filecmp.cmp(_temp_fn, _etalon_fn))

            _tempfile.close()

            if (os.path.exists(_temp_fn)):
                os.remove(_temp_fn)

    def test_unwrap_buf__bytes(self):
        # this case it is more efficient to test by classic way:
        # source file -> unwrap -> compare to etalon 
        _path = os.path.join(self.samples, "unwrap")
        _path_sources = os.path.join(_path, "sources")
        _path_results = os.path.join(_path, "results")

        for _sample_fn in fnmatch.filter(os.listdir(_path_sources), '*.plb'):
            _etalon_fn = ".".join([list(os.path.splitext(_sample_fn)).pop(0), "sql"])
            _etalon_fn = os.path.join(_path_results, _etalon_fn)
            _sample_fn = os.path.join(_path_sources, _sample_fn)

            if not (os.path.exists(_etalon_fn)):
                # this case file is not wrapped correctly
                # so exception should be raised
                with open(_sample_fn, mode='rb') as _fl_in:
                    with self.assertRaises(Exception):
                        self._wrapper.unwrap_buf(_fl_in)
                continue

            _fl_in = open(_sample_fn, 'rb')
            _result = self._wrapper.unwrap_buf(_fl_in)
            _fl_in.close()

            with open(_etalon_fn, mode='rb') as _f:
                self.assertEqual(_result, _f.read())

