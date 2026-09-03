import { Badge } from "@/components/ui/badge";
import { STAGE_SEQUENCE, TERMINAL_STATUSES, type RunDetail } from "@/lib/types";

type StageState = "done" | "running" | "pending";

/**
 * Which stages are behind, on, and ahead of the run's current status.
 *
 * A completed run has every stage behind it; a failed or cancelled run leaves
 * the stages it never reached as pending, which is the honest reading.
 */
function stateFor(run: RunDetail, index: number, currentIndex: number): StageState {
  if (run.status === "completed") return "done";
  if (currentIndex < 0) return "pending";
  if (index < currentIndex) return "done";
  if (index === currentIndex) {
    return TERMINAL_STATUSES.has(run.status) ? "done" : "running";
  }
  return "pending";
}

const VARIANT: Record<StageState, "default" | "secondary" | "outline"> = {
  done: "default",
  running: "secondary",
  pending: "outline",
};

export default function StageProgress({ run }: { run: RunDetail }) {
  const stages = STAGE_SEQUENCE.filter(
    (stage) => stage.status !== "awaiting_review" || run.review_items,
  );
  const currentIndex = stages.findIndex((stage) => stage.status === run.status);

  return (
    <ol className="flex flex-wrap gap-2">
      {stages.map((stage, index) => {
        const state = stateFor(run, index, currentIndex);
        return (
          <li key={stage.status} data-testid={`stage-${stage.status}`}>
            <Badge variant={VARIANT[state]}>
              {stage.label} <span className="ml-1 opacity-70">{state}</span>
            </Badge>
          </li>
        );
      })}
    </ol>
  );
}
