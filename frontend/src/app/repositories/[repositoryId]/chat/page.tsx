import { Suspense } from "react";
import RepositoryChatClient from "./workspace-client";

type PageProps = {
  params: Promise<{ repositoryId: string }>;
};

async function WorkspaceContent({ params }: PageProps) {
  const { repositoryId } = await params;
  return <RepositoryChatClient repositoryId={repositoryId} />;
}

export default function RepositoryChatPage({ params }: PageProps) {
  return (
    <Suspense
      fallback={
        <main className="workspace-loading">
          <span>Opening repository workspace...</span>
        </main>
      }
    >
      <WorkspaceContent params={params} />
    </Suspense>
  );
}
