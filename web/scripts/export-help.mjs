// Writes config/help.json: the help texts in German and English, for the API's
// question assistant. The web app is the one place these texts are edited; CI
// checks that this file is up to date (npm run export-help, then git diff).
import { buildSync } from "esbuild";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));

async function load(lang) {
  const out = buildSync({
    entryPoints: [`${root}src/i18n/${lang}.ts`],
    bundle: true,
    format: "esm",
    write: false,
    logLevel: "error",
  });
  const code = out.outputFiles[0].text;
  const mod = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
  return mod[lang] ?? mod.default;
}

function items(t) {
  const help = t.help.items.map((i) => ({
    q: i.q,
    a: [...(i.a ?? []), ...(i.list ?? []).map((x) => `- ${x}`)].join("\n"),
  }));
  const why = (t.home.why ?? []).map(([title, text]) => ({ q: title, a: text }));
  const not = { q: t.about.notTitle, a: t.about.not.map((x) => `- ${x}`).join("\n") };
  return [...help, ...why, not];
}

const doc = { de: items(await load("de")), en: items(await load("en")) };
writeFileSync(`${root}../config/help.json`, JSON.stringify(doc, null, 1) + "\n");
console.log(`help.json: ${doc.de.length} German and ${doc.en.length} English entries`);
