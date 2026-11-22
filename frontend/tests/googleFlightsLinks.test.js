import test from 'node:test';
import assert from 'node:assert/strict';
import {googleFlightsSearchUrl, buildGoogleFlightsTfs, ORIGIN_AIRPORTS, DESTINATION_AIRPORTS} from '../src/googleFlightsLinks.js';

// Analisa a estrutura protobuf, em vez de apenas verificar um texto q ignorado.
function readFields(buffer) {
  let pos = 0;
  const readNum = () => {
    let v = 0, shift = 0, byte;
    do {
      byte = buffer[pos++];
      if (byte === undefined) throw new Error('Protobuf incompleto');
      v += (byte & 127) * 2 ** shift;
      shift += 7;
    } while (byte & 128);
    return v;
  };
  const fields = [];
  while (pos < buffer.length) {
    const tag = readNum();
    const id = tag >>> 3;
    const type = tag & 7;
    if (type === 0) fields.push({id, type, value: readNum()});
    else if (type === 2) {
      const length = readNum();
      fields.push({id, type, value: buffer.subarray(pos, pos + length)});
      pos += length;
    } else throw new Error('Tipo protobuf inesperado');
  }
  return fields;
}
const decode = url => readFields(Buffer.from(new URL(url).searchParams.get('tfs'), 'base64url'));
const findText = (fields, id) => fields.find(x => x.id === id).value.toString('utf8');

test('link contém ida, volta, aeroportos e 2 adultos realmente codificados', () => {
  const url = googleFlightsSearchUrl({
    originCity:'São Paulo', originAirport:'GRU',
    destinationCity:'Barcelona', destinationAirport:'BCN',
    departure:'2027-09-09', returnDate:'2027-09-24'
  });
  const parsed = new URL(url);
  assert.equal(parsed.hostname, 'www.google.com');
  assert.equal(parsed.pathname, '/travel/flights/search');
  assert.equal(parsed.searchParams.get('curr'), 'BRL');
  assert.ok(parsed.searchParams.has('tfs'));
  assert.equal(parsed.searchParams.has('q'), false);
  const fields = decode(url);
  assert.equal(fields.filter(f => f.id === 8).length, 2);
  assert.equal(fields.find(f=>f.id===9).value, 1);
  assert.equal(fields.find(f=>f.id===19).value, 1);
  const legs = fields.filter(f=>f.id===3).map(f=>readFields(f.value));
  assert.equal(legs.length, 2);
  assert.equal(findText(legs[0],2), '2027-09-09');
  assert.equal(findText(legs[1],2), '2027-09-24');
  const a = readFields(legs[0].find(f=>f.id===13).value);
  const b = readFields(legs[0].find(f=>f.id===14).value);
  const c = readFields(legs[1].find(f=>f.id===13).value);
  const d = readFields(legs[1].find(f=>f.id===14).value);
  assert.equal(findText(a,2), 'GRU');
  assert.equal(findText(b,2), 'BCN');
  assert.equal(findText(c,2), 'BCN');
  assert.equal(findText(d,2), 'GRU');
});

test('links distinguem origem destino e datas e codificam três aeroportos de Milão', () => {
  const p = { originCity:'Rio de Janeiro', originAirport:'GIG', destinationCity:'Milão',
    destinationAirport:'MXP', departure:'2027-09-11', returnDate:'2027-09-26'};
  const first = googleFlightsSearchUrl(p);
  const second = googleFlightsSearchUrl({...p, originAirport:'SDU', destinationAirport:'BGY', returnDate:'2027-09-27'});
  assert.notEqual(first, second);
  const secondBytes = Buffer.from(new URL(second).searchParams.get('tfs'), 'base64url');
  assert.ok(secondBytes.includes(Buffer.from('SDU')));
  assert.ok(secondBytes.includes(Buffer.from('BGY')));
  assert.ok(secondBytes.includes(Buffer.from('2027-09-27')));
  assert.deepEqual(ORIGIN_AIRPORTS['São Paulo'],['GRU','CGH','VCP']);
  assert.deepEqual(DESTINATION_AIRPORTS['Milão'],['MXP','BGY','LIN']);
});

test('bloqueia combinações inválidas', () => {
  const p = { originCity:'São Paulo', originAirport:'GRU', destinationCity:'Roma',
    destinationAirport:'FCO', departure:'2027-09-08', returnDate:'2027-09-24'};
  assert.throws(()=> googleFlightsSearchUrl({...p,originAirport:'ZZZ'}));
  assert.throws(()=> googleFlightsSearchUrl({...p,destinationAirport:'MAD'}));
  assert.throws(()=> googleFlightsSearchUrl({...p,returnDate:'2027-09-07'}));
  assert.match(buildGoogleFlightsTfs('GRU','FCO','2027-09-08','2027-09-24'), /^[A-Za-z0-9_-]+$/);
});
