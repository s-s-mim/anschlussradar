// Sets who can open the web app, after `npm run build`.
//   WEB_ACCESS=demo   (default) only people invited in the Azure portal, role "demo"
//   WEB_ACCESS=public everyone
// Switching later is only a change of the GitHub variable WEB_ACCESS and a new deploy.
import { readFileSync, writeFileSync } from "node:fs";

const file = new URL("../dist/staticwebapp.config.json", import.meta.url);
const config = JSON.parse(readFileSync(file, "utf8"));
const mode = (process.env.WEB_ACCESS || "demo").trim().toLowerCase();

if (mode === "public") {
  console.log("Web access: public");
} else {
  const open = ["/login.html", "/icons/*", "/manifest.webmanifest", "/robots.txt"].map((route) => ({
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
  console.log("Web access: demo (invited people only)");
}
writeFileSync(file, JSON.stringify(config, null, 2));
