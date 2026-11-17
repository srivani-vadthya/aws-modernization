import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import {
  createShell,
  ingestGit,
  ingestSample,
  classify,
} from "@/lib/pipeline";
import { engagementDir, listEngagements, saveEngagement, sourceDir } from "@/lib/store";
import { unzipTo } from "@/lib/unzip";

export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json(listEngagements());
}

export async function POST(req: Request) {
  const contentType = req.headers.get("content-type") || "";
  try {
    if (contentType.includes("multipart/form-data")) {
      const form = await req.formData();
      const file = form.get("file");
      const name = String(form.get("name") || "Zip engagement");
      if (!(file instanceof File)) {
        return NextResponse.json({ error: "file required" }, { status: 400 });
      }
      let e = createShell({ name, sourceType: "zip" });
      const destParent = engagementDir(e.id);
      fs.mkdirSync(destParent, { recursive: true });
      const zipPath = path.join(destParent, "upload.zip");
      const buf = Buffer.from(await file.arrayBuffer());
      fs.writeFileSync(zipPath, buf);
      unzipTo(zipPath, sourceDir(e.id));
      e = classify(e);
      return NextResponse.json(e);
    }

    const body = (await req.json()) as {
      mode: "sample" | "git";
      name?: string;
      gitUrl?: string;
      gitBranch?: string;
    };

    if (body.mode === "sample") {
      let e = createShell({
        name: body.name || "LIFE400 — ACME term life (IBM i)",
        sourceType: "sample",
      });
      e = ingestSample(e);
      return NextResponse.json(e);
    }

    if (body.mode === "git") {
      if (!body.gitUrl) {
        return NextResponse.json({ error: "gitUrl required" }, { status: 400 });
      }
      let e = createShell({
        name: body.name || body.gitUrl,
        sourceType: "git",
        gitUrl: body.gitUrl,
        gitBranch: body.gitBranch || "main",
      });
      try {
        e = ingestGit(e);
      } catch {
        const dest = sourceDir(e.id);
        if (fs.existsSync(dest)) fs.rmSync(dest, { recursive: true, force: true });
        e.gitBranch = undefined;
        e = ingestGit(e);
      }
      return NextResponse.json(e);
    }

    return NextResponse.json({ error: "Unknown mode" }, { status: 400 });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Ingest failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
