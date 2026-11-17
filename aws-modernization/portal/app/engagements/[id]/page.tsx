import { notFound } from "next/navigation";
import { loadEngagement } from "@/lib/store";
import { WorkspaceClient } from "@/components/WorkspaceClient";

export const dynamic = "force-dynamic";

export default async function EngagementPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const e = loadEngagement(id);
  if (!e) notFound();
  return <WorkspaceClient initial={e} />;
}
