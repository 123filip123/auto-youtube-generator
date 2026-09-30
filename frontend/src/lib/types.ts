// Mirrors api/schemas.py field for field. Change both together.

export type RunStatus =
  | "pending"
  | "generating_list"
  | "awaiting_review"
  | "generating_media"
  | "rendering_titles"
  | "rendering_video"
  | "archiving"
  | "completed"
  | "failed"
  | "cancelled";

/** Statuses after which polling should stop. Mirrors api.runs.TERMINAL_STATUSES. */
export const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

/** The stages shown in the progress indicator, in order. */
export const STAGE_SEQUENCE: readonly { status: RunStatus; label: string }[] = [
  { status: "generating_list", label: "Generate list" },
  { status: "awaiting_review", label: "Review items" },
  { status: "generating_media", label: "Images & audio" },
  { status: "rendering_titles", label: "Titled images" },
  { status: "rendering_video", label: "Render video" },
  { status: "archiving", label: "Archive" },
];

export interface ItemPayload {
  title: string;
  description: string;
  image_prompts: string[];
}

export interface AssetStatus {
  label: string;
  ok: boolean;
  error: string | null;
}

export interface RunSummary {
  id: string;
  topic: string;
  num_items: number;
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
}

export interface RunDetail extends RunSummary {
  review_items: boolean;
  overrides: Record<string, string | number>;
  production_models: boolean;
  items: ItemPayload[];
  assets: AssetStatus[];
  asset_total: number;
  logs: string[];
  error: string | null;
  video_url: string | null;
  archive_slug: string | null;
}

export interface CreateRunRequest {
  topic: string;
  num_items: number;
  review_items: boolean;
  overrides: Record<string, string | number>;
  production_models: boolean;
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
  production_image_settings: Record<string, string>;
}

export interface ArchiveSummary {
  slug: string;
  item_count: number;
  image_count: number;
  audio_count: number;
  has_video: boolean;
  modified_at: string;
}

export interface ArchiveItem {
  title: string;
  description: string;
  image_prompts: string[];
  image_urls: string[];
  titled_image_urls: string[];
  audio_url: string | null;
}

export interface ArchiveDetail {
  slug: string;
  video_url: string | null;
  items: ArchiveItem[];
}
