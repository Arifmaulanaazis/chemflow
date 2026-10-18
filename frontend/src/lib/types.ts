export interface Job {
  id: string;
  name: string;
  command: string;
  status: string;
  created: number;
  started: number | null;
  finished: number | null;
  exit_code: number | null;
  stage: string | null;
  pending_input?: boolean;
}
export interface Resources {
  cpu: number;
  cores: number;
  ram_percent: number;
  ram_used: number;
  ram_total: number;
  disk_percent: number;
  disk_free: number;
  platform: string;
  time: number;
}
export interface Artifact {
  path: string;
  size: number;
  modified: number;
  extension: string;
}
export interface Upload {
  purpose?: string | null;
  id: string;
  name: string;
  size: number;
}
export interface Option {
  name: string;
  flag: string;
  label: string;
  group: string;
  help: string;
  required: boolean;
  kind: "boolean" | "file" | "number" | "text" | "tool";
  multiple: boolean;
  count: number | null;
  choices: string[] | null;
  tool_choices?: { id: string; label: string }[] | null;
  default: unknown;
}
export interface Schema {
  commands: Record<string, Option[]>;
  platform: string;
  version: string;
  biovia: boolean;
  max_upload_mb: number;
}
export interface Update {
  status: string;
  current: string;
  latest?: string;
  url?: string;
  message?: string;
  checked_at?: number;
  source_status?: string;
  source_local?: string;
  source_remote?: string;
  automatic?: {
    mode: string;
    status?: string;
    message?: string;
    latest?: string;
  };
}
export interface Preview {
  kind: string;
  text?: string;
  rows?: unknown[][];
  sheets?: string[];
  sheet?: string;
  truncated?: boolean;
}
