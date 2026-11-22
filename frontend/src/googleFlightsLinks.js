// Links de busca Google Flights: usa q, formato legível suportado pelo buscador.
// O Google pode reinterpretar filtros ao abrir; a ativação do alerta é sempre manual.
export const ORIGIN_AIRPORTS = Object.freeze({
  'São Paulo': ['GRU', 'CGH', 'VCP'],
  'Rio de Janeiro': ['GIG', 'SDU'],
});
export const DESTINATION_AIRPORTS = Object.freeze({
  'Barcelona': ['BCN'],
  'Madri': ['MAD'],
  'Roma': ['FCO'],
  'Milão': ['MXP', 'BGY', 'LIN'],
});
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export function googleFlightsSearchUrl({ originCity, originAirport, destinationCity, destinationAirport, departure, returnDate }) {
  if (!ORIGIN_AIRPORTS[originCity]?.includes(originAirport)) {
    throw new Error('Aeroporto de origem inválido');
  }
  if (!DESTINATION_AIRPORTS[destinationCity]?.includes(destinationAirport)) {
    throw new Error('Aeroporto de destino inválido');
  }
  if (!DATE_PATTERN.test(departure) || !DATE_PATTERN.test(returnDate) || returnDate <= departure) {
    throw new Error('Datas de viagem inválidas');
  }
  const query = `Round trip flights from ${originAirport} to ${destinationAirport} on ${departure} returning ${returnDate} for 2 adults in economy`;
  const parameters = new URLSearchParams({ hl: 'pt-BR', gl: 'BR', curr: 'BRL', q: query });
  return `https://www.google.com/travel/flights?${parameters.toString()}`;
}
