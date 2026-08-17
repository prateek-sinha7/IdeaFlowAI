---
name: sql-code-review
display_name: SQL Code Review
description: Universal SQL code review for security, maintainability, and quality across MySQL, PostgreSQL, SQL Server, and Oracle.
category: collaboration
isBeta: false
tags:
- sql
- code-review
- security
- sql-injection
- performance
- anti-patterns
- access-control
- best-practices
---

# SQL Code Review

Comprehensive SQL code review focusing on security, performance, maintainability, and database best practices across all major SQL databases.

## Security Analysis

### SQL Injection Prevention

```sql
-- CRITICAL: SQL Injection vulnerability
query = "SELECT * FROM users WHERE id = " + userInput;

-- SECURE: Parameterized queries
PREPARE stmt FROM 'SELECT * FROM users WHERE id = ?';
EXECUTE stmt USING @user_id;
```

### Access Control & Permissions

- **Principle of Least Privilege**: Grant minimum required permissions
- **Role-Based Access**: Use database roles instead of direct user permissions
- **Schema Security**: Proper schema ownership and access controls
- **Function/Procedure Security**: Review DEFINER vs INVOKER rights

### Data Protection

- Avoid `SELECT *` on tables with sensitive columns
- Ensure sensitive operations are audit logged
- Use views or functions to mask sensitive data
- Verify encrypted storage for sensitive data

## Performance Optimization

### Query Structure Analysis

```sql
-- BAD: Inefficient query patterns
SELECT DISTINCT u.*
FROM users u, orders o, products p
WHERE u.id = o.user_id
AND o.product_id = p.id
AND YEAR(o.order_date) = 2024;

-- GOOD: Optimized structure
SELECT u.id, u.name, u.email
FROM users u
INNER JOIN orders o ON u.id = o.user_id
WHERE o.order_date >= '2024-01-01'
AND o.order_date < '2025-01-01';
```

### Index Strategy Review

- Identify columns that need indexing
- Find unused or redundant indexes
- Check composite index column ordering
- Verify covering indexes for frequent queries

## Maintainability

### Code Standards

- Consistent naming conventions (snake_case)
- Proper indentation and formatting
- Meaningful table/column names
- Comments on complex logic only

### Anti-Patterns to Flag

- `SELECT *` in production code
- Implicit joins (comma-separated FROM)
- Functions on indexed columns in WHERE clauses
- Missing transaction boundaries on multi-statement operations
- Hardcoded values instead of parameters
- N+1 query patterns in application code

## Review Checklist

- [ ] No SQL injection vulnerabilities
- [ ] Least privilege access control
- [ ] Explicit JOIN syntax (no implicit joins)
- [ ] Proper index coverage for WHERE/JOIN conditions
- [ ] No functions on indexed columns in predicates
- [ ] Transaction boundaries for multi-statement ops
- [ ] Consistent naming conventions
- [ ] No SELECT * in production queries
