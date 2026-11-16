// All times in the app are German local time (Europe/Berlin), wherever the phone is.

const TZ = "Europe/Berlin";

function parts(d: Date): Record<string, string> {
  const fmt = new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return Object.fromEntries(fmt.formatToParts(d).map((p) => [p.type, p.value]));
}

/** Today's date and the current time in Germany, for the form defaults. */
export function berlinNow(now = new Date()): { date: string; time: string } {
  const p = parts(now);
  const hour = p.hour === "24" ? "00" : p.hour;
  return { date: `${p.year}-${p.month}-${p.day}`, time: `${hour}:${p.minute}` };
}

/** "2026-11-16" + "07:42" in German time -> ISO string with the right offset. */
export function berlinIso(date: string, time: string): string {
  const [y, mo, d] = date.split("-").map(Number);
  const [h, mi] = time.split(":").map(Number);
  const asUtc = Date.UTC(y, mo - 1, d, h, mi);
  // Offset of Berlin at about that moment (one hour in winter, two in summer).
  const p = parts(new Date(asUtc));
  const shown = Date.UTC(+p.year, +p.month - 1, +p.day, p.hour === "24" ? 0 : +p.hour, +p.minute);
  const offsetMin = Math.round((shown - asUtc) / 60000);
  const sign = offsetMin >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMin);
  const off = `${sign}${String(Math.floor(abs / 60)).padStart(2, "0")}:${String(abs % 60).padStart(2, "0")}`;
  return `${date}T${time}:00${off}`;
}

/** "2026-11-16T07:42:00+01:00" -> "07:42". The API already sends German time. */
export function hhmm(iso: string | null): string {
  return iso ? iso.slice(11, 16) : "–";
}

/** Minutes after an ISO time, as a new ISO string in German time. */
export function addMinutes(iso: string, minutes: number): { date: string; time: string } {
  return berlinNow(new Date(new Date(iso).getTime() + minutes * 60000));
}

export function duration(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return h ? `${h}:${String(m).padStart(2, "0")} h` : `${m} min`;
}
