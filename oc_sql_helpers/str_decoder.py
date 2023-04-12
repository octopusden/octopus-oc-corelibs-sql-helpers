#!/usr/bin/env python3

import chardet
import re


def decode_to_str(line, probables=None):
    """
    for Python 3 specially: force str_line object to be decoded to string if it is bytes-like object
    :param bytes line: string to decode but currently bytest
    :param list porbables: list of most probable encodings to check for if auto-detect fails
    :return str: (or None, exception will be thrown if unable to decode)
    """

    if isinstance(line, str):
        # no decoding needed
        return line

    if not probables:
        probables = ['utf-8', 'cp866', 'cp1251', 'koi8-r']

    _enc = chardet.detect(line)
    _result = None

    if _enc.get('encoding'):
        try:
            _result = line.decode(_enc.get('encoding'))
        except:
            _result = None
            pass

    # empty line is falsy, but it is possible, so checking 'None' exactly
    if _result is not None:
        return _result

    # now try to decode a line with pre-defined list of most probable encodings
    for _enc in probables:
        try:
            _result = line.decode(_enc)
        except:
            _result = None
            pass

        if _result is not None:
            break

    if _result is None:
        raise ValueError("Unable to decode: encoding is not detected or not supported")

    return _result


if __name__ == "__main__":
    # parse command-line arguments and decode file content to another file
    import argparse
    import os
    import logging

    _parser = argparse.ArgumentParser(description='Try to decode a text file to Unicode and save to another file.')
    _parser.add_argument("--in", dest="fn_in", help="Input file path", required=True)
    _parser.add_argument("--out", dest="fn_out", help="Output file path", required=True)
    _parser.add_argument("--probables", dest="probables", default="", type=str,
        help="Comma-separated list of possbile encodings to try")
    _parser.add_argument("--log-level", dest="log_level", help="Logging level", type=int, default=20)
    _args = _parser.parse_args()

    logging.basicConfig(
            format="%(pathname)s: %(asctime)-15s: %(levelname)s: %(funcName)s: %(lineno)d: %(message)s",
            level=_args.log_level)

    _fn_in = os.path.abspath(_args.fn_in)
    _fn_out = os.path.abspath(_args.fn_out)
    logging.info("Input file: '%s'" % _fn_in)
    logging.info("Output file: '%s'" % _fn_out)
    _probables = _args.probables.split(",")

    if _probables:
        _probables = list(map(lambda x: x.strip().lower(), _probables))
        logging.debug("Encodings to check: %s" % ",".join(_probables))
    
    with open(_fn_in, mode="rb") as _fl_in:
        with open(_fn_out, mode="wt") as _fl_out:
            _fl_out.write(decode_to_str(_fl_in.read(), probables=_probables))

