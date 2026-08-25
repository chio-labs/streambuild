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
            expected_sha256="94ba224d61d0905367f0b6fd06f63b89ae76e96dcc9672bf18226d907eab120e",
        ),
        CliHelpBaselineTestCase(
            description="captures admin help",
            argv=("admin", "--help"),
            expected_sha256="94a9a0f5488d5f50a1a3440e36d11326de712b3a4ed6d786d17850e9bc4952bb",
        ),
        CliHelpBaselineTestCase(
            description="captures dev help",
            argv=("dev", "--help"),
            expected_sha256="0626ef5bb73c44607283b778c85f22c2196708f71fc012f00c3e82e71123453c",
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
            expected_sha256="37f0e5549adba5d93cbc0f33ae4a84edabc665ba05e0e353801f482acfa9a77e",
        ),
        CliHelpBaselineTestCase(
            description="captures plan help",
            argv=("plan", "--help"),
            expected_sha256="b208d4d6f066bbe81fedbf3b34579bd4abcb938142b333911e6a645d2bb84279",
        ),
        CliHelpBaselineTestCase(
            description="captures build help",
            argv=("build", "--help"),
            expected_sha256="7dd8a7aba28df1a57bf32a2d66338bfc78b5bd92a7d8a4f2922b9c0cb7c15bc9",
        ),
        CliHelpBaselineTestCase(
            description="captures destroy help",
            argv=("destroy", "--help"),
            expected_sha256="e592734b892461602c2b8fa8ff1d5c02e5fb57391bd23d2179573836b41111cf",
        ),
        CliHelpBaselineTestCase(
            description="captures reset target help",
            argv=("reset-target", "--help"),
            expected_sha256="c4fa3e2b305b9b4c93b132ffa3c6fde059324ef037407a2ac2e1e6a8e08b7c4c",
        ),
        CliHelpBaselineTestCase(
            description="captures audit help",
            argv=("audit", "--help"),
            expected_sha256="ddc5e002b64acbd64f6e91d4e4b5a0eb3dc7e404d62a4d7905d3de4532ec38d8",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment help",
            argv=("deployment", "--help"),
            expected_sha256="f5025e9bfb254aa79859ddeeb2952e2b34bab59f09e9b6e0b4a026306f6693ae",
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
            description="captures deployment diff help",
            argv=("deployment", "diff", "--help"),
            expected_sha256="a988b4dd62fd1ec998279996f05ffa0c0be5e5764989b92cbcbba7cc8bfae81a",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment rollback help",
            argv=("deployment", "rollback", "--help"),
            expected_sha256="f2cf6dbcdf0c88e49712b46b63ccfba982d36cfccb44a3936fca2dc895622e33",
        ),
        CliHelpBaselineTestCase(
            description="captures reconcile help",
            argv=("reconcile", "--help"),
            expected_sha256="0afbcccdc77e64c25ee8da07473e2533c197edac90e912c01cfc9c16d373691d",
        ),
        CliHelpBaselineTestCase(
            description="captures janitor help",
            argv=("janitor", "--help"),
            expected_sha256="d46fb2bd3d3f768f8c40a139420979f8700619f6234ad5057dbe43130de29cb3",
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
