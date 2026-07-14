/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import type { AnySchema } from "ajv";
import Ajv2020 from "ajv/dist/2020.js";

import type { FileHealthIssues, FileHealthRepairs, FileHealthResponse, FileHealthRun } from "@/services/api";

const backendFixturePath = (name: string): string =>
  resolve(process.cwd(), "../backend/tests/fixtures/file_health", name);

const frontendSchemaPath = (): string =>
  resolve(process.cwd(), "src/contracts/schemas/file-health-response.schema.json");

const loadFixture = <T>(name: string): T => JSON.parse(readFileSync(backendFixturePath(name), "utf8")) as T;

const EXPECTED_ISSUE_KEYS: (keyof FileHealthIssues)[] = [
  "missing_source_files",
  "generated_image_missing",
  "generated_image_abandoned",
  "metadata_mismatch",
  "file_index_ownership_mismatch",
  "orphaned_work_item",
  "generated_image_job_mismatch",
];

const EXPECTED_REPAIR_KEYS: (keyof FileHealthRepairs)[] = [
  "repaired",
  "requeued",
  "failed",
  "skipped",
  "recovered",
  "unchanged",
];

const EXPECTED_RUN_KEYS: (keyof FileHealthRun)[] = [
  "id",
  "trigger",
  "started_at",
  "finished_at",
  "status",
  "error",
  "issues",
  "repairs",
];

const ENVELOPE_KEYS: (keyof FileHealthResponse)[] = ["run"];

describe("maintenance file-health contract fixtures", () => {
  let schema: AnySchema;
  let validate: ReturnType<Ajv2020["compile"]>;

  beforeAll(() => {
    schema = JSON.parse(readFileSync(frontendSchemaPath(), "utf8")) as AnySchema;
    validate = new Ajv2020().compile(schema);
  });

  it("never-run fixture validates and matches expected shape", () => {
    const fixture = loadFixture<FileHealthResponse>("never_run.json");
    expect(validate(fixture)).toBe(true);
    expect(Object.keys(fixture)).toEqual(ENVELOPE_KEYS);
    expect(fixture.run).toBeNull();
  });

  it("success fixture validates and has correct key sets", () => {
    const fixture = loadFixture<FileHealthResponse>("success.json");
    expect(validate(fixture)).toBe(true);
    expect(Object.keys(fixture)).toEqual(ENVELOPE_KEYS);
    const run = fixture.run!;
    expect(Object.keys(run)).toEqual(EXPECTED_RUN_KEYS);
    expect(Object.keys(run.issues)).toEqual(EXPECTED_ISSUE_KEYS);
    expect(Object.keys(run.repairs)).toEqual(EXPECTED_REPAIR_KEYS);
    expect(run.status).toBe("ok");
    expect(run.trigger).toMatch(/^(manual|daemon)$/);
    expect(Object.values(run.issues).some((v) => v > 0)).toBe(true);
    expect(Object.values(run.repairs).some((v) => v > 0)).toBe(true);
  });

  it("error fixture validates and has zero counts", () => {
    const fixture = loadFixture<FileHealthResponse>("error.json");
    expect(validate(fixture)).toBe(true);
    const run = fixture.run!;
    expect(run.status).toBe("error");
    expect(run.error).toBe("boom");
    expect(Object.values(run.issues).every((v) => v === 0)).toBe(true);
    expect(Object.values(run.repairs).every((v) => v === 0)).toBe(true);
  });

  it("schema-compat fixture validates boundary values", () => {
    const fixture = loadFixture<FileHealthResponse>("schema_compat.json");
    expect(validate(fixture)).toBe(true);
    const run = fixture.run!;
    expect(run.started_at).toBe(0);
    expect(run.finished_at).toBe(0.001);
    expect(Object.values(run.issues).every((v) => v >= 0)).toBe(true);
    expect(Object.values(run.repairs).every((v) => v >= 0)).toBe(true);
  });

  it("validates backend Pydantic frozen key-sets match frontend types", () => {
    const fixture = loadFixture<FileHealthResponse>("success.json");
    const run = fixture.run!;
    // issues keys must match FileHealthIssues exactly
    for (const key of EXPECTED_ISSUE_KEYS) {
      expect(run.issues).toHaveProperty(key);
    }
    expect(Object.keys(run.issues).length).toBe(EXPECTED_ISSUE_KEYS.length);
    // repairs keys must match FileHealthRepairs exactly
    for (const key of EXPECTED_REPAIR_KEYS) {
      expect(run.repairs).toHaveProperty(key);
    }
    expect(Object.keys(run.repairs).length).toBe(EXPECTED_REPAIR_KEYS.length);
  });
});
