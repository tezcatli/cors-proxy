// Finding what a listener sees and acts on, never by a styling class (a
// redesign renames those): a button or a link by its name — its aria-label,
// else its text — and an element without one by its data-test.

const nameOf = el => el.attributes('aria-label') ?? el.text()

export const buttons = (w, name) =>
  w.findAll('button').filter(b => name === undefined || matches(nameOf(b), name))

export const button = (w, name) => buttons(w, name)[0]

export const links = (w, name) =>
  w.findAll('a').filter(a => name === undefined || matches(nameOf(a), name))

export const byTest = (w, id) => w.findAll(`[data-test="${id}"]`)

function matches(text, name) {
  return name instanceof RegExp ? name.test(text) : text.includes(name)
}
