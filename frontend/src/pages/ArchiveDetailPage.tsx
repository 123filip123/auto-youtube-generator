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
      <div>
        <h1 className="text-xl font-semibold">{archive.title}</h1>
        {archive.style && (
          <p className="text-sm text-muted-foreground">{archive.style}</p>
        )}
      </div>

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

      {archive.legacy ? (
        <Alert>
          <AlertDescription>
            This run used an older format, so its script is not available. The
            video and its media files are still here.
          </AlertDescription>
        </Alert>
      ) : (
        archive.sections.map((section, index) => (
          <Card key={index}>
            <CardHeader>
              <CardTitle className="text-base">{section.label}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm">{section.narration}</p>
              {section.prompts.length > 0 && (
                <ul className="list-disc pl-5 text-xs text-muted-foreground">
                  {section.prompts.map((prompt, promptIndex) => (
                    <li key={promptIndex}>{prompt}</li>
                  ))}
                </ul>
              )}
              {section.audio_url && (
                <audio controls src={section.audio_url} className="w-full" />
              )}
              {section.image_urls.length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">
                    Generated drawings
                  </p>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {section.image_urls.map((url) => (
                      <img key={url} src={url} alt="" className="w-full rounded" />
                    ))}
                  </div>
                </div>
              )}
              {section.composed_image_urls.length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">
                    Composed frames
                  </p>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {section.composed_image_urls.map((url) => (
                      <img key={url} src={url} alt="" className="w-full rounded" />
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}
