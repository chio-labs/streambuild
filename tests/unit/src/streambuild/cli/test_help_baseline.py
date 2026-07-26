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
            expected_sha256="9c7f2b7bbaed8a1e3c119e699df25d7679bdf1827bb6b27a4855811049927ea6",
        ),
        CliHelpBaselineTestCase(
            description="captures discover help",
            argv=("discover", "--help"),
            expected_sha256="32ea3bcad6677c8abd5067ab8604699e7d375e3b7e43bbc5cdbef8eb0ff0ede1",
        ),
        CliHelpBaselineTestCase(
            description="captures compile help",
            argv=("compile", "--help"),
            expected_sha256="bd74202f2022ab3ea39c81d2a579e7ff0a2b2be451721a031f1c9fb9d80ebb63",
        ),
        CliHelpBaselineTestCase(
            description="captures test help",
            argv=("test", "--help"),
            expected_sha256="382eecd5d3167774e9c77505e36cf255084ea15970496e76ddcceb147a80218e",
        ),
        CliHelpBaselineTestCase(
            description="captures plan help",
            argv=("plan", "--help"),
            expected_sha256="063f42f6d9d791ba35ab57a676dddb3c82d9f90d8da974f075f6071364684f66",
        ),
        CliHelpBaselineTestCase(
            description="captures backfill help",
            argv=("backfill", "--help"),
            expected_sha256="f8975a898cc84a9b9a7a022a8cc2ab60a3f3e6ab56c5778ce32a7bc41e8fbb2f",
        ),
        CliHelpBaselineTestCase(
            description="captures audit help",
            argv=("audit", "--help"),
            expected_sha256="d6d0abd403af1a2574a399b43e5230c92a4cc734775f7d459b674c9385db923e",
        ),
        CliHelpBaselineTestCase(
            description="captures audit backfill help",
            argv=("audit", "backfill", "--help"),
            expected_sha256="f073fbdcf5568f356a138601d55179267ee03dbaebe8dddb764525af66939e9d",
        ),
        CliHelpBaselineTestCase(
            description="captures publish help",
            argv=("publish", "--help"),
            expected_sha256="0aeff8b28481a187e5b8d544a943aab140d2fb891fb9b0cb4243baadad500bd9",
        ),
        CliHelpBaselineTestCase(
            description="captures reconcile help",
            argv=("reconcile", "--help"),
            expected_sha256="65086d0d43fbe09850a27780f5904c22cfdfe3fa55482b8e4465d2c1dc86ba98",
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
