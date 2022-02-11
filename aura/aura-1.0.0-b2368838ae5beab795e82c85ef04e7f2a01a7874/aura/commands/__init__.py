import inspect

import click

from .base import BaseCommand, BaseXMLFeedCommand


def hidden_option(*param_decls, **attrs):
    """Attaches an option to the command.  All positional arguments are
    passed as parameter declarations to :class:`Option`; all keyword
    arguments are forwarded unchanged.  This is equivalent to creating an
    :class:`Option` instance manually and attaching it to the
    :attr:`Command.params` list.
    """
    def decorator(f):
        if 'help' in attrs:
            attrs['help'] = inspect.cleandoc(attrs['help'])
        click.decorators._param_memo(f, HiddenOption(param_decls, **attrs))
        return f
    return decorator


def normalize_lang(ctx, param, value):
    if value is not None:
        return value.replace("_", "-")
    return value


class HiddenOption(click.Option):
    def get_help_record(self, ctx):
        pass
