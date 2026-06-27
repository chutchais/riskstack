import React from "react";
import axios from "axios";
import Heatmap from "./components/Heatmap";

const demoCells = [
  { id: "c1", bay: 1, row: 1, tier: 1, status: "SAFE", score: 94, containerNumber: "MSCU1234567" },
  { id: "c2", bay: 2, row: 1, tier: 1, status: "WARNING", score: 72, containerNumber: "TCLU7654321" },
  { id: "c3", bay: 3, row: 1, tier: 2, status: "CRITICAL", score: 41, containerNumber: "OOLU9123456" },
  { id: "c4", bay: 1, row: 2, tier: 1, status: "SAFE", score: 89, containerNumber: "CMAU1122334" },
  { id: "c5", bay: 2, row: 2, tier: 2, status: "WARNING", score: 68, containerNumber: "HLCU5566778" },
];

export default function App() {
  const [file, setFile] = React.useState(null);
  const [uploadedBy, setUploadedBy] = React.useState("");
  const [isUploading, setIsUploading] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState("");
  const [uploadResult, setUploadResult] = React.useState(null);
  const [batchDetails, setBatchDetails] = React.useState(null);

  const containerNumberById = React.useMemo(() => {
    const map = new Map();
    for (const item of batchDetails?.containers || []) {
      map.set(item.container_id, item.container_number);
    }
    return map;
  }, [batchDetails]);

  const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

  async function handleSubmit(event) {
    event.preventDefault();
    if (!file) {
      setErrorMessage("Please choose an EDI file before uploading.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    if (uploadedBy.trim()) {
      formData.append("uploaded_by", uploadedBy.trim());
    }

    setIsUploading(true);
    setErrorMessage("");
    setUploadResult(null);
    setBatchDetails(null);

    try {
      const response = await axios.post(`${apiBaseUrl}/upload/edi`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const summary = response.data;
      setUploadResult(summary);

      if (summary?.batch_id) {
        const detailResponse = await axios.get(`${apiBaseUrl}/historical/batches/${summary.batch_id}`);
        setBatchDetails(detailResponse.data);
      }
    } catch (error) {
      const apiError = error?.response?.data?.detail;
      setErrorMessage(typeof apiError === "string" ? apiError : error.message || "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <main className="app-shell">
      <h1 className="app-title">RiskStack Container Yard Safety</h1>

      <section className="upload-panel">
        <h2 className="upload-title">Upload EDI File</h2>
        <p className="upload-subtitle">POST to {apiBaseUrl}/upload/edi</p>

        <form className="upload-form" onSubmit={handleSubmit}>
          <label className="field-label" htmlFor="uploadedBy">
            Uploaded by
          </label>
          <input
            id="uploadedBy"
            type="text"
            value={uploadedBy}
            onChange={(event) => setUploadedBy(event.target.value)}
            placeholder="Optional name"
            className="text-input"
          />

          <label className="field-label" htmlFor="ediFile">
            EDI file
          </label>
          <input
            id="ediFile"
            type="file"
            accept=".edi,.txt"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
            className="file-input"
          />

          <button type="submit" className="upload-button" disabled={isUploading}>
            {isUploading ? "Uploading..." : "Upload and Evaluate"}
          </button>
        </form>

        {errorMessage ? <p className="error-text">{errorMessage}</p> : null}

        {uploadResult ? (
          <div className="result-panel">
            <h3 className="result-title">Result</h3>
            <pre className="result-json">{JSON.stringify(uploadResult, null, 2)}</pre>
          </div>
        ) : null}

        {batchDetails ? (
          <div className="result-panel">
            <h3 className="result-title">Batch Details</h3>
            <div className="result-grid">
              <p><strong>Batch ID:</strong> {batchDetails.batch_id}</p>
              <p><strong>Status:</strong> {batchDetails.processing_status}</p>
              <p><strong>Total Containers:</strong> {batchDetails.total_containers}</p>
              <p><strong>Evaluations:</strong> {batchDetails.evaluations?.length ?? 0}</p>
            </div>

            <h4 className="result-subtitle">Latest Evaluations (Top 20)</h4>
            <div className="table-wrap">
              <table className="result-table">
                <thead>
                  <tr>
                    <th>Container Number</th>
                    <th>Status</th>
                    <th>Score</th>
                    <th>Racking</th>
                    <th>Wind</th>
                    <th>Tier Load</th>
                    <th>Corner Stress</th>
                  </tr>
                </thead>
                <tbody>
                  {(batchDetails.evaluations || []).slice(0, 100).map((item) => (
                    <tr key={item.evaluation_id}>
                      <td>{containerNumberById.get(item.container_id) || item.container_id}</td>
                      <td>{item.status}</td>
                      <td>{item.overall_score?.toFixed?.(1) ?? item.overall_score}</td>
                      <td>{item.racking_ratio?.toFixed?.(3) ?? item.racking_ratio}</td>
                      <td>{item.wind_exposure_ratio?.toFixed?.(3) ?? item.wind_exposure_ratio}</td>
                      <td>{item.tier_load_ratio?.toFixed?.(3) ?? item.tier_load_ratio}</td>
                      <td>{item.corner_post_stress_ratio?.toFixed?.(3) ?? item.corner_post_stress_ratio}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </section>

      <Heatmap block="A" cells={demoCells} maxBay={4} maxRow={3} />
    </main>
  );
}