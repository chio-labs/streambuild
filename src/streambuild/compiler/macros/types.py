"""Types for authored Python SQL macros."""

from collections.abc import Callable

type MacroFunction = Callable[..., object]
