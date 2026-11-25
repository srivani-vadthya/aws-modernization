export type EngineFinding = { code: string; severity: 'blocker' | 'warning' | 'info'; message: string; evidence: string[]; source: string };

export type EnginePreview = {
  engagementId: string; moduleId: string; packageId: string; packageSchemaVersion: string | null;
  packageIntegrity: string; overallStatus: 'NOT_READY' | 'READY_WITH_WARNINGS' | 'READY'; executable: boolean;
  target: Record<string, unknown>; templates: {id: string; revision: string; compatibility?: {status: string}}[];
  findings: EngineFinding[];
};

export type ModernizationRun = {
  runId: string; engagementId: string; moduleId: string; packageId: string; packageSchemaVersion: string;
  status: 'DRAFT' | 'VALIDATING' | 'BLOCKED' | 'READY_FOR_APPROVAL' | 'APPROVED' | 'PLANNED' | 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  createdAt: string; updatedAt: string; validation: EnginePreview;
};

export type PlanReference = {artifactId: string; pointer: string; entityId?: string | null};
export type ModernizationTask = {
  taskId: string; name: string; description: string; category: string; workstreamId: string;
  sourceArtifacts: PlanReference[]; businessRules: PlanReference[]; requirements: PlanReference[]; stories: PlanReference[]; acceptanceCriteria: PlanReference[];
  dependencies: string[]; suggestedProvider: string; providerRationale: string; capabilityVerification: Record<string, unknown>; expectedOutputFolders: string[]; fallbackEligible: boolean; fallbackProvider?: string | null; planningStatus: 'proposed' | 'blocked'; risks: string[];
};
export type ModernizationPlan = {
  planId: string; packageId: string; packageDigest: string; status: 'DRAFT_PLAN' | 'BLOCKED_PLAN' | 'READY_FOR_REVIEW' | 'APPROVED_PLAN'; stale: boolean;
  strategy: {category: string; rationale: string; confidence: string; risks: string[]; unresolvedQuestions: string[]};
  providerReadiness: Record<string, {status: string; issues: string[]; verification: string}>; workstreams: {id: string; name: string; rationale: string; taskIds: string[]}[]; tasks: ModernizationTask[]; dependencyOrder: string[][];
  risks: EngineFinding[]; blockers: EngineFinding[]; createdAt: string;
};

export type ModernizationAgent = {agentId: string; name: string; description: string; taskCategories: string[]; availability: string; capabilityMetadata: Record<string, unknown>};
export type OrchestrationAssignment = {taskId: string; agentId: string; assignmentRationale: string; prerequisiteTasks: string[]; status: string; blockedReasons: string[]; expectedOutputs: string[]};
export type OrchestrationRecord = {orchestrationId: string; planId: string; status: string; stale: boolean; assignments: OrchestrationAssignment[]; readyTaskIds: string[]; blockedTaskIds: string[]; independentTaskIds: string[]; findings: EngineFinding[]};
export type ExecutionRecord = {executionId: string; status: string; executionAuthorized: boolean; tasks: {taskId: string; agentId: string; status: string; attempts: unknown[]}[]; logs: {at: string; taskId?: string; agentId?: string; provider?: string; eventType: string; message: string; status: string}[]; checkpoints: unknown[]; artifacts: GeneratedArtifact[]; validation?: {stage: string; status: string; message: string}[]};
export type GeneratedArtifact = {artifactId: string; path: string; artifactType: string; sourceTaskId: string; sha256?: string; validationStatus: string};
