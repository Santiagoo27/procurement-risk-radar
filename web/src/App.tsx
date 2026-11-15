import { NavLink, Route, Routes } from "react-router-dom";
import { Disclaimer } from "./components/Disclaimer";
import Entity from "./routes/Entity";
import Home from "./routes/Home";
import Methodology from "./routes/Methodology";
import NotFound from "./routes/NotFound";
import Try from "./routes/Try";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded px-2 py-1 ${isActive ? "bg-blue-50 text-accent" : "text-muted hover:text-ink"}`;

export default function App() {
  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-line bg-white">
        <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
          <NavLink to="/" className="mr-auto text-base font-semibold text-ink">
            Procurement Risk Radar
          </NavLink>
          <NavLink to="/" end className={navClass}>Map</NavLink>
          <NavLink to="/try" className={navClass}>Try it</NavLink>
          <NavLink to="/methodology" className={navClass}>Methodology</NavLink>
          <a className="rounded px-2 py-1 text-muted hover:text-ink"
             href="https://github.com/Santiagoo27/procurement-risk-radar">GitHub</a>
        </nav>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/entity/:buyerId" element={<Entity />} />
          <Route path="/try" element={<Try />} />
          <Route path="/methodology" element={<Methodology />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <Disclaimer />
    </div>
  );
}
