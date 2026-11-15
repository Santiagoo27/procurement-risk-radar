import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <Link className="text-accent underline" to="/">Back to the map</Link>
    </div>
  );
}
