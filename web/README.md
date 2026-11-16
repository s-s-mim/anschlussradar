# Web app

React and TypeScript, built with Vite, hosted on Azure Static Web Apps. Mobile first,
German and English, installable as an app (PWA), works offline for the start page.

No cookies, no tracking, no fonts or maps from other servers. The app only stores the
language, saved routes and the last five searches in the browser (localStorage).

## Pages

| Address | Page |
|---|---|
| `/` | Search form, saved routes, recent searches |
| `/connections?from=…&to=…&date=…&time=…` | Results with reliability and live check |
| `/help`, `/about`, `/contact` | Help, about, contact form |
| `/impressum`, `/datenschutz` | Legal notice and privacy policy |

## Before going public

Fill in your address and a contact e-mail in `src/site.ts`. Until then the Impressum
and the privacy policy show the placeholders highlighted in yellow.

## Run it on your computer (optional)

Needs Node.js 20.19 or newer.

```
cd web
npm install
npm run dev
```

The dev server sends `/api` calls to `http://localhost:7071`, where the API runs with
`func start` in the `api` folder.

## Files

- `src/i18n/de.ts`, `src/i18n/en.ts`: all short texts. German is the main language.
- `src/pages/`: one file per page. Help, About and the legal pages hold both languages.
- `src/lib/`: API calls, German time handling, browser storage, the tiny router.
- `public/sw.js`: service worker. It never caches API answers.
- `public/staticwebapp.config.json`: routing and security headers for Azure.
