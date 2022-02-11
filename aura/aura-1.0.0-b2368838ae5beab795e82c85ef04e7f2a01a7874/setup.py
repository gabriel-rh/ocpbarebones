from distutils.dir_util import remove_tree
from distutils import log
from setuptools import Command, setup, find_packages
from setuptools.command.test import test as TestCommand
import os
import re
import shlex
import sys


class Tox(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import tox
        errcode = tox.cmdline(self.test_args)
        sys.exit(errcode)


# See http://doc.pytest.org/en/latest/goodpractices.html#manual-integration
# We use the manual method here, because the test runner isn't available on RHEL
class PyTest(TestCommand):
    user_options = [('addopts=', None, "Additional options to be passed verbatim to the "
                                       "pytest runner"),
                    ('no-cov', None, "Don't print coverage reports")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.addopts = None
        self.no_cov = False

    def finalize_options(self):
        TestCommand.finalize_options(self)
        if self.addopts:
            self.addopts = shlex.split(self.addopts)
        else:
            self.addopts = []
        if not self.no_cov:
            self.addopts.extend(["--cov", "aura",
                                 "--cov-report", "html",
                                 "--cov-report", "xml",
                                 "--junitxml", "junit.xml"])
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import pytest
        errcode = pytest.main(self.addopts)
        sys.exit(errcode)


class Clean(Command):
    description = "Custom clean command that forcefully removes dist/build directories"
    user_options = [
        ("tests", "t", "remove all test output"),
        ("all", "a", "remove all build and test output, not just temporary by-products")
    ]

    boolean_options = ["tests", "all"]

    def initialize_options(self):
        self.cwd = None
        self.tests = False
        self.all = False

    def finalize_options(self):
        assert not (self.all and self.tests), 'Cannot use --tests and --all at the same time.'
        self.cwd = os.getcwd()

    def run(self):
        assert os.getcwd() == self.cwd, 'Must be in package root: %s' % self.cwd

        directories = []
        if not self.tests:
            directories.extend(["build", "dist", "aura.egg-info"])

        if self.all or self.tests:
            directories.extend(["htmlcov", ".tox"])

            # Remove junit and coverage test reports
            for f in os.listdir(self.cwd):
                if re.match("^junit.*\.xml$", f) or re.match("^coverage.*\.xml$", f):
                    log.info("removing '%s'", f)
                    if not self.dry_run:
                        os.remove(os.path.join(self.cwd, f))

        # remove the directories
        for directory in directories:
            if os.path.exists(directory):
                remove_tree(directory, dry_run=self.dry_run)
            else:
                log.warn("'%s' does not exist -- can't clean it", directory)


# Load the version
exec(open('aura/version.py').read())
setup(
    name='aura',
    version=__version__,
    description='Command line tool for compiling various source formats',
    author='CCS Tools',
    author_email='cp-docs@redhat.com',
    url='',
    download_url='',
    platforms='Cross platform (Linux, Mac OSX, Windows)',
    keywords=[''],
    packages=find_packages(),
    install_requires=['Click',
                      'requests',
                      'lxml >= 3.0',
                      'numpy',
                      'Pillow',
                      'num2words',
                      'GitPython'],
    entry_points={
        'console_scripts': [
            'aura = aura.cli:cli'
        ]
    },
    data_files=[('etc/bash_completion.d', ['aura.bash']),
                ('etc/aura', ['aura.conf'])],
    tests_require=['mock',
                   'pytest-cov',
                   'pytest'],
    cmdclass={'clean': Clean,
              'test': PyTest,
              'tox': Tox},
)
