const BASE = 'https://images.igdb.com/igdb/image/upload'
export const igdbUrl = (id, tpl) => id ? `${BASE}/${tpl}/${id}.jpg` : null
