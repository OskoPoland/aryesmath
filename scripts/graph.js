const manifestURL = new URL("../notecards/noteManifest.json", import.meta.url);

async function getNotecards() {
    const response = await fetch(manifestURL);

    if (!response.ok) {
        throw new Error(
        `Could not load notecard manifest: ${response.status}`
        );
    }
     const data = await response.json();

  const notecards = Array.isArray(data)
    ? data
    : data.notecards;

  if (!Array.isArray(notecards)) {
    throw new TypeError(
      "The notecard manifest must contain an array."
    );
  }

  return notecards;
}

function normalizeTags(tags) {
    if (!Array.isArray(tags)) {
        return []
    }

    return [
        ...new Set(
            tags.filter(tag => typeof tag === "string")
                .map(tag => tag.trim().toLowerCase())
                .filter(Boolean)
        )
    ];
}

function buildCystoscapeElements(notecards) {
    const cards = notecards.map(card => ({
        ...card,
        tags : normalizeTags(card.tags)
    }));

    const nodes = cards.map(card => ({
        data : {
            id : card.slug,
            label : card.title,
            file : card.file,
            tags : card.tags.join(", ")
        }
    }));

    const edges = []
    for (let i = 0; i < cards.length; i += 1) {
    for (let j = i + 1; j < cards.length; j += 1) {
      const first = cards[i];
      const second = cards[j];

      const secondTags = new Set(second.tags);

      const sharedTags = first.tags.filter(tag =>
        secondTags.has(tag)
      );

      if (sharedTags.length === 0) {
        continue;
      }

      edges.push({
        data: {
          id: `${first.slug}--${second.slug}`,
          source: first.slug,
          target: second.slug,
          sharedTags: sharedTags.join(", "),
          weight: sharedTags.length
        }
      });
    }
  }

  return [...nodes, ...edges];
}

const cytoscape = window.cytoscape;

let currentGraph = null;

export async function loadNotecardGraph() {
    const container = document.getElementById("notecard-graph");
    const status = document.getElementById("graph-status");

    if (!container) {
        throw new Error(
            `Missing element with id=notecard-graph`
        );
    }

    if (typeof cytoscape !== 'function') {
        throw new Error("Cytoscape.js has not loaded");
    }

    const notecards = await getNotecards();
    const elements = buildCystoscapeElements(notecards);
    console.log(elements);
    if (currentGraph) {
        currentGraph.destroy();
    }

    currentGraph = cytoscape({
        container,
        elements,
         style: [
      {
        selector: "node",
        style: {
          label: "data(label)",
          width: 46,
          height: 46,
          "background-color": "#dbeafe",
          "border-color": "#2563eb",
          "border-width": 2,
          color: "#111827",
          "font-size": 13,
          "text-wrap": "wrap",
          "text-max-width": 130,
          "text-valign": "bottom",
          "text-margin-y": 8
        }
      },
      {
        selector: "node:selected",
        style: {
          "background-color": "#bfdbfe",
          "border-width": 4
        }
      },
      {
        selector: "edge",
        style: {
          width: "mapData(weight, 1, 5, 1, 6)",
          "line-color": "#9ca3af",
          "curve-style": "bezier",
          opacity: 0.7
        }
      },
      {
        selector: "edge:selected",
        style: {
          "line-color": "#2563eb",
          opacity: 1
        }
      }
    ],

    layout: {
      name: "cose",
      animate: false,
      fit: true,
      padding: 40
    } 
    });

    currentGraph.on("tap", "node", event => {
        const slug = event.target.id();
        window.location.hash = `/notes/${slug}`;
    });

    currentGraph.on("mouseover", "edge", event => {
        const sharedTags = event.target.data("sharedTags");
        event.target.style("label",sharedTags);
    });

    currentGraph.on("mouseout", "edge", event => {
        event.target.removeStyle("label");
    });

    if (status) {
        status.textContent = 
        `${currentGraph.nodes().length} notecards, ` + 
        `${currentGraph.edges().length} connections`;
    }

    return currentGraph;
}