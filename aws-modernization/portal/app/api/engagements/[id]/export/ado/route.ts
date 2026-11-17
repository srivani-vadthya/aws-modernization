import { NextResponse } from "next/server";
import { loadEngagement } from "@/lib/store";

export const runtime = "nodejs";

export async function POST(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  const e = loadEngagement(id);
  if (!e) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const org = process.env.ADO_ORG;
  const project = process.env.ADO_PROJECT;
  const pat = process.env.ADO_PAT;

  const payload = e.backlog.map((item) => ({
    type: item.adoType,
    title: `[${item.id}] ${item.title}`,
    wave: item.wave,
    requirementIds: item.requirementIds,
  }));

  if (!org || !project || !pat) {
    return NextResponse.json({
      exported: false,
      reason:
        "ADO_ORG / ADO_PROJECT / ADO_PAT not configured. Returning work-item payload for demo.",
      workItems: payload,
    });
  }

  const auth = Buffer.from(`:${pat}`).toString("base64");
  const created: { id: number; title: string }[] = [];
  for (const item of payload) {
    const res = await fetch(
      `https://dev.azure.com/${org}/${project}/_apis/wit/workitems/$${item.type}?api-version=7.1`,
      {
        method: "POST",
        headers: {
          Authorization: `Basic ${auth}`,
          "Content-Type": "application/json-patch+json",
        },
        body: JSON.stringify([
          { op: "add", path: "/fields/System.Title", value: item.title },
          {
            op: "add",
            path: "/fields/System.Tags",
            value: `Nexus;Wave-${item.wave}`,
          },
        ]),
      },
    );
    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { exported: false, error: text, workItems: payload },
        { status: 502 },
      );
    }
    const json = (await res.json()) as { id: number };
    created.push({ id: json.id, title: item.title });
  }
  return NextResponse.json({ exported: true, created });
}
