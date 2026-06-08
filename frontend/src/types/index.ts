export interface FileNode {
  name: string;
  path: string;
  type: "folder" | "image";
  has_children?: boolean;
  children?: FileNode[];
  isOpen?: boolean;
  cover_images?: string[];
  mtime?: number; // Modified time from backend
  image_count?: number; // Number of images in folder (from backend)
  width?: number; // Image width in pixels (from backend scan)
  height?: number; // Image height in pixels (from backend scan)
}

export type SortField = "name" | "date";
export type SortOrder = "asc" | "desc";

export interface SortOption {
  field: SortField;
  order: SortOrder;
}

export type GenerationParams = {
  Seed?: string;
  Steps?: string;
  CFG?: string;
  Sampler?: string;
  Scheduler?: string;
  Model?: string;
  AspectRatio?: string;
  Width?: string;
  Height?: string;
  SwarmVersion?: string;
  Lora?: string[];
  // Allow backend to add additional fields in the future
  [key: string]: string | number | string[] | undefined;
};

export interface MetadataModelInfo {
  name?: string;
  param?: string;
  hash?: string;
}

export interface MetadataResponse {
  tool: string;
  prompt: string;
  negative_prompt: string;
  params: GenerationParams;
  models?: MetadataModelInfo[];
  date?: string;
  generation_time?: string;
  width: number | null;
  height: number | null;
  name: string;
  error?: string;
}

export interface ScanResponse {
  folders: FileNode[];
  images: FileNode[];
  next_cursor: number | null;
  total_images: number;
}

export type SearchScope = "current" | "all";

export interface UnifiedSearchResult {
  name: string;
  path: string;
  type: "folder" | "photo" | "file";
  parent_path: string;
  relative_path: string;
  mtime: number;
  width: number | null;
  height: number | null;
  cover_images?: string[];
  image_count?: number;
  match_type: string;
  model: string;
  sampler: string;
  seed: string;
  prompt_snippet: string;
}

export interface UnifiedSearchResults {
  albums: UnifiedSearchResult[];
  photos: UnifiedSearchResult[];
  prompt: UnifiedSearchResult[];
}

export interface UnifiedSearchResponse extends UnifiedSearchResults {
  query: string;
  scope: SearchScope;
  root: string;
}

export interface MetadataSearchResult {
  name: string;
  path: string;
  type: "file";
  mtime: number;
  width: number | null;
  height: number | null;
  model: string;
  sampler: string;
  seed: string;
  prompt_snippet: string;
}

export interface MetadataSearchResponse {
  query: string;
  total: number;
  results: MetadataSearchResult[];
}
