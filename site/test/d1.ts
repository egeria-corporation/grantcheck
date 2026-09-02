/**
 * A D1 adapter over `node:sqlite`, so the account tests run against the real schema.
 *
 * Mocking the database would mean the tests agree with my idea of what the SQL does rather
 * than with what it does. The interesting failures here — a UNIQUE constraint, a WHERE
 * clause that fails to scope a row to its account, a LEFT JOIN yielding nulls — only show
 * up against a real engine, and those are exactly the ones worth catching.
 *
 * Deliberately partial: it implements the surface `src/` actually uses and nothing more.
 */

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";

// Loaded through createRequire rather than imported. `node:sqlite` postdates Vite 5's list
// of Node builtins, so Vite tries to resolve it as an npm package and fails; going through
// the real CommonJS resolver sidesteps the bundler entirely.
const { DatabaseSync } = createRequire(import.meta.url)("node:sqlite") as {
  DatabaseSync: new (path: string) => DatabaseSyncLike;
};

type DatabaseSyncLike = {
  prepare(sql: string): {
    get(...params: never[]): unknown;
    all(...params: never[]): unknown[];
    run(...params: never[]): unknown;
  };
  exec(sql: string): void;
};

type Row = Record<string, unknown>;

class Stmt {
  constructor(
    private readonly db: DatabaseSyncLike,
    private readonly sql: string,
    private readonly params: unknown[] = [],
  ) {}

  bind(...params: unknown[]): Stmt {
    return new Stmt(this.db, this.sql, params);
  }

  // node:sqlite rejects undefined and booleans; D1 accepts both. Normalize at the edge so
  // call sites are not written around the test harness.
  private args(): unknown[] {
    return this.params.map((p) => {
      if (p === undefined) return null;
      if (typeof p === "boolean") return p ? 1 : 0;
      return p;
    });
  }

  async first<T = Row>(): Promise<T | null> {
    const row = this.db.prepare(this.sql).get(...(this.args() as never[]));
    return (row as T) ?? null;
  }

  async all<T = Row>(): Promise<{ results: T[]; success: true }> {
    const rows = this.db.prepare(this.sql).all(...(this.args() as never[]));
    return { results: rows as T[], success: true };
  }

  async run(): Promise<{ success: true; meta: { changes: number } }> {
    const result = this.db.prepare(this.sql).run(...(this.args() as never[])) as {
      changes?: number | bigint;
    };
    // D1 reports affected rows on meta.changes; node:sqlite puts it on the result directly
    // (and as a BigInt). Callers that count deletions read the D1 shape.
    return { success: true, meta: { changes: Number(result?.changes ?? 0) } };
  }
}

export class TestD1 {
  private readonly db: DatabaseSyncLike = new DatabaseSync(":memory:");

  constructor() {
    // The real schema file, not a copy. A column added to schema.sql and forgotten in the
    // code fails here rather than in production.
    const schema = readFileSync(join(import.meta.dirname, "..", "schema.sql"), "utf8");
    this.db.exec(schema);
  }

  prepare(sql: string): Stmt {
    return new Stmt(this.db, sql);
  }

  async batch(statements: Stmt[]): Promise<unknown[]> {
    // D1 batches are atomic; so is this.
    this.db.exec("BEGIN");
    try {
      const out = [];
      for (const s of statements) out.push(await s.run());
      this.db.exec("COMMIT");
      return out;
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }

  /** Raw read, for asserting on what was actually persisted. */
  raw<T = Row>(sql: string, ...params: unknown[]): T[] {
    return this.db.prepare(sql).all(...(params as never[])) as T[];
  }

  /**
   * The single row a query is expected to return.
   *
   * `raw(...)[0]` is possibly-undefined under noUncheckedIndexedAccess, and the usual fix
   * is a non-null assertion — which turns "the row is missing" into a confusing crash three
   * lines later. This fails with the query that came back empty.
   */
  one<T = Row>(sql: string, ...params: unknown[]): T {
    const rows = this.raw<T>(sql, ...params);
    if (rows.length !== 1) {
      throw new Error(`expected exactly 1 row, got ${rows.length}: ${sql}`);
    }
    return rows[0] as T;
  }

  exec(sql: string): void {
    this.db.exec(sql);
  }
}

/** Typed as D1Database for the code under test; it is the subset that code touches. */
export function testDb(): TestD1 & D1Database {
  return new TestD1() as unknown as TestD1 & D1Database;
}
