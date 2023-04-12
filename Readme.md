# PL/SQL helpers classes

Tools for auto-processing and formatting PL/SQL code

## Limitations

- Multi-object files are **not** supported. This means: one file - one object with `create` statement. Result of processing multi-object files is unpredictable, so all tools (except *str\_decoder*) will raise an exception.
- *Object names* must be given using *ASCII* characters only.
- Using for non-supported object definitions will raise an exception too. Supported object types are:
    - *PROCEDURE*
    - *FUNCTION*
    - *PACKAGE*
    - *PACKAGE BODY*

## Details

### str\_decoder

The only function **decode_to_str** tries to detect line encoding and re-code it to `UTF-8`.
Raises **ValueError** if encoding is impossible.

#### Synopsis

`decode_to_str(line, probables=None)`

- `line` - `bytes` object with a text to decode
- `probables` - `list` of `str` with primary encodings to check. Default: `['cp866', 'cp1251', 'koi8-r']`
- *return value* - `str` (decoded and re-encoded to `UTF-8`)

#### Command-line usage

Decoding whole file to another file.
Run this to get list of arguments:

`python -m oc_sql_helpers.str_decoder --help`

### wrapper

`PLSQLWrapper` class is a tool to work with Oracle-wrapped sources.

#### Requirements

There are additional requirements to *wrap* files. Note that *unwrap* methods are working without it. These are due to usage of original `wrap` utility from *Oracle* **which is not included to this package due to license violation**. You have to install it separately.

- `ORACLE_HOME` environment variable is to be set correctly
- `wrap` binary is to be placed under `${ORACLE_HOME}/bin` and must have *execute* permission for effective user

#### Synopsis

`PLSQLWrapper()` - to instantiate an object for that class

**Methods**

-   `wrap_path(path_in, write_to=None)`
    - `path_in` - `str` object with absolute or relative path to file to wrap.
    - `write_to` - one of:
        - `None` - the wrapping result will be returned by this method as `bytes` object
        - `file` - result will be written to the file-like object specified here. **Must** be opened in read-write binary mode (`'w+b'`) and support `seek` operation.
        - `str`  - path to output file, absolute or relative. Result will be written there. **Must** have an extension - this is Oracle `wrap` utility featrue. It appends `.plb` suffix on its own if an extension omitted. **Please specify the extension always**
    - *return value*: see `write_to` above
-   `wrap_buf(fl_in, write_to=None)`
    - `fl_in` - `file` or `file-like` object to wrap data from. *Must* be opened in binary mode and support `seek` operation (`'rb'`).
    - `write_to` - the same as for `wrap_path`
    - *return value*: the same as for `wrap_path`
-   `unwrap_path(path_in, write_to=None)`
    - `path_in` - `str` object with absolute or relative path to file to unwrap.
    - `write_to` - one of:
        - `None` - the unwrapping result will be returned by this method as `bytes` object
        - `file` - result will be written to the file-like object specified here. **Must** be opened in read-write binary mode (`'w+b'`) and support `seek` operation.
        - `str`  - path to output file, absolute or relative. Result will be written there.
    - *return value*: see `write_to` above
-   `unwrap_buf(fl_in, write_to=None)`
    - `fl_in` - `file` or `file-like` object to wrap data from. *Must* be opened in binary mode and support `seek` operation (`'rb'`).
    - `write_to` - the same as for `unwrap_path`
    - *return value*: the same as for `unwrap_path`

#### Command-line usage

Wrapping/unwrapping whole file to another file.
Run this to get list of arguments:

`python -m oc_sql_helpers.wrapper --help`

### normalizer

`PLSQLNormalizer` class is or PL/SQL code *normalization*.

#### The Normalization Term
**Normalization** means *almost* the same as **code style** does, but less strictly. This means normalization result may be unusable even if source is correct one from *PL/SQL* point of view.

*Default normalization* is:

- All line endings are replaced to *unix*-style
- All trash before first uncommented `CREATE` statement is removed.
- `CREATE` statement itself is ordered to the first line up to `AS` (or `IS`, or `WRAPPED`) token, including object name, type and schema. Extra space characters and comments are replaced with single space.
- First line (with ordered `CREATE` statement) is *UPPRCASED*, including *schema* and *object* name.
- If *schema* or *object* name is given in double-quotes `"` then those double-quotes will be removed where possible. Example: `"schema"."name"` will be `SCHEMA.NAME` after normalization, while `"another.schema"."another.name"` will have the doble quotes: `"ANOTHER.SCHEMA"."ANOTHER.NAME"`
- rest part of object definition body will not be changed

*Another normalization flags*:

- `uppercase`: all language lexemes in object body will be uppercased except literals
- `no-comments`: all comments inside the body, including comment signs themselves, will be replaced with single space.
- `no-spaces`: all repeating space-characters (space itself, newline, tabulation...) will be replaced with general single space. Example: `var   :=     'the  value'` will be translated to `var := 'the  value'`. Note that no replacement is done inside a literal `'the  value'`. **This flag may not be used witout `no-comments`**
- `no-literals`: all string literal values will be replaced to empty ones. Literal signs themselves are not changed.
- `comments-only`: Discard the whole file content but comments, including comment signs themselves. Each comment will be started with a new line. **This flag is not compatible with anyone above**

#### Synopsis

`PLSQLNormalizer()` - to instantiate an object for this class

**Methods**

-   `normalize_path(path, flags=None, lines=None, write_to=None)`
    - `path`  - `str` object with absolute or relative path to file to normalize.
    - `flags` - normalization flags, `list` of integers from `PLSQLNormalizationFlags` enumeration, see below. `None` value means do *default* (`CREATE` definition) normalization only.
    - `lines` - `int`, limit normalization lines (counted from *source*). **Default**: `None`, means normalize whole source
    - `write_to` - one of:
        - `None` - the wrapping result will be returned by this method as `bytes` object
        - `file` - result will be written to the file-like object specified here. **Must** be opened in read-write binary mode (`'w+b'`) and support `seek` operation.
        - `str`  - path to output file, absolute or relative. Result will be written there. **Must** have an extension - this is Oracle `wrap` utility featrue. It appends `.plb` suffix on its own if an extension omitted. **Please specify the extension always**
    - *return value*: see `write_to` above
-   `normalize(fl, flags, lines=None write_to=None)`
    - `fl` - one of:
        - `file` or `file-like` object to normalize data from. *Must* be opened in binary mode and support `seek` operation (`'rb'`).
        - `str` - string data to normalize
        - `bytes` - "binary" data to normalize
    - `flags` - the same as for `normalize_path`
    - `lines` - the same as for `normalize_path`
    - `write_to` - the same as for `normalize_path`
    - *return value*: the same as for `normalize_path`
-   `is_sql(fl)` - check the data given is supported *PL/SQL* code
    - `fl` - the same as for `normalize`
    - *retun value* - `bool`, wrapped *PL/SQL* code or not
-   `is_sql_path(path)` - the same as `is_sql` but argument is treated as a path to a file with possible code
-   `is_wrapped(fl)` - check the data given is supported wrapped *PL/SQL* code
    - `fl` - the same as for `normalize`
    - *retun value* - `bool`, supported *PL/SQL* code or not
-   `is_wrapped_path(path)` - the same as `is_wrapped` but argument is treated as a path to a file with possible code
-   `is_wrappable(fl)` - check the data given is supported wrapped *PL/SQL* code
    - `fl` - the same as for `normalize`
    - *retun value* - `bool`, wrappable *PL/SQL* object in the code or not
-   `is_wrappable_path(path)` - the same as `is_wrappable` but argument is treated as a path to a file with possible code

`PLSQLNormalizationFlags` - enumeration of flags:

- `uppercase`
- `no_comments`
- `no_spaces`
- `no_literals`
- `comments_only`

See detailed description above in *Another normalization flags* chapter from *The Normalization Term* section.

#### Command-line usage

Normalizing whole file to another file.
Run this to get list of arguments:

`python -m oc_sql_helpers.normalizer --help`
