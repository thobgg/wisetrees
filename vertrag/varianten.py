"""Varianten der Vertragstests: dieselben Fälle mit anderen Datenschutz-Einstellungen (KONZEPT.md E19).

Je Variante steht hier, was in der Referenz eingestellt wird (Baumwerte und Regeln) und was in wisetrees; die
Aufzeichnungen liegen unter aufzeichnungen/varianten/<variante>/<rolle>/<fall>.json, nur wo die Antwort von der
Hauptaufzeichnung abweicht. Nach jeder Variante gelten
wieder die Vorgaben eines neuen Baums.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .faelle import FAELLE, Fall


@dataclass(frozen=True)
class Variante:
    name: str
    zweck: str
    referenz: dict = field(default_factory=dict)        # Baumwert der Referenz → Wert
    referenz_spalten: dict = field(default_factory=dict)  # Spalte der Baumtabelle der Referenz → Wert
    wisetrees: dict = field(default_factory=dict)       # Feld von baum.datenschutz.Einstellungen → Wert
    regeln: tuple = ()                                   # (xref | None, tag | None, resn | None); None = Regel weg


# Fälle, die Sichtbarkeit zeigen: Liste, Suche, lebende und verstorbene Personen, Familien, Bäume.
_NAMEN = {
    "Info", "Individuals", "Individuals__q=Falkenrath",
    "Individual__xref=I1", "Individual__xref=I2", "Individual__xref=I21", "Individual__xref=I22",
    "Individual__xref=I54", "Individual__xref=I130",
    "Family__xref=F1", "Family__xref=F3", "Family__xref=F8",
    "Pedigree__xref=I1", "Descendants__generations=3__xref=I54", "Descendants__generations=2__xref=I21",
}
FAELLE_VARIANTEN: list[Fall] = [f for f in FAELLE if f.name in _NAMEN]

VARIANTEN: list[Variante] = [
    Variante("schutz-aus", "Datenschutz ganz aus: alle Datensätze für alle",
             referenz={"HIDE_LIVE_PEOPLE": "0"}, wisetrees={"enabled": False}),
    Variante("nur-mitglieder", "Baum nur für angemeldete Mitglieder",
             wisetrees={"members_only": True}, referenz_spalten={"private": 1}),
    Variante("verstorbene-ab-mitglied", "Verstorbene erst ab Mitglied",
             referenz={"SHOW_DEAD_PEOPLE": "1"}, wisetrees={"show_dead_people": 1}),
    Variante("namen-nur-verwalter", "Namen privater Personen nur für Verwalter",
             referenz={"SHOW_LIVING_NAMES": "0"}, wisetrees={"show_living_names": 0}),
    Variante("namen-fuer-alle", "Namen privater Personen auch für Besucher",
             referenz={"SHOW_LIVING_NAMES": "2"}, wisetrees={"show_living_names": 2}),
    Variante("beziehungen-aus", "Familien mit privaten Mitgliedern nicht zeigen",
             referenz={"SHOW_PRIVATE_RELATIONSHIPS": "0"}, wisetrees={"show_private_relationships": False}),
    Variante("hoechstalter-60", "Höchstalter 60 Jahre statt 120",
             referenz={"MAX_ALIVE_AGE": "60"}, wisetrees={"max_alive_age": 60}),
    Variante("nach-geburt-150", "Verstorbene privat, bis die Geburt 150 Jahre zurückliegt",
             referenz={"KEEP_ALIVE_YEARS_BIRTH": "150"}, wisetrees={"keep_alive_years_birth": 150}),
    Variante("nach-tod-60", "Verstorbene privat, bis der Tod 60 Jahre zurückliegt",
             referenz={"KEEP_ALIVE_YEARS_DEATH": "60"}, wisetrees={"keep_alive_years_death": 60}),
    Variante("regeln", "Regeln je Art, je Datensatz und je Faktart an einem Datensatz",
             regeln=((None, "OCCU", "privacy"), (None, "SOUR", None), (None, "OBJE", "privacy"),
                     ("I21", None, "confidential"), ("I22", "BIRT", "confidential"), ("F8", None, "privacy"),
                     ("I54", None, "none"))),
]
