from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .analyzer import RemovalAnalyzer
from .remover import RemovalExecutor
from .scanners import ApplicationScanner
from .utils import format_size


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="restlos",
        description="Anwendungen und sicher zuordenbare Restdateien unter Linux entfernen.",
    )
    parser.add_argument("--version", action="version", version=f"Restlos {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="erkannte Anwendungen auflisten")
    list_parser.add_argument("--json", action="store_true")
    list_parser.add_argument("--limit", type=int, default=0)

    analyze_parser = subparsers.add_parser("analyze", help="Löschplan anzeigen")
    analyze_parser.add_argument("query")
    analyze_parser.add_argument("--json", action="store_true")

    remove_parser = subparsers.add_parser("remove", help="Anwendung gemäß Löschplan entfernen")
    remove_parser.add_argument("query")
    remove_parser.add_argument("--yes", action="store_true", help="endgültige Löschung bestätigen")
    remove_parser.add_argument("--trash", action="store_true", help="Benutzerdaten in den Papierkorb verschieben")
    return parser


def find_application(query: str, applications):
    exact = [
        app for app in applications
        if query.casefold() in {app.key.casefold(), app.package_id.casefold(), app.name.casefold()}
    ]
    if len(exact) == 1:
        return exact[0]
    partial = [app for app in applications if query.casefold() in f"{app.name} {app.package_id}".casefold()]
    if len(partial) == 1:
        return partial[0]
    if not exact and not partial:
        raise ValueError(f"Keine Anwendung für „{query}“ gefunden.")
    matches = exact or partial
    names = ", ".join(f"{app.name} [{app.key}]" for app in matches[:10])
    raise ValueError(f"Mehrdeutige Auswahl: {names}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if not arguments.command:
        from .gui import run_gui
        return run_gui()

    applications = ApplicationScanner().scan()
    if arguments.command == "list":
        selected = applications[: arguments.limit or None]
        if arguments.json:
            print(json.dumps([app.to_dict() for app in selected], ensure_ascii=False, indent=2))
        else:
            for app in selected:
                print(f"{app.name}\t{app.source.value}\t{app.package_id}")
        return 0

    try:
        app = find_application(arguments.query, applications)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    plan = RemovalAnalyzer().analyze(app)

    if arguments.command == "analyze":
        if arguments.json:
            print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(f"{app.name} ({app.source.value})")
            for action in plan.actions:
                print(f"  Paketaktion: {action.label}")
            for target in plan.targets:
                marker = "x" if target.selected else " "
                print(f"  [{marker}] {target.path} – {target.reason}, {format_size(target.size)}, {target.confidence.value}")
            for warning in plan.warnings:
                print(f"  WARNUNG: {warning}")
            print(f"Ausgewählte Benutzerdaten: {format_size(plan.total_size)}")
        return 0

    if not arguments.yes:
        print("Abgebrochen: Für die Entfernung ist --yes erforderlich.", file=sys.stderr)
        return 2
    executor = RemovalExecutor()

    def report(message: str, fraction: float) -> None:
        print(f"[{fraction * 100:5.1f}%] {message}", file=sys.stderr)

    result = executor.execute(plan, permanent=not arguments.trash, progress=report)
    if result.success:
        print(f"{app.name} wurde entfernt. Protokoll: {result.receipt_path or 'nicht geschrieben'}")
        return 0
    print("Entfernung nicht vollständig:", file=sys.stderr)
    for error in result.errors:
        print(f"  {error}", file=sys.stderr)
    return 1
