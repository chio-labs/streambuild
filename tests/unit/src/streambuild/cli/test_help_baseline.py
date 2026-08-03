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
            expected_sha256="c688d156aaed17cbf55dbf26b217eee84a9f6b681273137c714c2474e6b21abd",
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
            expected_sha256="35f4b9078a532f0d6c07ebcc530272cd4aadc1c1ade48f8b345aa23ba359e08b",
        ),
        CliHelpBaselineTestCase(
            description="captures build help",
            argv=("build", "--help"),
            expected_sha256="7956a1dc824961643a23c598a177a20427a9a8bf2ddac8ca4e7f5832059439ee",
        ),
        CliHelpBaselineTestCase(
            description="captures audit help",
            argv=("audit", "--help"),
            expected_sha256="ed25ed03a8e014f19ef9d06689aa41bde5c192ce019cde0c905d2058f2c9f3b4",
        ),
        CliHelpBaselineTestCase(
            description="captures audit deployment help",
            argv=("audit", "deployment", "--help"),
            expected_sha256="22b4b1266712a31161a2938610f9619d727b8164e7573b0398891f1c8018e816",
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
