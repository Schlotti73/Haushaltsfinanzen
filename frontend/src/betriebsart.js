import { systemApi } from './api'

// Die Betriebsart ("standard" oder "docker") kommt vom Server und aendert sich
// zur Laufzeit nie - sie haengt am Image bzw. an der Dienst-Konfiguration.
// Darum wird sie genau einmal geholt und das Versprechen behalten: jede weitere
// Komponente, die danach fragt, bekommt dasselbe, ohne eine zweite Anfrage.
//
// Faellt die Abfrage aus, gilt "standard". Das ist die richtige Richtung des
// Zweifels: im Standardbetrieb zeigt die Oberflaeche einen Windows-Hinweis zu
// viel, im Container waere umgekehrt ein Knopf sichtbar, der dort nichts tun
// kann.
let versprechen = null

export function ladeBetriebsart() {
  if (!versprechen) {
    versprechen = systemApi.version()
      .then(r => r.data?.betriebsart || 'standard')
      .catch(() => 'standard')
  }
  return versprechen
}
