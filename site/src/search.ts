/**
 * Name search, over an FTS5 index.
 *
 * The obvious query is `name LIKE '%red cross%'`, and it is what this site shipped with. A
 * leading wildcard cannot use an index, so on 3.27M organizations every search is a full
 * table scan: measured at ~6.5M rows read per query, which burns a month's included reads in
 * a few thousand searches and takes seconds to return. FTS5 turns that into an index lookup.
 */

/** Never return more than this many, however the query is written. */
export const SEARCH_LIMIT = 20;

/** Long enough for "boys and girls clubs of greater x", short enough to bound the work. */
const MAX_TOKENS = 8;

/**
 * Turn what somebody typed into an FTS5 MATCH expression.
 *
 * User input cannot go anywhere near MATCH unescaped. FTS5 query text is a small language
 * with its own operators — `AND`, `OR`, `NOT`, `NEAR`, `*`, `^`, `:`, parentheses, quotes —
 * so a name like `AT&T` or a stray `"` is at best a syntax error that 500s the page, and
 * column filters (`name:foo`) are a way to probe the index. Rather than escape that
 * grammar, this discards it: only letters and digits survive, and each surviving token is
 * emitted as a quoted phrase, which FTS5 treats as a literal.
 *
 * Tokens are implicitly ANDed, so "red cross" requires both words but in any order and any
 * position — which is the behaviour the old substring match had and the reason it was worth
 * keeping. The final token gets a prefix wildcard so "amer" still finds AMERICAN while
 * somebody is still typing.
 *
 * Returns null when nothing searchable remains, so the caller can skip the query entirely
 * rather than asking the database to match nothing.
 */
export function ftsQuery(raw: string): string | null {
  const tokens = (raw.match(/[\p{L}\p{N}]+/gu) ?? []).slice(0, MAX_TOKENS);
  if (tokens.length === 0) return null;

  return tokens
    .map((token, i) => {
      const quoted = `"${token}"`;
      // Prefix-match the last token only. Applying it to every token would match far too
      // much ("a" would match everything) for no gain: the earlier words are already typed.
      const isLast = i === tokens.length - 1;
      return isLast && token.length >= 2 ? `${quoted}*` : quoted;
    })
    .join(" ");
}

export type SearchHit = {
  ein: string;
  name: string | null;
  city: string | null;
  state: string | null;
};

/**
 * Run a name search. Returns [] for an unsearchable query rather than throwing.
 *
 * The join is on rowid because this is an external-content FTS5 table: it indexes
 * `organization` in place rather than storing a second copy of every name, so its rowid is
 * the base table's rowid.
 */
export async function searchByName(db: D1Database, raw: string): Promise<SearchHit[]> {
  const match = ftsQuery(raw);
  if (!match) return [];

  try {
    const { results } = await db
      .prepare(
        "SELECT o.ein, o.name, o.city, o.state FROM organization_fts f " +
          "JOIN organization o ON o.rowid = f.rowid " +
          "WHERE organization_fts MATCH ? ORDER BY rank LIMIT ?",
      )
      .bind(match, SEARCH_LIMIT)
      .all<SearchHit>();
    return results ?? [];
  } catch (error) {
    // A malformed MATCH expression is a 500 on a page whose whole job is to be forgiving.
    // ftsQuery should make that impossible; if it ever does not, "no results" is the right
    // answer for the visitor and the log line is for us.
    console.error("search failed:", error instanceof Error ? error.message : "unknown");
    return [];
  }
}
