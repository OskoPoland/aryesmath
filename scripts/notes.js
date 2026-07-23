const manifestURL = new URL("../notecards/noteManifest.json", import.meta.url);

export async function loadNoteCardList() {
    const list = document.getElementById("notecard-list");

    if (!list) {
        return;
    }

    try {
        const response = await fetch(manifestURL);

        if (!response.ok) {
            throw new Error(`Could not fetch notecard list :${response.status}`);
        }

        const notecards = await response.json();
        list.innerHTML = notecards
        list.replaceChildren();
        notecards.forEach(card => {
            console.log(card);
            console.log(card.title);
            const article = document.createElement('article');
            article.className = 'notecard-link';

            const link = document.createElement('a');
            link.href = `#/notes/${card.slug}`;
            link.textContent = card.title;

            article.appendChild(link);
            list.appendChild(article);
        });
    } catch(error) {
        console.error(error); 
        list.innerHTML = "<p>The notecard list could not be loaded.</p>";
    }
}

export async function getNotecardPath(route) {
    const response = await fetch(manifestURL);
    const notecards = await response.json();
    console.log(notecards);

    const slug = route.replace("/notes/", "");

    const card = notecards.find(
        notecard => notecard.slug === slug
    );

    return card?.file ?? null;
}