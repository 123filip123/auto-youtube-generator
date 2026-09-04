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
import type { Beat, ItemPayload } from "@/lib/types";

interface Props {
  runId: string;
  items: ItemPayload[];
  onApproved: () => void;
}

/**
 * Edit the generated storyboards before any media is paid for.
 *
 * Beat counts are free-form here: the backend validates with
 * `expected_prompts=None`, so adding or removing a beat is allowed and the
 * media stage adapts to whatever count each item ends up with.
 */
export default function ItemEditor({ runId, items, onApproved }: Props) {
  const [draft, setDraft] = useState<ItemPayload[]>(() =>
    items.map((item) => ({
      ...item,
      beats: item.beats.length
        ? item.beats.map((beat) => ({ ...beat }))
        : item.image_prompts.map((prompt) => ({ narration: "", prompt })),
    })),
  );
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const updateItem = (index: number, patch: Partial<ItemPayload>) =>
    setDraft((previous) =>
      previous.map((item, position) =>
        position === index ? { ...item, ...patch } : item,
      ),
    );

  const updateBeat = (index: number, beatIndex: number, patch: Partial<Beat>) =>
    updateItem(index, {
      beats: draft[index].beats.map((beat, position) =>
        position === beatIndex ? { ...beat, ...patch } : beat,
      ),
    });

  const addBeat = (index: number) =>
    updateItem(index, {
      beats: [...draft[index].beats, { narration: "", prompt: "" }],
    });

  const removeBeat = (index: number, beatIndex: number) =>
    updateItem(index, {
      beats: draft[index].beats.filter((_, position) => position !== beatIndex),
    });

  /** Mirrors the server: the script is the beat narrations, joined. */
  const derivedDescription = (item: ItemPayload) =>
    item.beats
      .map((beat) => beat.narration.trim())
      .filter(Boolean)
      .join(" ") || item.description;

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
              <Label htmlFor={`style-${index}`}>Item {index + 1} style</Label>
              <Textarea
                id={`style-${index}`}
                value={item.style}
                onChange={(event) => updateItem(index, { style: event.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                The recurring figure and setting, redrawn in every frame.
              </p>
            </div>

            <div className="space-y-1">
              <Label>Item {index + 1} narration</Label>
              <p className="text-sm">{derivedDescription(item)}</p>
              <p className="text-xs text-muted-foreground">
                Derived from the beats below. Edit a beat to change it.
              </p>
            </div>

            <div className="space-y-3">
              {item.beats.map((beat, beatIndex) => (
                <div key={beatIndex} className="space-y-1 rounded border p-3">
                  <div className="flex items-center justify-between">
                    <Label htmlFor={`narration-${index}-${beatIndex}`}>
                      Item {index + 1} beat {beatIndex + 1} narration
                    </Label>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove item ${index + 1} beat ${beatIndex + 1}`}
                      onClick={() => removeBeat(index, beatIndex)}
                    >
                      Remove
                    </Button>
                  </div>
                  <Input
                    id={`narration-${index}-${beatIndex}`}
                    value={beat.narration}
                    onChange={(event) =>
                      updateBeat(index, beatIndex, { narration: event.target.value })
                    }
                  />
                  <Label htmlFor={`prompt-${index}-${beatIndex}`}>
                    Item {index + 1} beat {beatIndex + 1} drawing
                  </Label>
                  <Input
                    id={`prompt-${index}-${beatIndex}`}
                    value={beat.prompt}
                    onChange={(event) =>
                      updateBeat(index, beatIndex, { prompt: event.target.value })
                    }
                  />
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => addBeat(index)}
              >
                Add beat
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
