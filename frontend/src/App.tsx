import { Navigate, Route, Routes } from "react-router-dom";

export function App() {
  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/" element={<Navigate to="/docs" replace />} />
        <Route path="/login" element={<LoginPlaceholder />} />
        <Route path="/docs" element={<DocsIndexPlaceholder />} />
        <Route
          path="/docs/:slug/elements"
          element={<DocElementsPlaceholder />}
        />
        <Route
          path="/docs/:slug/elements/:elementId"
          element={<DocElementsPlaceholder />}
        />
        <Route
          path="/docs/:slug/synthesise"
          element={<SynthesisePlaceholder />}
        />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

// Placeholders — replaced in subsequent tasks.
function LoginPlaceholder() {
  return <div className="p-8">Login (Task 9)</div>;
}
function DocsIndexPlaceholder() {
  return <div className="p-8">Docs Index (Task 11)</div>;
}
function DocElementsPlaceholder() {
  return <div className="p-8">Doc Elements (Task 23)</div>;
}
function SynthesisePlaceholder() {
  return <div className="p-8">Synthesise (Task 26)</div>;
}
function NotFound() {
  return <div className="p-8">Page not found.</div>;
}
