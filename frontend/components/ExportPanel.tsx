"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE, ExportInfo, getExportInfo } from "@/lib/api";

export default function ExportPanel({
  paperId,
  revision,
}: {
  paperId: string;
  revision: number;
}) {
  const [info, setInfo] = useState<ExportInfo | null>(null);
  const [style, setStyle] = useState<string>("");

  useEffect(() => {
    let live = true;
    getExportInfo(paperId)
      .then((result) => {
        if (!live) return;
        setInfo(result);
        setStyle((current) => current || pickDefault(result));
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [paperId, revision]);

  const href = useCallback(
    (extension: string) =>
      `${API_BASE}/papers/${paperId}/${extension}` +
      `?revision=${revision}${style ? `&style=${style}` : ""}`,
    [paperId, revision, style],
  );

  if (!info) return null;

  const detected = info.detected_style !== "unknown";

  return (
    <div className="panel">
      <p className="panel__title">Export revision {revision}</p>
      <p className="hint">
        {detected ? (
          <>
            Detected style is <strong>{info.detected_style}</strong>. Citations
            are rendered by citeproc from the real CSL stylesheet, so changing
            this reformats the bibliography without touching the data.
          </>
        ) : (
          <>
            The citation style could not be detected confidently, so pick one.
            The bibliography is rendered by citeproc from that CSL stylesheet.
          </>
        )}
      </p>

      <div className="export">
        <label className="export__style">
          <span>Style</span>
          <select value={style} onChange={(event) => setStyle(event.target.value)}>
            {info.available_styles.map((name) => (
              <option key={name} value={name}>
                {name.toUpperCase()}
              </option>
            ))}
          </select>
        </label>

        <a className="button" href={href("export.tex")} download>
          Download .tex
        </a>
      </div>

      <p className="hint">
        Compiles to a PDF with one pdflatex run, or by dropping it into
        Overleaf. The bibliography is already inside the file, so no BibTeX
        step is needed.
      </p>
    </div>
  );
}

function pickDefault(info: ExportInfo): string {
  if (info.available_styles.includes(info.detected_style)) {
    return info.detected_style;
  }
  return info.available_styles[0] ?? "";
}
