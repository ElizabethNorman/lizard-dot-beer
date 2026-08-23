let totalRoads = 0;

let progress = {
    walked: [],
    excluded: []
};

async function initializeWalkPg() {


    console.log("we got here");
    const progressResponse =
        await fetch('/assets/data/progress.json');

    progress =
        await progressResponse.json();



    const map = L.map('map').setView([53.9171, -122.7497], 13);

    let currentMode = "walked";





    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        {
            maxZoom: 19,
            referrerPolicy: 'strict-origin-when-cross-origin',
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);


    fetch('/assets/data/roads.geojson')
        .then(r => r.json())
        .then(data => {

            L.geoJSON(data, {
                onEachFeature,
                style: function (feature) {

                    const id =
                        feature.properties.OBJECTID;

                    if (progress.walked.includes(id)) {

                        return {
                            color: "green",
                            weight: 4
                        };
                    }

                    if (progress.excluded.includes(id)) {

                        return {
                            color: "red",
                            weight: 4
                        };
                    }

                    return {
                        color: "gray",
                        weight: 2
                    };
                }
            }).addTo(map);
            totalRoads = data.features.length;
            updateStats();
        });

    document.getElementById("walkedMode")?.addEventListener("click", () => {
        currentMode = "walked";
            updateModeDisplay();
    })

    document.getElementById("excludedMode")?.addEventListener("click", () => {
        currentMode = "excluded";
            updateModeDisplay();
    })

    const modeDisplay =
    document.getElementById(
        "currentModeDisplay"
    );

    function updateModeDisplay() {

    modeDisplay.textContent =
        `Mode: ${currentMode}`;
}

    function onEachFeature(feature, layer) {

        //start of where to comment out

        // layer.on('click', () => {

        //     const objectId = feature.properties.OBJECTID;

        //     const walkedIndex =
        //         progress.walked.indexOf(objectId);

        //     const excludedIndex =
        //         progress.excluded.indexOf(objectId);

        //     if (currentMode === "walked") {

        //         if (walkedIndex !== -1) {

        //             // Already walked -> remove it
        //             progress.walked.splice(walkedIndex, 1);

        //             layer.setStyle({
        //                 color: "gray",
        //                 weight: 2
        //             });

        //         } else {

        //             // Remove from excluded if needed
        //             if (excludedIndex !== -1) {
        //                 progress.excluded.splice(excludedIndex, 1);
        //             }

        //             // Add to walked
        //             progress.walked.push(objectId);

        //             layer.setStyle({
        //                 color: "blue",
        //                 weight: 4
        //             });
        //         }
        //     }

        //     if (currentMode === "excluded") {

        //         if (excludedIndex !== -1) {

        //             // Already excluded -> remove it
        //             progress.excluded.splice(excludedIndex, 1);

        //             layer.setStyle({
        //                 color: "gray",
        //                 weight: 2
        //             });

        //         } else {

        //             // Remove from walked if needed
        //             if (walkedIndex !== -1) {
        //                 progress.walked.splice(walkedIndex, 1);
        //             }

        //             // Add to excluded
        //             progress.excluded.push(objectId);

        //             layer.setStyle({
        //                 color: "red",
        //                 weight: 4
        //             });
        //         }
        //     }

        //     updateStats();
        // });

        //end of where to comment out

    }

    document
        .getElementById("exportProgress")
        ?.addEventListener("click", exportProgress);

}

function updateStats() {

    const walked = progress.walked.length;

    const excluded = progress.excluded.length;

    const walkableRoads =
        totalRoads - excluded;

    const percentage =
        walkableRoads > 0
            ? ((walked / walkableRoads) * 100)
                .toFixed(1)
            : 0;

    document.getElementById("stats").innerHTML = `
        <strong>STATS:</strong><br>
        Walked: ${walked}<br>
        Excluded: ${excluded}<br>
        Remaining: ${walkableRoads - walked}<br>
        Complete: ${percentage}%
    `;
}



function exportProgress() {

    const today =
        new Date().toISOString().split('T')[0];


    const data =
        JSON.stringify(progress, null, 2);

    const blob =
        new Blob([data], {
            type: "application/json"
        });

    const url =
        URL.createObjectURL(blob);

    const a =
        document.createElement("a");

    a.href = url;
    a.download = `progress-${today}.json`;

    a.click();

    URL.revokeObjectURL(url);
}

initializeWalkPg();
