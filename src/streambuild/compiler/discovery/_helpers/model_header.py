"""Parse SQLBuild-style MODEL header values."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from streambuild.compiler.discovery.constants import KAFKA_RETENTION_KEYS, MODEL_RETENTION_KEYS
from streambuild.compiler.discovery.exceptions import ModelHeaderSyntaxError, RetentionConfigError
from streambuild.compiler.discovery.main._parse_duration_seconds import parse_duration_seconds
from streambuild.compiler.discovery.models import KafkaRetentionPolicy, ModelRetentionPolicy
from streambuild.compiler.discovery.types import RetentionMissingBehavior

_END_TOKEN: str = "end"
_WORD_TOKEN: str = "word"
_STRING_TOKEN: str = "string"
_SYMBOL_TOKEN: str = "symbol"
_SYMBOLS: frozenset[str] = frozenset({"(", ")", "[", "]", ","})
_YAML_MAPPING_SYMBOLS: frozenset[str] = frozenset({"{", "}"})
_OPEN_PAREN: str = "("
_CLOSE_PAREN: str = ")"
_OPEN_BRACKET: str = "["
_CLOSE_BRACKET: str = "]"
_COMMA: str = ","
_KEY_VALUE_SEPARATOR: str = ":"
_QUOTE_NAMES: dict[str, str] = {"'": "single", '"': "double"}
_ESCAPE_CHARACTER: str = "\\"
_TRUE_VALUE: str = "true"
_FALSE_VALUE: str = "false"
_NULL_VALUE: str = "null"
_INTEGER_PATTERN: re.Pattern[str] = re.compile(r"^[+-]?\d+$")
_FLOAT_PATTERN: re.Pattern[str] = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)$")
_COLUMN_NAME_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class _ModelHeaderToken:
    kind: str
    value: str
    position: int


class _ModelHeaderParser:
    def __init__(self, *, header: str) -> None:
        self._tokens: list[_ModelHeaderToken] = _tokenize_model_header(header)
        self._index: int = 0

    def parse(self) -> dict[str, object]:
        if self._peek().kind == _END_TOKEN:
            return {}
        values: dict[str, object] = self._parse_map(end_symbol=None)
        self._expect_end()
        return values

    def _parse_map(self, *, end_symbol: str | None) -> dict[str, object]:
        values: dict[str, object] = {}
        while not self._is_at_end_symbol(end_symbol):
            if self._match_symbol(_COMMA):
                continue
            key: str = self._consume_key()
            if self._match_symbol(_KEY_VALUE_SEPARATOR):
                raise ModelHeaderSyntaxError(
                    f"unexpected ':' after key '{key}'; use SQLBuild syntax '{key} value'"
                )
            if self._is_at_end_symbol(end_symbol) or self._peek().kind == _END_TOKEN:
                raise ModelHeaderSyntaxError(
                    f"unexpected token '{key}' without a value; quote values with spaces"
                )
            values[key] = self._parse_value()
            self._match_symbol(_COMMA)
        if end_symbol is not None:
            self._consume_symbol(end_symbol)
        return values

    def _parse_value(self) -> object:
        token: _ModelHeaderToken = self._peek()
        if token.kind == _STRING_TOKEN:
            self._advance()
            return token.value
        if token.kind == _WORD_TOKEN:
            self._advance()
            if self._peek().kind == _SYMBOL_TOKEN and self._peek().value == _OPEN_PAREN:
                self._advance()
                return {token.value: self._parse_map(end_symbol=_CLOSE_PAREN)}
            return _parse_word_value(token.value)
        if self._match_symbol(_OPEN_BRACKET):
            return self._parse_list()
        if self._match_symbol(_OPEN_PAREN):
            return self._parse_map(end_symbol=_CLOSE_PAREN)
        raise ModelHeaderSyntaxError(f"expected value at position {token.position}")

    def _parse_list(self) -> list[object]:
        values: list[object] = []
        while not self._is_at_end_symbol(_CLOSE_BRACKET):
            if self._match_symbol(_COMMA):
                continue
            values.append(self._parse_value())
            self._match_symbol(_COMMA)
        self._consume_symbol(_CLOSE_BRACKET)
        return values

    def _consume_key(self) -> str:
        token: _ModelHeaderToken = self._peek()
        if token.kind != _WORD_TOKEN:
            raise ModelHeaderSyntaxError(f"expected key at position {token.position}")
        self._advance()
        return token.value

    def _is_at_end_symbol(self, symbol: str | None) -> bool:
        token: _ModelHeaderToken = self._peek()
        if symbol is None:
            return token.kind == _END_TOKEN
        return token.kind == _SYMBOL_TOKEN and token.value == symbol

    def _match_symbol(self, symbol: str) -> bool:
        token: _ModelHeaderToken = self._peek()
        if token.kind == _SYMBOL_TOKEN and token.value == symbol:
            self._advance()
            return True
        return False

    def _consume_symbol(self, symbol: str) -> None:
        if self._match_symbol(symbol):
            return
        token: _ModelHeaderToken = self._peek()
        raise ModelHeaderSyntaxError(f"expected '{symbol}' at position {token.position}")

    def _expect_end(self) -> None:
        token: _ModelHeaderToken = self._peek()
        if token.kind != _END_TOKEN:
            raise ModelHeaderSyntaxError(
                f"unexpected token '{token.value}' at position {token.position}"
            )

    def _peek(self) -> _ModelHeaderToken:
        return self._tokens[self._index]

    def _advance(self) -> _ModelHeaderToken:
        token: _ModelHeaderToken = self._tokens[self._index]
        self._index += 1
        return token


def parse_model_header(*, header: str) -> dict[str, object]:
    """Parse one MODEL header with SQLBuild's map and list grammar."""

    return _ModelHeaderParser(header=header).parse()


def parse_model_retention(
    *, value: object, field_path: str
) -> ModelRetentionPolicy | Literal[False] | None:
    """Parse one typed model retention choice or explicit disable."""

    if value is None or value is False:
        return value
    mapping: Mapping[object, object] = _retention_mapping(value=value, field_path=field_path)
    _retention_allowed_keys(mapping=mapping, allowed=MODEL_RETENTION_KEYS, field_path=field_path)
    timestamp_column: str = _retention_column(
        value=mapping.get("timestamp_column"),
        field_path=f"{field_path}.timestamp_column",
    )
    cap_value: object | None = mapping.get("cap_at_column")
    cap_at_column: str | None = (
        None
        if cap_value is None
        else _retention_column(value=cap_value, field_path=f"{field_path}.cap_at_column")
    )
    when_missing_value: object = mapping.get("when_missing", RetentionMissingBehavior.ERROR)
    try:
        when_missing: RetentionMissingBehavior = RetentionMissingBehavior(when_missing_value)
    except (TypeError, ValueError) as error:
        raise RetentionConfigError(
            f"{field_path}.when_missing must be 'error' or 'skip'"
        ) from error
    return ModelRetentionPolicy(
        duration_seconds=_retention_duration(
            value=mapping.get("duration"), field_path=f"{field_path}.duration"
        ),
        timestamp_column=timestamp_column,
        cap_at_column=cap_at_column,
        when_missing=when_missing,
    )


def parse_kafka_retention(
    *, value: object, field_path: str
) -> KafkaRetentionPolicy | Literal[False] | None:
    """Parse one managed Kafka retention choice or explicit disable."""

    if value is None or value is False:
        return value
    mapping: Mapping[object, object] = _retention_mapping(value=value, field_path=field_path)
    _retention_allowed_keys(mapping=mapping, allowed=KAFKA_RETENTION_KEYS, field_path=field_path)
    return KafkaRetentionPolicy(
        duration_seconds=_retention_duration(
            value=mapping.get("duration"), field_path=f"{field_path}.duration"
        ),
        timestamp=_retention_choice(
            value=mapping.get("timestamp", "broker"),
            allowed=frozenset({"broker"}),
            field_path=f"{field_path}.timestamp",
        ),
        fallback=_optional_retention_choice(
            value=mapping.get("fallback"),
            allowed=frozenset({"landed"}),
            field_path=f"{field_path}.fallback",
        ),
        cap_at=_optional_retention_choice(
            value=mapping.get("cap_at"),
            allowed=frozenset({"landed"}),
            field_path=f"{field_path}.cap_at",
        ),
    )


def _retention_mapping(*, value: object, field_path: str) -> Mapping[object, object]:
    if value is True or not isinstance(value, Mapping):
        raise RetentionConfigError(f"{field_path} must be false or a mapping")
    return cast(Mapping[object, object], value)


def _retention_allowed_keys(
    *, mapping: Mapping[object, object], allowed: frozenset[str], field_path: str
) -> None:
    invalid: tuple[str, ...] = tuple(sorted(str(key) for key in mapping if key not in allowed))
    if invalid:
        raise RetentionConfigError(f"{field_path} contains unsupported keys: {', '.join(invalid)}")


def _retention_duration(*, value: object, field_path: str) -> int:
    try:
        return parse_duration_seconds(value=value, field_path=field_path, allow_zero=False)
    except ValueError as error:
        raise RetentionConfigError(str(error)) from error


def _retention_column(*, value: object, field_path: str) -> str:
    if not isinstance(value, str) or _COLUMN_NAME_PATTERN.fullmatch(value) is None:
        raise RetentionConfigError(f"{field_path} must be an unqualified column name")
    return value


def _retention_choice(*, value: object, allowed: frozenset[str], field_path: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        expected: str = " or ".join(repr(item) for item in sorted(allowed))
        raise RetentionConfigError(f"{field_path} must be {expected}")
    return value


def _optional_retention_choice(
    *, value: object, allowed: frozenset[str], field_path: str
) -> str | None:
    return (
        None
        if value is None
        else _retention_choice(value=value, allowed=allowed, field_path=field_path)
    )


def _tokenize_model_header(header: str) -> list[_ModelHeaderToken]:
    tokens: list[_ModelHeaderToken] = []
    index: int = 0
    while index < len(header):
        character: str = header[index]
        if character.isspace():
            index += 1
            continue
        if character in _YAML_MAPPING_SYMBOLS:
            raise ModelHeaderSyntaxError(
                "YAML-like brace mappings are not supported at position "
                f"{index}; use SQLBuild parenthesized mapping syntax"
            )
        if character in _SYMBOLS or character == _KEY_VALUE_SEPARATOR:
            tokens.append(_ModelHeaderToken(kind=_SYMBOL_TOKEN, value=character, position=index))
            index += 1
            continue
        if character in _QUOTE_NAMES:
            string_value: str
            next_index: int
            string_value, next_index = _read_quoted_string(header=header, start=index)
            tokens.append(_ModelHeaderToken(kind=_STRING_TOKEN, value=string_value, position=index))
            index = next_index
            continue
        next_index = index
        while next_index < len(header):
            next_character: str = header[next_index]
            if (
                next_character.isspace()
                or next_character in _SYMBOLS
                or next_character in _YAML_MAPPING_SYMBOLS
                or next_character == _KEY_VALUE_SEPARATOR
            ):
                break
            if next_character in _QUOTE_NAMES:
                raise ModelHeaderSyntaxError(
                    f"unexpected {_QUOTE_NAMES[next_character]} quote inside bare value at "
                    f"position {next_index}; quote the whole value"
                )
            next_index += 1
        value: str = header[index:next_index]
        if not value:
            raise ModelHeaderSyntaxError(f"unexpected character '{character}' at position {index}")
        tokens.append(_ModelHeaderToken(kind=_WORD_TOKEN, value=value, position=index))
        index = next_index
    tokens.append(_ModelHeaderToken(kind=_END_TOKEN, value="", position=len(header)))
    return tokens


def _read_quoted_string(*, header: str, start: int) -> tuple[str, int]:
    value_parts: list[str] = []
    quote: str = header[start]
    quote_name: str = _QUOTE_NAMES[quote]
    index: int = start + 1
    while index < len(header):
        character: str = header[index]
        if character == _ESCAPE_CHARACTER:
            if index + 1 >= len(header):
                raise ModelHeaderSyntaxError(f"unterminated escape at position {index}")
            value_parts.append(header[index + 1])
            index += 2
            continue
        if character == quote:
            return "".join(value_parts), index + 1
        value_parts.append(character)
        index += 1
    raise ModelHeaderSyntaxError(f"unterminated {quote_name}-quoted string at position {start}")


def _parse_word_value(value: str) -> object:
    if value == _TRUE_VALUE:
        return True
    if value == _FALSE_VALUE:
        return False
    if value == _NULL_VALUE:
        return None
    if _INTEGER_PATTERN.match(value):
        return int(value)
    if _FLOAT_PATTERN.match(value):
        return float(value)
    return value
