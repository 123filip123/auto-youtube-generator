import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createRun, getConfig } from "@/lib/api";
import type { ConfigField } from "@/lib/types";

export default function NewRunPage() {
  const navigate = useNavigate();

  const [topic, setTopic] = useState("");
  const [targetSeconds, setTargetSeconds] = useState(85);
  const [reviewScript, setReviewScript] = useState(false);
  const [fields, setFields] = useState<ConfigField[]>([]);
  const [current, setCurrent] = useState<Record<string, string | number>>({});
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getConfig()
      .then((payload) => {
        setFields(payload.overridable);
        setCurrent(payload.values);
      })
      .catch(() => {
        // The form still works without the override section.
        setFields([]);
      });
  }, []);

  const setOverride = (name: string, value: string) =>
    setOverrides((previous) => ({ ...previous, [name]: value }));

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    if (!topic.trim()) {
      setError("Enter a topic first.");
      return;
    }

    // Blank fields mean "leave this alone", not "set it to empty".
    const filled = Object.fromEntries(
      Object.entries(overrides).filter(([, value]) => value.trim() !== ""),
    );

    setSubmitting(true);
    try {
      const run = await createRun({
        topic: topic.trim(),
        target_seconds: targetSeconds,
        review_script: reviewScript,
        overrides: filled,
      });
      navigate(`/runs/${run.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>New run</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="topic">Topic</Label>
            <Input
              id="topic"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="how dogs evolved from wolves"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="target-seconds">Target length (seconds)</Label>
            <Input
              id="target-seconds"
              type="number"
              min={15}
              max={180}
              value={targetSeconds}
              onChange={(event) => setTargetSeconds(Number(event.target.value))}
              className="w-32"
            />
            <p className="text-xs text-muted-foreground">
              Section and image counts follow from this — the script is written
              to fit, and a drawing lands about every 2.5 seconds.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="review"
              checked={reviewScript}
              onCheckedChange={(checked) => setReviewScript(checked === true)}
            />
            <Label htmlFor="review" className="font-normal">
              Let me review the script before generating media
            </Label>
          </div>
        </CardContent>
      </Card>

      {fields.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Overrides for this run (optional)
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            {fields.map((field) => (
              <div key={field.name} className="space-y-1">
                <Label htmlFor={field.name}>{field.name}</Label>
                <Input
                  id={field.name}
                  value={overrides[field.name] ?? ""}
                  onChange={(event) => setOverride(field.name, event.target.value)}
                  placeholder={String(current[field.name] ?? "")}
                  list={field.choices ? `${field.name}-choices` : undefined}
                />
                {field.choices && (
                  <datalist id={`${field.name}-choices`}>
                    {field.choices.map((choice) => (
                      <option key={choice} value={choice} />
                    ))}
                  </datalist>
                )}
                <p className="text-xs text-muted-foreground">{field.description}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button type="submit" disabled={submitting}>
        {submitting ? "Starting..." : "Start run"}
      </Button>
    </form>
  );
}
