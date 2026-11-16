import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { useI18n } from "./i18n";
import { getModelStatus } from "./lib/api";
import { useLocation } from "./lib/router";
import type { Stage } from "./lib/types";
import { About } from "./pages/About";
import { Contact } from "./pages/Contact";
import { Help } from "./pages/Help";
import { Home } from "./pages/Home";
import { Line } from "./pages/Line";
import { Lines } from "./pages/Lines";
import { NetworkMap } from "./pages/NetworkMap";
import { Impressum, Privacy } from "./pages/Legal";
import { NotFound } from "./pages/NotFound";
import { Results } from "./pages/Results";
import { Station } from "./pages/Station";
import { Stations } from "./pages/Stations";

const TITLES: Record<string, string> = {
  "/stations": "nav.stations",
  "/map": "nav.map",
  "/lines": "nav.lines",
  "/help": "nav.help",
  "/about": "nav.about",
  "/contact": "nav.contact",
  "/impressum": "nav.imprint",
  "/datenschutz": "nav.privacy",
};

export function App() {
  const { path, search } = useLocation();
  const { t } = useI18n();
  const [stage, setStage] = useState<Stage | null>(null);
  const main = useRef<HTMLElement>(null);
  const first = useRef(true);

  useEffect(() => {
    getModelStatus()
      .then((s) => setStage(s.stage))
      .catch(() => setStage(null)); // offline or API not reachable: no banner
  }, []);

  useEffect(() => {
    const key = TITLES[path];
    document.title = key ? `${t(key)} – AnschlussRadar` : "AnschlussRadar";
    // Move focus to the new page for screen readers, but not on the first load.
    if (first.current) first.current = false;
    else main.current?.focus();
  }, [path, t]);

  let page: ReactNode;
  switch (path) {
    case "/":
      page = <Home key={search.toString()} search={search} stage={stage} />;
      break;
    case "/connections":
      page = <Results search={search} onStage={setStage} />;
      break;
    case "/stations":
      page = <Stations />;
      break;
    case "/map":
      page = <NetworkMap />;
      break;
    case "/lines":
      page = <Lines />;
      break;
    case "/line":
      page = <Line search={search} />;
      break;
    case "/station":
      page = <Station search={search} />;
      break;
    case "/help":
      page = <Help />;
      break;
    case "/about":
      page = <About />;
      break;
    case "/contact":
      page = <Contact />;
      break;
    case "/impressum":
      page = <Impressum />;
      break;
    case "/datenschutz":
      page = <Privacy />;
      break;
    default:
      page = <NotFound />;
  }

  return (
    <>
      <Header path={path} />
      <main id="main" ref={main} tabIndex={-1}>
        {page}
      </main>
      <Footer />
    </>
  );
}
