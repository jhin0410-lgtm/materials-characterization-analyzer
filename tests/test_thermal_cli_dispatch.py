from __future__ import annotations

from mca import cli_entry


def test_console_dispatches_thermal(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_thermal_main(argv: list[str]) -> int:
        observed["argv"] = argv
        return 17

    monkeypatch.setattr(cli_entry, "thermal_main", fake_thermal_main)
    assert cli_entry.main(["thermal", "--help"]) == 17
    assert observed["argv"] == ["--help"]
