Command Line Tool assisting in rendering DocBook/AsciiDoc
=========================================================

Frameworks/Libraries Used
-------------------------

Source:

* Click [http://click.pocoo.org/3/](http://click.pocoo.org/3/)
* GitPython [https://gitpython.readthedocs.io/en/stable/](https://gitpython.readthedocs.io/en/stable/)
* lxml [http://lxml.de/](http://lxml.de/)
* python-num2words [https://pypi.python.org/pypi/num2words/](https://pypi.python.org/pypi/num2words/)
* python-progress [https://pypi.python.org/pypi/progress/](https://pypi.python.org/pypi/progress/)
* python-requests [http://docs.python-requests.org/en/latest/](http://docs.python-requests.org/en/latest/)

Testing:

* PyTest [http://pytest.org/latest/](http://pytest.org/latest/)

External Tools used
-------------------

* Publican [https://fedorahosted.org/publican/](https://fedorahosted.org/publican/)
* AsciiDoctor [http://asciidoctor.org/](http://asciidoctor.org/)
  * AsciiDoctor Diagram [http://asciidoctor.org/docs/asciidoctor-diagram/](http://asciidoctor.org/docs/asciidoctor-diagram/)

Source Structure
----------------

The source is broken up into the following structure:

    |- aura
        |- commands       - Contains a set of modules that represent the sub commands for the app. They are loaded by the cli dynamically,
                            to allow for additional commands to easily be plugged in.
            |- base.py    - Contains the base functionality for all commands.
            ...
        |- transformers   - Contains a set of modules that do the core work of transforming source content to different formats. Each
                            module should be responsible for transforming only one source format.
            |- base.py    - Contains the interface that all transformers should implement.
            ...
        |- __init__.py
        |- cli.py         - Is the main entry point and contains the root cli command.
        |- compat.py      - Contains functions to make aura compatible across different OS's.
        |- exceptions.py  - Contains any custom exceptions for the app.
        |- utils.py       - Contains utility functions that can be used throughout the app.
    |- specs              - Contains rpm spec files for dependencies that aren't available in normal repositories.
        ...
    |- tests              - Contains all the tests for the app. These tests are currently configured to use pytest
        |- base.py        - Contains the base test functionality, that can be used in all tests.
        |- conftest.py    - Contains pytest fixtures that are to be shared between different tests.
        ...
    |- setup.py
    |- aura.spec          - A RPM spec file, that can be used to build a distributable rpm.
    |- aura.bash          - A bash completion script for the app.
    |- aura.conf          - An example of the configuration file for the app.

Running aura for development
----------------------------
Run the following command from the root of the aura repository:

    pip install -e ./

This will install aura locally and any code changes will be reflected instantly when running the command.

To uninstall:

    pip uninstall aura

Adding new built-in commands
----------------------------

To add a new command, you need to create a module in aura/commands/, that is named "cmd_`<command_name>`". The other requirement is that
there must be a `cli` function that is annotated with `click.command` (see below for an example). The `cli` function will then be used as the
entry point for executing the commands functionality.

Example:

    import click


    @click.command('name', short_help='Help text that shows in the root command help')
    def cli():
        """Expanded help text that is displayed for this commands help"""
        ...

Adding new commands via a plugin
--------------------------------

New commands can be added as plugins by using setup tool entry points: [http://setuptools.readthedocs.io/en/latest/setuptools.html#dynamic-discovery-of-services-and-plugins](http://setuptools.readthedocs.io/en/latest/setuptools.html#dynamic-discovery-of-services-and-plugins).

To create a new command, create a new function that is annotated with `click.command` (see above for an example) in a separate plugin package/module. Then in your setup.py configuration register an `aura.commands` entry point for your new command (see below for an example).

Example:

    entry_points={
        'aura.commands': [
            'delete = plugin_package.commands.cmd_delete:cli',
            'list = plugin_package.commands.cmd_list:cli'
        ],
    }

Testing
-------

Tests are setup to run using pytest. To execute the tests, run the following from the root source directory.

    python setup.py test

This will run through all the test in the `tests` directory.

Note: Tests can also be run using `py.test --capture=no tests/`
