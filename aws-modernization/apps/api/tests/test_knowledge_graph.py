from app.knowledge_graph import identify_scope


def test_identify_scope_traces_use_cases_and_reports_module_evidence():
    seed = {
        "graph": {
            "nodes": [
                {"id": "ORDER-SCREEN", "label": "Order Submit Screen", "type": "screen", "capability": "orders"},
                {"id": "ORDER-SVC", "label": "Order Service", "type": "program", "capability": "orders"},
                {"id": "ORDER-TABLE", "label": "ORDER", "type": "table", "capability": "orders"},
                {"id": "INVOICE-TABLE", "label": "INVOICE", "type": "table", "capability": "orders"},
                {"id": "CUSTOMER-TABLE", "label": "CUSTOMER", "type": "table", "capability": "orders"},
                {"id": "COMMON-LOGGER", "label": "Common Logger", "type": "program", "capability": "orders"},
                {"id": "BILLING-SVC", "label": "Billing Service", "type": "program", "capability": "billing"},
            ],
            "edges": [
                {"id": "SCREEN-CALL", "source": "ORDER-SCREEN", "target": "ORDER-SVC", "kind": "CALLS"},
                {"id": "SERVICE-WRITE", "source": "ORDER-SVC", "target": "ORDER-TABLE", "kind": "WRITES"},
                {"id": "SERVICE-INVOICE-WRITE", "source": "ORDER-SVC", "target": "INVOICE-TABLE", "kind": "WRITES"},
                {"id": "SERVICE-READ", "source": "ORDER-SVC", "target": "CUSTOMER-TABLE", "kind": "READS"},
                {"id": "BILLING-ORDER-WRITE", "source": "BILLING-SVC", "target": "ORDER-TABLE", "kind": "WRITES"},
            ],
        },
        "programs": [
            {"id": "ORDER-SVC", "capability": "orders"},
            {"id": "COMMON-LOGGER", "capability": "orders"},
            {"id": "BILLING-SVC", "capability": "billing"},
        ],
        "tables": [
            {"id": "ORDER-TABLE", "capability": "orders"},
            {"id": "INVOICE-TABLE", "capability": "orders"},
            {"id": "CUSTOMER-TABLE", "capability": "orders"},
        ],
        "semantic_ir": [
            {
                "id": "SIR-ORDER",
                "module": "orders",
                "rules": [
                    {
                        "ruleId": "RULE-ORDER-1",
                        "statement": "Validate order before accepting the order.",
                        "astNode": "ORDER-SVC:VALIDATE",
                        "kind": "deterministic_business_rule",
                    }
                ],
            }
        ],
    }

    report = identify_scope(seed)

    assert len(report["useCaseFlows"]) == 1
    flow = report["useCaseFlows"][0]
    assert flow["entryPoint"] == "ORDER-SCREEN"
    assert flow["callChain"] == ["ORDER-SVC"]
    assert flow["tablesRead"] == ["CUSTOMER-TABLE"]
    assert flow["tablesWritten"] == ["INVOICE-TABLE", "ORDER-TABLE"]
    assert flow["transactionBoundary"] == ["CUSTOMER-TABLE", "INVOICE-TABLE", "ORDER-TABLE"]
    assert flow["isMutation"] is True

    module = next(item for item in report["logicalModules"] if item["moduleId"] == "orders")
    assert module["ownedTables"] == ["INVOICE-TABLE"]
    assert "ORDER-TABLE" in module["sharedKernels"]
    assert "COMMON-LOGGER" not in module["programs"]
    assert report["businessRules"][0]["ruleId"] == "RULE-ORDER-1"
    assert "Order" in report["domainVocabulary"]
