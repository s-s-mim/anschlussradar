// Details for the legal notice (Impressum) and the privacy policy.
// FILL THESE IN before the app goes public. Until then the pages show the
// placeholders in brackets, so nothing wrong is published by accident.
export const SITE = {
  operatorName: "Sheikh Sharfuddin Mim",
  street: "[Straße und Hausnummer]",
  city: "[PLZ] Kriftel",
  country: "Deutschland",
  // A separate address only for this app, e.g. kontakt@anschlussradar.de, not your private one.
  email: "[kontakt@ihre-domain.de]",
  sourceCode: "https://github.com/s-s-mim/anschlussradar",
  privacyUpdated: "November 2026",
};

export const isPlaceholder = (value: string) => value.startsWith("[") || value.includes("[");
