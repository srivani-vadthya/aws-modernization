"""Builds the capability-level summary from a list of AstFile objects."""
from __future__ import annotations
from .models import AstFile


def build_summary(files: list[AstFile]) -> dict:
    caps: dict[str, dict] = {}
    total_symbols = total_debt = 0
    all_externals: set[str] = set()
    arch_flag_totals: dict[str, int] = {}

    for af in files:
        c = af.capability
        if c not in caps:
            caps[c] = {"files": 0, "loc": 0, "symbols": 0, "tech_debt": 0,
                       "external_calls": set(), "arch_flags": set()}
        caps[c]["files"] += 1
        caps[c]["loc"]   += af.loc

        for sym in af.symbols:
            caps[c]["symbols"]    += 1
            caps[c]["tech_debt"]  += len(sym.tech_debt_flags)
            caps[c]["external_calls"].update(sym.external_calls)
            caps[c]["arch_flags"].update(sym.arch_flags)
            all_externals.update(sym.external_calls)
            for flag in sym.arch_flags:
                arch_flag_totals[flag] = arch_flag_totals.get(flag, 0) + 1
            total_symbols += 1
            total_debt    += len(sym.tech_debt_flags)

    for c in caps:
        caps[c]["external_calls"] = sorted(caps[c]["external_calls"])
        caps[c]["arch_flags"]     = sorted(caps[c]["arch_flags"])

    return {
        "total_files":           len(files),
        "total_loc":             sum(af.loc for af in files),
        "total_symbols":         total_symbols,
        "total_tech_debt_flags": total_debt,
        "external_integrations": sorted(all_externals),
        "arch_flag_totals":      arch_flag_totals,
        "by_capability":         caps,
    }
