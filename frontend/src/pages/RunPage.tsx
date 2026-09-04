import { Link, useParams } from "react-router-dom";

import AssetList from "@/components/AssetList";
import LogPanel from "@/components/LogPanel";
import ScriptEditor from "@/components/ScriptEditor";
import StageProgress from "@/components/StageProgress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRun } from "@/hooks/useRun";
import { cancelRun } from "@/lib/api";
import { TERMINAL_STATUSES } from "@/lib/types";

export default function RunPage() {
  const { runId } = useParams<{ runId: string }>();
  const { run, error, loading, refresh } = useRun(runId ?? null);

  if (loading && !run) return <p>Loading run...</p>;
  if (!run) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error ?? "Run not found."}</AlertDescription>
      </Alert>
    );
  }

  const finished = TERMINAL_STATUSES.has(run.status);

  const onCancel = async () => {
    try {
      await cancelRun(run.id);
    } finally {
      refresh();
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold">{run.topic}</h1>
          <p className="text-sm text-muted-foreground">
            {run.target_seconds}s · {run.status}
          </p>
        </div>
        {!finished && (
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>

      <StageProgress run={run} />

      {run.status === "awaiting_review" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Review the script</CardTitle>
          </CardHeader>
          <CardContent>
            <ScriptEditor runId={run.id} script={run.script} onApproved={refresh} />
          </CardContent>
        </Card>
      )}

      {!finished && (
        <p className="text-xs text-muted-foreground">
          Cancelling stops the run at the next stage boundary. Work already in
          flight — an OpenAI batch or a video render — finishes first.
        </p>
      )}

      <AssetList assets={run.assets} total={run.asset_total} />

      {error && (
        <Alert>
          <AlertDescription>
            Lost contact with the server ({error}). Still retrying.
          </AlertDescription>
        </Alert>
      )}

      {run.error && (
        <Alert variant="destructive">
          <AlertDescription className="whitespace-pre-wrap">
            {run.error}
          </AlertDescription>
        </Alert>
      )}

      {run.video_url && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Finished video</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <video
              data-testid="run-video"
              src={run.video_url}
              controls
              className="max-h-[70vh] rounded border"
            />
            {run.archive_slug && (
              <Link
                to={`/archives/${run.archive_slug}`}
                className="block text-sm underline"
              >
                Open archive
              </Link>
            )}
          </CardContent>
        </Card>
      )}

      <LogPanel logs={run.logs} />
    </div>
  );
}
