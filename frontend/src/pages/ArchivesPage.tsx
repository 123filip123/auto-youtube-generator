import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

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
import { listArchives } from "@/lib/api";
import type { ArchiveSummary } from "@/lib/types";

export default function ArchivesPage() {
  const [archives, setArchives] = useState<ArchiveSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listArchives()
      .then(setArchives)
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
  if (archives === null) return <p>Loading archives...</p>;
  if (archives.length === 0) return <p>No archives yet. Start a run first.</p>;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Topic</TableHead>
          <TableHead>Sections</TableHead>
          <TableHead>Images</TableHead>
          <TableHead>Audio</TableHead>
          <TableHead>Video</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {archives.map((archive) => (
          <TableRow key={archive.slug}>
            <TableCell>
              <Link to={`/archives/${archive.slug}`} className="underline">
                {archive.slug}
              </Link>
              {archive.legacy && (
                <Badge variant="secondary" className="ml-2">
                  Legacy
                </Badge>
              )}
            </TableCell>
            <TableCell>{archive.section_count}</TableCell>
            <TableCell>{archive.image_count}</TableCell>
            <TableCell>{archive.audio_count}</TableCell>
            <TableCell>{archive.has_video ? "yes" : "no"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
