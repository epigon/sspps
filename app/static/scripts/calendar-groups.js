function setupDragAndDrop() {
    // Add delete button to existing courses in groups if missing
    document.querySelectorAll(".calendar-group .course").forEach(el => {
        if (!el.querySelector(".btn-delete-course")) {
            const deleteBtn = document.createElement("span");
            deleteBtn.className = "text-danger btn-delete-course ms-auto";
            deleteBtn.style.cursor = "pointer";
            deleteBtn.style.fontWeight = "bold";
            deleteBtn.title = "Remove";
            deleteBtn.textContent = "×";

            // Use flex container or add styles so button is at row end
            el.classList.add("d-flex", "align-items-center");
            const firstChild = el.firstChild;
            if (firstChild) {
                // Wrap text in a span for spacing
                const textSpan = document.createElement("span");
                textSpan.className = "flex-grow-1";
                textSpan.textContent = el.textContent.trim();
                el.textContent = "";
                el.appendChild(textSpan);
            }
            el.appendChild(deleteBtn);
        }
    });

    document.querySelectorAll(".course").forEach(el => {
        if (!el.dataset.bound) {
            el.addEventListener("dragstart", e => {
                const sourceGroup = el.closest(".calendar-group");
                e.dataTransfer.setData("text/plain", JSON.stringify({
                    id: el.dataset.id,
                    name: el.dataset.name,
                    source: el.closest("#course-list") ? "main" : "group",
                    sourceGroupId: sourceGroup ? sourceGroup.id : null
                }));
            });
            el.dataset.bound = "true";
        }
    });

    document.querySelectorAll(".calendar-group").forEach(group => {
        group.addEventListener("dragover", e => e.preventDefault());

        group.addEventListener("drop", e => {
            e.preventDefault();
            const data = JSON.parse(e.dataTransfer.getData("text/plain"));
            const fromMain = data.source === "main";

            const exists = Array.from(group.querySelectorAll(".course"))
                .some(el => el.dataset.id === data.id);
            if (exists) return;

            const newEl = document.createElement("div");
            newEl.className = "course d-flex align-items-center";
            newEl.dataset.id = data.id;
            newEl.dataset.name = data.name;
            newEl.draggable = true;

            newEl.innerHTML = `
                <span class="flex-grow-1">${data.name}</span>
                <span class="text-danger btn-delete-course ms-auto" style="cursor: pointer; font-weight: bold;" title="Remove">&times;</span>
            `;
            group.appendChild(newEl);

            setupDragAndDrop();

            if (!fromMain && data.sourceGroupId) {
                const sourceGroup = document.getElementById(data.sourceGroupId);
                if (sourceGroup && sourceGroup !== group) {
                    sourceGroup.querySelectorAll(".course").forEach(courseEl => {
                        if (courseEl.dataset.id === data.id) {
                            courseEl.remove();
                        }
                    });
                }
            }
        });
    });

    // Bind delete buttons click handlers
    document.querySelectorAll(".btn-delete-course").forEach(button => {
        if (!button.dataset.bound) {
            button.addEventListener("click", e => {
                e.stopPropagation();
                e.target.closest(".course").remove();
            });
            button.dataset.bound = "true";
        }
    });
}

setupDragAndDrop();

document.getElementById("course-search").addEventListener("input", function () {
    const search = this.value.toLowerCase();
    document.querySelectorAll("#course-list .course").forEach(el => {
        el.style.display = el.textContent.toLowerCase().includes(search) ? "" : "none";
    });
});

function saveSelection() {
    const responseEl = document.getElementById("formResponseMessage");

    // Disable only the clicked button
    const buttons = document.querySelectorAll(".save-selection-btn");
    buttons.forEach(btn => {
        btn.disabled = true;
        btn.dataset.originalText = btn.textContent;
        btn.textContent = "Saving...";
    });

    const data = {};
    document.querySelectorAll(".calendar-group").forEach(group => {
        const groupId = group.id;
        const courses = [];
        group.querySelectorAll(".course").forEach(course => {
            courses.push({
                id: course.dataset.id,
                name: course.dataset.name
            });
        });
        if (!group.classList.contains("untracked")) {
            data[groupId] = courses;
        }
    });

    fetch("/calendars/save_selections", {
        method: "POST",
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    }).then(res => res.json())
        .then(msg => {
            const responseEl = document.getElementById("formResponseMessage");
            responseEl.classList.remove("d-none", "alert-success", "alert-danger");

            if (msg.error) {
                responseEl.classList.add("alert-danger");
                responseEl.textContent = msg.error;
            } else {
                responseEl.classList.add("alert-success");
                responseEl.textContent = msg.message;
            }
        })
    .catch(err => {
        responseEl.classList.remove("d-none", "alert-success");
        responseEl.classList.add("alert-danger");
        responseEl.textContent = "An unexpected error occurred.";
        console.error(err);
    })
    .finally(() => {
        // Re-enable buttons and restore text
        buttons.forEach(btn => {
            btn.disabled = false;
            btn.textContent = btn.dataset.originalText || "Save";
        });
    });
}

function refreshCalendars() {
    const responseEl = document.getElementById("formResponseMessage");

    // Disable only the clicked button
    const buttons = document.querySelectorAll(".refresh-btn");
    buttons.forEach(btn => {
        btn.disabled = true;
        btn.dataset.originalText = btn.textContent;
        btn.textContent = "Updating...";
    });

    fetch("/calendars/generate_scheduled_ics", {
        method: "POST",
        headers: { 'Content-Type': 'application/json' }
    }).then(res => res.json())
        .then(msg => {
            const responseEl = document.getElementById("formResponseMessage");
            responseEl.classList.remove("d-none", "alert-success", "alert-danger");

            if (msg.error) {
                responseEl.classList.add("alert-danger");
                responseEl.textContent = msg.error;
            } else {
                responseEl.classList.add("alert-success");
                responseEl.textContent = msg.message;
            }
        })
    .catch(err => {
        responseEl.classList.remove("d-none", "alert-success");
        responseEl.classList.add("alert-danger");
        responseEl.textContent = "An unexpected error occurred.";
        console.error(err);
    })
    .finally(() => {
        // Re-enable buttons and restore text
        buttons.forEach(btn => {
            btn.disabled = false;
            btn.textContent = btn.dataset.originalText || "Refresh Calendar Files";
        });
    });
}