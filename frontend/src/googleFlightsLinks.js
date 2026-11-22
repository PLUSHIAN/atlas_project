// Somente gera LINKS de navegação, sem scraping nem acesso automatizado.
// O parâmetro tfs é o formato de busca utilizado pelo Google Flights (não é API
// pública documentada e pode mudar). Validar no Google antes de ativar alertas.
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
const writeNumber = value => {
  const bytes = [];
  let n = value;
  while (n >= 128) {
    bytes.push((n % 128) + 128);
    n = Math.floor(n / 128);
  }
  bytes.push(n);
  return bytes;
};
const numberField = (id, value) => [...writeNumber(id * 8), ...writeNumber(value)];
const bytesField = (id, bytes) => [...writeNumber(id * 8 + 2), ...writeNumber(bytes.length), ...bytes];
const textField = (id, value) => bytesField(id, Array.from(new TextEncoder().encode(value)));
const airportField = code => [...numberField(1, 1), ...textField(2, code)];
const legField = (date, from, to) => [
  ...textField(2, date),
  ...bytesField(13, airportField(from)),
  ...bytesField(14, airportField(to)),
];

// Viajar de A para B e voltar de B para A, com dois adultos e classe econômica.
// Os filtros são codificados no tfs (ao contrário de q, que abria a página vazia).
export function buildGoogleFlightsTfs(from, to, departure, returnDate) {
  const fields = [
    ...numberField(1, 28),
    ...numberField(2, 2),
    ...bytesField(3, legField(departure, from, to)),
    ...bytesField(3, legField(returnDate, to, from)),
    ...numberField(8, 1),
    ...numberField(8, 1),
    ...numberField(9, 1),
    ...numberField(14, 1),
    ...bytesField(16, [8, ...Array(9).fill(255), 1]),
    ...numberField(19, 1),
  ];
  return btoa(String.fromCharCode(...fields))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function googleFlightsSearchUrl({ originCity, originAirport, destinationCity, destinationAirport, departure, returnDate }) {
  if (!ORIGIN_AIRPORTS[originCity]?.includes(originAirport)) throw new Error('Aeroporto de origem inválido');
  if (!DESTINATION_AIRPORTS[destinationCity]?.includes(destinationAirport)) throw new Error('Aeroporto de destino inválido');
  if (!DATE_PATTERN.test(departure) || !DATE_PATTERN.test(returnDate) || returnDate <= departure ||
      !Number.isFinite(Date.parse(departure)) || !Number.isFinite(Date.parse(returnDate))) {
    throw new Error('Datas de viagem inválidas');
  }
  const tfs = buildGoogleFlightsTfs(originAirport, destinationAirport, departure, returnDate);
  const params = new URLSearchParams({ tfs, tfu: 'EgIIACIA', hl: 'pt-BR', gl: 'BR', curr: 'BRL' });
  return `https://www.google.com/travel/flights/search?${params}`;
}
