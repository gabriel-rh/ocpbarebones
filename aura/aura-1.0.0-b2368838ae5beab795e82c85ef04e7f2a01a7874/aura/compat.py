import logging
import subprocess
import sys
import warnings

_ver = sys.version_info
is_py2 = (_ver[0] == 2)
is_py3 = (_ver[0] == 3)

if is_py2:
    import urllib as urllib
    from urlparse import urljoin, urlparse
    from ConfigParser import ConfigParser, RawConfigParser, SafeConfigParser
    from StringIO import StringIO

    str = str
    unicode = unicode
    basestring = basestring
else:
    import urllib.parse as urllib
    from urllib.parse import urljoin, urlparse
    from configparser import ConfigParser, RawConfigParser, SafeConfigParser
    from io import StringIO

    str = str
    unicode = str
    basestring = str

_warnings_showwarning = None


class NullHandler(logging.Handler):
    def emit(self, record):
        pass


# Warnings backport (see https://hg.python.org/cpython/file/2.7/Lib/logging/__init__.py#l1701)
def _showwarning(message, category, filename, lineno, file=None, line=None):
    """
    Implementation of showwarnings which redirects to logging, which will first
    check to see if the file parameter is None. If a file is specified, it will
    delegate to the original warnings implementation of showwarning. Otherwise,
    it will call warnings.formatwarning and will log the resulting string to a
    warnings logger named "py.warnings" with level logging.WARNING.
    """
    if file is not None:
        if _warnings_showwarning is not None:
            _warnings_showwarning(message, category, filename, lineno, file, line)
    else:
        s = warnings.formatwarning(message, category, filename, lineno, line)
        logger = logging.getLogger("py.warnings")
        if not logger.handlers:
            logger.addHandler(NullHandler())
        logger.warning("%s", s)


def capture_warnings(capture):
    """
    If capture is true, redirect all warnings to the logging package.
    If capture is False, ensure that warnings are not redirected to logging
    but to their original destinations.
    """
    global _warnings_showwarning
    if capture:
        if _warnings_showwarning is None:
            _warnings_showwarning = warnings.showwarning
            warnings.showwarning = _showwarning
    else:
        if _warnings_showwarning is not None:
            warnings.showwarning = _warnings_showwarning
            _warnings_showwarning = None


# subprocess.check_output() backport (see https://gist.github.com/edufelipe/1027906)
def check_output(*popenargs, **kwargs):
    """Run command with arguments and return its output as a byte string.

    Backported from Python 2.7 as it's implemented as pure python on stdlib.

    check_output(['/usr/bin/python', '--version'])
    Python 2.6.2
    """
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
    output, unused_err = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        error = subprocess.CalledProcessError(retcode, cmd)
        error.output = output
        raise error
    return output


def init_git_repo(*args, **kwargs):
    """
    Creates a git Repo object allowing for compatibility issues between GitPython >= 1.0 and GitPython < 1.0
    """
    # Import the git module, so we can query the git repo
    import git

    # Init the repo object
    search_parent_directories = kwargs.pop('search_parent_directories', True)
    try:
        repo = git.Repo(*args, search_parent_directories=search_parent_directories, **kwargs)
    except TypeError:
        # GitPython pre 1.0 searched parent directories by default
        repo = git.Repo(*args, **kwargs)

    return repo
