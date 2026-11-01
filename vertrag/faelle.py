"""Die Fälle der Vertragstests: welche Route mit welchen Parametern für welche Rolle.

Gewählt am Falkenrath-Baum 1.7.1 (CC0):
  I1  Jonas Falkenrath, *1985, lebt; Eltern F3, Ehe F1
  I2  Mira Sandvoss, *1987, lebt, ohne Eltern
  I21 Heinrich Falkenrath, 1897–†, Porträt, Paten, Ehe F8 (Hochzeit 1924)
  I22 Anna Rosskamp, 1901–†, Porträt
  I54 Hans Jürgen Falkenrath, „um 1770“, Stammvater, Ehe F22
  I130 Georg Mohwinkel, 1833–†, Ort mit GOV-Kennung
Unbekannte Kennungen prüfen den Fehlerweg.

Ein Fall wird für jede Rolle aufgezeichnet und geprüft.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BAUM = "falkenrath"

# Passwort aller Testkonten (nur für Wegwerf-Testserver)
PASSWORT = "vertrag-passwort-1"

# Rolle -> Kontoname (None = nicht angemeldet)
ROLLEN = {
    "besucher": None,
    "mitglied": "mitglied",
    "bearbeiter": "bearbeiter",
    "moderator": "moderator",
    "verwalter": "verwalter",
}


@dataclass(frozen=True)
class Fall:
    aktion: str
    params: dict = field(default_factory=dict)
    mit_baum: bool = True

    @property
    def name(self) -> str:
        teile = [self.aktion] + [f"{k}={v}" for k, v in sorted(self.params.items())]
        return "__".join(teile).replace(" ", "_")

    def __hash__(self):
        return hash(self.name)


FAELLE: list[Fall] = [
    Fall("Info", mit_baum=False),
    # Personenliste und Suche
    Fall("Individuals"),
    Fall("Individuals", {"page": 2}),
    Fall("Individuals", {"q": "Falkenrath"}),
    Fall("Individuals", {"q": "Rosskamp"}),
    Fall("Individuals", {"q": "Jonas"}),
    Fall("Individuals", {"q": "Bienenbüttel", "scope": "all"}),
    Fall("Individuals", {"q": "Gibtesnicht"}),
    # Einzelne Personen
    Fall("Individual", {"xref": "I1"}),
    Fall("Individual", {"xref": "I2"}),
    Fall("Individual", {"xref": "I21"}),
    Fall("Individual", {"xref": "I22"}),
    Fall("Individual", {"xref": "I54"}),
    Fall("Individual", {"xref": "I130"}),
    Fall("Individual", {"xref": "I21", "relativeTo": "I130"}),
    Fall("Individual", {"xref": "I22", "relativeTo": "I1"}),
    Fall("Individual", {"xref": "I99999"}),
    # Familien
    Fall("Family", {"xref": "F1"}),
    Fall("Family", {"xref": "F3"}),
    Fall("Family", {"xref": "F8"}),
    Fall("Family", {"xref": "F22"}),
    Fall("Family", {"xref": "F99999"}),
    # Vorfahren
    Fall("Pedigree", {"xref": "I1"}),
    Fall("Pedigree", {"xref": "I1", "generations": 5}),
    Fall("Pedigree", {"xref": "I21", "generations": 3, "siblings": 1}),
    Fall("Pedigree", {"xref": "I130", "generations": 2}),
    # Faktenarten zum Anlegen
    Fall("Tags", {"type": "INDI"}),
    Fall("Tags", {"type": "FAM"}),
    Fall("Tags"),
    # Nachkommen
    Fall("Descendants", {"xref": "I54", "generations": 3}),
    Fall("Descendants", {"xref": "I21", "generations": 2}),
    Fall("Descendants", {"xref": "I1"}),
]
