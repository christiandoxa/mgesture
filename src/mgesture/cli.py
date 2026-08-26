from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from . import __version__
from .application import Application
from .commands.benchmark import print_benchmark, run_benchmark
from .commands.calibrate import calibrate
from .commands.list_cameras import list_cameras
from .commands.replay import run_replay
from .config import config_path, config_text, load_config, with_overrides, write_config
from .diagnostics import DoctorCode, collect_checks, print_report
from .logging_config import configure_logging
from .release import run_update
from .self_test import run_self_test
from .vision.model_manager import install_model


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mgesture", description="Safe local webcam hand-gesture mouse control"
    )
    parser.add_argument("--version", action="version", version=f"mgesture {__version__}")
    parser.add_argument("--engine", dest="global_engine", choices=("auto", "mojo", "python"))
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="run webcam gesture control; starts paused")
    run.add_argument("--camera", type=int)
    run.add_argument("--engine", choices=("auto", "mojo", "python"))
    run.add_argument("--compute", choices=("auto", "gpu", "cpu"))
    run.add_argument("--profile", choices=("performance", "balanced", "efficiency"))
    run.add_argument("--backend", choices=("auto", "fake", "x11", "wayland", "windows", "macos"))
    run.add_argument("--preview", action=argparse.BooleanOptionalAction, default=None)
    run.add_argument("--monitor", type=int)
    run.add_argument("--config", type=Path)
    run.add_argument("--armed", action="store_true")
    run.add_argument("--log-level", default=None)

    doctor = subparsers.add_parser(
        "doctor", help="diagnose environment, camera, model, pointer, and compute backends"
    )
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--runtime", action="store_true")
    subparsers.add_parser("list-cameras", help="list cameras that open and return a frame")
    subparsers.add_parser("calibrate", help="safe camera calibration wizard")
    benchmark = subparsers.add_parser("benchmark", help="benchmark the core gesture engine")
    benchmark.add_argument("--engine", choices=("python", "mojo", "compare"), default="compare")
    benchmark.add_argument("--compute", choices=("cpu", "gpu", "auto"), default="cpu")
    benchmark.add_argument("--compare-compute", action="store_true")
    benchmark.add_argument("--output", type=Path)
    replay = subparsers.add_parser("replay", help="replay a fixture into a fake backend")
    replay.add_argument("--fixture", type=Path, default=Path("tests/fixtures/basic.json"))
    replay.add_argument("--engine", choices=("python", "mojo"), default="python")

    config = subparsers.add_parser("config", help="inspect or write TOML configuration")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("path")
    config_sub.add_parser("show")
    config_write = config_sub.add_parser("write-example")
    config_write.add_argument("--path", type=Path)

    model = subparsers.add_parser("model", help="manage the offline MediaPipe model")
    model_sub = model.add_subparsers(dest="model_command", required=True)
    model_install = model_sub.add_parser("install")
    model_install.add_argument("--path", type=Path)

    self_test = subparsers.add_parser(
        "self-test", help="run a headless fake-input runtime self-test"
    )
    self_test.add_argument("--headless", action="store_true")
    self_test.add_argument("--fake-input", action="store_true")
    self_test.add_argument("--engine", choices=("auto", "mojo", "python"))
    update = subparsers.add_parser("update", help="check for or install a newer release")
    update.add_argument("--check", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if args.command is None:
        return main(["run"] if argv is None else ["run", *argv])
    if args.command == "config":
        if args.config_command == "path":
            print(config_path())
        elif args.config_command == "show":
            print(config_text(load_config()))
        else:
            print(write_config(load_config(), args.path))
        return
    if args.command == "model":
        target = install_model(args.path)
        print(f"installed {target}")
        return
    if args.command == "list-cameras":
        raise SystemExit(list_cameras())
    if args.command == "doctor":
        try:
            config = load_config()
            checks, code = collect_checks(
                config, check_camera=not args.runtime, check_input=not args.runtime
            )
        except ValueError as exc:
            print(exc)
            raise SystemExit(6) from exc
        if args.json:
            from .diagnostics import report_json

            print(json.dumps(report_json(config, checks, runtime=args.runtime), indent=2))
        else:
            print_report(checks)
        raise SystemExit(0 if args.runtime and code == DoctorCode.OPTIONAL_ACCELERATION else code)
    if args.command == "calibrate":
        raise SystemExit(calibrate(load_config()))
    if args.command == "replay":
        print(json.dumps(run_replay(args.fixture, args.engine), indent=2))
        return
    if args.command == "benchmark":
        result = run_benchmark(args.engine, args.output, args.compute, args.compare_compute)
        print_benchmark(result)
        return
    if args.command == "self-test":
        engine_request = args.engine or args.global_engine or "auto"
        result = run_self_test(require_mojo=engine_request == "mojo", engine_request=engine_request)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["passed"] else 1)
    if args.command == "update":
        raise SystemExit(run_update(args.check))
    if args.command == "run":
        engine = args.engine or args.global_engine
        config = load_config(args.config)
        config = with_overrides(
            config,
            index=args.camera,
            engine=engine,
            backend=args.backend,
            preview=args.preview,
            armed=args.armed or None,
            log_level=args.log_level,
            mode=args.compute,
            profile=args.profile,
            monitor=args.monitor,
        )
        configure_logging(config.log_level)
        try:
            armed_override = True if args.armed else None
            raise SystemExit(
                Application(config, engine, args.backend, args.preview, armed_override).run()
            )
        except KeyboardInterrupt:
            logging.getLogger(__name__).info("stopped")
        return
