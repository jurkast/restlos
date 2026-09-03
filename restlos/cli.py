from __future__ import annotations

import argparse
import json
import sys

from . import APP_TAGLINE, __version__
from .analyzer import RemovalAnalyzer
from .i18n import configure, current_language, display_text, translate as _
from .recovery import RecoveryManager
from .remover import RemovalExecutor
from .scanners import ApplicationScanner
from .utils import format_size


class LocalizedArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        text = super().format_help()
        if current_language() == "de":
            for source, target in (
                ("usage:", "Verwendung:"),
                ("positional arguments:", "Positionsargumente:"),
                ("options:", "Optionen:"),
                ("show this help message and exit", "diese Hilfe anzeigen und beenden"),
                ("show program's version number and exit", "Programmversion anzeigen und beenden"),
            ):
                text = text.replace(source, target)
        return text


def build_parser() -> argparse.ArgumentParser:
    parser = LocalizedArgumentParser(
        prog="restlos",
        description=_(APP_TAGLINE),
    )
    parser.add_argument("--version", action="version", version=f"Restlos {__version__}")
    parser.add_argument("--language", choices=("system", "de", "en"), help=_("Sprache für diesen Aufruf"))
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help=_("erkannte Anwendungen auflisten"))
    list_parser.add_argument("--json", action="store_true")
    list_parser.add_argument("--limit", type=int, default=0)

    analyze_parser = subparsers.add_parser("analyze", help=_("Löschplan anzeigen"))
    analyze_parser.add_argument("query")
    analyze_parser.add_argument("--json", action="store_true")

    remove_parser = subparsers.add_parser("remove", help=_("Anwendung gemäß Löschplan entfernen"))
    remove_parser.add_argument("query")
    remove_parser.add_argument("--yes", action="store_true", help=_("Entfernung bestätigen"))
    remove_parser.add_argument("--trash", action="store_true", help=_("Benutzerdaten in den Papierkorb verschieben"))
    remove_parser.add_argument(
        "--backup",
        action="store_true",
        help=_("Safety Backup geeigneter Einstellungen und Spielstände vor endgültigem Löschen erstellen"),
    )

    recovery_parser = subparsers.add_parser(
        "recovery",
        help=_("wiederherstellbare Entfernungsvorgänge verwalten"),
    )
    recovery_commands = recovery_parser.add_subparsers(dest="recovery_command", required=True)
    recovery_list = recovery_commands.add_parser("list", help=_("verfügbare Wiederherstellungen auflisten"))
    recovery_list.add_argument("--json", action="store_true")
    recovery_restore = recovery_commands.add_parser("restore", help=_("Benutzerdaten eines Vorgangs wiederherstellen"))
    recovery_restore.add_argument("recovery_id")
    recovery_restore.add_argument("--yes", action="store_true", help=_("Wiederherstellung bestätigen"))
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
        raise ValueError(_("Keine Anwendung für „{query}“ gefunden.", query=query))
    matches = exact or partial
    names = ", ".join(f"{app.name} [{app.key}]" for app in matches[:10])
    raise ValueError(_("Mehrdeutige Auswahl: {names}", names=names))


def main(argv: list[str] | None = None) -> int:
    raw_arguments = list(argv) if argv is not None else sys.argv[1:]
    for index, value in enumerate(raw_arguments):
        if value.startswith("--language="):
            configure(value.partition("=")[2])
            break
        if value == "--language" and index + 1 < len(raw_arguments):
            configure(raw_arguments[index + 1])
            break
    parser = build_parser()
    arguments = parser.parse_args(raw_arguments)
    if arguments.language:
        configure(arguments.language)
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
                                "trash_paths": [item.original_path for item in record.available_trash_items],
                                "backup_paths": [item.original_path for item in record.available_backup_items],
                                "backup_archive": record.backup_path,
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
                print(_("Keine wiederherstellbaren Restlos-Vorgänge gefunden."))
            else:
                for record in records:
                    print(
                        _(
                            "{id}\t{name}\t{count} Pfad(e)\t{size}",
                            id=record.recovery_id,
                            name=record.app_name,
                            count=len(record.available_items),
                            size=format_size(record.available_size),
                        )
                    )
            return 0

        if not arguments.yes:
            print(_("Abgebrochen: Für die Wiederherstellung ist --yes erforderlich."), file=sys.stderr)
            return 2
        result = manager.restore(arguments.recovery_id)
        if result.success:
            print(_("{count} Pfad(e) wurden wiederhergestellt.", count=len(result.restored_paths)))
            print(_("Paketaktionen werden nicht automatisch rückgängig gemacht."))
            return 0
        print(_("Wiederherstellung nicht vollständig:"), file=sys.stderr)
        for error in result.errors:
            print(f"  {display_text(error)}", file=sys.stderr)
        return 1

    applications = ApplicationScanner().scan()
    if arguments.command == "list":
        selected = applications[: arguments.limit or None]
        if arguments.json:
            print(json.dumps([app.to_dict() for app in selected], ensure_ascii=False, indent=2))
        else:
            for app in selected:
                print(f"{app.name}\t{display_text(app.source.value)}\t{app.package_id}")
        return 0

    try:
        app = find_application(arguments.query, applications)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    plan = RemovalAnalyzer().analyze(app, applications=applications)

    if arguments.command == "analyze":
        if arguments.json:
            print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(f"{app.name} ({display_text(app.source.value)})")
            for action in plan.actions:
                print(_("  Paketaktion: {label}", label=display_text(action.label)))
            for target in plan.targets:
                marker = "x" if target.selected else " "
                print(
                    f"  [{marker}] {target.path} – {display_text(target.reason)}, "
                    f"{format_size(target.size)}, {display_text(target.confidence.value)}"
                )
                for use in target.shared_with:
                    print(_("  GESCHÜTZT: {name} ({source}) – {evidence}: {path}", name=use.app_name,
                            source=display_text(use.source), evidence=display_text(use.evidence), path=use.reference_path))
            for warning in plan.warnings:
                print(_("  WARNUNG: {warning}", warning=display_text(warning)))
            if plan.safety_error:
                print(_("  GESPERRT: {error}", error=plan.safety_error))
            print(_("Ausgewählte Benutzerdaten: {size}", size=format_size(plan.total_size)))
        return 0

    if not arguments.yes:
        print(_("Abgebrochen: Für die Entfernung ist --yes erforderlich."), file=sys.stderr)
        return 2
    if arguments.trash and arguments.backup:
        print(_("--backup ist für endgültiges Löschen vorgesehen und kann nicht mit --trash verwendet werden."), file=sys.stderr)
        return 2
    executor = RemovalExecutor()

    def report(message: str, fraction: float) -> None:
        print(f"[{fraction * 100:5.1f}%] {display_text(message)}", file=sys.stderr)

    result = executor.execute(
        plan,
        permanent=not arguments.trash,
        create_backup=arguments.backup,
        progress=report,
    )
    if result.success:
        print(
            _(
                "{name} wurde entfernt. Protokoll: {path}",
                name=app.name,
                path=result.receipt_path or _("nicht geschrieben"),
            )
        )
        if result.recovery_items:
            print(
                _(
                    "Wiederherstellbar: {count} Pfad(e) mit Kennung {id}.",
                    count=len(result.recovery_items),
                    id=result.recovery_id,
                )
            )
        if result.backup_items:
            print(
                _(
                    "Safety Backup: {count} Datenpfad(e) mit Kennung {id}.",
                    count=len(result.backup_items),
                    id=result.recovery_id,
                )
            )
        if result.residual_paths:
            print(_("Kontrollscan: {count} weitere mögliche Restpfade gefunden.", count=len(result.residual_paths)))
            for path in result.residual_paths[:10]:
                print(f"  {path}")
        elif result.verification_error:
            print(_("Kontrollscan fehlgeschlagen: {error}", error=result.verification_error), file=sys.stderr)
        else:
            print(_("Kontrollscan: keine weiteren zuordenbaren Restpfade gefunden."))
        if result.kept_paths:
            print(_("Bewusst nicht ausgewählt und beibehalten: {count} Pfad(e).", count=len(result.kept_paths)))
        return 0
    print(_("Entfernung nicht vollständig:"), file=sys.stderr)
    for error in result.errors:
        print(f"  {display_text(error)}", file=sys.stderr)
    return 1
