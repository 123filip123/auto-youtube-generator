import { Progress } from "@/components/ui/progress";
import type { AssetStatus } from "@/lib/types";

/** Per-asset outcomes for the stage that is running now. */
export default function AssetList({
  assets,
  total,
}: {
  assets: AssetStatus[];
  total: number;
}) {
  if (total === 0 && assets.length === 0) return null;

  const percent = total > 0 ? Math.round((assets.length / total) * 100) : 0;
  const failed = assets.filter((asset) => !asset.ok);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Progress value={percent} className="w-64" />
        <span className="text-sm text-muted-foreground">
          {assets.length} of {total}
        </span>
      </div>

      {failed.length > 0 && (
        <ul className="space-y-1 text-sm text-destructive">
          {failed.map((asset) => (
            <li key={asset.label}>
              {asset.label}: {asset.error}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
