"""
SQLite persistence layer for the Prospect Engine.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Optional

from thefuzz import fuzz

from models import normalize_domain, normalize_company_name, ProspectRecord

_FUZZY_THRESHOLD = 85

_CREATE_PROSPECTS = """
CREATE TABLE IF NOT EXISTS prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    domain TEXT DEFAULT '',
    address TEXT DEFAULT '',
    city TEXT DEFAULT '',
    state TEXT DEFAULT '',
    zip_code TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    website TEXT DEFAULT '',
    vertical TEXT DEFAULT '',
    source_channel TEXT DEFAULT '',
    estimated_employees INTEGER,
    estimated_revenue INTEGER,
    product_keywords TEXT DEFAULT '',
    compliance_signals TEXT DEFAULT '',
    contact_name TEXT DEFAULT '',
    contact_title TEXT DEFAULT '',
    contact_email TEXT DEFAULT '',
    contact_source TEXT DEFAULT '',
    email_verified TEXT DEFAULT '',
    email_confidence INTEGER,
    registration_id TEXT DEFAULT '',
    import_products TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    score INTEGER DEFAULT 0,
    score_breakdown TEXT DEFAULT '',
    tier TEXT DEFAULT 'PARK',
    status TEXT DEFAULT 'NEW',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    run_count INTEGER DEFAULT 1,
    status_updated TEXT DEFAULT '',
    status_notes TEXT DEFAULT ''
);
"""

_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_normalized_name ON prospects(normalized_name);
CREATE INDEX IF NOT EXISTS idx_domain ON prospects(domain);
CREATE INDEX IF NOT EXISTS idx_status ON prospects(status);
CREATE INDEX IF NOT EXISTS idx_first_seen ON prospects(first_seen);
CREATE INDEX IF NOT EXISTS idx_score ON prospects(score);
"""

_CREATE_RUN_HISTORY = """
CREATE TABLE IF NOT EXISTS run_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT,
    states_used TEXT,
    verticals_used TEXT,
    channels_used TEXT,
    raw_count INTEGER,
    dedup_count INTEGER,
    new_count INTEGER,
    updated_count INTEGER,
    hot_count INTEGER,
    warm_count INTEGER,
    nurture_count INTEGER,
    park_count INTEGER,
    avg_score REAL,
    duration_seconds INTEGER,
    serpapi_credits INTEGER,
    apollo_credits INTEGER,
    hunter_search_credits INTEGER,
    hunter_verify_credits INTEGER
);
"""

# Multi-value fields that should be set-unioned on merge
_MULTI_VALUE_FIELDS = ("source_channel", "vertical", "product_keywords", "compliance_signals")

# Fields that must never be overwritten by upsert
_PROTECTED_FIELDS = ("status", "first_seen", "status_notes", "status_updated")


def _merge_set_field(a: str, b: str) -> str:
    """Merge two comma-separated value strings into a sorted, deduplicated string."""
    parts_a = {v.strip() for v in a.split(",") if v.strip()}
    parts_b = {v.strip() for v in b.split(",") if v.strip()}
    merged = parts_a | parts_b
    return ", ".join(sorted(merged))


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class ProspectDB:
    def __init__(self, path: str):
        self.path = path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(_CREATE_PROSPECTS)
            for stmt in _CREATE_INDEXES.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)
            conn.execute(_CREATE_RUN_HISTORY)
            conn.commit()

    def _find_match(self, prospect: ProspectRecord, conn: sqlite3.Connection) -> Optional[dict]:
        """Find an existing DB record matching this prospect by domain or fuzzy name."""
        norm_domain = normalize_domain(prospect.website) if prospect.website else ""
        norm_name = normalize_company_name(prospect.company_name)

        # 1. Exact domain match
        if norm_domain:
            cursor = conn.execute(
                "SELECT * FROM prospects WHERE domain = ? AND domain != ''",
                (norm_domain,)
            )
            row = cursor.fetchone()
            if row:
                return _row_to_dict(row)

        # 2. Fuzzy name match
        cursor = conn.execute("SELECT * FROM prospects")
        for row in cursor.fetchall():
            existing_norm = row["normalized_name"]
            score = fuzz.token_sort_ratio(norm_name, existing_norm)
            if score >= _FUZZY_THRESHOLD:
                return _row_to_dict(row)

        return None

    def upsert(self, prospects: list[ProspectRecord]) -> tuple[int, int]:
        """Insert or update prospects. Returns (new_count, updated_count)."""
        new_count = 0
        updated_count = 0
        today = date.today().isoformat()

        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row

            for p in prospects:
                norm_domain = normalize_domain(p.website) if p.website else ""
                norm_name = normalize_company_name(p.company_name)

                existing = self._find_match(p, conn)

                if existing is None:
                    # INSERT new record
                    conn.execute(
                        """
                        INSERT INTO prospects (
                            company_name, normalized_name, domain,
                            address, city, state, zip_code, phone, website,
                            vertical, source_channel,
                            estimated_employees, estimated_revenue,
                            product_keywords, compliance_signals,
                            contact_name, contact_title, contact_email,
                            contact_source, email_verified, email_confidence,
                            registration_id, import_products, notes,
                            score, score_breakdown, tier,
                            status, first_seen, last_seen, run_count
                        ) VALUES (
                            ?, ?, ?,
                            ?, ?, ?, ?, ?, ?,
                            ?, ?,
                            ?, ?,
                            ?, ?,
                            ?, ?, ?,
                            ?, ?, ?,
                            ?, ?, ?,
                            ?, ?, ?,
                            'NEW', ?, ?, 1
                        )
                        """,
                        (
                            p.company_name, norm_name, norm_domain,
                            p.address, p.city, p.state, p.zip_code, p.phone, p.website,
                            p.vertical, p.source_channel,
                            p.estimated_employees, p.estimated_revenue,
                            p.product_keywords, p.compliance_signals,
                            p.contact_name, p.contact_title, p.contact_email,
                            p.contact_source, p.email_verified, p.email_confidence,
                            p.registration_id, p.import_products, p.notes,
                            p.score, p.score_breakdown, p.tier if p.tier else "PARK",
                            today, today,
                        )
                    )
                    new_count += 1
                else:
                    # UPDATE existing record — merge, but never overwrite protected fields
                    record_id = existing["id"]

                    # Merge multi-value fields
                    merged_fields = {}
                    for f in _MULTI_VALUE_FIELDS:
                        merged_fields[f] = _merge_set_field(existing.get(f, ""), getattr(p, f))

                    # Fill blank single-value fields from new record
                    # (skip multi-value, protected, and id/run_count/last_seen which we handle separately)
                    skip = set(_MULTI_VALUE_FIELDS) | set(_PROTECTED_FIELDS) | {
                        "id", "run_count", "last_seen", "normalized_name",
                        "company_name", "scraped_date"
                    }
                    single_updates = {}
                    prospect_dict = p.to_dict()
                    for fname, incoming in prospect_dict.items():
                        if fname in skip:
                            continue
                        current = existing.get(fname)
                        is_blank = current == "" or current is None or current == 0
                        if is_blank and incoming not in ("", None, 0):
                            single_updates[fname] = incoming

                    # Also update domain if it was blank and now we have one
                    if not existing.get("domain") and norm_domain:
                        single_updates["domain"] = norm_domain

                    # Build SET clause
                    set_parts = []
                    params = []

                    for f in _MULTI_VALUE_FIELDS:
                        set_parts.append(f"{f} = ?")
                        params.append(merged_fields[f])

                    for fname, val in single_updates.items():
                        set_parts.append(f"{fname} = ?")
                        params.append(val)

                    set_parts.append("last_seen = ?")
                    params.append(today)
                    set_parts.append("run_count = run_count + 1")

                    params.append(record_id)

                    conn.execute(
                        f"UPDATE prospects SET {', '.join(set_parts)} WHERE id = ?",
                        params
                    )
                    updated_count += 1

            conn.commit()

        return new_count, updated_count

    def set_status(self, name: str, status: str, note: str = "") -> int:
        """Update status for prospects matching name. Returns count of matched rows."""
        norm_name = normalize_company_name(name)
        now = datetime.now().isoformat()
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                """
                UPDATE prospects
                SET status = ?, status_updated = ?, status_notes = ?
                WHERE LOWER(normalized_name) LIKE ?
                """,
                (status, now, note, f"%{norm_name}%")
            )
            conn.commit()
            return cursor.rowcount

    def search(self, query: str) -> list[dict]:
        """Search prospects by space-separated terms across key fields."""
        terms = query.strip().split()
        if not terms:
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM prospects ORDER BY score DESC")
                return [_row_to_dict(r) for r in cursor.fetchall()]

        # Build AND across all terms, each term ORed across fields
        conditions = []
        params = []
        search_fields = ["company_name", "city", "state", "vertical", "product_keywords", "notes"]

        for term in terms:
            term_conditions = " OR ".join(
                f"{f} LIKE ?" for f in search_fields
            )
            conditions.append(f"({term_conditions})")
            for _ in search_fields:
                params.append(f"%{term}%")

        where_clause = " AND ".join(conditions)
        sql = f"SELECT * FROM prospects WHERE {where_clause} ORDER BY score DESC"

        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            return [_row_to_dict(r) for r in cursor.fetchall()]

    def get_pipeline_stats(self) -> dict:
        """Return status_counts and tier_counts dicts."""
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row

            cursor = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM prospects GROUP BY status"
            )
            status_counts = {row["status"]: row["cnt"] for row in cursor.fetchall()}

            cursor = conn.execute(
                "SELECT tier, COUNT(*) as cnt FROM prospects GROUP BY tier"
            )
            tier_counts = {row["tier"]: row["cnt"] for row in cursor.fetchall()}

        return {"status_counts": status_counts, "tier_counts": tier_counts}

    def get_by_status(self, status: str) -> list[dict]:
        """Return all prospects with the given status."""
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM prospects WHERE status = ? ORDER BY score DESC",
                (status,)
            )
            return [_row_to_dict(r) for r in cursor.fetchall()]

    def get_db_stats(self) -> dict:
        """Return total count, tier distribution, avg score."""
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row

            cursor = conn.execute("SELECT COUNT(*) as total, AVG(score) as avg_score FROM prospects")
            row = cursor.fetchone()
            total = row["total"]
            avg_score = row["avg_score"]

            cursor = conn.execute(
                "SELECT tier, COUNT(*) as cnt FROM prospects GROUP BY tier"
            )
            tier_dist = {row["tier"]: row["cnt"] for row in cursor.fetchall()}

        return {"total": total, "avg_score": avg_score, "tier_distribution": tier_dist}

    def get_prospects_for_export(self) -> list[dict]:
        """Return all prospects sorted by score desc."""
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM prospects ORDER BY score DESC")
            return [_row_to_dict(r) for r in cursor.fetchall()]

    def get_new_this_run(self, run_date: str) -> list[dict]:
        """Return prospects first seen on run_date, sorted by score desc."""
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM prospects WHERE first_seen = ? ORDER BY score DESC",
                (run_date,)
            )
            return [_row_to_dict(r) for r in cursor.fetchall()]

    def record_run(self, *, states: str = "", verticals: str = "", channels: str = "",
                   raw_count: int = 0, dedup_count: int = 0, new_count: int = 0,
                   updated_count: int = 0, hot: int = 0, warm: int = 0,
                   nurture: int = 0, park: int = 0, avg_score: float = 0.0,
                   duration: int = 0, serpapi: int = 0, apollo: int = 0,
                   hunter_search: int = 0, hunter_verify: int = 0):
        """Insert a run record into run_history."""
        run_date = datetime.now().isoformat()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO run_history (
                    run_date, states_used, verticals_used, channels_used,
                    raw_count, dedup_count, new_count, updated_count,
                    hot_count, warm_count, nurture_count, park_count,
                    avg_score, duration_seconds,
                    serpapi_credits, apollo_credits,
                    hunter_search_credits, hunter_verify_credits
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_date, states, verticals, channels,
                    raw_count, dedup_count, new_count, updated_count,
                    hot, warm, nurture, park,
                    avg_score, duration,
                    serpapi, apollo, hunter_search, hunter_verify,
                )
            )
            conn.commit()

    def get_run_history(self) -> list[dict]:
        """Return all run history records."""
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM run_history ORDER BY run_date DESC"
            )
            return [_row_to_dict(r) for r in cursor.fetchall()]

    def reset(self, confirm: bool = False):
        """Drop and recreate all tables if confirm=True."""
        if not confirm:
            return
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE IF EXISTS prospects")
            conn.execute("DROP TABLE IF EXISTS run_history")
            conn.commit()
        self._init_db()

    def get_for_verification(self, tiers: list[str], limit: int) -> list[dict]:
        """Return prospects with an email, not yet verified, in the given tiers."""
        placeholders = ",".join("?" * len(tiers))
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                f"""
                SELECT * FROM prospects
                WHERE contact_email != ''
                  AND (email_verified IS NULL OR email_verified = '')
                  AND tier IN ({placeholders})
                ORDER BY score DESC
                LIMIT ?
                """,
                (*tiers, limit)
            )
            return [_row_to_dict(r) for r in cursor.fetchall()]

    def update_email_verified(self, prospect_id: int, status: str):
        """Update the email_verified field for a prospect."""
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "UPDATE prospects SET email_verified = ? WHERE id = ?",
                (status, prospect_id)
            )
            conn.commit()
