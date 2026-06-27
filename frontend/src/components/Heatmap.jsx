import React, { useMemo, useState } from "react";

/**
 * @typedef {"SAFE" | "WARNING" | "CRITICAL"} CellStatus
 */

/**
 * @typedef {Object} HeatmapCell
 * @property {string} id
 * @property {number} bay
 * @property {number} row
 * @property {number} tier
 * @property {CellStatus} status
 * @property {number=} score
 * @property {string=} containerNumber
 */

/**
 * @typedef {Object} HeatmapProps
 * @property {string} block
 * @property {HeatmapCell[]} cells
 * @property {number=} maxBay
 * @property {number=} maxRow
 * @property {(cell: HeatmapCell) => void=} onCellClick
 */

const STATUS_STYLE = {
  SAFE: "bg-emerald-500/90 border-emerald-300 text-emerald-50",
  WARNING: "bg-amber-500/90 border-amber-300 text-amber-50",
  CRITICAL: "bg-rose-600/90 border-rose-300 text-rose-50",
};

const STATUS_LABEL = {
  SAFE: "Green",
  WARNING: "Yellow",
  CRITICAL: "Red",
};

function buildCellIndex(cells) {
  const index = new Map();
  for (const cell of cells) {
    index.set(`${cell.bay}-${cell.row}`, cell);
  }
  return index;
}

/**
 * Heatmap grid for yard block safety status.
 * Uses Bay as X-axis and Row as Y-axis.
 *
 * @param {HeatmapProps} props
 */
export default function Heatmap({ block, cells, maxBay, maxRow, onCellClick }) {
  const [hoveredId, setHoveredId] = useState("");

  const computedMaxBay = useMemo(() => {
    if (typeof maxBay === "number" && maxBay > 0) {
      return maxBay;
    }
    return cells.length ? Math.max(...cells.map((c) => c.bay)) : 1;
  }, [cells, maxBay]);

  const computedMaxRow = useMemo(() => {
    if (typeof maxRow === "number" && maxRow > 0) {
      return maxRow;
    }
    return cells.length ? Math.max(...cells.map((c) => c.row)) : 1;
  }, [cells, maxRow]);

  const cellIndex = useMemo(() => buildCellIndex(cells), [cells]);

  const summary = useMemo(() => {
    const counts = { SAFE: 0, WARNING: 0, CRITICAL: 0 };
    for (const cell of cells) {
      counts[cell.status] += 1;
    }
    return counts;
  }, [cells]);

  const bays = useMemo(
    () => Array.from({ length: computedMaxBay }, (_, i) => i + 1),
    [computedMaxBay]
  );

  const rows = useMemo(
    () => Array.from({ length: computedMaxRow }, (_, i) => computedMaxRow - i),
    [computedMaxRow]
  );

  return (
    <section className="w-full rounded-2xl border border-slate-700 bg-slate-900 p-4 text-slate-100 shadow-xl sm:p-6">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-wide">Yard Heatmap</h2>
          <p className="text-sm text-slate-300">Block {block} safety status by bay and row</p>
        </div>

        <div className="flex items-center gap-3 text-xs sm:text-sm">
          <LegendPill label={`Green ${summary.SAFE}`} swatch="bg-emerald-500" />
          <LegendPill label={`Yellow ${summary.WARNING}`} swatch="bg-amber-500" />
          <LegendPill label={`Red ${summary.CRITICAL}`} swatch="bg-rose-600" />
        </div>
      </header>

      <div className="overflow-x-auto">
        <div
          className="inline-grid gap-1 rounded-xl bg-slate-950/60 p-2"
          style={{
            gridTemplateColumns: `3rem repeat(${computedMaxBay}, minmax(2.5rem, 1fr))`,
          }}
        >
          <div className="h-10" />
          {bays.map((bay) => (
            <div
              key={`bay-${bay}`}
              className="flex h-10 items-center justify-center rounded-md bg-slate-800 text-xs font-semibold text-slate-200"
            >
              B{bay}
            </div>
          ))}

          {rows.map((row) => (
            <React.Fragment key={`row-${row}`}>
              <div className="flex h-10 items-center justify-center rounded-md bg-slate-800 text-xs font-semibold text-slate-200">
                R{row}
              </div>

              {bays.map((bay) => {
                const key = `${bay}-${row}`;
                const cell = cellIndex.get(key);
                const status = cell?.status ?? "SAFE";
                const active = hoveredId === (cell?.id ?? "");

                return (
                  <button
                    key={key}
                    type="button"
                    onMouseEnter={() => setHoveredId(cell?.id ?? "")}
                    onMouseLeave={() => setHoveredId("")}
                    onClick={() => cell && onCellClick && onCellClick(cell)}
                    className={[
                      "relative h-10 rounded-md border text-[11px] font-semibold transition",
                      "focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400",
                      STATUS_STYLE[status],
                      active ? "scale-[1.02] ring-2 ring-white/80" : "hover:brightness-110",
                      !cell ? "opacity-35" : "opacity-100",
                    ].join(" ")}
                    title={
                      cell
                        ? [
                            `Container: ${cell.containerNumber || "N/A"}`,
                            `Status: ${STATUS_LABEL[cell.status]}`,
                            `Score: ${typeof cell.score === "number" ? cell.score.toFixed(1) : "N/A"}`,
                            `Tier: ${cell.tier}`,
                            `Bay/Row: ${cell.bay}/${cell.row}`,
                          ].join(" | ")
                        : `Bay ${bay}, Row ${row}: Empty`
                    }
                  >
                    {cell ? (cell.score != null ? cell.score.toFixed(0) : cell.tier) : "-"}
                  </button>
                );
              })}
            </React.Fragment>
          ))}
        </div>
      </div>

      <p className="mt-3 text-xs text-slate-400">
        Cell color maps directly to backend safety status metrics: SAFE (Green), WARNING (Yellow), CRITICAL (Red).
      </p>
    </section>
  );
}

function LegendPill({ label, swatch }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-800 px-3 py-1 text-slate-100">
      <span className={`h-2.5 w-2.5 rounded-full ${swatch}`} />
      {label}
    </span>
  );
}
