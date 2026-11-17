// Impressum and Datenschutzerklärung. The German text is the binding one; the
// English page is a translation for convenience. Operator details come from site.ts.
import { useState } from "react";
import type { ReactNode } from "react";
import { useI18n } from "../i18n";
import { NotList } from "../components/Why";
import { removeAllWatches } from "../lib/push";
import { store } from "../lib/storage";
import { SITE, isPlaceholder } from "../site";

const ext = { target: "_blank", rel: "noopener noreferrer" } as const;

// While the app is a demo, people sign in through Azure before they can open it.
const DEMO = (import.meta.env.VITE_WEB_ACCESS || "demo") !== "public";

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
      {lang !== "de" && (
        <p className="muted" lang="en">
          Legal notice required by German law. The information is the same in every language.
        </p>
      )}
      <h2>Angaben gemäß § 5 DDG</h2>
      <Address />
      <h2>Kontakt</h2>
      <p>
        E-Mail: <Email />
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
          removeAllWatches().finally(() => setDone(true));
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
      <NotList />

      <Section title="1. Verantwortlich">
        <Address />
        <p>
          E-Mail: <Email />
        </p>
      </Section>

      <Section title="2. Aufruf der App und Hosting">
        <p>
          AnschlussRadar läuft bei Microsoft Azure (Microsoft Ireland Operations Limited, One Microsoft Place, South
          County Business Park, Leopardstown, Dublin 18, Irland). Der Server, der Suchanfragen beantwortet, steht in Frankfurt am Main. Die Dateien der Web-Seite liefert Azure Static Web Apps über das weltweite Netz von Microsoft aus; sie sind dort in einem Rechenzentrum in den USA hinterlegt. Mit Microsoft besteht ein
          Vertrag zur Auftragsverarbeitung nach Art. 28 DSGVO. Für Daten, die dabei in die USA gelangen, ist Microsoft nach dem EU-US Data Privacy Framework zertifiziert.
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

      {DEMO && (
        <Section title="Anmeldung während der Demo-Phase">
          <p>
            Im Moment können nur eingeladene Personen AnschlussRadar öffnen. Du meldest dich dafür mit deinem GitHub-
            oder Microsoft-Konto an. Die Anmeldung übernimmt Microsoft Azure. Dabei erhält die App deinen
            Benutzernamen bzw. deine E-Mail-Adresse und eine Kennung deines Kontos, um zu prüfen, ob du eingeladen
            bist. Die Einladung und diese Angaben bleiben gespeichert, bis ich die Einladung lösche, spätestens
            wenn die Demo-Phase endet. Rechtsgrundlage ist Art. 6 Abs. 1 lit. b DSGVO: Du hast die Einladung
            angenommen, um die Demo zu nutzen.
          </p>
        </Section>
      )}

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

      <Section title="5. Kontakt per E-Mail">
        <p>
          Wenn du mir eine E-Mail schreibst, verarbeite ich deine E-Mail-Adresse, deinen Namen, falls du ihn nennst,
          und den Inhalt deiner Nachricht, um dir zu antworten. Ich lösche die E-Mails, wenn dein Anliegen erledigt
          ist, spätestens nach sechs Monaten, es sei denn, eine gesetzliche Pflicht verlangt eine längere
          Aufbewahrung. Rechtsgrundlage ist Art. 6 Abs. 1 lit. f DSGVO, mein berechtigtes Interesse ist die
          Beantwortung deiner Anfrage.
        </p>
      </Section>

      <Section title="6. Rückmeldung „Hat dieser Umstieg geklappt?“">
        <p>
          Nach einem Umstieg kannst du angeben, ob er geklappt hat. Gespeichert werden nur der Bahnhof, die beiden
          Züge, die geplanten Zeiten, deine Antwort und der Zeitpunkt der Antwort. Deine IP-Adresse, eine
          Gerätekennung oder andere Angaben über dich werden dabei nicht gespeichert. Gegen massenhafte Antworten hält
          der Server höchstens eine Stunde lang einen nicht umkehrbaren Hashwert der IP-Adresse im Arbeitsspeicher.
          Die Antworten dienen dazu, die Zuverlässigkeitswerte zu prüfen. Rechtsgrundlage ist Art. 6 Abs. 1 lit. f
          DSGVO.
        </p>
      </Section>

      <Section title="7. Benachrichtigungen für beobachtete Verbindungen">
        <p>
          Wenn du für eine Verbindung „Jeden Tag prüfen“ einschaltest, speichere ich: eine zufällige Gerätekennung, die
          dein Browser erzeugt, die Push-Adresse, die dein Browser dafür ausgibt, die beiden Bahnhöfe, die Abfahrtszeit,
          die Wochentage und die Sprache. Etwa eine Stunde vor Abfahrt sucht der Server die Verbindung und schickt nur
          dann eine Nachricht, wenn ein Umstieg gefährdet ist. Die Nachricht läuft über den Push-Dienst deines
          Browser-Herstellers (zum Beispiel Apple, Google oder Mozilla), der sie an dein Gerät zustellt; dabei können
          Daten in die USA gelangen.
        </p>
        <p>
          Die Daten liegen in Microsoft Azure (Frankfurt). Sie werden gelöscht, sobald du die Benachrichtigungen
          ausschaltest, mit dem Knopf oben, oder automatisch 90 Tage nachdem du die App zuletzt geöffnet hast.
          Rechtsgrundlage ist deine Einwilligung (Art. 6 Abs. 1 lit. a DSGVO, § 25 Abs. 1 TDDDG), die du jederzeit
          widerrufen kannst, indem du die Benachrichtigungen ausschaltest.
        </p>
      </Section>

      <Section title="8. Fragen auf der Hilfeseite">
        <p>
          Die Suche in den Hilfetexten läuft nur auf deinem Gerät; dabei wird nichts gesendet. Wenn du eine Frage
          absendest, speichere ich: den Text der Frage, die Sprache, den Zeitpunkt und eine zufällige Kennung. Name und
          E-Mail-Adresse werden nicht abgefragt. Auf deinem Gerät bleiben die Kennung und der Text, damit die Antwort
          unter „Meine Fragen“ erscheint. Wenn du um eine Benachrichtigung bittest, speichere ich zusätzlich die
          Push-Adresse deines Browsers, bis die Nachricht verschickt ist; der Versand läuft wie in Abschnitt 7
          beschrieben.
        </p>
        <p>
          Ist die automatische Antwort eingeschaltet, werden Fragen, zu denen die Hilfetexte nichts passendes enthalten,
          an Azure OpenAI von Microsoft geschickt (Verarbeitung in der EU). Microsoft nutzt diese Daten nicht zum
          Training seiner Modelle. Diese Fragen speichere ich nicht, außer du sendest sie danach selbst ab. Bitte
          schreib keine persönlichen Daten in eine Frage.
        </p>
        <p>
          Die Daten liegen in Microsoft Azure (Frankfurt). Fragen werden 30 Tage nach der Antwort gelöscht, Fragen ohne
          Antwort nach 60 Tagen. Rechtsgrundlage ist mein berechtigtes Interesse, Fragen zu beantworten und die Hilfe zu
          verbessern (Art. 6 Abs. 1 lit. f DSGVO), für die Benachrichtigung deine Einwilligung (Art. 6 Abs. 1 lit. a
          DSGVO, § 25 Abs. 1 TDDDG).
        </p>
      </Section>

      <Section title="9. Deine Rechte">
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
      <NotList />

      <Section title="1. Controller">
        <Address />
        <p>
          Email: <Email />
        </p>
      </Section>

      <Section title="2. Opening the app and hosting">
        <p>
          AnschlussRadar runs on Microsoft Azure (Microsoft Ireland Operations Limited, One Microsoft Place, South
          County Business Park, Leopardstown, Dublin 18, Ireland). The server that answers searches is in Frankfurt am Main. The files of the web page are delivered by Azure Static Web Apps through Microsoft's worldwide network; they are stored in a data centre in the US. There is a data processing
          agreement with Microsoft under Art. 28 GDPR. For data that reaches the US this way, Microsoft is certified under the EU-US Data Privacy Framework.
        </p>
        <p>
          When you open the app, the server processes technically necessary data: your IP address, date and time, the
          address you opened and your browser's identifier. Without this data the page can't be delivered. To find
          errors I keep logs of requests to the server (time, type of request, response time, error messages) for up
          to 90 days. IP addresses are not stored in these logs.
        </p>
        <p>The legal basis is Art. 6(1)(f) GDPR. My legitimate interest is a secure, working service.</p>
      </Section>

      {DEMO && (
        <Section title="Signing in during the demo phase">
          <p>
            Right now only invited people can open AnschlussRadar. You sign in with your GitHub or Microsoft account.
            Microsoft Azure handles the sign-in. The app receives your user name or email address and an ID of your
            account to check that you were invited. The invitation and these details are kept until I delete the
            invitation, at the latest when the demo phase ends. The legal basis is Art. 6(1)(b) GDPR: you accepted
            the invitation to use the demo.
          </p>
        </Section>
      )}

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

      <Section title="5. Contact by email">
        <p>
          When you send me an email I process your email address, your name if you give it, and the content of your
          message to reply to you. I delete the emails once your request is dealt with, at the latest after six
          months, unless a legal duty requires keeping them longer. The legal basis is Art. 6(1)(f) GDPR; my
          legitimate interest is answering your request.
        </p>
      </Section>

      <Section title="6. Feedback “Did this transfer work?”">
        <p>
          After a transfer you can say whether it worked. Only the station, the two trains, the planned times, your
          answer and the time of the answer are stored. Your IP address, a device ID or other details about you are
          not stored. To stop floods of answers, the server keeps a one-way hash of the IP address in memory for at
          most one hour. The answers are used to check the reliability scores. The legal basis is Art. 6(1)(f) GDPR.
        </p>
      </Section>

      <Section title="7. Alerts for watched connections">
        <p>
          When you turn on "Check every day" for a connection, I store: a random device ID made by your browser, the
          push address your browser hands out for it, the two stations, the departure time, the weekdays and the
          language. About an hour before departure the server looks up the connection and only sends a message if a
          change is at risk. The message goes through the push service of your browser maker (for example Apple, Google
          or Mozilla), which delivers it to your device; data may reach the US in the process.
        </p>
        <p>
          The data is stored in Microsoft Azure (Frankfurt). It is deleted as soon as you turn alerts off, with the
          button above, or automatically 90 days after you last opened the app. The legal basis is your consent (Art.
          6(1)(a) GDPR, § 25(1) TDDDG), which you can withdraw at any time by turning alerts off.
        </p>
      </Section>

      <Section title="8. Questions on the help page">
        <p>
          The search in the help texts runs only on your device; nothing is sent. When you send a question, I store:
          the text of the question, the language, the time and a random ID. Name and email address are not asked for.
          The ID and the text stay on your device so the answer can appear under "My questions". If you ask for a
          notification, I also store your browser's push address until the message has been sent; sending works as
          described in section 7.
        </p>
        <p>
          When the automatic answer is switched on, questions the help texts don't cover are sent to Microsoft's Azure
          OpenAI (processed in the EU). Microsoft does not use this data to train its models. I don't store these
          questions unless you send them afterwards yourself. Please don't put personal data in a question.
        </p>
        <p>
          The data is stored in Microsoft Azure (Frankfurt). Questions are deleted 30 days after the answer, and after
          60 days if there is no answer. The legal basis is my legitimate interest in answering questions and improving
          the help (Art. 6(1)(f) GDPR), and for the notification your consent (Art. 6(1)(a) GDPR, § 25(1) TDDDG).
        </p>
      </Section>

      <Section title="9. Your rights">
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
  const { lang, dict } = useI18n();
  if (lang === "de" || lang === "en") {
    return <div className="page prose wrap narrow">{lang === "de" ? <PrivacyDe /> : <PrivacyEn />}</div>;
  }
  // Other languages: the short list translated, the policy itself in English (German is binding).
  return (
    <div className="page prose wrap narrow">
      <NotList />
      <p className="muted lang-note">{dict.about.onlyDeEn}</p>
      <div lang="en" dir="ltr">
        <PrivacyEn />
      </div>
    </div>
  );
}
