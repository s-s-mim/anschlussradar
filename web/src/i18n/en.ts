import type { Translation } from "./de";

export const en: Translation = {
  nav: {
    search: "Search",
    help: "Help",
    about: "About",
    contact: "Contact",
    imprint: "Legal notice",
    privacy: "Privacy",
    language: "Language",
    skip: "Skip to content",
  },
  home: {
    title: "Will I make my connection?",
    lead: "For train journeys anywhere in Germany, AnschlussRadar shows how often a transfer worked in the past and checks live whether it works today.",
    from: "From",
    to: "To",
    swap: "Swap start and destination",
    date: "Date",
    time: "Time",
    departure: "Depart",
    arrival: "Arrive",
    now: "Now",
    search: "Find connections",
    searching: "Searching …",
    pickStation: "Please pick a station from the list.",
    saved: "Saved routes",
    recent: "Recent searches",
    remove: "Remove",
    whyTitle: "What AnschlussRadar does differently",
    whyLink: "What does AnschlussRadar do differently?",
    growing:
      "You can already find connections all over Germany. Reliability scores cover more and more stations, and more kinds of transport are coming, partly based on your feedback.",
    why: [
      ["Real history, not just the timetable", "For every transfer you see how often it actually worked in recent weeks."],
      ["Most reliable first", "Sort by your chance of getting there, not only by arrival time."],
      ["Live check on the day", "If today's trains are late, you see straight away whether your transfer still works."],
    ],
  },
  station: {
    placeholder: "Station or stop",
    noMatch: "No station found. Check the spelling?",
    loading: "Searching …",
  },
  results: {
    title: "{from} → {to}",
    change: "Change search",
    fastest: "Fastest first",
    reliable: "Most reliable first",
    sortLabel: "Sort",
    earlier: "Earlier",
    later: "Later",
    none: "No train connection found. Try another time or a larger station nearby.",
    direct: "Direct",
    transfers_one: "{count} change",
    transfers_other: "{count} changes",
    save: "Save route",
    unsave: "Saved",
    reliability: "Reliability",
    noScoreYet: "no score yet",
    details: "Details",
    hideDetails: "Hide details",
    track: "Pl. {track}",
    trackChanged: "Platform change: now pl. {track}",
    cancelled: "cancelled",
    towards: "to {headsign}",
    reason: "Reason: {text}",
    attribution: "Journey data: Transitous",
  },
  transfer: {
    at: "Change at {station}",
    buffer: "{min} min to change",
    chance: "of these transfers work",
    notRecorded: "We don't collect data for this station yet.",
    notRail: "No score for buses, trams or underground lines yet.",
    cancelled: "A train on this transfer is cancelled.",
    learning: "A score appears once the model has enough data.",
    live: {
      ok: "Live: fine, {min} min to spare",
      tight: "Live: tight, {min} min to spare",
      at_risk: "Live: at risk",
      missed: "Live: probably won't work",
      cancelled: "Live: train cancelled",
    },
  },
  feedback: {
    question: "Did this transfer work?",
    yes: "Yes, made it",
    no: "No, missed it",
    thanks: "Thanks! This helps check the scores.",
    failed: "That didn't work. Please try again later.",
  },
  score: {
    earlyEstimate: "early estimate",
    limitedData: "limited data",
    basedOn_one: "from {count} trip",
    basedOn_other: "from {count} trips",
  },
  banner: {
    title: "AnschlussRadar is still learning.",
    live_only: "Live delays are accurate from today. Reliability scores will appear in about two weeks.",
    early: "Live delays are accurate from today. Reliability scores are early estimates and get better every week.",
  },
  errors: {
    offline: "No internet connection. Check your network and try again.",
    planner: "The journey planner isn't answering right now. Try again in a few minutes.",
    generic: "That didn't work. Please try again.",
    retry: "Try again",
  },
  contact: {
    title: "Contact",
    lead: "Questions, bugs or ideas: send me an email. I usually answer within a few days.",
    privacyNote: "I only use your email to reply to you. More in the privacy policy.",
    code: "You can also report bugs in the code on",
  },
  privacy: {
    clear: "Delete data saved on this device",
    cleared: "Deleted. Nothing from AnschlussRadar is stored on this device any more.",
  },
  footer: {
    planner: "Journey planning by Transitous",
    notDb: "Not a Deutsche Bahn service.",
  },
  notFound: {
    title: "This page doesn't exist.",
    back: "Go to search",
  },
  about: {
    notTitle: "What AnschlussRadar doesn't do",
    not: [
      "No account or sign-in needed (except during the demo phase)",
      "No cookies, no tracking, no analytics services",
      "No ads, no selling or passing on of data",
      "No tickets, no payments",
      "Not a Deutsche Bahn service",
      "No guarantee: the scores are estimates from past trips",
    ],
    onlyDeEn: "This page is available in German and English. Here is the English version.",
  },
  help: {
    title: "Help",
    items: [
      {
        q: "What does the percentage mean?",
        a: [
          "\"84% of these transfers work\" means: for similar transfers in recent weeks (same station, similar trains, similar time to change), the connection was made in 84 out of 100 cases.",
          "The number next to a journey is the chance that all of its transfers work. A direct train has nothing to miss, so it gets no number.",
        ],
      },
      {
        q: "What counts as made?",
        a: [
          "A transfer counts as made when the connecting train leaves at least the minimum transfer time after the actual arrival. That time is 3 minutes, or 5 minutes with a long-distance train, plus 2 minutes when you change between levels (for example from the underground S-Bahn platforms). We can't see whether someone ran or whether the train waited.",
        ],
      },
      {
        q: "Why do some transfers have no score?",
        a: [],
        list: [
          "The model is still learning. During the first weeks there is only the live check.",
          "The transfer is at a station we don't collect data for yet. Right now these are the large transfer stations, and the list is growing.",
          "Part of the trip is a bus, tram or underground line. There are no scores for those yet.",
        ],
      },
      {
        q: "What does the live check show?",
        a: [
          "On the day of travel we compare the current delays of both trains with the minimum transfer time. The time to spare is what's left on top of it. \"Fine\" means 5 minutes or more to spare. \"Tight\" means 2 to 4 minutes. \"At risk\" means less than 2 minutes, so it only works if nothing else goes wrong. \"Probably won't work\" means that by the current times the connection leaves before you arrive.",
        ],
      },
      {
        q: "What is \"Did this transfer work?\" for?",
        a: [
          "After a transfer you can say with one tap whether it worked. Only the transfer and your answer are stored, nothing about you. The answers help check the scores.",
        ],
      },
      {
        q: "Can I rely on it?",
        a: [
          "The scores are estimates from past trips, not a promise. Disruptions, engineering work or strikes can change everything. On the way, follow the displays and announcements on the train and at the station.",
        ],
      },
      {
        q: "Can I buy tickets here?",
        a: ["No. AnschlussRadar only shows connections and how reliable they are."],
      },
      {
        q: "How do I add the app to my home screen?",
        a: [
          "iPhone: open the page in Safari, tap \"Share\", then \"Add to Home Screen\". Android: open the page in Chrome, tap the menu (three dots), then \"Install app\" or \"Add to Home screen\".",
        ],
      },
    ],
    more: "Still have a question?",
    moreLink: "Write to me.",
  },
};
