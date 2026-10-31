import hashlib

import pytest
from _pytest.capture import CaptureFixture

from sqltide.cli.entry._helpers.parser import build_cli_parser
from tests.unit.src.sqltide.cli._test_types import CliHelpBaselineTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CliHelpBaselineTestCase(
            description="captures root help",
            argv=("--help",),
            expected_sha256="0fa6a0489c3b23409a3395779210acf91d68fbe6769c240c8e55b895f49a8369",
        ),
        CliHelpBaselineTestCase(
            description="captures admin help",
            argv=("admin", "--help"),
            expected_sha256="8a71117b230ad9c2a0920d0c264609cd1d5267da2945f3421206b73e00ebb46d",
        ),
        CliHelpBaselineTestCase(
            description="captures dev help",
            argv=("dev", "--help"),
            expected_sha256="69b20381c41a73605a3a0217acd99f1d66c4d1551a50bdcd7dcc4d2234a1e150",
        ),
        CliHelpBaselineTestCase(
            description="captures discover help",
            argv=("discover", "--help"),
            expected_sha256="600bee74833061387911497fbaa299d735e8183ecacdeaa0ad117df0f8d61843",
        ),
        CliHelpBaselineTestCase(
            description="captures compile help",
            argv=("compile", "--help"),
            expected_sha256="de37dc118e2619233c6b286e33bcf04aef8e3b73891c1d45e064414b64e0eb6e",
        ),
        CliHelpBaselineTestCase(
            description="captures test help",
            argv=("test", "--help"),
            expected_sha256="f450726442f980b6efb10ddae32281b2b06d43c031d7f779a45b8cdf573eb04a",
        ),
        CliHelpBaselineTestCase(
            description="captures plan help",
            argv=("plan", "--help"),
            expected_sha256="3c04d95e6a20ef427709c98c8fc17b5134c772b1f005f410eb6b115412aa3b76",
        ),
        CliHelpBaselineTestCase(
            description="captures build help",
            argv=("build", "--help"),
            expected_sha256="2a664e12ff7eb4c7f8878502567a1855df2147e6b3cd6ba010bf62af9b462476",
        ),
        CliHelpBaselineTestCase(
            description="captures destroy help",
            argv=("destroy", "--help"),
            expected_sha256="fe2be29e7b30d73cc3e228e73b834dd4c60bdef6d9187cdf497299754a880003",
        ),
        CliHelpBaselineTestCase(
            description="captures reset target help",
            argv=("reset-target", "--help"),
            expected_sha256="8f34601d874163d6a4ea86aab6ba7243af063c2e89d92d461ffe6189b0ba7b7f",
        ),
        CliHelpBaselineTestCase(
            description="captures audit help",
            argv=("audit", "--help"),
            expected_sha256="319a98c89a13ae1e2156e0f003ccf303fcdd8d7edc0ec6f385cdbe832d81e7d9",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment help",
            argv=("deployment", "--help"),
            expected_sha256="0fd919a9d6e2daaacea62602777b3467673b0b76ca8dde40416b85ed1dc58b4f",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment list help",
            argv=("deployment", "list", "--help"),
            expected_sha256="66dee752107d197f7832e5cebd575377ac64e1ae0037b6e9edbe8c4e1647ff89",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment show help",
            argv=("deployment", "show", "--help"),
            expected_sha256="22e212378a92c28c7240db5591f0fd9c60d0ff630eb409506164cf4b31dc238f",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment audit help",
            argv=("deployment", "audit", "--help"),
            expected_sha256="dd5cba99940585378fd0eab428367aaaac45449e9ec494af8d7a720752cfbb7c",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment promote help",
            argv=("deployment", "promote", "--help"),
            expected_sha256="f3b5c5c8f6408a697fd48b28ab7499822ab770bf6717f208f5fc730059840bcc",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment diff help",
            argv=("deployment", "diff", "--help"),
            expected_sha256="aec644c958323c2eb1fb1c8eea345d107423840756711e3a1de40c85a0cf0065",
        ),
        CliHelpBaselineTestCase(
            description="captures deployment rollback help",
            argv=("deployment", "rollback", "--help"),
            expected_sha256="f0aaa68ff353c35f43c89bc9f664869253cc7ed7a265a1a6c637c805adf14970",
        ),
        CliHelpBaselineTestCase(
            description="captures reconcile help",
            argv=("reconcile", "--help"),
            expected_sha256="41991afe5178114070ae977f452f6338c106d3367590cc1820ea57092ebd6fb1",
        ),
        CliHelpBaselineTestCase(
            description="captures janitor help",
            argv=("janitor", "--help"),
            expected_sha256="ace7c516e94314a1e9a6ee5f2d6cf28a47d3186f3443c9ac666d81dabd4407c7",
        ),
        CliHelpBaselineTestCase(
            description="captures doctor help",
            argv=("doctor", "--help"),
            expected_sha256="f81420dedb68b54d0220207d5bb49a367c5e57eb40f82625b4c1a6edc5499442",
        ),
        CliHelpBaselineTestCase(
            description="captures repair help",
            argv=("repair", "--help"),
            expected_sha256="bb206d55a81b9b52be02307f16b233c74fe2c88650cff7f3394f1c7f92ee6192",
        ),
        CliHelpBaselineTestCase(
            description="captures repair active-view help",
            argv=("repair", "active-view", "--help"),
            expected_sha256="6ea6f1f5d076125558f32dce5d66cc7ff19c77217b1977d16c118a3f25ba36ba",
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
