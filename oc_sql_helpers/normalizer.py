#/usr/bin/env python3

"""
Normalizing file buffer with PL/SQL code:
- remove comments (if set)
- replace all windows-stype newline to unix-style (unconditionally)
- all-in-one-string, except literals (if set)
- capitalize all, except literals (if set)
- removes double quotes from object names if no spaces are in them
All files and file-like objects have to be opened in BINARY mode
"""

import re
from enum import IntEnum
import tempfile
import logging
import os

class PLSQLNormalizationFlags(IntEnum):
    # BEG: possible normalization flags
    """
    Process flags:
    :param no_comments: strip all comments from body.
    :param no_spaces: replace all space symbols sequences to one spaces in the body. Can't be used without 'm_fl_no_comments'
    :param uppercase: make all relevant (non-literals and non-comments) to uppercase
    """
    no_comments = 1
    no_spaces = 2
    uppercase = 3
    no_literals = 4
    comments_only = 5
    # END: possible normalization flags

class PLSQLNormalizationError(Exception):
    pass

class PLSQLNormalizer():
    """
    PL/SQL code normalizing class.
    """

    __re_pattern_type = type(re.compile('^$'))
    _comment_started = False
    _literal_started = False
    _object_name_started = False
    _wrapped = False
    _create_found = False
    _or_found = False
    _replace_found = False
    _as_found = False
    _object_type = None
    _object_name = None
    _process_flags = list()
    _re_endobj = None
    _re_win_nl = re.compile(b'\r')
    _re_end_space = re.compile(b'\s+$')
    _re_start_space = re.compile(b'^\s+')
    _re_any_space = re.compile(b'\s+')
    _re_add_slash = re.compile(b'(^|\s+)\/(\s+)?(\n)?$')
    # these object regexps is to be searched in declaration and have not to be found in body
    _re_objects_decl={
            "create": [{"start": re.compile(b'(\s|^)create(\s|$)', flags=re.I)}],
            "or": [{"start": re.compile(b'(\s|^)or(\s|$)', flags=re.I)}],
            "replace": [{"start": re.compile(b'(\s|^)replace(\s|$)', flags=re.I)}],
            "object_type": [{"start": re.compile(b'(\s|^)(function|procedure|package|body|trigger)(\s|$)', flags=re.I)}],
            "as": [{"start": re.compile(b'(\s|^)(as|is)(\s|$)', flags=re.I)}],
            "wrapped": [{"start": re.compile(b'(\s|^)wrapped(\s|$)', flags=re.I)}]}
    # these objects are legal in any part of file
    # NOTE: national charset literals may be supported in wrong way by this implementation
    _re_objects_body={
            "object_name": [{"start": re.compile(b'"'), "end": re.compile(b'"')}],
            "literal":[
                {"start": re.compile(b"q'(.)", flags=re.I), "end": b"%s'", 
                    "substitutes": {
                        b"[": b"\]", 
                        b"{": b"\}", 
                        b"<": b"\>", 
                        b"(": b"\)", 
                        b"?": b"\?", 
                        b".": b"\.", 
                        b"^": b"\^", 
                        b"$": b"\$", 
                        b"\\": b"\\\\", 
                        b"*": b"\*",
                        b"+": b"\+", 
                        b"|": b"\|",
                        # there may be a closing brackets also, we have to escape them too
                        b"]": b"\]", 
                        b"}": b"\}", 
                        b">": b"\>", 
                        b")": b"\)"}},
                {"start": re.compile(b"'", flags=re.I), "end": re.compile(b"'")}],
            "comment":[
                {"start": re.compile(b'(\s|^)\-\-'), "end": re.compile(b'\n')},
                {"start": re.compile(b'\/\*'), "end": re.compile(b'\*\/')}]}

    def _fl_full(self):
        """
        Returns a list of full flags possible
        :param self: self class object reference
        """

        return [PLSQLNormalizationFlags.no_comments, PLSQLNormalizationFlags.no_spaces, PLSQLNormalizationFlags.uppercase]

    def _reset_parse_flags(self):
        """
        Drop any object-related flags
        """
        self._comment_started = False
        self._literal_started = False
        self._object_name_started = False

    @property
    def _parsecontext(self):
        """
        Return a string representation of parse flags
        """
        if self._comment_started:
            return "comment"

        if self._literal_started:
            return "literal"

        if self._object_name_started:
            return "object_name"

        return None

    def _reset(self):
        """
        Reset parse parameters to their defaults.
        :param self: self class object reference
        """
        self._reset_parse_flags()
        self._wrapped = False
        self._create_found = False
        self._or_found = False
        self._replace_found = False
        self._as_found = False
        self._object_type = None
        self._object_name = None
        self._re_endobj = None
        self._process_flags = list()
        self._object_name_append = False
        self._object_name_remove_quotes = False
        return

    def _check_flags(self):
        """
        Checks the flags are convinient and does not conflict.
        :param self: self class object reference
        """

        if all([
            PLSQLNormalizationFlags.no_comments not in self._process_flags,
            PLSQLNormalizationFlags.no_spaces in self._process_flags]):

            raise PLSQLNormalizationError(
                    "Can not process with 'no_spaces' without 'no_comments' since this could convert PL/SQL code sample to one with wrong syntax.")

        if all([
            PLSQLNormalizationFlags.comments_only in self._process_flags,
            len(self._process_flags) > 1]):

            raise PLSQLNormalizationError("Flag 'comments_only' is incompatible with another normalization flags")
        return

    @property
    def _anything_started(self):
        """
        Check if we are parsing any non-changed object now
        """
        return bool(any([self._comment_started, self._literal_started, self._object_name_started]) and self._re_endobj)

    def _make_reg_end(self, regdict, match):
        """
        Construct regular expression end upon dictionary given
        :param dict regdict: regexp dictionary entry
        :param re.Match: match object with groupped content
        :return re.Pattern:  compiled regular expression
        """
        if not regdict or not regdict.get("end"):
            return None

        _result = regdict.get("end")

        if isinstance(_result, self.__re_pattern_type):
            return _result

        _subst = list(match.groups())

        if regdict.get("substitutes"):
            _subst = list(map(lambda x: regdict.get("substitutes").get(x, x), _subst))

        logging.debug("Regular expression to compile: '%s'" % (_result % tuple(_subst)))

        _result = re.compile(_result % tuple(_subst))

        return _result

    def _search_regexp_on_dict(self, line, regxps):
        """
        Try to find the nearest regular expression match in the dictionary
        :param bytes line: line to search
        :param dict regexps: regular expression dictionary
        :return dict: {"context": matchKey, "match": MatchObject, "end": CompiledRegularExpession}
        """
        _result = None
        for _k, _v in regxps.items():
            if not _v:
                # out of interest
                continue

            for _regx in _v:
                _match = _regx.get("start").search(line)

                if not _match:
                    # out of interest
                    continue

                # here we have a match object
                # if start posistion is less than one we have now - replace the context key in the result
                if _result and _match.start() >= _result.get("match").start():
                    # not a first inc, out of interest
                    continue

                logging.log(1, "Found context: [%s], match: [%s]" % (_k, _match))

                _result = {"context": _k, "match": _match, "end": self._make_reg_end(_regx, _match)}

        return _result

    def _search_declaration_regx(self, line):
        """
        Search 'line' upon declaration regular expressions
        :param bytes line: line to search declaration at
        :return dict: or 'None' if not found
        """
        return self._search_regexp_on_dict(line, self. _re_objects_decl)

    def _search_body_regx(self, line):
        """
        Search 'line' upon body regular expressions
        :param bytes line: line to search at
        :return dict: or 'None' if not found
        """
        return self._search_regexp_on_dict(line, self._re_objects_body)

    def _search_combine_regex(self, line):
        """
        Search 'line' upon any regular expression from objects
        :param bytes line: line to search at
        :return dict: or 'None' if not found
        """
        _result = None
        for _reg_dict in [self._re_objects_decl, self._re_objects_body]:
            _t = self._search_regexp_on_dict(line, _reg_dict)

            if not _result:
                _result = _t
                continue

            if not _t:
                continue

            if _t.get("match").start() < _result.get("match").start():
                _result = _t

        return _result

    def _join_line(self, b_before, b_joining, b_after, context, start):
        """
        Join the line upon normalization flags
        :param bytes b_before: first part of line
        :param bytes b_joining: joining bytes
        :param bytes b_after: bytes after
        :param str context: join context
        :param boolean start: join as start or as end
        """
        logging.log(1, "%s,%s,%s,%s,%s" % (b_before, b_joining, b_after, context, start))
        if (PLSQLNormalizationFlags.no_spaces not in self._process_flags \
                and any([self._as_found,
                    self._wrapped,
                    context == "comment" and PLSQLNormalizationFlags.comments_only in self._process_flags])):
            return b"".join([b_before, b_joining, b_after])

        # if two of three components are space-chars only then return 'as is'
        # do not modify b_after anyhow since it is modified when 'filtering' it properly
        _see_start_context = bool(context in ["object_name", "literal", "comment"])
        if not _see_start_context or all([_see_start_context, start]):
            b_before = self._re_any_space.sub(b" ", b_before)

        if not _see_start_context:
            b_joining = self._re_any_space.sub(b" ", b_joining)

        _result = b_before
        
        if self._re_end_space.search(_result) and not _see_start_context \
                or all([_see_start_context, start]):
            b_joining = b_joining.lstrip()
            
        _result = b"".join([_result, b_joining])
        
        if all([
            self._re_end_space.search(_result),
            self._re_start_space.search(b_after),
            not _see_start_context or all([_see_start_context, not start]) or not b_joining ]):
                _result = _result.rstrip()
            
        _result = b"".join([_result, b_after])

        return _result                

    def _append_object_name(self, line):
        """
        Append object name from line given
        Should not be called inside comments and literals
        """
        _to_append = line.upper()

        # if we have to remove quotes - strip them
        if self._object_name_remove_quotes:
            _to_append = re.sub(b'"', b'', _to_append)

        # if object name is not started - append everything before first space char
        if not self._object_name_started:
            _to_append = list(self._re_any_space.split(_to_append)).pop(0)
            # re-calculate '_object_name_append' flag for this case
            self._object_name_append = self._re_any_space.search(line)

        if _to_append:
            try:
                _to_append = _to_append.decode("utf-8")
            except UnicodeDecodeError as _e:
                logging.exception(_e)
                raise PLSQLNormalizationError("Non-ASCII characters found in possible object name: %s" % _to_append)

            if not self._object_name:
                self._object_name = _to_append
            else:
                self._object_name = ''.join([self._object_name, _to_append])

    def _filter_content(self, line):
        """
        Do line transfomation upon normalization flags
        :param bytes line: line to transform
        :return bytes: filtered
        """
        if PLSQLNormalizationFlags.comments_only in self._process_flags:
            if self._comment_started:
                return line

            # we have to parse object name and type nevermind
            if self._object_name_append:
                self._append_object_name(line)

            return b""

        if self._comment_started:
            if PLSQLNormalizationFlags.no_comments in self._process_flags:
                return b""

            if all([not self._as_found, not self._wrapped]):
                return b""

            return line

        # Everything is denied before 'create' instance
        if not self._create_found:
            return b""

        # append object name if we found something
        if self._object_name_append:
            self._append_object_name(line)

        # if we have an object name - return 'as is', with a quotes drop
        if self._object_name_started:
            if PLSQLNormalizationFlags.uppercase in self._process_flags or \
                    (self._create_found and not self._as_found):
                line = line.upper()

            if self._object_name_remove_quotes:
                line = re.sub(b'"', b'', line)

            return line

        # if we have a literal - see literal flags
        if self._literal_started:
            if PLSQLNormalizationFlags.no_literals in self._process_flags:
                return b''
            else:
                return line

        # strip leading spaces 'create' word 
        if line.lstrip().upper().startswith(b'CREATE'):
            line = line.lstrip()

        # everything before "as" (or "wrapped") should be uppercased unconditionally and aligned in one long line

        if PLSQLNormalizationFlags.uppercase in self._process_flags or \
                (self._create_found and not self._as_found):
            line = line.upper()

        if PLSQLNormalizationFlags.no_spaces in self._process_flags or \
                (self._create_found and not self._as_found):
            line = self._re_any_space.sub(b' ', line)

        return line

    def _normalize_line(self, line):
        """
        Normalizes the 'line' by-literals.
        :param bytes line: line to process
        :return: normalized 'line', possible empty
        """
        if not line:
            return b''

        line = self._re_win_nl.sub(b'', line)
        _result = b""

        if self._wrapped:
            # we only have to check if 'create' or 'wrapped' word comes in the line
            if self._search_declaration_regx(line):
                raise PLSQLNormalizationError("Wrong wrapped content: '%s'" % line.strip())

            if PLSQLNormalizationFlags.comments_only in self._process_flags:
                return b''

            return line

        # if anything is stareted:
        # we have to search for the end, split line and process it separately after changin flags
        if self._anything_started:
            _match = self._re_endobj.search(line)

            if not _match:
                return self._filter_content(line)

            _line_before = self._filter_content(line[:_match.start()])
            _joining = line[_match.start():_match.end()]
            _joining_orig = _joining
            _line_after = line[_match.end():]
            _context = self._parsecontext

            if _context not in ["literal"] or PLSQLNormalizationFlags.comments_only in self._process_flags:
                _joining = self._filter_content(_joining)

            self._reset_parse_flags()

            if _context == "comment":
                if (PLSQLNormalizationFlags.no_comments in self._process_flags or not self._as_found) \
                    and _joining_orig.endswith(b'\n'):
                        # we have to add extra space or newline if we remove a comment which ends with newline
                        _line_after = b'\n' + _line_after

                if PLSQLNormalizationFlags.comments_only in self._process_flags \
                    and not _joining.endswith(b'\n'):
                        # we have to start all comments with newline character, add it forcibly if  comment is ended
                        _joining += b"\n"

            elif _context == "object_name":
                # object_name_append is dropped in _filter_content
                if self._object_name_remove_quotes:
                    self._object_name_remove_quotes = False

            _line_after = self._normalize_line(_line_after)
            return self._join_line(_line_before, _joining, _line_after, _context, False)

        # nothing is started, so context is a combination of flags
        # create_found = False - pre-create normalization
        # create_found = True but as_found = False and not _wrapped - parsing object declaration
        # create_found and as_found - parsing body

        # first see regexp and split a line upon it
        _matchdict = self._search_combine_regex(line)

        if not _matchdict:
            # try to parse object name if it is not parset yet, but it is time to do so
            if self._object_type and not self._object_name and line.strip():
                # this case we have to append first word from a line as object name
                try:
                    self._object_name = list(self._re_any_space.split(line.strip().upper())).pop(0).decode("utf-8")
                except UnicodeDecodeError as _e:
                    logging.exception(_e)
                    raise PLSQLNormalizationError("Non-ASCII characters found in possible object name: %s" % (
                        list(self._re_any_space.split(line.strip().upper())).pop(0)))

            return self._filter_content(line)

        _match = _matchdict.get("match")
        _context = _matchdict.get("context")
        _line_before = self._filter_content(line[:_match.start()])
        _joining = line[_match.start():_match.end()]
        _line_after = line[_match.end():]
        self._re_endobj = _matchdict.get("end")

        logging.log(1, "%s,%s,%s,%s" % (_line_before, _joining, _line_after, _context))

        if _line_before \
            and self._object_type \
            and not self._object_name:
                # append object name with the first word from _line_before
                self._object_name = list(self._re_any_space.split(_line_before.strip().upper())).pop(0).decode("utf-8")

        # first check for contexts allowed in all parts
        if _context == "comment":
            self._comment_started = True

            if PLSQLNormalizationFlags.comments_only in self._process_flags:
                # this case we have to remove spaces before comment sign
                _joining = _joining.lstrip()

        elif _context == "object_name":
            self._object_name_started = True

            # additional actions if we are parsing "create or replace" definitions
            if self._create_found and not self._as_found:
                # additional actions for object name
                # 1. append to 'self._object_name'
                self._object_name_append = True
                # 1. if there is a finish of object name and no spaces inside and 
                _end_object_name = self._re_endobj.search(_line_after)

                if _end_object_name and not re.search(b'[^\w]', _line_after[:_end_object_name.start()]):
                    # only ASCII printable characters are used - we can remove quotes safely
                    self._object_name_remove_quotes = True

        elif _context == "literal":
            self._literal_started = True

        elif not self._create_found:
            # parsing a declaration
            # process comments only and wait for 'create' instance outside comment

            # we have to ignore anything but comment and 'create' outside it
            # any other cases shoud be ignored
            
            if _context == "create":
                # append line with 'create' and continue
                self._create_found = True

        elif not self._as_found:
            # waiting for 'as/is' or 'wrapped' lexeme - parse object type and name
            # we can found 'or' 'replace' lexemes
            # that is: here we do parsing an object declaration

            if _context == "or":
                self._or_found = True
            elif _context == "replace":
                if not self._or_found:
                    raise PLSQLNormalizationError("Wrong syntax: 'replace' found before 'or'")
                self._replace_found = True
            elif _context == "object_type":
                _joining = _joining.upper()

                if not self._object_type:
                    self._object_type = _joining.strip().decode('utf-8')
                elif _joining.strip() == b'BODY' and self._object_type == 'PACKAGE':
                    self._object_type = " ".join([self._object_type, _joining.strip().decode('utf-8')])
                else:
                    raise PLSQLNormalizationError("Unsupported object type: '%s'" % (" ".join([self._object_type, _joining.strip().decode('utf-8')])))
            elif _context in ["as", "wrapped"] :
                if not self._object_type:
                    raise PLSQLNormalizationError("Keyword '%s' found in declaration but object type is not deteced (or is not supported)" % \
                            _joining.strip().decode("utf-8"))

                if not self._object_name:
                    raise PLSQLNormalizationError("Keyword '%s' found in declaration but object name is not parsed" 
                            % _joining.strip().decode("utf-8"))

                _joining = _joining.upper()

                if _context == "as":
                    self._as_found = True
                elif _context == "wrapped":
                    self._wrapped = True
            elif _context == "create":
                raise PLSQLNormalizationError("Keyword 'create' is duplicated in object definition")

        else:
            # parsing a body
            # 'create', 'replace', 'wrapped' is forbidden inside
            if _context in ["create", "replace", "wrapped"]:
                raise PLSQLNormalizationError("'%s' keyword inside an object body" % _context)

        if _context not in ["literal"] or PLSQLNormalizationFlags.comments_only in self._process_flags:
            _joining = self._filter_content(_joining)
        
        logging.log(1, "%s,%s,%s,%s" % (_line_before, _joining, _line_after, _context))
        _line_after = self._normalize_line(_line_after)
        return self._join_line(_line_before, _joining, _line_after, _context, True)


    def normalize_path(self, path, flags=None, lines=None, write_to=None):
        """
        Normalize file resided on 'path'
        :param list flags: process flags, list where two options may be specified, see 'process flags' above
        :param int lines: number of lines to normalize
        :param str write_to: path to a file for output, or file-like object
        :return bytes: normalized 'fl' ir 'write_to' is omitted,  None otherwise.
        """
        if not isinstance(path, str):
            raise TypeError("Path should be a string, not '%s'" % type(path))

        _result = None

        with open(path, mode='rb') as _fl:
            _result = self.normalize(_fl, flags=flags, lines=lines, write_to=write_to)

        return _result

    def normalize(self, fl, flags=None, lines=None, write_to=None):
        """
        Does normalization of 'fl'.
        :param file fl: str or bytes, or file-like object to normalize, have to be opened in binary mode
        :param list flags: process flags, list where two options may be specified, see 'process flags' above
        :param int lines: number of lines to normalize
        :param write_to: file to write result to
        :return bytes: normalized 'fl' ir 'write_to' is omitted, 'None' otherwise.
        """

        self._reset()

        if isinstance(flags, list):
            self._process_flags = flags

        self._check_flags()

        # check if we have file-like object as input
        # create temporary one if not
        _fl = None

        if isinstance(fl, str):
            fl = fl.encode('utf-8')

        if isinstance(fl, bytes):
            _fl = tempfile.NamedTemporaryFile(suffix='.sql', mode='w+b')
            _fl.write(fl)
            fl = _fl

        # check 'write_to' and create temporary output if omitted
        _write_to = None

        if not write_to:
            logging.debug("write_to is empty, creating temporary buffer...")
            _write_to = tempfile.NamedTemporaryFile(suffix='.sql')
        elif isinstance(write_to, str):
            _write_to = open(write_to, mode='w+b')
        else:
            logging.debug("Assuming 'write_to' is a real file-like object with valid 'name' attribute")
            _write_to = write_to

        # read normalization input line-by-line
        _pos = fl.tell()
        fl.seek(0, os.SEEK_SET)
        _write_to.seek(0, os.SEEK_SET)
        _lines = 0

        # add slash is set by default, but will be dropped if line ends with space
        # we do not need trailing slash if we print comments only
        _add_slash = PLSQLNormalizationFlags.comments_only not in self._process_flags
        _end_space = True

        while True:
            _line = fl.readline()

            if not _line:
                # end of file
                break

            # we have to join lines upon flags set BEFORE normalization since after those flags will be changed
            _as_found = self._as_found
            _wrapped = self._wrapped
            _anything_started = self._anything_started
            logging.log(1, _line)
            _normalized = self._normalize_line(_line)

            # join lines upon normalization flags
            # if we have not to replace many spaces with one
            # then join lines 'as_is'
            # otherwise add a space if previous line does not end with it
            # and new line does not start with space
            if (PLSQLNormalizationFlags.no_spaces in self._process_flags or all([not _as_found, not _wrapped])):
                if not _end_space \
                        and not _anything_started \
                        and not self._re_start_space.search(_normalized):
                    _write_to.write(b" ")
                elif _end_space \
                        and self._re_start_space.search(_normalized):
                    _normalized = _normalized.lstrip()

            logging.log(1, _normalized)
            _write_to.write(_normalized)

            _lines += 1

            if lines and _lines >= lines:
                logging.debug("Normalized first '%d' lines, limit is '%d'")
                _add_slash = False
                break

            # we need last _normalized to see if we have to add slash at the end
            if PLSQLNormalizationFlags.comments_only not in self._process_flags and _normalized.strip():
                _add_slash = not self._re_add_slash.search(_normalized)

            if (PLSQLNormalizationFlags.no_spaces in self._process_flags or all([not _wrapped, not _as_found])) \
                    and not _anything_started \
                    and _normalized:
                # this case we have to join lines 'as_is'
                # but do nod add extra spaces if _normalized is "empty"
                if _normalized.strip():
                    _end_space = self._re_end_space.search(_normalized)
            else:
                _end_space = True

        if _add_slash:
            if PLSQLNormalizationFlags.no_spaces not in self._process_flags:
                _write_to.write(b"\n\n/")
            else:
                _write_to.write(b" /")

        if _fl:
            # we did temporary file for reading
            _fl.close()
        else:
            fl.seek(_pos, os.SEEK_SET)

        # returning result basing on 'write_to' arg
        _result = None
        if not write_to:
            _write_to.seek(0, os.SEEK_SET)
            _result = _write_to.read()
            _write_to.close()
        elif isinstance(write_to, str):
            _write_to.close()
        else:
            _write_to.seek(0, os.SEEK_END)

        # additional check if normalization was successful
        if not self._object_type:
            raise PLSQLNormalizationError("Object type not parsed.")

        if not self._object_name:
            raise PLSQLNormalizationError("Object name not parsed.")

        return _result

    def is_sql_path(self, path):
        """
        Check if file under 'path' is our PL/SQL code or not
        :param str path: path to a file
        :return boolean: is our regular PL/SQL or not
        """
        _result = False

        with open(path, mode='rb') as _fl:
            _result = self.is_sql(_fl)

        return _result

    def is_sql(self, fl):
        """
        Our internal criteria to check is file PL/SQL or not.
        After normalization first phrase is to be like CREATE (or replace) (object)...
        :param file fl: line (str or bytes) to check, or file-like object to analyse
        :return: boolean
        """
        self._is_props_g(fl)
        return self._create_found and bool(self._object_type) and bool(self._object_name)

    def _is_props_g(self, fl):
        """
        General part of 'is_sql', 'is_wrapped', 'is_wrappable' methods
        """
        # create temporary file for normalization output
        _tmp = tempfile.NamedTemporaryFile(suffix='.tmpsql', mode='w+b')
        try:
            self.normalize(fl, self._fl_full() + [PLSQLNormalizationFlags.no_literals], write_to=_tmp)
        except (PLSQLNormalizationError, RecursionError) as _e:
            # we do not need log these exceptions as exceptions - it is OK for all use cases
            logging.debug(_e, exc_info=True)
            self._reset()

        _tmp.close()

    def is_wrapped_path(self, path):
        """
        Check if a file on given path is wrapped or not
        :param str path: path to a file
        :return boolean: is wrapped or not
        """
        if not isinstance(path, str):
            raise TypeError("Path should be a string, not '%s'" % type(path))

        _result = False

        with open(path, mode='rb') as _fl:
            _result = self.is_wrapped(_fl)

        return _result

    def is_wrapped(self, fl):
        """
        Check file content for really wrapped stuff
        :param file fl: string or bytes to check, or file-like object to check content for,
                        should be opened in BINARY read or read-write mode
        :return boolean: is content 'fl' wrapped or not
        """
        self._is_props_g(fl)
        return  self._create_found and \
                bool(self._object_type) and \
                bool(self._object_name) and \
                self._wrapped


    def is_wrappable_path(self, path):
        """
        Check if file resided under 'path' may be wrapped or not
        :param str path: path to a file
        :return boolean: may be wrapped or not
        """
        if not isinstance(path, str):
            raise TypeError("Path should be a string, not '%s'" % type(path))

        _result = False

        with open(path, mode='rb') as _fl:
            _result = self.is_wrappable(_fl)

        return _result

        
    def is_wrappable(self, fl):
        """
        Check if file or string/bytes given in 'fl' may be wrapped or not
        :param file fl: string or bytes to check, or file-like object to check content for wrappability
        :return boolean: may be wrapped or not
        """
        self._is_props_g(fl)
        # we do not set 'as_found' for non-wrappable objects
        return  self._create_found and \
                bool(self._object_type) and \
                bool(self._object_name) and \
                self._object_type.lower() in ['procedure', 'function', 'package body'] and \
                self._as_found


if __name__ == "__main__":
    # parse command-line arguments and decode file content to another file
    import argparse

    _parser = argparse.ArgumentParser(description='Normalize one PL/SQL file and write result to another.')
    _parser.add_argument("--in", dest="fn_in", help="Input file path", required=True)
    _parser.add_argument("--out", dest="fn_out", help="Output file path", required=True)
    _parser.add_argument("--no-comments", dest="no_comments", help="Strip comments", default=False, action='store_true')
    _parser.add_argument("--no-spaces", dest="no_spaces", help="Replace space chars sequences with single space",
            default=False, action='store_true')
    _parser.add_argument("--uppercase", dest="uppercase", help="Make PL/SQL lexemes uppercase", default=False,
            action='store_true')
    _parser.add_argument("--no-literals", dest="no_literals", help="Strip literals content", default=False,
            action='store_true')
    _parser.add_argument("--comments-only", dest="comments_only", help="Leave comments only, strip others",
            default=False, action='store_true')
    _parser.add_argument("--full", dest='full', help="The same as --no-comments --no-spaces --uppercase",
            default=False, action='store_true')
    _parser.add_argument("--log-level", dest="log_level", help="Logging level", type=int, default=20)
    _args = _parser.parse_args()

    logging.basicConfig(
            format="%(pathname)s: %(asctime)-15s: %(levelname)s: %(funcName)s: %(lineno)d: %(message)s",
            level=_args.log_level)

    _fn_in = os.path.abspath(_args.fn_in)
    _fn_out = os.path.abspath(_args.fn_out)
    logging.info("Input file: '%s'" % _fn_in)
    logging.info("Output file: '%s'" % _fn_out)

    # preparing flags
    _flags = list()

    if _args.full:
        _args.no_comments = True
        _args.no_spaces = True
        _args.uppercase = True

    logging.debug("Preparing normalization flags...")

    for _flag in PLSQLNormalizationFlags.__dict__.keys():
        if _flag.startswith("_"):
            continue

        if not hasattr(_args, _flag):
            continue

        logging.debug("Checking normalization flag '%s'" % _flag)

        if getattr(_args, _flag):
            _flags.append(getattr(PLSQLNormalizationFlags, _flag))

    if _flags:
        logging.info("Normalization flags: %s" % ",".join(list(map(lambda x: str(x), _flags))))
    else:
        logging.info("No normalization flags set")

    PLSQLNormalizer().normalize_path(_fn_in, write_to=_fn_out, flags=_flags)
    logging.info("Done")
