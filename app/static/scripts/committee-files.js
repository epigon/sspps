$(document).ready(function () {
    let selectedFiles = [];
    const allowedExtensions = ["pdf", "doc", "docx", "xls", "xlsx", "pages", "numbers", "key", "jpg", "jpeg", "png", "gif", "bmp", "svg", "webp", "ppt", "pptx"];

    let dropArea = $("#drop-area");
    let saveButton = $("#save-btn");
    let browseButton = $("#browse-btn");
    let fileInput = $("#file-input");
    let fileList = $("#file-list");
    let uploadForm = $("#upload-form");
    let uploadStatus = $("#upload-status");
    let filesTable = new $("#files-table").DataTable();

    // Load existing files
    function loadFiles() {
        $('.dt-input').addClass("me-1"); //add spacing to dt-input select
        let ay_committee_id = uploadForm.find('[name="ay_committee_id"]').val();
        $.ajax({
            url: `/committeetracker/${ay_committee_id}/uploaded_files`,
            type: "GET",
            success: function (response) {
                filesTable.clear();
                let allow_delete = response.allow_delete;
                $.each(response.files, function (index, file) {
                    let fileName = file.name.toLowerCase();
                    let fileUrl = `/static/uploads/${file.name}`;
                    let isImage = /\.(jpg|jpeg|png|gif|bmp|svg|webp)$/i.test(fileName);

                    let preview = isImage
                        ? `<img src="${fileUrl}" width="50" height="50"><br/><a href="${fileUrl}" target="_blank">Preview</a>`
                        : `<a href="${fileUrl}" target="_blank">Preview</a>`;

                    let deletebtn = ``
                    if (allow_delete){
                        deletebtn = `<button class="delete-file-btn btn btn-danger btn-sm" data-file-id="${file.id}" data-file-name="${file.name}">Delete</button>`
                    } 
                    filesTable.row.add([
                        file.name,
                        (file.size / 1024).toFixed(2) + " KB",
                        preview,
                        deletebtn
                    ]).draw(false);
                });
            }
        });
    }
    loadFiles(); // Load on page load

    // Drag & Drop Events
    dropArea.on("dragover", function (event) {
        event.preventDefault();
        dropArea.addClass("drag-over");
    });

    dropArea.on("dragleave", function () {
        dropArea.removeClass("drag-over");
    });

    dropArea.on("drop", function (event) {
        event.preventDefault();
        dropArea.removeClass("drag-over");
        handleFileSelection(event.originalEvent.dataTransfer.files);
    });

    // Browse Button
    browseButton.on("click", function () {
        fileInput.click();
    });

    // File Input Change Event
    fileInput.on("change", function (event) {
        handleFileSelection(event.target.files);
    });

    // Form Submit (AJAX Upload)
    uploadForm.on("submit", function (event) {
        event.preventDefault();
        let ay_committee_id = $("#upload-form").find('[name="ay_committee_id"]').val();
        if (selectedFiles.length === 0) return;

        let formData = new FormData();
        formData.append("ay_committee_id", ay_committee_id);
        selectedFiles.forEach(file => {
            formData.append("files", file);
        });

        $.ajax({
            url: "/committeetracker/upload",
            type: "POST",
            data: formData,
            contentType: false,
            processData: false,
            success: function (response) {
                uploadStatus.text(response.success).addClass("alert alert-success").removeClass("alert-danger");
                saveButton.prop("disabled", true).hide();
                selectedFiles = [];
                loadFiles(); // Refresh DataTable
                fileList.empty();
            },
            error: function (response) {
                uploadStatus.text(response.responseJSON.error).addClass("alert alert-danger").removeClass("alert-success");
            }
        });
    });

    // Function to Handle File Selection
    function handleFileSelection(files) {
        let validFiles = [];

        for (let file of files) {
            let fileExtension = file.name.split('.').pop().toLowerCase();
            if (allowedExtensions.includes(fileExtension)) {
                validFiles.push(file);
            } else {
                $("#uploadStatus").text(`Invalid file type: ${file.name}`).css("color", "red");
            }
        }

        if (validFiles.length > 0) {
            selectedFiles = selectedFiles.concat(validFiles); // Append new files
            updateFileList();
            saveButton.prop("disabled", false).show();
        }
    }

    // Function to Update File List
    function updateFileList() {
        fileList.empty();
        selectedFiles.forEach((file, index) => {
            fileList.append(`<p>${index + 1}. ${file.name}</p>`);
        });
    }

    // Delete File
    $(document).on("click", ".delete-file-btn", function () {
        let file_id = $(this).data("file-id");
        let file_name = $(this).data("file-name");
        let confirmed = confirm("Are you sure you want to delete " + file_name + "?")
        if (!confirmed) return;
        $.ajax({
            url: `/committeetracker/delete_file/${file_id}`,
            type: "POST",
            contentType: "application/json",
            success: function (response) {
                $('#upload-status').text(response.message).removeClass('alert-danger').addClass('alert alert-success');
                loadFiles(); // Refresh DataTable
            },
            error: function (response) {
                uploadStatus.text(response.responseJSON.error).css("color", "red");
            }
        });
    });
});