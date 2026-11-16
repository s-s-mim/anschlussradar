import { useI18n } from "../i18n";
import { Link } from "../lib/router";

function De() {
  return (
    <>
      <h1>Hilfe</h1>
      <details open>
        <summary>Was bedeutet die Prozentzahl?</summary>
        <p>
          „84 % dieser Umstiege klappen“ heißt: Bei vergleichbaren Umstiegen in den letzten Wochen, also am selben
          Bahnhof, mit ähnlichen Zügen und ähnlich viel Umsteigezeit, wurde der Anschluss in 84 von 100 Fällen
          erreicht.
        </p>
        <p>
          Die Zahl rechts neben einer Verbindung ist die Chance, dass alle ihre Umstiege klappen. Bei einer
          Direktverbindung gibt es nichts zu verpassen, deshalb steht dort keine Zahl.
        </p>
      </details>
      <details>
        <summary>Was zählt als geschafft?</summary>
        <p>
          Ein Umstieg zählt als geschafft, wenn der Anschlusszug nach der tatsächlichen Ankunft noch mindestens die
          Mindestumsteigezeit Zeit lässt. Die beträgt 3 Minuten, mit einem Fernzug 5 Minuten. Bei einem Wechsel
          zwischen Ebenen (zum Beispiel vom S-Bahn-Tiefbahnhof nach oben) kommen 2 Minuten dazu. Ob jemand
          tatsächlich gerannt ist oder ob der Zug gewartet hat, sehen wir nicht.
        </p>
      </details>
      <details>
        <summary>Warum steht bei manchen Umstiegen kein Wert?</summary>
        <ul>
          <li>Das Modell lernt noch. In den ersten Wochen gibt es nur den Live-Check.</li>
          <li>Der Umstieg ist an einem Bahnhof, für den wir noch keine Daten sammeln. Im Moment sind das die großen Hauptbahnhöfe, die Liste wächst.</li>
          <li>Ein Teil der Fahrt ist ein Bus, eine Straßenbahn oder eine U-Bahn. Dafür gibt es noch keine Werte.</li>
        </ul>
      </details>
      <details>
        <summary>Was zeigt der Live-Check?</summary>
        <p>
          Am Reisetag vergleichen wir die aktuellen Verspätungen beider Züge mit der Mindestumsteigezeit. Die
          Reserve ist die Zeit, die darüber hinaus bleibt. „Klappt“ heißt: 5 Minuten Reserve oder mehr. „Knapp“
          heißt: 2 bis 4 Minuten. „Gefährdet“ heißt: weniger als 2 Minuten, es reicht nur, wenn alles glattgeht. „Wird wohl nicht klappen“ heißt: nach den aktuellen Zeiten fährt der Anschluss vor dir ab.
        </p>
      </details>
      <details>
        <summary>Kann ich mich darauf verlassen?</summary>
        <p>
          Die Werte sind Schätzungen aus vergangenen Fahrten, keine Garantie. Bei Störungen, Bauarbeiten oder
          Streiks kann es ganz anders kommen. Achte unterwegs auf die Anzeigen und Durchsagen im Zug und am Bahnhof.
        </p>
      </details>
      <details>
        <summary>Kann ich hier Fahrkarten kaufen?</summary>
        <p>Nein. AnschlussRadar zeigt nur Verbindungen und ihre Zuverlässigkeit.</p>
      </details>
      <details>
        <summary>Wie lege ich die App auf den Startbildschirm?</summary>
        <p>
          iPhone: Öffne die Seite in Safari, tippe auf „Teilen“ und dann auf „Zum Home-Bildschirm“. Android: Öffne die
          Seite in Chrome, tippe auf das Menü (drei Punkte) und dann auf „App installieren“ oder „Zum Startbildschirm
          hinzufügen“.
        </p>
      </details>
      <p>
        Noch eine Frage offen? <Link href="/contact">Schreib mir.</Link>
      </p>
    </>
  );
}

function En() {
  return (
    <>
      <h1>Help</h1>
      <details open>
        <summary>What does the percentage mean?</summary>
        <p>
          "84% of these transfers work" means: for similar transfers in recent weeks (same station, similar trains,
          similar time to change), the connection was made in 84 out of 100 cases.
        </p>
        <p>
          The number next to a journey is the chance that all of its transfers work. A direct train has nothing to
          miss, so it gets no number.
        </p>
      </details>
      <details>
        <summary>What counts as made?</summary>
        <p>
          A transfer counts as made when the connecting train leaves at least the minimum transfer time after the
          actual arrival. That time is 3 minutes, or 5 minutes with a long-distance train, plus 2 minutes when you change
          between levels (for example from the underground S-Bahn platforms). We can't see whether someone ran or
          whether the train waited.
        </p>
      </details>
      <details>
        <summary>Why do some transfers have no score?</summary>
        <ul>
          <li>The model is still learning. During the first weeks there is only the live check.</li>
          <li>The transfer is at a station we don't collect data for yet. Right now these are the large main stations, and the list is growing.</li>
          <li>Part of the trip is a bus, tram or underground line. There are no scores for those yet.</li>
        </ul>
      </details>
      <details>
        <summary>What does the live check show?</summary>
        <p>
          On the day of travel we compare the current delays of both trains with the minimum transfer time. The time
          to spare is what's left on top of it. "Fine" means 5 minutes or more to spare. "Tight" means 2 to 4
          minutes. "At risk" means less than 2 minutes, so it only works if nothing else goes wrong. "Probably won't work" means that by the current times the connection leaves before you
          arrive.
        </p>
      </details>
      <details>
        <summary>Can I rely on it?</summary>
        <p>
          The scores are estimates from past trips, not a promise. Disruptions, engineering work or strikes can
          change everything. On the way, follow the displays and announcements on the train and at the station.
        </p>
      </details>
      <details>
        <summary>Can I buy tickets here?</summary>
        <p>No. AnschlussRadar only shows connections and how reliable they are.</p>
      </details>
      <details>
        <summary>How do I add the app to my home screen?</summary>
        <p>
          iPhone: open the page in Safari, tap "Share", then "Add to Home Screen". Android: open the page in Chrome,
          tap the menu (three dots), then "Install app" or "Add to Home screen".
        </p>
      </details>
      <p>
        Still have a question? <Link href="/contact">Write to me.</Link>
      </p>
    </>
  );
}

export function Help() {
  const { lang } = useI18n();
  return <div className="page prose wrap narrow">{lang === "de" ? <De /> : <En />}</div>;
}
