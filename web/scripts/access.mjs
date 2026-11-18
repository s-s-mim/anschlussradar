// Sets who can open the web app, after `npm run build`.
//   WEB_ACCESS=demo   (default) only people invited in the Azure portal, role "demo"
//   WEB_ACCESS=public everyone
// Switching later is only a change of the GitHub variable WEB_ACCESS and a new deploy.
import { readFileSync, writeFileSync } from "node:fs";

// Search engines: the demo is never indexed. A public site gets a sitemap and absolute
// preview-image links once SITE_URL (e.g. https://anschlussradar.de) is set.
const siteUrl = (process.env.SITE_URL || "").trim().replace(/\/+$/, "");
const dist = (name) => new URL(`../dist/${name}`, import.meta.url);
const PAGES = ["/", "/map", "/lines", "/stations", "/help", "/about", "/contact", "/impressum", "/datenschutz"];

const file = new URL("../dist/staticwebapp.config.json", import.meta.url);
const config = JSON.parse(readFileSync(file, "utf8"));
const mode = (process.env.WEB_ACCESS || "demo").trim().toLowerCase();

if (mode === "public") {
  let robots = "User-agent: *\nAllow: /\n";
  if (siteUrl) {
    robots += `Sitemap: ${siteUrl}/sitemap.xml\n`;
    const urls = PAGES.map((p) => `  <url><loc>${siteUrl}${p}</loc></url>`).join("\n");
    writeFileSync(
      dist("sitemap.xml"),
      `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`,
    );
    const html = readFileSync(dist("index.html"), "utf8")
      .replace('content="/og.png"', `content="${siteUrl}/og.png"`)
      .replace("</head>", `  <link rel="canonical" href="${siteUrl}/" />\n    <meta property="og:url" content="${siteUrl}/" />\n  </head>`);
    writeFileSync(dist("index.html"), html);
  }
  writeFileSync(dist("robots.txt"), robots);
  console.log(`Web access: public${siteUrl ? `, site ${siteUrl}` : ", no SITE_URL yet (no sitemap)"}`);
} else {
  const open = ["/login.html", "/icons/*", "/manifest.webmanifest", "/robots.txt", "/og.png"].map((route) => ({
    route,
    allowedRoles: ["anonymous"],
  }));
  // Signing in alone is not enough: the role "demo" is only given by invitation.
  config.routes = [
    ...open,
    ...(config.routes || []).map((r) => ({ ...r, allowedRoles: ["demo"] })),
    { route: "/*", allowedRoles: ["demo"] },
  ];
  config.responseOverrides = {
    401: { statusCode: 302, redirect: "/login.html" },
    403: { statusCode: 302, redirect: "/login.html#denied" },
  };
  config.globalHeaders["X-Robots-Tag"] = "noindex";
  writeFileSync(dist("robots.txt"), "User-agent: *\nDisallow: /\n");
  console.log("Web access: demo (invited people only)");
}
writeFileSync(file, JSON.stringify(config, null, 2));
