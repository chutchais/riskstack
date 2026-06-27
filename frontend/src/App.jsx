import React from "react";
import Heatmap from "./components/Heatmap";

const demoCells = [
  { id: "c1", bay: 1, row: 1, tier: 1, status: "SAFE", score: 94, containerNumber: "MSCU1234567" },
  { id: "c2", bay: 2, row: 1, tier: 1, status: "WARNING", score: 72, containerNumber: "TCLU7654321" },
  { id: "c3", bay: 3, row: 1, tier: 2, status: "CRITICAL", score: 41, containerNumber: "OOLU9123456" },
  { id: "c4", bay: 1, row: 2, tier: 1, status: "SAFE", score: 89, containerNumber: "CMAU1122334" },
  { id: "c5", bay: 2, row: 2, tier: 2, status: "WARNING", score: 68, containerNumber: "HLCU5566778" },
];

export default function App() {
  return (
    <main className="app-shell">
      <h1 className="app-title">RiskStack Container Yard Safety</h1>
      <Heatmap block="A" cells={demoCells} maxBay={4} maxRow={3} />
    </main>
  );
}