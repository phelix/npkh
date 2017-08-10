# -*- coding: utf-8 -*-
"""
MIT license

Screen and file logger. Supports print() style arguments and encoded strings.

"""

import os

def ensure_dirs(path):
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise

from logging import *

def join_args_unicode(*args):
    """Join arguments as unicode string representations."""
    args2 = []
    for arg in args:
        try:
            arg = unicode(arg)
        except UnicodeDecodeError:
            try:
                arg = arg.decode("utf-8")
            except UnicodeDecodeError:
                arg = arg.decode("cp1252")
        args2.append(arg)
    return " ".join(args2)

class MyLogger(Logger):
    """Modified logging class to be able to digest several arguments similar to print().
Also support encoded strings."""
    def _log(self, level, msg, args, **kwargs):
        msg = join_args_unicode(*((msg,) + args))
        args = ()
        Logger._log(self, level, msg, args, **kwargs)
setLoggerClass(MyLogger)

def get_my_logger(name=None, levelConsole=INFO, filename=None, levelFile=DEBUG, clear=False):
    """Logger logging to both screen and file as configured."""
    # create formatter
    formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger = getLogger(name)
    logger.setLevel(DEBUG)  # set max Level to output

    ch = StreamHandler()
    ch.setLevel(levelConsole)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    if filename:
        ensure_dirs(os.path.dirname(filename))
        fh = FileHandler(filename, mode='w' if clear else 'a')
        fh.setLevel(levelFile)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger

if __name__ == "__main__":
    log = get_my_logger("test", levelConsole=DEBUG, filename="./logtest\\t/test.txt", clear=True)
    log.info("test", 1)
    log.debug("teeeesüst2", u"teäst2b")
    try:
        1/0
    except:
        log.debug("zomb", exc_info=True)
