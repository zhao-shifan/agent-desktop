import { useEffect, useMemo, useState } from "react";
import * as XLSX from "xlsx";
import type { PreviewFile } from "../../types/workbench";
import { formatBytes } from "../../lib/preview";
import { useBinaryResource } from "../../lib/useResource";
import { PreviewError, PreviewLoading, PreviewToolbar } from "./PreviewParts";

const MAX_ROWS = 400;
const MAX_COLS = 60;

type MergeSpan = { rowSpan: number; colSpan: number };

function parseWorkbook(data: ArrayBuffer) {
  return XLSX.read(new Uint8Array(data), { type: "array", cellDates: true });
}

export function SheetPreview({ file }: { file: PreviewFile }) {
  const url = file.url || file.path;
  const resource = useBinaryResource(url);
  const [activeSheet, setActiveSheet] = useState("");
  const workbook = useMemo(
    () => (resource.status === "ready" ? parseWorkbook(resource.data) : null),
    [resource.status, resource.data],
  );

  useEffect(() => {
    if (workbook?.SheetNames.length) {
      setActiveSheet((current) =>
        current && workbook.SheetNames.includes(current) ? current : workbook.SheetNames[0],
      );
    }
  }, [workbook]);

  const table = useMemo(() => {
    if (!workbook || !activeSheet) return null;
    const sheet = workbook.Sheets[activeSheet];
    if (!sheet) return null;
    const rows = XLSX.utils.sheet_to_json<unknown[]>(sheet, {
      header: 1,
      defval: "",
      raw: false,
      blankrows: true,
    }) as unknown[][];

    const colCount = Math.min(
      Math.max(1, ...rows.map((row) => row.length)),
      MAX_COLS,
    );
    const spans = new Map<string, MergeSpan>();
    const covered = new Set<string>();
    for (const merge of sheet["!merges"] ?? []) {
      if (merge.s.r >= MAX_ROWS || merge.s.c >= MAX_COLS) continue;
      const rowSpan = Math.min(merge.e.r - merge.s.r + 1, MAX_ROWS - merge.s.r);
      const colSpan = Math.min(merge.e.c - merge.s.c + 1, MAX_COLS - merge.s.c);
      if (rowSpan < 1 || colSpan < 1) continue;
      spans.set(`${merge.s.r}:${merge.s.c}`, { rowSpan, colSpan });
      for (let r = merge.s.r; r <= merge.e.r && r < MAX_ROWS; r++) {
        for (let c = merge.s.c; c <= merge.e.c && c < MAX_COLS; c++) {
          if (r !== merge.s.r || c !== merge.s.c) covered.add(`${r}:${c}`);
        }
      }
    }

    return {
      rows: rows.slice(0, MAX_ROWS),
      colCount,
      spans,
      covered,
      sheet,
      totalRows: rows.length,
      totalCols: Math.max(...rows.map((row) => row.length), 0),
    };
  }, [workbook, activeSheet]);

  return (
    <div className="wb-preview wb-sheet-preview">
      <PreviewToolbar>
        <span className="wb-preview-file">
          <span className="wb-preview-ext">XLSX</span>
          {file.name}
        </span>
        <span className="wb-preview-meta">{formatBytes(file.size)}</span>
        <span className="wb-preview-spacer" />
        {table ? (
          <span className="wb-preview-chip">
            {table.totalRows} 行 × {table.totalCols} 列
            {table.totalRows > MAX_ROWS || table.totalCols > MAX_COLS ? "（仅展示前 400×60）" : ""}
          </span>
        ) : null}
        <button type="button" className="wb-btn wb-btn--ghost" onClick={resource.reload}>
          重新加载
        </button>
      </PreviewToolbar>

      {workbook && workbook.SheetNames.length > 1 ? (
        <div className="wb-sheet-tabs">
          {workbook.SheetNames.map((name) => (
            <button
              key={name}
              type="button"
              className={`wb-sheet-tab ${name === activeSheet ? "is-active" : ""}`}
              onClick={() => setActiveSheet(name)}
            >
              {name}
            </button>
          ))}
        </div>
      ) : null}

      <div className="wb-preview-stage wb-sheet-stage">
        {resource.status === "loading" ? <PreviewLoading label="正在读取表格…" /> : null}
        {resource.status === "error" ? (
          <PreviewError message={`表格读取失败：${resource.error}`} onRetry={resource.reload} />
        ) : null}
        {table ? (
          <div className="wb-sheet-scroll">
            <table className="wb-sheet-table">
              <thead>
                <tr>
                  <th className="wb-sheet-corner" />
                  {Array.from({ length: table.colCount }, (_, column) => (
                    <th key={column} className="wb-sheet-col">
                      {XLSX.utils.encode_col(column)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    <th className="wb-sheet-rowno">{rowIndex + 1}</th>
                    {Array.from({ length: table.colCount }, (_, column) => {
                      const key = `${rowIndex}:${column}`;
                      if (table.covered.has(key)) return null;
                      const span = table.spans.get(key);
                      const value = row[column];
                      const rawCell = table.sheet[XLSX.utils.encode_cell({ r: rowIndex, c: column })];
                      const formula = rawCell?.f ? `=${rawCell.f}` : "";
                      const text =
                        value != null && String(value) !== ""
                          ? String(value)
                          : rawCell?.w ?? formula;
                      const numeric = /^-?\d[\d,]*(\.\d+)?%?$/.test(text.trim());
                      return (
                        <td
                          key={key}
                          rowSpan={span?.rowSpan}
                          colSpan={span?.colSpan}
                          className={formula && !value ? "is-formula" : numeric ? "is-number" : undefined}
                          title={text}
                        >
                          {text}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </div>
  );
}
