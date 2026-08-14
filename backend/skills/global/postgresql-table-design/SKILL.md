---
name: postgresql-table-design
display_name: PostgreSQL Table Design
description: PostgreSQL-specific schema design covering data types, indexing, constraints, performance patterns, and advanced features.
category: testing
isBeta: false
tags:
- postgresql
- schema-design
- indexing
- constraints
- data-types
- partitioning
- jsonb
- rls
---

# PostgreSQL Table Design

## Core Rules

- Define a **PRIMARY KEY** for reference tables. Prefer `BIGINT GENERATED ALWAYS AS IDENTITY`; use `UUID` only when global uniqueness/opacity is needed.
- **Normalize first (to 3NF)** to eliminate redundancy; denormalize only for measured, high-ROI reads.
- Add **NOT NULL** everywhere semantically required; use **DEFAULT**s for common values.
- Create **indexes for access paths you actually query**: PK/unique (auto), FK columns (manual!), frequent filters/sorts, join keys.
- Prefer **TIMESTAMPTZ** for event time; **NUMERIC** for money; **TEXT** for strings; **BIGINT** for integers.

## PostgreSQL Gotchas

- Unquoted identifiers are lowercased. Use `snake_case`.
- UNIQUE allows multiple NULLs. Use `NULLS NOT DISTINCT` (PG15+).
- PostgreSQL does NOT auto-index FK columns. Add them explicitly.
- Length/precision overflows error out (no silent truncation).
- Sequences have gaps (normal behavior from rollbacks/crashes).
- No clustered PK by default (unlike SQL Server/InnoDB).
- MVCC: updates/deletes leave dead tuples; vacuum handles them.

## Data Types

- **IDs**: `BIGINT GENERATED ALWAYS AS IDENTITY` preferred; `UUID` for distributed/opaque IDs
- **Strings**: `TEXT` preferred; use `CHECK (LENGTH(col) <= n)` over `VARCHAR(n)`
- **Money**: `NUMERIC(p,s)` (never float)
- **Time**: `TIMESTAMPTZ` for timestamps; `DATE` for date-only
- **Booleans**: `BOOLEAN NOT NULL`
- **Enums**: `CREATE TYPE ... AS ENUM` for small stable sets; TEXT + CHECK for evolving values
- **Arrays**: Index with GIN for containment queries
- **JSONB**: Preferred over JSON; index with GIN; use for semi-structured data
- **Range types**: `daterange`, `numrange`, `tstzrange` for intervals; index with GiST

### Do NOT Use

- `timestamp` without timezone → use `timestamptz`
- `char(n)` or `varchar(n)` → use `text`
- `money` type → use `numeric`
- `serial` → use `generated always as identity`

## Constraints

- **FK**: Specify `ON DELETE/UPDATE` action; add explicit index on referencing column
- **UNIQUE**: Use `NULLS NOT DISTINCT` (PG15+) unless duplicate NULLs needed
- **CHECK**: NULL values pass (three-valued logic); combine with NOT NULL
- **EXCLUDE**: Prevent overlapping values (e.g., room double-booking)

## Indexing

- **B-tree**: Default for equality/range (`=`, `<`, `>`, `BETWEEN`, `ORDER BY`)
- **Composite**: Order matters; leftmost prefix must be present in query
- **Covering**: `INCLUDE (cols)` for index-only scans
- **Partial**: For hot subsets (`WHERE status = 'active'`)
- **Expression**: For computed keys (`LOWER(email)`)
- **GIN**: JSONB, arrays, full-text search
- **GiST**: Range types, geometric, spatial

## Row-Level Security

```sql
ALTER TABLE tbl ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_access ON orders FOR SELECT TO app_users
  USING (user_id = current_user_id());
```
