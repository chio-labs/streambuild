"""Read and confirm an operator-supplied password."""

import getpass
import sys

from streambuild.cli.entry.exceptions import CliUserError


def read_password() -> str:
    """Read one password from a pipe or interactive terminal."""

    if not sys.stdin.isatty():
        password: str = sys.stdin.readline().rstrip("\n")
        if not password:
            raise CliUserError("Password input was empty")
        return password
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        raise CliUserError("Passwords do not match")
    return password
