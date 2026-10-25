import pytest

from price_sentinel.cli import parser

URL = "https://www.x-kom.pl/p/1195326-konsola-playstation-sony-playstation-5-slim.html"


@pytest.mark.parametrize("command", [["check", "--url"], ["add"]])
def test_cmd_literal_apostrophes_have_actionable_error(command, capsys):
    with pytest.raises(SystemExit) as exc:
        parser().parse_args([*command, f"'{URL}'"])
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert "CMD" in error and "podwójnych cudzysłowów" in error
    assert URL not in error  # Nie odbijaj całego wejściowego adresu w błędzie.


@pytest.mark.parametrize("command", [["check", "--url"], ["add"]])
def test_unquoted_argument_is_preserved(command):
    assert parser().parse_args([*command, URL]).url == URL
