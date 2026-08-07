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
            expected_sha256="a4653ad51d34266204d07336e16a8516eb31e5f8f6baba90da52477967d05a8e",
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
            expected_sha256="ec5e9710cfabd3a81ab7086ba742d351704f70720615f5682693f2034c067302",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment help",
            argv=("deployment", "--help"),
            expected_sha256="8dd62f8d2f020f4dc961645133118fbee179ca610291eee2d1db0a8afe4f9ae5",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment list help",
            argv=("deployment", "list", "--help"),
            expected_sha256="8f4107a020f3d51334c3c14d3a06bedddc20c40b125d87a8db55ec10914a8cfb",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment show help",
            argv=("deployment", "show", "--help"),
            expected_sha256="f7ccfe5513b4fa47eb9a4cf03ba065a67fbb2c3e24a21c28d684a7d6f6a1a0ef",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment audit help",
            argv=("deployment", "audit", "--help"),
            expected_sha256="1f1a2d40f6caea7a95694b2338eef28deac12d1a38160f9b0c63c7efbaa81895",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment promote help",
            argv=("deployment", "promote", "--help"),
            expected_sha256="7fce4a4efc1362f51184a8289bdb09404dc9d6f0e5bb494f8b0d47d2c32b451e",
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
