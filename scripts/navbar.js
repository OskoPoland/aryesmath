async function loadNavbar() {
    if (document.getElementById("navbar")) {
        return;
    }

    try {
        const response = await fetch("../components/navbar.html");

        if (!response.ok) {
            throw new Error(`Navbar could not be loaded: ${response.status}`);
        }

        const navbarHtml = await response.text();

        document.body.insertAdjacentHTML("afterbegin", navbarHtml);
    } catch (error) {
        console.error(error);
    }
}

document.addEventListener("DOMContentLoaded",loadNavbar);