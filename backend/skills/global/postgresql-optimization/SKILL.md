---
name: postgresql-optimization
display_name: PostgreSQL Optimization
description: PostgreSQL optimization including indexes, query plans, partitioning, JSONB operations, and connection pooling.
category: testing
isBeta: false
tags:
- postgresql
- query-optimization
- indexing
- partitioning
- jsonb
- explain-analyze
- connection-pooling
- performance
---

# PostgreSQL Optimization

## Index Strategies

```sql
-- B-tree index for equality and range queries (default)
CREATE INDEX idx_orders_customer_id ON orders (customer_id);

-- Composite index (column order matters: equality columns first, range last)
CREATE INDEX idx_orders_status_created ON orders (status, created_at DESC);

-- Partial index (smaller, faster for filtered queries)
CREATE INDEX idx_orders_pending ON orders (created_at)
  WHERE status = 'pending';

-- Covering index (avoids table lookup entirely)
CREATE INDEX idx_users_email_name ON users (email) INCLUDE (name, avatar_url);

-- GIN index for JSONB containment queries
CREATE INDEX idx_products_metadata ON products USING GIN (metadata);

-- GiST index for full-text search
CREATE INDEX idx_articles_search ON articles USING GiST (
  to_tsvector('english', title || ' ' || body)
);

-- Concurrent index creation (no table lock)
CREATE INDEX CONCURRENTLY idx_large_table_col ON large_table (col);
```

## Reading Query Plans

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT o.id, o.total, u.name
FROM orders o
JOIN users u ON o.user_id = u.id
WHERE o.status = 'shipped'
  AND o.created_at > NOW() - INTERVAL '30 days'
ORDER BY o.created_at DESC
LIMIT 20;
```

Key things to look for:
- `Seq Scan` on large tables → missing index
- `Nested Loop` with high row estimates → missing join index
- `Sort` without `Index Scan` → sort happening in memory/disk
- `Buffers: shared hit` vs `shared read` → cache efficiency

## Partitioning

```sql
CREATE TABLE events (
    id          BIGINT GENERATED ALWAYS AS IDENTITY,
    event_type  TEXT NOT NULL,
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

CREATE TABLE events_2024_q1 PARTITION OF events
    FOR VALUES FROM ('2024-01-01') TO ('2024-04-01');
CREATE TABLE events_2024_q2 PARTITION OF events
    FOR VALUES FROM ('2024-04-01') TO ('2024-07-01');
```

Partition tables with more than 10M rows when queries consistently filter on the partition key.

## Best Practices

1. **Index FK columns**: PostgreSQL does not auto-index them
2. **Use partial indexes**: For hot subsets of data
3. **Avoid SELECT ***: Only retrieve needed columns
4. **Use EXPLAIN ANALYZE**: Always validate query plans
5. **Monitor bloat**: Run VACUUM and watch dead tuple counts
6. **Connection pooling**: Use PgBouncer or built-in pooling
7. **Batch operations**: Prefer bulk inserts over row-by-row
