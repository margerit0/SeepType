"""Prepare word-list coverage and bounded requests; generation is opt-in and external."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.lexicon_expand.catalog import prepare
from tools.lexicon_expand.common import CACHE, Invalid
from tools.lexicon_expand.generation import generate
from tools.lexicon_expand.planning import make_plan, make_repair_plan
from tools.lexicon_expand.quality import audit_file
from tools.lexicon_expand.evaluation import make_comparison
from tools.lexicon_expand.provider import load_config, read_key
from tools.lexicon_expand.sources import fetch_sources, verify_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch-sources", help="Restore pinned public source snapshots")
    verify = commands.add_parser("verify-sources", help="Verify local source checksums")
    verify.add_argument("--full", action="store_true", help="Also reproduce excerpts from full snapshots")
    build = commands.add_parser("prepare", help="Build target catalog and reference coverage, offline")
    build.add_argument("--output", type=Path, default=CACHE / "prepared")
    plan = commands.add_parser("plan", help="Build inspectable request JSONL without a model call")
    plan.add_argument("--prepared", type=Path, default=CACHE / "prepared")
    plan.add_argument("--output", type=Path)
    plan.add_argument("--prompt-version", type=int, choices=[1, 2, 3, 4], default=2)
    plan.add_argument("--pack", choices=["ielts", "cefr"], default="ielts")
    plan.add_argument("--words", type=int, default=200)
    plan.add_argument("--scene-terms", type=int, default=100)
    plan.add_argument("--batch-size", type=int, default=10)
    repair = commands.add_parser('repair-plan', help='Plan only reviewed revision senses; never send or adopt results')
    repair.add_argument('--review', type=Path, required=True, help='Explicit reviewed batch (historical inputs are not bundled)')
    repair.add_argument('--output', type=Path, default=CACHE / 'repair-v2')
    repair.add_argument('--prepared', type=Path, default=CACHE / 'prepared')
    repair.add_argument('--batch-size', type=int, default=5)
    audit = commands.add_parser('quality-audit', help='Check pronunciation and case without semantic approval')
    audit.add_argument('--drafts', type=Path, required=True)
    audit.add_argument('--output', type=Path, required=True)
    audit.add_argument('--prepared', type=Path, default=CACHE / 'prepared')
    audit.add_argument('--quality-version', type=int, choices=[1, 2], default=2)
    comparison = commands.add_parser('comparison-plan', help='Prepare two same-target plans excluding prompt examples')
    comparison.add_argument('--output', type=Path, default=CACHE / 'comparison-v2-final')
    config = commands.add_parser("config", help="Validate endpoint configuration without connecting")
    config.add_argument("path", type=Path)
    config.add_argument("--check-key", action="store_true", help="Check only whether the named key is available")
    run = commands.add_parser("generate", help="Preview a run; --execute sends requests to the configured API")
    run.add_argument("--plan", type=Path, default=CACHE / "pilot-v2")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, default=CACHE / "pilot-v2-results")
    run.add_argument("--execute", action="store_true")
    run.add_argument("--max-items", type=int, default=300)
    run.add_argument("--max-requests", type=int, default=60)
    run.add_argument("--max-output-budget", type=int, default=245760)
    run.add_argument("--retry-failed", action="store_true")
    run.add_argument("--retry-uncertain", action="store_true")
    args = parser.parse_args()
    if args.command == "fetch-sources":
        result = {"sources": fetch_sources(), "model_requests": 0}
    elif args.command == "verify-sources":
        lock = verify_sources(full=args.full)
        result = {"verified": True, "full_snapshots_checked": args.full,
                  "sources": [source["id"] for source in lock["sources"]], "model_requests": 0}
    elif args.command == "prepare":
        summary = prepare(args.output)
        result = {"coverage": summary["coverage"], "scenario_topics": len(summary["scenarios"]),
                  "output": str(args.output.resolve()), "model_requests": 0, "generated_translations": 0}
    elif args.command == "plan":
        result = make_plan(args.prepared, args.output, word_count=args.words, scene_count=args.scene_terms,
                           batch_size=args.batch_size, pack=args.pack, prompt_version=args.prompt_version)
    elif args.command == 'repair-plan':
        result = make_repair_plan(args.review, args.output, prepared=args.prepared, batch_size=args.batch_size)
    elif args.command == 'quality-audit':
        result = audit_file(args.drafts, args.output, args.prepared, version=args.quality_version)
    elif args.command == 'comparison-plan':
        result = make_comparison(args.output)
    elif args.command == "config":
        result = load_config(args.path)
        result["network_requests"] = 0
        if args.check_key:
            read_key(result["api_key_env"])
            result["key_available"] = True
    else:
        result = generate(args.plan, args.config, args.output, execute=args.execute, max_items=args.max_items,
                          max_requests=args.max_requests, max_output_budget=args.max_output_budget,
                          retry_failed=args.retry_failed, retry_uncertain=args.retry_uncertain,
                          progress=lambda event: print(json.dumps(event, ensure_ascii=False), flush=True))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except Invalid as error:
        print(f"Lexicon expansion: {error}", file=sys.stderr)
        raise SystemExit(1)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Lexicon expansion could not read or validate its inputs ({type(error).__name__}).", file=sys.stderr)
        raise SystemExit(1)
