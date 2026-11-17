export type Gate = {
  status: string;
  decision: string | null;
  comment: string | null;
  actor: string | null;
  at: string | null;
};

export type Engagement = {
  id: string;
  name: string;
  sourceType: string;
  gitUrl?: string | null;
  gitBranch?: string | null;
  region: string;
  status: string;
  currentPhase: string;
  createdAt: string;
  updatedAt?: string;
  domain?: string;
  gates: Record<string, Gate>;
  inventory: {
    assets: { path: string; kind: string; language: string; loc: number }[];
    assetCount: number;
    counts: Record<string, number>;
    languages: Record<string, number>;
    warnings: string[];
  } | null;
  seed: Seed | null;
  scope: {
    capabilityId: string;
    name: string;
    programs: { id: string; name: string }[];
    tables: { id: string }[];
    sharedServices?: {
      resourceId: string;
      kind: "program" | "table";
      resourceName?: string;
      consumers: string[];
      recommendedStrategy?: string;
    }[];
    metrics: { programs: number; tables: number; sharedCount?: number; coupling: string; risk: string };
  } | null;

  feedbackHistory?: {
    timestamp: string;
    fromPhase: string;
    targetPhase: string;
    comment: string;
    reasoning: string;
    actionTaken?: string;
  }[];
  adoExport: { mode: string; message?: string; org?: string; project?: string; workItems: unknown[]; results?: unknown[] } | null;
  awsIntake?: { uri: string; uploadedAt: string; encryption: string } | null;
};

export type Integration = {
  id: string;
  name: string;
  kind: 'database' | 'internal-system' | 'third-party' | 'messaging' | 'file-transfer' | 'identity';
  protocol: string;
  direction: 'inbound' | 'outbound' | 'both';
  inCodebase: boolean;
  evidence: string;
  usedBy: string[];
  note?: string;
};

export type SemanticIR = {
  id: string;
  name: string;
  summary: string;
  module: string;
  inputs: { name: string; type: string; required: boolean }[];
  rules: {
    ruleId: string;
    statement: string;
    classification?: string;
    kind?: "deterministic_business_rule" | "legacy_plumbing_pruned";
    astNode: string;
    legacyLines: string;
    snippet: string;
    trustBoundary?: string;
  }[];
  stateMachine: string;
  sideEffects: string[];
  integrations: string[];
};

export type ClarificationQuestion = {
  id: string;
  text: string;
  why: string;
  kind: 'single' | 'text';
  options?: string[];
  recommended?: string;
  evidence?: { path: string; lines: string; snippet: string };
};

export type Telemetry = {
  summary: {
    totalRequests: number;
    totalInputTokens: number;
    totalOutputTokens: number;
    totalCostUsd: number;
    totalDurationMs: number;
    model: string;
    provider: string;
  };
  byPhase: {
    phase: string;
    action: string;
    model: string;
    inputTokens: number;
    outputTokens: number;
    costUsd: number;
    durationMs: number;
  }[];
};

export type CapabilityComponent = {
  id: string;
  name: string;
  kind: 'program' | 'table' | 'job' | 'screen';
  loc?: number;
  store?: string;
  role: string;
};

export type Strategy7R = {
  strategy: string;
  targetCloud: {
    aws: string;
    azure: string;
  };
  rationale: string;
  effortWeeks: number;
  roiScore: string;
};

export type FoundationalCheck = {
  id: string;
  title: string;
  status: 'PASS' | 'WARN' | 'FAIL';
  category: string;
  evidence: string;
  remediation: string;
};

export type FoundationalReadiness = {
  overallStatus: 'READY' | 'CONDITIONAL_APPROVAL' | 'BLOCKED';
  readinessScore: number;
  certifiedAt: string;
  checks: FoundationalCheck[];
};

export type DatabaseInvariant = {
  id: string;
  name: string;
  kind: string;
  table: string;
  database: string;
  purpose: string;
  legacySql: string;
  modernEquivalent: string;
  targetCloud: string;
  riskLevel: string;
};

export type CollationTestCase = {
  id: string;
  inputCodes?: string[];
  legacyEbcdicOrder?: string[];
  naiveAsciiOrder?: string[];
  fieldName?: string;
  legacyRepresentation?: string;
  modernRepresentation?: string;
  parityStatus?: string;
  flaggedDiscrepancy: boolean;
  remediation: string;
};

export type CollationParity = {
  collationScenario: string;
  explanation: string;
  testCases: CollationTestCase[];
};

export type CdcStatus = {
  activeRouting?: {
    cloudWeight: number;
    legacyWeight: number;
    targetEngine: string;
    mode: string;
    lastSwitchedAt: string;
    reason: string;
  };
  status: 'HEALTHY' | 'DEGRADED' | 'SYNCING';
  syncDirection: string;
  replicationEngine: string;
  forwardLagMs: number;
  reverseLagMs: number;
  conflictsDetectedToday: number;
  conflictResolutionStrategy: string;
  safeRollbackCertified: boolean;
  rollbackRecoveryPointSecs: number;
};


export type Seed = {
  domain: string;
  sample: string;
  programs: { id: string; name: string; capability: string; loc: number }[];
  capabilities: {
    id: string;
    name: string;
    summary: string;
    programs: number;
    tables: number;
    jobs: number;
    screens: number;
    loc?: number;
    complexity?: string;
    recommendedOrder?: number;
    dependsOn?: string[];
    integrations?: string[];
    components?: CapabilityComponent[];
    coupling: string;
    risk: string;
    riskScore?: number;
    riskBreakdown?: {
      blastRadiusPoints: number;
      storageComplexityPoints: number;
      codeVolumePoints: number;
      surfaceAreaPoints: number;
      rationale: string;
    };
    strategy7R?: Strategy7R;
  }[];
  graph: {
    nodes: {
      id: string;
      label: string;
      type: string;
      capability: string;
      position: { x: number; y: number };
    }[];
    edges: { id: string; source: string; target: string; kind: string }[];
  };
  discovery: {
    engine: string;
    region: string;
    objective: string;
    pattern: string;
    onlineVsBatch: { online: number; batch: number };
    complexity: string;
    techDebt: string[];
    transformStatus: string;
    notes: string;
    integrations?: Integration[];
  };
  semantic_ir?: SemanticIR[];
  clarifications?: Record<string, ClarificationQuestion[]>;
  telemetry?: Telemetry;
  copybook_schemas?: {
    id: string;
    sourceDataset: string;
    storageType: string;
    recordLayout: string;
    targetTable: string;
    fields: {
      level: number;
      name: string;
      picture: string;
      usage?: string;
      dataType: string;
      sqlColumn: string;
      sqlType: string;
      jpaAnnotation: string;
      notes?: string;
    }[];
    ddl: string;
    jpaEntity: string;
    dmsMapping: string;
  }[];
  shadow_parity?: {
    summary: {
      totalVectors: number;
      passedParity: number;
      flaggedDiscrepancies: number;
      parityRatePct: number;
      tolerances: string;
    };
    testCases: {
      id: string;
      description: string;
      legacyPayloadType: string;
      legacyInputHex: string;
      legacyOutput: Record<string, any>;
      modernOutput: Record<string, any>;
      status: 'MATCH' | 'DISCREPANCY';
      fieldDiffs: {
        field: string;
        legacyVal: string;
        modernVal: string;
        diffReason: string;
      }[];
    }[];
    shadowHarnessCode: string;
  };
  wave_cutover?: {
    waves: {
      waveNumber: number;
      name: string;
      strategy: string;
      riskLevel: string;
      durationWeeks: number;
      modules: string[];
      routingRule: string;
      rollbackPlan: string;
      canaryPercent: number;
    }[];
    stranglerRouting: {
      ingress: string;
      rules: {
        path: string;
        method: string;
        target: 'MAINFRAME_CICS' | 'AWS_SPRING_BOOT';
        weight: number;
        featureFlag: string;
      }[];
      apiGatewayConfig: string;
    };
  };
  requirements: {
    id: string;
    type: string;
    statement: string;
    description?: string;
    acceptanceCriteria?: string[];
    definitionOfDone?: string;
    traces: string[];
    astNodes?: string[];
    sirRules?: string[];
    stories?: string[];
    targetCode?: string;
    testCases?: string[];
  }[];
  backlog: {
    id: string;
    type: string;
    title: string;
    userStory?: string;
    acceptanceCriteria?: string[];
    definitionOfDone?: string;
    wave: number;
    moscow: string;
    storyPoints?: number;
    requirementIds: string[];
    traces?: string[];
    astNodes?: string[];
    sirRules?: string[];
    adoId?: string;
    adoUrl?: string;
    adoStatus?: string;
    targetCode?: string;
    testCases?: string[];
  }[];
  target: {
    language: string;
    framework: string;
    architecture: string;
    pattern: string;
    data: string;
    modules: { id: string; package: string; wave: number }[];
    events: string[];
    landingZone: Record<string, string>;
    transform: { engine: string; sideArtifact: string };
  };
  tests: { id: string; req: string; kind: string; title: string }[];
  failures: {
    id: string;
    phase: string;
    code: string;
    severity?: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
    title?: string;
    message: string;
    impact?: string;
    evidence?: string;
    astNode?: string;
    suggestedAction: string;
    resolved: boolean;
  }[];
  coveragePct: number;
  applied_graph?: AppliedGraph;
  scope_analysis?: ScopeAnalysis;
  foundational_readiness?: FoundationalReadiness;
  database_invariants?: DatabaseInvariant[];
  collation_parity?: CollationParity;
  cdc_status?: CdcStatus;
};

export type ScopeAnalysis = {
  useCaseFlows: {
    id: string;
    entryPoint: string;
    entryLabel: string;
    entryType: string;
    callChain: string[];
    tablesRead: string[];
    tablesWritten: string[];
    transactionBoundary: string[];
    isMutation: boolean;
    candidateUseCaseName: string;
  }[];
  logicalModules: {
    moduleId: string;
    programs: string[];
    tables: string[];
    ownedTables: string[];
    intraEdges: number;
    crossEdges: number;
    cohesionScore: number;
    sharedKernels: string[];
    isHighlyCoupled: boolean;
    recommendedBoundary: string;
  }[];
  businessRules: {
    ruleId: string;
    module: string;
    statement: string;
    classification: string;
    astNode: string;
    legacyEvidence: string;
    snippet: string;
    trustBoundary: string;
    domainVocabulary: string[];
  }[];
  domainVocabulary: string[];
  summary: {
    totalUseCaseFlows: number;
    mutatingFlows: number;
    readOnlyFlows: number;
    logicalModuleCount: number;
    businessRuleCount: number;
    sharedKernelCount: number;
  };
  basis: string;
};

export type AppliedGraphNode = {
  id: string;
  label: string;
  type: string;
  capability: string;
  position: { x: number; y: number };
  semanticRole?: string;
  trustBoundary?: string;
  sirRules?: string[];
};

export type AppliedGraphEdge = {
  id: string;
  source: string;
  target: string;
  kind: string;
  semanticType?: string;
  modernEquivalent?: string;
  migrationRisk?: string;
};

export type WorkflowChain = {
  id: string;
  sirRule: string;
  sirStatement: string;
  astNode: string;
  legacyEvidence: string;
  requirement: string;
  requirementStatement: string;
  backlogItem: string;
  backlogTitle: string;
  wave: number;
  testCases: string[];
  trustBoundary: string;
  traceComplete: boolean;
};

export type SharedKernel = {
  id: string;
  nodeId: string;
  nodeType: string;
  consumingCapabilities: string[];
  couplingDegree: number;
  recommendation: string;
  migrationRisk: string;
};

export type AppliedGraph = {
  nodes: AppliedGraphNode[];
  edges: AppliedGraphEdge[];
  dataLineage: {
    id: string;
    source: string;
    target: string;
    kind: string;
    sourceField: string;
    targetColumn: string;
    sourceType: string;
    targetType: string;
    conversionNote: string;
    migrationRisk: string;
  }[];
  workflowChains: WorkflowChain[];
  sharedKernels: SharedKernel[];
  statistics: {
    totalNodes: number;
    capabilityNodes: number;
    programNodes: number;
    tableNodes: number;
    eventNodes: number;
    totalEdges: number;
    edgesByKind: Record<string, number>;
    dataLineageFields: number;
    totalWorkflowChains: number;
    tracedWorkflowChains: number;
    sharedKernelCount: number;
  };
  semanticIndex: {
    nodesByRole: Record<string, string[]>;
    nodesByTrustBoundary: Record<string, string[]>;
    edgesBySemanticType: Record<string, string[]>;
  };
  basis: string;
};

export type PhaseMeta = { id: string; label: string; group: string };

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  meta: () => fetch("/api/meta").then((r) => parse<{ phases: PhaseMeta[] }>(r)),
  list: () =>
    fetch("/api/engagements").then((r) =>
      parse<Pick<Engagement, "id" | "name" | "sourceType" | "status" | "currentPhase" | "updatedAt" | "domain">[]>(r),
    ),
  get: (id: string) => fetch(`/api/engagements/${id}`).then((r) => parse<Engagement>(r)),
  sample: () => fetch("/api/engagements/sample", { method: "POST" }).then((r) => parse<Engagement>(r)),
  git: (url: string, branch: string) =>
    fetch("/api/engagements/git", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, branch }),
    }).then((r) => parse<Engagement>(r)),
  zip: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch("/api/engagements/zip", { method: "POST", body: fd }).then((r) => parse<Engagement>(r));
  },
  folder: (path: string, name?: string) =>
    fetch("/api/engagements/folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, name }),
    }).then((r) => parse<Engagement>(r)),
  gate: (id: string, phase: string, decision: "approved" | "rejected", comment: string, actor: string) =>
    fetch(`/api/engagements/${id}/gates/${phase}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, comment, actor }),
    }).then((r) => parse<Engagement>(r)),
  scope: (id: string, capabilityId: string) =>
    fetch(`/api/engagements/${id}/scope`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ capabilityId }),
    }).then((r) => parse<Engagement>(r)),
  scopeAnalysis: (id: string) =>
    fetch(`/api/engagements/${id}/scope-analysis`).then((r) => parse<ScopeAnalysis>(r)),
  postpone: (id: string, dependencyId: string, reason?: string, strategy?: "spike" | "acl") =>
    fetch(`/api/engagements/${id}/scope/postpone`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dependencyId, reason, strategy }),
    }).then((r) => parse<Engagement>(r)),
  ado: (id: string, config?: { org?: string; project?: string; pat?: string }) =>
    fetch(`/api/engagements/${id}/ado-export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config || {}),
    }).then((r) => parse<Engagement["adoExport"]>(r)),
  feedback: (id: string, comment: string, currentPhase: string) =>
    fetch(`/api/engagements/${id}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment, currentPhase }),
    }).then((r) =>
      parse<{
        ok: boolean;
        targetPhase: string;
        reasoning: string;
        actionTaken: string;
        engagement: Engagement;
      }>(r),
    ),
  awsIntake: (id: string) =>
    fetch(`/api/engagements/${id}/aws-intake`, { method: "POST" }).then((r) => parse<Engagement>(r)),
  playwright: (id: string) =>
    fetch(`/api/engagements/${id}/playwright`).then((r) =>
      parse<{ files: Record<string, string>; summary: { specs: number; pages: number; fixtures: number } }>(r),
    ),
  bedrockGenerate: (id: string) =>
    fetch(`/api/engagements/${id}/bedrock/generate`, { method: "POST" }).then((r) =>
      parse<{ ok: boolean; srs: string; c4: string; playwrightFiles: string[] }>(r),
    ),
  setTarget: (id: string, target: { language: string; framework: string; data: string; architecture: string }) =>
    fetch(`/api/engagements/${id}/target`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(target),
    }).then((r) => parse<Engagement>(r)),
  clarifications: (id: string, phase: string, answers: Record<string, string>) =>
    fetch(`/api/engagements/${id}/clarifications/${phase}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    }).then((r) => parse<Engagement>(r)),
  foundationalReadiness: (id: string) =>
    fetch(`/api/engagements/${id}/foundational-readiness`).then((r) => parse<FoundationalReadiness>(r)),
  databaseInvariants: (id: string) =>
    fetch(`/api/engagements/${id}/database-invariants`).then((r) => parse<DatabaseInvariant[]>(r)),
  collationParity: (id: string) =>
    fetch(`/api/engagements/${id}/collation-parity`).then((r) => parse<CollationParity>(r)),
  cdcStatus: (id: string) =>
    fetch(`/api/engagements/${id}/cdc-status`).then((r) => parse<CdcStatus>(r)),
  sharedKernels: (id: string) =>
    fetch(`/api/engagements/${id}/shared-kernels`).then((r) =>
      parse<{
        capability: string;
        totalSharedKernels: number;
        status: string;
        artifacts: Array<{
          resourceId: string;
          resourceName: string;
          kind: string;
          consumers: string[];
          pattern: string;
          openapiSpec: string;
          syncStrategy: string;
          blastRadiusRisk: string;
        }>;
      }>(r),
    ),
  functionalRules: (id: string) =>
    fetch(`/api/engagements/${id}/functional-rules`).then((r) =>
      parse<{
        capability: string;
        totalRulesSynthesized: number;
        gherkinFeatures: Array<{
          requirementId: string;
          statement: string;
          traces: string;
          gherkinFeature: string;
          verificationStatus: string;
        }>;
      }>(r),
    ),
  terraformAzure: (id: string) =>
    fetch(`/api/engagements/${id}/terraform/azure`).then((r) =>
      parse<{ files: Record<string, string> }>(r),
    ),
  githubPublish: (
    id: string,
    payload: { repoName: string; token?: string; org?: string; private?: boolean },
  ) =>
    fetch(`/api/engagements/${id}/github-publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) =>
      parse<{
        ok: boolean;
        repoUrl?: string;
        owner?: string;
        filesCommitted?: number;
        workflowUrl?: string;
        error?: string;
      }>(r),
    ),
  goldenParity: (id: string) =>
    fetch(`/api/engagements/${id}/golden-parity`).then((r) =>
      parse<{
        engagementId: string;
        totalVectorsReplayed: number;
        identicalMatches: number;
        discrepancyCount: number;
        parityConfidenceScore: number;
        maxTolerancePct: number;
        status: string;
        piiMaskingApplied: boolean;
        executionEngine: string;
        sampleVectors: Array<{
          vectorId: string;
          transactionCode: string;
          scenario: string;
          inputPayload: Record<string, any>;
          legacyOutput: {
            rawHexDump: string;
            decodedCommarea: Record<string, string>;
          };
          modernOutput: {
            jsonResponse: Record<string, any>;
            httpStatus: number;
            latencyMs: number;
          };
          status: string;
          deltaDetails: Array<{
            field: string;
            legacyValue: string;
            modernValue: string;
            diff: string;
            rootCause: string;
            remediation: string;
          }>;
        }>;
        discrepancies: Array<{
          vectorId: string;
          field: string;
          legacyValue: string;
          modernValue: string;
          delta: string;
          rootCause: string;
          remediation: string;
          severity: string;
        }>;
      }>(r),
    ),
  batchModernize: (id: string, jclText?: string) =>
    fetch(`/api/engagements/${id}/batch-modernize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jclText }),
    }).then((r: Response) =>
      parse<{
        sourceJcl: string;
        stepsParsed: number;
        targetRuntime: string;
        springBatchConfig: string;
        chunkSize: number;
        idempotencyKeyStrategy: string;
        dataPipelineDefinition: Record<string, any>;
      }>(r),
    ),
  sagaOrchestrator: (id: string) =>
    fetch(`/api/engagements/${id}/saga-orchestrator`).then((r: Response) =>
      parse<{
        sagaName: string;
        coordinatorPattern: string;
        isolationLevel: string;
        steps: Array<{
          stepNumber: number;
          service: string;
          action: string;
          compensatingAction: string;
          timeoutMs: number;
        }>;
        stateMachineDefinition: Record<string, any>;
        javaOrchestratorCode: string;
      }>(r),
    ),
  canaryRouting: (id: string, payload: { cloudWeight: number; targetEngine?: string; reason?: string }) =>
    fetch(`/api/engagements/${id}/canary-routing`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r: Response) =>
      parse<{
        ok: boolean;
        activeRouting: {
          cloudWeight: number;
          legacyWeight: number;
          targetEngine: string;
          mode: string;
          lastSwitchedAt: string;
          reason?: string;
        };
        cdcStatus: any;
        driftAlert?: string | null;
      }>(r),
    ),
  instantRollback: (id: string) =>
    fetch(`/api/engagements/${id}/instant-rollback`, {
      method: "POST",
    }).then((r: Response) =>
      parse<{
        ok: boolean;
        message: string;
        activeRouting: {
          cloudWeight: number;
          legacyWeight: number;
          targetEngine: string;
          mode: string;
          lastSwitchedAt: string;
          reason?: string;
        };
        cdcStatus: any;
      }>(r),
    ),
  setDiscoveryEngine: (id: string, engineId: 'universal' | 'transform') =>
    fetch(`/api/engagements/${id}/discovery-engine`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engineId }),
    }).then((r: Response) =>
      parse<{
        ok: boolean;
        discoveryEngine: string;
        discovery: any;
      }>(r),
    ),
  knowledgeGraph: (id: string) =>
    fetch(`/api/engagements/${id}/knowledge-graph`).then((r) => parse<AppliedGraph>(r)),
  packUrl: (id: string) => `/api/engagements/${id}/pack`,
};


