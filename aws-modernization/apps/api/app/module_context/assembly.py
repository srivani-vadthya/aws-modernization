"""Build indexes solely from collected snapshots, never from upstream generators."""
import json
import re
from collections import Counter
import xml.etree.ElementTree as ET
from .contracts import EngineContract
from .repository import canonical, digest


def pointer(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def readiness_contract(findings):
    counts = Counter(f.severity for f in findings)
    categories = {}
    for i, f in enumerate(findings):
        code = f.code
        category = ("approval" if "APPROVAL" in code or "APPROVED" in code else
                    "compatibility" if "TEMPLATE" in code or "TARGET" in code or "REACT" in code else
                    "unresolved-reference" if "TRACE" in code or "REFERENCE" in code else
                    "missing-evidence" if any(s in code for s in ("MISSING", "BASELINE", "UNAVAILABLE", "GAPS", "NOT_PERSISTED")) else "validation")
        categories.setdefault(category, []).append(i)
    status = "NOT_READY" if counts['blocker'] else "READY_WITH_WARNINGS" if counts['warning'] else "READY"
    return {"overallStatus": status, "counts": dict(counts), "categories": categories}


def assemble(c):
    artifacts = {a.id: a for a in c.artifacts}
    def snap(name, default):
        a = artifacts.get(name)
        return json.loads(c.files[a.path]) if a else default
    def ref(a, p=""):
        return {"artifactId": a, "pointer": p}
    entities, links, deps = [], [], []
    def entity(kind, original, a, p):
        key = kind + ":" + str(original)
        if any(e['id'] == key for e in entities):
            c.finding("DUPLICATE_UPSTREAM_ID", "Duplicate identity in collected evidence.", a, "blocker", [p])
            key += ":occurrence:" + str(len(entities))
        entities.append({"id": key, "kind": kind, "originalId": str(original), "reference": ref(a, p)})
        return key
    def link(kind, source, target, evidence, original=None, missing=False):
        status = "resolved" if target else "missing" if missing else "unresolved"
        links.append({"kind": kind, "fromId": source, "toId": target, "status": status,
                      "originalReference": str(original) if original is not None else None,
                      "evidence": evidence,
                      "explanation": "Explicit upstream relationship." if target else
                        "No upstream relationship is recorded." if missing else "Recorded reference cannot be resolved within collected evidence."})
    def dep(category, status, name, evidence, implementation=None, version=None, explanation="Recorded evidence; runtime behavior not verified."):
        deps.append({"id": "dependency:" + str(len(deps)), "category": category, "status": status,
                     "name": str(name), "version": str(version) if version is not None else None,
                     "implementationArtifactId": implementation, "evidence": evidence, "explanation": explanation})
    sources = {a.path.removeprefix("source/"): entity("source", a.path.removeprefix("source/"), a.id, "")
               for a in c.artifacts if a.kind == "source"}
    nodes = {}
    graph = snap('module-graph', {})
    for i, n in enumerate(graph.get('nodes', [])):
        p = '/nodes/' + str(i)
        key = entity('akg', n['id'], 'module-graph', p)
        nodes[n['id']] = key
        path = n.get('file') or n.get('path')
        if path:
            link('akg-source', key, sources.get(path), ref('module-graph',p), path)
        if n.get('type') in {'entity','table','database','config','external','integration','event'}:
            category = 'database' if n['type'] in {'entity','table','database'} else 'configuration' if n['type']=='config' else 'messaging' if n['type']=='event' else 'external-service'
            impl = 'source:' + path if path in sources else None
            dep(category, 'potential' if category in {'database','configuration'} else 'external-incomplete',n['id'],ref('module-graph',p),impl)
    for i, edge in enumerate(graph.get('edges', [])):
        a, b = edge.get('source'), edge.get('target')
        dep('internal', 'potential' if a in nodes and b in nodes else 'unresolved', str(a)+' -> '+str(b),ref('module-graph','/edges/'+str(i)))
    sir = snap('sir', [])
    contracts, rules = {}, {}
    for i, s in enumerate(sir):
        p='/'+str(i);key=entity('sir',s['id'],'sir',p);contracts[s['id']]=key
        entry=(s.get('trace') or {}).get('entryPoint')
        link('sir-akg',key,nodes.get(entry),ref('sir',p),entry,missing=not entry)
        for j,r in enumerate(s.get('rules', [])):
            rkey=entity('rule',r.get('ruleId',p+'/rules/'+str(j)),'sir',p+'/rules/'+str(j))
            if r.get('ruleId'): rules[r['ruleId']]=rkey
            link('sir-rule',key,rkey,ref('sir',p+'/rules/'+str(j)))
        for j, integration in enumerate(s.get('integrations', [])):
            dep('external-service','external-incomplete',integration if isinstance(integration,str) else integration.get('id',integration.get('name','unnamed')),ref('sir',p+'/integrations/'+str(j)))
    requirements=snap('requirements',{}).get('requirements',[])
    reqs={r['id']:entity('requirement',r['id'],'requirements','/requirements/'+str(i)) for i,r in enumerate(requirements) if r.get('id')}
    stories, criteria = {}, {}
    story_objects=[]
    for ei,ep in enumerate(snap('stories',{}).get('backlog',{}).get('epics',[])):
        for fi,feature in enumerate(ep.get('features',[])):
            for si,s in enumerate(feature.get('stories',[])):
                p=f'/backlog/epics/{ei}/features/{fi}/stories/{si}'
                key=entity('story',s['id'],'stories',p);stories[s['id']]=key;story_objects.append((s,p,key))
                tr=s.get('trace') or {}
                link('story-sir',key,contracts.get(tr.get('sirId')),ref('stories',p),tr.get('sirId'),not tr.get('sirId'))
                for rid in tr.get('ruleIds',[]):link('story-rule',key,rules.get(rid),ref('stories',p),rid)
                for j,ac in enumerate(s.get('acceptanceCriteria',[])):
                    ck=entity('criterion',s['id']+':'+str(j),'stories',p+'/acceptanceCriteria/'+str(j));criteria[(s['id'],j)]=(ck,ac)
                    link('story-criterion',key,ck,ref('stories',p+'/acceptanceCriteria/'+str(j)))
                if not s.get('acceptanceCriteria'):link('story-criterion',key,None,ref('stories',p),missing=True)
                for rid in s.get('requirementIds',tr.get('requirementIds',[])):
                    link('story-requirement',key,reqs.get(rid),ref('stories',p),rid)
    for i,r in enumerate(requirements):
        if r.get('id') not in reqs:continue
        key=reqs[r['id']];evidence=ref('requirements','/requirements/'+str(i))
        refs=r.get('sirIds',[]) or ([r['sirId']] if r.get('sirId') else [])
        for sid in refs:link('requirement-sir',key,contracts.get(sid),evidence,sid)
        if not refs:link('requirement-sir',key,None,evidence,missing=True)
        story_refs=r.get('storyIds',[])
        for sid in story_refs:link('requirement-story',key,stories.get(sid),evidence,sid)
        reverse=any(l['kind']=='story-requirement' and l['toId']==key for l in links)
        if not story_refs and not reverse:link('requirement-story',key,None,evidence,missing=True)
    # Legacy backlog links remain separate from the current generated story identities.
    for i,s in enumerate(snap('requirements',{}).get('legacyBacklog',[])):
        if not isinstance(s,dict) or not s.get('id'):continue
        key=entity('legacy-backlog',s['id'],'requirements','/legacyBacklog/'+str(i))
        for rid in s.get('requirementIds',[]):link('legacy-backlog-requirement',key,reqs.get(rid),ref('requirements','/legacyBacklog/'+str(i)),rid)
    tests=snap('tests',{});scenarios={};covered=set()
    assessable=bool(tests.get('scenarios')) and any('criterionIndex' in x for x in tests['scenarios'])
    for i,s in enumerate(tests.get('scenarios',[])):
        p='/scenarios/'+str(i);key=entity('scenario',s['id'],'tests',p);scenarios[s['id']]=key
        ac=criteria.get((s.get('storyId'),s.get('criterionIndex')))
        exact=ac and s.get('criterion')==ac[1]
        link('scenario-criterion',key,ac[0] if exact else None,ref('tests',p),str((s.get('storyId'),s.get('criterionIndex'))))
        if exact:covered.add(ac[0])
    for i,case in enumerate(tests.get('cases',[])):
        p='/cases/'+str(i);key=entity('test-case',case['id'],'tests',p)
        link('case-scenario',key,scenarios.get(case.get('scenarioId')),ref('tests',p),case.get('scenarioId'))
    for (sid,j),(key,ac) in criteria.items():
        if key not in covered:
            e=next(e for e in entities if e['id']==key)
            link('criterion-test',key,None,e['reference'],missing=True)
    covered_rules={l['toId'] for l in links if l['kind']=='story-rule' and l['status']=='resolved'}
    covered_reqs={l['toId'] for l in links if l['kind']=='story-requirement' and l['status']=='resolved'} | {l['fromId'] for l in links if l['kind']=='requirement-story' and l['status']=='resolved'}
    summary={'resolvedRelationships':sum(l['status']=='resolved' for l in links),
             'missingRelationships':sum(l['status']=='missing' for l in links),
             'unresolvedReferences':sum(l['status']=='unresolved' for l in links),
             'uncoveredBusinessRules':len(set(rules.values())-covered_rules),
             'requirementsWithoutStoryCoverage':len(set(reqs.values())-covered_reqs),
             'storiesWithoutAcceptanceCriteria':sum(not s.get('acceptanceCriteria') for s,p,k in story_objects),
             'acceptanceCriteriaWithoutTestCoverage':len(criteria)-len(covered) if assessable else None,
             'criterionCoverageAssessment':'assessed-explicit-links' if assessable else 'unavailable'}
    for status in ['missing','unresolved']:
        affected=[l for l in links if l['status']==status]
        if affected:c.finding('TRACE_'+status.upper(),f'{len(affected)} trace relationships are {status}; inspect the typed relationship index.',severity='blocker' if status=='unresolved' else 'warning',evidence=sorted({l['evidence']['artifactId'] for l in affected}))
    # Gate records preserve originals in approvals.json, without retroactive hash approval.
    approvals=[]
    for phase,g in snap('approvals',{}).items():
        if not isinstance(g,dict):continue
        ids=g.get('artifactIds',[]) or ([g['artifactId']] if g.get('artifactId') else [])
        revision=g.get('artifactSha256') or g.get('artifactRevision') or g.get('revision')
        hashes={i:artifacts[i].sha256 for i in ids if i in artifacts}
        binding='exact-artifact-hash' if ids and len(hashes)==len(ids) and revision and all(h==revision for h in hashes.values()) else 'mismatch' if ids and revision else 'unavailable'
        approvals.append({'gateId':phase,'gateType':g.get('type'),'status':g.get('status'),'decision':g.get('decision'),
             'comment':g.get('comment'),'actor':g.get('actor'),'timestamp':g.get('at'), 'artifactIds':ids,
             'recordedRevision':revision,'snapshotHashes':hashes,'binding':binding,'evidence':ref('approvals','/'+pointer(phase)),
             'unavailableFields':[field for field in ['type','status','decision','comment','actor','at'] if g.get(field) is None]+([] if ids else ['artifactIds'])+([] if revision else ['artifactRevision'])})
        if binding=='mismatch':c.finding('APPROVAL_REVISION_MISMATCH','Recorded approval does not match referenced packaged content.','approvals','blocker',[phase])
    # Library declarations are confirmed as declarations, never as successful restore/build.
    for a in list(c.artifacts):
        if a.kind!='source':continue
        data=c.files[a.path]
        try:
            if a.path.endswith('package.json'):
                obj=json.loads(data)
                for group in ['dependencies','devDependencies','peerDependencies']:
                    for name,version in obj.get(group,{}).items():dep('library','confirmed',name,ref(a.id,'/'+group+'/'+pointer(name)),version=version,explanation='Explicit package manifest declaration; installation not verified.')
            elif a.path.endswith(('.csproj','.vbproj','packages.config')):
                tree=ET.fromstring(data)
                for el in tree.iter():
                    if el.tag.split('}')[-1] in {'PackageReference','package'}:
                        name=el.get('Include') or el.get('id')
                        if name:dep('library','confirmed',name,ref(a.id),version=el.get('Version') or el.get('version'),explanation='Explicit XML declaration; conditions and restore not evaluated.')
        except (ValueError,ET.ParseError):
            c.finding('DEPENDENCY_MANIFEST_UNREADABLE','Dependency manifest cannot be parsed.',a.id,evidence=[a.path])
        if a.role in {'build-support','integration-contract','test-baseline'}:
            dep('build' if a.role=='build-support' else 'api' if a.role=='integration-contract' else 'deployment','potential',a.path,ref(a.id),a.id,explanation='Supporting-file evidence; applicability requires review.')
        if a.role in {'dependency','shared'}:
            dep('module','potential',a.path,ref(a.id),a.id,explanation='Collected dependency closure; scope ownership is not execution verification.')
    for row in c.inventory_rows:
        if row['status']=='unavailable' and row['path']!='full-ast' and 'scope' in artifacts:
            dep('build','implementation-unavailable',row['path'],ref('scope'),explanation=row['reason'])
    # Preserved source references are locators, never synthesized business relationships.
    target=snap('target',{})
    target_fields={k:target.get(k) or None for k in ['language','framework','frameworkVersion','runtime','runtimeVersion','architecture']}
    tc={'snapshot':ref('target') if 'target' in artifacts else None,'configurationDigest':digest(canonical(target)),**target_fields,
        'frontendFramework':target.get('frontendRequirement') or None,'database':target.get('data') or None,
        'apiApproach':target.get('apiApproach') or None,'missingFields':[], 'templateIds':[t['id'] for t in c.template_rows]}
    tc['missingFields']=[k for k,v in {**target_fields,'database':tc['database'],'apiApproach':tc['apiApproach']}.items() if v is None]
    bundles=[]
    for t in c.template_rows:
        bundles.append({'id':t['id'],'revision':t['revision'],'aggregateDigest':t['contentDigest'],'sourceIdentity':t['sourceIdentity'],
          'files':[{'name':f['name'],'reference':ref('template:'+t['id']+'/'+f['path']),'sourcePath':f['sourcePath'],'sha256':f['sha256']} for f in t['files']],
          'missingFiles':t['missingFiles'],'compatibilityStatus':t['compatibility']['status']})
    # Missing baseline remains blocking evidence, even when checks-mode tests passed.
    c.finding('LIVE_BASELINE_MISSING','No independently verified, source-bound live behavioral baseline is available.',severity='blocker',evidence=['tests'])
    return EngineContract.model_validate({'inventory':c.inventory_rows,'traceability':{'entities':entities,'relationships':links,'summary':summary},
        'approvals':{'records':approvals},'dependencies':{'items':deps,'counts':dict(Counter(d['status'] for d in deps))},
        'target':tc,'templates':bundles,'readiness':readiness_contract(c.findings)})
