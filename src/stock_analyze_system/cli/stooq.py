"""stooq サブコマンド（historical price download）."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date as date_type, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from sqlalchemy.exc import SQLAlchemyError

from stock_analyze_system.ingestion.stooq import (
    StooqAuthError,
    StooqNotFoundError,
    StooqParseError,
    StooqRateLimitError,
    StooqPriceClient,
)

if TYPE_CHECKING:
    from stock_analyze_system.cli.container import ServiceContainer

logger = logging.getLogger(__name__)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("stooq", help="stooq.com historical price operations")
    sub = parser.add_subparsers(dest="action", required=True)

    dl = sub.add_parser("download", help="Download historical prices from stooq")
    dl.add_argument("--years", type=int, default=10, help="Keep only last N years")
    dl.add_argument(
        "--apikey", type=str,
        default=os.getenv("STOOQ_API_KEY"),
        help="stooq API key (fallback: STOOQ_API_KEY env)",
    )
    dl.add_argument("--limit", type=int, default=None, help="Limit number of companies (for testing)")
    dl.add_argument("--skip-existing", action="store_true", help="Skip companies already in price_history")
    dl.add_argument(
        "--retry-incomplete", 
        action="store_true", 
        help="Retry only incomplete companies (data gaps, skip new listings)"
    )
    dl.add_argument(
        "--incomplete-threshold-days",
        type=int,
        default=90,
        help="Days threshold to consider a company as new listing (default: 90)"
    )
    dl.add_argument(
        "--incomplete-threshold-rows",
        type=int,
        default=250,
        help="Row count threshold to consider data complete (default: 250)"
    )
    dl.add_argument("--dry-run", action="store_true", help="Skip DB writes")

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: "ServiceContainer") -> None:
    if args.action == "download":
        await _handle_download(args, services)


async def _handle_download(args: argparse.Namespace, services: "ServiceContainer") -> None:
    if services.session is None:
        print("ERROR: Database session is not available", file=sys.stderr)
        sys.exit(1)
    
    # Double-check env var (parser default reads before .env is loaded by load_config())
    api_key = args.apikey or os.getenv("STOOQ_API_KEY")
    if not api_key:
        print("ERROR: --apikey or STOOQ_API_KEY env var is required", file=sys.stderr)
        sys.exit(1)
    
    years = args.years
    limit = args.limit
    skip_existing = args.skip_existing
    retry_incomplete = args.retry_incomplete
    incomplete_threshold_days = args.incomplete_threshold_days
    incomplete_threshold_rows = args.incomplete_threshold_rows
    dry_run = args.dry_run

    from stock_analyze_system.models.company import Company
    from stock_analyze_system.repositories.price_history import PriceHistoryRepository
    from sqlalchemy import select

    repo = PriceHistoryRepository(services.session)

    # Fetch US companies with tickers
    stmt = select(Company).where(Company.id.like("US_%"), Company.ticker.is_not(None))
    if limit:
        stmt = stmt.limit(limit)
    result = await services.session.execute(stmt)
    companies = list(result.scalars().all())
    
    # Skip existing if requested
    if skip_existing:
        filtered = []
        for company in companies:
            exists = await repo.exists_for_company(company.id)
            if not exists:
                filtered.append(company)
        skipped_count = len(companies) - len(filtered)
        if skipped_count:
            logger.info("Skipping %d companies already in price_history", skipped_count)
        companies = filtered
    
    # Retry incomplete companies (data gaps only, skip new listings)
    if retry_incomplete:
        stats = await repo.get_company_stats()
        incomplete = {
            cid: stat for cid, stat in stats.items()
            if stat["span_days"] >= incomplete_threshold_days 
            and stat["rows"] < incomplete_threshold_rows
        }
        
        company_map = {c.id: c for c in companies}
        retry_companies = []
        new_listings = []
        
        for cid, stat in incomplete.items():
            if cid in company_map:
                retry_companies.append(company_map[cid])
        
        for cid, stat in stats.items():
            if stat["span_days"] < incomplete_threshold_days:
                if cid in company_map:
                    new_listings.append({
                        "company_id": cid,
                        "ticker": company_map[cid].ticker,
                        "rows": stat["rows"],
                        "span_days": stat["span_days"],
                    })
        
        companies = retry_companies
        logger.info(
            "Retrying %d incomplete companies (skipped %d new listings)", 
            len(retry_companies), len(new_listings)
        )

    total = len(companies)
    logger.info("stooq download: %d companies to process", total)

    client = StooqPriceClient(api_key=api_key, rate=1.0)
    errors: list[dict] = []
    success = 0
    t0 = time.perf_counter()

    for idx, company in enumerate(companies, 1):
        ticker = company.ticker
        logger.info("[%d/%d] Processing %s (%s)", idx, total, company.id, ticker)
        try:
            rows = await client.fetch_history(ticker, years=years)
            
            if not rows:
                errors.append({"ticker": ticker, "company_id": company.id, "reason": "EMPTY", "timestamp": datetime.now(timezone.utc).isoformat()})
                continue
            
            # Fill company_id
            for row in rows:
                row["company_id"] = company.id
            
            if not dry_run:
                await repo.upsert_many(rows)
                await repo._session.commit()
            
            success += 1
        except StooqAuthError as exc:
            # Auth error is global (not ticker-specific): fail-fast
            await client.close()
            error_msg = f"Authentication failed for stooq API key: {exc}"
            logger.error(error_msg)
            print(f"ERROR: {error_msg}", file=sys.stderr)
            errors.append({"ticker": ticker, "company_id": company.id, "reason": "AUTH_ERROR", "timestamp": datetime.now(timezone.utc).isoformat()})
            _write_errors(errors)
            sys.exit(1)
        except StooqRateLimitError as exc:
            # Rate limit is global: fail-fast with clear message
            await client.close()
            print(f"\nERROR: {exc}", file=sys.stderr)
            print("Stooq daily hit limit has been reached.", file=sys.stderr)
            print("Please retry tomorrow after the limit resets.", file=sys.stderr)
            _write_errors(errors)
            sys.exit(3)
        except StooqNotFoundError:
            errors.append({"ticker": ticker, "company_id": company.id, "reason": "NOT_FOUND", "timestamp": datetime.now(timezone.utc).isoformat()})
        except StooqParseError as exc:
            errors.append({"ticker": ticker, "company_id": company.id, "reason": f"PARSE_ERROR: {exc}", "timestamp": datetime.now(timezone.utc).isoformat()})
        except httpx.TimeoutException:
            errors.append({"ticker": ticker, "company_id": company.id, "reason": "TIMEOUT", "timestamp": datetime.now(timezone.utc).isoformat()})
        except SQLAlchemyError as exc:
            await repo._session.rollback()
            errors.append({"ticker": ticker, "company_id": company.id, "reason": f"DB_ERROR: {exc}", "timestamp": datetime.now(timezone.utc).isoformat()})
            logger.warning("stooq DB error for %s: %s", company.id, exc, exc_info=exc)
        except Exception as exc:  # noqa: BLE001
            await repo._session.rollback()
            errors.append({"ticker": ticker, "company_id": company.id, "reason": f"UNKNOWN: {exc}", "timestamp": datetime.now(timezone.utc).isoformat()})
            logger.warning("stooq download failed for %s: %s", company.id, exc, exc_info=exc)

    await client.close()
    elapsed = time.perf_counter() - t0

    # Report
    print(f"\nDownload Summary\n{'='*40}")
    print(f"Total companies: {total}")
    print(f"Success: {success}")
    print(f"Failed: {len(errors)}")
    print(f"Elapsed: {elapsed:.1f}s")
    
    if errors:
        _write_errors(errors)
    
    # Write incomplete report (always, for visibility)
    stats = await repo.get_company_stats()
    new_listings = []
    data_gaps = []
    not_found_errors = [e for e in errors if e.get("reason") == "NOT_FOUND"]
    
    for cid, stat in stats.items():
        if stat["span_days"] < incomplete_threshold_days:
            new_listings.append({
                "company_id": cid,
                "rows": stat["rows"],
                "span_days": stat["span_days"],
            })
        elif stat["rows"] < incomplete_threshold_rows:
            data_gaps.append({
                "company_id": cid,
                "rows": stat["rows"],
                "span_days": stat["span_days"],
            })
    
    _write_incomplete_report(new_listings, data_gaps, not_found_errors)
    
    return None


def _write_errors(errors: list[dict]) -> None:
    """Write errors to JSON file, ensuring directory exists."""
    error_dir = Path("data")
    error_dir.mkdir(parents=True, exist_ok=True)
    error_path = error_dir / f"stooq_errors_{date_type.today().isoformat()}.json"
    with open(error_path, "w") as f:
        json.dump(errors, f, indent=2)
    print(f"Errors saved to: {error_path}")


def _write_incomplete_report(
    new_listings: list[dict],
    data_gaps: list[dict],
    not_found: list[dict],
) -> None:
    """Write incomplete companies report to JSON file."""
    report_dir = Path("data")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"stooq_incomplete_{date_type.today().isoformat()}.json"
    report = {
        "new_listings": new_listings,
        "data_gaps": data_gaps,
        "not_found": not_found,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Incomplete report saved to: {report_path}")
