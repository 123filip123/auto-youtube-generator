// Mirrors api/schemas.py field for field. Change both together.

export type RunStatus =
  | "pending"
  | "generating_script"
  | "generating_prompts"
  | "awaiting_review"
  | "generating_media"
  | "composing_frames"
  | "rendering_video"
  | "archiving"
  | "completed"
  | "failed"
  | "cancelled";

/** Statuses after which polling should stop. Mirrors api.runs.TERMINAL_STATUSES. */
export const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set<RunStatus>([
  "completed",
  "failed",
  "cancelled",
]);

/** The stages shown in the progress indicator, in order. */
export const STAGE_SEQUENCE: readonly { status: RunStatus; label: string }[] = [
  { status: "generating_script", label: "Write script" },
  { status: "generating_prompts", label: "Design drawings" },
  { status: "awaiting_review", label: "Review script" },
  { status: "generating_media", label: "Images & audio" },
  { status: "composing_frames", label: "Compose frames" },
  { status: "rendering_video", label: "Render video" },
  { status: "archiving", label: "Archive" },
];

export interface Section {
  label: string;
  narration: string;
  prompts: string[];
  /** Server-derived timings; sent back but ignored on write. */
  start: number;
  end: number;
}

export interface ScriptPayload {
  topic: string;
  title: string;
  style: string;
  sections: Section[];
}

export interface AssetStatus {
  label: string;
  ok: boolean;
  error: string | null;
}

export interface RunSummary {
  id: string;
  topic: string;
  target_seconds: number;
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
}

export interface RunDetail extends RunSummary {
  review_script: boolean;
  overrides: Record<string, string | number>;
  script: ScriptPayload;
  assets: AssetStatus[];
  asset_total: number;
  logs: string[];
  error: string | null;
  video_url: string | null;
  archive_slug: string | null;
}

export interface CreateRunRequest {
  topic: string;
  target_seconds: number;
  review_script: boolean;
  overrides: Record<string, string | number>;
}

export interface ConfigField {
  name: string;
  type: "int" | "str";
  choices: string[] | null;
  description: string;
}

export interface ConfigPayload {
  values: Record<string, string | number>;
  overridable: ConfigField[];
}

export interface ArchiveSummary {
  slug: string;
  section_count: number;
  image_count: number;
  audio_count: number;
  has_video: boolean;
  legacy: boolean;
  modified_at: string;
}

export interface ArchiveSection {
  label: string;
  narration: string;
  prompts: string[];
  start: number;
  end: number;
  image_urls: string[];
  composed_image_urls: string[];
  audio_url: string | null;
}

export interface ArchiveDetail {
  slug: string;
  topic: string;
  title: string;
  style: string;
  video_url: string | null;
  legacy: boolean;
  sections: ArchiveSection[];
}
