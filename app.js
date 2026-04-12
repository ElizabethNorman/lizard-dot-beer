const content = document.getElementById("content");

async function loadPage() {
  const page = window.location.hash.substring(1) || "home";
  const res = await fetch(`/pages/${page}.html`);
  const html = await res.text();
  content.innerHTML = html;
}

window.addEventListener("hashchange", loadPage);

// load default page
loadPage();