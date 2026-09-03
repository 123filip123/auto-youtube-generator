import { NavLink, Route, Routes } from "react-router-dom";

import ArchiveDetailPage from "@/pages/ArchiveDetailPage";
import ArchivesPage from "@/pages/ArchivesPage";
import ConfigPage from "@/pages/ConfigPage";
import NewRunPage from "@/pages/NewRunPage";
import RunPage from "@/pages/RunPage";

const NAV = [
  { to: "/", label: "New run", end: true },
  { to: "/archives", label: "Archives", end: false },
  { to: "/config", label: "Config", end: false },
];

export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b">
        <nav className="mx-auto flex max-w-4xl items-baseline gap-6 px-6 py-4">
          <span className="font-semibold">Auto YouTube Generator</span>
          <div className="flex gap-4 text-sm">
            {NAV.map((entry) => (
              <NavLink
                key={entry.to}
                to={entry.to}
                end={entry.end}
                className={({ isActive }) =>
                  isActive ? "font-medium underline" : "text-muted-foreground"
                }
              >
                {entry.label}
              </NavLink>
            ))}
          </div>
        </nav>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <Routes>
          <Route path="/" element={<NewRunPage />} />
          <Route path="/runs/:runId" element={<RunPage />} />
          <Route path="/archives" element={<ArchivesPage />} />
          <Route path="/archives/:slug" element={<ArchiveDetailPage />} />
          <Route path="/config" element={<ConfigPage />} />
        </Routes>
      </main>
    </div>
  );
}
