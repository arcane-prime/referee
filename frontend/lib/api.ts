const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface UploadedPaper {
  paper_id: string;
  filename: string;
  size_bytes: number;
  uploaded_at: string;
}

export interface TextRun {
  kind: "text";
  text: string;
}

export interface CiteNode {
  kind: "cite";
  id: string;
  ref_ids: string[];
  raw_marker: string | null;
}

export interface XRefNode {
  kind: "xref";
  id: string;
  target_kind: string;
  label: string;
}

export interface MathNode {
  kind: "math";
  id: string;
  source: string;
}

export type Inline = TextRun | CiteNode | XRefNode | MathNode;

export interface Block {
  id: string;
  kind: "paragraph" | "heading" | "abstract" | "caption" | "formula";
  inlines: Inline[];
  label: string | null;
}

export interface Section {
  id: string;
  title: string;
  level: number;
  blocks: Block[];
}

export interface ExtractedDocument {
  id: string;
  paper_id: string;
  revision: number;
  title: string;
  authors: string[];
  style: string;
  style_confidence: number;
  sections: Section[];
}

export interface CSLItem {
  id: string;
  title: string | null;
  DOI: string | null;
}

export interface RawReference {
  id: string;
  raw: string;
  parsed: CSLItem | null;
}

export interface ExtractionSummary {
  section_count: number;
  block_count: number;
  citation_count: number;
  unlinked_citation_count: number;
  references: {
    total: number;
    good: number;
    degraded: number;
    failed: number;
  };
  detected_style: string;
  style_confidence: number;
}

export interface ExtractionResult {
  paper_id: string;
  extracted_at: string;
  parser: string;
  document: ExtractedDocument;
  references: RawReference[];
  summary: ExtractionSummary;
}

export interface ApiError {
  code: string;
  detail: string;
}

export class RefereeApiError extends Error {
  readonly code: string;

  constructor(code: string, detail: string) {
    super(detail);
    this.name = "RefereeApiError";
    this.code = code;
  }
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new RefereeApiError("network_error", "Could not reach the server.");
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiError | null;
    throw new RefereeApiError(
      body?.code ?? "request_failed",
      body?.detail ?? `Request failed with status ${response.status}.`,
    );
  }

  return (await response.json()) as T;
}

export async function uploadPaper(file: File): Promise<UploadedPaper> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadedPaper>("/papers", { method: "POST", body: form });
}

export async function extractPaper(paperId: string): Promise<ExtractionResult> {
  return request<ExtractionResult>(`/papers/${paperId}/extract`, { method: "POST" });
}

/*
 Notes

 FormData is passed to fetch without a Content-Type header on purpose. The
 browser generates multipart/form-data along with the boundary token; setting
 the header manually omits the boundary and the request fails to parse server
 side.

 The backend answers failures with {code, detail}. `code` is the stable value
 to branch on; `detail` is for display. A thrown RefereeApiError therefore
 always carries something showable, including for transport failures where no
 response body exists.

 The Inline union mirrors the backend's discriminated union on `kind`, so the
 renderer switches on the same discriminator the parser wrote. Citations are
 nodes here for the same reason they are nodes on the server: the marker text
 is never part of the prose, and the UI is what turns a CiteNode back into
 something a reader sees.
*/
