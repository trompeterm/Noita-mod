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
    if not getattr(args, "force", False) and noita_is_running():
        print("Noita is running. Close it first: Noita only loads mod files at startup, and")
        print("replacing them while it runs can leave the old version active. (--force skips this check.)")
        return 1
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    print(f"Installed {source} -> {dest}")
    return 0


def stale_mod_files(source: Path, dest: Path) -> list[str]:
    """Files in the repo's mod folder that are missing or different in the installed copy."""
    import filecmp

    stale = []
    for path in sorted(source.rglob("*")):
        if path.is_file():
            relative = path.relative_to(source)
            installed = dest / relative
            if not installed.is_file() or not filecmp.cmp(path, installed, shallow=False):
                stale.append(relative.as_posix())
    return stale


def noita_is_running() -> bool:
    """True if a noita.exe process exists (Windows only; False elsewhere or on error)."""
    import subprocess

    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq noita.exe", "/NH"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "noita.exe" in out.lower()


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
    cmd_install_mod(argparse.Namespace(source=None, dest=None, force=False))

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


def describe_agent_packet(packet) -> str:
    done = f"  DONE ({packet.reason.name.lower()})" if packet.terminal else ""
    goal = f"{packet.goal_dist:.0f} px ({packet.goal_dx:+.0f},{packet.goal_dy:+.0f})" if packet.has_goal else "none"
    rays = " ".join(f"{d:.0f}" for d in packet.rays)
    return "\n".join([
        f"frame {packet.frame}  episode {packet.episode}  room {packet.room_index}/{packet.room_count}"
        f"  attempt {packet.attempt}  {packet.objective.name.lower()}  cmd {packet.cmd_seq}{done}",
        f"  time {packet.steps}/{packet.max_steps} steps  reward {packet.reward:+.3f}"
        f"  return {packet.episode_return:+.3f}",
        f"  pos {packet.x:.1f},{packet.y:.1f}  vel {packet.vx:.1f},{packet.vy:.1f}"
        f"  {'ground' if packet.on_ground else 'air'}  hp {packet.hp:.2f}/{packet.max_hp:.2f}"
        f"  gold {packet.gold}  mana {packet.mana}/{packet.mana_max}",
        f"  goal {goal}{' IN' if packet.in_goal else ''}  enemies {packet.enemies_alive}"
        f"  gold left {packet.gold_left}  keys {'+'.join(sorted(packet.buttons)) or 'none'}"
        f"  aim {packet.aim_x:+.2f},{packet.aim_y:+.2f}",
        f"  rays {rays}",
    ])


def cmd_agent_probe(args: argparse.Namespace) -> int:
    """Read the RL-agent telemetry strip from Noita's window, and optionally send input.

    By default this works with Noita in the background: the window's own contents are
    captured (PrintWindow) and keys are posted to Noita's window only. Noita must not be
    minimized, and must not pause when unfocused (see `noita-rl configure-noita`).
    --focus uses the old method instead: bring Noita to the front and copy the screen.
    """
    import time

    import win32gui

    from noita_rl.platform.windows.capture import MssFrameCapture, PrintWindowCapture
    from noita_rl.platform.windows.input import NoitaWindowInput
    from noita_rl.platform.windows.process import (
        WindowsProcessController,
        client_area,
        focus_window,
        make_dpi_aware,
    )
    from noita_rl.telemetry.agent_packet import BUTTONS, decode_agent_strip

    hold = {name.strip() for name in args.hold.split(",") if name.strip()} if args.hold else set()
    if hold - set(BUTTONS):
        print(f"Unknown keys {sorted(hold - set(BUTTONS))}. Choose from: {', '.join(BUTTONS)}")
        return 2
    make_dpi_aware()
    settings = Settings()
    window = WindowsProcessController(str(settings.noita_exe), []).find_window(settings.window_title)
    if window is None:
        print("No Noita window found (noita.exe). Start Noita with Mode = RL agent.")
        return 1
    if win32gui.IsIconic(window.hwnd) and not args.focus:
        print("Noita is minimized, so it draws nothing to read. Restore it (it can stay behind other")
        print("windows), and run `noita-rl configure-noita` once so it keeps running unfocused.")
        return 1
    terminal = win32gui.GetForegroundWindow()
    if args.focus:
        focus_window(window.hwnd)
    keys = NoitaWindowInput(window.hwnd)
    capture = MssFrameCapture() if args.focus else PrintWindowCapture()
    try:
        return _probe(args, settings, window.hwnd, client_area, capture, keys, hold, decode_agent_strip, time)
    finally:
        keys.release_all()
        if args.focus and terminal and terminal != window.hwnd and not args.stay:
            try:
                focus_window(terminal, settle_s=0)
            except Exception:  # noqa: BLE001 - focus is a convenience
                pass


def _probe(args, settings, hwnd, client_area, capture, keys, hold, decode, time) -> int:
    if args.room is not None or args.restart:
        keys.send_agent_command(args.room)
        time.sleep(0.2)
    hint = None
    deadline = time.time() + args.seconds
    last_frame = -1
    first = None
    while True:
        keys.hold(hold)
        window = client_area(hwnd)  # re-read: the window may have been restored or moved
        try:
            pixels = capture.capture(window)
            packet, hint = decode(pixels, hint)
        except ValueError as error:
            print(f"Could not read the strip: {error}")
            print(f"  (captured Noita's {window.width}x{window.height} area)")
            stale = stale_mod_files(settings.mod_source, settings.mod_install)
            if stale:
                print(f"The installed mod is out of date ({len(stale)} files differ, e.g. {stale[0]}).")
                print("Close Noita, run `uv run noita-rl install-mod`, then start a new game.")
            if args.save and "pixels" in locals():
                from PIL import Image

                Image.fromarray(pixels).save(args.save)
                print(f"Saved the screenshot to {args.save}")
            return 1
        first = first or (packet, time.time())
        if packet.frame != last_frame:
            last_frame = packet.frame
            print(describe_agent_packet(packet))
            print(f"  (strip at {hint[0]:.1f},{hint[1]:.1f}, {hint[2]:.2f} px per cell)")
        if time.time() >= deadline:
            break
        time.sleep(0.25 if hold else 0.5)
    start, started = first
    elapsed = time.time() - started
    if elapsed >= 1:
        frames = packet.frame - start.frame
        print(f"Noita ran {frames} frames in {elapsed:.1f} s ({frames / elapsed:.0f} per second)."
              + ("  It looks paused: run `noita-rl configure-noita`." if frames == 0 else ""))
    if hold:
        seen = set(packet.buttons)
        print(f"Mod saw keys: {', '.join(sorted(seen)) or 'none'} (sent: {', '.join(sorted(hold))})")
        if not hold <= seen:
            print("Some keys did not reach the mod. Noita may not accept keys while in the background.")
            return 1
    return 0


def cmd_configure_noita(args: argparse.Namespace) -> int:
    """Make Noita keep running in the background: windowed, no pause when unfocused."""
    from noita_rl.noita_config import BACKGROUND_SETTINGS, configure, default_config_path

    path = Path(args.config) if args.config else default_config_path()
    if noita_is_running():
        print("Close Noita first: it rewrites config.xml when it exits, which would undo this.")
        return 1
    backup = path.with_name(path.name + ".noita_rl_backup")
    if args.undo:
        if not backup.exists():
            print(f"No backup at {backup}; nothing to undo.")
            return 1
        shutil.copy2(backup, path)
        print(f"Restored {path} from {backup}")
        return 0
    try:
        before, made = configure(path)
    except (OSError, ValueError) as error:
        print(f"Could not update {path}: {error}")
        return 1
    for name, value in BACKGROUND_SETTINGS.items():
        print(f"  {name}: {before[name]} -> {value}")
    print(f"Updated {path}" + (f" (original saved as {made.name})" if made else " (already set)"))
    print("Noita now runs windowed and keeps going when you switch to other apps. Don't minimize it.")
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
    install.add_argument("--force", action="store_true", help="Install even if Noita is running")
    install.set_defaults(func=cmd_install_mod)

    pull = sub.add_parser("pull-rooms", help="Copy rooms exported by the in-game editor into the repo, validated")
    pull.add_argument("--settings", help="Path to mod_settings.bin (default: save00 in LocalLow)")
    pull.add_argument("--dest", help="Scenario folder (default: examples/scenarios)")
    pull.add_argument("--overwrite", action="store_true", help="Replace scenarios with the same id")
    pull.set_defaults(func=cmd_pull_rooms)

    debug = sub.add_parser("debug-status", help="Show the mod's saved settings and crash breadcrumbs")
    debug.add_argument("--settings", help="Path to mod_settings.bin (default: save00 in LocalLow)")
    debug.set_defaults(func=cmd_debug_status)

    probe = sub.add_parser("agent-probe", help="Read the RL-agent telemetry strip from the Noita window")
    probe.add_argument("--seconds", type=float, default=0, help="Keep reading for this long")
    probe.add_argument("--room", type=int, help="First send a command: start an episode in course room N")
    probe.add_argument("--restart", action="store_true", help="First send a command: restart the current room")
    probe.add_argument("--save", help="Save the screenshot here if the strip can't be read")
    probe.add_argument("--hold", help="Hold action keys while reading, e.g. right,jump")
    probe.add_argument("--focus", action="store_true",
                       help="Bring Noita to the front and copy the screen (old method)")
    probe.add_argument("--stay", action="store_true", help="With --focus: leave Noita in front afterwards")
    probe.set_defaults(func=cmd_agent_probe)

    configure = sub.add_parser("configure-noita",
                               help="Let Noita run in the background: windowed, no pause when unfocused")
    configure.add_argument("--config", help="Path to Noita's config.xml (default: save_shared in LocalLow)")
    configure.add_argument("--undo", action="store_true", help="Restore the backup made the first time")
    configure.set_defaults(func=cmd_configure_noita)

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
