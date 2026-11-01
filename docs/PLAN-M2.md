# Meilenstein 2, Schritt 1: Schreiben mit Moderation

Stand: 02.11.2026. Grundlage: KONZEPT.md 5.3, E4 (a), E7, E17, E19 B, E21; FUNKTIONEN.md 1.4 (`write`, `moderation`).

## Ziel

Bearbeiter ändern den Baum über die Apps wie bei der Referenz: Fakten anlegen, ändern und löschen, Personen anlegen,
verknüpfen, lösen und löschen. Jede Änderung ist zuerst **offen**; Moderatoren und Verwalter nehmen sie an oder
verwerfen sie. Mit „sofort annehmen“ am Konto gilt sie gleich. Danach meldet `Info.features` `write` und
`moderation`.

## Was feststeht

- **Ablage (E4 a):** Die Modelltabellen enthalten nur den angenommenen Stand. Offene Änderungen sind Sätze in
  `change_set` mit Einzelschritten in `change_step` (Objektart, interne Kennung, Operation, alte und neue Werte).
  Besucher und Mitglieder lesen nur den angenommenen Stand; für sie gibt es nichts herauszufiltern.
- **Wer schreibt (Referenz):** Rolle Bearbeiter und höher. Ohne „sofort annehmen“ ist jede Änderung offen, auch die
  eines Moderators oder Verwalters; Annehmen und Verwerfen dürfen Moderator und Verwalter. Mit „sofort annehmen“
  entsteht der Satz gleich als angenommen – er ist dann nur Protokoll.
- **Lesen für Bearbeiter:** Die offenen Schritte werden über die Antwort gelegt, berührte Fakten tragen
  `pending: true`. Suche und Personenliste laufen auf dem angenommenen Stand wie in der Referenz (E21).
- **Kennungen:** neue Datensätze im Stil `I…`, `F…` (E1); `factId` bleibt bei Änderungen gleich (E7). Die Apps
  suchen nach dem Speichern die neue Kennung und nehmen sonst die alte – beides geht.
- **Nach dem Annehmen** wird das Modell neu geladen (E21). Offene Änderungen allein ändern das Modell nicht.
- **Eingabe:** nur die Felder, die die Apps senden (Art, Wert, Datum, Ort, Notiz, Typ, Adresse); GEDCOM-Text als
  Eingabe nicht (FUNKTIONEN.md 1.4).

## Schritte (je ein Commit mit Tests, nach jedem Schritt anhalten)

1. **Schreibschicht:** Satz anlegen, Schritte speichern, annehmen (auf die Tabellen anwenden), verwerfen.
   Konflikterkennung beim Annehmen: Hat sich der angenommene Stand seit dem Anlegen geändert, wird nicht still
   überschrieben. Neue Kennungen, Protokoll.
2. **`Fact`:** Fakt anlegen oder ändern; Ortstext einem Ort zuordnen wie beim Import (dabei `3 _LOC`-Verweis wie
   in der Referenz, wenn eindeutig). Fehler wie die Referenz: `not-editable`, `fact-not-found`, `fact-locked`,
   `invalid-value`.
3. **Überlagerung und Moderation:** Leseschicht legt offene Schritte für Bearbeiter darüber; `Pending`, `Accept`,
   `Reject` (einzeln und für den ganzen Baum), `Info.trees[].pending`. Eigener Test: Besucher und Mitglieder sehen
   nie Offenes – weder in einer Person noch in Liste oder Suche.
4. **`DeleteFact`:** bei geteilten Ereignissen nur den eigenen Verweis lösen, wenn andere beteiligt sind.
5. **`AddIndividual`, `Link`, `Unlink`, `DeleteRecord`.**
6. **Fähigkeiten melden:** `features` um `write` und `moderation`; FUNKTIONEN.md und API-V1.md nachziehen.

## Wie es belegt wird

- **Schreibfälle aus der Referenz:** kurze Abläufe, z. B. „Fakt ändern als Bearbeiter → Person als Mitglied,
  Bearbeiter, Moderator lesen → `Pending` → annehmen → wieder lesen“. Vor jedem Ablauf werden die Datenbank der
  Referenz und die `.wise` samt Kontendatei von wisetrees auf den Ausgangsstand zurückgesetzt. Verglichen werden die
  Antwort des Schreibens und alle Lesungen danach, normalisiert wie die übrigen Vertragstests.
- **Unit-Tests** für Schreibschicht, Konflikte und die Sperre gegen Durchsickern.
- Die bestehenden Vertragstests und Varianten bleiben unverändert grün.

## Risiken

- **Geteilte Ereignisse:** Eine offene Änderung an einer Taufe betrifft die Antworten für Täufling, Eltern und
  Paten. Die Überlagerung muss jede Objektart richtig behandeln.
- **Konflikte:** Zwei offene Sätze am selben Fakt, oder ein angenommener Stand, der sich inzwischen geändert hat.
  Verhalten wie die Referenz, belegt durch einen Schreibfall.
- **Große Bäume:** Neuladen nach dem Annehmen kostet bei 50.000 Personen rund 3 Sekunden; gezieltes Nachführen erst,
  wenn es stört.
