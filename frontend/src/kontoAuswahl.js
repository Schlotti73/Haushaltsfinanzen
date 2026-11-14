// Konten für Auswahl-Dropdowns aufbereiten.
//
// Seiten laden bewusst weiterhin ALLE Konten (kontenApi.list(false)), weil sie
// damit auch die Kontonamen bereits gebuchter Vorgänge auflösen – ein
// deaktiviertes Konto muss in der Historie lesbar bleiben. Nur dort, wo man ein
// Konto neu AUSWÄHLT, sollen inaktive nicht mehr auftauchen.
//
// Das aktuell gewählte Konto bleibt immer enthalten, auch wenn es inaktiv ist:
// sonst fiele der Wert beim Bearbeiten eines Altdatensatzes still aus dem
// <select> und würde beim nächsten Speichern überschrieben.
export function auswaehlbareKonten(konten, gewaehltId) {
  const id = gewaehltId === null || gewaehltId === undefined || gewaehltId === ''
    ? null
    : Number(gewaehltId)
  return konten.filter((k) => k.aktiv || k.id === id)
}
