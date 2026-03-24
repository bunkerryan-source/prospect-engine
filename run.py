"""
Prospect Engine CLI — argument parsing, database commands, and pipeline orchestration.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date

import yaml
from dotenv import load_dotenv

from models import ProspectRecord, deduplicate
from modules.web_search import WebSearchModule
from modules.sqep import SQEPModule
from modules.import_search import ImportSearchModule
from modules.apollo import ApolloModule
from enrichment.hunter import HunterEnrichment
from scoring.scorer import score_prospects
from persistence.database import ProspectDB
from output.exporter import export_xlsx, export_csv
from utils.search import SearchClient
from utils.checkpoints import CheckpointManager
from utils.credits import estimate_credits, format_credit_warning, format_credit_summary


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Prospect Engine — find, enrich, and score sales prospects"
    )

    # Scraping group
    scraping = parser.add_argument_group("Scraping")
    scraping.add_argument("--states", type=str, default=None,
                          help="Comma-separated list of state list names from config")
    scraping.add_argument("--nationwide", action="store_true",
                          help="Search all 50 US states")
    scraping.add_argument("--verticals", type=str, default=None,
                          help="Comma-separated list of verticals to search")
    scraping.add_argument("--channels", type=str, default=None,
                          help="Comma-separated list of channels to use")
    scraping.add_argument("--skip-enrichment", action="store_true",
                          help="Skip Hunter.io email enrichment")
    scraping.add_argument("--skip-scoring", action="store_true",
                          help="Skip lead scoring")
    scraping.add_argument("--dry-run", action="store_true",
                          help="Show credit estimates without running")
    scraping.add_argument("--resume", action="store_true",
                          help="Resume from last checkpoint")

    # Verification group
    verification = parser.add_argument_group("Verification")
    verification.add_argument("--verify-emails", action="store_true",
                              help="Run email verification on existing prospects")
    verification.add_argument("--tier", type=str, default=None,
                              help="Tier to verify (e.g. HOT, WARM)")
    verification.add_argument("--all", action="store_true", dest="all_tiers",
                              help="Verify all tiers")

    # Database group
    database = parser.add_argument_group("Database")
    database.add_argument("--set-status", nargs=2, metavar=("NAME", "STATUS"),
                          help="Set prospect status by name")
    database.add_argument("--pipeline", action="store_true",
                          help="Show pipeline statistics")
    database.add_argument("--list-status", type=str, metavar="STATUS",
                          help="List prospects with given status")
    database.add_argument("--search", type=str,
                          help="Search prospects by keyword")
    database.add_argument("--db-stats", action="store_true",
                          help="Show database statistics")
    database.add_argument("--export-db", type=str, metavar="PATH",
                          help="Export all prospects to CSV")
    database.add_argument("--reset-db", action="store_true",
                          help="Reset database (requires --confirm)")
    database.add_argument("--confirm", action="store_true",
                          help="Confirm destructive operations")
    database.add_argument("--note", type=str, default="",
                          help="Note for status changes")

    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(path="config.yaml") -> dict:
    """Load .env and config.yaml, returning the config dict."""
    load_dotenv()
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


# ---------------------------------------------------------------------------
# State resolution
# ---------------------------------------------------------------------------

def resolve_states(config: dict, states_arg: str | None, nationwide: bool) -> list[str]:
    """Resolve the target state list from CLI args and config."""
    if nationwide:
        return list(ALL_STATES)

    state_lists = config.get("state_lists", {})

    if states_arg:
        names = [n.strip() for n in states_arg.split(",")]
        result = []
        seen = set()
        for name in names:
            if name not in state_lists:
                print(f"Error: state list '{name}' not found in config. "
                      f"Available: {', '.join(state_lists.keys())}")
                sys.exit(1)
            for s in state_lists[name]["states"]:
                if s not in seen:
                    result.append(s)
                    seen.add(s)
        return result

    # Find default list
    for list_name, list_cfg in state_lists.items():
        if list_cfg.get("default"):
            return list_cfg["states"]

    print("Error: no --states specified and no default state list in config.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# API key checking
# ---------------------------------------------------------------------------

def check_api_keys() -> dict:
    """Check for API keys in environment. Returns dict of available keys."""
    keys = {
        "serpapi": os.environ.get("SERPAPI_KEY"),
        "apollo": os.environ.get("APOLLO_API_KEY"),
        "hunter": os.environ.get("HUNTER_API_KEY"),
    }

    missing = []
    for name, env_var in [("serpapi", "SERPAPI_KEY"), ("apollo", "APOLLO_API_KEY"),
                          ("hunter", "HUNTER_API_KEY")]:
        if keys[name] is None:
            missing.append(env_var)
            print(f"Warning: {env_var} not set — {name} features will be skipped.")

    if len(missing) == 3:
        print("Error: No API keys found. At least one of SERPAPI_KEY, "
              "APOLLO_API_KEY, or HUNTER_API_KEY must be set.")
        sys.exit(1)

    return keys


# ---------------------------------------------------------------------------
# Database commands
# ---------------------------------------------------------------------------

def handle_db_command(command: str, db: ProspectDB, **kwargs):
    """Dispatch to appropriate DB method and print results."""
    if command == "set_status":
        name = kwargs["name"]
        status = kwargs["status"]
        note = kwargs.get("note", "")
        count = db.set_status(name, status, note)
        print(f"Updated {count} prospect(s) matching '{name}' to status '{status}'.")

    elif command == "pipeline":
        stats = db.get_pipeline_stats()
        print("\n=== Pipeline Statistics ===")
        print("\nStatus Breakdown:")
        for status, count in stats.get("status_counts", {}).items():
            print(f"  {status:12s} {count}")
        print("\nTier Distribution:")
        for tier, count in stats.get("tier_counts", {}).items():
            print(f"  {tier:12s} {count}")

    elif command == "list_status":
        status = kwargs["status"]
        prospects = db.get_by_status(status)
        print(f"\n=== Prospects with status '{status}' ({len(prospects)}) ===")
        for p in prospects:
            print(f"  {p['company_name']:40s} | {p.get('state', ''):5s} | "
                  f"Score: {p.get('score', 0):3d} | {p.get('tier', '')}")

    elif command == "search":
        query = kwargs["query"]
        results = db.search(query)
        print(f"\n=== Search results for '{query}' ({len(results)}) ===")
        for p in results:
            print(f"  {p['company_name']:40s} | {p.get('state', ''):5s} | "
                  f"Score: {p.get('score', 0):3d} | {p.get('tier', '')} | "
                  f"Status: {p.get('status', '')}")
        return results

    elif command == "db_stats":
        stats = db.get_db_stats()
        print("\n=== Database Statistics ===")
        print(f"  Total prospects: {stats['total']}")
        print(f"  Average score:   {stats['avg_score']:.1f}" if stats['avg_score'] else
              f"  Average score:   N/A")
        print("  Tier distribution:")
        for tier, count in stats.get("tier_distribution", {}).items():
            print(f"    {tier:12s} {count}")

    elif command == "export_db":
        path = kwargs["path"]
        prospects = db.get_prospects_for_export()
        export_csv(path, prospects)
        print(f"Exported {len(prospects)} prospects to {path}")

    elif command == "reset_db":
        confirm = kwargs.get("confirm", False)
        if not confirm:
            print("Error: --reset-db requires --confirm flag.")
            return
        db.reset(confirm=True)
        print("Database has been reset.")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline(
    config_path: str = "config.yaml",
    states_arg: str | None = None,
    nationwide: bool = False,
    verticals: str | None = None,
    channels: str | None = None,
    skip_enrichment: bool = False,
    skip_scoring: bool = False,
    dry_run: bool = False,
    resume: bool = False,
):
    """Run the full prospect scraping pipeline."""
    # 1. Load config
    config = load_config(config_path)

    # 2. Check API keys
    keys = check_api_keys()

    # 3. Resolve states
    states = resolve_states(config, states_arg, nationwide)
    print(f"Target states ({len(states)}): {', '.join(states)}")

    # 4. Determine active verticals
    all_verticals = list(config.get("verticals", {}).keys())
    if verticals:
        active_verticals = [v.strip() for v in verticals.split(",")]
    else:
        active_verticals = all_verticals
    print(f"Active verticals: {', '.join(active_verticals)}")

    # 5. Determine active channels
    all_channels = []
    if keys["serpapi"]:
        all_channels.extend(["web_search", "sqep", "import_search"])
    if keys["apollo"]:
        all_channels.append("apollo")
    if channels:
        active_channels = [c.strip() for c in channels.split(",")]
    else:
        active_channels = all_channels
    print(f"Active channels: {', '.join(active_channels)}")

    # 6. Estimate credits
    estimates = estimate_credits(config, active_verticals, states, active_channels)
    warning_text = format_credit_warning(estimates)
    print(f"\n{warning_text}\n")

    # 7. Dry run — print and return
    if dry_run:
        print("Estimated credit usage shown above. Dry run — no actions taken.")
        return

    # 8. Prompt user
    answer = input("Proceed? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        return

    # 9. Start timer
    start_time = time.time()

    # 10. Init checkpoint manager
    checkpoint = CheckpointManager(config)
    checkpoint.start_run()

    # 11. Resume: load completed modules
    completed_modules = set()
    if resume:
        completed_modules = checkpoint.get_completed_modules()
        if completed_modules:
            print(f"Resuming — skipping completed modules: {', '.join(sorted(completed_modules))}")

    # 12. Run modules
    all_prospects: list[ProspectRecord] = []
    serpapi_credits = 0

    # -- web_search --
    if "web_search" in active_channels and keys["serpapi"]:
        if "web_search" not in completed_modules:
            print("\n--- Running Web Search module ---")
            search_client = SearchClient(config, keys["serpapi"])
            module = WebSearchModule(config, states, search_client)
            prospects = module.run(active_verticals)
            serpapi_credits += search_client.call_count
            checkpoint.save("web_search",
                            [p.to_dict() for p in prospects],
                            credits_used=search_client.call_count)
            all_prospects.extend(prospects)
            print(f"  Found {len(prospects)} prospects ({search_client.call_count} API calls)")
        else:
            data = checkpoint.load("web_search")
            all_prospects.extend([ProspectRecord(**d) for d in data])
            print("Loaded web_search from checkpoint.")

    # -- sqep --
    if "sqep" in active_channels and keys["serpapi"]:
        if "sqep" not in completed_modules:
            print("\n--- Running SQEP module ---")
            search_client = SearchClient(config, keys["serpapi"])
            module = SQEPModule(config, states, search_client)
            prospects = module.run(active_verticals)
            serpapi_credits += search_client.call_count
            checkpoint.save("sqep",
                            [p.to_dict() for p in prospects],
                            credits_used=search_client.call_count)
            all_prospects.extend(prospects)
            print(f"  Found {len(prospects)} prospects ({search_client.call_count} API calls)")
        else:
            data = checkpoint.load("sqep")
            all_prospects.extend([ProspectRecord(**d) for d in data])
            print("Loaded sqep from checkpoint.")

    # -- import_search --
    if "import_search" in active_channels and keys["serpapi"]:
        if "import_search" not in completed_modules:
            print("\n--- Running Import Search module ---")
            search_client = SearchClient(config, keys["serpapi"])
            module = ImportSearchModule(config, states, search_client)
            prospects = module.run(active_verticals)
            serpapi_credits += search_client.call_count
            checkpoint.save("import_search",
                            [p.to_dict() for p in prospects],
                            credits_used=search_client.call_count)
            all_prospects.extend(prospects)
            print(f"  Found {len(prospects)} prospects ({search_client.call_count} API calls)")
        else:
            data = checkpoint.load("import_search")
            all_prospects.extend([ProspectRecord(**d) for d in data])
            print("Loaded import_search from checkpoint.")

    # -- apollo --
    apollo_credits = 0
    if "apollo" in active_channels and keys["apollo"]:
        if "apollo" not in completed_modules:
            print("\n--- Running Apollo module ---")
            module = ApolloModule(config, states, keys["apollo"])
            prospects = module.run(active_verticals)
            apollo_credits = module.company_search_credits + module.people_search_credits
            checkpoint.save("apollo",
                            [p.to_dict() for p in prospects],
                            credits_used=apollo_credits)
            all_prospects.extend(prospects)
            print(f"  Found {len(prospects)} prospects ({apollo_credits} API calls)")
        else:
            data = checkpoint.load("apollo")
            all_prospects.extend([ProspectRecord(**d) for d in data])
            print("Loaded apollo from checkpoint.")

    raw_count = len(all_prospects)
    print(f"\nTotal raw prospects: {raw_count}")

    # 13-14. Deduplicate
    if "dedup" not in completed_modules:
        all_prospects = deduplicate(all_prospects)
        checkpoint.save("dedup", [p.to_dict() for p in all_prospects])
        print(f"After deduplication: {len(all_prospects)}")
    else:
        data = checkpoint.load("dedup")
        all_prospects = [ProspectRecord(**d) for d in data]
        print(f"Loaded dedup from checkpoint: {len(all_prospects)} prospects")

    dedup_count = len(all_prospects)

    # 15. Hunter enrichment
    hunter_search_credits = 0
    if not skip_enrichment and keys.get("hunter"):
        if "hunter" not in completed_modules:
            print("\n--- Running Hunter enrichment ---")
            hunter = HunterEnrichment(config, keys["hunter"])
            all_prospects = hunter.enrich(all_prospects)
            hunter_search_credits = hunter.search_credits_used
            checkpoint.save("hunter",
                            [p.to_dict() for p in all_prospects],
                            credits_used=hunter_search_credits)
            print(f"  Hunter searches used: {hunter_search_credits}")
        else:
            data = checkpoint.load("hunter")
            all_prospects = [ProspectRecord(**d) for d in data]
            print("Loaded hunter from checkpoint.")

    # 16. Score
    if not skip_scoring:
        print("\n--- Scoring prospects ---")
        all_prospects = score_prospects(all_prospects, config, states)
        print(f"  Scored {len(all_prospects)} prospects")

    # 17. Database upsert
    db_path = config.get("database", {}).get("path", "prospects.db")
    db = ProspectDB(db_path)
    new_count, updated_count = db.upsert(all_prospects)
    print(f"\nDatabase: {new_count} new, {updated_count} updated")

    # 18. Record run history
    tier_counts = {"HOT": 0, "WARM": 0, "NURTURE": 0, "PARK": 0}
    for p in all_prospects:
        tier = p.tier.upper() if p.tier else "PARK"
        if tier in tier_counts:
            tier_counts[tier] += 1

    scores = [p.score for p in all_prospects if p.score]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    duration = int(time.time() - start_time)

    db.record_run(
        states=", ".join(states),
        verticals=", ".join(active_verticals),
        channels=", ".join(active_channels),
        raw_count=raw_count,
        dedup_count=dedup_count,
        new_count=new_count,
        updated_count=updated_count,
        hot=tier_counts["HOT"],
        warm=tier_counts["WARM"],
        nurture=tier_counts["NURTURE"],
        park=tier_counts["PARK"],
        avg_score=avg_score,
        duration=duration,
        serpapi=serpapi_credits,
        apollo=apollo_credits,
        hunter_search=hunter_search_credits,
    )

    # 19. Export
    run_date = date.today().isoformat()
    output_dir = config.get("output", {}).get("directory", "output")
    os.makedirs(output_dir, exist_ok=True)
    prefix = config.get("output", {}).get("filename_prefix", "prospects")
    formats = config.get("output", {}).get("formats", ["xlsx", "csv"])

    all_db_prospects = db.get_prospects_for_export()
    run_history = db.get_run_history()
    pipeline_stats = db.get_pipeline_stats()

    if "xlsx" in formats:
        xlsx_path = os.path.join(output_dir, f"{prefix}_{run_date}.xlsx")
        export_xlsx(xlsx_path, all_db_prospects, run_history, pipeline_stats, run_date)
        print(f"Exported: {xlsx_path}")

    if "csv" in formats:
        csv_path = os.path.join(output_dir, f"{prefix}_{run_date}.csv")
        export_csv(csv_path, all_db_prospects)
        print(f"Exported: {csv_path}")

    # 20. Credit summary
    actuals = {
        "serpapi": serpapi_credits,
        "apollo": apollo_credits,
        "hunter_search": hunter_search_credits,
        "hunter_verify": 0,
    }
    limits = {
        "serpapi": config.get("search_api", {}).get("plan_limit", 0),
        "apollo": config.get("apollo", {}).get("plan_limit", 0),
        "hunter_search": config.get("hunter", {}).get("search_credit_limit", 0),
        "hunter_verify": config.get("hunter", {}).get("verification_credit_limit", 0),
    }
    print(f"\n{format_credit_summary(actuals, limits)}")
    print(f"Pipeline completed in {duration}s")

    # 21. Cleanup checkpoints
    keep = config.get("checkpoints", {}).get("keep_on_success", False)
    checkpoint.cleanup(keep=keep)


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

def run_verification(
    config_path: str = "config.yaml",
    tier: str | None = None,
    all_tiers: bool = False,
):
    """Run email verification on existing DB prospects."""
    config = load_config(config_path)
    keys = check_api_keys()

    if not keys.get("hunter"):
        print("Error: HUNTER_API_KEY required for email verification.")
        sys.exit(1)

    db_path = config.get("database", {}).get("path", "prospects.db")
    db = ProspectDB(db_path)

    # Determine tiers
    if all_tiers:
        tiers = ["HOT", "WARM", "NURTURE", "PARK"]
    elif tier:
        tiers = [tier.upper()]
    else:
        tiers = ["HOT", "WARM"]

    print(f"Verifying emails for tiers: {', '.join(tiers)}")

    # Get prospects needing verification
    hunter_cfg = config.get("hunter", {})
    limit = hunter_cfg.get("max_verifications_per_run", 50)
    prospects = db.get_for_verification(tiers, limit)
    print(f"Found {len(prospects)} prospects to verify (limit: {limit})")

    if not prospects:
        print("No prospects need verification.")
        return

    # Build email list
    emails_with_ids = [(p["id"], p["contact_email"]) for p in prospects]

    # Run verification
    hunter = HunterEnrichment(config, keys["hunter"])
    results = hunter.verify_batch(emails_with_ids, limit)

    # Update DB
    for prospect_id, status in results.items():
        db.update_email_verified(prospect_id, status)

    # Print summary
    status_counts: dict[str, int] = {}
    for status in results.values():
        status_counts[status] = status_counts.get(status, 0) + 1

    print(f"\nVerification complete: {len(results)} emails checked")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    print(f"Hunter verification credits used: {hunter.verify_credits_used}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """CLI entry point — routes to DB commands, verification, or pipeline."""
    args = parse_args()

    # --- DB commands ---
    if args.set_status:
        config = load_config()
        db = ProspectDB(config.get("database", {}).get("path", "prospects.db"))
        handle_db_command("set_status", db,
                          name=args.set_status[0],
                          status=args.set_status[1],
                          note=args.note)
        return

    if args.pipeline:
        config = load_config()
        db = ProspectDB(config.get("database", {}).get("path", "prospects.db"))
        handle_db_command("pipeline", db)
        return

    if args.list_status:
        config = load_config()
        db = ProspectDB(config.get("database", {}).get("path", "prospects.db"))
        handle_db_command("list_status", db, status=args.list_status)
        return

    if args.search:
        config = load_config()
        db = ProspectDB(config.get("database", {}).get("path", "prospects.db"))
        handle_db_command("search", db, query=args.search)
        return

    if args.db_stats:
        config = load_config()
        db = ProspectDB(config.get("database", {}).get("path", "prospects.db"))
        handle_db_command("db_stats", db)
        return

    if args.export_db:
        config = load_config()
        db = ProspectDB(config.get("database", {}).get("path", "prospects.db"))
        handle_db_command("export_db", db, path=args.export_db)
        return

    if args.reset_db:
        config = load_config()
        db = ProspectDB(config.get("database", {}).get("path", "prospects.db"))
        handle_db_command("reset_db", db, confirm=args.confirm)
        return

    # --- Email verification ---
    if args.verify_emails:
        run_verification(tier=args.tier, all_tiers=args.all_tiers)
        return

    # --- Pipeline (default) ---
    run_pipeline(
        states_arg=args.states,
        nationwide=args.nationwide,
        verticals=args.verticals,
        channels=args.channels,
        skip_enrichment=args.skip_enrichment,
        skip_scoring=args.skip_scoring,
        dry_run=args.dry_run,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
