"""Constants for authored Python SQL macros."""

PYTHON_LITERAL_NAMES: frozenset[str] = frozenset({"True", "False", "None"})

OPEN_PAREN: str = "("
UNDERSCORE: str = "_"

MACRO_SIGIL: str = "@"
MACRO_CALL_SIGIL: str = "@"
MACRO_CONTEXT_PARAMETER_NAME: str = "ctx"
MACRO_CONTEXT_ANNOTATION_NAME: str = "MacroContext"
PIPELINE_NAMING_CONTEXT_ANNOTATION_NAME: str = "PipelineNamingContext"
