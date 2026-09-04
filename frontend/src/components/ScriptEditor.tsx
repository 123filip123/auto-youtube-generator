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
import { approveScript } from "@/lib/api";
import type { ScriptPayload, Section } from "@/lib/types";

interface Props {
  runId: string;
  script: ScriptPayload;
  onApproved: () => void;
}

/**
 * Edit the script and its drawings before any media is paid for.
 *
 * Editing narration deliberately does NOT recount drawings. The prompts are
 * already paired one-to-one with shots, and assembly divides each section's
 * measured audio by however many drawings it ends up with — so a shorter
 * narration simply means each drawing holds for less time. Add or remove a
 * drawing here to change the rhythm.
 */
export default function ScriptEditor({ runId, script, onApproved }: Props) {
  const [draft, setDraft] = useState<ScriptPayload>(() => ({
    ...script,
    sections: script.sections.map((section) => ({
      ...section,
      prompts: [...section.prompts],
    })),
  }));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const updateSection = (index: number, patch: Partial<Section>) =>
    setDraft((previous) => ({
      ...previous,
      sections: previous.sections.map((section, position) =>
        position === index ? { ...section, ...patch } : section,
      ),
    }));

  const updatePrompt = (index: number, promptIndex: number, value: string) =>
    updateSection(index, {
      prompts: draft.sections[index].prompts.map((prompt, position) =>
        position === promptIndex ? value : prompt,
      ),
    });

  const addPrompt = (index: number) =>
    updateSection(index, { prompts: [...draft.sections[index].prompts, ""] });

  const removePrompt = (index: number, promptIndex: number) =>
    updateSection(index, {
      prompts: draft.sections[index].prompts.filter(
        (_, position) => position !== promptIndex,
      ),
    });

  const removeSection = (index: number) =>
    setDraft((previous) => ({
      ...previous,
      sections: previous.sections.filter((_, position) => position !== index),
    }));

  const onApprove = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await approveScript(runId, draft);
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

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Style sheet</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          <Label htmlFor="style">Style sheet</Label>
          <Textarea
            id="style"
            value={draft.style}
            onChange={(event) =>
              setDraft((previous) => ({ ...previous, style: event.target.value }))
            }
          />
          <p className="text-xs text-muted-foreground">
            The recurring figures and colours for the whole video. Drawings do
            not carry over between sections, so this text is the only thing
            keeping them consistent across a cut.
          </p>
        </CardContent>
      </Card>

      {draft.sections.map((section, index) => (
        <Card key={index}>
          <CardHeader>
            <CardTitle className="text-base">Section {index + 1}</CardTitle>
            <CardAction>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Remove section ${index + 1}`}
                onClick={() => removeSection(index)}
              >
                Remove section
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor={`label-${index}`}>Section {index + 1} label</Label>
              <Input
                id={`label-${index}`}
                value={section.label}
                onChange={(event) =>
                  updateSection(index, { label: event.target.value })
                }
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor={`narration-${index}`}>
                Section {index + 1} narration
              </Label>
              <Textarea
                id={`narration-${index}`}
                rows={3}
                value={section.narration}
                onChange={(event) =>
                  updateSection(index, { narration: event.target.value })
                }
              />
              <p className="text-xs text-muted-foreground">
                {section.prompts.length} drawing(s) over this narration. Editing
                the words does not change that count — add or remove a drawing
                below to change the pace.
              </p>
            </div>

            <div className="space-y-3">
              {section.prompts.map((prompt, promptIndex) => (
                <div key={promptIndex} className="space-y-1 rounded border p-3">
                  <div className="flex items-center justify-between">
                    <Label htmlFor={`prompt-${index}-${promptIndex}`}>
                      Section {index + 1} drawing {promptIndex + 1}
                    </Label>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove section ${index + 1} drawing ${promptIndex + 1}`}
                      onClick={() => removePrompt(index, promptIndex)}
                    >
                      Remove
                    </Button>
                  </div>
                  <Input
                    id={`prompt-${index}-${promptIndex}`}
                    value={prompt}
                    onChange={(event) =>
                      updatePrompt(index, promptIndex, event.target.value)
                    }
                  />
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                aria-label={`Add drawing to section ${index + 1}`}
                onClick={() => addPrompt(index)}
              >
                Add drawing
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
        disabled={submitting || draft.sections.length === 0}
      >
        {submitting ? "Approving..." : "Approve and generate media"}
      </Button>
    </div>
  );
}
