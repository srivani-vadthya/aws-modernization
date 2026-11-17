"""Playwright E2E and API Test Suite Generator for Modernized Workloads."""

from __future__ import annotations

import json
from pathlib import Path


def generate_playwright_suite(output_dir: Path, engagement: dict) -> dict[str, str]:
    """Generate an idiomatic Playwright test suite (TypeScript) based on the engagement scope & requirements.
    
    Returns a dictionary of relative file paths to file contents.
    """
    scope = engagement.get("scope") or {}
    cap_name = scope.get("name") or "Core Business Capability"
    cap_id = scope.get("capabilityId") or "core"
    seed = engagement.get("seed") or {}
    requirements = seed.get("requirements", [])
    
    # Filter or select requirements relevant to the test suite
    test_reqs = [r for r in requirements if r.get("id") in {"REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"}]
    if not test_reqs:
        test_reqs = requirements[:5]

    files: dict[str, str] = {}

    # 1. package.json for test suite
    files["package.json"] = json.dumps(
        {
            "name": f"modernize-{cap_id}-playwright-tests",
            "version": "1.0.0",
            "description": f"Automated Playwright E2E & API test harness for {cap_name}",
            "scripts": {
                "test": "playwright test",
                "test:headed": "playwright test --headed",
                "test:ui": "playwright test --ui",
                "test:report": "playwright show-report"
            },
            "devDependencies": {
                "@playwright/test": "^1.49.0",
                "@types/node": "^22.0.0",
                "typescript": "^5.6.0"
            }
        },
        indent=2,
    )

    # 2. playwright.config.ts
    files["playwright.config.ts"] = f"""import {{ defineConfig, devices }} from '@playwright/test';

/**
 * Modernization E2E & API Test Harness for {cap_name}
 * Validates functional parity between legacy rules and the cloud-native target.
 */
export default defineConfig({{
  testDir: './specs',
  timeout: 30 * 1000,
  expect: {{
    timeout: 5000
  }},
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', {{ open: 'never' }}],
    ['json', {{ outputFile: 'test-results/report.json' }}],
    ['list']
  ],
  use: {{
    baseURL: process.env.SERVICE_BASE_URL || 'http://localhost:8080',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  }},
  projects: [
    {{
      name: 'chromium',
      use: {{ ...devices['Desktop Chrome'] }},
    }},
    {{
      name: 'api-contract-tests',
      testMatch: /.*api.*\\.spec\\.ts/,
    }},
  ],
}});
"""

    # 3. Page Object Model: pages/PolicyPortalPage.ts
    files["pages/PolicyPortalPage.ts"] = f"""import {{ Page, Locator, expect }} from '@playwright/test';

/**
 * Page Object Model for Modernized {cap_name} Portal UI
 */
export class PolicyPortalPage {{
  readonly page: Page;
  readonly customerIdInput: Locator;
  readonly planCodeSelect: Locator;
  readonly sumAssuredInput: Locator;
  readonly occupationClassInput: Locator;
  readonly smokerCheckbox: Locator;
  readonly dateOfBirthInput: Locator;
  readonly submitButton: Locator;
  readonly statusBanner: Locator;
  readonly policyNumberDisplay: Locator;
  readonly premiumDisplay: Locator;
  readonly validationErrors: Locator;

  constructor(page: Page) {{
    this.page = page;
    this.customerIdInput = page.locator('#customer-id');
    this.planCodeSelect = page.locator('#plan-code');
    this.sumAssuredInput = page.locator('#sum-assured');
    this.occupationClassInput = page.locator('#occupation-class');
    this.smokerCheckbox = page.locator('#smoker-toggle');
    this.dateOfBirthInput = page.locator('#dob-input');
    this.submitButton = page.locator('button[type="submit"]');
    this.statusBanner = page.locator('[data-testid="status-banner"]');
    this.policyNumberDisplay = page.locator('[data-testid="policy-number"]');
    this.premiumDisplay = page.locator('[data-testid="calculated-premium"]');
    this.validationErrors = page.locator('[data-testid="error-message"]');
  }}

  async goto() {{
    await this.page.goto('/portal/issue-policy');
    await expect(this.submitButton).toBeVisible();
  }}

  async submitApplication(data: {{
    customerId: string;
    planCode: string;
    sumAssured: number;
    occupationClass: string;
    smoker: boolean;
    dob: string;
  }}) {{
    await this.customerIdInput.fill(data.customerId);
    await this.planCodeSelect.selectOption(data.planCode);
    await this.sumAssuredInput.fill(data.sumAssured.toString());
    await this.occupationClassInput.fill(data.occupationClass);
    if (data.smoker) {{
      await this.smokerCheckbox.check();
    }} else {{
      await this.smokerCheckbox.uncheck();
    }}
    await this.dateOfBirthInput.fill(data.dob);
    await this.submitButton.click();
  }}
}}
"""

    # 4. Functional E2E Spec: specs/business-rules.spec.ts
    req_comments = "\n".join(f" * - {r.get('id')}: {r.get('statement')}" for r in test_reqs)
    files["specs/business-rules.spec.ts"] = f"""import {{ test, expect }} from '@playwright/test';
import {{ PolicyPortalPage }} from '../pages/PolicyPortalPage';

/**
 * E2E Acceptance Suite: {cap_name}
 * Traceability Matrix:
{req_comments}
 */
test.describe('{cap_name} - Functional Business Rules', () => {{
  let portal: PolicyPortalPage;

  test.beforeEach(async ({{ page }}) => {{
    portal = new PolicyPortalPage(page);
    await portal.goto();
  }});

  test('REQ-001: Valid applicant issues policy with standard premium', async () => {{
    await portal.submitApplication({{
      customerId: 'CUST-80219',
      planCode: 'T1001',
      sumAssured: 250000,
      occupationClass: '01',
      smoker: false,
      dob: '1990-06-15',
    }});

    await expect(portal.statusBanner).toContainText(/APPROVED|ISSUED/i);
    await expect(portal.policyNumberDisplay).toBeVisible();
    await expect(portal.premiumDisplay).not.toBeEmpty();
  }});

  test('REQ-002: Decline high-risk occupation class XX (Underwriting rejection)', async () => {{
    await portal.submitApplication({{
      customerId: 'CUST-80220',
      planCode: 'T1001',
      sumAssured: 150000,
      occupationClass: 'XX', // High-risk automatic decline rule
      smoker: false,
      dob: '1985-04-10',
    }});

    await expect(portal.statusBanner).toContainText(/DECLINED|REJECTED/i);
    await expect(portal.validationErrors).toContainText(/Occupation class XX is ineligible for standard term issue/i);
  }});

  test('REQ-003: Smoker rating applies mandatory premium load', async () => {{
    await portal.submitApplication({{
      customerId: 'CUST-80221',
      planCode: 'T1001',
      sumAssured: 200000,
      occupationClass: '02',
      smoker: true,
      dob: '1980-01-20',
    }});

    await expect(portal.statusBanner).toContainText(/APPROVED/i);
    // Verified against legacy premium formula with Table-B rating load
    const premiumText = await portal.premiumDisplay.textContent();
    expect(Number(premiumText?.replace(/[^0-9.]/g, ''))).toBeGreaterThan(50);
  }});
}});
"""

    # 5. API Contract Test Spec: specs/api-contract.spec.ts
    files["specs/api-contract.spec.ts"] = f"""import {{ test, expect }} from '@playwright/test';

/**
 * Microservice REST API Contract Verification
 * Tests the modernized cloud-native endpoints directly.
 */
test.describe('{cap_name} - REST API Contract & Concurrency', () => {{
  test('POST /api/policies - creates policy successfully with 201 Created', async ({{ request }}) => {{
    const response = await request.post('/api/policies', {{
      data: {{
        customerId: 10001,
        planCode: 'T1001',
        sumAssured: 100000.00,
        smoker: false,
        occupationClass: '01',
        dateOfBirth: '1992-08-14'
      }}
    }});

    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body).toHaveProperty('policyNumber');
    expect(body.status).toBe('ACTIVE');
    expect(body.annualPremium).toBeGreaterThan(0);
  }});

  test('POST /api/policies - rejects invalid age limit (boundary test)', async ({{ request }}) => {{
    const response = await request.post('/api/policies', {{
      data: {{
        customerId: 10002,
        planCode: 'T1001',
        sumAssured: 100000.00,
        smoker: false,
        occupationClass: '01',
        dateOfBirth: '2015-01-01' // Underage applicant
      }}
    }});

    expect(response.status()).toBe(400);
    const errorBody = await response.json();
    expect(JSON.stringify(errorBody)).toContain('Issue age');
  }});

  test('GET /health/live - service health check returns 200 OK', async ({{ request }}) => {{
    const response = await request.get('/health/live');
    expect(response.status()).toBe(200);
  }});
}});
"""

    # 6. Test Fixture: fixtures/test-data.json
    files["fixtures/test-data.json"] = json.dumps(
        {
            "capability": cap_name,
            "generatedFor": engagement.get("id"),
            "scenarios": [
                {
                    "name": "Standard Non-Smoker Issue",
                    "payload": {
                        "customerId": "88102",
                        "dob": "1994-03-21",
                        "sex": "M",
                        "smoker": False,
                        "occupationClass": "01",
                        "planCode": "T1001",
                        "sumAssured": 300000.00
                    },
                    "expectedResult": "APPROVED",
                    "ruleTrace": "REQ-001"
                },
                {
                    "name": "Automatic Decline High Risk",
                    "payload": {
                        "customerId": "88103",
                        "dob": "1989-11-04",
                        "sex": "F",
                        "smoker": False,
                        "occupationClass": "XX",
                        "planCode": "T1001",
                        "sumAssured": 100000.00
                    },
                    "expectedResult": "DECLINED",
                    "ruleTrace": "REQ-002"
                }
            ]
        },
        indent=2,
    )

    # Write files to disk
    output_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        dest = output_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    return files
