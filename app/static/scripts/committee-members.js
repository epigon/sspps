$(document).ready(function () {
    function displayYesNo(value) {
        return value ? "Yes" : "No";
    }

    // Initialize DataTable
    let table = new $('#memberTable').DataTable({
        pageLength: 10
    });

    $('.dt-input').addClass("me-1"); //add spacing to dt-input select

    $.fn.dataTable.ext.search.push(function (settings, data, dataIndex) {
        if (settings.nTable.id !== 'memberTable') {
            return true; // Skip if it's not the right table
        }
        if (!$('#toggleActive').prop('checked')) {
            return !data[6].toLowerCase().includes('deleted'); // Exclude "Deleted" (Actions column at index 4)
        }
        return true; // Show all if filter is off
    });

    table.draw();

    $('#toggleActive').on('click', function () {
        table.draw(); // Apply or reset the filter
    });

    function resetForm() {
        // $('#memberForm')[0].reset();
        $('#addformResponseMessage').html("").removeClass('alert alert-danger alert-success');
        $('#member-status').html("").removeClass('alert alert-danger alert-success');
        $(".is-invalid").removeClass("is-invalid");
        $('#memberForm').find('[name="employee_id"]').show();
        $("label[for='employee_id']").show();
    }
    // Open Modal for Adding Member
    $('#addMemberButton').on('click', function () {
        resetForm();
        $('#memberForm')[0].reset();

        $('#member-id').val(''); // Clear ID for new member
        $('#memberModalTitle').text("Add Member");
        $('#memberFormSubmitBtn').text("Add Member");

        // ✅ Preselect "Member" in member_role_id dropdown
        let roleSelect = $('#memberForm').find('[name="member_role_id"]');
        roleSelect.find('option').each(function () {
            if ($(this).text().trim().toLowerCase() === 'member') {
                $(this).prop('selected', true);
            }
        });
        
        $('#memberModal').modal('show');
    });

    // Open Modal for Editing Member
    $('#members-list').on('click', '.edit-btn', function () {
        resetForm();
        let memberId = $(this).data('id');
        let row = $(`tr[data-id='${memberId}']`);
        $('#member-id').val(memberId);  // Set ID for editing
        $('#memberModalTitle').text("Edit Member " + row.find('.employee-id').text());

        $('#memberFormSubmitBtn').text("Save Changes");

        // Populate fields with existing values
        $('#memberForm').find('[name="employee_id"]').val(row.find('.employee-id').data('employee-id')).hide();
        $("label[for='employee_id']").hide();
        $('#memberForm').find('[name="member_role_id"]').val(row.find('.member-role').data('member-role-id'));
        $('#memberForm').find('[name="start_date"]').val(row.find('.start-date').text());
        $('#memberForm').find('[name="end_date"]').val(row.find('.end-date').text());
        if (row.find('.voting').text().trim().toLowerCase() == "yes") {
            $('#memberForm').find('[name="voting"]').prop('checked', true);
        } else {
            $('#memberForm').find('[name="voting"]').prop('checked', false);
        }
        $('#memberForm').find('[name="notes"]').val(row.find('.notes').text());

        $('#memberModal').modal('show');
    });

    // Handle Form Submission for Add/Edit
    $('#memberForm').on('submit', function (event) {
        event.preventDefault();
        $(".table-success").removeClass("table-success");
        let memberId = $('#member-id').val(); // Get the member ID

        let url = memberId ? `/committee_tracker/edit_member/${memberId}` : "/committee_tracker/add_member";
        let method = "POST";

        $.ajax({
            url: url,
            type: method,
            data: new FormData(this),
            processData: false,
            contentType: false,
            dataType: "json",
            success: function (data) {
                if (data.success) {
                    if (!memberId) {
                        // Adding new member
                        let row = table.row.add([
                            data.member.user,
                            data.member.member_role,
                            data.member.start_date,
                            data.member.end_date,
                            displayYesNo(data.member.voting),
                            `<button class="btn btn-warning btn-sm edit-btn" data-bs-toggle="modal" data-bs-target="#memberModal" data-id="${data.member.id}">Edit</button> 
                                <button class="btn btn-danger btn-sm delete-btn" data-bs-toggle="modal" data-bs-target="#deleteMemberModal" data-id="${data.member.id}">Delete</button>`,
                            data.member.notes
                        ]).draw().node();

                        $(row).attr('data-id', data.member.id).addClass('table-success');

                        $(row).find('td').eq(0).attr('data-employee-id', data.member.employee_id).addClass("employee-id");    // First column
                        $(row).find('td').eq(1).attr('data-member-role-id', data.member.member_role_id).addClass("member-role");  // Second column
                        $(row).find('td').eq(2).addClass("start-date"); // 3rd column
                        $(row).find('td').eq(3).addClass("end-date"); // 4th column
                        $(row).find('td').eq(4).addClass("voting"); // 5th column
                        $(row).find('td').eq(5).addClass("actions"); // 6th column
                        $(row).find('td').eq(6).addClass("notes"); // 7th column
                        // Redraw the table to refresh sorting
                        table.row(row).invalidate().draw(false); // False prevents pagination reset
                    } else {
                        // Editing existing member
                        let row = $(`tr[data-id='${memberId}']`);
                        let rowIndex = table.row(row).index();
                        let rowData = table.row(rowIndex).data();

                        rowData[1] = data.member.member_role;
                        rowData[2] = data.member.start_date;
                        rowData[3] = data.member.end_date;
                        rowData[4] = displayYesNo(data.member.voting);
                        rowData[5] = rowData[5];
                        rowData[6] = data.member.notes;

                        row.find('.member-role').data('member-role-id', data.member.member_role_id);
                        row.attr('data-id', data.member.id).addClass('table-success');
                        table.row(rowIndex).data(rowData).draw(false);
                    }

                    $('#memberModal').modal('hide');
                    $('#member-status').text(data.message).removeClass('alert-danger').addClass('alert alert-success');
                } else {
                    $('#addformResponseMessage').text(data.message).removeClass('alert-success').addClass('alert alert-danger');
                }
            },
            error: function (jqXHR) {
                try {
                    let response = JSON.parse(jqXHR.responseText);
                    $('#addformResponseMessage').html(response.message.join('<br/>')).removeClass('alert-success').addClass('alert alert-danger');
                    $.each(response.errors, function (index, field) {
                        $('#memberForm').find(`[name="${field}"]`).addClass("is-invalid");
                    });
                } catch (e) {
                    console.error("Failed to parse error response:", jqXHR.responseText);
                }
            }
        });
    });

    // Populate Delete Modal
    $('#members-list').on('click', '.delete-btn', function () {
        $('#deleteMemberForm')[0].reset();
        $('#deleteFormResponseMessage').text("");
        let memberId = $(this).data('id');
        let row = $(`tr[data-id='${memberId}']`);
        $('#delete-member-id').val(memberId);
        $('#deleteMember').text(row.find('.employee-id').text());
        $('#deleteMemberForm').find('[name="notes"]').val(row.find('.notes').text().trim());
        $(".table-success").removeClass("table-success");
    });

    // Handle Delete Member
    $('#deleteMemberForm').on('submit', function (event) {
        event.preventDefault();
        let memberId = $('#delete-member-id').val();
        $.ajax({
            url: `/committee_tracker/delete_member/${memberId}`,
            type: "POST",
            data: new FormData(this),
            processData: false,
            contentType: false,
            dataType: "json",
            success: function (data) {
                if (data.success) {
                    $('#deleteMemberModal').modal('hide');
                    let row = $(`tr[data-id='${memberId}']`);
                    let rowIndex = table.row(row).index(); // Get the row index
                    let rowData = table.row(rowIndex).data();
                    rowData[5] = ``;  // Update actions column
                    rowData[6] = `Deleted: ${data.member.delete_date} (${data.member.notes})`;  // Update notes column
                    $(row).addClass("table-success");
                    $(row).find('td').addClass("text-muted fst-italic");

                    table.row(rowIndex).data(rowData).draw(false); // Update the row in DataTable

                    $('#member-status').text(data.message).removeClass('alert-danger').addClass('alert alert-success');
                    $(`.delete-btn[data-id='${memberId}'], .edit-btn[data-id='${memberId}']`).addClass("d-none");

                } else {
                    $('#member-status').text(data.message).removeClass('alert-success').addClass('alert alert-danger');
                }
            },
            error: function (error) {
                console.error("Error:", error);
            }
        });
    });
});