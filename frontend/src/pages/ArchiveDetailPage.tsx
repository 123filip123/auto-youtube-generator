import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { getArchive } from "@/lib/api";
import type { ArchiveDetail } from "@/lib/types";

export default function ArchiveDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const [archive, setArchive] = useState<ArchiveDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    getArchive(slug)
      .then(setArchive)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : String(caught)),
      );
  }, [slug]);

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }
  if (!archive) return <p>Loading archive...</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{archive.slug}</h1>

      {archive.video_url ? (
        <video
          data-testid="archive-video"
          src={archive.video_url}
          controls
          className="max-h-[70vh] rounded border"
        />
      ) : (
        <p className="text-sm text-muted-foreground">
          No video was archived for this run.
        </p>
      )}

      <Separator />

      {archive.items.map((item, index) => (
        <Card key={`${item.title}-${index}`}>
          <CardHeader>
            <CardTitle className="text-base">{item.title}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm">{item.description}</p>

            {item.audio_url && (
              <audio
                data-testid={`audio-${index + 1}`}
                src={item.audio_url}
                controls
                className="w-full"
              />
            )}

            <div className="flex flex-wrap gap-2">
              {item.image_urls.map((url, imageIndex) => (
                <img
                  key={url}
                  src={url}
                  alt={`${item.title} image ${imageIndex + 1}`}
                  className="h-32 w-32 rounded border object-cover"
                />
              ))}
              {item.titled_image_urls.map((url, imageIndex) => (
                <img
                  key={url}
                  src={url}
                  alt={`${item.title} titled image ${imageIndex + 1}`}
                  className="h-32 w-auto rounded border object-contain"
                />
              ))}
            </div>

            {item.beats.length > 0 ? (
              <ol className="space-y-1 text-xs text-muted-foreground">
                {item.beats.map((beat, beatIndex) => (
                  <li key={beatIndex}>
                    <span className="text-foreground">{beat.narration}</span>{" "}
                    {beat.prompt}
                  </li>
                ))}
              </ol>
            ) : (
              <ul className="list-disc pl-5 text-xs text-muted-foreground">
                {item.image_prompts.map((prompt, promptIndex) => (
                  <li key={promptIndex}>{prompt}</li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
