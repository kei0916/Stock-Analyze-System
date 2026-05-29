"""Screening read-only query service."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import func

from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.services.analysis_target import AnalysisTargetService

logger = logging.getLogger(__name__)


SCREENING_NUMERIC_FIELDS: tuple[str, ...] = (
    "stock_price", "market_cap", "trailing_per", "eps",
    "forward_per", "pbr", "psr", "ev_ebitda",
    "dividend_yield", "roe", "operating_margin", "net_margin",
    "revenue_growth", "earnings_growth", "de_ratio",
    "peg_ratio", "fcf_yield", "beta", "volume",
)
SCREENING_CATEGORICAL_FIELDS: tuple[str, ...] = ("sector", "industry", "exchange")


@dataclass(frozen=True)
class FieldMetadata:
    field: str
    label: str
    format: Literal["ratio", "currency", "percent", "count", "string"]


FIELD_METADATA: tuple[FieldMetadata, ...] = (
    FieldMetadata("trailing_per", "PER (trailing)", "ratio"),
    FieldMetadata("forward_per",  "PER (forward)",  "ratio"),
    FieldMetadata("pbr",          "PBR",            "ratio"),
    FieldMetadata("psr",          "PSR",            "ratio"),
    FieldMetadata("ev_ebitda",    "EV/EBITDA",      "ratio"),
    FieldMetadata("market_cap",   "時価総額",        "currency"),
    FieldMetadata("eps",          "EPS",            "currency"),
    FieldMetadata("stock_price",  "株価",            "currency"),
    FieldMetadata("dividend_yield","配当利回り",     "percent"),
    FieldMetadata("roe",          "ROE",            "percent"),
    FieldMetadata("operating_margin", "営業利益率",  "percent"),
    FieldMetadata("net_margin",   "純利益率",        "percent"),
    FieldMetadata("revenue_growth", "売上成長率",    "percent"),
    FieldMetadata("earnings_growth","利益成長率",    "percent"),
    FieldMetadata("de_ratio",     "負債資本倍率",    "ratio"),
    FieldMetadata("peg_ratio",    "PEG",            "ratio"),
    FieldMetadata("fcf_yield",    "FCF利回り",      "percent"),
    FieldMetadata("beta",         "β",             "ratio"),
    FieldMetadata("volume",       "出来高",          "count"),
    FieldMetadata("sector",       "セクター",        "string"),
    FieldMetadata("industry",     "業種",            "string"),
    FieldMetadata("exchange",     "市場",            "string"),
)


@dataclass(frozen=True)
class FilterClause:
    field: str
    op: Literal["gte", "lte", "between", "eq", "in"]
    value: float | int | tuple[float, float] | str | list[str]


@dataclass(frozen=True)
class SortSpec:
    field: str
    desc: bool = True


@dataclass(frozen=True)
class ScreenSpec:
    filters: list[FilterClause] = field(default_factory=list)
    sort: SortSpec | None = None
    limit: int = 100
    offset: int = 0
    include_null: bool = False


@dataclass
class ScreenResultItem:
    company_id: str
    ticker: str | None
    name: str
    sector: str | None
    market: str
    metrics: dict[str, float | int | None]


@dataclass
class ScreenResult:
    items: list[ScreenResultItem]
    total_matched: int
    spec: ScreenSpec
    limit: int
    offset: int


@dataclass
class Bucket:
    lower: float
    upper: float
    count: int


@dataclass
class Distribution:
    field: str
    min: float | None
    max: float | None
    null_count: int
    finite_count: int
    non_finite_count: int
    buckets: list[Bucket]


@dataclass
class AddToTargetsResult:
    requested: int
    added: int
    already_present: int
    skipped: int


class ScreeningService:
    """Filter / sort / distribution / add-to-targets (read-only)."""

    def __init__(
        self,
        screening_repo: ScreeningRepository,
        company_repo: CompanyRepository,
        target_service: AnalysisTargetService,
    ):
        self._screening_repo = screening_repo
        self._company_repo = company_repo
        self._target_service = target_service

    @staticmethod
    def _validate(spec: ScreenSpec) -> None:
        all_fields = set(SCREENING_NUMERIC_FIELDS) | set(SCREENING_CATEGORICAL_FIELDS)
        if not (1 <= spec.limit <= 1000):
            raise ValueError(f"limit must be in 1..1000, got {spec.limit}")
        if spec.offset < 0:
            raise ValueError(f"offset must be >= 0, got {spec.offset}")
        if spec.sort is not None and spec.sort.field not in all_fields:
            raise ValueError(f"unknown sort field: {spec.sort.field!r}")
        for clause in spec.filters:
            if clause.field not in all_fields:
                raise ValueError(f"unknown field: {clause.field!r}")
            is_numeric = clause.field in SCREENING_NUMERIC_FIELDS
            if is_numeric and clause.op in ("eq", "in"):
                raise ValueError(
                    f"op {clause.op!r} not allowed on numeric field "
                    f"{clause.field!r}",
                )
            if not is_numeric and clause.op in ("gte", "lte", "between"):
                raise ValueError(
                    f"op {clause.op!r} not allowed on categorical field "
                    f"{clause.field!r}",
                )
            if clause.op == "between":
                v = clause.value
                if not (isinstance(v, (tuple, list)) and len(v) == 2):
                    raise ValueError(
                        f"between expects 2-tuple, got {v!r}",
                    )
                lo, hi = v
                if lo > hi:
                    raise ValueError(
                        f"between lower must be <= upper, got ({lo}, {hi})",
                    )
            if clause.op == "in":
                if not isinstance(clause.value, (list, tuple)):
                    raise ValueError(
                        f"in expects list/tuple, got {clause.value!r}",
                    )

    @staticmethod
    def _resolve_column(field: str):
        if field not in (set(SCREENING_NUMERIC_FIELDS) | set(SCREENING_CATEGORICAL_FIELDS)):
            raise ValueError(f"unknown field: {field!r}")
        return getattr(ScreeningCache, field)

    @staticmethod
    def _resolve_query_column(field: str, company_model):
        if field == "sector":
            return func.coalesce(ScreeningCache.sector, company_model.sector)
        if field == "exchange":
            return func.coalesce(ScreeningCache.exchange, company_model.market)
        return ScreeningService._resolve_column(field)

    async def run_screen(self, spec: ScreenSpec) -> ScreenResult:
        from sqlalchemy import select

        from stock_analyze_system.models.company import Company

        self._validate(spec)
        base_company_clauses = [
            Company.ticker.is_not(None),
            Company.cik.is_not(None),
        ]
        where_clauses = []
        for clause in spec.filters:
            col = self._resolve_query_column(clause.field, Company)
            is_numeric = clause.field in SCREENING_NUMERIC_FIELDS
            if clause.op == "gte":
                cond = col >= clause.value
            elif clause.op == "lte":
                cond = col <= clause.value
            elif clause.op == "between":
                lo, hi = clause.value
                cond = col.between(lo, hi)
            elif clause.op == "eq":
                cond = col == clause.value
            else:  # "in"
                cond = col.in_(list(clause.value))
            if is_numeric and spec.include_null:
                from sqlalchemy import or_
                where_clauses.append(or_(cond, col.is_(None)))
            else:
                where_clauses.append(cond)
                if is_numeric:
                    where_clauses.append(col.is_not(None))

        sort_field = spec.sort.field if spec.sort else "market_cap"
        sort_desc = spec.sort.desc if spec.sort else True
        sort_col = self._resolve_query_column(sort_field, Company)

        base = (
            select(Company, ScreeningCache)
            .outerjoin(ScreeningCache, Company.id == ScreeningCache.company_id)
            .where(*base_company_clauses, *where_clauses)
            .order_by(sort_col.is_(None),
                      sort_col.desc() if sort_desc else sort_col.asc())
            .limit(spec.limit)
            .offset(spec.offset)
        )
        rows = (await self._screening_repo._session.execute(base)).all()

        count_stmt = (
            select(func.count())
            .select_from(Company)
            .outerjoin(ScreeningCache, Company.id == ScreeningCache.company_id)
            .where(*base_company_clauses, *where_clauses)
        )
        total = (await self._screening_repo._session.execute(count_stmt)).scalar() or 0

        items: list[ScreenResultItem] = []
        for company, cache in rows:
            metrics = {
                f: getattr(cache, f) if cache is not None else None
                for f in SCREENING_NUMERIC_FIELDS
            }
            items.append(ScreenResultItem(
                company_id=company.id,
                ticker=company.ticker,
                name=company.name,
                sector=(cache.sector if cache is not None else None) or company.sector,
                market=company.market,
                metrics=metrics,
            ))
        return ScreenResult(
            items=items, total_matched=total, spec=spec,
            limit=spec.limit, offset=spec.offset,
        )

    async def get_distribution(
        self, field: str, buckets: int = 20,
    ) -> Distribution:
        from sqlalchemy import and_, case, func, not_, select

        if field not in SCREENING_NUMERIC_FIELDS:
            raise ValueError(f"distribution available only on numeric fields, got {field!r}")
        if not (1 <= buckets <= 100):
            raise ValueError(f"buckets must be in 1..100, got {buckets}")
        col = getattr(ScreeningCache, field)
        is_not_nan = col == col
        finite = and_(
            col.is_not(None),
            col != float("inf"),
            col != float("-inf"),
            is_not_nan,
        )
        stat_stmt = select(
            func.min(col).filter(finite),
            func.max(col).filter(finite),
            func.count().filter(col.is_(None)),
            func.count().filter(finite),
            func.count().filter(and_(col.is_not(None), not_(finite))),
        )
        lo, hi, null_count, finite_count, non_finite = (
            await self._screening_repo._session.execute(stat_stmt)
        ).one()

        if finite_count == 0:
            return Distribution(
                field=field, min=None, max=None,
                null_count=null_count, finite_count=0,
                non_finite_count=non_finite, buckets=[],
            )
        if lo == hi:
            return Distribution(
                field=field, min=lo, max=hi,
                null_count=null_count, finite_count=finite_count,
                non_finite_count=non_finite,
                buckets=[Bucket(lower=lo, upper=hi, count=finite_count)],
            )
        width = (hi - lo) / buckets
        case_args = [
            (
                and_(
                    col >= lo + i * width,
                    (col < lo + (i + 1) * width) if i < buckets - 1 else (col <= hi),
                ),
                i,
            )
            for i in range(buckets)
        ]
        bucket_idx = case(*case_args).label("idx")
        bucket_stmt = (
            select(bucket_idx, func.count())
            .where(finite)
            .group_by(bucket_idx)
        )
        rows = (await self._screening_repo._session.execute(bucket_stmt)).all()
        counts = {idx: cnt for idx, cnt in rows}
        return Distribution(
            field=field, min=lo, max=hi,
            null_count=null_count, finite_count=finite_count,
            non_finite_count=non_finite,
            buckets=[
                Bucket(
                    lower=lo + i * width,
                    upper=(lo + (i + 1) * width) if i < buckets - 1 else hi,
                    count=counts.get(i, 0),
                )
                for i in range(buckets)
            ],
        )

    async def add_to_targets(self, company_ids: list[str]) -> AddToTargetsResult:
        if not company_ids:
            raise ValueError("company_ids must be non-empty")
        if len(company_ids) > 100:
            raise ValueError("max 100 ids per call")
        unique = list(dict.fromkeys(company_ids))
        existing = await self._company_repo.find_existing_ids(unique)
        valid = [cid for cid in unique if cid in existing]
        skipped = len(unique) - len(valid)
        added = await self._target_service.add_from_screening(valid)
        already_present = len(valid) - added
        return AddToTargetsResult(
            requested=len(company_ids),
            added=added,
            already_present=already_present,
            skipped=skipped,
        )
