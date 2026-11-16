from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from noita_rl.compiler.compile import compile_and_activate, compile_scenario
from noita_rl.compiler.preview import render_scenario_preview
from noita_rl.schema import load_and_validate_json, validate_document
from noita_rl.settings import Settings


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.path)
    schema = args.schema
    document = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_document(schema, document)
    if errors:
        print(f"Validation failed for {path}:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"OK: {path}")
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    scenario = Path(args.scenario)
    root = repo_root()
    if args.activate:
        built = compile_and_activate(scenario, root)
    else:
        built = compile_scenario(scenario, root / "mod" / "files" / "build")
    print(built)
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    scenario = Path(args.scenario)
    root = repo_root()
    built = compile_scenario(scenario, root / "mod" / "files" / "build")
    out = Path(args.output) if args.output else built / "preview.png"
    render_scenario_preview(built / "scenario.json", built / "materials.png", out)
    print(out)
    return 0


def cmd_install_mod(args: argparse.Namespace) -> int:
    settings = Settings()
    source = Path(args.source) if args.source else settings.mod_source
    dest = Path(args.dest) if args.dest else settings.mod_install
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    print(dest)
    return 0


EXPORT_PREFIX = "noita_rl.export_"


def cmd_pull_rooms(args: argparse.Namespace) -> int:
    from noita_rl.modsettings import default_mod_settings_path, read_mod_settings

    path = Path(args.settings) if args.settings else default_mod_settings_path()
    dest = Path(args.dest) if args.dest else repo_root() / "examples" / "scenarios"
    try:
        settings = read_mod_settings(path)
    except (OSError, ValueError) as error:
        print(f"Could not read Noita's mod settings at {path}: {error}")
        return 1
    rooms = {k[len(EXPORT_PREFIX):]: v for k, v in sorted(settings.items()) if k.startswith(EXPORT_PREFIX)}
    if not rooms:
        print(f"No exported rooms in {path}.")
        print("Click 'Export for RL' in the Room Editor. If you just did, close Noita and try again.")
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name, text in rooms.items():
        try:
            document = json.loads(text) if isinstance(text, str) else None
        except json.JSONDecodeError as error:
            document, errors = None, [str(error)]
        else:
            errors = validate_document("scenario", document) if isinstance(document, dict) else ["not a JSON object"]
        if errors:
            failed += 1
            print(f"SKIP {name}: " + "; ".join(errors))
            continue
        target = dest / f"{document['id']}.json"
        if target.exists() and not args.overwrite and json.loads(target.read_text(encoding="utf-8")) != document:
            failed += 1
            print(f"SKIP {name}: {target} already exists with different content (use --overwrite)")
            continue
        target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"OK   {name} -> {target}")
    return 1 if failed else 0


def cmd_smoke_test(args: argparse.Namespace) -> int:
    from noita_rl.env import NoitaRLEnv

    scenario = Path(args.scenario) if args.scenario else repo_root() / "examples" / "scenarios" / "movement_basics.json"
    load_and_validate_json(scenario, "scenario")
    compile_and_activate(scenario, repo_root())
    cmd_install_mod(argparse.Namespace(source=None, dest=None))

    env = NoitaRLEnv(scenario_path=scenario, auto_launch=True)
    try:
        obs, info = env.reset()
        print(f"reset frame={obs['frame']}")
        obs, reward, terminated, truncated, info = env.step(0)
        print(f"step reward={reward} frame={obs['frame']} terminated={terminated} truncated={truncated}")
        return 0
    finally:
        env.close()


def cmd_debug_status(args: argparse.Namespace) -> int:
    from noita_rl.modsettings import default_mod_settings_path, read_mod_settings

    path = Path(args.settings) if args.settings else default_mod_settings_path()
    try:
        settings = read_mod_settings(path)
    except (OSError, ValueError) as error:
        print(f"Could not read {path}: {error}")
        return 1
    print(f"{path}")
    for name, value in sorted(settings.items()):
        if not name.startswith("noita_rl."):
            continue
        shown = value if not isinstance(value, str) or len(value) <= 120 else f"<{len(value)} chars>"
        print(f"  {name} = {shown}")
    stage = settings.get("noita_rl.debug_stage")
    if stage is None:
        print("No editor breadcrumbs yet: the mod has not run since it was installed.")
    else:
        print(f"Last stage reached: {stage}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noita-rl")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate a JSON document against a schema")
    validate.add_argument("path")
    validate.add_argument("--schema", choices=("scenario", "curriculum"), default="scenario")
    validate.set_defaults(func=cmd_validate)

    compile_cmd = sub.add_parser("compile", help="Compile a scenario into mod build artifacts")
    compile_cmd.add_argument("scenario")
    compile_cmd.add_argument("--activate", action="store_true")
    compile_cmd.set_defaults(func=cmd_compile)

    preview = sub.add_parser("preview", help="Render a compiled scenario preview image")
    preview.add_argument("scenario")
    preview.add_argument("--output")
    preview.set_defaults(func=cmd_preview)

    install = sub.add_parser("install-mod", help="Copy the mod folder into the local Noita mods directory")
    install.add_argument("--source")
    install.add_argument("--dest")
    install.set_defaults(func=cmd_install_mod)

    pull = sub.add_parser("pull-rooms", help="Copy rooms exported by the in-game editor into the repo, validated")
    pull.add_argument("--settings", help="Path to mod_settings.bin (default: save00 in LocalLow)")
    pull.add_argument("--dest", help="Scenario folder (default: examples/scenarios)")
    pull.add_argument("--overwrite", action="store_true", help="Replace scenarios with the same id")
    pull.set_defaults(func=cmd_pull_rooms)

    debug = sub.add_parser("debug-status", help="Show the mod's saved settings and crash breadcrumbs")
    debug.add_argument("--settings", help="Path to mod_settings.bin (default: save00 in LocalLow)")
    debug.set_defaults(func=cmd_debug_status)

    smoke = sub.add_parser("smoke-test", help="Launch Noita and perform a short environment smoke test")
    smoke.add_argument("--scenario")
    smoke.set_defaults(func=cmd_smoke_test)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
