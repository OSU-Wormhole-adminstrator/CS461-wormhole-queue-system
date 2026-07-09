document.addEventListener("DOMContentLoaded", function () {
    const socket = io("/hardware");

    socket.on("connect", function () {
        console.log("Connected to hardware updates");
    });

    socket.on("hardware_update", function (payload) {
        if (!payload || !Array.isArray(payload.boxes)) {
            return;
        }
        renderHardwareTable(payload.boxes);
        setLastApiPost(payload.last_update);
    });

    socket.on("disconnect", function () {
        console.log("Disconnected from hardware updates");
    });
});

function renderHardwareTable(boxes) {
    const rowsContainer = document.getElementById("hardware_rows");
    if (!rowsContainer) {
        return;
    }

    rowsContainer.innerHTML = "";
    if (boxes.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.setAttribute("colspan", "3");
        cell.style.cssText = "padding:8px; text-align:center;";
        cell.textContent = "No hardware box status is available yet.";
        row.appendChild(cell);
        rowsContainer.appendChild(row);
        return;
    }

    boxes.forEach(function (box) {
        const row = document.createElement("tr");
        const nameCell = createCell(box.name || "");
        const statusCell = createCell(box.status || "Unknown");
        const timeCell = createCell(box.last_seen_local || box.last_seen || "");

        statusCell.style.backgroundColor = statusColor(box.status);
        statusCell.style.color = "black";

        row.appendChild(nameCell);
        row.appendChild(statusCell);
        row.appendChild(timeCell);
        rowsContainer.appendChild(row);
    });
}

function createCell(text) {
    const cell = document.createElement("td");
    cell.style.cssText = "padding:8px; text-align:center;";
    cell.textContent = text;
    return cell;
}

function statusColor(status) {
    switch (status) {
        case "Green":
            return "green";
        case "Yellow":
            return "yellow";
        case "Orange":
            return "orange";
        default:
            return "red";
    }
}

function setLastApiPost(value) {
    const lastApi = document.getElementById("last_api_post");
    if (!lastApi) {
        return;
    }
    lastApi.textContent = "Last API post: " + (value || new Date().toLocaleString());
}
