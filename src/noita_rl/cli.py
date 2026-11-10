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
