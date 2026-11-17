"""EF6 model from the latest migration snapshot (the `Target` EDMX inside the .resx).

This is EF's own view of the schema: entity -> table, property -> column, and the
store type (`decimal(18,2)`, `nvarchar(max)`) — the same model `DbModelBuilder`
produced when the migration was scaffolded. No defaults are guessed.
"""
from __future__ import annotations

import base64
import gzip
import re
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

_TARGET = re.compile(r'<data\s+name="Target"[^>]*>\s*<value>(.*?)</value>', re.S)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _store_type(p: ET.Element) -> str:
    t = p.get("Type", "")
    if p.get("MaxLength"):
        t += f"({p.get('MaxLength')})"
    elif p.get("Precision"):
        t += f"({p.get('Precision')},{p.get('Scale', '0')})"
    return t


def load_ef_model(root: Path, resources: list[str]) -> dict:
    """Returns {"source": {...}, "entities": {clr_fqn: {"table", "columns": {prop: {...}}}}}."""
    snapshots = sorted(r for r in resources if "/migrations/" in f"/{r.lower()}" and r.lower().endswith(".resx"))
    for rel in reversed(snapshots):  # migration ids are timestamp-prefixed: last is newest
        raw = (root / rel).read_text(encoding="utf-8-sig", errors="ignore")
        m = _TARGET.search(raw)
        if not m:
            continue
        try:
            edmx = gzip.decompress(base64.b64decode(m.group(1).strip())).decode("utf-8-sig")
            xml = ET.fromstring(edmx)
        except Exception:
            continue
        model_line = raw.count("\n", 0, m.start()) + 1
        return {"source": {"file": rel, "line": model_line,
                           "migration": PurePosixPath(rel).stem}, "entities": _parse(xml)}
    return {"source": None, "entities": {}}


def _parse(xml: ET.Element) -> dict:
    csdl_clr: dict[str, str] = {}           # CSDL entity name -> CLR fqn
    csdl_props: dict[str, dict[str, dict]] = {}
    ssdl: dict[str, dict[str, dict]] = {}   # table -> column -> {storeType, nullable}
    mapping: dict[str, tuple[str, dict[str, str]]] = {}   # CSDL entity name -> (table, prop->column)

    for section in xml.iter():
        tag = _local(section.tag)
        if tag == "ConceptualModels":
            for et in (e for e in section.iter() if _local(e.tag) == "EntityType"):
                clr = next((v for k, v in et.attrib.items() if k.endswith("ClrType")), None)
                name = et.get("Name", "")
                if clr:
                    csdl_clr[name] = clr.split(",")[0].strip()
                csdl_props[name] = {p.get("Name"): {"clrType": p.get("Type"), "nullable": p.get("Nullable", "true") != "false"}
                                    for p in et if _local(p.tag) == "Property"}
        elif tag == "StorageModels":
            for et in (e for e in section.iter() if _local(e.tag) == "EntityType"):
                ssdl[et.get("Name", "")] = {p.get("Name"): {"storeType": _store_type(p),
                                                           "nullable": p.get("Nullable", "true") != "false"}
                                            for p in et if _local(p.tag) == "Property"}
        elif tag == "Mappings":
            for etm in (e for e in section.iter() if _local(e.tag) == "EntityTypeMapping"):
                tname = etm.get("TypeName", "").split(".")[-1].replace("IsTypeOf(", "").rstrip(")")
                for frag in (e for e in etm if _local(e.tag) == "MappingFragment"):
                    cols = {sp.get("Name"): sp.get("ColumnName") for sp in frag if _local(sp.tag) == "ScalarProperty"}
                    mapping[tname] = (frag.get("StoreEntitySet", tname), cols)

    out: dict[str, dict] = {}
    for name, (table, cols) in mapping.items():
        fqn = csdl_clr.get(name)
        if not fqn:
            continue
        columns = {}
        for prop, col in cols.items():
            st = ssdl.get(table, {}).get(col, {})
            columns[prop] = {"column": col, "storeType": st.get("storeType", ""),
                             "nullable": st.get("nullable", True),
                             "clrType": csdl_props.get(name, {}).get(prop, {}).get("clrType", "")}
        out[fqn] = {"table": table, "columns": columns}
    return out
