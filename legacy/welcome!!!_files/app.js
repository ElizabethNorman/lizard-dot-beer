const content = document.getElementById("content");

async function loadPage(page) {
  const res = await fetch(`/pages/${page}.html`);
  const html = await res.text();
  content.innerHTML = html;
}

document.querySelectorAll("nav a").forEach(link => {
  link.addEventListener("click", e => {
    e.preventDefault();
    const page = link.dataset.page;
    loadPage(page);
  });
});

// load default page
loadPage("home");