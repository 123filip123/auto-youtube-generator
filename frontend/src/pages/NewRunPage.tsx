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

/** One line saying what the production option switches to, or null. */
function describeProduction(settings: Record<string, string>): string | null {
  const parts = [
    settings.IMAGE_MODEL,
    settings.IMAGE_QUALITY && `${settings.IMAGE_QUALITY} quality`,
  ].filter(Boolean);
  if (parts.length === 0) return null;
  return `Images: ${parts.join(", ")}. Slower and more expensive.`;
}

export default function NewRunPage() {
  const navigate = useNavigate();

  const [topic, setTopic] = useState("");
  const [numItems, setNumItems] = useState(5);
  const [reviewItems, setReviewItems] = useState(false);
  const [productionModels, setProductionModels] = useState(false);
  const [production, setProduction] = useState<Record<string, string>>({});
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
        setProduction(payload.production_image_settings ?? {});
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
        num_items: numItems,
        review_items: reviewItems,
        overrides: filled,
        production_models: productionModels,
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
              placeholder="Top 5 Extinct Animals"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="num-items">Number of items</Label>
            <Input
              id="num-items"
              type="number"
              min={1}
              max={50}
              value={numItems}
              onChange={(event) => setNumItems(Number(event.target.value))}
              className="w-32"
            />
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="review"
              checked={reviewItems}
              onCheckedChange={(checked) => setReviewItems(checked === true)}
            />
            <Label htmlFor="review" className="font-normal">
              Let me review the items before generating media
            </Label>
          </div>

          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Checkbox
                id="production"
                checked={productionModels}
                onCheckedChange={(checked) => setProductionModels(checked === true)}
              />
              <Label htmlFor="production" className="font-normal">
                Production models
              </Label>
            </div>
            {describeProduction(production) && (
              <p className="text-xs text-muted-foreground">
                {describeProduction(production)}
              </p>
            )}
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
