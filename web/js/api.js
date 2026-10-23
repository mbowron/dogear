// The only module that talks to the server.

async function call(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
    const err = new Error(typeof detail === "string" ? detail : "Request failed");
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const api = {
  recipes: () => call("GET", "/api/recipes").then((d) => d.recipes),
  recipe: (slug, servings) =>
    call("GET", `/api/recipes/${encodeURIComponent(slug)}${servings ? `?servings=${servings}` : ""}`),
  rate: (slug, stars) => call("PUT", `/api/recipes/${encodeURIComponent(slug)}/rating`, { stars }),
  logCook: (slug, { servings, note, date } = {}) =>
    call("POST", `/api/recipes/${encodeURIComponent(slug)}/cooks`, { servings, note, date }),
  editCook: (id, note) => call("PATCH", `/api/cooks/${id}`, { note }),
  deleteCook: (id) => call("DELETE", `/api/cooks/${id}`),
};
