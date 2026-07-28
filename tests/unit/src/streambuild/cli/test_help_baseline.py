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
            expected_sha256="6e2e6f1c14aa17885dd1dd6cdf01622f8b485f0f347918af16a68d6cc9009cd7",
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
            expected_sha256="b146b78f63c6833813c263d1b980b8e5ed6d88495c94649a78c9fdd12ad4d10c",
        ),
        CliHelpBaselineTestCase(
            description="captures reconcile help",
            argv=("reconcile", "--help"),
            expected_sha256="90c11b9bf55f9832d20932ce11407ec8f095417c91e6accbaab0e7a1a94959db",
        ),
        CliHelpBaselineTestCase(
            description="captures janitor help",
            argv=("janitor", "--help"),
            expected_sha256="608566c20ec37889bb540d3da1cf4c225fac75ffb020db9f393723a38bb85905",
        ),
        CliHelpBaselineTestCase(
            description="captures doctor help",
            argv=("doctor", "--help"),
            expected_sha256="e653ccda0c6db5f2bd9c2479a3154dc6a0b63a031819b71ff6ff3aed2ca31b89",
        ),
        CliHelpBaselineTestCase(
            description="captures repair help",
            argv=("repair", "--help"),
            expected_sha256="ff32b9f6b3c598cf816b35094466af494f0c8dafb5374add6788009c53ce58a7",
        ),
        CliHelpBaselineTestCase(
            description="captures repair active-view help",
            argv=("repair", "active-view", "--help"),
            expected_sha256="ab6002a5ceacf347c51e252864df9e6172f0a6da31f4b92427e16bca7576b024",
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
