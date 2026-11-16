// Impressum and Datenschutzerklärung. The German text is the binding one; the
// English page is a translation for convenience. Operator details come from site.ts.
import { useState } from "react";
import type { ReactNode } from "react";
import { useI18n } from "../i18n";
import { Link } from "../lib/router";
import { store } from "../lib/storage";
import { SITE, isPlaceholder } from "../site";

const ext = { target: "_blank", rel: "noopener noreferrer" } as const;

function V({ children }: { children: string }) {
  return isPlaceholder(children) ? <mark>{children}</mark> : <>{children}</>;
}

function Address() {
  return (
    <p>
      <V>{SITE.operatorName}</V>
      <br />
      <V>{SITE.street}</V>
      <br />
      <V>{SITE.city}</V>
      <br />
      <V>{SITE.country}</V>
    </p>
  );
}

function Email() {
  return isPlaceholder(SITE.email) ? <mark>{SITE.email}</mark> : <a href={`mailto:${SITE.email}`}>{SITE.email}</a>;
}

export function Impressum() {
  const { lang } = useI18n();
  return (
    <div className="page prose wrap narrow">
      <h1>Impressum</h1>
      {lang === "en" && (
        <p className="muted">Legal notice required by German law. The information is the same in both languages.</p>
      )}
      <h2>Angaben gemäß § 5 DDG</h2>
      <Address />
      <h2>Kontakt</h2>
      <p>
        E-Mail: <Email />
        <br />
        oder über das <Link href="/contact">Kontaktformular</Link>
      </p>
      <h2>Verantwortlich für den Inhalt nach § 18 Abs. 2 MStV</h2>
      <p>
        <V>{SITE.operatorName}</V>, Anschrift wie oben
      </p>
      <h2>Hinweis</h2>
      <p>
        AnschlussRadar ist ein privates, nicht kommerzielles Projekt. Es ist kein Angebot der Deutschen Bahn AG und
        steht in keiner Verbindung zu ihr. Alle Angaben zu Verbindungen und ihrer Zuverlässigkeit sind ohne Gewähr.
      </p>
    </div>
  );
}

function ClearButton() {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  return (
    <p>
      <button
        type="button"
        className="ghost"
        onClick={() => {
          store.clearAll();
          setDone(true);
        }}
      >
        {t("privacy.clear")}
      </button>
      {done && (
        <span role="status" className="small">
          {" "}
          {t("privacy.cleared")}
        </span>
      )}
    </p>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function PrivacyDe() {
  return (
    <>
      <h1>Datenschutzerklärung</h1>
      <p className="lead">
        Kurz gesagt: AnschlussRadar braucht kein Konto, setzt keine Cookies, zeigt keine Werbung und verfolgt dich
        nicht. Es lädt keine Schriften, Karten oder Skripte von fremden Servern. Hier steht genau, welche Daten
        trotzdem anfallen und warum.
      </p>

      <Section title="1. Verantwortlich">
        <Address />
        <p>
          E-Mail: <Email />
        </p>
      </Section>

      <Section title="2. Aufruf der App und Hosting">
        <p>
          AnschlussRadar läuft bei Microsoft Azure (Microsoft Ireland Operations Limited, One Microsoft Place, South
          County Business Park, Leopardstown, Dublin 18, Irland) in Rechenzentren in der EU. Mit Microsoft besteht ein
          Vertrag zur Auftragsverarbeitung nach Art. 28 DSGVO. Microsoft ist nach dem EU-US Data Privacy Framework
          zertifiziert, falls im Einzelfall Daten in die USA gelangen.
        </p>
        <p>
          Wenn du die App aufrufst, verarbeitet der Server technisch notwendige Daten: deine IP-Adresse, Datum und
          Uhrzeit, die aufgerufene Adresse und die Kennung deines Browsers. Ohne diese Daten kann die Seite nicht
          ausgeliefert werden. Zur Fehlersuche speichere ich Protokolle der Anfragen an den Server (Zeitpunkt,
          Art der Anfrage, Antwortzeit, Fehlermeldungen) höchstens 90 Tage. IP-Adressen werden in diesen Protokollen
          nicht gespeichert.
        </p>
        <p>Rechtsgrundlage ist Art. 6 Abs. 1 lit. f DSGVO. Mein berechtigtes Interesse ist ein sicherer und funktionierender Betrieb.</p>
      </Section>

      <Section title="3. Bahnhofs- und Verbindungssuche">
        <p>
          Was du in die Bahnhofssuche tippst, geht an den Server von AnschlussRadar, damit er passende Bahnhöfe vorschlagen kann. Bei
          einer Verbindungssuche schickt der Server die Koordinaten von Start und Ziel und die gewünschte Zeit an den
          freien Routenplaner <a href="https://transitous.org" {...ext}>Transitous</a>. Deine IP-Adresse oder andere
          Angaben über dich werden dabei nicht weitergegeben.
        </p>
        <p>
          Suchergebnisse bleiben höchstens zwei Minuten im Arbeitsspeicher, damit gleiche Suchen schneller gehen.
          Außerdem wird gezählt, wie viele Suchen es pro Tag gibt. Beides lässt sich keiner Person zuordnen.
          Rechtsgrundlage ist Art. 6 Abs. 1 lit. f DSGVO: Ohne diese Verarbeitung könnte die App keine Verbindungen
          anzeigen.
        </p>
      </Section>

      <Section title="4. Speicherung auf deinem Gerät">
        <p>
          Die App speichert einige Dinge nur in deinem Browser (Local Storage), damit sie beim nächsten Besuch noch da
          sind: die gewählte Sprache, deine gespeicherten Strecken und die letzten fünf Suchen. Diese Daten verlassen
          dein Gerät nicht. Außerdem legt der Browser die App-Dateien in einem Zwischenspeicher ab, damit sie auch ohne
          Netz startet.
        </p>
        <p>
          Das ist für die Funktionen, die du nutzt, unbedingt erforderlich (§ 25 Abs. 2 Nr. 2 TDDDG). Du kannst die
          Daten jederzeit löschen, mit diesem Knopf oder in den Einstellungen deines Browsers:
        </p>
        <ClearButton />
      </Section>

      <Section title="5. Kontaktformular">
        <p>
          Wenn du das Kontaktformular nutzt, verarbeite ich deinen Namen, deine E-Mail-Adresse, das Thema und deine
          Nachricht, um dir zu antworten. Die Nachricht wird über Microsoft Azure Communication Services als E-Mail an
          mich geschickt und nicht in einer Datenbank gespeichert. Ich lösche sie, wenn dein Anliegen erledigt ist,
          spätestens nach sechs Monaten, es sei denn, eine gesetzliche Pflicht verlangt eine längere Aufbewahrung.
        </p>
        <p>
          Gegen Spam begrenzt der Server die Zahl der Nachrichten pro Absender. Dafür hält er einen nicht
          umkehrbaren Hashwert der IP-Adresse höchstens eine Stunde im Arbeitsspeicher. Rechtsgrundlage ist Art. 6
          Abs. 1 lit. f DSGVO, mein berechtigtes Interesse ist die Beantwortung deiner Anfrage und der Schutz vor
          Missbrauch.
        </p>
      </Section>

      <Section title="6. Deine Rechte">
        <p>
          Du hast das Recht auf Auskunft (Art. 15 DSGVO), Berichtigung (Art. 16), Löschung (Art. 17), Einschränkung
          der Verarbeitung (Art. 18), Datenübertragbarkeit (Art. 20) und Widerspruch gegen Verarbeitungen auf Grundlage
          von Art. 6 Abs. 1 lit. f (Art. 21). Schreib dafür einfach an die oben genannte Adresse.
        </p>
        <p>
          Du kannst dich außerdem bei einer Datenschutz-Aufsichtsbehörde beschweren, zum Beispiel beim{" "}
          <a href="https://datenschutz.hessen.de" {...ext}>
            Hessischen Beauftragten für Datenschutz und Informationsfreiheit
          </a>
          .
        </p>
      </Section>

      <p className="muted small">Stand: {SITE.privacyUpdated}</p>
    </>
  );
}

function PrivacyEn() {
  return (
    <>
      <h1>Privacy policy</h1>
      <p className="muted">This is a translation for convenience. The German version is the binding one.</p>
      <p className="lead">
        In short: AnschlussRadar needs no account, sets no cookies, shows no ads and does not track you. It loads no
        fonts, maps or scripts from other servers. Here is exactly which data is still processed and why.
      </p>

      <Section title="1. Controller">
        <Address />
        <p>
          Email: <Email />
        </p>
      </Section>

      <Section title="2. Opening the app and hosting">
        <p>
          AnschlussRadar runs on Microsoft Azure (Microsoft Ireland Operations Limited, One Microsoft Place, South
          County Business Park, Leopardstown, Dublin 18, Ireland) in data centres in the EU. There is a data processing
          agreement with Microsoft under Art. 28 GDPR. Microsoft is certified under the EU-US Data Privacy Framework in
          case data reaches the US in individual cases.
        </p>
        <p>
          When you open the app, the server processes technically necessary data: your IP address, date and time, the
          address you opened and your browser's identifier. Without this data the page can't be delivered. To find
          errors I keep logs of requests to the server (time, type of request, response time, error messages) for up
          to 90 days. IP addresses are not stored in these logs.
        </p>
        <p>The legal basis is Art. 6(1)(f) GDPR. My legitimate interest is a secure, working service.</p>
      </Section>

      <Section title="3. Station and journey search">
        <p>
          What you type into the station search goes to the AnschlussRadar server so it can suggest stations. For a journey search
          the server sends the coordinates of start and destination and the time you chose to the free journey planner{" "}
          <a href="https://transitous.org" {...ext}>Transitous</a>. Your IP address and other details about you are
          not passed on.
        </p>
        <p>
          Search results stay in memory for up to two minutes so that repeated searches are faster, and the server counts how many searches there are per day. Neither can be linked to a person. The legal basis is Art. 6(1)(f)
          GDPR: without this the app couldn't show connections.
        </p>
      </Section>

      <Section title="4. Storage on your device">
        <p>
          The app keeps a few things only in your browser (local storage) so they are still there next time: your
          language, your saved routes and your last five searches. This data never leaves your device. The browser
          also caches the app files so it can start without a network.
        </p>
        <p>
          This is strictly necessary for the features you use (§ 25(2) no. 2 TDDDG). You can delete the data at any
          time, with this button or in your browser settings:
        </p>
        <ClearButton />
      </Section>

      <Section title="5. Contact form">
        <p>
          When you use the contact form I process your name, email address, topic and message to reply to you. The
          message is sent to me as an email through Microsoft Azure Communication Services and is not stored in a
          database. I delete it once your request is dealt with, at the latest after six months, unless a legal duty
          requires keeping it longer.
        </p>
        <p>
          To stop spam the server limits the number of messages per sender. For this it keeps a one-way hash of the IP
          address in memory for at most one hour. The legal basis is Art. 6(1)(f) GDPR; my legitimate interest is
          answering your request and preventing abuse.
        </p>
      </Section>

      <Section title="6. Your rights">
        <p>
          You have the right of access (Art. 15 GDPR), rectification (Art. 16), erasure (Art. 17), restriction of
          processing (Art. 18), data portability (Art. 20) and to object to processing based on Art. 6(1)(f) (Art.
          21). Just write to the address above.
        </p>
        <p>
          You can also complain to a data protection authority, for example the{" "}
          <a href="https://datenschutz.hessen.de" {...ext}>
            Hessian Commissioner for Data Protection and Freedom of Information
          </a>
          .
        </p>
      </Section>

      <p className="muted small">Last updated: {SITE.privacyUpdated}</p>
    </>
  );
}

export function Privacy() {
  const { lang } = useI18n();
  return <div className="page prose wrap narrow">{lang === "de" ? <PrivacyDe /> : <PrivacyEn />}</div>;
}
