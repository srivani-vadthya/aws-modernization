"""Shared data models for the AST inventory."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AstSymbol:
    kind: str               # class | interface | enum | record | struct | method | component | service | page | module
    name: str
    file: str
    line: int
    capability: str
    namespace: Optional[str] = None
    base_types: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    external_calls: list[str] = field(default_factory=list)
    tech_debt_flags: list[str] = field(default_factory=list)
    arch_flags: list[str] = field(default_factory=list)   # legacy arch markers


@dataclass
class AstFile:
    path: str
    language: str           # csharp | vb | typescript | config | webforms | wcf | asmx
    capability: str
    loc: int = 0
    imports: list[str] = field(default_factory=list)
    symbols: list[AstSymbol] = field(default_factory=list)
