import hashlib

import pytest
from _pytest.capture import CaptureFixture

from streambuild.cli.entry._helpers.parser import build_cli_parser
from tests.unit.src.streambuild.cli._test_types import CliHelpBaselineTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CliHelpBaselineTestCase(
            description="captures root help",
            argv=("--help",),
            expected_sha256="da94d32e7a6e7c1915c2c55396275a5d28689f62f29ddee08336ea18f45acc3c",
        ),
        CliHelpBaselineTestCase(
            description="captures discover help",
            argv=("discover", "--help"),
            expected_sha256="f97516a6518cdf50b98a8181bcb1398df131e4a646cdea88404ef5ed5b91ebd8",
        ),
        CliHelpBaselineTestCase(
            description="captures compile help",
            argv=("compile", "--help"),
            expected_sha256="515dcbb6b7d3ea934d6a5ff460ebd63d85ed7f8941500ba6d599a78b4053b1a1",
        ),
        CliHelpBaselineTestCase(
            description="captures test help",
            argv=("test", "--help"),
            expected_sha256="df6f4d397c6cbc5bf79a87af06afa858e5d2352aa2bb4a78db08a02b92cdc111",
        ),
        CliHelpBaselineTestCase(
            description="captures plan help",
            argv=("plan", "--help"),
            expected_sha256="0169a46ce89e7ab4d99c449141975ad2b70a11b9378864d54bcee65aa8bbac0c",
        ),
        CliHelpBaselineTestCase(
            description="captures backfill help",
            argv=("backfill", "--help"),
            expected_sha256="9acc0f3cf1715a2bfd98fb685e17aa75ece62e9f46497e092f629fa6a11b4895",
        ),
        CliHelpBaselineTestCase(
            description="captures build help",
            argv=("build", "--help"),
            expected_sha256="4eb5b528cae24b0d9b09972e9f44fc053f741e705db2fbd64396e8008a46f84f",
        ),
        CliHelpBaselineTestCase(
            description="captures audit help",
            argv=("audit", "--help"),
            expected_sha256="78b4cccfe015c1584c275ecb98450586d1307cd5f8ebad75faadd85375236ed2",
        ),
        CliHelpBaselineTestCase(
            description="captures audit backfill help",
            argv=("audit", "backfill", "--help"),
            expected_sha256="3b854702aafb5187ca379b970f35a05f653d37376eee5ce33ee0abc75f1357ef",
        ),
        CliHelpBaselineTestCase(
            description="captures publish help",
            argv=("publish", "--help"),
            expected_sha256="39c99476dba74e42b9bb8262a892e4421b9be2e42e9f5980b07781e8c6a82e31",
        ),
        CliHelpBaselineTestCase(
            description="captures reconcile help",
            argv=("reconcile", "--help"),
            expected_sha256="90c11b9bf55f9832d20932ce11407ec8f095417c91e6accbaab0e7a1a94959db",
        ),
        CliHelpBaselineTestCase(
            description="captures janitor help",
            argv=("janitor", "--help"),
            expected_sha256="a0dfaff8fdd35f96641f3ad92875507adc4a6ea3f6bf9bb0a347515e0e01a539",
        ),
        CliHelpBaselineTestCase(
            description="captures doctor help",
            argv=("doctor", "--help"),
            expected_sha256="6a054bd5e903db0fed2564ee45a901b4582c6da9c70253c266cad7a9881c360e",
        ),
        CliHelpBaselineTestCase(
            description="captures repair help",
            argv=("repair", "--help"),
            expected_sha256="ff32b9f6b3c598cf816b35094466af494f0c8dafb5374add6788009c53ce58a7",
        ),
        CliHelpBaselineTestCase(
            description="captures repair active-view help",
            argv=("repair", "active-view", "--help"),
            expected_sha256="cf33e901a1eeae1bbada96c65d0e0d7ae760b249110c1e326a69d44aef8ad23e",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_slice_zero_command_when_rendering_help_then_matches_baseline(
    test_case: CliHelpBaselineTestCase,
    capsys: CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        build_cli_parser().parse_args(list(test_case.argv))
    captured_output: str = capsys.readouterr().out
    actual_sha256: str = hashlib.sha256(captured_output.encode("utf-8")).hexdigest()

    assert actual_sha256 == test_case.expected_sha256
