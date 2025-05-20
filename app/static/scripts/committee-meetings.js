$(document).ready(function () {

    let meetingsTable = new $("#meetingTable").DataTable();
    // Open modal for adding a meeting
    $("#addMeetingButton").click(function () {
        $('#meeting-status').text("").removeClass('alert alert-success alert-danger');
        let meetingForm = $("#meetingForm");
        $("#meetingForm").find("[name='meeting_id']").val("");
        $("#meetingForm").find("[name='title']").val("");
        $("#meetingForm").find("[name='date']").val("");
        $("#meetingForm").find("[name='start_time").val("");
        $("#meetingForm").find("[name='end_time").val("");
        $("#meetingForm").find("[name='location").val("");
        $("#meetingForm").find("[name='notes").val("");

        $(".modal-title").text("Add Meeting");
    });

    // Open modal for editing a meeting
    $(document).on("click", ".edit-meeting-btn", function () {
        $('#meeting-status').text("").removeClass('alert alert-success alert-danger');
        let meetingForm = $("#meetingForm");
        let meetingId = $(this).data("id");
        let title = $(this).data("title");
        let date = $(this).data("date");
        let startTime = $(this).data("start-time");
        let endTime = $(this).data("end-time");
        let location = $(this).data("location");
        let notes = $(this).data("notes");
        $("#meetingForm").find("[name='meeting_id']").val(meetingId);
        $("#meetingForm").find("[name='title']").val(title);
        $("#meetingForm").find("[name='date']").val(date);
        $("#meetingForm").find("[name='start_time").val(startTime);
        $("#meetingForm").find("[name='end_time").val(endTime);
        $("#meetingForm").find("[name='location").val(location);
        $("#meetingForm").find("[name='notes").val(notes);
        $(".modal-title").text("Edit Meeting");

        $("#meetingModal").modal("show");
    });

    // Submit the meeting form
    $("#meetingForm").submit(function (event) {
        event.preventDefault();

        let meetingId = $('#meeting-id').val(); // Get the member ID
        $.ajax({
            type: "POST",
            url: "/committeetracker/save_meeting",
            data: new FormData(this),
            processData: false,
            contentType: false,
            dataType: "json",
            success: function (response) {
                $('#meeting-status').text("Meeting saved successfully.").removeClass('alert-danger').addClass('alert alert-success');
                meetingsTable.clear();
                $.each(response.meetings, function (index, meeting) {
                    meetingsTable.row.add([
                        meeting.title,
                        meeting.date + " " + meeting.start_time + " - " + meeting.end_time,
                        meeting.location,
                        meeting.notes,
                        `<button class="btn btn-warning btn-sm edit-meeting-btn" data-id="${meeting.id}"
                                    data-title="${meeting.title}" data-date="${meeting.date}"
                                    data-start-time="${meeting.start_time}"
                                    data-end-time="${meeting.end_time}"
                                    data-location="${meeting.location}" data-notes="${meeting.notes}">Edit</button> 
                                    <button class="btn btn-danger btn-sm delete-meeting-btn"
                                    data-id="${meeting.id}">Delete</button>`
                    ]).draw(false);
                });
                $('#meetingModal').modal('hide');
            },
            error: function (error) {
                console.log(error);
                alert("Error saving meeting.");
                $('#addformResponseMessage').text(data.message).removeClass('alert-success').addClass('alert alert-danger');
            }
        });
    });

    // Delete meeting
    $(document).on("click", ".delete-meeting-btn", function () {
        $('#meeting-status').text("").removeClass('alert alert-success alert-danger');
        let meetingId = $(this).data("id");
        let deleteRow = $(this).parents("tr");
        if (confirm("Are you sure you want to delete this meeting?")) {
            $.ajax({
                type: "POST",
                url: `/committeetracker/delete_meeting/${meetingId}`,
                contentType: "application/json",
                success: function (response) {
                    meetingsTable
                        .row(deleteRow)
                        .remove()
                        .draw();
                    // deleteRow.remove();
                    // meetingsTable.draw(); // Update the row in DataTable
                    $('#meeting-status').text("Meeting successfully deleted.").removeClass('alert-danger').addClass('alert alert-success');
                },
                error: function (error) {
                    alert("Error deleting meeting.");
                }
            });
        }
    });
});