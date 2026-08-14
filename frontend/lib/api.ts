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

export interface Verification {
  attempted: boolean;
  succeeded: boolean;
  message: string | null;
  search_api: string | null;
  resolved: number;
  ambiguous: number;
  unresolved: number;
  with_abstract: number;
  with_doi: number;
}

export interface ExtractionResult {
  paper_id: string;
  extracted_at: string;
  parser: string;
  document: ExtractedDocument;
  references: ResolvedReference[];
  summary: ExtractionSummary;
  verification: Verification;
}

export type ResolutionStatus = "resolved" | "ambiguous" | "unresolved";

export interface ExternalIds {
  doi: string | null;
  openalex: string | null;
  semantic_scholar: string | null;
}

export interface Resolution {
  status: ResolutionStatus;
  score: number;
  matched: CSLItem | null;
  external_ids: ExternalIds;
  abstract: string | null;
  source_api: string | null;
  abstract_source: string | null;
  reason: string | null;
}

export interface ResolvedReference {
  id: string;
  raw: string;
  parsed: CSLItem | null;
  resolution: Resolution;
  provenance: string;
}

export type SupportGrade =
  | "supports"
  | "partially_supports"
  | "not_supported"
  | "insufficient_evidence";

export interface Evidence {
  ref_id: string;
  quote: string | null;
  grade: SupportGrade;
  note: string | null;
  quote_verified: boolean;
  source_title: string | null;
  source_doi: string | null;
  source_url: string | null;
}

export interface SuggestedSource {
  title: string;
  doi: string | null;
  openalex_id: string | null;
  url: string | null;
  year: number | null;
  reason: string | null;
}

export interface Finding {
  id: string;
  kind: "unsupported_claim" | "missing_citation" | "uncited_claim";
  severity: "high" | "medium" | "low";
  block_id: string;
  sentence_index: number;
  start: number;
  end: number;
  sentence: string;
  message: string;
  evidence: Evidence[];
  suggested_sources: SuggestedSource[];
}

export interface ReviewSummary {
  sentences_examined: number;
  claims_with_citations: number;
  citations_checked: number;
  references_without_abstract: number;
  findings_total: number;
  unsupported_claims: number;
  missing_citations: number;
}

export interface ReviewResult {
  paper_id: string;
  reviewed_at: string;
  model: string;
  findings: Finding[];
  summary: ReviewSummary;
}

export type OperationKind =
  | "shorten_block"
  | "rewrite_block"
  | "add_citation"
  | "delete_block";

export interface CitationDelta {
  added: string[];
  removed: string[];
  moved: string[];
}

export interface BlockPatch {
  block_id: string;
  operation: OperationKind;
  before: Inline[];
  after: Inline[];
  before_text: string;
  after_text: string;
  citations: CitationDelta;
  deleted: boolean;
}

export interface RejectedOperation {
  block_id: string;
  operation: OperationKind;
  reason: string;
}

export interface RevisionProposal {
  paper_id: string;
  base_revision: number;
  command: string;
  intent: string;
  patches: BlockPatch[];
  rejected: RejectedOperation[];
  citations: CitationDelta;
  note: string | null;
}

export interface ProposalResult {
  proposal: RevisionProposal;
  applicable: boolean;
  message: string | null;
}

export interface AppliedRevision {
  paper_id: string;
  revision: number;
  base_revision: number;
  command: string;
  applied_blocks: string[];
  citations: CitationDelta;
}

export interface AppliedResult {
  applied: AppliedRevision;
  message: string;
}

export interface CurrentDocument {
  paper_id: string;
  revision: number;
  available_revisions: number[];
  document: ExtractedDocument;
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

export async function reviewPaper(
  paperId: string,
  verified: boolean,
): Promise<ReviewResult> {
  const query = new URLSearchParams({
    check_support: String(verified),
    find_uncited_claims: "true",
    find_missing_work: String(verified),
  });
  return request<ReviewResult>(`/papers/${paperId}/review?${query}`, {
    method: "POST",
  });
}

export async function planEdit(
  paperId: string,
  command: string,
): Promise<ProposalResult> {
  return request<ProposalResult>(`/papers/${paperId}/edit/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command }),
  });
}

export async function applyEdit(
  paperId: string,
  proposal: RevisionProposal,
  approved: string[],
): Promise<AppliedResult> {
  return request<AppliedResult>(`/papers/${paperId}/edit/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ proposal, approved }),
  });
}

export async function getDocument(
  paperId: string,
  revision?: number,
): Promise<CurrentDocument> {
  const query = revision === undefined ? "" : `?revision=${revision}`;
  return request<CurrentDocument>(`/papers/${paperId}/document${query}`, {
    method: "GET",
  });
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

 There is no client for POST /papers/{id}/resolve, though the endpoint exists.
 Resolution runs as part of extraction, so the UI never calls it on its own.
 The route stays on the server because the resolution module owns it and is
 usable independently; adding a function here that nothing calls would not make
 that any more true.

 planEdit and applyEdit are two calls because approval is a real step. planEdit
 writes nothing on the server; it returns what would happen. The proposal is
 then sent back verbatim to applyEdit, which re-verifies it against the
 document on disk rather than trusting what came from the browser. That is why
 the whole proposal travels rather than an id: the server holds no session
 state, and a proposal cannot expire because a process restarted.

 `approved` carries block ids, so a researcher can accept two changes and drop
 the third. The server treats an absent list as "all of them", but this client
 always sends an explicit list, because in a UI with checkboxes the difference
 between "everything" and "everything that happens to be ticked" is a bug
 waiting to be found by a user who unticked one.

 getDocument exists so the paper can be re-read after an edit without re-running
 extraction. Re-extracting would call GROBID and the literature databases again
 to rebuild a document that is already on disk.
*/
