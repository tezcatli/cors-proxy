import { normKey } from './utils.js'

const _map = new Map([
  // plain misspelling → canonical name (normKey applied automatically)
  // e.g. ['elden rings', 'Elden Ring'],
  ['artic eggs', 'Arctic Eggs'],
  ['make way', 'Make Way'],
  ['l\'ordre des géants','Indiana Jones and the Great Circle: The Order of Giants'],
  ['indiana jones et le cercle ancien','Indiana Jones and the Great Circle'],
  ['1348: Ex-Voto','1348: Ex Voto'],
  ['elden ring nightrein','elden ring nightreign'],
  ['Vendran las aves','Vendrán las aves'],
  ['shogun shodown','Shogun Showdown'],
  ['Eté','Été'],
  ['beyond good and evil remastered','Beyond Good & Evil: 20th Anniversary Edition'],
  ['Top Spin 2K25','Top Spin 2K 25'],

].map(([k, v]) => [normKey(k), v]))

export function correct(name) {
  return _map.get(normKey(name)) ?? name
}
