import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const CONTRACT = JSON.parse(
  readFileSync(join(__dirname, '../../contracts/api.json'), 'utf8')
);

export const AUTH = CONTRACT.auth;
export const RAWG = CONTRACT.rawg;

export function mockResponse(entry, body = {}) {
  return {
    ok: entry.status < 400,
    status: entry.status,
    json: async () => body,
  };
}
