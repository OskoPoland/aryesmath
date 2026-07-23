import { loadNoteCardList, getNotecardPath } from "./notes.js";
import { loadNotecardGraph } from "./graph.js";

const app = document.getElementById("app");
//Page Routes - When adding a new page add a new route
const pages = {
  "/": "./pages/home.html",
  "/cv": "./pages/index.html",
  "/notes": "./pages/notes.html",
  "/teaching": "./pages/teaching.html",
  "/writings": "./pages/writings.html",
  "/notes" : "./pages/notes.html"
};

async function renderPage() {
  const route = window.location.hash.slice(1) || "/";
  let pagePath = pages[route];

  if (!pagePath && route.startsWith("/notes/")) {
    pagePath = await getNotecardPath(route);
  }
  console.log(pagePath);
  if (!pagePath) {
    app.innerHTML = `
            <section>
                <h2>404</h2>
                <p>Page not found.</p>
            </section>
        `;
    return;
  }

  const response = await fetch(pagePath);
  app.innerHTML = await response.text();

  if (window.MathJax?.startup?.promise) {
    await MathJax.startup.promise;
    await MathJax.typesetPromise([app]);
  }

  if (route === "/notes") {
    await loadNoteCardList();
    await loadNotecardGraph();
  }
} 

window.addEventListener("hashchange", renderPage);
window.addEventListener("DOMContentLoaded", renderPage);
