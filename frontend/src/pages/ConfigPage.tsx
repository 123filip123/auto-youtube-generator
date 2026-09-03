import { useEffect, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getConfig } from "@/lib/api";
import type { ConfigPayload } from "@/lib/types";

export default function ConfigPage() {
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getConfig()
      .then(setConfig)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : String(caught)),
      );
  }, []);

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }
  if (!config) return <p>Loading config...</p>;

  const overridable = new Map(config.overridable.map((field) => [field.name, field]));
  const names = Object.keys(config.values).sort();

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Defaults live in <code>config.py</code> and can be changed permanently
        with an environment variable of the same name. Fields marked{" "}
        <em>per run</em> can also be overridden for a single run from the new-run
        form.
      </p>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Value</TableHead>
            <TableHead>Notes</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {names.map((name) => {
            const field = overridable.get(name);
            return (
              <TableRow key={name} data-testid={`row-${name}`}>
                <TableCell className="font-mono text-xs">{name}</TableCell>
                <TableCell className="font-mono text-xs">
                  {String(config.values[name])}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {field && <Badge variant="secondary">per run</Badge>}{" "}
                  {field?.description}
                  {field?.choices && ` One of: ${field.choices.join(", ")}.`}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
