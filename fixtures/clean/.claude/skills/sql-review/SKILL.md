---
name: sql-review
description: Review a SQL query for correctness, index usage, and lock risk before it ships. Use when the user pastes a query, a migration, or a slow-query log entry. Not for schema design or ORM mapping.
version: 1.1.0
---

# SQL review

1. 看执行计划有没有全表扫。
2. 看 WHERE 列有没有可用索引，函数包裹列会导致索引失效。
3. 看事务里有没有长时间持有的锁。
4. 只对 `blocker` 给完整重写，其余给方向。
