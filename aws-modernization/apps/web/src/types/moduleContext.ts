export type ContextFinding = {
  code: string;
  severity: 'blocker' | 'warning' | 'info';
  message: string;
  artifactId: string | null;
  evidence: string[];
  action: string;
};

export type ContextTemplate = {
  id: string;
  kind: string;
  language: string;
  framework: string;
  major: string | null;
  limitations: string[];
  available: boolean;
  sourceIdentity: string;
  revision: string;
  dependencies: {name: string; version: string | null}[];
  files: {name: string; sha256: string; applicability: {condition: string; evaluation: string}}[];
  compatibility: {status: string; issues: {code: string; message: string; severity: string}[]};
};

export type ContextPackage = {
  schemaVersion: string;
  packageId: string;
  engagementId: string;
  moduleId: string;
  createdAt: string;
  inputFingerprint: string;
  packageDigest: string;
  source: { repository: string | null; requestedBranch: string | null; repositoryContentDigest: string };
  templates: { id: string; contentDigest: string; fileCount: number; revision?: string; compatibility?: ContextTemplate["compatibility"] }[];
  artifacts: {
    id: string; kind: string; path: string; role: string; provenance: string;
    validation: string; sha256: string; bytes: number; approval: Record<string, unknown>;
  }[];
  coverage: { sourceFiles: number; sirContracts: number; stories: number };
  contract?: {
    artifactCount: number;
    traceability: { summary: {
      resolvedRelationships: number; missingRelationships: number; unresolvedReferences: number;
      uncoveredBusinessRules: number; requirementsWithoutStoryCoverage: number;
      storiesWithoutAcceptanceCriteria: number; acceptanceCriteriaWithoutTestCoverage: number | null;
    }};
    dependencies: { counts: Record<string, number> };
    approvals: { records: { gateId: string; status: string | null; decision: string | null; binding: string }[] };
    target: { language: string | null; framework: string | null; frameworkVersion: string | null; database: string | null; apiApproach: string | null; missingFields: string[] };
    readiness: { overallStatus: 'NOT_READY' | 'READY_WITH_WARNINGS' | 'READY'; counts: Record<string, number> };
  };
  readiness: {
    packageIntegrity: string;
    modernizationPrerequisites: string;
    executionVerified: boolean;
    findings: ContextFinding[];
  };
};
