# Applied Knowledge Graph for .NET sources

Engagements whose source contains a `.sln` or `.csproj` get their AKG from `apps/api/app/dotnet_akg/`.
Two rules hold for everything it emits:

1. Nodes and edges come from parsers that understand the language (tree-sitter C# and TypeScript
   grammars, plus a solution-wide symbol table), not from text matching.
2. Every edge records `{file, line, rule_id}` plus an `evidence` list with each call site. An edge without
   a location is rejected, and the applied graph drops any that reach it (`edgesDroppedWithoutLocation`).

Roslyn would give a complete semantic model, but it needs a .NET SDK on the API host. The symbol
table here covers the subset the graph needs: namespace-, `using`- and alias-aware resolution, member
lookup through base chains, and generic substitution. Unresolvable expressions produce no edge.

## Inputs

| Input | Read from |
|---|---|
| Which files belong to the app | `.sln` → each `.csproj` (`Compile`, `TypeScriptCompile`, `Content`, `ProjectReference`). SDK-style projects compile `**/*.cs`. TypeScript outside every project, such as a separate SPA folder, is also scanned. |
| C# | tree-sitter C# grammar + `SymbolTable` (`csharp.py`) |
| TypeScript | tree-sitter TypeScript/TSX grammar: `$resource`, `$http.*` and `fetch` calls with their HTTP verbs |
| Razor | `@model`, `Html.Partial`, `ng-controller`, and the `View("…")` call site in the controller |
| Config | XML parse of `Web.config`/`App.config` (connection strings, app settings) |
| Column types | The EF6 model in the newest migration `.resx` (`Target` EDMX): entity → table, property → column, store type |

## Edge rules

| Edge | Rule ids | Detection |
|---|---|---|
| `CALLS` | `call.invocation`, `call.object-creation`, `call.inherited-member` | Invocation or `new` whose receiver resolves to another solution type |
| `ACCESSES_DATA` | `data.repository-call`, `data.dbset-call` | Receiver derives from a generic repository base (a solution type holding `DbSet<T>` of its own `T`), or is `DbSet<T>`. The entity is the bound `T`. Read or write is classified from the repository method body (`EntityState.Added/Modified/Deleted`, `DbSet.Add/Remove`); `Detach` is neither. |
| `INHERITS` / `IMPLEMENTS` | `base-list.*` | Resolved base list entries that are solution types |
| `REFERENCES` | `entity.navigation-property`, `ef.fluent-relationship` | Entity navigation properties; `HasRequired/HasMany(...).WithRequired(...)` |
| `MAPS_TO` | `automapper.create-map`, `automapper.reverse-map` | `CreateMap<TSource, TDest>` generic arguments |
| `HTTP_CALLS` | `http.attribute-route`, `http.convention-route+verb`, `http.convention-route+action-name` | TS URL + verb matched to `[RoutePrefix]`/`[Route]`/`[HttpX("…")]` templates, then to `MapHttpRoute` conventions |
| `INVOKES_EXTERNAL` | `external.object-creation`, `external.member-call` | A type the solution does not define, confirmed by the file's `using` (`catalog.EXTERNAL_TYPES`) |
| `EMITS_EVENT` | `event.publisher-call` | Only real publishers (MediatR, MassTransit, Service Bus, EventBridge, SNS). Comments and SIR prose never create events. |
| `RENDERS`, `BINDS_MODEL`, `INCLUDES`, `HOSTS_SCRIPT` | `razor.*` | Razor views |
| `READS_CONFIG` | `config.configuration-manager` | `ConfigurationManager.AppSettings["k"]` / `ConnectionStrings["k"]` |
| `CONTAINS` | `capability.*` | Capability membership, located at the type declaration, with the reason in `basis` |

## Capabilities

1. **Aggregates come from the EF model plus behaviour.** EF maps most 1:N relations in both directions,
   so `E` joins `P`'s aggregate only when they form a 1:N pair and most workflows that write `E` also write `P`.
   Entities that no workflow writes are reference data: they go to the one aggregate that references them, or to
   `platform` when several do. Hub entities, such as an audit log that references most of the model, never own anything.
2. **Code goes where it writes.** Score per capability: write ×3, read ×1, AutoMapper map ×2. Ties go to the upstream
   aggregate. A spread across three or more capabilities with no clear leader goes to `platform`.
3. **Platform:** generic repository bases, DbContexts, `HttpApplication`, and anything used by three or more capabilities.
4. **Propagation:** types with no data affinity follow their callers, callees and views.
5. **Satellites fold in:** an aggregate written only from one other capability becomes part of it.
6. **Overrides beat every rule.** Use `akg-overrides.json` in the engagement folder (or the source root), or
   `PUT /api/engagements/{id}/akg-overrides`:

```json
{
  "rename": {"invoice": "Billing, Invoicing & SOA"},
  "merge":  {"soa": "invoice"},
  "assign": {"DefaultRebateController": "policy"}
}
```

Every node carries `capabilityBasis` (rule + detail) explaining its assignment.

## Derived layers

- **Lineage:** view-model property → entity property (AutoMapper `ForMember`, name match, or flattening such as
  `ClientName` → `Client.Name`) → table column and store type from the EF snapshot. A numeric type change
  (`double` → `decimal(18,2)`) is high risk.
- **Code workflows:** from each TS HTTP call, each controller action not already reached from the front end, and
  `Application_Start`. The walk follows method-level calls (including private helpers) to depth 6. A workflow is
  *fully traced* only when it ends at a write, an external call or an event.
- **Shared kernels:** capability pairs with edges in both directions, plus nodes used by three or more capabilities,
  weighted by edge count.

## Testing

```bash
cd apps/api
python -m pytest tests/test_dotnet_akg.py
# score any solution against a hand-checked reference graph
python -m app.dotnet_akg.evaluate --root <solution dir> --reference ref.json --min-recall 1 --min-precision 1
```

- `tests/fixtures/legacy_shop` (EF6, Web API 2, AngularJS, unit of work) and `tests/fixtures/modern_tickets`
  (SDK-style, ASP.NET Core attribute routing, DbContext injection, MediatR) each have a `*.reference.json`.
  Precision and recall must be 1.0 per edge type.
- `regression_checks` enforces the invariants on every run: no unlocated edges, no `external:` node for a solution
  type, no event without a publisher call, and no lineage row without a source.
- The IMS tests run when `IMS_ROOT` points to the IMS source (default `C:\Sai\git-legacy codes\ims`). They
  recompute every `Uow.<Repo>.<Method>()` site with an independent method and require an exact match.

Reference format: `{"closedSources": [...], "edges": [{"kind", "source", "target"}]}`, using node ids
(fully-qualified type names, `ts:<path>`, `view:<path>`, `external:<ns.Type>`).
