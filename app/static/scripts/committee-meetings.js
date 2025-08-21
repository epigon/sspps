let meetingsTable; // global so all handlers can access

$(document).ready(function () {
    const committeeId = $("#meetingsTable").data("ay-committee-id");

    meetingsTable = $('#meetingsTable').DataTable({
        columns: [
            { data: "title" },
            { data: "date" },
            { data: "location" },
            { data: "notes" },
            { data: "attendance", render: data => data }, // just return HTML
            { data: "actions", render: data => data, orderable: false, searchable: false }
        ],
        responsive: true,
        rowId: row => `meeting-${row.id}`
    });

    // Example: fetch JSON manually and redraw
    $.getJSON(`/committee_tracker/${committeeId}/meetings/json`, function (meetings) {
        redrawMeetingsTable(meetings);
    });

    function formatDateTime(dateStr, startTime, endTime) {
        const [year, month, day] = dateStr.split("-").map(Number);

        // Create Date objects for start and end
        const startParts = startTime.split(":").map(Number);
        const endParts = endTime.split(":").map(Number);

        const startDate = new Date(year, month - 1, day, startParts[0], startParts[1]);
        const endDate = new Date(year, month - 1, day, endParts[0], endParts[1]);

        function format12Hour(date) {
            let hours = date.getHours();
            const minutes = date.getMinutes().toString().padStart(2, "0");
            const ampm = hours >= 12 ? "PM" : "AM";
            hours = hours % 12 || 12; // convert 0 to 12
            return `${hours}:${minutes} ${ampm}`;
        }

        return `${month}/${day}/${year} ${format12Hour(startDate)} - ${format12Hour(endDate)}`;
    }


    // Add Meeting Modal
    $("#addMeetingButton").click(function () {
        $("#meetingForm")[0].reset();
        $("#meetingForm").find("[name='meeting_id']").val("");
        $(".modal-title").text("Add Meeting");
    });

    // Edit Meeting Modal
    $(document).on("click", ".edit-meeting-btn", function () {
        const data = $(this).data();
        const form = $("#meetingForm");
        form.find("[name='meeting_id']").val(data.id);
        form.find("[name='title']").val(data.title);
        form.find("[name='date']").val(data.date);
        form.find("[name='location']").val(data.location);
        form.find("[name='notes']").val(data.notes);
        $(".modal-title").text("Edit Meeting");
        $("#meetingModal").modal("show");
    });

    // Save Meeting (AJAX)
    $("#meetingForm").submit(function (e) {
        e.preventDefault();
        const formData = new FormData(this);
        $.ajax({
            url: "/committee_tracker/save_meeting",
            method: "POST",
            data: formData,
            processData: false,
            contentType: false,
            dataType: "json",
            success: function (data) {
                if (data.meetings) {
                    redrawMeetingsTable(data.meetings);
                }
                $("#meetingModal").modal("hide");
            },
            error: () => alert("Error saving meeting.")
        });
    });

    // Delete Meeting
    $(document).on("click", ".delete-meeting-btn", function () {
        if (!confirm("Are you sure you want to delete this meeting?")) return;
        const meetingId = $(this).data("id");
        $.ajax({
            url: `/committee_tracker/delete_meeting/${meetingId}`,
            method: "POST",
            success: function (data) {
                if (data.meetings) {
                    redrawMeetingsTable(data.meetings);
                }
            },
            error: () => alert("Error deleting meeting.")
        });
    });

    // Attendance Modal
    document.getElementById("attendanceModal").addEventListener("show.bs.modal", function (event) {
        const button = event.relatedTarget;
        const meetingId = button.getAttribute("data-meeting-id");
        const saveUrl = button.getAttribute("data-save-url");

        // Set the form action
        const form = document.getElementById("attendanceForm");
        form.action = saveUrl;

        document.getElementById("attendanceMeetingId").value = meetingId;

        const tbody = document.getElementById("attendanceModalBody");
        tbody.innerHTML = "";

        fetch(`/committee_tracker/${committeeId}/meeting/${meetingId}/attendance/json`)
            .then(res => res.json())
            .then(data => {
                const members = data.members || [];
                const attendance = data.attendance || {};

                members.forEach(member => {
                    const row = document.createElement("tr");

                    // Member Name
                    const nameCell = document.createElement("td");
                    nameCell.textContent = `${member.last_name}, ${member.first_name}`;
                    row.appendChild(nameCell);

                    // Status Buttons
                    const statusCell = document.createElement("td");
                    const btnGroup = document.createElement("div");
                    btnGroup.className = "btn-group me-2";
                    btnGroup.setAttribute("role", "group");

                    const hiddenInput = document.createElement("input");
                    hiddenInput.type = "hidden";
                    hiddenInput.name = `status_${member.id}`;
                    hiddenInput.value = attendance[member.id] || "";
                    statusCell.appendChild(hiddenInput);

                    const statuses = ["Present", "Absent", "Excused"];
                    const statusClasses = {
                        "Present": "btn-success",
                        "Absent": "btn-danger",
                        "Excused": "btn-secondary"
                    };

                    statuses.forEach(status => {
                        const btn = document.createElement("button");
                        btn.type = "button";
                        btn.className = "btn btn-outline-primary btn-sm";
                        btn.textContent = status;

                        if (attendance[member.id] === status) {
                            btn.classList.add("active", statusClasses[status]);
                            btn.classList.remove("btn-outline-primary");
                        }

                        btn.addEventListener("click", () => {
                            Array.from(btnGroup.children).forEach(sibling => {
                                sibling.classList.remove("active", "btn-success", "btn-danger", "btn-secondary");
                                sibling.classList.add("btn-outline-primary");
                            });
                            btn.classList.add("active", statusClasses[status]);
                            btn.classList.remove("btn-outline-primary");
                            hiddenInput.value = status;
                        });

                        btnGroup.appendChild(btn);
                    });

                    statusCell.appendChild(btnGroup);

                    // Clear Button
                    const clearBtn = document.createElement("button");
                    clearBtn.type = "button";
                    clearBtn.className = "btn btn-outline-secondary btn-sm";
                    clearBtn.textContent = "Clear";
                    clearBtn.addEventListener("click", () => {
                        Array.from(btnGroup.children).forEach(sibling => {
                            sibling.classList.remove("active", "btn-success", "btn-danger", "btn-secondary");
                            sibling.classList.add("btn-outline-primary");
                        });
                        hiddenInput.value = "";
                    });

                    statusCell.appendChild(clearBtn);
                    row.appendChild(statusCell);
                    tbody.appendChild(row);
                });
            })
            .catch(err => console.error(err));
    });

    // Save Attendance (AJAX)
    document.getElementById("attendanceForm").addEventListener("submit", function (e) {
        e.preventDefault();
        const formData = new FormData(this);

        fetch(this.action, {
            method: "POST",
            body: formData,
            headers: { "X-Requested-With": "XMLHttpRequest" }
        })
            .then(res => res.json())
            .then(data => {
                if (data.success && Array.isArray(data.meetings)) {
                    redrawMeetingsTable(data.meetings);
                }
                const modal = bootstrap.Modal.getInstance(document.getElementById("attendanceModal"));
                modal.hide();
            })
            .catch(err => console.error(err));
    });

    // Helper: redraw full table
    function redrawMeetingsTable(meetings) {

        const rows = meetings.map(meeting => {

            let attendanceHtml = "<ul class='list-unstyled mb-0'>";
            if (Array.isArray(meeting.attendance)) {
                meeting.attendance.forEach(att => {
                    if (!att.name || !att.status || att.status == "—") return;
                    console.log("att.status", att.status);
                    let badgeClass = att.status === 'Present' ? 'bg-success' :
                        att.status === 'Absent' ? 'bg-danger' :
                            'bg-secondary';
                    attendanceHtml += `<li>${att.name} - 
                                   <span class="badge ${badgeClass}">${att.status}</span></li>`;
                })
            }
            attendanceHtml += "</ul>";

            const actionsHtml = `
            <button class="btn btn-primary btn-sm record-attendance-btn"
                    data-bs-toggle="modal"
                    data-bs-target="#attendanceModal"
                    data-meeting-id="${meeting.id}"
                    data-save-url="/committee_tracker/save_attendance?meeting_id=${meeting.id}"
                    >Record Attendance</button>
            <button class="btn btn-warning btn-sm edit-meeting-btn"
                    data-id="${meeting.id}"
                    data-title="${meeting.title}" data-date="${meeting.date}"
                    data-location="${meeting.location}" data-notes="${meeting.notes}">Edit</button>
            <button class="btn btn-danger btn-sm delete-meeting-btn"
                    data-id="${meeting.id}">Delete</button>
        `;
            return {
                title: meeting.title,
                date: meeting.date,
                location: meeting.location,
                notes: meeting.notes,
                attendance: attendanceHtml,
                actions: actionsHtml
            };
        });
        meetingsTable.clear().rows.add(rows).draw(false);
    }
});