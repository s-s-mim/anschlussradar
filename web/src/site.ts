// Details for the legal notice (Impressum), the contact page and the privacy policy.
export const SITE = {
  operatorName: "Sheikh Sharfuddin Mim",
  street: "Sodener Str. 5",
  city: "60326 Frankfurt am Main",
  country: "Deutschland",
  // Split so the address does not sit in the page as one plain string for spam bots;
  // the pages join it again.
  emailUser: "sharfuddin730",
  emailDomain: "gmail.com",
  linkedin: "https://www.linkedin.com/in/sheikh-sharfuddin-mim",
  sourceCode: "https://github.com/s-s-mim/anschlussradar",
  // The GitHub repository is private until the public launch. Set to true once it is
  // public, so the app shows the link (a private repository answers "404" to visitors).
  sourcePublic: false,
  privacyUpdated: "November 2026",
};

export const siteEmail = () => `${SITE.emailUser}@${SITE.emailDomain}`;

export const isPlaceholder = (value: string) => value.startsWith("[") || value.includes("[");
