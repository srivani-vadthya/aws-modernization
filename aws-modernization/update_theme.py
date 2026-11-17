import re

with open("apps/web/src/components/PhasePanels.tsx", "r", encoding="utf-8") as f:
    code = f.read()

# Replace Card
card_pattern = re.compile(
    r'function Card\(\{ title, children \}: \{ title: string; children: ReactNode \}\) \{.*?</section>\s*\);\s*\}',
    re.DOTALL
)
new_card = """function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">{title}</h3>
      <div className="mt-3 text-slate-800">{children}</div>
    </section>
  );
}"""
code = card_pattern.sub(new_card, code, count=1)

# Borders
code = code.replace("border-white/10", "border-slate-200")
code = code.replace("border-white/5", "border-slate-100")
code = code.replace("border-white/20", "border-slate-300")
code = code.replace("border-white/15", "border-slate-200")
code = code.replace("divide-white/5", "divide-slate-200")
code = code.replace("divide-white/10", "divide-slate-200")

# Backgrounds
code = code.replace("bg-white/5", "bg-slate-100")
code = code.replace("bg-white/10", "bg-slate-100")
code = code.replace("bg-white/15", "bg-slate-200")
code = code.replace("bg-white/20", "bg-slate-200")
code = code.replace("hover:bg-white/5", "hover:bg-slate-100")
code = code.replace("hover:bg-white/10", "hover:bg-slate-100")
code = code.replace("hover:bg-white/20", "hover:bg-slate-200")

# Black background overlays -> light slate
code = code.replace("bg-black/40", "bg-slate-50")
code = code.replace("bg-black/30", "bg-slate-50")
code = code.replace("bg-black/50", "bg-slate-100")
code = code.replace("bg-black/20", "bg-slate-50")
code = code.replace("bg-black/60", "bg-slate-900") # for terminal code blocks

# Ink backgrounds
code = code.replace("bg-ink-900", "bg-white")
code = code.replace("bg-ink-800", "bg-slate-50")
code = code.replace("bg-ink-700", "bg-slate-100")
code = code.replace("bg-ink-950", "bg-slate-900")

# Text contrast
code = code.replace("text-slate-400", "text-slate-600")
code = code.replace("text-slate-300", "text-slate-700")
code = code.replace("text-slate-200", "text-slate-900")
code = code.replace("text-slate-100", "text-slate-900")

# Copper accents -> Modern blue/indigo
code = code.replace("text-copper-300", "text-blue-700 font-semibold")
code = code.replace("text-copper-400", "text-blue-600 font-medium")
code = code.replace("bg-copper-400/20", "bg-blue-100 text-blue-800")
code = code.replace("border-copper-400", "border-blue-500")
code = code.replace("border-copper-500", "border-blue-600")

# Readability of emerald, amber, blue badges
code = code.replace("text-emerald-300", "text-emerald-700")
code = code.replace("text-emerald-400", "text-emerald-700")
code = code.replace("bg-emerald-500/20", "bg-emerald-100 border border-emerald-200")
code = code.replace("bg-emerald-500/10", "bg-emerald-50 border border-emerald-200")
code = code.replace("text-amber-200", "text-amber-800")
code = code.replace("text-amber-300", "text-amber-800")
code = code.replace("bg-amber-500/20", "bg-amber-100 border border-amber-200")
code = code.replace("text-blue-300", "text-blue-700")
code = code.replace("bg-blue-500/20", "bg-blue-100 border border-blue-200")

with open("apps/web/src/components/PhasePanels.tsx", "w", encoding="utf-8") as f:
    f.write(code)

print("PhasePanels.tsx successfully updated for light theme!")
