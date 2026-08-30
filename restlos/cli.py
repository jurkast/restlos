from __future__ import annotations

import argparse
import json
import sys

from . import APP_TAGLINE, __version__
from .analyzer import RemovalAnalyzer
from .recovery import RecoveryManager
from .remover import RemovalExecutor
from .scanners import ApplicationScanner
from .utils import format_size


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="restlos",
        description=APP_TAGLINE,
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
    remove_parser.add_argument("--yes", action="store_true", help="Entfernung bestätigen")
    remove_parser.add_argument("--trash", action="store_true", help="Benutzerdaten in den Papierkorb verschieben")

    recovery_parser = subparsers.add_parser(
        "recovery",
        help="wiederherstellbare Entfernungsvorgänge verwalten",
    )
    recovery_commands = recovery_parser.add_subparsers(dest="recovery_command", required=True)
    recovery_list = recovery_commands.add_parser("list", help="verfügbare Wiederherstellungen auflisten")
    recovery_list.add_argument("--json", action="store_true")
    recovery_restore = recovery_commands.add_parser("restore", help="Benutzerdaten eines Vorgangs wiederherstellen")
    recovery_restore.add_argument("recovery_id")
    recovery_restore.add_argument("--yes", action="store_true", help="Wiederherstellung bestätigen")
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

    if arguments.command == "recovery":
        manager = RecoveryManager()
        if arguments.recovery_command == "list":
            records = manager.list_records()
            if arguments.json:
                print(
                    json.dumps(
                        [
                            {
                                "id": record.recovery_id,
                                "timestamp": record.timestamp,
                                "application": record.app_name,
                                "package_id": record.package_id,
                                "source": record.source,
                                "available_paths": [item.original_path for item in record.available_items],
                                "available_size": record.available_size,
                                "package_actions": record.actions,
                                "residual_paths": record.residual_paths,
                            }
                            for record in records
                        ],
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            elif not records:
                print("Keine wiederherstellbaren Restlos-Vorgänge gefunden.")
            else:
                for record in records:
                    print(
                        f"{record.recovery_id}\t{record.app_name}\t"
                        f"{len(record.available_items)} Pfad(e)\t{format_size(record.available_size)}"
                    )
            return 0

        if not arguments.yes:
            print("Abgebrochen: Für die Wiederherstellung ist --yes erforderlich.", file=sys.stderr)
            return 2
        result = manager.restore(arguments.recovery_id)
        if result.success:
            print(f"{len(result.restored_paths)} Pfad(e) wurden wiederhergestellt.")
            print("Paketaktionen werden nicht automatisch rückgängig gemacht.")
            return 0
        print("Wiederherstellung nicht vollständig:", file=sys.stderr)
        for error in result.errors:
            print(f"  {error}", file=sys.stderr)
        return 1

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
        if result.recovery_items:
            print(
                f"Wiederherstellbar: {len(result.recovery_items)} Pfad(e) mit Kennung {result.recovery_id}."
            )
        if result.residual_paths:
            print(f"Kontrollscan: {len(result.residual_paths)} weitere mögliche Restpfade gefunden.")
            for path in result.residual_paths[:10]:
                print(f"  {path}")
        elif result.verification_error:
            print(f"Kontrollscan fehlgeschlagen: {result.verification_error}", file=sys.stderr)
        else:
            print("Kontrollscan: keine weiteren zuordenbaren Restpfade gefunden.")
        if result.kept_paths:
            print(f"Bewusst nicht ausgewählt und beibehalten: {len(result.kept_paths)} Pfad(e).")
        return 0
    print("Entfernung nicht vollständig:", file=sys.stderr)
    for error in result.errors:
        print(f"  {error}", file=sys.stderr)
    return 1
