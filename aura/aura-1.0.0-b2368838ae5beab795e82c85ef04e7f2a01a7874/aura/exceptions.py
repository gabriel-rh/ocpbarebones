class InvalidInputException(Exception):
    """The user entered some invalid input"""


class UnknownAPIException(Exception):
    """Thrown when an API that isn't available is trying to be loaded."""

    def __init__(self, name):
        message = "The API \"" + name + "\" is not an available API."
        super(UnknownAPIException, self).__init__(message)


class UnknownSourceFormatException(Exception):
    """Thrown when a transformer cannot be loaded for the specified source format."""

    def __init__(self, name):
        message = "No transformer can be found for the  \"" + name + "\" source format."
        super(UnknownSourceFormatException, self).__init__(message)
