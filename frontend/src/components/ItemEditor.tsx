import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { approveItems } from "@/lib/api";
import type { ItemPayload } from "@/lib/types";

interface Props {
  runId: string;
  items: ItemPayload[];
  onApproved: () => void;
}

/**
 * Edit the generated items before any media is paid for.
 *
 * Prompt counts are free-form here: the backend validates with
 * `expected_prompts=None`, so adding or removing a prompt is allowed and the
 * media stage adapts to whatever count each item ends up with.
 */
export default function ItemEditor({ runId, items, onApproved }: Props) {
  const [draft, setDraft] = useState<ItemPayload[]>(() =>
    items.map((item) => ({ ...item, image_prompts: [...item.image_prompts] })),
  );
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const updateItem = (index: number, patch: Partial<ItemPayload>) =>
    setDraft((previous) =>
      previous.map((item, position) =>
        position === index ? { ...item, ...patch } : item,
      ),
    );

  const updatePrompt = (index: number, promptIndex: number, value: string) =>
    updateItem(index, {
      image_prompts: draft[index].image_prompts.map((prompt, position) =>
        position === promptIndex ? value : prompt,
      ),
    });

  const addPrompt = (index: number) =>
    updateItem(index, { image_prompts: [...draft[index].image_prompts, ""] });

  const removePrompt = (index: number, promptIndex: number) =>
    updateItem(index, {
      image_prompts: draft[index].image_prompts.filter(
        (_, position) => position !== promptIndex,
      ),
    });

  const removeItem = (index: number) =>
    setDraft((previous) => previous.filter((_, position) => position !== index));

  const onApprove = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await approveItems(runId, draft);
      onApproved();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Edit anything you want before images and narration are generated.
        Approving starts the paid work.
      </p>

      {draft.map((item, index) => (
        <Card key={index}>
          <CardHeader>
            <CardTitle className="text-base">Item {index + 1}</CardTitle>
            <CardAction>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Remove item ${index + 1}`}
                onClick={() => removeItem(index)}
              >
                Remove item
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor={`title-${index}`}>Item {index + 1} title</Label>
              <Input
                id={`title-${index}`}
                value={item.title}
                onChange={(event) => updateItem(index, { title: event.target.value })}
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor={`description-${index}`}>
                Item {index + 1} description
              </Label>
              <Textarea
                id={`description-${index}`}
                value={item.description}
                onChange={(event) =>
                  updateItem(index, { description: event.target.value })
                }
              />
            </div>

            <div className="space-y-2">
              {item.image_prompts.map((prompt, promptIndex) => (
                <div key={promptIndex} className="space-y-1">
                  <Label htmlFor={`prompt-${index}-${promptIndex}`}>
                    Item {index + 1} prompt {promptIndex + 1}
                  </Label>
                  <div className="flex gap-2">
                    <Input
                      id={`prompt-${index}-${promptIndex}`}
                      value={prompt}
                      onChange={(event) =>
                        updatePrompt(index, promptIndex, event.target.value)
                      }
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove item ${index + 1} prompt ${promptIndex + 1}`}
                      onClick={() => removePrompt(index, promptIndex)}
                    >
                      Remove
                    </Button>
                  </div>
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => addPrompt(index)}
              >
                Add prompt
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button
        type="button"
        onClick={onApprove}
        disabled={submitting || draft.length === 0}
      >
        {submitting ? "Approving..." : "Approve and generate media"}
      </Button>
    </div>
  );
}
