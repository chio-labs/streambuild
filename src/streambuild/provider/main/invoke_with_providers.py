"""Apache-2.0: SQLBuild provider/main/runtime.py@7625d22e2716."""

from __future__ import annotations

from collections.abc import Callable

from streambuild.provider._helpers.injection import call_with_provider_injection
from streambuild.provider.classes.container import ProviderContainer


def invoke_with_providers(
    *,
    function: Callable[..., object],
    context: object,
    providers: ProviderContainer | None = None,
    supplied_kwargs: dict[str, object] | None = None,
) -> object:
    """Call a sensor function with optional provider injection."""

    return call_with_provider_injection(
        function=function,
        context=context,
        providers=providers,
        supplied_kwargs=supplied_kwargs,
    )
