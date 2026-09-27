import {
  CheckCircle2,
  Clock,
  Database,
  Key,
  Play,
  RefreshCw,
  Server,
  Table as TableIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api, DBStatus, SQLQueryResult } from "../lib/api";

const PRESET_QUERIES = [
  {
    name: "Top 5 Most Cited Papers (JOIN + GROUP BY)",
    sql: `SELECT p.id, p.title, p.year, COUNT(e.id) AS citations_count
FROM papers p
JOIN edges e ON p.id = e.target_paper_id
WHERE e.edge_type = 'citation'
GROUP BY p.id, p.title, p.year
ORDER BY citations_count DESC
LIMIT 5;`,
  },
  {
    name: "Graph Edge Type Distribution (Aggregation)",
    sql: `SELECT edge_type, COUNT(*) AS total_edges, ROUND(AVG(confidence), 3) AS avg_confidence
FROM edges
GROUP BY edge_type
ORDER BY total_edges DESC;`,
  },
  {
    name: "Paper Keyword Association (M:N Join)",
    sql: `SELECT k.text AS keyword, COUNT(pk.paper_id) AS paper_count
FROM keywords k
JOIN paper_keywords pk ON k.id = pk.keyword_id
GROUP BY k.id, k.text
ORDER BY paper_count DESC
LIMIT 10;`,
  },
  {
    name: "Paper Chunking & Vector Coverage",
    sql: `SELECT p.id, p.title, COUNT(c.id) AS chunk_count, LENGTH(p.full_text) AS text_length
FROM papers p
LEFT JOIN paper_chunks c ON p.id = c.paper_id
GROUP BY p.id, p.title, p.full_text
ORDER BY chunk_count DESC
LIMIT 8;`,
  },
  {
    name: "Recent RAG Chat Queries & Cited Records",
    sql: `SELECT id, question, cited_paper_ids, SUBSTR(answer, 1, 100) AS answer_preview
FROM chat_history
ORDER BY id DESC
LIMIT 5;`,
  },
];

export function DatabasePage() {
  const [status, setStatus] = useState<DBStatus | null>(null);
  const [selectedTable, setSelectedTable] = useState<string>("papers");
  const [customSQL, setCustomSQL] = useState<string>(PRESET_QUERIES[0].sql);
  const [queryResult, setQueryResult] = useState<SQLQueryResult | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [executing, setExecuting] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState(false);

  function loadStatus() {
    setLoadingStatus(true);
    api
      .dbStatus()
      .then((data) => {
        setStatus(data);
        if (data.tables.length > 0 && !selectedTable) {
          setSelectedTable(data.tables[0].table_name);
        }
      })
      .catch((err) => console.error("Failed to fetch DB status", err))
      .finally(() => setLoadingStatus(false));
  }

  useEffect(() => {
    loadStatus();
    // Run initial preset query
    runQuery(PRESET_QUERIES[0].sql);
  }, []);

  async function runQuery(sqlToRun: string) {
    setExecuting(true);
    setQueryError(null);
    try {
      const res = await api.dbQuery(sqlToRun);
      setQueryResult(res);
    } catch (err: any) {
      setQueryError(err?.message || "Failed to execute SQL query");
      setQueryResult(null);
    } finally {
      setExecuting(false);
    }
  }

  const activeTableInfo = status?.tables.find((t) => t.table_name === selectedTable);

  return (
    <section className="page" style={{ maxWidth: 1200, margin: "0 auto", paddingBottom: 60 }}>
      <header className="pageHeader inlineHeader">
        <div>
          <h1>DBMS & Schema Explorer</h1>
          <p>
            Inspect the relational database architecture, table schemas, foreign key constraints, and run interactive SQL queries.
          </p>
        </div>
        <button className="secondary" onClick={loadStatus} disabled={loadingStatus}>
          <RefreshCw size={16} className={loadingStatus ? "spin" : ""} /> Refresh DBMS
        </button>
      </header>

      {/* Engine Status Banner */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: 16,
          marginBottom: 24,
        }}
      >
        <div className="panel" style={{ padding: 18 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#2563eb", marginBottom: 6 }}>
            <Server size={20} />
            <span style={{ fontSize: 13, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
              Database Engine
            </span>
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: "#0f172a" }}>
            {status?.engine ? status.engine.toUpperCase() : "Connecting..."}
          </div>
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>
            {status?.is_sqlite ? "Local SQLite (Zero-config)" : "Supabase / PostgreSQL (Cloud Cloud RDBMS)"}
          </div>
        </div>

        <div className="panel" style={{ padding: 18 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#059669", marginBottom: 6 }}>
            <TableIcon size={20} />
            <span style={{ fontSize: 13, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
              Relational Tables
            </span>
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: "#0f172a" }}>
            {status?.total_tables ?? 6} Tables
          </div>
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>
            Normalized relational 3NF schema
          </div>
        </div>

        <div className="panel" style={{ padding: 18 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#d97706", marginBottom: 6 }}>
            <Database size={20} />
            <span style={{ fontSize: 13, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
              Total Records
            </span>
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: "#0f172a" }}>
            {status?.total_records?.toLocaleString() ?? 0} Rows
          </div>
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>
            Across all tables & chunks
          </div>
        </div>

        <div className="panel" style={{ padding: 18 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#7c3aed", marginBottom: 6 }}>
            <CheckCircle2 size={20} />
            <span style={{ fontSize: 13, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
              ACID Integrity
            </span>
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: "#0f172a" }}>Foreign Keys ON</div>
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>Cascading deletes supported</div>
        </div>
      </div>

      {/* Relational Schema Viewer & Tables */}
      <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 20, marginBottom: 32 }}>
        {/* Table Selector List */}
        <div className="panel" style={{ padding: 16 }}>
          <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
            <TableIcon size={16} /> Database Tables
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {status?.tables.map((table) => (
              <button
                key={table.table_name}
                onClick={() => setSelectedTable(table.table_name)}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "10px 14px",
                  borderRadius: 6,
                  border: selectedTable === table.table_name ? "1px solid #3b82f6" : "1px solid #e2e8f0",
                  background: selectedTable === table.table_name ? "#eff6ff" : "#ffffff",
                  color: selectedTable === table.table_name ? "#1d4ed8" : "#334155",
                  fontWeight: selectedTable === table.table_name ? 600 : 400,
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                <span>{table.table_name}</span>
                <span
                  style={{
                    background: selectedTable === table.table_name ? "#dbeafe" : "#f1f5f9",
                    padding: "2px 8px",
                    borderRadius: 12,
                    fontSize: 11,
                    color: "#475569",
                  }}
                >
                  {table.row_count} rows
                </span>
              </button>
            ))}
          </div>

          <div style={{ marginTop: 24, padding: "12px 14px", background: "#f8fafc", borderRadius: 6, fontSize: 12 }}>
            <strong>Connection String:</strong>
            <code style={{ display: "block", marginTop: 4, wordBreak: "break-all", color: "#64748b" }}>
              {status?.database_url_masked || "sqlite:///./research_graph.db"}
            </code>
          </div>
        </div>

        {/* Selected Table Schema Details */}
        <div className="panel" style={{ padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div>
              <h2 style={{ margin: 0, fontSize: 18 }}>Table: <code>{selectedTable}</code></h2>
              <span style={{ fontSize: 13, color: "#64748b" }}>
                {activeTableInfo?.row_count ?? 0} records stored
              </span>
            </div>
            {activeTableInfo?.foreign_keys && activeTableInfo.foreign_keys.length > 0 && (
              <div style={{ display: "flex", gap: 6 }}>
                {activeTableInfo.foreign_keys.map((fk, idx) => (
                  <span
                    key={idx}
                    style={{
                      background: "#fef3c7",
                      color: "#92400e",
                      padding: "4px 8px",
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 500,
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                  >
                    <Key size={12} /> FK: {fk.constrained_columns.join(", ")} &rarr; {fk.referred_table}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f8fafc", borderBottom: "2px solid #e2e8f0", textAlign: "left" }}>
                  <th style={{ padding: "8px 12px" }}>Column Name</th>
                  <th style={{ padding: "8px 12px" }}>Data Type</th>
                  <th style={{ padding: "8px 12px" }}>Key</th>
                  <th style={{ padding: "8px 12px" }}>Nullable</th>
                </tr>
              </thead>
              <tbody>
                {activeTableInfo?.columns.map((col) => (
                  <tr key={col.name} style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "8px 12px", fontWeight: 600 }}>{col.name}</td>
                    <td style={{ padding: "8px 12px", fontFamily: "monospace", color: "#2563eb" }}>{col.type}</td>
                    <td style={{ padding: "8px 12px" }}>
                      {col.primary_key && (
                        <span
                          style={{
                            background: "#fee2e2",
                            color: "#991b1b",
                            padding: "2px 6px",
                            borderRadius: 4,
                            fontSize: 11,
                            fontWeight: 600,
                          }}
                        >
                          PRIMARY KEY
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "8px 12px", color: col.nullable ? "#64748b" : "#dc2626" }}>
                      {col.nullable ? "YES" : "NOT NULL"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Interactive SQL Console Section */}
      <div className="panel" style={{ padding: 24, marginTop: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 18, display: "flex", alignItems: "center", gap: 8 }}>
              <Play size={18} color="#2563eb" /> Interactive SQL Console
            </h2>
            <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: 13 }}>
              Execute live read-only SQL queries to verify relational joins, groupings, and graph queries.
            </p>
          </div>
        </div>

        {/* Preset Query Buttons */}
        <div style={{ marginBottom: 16 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#475569", display: "block", marginBottom: 8 }}>
            Sample DBMS Queries:
          </span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {PRESET_QUERIES.map((preset, idx) => (
              <button
                key={idx}
                type="button"
                className="secondary"
                style={{ fontSize: 12, padding: "6px 12px" }}
                onClick={() => {
                  setCustomSQL(preset.sql);
                  runQuery(preset.sql);
                }}
              >
                {preset.name}
              </button>
            ))}
          </div>
        </div>

        {/* SQL Input Area */}
        <div style={{ position: "relative", marginBottom: 16 }}>
          <textarea
            value={customSQL}
            onChange={(e) => setCustomSQL(e.target.value)}
            rows={5}
            style={{
              width: "100%",
              fontFamily: "monospace",
              fontSize: 13,
              padding: "12px 16px",
              background: "#1e293b",
              color: "#f8fafc",
              borderRadius: 8,
              border: "1px solid #334155",
              boxSizing: "border-box",
            }}
            placeholder="Type your SELECT SQL query here..."
          />
          <button
            onClick={() => runQuery(customSQL)}
            disabled={executing || !customSQL.trim()}
            style={{
              position: "absolute",
              right: 12,
              bottom: 16,
              background: "#2563eb",
              color: "white",
              border: "none",
              borderRadius: 6,
              padding: "8px 16px",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <Play size={14} /> {executing ? "Executing..." : "Run SQL"}
          </button>
        </div>

        {queryError && (
          <div style={{ padding: 14, background: "#fee2e2", color: "#991b1b", borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
            <strong>Query Error:</strong> {queryError}
          </div>
        )}

        {/* Query Results Table */}
        {queryResult && (
          <div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 12px",
                background: "#f1f5f9",
                borderRadius: "6px 6px 0 0",
                fontSize: 12,
                color: "#475569",
              }}
            >
              <span>
                <strong>{queryResult.row_count}</strong> row(s) returned
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <Clock size={12} /> Execution time: <strong>{queryResult.execution_time_ms} ms</strong>
              </span>
            </div>

            <div style={{ maxHeight: 360, overflowY: "auto", border: "1px solid #e2e8f0", borderTop: "none" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ background: "#f8fafc", borderBottom: "1px solid #cbd5e1", textAlign: "left" }}>
                    {queryResult.columns.map((col) => (
                      <th key={col} style={{ padding: "8px 12px", fontWeight: 600, color: "#1e293b" }}>
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {queryResult.rows.map((row, rowIdx) => (
                    <tr
                      key={rowIdx}
                      style={{
                        borderBottom: "1px solid #f1f5f9",
                        background: rowIdx % 2 === 0 ? "#ffffff" : "#fafafa",
                      }}
                    >
                      {queryResult.columns.map((col) => (
                        <td key={col} style={{ padding: "8px 12px", color: "#334155", maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {row[col] === null ? (
                            <span style={{ color: "#94a3b8", fontStyle: "italic" }}>NULL</span>
                          ) : (
                            row[col]
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
