import test from 'node:test';
import assert from 'node:assert/strict';
import {googleFlightsSearchUrl, ORIGIN_AIRPORTS, DESTINATION_AIRPORTS} from '../src/googleFlightsLinks.js';

test('link Google Flights leva parâmetros de ida e volta para dois adultos', () => {
  const url = new URL(googleFlightsSearchUrl({
    originCity: 'São Paulo', originAirport: 'GRU',
    destinationCity: 'Barcelona', destinationAirport: 'BCN',
    departure: '2027-09-08', returnDate: '2027-09-23'
  }));
  assert.equal(url.hostname, 'www.google.com');
  assert.equal(url.pathname, '/travel/flights');
  assert.equal(url.searchParams.get('curr'), 'BRL');
  assert.equal(url.searchParams.get('hl'), 'pt-BR');
  assert.match(url.searchParams.get('q'), /GRU to BCN on 2027-09-08 returning 2027-09-23/);
  assert.match(url.searchParams.get('q'), /2 adults in economy/);
});
test('links distinguem datas de retorno e aeroportos', () => {
  const p = { originCity:'Rio de Janeiro', originAirport:'GIG', destinationCity:'Milão',
    destinationAirport:'MXP', departure:'2027-09-11', returnDate:'2027-09-26' };
  const first = googleFlightsSearchUrl(p);
  const second = googleFlightsSearchUrl({...p, originAirport:'SDU', destinationAirport:'BGY', returnDate:'2027-09-27'});
  assert.notEqual(first, second);
  assert.match(new URL(second).searchParams.get('q'), /SDU to BGY on 2027-09-11 returning 2027-09-27/);
});
test('bloqueia cidades, aeroportos e datas incorretas', () => {
  const p = { originCity:'São Paulo', originAirport:'GRU', destinationCity:'Roma',
    destinationAirport:'FCO', departure:'2027-09-08', returnDate:'2027-09-24'};
  assert.throws(()=> googleFlightsSearchUrl({...p,originAirport:'ZZZ'}));
  assert.throws(()=> googleFlightsSearchUrl({...p,destinationAirport:'MAD'}));
  assert.throws(()=> googleFlightsSearchUrl({...p,returnDate:'2027-09-07'}));
  assert.deepEqual(ORIGIN_AIRPORTS['São Paulo'],['GRU','CGH','VCP']);
  assert.deepEqual(DESTINATION_AIRPORTS['Milão'],['MXP','BGY','LIN']);
});
