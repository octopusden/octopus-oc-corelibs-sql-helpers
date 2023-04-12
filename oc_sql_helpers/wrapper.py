#!/usr/bin/env python3
# partial usage: 'unwrap.py' by niels@teusink.net/blog.teusink.net which is distributed under Public Domain license

"""
This module does wrapping and unwrapping of PL/SQL code.
'Unwrap' is done by  'unwrap.py' (niels@teusink.net/blog.teusink.net)
    which is distributed under Public Domain license:
    code inserted and adopted for Python3 usage.
'Wrap' uses oracle 'wrap' utility from ${ORACLE_HOME}/bin, so it must exist anyhow, but NOT included to this package
    due to license violation
"""

import os
import tempfile
import errno
import subprocess
import base64
import zlib
import re
import logging
from .normalizer import PLSQLNormalizer

class PLSQLWrapError(Exception):
    pass

class PLSQLWrapper(object):

    # simple substitution map for unwrapping
    _charmap = [0x3d, 0x65, 0x85, 0xb3, 0x18, 0xdb, 0xe2, 0x87, 0xf1, 0x52, 0xab, 0x63, 0x4b, 0xb5, 0xa0, 0x5f, 0x7d, 0x68, 0x7b, 0x9b, 0x24, 0xc2, 0x28, 0x67, 0x8a, 0xde, 0xa4, 0x26, 0x1e, 0x03, 0xeb, 0x17, 0x6f, 0x34, 0x3e, 0x7a, 0x3f, 0xd2, 0xa9, 0x6a, 0x0f, 0xe9, 0x35, 0x56, 0x1f, 0xb1, 0x4d, 0x10, 0x78, 0xd9, 0x75, 0xf6, 0xbc, 0x41, 0x04, 0x81, 0x61, 0x06, 0xf9, 0xad, 0xd6, 0xd5, 0x29, 0x7e, 0x86, 0x9e, 0x79, 0xe5, 0x05, 0xba, 0x84, 0xcc, 0x6e, 0x27, 0x8e, 0xb0, 0x5d, 0xa8, 0xf3, 0x9f, 0xd0, 0xa2, 0x71, 0xb8, 0x58, 0xdd, 0x2c, 0x38, 0x99, 0x4c, 0x48, 0x07, 0x55, 0xe4, 0x53, 0x8c, 0x46, 0xb6, 0x2d, 0xa5, 0xaf, 0x32, 0x22, 0x40, 0xdc, 0x50, 0xc3, 0xa1, 0x25, 0x8b, 0x9c, 0x16, 0x60, 0x5c, 0xcf, 0xfd, 0x0c, 0x98, 0x1c, 0xd4, 0x37, 0x6d, 0x3c, 0x3a, 0x30, 0xe8, 0x6c,
                    0x31, 0x47, 0xf5, 0x33, 0xda, 0x43, 0xc8, 0xe3, 0x5e, 0x19, 0x94, 0xec, 0xe6, 0xa3, 0x95, 0x14, 0xe0, 0x9d, 0x64, 0xfa, 0x59, 0x15, 0xc5, 0x2f, 0xca, 0xbb, 0x0b, 0xdf, 0xf2, 0x97, 0xbf, 0x0a, 0x76, 0xb4, 0x49, 0x44, 0x5a, 0x1d, 0xf0, 0x00, 0x96, 0x21, 0x80, 0x7f, 0x1a, 0x82, 0x39, 0x4f, 0xc1, 0xa7, 0xd7, 0x0d, 0xd1, 0xd8, 0xff, 0x13, 0x93, 0x70, 0xee, 0x5b, 0xef, 0xbe, 0x09, 0xb9, 0x77, 0x72, 0xe7, 0xb2, 0x54, 0xb7, 0x2a, 0xc7, 0x73, 0x90, 0x66, 0x20, 0x0e, 0x51, 0xed, 0xf8, 0x7c, 0x8f, 0x2e, 0xf4, 0x12, 0xc6, 0x2b, 0x83, 0xcd, 0xac, 0xcb, 0x3b, 0xc4, 0x4e, 0xc0, 0x69, 0x36, 0x62, 0x02, 0xae, 0x88, 0xfc, 0xaa, 0x42, 0x08, 0xa6, 0x45, 0x57, 0xd3, 0x9a, 0xbd, 0xe1, 0x23, 0x8d, 0x92, 0x4a, 0x11, 0x89, 0x74, 0x6b, 0x91, 0xfb, 0xfe, 0xc9, 0x01, 0xea, 0x1b, 0xf7, 0xce]

    # wrapped delcaration regexp
    _re_decl = re.compile(
            b"(?P<create_suffix>create\s+(or\s+replace\s+)?)(?P<object_type>(package\s+body|package|procedure|function))\s+(?P<object_name>(.*))\s+wrapped(\s+|$)", 
            flags=re.I)
    _re_cmnt = re.compile(b"(/\*.*?\*/|\-\-[^\n]*?\n)", flags=re.DOTALL)

    def _check_file_really_wrapped(self, fl):
        """
        Read fl and check it is wrapped
        :param fl: file-like object to check, should be opened in binary mode
        :return str: error description
        """
        if not os.path.exists(fl.name):
            return "Output file '%s' was not created" % fl.name

        if not os.stat(fl.name).st_size:
            return "Output file '%s' has zero length" % fl.name

        # file may be simply copied and not actually wrapped
        if not PLSQLNormalizer().is_wrapped(fl):
            return "Output file '%s' is not actually wrapped" % fl.name

        return ""

    def wrap_path(self, path_in, write_to=None):
        """
        Wraps PL/SQL file.
        :param str path_in: string, path to a file to wrap
        :param write_to: string or file-like object for output, shoud be opened in binary read-write mode
        :return str: 'None' if 'write_to' given, wrapped bytes object with wrapped content otherwise
        """
        # Here and below all python-2 related paths commented for possible usage with Python 2.7 in the future
        #if version_info.major == 2 and not isinstance(path_in, basestring):
        #    raise TypeError('str_path should be string')

        #if version_info.major == 3 and not isinstance(path_in, str):
        if not isinstance(path_in, str):
            raise TypeError('path should be a string, not %s' % type(path_in))

        logging.debug('wrap_path called with argument %s', path_in)

        _oracle_home = os.getenv("ORACLE_HOME")

        if not _oracle_home:
            raise ValueError("ORACLE_HOME environment variable is not set")

        _lib_path = os.path.join(_oracle_home, "lib")

        if _lib_path not in os.getenv('PATH', ""):
            os.environ['PATH'] = ':'.join([_lib_path, os.getenv("PATH", "")])

        if _lib_path not in os.getenv('LD_LIBRARY_PATH', ""):
            os.environ['LD_LIBRARY_PATH'] = ':'.join([_lib_path, os.getenv("LD_LIBRARY_PATH", "")])

        _bin_path = os.path.join(_oracle_home, "bin")

        if _bin_path not in os.getenv('PATH', ""):
            os.environ['PATH'] = ':'.join([_bin_path, os.getenv("PATH", "")])

        _wrap_path = os.path.join(_bin_path, "wrap")

        if not os.path.exists(_wrap_path):
            raise FileNotFoundError(_wrap_path)

        # create temporary file and try to wrap to it
        if not write_to:
            logging.debug("write_to is empty, creating temporary buffer...")
            _tempfile = tempfile.NamedTemporaryFile(suffix='.plb')
            _temp_path = _tempfile.name
        elif isinstance(write_to, str):
            _tempfile = open(write_to, mode='w+b')
            _temp_path = write_to
        else:
            logging.debug("Assuming 'write_to' is a real file-like object with valid 'name' attribute")
            _tempfile = write_to
            _temp_path = write_to.name

        if not list(os.path.splitext(_temp_path)).pop():
            # close temporary opened resources
            if not write_to or isinstance(write_to, str):
                _tempfile.close()

            raise PLSQLWrapError("Wrap to file without extension is not supported ('%s')" % _temp_path)

        # fixing problem with Oracle wrap trying to open file without extension
        _tmpdir = tempfile.TemporaryDirectory(suffix='wrap')
        if not list(os.path.splitext(path_in)).pop():
            logging.debug(
                'wrap_path got file without extension, this breaks Oracle "wrap", fixing by creating symlink...')
            logging.debug('wrap_path temp directory created: %s', _tmpdir.name)
            _path_new = os.path.join(_tmpdir.name, '.'.join([os.path.basename(path_in),'sql']))
            logging.debug('wrap_path creating symlink %s', _path_new)
            os.symlink(path_in, _path_new)
            path_in = _path_new

        _wrap_result = subprocess.check_output([_wrap_path, "iname=%s" % path_in, "oname=%s" % _temp_path])
        _wrapped = None
        logging.debug("Wrap result: '%s'" % str(_wrap_result))

        # checking if output file has more than zero length
        # workaround for buggy 'wrap' utility who may silently rid of wrapping in case of wrong SQL
        # this case zero-lenght file will be created

        _error = self._check_file_really_wrapped(_tempfile)

        if not write_to:
            _tempfile.seek(0, os.SEEK_SET)
            _wrapped = _tempfile.read()
            _tempfile.close()

            if os.path.exists(_temp_path):
                os.remove(_temp_path)
        elif isinstance(write_to, str):
            _tempfile.close()
        else:
            _tempfile.seek(0, os.SEEK_END)
        
        _tmpdir.cleanup()

        # cleanup workaround about buggy 'tempfile', but this should never happen
        if os.path.exists(_tmpdir.name):
            os.remove(_tmpdir.name)

        if _error:
            raise PLSQLWrapError(_error)

        return _wrapped

    def wrap_buf(self, fl_in, write_to=None):
        """
        Wraps PL/SQL file buffer.
        :param fl_in: file or file-like object to wrap, have to be open in binary mode, not string
        :return bytes: bytes object with wrapped content if 'write_to' is omitted, 'None' otherwise
        """
        _wrapped = self.wrap_path(fl_in.name, write_to)

        return _wrapped

    def _decode_base64_package(self, pkg_base64):
        """
        Decodes wrapped package.
        :param bytes pkg_base64: byte-like object, wrapped content (base64 package)
        :return bytes: decoded/unwrapped 'pkg_base64'
        """
        # convert encoded wrapped characters to byte sequence
        # strip the first 20 chars (SHA1 hash, don't bother checking it at the moment) #comment by neils
        _base64dec = base64.b64decode(pkg_base64)[20:]
        _decoded = b''

        for _char in _base64dec:  # see byte-by-byte
            # commented for possible future use in Python 2.7
            #if version_info.major == 2:
            #    _decoded += chr(
            #        self._charmap[ord(str_base64dec[int_idx])])

            #if version_info.major == 3:
            _decoded += bytes([self._charmap[_char]])

        return zlib.decompress(_decoded)

    def unwrap_buf(self, fl_in, write_to=None):
        """
        Unwraps PL/SQL wrapped file buffer.
        :param self: self class object reference
        :param fl_in: file or file-like object to unwrap,
                      have to be opened in BINARY mode because of possible encoding issues
        :param write_to: string (path) or file-like object to write result to
        :return: 'None' if 'write_to' given, bytes object with unwrapped content if 'write_to' is omitted
        """
        # prepare output
        _fl_out = None
        
        # if we have a string path - just open a file
        if not write_to:
            _fl_out = tempfile.NamedTemporaryFile(suffix='.sql', mode='w+b')
        elif isinstance(write_to, str):
            _fl_out = open(write_to, mode='wb')
        else:
            _fl_out = write_to

        _pos = fl_in.tell()
        fl_in.seek(0, os.SEEK_SET)

        # commented for possible usage in Python 2.7
        #if version_info.major == 2:
        #    _re_wrapstart = re.compile(r"^[0-9a-f]+ ([0-9a-f]+)$")
        #    self._re_decl = re.compile(
        #        r"(?P<create_suffix>create\s+(or\s+replace\s+))(?P<object_type>(package\s+body|package|procedure|function))\s+(?P<object_name>(.*))\s+wrapped", flags=re.I)

        #if version_info.major == 3:
        _re_wrapstart = re.compile(b"^[0-9a-f]+ ([0-9a-f]+)$")

        _decl = b""
        _decl_next = b""
        _obj_type = b""
        _obj_name = b""
        _create_prefix = b""

        while True:
            _line = fl_in.readline()

            if not _line:
                # end of file
                break

            _line = self._re_cmnt.sub(b" ", _line)
            _line = _line.strip()

            if not _line:
                # empty line - out of interest
                continue

            _match_decl = self._re_decl.search(_decl)

            if not _match_decl:
                _decl = b' '.join([_decl, _line])
                _decl = self._re_cmnt.sub(b'', _decl)
                continue

            _decl = _decl[_match_decl.start(): _match_decl.end()]

            # commented for possible usage in Python 2.7
            #if version_info.major == 2:
            #    _obj_type = re.sub(
            #        r'\s+', " ", _match_decl.groupdict()["object_type"].upper())

            #if version_info.major == 3:
            _obj_type = re.sub(b'\s+', b" ", _match_decl.groupdict().get("object_type").upper())
            _obj_name = _match_decl.groupdict().get("object_name").upper()
            _create_prefix = _match_decl.groupdict().get("create_suffix").upper()
            logging.log(1, "object_type: %s" % _obj_type)
            logging.log(1, "Object_name: %s" % _obj_name)
            logging.log(1, "Create prefix: %s" % _create_prefix)

            # comment by neils:
            #  "This is really naive parsing, but works on every package I've thrown at it"
            _match_wrapstart = _re_wrapstart.match(_line)

            if not _match_wrapstart:
                continue

            _base64len = int(_match_wrapstart.groups()[0], 16)
            _base64 = b""

            # append symbols while length is less then expected, check length every time.
            # lenght is in symbols, not in strings
            while len(_base64) < _base64len:
                _line_add = fl_in.readline()

                # read one more line
                if not _line_add:
                    break

                # stripping makes length calculation wrong
                # but we have to remove '\r' - it counts as single 'newline' character
                #_line_add = _line_add.strip()
                _line_add = _line_add.replace(b'\r', b"")

                if not _line_add:
                    continue

                _base64 += _line_add

            if len(_base64) > _base64len:
                #we have to strip _base64 to its len and put other part to declaration
                _decl_next = _base64[_base64len:]
                _base64=_base64[:_base64len]

            _add = self._decode_base64_package(_base64.replace(b'\n', b"")) + b'\n'

            if _add.upper().startswith(_obj_type):
                _start = _create_prefix + _obj_type
                logging.log(1, "Start: %s" % _start)

                # commented for possible use in Python 2.7
                #if version_info.major == 2:
                #    str_start = re.sub(r"\s+", " ", str_start.strip())

                #if version_info.major == 3:
                _start = re.sub(b"\s+", b" ", _start.strip())
                logging.log(1, "Start: %s" % _start)

                if b"." in _obj_name:
                    # we have to parse schema name from object name
                    _splitted = _obj_name.split(b'.')
                    _schema_name = b""
                    _quoted = False

                    for _s in _splitted:
                        if _schema_name:
                            _schema_name = b'.'.join([_schema_name, _s])
                        else:
                            _schema_name = _s

                        # may be double quoted, line "schema"."name"
                        _nq = len(_s.split(b'"')) - 1

                        if _nq%2:
                            _quoted = not _quoted
                            logging.log(1, "quoted: %s" % str(_quoted))
                        
                        if not _quoted:
                            break

                    _start = b' '.join([_start, _schema_name + b'.'])
                else:
                    _start += b' '

                    # commented for possible use in Python 2.7
                    #if version_info.major == 2:
                    #    str_start = re.sub(r'\s+$', ' ', str_start)

                    #if version_info.major == 3:
                    _start = re.sub(b'\s+$', b' ', _start)

                logging.log(1, "Start: %s" % _start)

                #if version_info.major == 2:
                #    _add = re.sub(r"^" + _obj_type + "\s+",
                #                     _start, _add, flags=re.I)

                #if version_info.major == 3:
                _add = re.sub(b"^%s\s+" % _obj_type, _start, _add, flags=re.I)
                _add = _add.replace(b"\0",b"")
            _fl_out.write(_add)

            #if version_info.major == 2:
            #    str_result = str_result.replace("\0", "")

            #if version_info.major == 3:
            #    str_result = str_result.replace(b"\0", b"")

            _decl = _decl_next if _decl_next else b""
            _obj_name = b""
            _obj_type = b""
            _create_prefix = b""

        fl_in.seek(_pos, os.SEEK_SET)

        _result = None

        if not write_to:
            _fl_out.seek(0, os.SEEK_SET)
            _result = _fl_out.read()
            _fl_out.close()
        elif isinstance(write_to, str):
            _fl_out.close()

        return _result

    def unwrap_path(self, path_in, write_to=None):
        """
        Unwraps a file resided under 'path'.
        Result is not predictable if the source 'fl_in' is not wrapped.
        :param str path_in: path to a file to unwrap
        :param write_to: string (path) or file-like object to write result to (binary mode!)
        :return: 'None' if 'write_to' given, bytes object with unwrapped content if 'write_to' is omitted
        """
        if not isinstance(path_in, str):
            raise TypeError('path should be a string, not %s' % type(path_in))

        with open(path_in, 'rb') as _fl_in:
            _result = self.unwrap_buf(_fl_in, write_to)

        return _result


if __name__ == "__main__":
    import argparse

    _parser = argparse.ArgumentParser(
            description='Wrap-unwrap PL/SQL code from one file to another, with additional checks')
    _parser.add_argument("--in", dest="fn_in", help="Input file path", required=True)
    _parser.add_argument("--out", dest="fn_out", help="Output file path", required=True)
    _parser.add_argument("--wrap", dest="wrap", help="Do wrapping", default=False, action='store_true')
    _parser.add_argument("--unwrap", dest="unwrap", help="Do unwrapping", default=False, action='store_true')
    _parser.add_argument("--log-level", dest="log_level", help="Logging level", type=int, default=20)
    _args = _parser.parse_args()

    logging.basicConfig(
            format="%(pathname)s: %(asctime)-15s: %(levelname)s: %(funcName)s: %(lineno)d: %(message)s",
            level=_args.log_level)

    if all([_args.wrap, _args.unwrap]):
        raise ValueError("Please specify one command only: --wrap or --unwrap")

    if not any([_args.wrap, _args.unwrap]):
        raise ValueError("Please specify one command to proceed: --wrap or --unwrap")

    _fn_in = os.path.abspath(_args.fn_in)
    _fn_out = os.path.abspath(_args.fn_out)
    logging.info("Input file: '%s'" % _fn_in)
    logging.info("Output file: '%s'" % _fn_out)

    if _args.wrap:
        logging.info("Processing wrap")
        PLSQLWrapper().wrap_path(_fn_in, write_to=_fn_out)

    if _args.unwrap:
        logging.info("Processin unwrap")
        PLSQLWrapper().unwrap_path(_fn_in, write_to=_fn_out)

    logging.info("Done")
    
