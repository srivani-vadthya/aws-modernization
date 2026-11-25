"""Offline validation shared by publication, retrieval verification and ZIP export."""
import json
from .repository import ContextError, canonical, digest


def validate_snapshot(m, files):
    artifacts=m['artifacts']
    ids={a['id']:a for a in artifacts};paths={a['path']:a for a in artifacts}
    if len(ids)!=len(artifacts) or len(paths)!=len(artifacts) or 'manifest.json' in paths:
        raise ContextError('Duplicate or reserved artifact identity/path')
    for a in artifacts:
        data=files.get(a['path'])
        if data is None or len(data)!=a['bytes'] or digest(data)!=a['sha256']:
            raise ContextError('Package artifact integrity check failed: '+a['path'])
    contract=m.get('contract')
    if contract:
        if contract['artifactCount']!=len(artifacts) or contract['traceability']['summary']['totalArtifacts']!=len(artifacts):
            raise ContextError('Artifact counts do not match')
        def refs(value):
            if isinstance(value,dict):
                if 'artifactId' in value and 'pointer' in value:
                    yield value
                else:
                    for child in value.values():yield from refs(child)
            elif isinstance(value,list):
                for child in value:yield from refs(child)
        for r in refs(contract):
            a=ids.get(r['artifactId'])
            if not a:raise ContextError('Unresolvable internal artifact reference')
            if r['pointer']:
                try:
                    if not r['pointer'].startswith('/'):raise ValueError('pointer')
                    value=json.loads(files[a['path']])
                    for part in r['pointer'][1:].split('/'):
                        part=part.replace('~1','/').replace('~0','~')
                        value=value[int(part)] if isinstance(value,list) else value[part]
                except (ValueError,KeyError,IndexError,TypeError) as exc:
                    raise ContextError('Unresolvable JSON pointer: '+r['artifactId']+r['pointer']) from exc
        trace=contract['traceability'];nodes={e['id'] for e in trace['entities']}
        if len(nodes)!=len(trace['entities']):raise ContextError('Duplicate trace entity')
        for link in trace['relationships']:
            if link['fromId'] not in nodes or (link['toId'] is not None and link['toId'] not in nodes):
                raise ContextError('Trace endpoint is absent')
            if (link['status']=='resolved') != (link['toId'] is not None):raise ContextError('Invalid trace resolution status')
        for status,key in [('resolved','resolvedRelationships'),('missing','missingRelationships'),('unresolved','unresolvedReferences')]:
            if trace['summary'][key]!=sum(l['status']==status for l in trace['relationships']):raise ContextError('Trace summary mismatch')
        for entry in contract['inventory']:
            if entry['artifactId'] is not None:
                a=ids.get(entry['artifactId'])
                if not a or a['sha256']!=entry['sha256']:raise ContextError('Source inventory hash mismatch')
        for dep in contract['dependencies']['items']:
            if dep['implementationArtifactId'] is not None and dep['implementationArtifactId'] not in ids:raise ContextError('Dependency implementation reference missing')
        for gate in contract['approvals']['records']:
            for aid,sha in gate['snapshotHashes'].items():
                if aid not in ids or ids[aid]['sha256']!=sha:raise ContextError('Approval snapshot hash mismatch')
        from .assembly import readiness_contract
        from .models import Finding
        actual=readiness_contract([Finding.model_validate(f) for f in m['readiness']['findings']])
        for key in ['overallStatus','counts','categories']:
            if actual[key]!=contract['readiness'][key]:raise ContextError('Readiness summary mismatch')
    for template in m['templates']:
        if 'files' not in template:continue  # historical v1 template metadata
        hashes={}
        for f in template['files']:
            a=paths.get(f['packagePath'])
            if not a or a['sha256']!=f['sha256'] or a['bytes']!=f['bytes']:raise ContextError('Template file mismatch')
            hashes[f['path']]=f['sha256']
        expected=digest(canonical(hashes))
        if len(hashes)!=template['fileCount'] or expected!=template['contentDigest'] or template['revision']!='sha256:'+expected:
            raise ContextError('Template aggregate mismatch')
        if contract:
            row=next((t for t in contract['templates'] if t['id']==template['id']),None)
            if not row or row['aggregateDigest']!=expected or row['revision']!=template['revision']:raise ContextError('Template contract mismatch')
    return {'valid':True,'schemaVersion':m['schemaVersion'],'artifactCount':len(artifacts),'packageDigest':m['packageDigest'],
            'internalReferences':'validated' if contract else 'legacy-envelope-only','templateHashes':'validated'}
