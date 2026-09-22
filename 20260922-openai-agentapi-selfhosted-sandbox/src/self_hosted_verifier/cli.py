from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .api import OpenAISessionApi
from .config import Config, ConfigurationError
from .controller import make_controller
from .docker import SubprocessDocker
from .models import VerificationReport
from .scenarios import VerificationRunner, build_fake_controller, write_report
from .storage import LifecycleLogger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify OpenAI Agents API self-hosted sessions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="create a session and start its executor")
    create.add_argument("--input", help="optional first message")

    resume = subparsers.add_parser("resume", help="resume a saved session")
    resume.add_argument("session_id")
    resume.add_argument("--input", required=True)

    stop = subparsers.add_parser("stop", help="stop the executor for a session")
    stop.add_argument("session_id")

    verify = subparsers.add_parser("verify", help="run the fixed verification scenarios")
    verify.add_argument("--mock", action="store_true", help="run deterministic local scenarios")
    verify.add_argument("--output", type=Path, help="write a JSON report to this path")
    return parser


def _real_controller(config: Config):
    config.ensure_directories()
    logger = LifecycleLogger(
        config.log_dir / "container-lifecycle.jsonl",
        [config.openai_api_key, config.executor_api_key],
    )
    return make_controller(config, OpenAISessionApi(config.openai_api_key), SubprocessDocker(), logger)


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = Config.from_env()
    except ConfigurationError as exc:
        if args.command == "verify" and args.mock:
            config = None
        elif args.command == "verify":
            report = VerificationReport(mode="real", not_run_reason=f"Not run: {exc}")
            output = args.output or Path("reports/real-api-report.json")
            write_report(report, output)
            _print_json(report.to_dict())
            return 2
        else:
            print(f"configuration error: {exc}", file=sys.stderr)
            return 2

    if args.command == "verify":
        if args.mock:
            import tempfile

            root = Path(tempfile.mkdtemp(prefix="self-hosted-verifier-"))
            controller, docker, api = build_fake_controller(root)
            report = VerificationRunner(controller, docker, api).run_all()
            output = args.output or root / "mock-report.json"
        else:
            if config is None:
                raise AssertionError("configuration should be present here")
            report = VerificationReport(
                mode="real",
                not_run_reason="Real API execution is explicit and requires valid credentials; use `verify --mock` for local tests.",
            )
            try:
                controller = _real_controller(config)
                runner = VerificationRunner(
                    controller, controller.executors.docker, controller.api, config.model, mode="real"
                )
                report = runner.run_all()
            except Exception as exc:
                report.not_run_reason = f"Real API verification was not completed: {type(exc).__name__}: {exc}"
            output = args.output or config.report_dir / "real-api-report.json"
        write_report(report, output)
        _print_json(report.to_dict())
        return 0 if report.passed else 2

    if config is None:
        print("configuration is required for this command", file=sys.stderr)
        return 2
    controller = _real_controller(config)
    if args.command == "create":
        record = controller.create(
            config.model,
            config.workspace_directory,
            instructions=config.agent_instructions,
            capability_directories=config.capability_directories,
        )
        payload = record.to_dict()
        if args.input:
            payload["turn"] = controller.send(record.session_id, args.input).__dict__
        _print_json(payload)
    elif args.command == "resume":
        result = controller.send(args.session_id, args.input)
        _print_json(result.__dict__)
    elif args.command == "stop":
        controller.stop(args.session_id)
        _print_json({"session_id": args.session_id, "stopped": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
